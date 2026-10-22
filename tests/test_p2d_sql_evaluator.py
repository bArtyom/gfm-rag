"""Synthetic P2d evaluator contract tests; no benchmark data or model calls."""
import hashlib
import multiprocessing
import sqlite3
import time

import pytest

from scripts.text2sql.p2d_sql_evaluator import compare_rows, execute_readonly


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE t (id INTEGER, value TEXT); INSERT INTO t VALUES (1,'a'),(2,NULL),(3,'a');")
    return path


def test_select_and_cte_union_are_readonly(db):
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    answer = execute_readonly(db, "WITH x AS (SELECT id FROM t WHERE id=1) SELECT id FROM x UNION SELECT 9")
    assert answer["status"] == "ok"
    assert answer["columns"] == ["id"]
    assert answer["rows"] == [(1,), (9,)]
    assert answer["seconds"] >= 0
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in db.parent.iterdir()) == ["synthetic.sqlite"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM t", "UPDATE t SET value='x'", "DROP TABLE t", "CREATE TABLE x(id)",
    "PRAGMA user_version", "ATTACH ':memory:' AS x", "BEGIN", "VACUUM", "REINDEX",
    "SELECT 1; SELECT 2", "SELECT 1; DELETE FROM t", "WITH x AS (DELETE FROM t RETURNING id) SELECT * FROM x",
    "WITH x AS (UPDATE t SET value='x' RETURNING id) SELECT * FROM x", "SELECT * INTO new_t FROM t",
])
def test_nonselect_commands_are_blocked_without_writes(db, sql):
    original = db.read_bytes()
    answer = execute_readonly(db, sql)
    assert answer["status"] == "blocked"
    assert set(answer) == {"status", "seconds", "error_type"}
    assert db.read_bytes() == original


@pytest.mark.parametrize("sql", [
    "SELECT random()", "SELECT RANDOMBLOB(10)", "SELECT load_extension('secret')",
    "SELECT readfile('secret')", "SELECT writefile('secret','payload')", "SELECT eval('DELETE FROM t')",
    "SELECT current_date", "SELECT CURRENT_TIME", "SELECT CURRENT_TIMESTAMP",
    "SELECT datetime('now')", "SELECT date()", "SELECT strftime('%s','now')",
    "SELECT datetime('2020-01-01','localtime')", "SELECT sqlite_version()",
    'SELECT "random"()', "SELECT coalesce(random(),1)",
])
def test_unsafe_and_nondeterministic_functions_are_blocked(db, sql):
    answer = execute_readonly(db, sql)
    assert answer["status"] == "blocked"
    assert set(answer) == {"status", "seconds", "error_type"}


def test_deterministic_functions_and_literal_unsafe_names_work(db):
    answer = execute_readonly(db, "SELECT count(*), upper('random'), date('2020-01-01','+1 day') FROM t")
    assert answer["status"] == "ok"
    assert answer["rows"] == [(3, "RANDOM", "2020-01-02")]


def test_unknown_function_is_rejected_without_error_content(db):
    answer = execute_readonly(db, "SELECT some_unknown_function('private-sql')")
    assert answer["status"] == "blocked"
    assert "private-sql" not in repr(answer)


def test_recursive_query_times_out_and_worker_is_reaped(db):
    children_before = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    answer = execute_readonly(db, "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n", timeout=0.15)
    assert answer["status"] == "timeout"
    assert time.monotonic() - start < 2
    assert {p.pid for p in multiprocessing.active_children()} == children_before


def test_streaming_row_limit_discards_partial_rows(db):
    answer = execute_readonly(db, "SELECT * FROM t", row_limit=2)
    assert answer["status"] == "row_limit"
    assert set(answer) == {"status", "seconds", "error_type"}
    assert execute_readonly(db, "SELECT * FROM t", row_limit=3)["status"] == "ok"


def test_byte_limit_discards_partial_rows(db):
    answer = execute_readonly(db, "SELECT printf('%1000s','x')", byte_limit=100)
    assert answer["status"] == "byte_limit"
    assert set(answer) == {"status", "seconds", "error_type"}


def test_blob_byte_limit(db):
    assert execute_readonly(db, "SELECT zeroblob(1024)", byte_limit=100)["status"] == "byte_limit"


