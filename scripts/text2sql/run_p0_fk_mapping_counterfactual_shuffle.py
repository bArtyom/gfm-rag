#!/usr/bin/env python3
"""Run a bounded FK-value counterfactual diagnostic on frozen BIRD pairs.

Questions, SQL, mappings, database paths, row values, and per-pair outputs are
private. Public output contains only anonymous counts and rates. The SQLite
main database is opened read-only; counterfactual values live only in TEMP
tables and TEMP views.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import resource
import sqlite3
import statistics
import subprocess
import sys
import time
from typing import Any

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "8"

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_p0_fk_mapping_instance_equivalence_20261107 as baseline  # noqa: E402
import prepare_p0_fk_disagreement_review_packet as packet  # noqa: E402
import p2d_sql_evaluator as evaluator  # noqa: E402
from audit_p0_fk_sql_used_mapping_alignment_20261107_02 import build_known_columns  # noqa: E402


EXPERIMENT_ID = "p0_fk_mapping_counterfactual_shuffle_20261107_01"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_PRIOR_RUNNER_SHA256 = "99245f972de3f8827c812ec0fc5f89e3d269ea9b80bfb5a1c1bad03ce81adc3c"
EXPECTED_PAIR_COUNT = 55
SEEDS = tuple(range(20261107, 20261127))
MAX_ATTEMPTS_PER_SEED = 100
MAX_WALL_SECONDS = 3600.0
MAX_CPU_SECONDS = 1800.0
MAX_RSS_GIB = 4.0
QUERY_TIMEOUT_SECONDS = 10.0
ROW_LIMIT = 50_000
BYTE_LIMIT = 64 * 1024 * 1024
SQLITE_HEAP_LIMIT = 256 * 1024 * 1024
STANDARD_COLLATIONS = {"binary", "nocase", "rtrim"}


class StopRun(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise StopRun(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - do not expose private input details.
        raise StopRun(f"JSON_READ_{type(error).__name__}") from None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def quote_ident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_resources(wall_start: float, cpu_start: float) -> dict[str, float]:
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    return {
        "wall_seconds": round(wall, 6),
        "cpu_seconds": round(cpu, 6),
        "peak_rss_gib": round(rss, 6),
    }


def check_budget(wall_start: float, cpu_start: float) -> dict[str, float]:
    metrics = current_resources(wall_start, cpu_start)
    require(metrics["wall_seconds"] <= MAX_WALL_SECONDS, "RESOURCE_WALL_LIMIT")
    require(metrics["cpu_seconds"] <= MAX_CPU_SECONDS, "RESOURCE_CPU_LIMIT")
    require(metrics["peak_rss_gib"] <= MAX_RSS_GIB, "RESOURCE_RSS_LIMIT")
    return metrics


def open_readonly(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=0)
    conn.enable_load_extension(False)
    evaluator._set_sqlite_memory_limit(conn, SQLITE_HEAP_LIMIT)
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, min(BYTE_LIMIT, SQLITE_HEAP_LIMIT // 2, 2**31 - 1))
    return conn


def input_paths(args: argparse.Namespace) -> dict[str, Path]:
    prior_root = args.prior_full_dir.resolve()
    return {
        "dev_json": args.dev_json.resolve(),
        "dev_tables_json": args.tables_json.resolve(),
        "source_manifest": args.source_manifest.resolve(),
        "prior_metrics": prior_root / "private_unit_metrics.json",
        "prior_aggregate": prior_root / "aggregate_summary.json",
        "prior_run_metadata": prior_root / "run_metadata.json",
    }


def verify_inputs(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    """Hash every source and SQLite snapshot before reading SQL or opening DBs."""
    expected = config["hash_capture"]
    expected_files = {
        "dev_json": expected["bird_dev_json_sha256"],
        "dev_tables_json": expected["bird_dev_tables_json_sha256"],
        "source_manifest": expected["source_manifest_sha256"],
        "prior_metrics": expected["prior_private_full_metrics_sha256"],
    }
    observed: dict[str, Any] = {"files": {}, "sqlite": {}}
    for name, expected_hash in expected_files.items():
        path = paths[name]
        require(path.is_file(), f"INPUT_MISSING_{name}")
        observed["files"][name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        require(observed["files"][name]["sha256"] == expected_hash, f"INPUT_HASH_MISMATCH_{name}")
    require(observed["files"]["prior_metrics"]["bytes"] == expected["private_metrics_bytes"], "METRICS_SIZE_MISMATCH")

    metadata = read_json(paths["prior_run_metadata"])
    db_paths: dict[str, Path] = {}
    for label, path_text in metadata.get("database_paths", {}).items():
        require(label in config["sqlite_files_by_anonymous_database"], "DATABASE_LABEL_MISMATCH")
        path = Path(path_text)
        spec = config["sqlite_files_by_anonymous_database"][label]
        require(path.is_file(), f"DATABASE_MISSING_{label}")
        database_id = path.parent.name
        alias_path = paths["dev_json"].parent / "dev_databases" / database_id / f"{database_id}.sqlite"
        require(alias_path.is_file() and alias_path.resolve() == path.resolve(), f"DATABASE_ALIAS_MISMATCH_{label}")
        observed_db = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        observed["sqlite"][label] = observed_db
        require(observed_db["bytes"] == spec["bytes"], f"DATABASE_SIZE_MISMATCH_{label}")
        require(observed_db["sha256"] == spec["sha256"], f"DATABASE_HASH_MISMATCH_{label}")
        db_paths[label] = path.resolve()
    require(set(db_paths) == set(config["sqlite_files_by_anonymous_database"]), "DATABASE_LABEL_SET_MISMATCH")
    prior_script = REPO_ROOT / "scripts/text2sql/audit_p0_fk_mapping_instance_equivalence_20261107.py"
    observed["prior_runner_sha256"] = sha256_file(prior_script)
    require(observed["prior_runner_sha256"] == EXPECTED_PRIOR_RUNNER_SHA256, "PRIOR_RUNNER_HASH_MISMATCH")
    return {
        "hashes": observed,
        "database_paths": db_paths,
        "database_labels_by_id": {p.parent.name: k for k, p in db_paths.items()},
        "prior_run_metadata": metadata,
    }


def assert_branch_and_config(args: argparse.Namespace, config: dict[str, Any]) -> tuple[str, str]:
    branch = git_value("branch", "--show-current")
    require(branch == EXPECTED_BRANCH, "BRANCH_MISMATCH")
    require(not git_value("status", "--porcelain"), "WORKTREE_NOT_CLEAN")
    require(config.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_MISMATCH")
    require(config.get("status") == "preregistered_before_sql_or_database_read", "CONFIG_NOT_PREREGISTERED")
    require(config.get("amendment") == "002", "CONFIG_AMENDMENT_MISMATCH")
    require(args.mode in {"smoke", "full"}, "MODE_INVALID")
    require(args.output_dir.exists() is False, "OUTPUT_DIRECTORY_ALREADY_EXISTS")
    require(args.output_dir.is_absolute(), "OUTPUT_DIRECTORY_NOT_ABSOLUTE")
    require(sqlite3.sqlite_version == "3.53.2", "SQLITE_VERSION_MISMATCH")
    require(platform.python_version() == "3.12.14", "PYTHON_VERSION_MISMATCH")
    import sqlglot

    require(sqlglot.__version__ == EXPECTED_SQLGLOT, "SQLGLOT_VERSION_MISMATCH")
    return branch, git_value("rev-parse", "HEAD")


def reconstruct_pairs(
    config: dict[str, Any],
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    prior_aggregate: dict[str, Any],
    database_labels_by_id: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    require(manifest.get("experiment_id") == "p0_fk_sql_used_mapping_rank_20261107_03", "SOURCE_MANIFEST_EXPERIMENT_MISMATCH")
    units = manifest.get("units")
    require(isinstance(units, dict), "SOURCE_UNITS_INVALID")
    full_ids = manifest.get("full_unit_ids")
    require(isinstance(full_ids, list) and len(full_ids) == 108, "SOURCE_FULL_SPLIT_INVALID")
    full_units = {unit_id: units[unit_id] for unit_id in full_ids if unit_id in units}
    require(len(full_units) == 108, "SOURCE_FULL_UNIT_MISSING")
    unit_hash_to_id = {baseline.unit_identity(unit): unit_id for unit_id, unit in full_units.items()}
    require(len(unit_hash_to_id) == len(full_units), "SOURCE_UNIT_HASH_COLLISION")

    prior_unit_rows = metrics.get("units")
    prior_candidate_rows = metrics.get("candidates")
    require(isinstance(prior_unit_rows, list) and len(prior_unit_rows) == 108, "PRIOR_UNIT_ROWS_INVALID")
    require(isinstance(prior_candidate_rows, list) and len(prior_candidate_rows) == 108, "PRIOR_CANDIDATE_ROWS_INVALID")
    unit_summary_by_hash = {str(row.get("unit_hash")): row for row in prior_unit_rows}
    candidate_record_by_hash = {str(row.get("unit_hash")): row for row in prior_candidate_rows if row.get("unit_hash")}
    require(len(unit_summary_by_hash) == 108, "PRIOR_UNIT_HASH_DUPLICATE")
    require(len(candidate_record_by_hash) == 97, "PRIOR_CANDIDATE_HASH_COUNT_MISMATCH")

    agg_metrics = prior_aggregate.get("metrics", {})
    require(prior_aggregate.get("experiment_id") == "p0_fk_mapping_instance_equivalence_20261107_01", "PRIOR_AGGREGATE_EXPERIMENT_MISMATCH")
    require(agg_metrics.get("complete_units") == 94, "PRIOR_COMPLETE_UNIT_COUNT_MISMATCH")
    require(agg_metrics.get("alternative_candidate_comparisons") == 144, "PRIOR_ALTERNATIVE_COUNT_MISMATCH")
    require(agg_metrics.get("candidate_level_bag_equal") == EXPECTED_PAIR_COUNT, "PRIOR_EQUAL_PAIR_COUNT_MISMATCH")

    observed_complete: dict[str, int] = defaultdict(int)
    observed_equivalent_units: dict[str, int] = defaultdict(int)
    manifest_by_hash: dict[str, dict[str, Any]] = {}
    for unit_id, unit in full_units.items():
        unit_hash = baseline.unit_identity(unit)
        manifest_by_hash[unit_hash] = unit
        summary = unit_summary_by_hash.get(unit_hash)
        require(summary is not None, "PRIOR_UNIT_NOT_IN_MANIFEST")
        label = database_labels_by_id.get(str(unit.get("db_id")))
        require(label is not None, "ANONYMOUS_DATABASE_LABEL_MISSING")
        if summary.get("status") == "complete":
            observed_complete[label] += 1
        candidate_record = candidate_record_by_hash.get(unit_hash, {})
        comparisons = candidate_record.get("candidate_comparisons", [])
        eligible_rows = [row for row in comparisons if not row.get("is_target") and row.get("status") == "ok" and row.get("bag_equal") is True]
        if summary.get("status") == "complete":
            recorded = int(summary.get("alternative_bag_equal_count", -1))
            require(recorded == len(eligible_rows), "PRIOR_UNIT_CANDIDATE_COUNT_MISMATCH")
            if eligible_rows:
                observed_equivalent_units[label] += 1

    prior_db = agg_metrics.get("anonymous_databases", {})
    expected_db = {
        label: (int(values["complete_units"]), int(values["units_with_bag_equivalent_alternative"]))
        for label, values in prior_db.items()
    }
    observed_db = {label: (observed_complete[label], observed_equivalent_units[label]) for label in sorted(database_labels_by_id.values())}
    require(observed_db == expected_db, "PRIOR_DATABASE_STRATA_MISMATCH")

    pairs: list[dict[str, Any]] = []
    for unit_hash, candidate_record in candidate_record_by_hash.items():
        unit_summary = unit_summary_by_hash.get(unit_hash)
        if unit_summary is None or unit_summary.get("status") != "complete":
            continue
        unit_id = unit_hash_to_id.get(unit_hash)
        require(unit_id is not None, "PRIOR_COMPARISON_UNIT_NOT_IN_MANIFEST")
        unit = full_units[unit_id]
        candidate_by_hash = {
            stable_hash(candidate.get("mapping_id"))[:20]: candidate
            for candidate in unit.get("candidate_mappings", [])
        }
        target_ids = unit.get("sql_used_mapping_ids")
        require(isinstance(target_ids, list) and len(target_ids) == 1, "SOURCE_TARGET_NOT_SINGLETON")
        target_id = str(target_ids[0])
        target_matches = [row for row in unit.get("candidate_mappings", []) if str(row.get("mapping_id")) == target_id]
        require(len(target_matches) == 1, "SOURCE_TARGET_CANDIDATE_NOT_UNIQUE")
        comparisons = candidate_record.get("candidate_comparisons", [])
        for row in comparisons:
            if row.get("is_target") is True or row.get("bag_equal") is not True or row.get("status") != "ok":
                continue
            candidate_hash = str(row.get("candidate_hash", ""))
            alternate = candidate_by_hash.get(candidate_hash)
            require(alternate is not None, "PRIOR_CANDIDATE_HASH_NOT_IN_MANIFEST")
            require(str(alternate.get("mapping_id")) != target_id, "PRIOR_ALTERNATE_IS_TARGET")
            pair_identity = stable_hash([unit_id, str(alternate.get("mapping_id"))])
            pairs.append(
                {
                    "pair_hash": pair_identity,
                    "unit_id": unit_id,
                    "unit_hash": unit_hash,
                    "candidate_hash": candidate_hash,
                    "mapping_id": str(alternate.get("mapping_id")),
                    "target_mapping_id": target_id,
                    "question_key_sha256": unit.get("question_key_sha256"),
                    "question_sql_sha256": unit.get("question_sql_sha256"),
                    "db_id": str(unit.get("db_id")),
                    "anonymous_db": database_labels_by_id[str(unit.get("db_id"))],
                    "table_pair": list(unit.get("table_pair", [])),
                    "unit": unit,
                    "target_mapping": target_matches[0],
                    "alternate_mapping": alternate,
                }
            )
    require(len(pairs) == EXPECTED_PAIR_COUNT, "RECONSTRUCTED_PAIR_COUNT_MISMATCH")
    require(len({pair["pair_hash"] for pair in pairs}) == EXPECTED_PAIR_COUNT, "RECONSTRUCTED_PAIR_HASH_COLLISION")
    pairs.sort(key=lambda pair: hashlib.sha256((EXPERIMENT_ID + pair["pair_hash"]).encode("utf-8")).hexdigest())
    source_summary = {
        "prior_complete_units": 94,
        "prior_alternative_candidate_comparisons": 144,
        "reconstructed_fixed_pairs": len(pairs),
        "complete_units_by_anonymous_db": {key: value[0] for key, value in observed_db.items()},
        "units_with_equal_alternative_by_anonymous_db": {key: value[1] for key, value in observed_db.items()},
    }
    return pairs, source_summary, manifest_by_hash


def field_key(table: str, column: str) -> str:
    return f"{table.casefold()}\u241f{column.casefold()}"


def encode_scalar(value: Any) -> Any:
    if value is None:
        return ["null"]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, str):
        return ["str", value]
    return [type(value).__name__, repr(value)]


def typed_key(value: Any) -> str:
    return json.dumps(encode_scalar(value), ensure_ascii=False, separators=(",", ":"))


def typed_counter(values: list[Any]) -> Counter[str]:
    return Counter(typed_key(value) for value in values)


def assignment_digest(assignments: dict[str, list[tuple[int, Any]]]) -> str:
    canonical = {
        key: [[rowid, encode_scalar(value)] for rowid, value in assignments[key]]
        for key in sorted(assignments)
    }
    return stable_hash(canonical)


def is_identity(
    field_rows: dict[str, list[tuple[int, Any]]],
    assignments: dict[str, list[tuple[int, Any]]],
) -> bool:
    return all(
        all(encode_scalar(original_value) == encode_scalar(new_value) for (_, original_value), (_, new_value) in zip(field_rows[key], assignments[key]))
        for key in field_rows
    )


def make_assignment(
    pair_hash: str,
    seed: int,
    attempt: int,
    field_rows: dict[str, list[tuple[int, Any]]],
) -> dict[str, list[tuple[int, Any]]]:
    assignments: dict[str, list[tuple[int, Any]]] = {}
    for key in sorted(field_rows):
        base_rows = field_rows[key]
        values = [value for _, value in base_rows]
        shuffled = list(values)
        rng = random.Random(f"{EXPERIMENT_ID}|{pair_hash}|{seed}|{attempt}|{key}")
        rng.shuffle(shuffled)
        assignments[key] = [(base_rows[index][0], shuffled[index]) for index in range(len(base_rows))]
    return assignments


def schema_table_info(conn: sqlite3.Connection, table: str) -> tuple[list[sqlite3.Row], str]:
    conn.row_factory = sqlite3.Row
    info = conn.execute(f"PRAGMA main.table_info({quote_ident(table)})").fetchall()
    row = conn.execute("SELECT sql FROM main.sqlite_master WHERE type='table' AND name=? COLLATE NOCASE", (table,)).fetchone()
    return info, str(row[0] or "") if row else ""


def get_index_specs(
    conn: sqlite3.Connection,
    table: str,
    changed_columns: set[str],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    index_rows = conn.execute(f"PRAGMA main.index_list({quote_ident(table)})").fetchall()
    for index_row in index_rows:
        _, index_name, is_unique, _origin, is_partial = index_row[:5]
        if int(is_unique) != 1:
            continue
        xinfo = conn.execute(f"PRAGMA main.index_xinfo({quote_ident(str(index_name))})").fetchall()
        key_rows = [row for row in xinfo if int(row[5]) == 1]
        key_names = [None if row[2] is None else str(row[2]) for row in key_rows]
        if any(name is None for name in key_names):
            raise StopRun("INELIGIBLE_EXPRESSION_UNIQUE_INDEX")
        overlaps = [str(name) for name in key_names if str(name).casefold() in changed_columns]
        if not overlaps:
            continue
        if len(key_names) != 1:
            raise StopRun("INELIGIBLE_MULTI_COLUMN_UNIQUE_INDEX")
        collation = str(key_rows[0][4] or "BINARY").casefold()
        if collation not in STANDARD_COLLATIONS:
            raise StopRun("INELIGIBLE_CUSTOM_UNIQUE_COLLATION")
        predicate = None
        if int(is_partial):
            row = conn.execute(
                "SELECT sql FROM main.sqlite_master WHERE type='index' AND name=? COLLATE NOCASE",
                (str(index_name),),
            ).fetchone()
            predicate = extract_partial_predicate(str(row[0] or "") if row else "")
            if not predicate:
                raise StopRun("INELIGIBLE_PARTIAL_UNIQUE_INDEX_UNPARSEABLE")
            try:
                evaluator._validate_sql(f"SELECT 1 FROM main.{quote_ident(table)} WHERE ({predicate})")
            except Exception:
                raise StopRun("INELIGIBLE_PARTIAL_UNIQUE_INDEX_UNSAFE") from None
        specs.append({"name": str(index_name), "column": overlaps[0], "collation": collation, "predicate": predicate})
    return specs


def extract_partial_predicate(index_sql: str) -> str | None:
    """Return a top-level partial-index WHERE clause without parsing row data."""
    depth = 0
    index = 0
    quote: str | None = None
    while index < len(index_sql):
        char = index_sql[index]
        if quote == "[":
            if char == "]":
                quote = None
            index += 1
            continue
        if quote is not None:
            if char == quote:
                if index + 1 < len(index_sql) and index_sql[index + 1] == quote and quote in {"'", '"', "`"}:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`", "["}:
            quote = char
            index += 1
            continue
        if index + 1 < len(index_sql) and index_sql[index:index + 2] == "--":
            newline = index_sql.find("\n", index + 2)
            index = len(index_sql) if newline < 0 else newline + 1
            continue
        if index + 1 < len(index_sql) and index_sql[index:index + 2] == "/*":
            end = index_sql.find("*/", index + 2)
            index = len(index_sql) if end < 0 else end + 2
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and (char.isalpha() or char == "_"):
            end = index + 1
            while end < len(index_sql) and (index_sql[end].isalnum() or index_sql[end] == "_"):
                end += 1
            if index_sql[index:end].casefold() == "where":
                predicate = index_sql[end:].strip().rstrip(";").strip()
                return predicate or None
            index = end
            continue
        index += 1
    return None


def foreign_key_rows(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in conn.execute(f"PRAGMA main.foreign_key_list({quote_ident(table)})").fetchall()]


def validate_declared_fk(
    conn: sqlite3.Connection,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> str | None:
    rows = foreign_key_rows(conn, child_table)
    by_id: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        by_id[int(row[0])].append(row)
    matches: list[tuple[Any, ...]] = []
    for group in by_id.values():
        for row in group:
            if str(row[3]).casefold() == child_column.casefold():
                if len(group) != 1:
                    return "composite_foreign_key"
                matches.append(row)
    if len(matches) != 1:
        return "foreign_key_not_unique"
    row = matches[0]
    actual_parent_column = str(row[4])
    if not actual_parent_column:
        parent_info, _ = schema_table_info(conn, parent_table)
        pk = [str(item["name"]) for item in parent_info if int(item["pk"]) > 0]
        if len(pk) != 1:
            return "referenced_parent_key_not_single_column"
        actual_parent_column = pk[0]
    if str(row[2]).casefold() != parent_table.casefold() or actual_parent_column.casefold() != parent_column.casefold():
        return "declared_foreign_key_mismatch"
    return None


def eligible_schema(
    conn: sqlite3.Connection,
    pair: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    target = pair["target_mapping"]
    alternate = pair["alternate_mapping"]
    if len(target.get("ordered_column_pairs", [])) != 1 or len(alternate.get("ordered_column_pairs", [])) != 1:
        return None, "composite_candidate_mapping"
    fields = [
        (str(target["child_table"]), str(target["ordered_column_pairs"][0][0]), str(target["parent_table"]), str(target["ordered_column_pairs"][0][1])),
        (str(alternate["child_table"]), str(alternate["ordered_column_pairs"][0][0]), str(alternate["parent_table"]), str(alternate["ordered_column_pairs"][0][1])),
    ]
    keys = [field_key(table, column) for table, column, _, _ in fields]
    if keys[0] == keys[1]:
        return None, "overlapping_changed_fields"
    child_key_set = set(keys)
    for table, column, parent_table, parent_column in fields:
        if field_key(parent_table, parent_column) in child_key_set:
            return None, "changed_field_overlaps_parent_key"
        info, create_sql = schema_table_info(conn, table)
        if not info:
            return None, "child_table_missing"
        if re_without_rowid(create_sql):
            return None, "without_rowid"
        if any(str(item["name"]).casefold() in {"rowid", "_rowid_", "oid"} for item in info):
            return None, "rowid_shadowed"
        if any(int(item["hidden"]) in {2, 3} for item in conn.execute(f"PRAGMA main.table_xinfo({quote_ident(table)})").fetchall()):
            return None, "generated_column"
        if has_check_constraint(create_sql):
            return None, "table_check_constraint"
        column_matches = [item for item in info if str(item["name"]).casefold() == column.casefold()]
        if len(column_matches) != 1:
            return None, "changed_column_missing_or_ambiguous"
        if int(column_matches[0]["pk"]) > 0:
            return None, "changed_column_is_primary_key"
        fk_problem = validate_declared_fk(conn, table, column, parent_table, parent_column)
        if fk_problem:
            return None, fk_problem
    changed_by_table: dict[str, set[str]] = defaultdict(set)
    table_names: dict[str, str] = {}
    for table, column, _, _ in fields:
        changed_by_table[table.casefold()].add(column.casefold())
        table_names[table.casefold()] = table
    unique_specs: dict[str, list[dict[str, Any]]] = {}
    for table_fold, columns in changed_by_table.items():
        table = table_names[table_fold]
        try:
            unique_specs[table_fold] = get_index_specs(conn, table, columns)
        except StopRun as error:
            return None, error.code.removeprefix("INELIGIBLE_").lower()
    fk_specs = []
    for table, column, parent_table, parent_column in fields:
        fk_specs.append({
            "child_table": table,
            "child_column": column,
            "parent_table": parent_table,
            "parent_column": parent_column,
            "field_key": field_key(table, column),
        })
    return {
        "fk_specs": fk_specs,
        "unique_specs": unique_specs,
        "changed_by_table": {table_names[key]: sorted(value) for key, value in changed_by_table.items()},
        "table_names": table_names,
    }, None


def re_without_rowid(create_sql: str) -> bool:
    import re

    return re.search(r"\bWITHOUT\s+ROWID\b", create_sql, flags=re.IGNORECASE) is not None


def has_check_constraint(create_sql: str) -> bool:
    import re

    return re.search(r"\bCHECK\s*\(", create_sql, flags=re.IGNORECASE) is not None


def bounded_rows(conn: sqlite3.Connection, query: str):
    started = time.perf_counter()
    deadline = started + QUERY_TIMEOUT_SECONDS
    conn.set_progress_handler(lambda: 1 if time.perf_counter() >= deadline else 0, 1000)
    try:
        cursor = conn.execute(query)
        for row in cursor:
            if time.perf_counter() >= deadline:
                raise sqlite3.OperationalError("interrupted")
            yield tuple(row)
    finally:
        conn.set_progress_handler(None, 0)


def bounded_first(conn: sqlite3.Connection, query: str) -> tuple[Any, ...] | None:
    rows = bounded_rows(conn, query)
    try:
        return next(rows, None)
    finally:
        rows.close()


def load_field_rows(conn: sqlite3.Connection, table: str, column: str, budget_check) -> list[tuple[int, Any]]:
    rows: list[tuple[int, Any]] = []
    query = f"SELECT rowid, {quote_ident(column)} FROM main.{quote_ident(table)} ORDER BY rowid"
    for index, row in enumerate(bounded_rows(conn, query), start=1):
        rows.append((int(row[0]), row[1]))
        if index % 10_000 == 0:
            budget_check()
    return rows


def has_invalid_fk_values(conn: sqlite3.Connection, spec: dict[str, Any], view: bool = False) -> bool:
    child_source = f"temp.{quote_ident(spec['child_table'])}" if view else f"main.{quote_ident(spec['child_table'])}"
    query = (
        f"SELECT 1 FROM {child_source} AS c "
        f"WHERE c.{quote_ident(spec['child_column'])} IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM main.{quote_ident(spec['parent_table'])} AS p "
        f"WHERE p.{quote_ident(spec['parent_column'])}=c.{quote_ident(spec['child_column'])}) LIMIT 1"
    )
    return bounded_first(conn, query) is not None


def fetch_field_snapshot(conn: sqlite3.Connection, schema: dict[str, Any], budget_check) -> tuple[dict[str, list[tuple[int, Any]]], dict[str, int]]:
    field_rows: dict[str, list[tuple[int, Any]]] = {}
    table_counts: dict[str, int] = {}
    for table, columns in schema["changed_by_table"].items():
        count_row = bounded_first(conn, f"SELECT COUNT(*) FROM main.{quote_ident(table)}")
        require(count_row is not None, "TABLE_COUNT_QUERY_EMPTY")
        count = int(count_row[0])
        table_counts[table.casefold()] = count
        for column in columns:
            key = field_key(table, column)
            field_rows[key] = load_field_rows(conn, table, column, budget_check)
            require(len(field_rows[key]) == count, "FIELD_ROW_COUNT_MISMATCH")
    return field_rows, table_counts


def validate_original_domains(conn: sqlite3.Connection, schema: dict[str, Any]) -> str | None:
    for spec in schema["fk_specs"]:
        try:
            if has_invalid_fk_values(conn, spec):
                return "original_fk_domain_violation"
        except sqlite3.Error:
            return "fk_domain_check_error"
    return None


def sql_mentions_unsupported_rowid(sql: str) -> bool:
    import re

    return re.search(r"\b(?:rowid|_rowid_|oid)\b", sql, flags=re.IGNORECASE) is not None


def sql_qualifies_changed_table(sql: str, child_tables: set[str]) -> bool:
    try:
        import sqlglot
        trees = [tree for tree in sqlglot.parse(sql, read="sqlite") if tree is not None]
        if len(trees) != 1:
            return True
        for node in trees[0].find_all(sqlglot.exp.Table):
            if str(node.name).casefold() in child_tables and (node.db or node.catalog):
                return True
        return False
    except Exception:
        return True


def view_unique_checks(conn: sqlite3.Connection, table: str, specs: list[dict[str, Any]]) -> bool:
    for spec in specs:
        collation = quote_ident(spec["collation"])
        col = quote_ident(spec["column"])
        where_sql = f" WHERE ({spec['predicate']})" if spec.get("predicate") else ""
        query = (
            f"SELECT 1 FROM temp.{quote_ident(table)}{where_sql} "
            f"GROUP BY {col} COLLATE {collation} HAVING COUNT({col})>1 LIMIT 1"
        )
        if bounded_first(conn, query) is not None:
            return False
    return True


def insert_mapping(conn: sqlite3.Connection, map_name: str, assignments: list[tuple[int, Any]]) -> None:
    conn.execute(f"CREATE TEMP TABLE {quote_ident(map_name)} (rid INTEGER PRIMARY KEY, value)")
    conn.executemany(
        f"INSERT INTO temp.{quote_ident(map_name)} (rid, value) VALUES (?, ?)",
        assignments,
    )


def build_temp_views(
    conn: sqlite3.Connection,
    schema: dict[str, Any],
    assignments: dict[str, list[tuple[int, Any]]],
    pair_hash: str,
) -> dict[str, Any]:
    map_names: dict[str, str] = {}
    per_table: dict[str, list[tuple[str, str]]] = defaultdict(list)
    actual_names: dict[str, str] = {}
    prefix = f"__gfmcf_{pair_hash[:16]}"
    for fk in schema["fk_specs"]:
        key = fk["field_key"]
        table_fold = fk["child_table"].casefold()
        if key in map_names:
            continue
        map_name = f"{prefix}_m_{len(map_names):02d}"
        insert_mapping(conn, map_name, assignments[key])
        map_names[key] = map_name
        per_table[table_fold].append((fk["child_column"], map_name))
        actual_names[table_fold] = fk["child_table"]

    validation_views: dict[str, str] = {}
    rowid_aliases: dict[str, str] = {}
    mapping_by_field = {key: name for key, name in map_names.items()}
    for table_fold, map_cols in per_table.items():
        table = actual_names[table_fold]
        info, _ = schema_table_info(conn, table)
        columns = [str(row["name"]) for row in info]
        rowid_alias = f"{prefix}_rowid"
        require(rowid_alias.casefold() not in {column.casefold() for column in columns}, "VALIDATION_ROWID_ALIAS_COLLISION")
        substitutions = {column.casefold(): map_name for column, map_name in map_cols}
        projections = []
        validation_projections = [f"t.rowid AS {quote_ident(rowid_alias)}"]
        joins = []
        for column in columns:
            map_name = substitutions.get(column.casefold())
            if map_name:
                alias = f"m_{len(joins):02d}"
                projections.append(
                    f"CASE WHEN {quote_ident(alias)}.rid IS NOT NULL "
                    f"THEN {quote_ident(alias)}.value ELSE t.{quote_ident(column)} END AS {quote_ident(column)}"
                )
                validation_projections.append(projections[-1])
                joins.append(
                    f"LEFT JOIN temp.{quote_ident(map_name)} AS {quote_ident(alias)} ON "
                    f"{quote_ident(alias)}.rid=t.rowid"
                )
            else:
                projections.append(f"t.{quote_ident(column)} AS {quote_ident(column)}")
                validation_projections.append(projections[-1])
        require(bool(projections), "TEMP_VIEW_EMPTY_PROJECTION")
        conn.execute(
            f"CREATE TEMP VIEW {quote_ident(table)} AS SELECT {', '.join(projections)} "
            f"FROM main.{quote_ident(table)} AS t {' '.join(joins)}"
        )
        validation_name = f"{prefix}_v_{len(validation_views):02d}"
        conn.execute(
            f"CREATE TEMP VIEW {quote_ident(validation_name)} AS SELECT {', '.join(validation_projections)} "
            f"FROM main.{quote_ident(table)} AS t {' '.join(joins)}"
        )
        validation_views[table_fold] = validation_name
        rowid_aliases[table_fold] = rowid_alias
    return {
        "map_names": mapping_by_field,
        "validation_views": validation_views,
        "rowid_aliases": rowid_aliases,
        "table_names": actual_names,
    }


def validate_temp_views(
    conn: sqlite3.Connection,
    schema: dict[str, Any],
    field_rows: dict[str, list[tuple[int, Any]]],
    assignments: dict[str, list[tuple[int, Any]]],
    table_counts: dict[str, int],
    view_artifacts: dict[str, Any],
) -> tuple[bool, str | None]:
    for table, columns in schema["changed_by_table"].items():
        expected_count = table_counts[table.casefold()]
        count_row = bounded_first(conn, f"SELECT COUNT(*) FROM temp.{quote_ident(table)}")
        require(count_row is not None, "TEMP_VIEW_COUNT_QUERY_EMPTY")
        actual_count = int(count_row[0])
        if actual_count != expected_count:
            return False, "row_count_mismatch"
        val_name = view_artifacts["validation_views"][table.casefold()]
        validation_count = bounded_first(conn, f"SELECT COUNT(*) FROM temp.{quote_ident(val_name)}")
        if validation_count is None or int(validation_count[0]) != expected_count:
            return False, "validation_view_row_count_mismatch"
        for column in columns:
            key = field_key(table, column)
            expected_values = [value for _, value in field_rows[key]]
            assigned_values = [value for _, value in assignments[key]]
            if len(assigned_values) != len(expected_values) or typed_counter(assigned_values) != typed_counter(expected_values):
                return False, "column_multiset_mismatch"
            if sum(value is None for value in assigned_values) != sum(value is None for value in expected_values):
                return False, "null_count_mismatch"
            map_name = view_artifacts["map_names"][key]
            map_count = bounded_first(conn, f"SELECT COUNT(*) FROM temp.{quote_ident(map_name)}")
            if map_count is None or int(map_count[0]) != expected_count:
                return False, "mapping_row_count_mismatch"
            if bounded_first(
                conn,
                f"SELECT 1 FROM main.{quote_ident(table)} AS t "
                f"LEFT JOIN temp.{quote_ident(map_name)} AS m ON m.rid=t.rowid "
                "WHERE m.rid IS NULL LIMIT 1",
            ) is not None:
                return False, "mapping_missing_source_row"
            rowid_alias = view_artifacts["rowid_aliases"][table.casefold()]
            check_sql = (
                f"SELECT 1 FROM temp.{quote_ident(val_name)} AS v "
                f"JOIN temp.{quote_ident(map_name)} AS m ON v.{quote_ident(rowid_alias)}=m.rid "
                f"WHERE typeof(v.{quote_ident(column)})<>typeof(m.value) "
                f"OR NOT (v.{quote_ident(column)} IS m.value) LIMIT 1"
            )
            if bounded_first(conn, check_sql) is not None:
                return False, "view_value_mapping_mismatch"
    for fk in schema["fk_specs"]:
        if has_invalid_fk_values(conn, fk, view=True):
            return False, "fk_domain_violation"
    for table, specs in schema["unique_specs"].items():
        table_name = next(name for name in schema["changed_by_table"] if name.casefold() == table)
        if not view_unique_checks(conn, table_name, specs):
            return False, "unique_constraint_violation"
    return True, None


def plan_valid_assignments(
    pair: dict[str, Any],
    schema: dict[str, Any],
    field_rows: dict[str, list[tuple[int, Any]]],
    table_counts: dict[str, int],
    db_path: Path,
    budget_check,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Freeze twenty distinct assignments only after every view invariant passes."""
    plans: list[dict[str, Any]] = []
    seen: set[str] = set()
    rejection_counts: Counter[str] = Counter()
    for seed in SEEDS:
        selected: dict[str, Any] | None = None
        for attempt in range(MAX_ATTEMPTS_PER_SEED):
            assignments = make_assignment(pair["pair_hash"], seed, attempt, field_rows)
            if is_identity(field_rows, assignments):
                rejection_counts["identity"] += 1
                continue
            digest = assignment_digest(assignments)
            if digest in seen:
                rejection_counts["duplicate_assignment"] += 1
                continue
            conn = None
            valid, invalid_reason = False, "view_setup_error"
            try:
                conn = open_readonly(db_path)
                view_artifacts = build_temp_views(conn, schema, assignments, pair["pair_hash"])
                conn.execute("PRAGMA query_only=ON")
                valid, invalid_reason = validate_temp_views(
                    conn, schema, field_rows, assignments, table_counts, view_artifacts
                )
            except sqlite3.Error as error:
                invalid_reason = f"view_setup_{getattr(error, 'sqlite_errorname', 'error').lower()}"
            finally:
                if conn is not None:
                    conn.close()
            budget_check()
            if not valid:
                rejection_counts[str(invalid_reason)] += 1
                continue
            seen.add(digest)
            selected = {"seed": seed, "attempt": attempt, "assignment_hash": digest}
            break
        if selected is None:
            raise StopRun("TWENTY_VALID_DISTINCT_ASSIGNMENTS_UNAVAILABLE")
        plans.append(selected)
    require(len(plans) == 20, "VALID_ASSIGNMENT_PLAN_COUNT_MISMATCH")
    return plans, dict(rejection_counts)


