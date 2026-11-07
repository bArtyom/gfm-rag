#!/usr/bin/env python3
"""Read-only SQLite audit of complete FK constraint identities in BIRD train."""
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
import sys
import time
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import audit_p0_bird_train_fk_mapping_capacity_20261107 as capacity  # noqa: E402

EXPERIMENT_ID = "p0_bird_train_fk_constraint_identity_20261107_01"
CAPACITY_ID = "p0_bird_train_fk_mapping_capacity_20261107_01"
EXPECTED_CAPACITY_RUNNER_SHA256 = "c98422fa518b0fa5c929ed77c27585f363f075fa3546b707cfd2d52dc9288871"
EXPECTED_CAPACITY_AGGREGATE_SHA256 = "fb7f8498f8fdfefe3f220ed06eaa04aa46d2f91ad7acc7018b9d49bdfcb54a66"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_QUESTIONS = 9428
EXPECTED_CANDIDATE_UNITS = 384
SMOKE_COUNT = 5
MIN_UNITS = 60
MIN_DATABASES = 4
MAX_WALL_SECONDS = 1800.0
MAX_CPU_SECONDS = 1200.0
MAX_RSS_GIB = 4.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def candidate_key_hash(candidate: dict) -> str:
    payload = [candidate["db_id"], candidate["question_key_hash"], list(candidate["table_pair"])]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def canonical_edge(child_table: str, child_column: str, parent_table: str, parent_column: str) -> tuple[str, str, str, str]:
    endpoints = sorted(
        ((child_table.casefold(), child_column.casefold()), (parent_table.casefold(), parent_column.casefold()))
    )
    return endpoints[0][0], endpoints[0][1], endpoints[1][0], endpoints[1][1]


def candidate_edges(schema: dict, table_pair: tuple[str, str]) -> set[tuple[str, str, str, str]]:
    result: set[tuple[str, str, str, str]] = set()
    for left_table, left_column, right_table, right_column in capacity.candidate_pairs(schema).get(table_pair, set()):
        result.add(canonical_edge(left_table, left_column, right_table, right_column))
    return result


def find_database_file(root: Path, db_id: str) -> Path:
    db_root = root.resolve()
    db_dir = (root / db_id).resolve()
    if os.path.commonpath((str(db_root), str(db_dir))) != str(db_root) or not db_dir.is_dir():
        raise ValueError("database_directory_outside_root_or_missing")
    files = sorted(path for pattern in ("*.sqlite", "*.db") for path in db_dir.glob(pattern) if path.is_file())
    if len(files) != 1:
        exact = [path for path in files if path.stem.casefold() == db_id.casefold()]
        if len(exact) == 1:
            files = exact
        else:
            raise ValueError("database_file_ambiguous_or_missing")
    path = files[0].resolve()
    if os.path.commonpath((str(db_root), str(path)) ) != str(db_root):
        raise ValueError("database_file_outside_root")
    return path


