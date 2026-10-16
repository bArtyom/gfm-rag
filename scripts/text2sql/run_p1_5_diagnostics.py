#!/usr/bin/env python3
"""Run the frozen P1.5 retrieval and FK diagnostics for the Text2SQL workbench.

The script reads only the registered BIRD dev inputs and the historical P1
artifacts. It never writes question text, SQL, embeddings, or raw database data
to the public repository. Per-question rank diagnostics stay in the supplied
local output directory.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import resource
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
P1_ARCHIVE_SUPPORT = (
    REPO_ROOT
    / "docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/gfmrag_p1_common.py"
)
EXPECTED_BASE_COMMIT = "1d3a05773cd4305fdd591e6bd729a03e22326e8c"
EXPECTED_ENCODER_SOURCE_SHA256 = "4515c5d6c586ad8ef63dc00b7ba6e70eac4496ce47e0a71c3988b81899c704a0"
EXPECTED_BASE_SOURCE_SHA256 = "bdf97e695add03d00978eaedc64dcd76647b8e3cf5d662b7491ddb65ec404328"
EXPECTED_LEGACY_RUNNER_SHA256 = "824cbfbd0e18b2ecadada6738b447300c8725515d7867cac4cb1467ff1d2bd4f"
EXPECTED_LEGACY_SUPPORT_SHA256 = "54fadef342ba6eb5e19d16f2121d9e078b258de909a1c9ed1a52b32a1b2c26de"
EXPECTED_QUERY_HASH = "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06"
EXPECTED_SCHEMA_HASH = "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97"
EXPECTED_P0_HASH = "0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf"
EXPECTED_LABEL_HASH = "1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525"
EXPECTED_MODEL_MANIFEST_HASH = "b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68"
EXPECTED_PREVIOUS_SUMMARY_HASH = "33aed3af07201515aa59d3d4bd03894befec597ea3853c07e815db8db2dda97a"
EXPECTED_PREVIOUS_ROWS_HASH = "c28776ed47a30f1c898cb0a849a9834d7668999c26eb3c643e00474928b249cb"
EXPECTED_SCHEMA_TEXT_HASH = "b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a"
QUERY_INSTRUCTION = (
    "Given a natural-language question about a database, retrieve the relevant "
    "tables and columns."
)
QUERY_PREFIX = f"Instruct: {QUERY_INSTRUCTION}\nQuery: "
DIMENSIONS = (512, 1024)
BUDGETS = (512, 1024, 2048)
MAX_GPU_SECONDS = 900
MAX_CPU_SECONDS = 1800
MAX_RSS_GIB = 16
MAX_THREADS = 8


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_p1_support(legacy_root: Path, dataset_root: Path, model_path: Path) -> Any:
    if not P1_ARCHIVE_SUPPORT.is_file():
        raise FileNotFoundError(f"Archived P1 support file is missing: {P1_ARCHIVE_SUPPORT}")
    spec = importlib.util.spec_from_file_location("gfmrag_p1_common", P1_ARCHIVE_SUPPORT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the archived P1 support module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.PROJECT_ROOT = legacy_root
    module.UPSTREAM_ROOT = REPO_ROOT
    module.DATA_ROOT = dataset_root
    module.DB_ROOT = dataset_root / "dev_databases"
    module.QUESTION_PATH = dataset_root / "dev.json"
    module.SCHEMA_PATH = dataset_root / "dev_tables.json"
    module.P0_AUDIT_PATH = legacy_root / "results/p0/full_audit_v3.json"
    module.GOLD_LABELS_PATH = (
        legacy_root / "results/p1/full_1534_final_20261014/per_question_private.jsonl"
    )
    module.MODEL_PATH = model_path
    module.DESCRIPTION_CSV_ENCODINGS.clear()
    return module


def verify_run_sources(common: Any, legacy_root: Path) -> dict[str, Any]:
    commit = git_output("rev-parse", "HEAD")
    if commit != EXPECTED_BASE_COMMIT:
        raise RuntimeError(f"Expected base commit {EXPECTED_BASE_COMMIT}, found {commit}")
    encoder_path = REPO_ROOT / "gfmrag/text_emb_models/qwen3_model.py"
    base_path = REPO_ROOT / "gfmrag/text_emb_models/base_model.py"
    encoder_sha = sha256_file(encoder_path)
    base_sha = sha256_file(base_path)
    if encoder_sha != EXPECTED_ENCODER_SOURCE_SHA256:
        raise RuntimeError(f"Official Qwen3 source SHA mismatch: {encoder_sha}")
    if base_sha != EXPECTED_BASE_SOURCE_SHA256:
        raise RuntimeError(f"Official base source SHA mismatch: {base_sha}")

    legacy_runner = legacy_root / "ai_temp_code/run_gfmrag_p1.py"
    legacy_support = legacy_root / "ai_temp_code/gfmrag_p1_common.py"
    legacy_runner_sha = sha256_file(legacy_runner)
    legacy_support_sha = sha256_file(legacy_support)
    if legacy_runner_sha != EXPECTED_LEGACY_RUNNER_SHA256:
        raise RuntimeError(f"Historical P1 runner SHA mismatch: {legacy_runner_sha}")
    if legacy_support_sha != EXPECTED_LEGACY_SUPPORT_SHA256:
        raise RuntimeError(f"Historical P1 support SHA mismatch: {legacy_support_sha}")
    return {
        "project_repository": "https://github.com/bArtyom/gfm-rag",
        "project_base_commit": commit,
        "project_branch": git_output("branch", "--show-current"),
        "project_worktree_status_before_run": git_output("status", "--short"),
        "official_encoder_source_commit": "b3e43219c49929da505244df4f0ba54c0947e4c4",
        "official_encoder_source_sha256": encoder_sha,
        "official_base_model_source_sha256": base_sha,
        "historical_runner_sha256": legacy_runner_sha,
        "historical_support_sha256": legacy_support_sha,
        "p1_5_runner_sha256": sha256_file(Path(__file__).resolve()),
        "archived_support_used_for_input_and_text_reconstruction": str(P1_ARCHIVE_SUPPORT.relative_to(REPO_ROOT)),
        "archived_support_sha256": sha256_file(P1_ARCHIVE_SUPPORT),
    }


def verify_model_manifest(common: Any, legacy_root: Path, model_path: Path) -> dict[str, Any]:
    manifest = legacy_root / "results/p0/model_files.sha256"
    if sha256_file(manifest) != EXPECTED_MODEL_MANIFEST_HASH:
        raise RuntimeError("Frozen local-model manifest hash mismatch")
    entries: list[tuple[str, str]] = []
    total_bytes = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, raw_path = line.split(maxsplit=1)
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = model_path / path
        if not path.is_file():
            raise FileNotFoundError(f"Frozen model file missing: {path}")
        if sha256_file(path) != expected:
            raise RuntimeError(f"Frozen model file hash mismatch: {path.name}")
        total_bytes += path.stat().st_size
        entries.append((path.name, expected))
    return {
        "manifest_sha256": sha256_file(manifest),
        "files_verified": len(entries),
        "verified_bytes": total_bytes,
        "model_weights_sha256": next(
            digest for name, digest in entries if name == "model.safetensors"
        ),
    }


def verify_database_hashes(common: Any) -> dict[str, Any]:
    with common.P0_AUDIT_PATH.open("r", encoding="utf-8") as file:
        audit = json.load(file)
    records = audit["database_input_hashes"]
    verified = 0
    total_bytes = 0
    by_extension: collections.Counter[str] = collections.Counter()
    by_type_bytes: collections.Counter[str] = collections.Counter()
    for record in records:
        relative = Path(record["relative_path"])
        path = common.DB_ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Frozen database input missing: {relative}")
        actual_size = path.stat().st_size
        if actual_size != int(record["bytes"]):
            raise RuntimeError(f"Frozen database input size mismatch: {relative}")
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Frozen database input hash mismatch: {relative}")
        extension = path.suffix.lower() or "(none)"
        by_extension[extension] += 1
        by_type_bytes[extension] += actual_size
        total_bytes += actual_size
        verified += 1
    return {
        "files_verified": verified,
        "bytes_verified": total_bytes,
        "by_extension": {
            ext: {"files": by_extension[ext], "bytes": by_type_bytes[ext]}
            for ext in sorted(by_extension)
        },
        "database_input_hash_manifest_sha256": sha256_file(common.P0_AUDIT_PATH),
    }


def build_schema_metadata(common: Any, prepared: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schemas = json.loads(common.SCHEMA_PATH.read_text(encoding="utf-8"))
    metadata: dict[str, Any] = {}
    for schema in schemas:
        db_id = schema["db_id"]
        column_meta: dict[str, dict[str, Any]] = {}
        for index, ((table_index, column_name), column_type) in enumerate(
            zip(schema["column_names_original"], schema["column_types"])
        ):
            if table_index < 0:
                continue
            table_name = schema["table_names_original"][table_index]
            column_meta[f"column:{db_id}:{index}"] = {
                "table_name": table_name,
                "column_name": column_name,
                "column_type": column_type,
            }
        metadata[db_id] = {
            "table_count": len(schema["table_names_original"]),
            "column_count": len(column_meta),
            "column_meta": column_meta,
        }
    nodes_by_id = {node.node_id: node for node in prepared["nodes"]}
    return metadata, nodes_by_id


def sqlite_foreign_key_instances(common: Any, schemas: list[dict[str, Any]]) -> dict[str, Any]:
    by_db: dict[str, Any] = {}
    all_instances: dict[str, list[dict[str, Any]]] = {}
    valid_instances: dict[str, list[dict[str, Any]]] = {}
    for schema in schemas:
        db_id = schema["db_id"]
        sqlite_path = common.DB_ROOT / db_id / f"{db_id}.sqlite"
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            sqlite_tables = {str(row[0]).casefold(): str(row[0]) for row in table_rows}
            columns_by_table: dict[str, set[str]] = {}
            primary_keys_by_table: dict[str, list[str]] = {}
            groups: dict[tuple[str, int], list[tuple[int, str, str, str]]] = {}
            for table_name in sqlite_tables.values():
                quoted = table_name.replace('"', '""')
                columns = conn.execute(f'PRAGMA table_info("{quoted}")').fetchall()
                columns_by_table[table_name.casefold()] = {
                    str(column[1]).casefold() for column in columns
                }
                primary_keys_by_table[table_name.casefold()] = [
                    str(column[1])
                    for _, column in sorted(
                        (int(column[5]), column)
                        for column in columns
                        if int(column[5]) > 0
                    )
                ]
                fk_rows = conn.execute(f'PRAGMA foreign_key_list("{quoted}")').fetchall()
                for row in fk_rows:
                    constraint_id, sequence, parent, source, target = row[:5]
                    groups.setdefault((table_name, int(constraint_id)), []).append(
                        (int(sequence), str(parent or ""), str(source or ""), str(target or ""))
                    )

            instances: list[dict[str, Any]] = []
            invalid_reasons: collections.Counter[str] = collections.Counter()
            implicit_parent_key_instances = 0
            for (child_table, constraint_id), rows in sorted(groups.items()):
                rows.sort(key=lambda row: row[0])
                parent_names = {row[1].casefold() for row in rows}
                parent_table = rows[0][1]
                raw_pairs = [[row[2], row[3]] for row in rows]
                parent_pk_columns = primary_keys_by_table.get(parent_table.casefold(), [])
                empty_targets = [not row[3] for row in rows]
                implicit_parent_key = False
                if any(empty_targets):
                    if all(empty_targets) and len(rows) == len(parent_pk_columns):
                        pairs = [
                            [row[2], parent_pk_columns[index]]
                            for index, row in enumerate(rows)
                        ]
                        implicit_parent_key = True
                        implicit_parent_key_instances += 1
                    else:
                        pairs = [[row[2], row[3]] for row in rows]
                else:
                    pairs = raw_pairs
                issues: list[str] = []
                if child_table.casefold() not in sqlite_tables:
                    issues.append("missing_child_table")
                if parent_table.casefold() not in sqlite_tables:
                    issues.append("missing_parent_table")
                if len(parent_names) != 1:
                    issues.append("multiple_parent_tables_in_constraint")
                for source, target in pairs:
                    if not source:
                        issues.append("empty_child_column")
                    elif source.casefold() not in columns_by_table.get(child_table.casefold(), set()):
                        issues.append("missing_child_column")
                    if not target:
                        issues.append("unresolved_implicit_parent_key")
                    elif target.casefold() not in columns_by_table.get(parent_table.casefold(), set()):
                        issues.append("missing_parent_column")
                canonical = {
                    "db_id": db_id,
                    "child_table": child_table,
                    "sqlite_constraint_id": constraint_id,
                    "parent_table": parent_table,
                    "ordered_column_pairs": pairs,
                }
                stable_id = "join:" + hashlib.sha256(
                    json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                instance_record = {
                    **canonical,
                    "raw_ordered_column_pairs": raw_pairs,
                    "implicit_parent_key_resolved": implicit_parent_key,
                }
                for issue in set(issues):
                    invalid_reasons[issue] += 1
                instances.append(
                    {
                        **instance_record,
                        "join_instance_id": stable_id,
                        "valid_endpoints": not issues,
                        "endpoint_issues": sorted(set(issues)),
                    }
                )

            schema_fk_pairs: set[tuple[str, str]] = set()
            original_columns = schema["column_names_original"]
            for left_index, right_index in schema.get("foreign_keys", []):
                left_table_index, left_column = original_columns[left_index]
                right_table_index, right_column = original_columns[right_index]
                if left_table_index < 0 or right_table_index < 0:
                    continue
                left_table = schema["table_names_original"][left_table_index]
                right_table = schema["table_names_original"][right_table_index]
                pair = tuple(
                    sorted(
                        (
                            f"{left_table.casefold()}.{left_column.casefold()}",
                            f"{right_table.casefold()}.{right_column.casefold()}",
                        )
                    )
                )
                schema_fk_pairs.add(pair)

            sqlite_fk_pairs: set[tuple[str, str]] = set()
            for instance in instances:
                if not instance["valid_endpoints"]:
                    continue
                for child_column, parent_column in instance["ordered_column_pairs"]:
                    if child_column and parent_column:
                        sqlite_fk_pairs.add(
                            tuple(
                                sorted(
                                    (
                                        f"{instance['child_table'].casefold()}.{child_column.casefold()}",
                                        f"{instance['parent_table'].casefold()}.{parent_column.casefold()}",
                                    )
                                )
                            )
                        )
            db_instances = [row for row in instances if row["valid_endpoints"]]
            signatures = collections.Counter(
                (
                    row["child_table"].casefold(),
                    row["parent_table"].casefold(),
                    tuple(
                        (str(child).casefold(), str(parent).casefold())
                        for child, parent in row["ordered_column_pairs"]
                    ),
                )
                for row in db_instances
            )
            all_instances[db_id] = instances
            valid_instances[db_id] = db_instances
            by_db[db_id] = {
                "schema_json_tables": len(schema["table_names_original"]),
                "sqlite_tables": len(sqlite_tables),
                "schema_json_fk_pairs": len(schema_fk_pairs),
                "sqlite_fk_instances_raw": len(instances),
                "valid_join_instances": len(db_instances),
                "composite_join_instances": sum(len(row["ordered_column_pairs"]) > 1 for row in db_instances),
                "invalid_join_instances": sum(not row["valid_endpoints"] for row in instances),
                "duplicate_join_instance_signatures": sum(count - 1 for count in signatures.values() if count > 1),
                "unique_valid_join_relations": len(signatures),
                "implicit_parent_key_instances": implicit_parent_key_instances,
                "invalid_reason_counts": dict(sorted(invalid_reasons.items())),
                "json_fk_pairs_missing_in_sqlite": len(schema_fk_pairs - sqlite_fk_pairs),
                "sqlite_fk_pairs_missing_in_json": len(sqlite_fk_pairs - schema_fk_pairs),
                "schema_sql_table_count_matches": len(schema["table_names_original"]) == len(sqlite_tables),
            }
        finally:
            conn.close()
    return {
        "per_database": by_db,
        "instances_private": all_instances,
        "valid_instances_private": valid_instances,
    }


def golden_join_audit(sql_text: str, db_id: str, fk_instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Map direct JOIN ON column equalities to complete SQLite FK instances.

    This is an AST-level coverage audit only. It does not decide whether an
    SQL path is the unique semantically correct business role.
    """
    try:
        import sqlglot
        from sqlglot import exp

        parsed = sqlglot.parse_one(sql_text, read="sqlite")
    except Exception:
        return {"parse_ok": False, "join_on_count": 0, "join_without_on_count": 0, "matched": 0, "partial": 0, "unmatched": 0, "ambiguous": 0, "role_candidate_joins": 0, "resolved_table_pairs": 0}

    join_count = 0
    joins_without_on = 0
    matched = 0
    partial = 0
    unmatched = 0
    ambiguous = 0
    role_candidate_joins = 0
    resolved_table_pairs = 0
    try:
        from sqlglot.optimizer.scope import traverse_scope

        scopes = list(traverse_scope(parsed))
    except Exception:
        scopes = []
    if not scopes:
        scopes = [type("ScopeLike", (), {"expression": parsed, "sources": {}})()]

    fk_by_table_pair: dict[frozenset[str], list[dict[str, Any]]] = {}
    for instance in fk_instances:
        fk_by_table_pair.setdefault(
            frozenset((instance["child_table"].casefold(), instance["parent_table"].casefold())), []
        ).append(instance)

    for scope in scopes:
        expression = scope.expression
        joins = expression.args.get("joins") or []
        source_map: dict[str, str] = {}
        for alias, source in (getattr(scope, "sources", {}) or {}).items():
            if isinstance(source, exp.Table):
                source_map[str(alias).casefold()] = str(source.name).casefold()
        # SQLGlot versions may omit base tables from scope.sources for some
        # syntax; add only aliases whose physical table is unique in this scope.
        local_tables = [
            table
            for table in expression.find_all(exp.Table)
            if table.find_ancestor(exp.Select) is expression
        ] if hasattr(expression, "find_all") else []
        for table in local_tables:
            alias = str(table.alias_or_name).casefold()
            name = str(table.name).casefold()
            previous = source_map.get(alias)
            if previous is None or previous == name:
                source_map[alias] = name

        for join in joins:
            on_clause = join.args.get("on")
            if on_clause is None:
                joins_without_on += 1
                continue
            join_count += 1
            equality_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
            for equality in on_clause.find_all(exp.EQ):
                left, right = equality.this, equality.expression
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                left_table = source_map.get(str(left.table).casefold())
                right_table = source_map.get(str(right.table).casefold())
                if not left_table or not right_table:
                    continue
                left_key = (left_table, str(left.name).casefold())
                right_key = (right_table, str(right.name).casefold())
                equality_pairs.add(tuple(sorted((left_key, right_key))))
            table_pairs = {frozenset((left[0], right[0])) for left, right in equality_pairs if left[0] != right[0]}
            if not table_pairs:
                unmatched += 1
                continue
            resolved_table_pairs += 1
            candidate_instances: list[dict[str, Any]] = []
            exact_instances: list[dict[str, Any]] = []
            partial_instances: list[dict[str, Any]] = []
            for table_pair in table_pairs:
                candidates = fk_by_table_pair.get(table_pair, [])
                if len(candidates) > 1:
                    role_candidate_joins += 1
                candidate_instances.extend(candidates)
                for instance in candidates:
                    expected_pairs = {
                        tuple(
                            sorted(
                                (
                                    (instance["child_table"].casefold(), str(child).casefold()),
                                    (instance["parent_table"].casefold(), str(parent).casefold()),
                                )
                            )
                        )
                        for child, parent in instance["ordered_column_pairs"]
                    }
                    overlap = expected_pairs.intersection(equality_pairs)
                    if expected_pairs and expected_pairs.issubset(equality_pairs):
                        exact_instances.append(instance)
                    elif overlap:
                        partial_instances.append(instance)
            if len(exact_instances) == 1:
                matched += 1
            elif len(exact_instances) > 1:
                ambiguous += 1
            elif partial_instances:
                partial += 1
            else:
                unmatched += 1

    return {
        "parse_ok": True,
        "join_on_count": join_count,
        "join_without_on_count": joins_without_on,
        "matched": matched,
        "partial": partial,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "role_candidate_joins": role_candidate_joins,
        "resolved_table_pairs": resolved_table_pairs,
    }


