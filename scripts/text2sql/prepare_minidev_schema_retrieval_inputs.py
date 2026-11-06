#!/usr/bin/env python3
"""Prepare private label-free Mini-Dev schema inputs and SQL-derived Gold labels."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

EXPERIMENT_ID = "gfm_minidev_schema_retrieval_transfer_20261106_01"
EXPECTED_QUESTIONS_SHA256 = "926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606"
EXPECTED_SCHEMA_SHA256 = "5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b"
MIN_PARSE_COVERAGE = 0.98
MIN_TABLE_LABELED = 495
MIN_FULL_TABLE_LABELED = 490
MIN_FULL_COLUMN_ELIGIBLE = 450
MIN_FULL_DATABASES = 11
MIN_SMOKE_TABLE_LABELED = 5
MIN_SMOKE_COLUMN_ELIGIBLE = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    os.chmod(path, 0o600)


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def git_output(*arguments: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def normalize(value: str) -> str:
    return value.casefold()


def parse_schema_catalog(schema_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or len(raw) != 11:
        raise ValueError("Pinned SQLite DDL must contain exactly 11 database entries")
    manifest: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    catalog: dict[str, dict[str, Any]] = {}
    for db_id in sorted(str(key) for key in raw):
        ddl = raw[db_id]
        if not isinstance(ddl, str):
            raise ValueError("SQLite DDL values must be strings")
        statements = sqlglot.parse(ddl, read="sqlite")
        tables: list[dict[str, Any]] = []
        for statement in statements:
            if not isinstance(statement, exp.Create) or not isinstance(statement.this, exp.Schema):
                continue
            table_expr = statement.this.this
            if not isinstance(table_expr, exp.Table):
                continue
            table_name = str(table_expr.name)
            columns: list[dict[str, str]] = []
            for definition in statement.this.expressions:
                if not isinstance(definition, exp.ColumnDef):
                    continue
                column_name = str(definition.this.name)
                kind = definition.args.get("kind")
                column_type = kind.sql(dialect="sqlite") if isinstance(kind, exp.Expression) else str(kind or "")
                columns.append({"name": column_name, "type": column_type})
            if not columns:
                continue
            if any(normalize(item["name"]) == normalize(table_name) for item in tables):
                raise ValueError("Duplicate table name under SQLite case-insensitive matching")
            tables.append({"name": table_name, "columns": columns})
        if not tables:
            raise ValueError("No physical CREATE TABLE statements were parsed for one database")

        table_names = [table["name"] for table in tables]
        column_names_original: list[list[Any]] = [[-1, "*"]]
        table_index: dict[str, int] = {}
        table_columns: dict[str, set[str]] = {}
        for index, table in enumerate(tables):
            table_index[normalize(table["name"])] = index
            table_columns[normalize(table["name"])] = {normalize(column["name"]) for column in table["columns"]}
        for table_i, table in enumerate(tables):
            nodes.append({"node_id": f"table:{db_id}:{table_i}", "db_id": db_id, "node_type": "table", "text": f"Table: {table['name']}"})
            for column in table["columns"]:
                column_i = len(column_names_original)
                column_names_original.append([table_i, column["name"]])
                type_text = f"; Type: {column['type']}" if column["type"] else ""
                nodes.append({
                    "node_id": f"column:{db_id}:{column_i}",
                    "db_id": db_id,
                    "node_type": "column",
                    "text": f"Column: {column['name']}{type_text}; Table: {table['name']}",
                })
        manifest_row = {
            "db_id": db_id,
            "table_names_original": table_names,
            "column_names_original": column_names_original,
            "tables": tables,
        }
        manifest.append(manifest_row)
        column_index: dict[tuple[int, str], int] = {}
        for col_i, (owner_i, column_name) in enumerate(column_names_original):
            if int(owner_i) >= 0:
                column_index[(int(owner_i), normalize(str(column_name)))] = col_i
        catalog[db_id] = {
            "db_id": db_id,
            "tables": tables,
            "table_index": table_index,
            "table_columns": table_columns,
            "column_index": column_index,
            "column_names_original": column_names_original,
        }
    nodes.sort(key=lambda row: (row["db_id"], row["node_type"] != "table", row["node_id"]))
    return manifest, nodes, catalog


def output_columns(
    source_scope: Scope,
    output_name: str,
    db_catalog: dict[str, Any],
    seen: set[tuple[int, str]],
) -> tuple[set[str], str]:
    key = (id(source_scope), normalize(output_name))
    if key in seen:
        return set(), "ambiguous"
    seen = set(seen)
    seen.add(key)
    matches: list[exp.Expression] = []
    for projection in source_scope.expression.selects:
        if normalize(str(projection.alias_or_name)) == normalize(output_name):
            matches.append(projection.this if isinstance(projection, exp.Alias) else projection)
    if not matches:
        return set(), "absent"
    if len(matches) != 1:
        return set(), "ambiguous"
    expression = matches[0]
    if any(isinstance(node, (exp.Select, exp.Subquery)) for node in expression.walk()):
        return set(), "ambiguous"
    physical: set[str] = set()
    for inner_column in expression.find_all(exp.Column):
        if inner_column.is_star:
            continue
        resolved, ok = resolve_column(inner_column, source_scope, db_catalog, seen, allow_output_alias=False)
        if not ok:
            return set(), "ambiguous"
        physical.update(resolved)
    return (physical, "resolved") if physical else (set(), "ambiguous")


def resolve_column(
    column: exp.Column,
    scope: Scope,
    db_catalog: dict[str, Any],
    seen: set[tuple[int, str]],
    *,
    allow_output_alias: bool = True,
) -> tuple[set[str], bool]:
    if column.is_star or normalize(str(column.name)) == "*":
        return set(), True
    name = normalize(str(column.name))
    qualifier = normalize(str(column.table)) if column.table else ""

    alias_clause = False
    if allow_output_alias and not qualifier:
        parent = column.parent
        while parent is not None and parent is not scope.expression:
            if isinstance(parent, (exp.Order, exp.Group, exp.Having)):
                alias_clause = True
                break
            parent = parent.parent
        aliases = [
            projection for projection in scope.expression.selects
            if normalize(str(projection.alias_or_name)) == name
        ] if alias_clause else []
        if len(aliases) == 1:
            # Projection dependencies are accounted for at the projection itself.
            return set(), True
        if len(aliases) > 1:
            return set(), False

    selected = list(scope.selected_sources.items())
    if qualifier:
        selected = [(alias, pair) for alias, pair in selected if normalize(str(alias)) == qualifier]
        if not selected:
            # Some dialect parsers retain the physical table name instead of the alias.
            selected = [
                (alias, pair) for alias, pair in scope.selected_sources.items()
                if isinstance(pair[1], exp.Table) and normalize(str(pair[1].name)) == qualifier
            ]
    if not selected:
        return set(), False

    matches: list[set[str]] = []
    unresolved_source = False
    for _alias, (_node, source) in selected:
        if isinstance(source, exp.Table):
            table_name = normalize(str(source.name))
            if table_name not in db_catalog["table_index"]:
                unresolved_source = True
                continue
            if name in db_catalog["table_columns"][table_name]:
                table_i = db_catalog["table_index"][table_name]
                col_i = db_catalog["column_index"][(table_i, name)]
                matches.append({f"column:{db_catalog['db_id']}:{col_i}"})
            continue
        if isinstance(source, Scope):
            columns, status = output_columns(source, str(column.name), db_catalog, seen)
            if status == "ambiguous":
                return set(), False
            if status == "resolved":
                matches.append(columns)
            continue
        unresolved_source = True

    if unresolved_source or len(matches) != 1:
        return set(), False
    return matches[0], bool(matches[0])


def extract_labels(sql: str, db_id: str, manifest_row: dict[str, Any], catalog_row: dict[str, Any]) -> tuple[set[str], set[str], bool, str]:
    statements = [statement for statement in sqlglot.parse(sql, read="sqlite") if statement is not None]
    if len(statements) != 1:
        raise ValueError("Expected exactly one SQL statement")
    tree = statements[0]
    scopes = list(traverse_scope(tree))
    schema = catalog_row
    gold_tables: set[str] = set()
    gold_columns: set[str] = set()
    all_columns_resolved = True
    has_using = False
    for join in tree.find_all(exp.Join):
        if join.args.get("using"):
            has_using = True
    for scope in scopes:
        for _alias, (_node, source) in scope.selected_sources.items():
            if isinstance(source, exp.Table):
                table_name = normalize(str(source.name))
                if table_name not in catalog_row["table_index"]:
                    all_columns_resolved = False
                    continue
                gold_tables.add(f"table:{db_id}:{catalog_row['table_index'][table_name]}")
        for column in scope.columns:
            if column.is_star or normalize(str(column.name)) == "*":
                continue
            resolved, ok = resolve_column(column, scope, schema, set())
            if not ok:
                all_columns_resolved = False
            gold_columns.update(resolved)
    column_eligible = bool(gold_columns) and all_columns_resolved and not has_using
    reason = "eligible"
    if has_using:
        reason = "using_join"
    elif not gold_columns:
        reason = "no_explicit_physical_columns"
    elif not all_columns_resolved:
        reason = "unresolved_or_ambiguous_column"
    return gold_tables, gold_columns, column_eligible, reason


def stable_qid(db_id: str, source_question_id: Any) -> str:
    return sha256_text(f"{EXPERIMENT_ID}\x1f{db_id}\x1f{source_question_id}")


def select_smoke(rows: list[dict[str, Any]]) -> set[str]:
    ordered = sorted(
        rows,
        key=lambda row: sha256_text(f"{EXPERIMENT_ID}\x1f{row['db_id']}\x1f{row['source_question_key']}"),
    )
    selected: list[dict[str, Any]] = []
    seen_databases: set[str] = set()
    for row in ordered:
        if row["db_id"] not in seen_databases:
            selected.append(row)
            seen_databases.add(row["db_id"])
        if len(selected) == 5:
            break
    if len(selected) != 5:
        raise ValueError("Unable to select five questions from distinct databases")
    return {row["question_id"] for row in selected}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--sqlite-schema", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-questions-sha256", default=EXPECTED_QUESTIONS_SHA256)
    parser.add_argument("--expected-schema-sha256", default=EXPECTED_SCHEMA_SHA256)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    source_commit = git_output("rev-parse", "HEAD")
    source_tree = git_output("rev-parse", "HEAD^{tree}")
    if source_commit != args.expected_commit or git_output("status", "--porcelain"):
        raise RuntimeError("CPU label audit requires the registered clean source commit")

    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse prepared output directory: {args.output_dir}")
    if sha256_file(args.questions) != args.expected_questions_sha256:
        raise ValueError("Question input hash mismatch")
    if sha256_file(args.sqlite_schema) != args.expected_schema_sha256:
        raise ValueError("SQLite schema input hash mismatch")
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)

    manifest, nodes, catalog = parse_schema_catalog(args.sqlite_schema)
    manifest_by_db = {row["db_id"]: row for row in manifest}
    raw_rows: list[dict[str, Any]] = []
    with args.questions.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            raw_rows.append(json.loads(line))
    if len(raw_rows) != 500:
        raise ValueError(f"Expected 500 Mini-Dev rows, got {len(raw_rows)}")

    questions: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    parse_success = 0
    table_labeled = 0
    reason_counts: Counter[str] = Counter()
    parse_failure_count = 0
    for raw in raw_rows:
        db_id = str(raw["db_id"])
        if db_id not in catalog:
            raise ValueError("Question database is absent from the official SQLite DDL")
        question_id = stable_qid(db_id, raw["question_id"])
        question = str(raw["question"])
        try:
            table_ids, column_ids, column_eligible, reason = extract_labels(
                str(raw["SQL"]), db_id, manifest_by_db[db_id], catalog[db_id]
            )
            parse_success += 1
        except Exception:
            parse_failure_count += 1
            table_ids, column_ids, column_eligible, reason = set(), set(), False, "sql_parse_or_scope_exception"
        if table_ids:
            table_labeled += 1
        reason_counts[reason] += 1
        questions.append({
            "question_id": question_id,
            "source_question_key": str(raw["question_id"]),
            "db_id": db_id,
            "question": question,
        })
        labels.append({
            "question_id": question_id,
            "db_id": db_id,
            "gold_table_ids": sorted(table_ids),
            "gold_column_ids": sorted(column_ids),
            "column_eligible": bool(column_eligible),
            "label_status": reason,
        })
    if len({row["question_id"] for row in questions}) != len(questions):
        raise ValueError("Question-key hash collision or duplicate source key")

    smoke_ids = select_smoke(questions)
    question_by_id = {row["question_id"]: row for row in questions}
    full_rows = [row for row in questions if row["question_id"] not in smoke_ids]
    full_labels = [row for row in labels if row["question_id"] not in smoke_ids]
    full_eligible = sum(row["column_eligible"] for row in full_labels)
    full_databases = {row["db_id"] for row in full_labels if row["column_eligible"]}
    smoke_eligible = sum(row["column_eligible"] for row in labels if row["question_id"] in smoke_ids)
    smoke_table_labeled = sum(bool(row["gold_table_ids"]) for row in labels if row["question_id"] in smoke_ids)
    full_table_labeled = sum(bool(row["gold_table_ids"]) for row in full_labels)
    parse_coverage = parse_success / len(raw_rows)
    gate_conditions = {
        "sql_parse_coverage_at_least_98_percent": parse_coverage >= MIN_PARSE_COVERAGE,
        "at_least_495_table_labeled_questions": table_labeled >= MIN_TABLE_LABELED,
        "at_least_490_full_table_labeled_questions": full_table_labeled >= MIN_FULL_TABLE_LABELED,
        "at_least_450_full_column_eligible_questions": full_eligible >= MIN_FULL_COLUMN_ELIGIBLE,
        "at_least_10_full_database_clusters": len(full_databases) >= MIN_FULL_DATABASES,
        "all_5_smoke_questions_table_labeled": smoke_table_labeled >= MIN_SMOKE_TABLE_LABELED,
        "at_least_4_smoke_questions_column_eligible": smoke_eligible >= MIN_SMOKE_COLUMN_ELIGIBLE,
    }
    gate_pass = all(gate_conditions.values())

    write_jsonl(args.output_dir / "questions_label_free.jsonl", [
        {"question_id": row["question_id"], "db_id": row["db_id"], "question": row["question"], "is_smoke": row["question_id"] in smoke_ids}
        for row in questions
    ])
    write_jsonl(args.output_dir / "gold_labels_private.jsonl", labels)
    write_jsonl(args.output_dir / "schema_nodes_private.jsonl", nodes)
    write_json(args.output_dir / "schema_manifest_private.json", manifest)
    audit = {
        "experiment_id": EXPERIMENT_ID,
        "questions": len(questions),
        "databases": len(manifest),
        "parsed_questions": parse_success,
        "parse_failure_count": parse_failure_count,
        "sql_parse_coverage": parse_coverage,
        "table_labeled_questions": table_labeled,
        "full_table_labeled_questions": full_table_labeled,
        "smoke_questions": len(smoke_ids),
        "smoke_databases": len({question_by_id[qid]["db_id"] for qid in smoke_ids}),
        "smoke_column_eligible_questions": smoke_eligible,
        "smoke_table_labeled_questions": smoke_table_labeled,
        "full_questions": len(full_rows),
        "full_column_eligible_questions": full_eligible,
        "full_database_clusters_with_column_labels": len(full_databases),
        "table_nodes": sum(row["node_type"] == "table" for row in nodes),
        "column_nodes": sum(row["node_type"] == "column" for row in nodes),
        "label_status_counts": dict(sorted(reason_counts.items())),
        "gate_conditions": gate_conditions,
        "input_sha256": {
            "questions": sha256_file(args.questions),
            "sqlite_schema": sha256_file(args.sqlite_schema),
        },
        "sqlglot_version": sqlglot.__version__,
        "contains_raw_question_sql_database_names_or_row_results": False,
    }
    cpu_seconds = time.process_time() - started_cpu
    wall_seconds = time.perf_counter() - started_wall
    max_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    resource_pass = cpu_seconds <= 900 and wall_seconds <= 1200 and max_rss_bytes <= 8 * 1024**3
    audit["status"] = "LABEL_GATE_PASS" if gate_pass and resource_pass else "STOP_LABEL_OR_RESOURCE_GATE_FAILED"
    audit["resource_gate"] = {
        "within_budget": resource_pass,
        "process_cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
        "peak_rss_bytes": max_rss_bytes,
    }
    write_json(args.output_dir / "cpu_label_audit.json", audit)
    preparation_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": "gfm_minidev_schema_retrieval_transfer_20261106_labels_001",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "command_argv": [sys.executable, *sys.argv],
        "environment": {"python": platform.python_version(), "sqlglot": sqlglot.__version__},
        "resources_preflight": {
            "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "nvidia_smi": command_output([
                "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]),
            "free_h": command_output(["free", "-h"]),
            "nproc": command_output(["nproc"]),
        },
        "timing": {"wall_seconds": wall_seconds, "process_cpu_seconds": cpu_seconds, "peak_rss_bytes": max_rss_bytes},
    }
    write_json(args.output_dir / "preparation_manifest_private.json", preparation_manifest)
    print(json.dumps(audit, ensure_ascii=False, allow_nan=False), flush=True)
    if not gate_pass or not resource_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
