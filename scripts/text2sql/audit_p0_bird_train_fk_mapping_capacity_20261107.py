#!/usr/bin/env python3
"""Metadata-only capacity audit for exploratory BIRD-train FK mapping review."""
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
import subprocess
import sys
import time

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import traverse_scope

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import audit_minidev_sql_fk_labels as sql_helpers  # noqa: E402

EXPERIMENT_ID = "p0_bird_train_fk_mapping_capacity_20261107_01"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_QUESTIONS = 9428
EXPECTED_TRAIN_DATABASES = 69
EXPECTED_DEV_DATABASES = 11
SMOKE_COUNT = 5
MIN_PARSE_RATE = 0.98
MIN_CAPACITY_UNITS = 60
MIN_CAPACITY_DATABASES = 4
MAX_WALL_SECONDS = 600.0
MAX_CPU_SECONDS = 300.0
MAX_RSS_GIB = 4.0


class ScopeAuditError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def current_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def unwrap_column(node: exp.Expression | None) -> exp.Column | None:
    while node is not None:
        if isinstance(node, exp.Column):
            return node
        if isinstance(node, (exp.Paren, exp.Cast, exp.TryCast)):
            node = node.this
        else:
            return None
    return None


def schema_columns(schema: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    names = schema["table_names_original"]
    for table_index, column_name in schema["column_names_original"]:
        table_index = int(table_index)
        if table_index >= 0 and str(column_name) != "*":
            result[str(names[table_index])].append(str(column_name))
    return result


def candidate_pairs(schema: dict) -> dict[tuple[str, str], set[tuple[str, str, str, str]]]:
    tables = schema["table_names_original"]
    columns = schema["column_names_original"]
    result: dict[tuple[str, str], set[tuple[str, str, str, str]]] = defaultdict(set)
    for raw_left, raw_right in schema.get("foreign_keys", []):
        left_index, right_index = int(raw_left), int(raw_right)
        if not (0 <= left_index < len(columns) and 0 <= right_index < len(columns)):
            raise ValueError("foreign_key_column_index_out_of_range")
        left_table_index, left_column = columns[left_index]
        right_table_index, right_column = columns[right_index]
        left_table_index, right_table_index = int(left_table_index), int(right_table_index)
        if left_table_index < 0 or right_table_index < 0:
            raise ValueError("foreign_key_points_to_wildcard")
        left_table = str(tables[left_table_index])
        right_table = str(tables[right_table_index])
        table_pair = tuple(sorted((left_table.casefold(), right_table.casefold())))
        endpoints = sorted(
            ((left_table, str(left_column)), (right_table, str(right_column))),
            key=lambda item: (item[0].casefold(), item[1].casefold()),
        )
        identity = (endpoints[0][0], endpoints[0][1], endpoints[1][0], endpoints[1][1])
        result[table_pair].add(identity)
    return result


def query_join_pairs(sql: str, schema: dict) -> tuple[set[tuple[str, str]], int, int, int, int]:
    parsed = [node for node in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE) if node is not None]
    if len(parsed) != 1:
        raise ValueError("statement_count")
    names = {str(name).casefold(): str(name) for name in schema["table_names_original"]}
    columns_by_table = {
        table.casefold(): {column.casefold(): column for column in values}
        for table, values in schema_columns(schema).items()
    }
    join_pairs: set[tuple[str, str]] = set()
    equality_count = qualified_count = resolved_count = using_count = 0
    try:
        for scope in traverse_scope(parsed[0]):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = sql_helpers._scope_aliases(scope, names)
            for join in scope.expression.args.get("joins") or []:
                on = join.args.get("on")
                if join.args.get("using"):
                    using_count += 1
                    continue
                if on is None:
                    continue
                for equality in on.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not join:
                        continue
                    equality_count += 1
                    left = unwrap_column(equality.this)
                    right = unwrap_column(equality.expression)
                    if left is None or right is None or not left.table or not right.table:
                        continue
                    qualified_count += 1
                    left_table = sql_helpers._resolve_column(left, aliases, columns_by_table)
                    right_table = sql_helpers._resolve_column(right, aliases, columns_by_table)
                    if left_table is None or right_table is None:
                        continue
                    if left_table[0].casefold() == right_table[0].casefold():
                        continue
                    resolved_count += 1
                    join_pairs.add(tuple(sorted((left_table[0].casefold(), right_table[0].casefold()))))
    except Exception as error:
        raise ScopeAuditError(type(error).__name__) from None
    return join_pairs, equality_count, qualified_count, resolved_count, using_count


