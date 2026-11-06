#!/usr/bin/env python3
"""Classify unresolved qualified JOIN equalities with conservative direct lineage."""
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
import sys
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


EXPERIMENT_ID = "p0_minidev_join_scope_taxonomy_20261106_01"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_ROWS = 500
SMOKE_QUESTIONS = 5
BASELINE_RESOLVED = 523
BASELINE_UNRESOLVED = 140
BASELINE_QUALIFIED = 663
GATE_MIN_RESOLVED = 630
MAX_RSS_BYTES = 4 * 1024**3
MAX_WALL_SECONDS = 1200


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest_question(db_id: str, question_id: str) -> str:
    return hashlib.sha256(f"{db_id}\0{question_id}".encode("utf-8")).hexdigest()


def smoke_digest(db_id: str, question_id: str) -> str:
    return hashlib.sha256(f"{EXPERIMENT_ID}{db_id}{question_id}".encode("utf-8")).hexdigest()


def canonical_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def _projection_name(projection: exp.Expression) -> str:
    name = str(projection.alias_or_name or "").strip()
    if name:
        return name
    body = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(body, exp.Column):
        return str(body.name or "").strip()
    return ""


def trace_direct_column(
    column: exp.Expression,
    scope: Scope,
    known_columns: Mapping[str, set[str]],
    *,
    depth: int = 0,
) -> tuple[tuple[str, str] | None, str, bool]:
    """Resolve a qualified column through unique direct projections only."""
    if depth > 12:
        return None, "lineage_depth_limit", depth > 0
    if not isinstance(column, exp.Column):
        return None, "not_a_column", depth > 0
    qualifier = str(column.table or "").strip()
    name = str(column.name or "").strip()
    if not qualifier or not name:
        return None, "unqualified_reference", depth > 0

    qualifier_fold = qualifier.casefold()
    references = [str(alias).casefold() for alias, _ in scope.references]
    if references.count(qualifier_fold) > 1:
        return None, "duplicate_alias", depth > 0
    source_keys = [key for key in scope.sources if str(key).casefold() == qualifier_fold]
    if not source_keys:
        return None, "alias_not_found_or_correlated", depth > 0
    if len(source_keys) > 1:
        return None, "duplicate_alias", depth > 0
    source = scope.sources[source_keys[0]]

    if isinstance(source, exp.Table):
        table_fold = canonical_name(source.name)
        schema_tables = {str(table).casefold(): str(table) for table in known_columns}
        table = schema_tables.get(table_fold)
        if table is None:
            return None, "physical_table_missing", depth > 0
        schema_columns = {str(value).casefold(): str(value) for value in known_columns[table]}
        resolved_column = schema_columns.get(name.casefold())
        if resolved_column is None:
            return None, "physical_column_missing", depth > 0
        return (table, resolved_column), "base_table_column", depth > 0

    if not isinstance(source, Scope):
        return None, "unsupported_source", depth > 0

    source_expression = source.expression
    if isinstance(source_expression, exp.Union):
        return None, "derived_union", True
    if not isinstance(source_expression, exp.Select):
        return None, "derived_non_select", True
    projections = list(source_expression.selects or [])
    if not projections:
        return None, "derived_projection_missing", True

    outer_columns = [str(value).strip() for value in (source.outer_columns or [])]
    if outer_columns:
        if len(outer_columns) != len(projections):
            return None, "derived_ambiguous_projection", True
        matches = [
            projection
            for output_name, projection in zip(outer_columns, projections)
            if output_name.casefold() == name.casefold()
        ]
    else:
        matches = [projection for projection in projections if _projection_name(projection).casefold() == name.casefold()]
    if not matches:
        return None, "derived_output_missing", True
    if len(matches) != 1:
        return None, "derived_ambiguous_projection", True

    projection = matches[0]
    body = projection.this if isinstance(projection, exp.Alias) else projection
    if not isinstance(body, exp.Column):
        return None, "derived_expression", True
    resolved, reason, _ = trace_direct_column(body, source, known_columns, depth=depth + 1)
    if resolved is None:
        return None, reason, True
    return resolved, "direct_projection", True