def analyze_gold_joins(common: Any, schemas: list[dict[str, Any]], fk: dict[str, Any]) -> dict[str, Any]:
    questions = json.loads(common.QUESTION_PATH.read_text(encoding="utf-8"))
    per_db: dict[str, collections.Counter[str]] = {
        schema["db_id"]: collections.Counter() for schema in schemas
    }
    parse_failures = 0
    query_count_with_join_on = 0
    for question in questions:
        db_id = question["db_id"]
        result = golden_join_audit(
            question.get("SQL", ""),
            db_id,
            fk["valid_instances_private"].get(db_id, []),
        )
        if not result["parse_ok"]:
            parse_failures += 1
        if result["join_on_count"] > 0:
            query_count_with_join_on += 1
        counter = per_db[db_id]
        counter["queries"] += 1
        counter["queries_with_join_on"] += result["join_on_count"] > 0
        counter["queries_with_any_unique_fk_match"] += result["matched"] > 0
        counter["queries_with_unmatched_or_partial_join"] += (
            result["unmatched"] + result["partial"] > 0
        )
        counter["queries_with_multi_fk_table_pair"] += result["role_candidate_joins"] > 0
        counter["queries_with_all_join_on_clauses_uniquely_matched"] += (
            result["join_on_count"] > 0
            and result["matched"] == result["join_on_count"]
            and result["partial"] == 0
            and result["unmatched"] == 0
            and result["ambiguous"] == 0
        )
        for name in (
            "join_on_count",
            "join_without_on_count",
            "matched",
            "partial",
            "unmatched",
            "ambiguous",
            "role_candidate_joins",
            "resolved_table_pairs",
        ):
            counter[name] += int(result[name])
    return {
        "questions": len(questions),
        "parse_failures": parse_failures,
        "queries_with_join_on": query_count_with_join_on,
        "per_database": {db: dict(counter) for db, counter in sorted(per_db.items())},
        "total": {
            name: sum(counter[name] for counter in per_db.values())
            for name in (
                "queries",
                "queries_with_join_on",
                "queries_with_any_unique_fk_match",
                "queries_with_unmatched_or_partial_join",
                "queries_with_multi_fk_table_pair",
                "queries_with_all_join_on_clauses_uniquely_matched",
                "join_on_count",
                "join_without_on_count",
                "matched",
                "partial",
                "unmatched",
                "ambiguous",
                "role_candidate_joins",
                "resolved_table_pairs",
            )
        },
        "interpretation": "Direct explicit JOIN ON column equalities only; unique FK coverage is not a unique semantic-role label.",
    }