def reconstruct_candidates(args: argparse.Namespace, config: dict) -> tuple[list[dict], dict, dict]:
    train_schemas, train_schema_hash = capacity.read_schema_file(args.train_tables)
    dev_schemas, dev_schema_hash = capacity.read_schema_file(args.dev_tables)
    if train_schema_hash != config["dataset"]["train_schema_sha256"]:
        raise ValueError("train_schema_hash_mismatch")
    if dev_schema_hash != config["dataset"]["dev_schema_sha256"]:
        raise ValueError("dev_schema_hash_mismatch")

    train_db_ids = [str(row["db_id"]) for row in train_schemas]
    dev_db_ids = [str(row["db_id"]) for row in dev_schemas]
    if len(set(train_db_ids)) != len(train_db_ids) or len(set(dev_db_ids)) != len(dev_db_ids):
        raise ValueError("duplicate_schema_database_id")
    overlap = set(train_db_ids) & set(dev_db_ids)
    if overlap:
        raise ValueError("train_dev_database_overlap")
    if len(train_db_ids) != 69 or len(dev_db_ids) != 11:
        raise ValueError("schema_database_count_mismatch")

    train_hash = sha256_file(args.train_json)
    if train_hash != config["dataset"]["train_json_sha256"]:
        raise ValueError("train_json_hash_mismatch")
    train_rows = json.loads(args.train_json.read_text(encoding="utf-8"))
    if not isinstance(train_rows, list) or len(train_rows) != EXPECTED_QUESTIONS:
        raise ValueError("train_question_count_mismatch")

    schemas = {str(row["db_id"]): row for row in train_schemas}
    old_capacity_smoke_indices = {
        index for index, row in sorted(
            enumerate(train_rows),
            key=lambda item: capacity.stable_hash(
                CAPACITY_ID, str(item[1]["db_id"]), str(item[1].get("question_id", item[0]))
            ),
        )[:capacity.SMOKE_COUNT]
    }
    candidates: list[dict] = []
    parse_failures: Counter[str] = Counter()
    scope_failures: Counter[str] = Counter()
    parsed_count = 0
    for index, row in enumerate(train_rows):
        if index in old_capacity_smoke_indices:
            continue
        db_id = str(row["db_id"])
        if db_id not in schemas:
            raise ValueError("train_question_schema_missing")
        schema = schemas[db_id]
        question_key = str(row.get("question_id", index))
        question_hash = capacity.stable_hash(CAPACITY_ID, db_id, question_key)
        try:
            join_pairs, *_ = capacity.query_join_pairs(str(row.get("SQL") or ""), schema)
        except capacity.ScopeAuditError as error:
            scope_failures[str(error)] += 1
            continue
        except Exception as error:
            parse_failures[type(error).__name__] += 1
            continue
        parsed_count += 1
        fk_by_pair = capacity.candidate_pairs(schema)
        eligible_pairs = [(pair, len(fk_by_pair.get(pair, set()))) for pair in sorted(join_pairs)
                          if len(fk_by_pair.get(pair, set())) > 1]
        if not eligible_pairs:
            continue
        eligible_pairs.sort(key=lambda item: capacity.stable_hash(
            CAPACITY_ID, db_id, question_hash, item[0][0], item[0][1]
        ))
        table_pair, metadata_pair_count = eligible_pairs[0]
        tables_by_key = {str(name).casefold(): str(name) for name in schema["table_names_original"]}
        if any(name not in tables_by_key for name in table_pair):
            raise ValueError("candidate_table_name_missing")
        candidates.append({
            "db_id": db_id,
            "question_index": index,
            "question_key_hash": question_hash,
            "table_pair": list(table_pair),
            "table_names": [tables_by_key[name] for name in table_pair],
            "metadata_fk_column_pair_count": metadata_pair_count,
            "metadata_edges": sorted(candidate_edges(schema, table_pair)),
        })

    if parsed_count != EXPECTED_QUESTIONS - capacity.SMOKE_COUNT or parse_failures or scope_failures:
        raise ValueError("train_sql_or_scope_reconstruction_incomplete")
    if len(candidates) != EXPECTED_CANDIDATE_UNITS:
        raise ValueError("capacity_candidate_count_mismatch")

    anon_db_order = sorted(
        {candidate["db_id"] for candidate in candidates},
        key=lambda db_id: capacity.stable_hash(CAPACITY_ID, "anon_db", db_id),
    )
    anon_db = {db_id: f"db_{index:02d}" for index, db_id in enumerate(anon_db_order, start=1)}
    histogram = Counter(anon_db[candidate["db_id"]] for candidate in candidates)
    expected_histogram = config["capacity_stage"]["expected_database_histogram"]
    if dict(sorted(histogram.items())) != dict(sorted(expected_histogram.items())):
        raise ValueError("capacity_database_histogram_mismatch")

    smoke: list[dict] = []
    ordered = sorted(candidates, key=lambda item: stable_hash(
        EXPERIMENT_ID, item["db_id"], item["question_key_hash"], *item["table_pair"]
    ))
    seen_dbs: set[str] = set()
    for candidate in ordered:
        if candidate["db_id"] not in seen_dbs:
            smoke.append(candidate)
            seen_dbs.add(candidate["db_id"])
            if len(smoke) == SMOKE_COUNT:
                break
    if len(smoke) < SMOKE_COUNT:
        chosen = {candidate_key_hash(item) for item in smoke}
        for candidate in ordered:
            if candidate_key_hash(candidate) not in chosen:
                smoke.append(candidate)
                chosen.add(candidate_key_hash(candidate))
                if len(smoke) == SMOKE_COUNT:
                    break

    state = {
        "train_json_sha256": train_hash,
        "train_schema_sha256": train_schema_hash,
        "dev_schema_sha256": dev_schema_hash,
        "train_database_count": len(train_db_ids),
        "dev_database_count": len(dev_db_ids),
        "overlap_database_count": 0,
        "question_count": len(train_rows),
        "capacity_stage_smoke_questions_excluded": len(old_capacity_smoke_indices),
        "sql_parse_success": parsed_count,
        "sql_parse_failures": dict(parse_failures),
        "scope_failures": dict(scope_failures),
        "candidate_unit_count": len(candidates),
        "candidate_units_by_anonymous_database": dict(sorted(histogram.items())),
        "candidate_id_hashes": [candidate_key_hash(item) for item in candidates],
        "smoke_candidate_id_hashes": [candidate_key_hash(item) for item in smoke],
    }
    return candidates, {candidate["db_id"]: anon_db[candidate["db_id"]] for candidate in candidates}, state


