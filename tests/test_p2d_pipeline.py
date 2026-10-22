from scripts.text2sql import p2d_sql_context_eval as p


def test_extraction_removes_only_registered_wrappers():
    assert p.extract_sql('```sql\nSELECT 1;\n```') == 'SELECT 1;'
    assert p.extract_sql('SQL: SELECT 1') == 'SELECT 1'
    assert p.extract_sql('Here is SQL: SELECT 1') == 'Here is SQL: SELECT 1'


def test_empty_results_with_different_projection_width_are_incorrect():
    left = {'status': 'ok', 'rows': [], 'columns': ['a']}
    right = {'status': 'ok', 'rows': [], 'columns': ['a', 'b']}
    assert p.compare_execution(left, right)['set_correct'] is False


def test_unavailable_execution_is_unknown_not_labelled_correct():
    assert p.compare_execution({'status': 'timeout'}, {'status': 'ok', 'rows': [], 'columns': ['a']})['set_correct'] is None


def test_direct_predicate_diagnostics_are_not_string_sql_matching():
    from scripts.text2sql.p2d_inputs import predicate_diagnostics
    schema = {'db_id': 'synthetic', 'table_names_original': ['t'], 'column_names_original': [[-1, '*'], [0, 'x'], [0, 'y']]}
    result = predicate_diagnostics('SELECT x FROM t WHERE x=2', 'SELECT x FROM t WHERE y=2', schema)
    assert result['direct_literal_set_exact'] is True
    assert result['direct_column_literal_pairs_exact'] is False


def test_absolute_deadline_rejects_expired_budget_before_more_work():
    import pytest
    import time
    with pytest.raises(RuntimeError, match='wall budget'):
        p.check_deadline(time.time()-10, {'budget': {'total_wall_seconds': 1}})