def equality_category(reasons: list[str], rescued: bool) -> str:
    if rescued:
        return "direct_projection_recoverable"
    values = set(reasons)
    if values & {"duplicate_alias", "derived_ambiguous_projection"}:
        return "duplicate_or_ambiguous_alias"
    if values & {"derived_expression", "derived_union", "derived_non_select"}:
        return "derived_expression_or_union"
    if "derived_output_missing" in values or "derived_projection_missing" in values:
        return "derived_output_missing"
    if values & {"physical_table_missing", "physical_column_missing"}:
        return "physical_column_missing"
    if values & {"alias_not_found_or_correlated", "unqualified_reference"}:
        return "alias_not_found_or_correlated"
    return "unsupported_or_other"


def analyze_question(row: Mapping[str, Any], known_columns: Mapping[str, set[str]]) -> dict[str, Any]:
    db_id = str(row["db_id"])
    question_id = str(row["question_id"])
    sql = str(row["SQL"])
    baseline = parse_gold_sql(sql, db_id=db_id, known_columns=known_columns, candidate_mappings=[])
    result = {
        "parse_success": bool(baseline["parse_success"]),
        "baseline_qualified": int(baseline["qualified_join_equality_count"]),
        "baseline_resolved": int(baseline["resolved_qualified_join_equality_count"]),
        "baseline_unresolved": int(baseline["unresolved_qualified_join_equality_count"]),
        "lineage_rescued": 0,
        "lineage_regression": 0,
        "lineage_scope_error": int(baseline["scope_analysis_error_count"]),
        "category_counts": Counter(),
        "operand_reason_counts": Counter(),
        "parse_error_class": baseline.get("parse_error_class"),
    }
    if not baseline["parse_success"]:
        return result

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    equality_count = 0
    baseline_resolved_count = 0
    baseline_unresolved_count = 0
    lineage_rescued = 0
    lineage_regression = 0
    category_counts: Counter[str] = Counter()
    operand_reason_counts: Counter[str] = Counter()
    try:
        expression = sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE)
        require(len(expression) == 1 and expression[0] is not None, "statement_count")
        for scope in traverse_scope(expression[0]):
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
                    equality_count += 1
                    baseline_left = _resolve_column(left, aliases, columns_by_table_fold)
                    baseline_right = _resolve_column(right, aliases, columns_by_table_fold)
                    trace_left, reason_left, used_left_projection = trace_direct_column(left, scope, known_columns)
                    trace_right, reason_right, used_right_projection = trace_direct_column(right, scope, known_columns)
                    old_resolved = baseline_left is not None and baseline_right is not None
                    new_resolved = trace_left is not None and trace_right is not None
                    if old_resolved:
                        baseline_resolved_count += 1
                        if not new_resolved:
                            lineage_regression += 1
                    else:
                        baseline_unresolved_count += 1
                        rescued = new_resolved and (used_left_projection or used_right_projection)
                        if rescued:
                            lineage_rescued += 1
                        category_counts[equality_category([reason_left, reason_right], rescued)] += 1
                        if baseline_left is None:
                            operand_reason_counts[reason_left] += 1
                        if baseline_right is None:
                            operand_reason_counts[reason_right] += 1
    except Exception as error:  # noqa: BLE001 - only exception class is reported.
        result["lineage_scope_error"] += 1
        result["lineage_error_class"] = type(error).__name__
        return result

    result.update({
        "qualified_equality_count": equality_count,
        "baseline_resolved_verified": baseline_resolved_count,
        "baseline_unresolved_verified": baseline_unresolved_count,
        "lineage_rescued": lineage_rescued,
        "lineage_regression": lineage_regression,
        "category_counts": category_counts,
        "operand_reason_counts": operand_reason_counts,
    })
    require(equality_count == result["baseline_qualified"], "qualified equality count mismatch")
    require(baseline_resolved_count == result["baseline_resolved"], "baseline resolved count mismatch")
    require(baseline_unresolved_count == result["baseline_unresolved"], "baseline unresolved count mismatch")
    return result


