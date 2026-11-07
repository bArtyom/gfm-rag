#!/usr/bin/env python3
"""Compare a frozen FK-domain anti-join with SQLite's native checker.

Only anonymized aggregate results are public. Questions, SQL, schema names,
FK IDs, row IDs, and values remain local. Source SQLite files are immutable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_p0_fk_mapping_counterfactual_shuffle as prior  # noqa: E402

EXPERIMENT_ID = "p0_fk_domain_violation_crosscheck_20261107_01"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_CONFIG = "configs/text2sql/p0_fk_domain_violation_crosscheck_20261107_01.json"
MAX_CPU_SECONDS = 900.0
MAX_WALL_SECONDS = 1800.0
MAX_RSS_GIB = 4.0
PRAGMA_TIMEOUT_SECONDS = 120.0


class AuditStop(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AuditStop(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - avoid exposing private input content.
        raise AuditStop(f"JSON_READ_{type(error).__name__}") from None


def write_private(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def current_resources(start_wall: float, start_cpu: float) -> dict[str, float]:
    return {
        "wall_seconds": round(time.perf_counter() - start_wall, 6),
        "cpu_seconds": round(time.process_time() - start_cpu, 6),
        "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6),
    }


def check_budget(start_wall: float, start_cpu: float) -> dict[str, float]:
    stats = current_resources(start_wall, start_cpu)
    require(stats["wall_seconds"] <= MAX_WALL_SECONDS, "RESOURCE_WALL_LIMIT")
    require(stats["cpu_seconds"] <= MAX_CPU_SECONDS, "RESOURCE_CPU_LIMIT")
    require(stats["peak_rss_gib"] <= MAX_RSS_GIB, "RESOURCE_RSS_LIMIT")
    return stats


def git(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--prior-full-dir", type=Path, required=True)
    parser.add_argument("--prior-stop-dir", type=Path, required=True)
    parser.add_argument("--prior-protocol-config", type=Path, required=True)
    parser.add_argument("--prior-execution-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-receipt", type=Path)
    return parser.parse_args()


def build_input_paths(args: argparse.Namespace) -> dict[str, Path]:
    prior_full = args.prior_full_dir.resolve()
    prior_stop = args.prior_stop_dir.resolve()
    return {
        "bird_dev_json": args.dev_json.resolve(),
        "bird_dev_tables_json": args.tables_json.resolve(),
        "source_manifest": args.source_manifest.resolve(),
        "prior_full_metrics": prior_full / "private_unit_metrics.json",
        "prior_full_aggregate": prior_full / "aggregate_summary.json",
        "prior_full_run_metadata": prior_full / "run_metadata.json",
        "prior_stop_aggregate": prior_stop / "aggregate_summary.json",
        "prior_stop_progress": prior_stop / "eligibility_progress_private.jsonl",
        "prior_stop_coverage_receipt": prior_stop / "coverage_stop_private.json",
        "prior_stop_preflight": prior_stop / "input_preflight_private.json",
        "prior_stop_run_receipt": prior_stop / "run_receipt.json",
        "prior_protocol_config": args.prior_protocol_config.resolve(),
        "prior_execution_config": args.prior_execution_config.resolve(),
        "prior_counterfactual_runner": REPO_ROOT / "scripts/text2sql/run_p0_fk_mapping_counterfactual_shuffle.py",
        "prior_instance_audit_runner": REPO_ROOT / "scripts/text2sql/audit_p0_fk_mapping_instance_equivalence_20261107.py",
    }


def verify_hashes(paths: dict[str, Path], expected: dict[str, str]) -> dict[str, Any]:
    require(set(paths) == set(expected), "INPUT_HASH_SET_MISMATCH")
    observed: dict[str, Any] = {}
    for name, path in paths.items():
        require(path.is_file(), f"INPUT_MISSING_{name}")
        digest = sha256_file(path)
        observed[name] = {"bytes": path.stat().st_size, "sha256": digest}
        require(digest == expected[name], f"INPUT_HASH_MISMATCH_{name}")
    return observed


def map_fk_id(conn: sqlite3.Connection, spec: dict[str, Any]) -> int:
    rows = prior.foreign_key_rows(conn, str(spec["child_table"]))
    by_id: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        by_id[int(row[0])].append(row)
    matches: list[int] = []
    for fk_id, group in by_id.items():
        if len(group) != 1:
            continue
        row = group[0]
        if str(row[3]).casefold() != str(spec["child_column"]).casefold():
            continue
        parent_column = str(row[4] or "")
        if not parent_column:
            parent_info, _ = prior.schema_table_info(conn, str(spec["parent_table"]))
            primary = [str(item["name"]) for item in parent_info if int(item["pk"]) > 0]
            require(len(primary) == 1, "FK_PARENT_KEY_NOT_SINGLE_COLUMN")
            parent_column = primary[0]
        if (
            str(row[2]).casefold() == str(spec["parent_table"]).casefold()
            and parent_column.casefold() == str(spec["parent_column"]).casefold()
        ):
            matches.append(fk_id)
    require(len(matches) == 1, "FK_ID_NOT_UNIQUE")
    return matches[0]


def run_pragma_for_table(
    conn: sqlite3.Connection,
    table: str,
    start_wall: float,
    start_cpu: float,
) -> dict[str, Any]:
    deadline = time.perf_counter() + PRAGMA_TIMEOUT_SECONDS
    conn.set_progress_handler(lambda: 1 if time.perf_counter() >= deadline else 0, 1000)
    counts: Counter[int] = Counter()
    try:
        cursor = conn.execute(f"PRAGMA main.foreign_key_check({prior.quote_ident(table)})")
        for index, row in enumerate(cursor, start=1):
            require(len(row) == 4, "PRAGMA_ROW_SHAPE_INVALID")
            counts[int(row[3])] += 1
            if index % 10_000 == 0:
                check_budget(start_wall, start_cpu)
        return {"status": "ok", "violation_rows_by_fkid": dict(counts)}
    except sqlite3.Error as error:
        message = str(error).casefold()
        category = "sqlite_error"
        if "foreign key mismatch" in message:
            category = "foreign_key_schema_mismatch"
        elif "interrupted" in message or time.perf_counter() >= deadline:
            category = "pragma_timeout"
        elif getattr(error, "sqlite_errorcode", None) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_IOERR}:
            category = "database_integrity_or_io_error"
        return {
            "status": "error",
            "error_category": category,
            "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
            "violation_rows_by_fkid": {},
        }
    finally:
        conn.set_progress_handler(None, 0)


def reconstruct_fixed_population(
    args: argparse.Namespace,
    config: dict[str, Any],
    observed_hashes: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Path], dict[str, str], dict[str, Any]]:
    old_config = read_json(args.prior_protocol_config)
    old_execution_config = read_json(args.prior_execution_config)
    simple_args = SimpleNamespace(
        dev_json=args.dev_json,
        tables_json=args.tables_json,
        source_manifest=args.source_manifest,
        prior_full_dir=args.prior_full_dir,
    )
    old_paths = prior.input_paths(simple_args)
    verified = prior.verify_inputs(old_config, old_paths)
    require(old_execution_config.get("prior_aggregate_sha256") == config["input_sha256"]["prior_full_aggregate"], "PRIOR_AGGREGATE_HASH_NOT_PINNED")
    require(old_execution_config.get("prior_runner_sha256") == prior.EXPECTED_PRIOR_RUNNER_SHA256, "PRIOR_EXECUTION_RUNNER_MISMATCH")
    require(verified["prior_run_metadata"].get("run_id") == "p0_fk_mapping_instance_equivalence_20261107_01_full_002", "PRIOR_RUN_ID_MISMATCH")
    require(verified["prior_run_metadata"].get("source_commit") == old_execution_config.get("prior_source_commit"), "PRIOR_SOURCE_COMMIT_MISMATCH")
    expected_sqlite = config["sqlite_files_by_anonymous_database"]
    require(set(verified["hashes"]["sqlite"]) == set(expected_sqlite), "SQLITE_LABEL_SET_MISMATCH")
    for label, expected in expected_sqlite.items():
        require(verified["hashes"]["sqlite"][label] == expected, f"SQLITE_HASH_MISMATCH_{label}")

    old_manifest = prior.read_json(args.source_manifest)
    old_metrics = prior.read_json(old_paths["prior_metrics"])
    old_aggregate = prior.read_json(old_paths["prior_aggregate"])
    stop_aggregate = read_json(args.prior_stop_dir / "aggregate_summary.json")
    require(stop_aggregate.get("status") == "INCONCLUSIVE_ELIGIBILITY_COVERAGE", "PRIOR_STOP_STATUS_MISMATCH")
    require(stop_aggregate.get("fixed_candidate_pairs") == 55, "PRIOR_STOP_PAIR_COUNT_MISMATCH")
    require(stop_aggregate.get("structurally_eligible_pairs") == 14, "PRIOR_ELIGIBLE_PAIR_COUNT_MISMATCH")
    require(stop_aggregate.get("eligibility_exclusion_counts") == {
        "changed_column_is_primary_key": 9,
        "original_fk_domain_violation": 32,
    }, "PRIOR_STOP_EXCLUSION_COUNTS_MISMATCH")
    require(stop_aggregate.get("eligible_pairs_by_anonymous_db") == {"DB-B": 12, "DB-C": 2}, "PRIOR_ELIGIBLE_STRATA_MISMATCH")

    pairs, source_summary, _ = prior.reconstruct_pairs(
        old_config,
        old_manifest,
        old_metrics,
        old_aggregate,
        verified["database_labels_by_id"],
    )
    require(len(pairs) == 55, "RECONSTRUCTED_PAIR_COUNT_MISMATCH")
    progress_rows = []
    with (args.prior_stop_dir / "eligibility_progress_private.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                progress_rows.append(json.loads(line))
    require(len(progress_rows) == 55, "PRIOR_PROGRESS_ROW_COUNT_MISMATCH")
    hashes = [str(row.get("pair_hash", "")) for row in progress_rows]
    require(len(set(hashes)) == 55 and all(hashes), "PRIOR_PROGRESS_PAIR_HASH_INVALID")
    statuses = Counter(str(row.get("status")) for row in progress_rows)
    require(statuses == Counter({"eligible": 14, "ineligible": 41}), "PRIOR_PROGRESS_STATUS_COUNTS_MISMATCH")
    reasons = Counter(str(row.get("reason")) for row in progress_rows if row.get("status") == "ineligible")
    require(reasons == Counter({"original_fk_domain_violation": 32, "changed_column_is_primary_key": 9}), "PRIOR_PROGRESS_REASON_COUNTS_MISMATCH")
    coverage_stop = read_json(args.prior_stop_dir / "coverage_stop_private.json")
    eligible_hashes = {str(value) for value in coverage_stop.get("eligible_pair_hashes", [])}
    progress_eligible_hashes = {str(row["pair_hash"]) for row in progress_rows if row.get("status") == "eligible"}
    require(len(eligible_hashes) == 14 and eligible_hashes == progress_eligible_hashes, "PRIOR_ELIGIBLE_PAIR_SET_MISMATCH")

    pair_by_hash = {pair["pair_hash"]: pair for pair in pairs}
    require(set(pair_by_hash) == set(hashes), "RECONSTRUCTED_PAIR_SET_MISMATCH")
    target_hashes = {
        str(row["pair_hash"])
        for row in progress_rows
        if row.get("status") == "ineligible" and row.get("reason") == "original_fk_domain_violation"
    }
    require(len(target_hashes) == 32, "TARGET_EXCLUSION_SAMPLE_COUNT_MISMATCH")
    fixed_pairs = [pair_by_hash[pair_hash] for pair_hash in target_hashes]
    fixed_pairs.sort(key=lambda pair: hashlib.sha256(f"{EXPERIMENT_ID}|{pair['pair_hash']}".encode("utf-8")).hexdigest())
    input_info = {
        "observed_input_hashes": observed_hashes,
        "verified_source_hashes": verified["hashes"],
        "source_reconstruction": source_summary,
        "fixed_candidate_pairs": 55,
        "target_exclusion_pairs": len(fixed_pairs),
        "target_pair_hashes_private": sorted(target_hashes),
    }
    return fixed_pairs, verified["database_paths"], verified["database_labels_by_id"], input_info


def audit_pairs(
    pairs: list[dict[str, Any]],
    database_paths: dict[str, Path],
    start_wall: float,
    start_cpu: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with ExitStack() as stack:
        connections: dict[str, sqlite3.Connection] = {}
        for pair in pairs:
            label = str(pair["anonymous_db"])
            if label not in connections:
                conn = prior.open_readonly(database_paths[label])
                conn.execute("PRAGMA query_only=ON")
                connections[label] = stack.enter_context(_ClosingConnection(conn))

        pair_declarations: dict[str, list[str]] = {}
        declarations: dict[str, dict[str, Any]] = {}
        pragma_by_table: dict[tuple[str, str], dict[str, Any]] = {}

        for index, pair in enumerate(pairs, start=1):
            check_budget(start_wall, start_cpu)
            label = str(pair["anonymous_db"])
            conn = connections[label]
            schema, reason = prior.eligible_schema(conn, pair)
            require(schema is not None and reason is None, "FIXED_PAIR_SCHEMA_NO_LONGER_ELIGIBLE")
            require(prior.validate_original_domains(conn, schema) == "original_fk_domain_violation", "CUSTOM_EXCLUSION_NOT_REPRODUCED")
            keys: list[str] = []
            for spec in schema["fk_specs"]:
                fk_id = map_fk_id(conn, spec)
                table = str(spec["child_table"])
                table_key = table.casefold()
                pragma_key = (label, table_key)
                if pragma_key not in pragma_by_table:
                    pragma_by_table[pragma_key] = run_pragma_for_table(conn, table, start_wall, start_cpu)
                declaration_key = hashlib.sha256(
                    json.dumps(
                        [label, table_key, fk_id, str(spec["child_column"]).casefold(), str(spec["parent_table"]).casefold(), str(spec["parent_column"]).casefold()],
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                custom_flag = bool(prior.has_invalid_fk_values(conn, spec))
                declaration = {
                    "anonymous_database": label,
                    "private_table_key": table_key,
                    "fk_id": fk_id,
                    "private_signature": [
                        str(spec["child_table"]).casefold(), str(spec["child_column"]).casefold(),
                        str(spec["parent_table"]).casefold(), str(spec["parent_column"]).casefold(),
                    ],
                    "custom_flag": custom_flag,
                    "declaration_hash": declaration_key,
                }
                previous = declarations.get(declaration_key)
                if previous is not None:
                    require(previous["private_signature"] == declaration["private_signature"], "DECLARATION_IDENTITY_COLLISION")
                    require(previous["custom_flag"] == custom_flag, "CUSTOM_FLAG_NOT_DETERMINISTIC")
                else:
                    declarations[declaration_key] = declaration
                keys.append(declaration_key)
            pair_declarations[str(pair["pair_hash"])] = keys
            if index % 5 == 0 or index == len(pairs):
                print(f"pair_audit_progress={index}/{len(pairs)}", flush=True)

        private_declarations: list[dict[str, Any]] = []
        for declaration_key, declaration in sorted(declarations.items()):
            table_key = declaration["private_table_key"]
            pragma = pragma_by_table[(declaration["anonymous_database"], table_key)]
            row_count = None
            pragma_flag: bool | None = None
            status = pragma["status"]
            if status == "ok":
                row_count = int(pragma["violation_rows_by_fkid"].get(declaration["fk_id"], 0))
                pragma_flag = row_count > 0
            agree = None if pragma_flag is None else declaration["custom_flag"] == pragma_flag
            private_declarations.append({
                "declaration_hash": declaration_key,
                "anonymous_database": declaration["anonymous_database"],
                "custom_flag": declaration["custom_flag"],
                "sqlite_pragma_flag": pragma_flag,
                "sqlite_violation_rows": row_count,
                "comparison_status": status,
                "pragma_error_category": pragma.get("error_category"),
                "comparison_agrees": agree,
            })

        private_pairs: list[dict[str, Any]] = []
        for pair_hash, declaration_keys in sorted(pair_declarations.items()):
            members = [declarations[key] for key in declaration_keys]
            custom_any = any(item["custom_flag"] for item in members)
            flags: list[bool | None] = []
            for declaration in members:
                pragma = pragma_by_table[(declaration["anonymous_database"], declaration["private_table_key"])]
                flags.append(None if pragma["status"] != "ok" else int(pragma["violation_rows_by_fkid"].get(declaration["fk_id"], 0)) > 0)
            pragma_any = True if any(flag is True for flag in flags) else (None if any(flag is None for flag in flags) else False)
            pair_agrees = None if pragma_any is None else custom_any == pragma_any
            private_pairs.append({
                "pair_hash": pair_hash,
                "anonymous_database": members[0]["anonymous_database"],
                "custom_pair_flag": custom_any,
                "sqlite_pair_flag": pragma_any,
                "comparison_agrees": pair_agrees,
                "candidate_declaration_hashes": declaration_keys,
            })

        declaration_agreement = Counter(
            "unresolved" if row["comparison_agrees"] is None else ("agree" if row["comparison_agrees"] else "disagree")
            for row in private_declarations
        )
        pair_agreement = Counter(
            "unresolved" if row["comparison_agrees"] is None else ("agree" if row["comparison_agrees"] else "disagree")
            for row in private_pairs
        )
        declaration_flags = Counter(
            "unresolved" if row["sqlite_pragma_flag"] is None else (
                "both_flagged" if row["custom_flag"] and row["sqlite_pragma_flag"] else
                "custom_only" if row["custom_flag"] else
                "pragma_only" if row["sqlite_pragma_flag"] else
                "neither_flagged"
            )
            for row in private_declarations
        )
        resolved_row_counts = [
            int(row["sqlite_violation_rows"])
            for row in private_declarations
            if row["sqlite_violation_rows"] is not None
        ]
        positive_row_counts = [count for count in resolved_row_counts if count > 0]
        per_db: dict[str, Any] = {}
        for label in sorted({str(pair["anonymous_db"]) for pair in pairs}):
            pair_rows = [row for row in private_pairs if row["anonymous_database"] == label]
            decl_rows = [row for row in private_declarations if row["anonymous_database"] == label]
            per_db[label] = {
                "fixed_pairs": len(pair_rows),
                "pair_agreement": dict(Counter("unresolved" if row["comparison_agrees"] is None else ("agree" if row["comparison_agrees"] else "disagree") for row in pair_rows)),
                "unique_declarations": len(decl_rows),
                "declaration_agreement": dict(Counter("unresolved" if row["comparison_agrees"] is None else ("agree" if row["comparison_agrees"] else "disagree") for row in decl_rows)),
            }
        public = {
            "experiment_id": EXPERIMENT_ID,
            "fixed_target_pair_count": len(private_pairs),
            "unique_candidate_declaration_count": len(private_declarations),
            "pair_level_agreement": dict(pair_agreement),
            "declaration_level_agreement": dict(declaration_agreement),
            "declaration_flag_categories": dict(declaration_flags),
            "sqlite_violation_row_count_distribution": {
                "resolved_declarations": len(resolved_row_counts),
                "zero_violation_declarations": sum(count == 0 for count in resolved_row_counts),
                "positive_violation_declarations": len(positive_row_counts),
                "positive_min": min(positive_row_counts) if positive_row_counts else None,
                "positive_median": statistics.median(positive_row_counts) if positive_row_counts else None,
                "positive_max": max(positive_row_counts) if positive_row_counts else None,
            },
            "pragma_error_table_count": sum(result["status"] == "error" for result in pragma_by_table.values()),
            "pragma_table_check_count": len(pragma_by_table),
            "anonymous_database_slices": per_db,
            "interpretation_limit": "Targeted audit of the 32 prior exclusions only; not a BIRD-wide FK-violation prevalence estimate or a semantic Role result.",
        }
        unresolved = pair_agreement.get("unresolved", 0) > 0 or declaration_agreement.get("unresolved", 0) > 0
        disagreements = pair_agreement.get("disagree", 0) > 0 or declaration_agreement.get("disagree", 0) > 0
        public["status"] = (
            "INCONCLUSIVE_NATIVE_CHECK" if unresolved else
            "PREDICATE_DISAGREEMENT_FOUND" if disagreements else
            "PREDICATE_EQUIVALENCE_CONFIRMED_ON_FIXED_SET"
        )
        private = {
            "experiment_id": EXPERIMENT_ID,
            "pair_results": private_pairs,
            "declaration_results": private_declarations,
            "pragma_table_results": [
                {"anonymous_database": label, "private_table_key": table, **result}
                for (label, table), result in sorted(pragma_by_table.items())
            ],
        }
        return public, private


class _ClosingConnection:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        self.conn.close()


def run(args: argparse.Namespace) -> int:
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    config_path = args.config.resolve(strict=True)
    require(config_path.as_posix().endswith(EXPECTED_CONFIG), "CONFIG_PATH_MISMATCH")
    config = read_json(config_path)
    require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_ID_MISMATCH")
    require(config.get("status") == "preregistered_before_private_manifest_parse_or_database_access", "CONFIG_NOT_PREREGISTERED")
    require(config.get("branch") == EXPECTED_BRANCH, "CONFIG_BRANCH_MISMATCH")
    require(args.run_id == config["run_ids"][args.mode], "RUN_ID_MISMATCH")
    require(args.output_dir.is_absolute() and not args.output_dir.exists(), "OUTPUT_DIRECTORY_INVALID")
    require(git("branch", "--show-current") == EXPECTED_BRANCH, "BRANCH_MISMATCH")
    current_commit = git("rev-parse", "HEAD")
    require(not git("status", "--porcelain"), "WORKTREE_NOT_CLEAN")
    require(platform.python_version() == "3.12.14", "PYTHON_VERSION_MISMATCH")
    require(sqlite3.sqlite_version == "3.53.2", "SQLITE_VERSION_MISMATCH")

    input_paths = build_input_paths(args)
    observed_hashes = verify_hashes(input_paths, config["input_sha256"])
    require(sha256_file(SCRIPT_DIR / "run_p0_fk_mapping_counterfactual_shuffle.py") == config["input_sha256"]["prior_counterfactual_runner"], "PRIOR_RUNNER_HASH_MISMATCH")

    fixed_pairs, database_paths, database_labels, input_info = reconstruct_fixed_population(args, config, observed_hashes)
    require(len(fixed_pairs) == 32, "FIXED_TARGET_PAIR_COUNT_MISMATCH")
    smoke_pairs = fixed_pairs[:5]
    if args.mode == "smoke":
        selected = smoke_pairs
    else:
        require(args.smoke_receipt is not None and args.smoke_receipt.is_file(), "SMOKE_RECEIPT_MISSING")
        receipt = read_json(args.smoke_receipt)
        require(receipt.get("status") == "SMOKE_COMPLETE", "SMOKE_NOT_COMPLETE")
        require(receipt.get("config_sha256") == sha256_file(config_path), "SMOKE_CONFIG_HASH_MISMATCH")
        require(receipt.get("source_commit") == current_commit, "SMOKE_SOURCE_COMMIT_MISMATCH")
        selected = fixed_pairs

    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    write_private(args.output_dir / "input_preflight_private.json", {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "source_commit": current_commit,
        "source_branch": EXPECTED_BRANCH,
        "runner_sha256": sha256_file(Path(__file__)),
        "config_sha256": sha256_file(config_path),
        **input_info,
    })

    public, private = audit_pairs(selected, database_paths, start_wall, start_cpu)
    post_hashes: dict[str, Any] = {}
    for label, db_path in database_paths.items():
        current = {"bytes": db_path.stat().st_size, "sha256": sha256_file(db_path)}
        expected = config["sqlite_files_by_anonymous_database"][label]
        require(current == expected, f"SQLITE_POST_HASH_MISMATCH_{label}")
        post_hashes[label] = current
    public["run_id"] = args.run_id
    public["mode"] = args.mode
    public["source_commit"] = current_commit
    public["resource_usage"] = check_budget(start_wall, start_cpu)
    public["sqlite_hashes_unchanged"] = True
    private["post_sqlite_hashes"] = post_hashes
    write_private(args.output_dir / "aggregate_summary.json", public)
    write_private(args.output_dir / "private_comparison_details.json", private)
    receipt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "SMOKE_COMPLETE" if args.mode == "smoke" else public["status"],
        "source_commit": current_commit,
        "config_sha256": sha256_file(config_path),
        "runner_sha256": sha256_file(Path(__file__)),
        "selected_target_pair_count": len(selected),
        "selected_pair_hashes_private": [pair["pair_hash"] for pair in selected],
        "resource_usage": public["resource_usage"],
    }
    write_private(args.output_dir / "run_receipt.json", receipt)
    print(json.dumps(public, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except AuditStop as error:
        if args.output_dir.is_absolute():
            try:
                args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
                args.output_dir.chmod(0o700)
                write_private(args.output_dir / "failure.json", {
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": args.run_id,
                    "status": "STOPPED",
                    "reason_code": error.code,
                })
            except FileExistsError:
                pass
        print(json.dumps({"experiment_id": EXPERIMENT_ID, "run_id": args.run_id, "status": "STOPPED", "reason_code": error.code}, sort_keys=True), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
