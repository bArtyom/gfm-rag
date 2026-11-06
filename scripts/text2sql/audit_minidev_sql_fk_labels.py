#!/usr/bin/env python3
"""Audit Gold-SQL FK mapping labels for the pinned reviewed BIRD Mini-Dev release."""
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
from typing import Any, Iterable, Mapping

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import Scope, traverse_scope


EXPERIMENT_ID = "p0_minidev_sql_fk_mapping_rank_20261106_01"
EXPECTED_SQLGLOT = "28.0.0"
EXPECTED_ROWS = 500
EXPECTED_SMOKE_QUESTIONS = 5
EXPECTED_COMMIT = "TO_BE_FROZEN"
EXPECTED_BRANCH = "research/minidev-sql-fk-use-rank-20261106"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def smoke_digest(db_id: str, question_id: str) -> str:
    # The registered split uses direct concatenation, without separators.
    return hashlib.sha256(f"{EXPERIMENT_ID}{db_id}{question_id}".encode("utf-8")).hexdigest()


def table_pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right), key=lambda value: (value.casefold(), value)))


def _column_index(known_columns: Mapping[str, Iterable[str]]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    table_by_fold: dict[str, str] = {}
    columns_by_table_fold: dict[str, dict[str, str]] = {}
    for table, columns in known_columns.items():
        table_fold = str(table).casefold()
        require(table_fold not in table_by_fold, f"case-insensitive table collision in {table}")
        table_by_fold[table_fold] = str(table)
        column_map: dict[str, str] = {}
        for column in columns:
            column_fold = str(column).casefold()
            require(column_fold not in column_map, f"case-insensitive column collision in {table}")
            column_map[column_fold] = str(column)
        columns_by_table_fold[table_fold] = column_map
    return table_by_fold, columns_by_table_fold


def _scope_aliases(
    scope: Scope, table_by_fold: Mapping[str, str]
) -> dict[str, str | None]:
    aliases: dict[str, str | None] = {}
    reference_counts = Counter(str(alias).casefold() for alias, _ in scope.references)
    for alias, _ in scope.references:
        alias_fold = str(alias).casefold()
        if reference_counts[alias_fold] > 1:
            aliases[alias_fold] = None
            continue
        source = next(
            (
                value
                for source_alias, value in scope.sources.items()
                if str(source_alias).casefold() == alias_fold
            ),
            None,
        )
        table_name: str | None = None
        if isinstance(source, exp.Table):
            table_name = table_by_fold.get(str(source.name).casefold())
        aliases[alias_fold] = table_name
    return aliases


def _resolve_column(
    column: exp.Column,
    aliases: Mapping[str, str | None],
    columns_by_table_fold: Mapping[str, Mapping[str, str]],
) -> tuple[str, str] | None:
    qualifier = str(column.table or "").strip()
    name = str(column.name or "").strip()
    if not qualifier or not name:
        return None
    table = aliases.get(qualifier.casefold())
    if table is None:
        return None
    column_name = columns_by_table_fold.get(table.casefold(), {}).get(name.casefold())
    if column_name is None:
        return None
    return table, column_name


def _qualified_column_pair(left: exp.Expression, right: exp.Expression) -> bool:
    return (
        isinstance(left, exp.Column)
        and isinstance(right, exp.Column)
        and bool(str(left.table or "").strip())
        and bool(str(right.table or "").strip())
    )


def _mapping_matches_equalities(
    mapping: Mapping[str, Any], equalities: list[tuple[tuple[str, str], tuple[str, str]]]
) -> bool:
    child_table = str(mapping["child_table"])
    parent_table = str(mapping["parent_table"])
    pairs = mapping["ordered_column_pairs"]
    if not pairs:
        return False
    for child_column, parent_column in pairs:
        found = any(
            (
                left_table.casefold() == child_table.casefold()
                and left_column.casefold() == str(child_column).casefold()
                and right_table.casefold() == parent_table.casefold()
                and right_column.casefold() == str(parent_column).casefold()
            )
            or (
                left_table.casefold() == parent_table.casefold()
                and left_column.casefold() == str(parent_column).casefold()
                and right_table.casefold() == child_table.casefold()
                and right_column.casefold() == str(child_column).casefold()
            )
            for (left_table, left_column), (right_table, right_column) in equalities
        )
        if not found:
            return False
    return True


def parse_gold_sql(
    sql: str,
    *,
    db_id: str,
    known_columns: Mapping[str, Iterable[str]],
    candidate_mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract only resolved, explicit JOIN-ON FK mapping labels from one SQL."""
    counters = {
        "join_count": 0,
        "using_join_count": 0,
        "join_on_equality_count": 0,
        "qualified_join_equality_count": 0,
        "resolved_qualified_join_equality_count": 0,
        "unresolved_qualified_join_equality_count": 0,
        "implicit_where_cross_table_equality_count": 0,
        "scope_analysis_error_count": 0,
    }
    try:
        parsed = [node for node in sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE) if node is not None]
    except Exception as error:  # noqa: BLE001 - aggregate only the error class; never persist SQL.
        return {
            "parse_success": False,
            "parse_error_class": type(error).__name__,
            **counters,
            "gold_mapping_ids_by_table_pair": {},
        }
    if len(parsed) != 1:
        return {
            "parse_success": False,
            "parse_error_class": "statement_count",
            **counters,
            "gold_mapping_ids_by_table_pair": {},
        }

    table_by_fold, columns_by_table_fold = _column_index(known_columns)
    candidates_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for mapping in candidate_mappings:
        candidates_by_pair[
            table_pair_key(str(mapping["child_table"]), str(mapping["parent_table"]))
        ].append(mapping)

    gold_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    expression = parsed[0]
    try:
        for scope in traverse_scope(expression):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = _scope_aliases(scope, table_by_fold)
            for join in scope.expression.args.get("joins") or []:
                counters["join_count"] += 1
                if join.args.get("using"):
                    counters["using_join_count"] += 1
                    continue
                on = join.args.get("on")
                if on is None:
                    continue
                equality_groups: dict[
                    tuple[tuple[str, str], tuple[str, str]],
                    list[tuple[tuple[str, str], tuple[str, str]]],
                ] = defaultdict(list)
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
                    pair = table_pair_key(resolved_left[0], resolved_right[0])
                    if len(candidates_by_pair.get(pair, [])) < 2:
                        continue
                    alias_pair = tuple(sorted((left_alias, right_alias)))
                    equality_groups[(alias_pair, pair)].append((resolved_left, resolved_right))
                for (_, pair), equalities in equality_groups.items():
                    for mapping in candidates_by_pair[pair]:
                        if _mapping_matches_equalities(mapping, equalities):
                            gold_by_pair[pair].add(str(mapping["mapping_id"]))

            where = scope.expression.args.get("where")
            if where is not None:
                for equality in where.find_all(exp.EQ):
                    if equality.find_ancestor(exp.Select) is not scope.expression:
                        continue
                    if equality.find_ancestor(exp.Join) is not None:
                        continue
                    left = equality.this
                    right = equality.expression
                    if not _qualified_column_pair(left, right):
                        continue
                    resolved_left = _resolve_column(left, aliases, columns_by_table_fold)
                    resolved_right = _resolve_column(right, aliases, columns_by_table_fold)
                    if resolved_left is not None and resolved_right is not None:
                        if resolved_left[0].casefold() != resolved_right[0].casefold():
                            counters["implicit_where_cross_table_equality_count"] += 1
    except Exception as error:  # noqa: BLE001 - keep failures aggregate-only and fail the gate later.
        counters["scope_analysis_error_count"] += 1
        return {
            "parse_success": True,
            "parse_error_class": None,
            "scope_error_class": type(error).__name__,
            **counters,
            "gold_mapping_ids_by_table_pair": {},
        }

    return {
        "parse_success": True,
        "parse_error_class": None,
        **counters,
        "gold_mapping_ids_by_table_pair": {
            pair: sorted(mapping_ids) for pair, mapping_ids in sorted(gold_by_pair.items())
        },
    }


def load_known_columns(schema_path: Path) -> dict[str, dict[str, set[str]]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    require(isinstance(schema, dict), "official SQLite schema root must be a DB-to-DDL object")
    known: dict[str, dict[str, set[str]]] = {}
    for db_id, ddl_script in schema.items():
        require(isinstance(ddl_script, str) and ddl_script.strip(), f"missing schema DDL for {db_id}")
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(ddl_script)
            table_names = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            tables: dict[str, set[str]] = {}
            for table_name in table_names:
                escaped = table_name.replace('"', '""')
                columns = {
                    str(row[1])
                    for row in connection.execute(f'PRAGMA table_info("{escaped}")')
                }
                require(bool(columns), f"schema table has no columns: {db_id}/{table_name}")
                tables[table_name] = columns
            require(bool(tables), f"official schema contains no tables for {db_id}")
            known[str(db_id)] = tables
        finally:
            connection.close()
    return known


def validate_dev_tables(dev_tables_path: Path, known_columns: Mapping[str, Mapping[str, set[str]]]) -> None:
    dev_tables = json.loads(dev_tables_path.read_text(encoding="utf-8"))
    require(isinstance(dev_tables, list), "BIRD dev_tables root must be a list")
    rows = {str(row["db_id"]): row for row in dev_tables}
    require(len(rows) == len(dev_tables), "duplicate db_id in dev_tables")
    require(set(rows) == set(known_columns), "official schema/dev_tables database set differs")
    for db_id, row in rows.items():
        table_names = [str(value) for value in row["table_names_original"]]
        dev_columns: dict[str, set[str]] = {table: set() for table in table_names}
        for table_index, column_name in row["column_names_original"]:
            if int(table_index) >= 0 and str(column_name) != "*":
                dev_columns[table_names[int(table_index)]].add(str(column_name))
        schema_table_lookup = {table.casefold(): table for table in known_columns[db_id]}
        dev_table_lookup = {table.casefold(): table for table in dev_columns}
        require(set(schema_table_lookup) == set(dev_table_lookup), f"schema table inventory differs for {db_id}")
        for table_fold, schema_table in schema_table_lookup.items():
            dev_table = dev_table_lookup[table_fold]
            schema_column_folds = {column.casefold() for column in known_columns[db_id][schema_table]}
            dev_column_folds = {column.casefold() for column in dev_columns[dev_table]}
            require(schema_column_folds == dev_column_folds, f"schema column inventory differs for {db_id}/{schema_table}")


def load_candidate_mappings(
    artifact_path: Path,
    known_columns: Mapping[str, Mapping[str, set[str]]],
) -> tuple[dict[str, dict[tuple[str, str], list[dict[str, Any]]]], int, int]:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    instances = artifact.get("instances_private")
    require(isinstance(instances, dict), "FK artifact instances_private is not an object")
    require(set(instances) == set(known_columns), "FK artifact and dataset database sets differ")
    candidates: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
    skipped_invalid_endpoint_count = 0
    duplicate_identity_count = 0
    seen_ids: set[str] = set()
    for db_id, rows in instances.items():
        by_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
        require(isinstance(rows, list), f"FK instance list is invalid for {db_id}")
        for row in rows:
            if row.get("valid_endpoints") is not True:
                skipped_invalid_endpoint_count += 1
                continue
            mapping_id = str(row["join_instance_id"])
            require(mapping_id not in seen_ids, "duplicate join_instance_id across FK artifact")
            seen_ids.add(mapping_id)
            child_table = str(row["child_table"])
            parent_table = str(row["parent_table"])
            pair_rows = row["ordered_column_pairs"]
            require(isinstance(pair_rows, list) and pair_rows, f"empty mapping columns for {mapping_id}")
            schema_tables = {table.casefold(): table for table in known_columns[db_id]}
            require(child_table.casefold() in schema_tables, f"unknown child table in mapping {mapping_id}")
            require(parent_table.casefold() in schema_tables, f"unknown parent table in mapping {mapping_id}")
            child_name = schema_tables[child_table.casefold()]
            parent_name = schema_tables[parent_table.casefold()]
            child_columns = {
                column.casefold(): column for column in known_columns[db_id][child_name]
            }
            parent_columns = {
                column.casefold(): column for column in known_columns[db_id][parent_name]
            }
            normalized_pairs = []
            for pair in pair_rows:
                require(isinstance(pair, list) and len(pair) == 2, f"malformed mapping columns for {mapping_id}")
                child_column, parent_column = str(pair[0]), str(pair[1])
                require(child_column.casefold() in child_columns, f"unknown child column in mapping {mapping_id}")
                require(parent_column.casefold() in parent_columns, f"unknown parent column in mapping {mapping_id}")
                normalized_pairs.append(
                    [child_columns[child_column.casefold()], parent_columns[parent_column.casefold()]]
                )
            mapping = {
                "mapping_id": mapping_id,
                "child_table": child_name,
                "parent_table": parent_name,
                "ordered_column_pairs": normalized_pairs,
            }
            identity = (
                child_name.casefold(),
                parent_name.casefold(),
                tuple(
                    (child_column.casefold(), parent_column.casefold())
                    for child_column, parent_column in normalized_pairs
                ),
            )
            if identity in by_identity:
                duplicate_identity_count += 1
                if mapping_id < str(by_identity[identity]["mapping_id"]):
                    by_identity[identity] = mapping
            else:
                by_identity[identity] = mapping
        by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for mapping in by_identity.values():
            by_pair[table_pair_key(mapping["child_table"], mapping["parent_table"])].append(mapping)
        for pair, mappings in by_pair.items():
            mappings.sort(key=lambda value: value["mapping_id"])
            ids = [row["mapping_id"] for row in mappings]
            require(len(ids) == len(set(ids)), f"duplicate candidate mapping ID for {db_id}/{pair}")
        candidates[str(db_id)] = dict(by_pair)
    return candidates, skipped_invalid_endpoint_count, duplicate_identity_count


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL line {line_number}") from error
            require(isinstance(row, dict), f"JSONL record {line_number} is not an object")
            rows.append(row)
    return rows


def _merge_counters(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    keys = (
        "join_count",
        "using_join_count",
        "join_on_equality_count",
        "qualified_join_equality_count",
        "resolved_qualified_join_equality_count",
        "unresolved_qualified_join_equality_count",
        "implicit_where_cross_table_equality_count",
        "scope_analysis_error_count",
    )
    total = {key: 0 for key in keys}
    for row in rows:
        for key in keys:
            total[key] += int(row.get(key, 0))
    return total


def _private_keys(payload: Mapping[str, Any], field: str) -> list[tuple[str, str]]:
    raw_keys = payload.get(field)
    require(isinstance(raw_keys, list), f"{field} must be a list")
    keys: list[tuple[str, str]] = []
    for raw_key in raw_keys:
        require(
            isinstance(raw_key, list)
            and len(raw_key) == 2
            and all(isinstance(value, str) and value for value in raw_key),
            f"{field} contains a malformed question key",
        )
        keys.append((raw_key[0], raw_key[1]))
    require(len(keys) == len(set(keys)), f"{field} contains duplicate question keys")
    return keys


def validate_smoke_private(
    payload: Mapping[str, Any],
    expected_keys: set[tuple[str, str]],
    expected_input_hashes: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Reject stale, incomplete, duplicate, or mismatched smoke audit output."""
    require(payload.get("experiment_id") == EXPERIMENT_ID, "smoke output experiment ID mismatch")
    require(
        payload.get("run_id") == f"{EXPERIMENT_ID}_cpu_smoke_001",
        "smoke output run ID mismatch",
    )
    require(payload.get("split") == "smoke", "smoke output split mismatch")
    require(payload.get("input_sha256") == dict(expected_input_hashes), "smoke input hashes mismatch")

    smoke_keys = _private_keys(payload, "smoke_question_keys")
    selected_keys = _private_keys(payload, "selected_question_keys")
    require(set(smoke_keys) == expected_keys, "smoke question split mismatch")
    require(set(selected_keys) == expected_keys, "smoke selected questions mismatch")

    rows = payload.get("question_audit_rows")
    require(isinstance(rows, list) and len(rows) == len(expected_keys), "smoke audit row count mismatch")
    row_keys: list[tuple[str, str]] = []
    for row in rows:
        require(isinstance(row, dict), "smoke audit row is malformed")
        db_id = row.get("db_id")
        question_id = row.get("question_id")
        require(
            isinstance(db_id, str) and db_id and isinstance(question_id, str) and question_id,
            "smoke audit row has a malformed question key",
        )
        key = (db_id, question_id)
        row_keys.append(key)
        require(
            row.get("question_key_sha256") == stable_digest(db_id, question_id),
            "smoke audit question-key digest mismatch",
        )
        require(isinstance(row.get("parse_success"), bool), "smoke parse status is malformed")
        counters = row.get("parse_counters")
        require(isinstance(counters, dict), "smoke parse counters are malformed")
        require(
            all(isinstance(value, int) and value >= 0 for value in counters.values()),
            "smoke parse counters contain invalid values",
        )
    require(len(row_keys) == len(set(row_keys)), "smoke audit rows contain duplicate questions")
    require(set(row_keys) == expected_keys, "smoke audit rows do not cover the registered questions")
    return rows


def _load_config(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    require(config["experiment_id"] == EXPERIMENT_ID, "config experiment ID mismatch")
    require(config["labels"]["sqlglot_version"] == EXPECTED_SQLGLOT, "config SQLGlot version mismatch")
    return config


def _git_value(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--split", choices=("smoke", "full"), required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-private", type=Path)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(sqlglot.__version__ == EXPECTED_SQLGLOT, f"SQLGlot version mismatch: {sqlglot.__version__}")
    require(args.output_dir.exists() is False, f"output directory already exists: {args.output_dir}")
    run_started = time.perf_counter()
    cpu_started = time.process_time()
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    config = _load_config(args.config)
    commit = _git_value("rev-parse", "HEAD")
    branch = _git_value("branch", "--show-current")
    require(commit == args.expected_commit, "source commit differs from the registered pre-run commit")
    require(branch == EXPECTED_BRANCH, "experiment branch mismatch")

    dataset_path = Path(config["data"]["local_path"])
    schema_path = Path(config["data"]["official_schema_local_path"])
    dev_tables_path = Path(config["data"]["dev_tables_path"])
    artifact_path = Path(config["data"]["fk_artifact"])
    input_paths = {
        "dataset": dataset_path,
        "official_sqlite_schema": schema_path,
        "bird_dev_tables": dev_tables_path,
        "fk_mapping_artifact": artifact_path,
    }
    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": f"{EXPERIMENT_ID}_cpu_{args.split}_001",
        "status": "started",
        "split": args.split,
        "attempted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": commit,
        "source_branch": branch,
        "command_argv": [sys.executable, *sys.argv],
        "config_path": str(args.config.resolve()),
        "config_sha256": sha256_file(args.config),
        "input_paths": {name: str(path) for name, path in input_paths.items()},
        "input_sha256": {name: sha256_file(path) for name, path in input_paths.items()},
        "environment": {
            "python": platform.python_version(),
            "sqlglot": sqlglot.__version__,
            "sqlite": sqlite3.sqlite_version,
            "conda_prefix": os.environ.get("CONDA_PREFIX"),
        },
    }
    _write_json(args.output_dir / "attempt_manifest.json", manifest)

    try:
        expected_hashes = {
            "dataset": config["data"]["sha256"],
            "official_sqlite_schema": config["data"]["official_schema_sha256"],
            "bird_dev_tables": config["data"]["bird_dev_tables_sha256"],
            "fk_mapping_artifact": config["data"]["fk_artifact_sha256"],
        }
        require(manifest["input_sha256"] == expected_hashes, "input SHA-256 differs from frozen config")
        known_columns = load_known_columns(schema_path)
        validate_dev_tables(dev_tables_path, known_columns)
        candidates, invalid_endpoints, duplicate_mapping_identities = load_candidate_mappings(
            artifact_path, known_columns
        )
        dataset = _read_jsonl(dataset_path)
        require(len(dataset) == EXPECTED_ROWS, f"dataset row count mismatch: {len(dataset)}")
        dataset_db_ids = {str(row["db_id"]) for row in dataset}
        require(dataset_db_ids == set(known_columns), "dataset and official schema database sets differ")
        row_keys = [(str(row["db_id"]), str(row["question_id"])) for row in dataset]
        require(len(row_keys) == len(set(row_keys)), "duplicate (db_id, question_id) in dataset")

        smoke_keys = {
            key
            for _, key in sorted(
                (smoke_digest(db_id, question_id), (db_id, question_id)) for db_id, question_id in row_keys
            )[:EXPECTED_SMOKE_QUESTIONS]
        }
        if args.split == "smoke":
            require(args.smoke_private is None, "smoke split must not receive a prior smoke file")
            selected = [row for row in dataset if (str(row["db_id"]), str(row["question_id"])) in smoke_keys]
            smoke_audit_rows = None
        else:
            require(args.smoke_private is not None and args.smoke_private.is_file(), "full split requires the smoke private output")
            smoke_payload = json.loads(args.smoke_private.read_text(encoding="utf-8"))
            smoke_audit_rows = validate_smoke_private(smoke_payload, smoke_keys, expected_hashes)
            selected = [row for row in dataset if (str(row["db_id"]), str(row["question_id"])) not in smoke_keys]
            full_keys = {(str(row["db_id"]), str(row["question_id"])) for row in selected}
            require(len(selected) == EXPECTED_ROWS - EXPECTED_SMOKE_QUESTIONS, "full split question count mismatch")
            require(full_keys == set(row_keys) - smoke_keys, "full split question keys mismatch")
            require(full_keys.isdisjoint(smoke_keys), "smoke/full question split overlaps")
            require(full_keys | smoke_keys == set(row_keys), "smoke/full split does not cover all dataset rows")

        private_rows: list[dict[str, Any]] = []
        anonymous_db_order = sorted(
            dataset_db_ids,
            key=lambda db_id: hashlib.sha256(f"{EXPERIMENT_ID}:{db_id}".encode("utf-8")).hexdigest(),
        )
        anonymous_db_names = {db_id: f"db_{index:02d}" for index, db_id in enumerate(anonymous_db_order, start=1)}
        for row in selected:
            db_id = str(row["db_id"])
            question_id = str(row["question_id"])
            parsed = parse_gold_sql(
                str(row["SQL"]),
                db_id=db_id,
                known_columns=known_columns[db_id],
                candidate_mappings=[mapping for values in candidates[db_id].values() for mapping in values],
            )
            pair_cases = []
            for pair, accepted in parsed["gold_mapping_ids_by_table_pair"].items():
                mapping_rows = candidates[db_id][pair]
                if len(mapping_rows) < 2 or not accepted:
                    continue
                pair_id = stable_digest(EXPERIMENT_ID, db_id, question_id, pair[0], pair[1])
                identities = [
                    {
                        "mapping_id": mapping["mapping_id"],
                        "identity": [
                            "fk_mapping",
                            mapping["child_table"],
                            mapping["ordered_column_pairs"],
                            mapping["parent_table"],
                        ],
                    }
                    for mapping in mapping_rows
                ]
                pair_cases.append(
                    {
                        "pair_id": pair_id,
                        "private_table_pair": list(pair),
                        "candidate_mapping_ids": [mapping["mapping_id"] for mapping in mapping_rows],
                        "accepted_mapping_ids": accepted,
                        "mapping_identities": identities,
                        "private_question_text": str(row["question"]),
                    }
                )
            private_rows.append(
                {
                    "db_id": db_id,
                    "question_id": question_id,
                    "anonymous_db_id": anonymous_db_names[db_id],
                    "question_key_sha256": stable_digest(db_id, question_id),
                    "parse_success": parsed["parse_success"],
                    "parse_error_class": parsed.get("parse_error_class"),
                    "scope_error_class": parsed.get("scope_error_class"),
                    "parse_counters": {key: value for key, value in parsed.items() if key.endswith("count")},
                    "candidate_cases": pair_cases,
                }
            )

        selected_question_keys = [(str(row["db_id"]), str(row["question_id"])) for row in selected]
        require(
            len(selected_question_keys) == len(set(selected_question_keys)),
            "selected split contains duplicate questions",
        )
        smoke_question_keys = sorted(smoke_keys)
        split_counters = _merge_counters(row["parse_counters"] for row in private_rows)
        split_parse_success = sum(int(row["parse_success"]) for row in private_rows)
        full_candidate_cases = [case for row in private_rows for case in row["candidate_cases"]]
        manifest.update(
            {
                "status": "completed",
                "elapsed_seconds": round(time.perf_counter() - run_started, 6),
                "cpu_process_seconds": round(time.process_time() - cpu_started, 6),
                "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
                "selected_question_count": len(selected),
                "selected_parse_success_count": split_parse_success,
                "selected_parse_failure_count": len(selected) - split_parse_success,
                "selected_parse_counters": split_counters,
                "scored_pair_count": len(full_candidate_cases),
                "scored_pair_database_count": len({row["db_id"] for row in private_rows if row["candidate_cases"]}),
            }
        )
        if args.split == "smoke":
            public_counters = split_counters
            public_parse_count = split_parse_success
            public_question_count = len(selected)
            gate = None
        else:
            require(smoke_audit_rows is not None, "validated smoke rows are unavailable")
            combined_rows = smoke_audit_rows + private_rows
            combined_keys = [
                (str(row["db_id"]), str(row["question_id"])) for row in combined_rows
            ]
            require(len(combined_rows) == EXPECTED_ROWS, "combined smoke/full audit row count mismatch")
            require(len(combined_keys) == len(set(combined_keys)), "combined smoke/full audit has duplicate questions")
            require(set(combined_keys) == set(row_keys), "combined smoke/full audit does not cover all 500 questions")
            public_counters = _merge_counters(row["parse_counters"] for row in combined_rows)
            public_parse_count = sum(int(row["parse_success"]) for row in combined_rows)
            public_question_count = len(combined_rows)
            qualified = public_counters["qualified_join_equality_count"]
            resolved = public_counters["resolved_qualified_join_equality_count"]
            full_databases = {row["db_id"] for row in private_rows if row["candidate_cases"]}
            parse_rate = public_parse_count / public_question_count if public_question_count else 0.0
            resolution_rate = resolved / qualified if qualified else 0.0
            gate = {
                "overall_sql_parse_success_rate": round(parse_rate, 6),
                "qualified_join_equality_resolution_rate": round(resolution_rate, 6),
                "full_scored_pair_count": len(full_candidate_cases),
                "full_scored_database_count": len(full_databases),
                "scope_analysis_error_count": public_counters["scope_analysis_error_count"],
                "parse_rate_pass": parse_rate >= float(config["label_quality_gate"]["sql_parse_success_rate_min"]),
                "resolution_rate_pass": resolution_rate >= float(config["label_quality_gate"]["qualified_join_equality_resolution_rate_min"]),
                "scored_pair_count_pass": len(full_candidate_cases) >= int(config["split"]["min_full_scored_pairs"]),
                "database_count_pass": len(full_databases) >= int(config["split"]["min_full_databases"]),
                "scope_analysis_pass": public_counters["scope_analysis_error_count"] == 0,
            }
            gate["status"] = "LABEL_GATE_PASS" if all(
                value for key, value in gate.items() if key.endswith("_pass")
            ) else "STOP_LABEL_GATE_FAILED"

        aggregate = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": manifest["run_id"],
            "split": args.split,
            "status": gate["status"] if gate is not None else "SMOKE_AUDIT_COMPLETE",
            "question_count_in_split": len(selected),
            "question_count_in_combined_quality_denominator": public_question_count,
            "sql_parse_success_count_in_combined_quality_denominator": public_parse_count,
            "sql_parse_failure_count_in_combined_quality_denominator": public_question_count - public_parse_count,
            "sql_parse_success_rate": round(public_parse_count / public_question_count, 6) if public_question_count else None,
            "join_on_counts_in_combined_quality_denominator": public_counters,
            "full_scored_pair_count": len(full_candidate_cases) if args.split == "full" else None,
            "full_scored_database_count": gate["full_scored_database_count"] if gate is not None else None,
            "skipped_invalid_endpoint_mapping_count": invalid_endpoints,
            "duplicate_mapping_identity_rows_collapsed": duplicate_mapping_identities,
            "label_gate": gate,
            "privacy": {
                "contains_raw_question_or_gold_sql": False,
                "contains_database_table_or_mapping_names": False,
                "contains_per_question_labels_or_scores": False,
            },
        }
        private_payload = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": manifest["run_id"],
            "split": args.split,
            "smoke_question_keys": [list(key) for key in smoke_question_keys],
            "selected_question_keys": [list(key) for key in selected_question_keys],
            "question_audit_rows": private_rows,
            "candidate_cases": full_candidate_cases,
            "input_sha256": manifest["input_sha256"],
        }
        _write_json(args.output_dir / "private_labels.json", private_payload)
        _write_json(args.output_dir / "anonymous_aggregate.json", aggregate)
        manifest["status"] = aggregate["status"]
        manifest["anonymous_aggregate_path"] = str((args.output_dir / "anonymous_aggregate.json").resolve())
        manifest["private_labels_path"] = str((args.output_dir / "private_labels.json").resolve())
        _write_json(args.output_dir / "attempt_manifest.json", manifest)
        print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True))
        return aggregate
    except Exception as error:  # noqa: BLE001 - preserve a private, aggregate-only failure record.
        manifest.update(
            {
                "status": "failed",
                "failure_class": type(error).__name__,
                "failure_message": str(error),
            }
        )
        _write_json(args.output_dir / "attempt_manifest.json", manifest)
        raise


if __name__ == "__main__":
    run(parse_args())