def read_pragmas_for_database(db_path: Path, allowed_tables: set[str]) -> dict:
    quoted_path = quote(str(db_path.resolve()), safe="/:\\")
    uri = f"file:{quoted_path}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=15.0)
    connection.execute("PRAGMA query_only=ON")
    allowed = {table.casefold() for table in allowed_tables}
    denied_actions: list[int] = []

    def authorizer(action: int, arg1: str | None, arg2: str | None, _database: str | None, _trigger: str | None) -> int:
        if (action == sqlite3.SQLITE_PRAGMA and (arg1 or "").casefold() == "foreign_key_list"
                and (arg2 or "").casefold() in allowed):
            return sqlite3.SQLITE_OK
        denied_actions.append(action)
        return sqlite3.SQLITE_DENY

    connection.set_authorizer(authorizer)
    pair_edges: dict[tuple[str, str], set[tuple[str, str, str, str]]] = defaultdict(set)
    grouped_rows: dict[tuple[str, str, int], list[tuple[int, tuple[str, str, str, str]]]] = defaultdict(list)
    pragma_count = fk_row_count = unqualified_row_count = 0
    try:
        for child_table in sorted(allowed_tables, key=str.casefold):
            escaped = child_table.replace('"', '""')
            rows = connection.execute(f'PRAGMA foreign_key_list("{escaped}")').fetchall()
            pragma_count += 1
            for row in rows:
                constraint_id, sequence, parent_table, from_column, to_column = row[:5]
                fk_row_count += 1
                if not parent_table or not from_column or not to_column:
                    unqualified_row_count += 1
                    continue
                child_key = child_table.casefold()
                parent_key = str(parent_table).casefold()
                edge = canonical_edge(child_table, str(from_column), str(parent_table), str(to_column))
                table_pair = tuple(sorted((child_key, parent_key)))
                pair_edges[table_pair].add(edge)
                grouped_rows[(child_key, parent_key, int(constraint_id))].append((int(sequence), (
                    child_key, str(from_column).casefold(), parent_key, str(to_column).casefold()
                )))
    finally:
        connection.close()
    if denied_actions:
        raise PermissionError("sqlite_authorizer_denied_unexpected_operation")

    signatures: dict[tuple[str, str], set[tuple[tuple[str, str, str, str], ...]]] = defaultdict(set)
    group_count = 0
    for (child, parent, _constraint_id), rows in grouped_rows.items():
        table_pair = tuple(sorted((child, parent)))
        signature = tuple(edge for _seq, edge in sorted(rows, key=lambda item: item[0]))
        if signature:
            signatures[table_pair].add(signature)
            group_count += 1
    return {
        "pair_edges": pair_edges,
        "signatures": signatures,
        "pragma_count": pragma_count,
        "fk_row_count": fk_row_count,
        "unqualified_row_count": unqualified_row_count,
        "constraint_group_count": group_count,
        "denied_action_count": len(denied_actions),
    }