def token_features(question_text: str, node_text: str, node_meta: dict[str, Any]) -> dict[str, bool]:
    import re

    tokenize = lambda value: {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", value.replace("_", " "))
        if len(token) > 1
    }
    query_tokens = tokenize(question_text)
    identifier_tokens = tokenize(
        f"{node_meta['table_name']} {node_meta['column_name']}"
    )
    lower = node_text.casefold()
    return {
        "name_token_overlap": bool(query_tokens.intersection(identifier_tokens)),
        "has_any_description": any(
            marker in lower for marker in ("; description:", "; format:", "; values:")
        ),
        "has_value_description": "; values:" in lower,
        "has_data_format": "; format:" in lower,
        "has_column_description": "; description:" in lower,
    }


def rank_metrics(scores: np.ndarray, positions: list[int], gold_ids: tuple[str, ...], node_ids: list[str]) -> dict[str, Any]:
    local_scores = scores[positions]
    order = np.argsort(-local_scores, kind="stable")
    ordered_ids = [node_ids[positions[int(index)]] for index in order]
    rank_by_id = {node_id: rank for rank, node_id in enumerate(ordered_ids, start=1)}
    gold_ranks = sorted(rank_by_id[node_id] for node_id in gold_ids)
    count = len(gold_ids)
    hits = {k: sum(rank <= k for rank in gold_ranks) for k in (5, 10, 20)}
    ap = sum((index / rank) for index, rank in enumerate(gold_ranks, start=1)) / count
    return {
        "gold_ranks": gold_ranks,
        "rank_by_id": rank_by_id,
        "recall_hits": {str(k): value for k, value in hits.items()},
        "recall": {str(k): hits[k] / count for k in hits},
        "first_gold_rank": gold_ranks[0],
        "mrr": 1.0 / gold_ranks[0],
        "map": ap,
        "precision": {str(k): hits[k] / k for k in (5, 10, 20)},
    }


