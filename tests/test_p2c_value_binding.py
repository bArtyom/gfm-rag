import hashlib

import pytest

from scripts.text2sql import predicate_value_binding as binding


SCHEMA = {'orders': {'status': 'o_status', 'amount': 'o_amount', 'id': 'o_id'},
          'archive': {'status': 'a_status', 'id': 'a_id'}}


def key(value, kind='string'):
    return hashlib.sha256(f'{kind}:{value}'.encode()).hexdigest()


def test_alias_and_literal_position_bind_to_correct_base_column():
    result = binding.bind_sql_literals("SELECT * FROM orders AS o WHERE 'X' = o.status AND o.amount >= -(2)", SCHEMA)
    assert result[key('x')]['node_ids'] == ['o_status']
    assert result[key('-2', 'number')]['node_ids'] == ['o_amount']
    assert result[key('x')]['unresolved_reasons'] == []


def test_unqualified_unique_column_resolves_but_ambiguous_column_is_unknown():
    good = binding.bind_sql_literals("SELECT * FROM orders JOIN archive ON orders.id=archive.id WHERE amount > 7", SCHEMA)
    assert good[key('7', 'number')]['node_ids'] == ['o_amount']
    ambiguous = binding.bind_sql_literals("SELECT * FROM orders JOIN archive ON orders.id=archive.id WHERE status='X'", SCHEMA)
    assert ambiguous[key('x')]['node_ids'] == []
    assert ambiguous[key('x')]['unresolved_reasons']


def test_subquery_alias_and_cte_passthrough_trace_to_base_column():
    result = binding.bind_sql_literals("WITH c AS (SELECT status AS code FROM orders) SELECT * FROM c WHERE code='X'", SCHEMA)
    assert result[key('x')]['node_ids'] == ['o_status']
    nested = binding.bind_sql_literals("SELECT * FROM (SELECT status AS code FROM orders) q WHERE q.code='X'", SCHEMA)
    assert nested[key('x')]['node_ids'] == ['o_status']


def test_computed_target_and_derived_aggregation_remain_unresolved():
    transformed = binding.bind_sql_literals("SELECT * FROM orders WHERE lower(status)='x'", SCHEMA)
    assert transformed[key('x')]['node_ids'] == []
    assert transformed[key('x')]['unresolved_reasons']
    derived = binding.bind_sql_literals("SELECT * FROM (SELECT max(amount) AS a FROM orders) q WHERE q.a>5", SCHEMA)
    assert derived[key('5', 'number')]['node_ids'] == []
    assert derived[key('5', 'number')]['unresolved_reasons']


def test_in_between_and_repeated_constant_keep_occurrence_specific_columns():
    result = binding.bind_sql_literals("SELECT * FROM orders o JOIN archive a ON o.id=a.id WHERE o.status IN ('X','Y') AND a.status='X' AND o.amount BETWEEN 2 AND 5", SCHEMA)
    assert result[key('x')]['node_ids'] == ['a_status', 'o_status']
    assert result[key('x')]['occurrences'] == 2
    assert result[key('y')]['node_ids'] == ['o_status']
    assert result[key('2', 'number')]['node_ids'] == ['o_amount']
    assert result[key('5', 'number')]['node_ids'] == ['o_amount']


def test_correlated_reference_uses_outer_scope_and_inner_alias_shadowing():
    result = binding.bind_sql_literals("SELECT * FROM orders o WHERE EXISTS (SELECT 1 FROM archive a WHERE a.id=o.id AND o.status='X' AND a.status='Y')", SCHEMA)
    assert result[key('x')]['node_ids'] == ['o_status']
    assert result[key('y')]['node_ids'] == ['a_status']
    assert key('1', 'number') not in result


def test_function_parameters_limit_and_patterns_do_not_create_bindings():
    result = binding.bind_sql_literals("SELECT * FROM orders WHERE strftime('%Y', status)='2020' AND status LIKE 'A%' LIMIT 3", SCHEMA)
    assert set(result) == {key('2020')}
    assert result[key('2020')]['unresolved_reasons']


def test_projection_literal_expansion_does_not_create_false_predicate_binding():
    result = binding.bind_sql_literals("SELECT 'X' AS code FROM orders WHERE code='X'", SCHEMA)
    assert result[key('x')]['node_ids'] == []
    assert result[key('x')]['unresolved_reasons']


def test_quoted_case_insensitive_sqlite_identifiers_and_alias_shadowing():
    result = binding.bind_sql_literals('SELECT * FROM "ORDERS" o WHERE EXISTS (SELECT 1 FROM archive o WHERE o.status=\'X\')', SCHEMA)
    assert result[key('x')]['node_ids'] == ['a_status']


def test_unused_cte_does_not_shadow_correlated_outer_table_alias():
    result = binding.bind_sql_literals("WITH o AS (SELECT status FROM archive) SELECT * FROM orders o WHERE EXISTS (SELECT 1 WHERE o.status='X')", SCHEMA)
    assert result[key('x')]['node_ids'] == ['o_status']


def test_catalog_keeps_global_column_index_and_excludes_wildcard():
    from scripts.text2sql.run_p2c_value_binding import schema_catalog
    schema = {'db_id': 'synthetic', 'table_names_original': ['T'],
              'column_names_original': [(-1, '*'), (0, 'code'), (0, 'id')]}
    assert schema_catalog(schema) == {'T': {'code': 'column:synthetic:1', 'id': 'column:synthetic:2'}}


def test_runner_rejects_closed_registration_or_unregistered_path():
    from argparse import Namespace
    from pathlib import Path
    from scripts.text2sql import run_p2c_value_binding as runner
    config = {'experiment_id': runner.EXPERIMENT_ID, 'status': 'completed',
              'run_ids': {'smoke': 's'}, 'private_output_dirs': {'smoke': '/frozen/output'}}
    args = Namespace(mode='smoke', run_id='s', output_dir=Path('/different/output'))
    with pytest.raises(RuntimeError, match='closed'):
        runner.validate_registration(config, args)
    config['status'] = 'preregistered_not_run'
    with pytest.raises(RuntimeError, match='identity/path'):
        runner.validate_registration(config, args)


@pytest.mark.parametrize('nodes,unknown,matching,want', (
    (['o_status'], [], ['o_status'], 'binding_supported'),
    (['a_status'], [], ['o_status'], 'binding_mismatch'),
    (['a_status'], ['transformed_target'], ['o_status'], 'binding_unresolved'),
    (['o_status'], ['transformed_target'], ['o_status'], 'binding_supported'),
))
def test_overlap_requires_same_node_and_mismatch_requires_no_unknowns(nodes, unknown, matching, want):
    assert binding.classify_binding({'node_ids': nodes, 'unresolved_reasons': unknown}, matching) == want
