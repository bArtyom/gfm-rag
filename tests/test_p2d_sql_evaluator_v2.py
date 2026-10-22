"""Synthetic safety fixtures for the separately versioned P2d v2 evaluator."""
import sqlite3

import pytest

from scripts.text2sql.p2d_sql_evaluator_v2 import _sqlite_error_category, execute_readonly
from scripts.text2sql.p2d_v2_saved_replay import (
    compare_executions,
    funnel_category,
    initialize_private_results_cache,
    result_signature,
    verify_cache_membership,
)


@pytest.fixture
def temporal_db(tmp_path):
    path = tmp_path / "synthetic_temporal.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE records(id INTEGER PRIMARY KEY, stamp TEXT, modifier TEXT);"
            "INSERT INTO records VALUES"
            "(1,'2021-01-31','+1 day'),"
            "(2,'now','localtime'),"
            "(3,'utc','utc'),"
            "(4,'subsec','subsec');"
        )
    return path


def test_static_date_column_is_evaluated_without_accessing_wall_clock(temporal_db):
    result = execute_readonly(temporal_db, "SELECT date(stamp) FROM records WHERE id=1")
    assert result["status"] == "ok"
    assert result["rows"] == [("2021-01-31",)]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT date(stamp, '+1 day') FROM records WHERE id=1", "2021-02-01"),
        ("SELECT time(stamp) FROM records WHERE id=1", "00:00:00"),
        ("SELECT datetime(date(stamp), '+1 day') FROM records WHERE id=1", "2021-02-01 00:00:00"),
        ("SELECT strftime('%Y-%m', stamp) FROM records WHERE id=1", "2021-01"),
    ],
)
def test_static_date_columns_and_modifiers_remain_supported(temporal_db, sql, expected):
    result = execute_readonly(temporal_db, sql)
    assert result["status"] == "ok"
    assert result["rows"] == [(expected,)]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT julianday(stamp) FROM records WHERE id=1",
        "SELECT unixepoch(stamp) FROM records WHERE id=1",
    ],
)
def test_numeric_temporal_functions_on_static_columns_are_supported(temporal_db, sql):
    result = execute_readonly(temporal_db, sql)
    assert result["status"] == "ok"
    assert len(result["rows"]) == 1
    assert isinstance(result["rows"][0][0], (int, float))


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 43, 0), reason="timediff requires SQLite 3.43+")
def test_timediff_accepts_static_time_values(temporal_db):
    result = execute_readonly(temporal_db, "SELECT timediff('2021-02-01','2021-01-31')")
    assert result["status"] == "ok"
    assert result["rows"] == [("+0000-00-01 00:00:00.000",)]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT date('now')",
        "SELECT date(stamp) FROM records WHERE id=2",
        "SELECT datetime('2021-01-31', 'localtime')",
        "SELECT datetime('2021-01-31', 'utc')",
        "SELECT datetime('2021-01-31', 'subsec')",
        "SELECT datetime('subsec')",
        "SELECT datetime('subsecond')",
        "SELECT date(stamp) FROM records WHERE id=3",
        "SELECT date(stamp) FROM records WHERE id=4",
        "SELECT datetime('2021-01-31', modifier) FROM records WHERE id=2",
        "SELECT datetime('2021-01-31', 'lo' || 'cal' || 'time')",
        "SELECT date(lower(stamp)) FROM records WHERE id=2",
        "SELECT CURRENT_TIMESTAMP",
        "SELECT date()",
        "SELECT datetime()",
        "SELECT strftime('%Y')",
        "SELECT timediff()",
    ],
)
def test_runtime_clock_and_timezone_sources_are_blocked(temporal_db, sql):
    result = execute_readonly(temporal_db, sql)
    assert result["status"] == "blocked"
    assert result["error_type"] in {"temporal_runtime_unsafe_argument", "unsafe_sql"}


def test_blob_text_cannot_smuggle_the_now_time_value(temporal_db):
    with sqlite3.connect(temporal_db) as connection:
        connection.execute("CREATE TABLE binary_clock(value BLOB)")
        connection.execute("INSERT INTO binary_clock VALUES (CAST('now' AS BLOB))")
    result = execute_readonly(temporal_db, "SELECT date(value) FROM binary_clock")
    assert result["status"] == "blocked"
    assert result["error_type"] == "temporal_runtime_unsafe_argument"


