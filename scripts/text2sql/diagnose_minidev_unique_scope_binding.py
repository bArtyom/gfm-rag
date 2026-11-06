#!/usr/bin/env python3
"""Audit unique in-scope binding for unqualified Mini-Dev JOIN lineage columns."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import subprocess
import time
from typing import Any, Mapping

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from audit_minidev_sql_fk_labels import (
    _column_index,
    _read_jsonl,
    _resolve_column,
    _scope_aliases,
    load_known_columns,
    parse_gold_sql,
    sha256_file,
)
from diagnose_minidev_join_scope_taxonomy import trace_direct_column


EXPERIMENT_ID = "p0_minidev_scope_binding_recovery_20261106_01"
PRIOR_EXPERIMENT_ID = "p0_minidev_join_scope_taxonomy_20261106_01"
EXPECTED_ROWS = 500
EXPECTED_SMOKE_ROWS = 5
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_BASELINE_QUALIFIED = 663
EXPECTED_BASELINE_RESOLVED = 523
EXPECTED_DIRECT_RESCUED = 46
EXPECTED_RESIDUAL = 94
MIN_TOTAL_RESOLVED = 630
MIN_SMOKE_RECOVERY_ROWS = 3
MAX_DEPTH = 12
MAX_WALL_SECONDS = 1200
MAX_RSS_BYTES = 4 * 1024**3


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: Any) -> str:
    return str(value or "").strip().casefold()


def digest_question(db_id: str, question_id: str) -> str:
    return hashlib.sha256(f"{db_id}\0{question_id}".encode("utf-8")).hexdigest()


def smoke_order_digest(question_key_digest: str) -> str:
    return hashlib.sha256(f"{EXPERIMENT_ID}{question_key_digest}".encode("utf-8")).hexdigest()


def projection_name(projection: exp.Expression) -> str:
    name = str(projection.alias_or_name or "").strip()
    if name:
        return name
    body = projection.this if isinstance(projection, exp.Alias) else projection
    return str(body.name or "").strip() if isinstance(body, exp.Column) else ""


def source_column(
    name: str,
    source: Any,
    known_columns: Mapping[str, set[str]],
    *,
    depth: int,
) -> tuple[tuple[str, str] | None, str, bool, bool]:
    """Resolve one visible source's output name through direct projections only."""
    if depth > MAX_DEPTH:
        return None, "lineage_depth_limit", depth > 0, False
    if isinstance(source, exp.Table):
        table_lookup = {canonical(table): str(table) for table in known_columns}
        table = table_lookup.get(canonical(source.name))
        if table is None:
            return None, "physical_table_missing", depth > 0, False
        columns = {canonical(column): str(column) for column in known_columns[table]}
        column = columns.get(canonical(name))
        if column is None:
            return None, "physical_column_missing", depth > 0, False
        return (table, column), "base_table_column", False, False

    if not isinstance(source, Scope):
        return None, "unsupported_source", depth > 0, False
    expression = source.expression
    if isinstance(expression, exp.Union):
        return None, "derived_union", True, False
    if not isinstance(expression, exp.Select):
        return None, "derived_non_select", True, False

    projections = list(expression.selects or [])
    if not projections:
        return None, "derived_projection_missing", True, False
    outer_columns = [str(value).strip() for value in (source.outer_columns or [])]
    if outer_columns:
        if len(outer_columns) != len(projections):
            return None, "derived_ambiguous_projection", True, False
        matches = [
            projection
            for output_name, projection in zip(outer_columns, projections)
            if canonical(output_name) == canonical(name)
        ]
    else:
        matches = [projection for projection in projections if canonical(projection_name(projection)) == canonical(name)]
    if not matches:
        return None, "derived_output_missing", True, False
    if len(matches) != 1:
        return None, "derived_ambiguous_projection", True, False

    projection = matches[0]
    body = projection.this if isinstance(projection, exp.Alias) else projection
    if not isinstance(body, exp.Column):
        return None, "derived_expression", True, False
    resolved, reason, nested_projection, nested_unqualified = scope_column(
        body, source, known_columns, depth=depth + 1
    )
    if resolved is None:
        return None, reason, True, nested_unqualified
    return resolved, "direct_projection", True, nested_unqualified or not bool(body.table)


