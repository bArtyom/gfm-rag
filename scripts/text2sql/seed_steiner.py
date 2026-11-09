"""Schema adaptation around an unchanged external GRAST-SQL Steiner helper.

Upstream code is loaded at runtime and is not vendored. Metadata and prediction
functions accept no question labels. Full table schemas preserve FK constraints;
the returned schema is context for a generator, not a prescribed SQL join plan.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from pathlib import Path
import sqlite3

import networkx as nx


def load_upstream(path=None):
    path = Path(path or os.environ['GRAST_SOURCE'])
    source = path / 'modules/steiner_tree_spanner/steiner.py'
    spec = importlib.util.spec_from_file_location('external_grast_steiner', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rank_seed_tables(schema, nodes, scores, seed_count, source='table'):
    if len(nodes) != len(scores) or seed_count < 1 or source not in {'table', 'column'}:
        raise ValueError('Invalid seed input')
    table_scores = {i: -math.inf for i in range(len(schema['table_names_original']))}
    for node, raw in zip(nodes, scores):
        score = float(raw)
        if not math.isfinite(score):
            raise ValueError('Nonfinite similarity')
        if node['node_type'] != source:
            continue
        identifier = int(node['node_id'].rsplit(':', 1)[-1])
        tid = identifier if source == 'table' else schema['column_names_original'][identifier][0]
        if tid >= 0:
            table_scores[tid] = max(table_scores[tid], score)
    eligible = [t for t, score in table_scores.items() if math.isfinite(score)]
    if len(eligible) < min(seed_count, len(table_scores)):
        raise ValueError('Too few eligible seed tables')
    return sorted(eligible, key=lambda t: (-table_scores[t], t))


def quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def read_constraints(schema, db_path):
    """Read entire SQLite FK constraint identities, including ordered composites."""
    tables = schema['table_names_original']
    table_ids = {name.casefold(): i for i, name in enumerate(tables)}
    columns = {(t, name.casefold()): i for i, (t, name) in enumerate(schema['column_names_original']) if t >= 0}
    uri = Path(db_path).resolve().as_uri() + '?mode=ro&immutable=1'
    connection = sqlite3.connect(uri, uri=True)
    result = []
    try:
        connection.execute('PRAGMA query_only=ON')
        for tid, table in enumerate(tables):
            grouped = {}
            for row in connection.execute(f'PRAGMA foreign_key_list({quote(table)})'):
                grouped.setdefault(row[0], []).append(row)
            for fk_id, rows in sorted(grouped.items()):
                rows.sort(key=lambda row: row[1])
                target = table_ids[rows[0][2].casefold()]
                pk = sorted((r for r in connection.execute(f'PRAGMA table_info({quote(tables[target])})') if r[5]), key=lambda r: r[5])
                pairs = []
                for row in rows:
                    target_column = row[4] if row[4] is not None else pk[row[1]][1]
                    pairs.append([columns[(tid, row[3].casefold())], columns[(target, target_column.casefold())]])
                result.append({'id': f'fk:{tid}:{fk_id}', 'source_table': tid, 'target_table': target, 'pairs': pairs})
    finally:
        connection.close()
    return result


def connect_schema(schema, constraints, seeds, upstream):
    seeds = sorted(set(seeds))
    if any(t < 0 or t >= len(schema['table_names_original']) for t in seeds):
        raise ValueError('Unknown seed table')
    graph = nx.Graph()
    representative = {}
    for cid, (tid, _) in enumerate(schema['column_names_original']):
        if tid >= 0:
            node = f't{tid:06d}.c{cid:06d}'
            graph.add_node(node)
            representative.setdefault(tid, node)
    table_graph = nx.Graph()
    table_graph.add_nodes_from(range(len(schema['table_names_original'])))
    for constraint in constraints:
        for a, b in constraint['pairs']:
            ta = schema['column_names_original'][a][0]
            tb = schema['column_names_original'][b][0]
            graph.add_edge(f't{ta:06d}.c{a:06d}', f't{tb:06d}.c{b:06d}')
        table_graph.add_edge(constraint['source_table'], constraint['target_table'])
    closure = upstream.get_steiner_subgraph(graph, [representative[t] for t in seeds])
    selected = set(seeds) | {int(n.split('.')[0][1:]) for n in closure.nodes}
    verify_seed_connectivity(table_graph, seeds, selected)
    seed_components = sum(bool(set(comp) & set(seeds)) for comp in nx.connected_components(table_graph))
    # Carry every legitimate FK among retained tables, not a single guessed role.
    retained_constraints = [c for c in constraints if c['source_table'] in selected and c['target_table'] in selected]
    return {'tables': sorted(selected), 'bridge_tables': sorted(selected - set(seeds)),
            'constraints': retained_constraints, 'connected': seed_components <= 1,
            'seed_components': seed_components}


def verify_seed_connectivity(table_graph, seeds, selected):
    """Reject upstream swallowed solver failures while allowing genuine forests."""
    retained = table_graph.subgraph(selected)
    for comp in nx.connected_components(table_graph):
        terminals = sorted(set(comp) & set(seeds))
        if terminals and any(not nx.has_path(retained, terminals[0], t) for t in terminals):
            raise RuntimeError('Upstream closure failed to connect connectable seeds')


def serialize_schema(schema, selected_tables, constraints):
    selected = set(selected_tables)
    lines = []
    columns = schema['column_names_original']
    for tid in sorted(selected):
        defs = [f'  {quote(name)} {schema["column_types"][cid]}' for cid, (owner, name) in enumerate(columns) if owner == tid]
        primary_ids = [cid for entry in schema['primary_keys']
                       for cid in ([entry] if isinstance(entry, int) else entry)]
        pk = [quote(columns[c][1]) for c in primary_ids if columns[c][0] == tid]
        if pk:
            defs.append('  PRIMARY KEY (' + ', '.join(pk) + ')')
        for c in constraints:
            if c['source_table'] == tid and c['target_table'] in selected:
                left = ', '.join(quote(columns[a][1]) for a, _ in c['pairs'])
                right = ', '.join(quote(columns[b][1]) for _, b in c['pairs'])
                defs.append(f'  FOREIGN KEY ({left}) REFERENCES {quote(schema["table_names_original"][c["target_table"]])} ({right})')
        lines.append('CREATE TABLE ' + quote(schema['table_names_original'][tid]) + ' (\n' + ',\n'.join(defs) + '\n);')
    return '\n'.join(lines)


def reference_tables(sql, schema):
    """Evaluation only: physical sources, resolving CTE/subquery aliases by scope."""
    import sqlglot
    from sqlglot import exp
    from sqlglot.optimizer.scope import traverse_scope

    lookup = {name.casefold(): i for i, name in enumerate(schema['table_names_original'])}
    tree = sqlglot.parse_one(sql, read='sqlite')
    found = set()
    for scope in traverse_scope(tree):
        for _, source in scope.sources.items():
            if isinstance(source, exp.Table):
                if source.name.casefold() not in lookup:
                    raise ValueError('Unmapped physical table')
                found.add(lookup[source.name.casefold()])
    if not found:
        raise ValueError('No physical tables in reference')
    return found


def choose_split(rows, seed, smoke_count=5, per_database=4):
    identities = [(str(r['db_id']), int(r['question_id'])) for r in rows]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate question identity')
    ordered = sorted(identities, key=lambda key: hashlib.sha256(f'{seed}|{key[0]}|{key[1]}'.encode()).hexdigest())
    smoke = ordered[:smoke_count]
    counts, pilot = {}, []
    for key in ordered[smoke_count:]:
        db = key[0]
        if counts.get(db, 0) < per_database:
            pilot.append(key)
            counts[db] = counts.get(db, 0) + 1
    return {'smoke': sorted(smoke), 'pilot': sorted(pilot)}