def test_sqlite_allocation_limit_is_reported_as_byte_limit(db):
    assert execute_readonly(db, "SELECT zeroblob(10000000)", byte_limit=100)["status"] == "byte_limit"


@pytest.mark.parametrize("sql", ["SELECT FROM", "SELECT missing FROM t", "SELECT * FROM nonexistent"])
def test_syntax_and_lookup_errors_do_not_include_sql_or_data(db, sql):
    answer = execute_readonly(db, sql)
    assert answer["status"] == "error"
    assert set(answer) == {"status", "seconds", "error_type"}
    assert sql not in repr(answer)


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite"
    assert execute_readonly(path, "SELECT 1")["status"] == "error"
    assert not path.exists()


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"timeout": float('nan')}, {"row_limit": -1}, {"byte_limit": 0}])
def test_invalid_limits_are_rejected(db, kwargs):
    assert execute_readonly(db, "SELECT 1", **kwargs)["status"] == "error"


@pytest.mark.parametrize("pred,ref,set_ok,bag_ok", [
    ([], [], True, True), ([], [(None,)], False, False),
    ([(1,), (1,)], [(1,)], True, False),
    ([(1,), (2,)], [(2,), (1,)], True, True),
    ([(1, 'a')], [('a', 1)], False, False),
    ([(None,)], [(None,)], True, True),
    ([(None,)], [('None',)], False, False),
    ([(1,)], [('1',)], False, False),
    ([(1.0,)], [(1.0000005,)], True, True),
    ([(0.0,)], [(0.000000005,)], True, True),
    ([(1,)], [(1.01,)], False, False),
    ([(b'a',)], [('a',)], False, False),
])
def test_set_bag_numeric_null_and_type_contract(pred, ref, set_ok, bag_ok):
    assert compare_rows(pred, ref) == {"set_correct": set_ok, "bag_correct": bag_ok, "comparison_status": "ok"}


def test_bag_comparison_finds_augmenting_path_in_ambiguous_matching():
    # First left row matches both right rows; second matches only the first.
    pred = [(1.0000005,), (0.9999995,)]
    ref = [(1.0,), (1.0000014,)]
    assert compare_rows(pred, ref) == {"set_correct": True, "bag_correct": True, "comparison_status": "ok"}
    assert compare_rows(ref, pred)["bag_correct"] is True


def test_set_tolerance_requires_symmetric_coverage():
    assert compare_rows([(1,), (2,)], [(1.0000001,)])["set_correct"] is False
    result = compare_rows([(1.0,), (1.0000005,)], [(1.0000002,)])
    assert result["set_correct"] is True
    assert result["bag_correct"] is False


def test_large_exact_comparison_uses_counter():
    rows = [(i,) for i in range(501)]
    assert compare_rows(rows, list(reversed(rows)))["bag_correct"] is True


def test_large_nonexact_tolerance_returns_unknown():
    result = compare_rows([(float(i),) for i in range(501)], [(i + 1e-9,) for i in range(501)])
    assert result == {"set_correct": None, "bag_correct": None, "comparison_status": "unknown_large_nonexact"}


@pytest.mark.parametrize("value", [float('inf'), float('-inf'), float('nan')])
def test_nonfinite_numbers_return_unknown(value):
    assert compare_rows([(value,)], [(value,)]) == {"set_correct": None, "bag_correct": None, "comparison_status": "unknown_nonfinite"}


def test_authorizer_blocks_clock_function_hidden_in_view(db):
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE VIEW clock_view AS SELECT datetime('now') AS stamp")
    answer = execute_readonly(db, "SELECT stamp FROM clock_view")
    assert answer["status"] == "blocked"
    assert set(answer) == {"status", "seconds", "error_type"}


def test_large_same_set_ambiguous_multiplicity_is_unknown_for_bag():
    result = compare_rows([(1.0,)] * 500 + [(1.0000005,)], [(1.0,)] + [(1.0000005,)] * 500)
    assert result == {"set_correct": True, "bag_correct": None, "comparison_status": "unknown_large_nonexact"}