def scope_column(
    column: exp.Expression,
    scope: Scope,
    known_columns: Mapping[str, set[str]],
    *,
    depth: int = 0,
) -> tuple[tuple[str, str] | None, str, bool, bool]:
    """Resolve qualified aliases and uniquely bound local unqualified columns.

    Correlated parent-scope lookup is deliberately unsupported. An unqualified
    reference is accepted only when exactly one visible local source exposes it.
    """
    if depth > MAX_DEPTH:
        return None, "lineage_depth_limit", depth > 0, False
    if not isinstance(column, exp.Column):
        return None, "not_a_column", depth > 0, False
    name = str(column.name or "").strip()
    if not name:
        return None, "empty_column_name", depth > 0, False

    qualifier = str(column.table or "").strip()
    reference_counts = Counter(canonical(alias) for alias, _ in scope.references)
    if qualifier:
        qualifier_key = canonical(qualifier)
        if reference_counts[qualifier_key] > 1:
            return None, "duplicate_alias", depth > 0, False
        source_keys = [key for key in scope.sources if canonical(key) == qualifier_key]
        if not source_keys:
            return None, "alias_not_found_or_correlated", depth > 0, False
        if len(source_keys) != 1:
            return None, "duplicate_alias", depth > 0, False
        return source_column(name, scope.sources[source_keys[0]], known_columns, depth=depth)

    matches: list[tuple[str, str]] = []
    used_projection = False
    reasons: list[str] = []
    for alias, source in scope.sources.items():
        alias_key = canonical(alias)
        if reference_counts[alias_key] > 1:
            return None, "duplicate_alias", depth > 0, False
        resolved, reason, projected, _nested_unqualified = source_column(
            name, source, known_columns, depth=depth + 1
        )
        if resolved is not None:
            matches.append(resolved)
            used_projection = used_projection or projected
        else:
            reasons.append(reason)
    if len(matches) == 1:
        return matches[0], "unique_unqualified_source", used_projection, True
    if len(matches) > 1:
        return None, "unqualified_ambiguous", depth > 0, True
    if "derived_expression" in reasons:
        return None, "derived_expression", depth > 0, True
    if "derived_union" in reasons:
        return None, "derived_union", depth > 0, True
    if "physical_column_missing" in reasons:
        return None, "physical_column_missing", depth > 0, True
    return None, "unqualified_not_found_or_correlated", depth > 0, True


def authorizer_read_set(
    connection: sqlite3.Connection, sql: str
) -> tuple[set[tuple[str, str]], str | None]:
    """Compile EXPLAIN only and collect base physical table/column reads."""
    reads: set[tuple[str, str]] = set()
    denied_action = False
    allowed = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION}
    recursive_action = getattr(sqlite3, "SQLITE_RECURSIVE", None)
    if recursive_action is not None:
        allowed.add(recursive_action)

    def authorize(action: int, arg1: str | None, arg2: str | None, _db: str | None, _trigger: str | None) -> int:
        nonlocal denied_action
        if action == sqlite3.SQLITE_READ:
            if arg1 and arg2:
                reads.add((canonical(arg1), canonical(arg2)))
            return sqlite3.SQLITE_OK
        if action in allowed:
            return sqlite3.SQLITE_OK
        denied_action = True
        return sqlite3.SQLITE_DENY

    connection.set_authorizer(authorize)
    try:
        # EXPLAIN yields virtual-machine instructions; it does not execute sql.
        connection.execute("EXPLAIN\n" + sql).fetchall()
        if denied_action:
            return reads, "authorizer_denied_action"
        return reads, None
    except sqlite3.Error as error:
        return reads, type(error).__name__
    finally:
        connection.set_authorizer(None)


def make_schema_connection(ddl: str) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(ddl)
    return connection