def budget_metrics(
    order: np.ndarray,
    candidate_indexes: list[int],
    nodes: list[Any],
    gold_ids: set[str],
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for budget in BUDGETS:
        remaining = budget
        selected: list[int] = []
        selected_ids: set[str] = set()
        used = 0
        for local_position in order:
            global_index = candidate_indexes[int(local_position)]
            node = nodes[global_index]
            if node.token_count <= remaining:
                selected.append(global_index)
                selected_ids.add(node.node_id)
                remaining -= node.token_count
                used += node.token_count
        found = len(gold_ids.intersection(selected_ids))
        results[str(budget)] = {
            "budget_tokens": budget,
            "tokens_used": used,
            "returned_elements": len(selected),
            "gold_elements": len(gold_ids),
            "retrieved_gold_elements": found,
            "recall": found / len(gold_ids) if gold_ids else None,
            "precision": found / len(selected) if selected else 0.0,
            "complete": int(found == len(gold_ids)),
        }
    return results


def quantile(values: list[float | int], q: float) -> float | None:
    return float(np.quantile(values, q)) if values else None


def score_embeddings(
    prepared: dict[str, Any],
    query_vectors_full: np.ndarray,
    node_vectors_full: np.ndarray,
    schema_meta: dict[str, Any],
    nodes_by_id: dict[str, Any],
    previous_rows: dict[str, Any] | None,
    mode: str,
    previous_is_full: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    if mode == "smoke":
        questions = questions[:5]
        active_dbs = {row["db_id"] for row in questions}
    else:
        active_dbs = set(prepared["nodes_by_db"])
    active_node_indexes = [i for i, node in enumerate(nodes) if node.db_id in active_dbs]
    active_questions = questions
    node_ids = [node.node_id for node in nodes]

    normalized_by_dim: dict[int, tuple[np.ndarray, np.ndarray, dict[str, float]]] = {}
    norm_stats: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        query_prefix = np.asarray(query_vectors_full[:, :dimension], dtype=np.float32)
        active_node_prefix = np.asarray(
            node_vectors_full[active_node_indexes, :dimension], dtype=np.float32
        )
        query_norms = np.linalg.norm(query_prefix, axis=1)
        node_norms = np.linalg.norm(active_node_prefix, axis=1)
        if not np.isfinite(query_prefix).all() or not np.isfinite(active_node_prefix).all():
            raise RuntimeError(f"Non-finite encoder values at dimension={dimension}")
        if np.any(query_norms <= 1e-12) or np.any(node_norms <= 1e-12):
            raise RuntimeError(f"Zero embedding norm at dimension={dimension}")
        query_unit = np.ascontiguousarray(query_prefix / query_norms[:, None], dtype=np.float32)
        active_node_unit = np.ascontiguousarray(
            active_node_prefix / node_norms[:, None], dtype=np.float32
        )
        node_unit = np.zeros((len(nodes), dimension), dtype=np.float32)
        node_unit[active_node_indexes] = active_node_unit
        norm_error = max(
            float(np.max(np.abs(np.linalg.norm(query_unit, axis=1) - 1.0))),
            float(np.max(np.abs(np.linalg.norm(active_node_unit, axis=1) - 1.0))),
        )
        normalized_by_dim[dimension] = (
            query_unit,
            node_unit,
            {"max_abs_error": norm_error, "raw_query_norm_median": float(np.median(query_norms)), "raw_node_norm_median": float(np.median(node_norms))},
        )
        norm_stats[str(dimension)] = normalized_by_dim[dimension][2]

    per_question: list[dict[str, Any]] = []
    dimension_acc: dict[int, dict[str, Any]] = {
        dimension: {
            "table_r5": [], "table_r10": [], "column_r5": [], "column_r10": [],
            "column_r20": [], "column_mrr": [], "column_map": [],
            "budgets": {str(budget): {"recall": [], "precision": [], "complete": [], "returned_elements": [], "tokens_used": []} for budget in BUDGETS},
            "gold_column_ranks": [], "first_column_rank": [],
        }
        for dimension in DIMENSIONS
    }
    db_acc: dict[str, dict[int, dict[str, Any]]] = {
        db_id: {dimension: {name: [] for name in ("table_r5", "table_r10", "column_r5", "column_r10", "column_r20", "column_mrr", "column_map")} | {"budgets": {str(budget): {"recall": [], "precision": [], "complete": [], "returned_elements": [], "tokens_used": []} for budget in BUDGETS}, "column_ranks": [], "first_column_rank": [], "questions": 0, "column_eligible_questions": 0} for dimension in DIMENSIONS}
        for db_id in active_dbs
    }
    by_db_node_indexes = {
        db_id: [index for index in active_node_indexes if nodes[index].db_id == db_id]
        for db_id in active_dbs
    }

    for query_index, question in enumerate(active_questions):
        db_id = question["db_id"]
        global_candidates = by_db_node_indexes[db_id]
        local_table_positions = [pos for pos, i in enumerate(global_candidates) if nodes[i].node_type == "table"]
        local_column_positions = [pos for pos, i in enumerate(global_candidates) if nodes[i].node_type == "column"]
        local_ids = [nodes[i].node_id for i in global_candidates]
        label = question["label"]
        row: dict[str, Any] = {
            "question_id": int(question["question_id"]),
            "db_id": db_id,
            "column_eligible": bool(label["column_eligible"]),
            "table_gold_count": len(label["gold_table_ids"]),
            "column_gold_count": len(label["gold_column_ids"]) if label["column_eligible"] else None,
            "dimensions": {},
        }
        for dimension in DIMENSIONS:
            query_unit, node_unit, _ = normalized_by_dim[dimension]
            scores = query_unit[query_index] @ node_unit[global_candidates].T
            table_metrics = rank_metrics(scores, local_table_positions, label["gold_table_ids"], local_ids)
            if label["column_eligible"]:
                column_metrics = rank_metrics(scores, local_column_positions, label["gold_column_ids"], local_ids)
                gold_ids = set((*label["gold_table_ids"], *label["gold_column_ids"]))
                order = np.argsort(-scores, kind="stable")
                budgets = budget_metrics(order, global_candidates, nodes, gold_ids)
            else:
                column_metrics = None
                budgets = None

            drow = {
                "table_hits": table_metrics["recall_hits"],
                "table_recall": table_metrics["recall"],
                "column_hits": column_metrics["recall_hits"] if column_metrics else None,
                "column_recall": column_metrics["recall"] if column_metrics else None,
                "column_gold_ranks": column_metrics["gold_ranks"] if column_metrics else None,
                "column_mrr": column_metrics["mrr"] if column_metrics else None,
                "column_map": column_metrics["map"] if column_metrics else None,
                "budgets": budgets,
            }
            row["dimensions"][str(dimension)] = drow
            current = dimension_acc[dimension]
            per_db = db_acc[db_id][dimension]
            per_db["questions"] += 1
            for metric_name, k in (("table_r5", 5), ("table_r10", 10)):
                value = table_metrics["recall"][str(k)]
                current[metric_name].append(value)
                per_db[metric_name].append(value)
            if column_metrics:
                per_db["column_eligible_questions"] += 1
                for metric_name, k in (("column_r5", 5), ("column_r10", 10), ("column_r20", 20)):
                    value = column_metrics["recall"][str(k)]
                    current[metric_name].append(value)
                    per_db[metric_name].append(value)
                current["column_mrr"].append(column_metrics["mrr"])
                current["column_map"].append(column_metrics["map"])
                current["gold_column_ranks"].extend(column_metrics["gold_ranks"])
                current["first_column_rank"].append(column_metrics["first_gold_rank"])
                per_db["column_mrr"].append(column_metrics["mrr"])
                per_db["column_map"].append(column_metrics["map"])
                per_db["column_ranks"].extend(column_metrics["gold_ranks"])
                per_db["first_column_rank"].append(column_metrics["first_gold_rank"])
                for budget, budget_result in budgets.items():
                    for metric in ("recall", "precision", "complete", "returned_elements", "tokens_used"):
                        current["budgets"][budget][metric].append(budget_result[metric])
                        per_db["budgets"][budget][metric].append(budget_result[metric])
            if dimension == 1024 and column_metrics:
                for node_id in label["gold_column_ids"]:
                    rank = column_metrics["rank_by_id"][node_id]
                    node = nodes_by_id[node_id]
                    metadata = schema_meta[db_id]["column_meta"][node_id]
                    features = token_features(question["text"], node.text, metadata)
                    row.setdefault("column_features", []).append({"rank": rank, **features})
        per_question.append(row)

    aggregate: dict[str, Any] = {
        "mode": mode,
        "questions": len(active_questions),
        "databases": len(active_dbs),
        "dimensions_reconstructed_from_one_1024_forward": list(DIMENSIONS),
        "norm_health": norm_stats,
        "global": {},
        "per_database": {},
        "paired_512_vs_1024": {},
        "reproduction_vs_historical_p1": None,
        "error_feature_rates_1024": {},
    }
    for dimension in DIMENSIONS:
        global_rows = dimension_acc[dimension]
        metric_map: dict[str, Any] = {}
        for metric in ("table_r5", "table_r10", "column_r5", "column_r10", "column_r20", "column_mrr", "column_map"):
            vals = global_rows[metric]
            db_means = [np.mean(db_acc[db][dimension][metric]) for db in sorted(active_dbs) if db_acc[db][dimension][metric]]
            metric_map[metric] = {
                "query_macro": float(np.mean(vals)) if vals else None,
                "database_macro": float(np.mean(db_means)) if db_means else None,
                "queries": len(vals),
            }
        metric_map["gold_column_rank_elements"] = {
            "count": len(global_rows["gold_column_ranks"]),
            "p50": quantile(global_rows["gold_column_ranks"], 0.50),
            "p90": quantile(global_rows["gold_column_ranks"], 0.90),
            "max": max(global_rows["gold_column_ranks"], default=None),
        }
        metric_map["first_gold_column_rank_per_question"] = {
            "count": len(global_rows["first_column_rank"]),
            "p50": quantile(global_rows["first_column_rank"], 0.50),
            "p90": quantile(global_rows["first_column_rank"], 0.90),
        }
        metric_map["budgets"] = {}
        for budget in map(str, BUDGETS):
            metric_map["budgets"][budget] = {
                metric: {
                    "query_macro": float(np.mean(global_rows["budgets"][budget][metric])) if global_rows["budgets"][budget][metric] else None,
                    "database_macro": float(np.mean([
                        np.mean(db_acc[db][dimension]["budgets"][budget][metric])
                        for db in sorted(active_dbs)
                        if db_acc[db][dimension]["budgets"][budget][metric]
                    ])) if global_rows["budgets"][budget][metric] else None,
                }
                for metric in ("recall", "precision", "complete", "returned_elements", "tokens_used")
            }
        aggregate["global"][str(dimension)] = metric_map
        aggregate["per_database"][str(dimension)] = {}
        for db_id in sorted(active_dbs):
            db_row = db_acc[db_id][dimension]
            db_metrics: dict[str, Any] = {
                "questions": db_row["questions"],
                "column_eligible_questions": db_row["column_eligible_questions"],
                "table_recall_at_5": float(np.mean(db_row["table_r5"])) if db_row["table_r5"] else None,
                "table_recall_at_10": float(np.mean(db_row["table_r10"])) if db_row["table_r10"] else None,
                "column_recall_at_5": float(np.mean(db_row["column_r5"])) if db_row["column_r5"] else None,
                "column_recall_at_10": float(np.mean(db_row["column_r10"])) if db_row["column_r10"] else None,
                "column_recall_at_20": float(np.mean(db_row["column_r20"])) if db_row["column_r20"] else None,
                "column_mrr": float(np.mean(db_row["column_mrr"])) if db_row["column_mrr"] else None,
                "column_map": float(np.mean(db_row["column_map"])) if db_row["column_map"] else None,
                "column_gold_rank_p50": quantile(db_row["column_ranks"], 0.50),
                "column_gold_rank_p90": quantile(db_row["column_ranks"], 0.90),
                "first_gold_column_rank_p50": quantile(db_row["first_column_rank"], 0.50),
                "first_gold_column_rank_p90": quantile(db_row["first_column_rank"], 0.90),
                "budgets": {},
            }
            for budget in map(str, BUDGETS):
                db_metrics["budgets"][budget] = {
                    metric: float(np.mean(db_row["budgets"][budget][metric])) if db_row["budgets"][budget][metric] else None
                    for metric in ("recall", "precision", "complete", "returned_elements", "tokens_used")
                }
            aggregate["per_database"][str(dimension)][db_id] = db_metrics

    rows_by_id = {str(row["question_id"]): row for row in per_question}
    qids = list(rows_by_id)
    if previous_rows is not None and previous_is_full and len(qids) == len(previous_rows):
        checks = collections.Counter()
        mismatches: list[dict[str, Any]] = []
        column_eligible_count = sum(row["column_eligible"] for row in per_question)
        for qid, row in rows_by_id.items():
            old = previous_rows.get(qid)
            if old is None:
                checks["missing_question"] += 1
                continue
            for dimension in DIMENSIONS:
                d = row["dimensions"][str(dimension)]
                old_metrics = old["metrics"][str(dimension)]
                pairs = [
                    ("table_hits", "table_r5_hits"),
                    ("table_hits", "table_r10_hits"),
                ]
                if row["column_eligible"]:
                    pairs.extend(
                        [
                            ("column_hits", "column_r5_hits"),
                            ("column_hits", "column_r10_hits"),
                        ]
                    )
                for outer, inner in pairs:
                    if inner.endswith("r5_hits"):
                        k = "5"
                    elif inner.endswith("r10_hits"):
                        k = "10"
                    else:
                        k = "5"
                    current_hits = d[outer][k] if d[outer] is not None else None
                    historical_hits = old_metrics.get(inner)
                    if current_hits == historical_hits:
                        checks[f"{dimension}_{inner}_match"] += 1
                    else:
                        if len(mismatches) < 20:
                            mismatches.append({"question_hash": hashlib.sha256(qid.encode()).hexdigest()[:12], "dimension": dimension, "metric": inner})
                if row["column_eligible"]:
                    current_budget = d["budgets"]["2048"]["complete"]
                    old_budget = old_metrics.get("budget_complete")
                    if int(current_budget) == int(old_budget):
                        checks[f"{dimension}_budget_complete_match"] += 1
                    else:
                        if len(mismatches) < 20:
                            mismatches.append({"question_hash": hashlib.sha256(qid.encode()).hexdigest()[:12], "dimension": dimension, "metric": "budget_complete"})
        expected = (
            len(qids) * 2 + column_eligible_count * 3
        ) * len(DIMENSIONS)
        matched = sum(value for key, value in checks.items() if key.endswith("_match"))
        aggregate["reproduction_vs_historical_p1"] = {
            "historical_run_id": "gfmrag_official_full1534_20261014_01",
            "previous_rows_sha256": EXPECTED_PREVIOUS_ROWS_HASH,
            "checks_expected": expected,
            "checks_matched": matched,
            "match_rate": matched / expected if expected else None,
            "matches_by_dimension_and_metric": dict(sorted(checks.items())),
            "mismatch_examples_question_hash_only": mismatches,
        }
    elif previous_rows is not None:
        aggregate["reproduction_vs_historical_p1"] = {
            "status": "not_applicable_to_smoke_subset",
            "smoke_rows": len(qids),
            "historical_rows": len(previous_rows),
        }

    if mode == "full":
        rescue_damage = {"column_r10": collections.Counter(), "budget_complete_2048": collections.Counter()}
        for row in per_question:
            if not row["column_eligible"]:
                continue
            old = row["dimensions"]["512"]
            new = row["dimensions"]["1024"]
            for metric, old_value, new_value in (
                ("column_r10", old["column_hits"]["10"], new["column_hits"]["10"]),
                ("budget_complete_2048", old["budgets"]["2048"]["complete"], new["budgets"]["2048"]["complete"]),
            ):
                category = "rescue_1024" if new_value > old_value else "damage_1024" if new_value < old_value else "same"
                rescue_damage[metric][category] += 1
        aggregate["paired_512_vs_1024"] = {
            metric: dict(sorted(counter.items()))
            for metric, counter in rescue_damage.items()
        }

    feature_comparison: dict[str, Any] = {}
    for feature in ("name_token_overlap", "has_any_description", "has_value_description", "has_data_format", "has_column_description"):
        groups = {"hit_at_10": [], "miss_at_10": []}
        for row in per_question:
            if not row["column_eligible"]:
                continue
            col_features = row.get("column_features", [])
            drow = row["dimensions"]["1024"]
            for features in col_features:
                rank = features["rank"]
                groups["hit_at_10" if rank <= 10 else "miss_at_10"].append(bool(features[feature]))
        feature_comparison[feature] = {
            group: {"gold_elements": len(values), "true_count": sum(values), "rate": float(np.mean(values)) if values else None}
            for group, values in groups.items()
        }
    aggregate["error_feature_rates_1024"] = {
        "definition": "Non-exclusive automatic text/metadata features among Gold column elements; descriptive association only, not causal or manually verified.",
        "features": feature_comparison,
    }

    if mode == "full":
        historical = previous_rows or {}
        checks = aggregate.get("reproduction_vs_historical_p1") or {}
        if checks.get("match_rate") != 1.0:
            aggregate["reproduction_gate"] = "FAIL"
        else:
            aggregate["reproduction_gate"] = "PASS"
    return aggregate, per_question


def analyze_saturation(
    questions: list[dict[str, Any]],
    nodes_by_db: dict[str, list[Any]],
    schema_meta: dict[str, Any],
) -> dict[str, Any]:
    questions_by_db: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for question in questions:
        questions_by_db[question["db_id"]].append(question)
    result: dict[str, Any] = {}
    distributions = {"table_gold_count": collections.Counter(), "column_gold_count": collections.Counter()}
    for question in questions:
        label = question["label"]
        distributions["table_gold_count"][str(len(label["gold_table_ids"]))] += 1
        if label["column_eligible"]:
            distributions["column_gold_count"][str(len(label["gold_column_ids"]))] += 1

    for db_id, db_questions in sorted(questions_by_db.items()):
        db_nodes = nodes_by_db[db_id]
        table_nodes = [node for node in db_nodes if node.node_type == "table"]
        column_nodes = [node for node in db_nodes if node.node_type == "column"]
        lengths = [node.token_count for node in db_nodes]
        all_schema_tokens = sum(lengths)
        token_stats = {}
        for budget in BUDGETS:
            oracle_fit = []
            complete_schema_fit = all_schema_tokens <= budget
            for question in db_questions:
                label = question["label"]
                if not label["column_eligible"]:
                    continue
                gold = set((*label["gold_table_ids"], *label["gold_column_ids"]))
                gold_tokens = sum(node.token_count for node in db_nodes if node.node_id in gold)
                oracle_fit.append(gold_tokens <= budget)
            token_stats[str(budget)] = {
                "budget_over_full_schema_token_total": budget / all_schema_tokens if all_schema_tokens else None,
                "gold_only_oracle_fit_rate": float(np.mean(oracle_fit)) if oracle_fit else None,
                "gold_only_oracle_fit_queries": int(sum(oracle_fit)),
                "column_eligible_queries": len(oracle_fit),
                "full_schema_fits": complete_schema_fit,
            }
        table_count = len(table_nodes)
        column_count = len(column_nodes)
        eligible = [q for q in db_questions if q["label"]["column_eligible"]]
        result[db_id] = {
            "questions": len(db_questions),
            "column_eligible_questions": len(eligible),
            "table_candidates": table_count,
            "column_candidates": column_count,
            "table_gold_elements": sum(len(q["label"]["gold_table_ids"]) for q in db_questions),
            "column_gold_elements": sum(len(q["label"]["gold_column_ids"]) for q in eligible),
            "table_gold_count_distribution": dict(sorted(collections.Counter(str(len(q["label"]["gold_table_ids"])) for q in db_questions).items(), key=lambda item: int(item[0]))),
            "column_gold_count_distribution": dict(sorted(collections.Counter(str(len(q["label"]["gold_column_ids"])) for q in eligible).items(), key=lambda item: int(item[0]))),
            "table_gold_count_above_k_queries": {
                str(k): sum(len(q["label"]["gold_table_ids"]) > k for q in db_questions)
                for k in (5, 10)
            },
            "table_candidates_at_most_k": {str(k): table_count <= k for k in (5, 10)},
            "table_candidate_topk_saturated": {str(k): table_count <= k for k in (5, 10)},
            "schema_node_tokens": {
                "total": all_schema_tokens,
                "p50": quantile(lengths, 0.50),
                "p95": quantile(lengths, 0.95),
                "max": max(lengths, default=None),
            },
            "budgets": token_stats,
        }
    return {
        "per_database": result,
        "global": {
            "table_gold_count_distribution": dict(sorted(distributions["table_gold_count"].items(), key=lambda item: int(item[0]))),
            "column_gold_count_distribution": dict(sorted(distributions["column_gold_count"].items(), key=lambda item: int(item[0]))),
            "table_gold_count_above_k_queries": {
                str(k): sum(len(q["label"]["gold_table_ids"]) > k for q in questions)
                for k in (5, 10)
            },
            "table_candidates_at_most_k_database_count": {
                str(k): sum(len([node for node in rows if node.node_type == "table"]) <= k for rows in nodes_by_db.values())
                for k in (5, 10)
            },
            "candidate_nodes": sum(len(rows) for rows in nodes_by_db.values()),
            "schema_tokens_total": sum(sum(node.token_count for node in rows) for rows in nodes_by_db.values()),
        },
    }


def load_previous_rows(previous_run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_start = json.loads((previous_run_dir / "run_start.json").read_text(encoding="utf-8"))
    summary_path = previous_run_dir / "summary.json"
    rows_path = previous_run_dir / "per_question_private.jsonl"
    if sha256_file(summary_path) != EXPECTED_PREVIOUS_SUMMARY_HASH:
        raise RuntimeError("Historical P1 summary hash mismatch")
    if sha256_file(rows_path) != EXPECTED_PREVIOUS_ROWS_HASH:
        raise RuntimeError("Historical P1 per-question hash mismatch")
    if run_start.get("source_commit") != "b3e43219c49929da505244df4f0ba54c0947e4c4":
        raise RuntimeError("Historical P1 encoder commit mismatch")
    rows: dict[str, Any] = {}
    with rows_path.open("r", encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            qid = str(row["question_id"])
            if qid in rows:
                raise RuntimeError("Duplicate question in historical P1 artifact")
            rows[qid] = row
    return run_start, rows


def write_private_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def current_resources(gpu_id: int) -> dict[str, Any]:
    try:
        gpu = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_id}",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception as exc:
        gpu = f"unavailable:{type(exc).__name__}"
    return {
        "selected_physical_gpu": gpu_id,
        "selected_gpu_status": gpu,
        "cpu_threads_available": os.cpu_count(),
        "process_thread_limit": MAX_THREADS,
        "python_maxrss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preflight", "smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--gpu-id", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    os.environ["OMP_NUM_THREADS"] = str(MAX_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(MAX_THREADS)
    started = time.perf_counter()
    cpu_started = time.process_time()
    run_start: dict[str, Any] = {
        "experiment_id": "p1_5_diagnosis_20261016",
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "preflight_started",
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "project_base_commit": git_output("rev-parse", "HEAD"),
        "gpu_resources_at_start": current_resources(args.gpu_id),
        "resource_budget": {
            "gpu_wall_seconds_max": MAX_GPU_SECONDS,
            "cpu_seconds_max": MAX_CPU_SECONDS,
            "process_maxrss_gib": MAX_RSS_GIB,
            "max_cpu_threads": MAX_THREADS,
        },
        "no_sql_execution": True,
        "no_api_calls": True,
        "no_dependency_installation": True,
        "no_model_download": True,
        "no_training": True,
    }
    write_json(args.output_dir / "run_start.json", run_start)

    if git_output("rev-parse", "HEAD") != EXPECTED_BASE_COMMIT:
        raise RuntimeError("Project base commit changed after registration")
    if args.mode in ("smoke", "full"):
        if os.environ.get("CUDA_VISIBLE_DEVICES") != str(args.gpu_id):
            raise RuntimeError(f"Expected CUDA_VISIBLE_DEVICES={args.gpu_id}")
        if os.environ.get("LOCAL_RANK") != str(args.gpu_id):
            raise RuntimeError(f"Expected LOCAL_RANK={args.gpu_id}")

    common = load_p1_support(args.legacy_root.resolve(), args.dataset_root.resolve(), args.model_path.resolve())
    source_record = verify_run_sources(common, args.legacy_root.resolve())
    previous_run, previous_rows = load_previous_rows(args.previous_run_dir.resolve())
    prepared = common.prepare_p1_inputs(load_tokenizer=True)
    if len(prepared["questions"]) != 1534 or len(prepared["nodes"]) != 873:
        raise RuntimeError("Frozen BIRD P1.5 input size mismatch")
    # The historical runner used a stable type-first order: all tables, then
    # all columns. The shared builder itself returns table/column interleaved.
    prepared["nodes"] = sorted(
        prepared["nodes"], key=lambda node: node.node_type != "table"
    )
    prepared["nodes_by_db"] = {
        db_id: sorted(rows, key=lambda node: node.node_type != "table")
        for db_id, rows in prepared["nodes_by_db"].items()
    }
    ordered_schema_hash = sha256_bytes(
        "\n".join(node.text for node in prepared["nodes"]).encode("utf-8")
    )
    prepared["text_hashes"]["schema_nodes"]["newline_join"] = ordered_schema_hash
    if ordered_schema_hash != EXPECTED_SCHEMA_TEXT_HASH:
        raise RuntimeError(
            "Frozen candidate-text serialization hash mismatch: "
            f"expected={EXPECTED_SCHEMA_TEXT_HASH} actual={ordered_schema_hash}"
        )
    model_integrity = verify_model_manifest(common, args.legacy_root.resolve(), args.model_path.resolve())
    database_integrity = verify_database_hashes(common)
    schemas = json.loads(common.SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_meta, nodes_by_id = build_schema_metadata(common, prepared)
    saturation = analyze_saturation(prepared["questions"], prepared["nodes_by_db"], schema_meta)
    fk = sqlite_foreign_key_instances(common, schemas)
    gold_joins = analyze_gold_joins(common, schemas, fk)
    input_manifest = {
        "experiment_id": "p1_5_diagnosis_20261016",
        "mode": args.mode,
        "project_commit": EXPECTED_BASE_COMMIT,
        "official_encoder_commit": "b3e43219c49929da505244df4f0ba54c0947e4c4",
        "historical_p1_runner_sha256": EXPECTED_LEGACY_RUNNER_SHA256,
        "historical_p1_support_sha256": EXPECTED_LEGACY_SUPPORT_SHA256,
        "historical_p1_run_id": previous_run["run_id"],
        "historical_p1_summary_sha256": EXPECTED_PREVIOUS_SUMMARY_HASH,
        "historical_p1_per_question_sha256": EXPECTED_PREVIOUS_ROWS_HASH,
        "data": {
            "dataset": "BIRD dev; exploratory; not independent evaluation",
            "question_count": len(prepared["questions"]),
            "database_count": len(prepared["nodes_by_db"]),
            "schema_node_count": len(prepared["nodes"]),
            "table_nodes": sum(node.node_type == "table" for node in prepared["nodes"]),
            "column_nodes": sum(node.node_type == "column" for node in prepared["nodes"]),
            "question_file_sha256": prepared["frozen_hashes"]["sha256"]["questions"],
            "schema_file_sha256": prepared["frozen_hashes"]["sha256"]["schema"],
            "p0_audit_sha256": prepared["frozen_hashes"]["sha256"]["p0_audit"],
            "gold_label_file_sha256": prepared["frozen_hashes"]["sha256"]["gold_labels"],
            "schema_text_sha256": prepared["text_hashes"]["schema_nodes"]["newline_join"],
            "query_prompt_sha256": prepared["text_hashes"]["query_prompts"]["newline_join"],
            "input_files_verified": database_integrity,
            "description_csv_encoding_counts": prepared["description_csv_encoding_counts"],
            "tokenizer_stats": prepared["token_stats"],
        },
        "model": {
            "model_path_alias": "/mnt/liansp3/sources/models/qwen3-embedding-0.6b",
            "local_model_manifest": model_integrity,
            "output_dimension": 1024,
            "prefix_diagnostic_dimensions": [512, 1024],
            "normalization": "explicit L2 normalization per prefix; exact dot-product cosine",
            "query_instruction": QUERY_INSTRUCTION,
            "batch_size": 32,
        },
        "candidate_text": "Historical P1 type-first schema text; same 873 nodes and exact serialized-text hash. Gold labels are scoring-only.",
        "environment": {
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "torch": package_version("torch"),
            "vllm": package_version("vllm"),
            "transformers": package_version("transformers"),
            "sqlglot": package_version("sqlglot"),
        },
        "source": source_record,
    }
    write_json(args.output_dir / "input_manifest.json", input_manifest)
    write_json(args.output_dir / "saturation_preflight.json", saturation)
    write_json(args.output_dir / "fk_gate_private.json", {"per_database": fk["per_database"], "instances_private": fk["instances_private"], "gold_joins": gold_joins})

    if args.mode == "preflight":
        receipt = {
            "status": "preflight_passed",
            "input_manifest_sha256": sha256_file(args.output_dir / "input_manifest.json"),
            "elapsed_wall_seconds": time.perf_counter() - started,
            "database_fk_per_database": fk["per_database"],
            "gold_join_summary": {key: value for key, value in gold_joins.items() if key != "per_database"},
            "saturation_global": saturation["global"],
        }
        write_json(args.output_dir / "preflight_receipt.json", receipt)
        run_start.update({"state": "completed", "finished_elapsed_wall_seconds": time.perf_counter() - started})
        write_json(args.output_dir / "run_start.json", run_start)
        print(json.dumps(receipt, ensure_ascii=False))
        return

    if args.mode == "smoke":
        active_questions = prepared["questions"][:5]
        active_db_ids = {row["db_id"] for row in active_questions}
        active_node_ids = {node.node_id for node in prepared["nodes"] if node.db_id in active_db_ids}
    else:
        active_questions = prepared["questions"]
        active_db_ids = set(prepared["nodes_by_db"])
        active_node_ids = {node.node_id for node in prepared["nodes"]}
    query_prompts = [row["prompt"] for row in active_questions]
    schema_texts = [node.text for node in prepared["nodes"] if node.node_id in active_node_ids]

    torch_threads = None
    import torch

    torch.set_num_threads(MAX_THREADS)
    torch_threads = torch.get_num_threads()
    encoder_class = common.load_official_qwen3_class()
    gpu_started = time.perf_counter()
    encoder = encoder_class(
        text_emb_model_name=str(args.model_path.resolve()),
        normalize=True,
        batch_size=32,
        query_instruct=None,
        passage_instruct=None,
        truncate_dim=1024,
        model_kwargs=None,
        tokenizer_kwargs={"local_files_only": True},
    )
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Expected exactly one visible CUDA device after official encoder initialization")
    gpu_name = torch.cuda.get_device_name(0)
    query_started = time.perf_counter()
    query_tensor = encoder.encode(query_prompts, is_query=True, show_progress_bar=False)
    query_encode_seconds = time.perf_counter() - query_started
    query_vectors = query_tensor.detach().to(device="cpu", dtype=torch.float32).numpy()
    del query_tensor
    if query_vectors.shape != (len(active_questions), 1024):
        raise RuntimeError(f"Unexpected query-vector shape: {query_vectors.shape}")
    schema_started = time.perf_counter()
    node_tensor = encoder.encode(schema_texts, is_query=False, show_progress_bar=False)
    schema_encode_seconds = time.perf_counter() - schema_started
    node_vectors_active = node_tensor.detach().to(device="cpu", dtype=torch.float32).numpy()
    del node_tensor
    if node_vectors_active.shape != (len(schema_texts), 1024):
        raise RuntimeError(f"Unexpected schema-vector shape: {node_vectors_active.shape}")
    del encoder
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    full_node_vectors = np.zeros((len(prepared["nodes"]), 1024), dtype=np.float32)
    active_node_indexes = [i for i, node in enumerate(prepared["nodes"]) if node.node_id in active_node_ids]
    full_node_vectors[active_node_indexes] = node_vectors_active
    aggregate, per_question = score_embeddings(
        prepared,
        query_vectors,
        full_node_vectors,
        schema_meta,
        nodes_by_id,
        previous_rows,
        args.mode,
        previous_is_full=(args.mode == "full"),
    )

    if args.mode == "smoke" and len(per_question) != 5:
        raise RuntimeError(f"Smoke must process 5 questions, got {len(per_question)}")
    gpu_elapsed = time.perf_counter() - gpu_started
    cpu_elapsed = time.process_time() - cpu_started
    maxrss_kib = max(
        int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss),
    )
    if gpu_elapsed > MAX_GPU_SECONDS or cpu_elapsed > MAX_CPU_SECONDS or maxrss_kib > MAX_RSS_GIB * 1024 * 1024:
        raise RuntimeError(
            f"Resource budget exceeded: gpu={gpu_elapsed:.1f}s cpu={cpu_elapsed:.1f}s maxrss={maxrss_kib / 1024 / 1024:.2f}GiB"
        )
    if args.mode == "full" and aggregate.get("reproduction_gate") != "PASS":
        aggregate["p1_5_gate"] = "NO-GO: exact historical row-level metric reproduction failed"
    else:
        aggregate["p1_5_gate"] = "PENDING: requires interpreting saturation, error features, and FK gate"
    aggregate["runtime"] = {
        "gpu_name": gpu_name,
        "gpu_id": args.gpu_id,
        "query_encode_seconds": query_encode_seconds,
        "schema_encode_seconds": schema_encode_seconds,
        "gpu_wall_seconds_load_and_encode": gpu_elapsed,
        "cpu_seconds_process": cpu_elapsed,
        "process_and_child_maxrss_gib": maxrss_kib / 1024 / 1024,
        "torch_threads": torch_threads,
    }
    write_json(args.output_dir / "aggregate_summary.json", aggregate)
    write_private_rows(args.output_dir / "per_question_private.jsonl", per_question)
    run_start.update(
        {
            "state": "completed",
            "finished_elapsed_wall_seconds": time.perf_counter() - started,
            "query_count": len(active_questions),
            "database_count": len(active_db_ids),
            "schema_node_count_encoded": len(schema_texts),
            "gpu_name": gpu_name,
            "runtime": aggregate["runtime"],
            "aggregate_summary_sha256": sha256_file(args.output_dir / "aggregate_summary.json"),
            "private_rows_sha256": sha256_file(args.output_dir / "per_question_private.jsonl"),
        }
    )
    write_json(args.output_dir / "run_start.json", run_start)
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "mode": args.mode,
                "questions": len(active_questions),
                "databases": len(active_db_ids),
                "reproduction_gate": aggregate.get("reproduction_gate"),
                "p1_5_gate": aggregate.get("p1_5_gate"),
                "runtime": aggregate["runtime"],
                "aggregate_summary_sha256": sha256_file(args.output_dir / "aggregate_summary.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
