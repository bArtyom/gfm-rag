#!/usr/bin/env python3
"""Re-evaluate frozen FK mapping rankings against reference-SQL-used mappings.

This CPU-only audit reads a small, frozen set of BIRD dev reference SQLs and
existing local reviewer/ranker outputs. It never writes SQL, question text,
database names, mapping IDs, or row-level results to the public aggregate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
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

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aggregate_p0_fk_mapping_model_review_three_proxy import (  # noqa: E402
    normalized_label,
    read_jsonl,
)
from audit_minidev_sql_fk_labels import parse_gold_sql  # noqa: E402
from prepare_p0_fk_disagreement_review_packet import question_key  # noqa: E402


EXPERIMENT_ID = "p0_fk_sql_used_mapping_alignment_20261107_01"
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


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - keep error output free of source contents.
        raise StopRun(f"JSON_READ_{type(error).__name__}") from None


def stable_hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def current_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def file_hashes(inputs: dict[str, dict[str, str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in inputs.items():
        path = Path(spec["path"])
        require(path.is_file(), f"INPUT_MISSING_{name}")
        digest = sha256_file(path)
        require(digest == spec["sha256"], f"INPUT_HASH_MISMATCH_{name}")
        observed[name] = digest
    return observed


def read_identity_mappings(manifest_row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest_row.get("mapping_identities")
    require(isinstance(raw, list) and len(raw) >= 2, "MANIFEST_MAPPING_LIST_INVALID")
    mappings: list[dict[str, Any]] = []
    mapping_ids: set[str] = set()
    for entry in raw:
        mapping_id = entry.get("mapping_id")
        identity = entry.get("identity")
        require(isinstance(mapping_id, str) and mapping_id, "MANIFEST_MAPPING_ID_INVALID")
        require(mapping_id not in mapping_ids, "MANIFEST_MAPPING_ID_DUPLICATE")
        require(isinstance(identity, list) and len(identity) == 4, "MANIFEST_MAPPING_IDENTITY_INVALID")
        child_table, parent_table, ordered_pairs, _multiplicity = identity
        require(
            isinstance(child_table, str)
            and isinstance(parent_table, str)
            and isinstance(ordered_pairs, list)
            and bool(ordered_pairs),
            "MANIFEST_MAPPING_IDENTITY_INVALID",
        )
        normalized_pairs: list[list[str]] = []
        for pair in ordered_pairs:
            require(
                isinstance(pair, list)
                and len(pair) == 2
                and all(isinstance(value, str) for value in pair),
                "MANIFEST_MAPPING_COLUMN_PAIR_INVALID",
            )
            normalized_pairs.append([pair[0], pair[1]])
        mappings.append(
            {
                "mapping_id": mapping_id,
                "child_table": child_table,
                "parent_table": parent_table,
                "ordered_column_pairs": normalized_pairs,
            }
        )
        mapping_ids.add(mapping_id)
    return mappings


def build_known_columns(schema_row: dict[str, Any]) -> dict[str, set[str]]:
    table_names = schema_row.get("table_names_original")
    column_rows = schema_row.get("column_names_original")
    require(isinstance(table_names, list) and isinstance(column_rows, list), "SCHEMA_ROW_INVALID")
    result: dict[str, set[str]] = {str(table): set() for table in table_names}
    require(len(result) == len(table_names), "SCHEMA_TABLE_DUPLICATE")
    for row in column_rows:
        require(isinstance(row, list) and len(row) == 2, "SCHEMA_COLUMN_ROW_INVALID")
        table_index, column_name = row
        if int(table_index) < 0 or str(column_name) == "*":
            continue
        require(int(table_index) < len(table_names), "SCHEMA_COLUMN_TABLE_INDEX_INVALID")
        result[str(table_names[int(table_index)])].add(str(column_name))
    return result


def table_pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right), key=lambda value: (value.casefold(), value)))


def sql_used_ids(
    sql: str,
    db_id: str,
    known_columns: dict[str, set[str]],
    candidate_mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed = parse_gold_sql(
        sql,
        db_id=db_id,
        known_columns=known_columns,
        candidate_mappings=candidate_mappings,
    )
    if parsed.get("parse_success") is not True:
        return {
            "parse_success": False,
            "parse_error_class": parsed.get("parse_error_class"),
            "scope_analysis_error_count": int(parsed.get("scope_analysis_error_count", 0)),
            "counters": {key: int(value) for key, value in parsed.items() if key.endswith("_count")},
            "resolution_complete": False,
            "gold_mapping_ids": [],
        }
    if int(parsed.get("scope_analysis_error_count", 0)):
        return {
            "parse_success": True,
            "parse_error_class": None,
            "scope_analysis_error_count": int(parsed["scope_analysis_error_count"]),
            "counters": {key: int(value) for key, value in parsed.items() if key.endswith("_count")},
            "resolution_complete": False,
            "gold_mapping_ids": [],
        }

    qualified = int(parsed.get("qualified_join_equality_count", 0))
    resolved = int(parsed.get("resolved_qualified_join_equality_count", 0))
    unresolved = int(parsed.get("unresolved_qualified_join_equality_count", 0))
    resolution_complete = qualified > 0 and resolved == qualified and unresolved == 0

    candidate_pair = table_pair_key(
        str(candidate_mappings[0]["child_table"]),
        str(candidate_mappings[0]["parent_table"]),
    )
    matched: set[str] = set()
    for pair, mapping_ids in parsed.get("gold_mapping_ids_by_table_pair", {}).items():
        if tuple(value.casefold() for value in pair) == tuple(value.casefold() for value in candidate_pair):
            matched.update(str(mapping_id) for mapping_id in mapping_ids)
    return {
        "parse_success": True,
        "parse_error_class": None,
        "scope_analysis_error_count": 0,
        "counters": {key: int(value) for key, value in parsed.items() if key.endswith("_count")},
        "resolution_complete": resolution_complete,
        "gold_mapping_ids": sorted(matched),
    }


def proxy_consensus(
    pair_id: str,
    candidate_ids: set[str],
    reviewers: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    votes: dict[tuple[str, tuple[str, ...]], list[int]] = defaultdict(list)
    for rows in reviewers.values():
        row = rows[pair_id]
        label = normalized_label(row)
        if label is None:
            continue
        decision, accepted = label
        require(set(accepted) <= candidate_ids, "REVIEWER_SELECTED_NONCANDIDATE")
        confidence = int(row["answer"]["confidence"])
        votes[(decision, accepted)].append(confidence)
    supported = [
        (label, confidence_values)
        for label, confidence_values in votes.items()
        if sum(value >= 2 for value in confidence_values) >= 2
    ]
    if len(supported) != 1:
        return None
    (decision, accepted), _ = supported[0]
    if decision not in {"single_mapping", "multiple_mappings"} or not accepted:
        return None
    return {"decision": decision, "accepted_mapping_ids": list(accepted)}


def selected_row(
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
    db_id = str(record["db_id"])
    schema_row = schemas_by_db.get(db_id)
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


def aggregate_metrics(private_rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluable = [
        row for row in private_rows
        if row["resolution_complete"] and row["sql_used_mapping_ids"]
    ]
    result: dict[str, Any] = {
        "evaluable_pair_count": len(evaluable),
        "methods": {},
        "paired_g_reasoner_vs_dense": {},
        "by_anonymous_database": {},
        "proxy_sql_alignment": {},
    }
    methods = ("g_reasoner", "dense_cosine")
    for method in methods:
        at1 = at3 = ties = 0
        reciprocal_ranks: list[float] = []
        for row in evaluable:
            gold = set(row["sql_used_mapping_ids"])
            ranking = row["ranked_mapping_ids"][method]
            ranks = [index + 1 for index, mapping_id in enumerate(ranking) if mapping_id in gold]
            require(bool(ranks), "SQL_USED_MAPPING_ABSENT_FROM_RANKING")
            at1 += int(ranking[0] in gold)
            at3 += int(any(rank <= 3 for rank in ranks))
            reciprocal_ranks.append(1.0 / min(ranks))
            ties += int(row["top_tie_counts"].get(method, 0) > 1)
        denominator = len(evaluable)
        result["methods"][method] = {
            "mapping_at_1": {
                "correct": at1,
                "denominator": denominator,
                "rate": round(at1 / denominator, 6) if denominator else None,
            },
            "mapping_at_3": {
                "correct": at3,
                "denominator": denominator,
                "rate": round(at3 / denominator, 6) if denominator else None,
            },
            "mrr_first_sql_used_mapping": round(
                sum(reciprocal_ranks) / denominator, 6
            ) if denominator else None,
            "top_score_tie_pairs": ties,
        }

    g_correct = 0
    dense_correct = 0
    g_only = 0
    dense_only = 0
    for row in evaluable:
        gold = set(row["sql_used_mapping_ids"])
        g_ok = row["ranked_mapping_ids"]["g_reasoner"][0] in gold
        dense_ok = row["ranked_mapping_ids"]["dense_cosine"][0] in gold
        g_correct += int(g_ok)
        dense_correct += int(dense_ok)
        g_only += int(g_ok and not dense_ok)
        dense_only += int(dense_ok and not g_ok)
    denominator = len(evaluable)
    delta_pp = (
        round((g_correct - dense_correct) / denominator * 100.0, 4)
        if denominator
        else None
    )
    result["paired_g_reasoner_vs_dense"] = {
        "g_only_rescues": g_only,
        "dense_only_rescues": dense_only,
        "net_rescues": g_only - dense_only,
        "mapping_at_1_delta_percentage_points": delta_pp,
    }

    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evaluable:
        by_db[row["anonymous_database"]].append(row)
    positive_databases_n5 = 0
    for db_label, rows in sorted(by_db.items()):
        g_ok = sum(
            row["ranked_mapping_ids"]["g_reasoner"][0] in set(row["sql_used_mapping_ids"])
            for row in rows
        )
        dense_ok = sum(
            row["ranked_mapping_ids"]["dense_cosine"][0] in set(row["sql_used_mapping_ids"])
            for row in rows
        )
        if len(rows) >= 5 and g_ok > dense_ok:
            positive_databases_n5 += 1
        result["by_anonymous_database"][db_label] = {
            "denominator": len(rows),
            "g_reasoner_mapping_at_1_correct": g_ok,
            "dense_mapping_at_1_correct": dense_ok,
            "net_rescues": g_ok - dense_ok,
        }
    result["positive_databases_with_n_at_least_5"] = positive_databases_n5

    proxy_rows = [row for row in evaluable if row["proxy_accepted_mapping_ids"] is not None]
    proxy_inclusion = sum(
        bool(set(row["sql_used_mapping_ids"]) & set(row["proxy_accepted_mapping_ids"]))
        for row in proxy_rows
    )
    proxy_exact = sum(
        set(row["sql_used_mapping_ids"]) == set(row["proxy_accepted_mapping_ids"])
        for row in proxy_rows
    )
    result["proxy_sql_alignment"] = {
        "proxy_adjudicable_pairs": len(proxy_rows),
        "reference_sql_mapping_in_accepted_set": proxy_inclusion,
        "reference_sql_mapping_in_accepted_set_rate": round(
            proxy_inclusion / len(proxy_rows), 6
        ) if proxy_rows else None,
        "exact_set_matches_descriptive_only": proxy_exact,
        "exact_set_match_rate_descriptive_only": round(
            proxy_exact / len(proxy_rows), 6
        ) if proxy_rows else None,
    }
    return result


def resource_snapshot(wall_start: float, cpu_start: float) -> dict[str, float]:
    return {
        "wall_seconds": round(time.perf_counter() - wall_start, 6),
        "cpu_seconds": round(time.process_time() - cpu_start, 6),
        "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6),
    }


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_private_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(0o600)


def prepare_run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    config = read_json(args.config)
    require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_ID_MISMATCH")
    require(config.get("status") == "preregistered_not_run", "CONFIG_STATUS_CHANGED")
    runner_lock = config.get("runner")
    require(isinstance(runner_lock, dict), "RUNNER_LOCK_MISSING")
    require(
        sha256_file(Path(__file__)) == runner_lock.get("sha256"),
        "RUNNER_HASH_MISMATCH",
    )
    require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGLOT_VERSION_MISMATCH")
    repo_root = args.repo_root.resolve()
    require(current_branch(repo_root) == EXPECTED_BRANCH, "GIT_BRANCH_MISMATCH")
    require(current_commit(repo_root) == args.expected_commit, "GIT_COMMIT_MISMATCH")
    require(args.run_id == config["experiment_id"].replace("_01", f"_{args.mode}_001"), "RUN_ID_MISMATCH")

    observed_hashes = file_hashes(config["inputs"])
    questions = read_json(Path(config["inputs"]["dev_json"]["path"]))
    schema_rows = read_json(Path(config["inputs"]["dev_tables_json"]["path"]))
    manifest = read_json(Path(config["inputs"]["private_pair_manifest"]["path"]))
    split = read_json(Path(config["inputs"]["rank_split"]["path"]))
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

    rows = manifest.get("selected_cases_private")
    require(isinstance(rows, list) and len(rows) == EXPECTED_PAIR_COUNT, "MANIFEST_PAIR_COUNT_MISMATCH")
    require(manifest.get("trusted_role_label_count") == 0, "TRUSTED_HUMAN_LABEL_COUNT_CHANGED")
    require(manifest.get("human_review_completed") is False, "HUMAN_REVIEW_STATE_CHANGED")
    manifest_by_pair = {str(row["pair_id"]): row for row in rows}
    require(len(manifest_by_pair) == len(rows), "MANIFEST_PAIR_ID_DUPLICATE")
    require(set(manifest_by_pair) == set(split.get("smoke_pair_ids", [])) | set(split.get("full_pair_ids", [])), "SPLIT_MANIFEST_COVERAGE_MISMATCH")
    smoke_pairs = set(split.get("smoke_pair_ids", []))
    full_pairs = set(split.get("full_pair_ids", []))
    require(len(smoke_pairs) == EXPECTED_SMOKE_COUNT, "SMOKE_SPLIT_COUNT_MISMATCH")
    require(len(full_pairs) == EXPECTED_FULL_COUNT, "FULL_SPLIT_COUNT_MISMATCH")
    require(not smoke_pairs & full_pairs, "SMOKE_FULL_OVERLAP")

    reviewer_outputs: dict[str, dict[str, dict[str, Any]]] = {}
    if args.mode == "full":
        reviewer_outputs = {
            name: read_jsonl(Path(config["inputs"][name]["path"]))
            for name in ("reviewer_a", "reviewer_b", "reviewer_c")
        }
        for name, output in reviewer_outputs.items():
            require(set(output) == set(manifest_by_pair), f"REVIEWER_COVERAGE_MISMATCH_{name}")

    predictions: dict[str, dict[str, Any]] = {}
    if args.mode == "full":
        predictions = read_jsonl(Path(config["inputs"]["rank_predictions_full"]["path"]))
        require(set(predictions) == full_pairs, "RANK_PREDICTION_COVERAGE_MISMATCH")

    database_names = sorted({str(row["private_db_id"]) for row in rows})
    database_labels = {db_id: f"DB-{chr(65 + index)}" for index, db_id in enumerate(database_names)}
    return config, {"manifest": manifest_by_pair, "split": split, "observed_hashes": observed_hashes}, questions_by_key, schemas_by_db, {"reviewers": reviewer_outputs, "predictions": predictions}, database_labels


def audit_pair(
    pair_id: str,
    manifest_row: dict[str, Any],
    questions_by_key: dict[str, dict[str, Any]],
    schemas_by_db: dict[str, dict[str, Any]],
    database_labels: dict[str, str],
) -> dict[str, Any]:
    record, known_columns, mappings = selected_row(pair_id, manifest_row, questions_by_key, schemas_by_db)
    parsed = sql_used_ids(str(record["SQL"]), str(record["db_id"]), known_columns, mappings)
    candidate_ids = {item["mapping_id"] for item in mappings}
    gold_ids = set(parsed["gold_mapping_ids"])
    require(gold_ids <= candidate_ids, "PARSED_SQL_MAPPING_NOT_IN_FROZEN_CANDIDATES")
    return {
        "pair_id": pair_id,
        "db_id": str(record["db_id"]),
        "anonymous_database": database_labels[str(record["db_id"])],
        "question_key_sha256": manifest_row["question_key_sha256"],
        "parse_success": parsed["parse_success"],
        "parse_error_class": parsed["parse_error_class"],
        "scope_analysis_error_count": parsed["scope_analysis_error_count"],
        "parser_counters": parsed["counters"],
        "resolution_complete": parsed["resolution_complete"],
        "candidate_mapping_ids": sorted(candidate_ids),
        "sql_used_mapping_ids": sorted(gold_ids),
    }


def build_parser_summary(private_rows: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = sum(bool(row["parse_success"]) for row in private_rows)
    scope_errors = sum(int(row["scope_analysis_error_count"]) for row in private_rows)
    matched = sum(bool(row["sql_used_mapping_ids"]) for row in private_rows)
    complete = sum(bool(row["resolution_complete"]) for row in private_rows)
    complete_and_matched = sum(
        bool(row["resolution_complete"] and row["sql_used_mapping_ids"])
        for row in private_rows
    )
    counter_keys = sorted({key for row in private_rows for key in row["parser_counters"]})
    counters = {
        key: sum(int(row["parser_counters"].get(key, 0)) for row in private_rows)
        for key in counter_keys
    }
    return {
        "selected_pair_count": len(private_rows),
        "sql_parse_success_count": parsed,
        "scope_analysis_error_count": scope_errors,
        "questions_with_complete_qualified_join_equality_resolution": complete,
        "pairs_with_sql_used_candidate_mapping": matched,
        "pairs_with_complete_resolution_and_sql_used_candidate_mapping": complete_and_matched,
        "pairs_without_matched_sql_used_mapping": len(private_rows) - matched,
        "qualified_join_equality_resolution_rate": round(
            counters.get("resolved_qualified_join_equality_count", 0)
            / counters.get("qualified_join_equality_count", 1),
            6,
        ) if counters.get("qualified_join_equality_count", 0) else None,
        "parser_counters": counters,
        "selected_pair_ids_sha256": stable_hash(sorted(row["pair_id"] for row in private_rows)),
    }


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    args.output_dir = args.output_dir.resolve()
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    base_summary: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "sqlglot_version": sqlglot.__version__,
        "gpu_used": False,
        "local_model_calls": 0,
        "external_api_calls": 0,
        "confirmed_input_tokens": 0,
        "confirmed_output_tokens": 0,
        "confirmed_total_tokens": 0,
        "estimated_api_cost_cny": "0.00",
    }
    private_rows: list[dict[str, Any]] = []
    try:
        config, frozen, questions_by_key, schemas_by_db, auxiliary, database_labels = prepare_run(args)
        base_summary["source_commit"] = args.expected_commit
        base_summary["input_sha256"] = frozen["observed_hashes"]
        split = frozen["split"]
        selected_pairs = sorted(set(split["smoke_pair_ids"] if args.mode == "smoke" else split["full_pair_ids"]))
        expected_count = EXPECTED_SMOKE_COUNT if args.mode == "smoke" else EXPECTED_FULL_COUNT
        require(len(selected_pairs) == expected_count, "SELECTED_PAIR_COUNT_MISMATCH")
        if args.mode == "full":
            require(args.smoke_summary is not None and args.smoke_summary.is_file(), "SMOKE_SUMMARY_MISSING")
            smoke_receipt = read_json(args.smoke_summary)
            require(smoke_receipt.get("status") == "SMOKE_PASS", "SMOKE_GATE_NOT_PASSED")
            require(smoke_receipt.get("run_id") == f"{EXPERIMENT_ID.replace('_01', '')}_smoke_001", "SMOKE_RUN_ID_MISMATCH")
            require(smoke_receipt.get("mode") == "smoke", "SMOKE_MODE_MISMATCH")
            require(smoke_receipt.get("source_commit") == args.expected_commit, "SMOKE_SOURCE_COMMIT_MISMATCH")
            expected_smoke_hash = stable_hash(sorted(split["smoke_pair_ids"]))
            require(smoke_receipt.get("selected_pair_ids_sha256") == expected_smoke_hash, "SMOKE_SPLIT_RECEIPT_MISMATCH")
            require(smoke_receipt.get("input_sha256") == frozen["observed_hashes"], "SMOKE_INPUT_HASH_MISMATCH")
            require(not set(selected_pairs) & set(split["smoke_pair_ids"]), "SMOKE_FULL_OVERLAP")

        for pair_id in selected_pairs:
            manifest_row = frozen["manifest"].get(pair_id)
            require(manifest_row is not None, "SELECTED_PAIR_MISSING_FROM_MANIFEST")
            row = audit_pair(pair_id, manifest_row, questions_by_key, schemas_by_db, database_labels)
            if args.mode == "full":
                prediction = auxiliary["predictions"][pair_id]
                candidates = set(row["candidate_mapping_ids"])
                require(set(prediction.get("candidate_mapping_ids", [])) == candidates, "PREDICTION_CANDIDATE_SET_MISMATCH")
                ranked = prediction.get("ranked_mapping_ids")
                require(isinstance(ranked, dict), "PREDICTION_RANKINGS_INVALID")
                ranked_methods = {}
                tie_counts = prediction.get("top_tie_counts", {})
                for method in ("g_reasoner", "dense_cosine"):
                    ranking = ranked.get(method)
                    require(
                        isinstance(ranking, list)
                        and len(ranking) == len(candidates)
                        and set(ranking) == candidates,
                        f"PREDICTION_RANKING_INVALID_{method}",
                    )
                    ranked_methods[method] = ranking
                row["ranked_mapping_ids"] = ranked_methods
                row["top_tie_counts"] = {
                    method: int(tie_counts.get(method, 0)) for method in ranked_methods
                }
                row["proxy_accepted_mapping_ids"] = None
                label = proxy_consensus(pair_id, candidates, auxiliary["reviewers"])
                if label is not None:
                    row["proxy_accepted_mapping_ids"] = label["accepted_mapping_ids"]
            private_rows.append(row)

        parser_summary = build_parser_summary(private_rows)
        base_summary.update(parser_summary)
        if args.mode == "smoke":
            passed = (
                parser_summary["sql_parse_success_count"] == EXPECTED_SMOKE_COUNT
                and parser_summary["scope_analysis_error_count"] == 0
                and parser_summary["questions_with_complete_qualified_join_equality_resolution"] == EXPECTED_SMOKE_COUNT
                and parser_summary["pairs_with_complete_resolution_and_sql_used_candidate_mapping"] >= 4
            )
            base_summary["status"] = "SMOKE_PASS" if passed else "STOP_SMOKE_GATE"
            base_summary["decision"] = "Run the one registered Full pass only if every Smoke gate passes." if passed else "Stop this registration; do not retry or expand the sample."
            base_summary["resources"] = resource_snapshot(wall_start, cpu_start)
            base_summary["input_sha256"] = frozen["observed_hashes"]
            write_private_jsonl(args.output_dir / "private_results.jsonl", private_rows)
            write_private_json(args.output_dir / "smoke_summary.json", base_summary)
            return (0 if passed else 2), base_summary

        parse_gate = (
            parser_summary["sql_parse_success_count"] >= 54
            and parser_summary["scope_analysis_error_count"] == 0
        )
        evaluable = [
            row for row in private_rows
            if row["resolution_complete"] and row["sql_used_mapping_ids"]
        ]
        eligible_db_count = len({row["anonymous_database"] for row in evaluable})
        coverage_gate = len(evaluable) >= 30 and eligible_db_count >= 3
        base_summary["full_parse_gate_passed"] = parse_gate
        base_summary["full_evaluable_database_count"] = eligible_db_count
        base_summary["full_sql_label_coverage_gate_passed"] = coverage_gate

        if not parse_gate:
            base_summary["status"] = "STOP_SQL_PARSER_GATE"
            base_summary["decision"] = "Parser coverage gate failed; ranking metrics were not computed. No retry is registered."
        elif not coverage_gate:
            base_summary["status"] = "STOP_SQL_LABEL_COVERAGE"
            base_summary["decision"] = "SQL-used candidate coverage gate failed; ranking metrics were not computed. No retry is registered."
        else:
            metrics = aggregate_metrics(private_rows)
            base_summary["metrics"] = metrics
            delta = metrics["paired_g_reasoner_vs_dense"]["mapping_at_1_delta_percentage_points"]
            net_rescues = metrics["paired_g_reasoner_vs_dense"]["net_rescues"]
            positives = metrics["positive_databases_with_n_at_least_5"]
            signal = (
                delta is not None
                and delta >= 5.0
                and net_rescues >= 4
                and positives >= 2
            )
            base_summary["status"] = "FULL_SIGNAL_SCREEN_PASS" if signal else "FULL_COMPLETED_NO_SIGNAL"
            base_summary["decision"] = (
                "Signal screen passed; nominate only for independent replication."
                if signal
                else "Signal screen failed; stop without model, graph, parameter, or sample variants."
            )
        base_summary["resources"] = resource_snapshot(wall_start, cpu_start)
        usage = base_summary["resources"]
        require(usage["wall_seconds"] <= MAX_WALL_SECONDS, "RESOURCE_WALL_LIMIT")
        require(usage["cpu_seconds"] <= MAX_CPU_SECONDS, "RESOURCE_CPU_LIMIT")
        require(usage["peak_rss_gib"] <= MAX_RSS_GIB, "RESOURCE_RSS_LIMIT")

        write_private_jsonl(args.output_dir / "private_results.jsonl", private_rows)
        public_summary = {
            key: value
            for key, value in base_summary.items()
            if key not in {"started_at_utc"}
        }
        public_summary["input_sha256"] = frozen["observed_hashes"]
        write_private_json(args.output_dir / "aggregate_summary.json", public_summary)
        return 0, public_summary
    except StopRun as error:
        base_summary["status"] = error.code
        base_summary["decision"] = "Stopped by a frozen input, pairing, parser, or resource gate; do not retry this registration."
        base_summary["resources"] = resource_snapshot(wall_start, cpu_start)
        if private_rows:
            write_private_jsonl(args.output_dir / "private_results.jsonl", private_rows)
        write_private_json(args.output_dir / "status.json", base_summary)
        return 2, base_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--smoke-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        code, summary = run(args)
    except StopRun as error:
        summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": error.code,
            "decision": "Stopped by a frozen preflight gate; preserve the run directory and do not retry.",
            "gpu_used": False,
            "local_model_calls": 0,
            "external_api_calls": 0,
            "confirmed_input_tokens": 0,
            "confirmed_output_tokens": 0,
            "confirmed_total_tokens": 0,
            "estimated_api_cost_cny": "0.00",
        }
        code = 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