def analyze_question(
    row: Mapping[str, Any],
    known_columns: Mapping[str, set[str]],
    ddl: str,
    connection_cache: dict[str, sqlite3.Connection],
) -> dict[str, Any]:
    db_id = str(row["db_id"])
    sql = str(row["SQL"])
    baseline = parse_gold_sql(sql, db_id=db_id, known_columns={db_id: known_columns}, candidate_mappings=[])
    result: dict[str, Any] = {
        "parse_success": bool(baseline["parse_success"]),
        "baseline_qualified": int(baseline["qualified_join_equality_count"]),
        "baseline_resolved": int(baseline["resolved_qualified_join_equality_count"]),
        "baseline_unresolved": int(baseline["unresolved_qualified_join_equality_count"]),
        "qualified_equality_count": 0,
        "baseline_resolved_verified": 0,
        "baseline_unresolved_verified": 0,
        "direct_projection_rescued": 0,
        "unique_scope_proposed": 0,
        "unique_scope_verified": 0,
        "authorizer_query_count": 0,
        "authorizer_compile_error_count": 0,
        "authorizer_reference_mismatch_count": 0,
        "baseline_regression": 0,
        "direct_projection_regression": 0,
        "scope_error": int(baseline["scope_analysis_error_count"]),
        "reason_counts": Counter(),
    }
    if not baseline["parse_success"]:
        return result

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    proposed_by_pair: list[tuple[tuple[str, str], tuple[str, str]]] = []
    category_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    try:
        parsed = sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE)
        require(len(parsed) == 1 and parsed[0] is not None, "statement_count")
        for scope in traverse_scope(parsed[0]):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = _scope_aliases(scope, table_by_fold)
            for join in scope.expression.args.get("joins") or []:
                if join.args.get("using"):
                    continue
                on = join.args.get("on")
                if on is None:
                    continue
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not join:
                        continue
                    left, right = equality.this, equality.expression
                    if not (
                        isinstance(left, exp.Column)
                        and isinstance(right, exp.Column)
                        and str(left.table or "").strip()
                        and str(right.table or "").strip()
                    ):
                        continue
                    result["qualified_equality_count"] += 1
                    baseline_left = _resolve_column(left, aliases, columns_by_table_fold)
                    baseline_right = _resolve_column(right, aliases, columns_by_table_fold)
                    old_left, old_reason_left, old_proj_left = trace_direct_column(left, scope, known_columns)
                    old_right, old_reason_right, old_proj_right = trace_direct_column(right, scope, known_columns)
                    new_left, new_reason_left, new_proj_left, new_unqual_left = scope_column(left, scope, known_columns)
                    new_right, new_reason_right, new_proj_right, new_unqual_right = scope_column(right, scope, known_columns)
                    baseline_resolved = baseline_left is not None and baseline_right is not None
                    old_direct_resolved = old_left is not None and old_right is not None
                    new_resolved = new_left is not None and new_right is not None

                    if baseline_resolved:
                        result["baseline_resolved_verified"] += 1
                        if not new_resolved or (new_left, new_right) != (baseline_left, baseline_right):
                            result["baseline_regression"] += 1
                        continue

                    result["baseline_unresolved_verified"] += 1
                    if old_direct_resolved:
                        result["direct_projection_rescued"] += 1
                        if not new_resolved or (new_left, new_right) != (old_left, old_right):
                            result["direct_projection_regression"] += 1
                        continue

                    if new_resolved and (new_unqual_left or new_unqual_right):
                        result["unique_scope_proposed"] += 1
                        proposed_by_pair.append((new_left, new_right))
                        reason_counts["unique_unqualified_projection"] += 1
                    else:
                        category = new_reason_left if new_left is None else new_reason_right
                        reason_counts[str(category)] += 1
                        category_counts[str(category)] += 1
                        if new_resolved and not (new_unqual_left or new_unqual_right):
                            reason_counts["resolved_without_new_unqualified_binding"] += 1

    except Exception as error:  # noqa: BLE001 - do not include SQL or identifier text.
        result["scope_error"] += 1
        result["scope_error_class"] = type(error).__name__
        return result

    require(result["qualified_equality_count"] == result["baseline_qualified"], "qualified equality count mismatch")
    require(result["baseline_resolved_verified"] == result["baseline_resolved"], "baseline resolution mismatch")
    require(result["baseline_unresolved_verified"] == result["baseline_unresolved"], "unresolved baseline mismatch")

    if proposed_by_pair:
        if db_id not in connection_cache:
            connection_cache[db_id] = make_schema_connection(ddl)
        reads, authorizer_error = authorizer_read_set(connection_cache[db_id], sql)
        result["authorizer_query_count"] = 1
        if authorizer_error:
            result["authorizer_compile_error_count"] = 1
            reason_counts[f"authorizer_{authorizer_error}"] += len(proposed_by_pair)
        else:
            for left_pair, right_pair in proposed_by_pair:
                required = {
                    (canonical(left_pair[0]), canonical(left_pair[1])),
                    (canonical(right_pair[0]), canonical(right_pair[1])),
                }
                if required <= reads:
                    result["unique_scope_verified"] += 1
                else:
                    result["authorizer_reference_mismatch_count"] += 1
                    reason_counts["authorizer_reference_mismatch"] += 1

    result["reason_counts"] = reason_counts
    result["category_counts"] = category_counts
    return result