@pytest.mark.parametrize('pred,ref,want', [
    (1000000, 1000001, False), (1000000, 1000000.5, False),
    (1000000.5, 1000000, False), (1, 1.0, True),
    (2**60, 2**60+1, False), (1000000.0, 1000000.5, True),
])
def test_integer_values_are_exact_and_only_floats_use_tolerance(pred, ref, want):
    assert compare_rows([(pred,)], [(ref,)])['set_correct'] is want


@pytest.mark.parametrize('sql,rows', [
    ("SELECT strftime('%Y','2020-01-01')", [('2020',)]),
    ("SELECT instr('abc','b'), char(65), substring('abc',2,1)", [(2, 'A', 'b')]),
])
def test_sqlite_actual_function_names_survive_sqlglot_normalization(db, sql, rows):
    answer = execute_readonly(db, sql)
    assert answer['status'] == 'ok'
    assert answer['rows'] == rows


@pytest.mark.parametrize('sql', [
    "SELECT strftime('%Y','now')", "SELECT strftime('%Y',value) FROM t",
    "SELECT date(value) FROM t", "SELECT date('2020-01-01',value) FROM t",
    "SELECT date(char(110,111,119))", "SELECT datetime('now','start of day')",
    "SELECT strftime('%Y',datetime('now'))", "SELECT strftime('%Y')",
])
def test_temporal_transformations_still_reject_clock_or_dynamic_arguments(db, sql):
    assert execute_readonly(db, sql)['status'] == 'blocked'


def test_sqlite_memory_pressure_is_bounded_and_worker_reaped(db):
    children_before = {p.pid for p in multiprocessing.active_children()}
    answer = execute_readonly(db, "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<50000) SELECT printf('%1000s',x) FROM n ORDER BY x DESC", sqlite_memory_limit=1024*1024)
    assert answer['status'] == 'memory_limit'
    assert set(answer) == {'status', 'seconds', 'error_type'}
    assert {p.pid for p in multiprocessing.active_children()} == children_before


def test_sqlite_memory_limit_can_be_configured_for_small_query(db):
    answer = execute_readonly(db, 'SELECT 1', sqlite_memory_limit=4*1024*1024)
    assert answer['status'] == 'ok'
    assert answer['rows'] == [(1,)]


@pytest.mark.parametrize('limit', [0, -1, 1.5, True])
def test_invalid_sqlite_memory_limits_are_rejected(db, limit):
    assert execute_readonly(db, 'SELECT 1', sqlite_memory_limit=limit)['status'] == 'error'


def _inspect_heap_in_isolated_child(pipe, requested):
    from scripts.text2sql.p2d_sql_evaluator import _set_sqlite_memory_limit
    with sqlite3.connect(':memory:') as conn:
        effective = _set_sqlite_memory_limit(conn, requested)
        actual = conn.execute('PRAGMA hard_heap_limit').fetchone()[0]
    pipe.send((effective, actual))
    pipe.close()


def test_effective_heap_limit_is_verified_in_sqlite_and_parent_is_unaffected():
    with sqlite3.connect(':memory:') as conn:
        before = conn.execute('PRAGMA hard_heap_limit').fetchone()[0]
    context = multiprocessing.get_context('fork')
    receiver, sender = context.Pipe(duplex=False)
    requested = 4 * 1024 * 1024
    child = context.Process(target=_inspect_heap_in_isolated_child, args=(sender, requested))
    try:
        child.start()
        sender.close()
        child.join(3)
        assert not child.is_alive()
        assert child.exitcode == 0
        assert receiver.poll(0)
        effective, actual = receiver.recv()
        assert 0 < effective <= requested
        assert actual == effective
    finally:
        if child.is_alive():
            child.kill()
        child.join()
        child.close()
        receiver.close()
    with sqlite3.connect(':memory:') as conn:
        assert conn.execute('PRAGMA hard_heap_limit').fetchone()[0] == before


def test_single_value_heap_guard_is_distinguished_from_result_byte_cap(db):
    answer = execute_readonly(db, 'SELECT zeroblob(3000000)', sqlite_memory_limit=4*1024*1024, byte_limit=8*1024*1024)
    assert answer['status'] == 'memory_limit'
    assert set(answer) == {'status', 'seconds', 'error_type'}