def run_logic_fixtures() -> dict[str, int]:
    schema = {"t": {"id"}, "u": {"id"}}
    fixtures = {
        "cte_direct": (
            "WITH q AS (SELECT t.id AS k FROM t) SELECT a.k = b.id FROM q AS a JOIN u AS b ON a.k = b.id",
            "direct_projection",
        ),
        "derived_direct": (
            "SELECT a.k = b.id FROM (SELECT t.id AS k FROM t) AS a JOIN u AS b ON a.k = b.id",
            "direct_projection",
        ),
        "nested_direct": (
            "WITH q AS (SELECT t.id AS k FROM t), r AS (SELECT q.k AS z FROM q) SELECT a.z = b.id FROM r AS a JOIN u AS b ON a.z = b.id",
            "direct_projection",
        ),
        "expression_rejected": (
            "WITH q AS (SELECT t.id + 1 AS k FROM t) SELECT a.k = b.id FROM q AS a JOIN u AS b ON a.k = b.id",
            "derived_expression",
        ),
        "missing_output_rejected": (
            "WITH q AS (SELECT t.id AS k FROM t) SELECT a.missing = b.id FROM q AS a JOIN u AS b ON a.missing = b.id",
            "derived_output_missing",
        ),
        "physical_column_rejected": (
            "SELECT a.missing = b.id FROM t AS a JOIN u AS b ON a.missing = b.id",
            "physical_column_missing",
        ),
        "duplicate_alias_rejected": (
            "SELECT a.id = a.id FROM t AS a JOIN u AS a ON a.id = a.id",
            "duplicate_alias",
        ),
    }
    for name, (sql, expected_reason) in fixtures.items():
        expression = sqlglot.parse_one(sql, read="sqlite")
        found = False
        actual_reason = None
        for scope in traverse_scope(expression):
            if not isinstance(scope.expression, exp.Select):
                continue
            for join in scope.expression.args.get("joins") or []:
                on = join.args.get("on")
                if on is None:
                    continue
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not join:
                        continue
                    left, right = equality.this, equality.expression
                    left_result, left_reason, _ = trace_direct_column(left, scope, schema)
                    right_result, right_reason, _ = trace_direct_column(right, scope, schema)
                    if left_result is not None and right_result is not None:
                        actual_reason = "direct_projection"
                    elif expected_reason in {left_reason, right_reason}:
                        actual_reason = expected_reason
                    else:
                        actual_reason = equality_category([left_reason, right_reason], False)
                    found = True
                    break
                if found:
                    break
            if found:
                break
        require(found, f"fixture missing equality: {name}")
        require(actual_reason == expected_reason, f"fixture outcome mismatch: {name}")
    return {"fixture_count": len(fixtures), "passed_count": len(fixtures)}


def sum_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    integer_fields = [
        "baseline_qualified", "baseline_resolved", "baseline_unresolved",
        "qualified_equality_count", "baseline_resolved_verified",
        "baseline_unresolved_verified", "lineage_rescued", "lineage_regression",
        "lineage_scope_error",
    ]
    totals = {field: sum(int(row.get(field, 0)) for row in rows) for field in integer_fields}
    categories: Counter[str] = Counter()
    operands: Counter[str] = Counter()
    for row in rows:
        categories.update(row.get("category_counts", {}))
        operands.update(row.get("operand_reason_counts", {}))
    totals["unresolved_equality_categories"] = dict(sorted(categories.items()))
    totals["unresolved_operand_reasons"] = dict(sorted(operands.items()))
    totals["lineage_resolved_total"] = totals["baseline_resolved"] + totals["lineage_rescued"] - totals["lineage_regression"]
    totals["lineage_resolution_rate"] = (
        round(totals["lineage_resolved_total"] / totals["baseline_qualified"], 6)
        if totals["baseline_qualified"] else 0.0
    )
    return totals


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--smoke-attempt", type=int, default=1)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-private", type=Path)
    return parser.parse_args()