def read_query(conn: sqlite3.Connection, sql: str) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        evaluator._validate_sql(sql)
    except Exception:
        return {"status": "blocked", "error_type": "unsafe_or_invalid_sql", "seconds": round(time.perf_counter() - start, 6)}
    deadline = start + QUERY_TIMEOUT_SECONDS
    conn.set_progress_handler(lambda: 1 if time.perf_counter() >= deadline else 0, 1000)
    conn.set_authorizer(evaluator._authorize)
    length_status = "byte_limit"
    try:
        if SQLITE_HEAP_LIMIT // 2 < BYTE_LIMIT:
            length_status = "memory_limit"
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(1024, min(BYTE_LIMIT, SQLITE_HEAP_LIMIT // 2, 2**31 - 1)))
        cursor = conn.execute(sql)
        columns = [item[0] for item in cursor.description]
        size = sum(len(column.encode("utf-8")) for column in columns)
        if size > BYTE_LIMIT:
            return {"status": "byte_limit", "error_type": "byte_limit", "seconds": round(time.perf_counter() - start, 6)}
        rows = []
        for row in cursor:
            if time.perf_counter() >= deadline:
                return {"status": "timeout", "error_type": "deadline_exceeded", "seconds": round(time.perf_counter() - start, 6)}
            if len(rows) >= ROW_LIMIT:
                return {"status": "row_limit", "error_type": "row_limit", "seconds": round(time.perf_counter() - start, 6)}
            size += 8 + sum(evaluator._cell_bytes(value) for value in row)
            if size > BYTE_LIMIT:
                return {"status": "byte_limit", "error_type": "byte_limit", "seconds": round(time.perf_counter() - start, 6)}
            rows.append(tuple(row))
        return {"status": "ok", "columns": columns, "rows": rows, "seconds": round(time.perf_counter() - start, 6)}
    except sqlite3.Error as error:
        if time.perf_counter() >= deadline or "interrupted" in str(error).lower():
            status, error_type = "timeout", "deadline_exceeded"
        elif getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_NOMEM:
            status, error_type = "memory_limit", "sqlite_memory_limit"
        elif getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_TOOBIG:
            status, error_type = length_status, length_status
        elif getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH:
            status, error_type = "blocked", "sqlite_authorizer_denied"
        else:
            status, error_type = "error", "sqlite_error"
        return {"status": status, "error_type": error_type, "seconds": round(time.perf_counter() - start, 6)}
    except MemoryError:
        return {"status": "memory_limit", "error_type": "python_memory_limit", "seconds": round(time.perf_counter() - start, 6)}
    finally:
        conn.set_progress_handler(None, 0)
        conn.set_authorizer(None)


def prepare_pair(
    pair: dict[str, Any],
    db_path: Path,
    record: dict[str, Any],
    schema_by_db: dict[str, dict[str, Any]],
    budget_check,
) -> tuple[dict[str, Any] | None, str | None]:
    conn = None
    try:
        conn = open_readonly(db_path)
    except Exception as error:  # noqa: BLE001 - only class is safe to report.
        return None, f"database_open_{type(error).__name__}"
    try:
        schema, reason = eligible_schema(conn, pair)
        if schema is None:
            return None, reason
        if validate_original_domains(conn, schema):
            return None, "original_fk_domain_violation"
        unit = pair["unit"]
        sql = record.get("SQL")
        if not isinstance(sql, str) or not sql.strip():
            return None, "question_sql_missing"
        if hashlib.sha256(sql.encode("utf-8")).hexdigest() != pair.get("question_sql_sha256"):
            return None, "question_sql_hash_mismatch"
        changed_tables = set(schema["table_names"].values())
        if sql_mentions_unsupported_rowid(sql):
            return None, "query_uses_rowid_alias"
        if sql_qualifies_changed_table(sql, {table.casefold() for table in changed_tables}):
            return None, "query_schema_qualifies_changed_table"
        schema_row = schema_by_db.get(str(unit["db_id"]))
        if schema_row is None:
            return None, "schema_row_missing"
        known_columns = build_known_columns(schema_row)
        target_sql, target_error = baseline.build_candidate_sql(sql, pair["target_mapping"], pair["target_mapping"], known_columns)
        alternate_sql, alternate_error = baseline.build_candidate_sql(sql, pair["target_mapping"], pair["alternate_mapping"], known_columns)
        if target_sql is None or alternate_sql is None:
            return None, "query_mapping_rewrite_unsupported"
        if target_error or alternate_error:
            return None, "query_mapping_rewrite_unsupported"
        field_rows, table_counts = fetch_field_snapshot(conn, schema, budget_check)
        conn.close()
        conn = None
        plans, rejection_counts = plan_valid_assignments(
            pair, schema, field_rows, table_counts, db_path, budget_check
        )
        receipt = {
            "schema": schema,
            "table_counts": table_counts,
            "permutation_plan": plans,
            "generation_rejections": rejection_counts,
            "target_sql": target_sql,
            "alternate_sql": alternate_sql,
        }
        return receipt, None
    except StopRun as error:
        return None, error.code.lower()
    except sqlite3.Error as error:
        return None, f"eligibility_sqlite_{getattr(error, 'sqlite_errorname', 'error').lower()}"
    except MemoryError:
        return None, "eligibility_memory_limit"
    finally:
        if conn is not None:
            conn.close()


def execute_pair(
    pair: dict[str, Any],
    receipt: dict[str, Any],
    db_path: Path,
    budget_check,
) -> dict[str, Any]:
    schema = receipt["schema"]
    snapshot_conn = open_readonly(db_path)
    try:
        field_rows, table_counts = fetch_field_snapshot(snapshot_conn, schema, budget_check)
    finally:
        snapshot_conn.close()
    require(table_counts == receipt["table_counts"], "TABLE_ROW_COUNT_REPLAY_MISMATCH")
    per_seed = []
    seen: set[str] = set()
    rejection_counts: Counter[str] = Counter()
    pair_status = "complete"
    for seed_index, plan in enumerate(receipt["permutation_plan"]):
        seed, attempt = int(plan["seed"]), int(plan["attempt"])
        assignments = make_assignment(pair["pair_hash"], seed, attempt, field_rows)
        assignment_hash = assignment_digest(assignments)
        if assignment_hash != plan["assignment_hash"] or assignment_hash in seen:
            pair_status = "assignment_replay_mismatch"
            break
        seen.add(assignment_hash)
        conn = None
        try:
            conn = open_readonly(db_path)
            view_artifacts = build_temp_views(conn, schema, assignments, pair["pair_hash"])
            conn.execute("PRAGMA query_only=ON")
            valid, invalid_reason = validate_temp_views(
                conn, schema, field_rows, assignments, table_counts, view_artifacts
            )
            if not valid:
                pair_status = "view_invariant_replay_mismatch"
                per_seed.append({"seed": seed, "attempt": attempt, "assignment_hash": assignment_hash, "status": pair_status, "reason": invalid_reason})
                break
            target = read_query(conn, receipt["target_sql"])
            alternate = read_query(conn, receipt["alternate_sql"])
            budget_check()
            if target.get("status") != "ok" or alternate.get("status") != "ok":
                pair_status = "query_incomplete"
                per_seed.append({
                    "seed": seed,
                    "attempt": attempt,
                    "assignment_hash": assignment_hash,
                    "status": "query_incomplete",
                    "target_status": target.get("status"),
                    "alternate_status": alternate.get("status"),
                    "target_error": target.get("error_type"),
                    "alternate_error": alternate.get("error_type"),
                })
                break
            if target.get("columns") != alternate.get("columns"):
                pair_status = "column_schema_mismatch"
                per_seed.append({"seed": seed, "attempt": attempt, "assignment_hash": assignment_hash, "status": pair_status})
                break
            comparison = evaluator.compare_rows(target["rows"], alternate["rows"])
            if comparison.get("comparison_status") != "ok":
                pair_status = "comparison_unknown"
                per_seed.append({
                    "seed": seed,
                    "attempt": attempt,
                    "assignment_hash": assignment_hash,
                    "status": pair_status,
                    "comparison_status": comparison.get("comparison_status"),
                })
                break
            target_count = len(target["rows"])
            alternate_count = len(alternate["rows"])
            per_seed.append({
                "seed": seed,
                "attempt": attempt,
                "assignment_hash": assignment_hash,
                "status": "ok",
                "informative": target_count > 0 or alternate_count > 0,
                "bag_equal": bool(comparison.get("bag_correct")),
                "set_equal": bool(comparison.get("set_correct")),
                "target_row_count": target_count,
                "alternate_row_count": alternate_count,
                "target_seconds": target.get("seconds"),
                "alternate_seconds": alternate.get("seconds"),
            })
        finally:
            if conn is not None:
                conn.close()
    return {
        "pair_hash": pair["pair_hash"],
        "candidate_hash": pair["candidate_hash"],
        "unit_hash": pair["unit_hash"],
        "anonymous_db": pair["anonymous_db"],
        "status": pair_status,
        "per_seed": per_seed,
        "rejection_counts": dict(rejection_counts),
    }


def aggregate_results(pair_results: list[dict[str, Any]], coverage: dict[str, Any]) -> dict[str, Any]:
    successful = [row for row in pair_results if row.get("status") == "complete" and len(row.get("per_seed", [])) == 20]
    informative = [row for row in successful if any(seed.get("informative") for seed in row["per_seed"])]
    all_empty = [row for row in successful if not any(seed.get("informative") for seed in row["per_seed"])]
    divergent = [row for row in informative if any(seed.get("informative") and seed.get("bag_equal") is False for seed in row["per_seed"])]
    db_labels = sorted({row["anonymous_db"] for row in informative})
    db_slices = {}
    for label in sorted(set(coverage["eligible_by_anonymous_db"]) | {row["anonymous_db"] for row in pair_results}):
        rows = [row for row in pair_results if row["anonymous_db"] == label]
        info_rows = [row for row in informative if row["anonymous_db"] == label]
        div_rows = [row for row in divergent if row["anonymous_db"] == label]
        db_slices[label] = {
            "eligible_pairs": coverage["eligible_by_anonymous_db"].get(label, 0),
            "executed_pairs": len(rows),
            "valid_20_seed_pairs": sum(row in successful for row in rows),
            "informative_pairs": len(info_rows),
            "ever_bag_diverged_pairs": len(div_rows),
        }
    per_seed = {}
    for seed in SEEDS:
        rows = [item for pair in successful for item in pair["per_seed"] if item["seed"] == seed]
        informative_rows = [item for item in rows if item.get("informative")]
        per_seed[str(seed)] = {
            "valid_pair_count": len(rows),
            "informative_pair_count": len(informative_rows),
            "bag_diverged_count": sum(item.get("bag_equal") is False for item in informative_rows),
            "set_diverged_count": sum(item.get("set_equal") is False for item in informative_rows),
            "both_empty_count": sum(not item.get("informative") for item in rows),
            "one_empty_count": sum((item.get("target_row_count") == 0) != (item.get("alternate_row_count") == 0) for item in informative_rows),
        }
    denominator = len(informative)
    rate = len(divergent) / denominator if denominator else None
    pair_fractions = []
    for pair in informative:
        informative_seeds = [seed for seed in pair["per_seed"] if seed.get("informative")]
        divergent_seeds = [seed for seed in informative_seeds if seed.get("bag_equal") is False]
        if informative_seeds:
            pair_fractions.append(len(divergent_seeds) / len(informative_seeds))
    if denominator < 40 or len(db_labels) < 3:
        decision = "INCONCLUSIVE_INFORMATIVE_COVERAGE"
    elif rate is not None and rate >= 0.5:
        decision = "POSITIVE_SENSITIVITY_SIGNAL"
    elif rate is not None and rate <= 0.25:
        decision = "WEAK_SENSITIVITY_SIGNAL"
    else:
        decision = "INCONCLUSIVE"
    return {
        "experiment_id": EXPERIMENT_ID,
        "status": decision,
        "fixed_candidate_pairs": EXPECTED_PAIR_COUNT,
        "structurally_eligible_pairs": coverage["eligible_pairs"],
        "executed_pairs": len(pair_results),
        "pairs_with_20_valid_seed_comparisons": len(successful),
        "all_perturbations_both_empty_pairs": len(all_empty),
        "informative_pairs": denominator,
        "primary_metric": "EverBagDiverged@20",
        "ever_bag_diverged_pairs": len(divergent),
        "ever_bag_diverged_rate": rate,
        "divergence_fraction_per_informative_pair": {
            "count": len(pair_fractions),
            "mean": statistics.mean(pair_fractions) if pair_fractions else None,
            "median": statistics.median(pair_fractions) if pair_fractions else None,
            "minimum": min(pair_fractions) if pair_fractions else None,
            "maximum": max(pair_fractions) if pair_fractions else None,
        },
        "original_static_instance": {
            "fixed_pairs_bag_equal": EXPECTED_PAIR_COUNT,
            "fixed_pairs": EXPECTED_PAIR_COUNT,
            "bag_equal_rate": 1.0,
        },
        "perturbation_outcomes": {
            "valid_seed_comparisons": sum(len(row["per_seed"]) for row in successful),
            "informative_seed_comparisons": sum(item.get("informative", False) for row in successful for item in row["per_seed"]),
            "both_empty_seed_comparisons": sum(not item.get("informative", False) for row in successful for item in row["per_seed"]),
            "one_empty_seed_comparisons": sum(
                (item.get("target_row_count") == 0) != (item.get("alternate_row_count") == 0)
                for row in successful for item in row["per_seed"] if item.get("informative")
            ),
        },
        "positive_threshold": 0.5,
        "weak_threshold": 0.25,
        "minimum_informative_pairs": 40,
        "minimum_anonymous_databases": 3,
        "informative_anonymous_databases": db_labels,
        "per_seed": per_seed,
        "anonymous_database_slices": db_slices,
        "eligibility_exclusion_counts": coverage["exclusion_counts"],
        "preflight_rejected_assignment_attempts": coverage.get("preflight_rejected_assignment_attempts", {}),
        "execution_failure_status_counts": dict(Counter(row.get("status", "unknown") for row in pair_results if row.get("status") != "complete")),
        "query_or_comparison_failure_pairs": sum(row.get("status") != "complete" for row in pair_results),
        "interpretation_limit": "This is a fixed-snapshot counterfactual sensitivity diagnostic, not semantic equivalence, business Role correctness, Test Suite Accuracy, or a GFM ranking result.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--prior-full-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-receipt", type=Path)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    require(args.config.is_file(), "CONFIG_MISSING")
    require(args.execution_config.is_file(), "EXECUTION_CONFIG_MISSING")
    config = read_json(args.config)
    execution_config = read_json(args.execution_config)
    branch, source_commit = assert_branch_and_config(args, config)
    require(execution_config.get("parent_config_sha256") == sha256_file(args.config), "EXECUTION_CONFIG_PARENT_MISMATCH")
    paths = input_paths(args)
    require(execution_config.get("prior_aggregate_sha256") == sha256_file(paths["prior_aggregate"]), "PRIOR_AGGREGATE_HASH_MISMATCH")
    require(execution_config.get("prior_runner_sha256") == EXPECTED_PRIOR_RUNNER_SHA256, "EXECUTION_PRIOR_RUNNER_MISMATCH")
    require(execution_config.get("permutations", {}).get("count") == 20, "EXECUTION_PERMUTATION_COUNT_MISMATCH")
    require(execution_config.get("permutations", {}).get("seeds_inclusive") == [SEEDS[0], SEEDS[-1]], "EXECUTION_SEED_RANGE_MISMATCH")
    require(execution_config.get("permutations", {}).get("max_rejection_attempts_per_seed") == MAX_ATTEMPTS_PER_SEED, "EXECUTION_ATTEMPT_LIMIT_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("positive_threshold") == 0.5, "EXECUTION_POSITIVE_THRESHOLD_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("weak_threshold") == 0.25, "EXECUTION_WEAK_THRESHOLD_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("minimum_eligible_pairs_before_smoke") == 40, "EXECUTION_ELIGIBILITY_GATE_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("minimum_informative_pairs_for_primary_metric") == 40, "EXECUTION_PRIMARY_GATE_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("minimum_anonymous_databases") == 3, "EXECUTION_DATABASE_GATE_MISMATCH")
    require(execution_config.get("coverage_and_decisions", {}).get("smoke_pairs") == 5, "EXECUTION_SMOKE_COUNT_MISMATCH")
    require(execution_config.get("permutations", {}).get("sample_order") == "ascending SHA256(experiment_id || private_pair_identity)", "EXECUTION_SAMPLE_ORDER_MISMATCH")
    frozen_environment = execution_config.get("environment", {})
    require(frozen_environment.get("python") == "3.12.14" and frozen_environment.get("sqlite") == "3.53.2" and frozen_environment.get("sqlglot") == EXPECTED_SQLGLOT, "EXECUTION_ENVIRONMENT_MISMATCH")
    require(frozen_environment.get("max_cpu_threads") == 8 and frozen_environment.get("max_cpu_seconds") == MAX_CPU_SECONDS, "EXECUTION_CPU_BUDGET_MISMATCH")
    require(frozen_environment.get("max_wall_seconds") == MAX_WALL_SECONDS and frozen_environment.get("max_rss_gib") == MAX_RSS_GIB, "EXECUTION_RESOURCE_BUDGET_MISMATCH")
    require(frozen_environment.get("query_timeout_seconds") == QUERY_TIMEOUT_SECONDS and frozen_environment.get("row_limit") == ROW_LIMIT, "EXECUTION_QUERY_LIMIT_MISMATCH")
    require(frozen_environment.get("byte_limit") == BYTE_LIMIT and frozen_environment.get("sqlite_heap_limit_bytes") == SQLITE_HEAP_LIMIT, "EXECUTION_OUTPUT_LIMIT_MISMATCH")
    expected_run_id = execution_config.get("run_ids", {}).get(args.mode)
    require(isinstance(expected_run_id, str) and expected_run_id, "EXECUTION_RUN_ID_MISSING")
    require(args.run_id == expected_run_id, "RUN_ID_MISMATCH")
    verified = verify_inputs(config, paths)
    verified["hashes"]["files"]["prior_aggregate"] = {
        "bytes": paths["prior_aggregate"].stat().st_size,
        "sha256": execution_config["prior_aggregate_sha256"],
    }
    prior_meta = verified["prior_run_metadata"]
    require(prior_meta.get("run_id") == "p0_fk_mapping_instance_equivalence_20261107_01_full_002", "PRIOR_RUN_ID_MISMATCH")
    require(prior_meta.get("source_commit") == execution_config.get("prior_source_commit"), "PRIOR_SOURCE_COMMIT_MISMATCH")
    require(prior_meta.get("runner_sha256") == EXPECTED_PRIOR_RUNNER_SHA256, "PRIOR_RUN_METADATA_RUNNER_MISMATCH")

    args.output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(args.output_dir, 0o700)
    write_json(args.output_dir / "input_preflight_private.json", {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "config_sha256": sha256_file(args.config),
        "execution_config_sha256": sha256_file(args.execution_config),
        "source_commit": source_commit,
        "source_branch": branch,
        "inputs": verified["hashes"],
    })

    # No BIRD question/SQL, candidate metrics, or SQLite connection is read before
    # the complete hash gate above.
    manifest = read_json(paths["source_manifest"])
    prior_metrics = read_json(paths["prior_metrics"])
    prior_aggregate = read_json(paths["prior_aggregate"])
    dev_questions = read_json(paths["dev_json"])
    schema_rows = read_json(paths["dev_tables_json"])
    require(isinstance(dev_questions, list) and len(dev_questions) == 1534, "BIRD_QUESTION_COUNT_MISMATCH")
    require(isinstance(schema_rows, list) and len(schema_rows) == 11, "BIRD_SCHEMA_COUNT_MISMATCH")
    questions_by_key = {packet.question_key(row): row for row in dev_questions if isinstance(row, dict)}
    require(len(questions_by_key) == len(dev_questions), "BIRD_QUESTION_KEY_DUPLICATE")
    schema_by_db = {str(row["db_id"]): row for row in schema_rows if isinstance(row, dict)}
    pairs, prior_reconstruction_summary, _ = reconstruct_pairs(
        config,
        manifest,
        prior_metrics,
        prior_aggregate,
        verified["database_labels_by_id"],
    )
    require(len(pairs) == EXPECTED_PAIR_COUNT, "FIXED_SAMPLE_COUNT_MISMATCH")
    expected_source = execution_config.get("reconstructed_source_expectations", {})
    require(
        expected_source.get("expected_fixed_pairs") == len(pairs)
        and expected_source.get("expected_complete_units") == prior_reconstruction_summary["prior_complete_units"]
        and expected_source.get("expected_alternative_comparisons") == prior_reconstruction_summary["prior_alternative_candidate_comparisons"],
        "EXECUTION_SAMPLE_ASSERTION_MISMATCH",
    )
    require(
        expected_source.get("expected_complete_units_by_anonymous_db") == prior_reconstruction_summary["complete_units_by_anonymous_db"]
        and expected_source.get("expected_equal_alternative_units_by_anonymous_db") == prior_reconstruction_summary["units_with_equal_alternative_by_anonymous_db"],
        "EXECUTION_STRATA_ASSERTION_MISMATCH",
    )

    if args.mode == "full":
        require(args.smoke_receipt is not None and args.smoke_receipt.is_file(), "SMOKE_RECEIPT_MISSING")
        smoke = read_json(args.smoke_receipt)
        require(smoke.get("status") == "SMOKE_PASS", "SMOKE_RECEIPT_NOT_PASS")
        smoke_hashes = set(smoke.get("selected_pair_hashes", []))
        require(len(smoke_hashes) == 5, "SMOKE_PAIR_COUNT_MISMATCH")
        smoke_private_path = args.smoke_receipt.parent / "private_pair_metrics.json"
        require(smoke_private_path.is_file(), "SMOKE_PRIVATE_METRICS_MISSING")
        smoke_private = read_json(smoke_private_path)
        smoke_assignments = {
            row["pair_hash"]: [seed.get("assignment_hash") for seed in row.get("per_seed", [])]
            for row in smoke_private.get("pairs", [])
        }
        require(set(smoke_assignments) == smoke_hashes, "SMOKE_PRIVATE_PAIR_SET_MISMATCH")
    else:
        smoke_hashes = set()
        smoke_assignments = {}

    receipts: dict[str, dict[str, Any]] = {}
    excluded: Counter[str] = Counter()
    eligible_pairs: list[dict[str, Any]] = []
    eligibility_progress_path = args.output_dir / "eligibility_progress_private.jsonl"
    eligibility_progress_path.touch(mode=0o600, exist_ok=False)
    with eligibility_progress_path.open("a", encoding="utf-8") as progress_handle:
        for index, pair in enumerate(pairs, start=1):
            require(pair["question_key_sha256"] in questions_by_key, "QUESTION_KEY_NOT_FOUND")
            record = questions_by_key[pair["question_key_sha256"]]
            db_path = verified["database_paths"][pair["anonymous_db"]]
            receipt, reason = prepare_pair(pair, db_path, record, schema_by_db, lambda: check_budget(wall_start, cpu_start))
            if receipt is None:
                excluded[str(reason or "ineligible_unknown")] += 1
                progress_row = {"pair_hash": pair["pair_hash"], "status": "ineligible", "reason": str(reason or "ineligible_unknown")}
            else:
                eligible_pairs.append(pair)
                receipts[pair["pair_hash"]] = receipt
                progress_row = {"pair_hash": pair["pair_hash"], "status": "eligible", "permutation_count": len(receipt["permutation_plan"])}
            progress_handle.write(json.dumps(progress_row, ensure_ascii=False, sort_keys=True) + "\n")
            progress_handle.flush()
            os.fsync(progress_handle.fileno())
            print(f"eligibility_progress={index}/{len(pairs)} eligible={len(eligible_pairs)}", flush=True)
            check_budget(wall_start, cpu_start)

    eligible_db = sorted({pair["anonymous_db"] for pair in eligible_pairs})
    eligible_by_db = Counter(pair["anonymous_db"] for pair in eligible_pairs)
    preflight_rejections: Counter[str] = Counter()
    for receipt in receipts.values():
        preflight_rejections.update(receipt.get("generation_rejections", {}))
    coverage = {
        "eligible_pairs": len(eligible_pairs),
        "eligible_by_anonymous_db": dict(eligible_by_db),
        "exclusion_counts": dict(excluded),
        "preflight_rejected_assignment_attempts": dict(preflight_rejections),
    }
    if len(eligible_pairs) < 40 or len(eligible_db) < 3:
        coverage_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "INCONCLUSIVE_ELIGIBILITY_COVERAGE",
            "fixed_candidate_pairs": EXPECTED_PAIR_COUNT,
            "structurally_eligible_pairs": len(eligible_pairs),
            "eligible_anonymous_databases": eligible_db,
            "minimum_eligible_pairs": 40,
            "minimum_anonymous_databases": 3,
            "eligibility_exclusion_counts": dict(excluded),
            "preflight_rejected_assignment_attempts": dict(preflight_rejections),
            "eligible_pairs_by_anonymous_db": dict(eligible_by_db),
        }
        write_json(args.output_dir / "aggregate_summary.json", coverage_summary)
        write_json(args.output_dir / "coverage_stop_private.json", {
            "eligible_pair_hashes": [pair["pair_hash"] for pair in eligible_pairs],
            "source_summary": prior_reconstruction_summary,
            "input_hashes": verified["hashes"],
        })
        write_json(args.output_dir / "run_receipt.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": coverage_summary["status"],
            "source_commit": source_commit,
            "source_branch": branch,
            "runner_sha256": sha256_file(Path(__file__)),
            "config_sha256": sha256_file(args.config),
            "execution_config_sha256": sha256_file(args.execution_config),
            "resources": check_budget(wall_start, cpu_start),
        })
        return {"status": coverage_summary["status"], "summary": coverage_summary, "resources": check_budget(wall_start, cpu_start)}

    if args.mode == "smoke":
        eligible_pairs = eligible_pairs[:5]
        require(len(eligible_pairs) == 5, "SMOKE_ELIGIBLE_PAIR_COUNT_MISMATCH")
    else:
        require(smoke_hashes.issubset({pair["pair_hash"] for pair in eligible_pairs}), "SMOKE_PAIRS_NOT_IN_FULL_ELIGIBLE_SET")

    private_pairs: list[dict[str, Any]] = []
    private_receipts: dict[str, Any] = {}
    pair_progress_path = args.output_dir / "pair_progress_private.jsonl"
    pair_progress_path.touch(mode=0o600, exist_ok=False)
    for index, pair in enumerate(eligible_pairs, start=1):
        receipt = receipts[pair["pair_hash"]]
        pair_result = execute_pair(
            pair,
            receipt,
            verified["database_paths"][pair["anonymous_db"]],
            lambda: check_budget(wall_start, cpu_start),
        )
        private_pairs.append(pair_result)
        with pair_progress_path.open("a", encoding="utf-8") as progress_handle:
            progress_handle.write(json.dumps(pair_result, ensure_ascii=False, sort_keys=True) + "\n")
            progress_handle.flush()
            os.fsync(progress_handle.fileno())
        private_receipts[pair["pair_hash"]] = {
            "assignment_hashes_preflight": [item["assignment_hash"] for item in receipt["permutation_plan"]],
            "assignment_attempts_preflight": [item["attempt"] for item in receipt["permutation_plan"]],
            "generation_rejections_preflight": receipt["generation_rejections"],
        }
        if pair_result.get("status") != "complete" or len(pair_result.get("per_seed", [])) != 20:
            if args.mode == "smoke":
                raise StopRun("SMOKE_PAIR_EXECUTION_INCOMPLETE")
        print(f"execution_progress={index}/{len(eligible_pairs)} complete_pairs={sum(x.get('status') == 'complete' for x in private_pairs)}", flush=True)

    if args.mode == "full":
        full_assignments = {
            row["pair_hash"]: [seed.get("assignment_hash") for seed in row.get("per_seed", [])]
            for row in private_pairs if row["pair_hash"] in smoke_hashes
        }
        require(full_assignments == smoke_assignments, "SMOKE_FULL_PERMUTATION_MISMATCH")

    resources = check_budget(wall_start, cpu_start)
    if args.mode == "smoke":
        require(len(private_pairs) == 5 and all(row.get("status") == "complete" and len(row.get("per_seed", [])) == 20 for row in private_pairs), "SMOKE_COVERAGE_GATE_FAILED")
        status = "SMOKE_PASS"
        public_summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": status,
            "fixed_candidate_pairs": EXPECTED_PAIR_COUNT,
            "structurally_eligible_pairs": coverage["eligible_pairs"],
            "smoke_pairs": len(private_pairs),
            "valid_seed_comparisons": sum(len(row["per_seed"]) for row in private_pairs),
            "smoke_informative_pairs": sum(any(seed.get("informative") for seed in row["per_seed"]) for row in private_pairs),
            "smoke_all_both_empty_pairs": sum(not any(seed.get("informative") for seed in row["per_seed"]) for row in private_pairs),
            "smoke_pairs_ever_bag_diverged": sum(any(seed.get("informative") and seed.get("bag_equal") is False for seed in row["per_seed"]) for row in private_pairs),
            "eligibility_exclusion_counts": coverage["exclusion_counts"],
            "preflight_rejected_assignment_attempts": coverage["preflight_rejected_assignment_attempts"],
            "anonymous_database_slices": {
                label: {"eligible_pairs": count, "smoke_pairs": sum(row["anonymous_db"] == label for row in private_pairs)}
                for label, count in sorted(coverage["eligible_by_anonymous_db"].items())
            },
        }
    else:
        public_summary = aggregate_results(private_pairs, coverage)
        public_summary["run_id"] = args.run_id
        status = public_summary["status"]

    # Rehash all source databases after execution; no result is accepted if any
    # original SQLite byte changed.
    post_db_hashes = {}
    for label, path in verified["database_paths"].items():
        post_db_hashes[label] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        require(post_db_hashes[label] == verified["hashes"]["sqlite"][label], f"DATABASE_CHANGED_{label}")

    write_json(args.output_dir / "aggregate_summary.json", public_summary)
    write_json(args.output_dir / "private_pair_metrics.json", {
        "pairs": private_pairs,
        "preflight_assignment_receipts": private_receipts,
    })
    write_json(args.output_dir / "input_manifest_private.json", {
        "inputs": verified["hashes"],
        "post_run_sqlite_hashes": post_db_hashes,
        "source_summary": prior_reconstruction_summary,
        "fixed_pair_hashes": [pair["pair_hash"] for pair in pairs],
    })
    receipt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": status,
        "selected_pair_hashes": [row["pair_hash"] for row in private_pairs],
        "config_sha256": sha256_file(args.config),
        "execution_config_sha256": sha256_file(args.execution_config),
        "runner_sha256": sha256_file(Path(__file__)),
        "source_commit": source_commit,
        "source_branch": branch,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "cpu_threads_max": 8,
        "wall_seconds": resources["wall_seconds"],
        "cpu_seconds": resources["cpu_seconds"],
        "peak_rss_gib": resources["peak_rss_gib"],
        "gpu_seconds": 0,
        "external_api_requests": 0,
        "local_model_requests": 0,
    }
    write_json(args.output_dir / "run_receipt.json", receipt)
    return {"status": status, "summary": public_summary, "resources": resources}


def main() -> int:
    args = parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except StopRun as error:
        if args.output_dir.exists():
            write_json(args.output_dir / "failure.json", {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "mode": args.mode,
                "status": "STOPPED",
                "reason_code": error.code,
            })
        print(json.dumps({"status": "STOPPED", "reason_code": error.code}, sort_keys=True))
        return 2
    except Exception as error:  # noqa: BLE001 - do not leak private data.
        reason = f"INTERNAL_ERROR_{type(error).__name__}"
        if args.output_dir.exists():
            write_json(args.output_dir / "failure.json", {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "mode": args.mode,
                "status": "STOPPED",
                "reason_code": reason,
            })
        print(json.dumps({"status": "STOPPED", "reason_code": reason}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
