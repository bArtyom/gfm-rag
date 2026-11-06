#!/usr/bin/env python3
"""Audit whether alternative FK mappings are distinguishable on BIRD instances.

Only direct, qualified FK equalities in a single JOIN-ON AND group are
replaced. SQL and result rows remain local; public output contains aggregates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
from typing import Any

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import traverse_scope

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import prepare_p0_fk_sql_used_mapping_rank_20261107_03 as sql_used_prep  # noqa: E402
from audit_minidev_sql_fk_labels import (  # noqa: E402
    _column_index,
    _mapping_matches_equalities,
    _qualified_column_pair,
    _resolve_column,
    _scope_aliases,
)
from audit_p0_fk_sql_used_mapping_alignment_20261107_02 import (  # noqa: E402
    build_known_columns,
    table_pair_key,
)
from p2d_sql_evaluator import compare_rows, execute_readonly  # noqa: E402
from prepare_p0_fk_disagreement_review_packet import question_key  # noqa: E402


EXPERIMENT_ID = "p0_fk_mapping_instance_equivalence_20261107_01"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_SMOKE_COUNT = 5
EXPECTED_FULL_COUNT = 108
MAX_WALL_SECONDS = 600.0
MAX_CPU_SECONDS = 300.0
MAX_RSS_GIB = 4.0
QUERY_TIMEOUT_SECONDS = 10.0
ROW_LIMIT = 50_000
BYTE_LIMIT = 64 * 1024 * 1024
SQLITE_HEAP_LIMIT = 256 * 1024 * 1024


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
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - don't expose source content.
        raise StopRun(f"JSON_READ_{type(error).__name__}") from None


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def peak_rss_gib() -> dict[str, float]:
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / (1024**2)
    return {"parent": round(own, 6), "largest_child": round(children, 6)}


def total_cpu_seconds() -> float:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime)


def normalize_pair(pair: tuple[str, str] | list[str]) -> tuple[str, str]:
    return tuple(sorted((str(value).casefold() for value in pair)))


def endpoint_key(
    left: tuple[str, str], right: tuple[str, str]
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (
            (str(left[0]).casefold(), str(left[1]).casefold()),
            (str(right[0]).casefold(), str(right[1]).casefold()),
        )
    )


def flatten_conjuncts(node: exp.Expression | None) -> list[exp.Expression]:
    if node is None:
        return []
    if isinstance(node, exp.Paren):
        return flatten_conjuncts(node.this)
    if isinstance(node, exp.And):
        return flatten_conjuncts(node.this) + flatten_conjuncts(node.expression)
    return [node]


def fold_and(nodes: list[exp.Expression]) -> exp.Expression:
    require(bool(nodes), "EMPTY_JOIN_ON_AFTER_SUBSTITUTION")
    result = nodes[0].copy()
    for node in nodes[1:]:
        result = exp.And(this=result, expression=node.copy())
    return result


def quoted_column(column_name: str, alias: str) -> exp.Column:
    return exp.Column(
        this=exp.Identifier(this=str(column_name), quoted=True),
        table=exp.Identifier(this=str(alias), quoted=True),
    )


def locate_target_join(
    sql: str,
    target: dict[str, Any],
    known_columns: dict[str, set[str]],
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = [
            tree
            for tree in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE)
            if tree is not None
        ]
    except Exception:
        return None, "SQL_PARSE_ERROR"
    if len(parsed) != 1:
        return None, "SQL_STATEMENT_COUNT"

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    target_pair = normalize_pair((target["child_table"], target["parent_table"]))
    matches: list[dict[str, Any]] = []
    unsupported_reason: str | None = None
    try:
        for scope_index, scope in enumerate(traverse_scope(parsed[0])):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = _scope_aliases(scope, table_by_fold)
            joins = scope.expression.args.get("joins") or []
            for join_index, join in enumerate(joins):
                if join.args.get("using"):
                    continue
                on = join.args.get("on")
                if on is None:
                    continue
                terms = flatten_conjuncts(on)
                equality_groups: dict[tuple[str, str], list[tuple[tuple[str, str], tuple[str, str]]]] = defaultdict(list)
                term_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
                for term in terms:
                    if not isinstance(term, exp.EQ) or not _qualified_column_pair(term.this, term.expression):
                        continue
                    left_resolved = _resolve_column(term.this, aliases, columns_by_table_fold)
                    right_resolved = _resolve_column(term.expression, aliases, columns_by_table_fold)
                    if left_resolved is None or right_resolved is None:
                        continue
                    if normalize_pair((left_resolved[0], right_resolved[0])) != target_pair:
                        continue
                    alias_pair = tuple(sorted((str(term.this.table).casefold(), str(term.expression.table).casefold())))
                    equality_groups[alias_pair].append((left_resolved, right_resolved))
                    term_groups[alias_pair].append(
                        {
                            "term": term,
                            "left": left_resolved,
                            "right": right_resolved,
                            "left_alias": str(term.this.table),
                            "right_alias": str(term.expression.table),
                        }
                    )

                for alias_pair, equalities in equality_groups.items():
                    if not _mapping_matches_equalities(target, equalities):
                        continue
                    rows = term_groups[alias_pair]
                    expected_pairs = [
                        endpoint_key(
                            (str(target["child_table"]), str(child_col)),
                            (str(target["parent_table"]), str(parent_col)),
                        )
                        for child_col, parent_col in target["ordered_column_pairs"]
                    ]
                    used_term_ids: set[int] = set()
                    child_aliases: set[str] = set()
                    parent_aliases: set[str] = set()
                    safe = True
                    for expected in expected_pairs:
                        found = [
                            row
                            for row in rows
                            if endpoint_key(row["left"], row["right"]) == expected
                        ]
                        if len(found) != 1:
                            safe = False
                            unsupported_reason = "TARGET_EQUALITY_MISSING_OR_DUPLICATED"
                            break
                        row = found[0]
                        used_term_ids.add(id(row["term"]))
                        if row["left"][0].casefold() == str(target["child_table"]).casefold():
                            child_aliases.add(row["left_alias"])
                            parent_aliases.add(row["right_alias"])
                        else:
                            child_aliases.add(row["right_alias"])
                            parent_aliases.add(row["left_alias"])
                    if not safe:
                        continue
                    if len(child_aliases) != 1 or len(parent_aliases) != 1:
                        unsupported_reason = "TARGET_ALIAS_AMBIGUOUS"
                        continue
                    if next(iter(child_aliases)).casefold() == next(iter(parent_aliases)).casefold():
                        unsupported_reason = "TARGET_ALIASES_COLLIDE"
                        continue
                    target_term_ids = {id(row["term"]) for row in rows if id(row["term"]) in used_term_ids}
                    if len(target_term_ids) != len(expected_pairs):
                        unsupported_reason = "TARGET_EQUALITY_REUSE"
                        continue
                    matches.append(
                        {
                            "tree": parsed[0],
                            "scope_index": scope_index,
                            "join_index": join_index,
                            "target_term_ids": target_term_ids,
                            "child_alias": next(iter(child_aliases)),
                            "parent_alias": next(iter(parent_aliases)),
                            "on": on,
                            "terms": terms,
                        }
                    )
    except Exception as error:  # noqa: BLE001 - aggregate only the safe class.
        return None, f"SCOPE_ERROR_{type(error).__name__}"

    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "MULTIPLE_TARGET_JOIN_GROUPS"
    return None, unsupported_reason or "TARGET_JOIN_NOT_FOUND_OR_NOT_CONJUNCTIVE"


def build_candidate_sql(
    sql: str,
    target: dict[str, Any],
    candidate: dict[str, Any],
    known_columns: dict[str, set[str]],
) -> tuple[str | None, str | None]:
    location, reason = locate_target_join(sql, target, known_columns)
    if location is None:
        return None, reason
    tree = location["tree"]
    scopes = list(traverse_scope(tree))
    if location["scope_index"] >= len(scopes):
        return None, "TARGET_SCOPE_INDEX_CHANGED"
    scope = scopes[location["scope_index"]]
    joins = scope.expression.args.get("joins") or []
    if location["join_index"] >= len(joins):
        return None, "TARGET_JOIN_INDEX_CHANGED"
    join = joins[location["join_index"]]
    retained = [term for term in location["terms"] if id(term) not in location["target_term_ids"]]
    replacements = [
        exp.EQ(
            this=quoted_column(str(child_col), location["child_alias"]),
            expression=quoted_column(str(parent_col), location["parent_alias"]),
        )
        for child_col, parent_col in candidate["ordered_column_pairs"]
    ]
    if not replacements:
        return None, "CANDIDATE_MAPPING_EMPTY"
    try:
        join.set("on", fold_and(retained + replacements))
        return tree.sql(dialect="sqlite"), None
    except Exception as error:  # noqa: BLE001 - aggregate only the safe class.
        return None, f"SQL_RENDER_{type(error).__name__}"


def execute_and_compare(
    db_path: Path,
    sql: str,
    reference: dict[str, Any],
) -> dict[str, Any]:
    result = execute_readonly(
        db_path,
        sql,
        timeout=QUERY_TIMEOUT_SECONDS,
        row_limit=ROW_LIMIT,
        byte_limit=BYTE_LIMIT,
        sqlite_memory_limit=SQLITE_HEAP_LIMIT,
    )
    if result.get("status") != "ok":
        return {"status": str(result.get("status", "unknown")), "error_type": str(result.get("error_type", "unknown"))}
    columns_equal = result.get("columns") == reference.get("columns")
    if not columns_equal:
        return {"status": "column_schema_mismatch", "error_type": "column_schema_mismatch"}
    comparison = compare_rows(result.get("rows", []), reference.get("rows", []))
    return {
        "status": "ok" if comparison.get("comparison_status") == "ok" else "comparison_unknown",
        "error_type": str(comparison.get("comparison_status", "unknown")),
        "set_equal": comparison.get("set_correct"),
        "bag_equal": comparison.get("bag_correct"),
        "row_count": len(result.get("rows", [])),
    }


def validate_manifest(manifest: dict[str, Any], config: dict[str, Any], mode: str) -> tuple[list[str], dict[str, dict[str, Any]]]:
    require(manifest.get("experiment_id") == config["data"]["source_manifest_experiment"], "SOURCE_MANIFEST_EXPERIMENT_MISMATCH")
    units = manifest.get("units")
    require(isinstance(units, dict), "MANIFEST_UNITS_INVALID")
    smoke_ids = manifest.get("smoke_unit_ids")
    full_ids = manifest.get("full_unit_ids")
    require(isinstance(smoke_ids, list) and isinstance(full_ids, list), "MANIFEST_SPLIT_INVALID")
    require(len(smoke_ids) == EXPECTED_SMOKE_COUNT, "SMOKE_UNIT_COUNT_MISMATCH")
    require(len(full_ids) == EXPECTED_FULL_COUNT, "FULL_UNIT_COUNT_MISMATCH")
    require(len(set(smoke_ids)) == len(smoke_ids) and len(set(full_ids)) == len(full_ids), "MANIFEST_SPLIT_DUPLICATE")
    require(not set(smoke_ids) & set(full_ids), "SMOKE_FULL_OVERLAP")
    require(set(units) == set(smoke_ids) | set(full_ids), "MANIFEST_UNIT_COVERAGE_MISMATCH")
    require(len(units) == int(config["data"]["source_manifest_units"]), "MANIFEST_UNIT_TOTAL_MISMATCH")
    candidate_rows = sum(
        len(unit.get("candidate_mappings", []))
        for unit in units.values()
    )
    require(candidate_rows == int(config["data"]["candidate_mapping_rows"]), "MANIFEST_CANDIDATE_ROW_COUNT_MISMATCH")
    selected_ids = smoke_ids if mode == "smoke" else full_ids
    return selected_ids, units


def unit_identity(unit: dict[str, Any]) -> str:
    return stable_hash(unit.get("unit_id", ""))[:20]


def run_unit(
    unit: dict[str, Any],
    questions_by_key: dict[str, dict[str, Any]],
    schema_by_db: dict[str, dict[str, Any]],
    db_path: Path,
    anonymous_db: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    key = unit.get("question_key_sha256")
    require(isinstance(key, str) and key in questions_by_key, "QUESTION_KEY_NOT_FOUND")
    record = questions_by_key[key]
    require(str(record.get("db_id")) == str(unit.get("db_id")), "QUESTION_DB_ID_MISMATCH")
    require(str(record.get("question_id")) == str(unit.get("question_id")), "QUESTION_ID_MISMATCH")
    sql = record.get("SQL")
    require(isinstance(sql, str) and bool(sql.strip()), "REFERENCE_SQL_MISSING")
    require(hashlib.sha256(sql.encode("utf-8")).hexdigest() == unit.get("question_sql_sha256"), "REFERENCE_SQL_HASH_MISMATCH")
    schema_row = schema_by_db.get(str(unit["db_id"]))
    require(schema_row is not None, "SCHEMA_DB_NOT_FOUND")
    known_columns = build_known_columns(schema_row)
    candidates = unit.get("candidate_mappings")
    require(isinstance(candidates, list) and len(candidates) >= 2, "CANDIDATE_LIST_INVALID")
    ids = [str(row.get("mapping_id", "")) for row in candidates]
    require(all(ids) and len(ids) == len(set(ids)), "CANDIDATE_MAPPING_ID_INVALID")
    target_ids = unit.get("sql_used_mapping_ids")
    require(isinstance(target_ids, list) and len(target_ids) == 1, "SQL_USED_TARGET_NOT_SINGLETON")
    target_id = str(target_ids[0])
    by_id = {str(row["mapping_id"]): row for row in candidates}
    require(target_id in by_id, "SQL_USED_TARGET_NOT_IN_CANDIDATES")
    target = by_id[target_id]

    pair_key = table_pair_key(str(unit["table_pair"][0]), str(unit["table_pair"][1]))
    resolved = sql_used_prep.resolve_sql_targets(
        sql,
        known_columns,
        {pair_key: candidates},
    )
    require(resolved.get("parse_success") is True, "REFERENCE_SQL_RESOLUTION_FAILED")
    require(int(resolved.get("counters", {}).get("scope_analysis_error_count", -1)) == 0, "REFERENCE_SQL_SCOPE_ERROR")
    target_rows = [row for row in resolved.get("pair_groups", []) if normalize_pair(row.get("pair", [])) == normalize_pair(unit["table_pair"])]
    require(len(target_rows) == 1, "REFERENCE_TARGET_PAIR_GROUP_COUNT")
    require(set(target_rows[0].get("sql_used_mapping_ids", [])) == {target_id}, "REFERENCE_TARGET_ID_MISMATCH")

    location, location_error = locate_target_join(sql, target, known_columns)
    if location is None:
        return (
            {
                "unit_hash": unit_identity(unit),
                "anonymous_db": anonymous_db,
                "status": "not_substitutable",
                "reason": location_error,
                "candidate_count": len(candidates),
            },
            {},
        )

    gold = execute_readonly(
        db_path,
        sql,
        timeout=QUERY_TIMEOUT_SECONDS,
        row_limit=ROW_LIMIT,
        byte_limit=BYTE_LIMIT,
        sqlite_memory_limit=SQLITE_HEAP_LIMIT,
    )
    if gold.get("status") != "ok":
        return (
            {
                "unit_hash": unit_identity(unit),
                "anonymous_db": anonymous_db,
                "status": "gold_execution_unknown",
                "reason": str(gold.get("error_type", gold.get("status", "unknown"))),
                "candidate_count": len(candidates),
            },
            {},
        )

    candidate_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        variant_sql, variant_error = build_candidate_sql(sql, target, candidate, known_columns)
        if variant_sql is None:
            candidate_rows.append(
                {
                    "candidate_hash": stable_hash(candidate["mapping_id"])[:20],
                    "is_target": str(candidate["mapping_id"]) == target_id,
                    "status": "not_substitutable",
                    "reason": variant_error,
                }
            )
            continue
        comparison = execute_and_compare(db_path, variant_sql, gold)
        candidate_rows.append(
            {
                "candidate_hash": stable_hash(candidate["mapping_id"])[:20],
                "is_target": str(candidate["mapping_id"]) == target_id,
                **comparison,
            }
        )
        if str(candidate["mapping_id"]) == target_id:
            require(
                comparison.get("status") == "ok"
                and comparison.get("set_equal") is True
                and comparison.get("bag_equal") is True,
                "TARGET_REPLAY_MISMATCH",
            )

    target_rows_private = [row for row in candidate_rows if row.get("is_target")]
    require(len(target_rows_private) == 1, "TARGET_REPLAY_COUNT_MISMATCH")
    alternatives = [row for row in candidate_rows if not row.get("is_target")]
    complete = all(row.get("status") == "ok" for row in candidate_rows)
    unit_summary = {
        "unit_hash": unit_identity(unit),
        "anonymous_db": anonymous_db,
        "status": "complete" if complete else "candidate_execution_incomplete",
        "reason": None if complete else "one_or_more_candidates_not_comparable",
        "candidate_count": len(candidates),
        "alternative_count": len(alternatives),
        "gold_row_count": len(gold.get("rows", [])),
        "gold_answer_empty": len(gold.get("rows", [])) == 0,
        "alternative_set_equal_count": sum(row.get("set_equal") is True for row in alternatives),
        "alternative_bag_equal_count": sum(row.get("bag_equal") is True for row in alternatives),
        "any_alternative_set_equal": any(row.get("set_equal") is True for row in alternatives),
        "any_alternative_bag_equal": any(row.get("bag_equal") is True for row in alternatives),
    }
    private = {
        "unit_hash": unit_identity(unit),
        "candidate_comparisons": candidate_rows,
    }
    return unit_summary, private


def wilson_interval(successes: int, total: int) -> dict[str, float | None]:
    if total <= 0:
        return {"lower": None, "upper": None}
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return {"lower": round(max(0.0, center - margin), 6), "upper": round(min(1.0, center + margin), 6)}


def summarize_units(unit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(row["status"]) for row in unit_rows)
    reasons = Counter(str(row["reason"]) for row in unit_rows if row.get("reason"))
    complete = [row for row in unit_rows if row.get("status") == "complete"]
    nonempty = [row for row in complete if not row.get("gold_answer_empty")]
    all_any_set = sum(bool(row.get("any_alternative_set_equal")) for row in complete)
    all_any_bag = sum(bool(row.get("any_alternative_bag_equal")) for row in complete)
    nonempty_any_set = sum(bool(row.get("any_alternative_set_equal")) for row in nonempty)
    nonempty_any_bag = sum(bool(row.get("any_alternative_bag_equal")) for row in nonempty)
    anonymous_db = {}
    for label in sorted({str(row["anonymous_db"]) for row in unit_rows}):
        rows = [row for row in complete if row["anonymous_db"] == label]
        informative = [row for row in rows if not row.get("gold_answer_empty")]
        bag = sum(bool(row.get("any_alternative_bag_equal")) for row in informative)
        anonymous_db[label] = {
            "complete_units": len(rows),
            "nonempty_gold_units": len(informative),
            "units_with_bag_equivalent_alternative": bag,
            "rate": round(bag / len(informative), 6) if informative else None,
        }
    alternative_count = sum(int(row.get("alternative_count", 0)) for row in complete)
    return {
        "selected_units": len(unit_rows),
        "complete_units": len(complete),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "gold_empty_units": sum(bool(row.get("gold_answer_empty")) for row in complete),
        "alternative_candidate_comparisons": alternative_count,
        "candidate_level_set_equal": sum(int(row.get("alternative_set_equal_count", 0)) for row in complete),
        "candidate_level_bag_equal": sum(int(row.get("alternative_bag_equal_count", 0)) for row in complete),
        "all_complete_units": {
            "denominator": len(complete),
            "any_alternative_set_equal": all_any_set,
            "any_alternative_bag_equal": all_any_bag,
            "bag_rate": round(all_any_bag / len(complete), 6) if complete else None,
        },
        "nonempty_gold_units": {
            "denominator": len(nonempty),
            "any_alternative_set_equal": nonempty_any_set,
            "any_alternative_bag_equal": nonempty_any_bag,
            "bag_rate": round(nonempty_any_bag / len(nonempty), 6) if nonempty else None,
            "bag_rate_wilson_95": wilson_interval(nonempty_any_bag, len(nonempty)),
            "set_rate": round(nonempty_any_set / len(nonempty), 6) if nonempty else None,
        },
        "anonymous_databases": anonymous_db,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--database-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    require(git_value(repo_root, "branch", "--show-current") == EXPECTED_BRANCH, "BRANCH_MISMATCH")
    require(not git_value(repo_root, "status", "--porcelain"), "WORKTREE_NOT_CLEAN")
    source_commit = git_value(repo_root, "rev-parse", "HEAD")
    require(args.run_id == f"{EXPERIMENT_ID}_{'smoke' if args.mode == 'smoke' else 'full'}_001", "RUN_ID_MISMATCH")
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")

    config = read_json(args.config)
    require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_MISMATCH")
    require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGLOT_VERSION_MISMATCH")
    execution = config.get("execution", {})
    require(int(execution.get("per_query_timeout_seconds", -1)) == int(QUERY_TIMEOUT_SECONDS), "QUERY_TIMEOUT_CONFIG_MISMATCH")
    require(int(execution.get("row_limit", -1)) == ROW_LIMIT, "ROW_LIMIT_CONFIG_MISMATCH")
    require(int(execution.get("byte_limit", -1)) == BYTE_LIMIT, "BYTE_LIMIT_CONFIG_MISMATCH")
    require(int(execution.get("sqlite_heap_limit_bytes", -1)) == SQLITE_HEAP_LIMIT, "SQLITE_HEAP_CONFIG_MISMATCH")
    require(int(execution.get("max_wall_seconds", -1)) == int(MAX_WALL_SECONDS), "WALL_BUDGET_CONFIG_MISMATCH")
    require(int(execution.get("max_cpu_seconds", -1)) == int(MAX_CPU_SECONDS), "CPU_BUDGET_CONFIG_MISMATCH")
    require(int(execution.get("max_rss_gib", -1)) == int(MAX_RSS_GIB), "RSS_BUDGET_CONFIG_MISMATCH")
    input_specs = {
        "dev_json": (args.dev_json, config["data"]["dev_json_sha256"]),
        "dev_tables_json": (args.tables_json, config["data"]["dev_tables_json_sha256"]),
        "source_manifest": (args.manifest, config["data"]["source_manifest_sha256"]),
    }
    input_hashes: dict[str, str] = {}
    for name, (path, expected) in input_specs.items():
        require(path.is_file(), f"INPUT_MISSING_{name}")
        observed = sha256_file(path)
        require(observed == expected, f"INPUT_HASH_MISMATCH_{name}")
        input_hashes[name] = observed
    manifest = read_json(args.manifest)
    selected_ids, units = validate_manifest(manifest, config, args.mode)

    selected_units = [units[unit_id] for unit_id in selected_ids]
    db_ids = sorted({str(unit["db_id"]) for unit in selected_units})
    require(len(db_ids) >= (3 if args.mode == "full" else 1), "ANONYMOUS_DB_COUNT_TOO_SMALL")
    if args.mode == "full":
        require(len(db_ids) == int(config["data"]["full_anonymous_databases"]), "FULL_DATABASE_COUNT_MISMATCH")
    db_labels = {db_id: f"DB-{chr(65 + index)}" for index, db_id in enumerate(db_ids)}
    db_paths: dict[str, Path] = {}
    db_hashes: dict[str, str] = {}
    database_root = args.database_root.resolve()
    for db_id in db_ids:
        require(Path(db_id).name == db_id and db_id not in {".", ".."}, "DATABASE_ID_INVALID")
        db_path = args.database_root / db_id / f"{db_id}.sqlite"
        require(db_path.is_file(), "DATABASE_FILE_MISSING")
        resolved_db_path = db_path.resolve()
        require(resolved_db_path.is_relative_to(database_root), "DATABASE_PATH_OUTSIDE_ROOT")
        db_paths[db_id] = resolved_db_path
        db_hashes[db_labels[db_id]] = sha256_file(db_path)

    require(args.dev_json.is_file() and args.tables_json.is_file(), "INPUT_FILE_MISSING_AFTER_HASH")
    question_rows = read_json(args.dev_json)
    schema_rows = read_json(args.tables_json)
    require(isinstance(question_rows, list) and len(question_rows) == 1534, "QUESTION_COUNT_MISMATCH")
    require(isinstance(schema_rows, list), "SCHEMA_ROOT_INVALID")
    questions_by_key = {question_key(row): row for row in question_rows if isinstance(row, dict)}
    require(len(questions_by_key) == len(question_rows), "QUESTION_KEY_DUPLICATE")
    schema_by_db = {str(row["db_id"]): row for row in schema_rows if isinstance(row, dict)}
    require(len(schema_by_db) == len(schema_rows), "SCHEMA_DB_ID_DUPLICATE")
    require(all(db_id in schema_by_db for db_id in db_ids), "SCHEMA_DB_NOT_FOUND")

    args.output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(args.output_dir, 0o700)
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    unit_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    candidate_count = sum(len(row.get("candidate_mappings", [])) for row in selected_units)
    require(candidate_count <= 500, "CANDIDATE_BUDGET_EXCEEDED")

    try:
        for index, unit in enumerate(selected_units, start=1):
            label = db_labels[str(unit["db_id"])]
            summary, private = run_unit(
                unit,
                questions_by_key,
                schema_by_db,
                db_paths[str(unit["db_id"])],
                label,
            )
            unit_rows.append(summary)
            private_rows.append(private)
            if index % 10 == 0 or index == len(selected_units):
                print(f"progress={index}/{len(selected_units)} complete={sum(row['status'] == 'complete' for row in unit_rows)}")
            wall = time.perf_counter() - wall_start
            cpu = total_cpu_seconds()
            rss = peak_rss_gib()
            require(wall <= MAX_WALL_SECONDS, "RESOURCE_WALL_LIMIT")
            require(cpu <= MAX_CPU_SECONDS, "RESOURCE_CPU_LIMIT")
            require(max(rss.values()) <= MAX_RSS_GIB, "RESOURCE_RSS_LIMIT")
    except StopRun:
        raise

    summary = summarize_units(unit_rows)
    if args.mode == "smoke":
        smoke_pass = (
            summary["complete_units"] == EXPECTED_SMOKE_COUNT
            and summary["status_counts"].get("not_substitutable", 0) == 0
            and summary["status_counts"].get("gold_execution_unknown", 0) == 0
        )
        require(smoke_pass, "SMOKE_COVERAGE_GATE_FAILED")
    else:
        complete_labels = {row["anonymous_db"] for row in unit_rows if row.get("status") == "complete"}
        require(summary["complete_units"] >= 80, "FULL_COVERAGE_GATE_FAILED")
        require(len(complete_labels) >= 3, "FULL_DATABASE_COVERAGE_GATE_FAILED")

    total_wall = time.perf_counter() - wall_start
    total_cpu = total_cpu_seconds()
    rss = peak_rss_gib()
    require(total_wall <= MAX_WALL_SECONDS, "RESOURCE_WALL_LIMIT")
    require(total_cpu <= MAX_CPU_SECONDS, "RESOURCE_CPU_LIMIT")
    require(max(rss.values()) <= MAX_RSS_GIB, "RESOURCE_RSS_LIMIT")

    full_nonempty = summary["nonempty_gold_units"]["denominator"]
    positive_rate = summary["nonempty_gold_units"]["bag_rate"]
    if args.mode == "smoke":
        status = "SMOKE_PASS"
    elif full_nonempty == 0:
        status = "INCONCLUSIVE_NO_NONEMPTY_GOLD"
    elif positive_rate is not None and positive_rate >= 0.10:
        status = "POSITIVE_INSTANCE_EQUIVALENCE_SIGNAL"
    elif positive_rate is not None and positive_rate <= 0.05:
        status = "WEAK_INSTANCE_EQUIVALENCE_SIGNAL"
    else:
        status = "INCONCLUSIVE"

    aggregate = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": status,
        "source_commit": source_commit,
        "source_branch": EXPECTED_BRANCH,
        "inputs": {
            **input_hashes,
            "sqlite_database_hashes_by_anonymous_db": db_hashes,
        },
        "dataset": {
            "name": "BIRD dev",
            "smoke_units": EXPECTED_SMOKE_COUNT,
            "full_units": EXPECTED_FULL_COUNT,
            "selected_units": len(selected_units),
            "anonymous_databases": len(db_ids),
            "candidate_mapping_rows": candidate_count,
        },
        "metrics": summary,
        "resources": {
            "environment": "think2sql_20260909",
            "python": platform.python_version(),
            "sqlglot": sqlglot.__version__,
            "sqlite": sqlite3.sqlite_version,
            "cpu_threads": 8,
            "wall_seconds": round(total_wall, 6),
            "cpu_seconds_parent": round(time.process_time() - cpu_start, 6),
            "cpu_seconds_including_children": round(total_cpu, 6),
            "peak_rss_gib_parent": rss["parent"],
            "peak_rss_gib_largest_child": rss["largest_child"],
            "gpu_seconds": 0,
            "model_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "external_api_requests": 0,
            "external_api_cost_cny": "0.00",
        },
        "interpretation_limit": config["interpretation_limit"],
    }
    write_json(args.output_dir / "aggregate_summary.json", aggregate)
    write_json(args.output_dir / "private_unit_metrics.json", {"units": unit_rows, "candidates": private_rows})
    write_json(
        args.output_dir / "run_metadata.json",
        {
            "run_id": args.run_id,
            "config_sha256": sha256_file(args.config),
            "runner_sha256": sha256_file(Path(__file__)),
            "source_commit": source_commit,
            "database_paths": {label: str(db_paths[db_id]) for db_id, label in db_labels.items()},
        },
    )
    return aggregate


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    try:
        aggregate = run(args)
        print(json.dumps({"status": aggregate["status"], "metrics": aggregate["metrics"], "resources": aggregate["resources"]}, sort_keys=True))
        return 0
    except StopRun as error:
        if output_dir.exists():
            write_json(output_dir / "failure.json", {"experiment_id": EXPERIMENT_ID, "run_id": args.run_id, "mode": args.mode, "status": "STOPPED", "reason_code": error.code})
        print(json.dumps({"status": "STOPPED", "reason_code": error.code}, sort_keys=True))
        return 2
    except Exception as error:  # noqa: BLE001 - don't leak local SQL or row data.
        reason = f"INTERNAL_ERROR_{type(error).__name__}"
        if output_dir.exists():
            write_json(output_dir / "failure.json", {"experiment_id": EXPERIMENT_ID, "run_id": args.run_id, "mode": args.mode, "status": "STOPPED", "reason_code": reason})
        print(json.dumps({"status": "STOPPED", "reason_code": reason}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