def git_value(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    args = parse_args()
    require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGlot version mismatch")
    require(not args.output_dir.exists(), "output directory already exists")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config["experiment_id"] == EXPERIMENT_ID, "experiment ID mismatch")
    require(config["environment"]["sqlglot"] == EXPECTED_SQLGLOT, "frozen SQLGlot mismatch")
    require(args.attempt >= 1 and args.smoke_attempt >= 1, "attempt number must be positive")
    require(git_value("rev-parse", "HEAD") == args.expected_commit, "source commit mismatch")
    require(git_value("branch", "--show-current") == config["project"]["branch"], "source branch mismatch")
    fixture_summary = run_logic_fixtures()

    data_path = Path(config["data"]["dataset_path"])
    schema_path = Path(config["data"]["schema_path"])
    input_paths = {"dataset": data_path, "schema": schema_path}
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    expected_hashes = {
        "dataset": config["data"]["dataset_sha256"],
        "schema": config["data"]["schema_sha256"],
    }
    require(input_hashes == expected_hashes, "frozen input hash mismatch")

    dataset = _read_jsonl(data_path)
    require(len(dataset) == EXPECTED_ROWS, "dataset row count mismatch")
    row_keys = [(str(row["db_id"]), str(row["question_id"])) for row in dataset]
    require(len(row_keys) == len(set(row_keys)), "duplicate question key")
    smoke_keys = {
        key for _, key in sorted((smoke_digest(db_id, qid), (db_id, qid)) for db_id, qid in row_keys)[:SMOKE_QUESTIONS]
    }
    if args.mode == "smoke":
        require(args.smoke_private is None, "smoke cannot consume prior summary")
        selected = [row for row in dataset if (str(row["db_id"]), str(row["question_id"])) in smoke_keys]
        run_id = f"{EXPERIMENT_ID}_cpu_smoke_{args.attempt:03d}"
    else:
        require(args.smoke_private is not None and args.smoke_private.is_file(), "full requires smoke summary")
        smoke_payload = json.loads(args.smoke_private.read_text(encoding="utf-8"))
        require(smoke_payload["experiment_id"] == EXPERIMENT_ID, "smoke experiment ID mismatch")
        require(smoke_payload["run_id"] == f"{EXPERIMENT_ID}_cpu_smoke_{args.smoke_attempt:03d}", "smoke run ID mismatch")
        require(smoke_payload["mode"] == "smoke", "smoke mode mismatch")
        require(smoke_payload["input_hashes"] == expected_hashes, "smoke input hash mismatch")
        smoke_row_digests = {row["question_key_digest"] for row in smoke_payload["question_rows"]}
        expected_smoke_digests = {digest_question(*key) for key in smoke_keys}
        require(smoke_row_digests == expected_smoke_digests, "smoke selection mismatch")
        require(len(smoke_payload["question_rows"]) == SMOKE_QUESTIONS, "smoke summary row count mismatch")
        smoke_totals = sum_rows([row["metrics"] for row in smoke_payload["question_rows"]])
        require(
            sum(smoke_totals["unresolved_equality_categories"].values()) == smoke_totals["baseline_unresolved"],
            "smoke category conservation failed",
        )
        selected = [row for row in dataset if (str(row["db_id"]), str(row["question_id"])) not in smoke_keys]
        require(len(selected) == EXPECTED_ROWS - SMOKE_QUESTIONS, "full row count mismatch")
        run_id = f"{EXPERIMENT_ID}_cpu_full_{args.attempt:03d}"

    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    started = time.perf_counter()
    cpu_started = time.process_time()
    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "attempt_number": args.attempt,
        "smoke_attempt_number": args.smoke_attempt if args.mode == "full" else None,
        "mode": args.mode,
        "source_commit": git_value("rev-parse", "HEAD"),
        "source_branch": git_value("branch", "--show-current"),
        "config_path": str(args.config.resolve()),
        "config_sha256": sha256_file(args.config),
        "input_paths": {key: str(value) for key, value in input_paths.items()},
        "input_hashes": input_hashes,
        "environment": {
            "python": platform.python_version(),
            "sqlglot": sqlglot.__version__,
            "sqlite": sqlite3.sqlite_version,
            "conda_prefix": os.environ.get("CONDA_PREFIX"),
            "device": "CPU",
        },
        "fixture_summary": fixture_summary,
        "selected_question_count": len(selected),
        "status": "started",
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt)

    try:
        known_by_db = load_known_columns(schema_path)
        require(set(known_by_db) == {str(row["db_id"]) for row in dataset}, "schema/database set mismatch")
        database_order = sorted(
            known_by_db,
            key=lambda db_id: hashlib.sha256(f"{EXPERIMENT_ID}:{db_id}".encode("utf-8")).hexdigest(),
        )
        anonymous_db = {db_id: f"db_{index:02d}" for index, db_id in enumerate(database_order, start=1)}
        question_rows: list[dict[str, Any]] = []
        for row in selected:
            db_id = str(row["db_id"])
            metrics = analyze_question(row, known_by_db[db_id])
            question_rows.append({
                "question_key_digest": digest_question(db_id, str(row["question_id"])),
                "anonymous_db_id": anonymous_db[db_id],
                "metrics": metrics,
            })
        totals = sum_rows([row["metrics"] for row in question_rows])
        require(totals["lineage_scope_error"] == 0, "scope error encountered")
        require(totals["lineage_regression"] == 0, "lineage regression encountered")
        require(
            sum(totals["unresolved_equality_categories"].values()) == totals["baseline_unresolved"],
            "unresolved equality category conservation failed",
        )
        if args.mode == "smoke":
            require(len(question_rows) == SMOKE_QUESTIONS, "smoke question count mismatch")

        private_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "input_hashes": input_hashes,
            "question_rows": question_rows,
            "aggregate": totals,
        }
        write_json(args.output_dir / "private_summary.json", private_summary)

        combined_rows = question_rows
        if args.mode == "full":
            combined_rows = json.loads(args.smoke_private.read_text(encoding="utf-8"))["question_rows"] + question_rows
            require(len(combined_rows) == EXPECTED_ROWS, "combined question coverage mismatch")
            digests = [row["question_key_digest"] for row in combined_rows]
            require(len(digests) == len(set(digests)), "smoke/full overlap")
            combined_totals = sum_rows([row["metrics"] for row in combined_rows])
            require(combined_totals["baseline_qualified"] == BASELINE_QUALIFIED, "baseline denominator mismatch")
            require(combined_totals["baseline_resolved"] == BASELINE_RESOLVED, "baseline resolved count mismatch")
            require(combined_totals["baseline_unresolved"] == BASELINE_UNRESOLVED, "baseline unresolved count mismatch")
            require(
                sum(combined_totals["unresolved_equality_categories"].values()) == BASELINE_UNRESOLVED,
                "combined category conservation failed",
            )
            gate = {
                "lineage_resolved_total": combined_totals["lineage_resolved_total"],
                "qualified_join_equality_count": combined_totals["baseline_qualified"],
                "resolution_rate": combined_totals["lineage_resolution_rate"],
                "minimum_resolved_for_95_percent": GATE_MIN_RESOLVED,
                "pass": combined_totals["lineage_resolved_total"] >= GATE_MIN_RESOLVED,
            }
        else:
            combined_totals = totals
            gate = None

        per_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in combined_rows:
            per_db[row["anonymous_db_id"]].append(row["metrics"])
        database_aggregates = {
            db_name: sum_rows(db_rows) for db_name, db_rows in sorted(per_db.items())
        }
        public_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "status": "complete",
            "question_count": len(combined_rows),
            "fixture_summary": fixture_summary,
            "aggregate": combined_totals,
            "anonymous_database_aggregates": database_aggregates,
            "resolution_gate": gate,
            "local_model_requests": 0,
            "external_api_requests": 0,
            "confirmed_tokens": {"input": 0, "output": 0, "total": 0},
            "estimated_model_api_cost_CNY": "0",
            "billed_cost_verified": False,
            "contains_raw_sql_or_question": False,
        }
        write_json(args.output_dir / "aggregate_summary.json", public_summary)
        attempt.update({
            "status": "completed",
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "cpu_process_seconds": round(time.process_time() - cpu_started, 6),
            "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "aggregate": totals,
        })
        require(attempt["peak_rss_bytes"] <= MAX_RSS_BYTES, "RSS budget exceeded")
        require(attempt["elapsed_seconds"] <= MAX_WALL_SECONDS, "wall budget exceeded")
        write_json(args.output_dir / "attempt_manifest.json", attempt)
        print(json.dumps({
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "mode": args.mode,
            "status": "completed",
            "question_count": len(selected),
            "baseline_qualified": totals["baseline_qualified"],
            "baseline_resolved": totals["baseline_resolved"],
            "baseline_unresolved": totals["baseline_unresolved"],
            "lineage_rescued": totals["lineage_rescued"],
            "lineage_regression": totals["lineage_regression"],
            "scope_errors": totals["lineage_scope_error"],
            "categories": totals["unresolved_equality_categories"],
            "wall_seconds": attempt["elapsed_seconds"],
            "peak_rss_bytes": attempt["peak_rss_bytes"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - prevent private SQL/error text from entering public output.
        attempt.update({"status": "failed", "failure_class": type(error).__name__})
        write_json(args.output_dir / "attempt_manifest.json", attempt)
        print(json.dumps({"experiment_id": EXPERIMENT_ID, "run_id": run_id, "status": "failed", "failure_class": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