def test_embedded_nul_cannot_truncate_a_temporal_value_to_now(temporal_db):
    result = execute_readonly(
        temporal_db,
        "SELECT date(CAST(x'6e6f7700666f6f' AS TEXT))",
    )
    assert result["status"] == "blocked"


def test_sqlite_join_order_error_gets_specific_private_triage():
    error = sqlite3.OperationalError("ON clause references tables to its right")
    assert _sqlite_error_category(error) == "bad_join"


def test_strftime_format_is_not_misclassified_as_a_time_value(temporal_db):
    result = execute_readonly(temporal_db, "SELECT strftime('now', '2021-01-31')")
    assert result["status"] == "ok"


def test_multi_statement_and_non_select_sql_remain_blocked(temporal_db):
    for sql in (
        "SELECT 1; SELECT 2",
        "SELECT date('2021-01-31'); DROP TABLE records",
        "PRAGMA table_info(records)",
        "ATTACH DATABASE ':memory:' AS other",
    ):
        result = execute_readonly(temporal_db, sql)
        assert result["status"] == "blocked"


def test_temporal_functions_hidden_in_views_are_blocked(temporal_db):
    with sqlite3.connect(temporal_db) as connection:
        connection.execute("CREATE VIEW temporal_view AS SELECT date('2021-01-31') AS value")
    result = execute_readonly(temporal_db, "SELECT value FROM temporal_view")
    assert result["status"] == "blocked", result


def test_writes_that_could_fire_triggers_and_unknown_udfs_are_blocked(temporal_db):
    with sqlite3.connect(temporal_db) as connection:
        connection.execute(
            "CREATE TRIGGER records_insert AFTER INSERT ON records "
            "BEGIN SELECT date('now'); END"
        )
    for sql in (
        "INSERT INTO records VALUES (5,'2021-01-01','+1 day')",
        "SELECT untrusted_udf(stamp) FROM records WHERE id=1",
    ):
        result = execute_readonly(temporal_db, sql)
        assert result["status"] == "blocked"


def test_saved_replay_signature_preserves_columns_types_and_unordered_bag():
    first = {"status": "ok", "columns": ["value"], "rows": [(1,), ("x",)]}
    reordered = {"status": "ok", "columns": ["value"], "rows": [("x",), (1,)]}
    changed_type = {"status": "ok", "columns": ["value"], "rows": [(1.0,), ("x",)]}
    changed_projection = {"status": "ok", "columns": ["other"], "rows": [(1,), ("x",)]}
    assert result_signature(first) == result_signature(reordered)
    assert result_signature(first) != result_signature(changed_type)
    assert result_signature(first) != result_signature(changed_projection)


def test_gate2_cache_rejects_unmanifested_results(tmp_path):
    cache = tmp_path / "private_results"
    cache.mkdir()
    (cache / "listed.pickle").write_bytes(b"listed")
    (cache / "stale.pickle").write_bytes(b"stale")
    with pytest.raises(RuntimeError, match="unmanifested"):
        verify_cache_membership(cache, {"listed.pickle"})


def test_gate1_cache_refuses_preexisting_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    cache = tmp_path / "private_results"
    cache.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        initialize_private_results_cache(cache)
    assert list(outside.iterdir()) == []


def test_saved_replay_funnel_keeps_reference_failures_separate():
    ok = {"status": "ok"}
    assert funnel_category({"status": "error"}, ok, {}) == "reference_unavailable"
    assert funnel_category(ok, {"status": "error", "error_type": "sql_parse_error"}, {}) == "prediction_parse"
    assert funnel_category(
        ok,
        {"status": "blocked", "error_type": "temporal_runtime_unsafe_argument"},
        {},
    ) == "prediction_ast_policy"
    assert funnel_category(ok, {"status": "error", "error_type": "sqlite_error"}, {}) == "prediction_sqlite"


def test_saved_replay_comparison_checks_projection_width():
    prediction = {"status": "ok", "columns": ["a", "b"], "rows": [(1, 2)]}
    reference = {"status": "ok", "columns": ["a"], "rows": [(1,)]}
    result = compare_executions(prediction, reference, lambda *_: pytest.fail("rows must not be compared"))
    assert result == {
        "set_correct": False,
        "bag_correct": False,
        "comparison_status": "column_count_mismatch",
    }
