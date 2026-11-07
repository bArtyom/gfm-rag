#!/usr/bin/env python3
"""Anonymous capacity audit for Spider 1.0 test FK-mapping candidates."""
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
import zipfile

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import traverse_scope

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import audit_minidev_sql_fk_labels as sql_helpers  # noqa: E402

EXPERIMENT_ID = "p0_spider_fk_mapping_candidate_capacity_20261107_01"
EXPECTED_ARCHIVE_SHA256 = "00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b"
EXPECTED_SQLGLOT = "28.0.0"
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


def source_commit(root: Path) -> str:
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
        left_table, right_table = str(tables[left_table_index]), str(tables[right_table_index])
        pair = tuple(sorted((left_table.casefold(), right_table.casefold())))
        endpoint_left = (left_table, str(left_column))
        endpoint_right = (right_table, str(right_column))
        first, second = sorted((endpoint_left, endpoint_right), key=lambda item: (item[0].casefold(), item[1].casefold()))
        identity = (first[0], first[1], second[0], second[1])
        result[pair].add(identity)
    return result


def query_join_pairs(sql: str, schema: dict) -> tuple[set[tuple[str, str]], int, int, int, int]:
    parsed = [node for node in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE) if node is not None]
    if len(parsed) != 1:
        raise ValueError("statement_count")
    names = {str(name).casefold(): str(name) for name in schema["table_names_original"]}
    known_columns = schema_columns(schema)
    columns_by_table = {
        table.casefold(): {column.casefold(): column for column in values}
        for table, values in known_columns.items()
    }
    join_pairs: set[tuple[str, str]] = set()
    equality_count = 0
    qualified_count = 0
    resolved_count = 0
    using_join_count = 0
    try:
        for scope in traverse_scope(parsed[0]):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = sql_helpers._scope_aliases(scope, names)
            for join in scope.expression.args.get("joins") or []:
                on = join.args.get("on")
                if join.args.get("using"):
                    using_join_count += 1
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
                    if left_table is None or right_table is None or left_table[0].casefold() == right_table[0].casefold():
                        continue
                    resolved_count += 1
                    join_pairs.add(tuple(sorted((left_table[0].casefold(), right_table[0].casefold()))))
    except Exception as error:  # aggregate only the exception class; never persist SQL text.
        raise ScopeAuditError(type(error).__name__) from None
    return join_pairs, equality_count, qualified_count, resolved_count, using_join_count


def load_archive(archive: Path) -> tuple[list[dict], list[tuple[str, str]], dict[str, dict]]:
    with zipfile.ZipFile(archive) as source:
        questions = json.loads(source.read("spider_data/test.json"))
        tables = json.loads(source.read("spider_data/test_tables.json"))
        raw_sql = source.read("spider_data/test_gold.sql").decode("utf-8")
    lines = [line for line in raw_sql.splitlines() if line.strip()]
    gold_rows: list[tuple[str, str]] = []
    for line in lines:
        pieces = line.split("\t")
        if len(pieces) != 2:
            raise ValueError("test_gold_sql_format_mismatch")
        gold_rows.append((pieces[0].strip(), pieces[1].strip()))
    if len(questions) != len(gold_rows):
        raise ValueError("test_question_gold_sql_count_mismatch")
    schemas = {str(row["db_id"]): row for row in tables}
    if len(schemas) != len(tables):
        raise ValueError("duplicate_test_schema_db_id")
    for question, (_, gold_db_id) in zip(questions, gold_rows):
        if str(question["db_id"]) != gold_db_id:
            raise ValueError("test_question_gold_database_mismatch")
    return questions, gold_rows, schemas


