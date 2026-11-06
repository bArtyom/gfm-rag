#!/usr/bin/env python
"""Compare BIRD and corrected SQL-derived retrieval labels on frozen P1.6 ranks.

The script never executes SQL and never loads a model. Question text, SQL, row IDs,
and per-question labels stay in the caller's private result directory.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import time

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


EXPERIMENT_ID = "p0_bird_gold_label_robustness_20261106_01"
EXPECTED_SHA256 = {
    "original_questions": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "schema": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
    "corrected_sql": "e7bf76408f99266506ea558d84982c69422e5db3dfecab5f08a3a8d3900e8395",
    "archived_labels": "1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525",
    "p1_6_rows": "6b28af7400cb70e0ab88a00b56654235571a074022fd8ea52b3f9744a844c4e9",
    "p1_6_nodes": "81ccc51c442c9d4771a16f600340c37f2673887fc0672d8179ecc20d39296754",
    "p1_6_aggregate": "925a7116835080b78f0752b3915f9bdf056e173434bd5b176111f7830c91c504",
}
EXPECTED_SOURCE_COMMIT = "fe766045c55b6875a43b30e9ac7683df5582f8cf"
EXPECTED_CORRECTED_ROWS = 498
EXPECTED_QUESTIONS = 1534
EXPECTED_NODES = 873
SMOKE_SIZE = 5
PARSER_VERSION = "30.12.0"
MIN_RATE = 0.98
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20261106
MAX_WALL_SECONDS = 600
MAX_RSS_BYTES = 8 * 1024**3


class AuditStop(RuntimeError):
    def __init__(self, status: str, public_reason: str):
        super().__init__(public_reason)
        self.status = status
        self.public_reason = public_reason


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AuditStop("STOP_INVALID_INPUT", f"invalid_jsonl_line_{line_no}") from exc
    return rows


def git_state(repo_root: Path) -> dict[str, str | None]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "worktree": "git_state_unavailable"}
    return {"commit": commit, "worktree": "clean" if not status else "dirty"}


def build_catalog(schema_rows: list[dict]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for schema in schema_rows:
        db_id = str(schema["db_id"])
        tables = {}
        columns_by_table: dict[int, dict[str, int]] = defaultdict(dict)
        table_names = schema["table_names_original"]
        for table_index, table_name in enumerate(table_names):
            key = str(table_name).casefold()
            if key in tables:
                raise AuditStop("STOP_SCHEMA_GATE", "duplicate_table_name_in_schema")
            tables[key] = table_index
        for column_index, pair in enumerate(schema["column_names_original"]):
            table_index, column_name = pair
            if int(table_index) < 0 or str(column_name) == "*":
                continue
            key = str(column_name).casefold()
            columns_by_table[int(table_index)][key] = column_index
        catalog[db_id] = {
            "tables": tables,
            "table_names": table_names,
            "columns_by_table": columns_by_table,
            "column_names": schema["column_names_original"],
        }
    return catalog


def physical_source_name(source) -> str | None:
    if not isinstance(source, exp.Table):
        return None
    db_name = str(source.db or "").casefold()
    catalog_name = str(source.catalog or "").casefold()
    if db_name not in ("", "main") or catalog_name:
        return None
    return str(source.name).casefold()


def local_sources(scope: Scope) -> dict[str, object]:
    return {
        str(alias).casefold(): source
        for alias, (_, source) in (scope.selected_sources or {}).items()
    }


def projection_alias_names(scope: Scope) -> set[str]:
    expression = scope.expression
    if not isinstance(expression, exp.Select):
        return set()
    return {str(item.alias_or_name).casefold() for item in expression.expressions if item.alias_or_name}


def output_alias_reference(column, scope: Scope) -> bool:
    name = str(column.name).casefold()
    if name not in projection_alias_names(scope):
        return False
    return any(
        column.find_ancestor(parent_type) is not None
        for parent_type in (exp.Order, exp.Group, exp.Having)
    )


def resolve_column(
    column,
    scope: Scope,
    db_catalog: dict,
    visited: set[tuple[int, str, str]] | None = None,
) -> tuple[str | None, str | None, bool]:
    """Resolve a direct base-column reference; derived outputs are already traced inside."""
    visited = set() if visited is None else visited
    name = str(column.name).casefold()
    if not name or name == "*":
        return None, "wildcard", False
    identity = (id(scope), str(column.table).casefold(), name)
    if identity in visited or len(visited) > 100:
        return None, "recursive_scope", True
    visited.add(identity)
    if str(column.db or "").casefold() not in ("", "main") or str(column.catalog or ""):
        return None, "external_database_source", True

    sources = local_sources(scope)
    qualifier = str(column.table or "").casefold()

    def bind_physical(source) -> tuple[str | None, str | None, bool]:
        table_name = physical_source_name(source)
        if table_name is None:
            if isinstance(source, Scope):
                return None, "derived_output", False
            return None, "unsupported_source", True
        table_index = db_catalog["tables"].get(table_name)
        if table_index is None:
            return None, "unknown_table", True
        column_index = db_catalog["columns_by_table"].get(table_index, {}).get(name)
        if column_index is None:
            return None, "missing_column", True
        db_id = db_catalog["db_id"]
        return f"column:{db_id}:{column_index}", None, False

    if qualifier:
        source = sources.get(qualifier)
        if source is not None:
            return bind_physical(source)
        if scope.parent is not None and bool(getattr(scope, "can_be_correlated", False)):
            return resolve_column(column, scope.parent, db_catalog, visited)
        return None, "unknown_qualifier", True

    if output_alias_reference(column, scope):
        return None, "select_output_alias", False

    physical_candidates = []
    derived_name_seen = False
    for source in sources.values():
        table_name = physical_source_name(source)
        if table_name is None:
            if isinstance(source, Scope) and name in projection_alias_names(source):
                derived_name_seen = True
            continue
        table_index = db_catalog["tables"].get(table_name)
        if table_index is None:
            continue
        column_index = db_catalog["columns_by_table"].get(table_index, {}).get(name)
        if column_index is not None:
            physical_candidates.append((table_name, column_index))
    if len(physical_candidates) == 1:
        _, column_index = physical_candidates[0]
        return f"column:{db_catalog['db_id']}:{column_index}", None, False
    if len(physical_candidates) > 1:
        return None, "ambiguous_unqualified", True
    if derived_name_seen:
        return None, "derived_output", False
    if scope.parent is not None and bool(getattr(scope, "can_be_correlated", False)):
        return resolve_column(column, scope.parent, db_catalog, visited)
    return None, "missing_column", True


def extract_labels(sql: str, db_id: str, catalog: dict) -> dict:
    db_catalog = catalog.get(str(db_id))
    if db_catalog is None:
        return {
            "parse_ok": False,
            "error_class": "unknown_database",
            "table_ids": [],
            "column_ids": [],
            "column_eligible": False,
            "wildcard_count": 0,
            "unresolved_table_count": 0,
            "unresolved_column_counts": {},
        }
    db_catalog = {**db_catalog, "db_id": str(db_id)}
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
        scopes = list(traverse_scope(tree))
    except Exception as exc:  # Do not retain parser text; it can contain SQL.
        return {
            "parse_ok": False,
            "error_class": type(exc).__name__,
            "table_ids": [],
            "column_ids": [],
            "column_eligible": False,
            "wildcard_count": 0,
            "unresolved_table_count": 0,
            "unresolved_column_counts": {},
        }

    table_ids: set[str] = set()
    column_ids: set[str] = set()
    unresolved_tables = 0
    unresolved_columns: Counter[str] = Counter()
    wildcard_count = 0
    direct_column_count = 0
    for scope in scopes:
        for _, source in local_sources(scope).items():
            table_name = physical_source_name(source)
            if table_name is None:
                if isinstance(source, exp.Table):
                    unresolved_tables += 1
                continue
            table_index = db_catalog["tables"].get(table_name)
            if table_index is None:
                unresolved_tables += 1
            else:
                table_ids.add(f"table:{db_id}:{table_index}")
        for column in scope.columns:
            if column.is_star or str(column.name) == "*":
                wildcard_count += 1
                continue
            direct_column_count += 1
            node_id, reason, unresolved = resolve_column(column, scope, db_catalog)
            if node_id:
                column_ids.add(node_id)
            elif unresolved and reason:
                unresolved_columns[reason] += 1

    # BIRD P0 labels exclude wildcard expansion. It reported no wildcard queries;
    # for any newly encountered wildcard, keep the query ineligible for column metrics.
    column_eligible = bool(direct_column_count or wildcard_count) and not unresolved_columns and not wildcard_count and bool(column_ids)
    return {
        "parse_ok": True,
        "error_class": None,
        "table_ids": sorted(table_ids),
        "column_ids": sorted(column_ids),
        "column_eligible": column_eligible,
        "wildcard_count": wildcard_count,
        "unresolved_table_count": unresolved_tables,
        "unresolved_column_counts": dict(sorted(unresolved_columns.items())),
    }


def exact_match_rows(corrected_rows: list[dict], originals: dict[int, dict]) -> tuple[list[dict], int]:
    matched = []
    mismatch_count = 0
    seen = set()
    fields = ("db_id", "question", "evidence")
    for corrected in corrected_rows:
        qid = int(corrected["question_id"])
        if qid in seen:
            raise AuditStop("STOP_MATCH_GATE", "duplicate_corrected_question_id")
        seen.add(qid)
        original = originals.get(qid)
        if original is None or any(corrected.get(field) != original.get(field) for field in fields):
            mismatch_count += 1
            continue
        matched.append({"qid": qid, "db_id": str(corrected["db_id"]), "original": original, "corrected": corrected})
    if len(seen) != len(corrected_rows):
        raise AuditStop("STOP_MATCH_GATE", "corrected_question_ids_not_unique")
    if mismatch_count:
        raise AuditStop("STOP_MATCH_GATE", "one_or_more_corrected_rows_fail_exact_metadata_match")
    return matched, mismatch_count


def smoke_key(record: dict) -> str:
    return hashlib.sha256(f"{record['db_id']}/{record['qid']}".encode("utf-8")).hexdigest()


def selected_smoke(records: list[dict]) -> list[dict]:
    return sorted(records, key=smoke_key)[:SMOKE_SIZE]


def archived_label_map(label_rows: list[dict]) -> dict[int, dict]:
    output = {}
    for row in label_rows:
        qid = int(row["question_id"])
        if qid in output:
            raise AuditStop("STOP_INVALID_INPUT", "duplicate_archived_label_question_id")
        output[qid] = {
            "db_id": str(row["db_id"]),
            "table_ids": sorted(set(row["gold_table_ids_private"])),
            "column_ids": sorted(set(row["gold_column_ids_private"])),
            "column_eligible": bool(row["column_eligible"]),
        }
    return output


def p1_row_map(rows: list[dict]) -> dict[int, dict]:
    output = {}
    for row in rows:
        qid = int(row["question_id"])
        if qid in output:
            raise AuditStop("STOP_INVALID_INPUT", "duplicate_p1_6_question_id")
        output[qid] = row
    return output


def evaluate_labels(labels: dict, rank_row: dict) -> dict:
    table_ids = set(labels["table_ids"])
    column_ids = set(labels["column_ids"])
    table_hits = {}
    for k, ids in rank_row["table_topk_ids"].items():
        table_hits[str(k)] = len(table_ids.intersection(ids))
    column_hits = {}
    if labels["column_eligible"]:
        for k, ids in rank_row["column_topk_ids"].items():
            column_hits[str(k)] = len(column_ids.intersection(ids))
    selected = set(rank_row["budgets"]["1024"]["selected_ids"])
    complete = bool(labels["column_eligible"] and table_ids.union(column_ids).issubset(selected))
    return {"table_hits": table_hits, "column_hits": column_hits, "complete_1024": complete}


def archived_baseline_parity(archived: dict, rank_row: dict) -> bool:
    calculated = evaluate_labels(archived, rank_row)
    for k, expected in rank_row["table_hits"].items():
        if calculated["table_hits"].get(str(k)) != int(expected):
            return False
    if archived["column_eligible"]:
        for k, expected in rank_row["column_hits"].items():
            if calculated["column_hits"].get(str(k)) != int(expected):
                return False
        if calculated["complete_1024"] != bool(rank_row["budgets"]["1024"]["complete"]):
            return False
    return True


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    union = a | b
    return 1.0 if not union else len(a & b) / len(union)


def row_metric(labels: dict, rank_row: dict, metric_name: str) -> float | None:
    evaluated = evaluate_labels(labels, rank_row)
    if metric_name.startswith("table_r"):
        k = metric_name.removeprefix("table_r")
        denom = len(labels["table_ids"])
        return safe_ratio(evaluated["table_hits"].get(k, 0), denom)
    if metric_name.startswith("column_r"):
        if not labels["column_eligible"]:
            return None
        k = metric_name.removeprefix("column_r")
        return safe_ratio(evaluated["column_hits"].get(k, 0), len(labels["column_ids"]))
    if metric_name == "complete_1024":
        return float(evaluated["complete_1024"]) if labels["column_eligible"] else None
    raise ValueError(f"Unknown metric {metric_name}")


def mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def clustered_bootstrap_ci(records: list[dict], metric_name: str, metric_pair: dict[int, tuple[float, float]],
                           minimum_clusters: int = 5) -> list[float] | None:
    by_db: dict[str, list[float]] = defaultdict(list)
    for record in records:
        pair = metric_pair.get(record["qid"])
        if pair is not None:
            by_db[record["db_id"]].append(pair[1] - pair[0])
    if len(by_db) < minimum_clusters:
        return None
    db_ids = sorted(by_db)
    sums = {db: sum(by_db[db]) for db in db_ids}
    counts = {db: len(by_db[db]) for db in db_ids}
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [rng.choice(db_ids) for _ in db_ids]
        n = sum(counts[db] for db in sampled)
        draws.append(sum(sums[db] for db in sampled) / n)
    draws.sort()
    low = draws[int(0.025 * (len(draws) - 1))] * 100.0
    high = draws[int(0.975 * (len(draws) - 1))] * 100.0
    return [low, high]


def summarize_metric(records: list[dict], metric_name: str) -> dict:
    original_values = []
    corrected_values = []
    paired: dict[int, tuple[float, float]] = {}
    original_by_db: dict[str, list[float]] = defaultdict(list)
    corrected_by_db: dict[str, list[float]] = defaultdict(list)
    for record in records:
        original_value = row_metric(record["original_labels"], record["rank_row"], metric_name)
        corrected_value = row_metric(record["corrected_labels"], record["rank_row"], metric_name)
        if original_value is not None:
            original_values.append(original_value)
            original_by_db[record["db_id"]].append(original_value)
        if corrected_value is not None:
            corrected_values.append(corrected_value)
            corrected_by_db[record["db_id"]].append(corrected_value)
        if original_value is not None and corrected_value is not None:
            paired[record["qid"]] = (original_value, corrected_value)
    delta_values = [right - left for left, right in paired.values()]
    db_macro_original = mean([mean(values) for values in original_by_db.values()])
    db_macro_corrected = mean([mean(values) for values in corrected_by_db.values()])
    ci = clustered_bootstrap_ci(records, metric_name, paired)
    return {
        "original_n": len(original_values),
        "corrected_n": len(corrected_values),
        "paired_common_n": len(paired),
        "original_query_macro": mean(original_values),
        "corrected_query_macro": mean(corrected_values),
        "original_database_macro": db_macro_original,
        "corrected_database_macro": db_macro_corrected,
        "paired_delta_percentage_points": None if not delta_values else mean(delta_values) * 100.0,
        "paired_database_cluster_bootstrap_95ci_percentage_points": ci,
        "bootstrap_clusters": len(set(r["db_id"] for r in records if r["qid"] in paired)),
    }


def round_floats(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 8)
    if isinstance(value, dict):
        return {key: round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_floats(item) for item in value]
    return value


def public_summary(stage: str, run_id: str, records: list[dict], checks: dict,
                   input_hashes: dict, elapsed_seconds: float, rss_bytes: int) -> dict:
    original_parse = sum(record["original_parsed"]["parse_ok"] for record in records)
    corrected_parse = sum(record["corrected_parsed"]["parse_ok"] for record in records)
    original_tables = sum(bool(record["original_parsed"]["table_ids"]) for record in records)
    corrected_tables = sum(bool(record["corrected_parsed"]["table_ids"]) for record in records)
    original_columns = sum(record["original_parsed"]["column_eligible"] for record in records)
    corrected_columns = sum(record["corrected_parsed"]["column_eligible"] for record in records)
    exact_label_rows = sum(record["historical_label_exact"] for record in records)
    table_changes = sum(record["original_labels"]["table_ids"] != record["corrected_labels"]["table_ids"] for record in records)
    column_changes = sum(record["original_labels"]["column_ids"] != record["corrected_labels"]["column_ids"] for record in records)
    eligibility_changes = sum(record["original_labels"]["column_eligible"] != record["corrected_labels"]["column_eligible"] for record in records)
    label_set_changes = sum(
        record["original_labels"]["table_ids"] != record["corrected_labels"]["table_ids"]
        or record["original_labels"]["column_ids"] != record["corrected_labels"]["column_ids"]
        for record in records
    )
    label_jaccard_table = mean([jaccard(r["original_labels"]["table_ids"], r["corrected_labels"]["table_ids"]) for r in records])
    label_jaccard_column = mean([jaccard(r["original_labels"]["column_ids"], r["corrected_labels"]["column_ids"]) for r in records])

    metrics = {}
    if stage == "full":
        for name in ("table_r5", "table_r10", "column_r5", "column_r10", "complete_1024"):
            metrics[name] = summarize_metric(records, name)
        complete_pairs = []
        for record in records:
            left = row_metric(record["original_labels"], record["rank_row"], "complete_1024")
            right = row_metric(record["corrected_labels"], record["rank_row"], "complete_1024")
            if left is not None and right is not None:
                complete_pairs.append((left, right))
        eligible_rows = [r for r in records if r["original_labels"]["column_eligible"] and r["corrected_labels"]["column_eligible"]]
        sensitivity_pct = 100.0 * safe_ratio(label_set_changes, len(records))
        primary_deltas = [metrics[key]["paired_delta_percentage_points"] for key in ("table_r10", "column_r10", "complete_1024")]
        if sensitivity_pct >= 5.0 or any(delta is not None and abs(delta) >= 2.0 for delta in primary_deltas):
            decision = "LABEL_SENSITIVE"
        elif sensitivity_pct <= 1.0 and all(delta is not None and abs(delta) < 1.0 for delta in primary_deltas):
            decision = "LABEL_ROBUST"
        else:
            decision = "INCONCLUSIVE_OR_MIXED"
        metrics["label_comparison"] = {
            "table_label_changed_questions": table_changes,
            "column_label_changed_questions": column_changes,
            "either_table_or_column_set_changed_questions": label_set_changes,
            "either_set_changed_percentage": sensitivity_pct,
            "column_eligibility_changed_questions": eligibility_changes,
            "table_label_set_exact_agreement_rate": 1.0 - table_changes / len(records),
            "column_label_set_exact_agreement_rate": 1.0 - column_changes / len(records),
            "table_label_set_macro_jaccard": label_jaccard_table,
            "column_label_set_macro_jaccard": label_jaccard_column,
            "complete_1024_rescues_on_common_eligible_questions": sum(left == 0.0 and right == 1.0 for left, right in complete_pairs),
            "complete_1024_damages_on_common_eligible_questions": sum(left == 1.0 and right == 0.0 for left, right in complete_pairs),
            "common_column_eligible_questions": len(eligible_rows),
        }
    else:
        decision = "SMOKE_ONLY_NOT_A_SCIENTIFIC_RESULT"

    db_count = len({record["db_id"] for record in records})
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "stage": stage,
        "status": "SMOKE_PASS" if stage == "smoke" and checks.get("all_gates_pass") else "FULL_COMPLETED" if stage == "full" and checks.get("all_gates_pass") else "STOP_GATE_FAILED",
        "interpretation": decision,
        "sample_questions": len(records),
        "database_clusters": db_count,
        "source_rows_exactly_matched": EXPECTED_CORRECTED_ROWS,
        "smoke_rows_excluded_from_full": SMOKE_SIZE if stage == "full" else 0,
        "parser_and_label_coverage": {
            "original_parse_rate": safe_ratio(original_parse, len(records)),
            "corrected_parse_rate": safe_ratio(corrected_parse, len(records)),
            "original_nonempty_table_label_rate": safe_ratio(original_tables, len(records)),
            "corrected_nonempty_table_label_rate": safe_ratio(corrected_tables, len(records)),
            "original_column_eligible_rate": safe_ratio(original_columns, len(records)),
            "corrected_column_eligible_rate": safe_ratio(corrected_columns, len(records)),
            "original_exact_label_compatibility_to_frozen_p1_rate": safe_ratio(exact_label_rows, len(records)),
            "historical_column_eligibility_changes": eligibility_changes,
        },
        "gates": checks,
        "metrics": metrics,
        "input_sha256": input_hashes,
        "runtime": {"wall_seconds": elapsed_seconds, "peak_rss_bytes": rss_bytes, "cpu_only": True},
        "environment": {
            "python": platform.python_version(),
            "sqlglot": importlib.metadata.version("sqlglot"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "thread_environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
        },
        "model_calls": 0,
        "sql_execution_count": 0,
        "dependency_changes": 0,
    }
    return round_floats(summary)


def private_rows_payload(records: list[dict]) -> list[dict]:
    output = []
    for record in records:
        output.append({
            "question_id": record["qid"],
            "db_id": record["db_id"],
            "historical_label_exact": record["historical_label_exact"],
            "original_table_label_count": len(record["original_labels"]["table_ids"]),
            "corrected_table_label_count": len(record["corrected_labels"]["table_ids"]),
            "original_column_label_count": len(record["original_labels"]["column_ids"]),
            "corrected_column_label_count": len(record["corrected_labels"]["column_ids"]),
            "original_column_eligible": record["original_labels"]["column_eligible"],
            "corrected_column_eligible": record["corrected_labels"]["column_eligible"],
            "original_metrics": record["original_metrics"],
            "corrected_metrics": record["corrected_metrics"],
        })
    return output


def source_hashes(args) -> dict[str, str]:
    mapping = {
        "original_questions": Path(args.original_json),
        "schema": Path(args.schema_json),
        "corrected_sql": Path(args.corrected_json),
        "archived_labels": Path(args.archived_labels),
        "p1_6_rows": Path(args.p1_rows),
        "p1_6_nodes": Path(args.node_manifest),
        "p1_6_aggregate": Path(args.p1_aggregate),
    }
    actual = {name: sha256_file(path) for name, path in mapping.items()}
    mismatches = {name: {"expected": EXPECTED_SHA256[name], "actual": actual[name]} for name in actual if actual[name] != EXPECTED_SHA256[name]}
    if mismatches:
        raise AuditStop("STOP_INPUT_HASH", "one_or_more_frozen_input_hashes_differ")
    return actual


def run(args) -> int:
    started = time.monotonic()
    out_dir = Path(args.output_dir)
    if out_dir.exists():
        raise AuditStop("STOP_OUTPUT_EXISTS", "output_directory_already_exists")
    out_dir.mkdir(parents=True, exist_ok=False)
    repo_root = Path(args.repo_root).resolve()
    git = git_state(repo_root)
    if args.expected_commit and git["commit"] != args.expected_commit:
        raise AuditStop("STOP_CODE_COMMIT", "checkout_commit_does_not_match_registered_commit")
    if git["worktree"] != "clean":
        raise AuditStop("STOP_DIRTY_WORKTREE", "project_worktree_is_not_clean")
    if sqlglot.__version__ != PARSER_VERSION:
        raise AuditStop("STOP_PARSER_VERSION", "sqlglot_version_does_not_match_registered_version")

    hashes = source_hashes(args)
    original_rows = read_json(Path(args.original_json))
    schema_rows = read_json(Path(args.schema_json))
    corrected_rows = read_json(Path(args.corrected_json))
    labels = archived_label_map(read_jsonl(Path(args.archived_labels)))
    ranks = p1_row_map(read_jsonl(Path(args.p1_rows)))
    node_rows = read_json(Path(args.node_manifest))
    if len(original_rows) != EXPECTED_QUESTIONS or len(schema_rows) != 11 or len(corrected_rows) != EXPECTED_CORRECTED_ROWS:
        raise AuditStop("STOP_INPUT_SHAPE", "frozen_dataset_row_counts_do_not_match_registration")
    if len(labels) != EXPECTED_QUESTIONS or len(ranks) != EXPECTED_QUESTIONS or len(node_rows) != EXPECTED_NODES:
        raise AuditStop("STOP_INPUT_SHAPE", "frozen_label_or_rank_manifest_count_mismatch")
    node_ids = {row["node_id"] for row in node_rows}
    if len(node_ids) != EXPECTED_NODES:
        raise AuditStop("STOP_INPUT_SHAPE", "frozen_node_ids_not_unique")

    originals = {}
    for row in original_rows:
        qid = int(row["question_id"])
        if qid in originals:
            raise AuditStop("STOP_MATCH_GATE", "duplicate_original_question_id")
        originals[qid] = row
    matched, mismatch_count = exact_match_rows(corrected_rows, originals)
    if len(matched) != EXPECTED_CORRECTED_ROWS or mismatch_count:
        raise AuditStop("STOP_MATCH_GATE", "corrected_source_not_one_to_one_exactly_matched")
    for record in matched:
        qid, db_id = record["qid"], record["db_id"]
        if qid not in labels or qid not in ranks or labels[qid]["db_id"] != db_id or ranks[qid]["db_id"] != db_id:
            raise AuditStop("STOP_LABEL_ALIGNMENT", "question_id_database_mapping_mismatch")

    if args.stage == "smoke":
        sample = selected_smoke(matched)
    else:
        if not args.smoke_run_dir:
            raise AuditStop("STOP_SMOKE_GATE", "full_requires_registered_smoke_run_directory")
        smoke_dir = Path(args.smoke_run_dir)
        smoke_summary = read_json(smoke_dir / "summary.json")
        smoke_receipt = read_json(smoke_dir / "run_receipt_private.json")
        if smoke_summary.get("status") != "SMOKE_PASS" or smoke_summary.get("gates", {}).get("all_gates_pass") is not True:
            raise AuditStop("STOP_SMOKE_GATE", "registered_smoke_did_not_pass")
        current_smoke = selected_smoke(matched)
        current_keys_hash = hashlib.sha256(json.dumps([f"{r['db_id']}/{r['qid']}" for r in current_smoke], separators=(",", ":")).encode()).hexdigest()
        if smoke_receipt.get("smoke_keys_sha256") != current_keys_hash:
            raise AuditStop("STOP_SMOKE_GATE", "smoke_selection_fingerprint_mismatch")
        if smoke_receipt.get("code_sha256") != sha256_file(Path(__file__).resolve()) or smoke_receipt.get("input_sha256") != hashes:
            raise AuditStop("STOP_SMOKE_GATE", "smoke_code_or_input_fingerprint_mismatch")
        smoke_qids = {record["qid"] for record in current_smoke}
        sample = [record for record in matched if record["qid"] not in smoke_qids]
        if len(sample) != EXPECTED_CORRECTED_ROWS - SMOKE_SIZE:
            raise AuditStop("STOP_SMOKE_GATE", "full_sample_size_after_smoke_exclusion_mismatch")

    catalog_raw = build_catalog(schema_rows)
    catalog = {db_id: {**value, "db_id": db_id} for db_id, value in catalog_raw.items()}
    parser_counts = Counter()
    records = []
    exact_archive_rows = 0
    baseline_parity_count = 0
    for record in sample:
        qid, db_id = record["qid"], record["db_id"]
        archived = labels[qid]
        rank_row = ranks[qid]
        original_parsed = extract_labels(str(record["original"].get("SQL", "")), db_id, catalog_raw)
        corrected_parsed = extract_labels(str(record["corrected"].get("SQL", "")), db_id, catalog_raw)
        parser_counts["original_parse_ok"] += int(original_parsed["parse_ok"])
        parser_counts["corrected_parse_ok"] += int(corrected_parsed["parse_ok"])
        parser_counts["original_nonempty_tables"] += int(bool(original_parsed["table_ids"]))
        parser_counts["corrected_nonempty_tables"] += int(bool(corrected_parsed["table_ids"]))
        parser_counts["original_column_eligible"] += int(original_parsed["column_eligible"])
        parser_counts["corrected_column_eligible"] += int(corrected_parsed["column_eligible"])
        parser_counts["original_wildcards"] += original_parsed["wildcard_count"]
        parser_counts["corrected_wildcards"] += corrected_parsed["wildcard_count"]
        parser_counts["original_unresolved_tables"] += original_parsed["unresolved_table_count"]
        parser_counts["corrected_unresolved_tables"] += corrected_parsed["unresolved_table_count"]
        for reason, count in original_parsed["unresolved_column_counts"].items():
            parser_counts[f"original_unresolved_column_{reason}"] += count
        for reason, count in corrected_parsed["unresolved_column_counts"].items():
            parser_counts[f"corrected_unresolved_column_{reason}"] += count
        original_labels = {
            "table_ids": original_parsed["table_ids"],
            "column_ids": original_parsed["column_ids"],
            "column_eligible": original_parsed["column_eligible"],
        }
        corrected_labels = {
            "table_ids": corrected_parsed["table_ids"],
            "column_ids": corrected_parsed["column_ids"],
            "column_eligible": corrected_parsed["column_eligible"],
        }
        archived_exact = (
            original_labels["table_ids"] == archived["table_ids"]
            and original_labels["column_ids"] == archived["column_ids"]
            and original_labels["column_eligible"] == archived["column_eligible"]
        )
        exact_archive_rows += int(archived_exact)
        baseline_parity = archived_baseline_parity(archived, rank_row)
        baseline_parity_count += int(baseline_parity)
        for candidate_id in original_labels["table_ids"] + original_labels["column_ids"] + corrected_labels["table_ids"] + corrected_labels["column_ids"]:
            if candidate_id not in node_ids:
                raise AuditStop("STOP_CANDIDATE_ALIGNMENT", "parsed_label_not_present_in_frozen_p1_6_nodes")
        original_metrics = evaluate_labels(original_labels, rank_row)
        corrected_metrics = evaluate_labels(corrected_labels, rank_row)
        records.append({
            "qid": qid,
            "db_id": db_id,
            "archived_labels": archived,
            "original_labels": original_labels,
            "corrected_labels": corrected_labels,
            "original_parsed": original_parsed,
            "corrected_parsed": corrected_parsed,
            "historical_label_exact": archived_exact,
            "baseline_parity": baseline_parity,
            "rank_row": rank_row,
            "original_metrics": original_metrics,
            "corrected_metrics": corrected_metrics,
        })

    n = len(records)
    rate = lambda key: safe_ratio(parser_counts[key], n)
    checks = {
        "exact_one_to_one_match_all_498": len(matched) == EXPECTED_CORRECTED_ROWS,
        "smoke_or_full_sample_size": n == (SMOKE_SIZE if args.stage == "smoke" else EXPECTED_CORRECTED_ROWS - SMOKE_SIZE),
        "sqlglot_version": sqlglot.__version__ == PARSER_VERSION,
        "original_parse_rate_at_least_98_percent": (rate("original_parse_ok") or 0.0) >= MIN_RATE,
        "corrected_parse_rate_at_least_98_percent": (rate("corrected_parse_ok") or 0.0) >= MIN_RATE,
        "original_nonempty_table_labels_at_least_98_percent": (rate("original_nonempty_tables") or 0.0) >= MIN_RATE,
        "corrected_nonempty_table_labels_at_least_98_percent": (rate("corrected_nonempty_tables") or 0.0) >= MIN_RATE,
        "original_column_eligibility_at_least_98_percent": (rate("original_column_eligible") or 0.0) >= MIN_RATE,
        "corrected_column_eligibility_at_least_98_percent": (rate("corrected_column_eligible") or 0.0) >= MIN_RATE,
        "historical_label_compatibility_at_least_98_percent": exact_archive_rows / n >= MIN_RATE,
        "frozen_p1_6_baseline_recomputed_for_sample": baseline_parity_count == n,
    }
    if args.stage == "smoke":
        checks["smoke_original_labels_match_frozen_p1_exactly"] = exact_archive_rows == SMOKE_SIZE
        checks["smoke_topk_and_complete_budget_parity_exact"] = baseline_parity_count == SMOKE_SIZE
    checks["all_gates_pass"] = all(checks.values())

    rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    elapsed = time.monotonic() - started
    checks["within_wall_budget"] = elapsed <= MAX_WALL_SECONDS
    checks["within_rss_budget"] = rss_bytes <= MAX_RSS_BYTES
    checks["all_gates_pass"] = all(value for key, value in checks.items() if key != "all_gates_pass")
    if not checks["all_gates_pass"]:
        status = "SMOKE_STOP_GATE" if args.stage == "smoke" else "FULL_STOP_GATE"
    else:
        status = "SMOKE_PASS" if args.stage == "smoke" else "FULL_COMPLETED"

    summary = public_summary(args.stage, args.run_id, records, checks, hashes, elapsed, rss_bytes)
    summary["status"] = status
    summary["parser_and_label_coverage"].update({
        "original_nonempty_table_labels": parser_counts["original_nonempty_tables"],
        "corrected_nonempty_table_labels": parser_counts["corrected_nonempty_tables"],
        "original_parse_ok": parser_counts["original_parse_ok"],
        "corrected_parse_ok": parser_counts["corrected_parse_ok"],
        "original_column_eligible": parser_counts["original_column_eligible"],
        "corrected_column_eligible": parser_counts["corrected_column_eligible"],
        "historical_exact_label_rows": exact_archive_rows,
        "frozen_p1_6_baseline_parity_rows": baseline_parity_count,
        "wildcard_references_original_corrected": [parser_counts["original_wildcards"], parser_counts["corrected_wildcards"]],
    })
    write_json(out_dir / "summary.json", round_floats(summary))
    with (out_dir / "per_question_private.jsonl").open("w", encoding="utf-8") as stream:
        for payload in private_rows_payload(records):
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    smoke_digest = None
    if args.stage == "smoke":
        smoke_digest = hashlib.sha256(
            json.dumps([f"{record['db_id']}/{record['qid']}" for record in selected_smoke(matched)], separators=(",", ":")).encode()
        ).hexdigest()
    receipt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "stage": args.stage,
        "status": status,
        "source_repository_commit": EXPECTED_SOURCE_COMMIT,
        "project_git_commit": git["commit"],
        "project_worktree": git["worktree"],
        "code_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(Path(args.config).resolve()),
        "input_sha256": hashes,
        "smoke_keys_sha256": smoke_digest,
        "argv": sys.argv,
        "environment": summary["environment"],
        "runtime": summary["runtime"],
        "private_input_rows": n,
        "created_at_utc": utc_now(),
    }
    write_json(out_dir / "run_receipt_private.json", receipt)
    print(json.dumps({
        "run_id": args.run_id,
        "stage": args.stage,
        "status": status,
        "questions": n,
        "exact_matches": len(matched),
        "historical_label_compatibility_rate": summary["parser_and_label_coverage"]["original_exact_label_compatibility_to_frozen_p1_rate"],
        "gates_pass": checks["all_gates_pass"],
        "wall_seconds": round(elapsed, 3),
        "peak_rss_bytes": rss_bytes,
        "api_calls": 0,
        "model_calls": 0,
        "sql_execution_count": 0,
        "summary_path": str(out_dir / "summary.json"),
    }, ensure_ascii=False))
    return 0 if checks["all_gates_pass"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", choices=("smoke", "full"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--original-json", required=True)
    parser.add_argument("--schema-json", required=True)
    parser.add_argument("--corrected-json", required=True)
    parser.add_argument("--archived-labels", required=True)
    parser.add_argument("--p1-rows", required=True)
    parser.add_argument("--node-manifest", required=True)
    parser.add_argument("--p1-aggregate", required=True)
    parser.add_argument("--smoke-run-dir")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        sys.exit(run(arguments))
    except AuditStop as exc:
        error_dir = Path(arguments.output_dir)
        if not error_dir.exists():
            error_dir.mkdir(parents=True, exist_ok=False)
        write_json(error_dir / "failure_receipt.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": arguments.run_id,
            "stage": arguments.stage,
            "status": exc.status,
            "reason_code": str(exc),
            "exception_type": type(exc).__name__,
            "created_at_utc": utc_now(),
        })
        print(json.dumps({"run_id": arguments.run_id, "stage": arguments.stage, "status": exc.status, "reason_code": str(exc)}, ensure_ascii=False))
        sys.exit(2)