def summarize_selected(candidates: list[dict], db_paths: dict[str, Path], anon_db: dict[str, str]) -> tuple[list[dict], dict]:
    tables_by_db: dict[str, set[str]] = defaultdict(set)
    candidate_pairs_by_db: dict[str, dict[tuple[str, str], set[tuple[str, str, str, str]]]] = defaultdict(dict)
    for item in candidates:
        pair = tuple(item["table_pair"])
        tables_by_db[item["db_id"]].update(item["table_names"])
        candidate_pairs_by_db[item["db_id"]][pair] = {tuple(edge) for edge in item["metadata_edges"]}

    before_hashes: dict[str, str] = {}
    after_hashes: dict[str, str] = {}
    sqlite_by_db: dict[str, dict] = {}
    for db_id in sorted(tables_by_db):
        path = db_paths[db_id]
        before_hashes[db_id] = sha256_file(path)
        result = read_pragmas_for_database(path, tables_by_db[db_id])
        after_hashes[db_id] = sha256_file(path)
        if before_hashes[db_id] != after_hashes[db_id]:
            raise RuntimeError("sqlite_database_hash_changed")
        sqlite_by_db[db_id] = result

    evidence: list[dict] = []
    alignment_counts: Counter[str] = Counter()
    signature_histogram: Counter[int] = Counter()
    eligible_by_anon: Counter[str] = Counter()
    unique_groups_by_anon: dict[str, set[tuple]] = defaultdict(set)
    for item in candidates:
        db_id = item["db_id"]
        pair = tuple(item["table_pair"])
        metadata = {tuple(edge) for edge in item["metadata_edges"]}
        sqlite_data = sqlite_by_db[db_id]
        actual = set(sqlite_data["pair_edges"].get(pair, set()))
        exact = metadata == actual
        signatures = sqlite_data["signatures"].get(pair, set()) if exact else set()
        signature_count = len(signatures)
        signature_histogram[signature_count] += 1
        alignment_counts["exact" if exact else "mismatch"] += 1
        if exact and signature_count >= 2:
            eligible_by_anon[anon_db[db_id]] += 1
        for signature in signatures:
            unique_groups_by_anon[anon_db[db_id]].add((pair, signature))
        evidence.append({
            "candidate_id_sha256": candidate_key_hash(item),
            "anonymous_database": anon_db[db_id],
            "question_index_private": item["question_index"],
            "question_key_hash_private": item["question_key_hash"],
            "database_id_private": db_id,
            "table_pair_private": item["table_names"],
            "metadata_edge_count": len(metadata),
            "pragma_edge_count": len(actual),
            "metadata_pragma_exact": exact,
            "distinct_constraint_signature_count": signature_count,
            "metadata_edges_private": sorted(metadata),
            "pragma_edges_private": sorted(actual),
            "constraint_signatures_private": [list(signature) for signature in sorted(signatures)],
            "database_sha256_before": before_hashes[db_id],
            "database_sha256_after": after_hashes[db_id],
        })
    summary = {
        "database_count": len(sqlite_by_db),
        "pragma_call_count": sum(row["pragma_count"] for row in sqlite_by_db.values()),
        "pragma_fk_row_count": sum(row["fk_row_count"] for row in sqlite_by_db.values()),
        "pragma_unqualified_row_count": sum(row["unqualified_row_count"] for row in sqlite_by_db.values()),
        "constraint_group_occurrences": sum(row["constraint_group_count"] for row in sqlite_by_db.values()),
        "sqlite_authorizer_denied_unexpected_operations": sum(row["denied_action_count"] for row in sqlite_by_db.values()),
        "metadata_pragma_alignment": dict(sorted(alignment_counts.items())),
        "distinct_constraint_signature_count_histogram": {
            str(key): value for key, value in sorted(signature_histogram.items())
        },
        "eligible_exact_multi_constraint_units": sum(eligible_by_anon.values()),
        "eligible_units_by_anonymous_database": dict(sorted(eligible_by_anon.items())),
        "unique_constraint_signatures_by_anonymous_database": {
            key: len(value) for key, value in sorted(unique_groups_by_anon.items())
        },
        "database_hash_changes": sum(before_hashes[key] != after_hashes[key] for key in before_hashes),
    }
    return evidence, summary


def save_private(output_dir: Path, summary: dict, evidence: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_dir.chmod(0o700)
    for filename, value in (("aggregate_summary.json", summary), ("candidate_evidence_private.json", evidence)):
        path = output_dir / filename
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o600)