def fixture_result(sql: str, known_columns: Mapping[str, set[str]]) -> tuple[tuple[str, str] | None, str]:
    parsed = sqlglot.parse_one(sql, read="sqlite")
    for scope in traverse_scope(parsed):
        if not isinstance(scope.expression, exp.Select):
            continue
        for join in scope.expression.args.get("joins") or []:
            on = join.args.get("on")
            if on is None:
                continue
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression or equality.find_ancestor(exp.Join) is not join:
                        continue
                    left, right = equality.this, equality.expression
                    if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                        continue
                    if {canonical(left.table), canonical(right.table)} != {"a", "b"}:
                        continue
                    resolved_left, reason_left, _projection_left, _unqualified_left = scope_column(left, scope, known_columns)
                resolved_right, reason_right, _projection_right, _unqualified_right = scope_column(right, scope, known_columns)
                if resolved_left is None or resolved_right is None:
                    return None, reason_left if resolved_left is None else reason_right
                return (resolved_left, resolved_right), "resolved"
    return None, "equality_missing"


def run_logic_fixtures() -> dict[str, int]:
    schema = {"t": {"id", "shared"}, "v": {"value", "only_v"}, "u": {"id", "shared"}}
    fixtures = [
        (
            "unique_unqualified_direct_projection",
            "WITH q AS (SELECT id AS k FROM t) SELECT a.k = b.value FROM q AS a JOIN v AS b ON a.k = b.value",
            (("t", "id"), ("v", "value")),
        ),
        (
            "unique_unqualified_among_sources",
            "WITH q AS (SELECT id AS k FROM t JOIN v ON t.id = v.value) SELECT a.k = b.value FROM q AS a JOIN v AS b ON a.k = b.value",
            (("t", "id"), ("v", "value")),
        ),
        (
            "ambiguous_unqualified_rejected",
            "WITH q AS (SELECT shared AS k FROM t JOIN u ON t.id = u.id) SELECT a.k = b.value FROM q AS a JOIN v AS b ON a.k = b.value",
            None,
        ),
        (
            "expression_projection_rejected",
            "WITH q AS (SELECT t.id + 1 AS k FROM t) SELECT a.k = b.value FROM q AS a JOIN v AS b ON a.k = b.value",
            None,
        ),
        (
            "qualified_projection_preserved",
            "WITH q AS (SELECT t.id AS k FROM t) SELECT a.k = b.value FROM q AS a JOIN v AS b ON a.k = b.value",
            (("t", "id"), ("v", "value")),
        ),
    ]
    passed = 0
    for _name, sql, expected in fixtures:
        actual, _reason = fixture_result(sql, schema)
        if expected is None:
            require(actual is None, f"fixture should reject: {_name}")
        else:
            require(actual is not None, f"fixture should resolve: {_name}")
            require(
                (canonical(actual[0][0]), canonical(actual[0][1]), canonical(actual[1][0]), canonical(actual[1][1]))
                == (canonical(expected[0][0]), canonical(expected[0][1]), canonical(expected[1][0]), canonical(expected[1][1])),
                f"fixture physical binding mismatch: {_name}",
            )
        passed += 1
    return {"fixture_count": len(fixtures), "passed_count": passed}