def read_schema_file(path: Path) -> tuple[list[dict], str]:
    digest = sha256_file(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("schema_file_not_list")
    return value, digest


def save_summary(output_dir: Path, summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_dir.chmod(0o700)
    target = output_dir / "aggregate_summary.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)


def run(args: argparse.Namespace) -> dict:
    root = args.repo_root.resolve()
    if current_commit(root) != args.expected_commit:
        raise ValueError("source_commit_mismatch")
    expected_suffix = "smoke_001" if args.mode == "smoke" else "full_001"
    if args.run_id != f"{EXPERIMENT_ID}_{expected_suffix}":
        raise ValueError("run_id_mismatch")
    if sqlglot.__version__ != EXPECTED_SQLGLOT:
        raise ValueError("sqlglot_version_mismatch")
    if os.environ.get("CUDA_VISIBLE_DEVICES", "") != "":
        raise ValueError("cpu_only_environment_required")
    if args.output_dir.exists():
        raise ValueError("output_directory_already_exists")

    started, cpu_started = time.perf_counter(), time.process_time()
    started_at = datetime.now(timezone.utc).isoformat()

    # Split isolation is verified from schema metadata before opening train.json.
    train_schemas, train_schema_hash = read_schema_file(args.train_tables)
    dev_schemas, dev_schema_hash = read_schema_file(args.dev_tables)
    train_db_ids = [str(row["db_id"]) for row in train_schemas]
    dev_db_ids = [str(row["db_id"]) for row in dev_schemas]
    if len(set(train_db_ids)) != len(train_db_ids) or len(set(dev_db_ids)) != len(dev_db_ids):
        raise ValueError("duplicate_schema_database_id")
    overlap = set(train_db_ids) & set(dev_db_ids)
    if overlap:
        summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "COMPLETED",
            "decision": "STOP_DATABASE_SPLIT_OVERLAP",
            "started_at_utc": started_at,
            "source_commit": current_commit(root),
            "train_schema_sha256": train_schema_hash,
            "dev_schema_sha256": dev_schema_hash,
            "train_schema_database_count": len(train_db_ids),
            "dev_schema_database_count": len(dev_db_ids),
            "overlap_database_count": len(overlap),
            "train_question_file_opened": False,
            "sql_parsing_performed": False,
            "privacy": "No database identifiers or row-level data serialized.",
        }
        save_summary(args.output_dir, summary)
        return summary
    if len(train_db_ids) != EXPECTED_TRAIN_DATABASES or len(dev_db_ids) != EXPECTED_DEV_DATABASES:
        raise ValueError("schema_database_count_mismatch")

    train_hash = sha256_file(args.train_json)
    train_rows = json.loads(args.train_json.read_text(encoding="utf-8"))
    if not isinstance(train_rows, list) or len(train_rows) != EXPECTED_QUESTIONS:
        raise ValueError("train_question_count_mismatch")
    schemas = {str(row["db_id"]): row for row in train_schemas}
    indexed = []
    for index, row in enumerate(train_rows):
        db_id = str(row["db_id"])
        if db_id not in schemas:
            raise ValueError("train_question_schema_missing")
        question_key = str(row.get("question_id", index))
        indexed.append({
            "db_id": db_id,
            "question_index": index,
            "question_key_hash": stable_hash(EXPERIMENT_ID, db_id, question_key),
            "smoke_key": stable_hash(EXPERIMENT_ID, db_id, question_key),
            "sql": row.get("SQL"),
        })
    smoke_indices = {
        row["question_index"] for row in sorted(indexed, key=lambda item: item["smoke_key"])[:SMOKE_COUNT]
    }
    selected = [row for row in indexed if (row["question_index"] in smoke_indices) == (args.mode == "smoke")]
    if args.mode == "full":
        if args.smoke_summary is None or not args.smoke_summary.is_file():
            raise ValueError("smoke_summary_required_for_full")
        prior = json.loads(args.smoke_summary.read_text(encoding="utf-8"))
        if (prior.get("run_id") != f"{EXPERIMENT_ID}_smoke_001"
                or prior.get("decision") != "SMOKE_PASS"
                or prior.get("source_commit") != args.expected_commit
                or prior.get("train_json_sha256") != train_hash
                or prior.get("train_schema_sha256") != train_schema_hash
                or prior.get("dev_schema_sha256") != dev_schema_hash):
            raise ValueError("smoke_receipt_mismatch")

    parse_failures: Counter[str] = Counter()
    scope_failures: Counter[str] = Counter()
    multiplicity: Counter[int] = Counter()
    per_db: dict[str, Counter[str]] = defaultdict(Counter)
    eligible: list[tuple[str, str, tuple[str, str], int]] = []
    join_questions = parsed_questions = 0
    on_equalities = qualified_equalities = resolved_equalities = using_joins = 0
    unresolved_fk_pairs = single_fk_pairs = ambiguous_pair_occurrences = 0

    for row in selected:
        schema = schemas[row["db_id"]]
        try:
            pairs, eq_count, qualified_count, resolved_count, using_count = query_join_pairs(str(row["sql"] or ""), schema)
        except ScopeAuditError as error:
            scope_failures[str(error)] += 1
            continue
        except Exception as error:
            parse_failures[type(error).__name__] += 1
            continue
        parsed_questions += 1
        on_equalities += eq_count
        qualified_equalities += qualified_count
        resolved_equalities += resolved_count
        using_joins += using_count
        if eq_count:
            join_questions += 1
        candidates_by_pair = candidate_pairs(schema)
        eligible_pairs = []
        for pair in sorted(pairs):
            candidates = candidates_by_pair.get(pair, set())
            multiplicity[len(candidates)] += 1
            if len(candidates) == 0:
                unresolved_fk_pairs += 1
            elif len(candidates) == 1:
                single_fk_pairs += 1
            else:
                ambiguous_pair_occurrences += 1
                eligible_pairs.append((pair, len(candidates)))
        if eligible_pairs:
            eligible_pairs.sort(key=lambda item: stable_hash(
                EXPERIMENT_ID, row["db_id"], row["question_key_hash"], item[0][0], item[0][1]
            ))
            pair, candidate_count = eligible_pairs[0]
            eligible.append((row["db_id"], row["question_key_hash"], pair, candidate_count))
            per_db[row["db_id"]]["eligible_question_units"] += 1
            per_db[row["db_id"]]["ambiguous_table_pairs"] += len(eligible_pairs)

    parse_rate = parsed_questions / max(1, len(selected))
    db_ids = sorted({row[0] for row in eligible}, key=lambda item: stable_hash(EXPERIMENT_ID, "anon_db", item))
    anonymous = {db: f"db_{index:02d}" for index, db in enumerate(db_ids, start=1)}
    db_hist = Counter(anonymous[db] for db, *_ in eligible)
    if args.mode == "smoke":
        decision = "SMOKE_PASS" if parsed_questions == SMOKE_COUNT and not scope_failures else "STOP_SMOKE_GATE"
    elif scope_failures or parse_rate < MIN_PARSE_RATE:
        decision = "STOP_PARSER_OR_SCOPE_GATE"
    elif len(eligible) >= MIN_CAPACITY_UNITS and len(db_hist) >= MIN_CAPACITY_DATABASES:
        decision = "CAPACITY_SUFFICIENT_FOR_CONSTRAINT_IDENTITY_STAGE"
    else:
        decision = "STOP_INSUFFICIENT_CAPACITY"

    wall_seconds = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_started
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > MAX_WALL_SECONDS or cpu_seconds > MAX_CPU_SECONDS or rss_gib > MAX_RSS_GIB:
        raise RuntimeError("resource_limit_exceeded")
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "status": "COMPLETED",
        "decision": decision,
        "mode": args.mode,
        "started_at_utc": started_at,
        "source_commit": current_commit(root),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "python_version": platform.python_version(),
        "sqlglot_version": sqlglot.__version__,
        "train_json_sha256": train_hash,
        "train_schema_sha256": train_schema_hash,
        "dev_schema_sha256": dev_schema_hash,
        "split_isolation": {
            "train_database_count": len(train_db_ids),
            "dev_database_count": len(dev_db_ids),
            "overlap_database_count": 0,
            "train_json_opened_after_zero_overlap": True,
        },
        "counts": {
            "questions_in_run": len(selected),
            "join_questions_with_explicit_on": join_questions,
            "sql_parse_success": parsed_questions,
            "sql_parse_failures_by_exception_class": dict(sorted(parse_failures.items())),
            "scope_analysis_failures_by_exception_class": dict(sorted(scope_failures.items())),
            "join_on_equalities": on_equalities,
            "qualified_join_on_equalities": qualified_equalities,
            "resolved_cross_table_equalities": resolved_equalities,
            "unresolved_qualified_equalities": qualified_equalities - resolved_equalities,
            "using_join_count_excluded": using_joins,
            "resolved_table_pairs_without_fk_rows": unresolved_fk_pairs,
            "resolved_table_pairs_with_one_fk_row": single_fk_pairs,
            "ambiguous_pair_occurrences_by_declared_fk_column_pairs": ambiguous_pair_occurrences,
            "one_pair_per_eligible_question_units": len(eligible),
            "anonymous_database_count": len(db_hist),
            "eligible_units_by_anonymous_database": dict(sorted(db_hist.items())),
            "declared_fk_column_pair_multiplicity_histogram": {
                str(key): value for key, value in sorted(multiplicity.items())
            },
        },
        "gates": {
            "train_dev_database_overlap_minimum": 0,
            "parse_rate_minimum": MIN_PARSE_RATE,
            "parse_rate_observed": parse_rate,
            "scope_errors_allowed": 0,
            "full_capacity_units_minimum": MIN_CAPACITY_UNITS,
            "full_anonymous_databases_minimum": MIN_CAPACITY_DATABASES,
        },
        "resources": {
            "device": "cpu",
            "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6),
            "peak_rss_gib": round(rss_gib, 6),
            "max_threads": 8,
            "gpu_seconds": 0,
            "model_calls": 0,
            "api_calls": 0,
            "sqlite_connections": 0,
            "sql_execution_calls": 0,
        },
        "privacy": {
            "question_ids_written": False,
            "question_text_written": False,
            "sql_written": False,
            "database_ids_written": False,
            "table_or_column_names_written": False,
            "fk_mapping_identity_written": False,
        },
        "interpretation": "Declared FK column-pair multiplicity is a capacity upper bound; it does not identify whole constraints or independent semantic mappings.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    result_path = args.output_dir / "aggregate_summary.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path.chmod(0o600)
    return summary


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--train-tables", type=Path, required=True)
    parser.add_argument("--dev-tables", type=Path, required=True)
    parser.add_argument("--smoke-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args)
    except Exception as error:
        output_dir = args.output_dir
        if not output_dir.exists():
            output_dir.mkdir(parents=True, mode=0o700)
            output_dir.chmod(0o700)
            receipt = {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "status": "STOPPED",
                "reason_class": type(error).__name__,
                "reason_code": str(error) if str(error).isidentifier() else "unclassified_error",
                "source_commit": current_commit(args.repo_root) if args.repo_root.is_dir() else None,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "privacy": "No SQL, question text, IDs, or schema names serialized.",
            }
            receipt_path = output_dir / "failure_receipt.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            receipt_path.chmod(0o600)
        print(json.dumps({"run_id": args.run_id, "status": "STOPPED", "reason_class": type(error).__name__}, sort_keys=True))
        return 2
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "decision": summary["decision"],
        "counts": summary.get("counts", {}),
        "resources": summary.get("resources", {}),
        "summary_path": str(args.output_dir / "aggregate_summary.json"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
