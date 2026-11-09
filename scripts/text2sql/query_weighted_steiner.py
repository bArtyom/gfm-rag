"""Question-conditioned FK costs; prediction helpers accept no reference labels."""
from __future__ import annotations

import math
import networkx as nx
import numpy as np
from steiner_solvers import solve_steiner


def relation_descriptor(schema, constraint):
    columns = schema['column_names_original']
    tables = schema['table_names_original']
    pairs = [f'{tables[columns[a][0]]}.{columns[a][1]} = {tables[columns[b][0]]}.{columns[b][1]}'
             for a, b in constraint['pairs']]
    if not pairs:
        raise ValueError('Empty FK constraint')
    return 'Foreign key relationship: ' + ' AND '.join(pairs) + '.'


def relation_costs(query, vectors):
    query = np.asarray(query, dtype=np.float64)
    vectors = np.asarray(vectors, dtype=np.float64)
    if query.ndim != 1 or vectors.ndim != 2 or vectors.shape[1] != len(query):
        raise ValueError('Embedding dimension mismatch')
    norms = np.linalg.norm(vectors, axis=1)
    qnorm = np.linalg.norm(query)
    if not np.isfinite(query).all() or not np.isfinite(vectors).all() or qnorm <= 0 or (norms <= 0).any():
        raise ValueError('Invalid embedding')
    similarity = np.clip(vectors @ query / (norms * qnorm), -1., 1.)
    return 1. + (1. - similarity) / 2.


def weighted_graph(table_count, constraints, costs):
    if len(constraints) != len(costs):
        raise ValueError('Constraint/cost count mismatch')
    graph = nx.Graph()
    graph.add_nodes_from(range(table_count))
    chosen = {}
    seen = set()
    for constraint, raw in zip(constraints, costs):
        cost = float(raw)
        if not math.isfinite(cost) or cost < 0:
            raise ValueError('Invalid cost')
        if constraint['id'] in seen:
            raise ValueError('Duplicate constraint ID')
        seen.add(constraint['id'])
        a, b = sorted([constraint['source_table'], constraint['target_table']])
        if a not in graph or b not in graph:
            raise ValueError('Unknown endpoint')
        if a == b:
            continue
        key = (a, b)
        previous = chosen.get(key)
        if previous is None or (cost, constraint['id']) < (graph[a][b]['weight'], previous['id']):
            graph.add_edge(a, b, weight=cost)
            chosen[key] = constraint
    return graph, chosen


def predict(schema, constraints, ranking, query, vectors, seed_count=3):
    seeds = sorted(ranking[:seed_count])
    if len(set(seeds)) != seed_count or len(ranking) != len(schema['table_names_original']):
        raise ValueError('Incomplete or duplicate ranking')
    costs = relation_costs(query, vectors)
    unit, unit_ids = weighted_graph(len(ranking), constraints, np.ones(len(constraints)))
    weighted, weighted_ids = weighted_graph(len(ranking), constraints, costs)
    if set(unit.edges) != set(weighted.edges) or set(unit) != set(weighted):
        raise RuntimeError('Topology changed')
    arms = {}
    for name, graph, identities in [('unit', unit, unit_ids), ('weighted', weighted, weighted_ids)]:
        result = solve_steiner(graph, seeds, 'mehlhorn')
        selected = graph.edge_subgraph([tuple(e) for e in result['edges']]).copy()
        selected.add_nodes_from(result['nodes'])
        if not set(seeds) <= set(selected) or not nx.is_forest(selected):
            raise RuntimeError('Invalid solver output')
        for comp in nx.connected_components(graph):
            terminals = sorted(set(comp) & set(seeds))
            if terminals and any(not nx.has_path(selected, terminals[0], t) for t in terminals):
                raise RuntimeError('Failed to connect connectable seeds')
        actual = sum(graph[a][b]['weight'] for a, b in result['edges'])
        if not math.isclose(actual, result['cost'], abs_tol=1e-9):
            raise RuntimeError('Objective mismatch')
        result['constraint_ids'] = [identities[tuple(sorted(e))]['id'] for e in result['edges']]
        arms[name] = result
    arms['dense'] = {'nodes': sorted(ranking[:len(arms['weighted']['nodes'])])}
    bridges = {tuple(sorted(e)) for e in nx.bridges(unit)}
    return {'seeds': seeds, 'ranking': ranking, 'arms': arms,
            'alternative_route': any(tuple(sorted(e)) not in bridges for e in arms['unit']['edges']),
            'relation_costs': costs.tolist()}