def summarize(rows: list[dict], schemas: dict[str, dict], split: str, archive_hash: str,
              root: Path, run_id: str, started: float, cpu_started: float,
              output_dir: Path) -> dict:
    parse_failures: Counter[str] = Counter()
    scope_failures: Counter[str] = Counter()
    multiplicity: Counter[int] = Counter()
    per_db: dict[str, Counter[str]] = defaultdict(Counter)
    eligible: list[tuple[str, str, tuple[str, str], int]] = []
    join_questions = 0
    parsed_questions = 0
    on_equalities = 0
    qualified_equalities = 0
    resolved_equalities = 0
    using_joins = 0
    ambiguous_pairs = 0
    pair_no_fk = 0
    pair_single_fk = 0

    for row in rows:
        db_id, question_index = row["db_id"], row["question_index"]
        schema = schemas.get(db_id)
        if schema is None:
            raise ValueError("test_schema_missing")
        fk_candidates = candidate_pairs(schema)
        try:
            pairs, eq_count, qualified_count, resolved_count, using_count = query_join_pairs(row["sql"], schema)
        except ScopeAuditError as error:
            scope_failures[str(error)] += 1
            continue
        except Exception as error:  # aggregate the class only; never persist SQL text.
            parse_failures[type(error).__name__] += 1
            continue
        parsed_questions += 1
        on_equalities += eq_count
        qualified_equalities += qualified_count
        resolved_equalities += resolved_count
        using_joins += using_count
        if eq_count:
            join_questions += 1
        eligible_pairs = []
        for pair in sorted(pairs):
            candidates = fk_candidates.get(pair, set())
            multiplicity[len(candidates)] += 1
            if len(candidates) == 0:
                pair_no_fk += 1
            elif len(candidates) == 1:
                pair_single_fk += 1
            if len(candidates) >= 2:
                ambiguous_pairs += 1
                eligible_pairs.append((pair, len(candidates)))
        if eligible_pairs:
            eligible_pairs.sort(key=lambda item: stable_hash(
                EXPERIMENT_ID, db_id, str(question_index), item[0][0], item[0][1]
            ))
            pair, candidate_count = eligible_pairs[0]
            eligible.append((db_id, str(question_index), pair, candidate_count))
            per_db[db_id]["eligible_question_units"] += 1
            per_db[db_id]["ambiguous_table_pairs"] += len(eligible_pairs)

    parse_rate = parsed_questions / max(1, len(rows))
    db_ids = sorted({row[0] for row in eligible}, key=lambda db: stable_hash(EXPERIMENT_ID, "anon_db", db))
    anonymous = {db: f"db_{index:02d}" for index, db in enumerate(db_ids, start=1)}
    db_hist = Counter(anonymous[db] for db, *_ in eligible)
    eligible_count = len(eligible)
    db_count = len(db_hist)
    if split == "smoke":
        decision = "SMOKE_ONLY_NO_CAPACITY_DECISION"
    elif parse_rate < MIN_PARSE_RATE or scope_failures:
        decision = "STOP_PARSER_OR_SCOPE_GATE"
    elif eligible_count >= MIN_CAPACITY_UNITS and db_count >= MIN_CAPACITY_DATABASES:
        decision = "CAPACITY_SUFFICIENT_FOR_MODEL_PROXY_REPLICATION"
    else:
        decision = "STOP_INSUFFICIENT_CAPACITY"

    wall_seconds = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_started
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > MAX_WALL_SECONDS or cpu_seconds > MAX_CPU_SECONDS or rss_gib > MAX_RSS_GIB:
        raise RuntimeError("resource_limit_exceeded")
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_dir.chmod(0o700)
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "status": "COMPLETED",
        "split": split,
        "decision": decision,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(root),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "dataset_archive_sha256": archive_hash,
        "python_version": platform.python_version(),
        "sqlglot_version": sqlglot.__version__,
        "counts": {
            "questions_in_split": len(rows),
            "join_questions_with_explicit_on": join_questions,
            "sql_parse_success": parsed_questions,
            "sql_parse_failures_by_exception_class": dict(sorted(parse_failures.items())),
            "scope_analysis_failures_by_exception_class": dict(sorted(scope_failures.items())),
            "join_on_equalities": on_equalities,
            "qualified_join_on_equalities": qualified_equalities,
            "unqualified_join_on_equalities": on_equalities - qualified_equalities,
            "resolved_cross_table_equalities": resolved_equalities,
            "unresolved_qualified_equalities": qualified_equalities - resolved_equalities,
            "resolved_qualified_equality_rate": resolved_equalities / max(1, qualified_equalities),
            "using_join_count_excluded": using_joins,
            "resolved_join_table_pairs_without_declared_fk": pair_no_fk,
            "resolved_join_table_pairs_with_one_declared_mapping": pair_single_fk,
            "ambiguous_question_table_pairs": ambiguous_pairs,
            "one_pair_per_eligible_question_units": eligible_count,
            "anonymous_database_count": db_count,
            "eligible_units_by_anonymous_database": dict(sorted(db_hist.items())),
            "declared_mapping_multiplicity_histogram": {str(key): value for key, value in sorted(multiplicity.items())},
        },
        "gates": {
            "sql_parse_rate_minimum": MIN_PARSE_RATE,
            "sql_parse_rate_observed": parse_rate,
            "scope_analysis_failures_allowed": 0,
            "eligible_units_minimum_after_smoke": MIN_CAPACITY_UNITS,
            "anonymous_database_minimum_after_smoke": MIN_CAPACITY_DATABASES,
        },
        "resources": {
            "device": "cpu",
            "wall_seconds": round(wall_seconds, 3),
            "cpu_seconds": round(cpu_seconds, 3),
            "peak_rss_gib": round(rss_gib, 3),
        },
        "privacy": "Aggregate counts only; no question, SQL, database, table, FK identity, or per-question output is serialized.",
    }
    output_file = output_dir / "aggregate_summary.json"
    output_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_file.chmod(0o600)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if source_commit(root) != args.expected_commit:
        raise ValueError("source_commit_mismatch")
    expected_suffix = "smoke_002" if args.mode == "smoke" else "full_001"
    expected_run_id = f"{EXPERIMENT_ID}_{expected_suffix}"
    if args.run_id != expected_run_id:
        raise ValueError("run_id_mismatch")
    if sqlglot.__version__ != EXPECTED_SQLGLOT:
        raise ValueError("sqlglot_version_mismatch")
    if os.environ.get("CUDA_VISIBLE_DEVICES", "") != "":
        raise ValueError("cpu_only_environment_required")
    started, cpu_started = time.perf_counter(), time.process_time()
    archive_hash = sha256_file(args.archive)
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("dataset_archive_hash_mismatch")
    questions, gold_rows, schemas = load_archive(args.archive)
    indexed = []
    for index, (question, (sql, db_id)) in enumerate(zip(questions, gold_rows)):
        indexed.append({"db_id": db_id, "question_index": index, "sql": sql,
                        "smoke_key": stable_hash(EXPERIMENT_ID, db_id, str(index))})
    smoke_indices = {row["question_index"] for row in sorted(indexed, key=lambda row: row["smoke_key"])[:SMOKE_COUNT]}
    if args.mode == "smoke":
        selected = [row for row in indexed if row["question_index"] in smoke_indices]
    else:
        selected = [row for row in indexed if row["question_index"] not in smoke_indices]
    for row in selected:
        row["split"] = args.mode
    summary = summarize(selected, schemas, args.mode, archive_hash, root, args.run_id,
                        started, cpu_started, args.output_dir)
    print(json.dumps({"run_id": args.run_id, "status": summary["status"],
                      "decision": summary["decision"], "counts": summary["counts"],
                      "resources": summary["resources"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