def run(args: argparse.Namespace) -> dict:
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = args.repo_root.resolve()
    if capacity.current_commit(root) != args.expected_commit:
        raise ValueError("source_commit_mismatch")
    if config["experiment_id"] != EXPERIMENT_ID or config["repository"] != "https://github.com/bArtyom/gfm-rag":
        raise ValueError("experiment_config_mismatch")
    if sha256_file(config_path) != args.expected_config_sha256:
        raise ValueError("config_hash_mismatch")
    if sha256_file(Path(__file__).resolve()) != config["implementation"]["runner_sha256"]:
        raise ValueError("runner_hash_mismatch")
    if sha256_file(Path(capacity.__file__).resolve()) != EXPECTED_CAPACITY_RUNNER_SHA256:
        raise ValueError("capacity_runner_hash_mismatch")
    aggregate_path = args.capacity_aggregate.resolve()
    if sha256_file(aggregate_path) != EXPECTED_CAPACITY_AGGREGATE_SHA256:
        raise ValueError("capacity_aggregate_hash_mismatch")
    if capacity.sqlglot.__version__ != EXPECTED_SQLGLOT:
        raise ValueError("sqlglot_version_mismatch")
    if platform.python_version() != "3.12.14":
        raise ValueError("python_version_mismatch")
    if sqlite3.sqlite_version != config["environment"]["sqlite"]:
        raise ValueError("sqlite_version_mismatch")
    if aggregate_path != Path(config["capacity_stage"]["aggregate_path"]).resolve():
        raise ValueError("capacity_aggregate_path_mismatch")
    if args.mode not in ("smoke", "full"):
        raise ValueError("mode_invalid")
    if args.run_id != config["runs"][args.mode]:
        raise ValueError("run_id_mismatch")
    if args.output_dir.exists():
        raise ValueError("output_directory_already_exists")
    if args.mode == "full":
        if args.smoke_summary is None or not args.smoke_summary.is_file():
            raise ValueError("smoke_summary_required_for_full")

    started = time.perf_counter()
    cpu_started = time.process_time()
    started_at = datetime.now(timezone.utc).isoformat()
    candidates, anon_db, inputs = reconstruct_candidates(args, config)
    smoke_hashes = set(inputs["smoke_candidate_id_hashes"])
    if args.mode == "smoke":
        selected = [candidate for candidate in candidates if candidate_key_hash(candidate) in smoke_hashes]
    else:
        prior = json.loads(args.smoke_summary.read_text(encoding="utf-8"))
        required_input_hashes = {
            "train_json": inputs["train_json_sha256"],
            "train_schema": inputs["train_schema_sha256"],
            "dev_schema": inputs["dev_schema_sha256"],
            "capacity_stage_aggregate": EXPECTED_CAPACITY_AGGREGATE_SHA256,
            "capacity_stage_runner": EXPECTED_CAPACITY_RUNNER_SHA256,
        }
        prior_input_hashes = prior.get("input_hashes", {})
        if (prior.get("run_id") != config["runs"]["smoke"]
                or prior.get("decision") != "SMOKE_PASS"
                or prior.get("source_commit") != args.expected_commit
                or prior.get("config_sha256") != args.expected_config_sha256
                or prior.get("runner_sha256") != config["implementation"]["runner_sha256"]
                or any(prior_input_hashes.get(key) != value for key, value in required_input_hashes.items())
                or set(prior.get("smoke_candidate_id_hashes", [])) != smoke_hashes):
            raise ValueError("smoke_receipt_mismatch")
        selected = [candidate for candidate in candidates if candidate_key_hash(candidate) not in smoke_hashes]

    database_root = args.database_root.resolve()
    expected_root = Path(config["dataset"]["database_root"]).resolve()
    if database_root != expected_root:
        raise ValueError("database_root_mismatch")
    db_paths = {db_id: find_database_file(database_root, db_id) for db_id in {row["db_id"] for row in selected}}
    evidence, pragma_summary = summarize_selected(selected, db_paths, anon_db)

    wall_seconds = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_started
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > MAX_WALL_SECONDS or cpu_seconds > MAX_CPU_SECONDS or rss_gib > MAX_RSS_GIB:
        raise RuntimeError("resource_limit_exceeded")

    if args.mode == "smoke":
        all_complete = len(evidence) == SMOKE_COUNT and pragma_summary["pragma_call_count"] > 0
        any_group = pragma_summary["constraint_group_occurrences"] > 0
        no_hash_change = pragma_summary["database_hash_changes"] == 0
        decision = "SMOKE_PASS" if all_complete and any_group and no_hash_change else "STOP_SMOKE_GATE"
    else:
        enough_units = pragma_summary["eligible_exact_multi_constraint_units"] >= MIN_UNITS
        enough_dbs = len(pragma_summary["eligible_units_by_anonymous_database"]) >= MIN_DATABASES
        no_hash_change = pragma_summary["database_hash_changes"] == 0
        decision = "CAPACITY_SUFFICIENT_FOR_MODEL_REVIEW_PREREGISTRATION" if enough_units and enough_dbs and no_hash_change else "STOP_INSUFFICIENT_EXACT_CONSTRAINT_CAPACITY"

    summary = {
        "experiment_id": EXPERIMENT_ID,
        "capacity_stage_experiment_id": CAPACITY_ID,
        "run_id": args.run_id,
        "amendment_id": config.get("amendment_id"),
        "mode": args.mode,
        "status": "COMPLETED",
        "decision": decision,
        "started_at_utc": started_at,
        "source_commit": capacity.current_commit(root),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(config_path),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlglot_version": capacity.sqlglot.__version__,
        "input_hashes": {
            "train_json": inputs["train_json_sha256"],
            "train_schema": inputs["train_schema_sha256"],
            "dev_schema": inputs["dev_schema_sha256"],
            "capacity_stage_aggregate": EXPECTED_CAPACITY_AGGREGATE_SHA256,
            "capacity_stage_runner": EXPECTED_CAPACITY_RUNNER_SHA256,
        },
        "split_and_reconstruction": {
            "train_database_count": inputs["train_database_count"],
            "dev_database_count": inputs["dev_database_count"],
            "train_dev_database_overlap": inputs["overlap_database_count"],
            "train_questions": inputs["question_count"],
            "capacity_stage_smoke_questions_excluded": inputs["capacity_stage_smoke_questions_excluded"],
            "train_sql_parse_success": inputs["sql_parse_success"],
            "train_sql_parse_failures": inputs["sql_parse_failures"],
            "train_scope_failures": inputs["scope_failures"],
            "capacity_candidate_units": inputs["candidate_unit_count"],
            "capacity_units_by_anonymous_database": inputs["candidate_units_by_anonymous_database"],
            "units_in_this_run": len(selected),
            "smoke_units_excluded_from_full": args.mode == "full",
        },
        "sqlite_constraint_audit": pragma_summary,
        "gates": {
            "sqlite_mode": "mode=ro&immutable=1",
            "authorizer_allowed_operation": "PRAGMA foreign_key_list for candidate-table allowlist only",
            "query_only": True,
            "business_rows_read": False,
            "gold_or_candidate_sql_executed": False,
            "full_minimum_exact_multi_constraint_units": MIN_UNITS,
            "full_minimum_anonymous_databases": MIN_DATABASES,
        },
        "smoke_candidate_id_hashes": inputs["smoke_candidate_id_hashes"],
        "resources": {
            "device": "cpu",
            "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6),
            "peak_rss_gib": round(rss_gib, 6),
            "gpu_seconds": 0,
            "model_calls": 0,
            "external_api_calls": 0,
        },
        "privacy": {
            "public_row_level_data": False,
            "question_text_or_sql_written": False,
            "database_ids_or_table_names_written_in_public_summary": False,
            "candidate_evidence_saved_private_only": True,
        },
        "interpretation": "Exact PRAGMA-to-metadata FK column-pair alignment and distinct complete constraint signatures define capacity for a separately registered local-model review; no semantic label or ranker result is produced here.",
    }
    save_private(args.output_dir, summary, evidence)
    return summary


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--train-tables", type=Path, required=True)
    parser.add_argument("--dev-tables", type=Path, required=True)
    parser.add_argument("--database-root", type=Path, required=True)
    parser.add_argument("--capacity-aggregate", type=Path, required=True)
    parser.add_argument("--smoke-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args)
    except Exception as error:
        if not args.output_dir.exists():
            args.output_dir.mkdir(parents=True, mode=0o700)
            args.output_dir.chmod(0o700)
            receipt = {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "mode": args.mode,
                "status": "STOPPED",
                "reason_class": type(error).__name__,
                "reason_code": str(error) if str(error).isidentifier() else "unclassified_error",
                "source_commit": capacity.current_commit(args.repo_root) if args.repo_root.is_dir() else None,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "privacy": "No question text, SQL, database identifiers, or table names serialized.",
            }
            path = args.output_dir / "failure_receipt.json"
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            path.chmod(0o600)
        print(json.dumps({"run_id": args.run_id, "status": "STOPPED", "reason_class": type(error).__name__}, sort_keys=True))
        return 2
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "decision": summary["decision"],
        "units_in_this_run": summary["split_and_reconstruction"]["units_in_this_run"],
        "sqlite_constraint_audit": summary["sqlite_constraint_audit"],
        "resources": summary["resources"],
        "summary_path": str(args.output_dir / "aggregate_summary.json"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
