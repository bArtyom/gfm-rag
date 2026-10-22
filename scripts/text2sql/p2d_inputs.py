"""Frozen sampling and generation messages. Reference SQL never enters messages."""
import hashlib
import json
import random

import sqlglot
from sqlglot import exp

SYSTEM = ('You are a SQLite SQL expert. Generate exactly one read-only SELECT query '
          'for the question using only the supplied schema and evidence. Return SQL '
          'only, without explanations. Do not invent tables or columns. Schema '
          'entries are table and column descriptions; Values fields are metadata.')


def digest_object(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def messages(question, evidence, context):
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': f'Database schema context:\n{context}\n\nQuestion: {question}\nEvidence: {evidence}\n\nSQL:'}]


def contexts(row, r0, r1):
    selected = {arm: row['arms'][arm]['budgets']['1024']['selected_ids'] for arm in ('V00', 'V01')}
    return {'E0': {'node_ids': selected['V00'], 'text': '\n'.join(r0[node] for node in selected['V00'])},
            'E1': {'node_ids': selected['V01'], 'text': '\n'.join(r1[node] for node in selected['V01'])},
            'E2': {'node_ids': selected['V00'], 'text': '\n'.join(r1[node] for node in selected['V00'])}}


def predicate_kinds(sql):
    tree = sqlglot.parse_one(sql, read='sqlite')
    return tuple(sorted({node.key for node in tree.find_all(exp.Predicate)}))


def feature(raw, question, previous):
    label = question['label']
    return (raw['db_id'], predicate_kinds(raw['SQL']), len(label['gold_table_ids']),
            len(label['gold_column_ids']), bool(previous['arms']['V00']['budgets']['1024']['complete']))


def match_controls(priority_ids, features, seed):
    rng = random.Random(seed)
    pools = {}
    for qid in sorted(features):
        if qid not in priority_ids:
            pools.setdefault(features[qid], []).append(qid)
    for candidates in pools.values():
        rng.shuffle(candidates)
    pairs, gaps = [], []
    for qid in priority_ids:
        pool = pools.get(features[qid], [])
        if pool:
            pairs.append((qid, pool.pop()))
        else:
            gaps.append(qid)
    return pairs, gaps


def predicate_diagnostics(predicted_sql, reference_sql, schema):
    """Lexical/direct AST diagnostics, never semantic correctness labels."""
    from scripts.text2sql.audit_p2c_values_risk import extract_predicate_literals
    from scripts.text2sql.predicate_value_binding import bind_sql_literals
    catalog = {table: {} for table in schema['table_names_original']}
    for index, (table_index, column) in enumerate(schema['column_names_original']):
        if table_index >= 0:
            catalog[schema['table_names_original'][table_index]][column] = f"column:{schema['db_id']}:{index}"
    try:
        predicted = extract_predicate_literals(predicted_sql)[0]
        reference = extract_predicate_literals(reference_sql)[0]
        p, r = [{(row['kind'], row['value']) for row in values} for values in (predicted, reference)]
        pb, rb = [bind_sql_literals(sql, catalog) for sql in (predicted_sql, reference_sql)]
        unknown = any(value['unresolved_reasons'] for bound in (pb, rb) for value in bound.values())
        pairs = [{(key, node) for key, value in bound.items() for node in value['node_ids']} for bound in (pb, rb)]
        return {'status': 'ok', 'reference_has_direct_literals': bool(r), 'direct_literal_set_exact': p == r,
                'direct_column_literal_pairs_exact': None if unknown else pairs[0] == pairs[1],
                'predicate_kind_set_exact': predicate_kinds(predicted_sql) == predicate_kinds(reference_sql)}
    except (sqlglot.errors.SqlglotError, ValueError, KeyError, AttributeError, TypeError):
        return {'status': 'unresolved', 'reference_has_direct_literals': None,
                'direct_literal_set_exact': None, 'direct_column_literal_pairs_exact': None, 'predicate_kind_set_exact': None}
