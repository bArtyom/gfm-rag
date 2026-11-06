#!/usr/bin/env python3
"""Prepare a private, SQL-derived FK mapping rank sample and data gate."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
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

import prepare_p0_fk_disagreement_review_packet as prep  # noqa: E402
from audit_minidev_sql_fk_labels import (  # noqa: E402
    _column_index,
    _mapping_matches_equalities,
    _qualified_column_pair,
    _resolve_column,
    _scope_aliases,
    parse_gold_sql,
    table_pair_key,
)
from audit_p0_fk_sql_used_mapping_alignment_20261107_02 import (  # noqa: E402
    build_known_columns,
    read_json,
)

EXPERIMENT_ID = "p0_fk_sql_used_mapping_rank_20261107_02"
EXPECTED_RUN_ID = "p0_fk_sql_used_mapping_rank_20261107_02_cpu_001"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_CONFIG_PATH = "configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_02.json"
EXPECTED_SQLGLOT = "28.0.0"
MIN_FULL_UNITS = 30
MIN_DATABASES = 3
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
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def current_branch(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_clean_worktree(root: Path) -> None:
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    require(not status.strip(), "WORKTREE_NOT_CLEAN")


def write_private(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def review_mapping_id(canonical_id: str) -> str:
    return "M" + hashlib.sha256(canonical_id.encode("utf-8")).hexdigest()[:12].upper()


def render_mapping_expression(candidate: dict[str, Any]) -> str:
    child = str(candidate["child_table"])
    parent = str(candidate["parent_table"])
    pairs = candidate["ordered_column_pairs"]
    return " AND ".join(
        f"{child}.{str(child_column)} = {parent}.{str(parent_column)}"
        for child_column, parent_column in pairs
    ).replace("|", "&#124;")


def write_model_review_packets(
    output_dir: Path,
    units_by_id: dict[str, dict[str, Any]],
    smoke_ids: set[str],
) -> dict[str, str]:
    """Write local-only A/B packets; reviewers see neither SQL nor target IDs."""
    packet_hashes: dict[str, str] = {}
    mode_units = {
        "smoke": [units_by_id[key] for key in sorted(smoke_ids)],
        "full": [units_by_id[key] for key in sorted(set(units_by_id) - smoke_ids)],
    }
    for mode, units in mode_units.items():
        for reviewer in ("A", "B"):
            lines: list[str] = []
            ordered_units = sorted(
                units,
                key=lambda row: hashlib.sha256(
                    f"{EXPERIMENT_ID}:{reviewer}:{mode}:{row['unit_id']}".encode("utf-8")
                ).hexdigest(),
            )
            for unit in ordered_units:
                question = re.sub(r"\s+", " ", str(unit["question"])).strip()
                require(bool(question) and "\n" not in question and "\r" not in question, "REVIEW_QUESTION_NOT_SINGLE_LINE")
                case_id = unit["review_case_id"]
                pair_id = unit["review_pair_id"]
                pair_name = " ↔ ".join(str(value) for value in unit["table_pair"]).replace("|", "&#124;")
                candidates = list(unit["candidate_mappings"])
                display_ids = [review_mapping_id(str(candidate["mapping_id"])) for candidate in candidates]
                require(len(display_ids) == len(set(display_ids)), "REVIEW_MAPPING_ID_COLLISION")
                order_key = lambda row: hashlib.sha256(
                    f"{EXPERIMENT_ID}:{reviewer}:{unit['unit_id']}:{row['mapping_id']}".encode("utf-8")
                ).hexdigest()
                candidates.sort(key=order_key)
                if reviewer == "B" and len(candidates) > 1:
                    a_order = sorted(
                        unit["candidate_mappings"],
                        key=lambda row: hashlib.sha256(
                            f"{EXPERIMENT_ID}:A:{unit['unit_id']}:{row['mapping_id']}".encode("utf-8")
                        ).hexdigest(),
                    )
                    if [row["mapping_id"] for row in candidates] == [row["mapping_id"] for row in a_order]:
                        candidates.reverse()
                lines.extend([f"## Case {case_id}", question, "", f"### Pair {pair_id}: {pair_name}"])
                for candidate in candidates:
                    display_id = review_mapping_id(str(candidate["mapping_id"]))
                    lines.append(f"| {display_id} | {render_mapping_expression(candidate)} |")
                lines.append("")
            payload = "\n".join(lines).rstrip() + "\n"
            path = output_dir / f"reviewer_{reviewer}_{mode}_packet.md"
            path.write_text(payload, encoding="utf-8")
            path.chmod(0o600)
            packet_hashes[f"reviewer_{reviewer}_{mode}"] = sha256_file(path)
    return packet_hashes


def mapping_id(identity: tuple[Any, ...]) -> str:
    return "fk_" + stable_hash(identity)[:20]


def valid_mappings_by_db(frozen: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[tuple[str, str], list[dict[str, Any]]]]]:
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for db_id, rows in frozen["fk_by_db"].items():
        for raw in rows:
            identity = raw["identity"]
            candidate = {
                "mapping_id": mapping_id(identity),
                "identity": ["declared_fk", raw["child_table"], [list(pair) for pair in raw["ordered_column_pairs"]], raw["parent_table"]],
                "child_table": raw["child_table"],
                "parent_table": raw["parent_table"],
                "ordered_column_pairs": [list(pair) for pair in raw["ordered_column_pairs"]],
                "multiplicity": int(raw["multiplicity"]),
            }
            by_db[str(db_id)].append(candidate)
            key = table_pair_key(candidate["child_table"], candidate["parent_table"])
            by_pair[str(db_id)][key].append(candidate)
    for db_id in by_db:
        ids = [row["mapping_id"] for row in by_db[db_id]]
        require(len(ids) == len(set(ids)), "CANONICAL_MAPPING_ID_COLLISION")
        for pair, rows in by_pair[db_id].items():
            pair_ids = [row["mapping_id"] for row in rows]
            require(len(pair_ids) == len(set(pair_ids)), "PAIR_MAPPING_ID_COLLISION")
    return by_db, by_pair


def resolve_sql_targets(
    sql: str,
    known_columns: dict[str, set[str]],
    candidates_by_pair: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    counters = {
        "join_count": 0,
        "using_join_count": 0,
        "join_on_equality_count": 0,
        "qualified_join_equality_count": 0,
        "resolved_qualified_join_equality_count": 0,
        "unresolved_qualified_join_equality_count": 0,
        "scope_analysis_error_count": 0,
    }
    try:
        parsed = [node for node in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE) if node is not None]
    except Exception as error:  # noqa: BLE001
        return {"parse_success": False, "parse_error_class": type(error).__name__, "counters": counters, "pair_groups": []}
    if len(parsed) != 1:
        return {"parse_success": False, "parse_error_class": "statement_count", "counters": counters, "pair_groups": []}

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    group_equalities: dict[tuple[int, int, tuple[str, str], tuple[str, str]], list[tuple[tuple[str, str], tuple[str, str]]]] = defaultdict(list)
    group_display: dict[tuple[int, int, tuple[str, str], tuple[str, str]], dict[str, Any]] = {}
    try:
        for scope_index, scope in enumerate(traverse_scope(parsed[0])):
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
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not join:
                        continue
                    counters["join_on_equality_count"] += 1
                    left, right = equality.this, equality.expression
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
                    pair = table_pair_key(resolved_left[0], resolved_right[0])
                    alias_pair = tuple(sorted((left_alias, right_alias)))
                    group_key = (scope_index, join_index, alias_pair, pair)
                    group_equalities[group_key].append((resolved_left, resolved_right))
                    group_display[group_key] = {
                        "pair": list(pair),
                        "alias_pair": list(alias_pair),
                        "equalities": group_equalities[group_key],
                    }
    except Exception as error:  # noqa: BLE001
        counters["scope_analysis_error_count"] += 1
        return {
            "parse_success": True,
            "parse_error_class": None,
            "scope_error_class": type(error).__name__,
            "counters": counters,
            "pair_groups": [],
        }

    grouped_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for group_key, equalities in group_equalities.items():
        pair = group_key[3]
        candidate_rows = candidates_by_pair.get(pair, [])
        exact_ids = sorted(
            str(candidate["mapping_id"])
            for candidate in candidate_rows
            if _mapping_matches_equalities(candidate, equalities)
        )
        row = grouped_pairs.setdefault(
            pair,
            {"candidate_count": len(candidate_rows), "sql_used_mapping_ids": set(), "join_alias_group_count": 0},
        )
        row["join_alias_group_count"] += 1
        row["sql_used_mapping_ids"].update(exact_ids)

    normalized_groups = []
    for pair, row in sorted(grouped_pairs.items()):
        normalized_groups.append({
            "pair": list(pair),
            "candidate_count": int(row["candidate_count"]),
            "sql_used_mapping_ids": sorted(row["sql_used_mapping_ids"]),
            "join_alias_group_count": int(row["join_alias_group_count"]),
        })

    reference = parse_gold_sql(
        sql,
        db_id="",
        known_columns=known_columns,
        candidate_mappings=[row for rows in candidates_by_pair.values() for row in rows],
    )
    expected_gold = {
        tuple(pair): sorted(ids)
        for pair, ids in reference.get("gold_mapping_ids_by_table_pair", {}).items()
    }
    observed_gold = {
        tuple(row["pair"]): row["sql_used_mapping_ids"]
        for row in normalized_groups
        if row["candidate_count"] >= 2 and row["sql_used_mapping_ids"]
    }
    require(expected_gold == observed_gold, "INDEPENDENT_TARGET_EXTRACTORS_DISAGREE")
    for field in ("parse_success", "qualified_join_equality_count", "resolved_qualified_join_equality_count", "unresolved_qualified_join_equality_count", "scope_analysis_error_count"):
        if field == "parse_success":
            require(reference.get(field) is True, "REFERENCE_PARSER_PARSE_DISAGREEMENT")
        else:
            require(int(reference.get(field, -1)) == int(counters[field]), f"REFERENCE_PARSER_COUNTER_MISMATCH_{field.upper()}")
    return {
        "parse_success": True,
        "parse_error_class": None,
        "counters": counters,
        "pair_groups": normalized_groups,
    }


def anonymous_db_map(db_ids: set[str]) -> dict[str, str]:
    ordered = sorted(db_ids, key=lambda value: hashlib.sha256(f"{EXPERIMENT_ID}:{value}".encode("utf-8")).hexdigest())
    return {db_id: f"db_{index:02d}" for index, db_id in enumerate(ordered, start=1)}


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(args.config)
    require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_ID_MISMATCH")
    require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGLOT_VERSION_MISMATCH")
    require(current_branch(args.repo_root) == EXPECTED_BRANCH, "BRANCH_MISMATCH")
    require(current_commit(args.repo_root) == args.expected_commit, "SOURCE_COMMIT_MISMATCH")
    require_clean_worktree(args.repo_root)
    require(args.run_id == EXPECTED_RUN_ID, "RUN_ID_MISMATCH")
    require(args.amendment_config is None, "UNEXPECTED_AMENDMENT_CONFIG")
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")

    expected_inputs = {
        "dev_json": args.dev_json,
        "dev_tables_json": args.tables_json,
        "fk_artifact": args.fk_artifact,
        "crosswalk_private": args.crosswalk_private,
        "canonical_full": args.canonical_full,
    }
    for name, path in expected_inputs.items():
        expected_sha = str(config["inputs"][name]["sha256"])
        actual_sha = sha256_file(path)
        require(actual_sha == expected_sha, f"INPUT_HASH_MISMATCH_{name.upper()}:expected={expected_sha}:actual={actual_sha}")
    exclusion_path = Path(config["inputs"]["exclusion_manifest"]["path"])
    expected_exclusion_sha = str(config["inputs"]["exclusion_manifest"]["sha256"])
    actual_exclusion_sha = sha256_file(exclusion_path)
    require(
        actual_exclusion_sha == expected_exclusion_sha,
        f"INPUT_HASH_MISMATCH_EXCLUSION_MANIFEST:expected={expected_exclusion_sha}:actual={actual_exclusion_sha}",
    )

    started = time.perf_counter()
    cpu_started = time.process_time()
    frozen = prep.load_frozen_inputs(args)
    require(len(frozen["questions"]) == 1534, "QUESTION_COUNT_MISMATCH")
    old_manifest = read_json(exclusion_path)
    old_cases = old_manifest.get("selected_cases_private")
    require(isinstance(old_cases, list) and len(old_cases) == 60, "EXCLUSION_MANIFEST_COUNT_MISMATCH")
    excluded_qkeys = {str(row["question_key_sha256"]) for row in old_cases}
    require(bool(excluded_qkeys), "EXCLUSION_QUESTION_KEYS_EMPTY")

    mappings_by_db, candidates_by_db_pair = valid_mappings_by_db(frozen)
    known_columns_by_db = {
        str(row["db_id"]): build_known_columns(row)
        for row in read_json(args.tables_json)
    }
    require(set(known_columns_by_db) == set(mappings_by_db), "SCHEMA_FK_DATABASE_SET_MISMATCH")

    totals = Counter()
    failures = Counter()
    complete_sql_units: list[dict[str, Any]] = []
    all_multifk_join_pair_count = 0
    matched_multifk_join_pair_count = 0
    unmatched_multifk_join_pair_count = 0
    for qkey, record in frozen["questions"].items():
        canonical = frozen["canonical"].get(qkey, {})
        if canonical.get("has_join_on") is not True:
            continue
        totals["join_on_questions"] += 1
        db_id = str(record["db_id"])
        sql = record.get("SQL")
        if not isinstance(sql, str) or not sql.strip():
            failures["REFERENCE_SQL_MISSING"] += 1
            continue
        resolved = resolve_sql_targets(sql, known_columns_by_db[db_id], candidates_by_db_pair[db_id])
        counters = resolved["counters"]
        totals["parsed_sql_questions"] += int(resolved["parse_success"])
        totals["scope_analysis_errors"] += int(counters["scope_analysis_error_count"])
        totals["qualified_join_equalities"] += int(counters["qualified_join_equality_count"])
        totals["resolved_qualified_join_equalities"] += int(counters["resolved_qualified_join_equality_count"])
        totals["unresolved_qualified_join_equalities"] += int(counters["unresolved_qualified_join_equality_count"])
        if not resolved["parse_success"]:
            failures[str(resolved["parse_error_class"] or "SQL_PARSE_FAILURE")] += 1
            continue
        if int(counters["scope_analysis_error_count"]):
            failures[str(resolved.get("scope_error_class") or "SCOPE_ANALYSIS_FAILURE")] += 1
            continue
        complete = (
            int(counters["qualified_join_equality_count"]) > 0
            and int(counters["resolved_qualified_join_equality_count"]) == int(counters["qualified_join_equality_count"])
            and int(counters["unresolved_qualified_join_equality_count"]) == 0
        )
        if not complete:
            failures["INCOMPLETE_QUALIFIED_JOIN_RESOLUTION"] += 1
            continue
        totals["fully_resolved_join_sql_questions"] += 1
        valid_candidate_groups = []
        for group in resolved["pair_groups"]:
            if int(group["candidate_count"]) < 2:
                continue
            totals["multi_fk_sql_join_pair_groups"] += int(group["join_alias_group_count"])
            all_multifk_join_pair_count += 1
            target_ids = sorted(set(group["sql_used_mapping_ids"]))
            if target_ids:
                matched_multifk_join_pair_count += 1
                candidate_ids = {row["mapping_id"] for row in candidates_by_db_pair[db_id][tuple(group["pair"])]}
                require(set(target_ids) <= candidate_ids, "SQL_TARGET_OUTSIDE_CANDIDATE_UNIVERSE")
                valid_candidate_groups.append({
                    "pair": list(group["pair"]),
                    "candidate_mappings": candidates_by_db_pair[db_id][tuple(group["pair"])],
                    "sql_used_mapping_ids": target_ids,
                })
            else:
                unmatched_multifk_join_pair_count += 1

        if not valid_candidate_groups:
            continue
        pair_rows = []
        for group in valid_candidate_groups:
            pair = group["pair"]
            pair_hash = stable_hash(pair)
            pair_rows.append((
                hashlib.sha256(f"{EXPERIMENT_ID}:{qkey}:{pair_hash}".encode("utf-8")).hexdigest(),
                group,
            ))
        _, chosen = min(pair_rows, key=lambda item: item[0])
        pair = tuple(chosen["pair"])
        question = str(record.get("question", ""))
        require(question.strip(), "QUESTION_TEXT_EMPTY")
        unit_id = stable_hash([EXPERIMENT_ID, qkey, list(pair)])
        review_id_map = {
            review_mapping_id(str(candidate["mapping_id"])): str(candidate["mapping_id"])
            for candidate in chosen["candidate_mappings"]
        }
        require(len(review_id_map) == len(chosen["candidate_mappings"]), "REVIEW_MAPPING_ID_COLLISION")
        complete_sql_units.append({
            "unit_id": unit_id,
            "question_key_sha256": qkey,
            "question_id": str(record.get("question_id", "")),
            "db_id": db_id,
            "question": question,
            "question_sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            "table_pair": list(pair),
            "candidate_mappings": chosen["candidate_mappings"],
            "sql_used_mapping_ids": chosen["sql_used_mapping_ids"],
            "sql_parse_counters": dict(counters),
            "review_case_id": "C" + unit_id[:12].upper(),
            "review_pair_id": "P" + unit_id[:12].upper(),
            "review_mapping_id_to_canonical_id": review_id_map,
        })

    excluded = [row for row in complete_sql_units if row["question_key_sha256"] in excluded_qkeys]
    fresh = [row for row in complete_sql_units if row["question_key_sha256"] not in excluded_qkeys]
    require(len({row["question_key_sha256"] for row in fresh}) == len(fresh), "ONE_UNIT_PER_QUESTION_VIOLATION")
    fresh.sort(key=lambda row: row["question_key_sha256"])
    smoke_units = sorted(
        fresh,
        key=lambda row: hashlib.sha256(f"{EXPERIMENT_ID}:{row['question_key_sha256']}".encode("utf-8")).hexdigest(),
    )[:5]
    smoke_ids = {row["unit_id"] for row in smoke_units}
    full_units = [row for row in fresh if row["unit_id"] not in smoke_ids]
    db_ids = {row["db_id"] for row in full_units}
    db_aliases = anonymous_db_map(db_ids)
    per_db_full = Counter(row["db_id"] for row in full_units)
    data_gate = len(full_units) >= MIN_FULL_UNITS and len([db for db, count in per_db_full.items() if count > 0]) >= MIN_DATABASES
    if len(smoke_units) != 5:
        status = "STOP_FEWER_THAN_FIVE_ELIGIBLE_SMOKE_UNITS"
    elif not data_gate:
        status = "STOP_DATA_GATE"
    else:
        status = "CPU_DATA_GATE_PASS"

    output = {
        "experiment_id": EXPERIMENT_ID,
        "status": status,
        "source_commit": args.expected_commit,
        "config_sha256": sha256_file(args.config),
        "recovery_config_sha256": None,
        "input_sha256": frozen["input_hashes"],
        "exclusion_manifest_sha256": sha256_file(Path(config["inputs"]["exclusion_manifest"]["path"])),
        "sqlglot_version": sqlglot.__version__,
        "run_id": args.run_id,
        "unit_count_after_exclusion": len(fresh),
        "smoke_unit_count": len(smoke_units),
        "full_unit_count": len(full_units),
        "full_anonymous_database_count": len(db_ids),
        "full_units_by_anonymous_database": {
            db_aliases[db_id]: per_db_full[db_id]
            for db_id in sorted(db_ids, key=lambda value: db_aliases[value])
        },
        "sql_parse_and_identity_coverage": {
            "join_on_question_count": int(totals["join_on_questions"]),
            "parsed_question_count": int(totals["parsed_sql_questions"]),
            "fully_resolved_question_count": int(totals["fully_resolved_join_sql_questions"]),
            "qualified_join_equality_count": int(totals["qualified_join_equalities"]),
            "resolved_qualified_join_equality_count": int(totals["resolved_qualified_join_equalities"]),
            "unresolved_qualified_join_equality_count": int(totals["unresolved_qualified_join_equalities"]),
            "scope_analysis_error_count": int(totals["scope_analysis_errors"]),
            "multi_fk_sql_join_pair_groups": int(totals["multi_fk_sql_join_pair_groups"]),
            "candidate_covered_multi_fk_join_pair_count": matched_multifk_join_pair_count,
            "candidate_uncovered_multi_fk_join_pair_count": unmatched_multifk_join_pair_count,
            "candidate_coverage_rate": round(matched_multifk_join_pair_count / all_multifk_join_pair_count, 6) if all_multifk_join_pair_count else None,
            "parse_failures_by_safe_class": dict(sorted(failures.items())),
        },
        "gates": {
            "full_units_min_30": len(full_units) >= MIN_FULL_UNITS,
            "full_databases_min_3": len(db_ids) >= MIN_DATABASES,
            "smoke_count_is_5": len(smoke_units) == 5,
        },
        "resource_usage": {
            "wall_seconds": round(time.perf_counter() - started, 6),
            "cpu_seconds": round(time.process_time() - cpu_started, 6),
            "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6),
            "gpu_calls": 0,
            "model_calls": 0,
            "external_api_calls": 0,
            "sql_execution_calls": 0,
        },
        "privacy": {
            "public_safe_aggregate_only": True,
            "sql_persisted": False,
            "question_or_schema_text_in_public_result": False,
            "row_ids_or_mapping_ids_in_public_result": False,
        },
    }
    private_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "source_commit": args.expected_commit,
        "config_sha256": output["config_sha256"],
        "input_sha256": frozen["input_hashes"],
        "exclusion_manifest_sha256": output["exclusion_manifest_sha256"],
        "smoke_unit_ids": sorted(smoke_ids),
        "full_unit_ids": sorted(row["unit_id"] for row in full_units),
        "units": {row["unit_id"]: row for row in fresh},
    }
    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    if status == "CPU_DATA_GATE_PASS":
        packet_hashes = write_model_review_packets(args.output_dir, private_manifest["units"], smoke_ids)
        output["model_review_packets"] = {
            "reviewers": {
                "A": "Qwen2.5-Coder-7B-Instruct",
                "B": "Qwen3-4B-Think2SQL",
            },
            "review_target": "secondary model-proxy semantic mapping labels; no SQL or SQL-used target exposed",
            "packet_sha256": packet_hashes,
            "trusted_human_role_labels": 0,
        }
    else:
        output["model_review_packets"] = {
            "status": "NOT_CREATED_DATA_GATE_FAILED",
            "trusted_human_role_labels": 0,
        }
    write_private(args.output_dir / "prepared_manifest_private.json", private_manifest)
    output["prepared_manifest_sha256"] = sha256_file(args.output_dir / "prepared_manifest_private.json")
    write_private(args.output_dir / "aggregate_summary.json", output)
    return output


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--amendment-config", type=Path)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--fk-artifact", type=Path, required=True)
    parser.add_argument("--crosswalk-private", type=Path, required=True)
    parser.add_argument("--canonical-full", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.config.resolve().as_posix().endswith(EXPECTED_CONFIG_PATH) is False:
        print("status=STOP_CONFIG_PATH_MISMATCH")
        return 2
    if args.output_dir.exists():
        print("status=STOP_OUTPUT_DIRECTORY_ALREADY_EXISTS")
        return 2
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = prepare(args)
    except StopRun as error:
        args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        args.output_dir.chmod(0o700)
        write_private(args.output_dir / "failure.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "STOPPED",
            "reason_code": error.code,
            "source_commit": args.expected_commit,
            "started_at_utc": started,
        })
        print(f"status=STOPPED reason_code={error.code}")
        return 2
    resource_failures = []
    if result["resource_usage"]["wall_seconds"] > MAX_WALL_SECONDS:
        resource_failures.append("CPU_WALL_LIMIT")
    if result["resource_usage"]["cpu_seconds"] > MAX_CPU_SECONDS:
        resource_failures.append("CPU_PROCESS_LIMIT")
    if result["resource_usage"]["peak_rss_gib"] > MAX_RSS_GIB:
        resource_failures.append("CPU_RSS_LIMIT")
    if resource_failures:
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "STOPPED_RESOURCE_LIMIT",
            "reason_codes": resource_failures,
            "resource_usage": result["resource_usage"],
        }
        write_private(args.output_dir / "resource_stop.json", failure)
        print(json.dumps({"status": failure["status"], "reason_codes": resource_failures}, sort_keys=True))
        return 3
    print(json.dumps({
        "status": result["status"],
        "unit_count_after_exclusion": result["unit_count_after_exclusion"],
        "smoke_unit_count": result["smoke_unit_count"],
        "full_unit_count": result["full_unit_count"],
        "full_anonymous_database_count": result["full_anonymous_database_count"],
        "candidate_coverage_rate": result["sql_parse_and_identity_coverage"]["candidate_coverage_rate"],
    }, sort_keys=True))
    return 0 if result["status"] == "CPU_DATA_GATE_PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