def sum_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "baseline_qualified", "baseline_resolved", "baseline_unresolved",
        "qualified_equality_count", "baseline_resolved_verified", "baseline_unresolved_verified",
        "direct_projection_rescued", "unique_scope_proposed", "unique_scope_verified",
        "authorizer_query_count", "authorizer_compile_error_count",
        "authorizer_reference_mismatch_count", "baseline_regression",
        "direct_projection_regression", "scope_error",
    ]
    totals = {field: sum(int(row.get(field, 0)) for row in rows) for field in fields}
    reasons: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    for row in rows:
        reasons.update(row.get("reason_counts", {}))
        categories.update(row.get("category_counts", {}))
    totals["reason_counts"] = dict(sorted(reasons.items()))
    totals["remaining_categories"] = dict(sorted(categories.items()))
    totals["total_resolved_after"] = (
        totals["baseline_resolved"] + totals["direct_projection_rescued"] + totals["unique_scope_verified"]
    )
    totals["resolution_rate_after"] = round(
        totals["total_resolved_after"] / totals["baseline_qualified"], 6
    ) if totals["baseline_qualified"] else 0.0
    return totals


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def git_value(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--smoke-private", type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config["experiment_id"] == EXPERIMENT_ID, "experiment ID mismatch")
    require(sqlglot.__version__ == EXPECTED_SQLGLOT == config["environment"]["sqlglot"], "SQLGlot version mismatch")
    require(git_value("rev-parse", "HEAD") == args.expected_commit, "source commit mismatch")
    require(git_value("branch", "--show-current") == config["project"]["branch"], "source branch mismatch")
    require(not args.output_dir.exists(), "output directory already exists")

    dataset_path = Path(config["data"]["dataset_path"])
    schema_path = Path(config["data"]["schema_path"])
    prior_summary_path = Path(config["data"]["prior_scope_private_summary"])
    input_hashes = {
        "dataset": sha256_file(dataset_path),
        "schema": sha256_file(schema_path),
        "prior_scope_private_summary": sha256_file(prior_summary_path),
    }
    expected_hashes = {
        "dataset": config["data"]["dataset_sha256"],
        "schema": config["data"]["schema_sha256"],
        "prior_scope_private_summary": config["data"]["prior_scope_private_summary_sha256"],
    }
    require(input_hashes == expected_hashes, "frozen input hash mismatch")

    prior = json.loads(prior_summary_path.read_text(encoding="utf-8"))
    require(prior["experiment_id"] == PRIOR_EXPERIMENT_ID, "prior taxonomy experiment mismatch")
    require(prior["run_id"] == f"{PRIOR_EXPERIMENT_ID}_cpu_full_001", "prior taxonomy run mismatch")
    require(prior["mode"] == "full" and len(prior["question_rows"]) == 495, "prior taxonomy Full mismatch")
    eligible = [
        row for row in prior["question_rows"]
        if int(row["metrics"].get("baseline_unresolved", 0)) > 0
        and int(row["metrics"].get("operand_reason_counts", {}).get("unqualified_reference", 0)) > 0
    ]
    require(len(eligible) == 56, "prior unqualified-operand eligibility changed")
    smoke_digests = {
        row["question_key_digest"]
        for row in sorted(eligible, key=lambda item: smoke_order_digest(item["question_key_digest"]))[:EXPECTED_SMOKE_ROWS]
    }

    rows = _read_jsonl(dataset_path)
    require(len(rows) == EXPECTED_ROWS, "dataset row count mismatch")
    digests = [digest_question(str(row["db_id"]), str(row["question_id"])) for row in rows]
    require(len(digests) == len(set(digests)), "duplicate question key")
    require(smoke_digests <= set(digests), "smoke selector key missing from dataset")

    if args.mode == "smoke":
        require(args.smoke_private is None, "Smoke cannot consume prior run output")
        selected = [row for row in rows if digest_question(str(row["db_id"]), str(row["question_id"])) in smoke_digests]
        run_id = f"{EXPERIMENT_ID}_cpu_smoke_{args.attempt:03d}"
    else:
        require(args.smoke_private is not None and args.smoke_private.is_file(), "Full requires Smoke summary")
        smoke = json.loads(args.smoke_private.read_text(encoding="utf-8"))
        require(smoke["experiment_id"] == EXPERIMENT_ID, "Smoke experiment mismatch")
        require(smoke["run_id"] == f"{EXPERIMENT_ID}_cpu_smoke_{args.attempt:03d}", "Smoke run ID mismatch")
        require(smoke["mode"] == "smoke" and smoke["input_hashes"] == input_hashes, "Smoke input mismatch")
        smoke_rows = smoke["question_rows"]
        require({row["question_key_digest"] for row in smoke_rows} == smoke_digests, "Smoke sample mismatch")
        smoke_totals = sum_rows([row["metrics"] for row in smoke_rows])
        require(smoke_totals["authorizer_reference_mismatch_count"] == 0, "Smoke authorizer mismatch")
        require(smoke_totals["baseline_regression"] == 0, "Smoke baseline regression")
        require(smoke_totals["direct_projection_regression"] == 0, "Smoke direct-lineage regression")
        recovered_questions = sum(int(row["metrics"].get("unique_scope_verified", 0)) > 0 for row in smoke_rows)
        require(recovered_questions >= MIN_SMOKE_RECOVERY_ROWS, "Smoke recovery gate failed")
        selected = [row for row in rows if digest_question(str(row["db_id"]), str(row["question_id"])) not in smoke_digests]
        require(len(selected) == EXPECTED_ROWS - EXPECTED_SMOKE_ROWS, "Full row count mismatch")
        run_id = f"{EXPERIMENT_ID}_cpu_full_{args.attempt:03d}"

    fixtures = run_logic_fixtures()
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    started = time.perf_counter()
    cpu_started = time.process_time()
    attempt_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "attempt_number": args.attempt,
        "mode": args.mode,
        "source_commit": git_value("rev-parse", "HEAD"),
        "source_branch": git_value("branch", "--show-current"),
        "config_sha256": sha256_file(args.config),
        "runner_sha256": sha256_file(Path(__file__)),
        "input_hashes": input_hashes,
        "selected_question_count": len(selected),
        "fixture_summary": fixtures,
        "environment": {
            "python": platform.python_version(),
            "sqlglot": sqlglot.__version__,
            "sqlite": sqlite3.sqlite_version,
            "conda_prefix": os.environ.get("CONDA_PREFIX"),
            "device": "CPU",
        },
        "status": "started",
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt_manifest)

    try:
        known_by_db = load_known_columns(schema_path)
        schema_scripts = json.loads(schema_path.read_text(encoding="utf-8"))
        require(set(known_by_db) == set(schema_scripts), "schema database set mismatch")
        require({str(row["db_id"]) for row in rows} == set(known_by_db), "dataset/schema database set mismatch")
        db_order = sorted(
            known_by_db,
            key=lambda db_id: hashlib.sha256(f"{EXPERIMENT_ID}:{db_id}".encode("utf-8")).hexdigest(),
        )
        anonymous_db = {db_id: f"db_{index:02d}" for index, db_id in enumerate(db_order, start=1)}
        connection_cache: dict[str, sqlite3.Connection] = {}
        question_rows: list[dict[str, Any]] = []
        for row in selected:
            db_id = str(row["db_id"])
            metrics = analyze_question(row, known_by_db[db_id], schema_scripts[db_id], connection_cache)
            question_rows.append({
                "question_key_digest": digest_question(db_id, str(row["question_id"])),
                "anonymous_db_id": anonymous_db[db_id],
                "metrics": metrics,
            })
        for connection in connection_cache.values():
            connection.close()

        current_totals = sum_rows([row["metrics"] for row in question_rows])
        require(current_totals["scope_error"] == 0, "scope error encountered")
        require(current_totals["baseline_regression"] == 0, "baseline resolution regressed")
        require(current_totals["direct_projection_regression"] == 0, "direct projection regressed")
        require(current_totals["authorizer_reference_mismatch_count"] == 0, "authorizer reference mismatch")
        require(current_totals["authorizer_compile_error_count"] == 0, "authorizer compile error")

        private_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "input_hashes": input_hashes,
            "question_rows": question_rows,
            "aggregate": current_totals,
        }
        write_json(args.output_dir / "private_summary.json", private_summary)

        if args.mode == "full":
            combined_rows = json.loads(args.smoke_private.read_text(encoding="utf-8"))["question_rows"] + question_rows
            require(len(combined_rows) == EXPECTED_ROWS, "combined row count mismatch")
            combined_digests = [row["question_key_digest"] for row in combined_rows]
            require(len(combined_digests) == len(set(combined_digests)), "Smoke/Full overlap")
            totals = sum_rows([row["metrics"] for row in combined_rows])
            require(totals["baseline_qualified"] == EXPECTED_BASELINE_QUALIFIED, "baseline denominator mismatch")
            require(totals["baseline_resolved"] == EXPECTED_BASELINE_RESOLVED, "baseline resolved mismatch")
            require(totals["baseline_unresolved"] == EXPECTED_RESIDUAL + EXPECTED_DIRECT_RESCUED, "baseline unresolved mismatch")
            require(totals["direct_projection_rescued"] == EXPECTED_DIRECT_RESCUED, "previous resolver mismatch")
            require(totals["total_resolved_after"] == totals["baseline_resolved"] + EXPECTED_DIRECT_RESCUED + totals["unique_scope_verified"], "total resolution arithmetic mismatch")
            gate = {
                "minimum_total_resolved": MIN_TOTAL_RESOLVED,
                "total_resolved_after": totals["total_resolved_after"],
                "qualified_join_equalities": totals["baseline_qualified"],
                "resolution_rate_after": totals["resolution_rate_after"],
                "unique_scope_rescues": totals["unique_scope_verified"],
                "pass": totals["total_resolved_after"] >= MIN_TOTAL_RESOLVED,
            }
        else:
            combined_rows = question_rows
            totals = current_totals
            gate = None

        per_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in combined_rows:
            per_db[row["anonymous_db_id"]].append(row["metrics"])
        public_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "status": "complete",
            "question_count": len(combined_rows),
            "fixture_summary": fixtures,
            "aggregate": totals,
            "anonymous_database_aggregates": {db: sum_rows(items) for db, items in sorted(per_db.items())},
            "resolution_gate": gate,
            "local_model_requests": 0,
            "external_api_requests": 0,
            "confirmed_tokens": {"input": 0, "output": 0, "total": 0},
            "estimated_model_api_cost_CNY": "0",
            "billed_cost_verified": False,
            "contains_raw_sql_or_question": False,
            "authorizer_scope_limit": "SQLite read set cross-checks physical table/column presence, not alias occurrence or JOIN-equality pairing",
        }
        write_json(args.output_dir / "aggregate_summary.json", public_summary)

        elapsed = round(time.perf_counter() - started, 6)
        cpu_seconds = round(time.process_time() - cpu_started, 6)
        peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        require(elapsed <= MAX_WALL_SECONDS, "wall budget exceeded")
        require(peak_rss <= MAX_RSS_BYTES, "RSS budget exceeded")
        attempt_manifest.update({
            "status": "completed",
            "elapsed_seconds": elapsed,
            "cpu_process_seconds": cpu_seconds,
            "peak_rss_bytes": peak_rss,
            "aggregate": current_totals,
        })
        write_json(args.output_dir / "attempt_manifest.json", attempt_manifest)
        print(json.dumps({
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "status": "completed",
            "question_count": len(combined_rows),
            "baseline_qualified": totals["baseline_qualified"],
            "baseline_resolved": totals["baseline_resolved"],
            "direct_projection_rescued": totals["direct_projection_rescued"],
            "unique_scope_proposed": totals["unique_scope_proposed"],
            "unique_scope_verified": totals["unique_scope_verified"],
            "total_resolved_after": totals["total_resolved_after"],
            "baseline_regression": totals["baseline_regression"],
            "direct_projection_regression": totals["direct_projection_regression"],
            "authorizer_mismatch": totals["authorizer_reference_mismatch_count"],
            "resolution_gate": gate,
            "elapsed_seconds": elapsed,
            "peak_rss_bytes": peak_rss,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - preserve private SQL and identifiers.
        attempt_manifest.update({"status": "failed", "failure_class": type(error).__name__})
        write_json(args.output_dir / "attempt_manifest.json", attempt_manifest)
        print(json.dumps({"experiment_id": EXPERIMENT_ID, "run_id": run_id, "status": "failed", "failure_class": type(error).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
