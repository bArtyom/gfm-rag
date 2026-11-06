#!/usr/bin/env python3
"""Diagnose alignment between frozen FK candidate identities and SQL JOIN equalities.

This CPU-only audit uses the same frozen 60 question/table-pair sample as the
preceding SQL-used label audit. It independently builds resolved JOIN-ON
column-pair signatures and compares them with frozen mapping identities, then
compares those IDs with the existing candidate-filtered matcher. Raw SQL,
table/column names, IDs, and per-pair rows stay in private local output.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from typing import Any

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import traverse_scope

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_p0_fk_sql_used_mapping_alignment_20261107_02 import (  # noqa: E402
    build_known_columns,
    read_identity_mappings,
    read_json,
    table_pair_key,
)
from audit_minidev_sql_fk_labels import (  # noqa: E402
    _column_index,
    _mapping_matches_equalities,
    _qualified_column_pair,
    _resolve_column,
    _scope_aliases,
    parse_gold_sql,
)
from prepare_p0_fk_disagreement_review_packet import question_key  # noqa: E402


EXPERIMENT_ID = "p0_fk_candidate_sql_identity_alignment_20261107_01"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_QUESTION_COUNT = 1534
EXPECTED_PAIR_COUNT = 60
EXPECTED_SMOKE_COUNT = 5
EXPECTED_FULL_COUNT = 55
MAX_WALL_SECONDS = 600.0
MAX_CPU_SECONDS = 300.0
MAX_RSS_GIB = 4.0


class StopRun(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise StopRun(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def verify_inputs(inputs: dict[str, dict[str, str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in inputs.items():
        path = Path(spec["path"])
        require(path.is_file(), f"INPUT_MISSING_{name}")
        digest = sha256_file(path)
        require(digest == spec["sha256"], f"INPUT_HASH_MISMATCH_{name}")
        observed[name] = digest
    return observed


def load_run_inputs(config: dict[str, Any], mode: str) -> tuple[
    dict[str, dict[str, Any]], list[str], list[str], dict[str, str], dict[str, dict[str, Any]]
]:
    inputs = config["inputs"]
    questions = read_json(Path(inputs["dev_json"]["path"]))
    schema_rows = read_json(Path(inputs["dev_tables_json"]["path"]))
    manifest = read_json(Path(inputs["private_pair_manifest"]["path"]))
    split = read_json(Path(inputs["frozen_split"]["path"]))
    require(isinstance(questions, list) and len(questions) == EXPECTED_QUESTION_COUNT, "QUESTION_COUNT_MISMATCH")
    require(isinstance(schema_rows, list), "SCHEMA_ROOT_INVALID")
    schemas_by_db = {str(row["db_id"]): row for row in schema_rows if isinstance(row, dict)}
    require(len(schemas_by_db) == len(schema_rows), "SCHEMA_DB_ID_DUPLICATE")

    questions_by_key: dict[str, dict[str, Any]] = {}
    for record in questions:
        require(isinstance(record, dict), "QUESTION_ROW_INVALID")
        key = question_key(record)
        require(key not in questions_by_key, "QUESTION_KEY_DUPLICATE")
        questions_by_key[key] = record

    manifest_rows = manifest.get("selected_cases_private")
    require(isinstance(manifest_rows, list) and len(manifest_rows) == EXPECTED_PAIR_COUNT, "MANIFEST_PAIR_COUNT_MISMATCH")
    require(manifest.get("trusted_role_label_count") == 0, "TRUSTED_HUMAN_LABEL_COUNT_CHANGED")
    require(manifest.get("human_review_completed") is False, "HUMAN_REVIEW_STATE_CHANGED")
    manifest_by_pair = {str(row["pair_id"]): row for row in manifest_rows}
    require(len(manifest_by_pair) == len(manifest_rows), "MANIFEST_PAIR_ID_DUPLICATE")

    smoke_ids = list(split.get("smoke_pair_ids", []))
    full_ids = list(split.get("full_pair_ids", []))
    require(len(smoke_ids) == EXPECTED_SMOKE_COUNT, "SMOKE_SPLIT_COUNT_MISMATCH")
    require(len(full_ids) == EXPECTED_FULL_COUNT, "FULL_SPLIT_COUNT_MISMATCH")
    require(len(set(smoke_ids)) == len(smoke_ids), "SMOKE_SPLIT_DUPLICATE")
    require(len(set(full_ids)) == len(full_ids), "FULL_SPLIT_DUPLICATE")
    require(not set(smoke_ids) & set(full_ids), "SMOKE_FULL_OVERLAP")
    require(set(manifest_by_pair) == set(smoke_ids) | set(full_ids), "SPLIT_MANIFEST_COVERAGE_MISMATCH")

    selected_ids = smoke_ids if mode == "smoke" else full_ids
    selected_rows = {pair_id: manifest_by_pair[pair_id] for pair_id in selected_ids}
    db_ids = sorted({str(row["private_db_id"]) for row in manifest_rows})
    db_labels = {db_id: f"DB-{chr(65 + index)}" for index, db_id in enumerate(db_ids)}
    return questions_by_key, selected_ids, db_ids, db_labels, {
        "manifest_by_pair": selected_rows,
        "all_manifest_by_pair": manifest_by_pair,
        "schemas_by_db": schemas_by_db,
        "questions_by_key": questions_by_key,
    }


def selected_sql(
    pair_id: str,
    manifest_row: dict[str, Any],
    questions_by_key: dict[str, dict[str, Any]],
    schemas_by_db: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, set[str]], list[dict[str, Any]]]:
    key = manifest_row.get("question_key_sha256")
    require(isinstance(key, str) and key, "MANIFEST_QUESTION_KEY_INVALID")
    record = questions_by_key.get(key)
    require(record is not None, "MANIFEST_QUESTION_NOT_FOUND")
    require(
        str(record.get("db_id")) == str(manifest_row.get("private_db_id"))
        and str(record.get("question_id")) == str(manifest_row.get("private_question_id")),
        "MANIFEST_QUESTION_KEY_MISMATCH",
    )
    schema_row = schemas_by_db.get(str(record["db_id"]))
    require(schema_row is not None, "QUESTION_SCHEMA_NOT_FOUND")
    mappings = read_identity_mappings(manifest_row)
    pair_keys = {
        tuple(value.casefold() for value in table_pair_key(item["child_table"], item["parent_table"]))
        for item in mappings
    }
    require(len(pair_keys) == 1, "PAIR_MANIFEST_SPANS_MULTIPLE_TABLE_PAIRS")
    sql = record.get("SQL")
    require(isinstance(sql, str) and bool(sql.strip()), "REFERENCE_SQL_MISSING")
    return record, build_known_columns(schema_row), mappings


def independent_join_equalities(
    sql: str,
    known_columns: dict[str, set[str]],
    target_pair: tuple[str, str],
) -> dict[str, Any]:
    """Resolve SQL JOIN equalities directly, without candidate-filtered labels."""
    counters = {
        "join_count": 0,
        "using_join_count": 0,
        "join_on_equality_count": 0,
        "qualified_join_equality_count": 0,
        "resolved_qualified_join_equality_count": 0,
        "unresolved_qualified_join_equality_count": 0,
    }
    try:
        parsed = [node for node in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE) if node is not None]
    except Exception as error:  # noqa: BLE001 - retain only safe error classes.
        return {"parse_success": False, "parse_error_class": type(error).__name__, "counters": counters, "groups": []}
    if len(parsed) != 1:
        return {"parse_success": False, "parse_error_class": "statement_count", "counters": counters, "groups": []}

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    target_fold = tuple(sorted((value.casefold() for value in target_pair)))
    groups: list[dict[str, Any]] = []
    scope_error_count = 0
    expression = parsed[0]
    try:
        for scope in traverse_scope(expression):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = _scope_aliases(scope, table_by_fold)
            for join_index, join in enumerate(scope.expression.args.get("joins") or []):
                counters["join_count"] += 1
                if join.args.get("using"):
                    counters["using_join_count"] += 1
                    continue
                on = join.args.get("on")
                if on is None:
                    continue
                equalities_by_alias_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not join:
                        continue
                    counters["join_on_equality_count"] += 1
                    left = equality.this
                    right = equality.expression
                    if not _qualified_column_pair(left, right):
                        continue
                    counters["qualified_join_equality_count"] += 1
                    resolved_left = _resolve_column(left, aliases, columns_by_table_fold)
                    resolved_right = _resolve_column(right, aliases, columns_by_table_fold)
                    if resolved_left is None or resolved_right is None:
                        counters["unresolved_qualified_join_equality_count"] += 1
                        continue
                    counters["resolved_qualified_join_equality_count"] += 1
                    left_alias = str(left.table).casefold()
                    right_alias = str(right.table).casefold()
                    if left_alias == right_alias:
                        continue
                    actual_pair = tuple(
                        value.casefold() for value in table_pair_key(resolved_left[0], resolved_right[0])
                    )
                    if actual_pair != target_fold:
                        continue
                    alias_pair = tuple(sorted((left_alias, right_alias)))
                    equalities_by_alias_pair[alias_pair].append({
                        "left_table": resolved_left[0],
                        "left_column": resolved_left[1],
                        "right_table": resolved_right[0],
                        "right_column": resolved_right[1],
                        "left_alias": left_alias,
                        "right_alias": right_alias,
                        "alias_pair": alias_pair,
                    })
                for alias_pair, equality_rows in sorted(equalities_by_alias_pair.items()):
                    groups.append({
                        "scope_index": len(groups),
                        "join_index": join_index,
                        "alias_pair": alias_pair,
                        "equalities": equality_rows,
                    })
    except Exception as error:  # noqa: BLE001 - retain only error class in private receipt.
        scope_error_count += 1
        return {
            "parse_success": True,
            "parse_error_class": None,
            "scope_analysis_error_count": scope_error_count,
            "scope_error_class": type(error).__name__,
            "counters": counters,
            "groups": [],
        }
    return {
        "parse_success": True,
        "parse_error_class": None,
        "scope_analysis_error_count": scope_error_count,
        "counters": counters,
        "groups": groups,
    }


def candidate_matches_from_signatures(
    mappings: list[dict[str, Any]], groups: list[dict[str, Any]]
) -> tuple[set[str], set[str]]:
    exact_ids: set[str] = set()
    partial_ids: set[str] = set()
    for mapping in mappings:
        child = str(mapping["child_table"])
        parent = str(mapping["parent_table"])
        wanted = Counter(
            (str(child_col).casefold(), str(parent_col).casefold())
            for child_col, parent_col in mapping["ordered_column_pairs"]
        )
        observed_any_partial = False
        for group in groups:
            observed: Counter[tuple[str, str]] = Counter()
            for equality in group["equalities"]:
                left_table = equality["left_table"]
                right_table = equality["right_table"]
                if left_table.casefold() == child.casefold() and right_table.casefold() == parent.casefold():
                    observed[(equality["left_column"].casefold(), equality["right_column"].casefold())] += 1
                elif left_table.casefold() == parent.casefold() and right_table.casefold() == child.casefold():
                    observed[(equality["right_column"].casefold(), equality["left_column"].casefold())] += 1
            overlap = sum((wanted & observed).values())
            if overlap and overlap < sum(wanted.values()):
                observed_any_partial = True
            if wanted and not (wanted - observed):
                exact_ids.add(str(mapping["mapping_id"]))
                break
        if observed_any_partial:
            partial_ids.add(str(mapping["mapping_id"]))
    return exact_ids, partial_ids


def classify_row(
    parsed: dict[str, Any],
    legacy: dict[str, Any],
    independent_ids: set[str],
    partial_ids: set[str],
    mappings: list[dict[str, Any]],
) -> str:
    if parsed.get("parse_success") is not True or legacy.get("parse_success") is not True:
        return "SQL_PARSE_FAILURE"
    if int(parsed.get("scope_analysis_error_count", 0)) or int(legacy.get("scope_analysis_error_count", 0)):
        return "SCOPE_ANALYSIS_FAILURE"
    counts = parsed["counters"]
    qualified = int(counts["qualified_join_equality_count"])
    resolved = int(counts["resolved_qualified_join_equality_count"])
    unresolved = int(counts["unresolved_qualified_join_equality_count"])
    resolution_complete = qualified > 0 and resolved == qualified and unresolved == 0
    target_pair_present = bool(parsed["groups"])
    legacy_ids = set(legacy.get("gold_mapping_ids", []))
    if not resolution_complete:
        return "INCOMPLETE_QUALIFIED_JOIN_RESOLUTION"
    if not target_pair_present:
        return "NO_TARGET_PAIR_EQUALITY_IN_EXPLICIT_ON"
    if independent_ids and legacy_ids:
        return "EXACT_MATCH_BOTH_AGREE" if independent_ids == legacy_ids else "EXACT_MATCH_BOTH_ID_DISAGREEMENT"
    if independent_ids:
        return "EXACT_MATCH_INDEPENDENT_ONLY"
    if legacy_ids:
        return "EXACT_MATCH_LEGACY_ONLY"
    if partial_ids and any(len(item["ordered_column_pairs"]) > 1 for item in mappings):
        return "PARTIAL_COMPOSITE_MAPPING_MATCH"
    return "TARGET_PAIR_ON_EQUALITY_NO_CANDIDATE_IDENTITY_MATCH"


def audit_pair(
    pair_id: str,
    manifest_row: dict[str, Any],
    questions_by_key: dict[str, dict[str, Any]],
    schemas_by_db: dict[str, dict[str, Any]],
    database_labels: dict[str, str],
) -> dict[str, Any]:
    record, known_columns, mappings = selected_sql(pair_id, manifest_row, questions_by_key, schemas_by_db)
    target_pair = table_pair_key(mappings[0]["child_table"], mappings[0]["parent_table"])
    independent = independent_join_equalities(str(record["SQL"]), known_columns, target_pair)
    legacy_raw = parse_gold_sql(
        str(record["SQL"]),
        db_id=str(record["db_id"]),
        known_columns=known_columns,
        candidate_mappings=mappings,
    )
    legacy_ids: set[str] = set()
    if legacy_raw.get("parse_success") is True and not int(legacy_raw.get("scope_analysis_error_count", 0)):
        for pair, ids in legacy_raw.get("gold_mapping_ids_by_table_pair", {}).items():
            if tuple(value.casefold() for value in pair) == tuple(value.casefold() for value in target_pair):
                legacy_ids.update(str(value) for value in ids)

    independent_ids, partial_ids = candidate_matches_from_signatures(mappings, independent["groups"])
    candidate_ids = {str(item["mapping_id"]) for item in mappings}
    require(independent_ids <= candidate_ids, "INDEPENDENT_MATCH_NOT_IN_CANDIDATES")
    require(legacy_ids <= candidate_ids, "LEGACY_MATCH_NOT_IN_CANDIDATES")
    row_class = classify_row(independent, legacy_raw, independent_ids, partial_ids, mappings)
    qualified = int(independent["counters"]["qualified_join_equality_count"])
    resolved = int(independent["counters"]["resolved_qualified_join_equality_count"])
    unresolved = int(independent["counters"]["unresolved_qualified_join_equality_count"])
    resolution_complete = qualified > 0 and resolved == qualified and unresolved == 0
    return {
        "pair_id_private": pair_id,
        "database_id_private": str(record["db_id"]),
        "anonymous_database": database_labels[str(record["db_id"])],
        "question_key_sha256": manifest_row["question_key_sha256"],
        "target_pair_private": list(target_pair),
        "row_class": row_class,
        "parse_success": independent.get("parse_success") is True,
        "parse_error_class": independent.get("parse_error_class"),
        "scope_analysis_error_count": int(independent.get("scope_analysis_error_count", 0)),
        "resolution_complete": resolution_complete,
        "legacy_parser_match_ids_private": sorted(legacy_ids),
        "independent_identity_match_ids_private": sorted(independent_ids),
        "partial_candidate_match_ids_private": sorted(partial_ids),
        "candidate_ids_private": sorted(candidate_ids),
        "candidate_mapping_count": len(mappings),
        "distinct_candidate_identity_count": len({
            (
                str(item["child_table"]).casefold(),
                str(item["parent_table"]).casefold(),
                tuple((str(a).casefold(), str(b).casefold()) for a, b in item["ordered_column_pairs"]),
            )
            for item in mappings
        }),
        "parser_counters": independent["counters"],
        "target_pair_equalities_private": [
            equality for group in independent["groups"] for equality in group["equalities"]
        ],
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(row["row_class"] for row in rows)
    complete = [row for row in rows if row["resolution_complete"]]
    agreed = sum(
        row["legacy_parser_match_ids_private"] == row["independent_identity_match_ids_private"]
        for row in complete
    )
    exact_independent = sum(bool(row["independent_identity_match_ids_private"]) for row in complete)
    pair_on = sum(
        row["row_class"] != "NO_TARGET_PAIR_EQUALITY_IN_EXPLICIT_ON"
        and row["resolution_complete"]
        and row["row_class"] not in {"SQL_PARSE_FAILURE", "SCOPE_ANALYSIS_FAILURE"}
        for row in rows
    )
    counters = Counter()
    for row in rows:
        counters.update({key: int(value) for key, value in row["parser_counters"].items()})
    by_db: dict[str, dict[str, Any]] = {}
    for label in sorted({row["anonymous_database"] for row in rows}):
        group = [row for row in rows if row["anonymous_database"] == label]
        by_db[label] = {
            "pair_count": len(group),
            "fully_resolved_count": sum(bool(row["resolution_complete"]) for row in group),
            "exact_identity_match_count": sum(
                bool(row["independent_identity_match_ids_private"]) and row["resolution_complete"]
                for row in group
            ),
            "legacy_independent_id_agreement_count": sum(
                row["legacy_parser_match_ids_private"] == row["independent_identity_match_ids_private"]
                and row["resolution_complete"]
                for row in group
            ),
            "row_class_counts": dict(sorted(Counter(row["row_class"] for row in group).items())),
        }
    identity_disagreement = sum(
        row["resolution_complete"]
        and row["legacy_parser_match_ids_private"] != row["independent_identity_match_ids_private"]
        for row in rows
    )
    return {
        "pair_count": len(rows),
        "row_class_counts": dict(sorted(classes.items())),
        "fully_resolved_pair_count": len(complete),
        "independent_exact_candidate_match_count": exact_independent,
        "legacy_independent_id_agreement_count": agreed,
        "legacy_independent_id_disagreement_count": identity_disagreement,
        "resolved_target_pair_on_equality_count": pair_on,
        "parser_counters": dict(sorted(counters.items())),
        "by_anonymous_database": by_db,
        "selected_pair_ids_sha256": stable_hash(sorted(row["pair_id_private"] for row in rows)),
        "interpretation": {
            "reference_sql_used_mapping_is_not_unique_semantic_gold": True,
            "exact_candidate_match_is_identity_coverage_not_ranking_accuracy": True,
            "identity_match_denominator_uses_fully_resolved_pairs": True,
        },
    }


def write_private(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    started_at = datetime.now(timezone.utc).isoformat()
    output_dir = args.output_dir.resolve()
    require(not output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.mkdir(mode=0o700)
    (output_dir / "run.started").write_text(started_at + "\n", encoding="utf-8")
    (output_dir / "run.started").chmod(0o600)
    status = "STOP_INVALID"
    stop_code: str | None = None
    try:
        config = read_json(args.config)
        require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_ID_MISMATCH")
        expected_config_status = "amendment_001_full_pending" if args.mode == "full" else "preregistered_not_run"
        require(config.get("status") == expected_config_status, "CONFIG_STATUS_CHANGED")
        runner_lock = config.get("runner", {})
        require(sha256_file(Path(__file__)) == runner_lock.get("sha256"), "RUNNER_HASH_MISMATCH")
        require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGLOT_VERSION_MISMATCH")
        repo_root = args.repo_root.resolve()
        branch = git_value(repo_root, "branch", "--show-current")
        commit = git_value(repo_root, "rev-parse", "HEAD")
        require(branch == EXPECTED_BRANCH, "GIT_BRANCH_MISMATCH")
        require(commit == args.expected_commit, "GIT_COMMIT_MISMATCH")
        require(args.run_id == f"{EXPERIMENT_ID}_{args.mode}_001", "RUN_ID_MISMATCH")
        hashes = verify_inputs(config["inputs"])
        questions_by_key, selected_ids, _, database_labels, loaded = load_run_inputs(config, args.mode)
        manifest_by_pair = loaded["manifest_by_pair"]
        schemas_by_db = loaded["schemas_by_db"]
        rows = [
            audit_pair(
                pair_id,
                manifest_by_pair[pair_id],
                questions_by_key,
                schemas_by_db,
                database_labels,
            )
            for pair_id in selected_ids
        ]
        summary = aggregate(rows)
        parse_success = sum(bool(row["parse_success"]) for row in rows)
        scope_errors = sum(int(row["scope_analysis_error_count"]) for row in rows)
        if args.mode == "smoke":
            gate_pass = (
                parse_success == EXPECTED_SMOKE_COUNT
                and scope_errors == 0
                and all(row["resolution_complete"] for row in rows)
                and len(rows) == EXPECTED_SMOKE_COUNT
            )
            status = "SMOKE_TECHNICAL_GATE_PASS" if gate_pass else "STOP_SMOKE_TECHNICAL_GATE"
        else:
            fully_resolved_count = sum(bool(row["resolution_complete"]) for row in rows)
            gate_pass = (
                parse_success >= 54
                and scope_errors == 0
                and fully_resolved_count >= 50
                and len(rows) == EXPECTED_FULL_COUNT
            )
            status = "FULL_DIAGNOSTIC_COMPLETE" if gate_pass else "STOP_FULL_TECHNICAL_GATE"

        resources = {
            "wall_seconds": round(time.perf_counter() - wall_start, 6),
            "cpu_seconds": round(time.process_time() - cpu_start, 6),
            "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6),
        }
        if resources["wall_seconds"] > MAX_WALL_SECONDS:
            status, stop_code = "STOP_RESOURCE_BUDGET", "WALL_BUDGET_EXCEEDED"
        elif resources["cpu_seconds"] > MAX_CPU_SECONDS:
            status, stop_code = "STOP_RESOURCE_BUDGET", "CPU_BUDGET_EXCEEDED"
        elif resources["peak_rss_gib"] > MAX_RSS_GIB:
            status, stop_code = "STOP_RESOURCE_BUDGET", "RSS_BUDGET_EXCEEDED"
        private_payload = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": status,
            "stop_code": stop_code,
            "started_at_utc": started_at,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "branch": branch,
            "commit": commit,
            "python_version": platform.python_version(),
            "sqlglot_version": sqlglot.__version__,
            "input_hashes": hashes,
            "selected_pair_count": len(rows),
            "summary_private": summary,
            "rows_private": rows,
            "resources": resources,
            "local_model_calls": 0,
            "external_api_calls": 0,
            "gpu_used": False,
        }
        write_private(output_dir / "private_result.json", private_payload)
        public_safe = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": status,
            "selected_pair_count": summary["pair_count"],
            "row_class_counts": summary["row_class_counts"],
            "fully_resolved_pair_count": summary["fully_resolved_pair_count"],
            "independent_exact_candidate_match_count": summary["independent_exact_candidate_match_count"],
            "legacy_independent_id_agreement_count": summary["legacy_independent_id_agreement_count"],
            "legacy_independent_id_disagreement_count": summary["legacy_independent_id_disagreement_count"],
            "resolved_target_pair_on_equality_count": summary["resolved_target_pair_on_equality_count"],
            "parser_counters": summary["parser_counters"],
            "by_anonymous_database": summary["by_anonymous_database"],
            "selected_pair_ids_sha256": summary["selected_pair_ids_sha256"],
            "resources": resources,
            "local_model_calls": 0,
            "external_api_calls": 0,
            "confirmed_input_tokens": 0,
            "confirmed_output_tokens": 0,
            "confirmed_total_tokens": 0,
            "gpu_used": False,
            "stop_code": stop_code,
        }
        write_private(output_dir / "public_safe_summary.json", public_safe)
        print(json.dumps(public_safe, ensure_ascii=False, sort_keys=True))
        return 0 if status in {"SMOKE_TECHNICAL_GATE_PASS", "FULL_DIAGNOSTIC_COMPLETE"} else 2
    except StopRun as error:
        stop_code = error.code
    except Exception as error:  # noqa: BLE001 - do not print user data or exception text.
        stop_code = f"UNEXPECTED_{type(error).__name__}"
    failure = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": status,
        "stop_code": stop_code,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": git_value(args.repo_root.resolve(), "branch", "--show-current") if args.repo_root.exists() else None,
        "commit": git_value(args.repo_root.resolve(), "rev-parse", "HEAD") if args.repo_root.exists() else None,
        "python_version": platform.python_version(),
        "sqlglot_version": getattr(sqlglot, "__version__", "unknown"),
        "local_model_calls": 0,
        "external_api_calls": 0,
        "gpu_used": False,
    }
    if output_dir.exists():
        write_private(output_dir / "failure_receipt.json", failure)
    print(json.dumps({"status": status, "stop_code": stop_code}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
