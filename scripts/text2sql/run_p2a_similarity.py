#!/usr/bin/env python3
"""Run the frozen S0 Cosine, S1 BM25, and S2 RRF BIRD-dev comparison."""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MAX_CPU_SECONDS = 1800
MAX_RSS_GIB = 16
MAX_THREADS = 8
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K0 = 60
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261018
TOP_K = {"table": (5, 10), "column": (5, 10, 20)}
BUDGETS = (512, 1024, 2048)
METHODS = ("S0_cosine", "S1_bm25", "S2_rrf")
P1_6_COMMIT = "d948d462f9407a18f4a48c85a76380d54f865cb2"
P1_6_RUN_ID = "p1_6_full1534_20261018_01"
EXPECTED_COUNTS = {
    "questions": 1534,
    "databases": 11,
    "nodes": 873,
    "tables": 75,
    "columns": 798,
    "column_eligible": 1460,
}

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_6_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_6_rebaseline.py"
P1_6_PROTOCOL = REPO_ROOT / "docs/research/text2sql/plans/p1_6_smoke_recovery_then_p2a_20261017.md"
P2A_PROTOCOL = REPO_ROOT / "docs/research/text2sql/plans/p2a_similarity_20261018.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def package_version(name: str) -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def run_output(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else f"unavailable: {result.stderr.strip()}"


def resource_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu_snapshot_not_used": run_output([
            "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]),
        "free_h": run_output(["free", "-h"]),
        "cpu_threads": os.cpu_count(),
        "disk": run_output(["df", "-h", str(REPO_ROOT)]),
    }


def load_p1_6_module() -> Any:
    spec = importlib.util.spec_from_file_location("p1_6_for_p2a", P1_6_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load frozen P1.6 helper: {P1_6_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--p1-6-run-dir", type=Path, required=True)
    parser.add_argument("--smoke-dir", type=Path)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--p1-5-run-dir", type=Path, required=True)
    return parser.parse_args()


def validate_p1_6_inputs(args: argparse.Namespace, p1: Any) -> tuple[dict[str, Any], Any, np.ndarray, np.ndarray]:
    run_dir = args.p1_6_run_dir.resolve()
    required = [
        run_dir / "run_start.json",
        run_dir / "aggregate_summary.json",
        run_dir / "input_manifest_private.json",
        run_dir / "ordered_node_manifest.json",
        run_dir / "embedding_cache_private.npz",
    ]
    if any(not path.is_file() for path in required):
        raise FileNotFoundError("P1.6 completed Full artifacts are incomplete")
    run_start = json.loads(required[0].read_text(encoding="utf-8"))
    summary = json.loads(required[1].read_text(encoding="utf-8"))
    if run_start.get("run_id") != P1_6_RUN_ID or run_start.get("mode") != "full" or run_start.get("state") != "completed":
        raise RuntimeError("P1.6 reference run metadata is not the registered completed Full run")
    if run_start.get("source", {}).get("published_commit") != P1_6_COMMIT:
        raise RuntimeError("P1.6 reference run came from an unexpected source commit")
    if summary.get("p1_6_gate") != "PASS" or summary.get("gate") != "PASS":
        raise RuntimeError("P1.6 Full Gate is not PASS")
    if run_start.get("result_summary_sha256") != sha256_file(required[1]):
        raise RuntimeError("P1.6 aggregate summary hash does not match run metadata")
    if run_start.get("input_manifest_private_sha256") != sha256_file(required[2]):
        raise RuntimeError("P1.6 input manifest hash does not match run metadata")
    if run_start.get("ordered_node_manifest_sha256") != sha256_file(required[3]):
        raise RuntimeError("P1.6 ordered node manifest hash does not match run metadata")
    if run_start.get("source", {}).get("worktree_status") != "clean":
        raise RuntimeError("P1.6 was not run from a clean source tree")

    _, common = p1.load_common(args.legacy_root, args.dataset_root, args.model_path)
    prepared = p1.prepare_inputs(common)
    validation_args = argparse.Namespace(
        legacy_root=args.legacy_root,
        model_path=args.model_path,
        previous_run_dir=args.previous_run_dir,
        p1_5_run_dir=args.p1_5_run_dir,
    )
    input_record = p1.validate_inputs(prepared, common, validation_args)
    _, current_node_manifest, current_manifest_bytes, current_manifest_hash = p1.canonicalize_input_record(input_record)
    if input_record.get("counts") != EXPECTED_COUNTS:
        raise RuntimeError(f"P2a frozen input counts differ: {input_record.get('counts')}")
    if current_manifest_hash != run_start.get("input_manifest_private_sha256"):
        raise RuntimeError("Current frozen input manifest differs from P1.6")
    if current_manifest_bytes != required[2].read_bytes():
        raise RuntimeError("Current canonical input manifest bytes differ from P1.6")
    if current_node_manifest != json.loads(required[3].read_text(encoding="utf-8")):
        raise RuntimeError("Current ordered node manifest differs from P1.6")
    if input_record.get("ordered_node_manifest_sha256") != run_start.get("ordered_node_manifest_content_sha256"):
        raise RuntimeError("Current ordered node manifest digest differs from P1.6")

    cache_path = required[4]
    encoding = summary.get("encoding", {})
    if sha256_file(cache_path) != encoding.get("private_npz_sha256"):
        raise RuntimeError("P1.6 private cache hash differs from the aggregate summary")
    with np.load(cache_path, allow_pickle=False) as cache:
        query_vectors = np.ascontiguousarray(cache["query_vectors"], dtype=np.float32)
        node_vectors = np.ascontiguousarray(cache["node_vectors"], dtype=np.float32)
    if query_vectors.shape != (1534, 1024) or node_vectors.shape != (873, 1024):
        raise RuntimeError("P1.6 cache has unexpected vector shapes")
    if not np.isfinite(query_vectors).all() or not np.isfinite(node_vectors).all():
        raise RuntimeError("P1.6 cache contains non-finite values")
    if p1.sha256_bytes(query_vectors.tobytes()) != encoding.get("query_vectors_sha256"):
        raise RuntimeError("P1.6 query vector hash mismatch")
    if p1.sha256_bytes(node_vectors.tobytes()) != encoding.get("node_vectors_sha256"):
        raise RuntimeError("P1.6 node vector hash mismatch")
    return {"run_start": run_start, "summary": summary, "input_record": input_record, "input_manifest_sha256": current_manifest_hash}, prepared, query_vectors, node_vectors


def tokenize(text: str) -> list[str]:
    normalized = text.casefold().replace("_", " ")
    return [token for token in re.findall(r"[A-Za-z0-9]+", normalized) if len(token) > 1]


def build_bm25_corpus(nodes: list[Any]) -> dict[str, Any]:
    tokenized = [tokenize(node.text) for node in nodes]
    frequencies = [collections.Counter(document) for document in tokenized]
    document_frequency: collections.Counter[str] = collections.Counter()
    for document in tokenized:
        document_frequency.update(set(document))
    doc_count = len(nodes)
    lengths = np.asarray([len(document) for document in tokenized], dtype=np.float64)
    average_length = float(np.mean(lengths)) if len(lengths) else 0.0
    inverse_document_frequency = {
        token: math.log1p((doc_count - df + 0.5) / (df + 0.5))
        for token, df in document_frequency.items()
    }
    return {
        "tokens": tokenized,
        "term_frequencies": frequencies,
        "lengths": lengths,
        "average_length": average_length,
        "idf": inverse_document_frequency,
        "documents": doc_count,
    }


def bm25_scores(query_text: str, corpus: dict[str, Any]) -> np.ndarray:
    query_tokens = tokenize(query_text)
    lengths = corpus["lengths"]
    average_length = corpus["average_length"]
    if average_length <= 0:
        return np.zeros(len(lengths), dtype=np.float64)
    scores = np.zeros(len(lengths), dtype=np.float64)
    for index, term_counts in enumerate(corpus["term_frequencies"]):
        doc_length = float(lengths[index])
        normalizer = BM25_K1 * (1.0 - BM25_B + BM25_B * doc_length / average_length)
        for token in query_tokens:
            tf = term_counts.get(token, 0)
            if tf:
                idf = corpus["idf"].get(token, 0.0)
                scores[index] += idf * tf * (BM25_K1 + 1.0) / (tf + normalizer)
    if not np.isfinite(scores).all():
        raise RuntimeError("BM25 produced a non-finite candidate score")
    return scores


def stable_order64(scores: np.ndarray, node_ids: list[str]) -> np.ndarray:
    return np.lexsort((np.asarray(node_ids, dtype=str), -np.asarray(scores, dtype=np.float64)))


def method_order(
    method: str,
    positions: list[int],
    dense_scores: np.ndarray,
    sparse_scores: np.ndarray,
    node_ids: list[str],
) -> tuple[list[int], np.ndarray]:
    if not positions:
        return [], np.asarray([], dtype=np.float64)
    ids = [node_ids[position] for position in positions]
    if method == "S0_cosine":
        values = np.asarray(dense_scores[positions], dtype=np.float32)
        offsets = p1_module.stable_order(values, ids)
    elif method == "S1_bm25":
        values = np.asarray(sparse_scores[positions], dtype=np.float64)
        offsets = stable_order64(values, ids)
    else:
        dense_offsets = p1_module.stable_order(np.asarray(dense_scores[positions], dtype=np.float32), ids)
        sparse_offsets = stable_order64(np.asarray(sparse_scores[positions], dtype=np.float64), ids)
        dense_ranks = np.empty(len(positions), dtype=np.int64)
        sparse_ranks = np.empty(len(positions), dtype=np.int64)
        dense_ranks[dense_offsets] = np.arange(1, len(positions) + 1)
        sparse_ranks[sparse_offsets] = np.arange(1, len(positions) + 1)
        values = 1.0 / (RRF_K0 + dense_ranks) + 1.0 / (RRF_K0 + sparse_ranks)
        offsets = stable_order64(values, ids)
    ordered_positions = [positions[int(offset)] for offset in offsets]
    ordered_values = np.asarray(values[offsets], dtype=np.float64)
    return ordered_positions, ordered_values


def evaluate(
    prepared: dict[str, Any],
    query_vectors: np.ndarray,
    node_vectors: np.ndarray,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    query_unit, _ = p1_module.normalized_vectors(query_vectors)
    node_unit, _ = p1_module.normalized_vectors(node_vectors)
    nodes_by_db: dict[str, list[int]] = collections.defaultdict(list)
    for index, node in enumerate(nodes):
        nodes_by_db[node.db_id].append(index)
    schema_tokens = {
        db_id: int(sum(nodes[index].token_count for index in indexes))
        for db_id, indexes in nodes_by_db.items()
    }
    non_saturated_dbs = {db_id for db_id, count in schema_tokens.items() if count > 2048}
    bm25_by_db = {
        db_id: build_bm25_corpus([nodes[index] for index in indexes])
        for db_id, indexes in nodes_by_db.items()
    }
    rows: list[dict[str, Any]] = []
    tie_counts = {
        method: {view: {"questions_with_ties": 0, "tie_groups": 0, "extra_candidates": 0} for view in ("all", "table", "column")}
        for method in METHODS
    }
    boundary_gaps: dict[str, dict[str, list[float]]] = {
        method: collections.defaultdict(list) for method in METHODS
    }

    for query_index, question in enumerate(questions):
        db_id = question["db_id"]
        candidate_indexes = nodes_by_db[db_id]
        local_ids = [nodes[index].node_id for index in candidate_indexes]
        dense_scores = np.asarray(query_unit[query_index] @ node_unit[candidate_indexes].T, dtype=np.float32)
        if not np.isfinite(dense_scores).all():
            raise RuntimeError("Dense cosine produced a non-finite candidate score")
        sparse_scores = bm25_scores(question["text"], bm25_by_db[db_id])
        table_positions = [local for local, global_index in enumerate(candidate_indexes) if nodes[global_index].node_type == "table"]
        column_positions = [local for local, global_index in enumerate(candidate_indexes) if nodes[global_index].node_type == "column"]
        all_positions = list(range(len(candidate_indexes)))
        label = question["label"]
        gold_tables = tuple(label["gold_table_ids"])
        gold_columns = tuple(label["gold_column_ids"]) if label["column_eligible"] else ()
        method_rows: dict[str, Any] = {}

        for method in METHODS:
            all_order, all_values = method_order(method, all_positions, dense_scores, sparse_scores, local_ids)
            table_order, table_values = method_order(method, table_positions, dense_scores, sparse_scores, local_ids)
            column_order, column_values = method_order(method, column_positions, dense_scores, sparse_scores, local_ids)
            view_values = {"all": (all_positions, all_values), "table": (table_positions, table_values), "column": (column_positions, column_values)}
            for view, (positions, values) in view_values.items():
                _, counts = np.unique(values, return_counts=True)
                groups = int(np.count_nonzero(counts > 1))
                tie_counts[method][view]["questions_with_ties"] += int(groups > 0)
                tie_counts[method][view]["tie_groups"] += groups
                tie_counts[method][view]["extra_candidates"] += int(np.sum(counts[counts > 1] - 1)) if groups else 0
            for kind, order, values, ks in (
                ("table", table_order, table_values, TOP_K["table"]),
                ("column", column_order, column_values, TOP_K["column"]),
            ):
                if kind == "column" and not label["column_eligible"]:
                    continue
                for k in ks:
                    if len(order) > k:
                        boundary_gaps[method][f"{kind}_r{k}"].append(float(values[k - 1] - values[k]))

            def typed_metrics(order: list[int], gold_ids: tuple[str, ...], ks: tuple[int, ...]) -> dict[str, Any]:
                retrieved: dict[str, list[str]] = {}
                hits_by_k: dict[str, int] = {}
                recall_by_k: dict[str, float] = {}
                precision_by_k: dict[str, float] = {}
                ranks = {local_ids[position]: rank for rank, position in enumerate(order, start=1)}
                gold_ranks = sorted(ranks[node_id] for node_id in gold_ids)
                for k in ks:
                    ids = [local_ids[position] for position in order[:k]]
                    hits = sum(rank <= k for rank in gold_ranks)
                    key = str(k)
                    retrieved[key] = ids
                    hits_by_k[key] = hits
                    recall_by_k[key] = hits / len(gold_ids) if gold_ids else 0.0
                    precision_by_k[key] = hits / len(ids) if ids else 0.0
                return {
                    "gold_count": len(gold_ids),
                    "gold_ranks": gold_ranks,
                    "topk_ids": retrieved,
                    "hits": hits_by_k,
                    "recall": recall_by_k,
                    "precision": precision_by_k,
                    "mrr": 1.0 / gold_ranks[0] if gold_ranks else None,
                    "map": sum(index / rank for index, rank in enumerate(gold_ranks, start=1)) / len(gold_ranks) if gold_ranks else None,
                }

            table_result = typed_metrics(table_order, gold_tables, TOP_K["table"])
            column_result = typed_metrics(column_order, gold_columns, TOP_K["column"]) if label["column_eligible"] else None
            budget_result = None
            if label["column_eligible"]:
                gold_all = set(gold_tables) | set(gold_columns)
                budget_result = {}
                for budget in BUDGETS:
                    remaining = budget
                    selected: list[str] = []
                    used = 0
                    for position in all_order:
                        node = nodes[candidate_indexes[position]]
                        if node.token_count <= remaining:
                            selected.append(node.node_id)
                            remaining -= node.token_count
                            used += node.token_count
                    hits = len(gold_all.intersection(selected))
                    budget_result[str(budget)] = {
                        "selected_ids": selected,
                        "tokens_used": used,
                        "returned_elements": len(selected),
                        "retrieved_gold_elements": hits,
                        "gold_elements": len(gold_all),
                        "recall": hits / len(gold_all) if gold_all else 0.0,
                        "precision": hits / len(selected) if selected else 0.0,
                        "complete": int(hits == len(gold_all)),
                        "gold_elements_per_1000_tokens": hits * 1000.0 / used if used else 0.0,
                    }
            method_rows[method] = {"table": table_result, "column": column_result, "budgets": budget_result}
        rows.append({
            "question_id": int(question["question_id"]),
            "db_id": db_id,
            "column_eligible": bool(label["column_eligible"]),
            "gold_column_ids": list(gold_columns),
            "non_saturated_database": db_id in non_saturated_dbs,
            "methods": method_rows,
        })

    return summarize(rows, nodes, schema_tokens, non_saturated_dbs, tie_counts, boundary_gaps), rows


def mean(values: list[float]) -> float | None:
    return float(np.mean(np.asarray(values, dtype=np.float64))) if values else None


def metric_summary(
    rows: list[dict[str, Any]],
    method: str,
    area: str,
    metric_type: str,
    metric: str,
    key: str | None = None,
    subset: bool = False,
) -> dict[str, Any]:
    eligible = [
        row for row in rows
        if (not subset or row["non_saturated_database"])
        and (metric_type != "column" or row["column_eligible"])
    ]
    values_by_db: dict[str, list[float]] = collections.defaultdict(list)
    total_hits = total_gold = 0
    for row in eligible:
        result = row["methods"][method][area]
        if result is None:
            continue
        if area == "budgets":
            budget_result = result[key]
            value = budget_result[metric]
        else:
            value = result[metric] if key is None else result[metric][key]
        if value is None:
            continue
        values_by_db[row["db_id"]].append(float(value))
        if area == "budgets" and metric == "recall":
            total_hits += int(budget_result["retrieved_gold_elements"])
            total_gold += int(budget_result["gold_elements"])
        elif metric == "recall" and key is not None:
            total_hits += int(result["hits"][key])
            total_gold += int(result["gold_count"])
    flat = [value for values in values_by_db.values() for value in values]
    database_means = [float(np.mean(values)) for values in values_by_db.values() if values]
    output: dict[str, Any] = {
        "query_macro": mean(flat),
        "database_macro": mean(database_means),
        "questions": len(flat),
        "databases": len(values_by_db),
    }
    if metric == "recall" and key is not None:
        output["element_micro"] = total_hits / total_gold if total_gold else None
        output["retrieved_gold_elements"] = total_hits
        output["gold_elements"] = total_gold
    return output


def summarize(
    rows: list[dict[str, Any]],
    nodes: list[Any],
    schema_tokens: dict[str, int],
    non_saturated_dbs: set[str],
    tie_counts: dict[str, Any],
    boundary_gaps: dict[str, Any],
) -> dict[str, Any]:
    per_database: dict[str, Any] = {}
    all_dbs = sorted(schema_tokens)
    for db_id in all_dbs:
        db_rows = [row for row in rows if row["db_id"] == db_id]
        eligible_rows = [row for row in db_rows if row["column_eligible"]]
        tables = sum(node.db_id == db_id and node.node_type == "table" for node in nodes)
        columns = sum(node.db_id == db_id and node.node_type == "column" for node in nodes)
        db_summary: dict[str, Any] = {
            "questions": len(db_rows),
            "column_eligible_questions": len(eligible_rows),
            "candidate_tables": tables,
            "candidate_columns": columns,
            "schema_tokens": schema_tokens[db_id],
            "non_saturated_at_2048": db_id in non_saturated_dbs,
            "methods": {},
        }
        for method in METHODS:
            method_summary: dict[str, Any] = {"table": {}, "column": {}, "budgets": {}}
            for k in TOP_K["table"]:
                method_summary["table"][f"recall@{k}"] = metric_summary(db_rows, method, "table", "table", "recall", str(k))
            for k in TOP_K["column"]:
                method_summary["column"][f"recall@{k}"] = metric_summary(db_rows, method, "column", "column", "recall", str(k))
                method_summary["column"][f"precision@{k}"] = metric_summary(db_rows, method, "column", "column", "precision", str(k))
            method_summary["column"]["mrr"] = metric_summary(db_rows, method, "column", "column", "mrr")
            method_summary["column"]["map"] = metric_summary(db_rows, method, "column", "column", "map")
            for budget in BUDGETS:
                method_summary["budgets"][str(budget)] = {}
                for metric in ("recall", "precision", "complete", "gold_elements_per_1000_tokens", "tokens_used", "returned_elements"):
                    method_summary["budgets"][str(budget)][metric] = metric_summary(db_rows, method, "budgets", "column", metric, str(budget))
            db_summary["methods"][method] = method_summary
        per_database[db_id] = db_summary

    global_summary: dict[str, Any] = {}
    non_saturated_summary: dict[str, Any] = {}
    for method in METHODS:
        method_global: dict[str, Any] = {"table": {}, "column": {}, "budgets": {}}
        method_subset: dict[str, Any] = {"column": {}, "budgets": {}}
        for k in TOP_K["table"]:
            method_global["table"][f"recall@{k}"] = metric_summary(rows, method, "table", "table", "recall", str(k))
        for k in TOP_K["column"]:
            method_global["column"][f"recall@{k}"] = metric_summary(rows, method, "column", "column", "recall", str(k))
            method_global["column"][f"precision@{k}"] = metric_summary(rows, method, "column", "column", "precision", str(k))
            method_subset["column"][f"recall@{k}"] = metric_summary(rows, method, "column", "column", "recall", str(k), subset=True)
            method_subset["column"][f"precision@{k}"] = metric_summary(rows, method, "column", "column", "precision", str(k), subset=True)
        method_global["column"]["mrr"] = metric_summary(rows, method, "column", "column", "mrr")
        method_global["column"]["map"] = metric_summary(rows, method, "column", "column", "map")
        method_subset["column"]["mrr"] = metric_summary(rows, method, "column", "column", "mrr", subset=True)
        method_subset["column"]["map"] = metric_summary(rows, method, "column", "column", "map", subset=True)
        for budget in BUDGETS:
            method_global["budgets"][str(budget)] = {}
            method_subset["budgets"][str(budget)] = {}
            for metric in ("recall", "precision", "complete", "gold_elements_per_1000_tokens", "tokens_used", "returned_elements"):
                method_global["budgets"][str(budget)][metric] = metric_summary(rows, method, "budgets", "column", metric, str(budget))
                method_subset["budgets"][str(budget)][metric] = metric_summary(rows, method, "budgets", "column", metric, str(budget), subset=True)
        global_summary[method] = method_global
        non_saturated_summary[method] = method_subset

    return {
        "questions": len(rows),
        "databases": len(all_dbs),
        "table_question_denominator": len(rows),
        "column_question_denominator": sum(row["column_eligible"] for row in rows),
        "non_saturated_2048": {
            "databases": sorted(non_saturated_dbs),
            "database_count": len(non_saturated_dbs),
            "questions": sum(row["db_id"] in non_saturated_dbs for row in rows),
            "column_question_denominator": sum(row["db_id"] in non_saturated_dbs and row["column_eligible"] for row in rows),
            "methods": non_saturated_summary,
        },
        "global": global_summary,
        "per_database": per_database,
        "tie_diagnostics": tie_counts,
        "ranking_boundary_gaps": {
            method: {key: p1_module.qstats(values) for key, values in sorted(boundary_gaps[method].items())}
            for method in METHODS
        },
        "question_rows_digest_sha256": p1_module.json_digest(rows),
    }


def paired_comparison(rows: list[dict[str, Any]], method: str, subset: bool = False) -> dict[str, Any]:
    per_database: dict[str, dict[str, Any]] = collections.defaultdict(lambda: {
        "column_r10_questions_rescued": 0,
        "column_r10_questions_damaged": 0,
        "column_r10_gold_elements_rescued": 0,
        "column_r10_gold_elements_damaged": 0,
        "column_r10_net_gold_hit_delta": 0,
        "budget2048_complete_rescued": 0,
        "budget2048_complete_damaged": 0,
        "column_eligible_questions": 0,
    })
    total = collections.Counter()
    for row in rows:
        if not row["column_eligible"] or (subset and not row["non_saturated_database"]):
            continue
        baseline = row["methods"]["S0_cosine"]
        candidate = row["methods"][method]
        baseline_gold_ids = set(baseline["column"]["topk_ids"]["10"])
        candidate_gold_ids = set(candidate["column"]["topk_ids"]["10"])
        baseline_hit_count = int(baseline["column"]["hits"]["10"])
        candidate_hit_count = int(candidate["column"]["hits"]["10"])
        gold_ids = set(row["gold_column_ids"])
        rescued_elements = len((candidate_gold_ids & gold_ids) - (baseline_gold_ids & gold_ids))
        damaged_elements = len((baseline_gold_ids & gold_ids) - (candidate_gold_ids & gold_ids))
        base_complete = int(baseline["budgets"]["2048"]["complete"])
        new_complete = int(candidate["budgets"]["2048"]["complete"])
        record = per_database[row["db_id"]]
        record["column_eligible_questions"] += 1
        record["column_r10_questions_rescued"] += int(candidate_hit_count > baseline_hit_count)
        record["column_r10_questions_damaged"] += int(candidate_hit_count < baseline_hit_count)
        record["column_r10_gold_elements_rescued"] += rescued_elements
        record["column_r10_gold_elements_damaged"] += damaged_elements
        record["column_r10_net_gold_hit_delta"] += candidate_hit_count - baseline_hit_count
        record["budget2048_complete_rescued"] += int(base_complete == 0 and new_complete == 1)
        record["budget2048_complete_damaged"] += int(base_complete == 1 and new_complete == 0)
        total["column_r10_questions_rescued"] += int(candidate_hit_count > baseline_hit_count)
        total["column_r10_questions_damaged"] += int(candidate_hit_count < baseline_hit_count)
        total["column_r10_gold_elements_rescued"] += rescued_elements
        total["column_r10_gold_elements_damaged"] += damaged_elements
        total["column_r10_net_gold_hit_delta"] += candidate_hit_count - baseline_hit_count
        total["budget2048_complete_rescued"] += int(base_complete == 0 and new_complete == 1)
        total["budget2048_complete_damaged"] += int(base_complete == 1 and new_complete == 0)
        total["column_eligible_questions"] += 1
    return {"subset": "non_saturated_2048" if subset else "all_column_eligible", "total": dict(total), "per_database": dict(per_database)}


def cluster_bootstrap_ci(
    per_database: dict[str, Any],
    method: str,
    metric_path: tuple[str, ...],
    baseline: str = "S0_cosine",
    subset: bool = False,
) -> dict[str, float | int]:
    selected = [
        (db_id, stats) for db_id, stats in sorted(per_database.items())
        if stats["column_eligible_questions"] > 0 and (not subset or stats["non_saturated_at_2048"])
    ]
    if not selected:
        raise RuntimeError("No database clusters are available for the registered bootstrap")
    deltas: list[float] = []
    weights: list[int] = []
    for _, stats in selected:
        base_value: Any = stats["methods"][baseline]
        new_value: Any = stats["methods"][method]
        for component in metric_path:
            base_value = base_value[component]
            new_value = new_value[component]
        deltas.append(float(new_value["query_macro"] - base_value["query_macro"]))
        weights.append(int(stats["column_eligible_questions"]))
    point = float(np.average(deltas, weights=weights))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    cluster_indices = rng.integers(0, len(selected), size=(BOOTSTRAP_DRAWS, len(selected)))
    delta_values = np.asarray(deltas, dtype=np.float64)
    cluster_weights = np.asarray(weights, dtype=np.float64)
    sampled_weights = cluster_weights[cluster_indices]
    sampled_deltas = delta_values[cluster_indices]
    draws = np.sum(sampled_weights * sampled_deltas, axis=1) / np.sum(sampled_weights, axis=1)
    low, high = np.quantile(draws, [0.025, 0.975])
    return {
        "database_clusters": len(selected),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "seed": BOOTSTRAP_SEED,
        "estimate_pp": point * 100.0,
        "ci95_low_pp": float(low * 100.0),
        "ci95_high_pp": float(high * 100.0),
    }


def db_deltas(summary: dict[str, Any], method: str, metric_path: tuple[str, ...], subset: bool = False) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for db_id, stats in summary["per_database"].items():
        if stats["column_eligible_questions"] == 0 or (subset and not stats["non_saturated_at_2048"]):
            continue
        base: Any = stats["methods"]["S0_cosine"]
        new: Any = stats["methods"][method]
        for part in metric_path:
            base = base[part]
            new = new[part]
        deltas[db_id] = float(new["query_macro"] - base["query_macro"])
    return deltas


def delta_values(summary: dict[str, Any], method: str, area: str, metric: str, key: str, subset: bool = False) -> dict[str, Any]:
    base = summary["non_saturated_2048"]["methods"]["S0_cosine"] if subset else summary["global"]["S0_cosine"]
    candidate = summary["non_saturated_2048"]["methods"][method] if subset else summary["global"][method]
    if area in ("table", "column"):
        metric_key = f"{metric}@{key}"
        base_value = base[area][metric_key]["query_macro"]
        candidate_value = candidate[area][metric_key]["query_macro"]
    else:
        base_value = base[area][key][metric]["query_macro"]
        candidate_value = candidate[area][key][metric]["query_macro"]
    return {"baseline": base_value, "candidate": candidate_value, "delta_pp": (candidate_value - base_value) * 100.0}


def decision_and_uncertainty(summary: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method in ("S1_bm25", "S2_rrf"):
        subset_r10 = delta_values(summary, method, "column", "recall", "10", subset=True)
        subset_complete = delta_values(summary, method, "budgets", "complete", "2048", subset=True)
        all_table_r10 = delta_values(summary, method, "table", "recall", "10", subset=False)
        r10_db = db_deltas(summary, method, ("column", "recall@10"), subset=True)
        complete_db = db_deltas(summary, method, ("budgets", "2048", "complete"), subset=True)
        r10_signal = subset_r10["delta_pp"] >= 2.0 and sum(value > 0 for value in r10_db.values()) >= 3
        complete_signal = subset_complete["delta_pp"] >= 1.0 and sum(value > 0 for value in complete_db.values()) >= 3
        table_guard = all_table_r10["delta_pp"] >= -1.0
        result[method] = {
            "non_saturated_column_r10": subset_r10,
            "non_saturated_complete_2048": subset_complete,
            "all_questions_table_r10": all_table_r10,
            "non_saturated_column_r10_database_deltas_pp": {key: value * 100.0 for key, value in r10_db.items()},
            "non_saturated_complete_2048_database_deltas_pp": {key: value * 100.0 for key, value in complete_db.items()},
            "column_r10_threshold_and_direction_pass": r10_signal,
            "complete_2048_threshold_and_direction_pass": complete_signal,
            "table_r10_guard_pass": table_guard,
            "meets_exploratory_success_criteria": bool((r10_signal or complete_signal) and table_guard),
            "bootstrap_db_cluster_ci": {
                "all_column_r10": cluster_bootstrap_ci(summary["per_database"], method, ("column", "recall@10")),
                "non_saturated_column_r10": cluster_bootstrap_ci(summary["per_database"], method, ("column", "recall@10"), subset=True),
                "non_saturated_complete_2048": cluster_bootstrap_ci(summary["per_database"], method, ("budgets", "2048", "complete"), subset=True),
            },
        }
    any_signal = any(row["meets_exploratory_success_criteria"] for row in result.values())
    return {"decision": "signal_for_independent_database_validation" if any_signal else "no_go_stop_method_expansion", "comparisons": result}


def assert_s0_parity(rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> None:
    if len(rows) != len(baseline_rows):
        raise RuntimeError("S0 and P1.6 per-question row counts differ")
    for current, baseline in zip(rows, baseline_rows):
        method_row = current["methods"]["S0_cosine"]
        for kind in ("table", "column"):
            if kind == "column" and not current["column_eligible"]:
                if method_row["column"] is not None or baseline["column_topk_ids"] != {}:
                    raise RuntimeError("S0 column eligibility differs from P1.6")
                continue
            base_top = baseline[f"{kind}_topk_ids"]
            base_hits = baseline[f"{kind}_hits"]
            if method_row[kind]["topk_ids"] != base_top or method_row[kind]["hits"] != base_hits:
                raise RuntimeError(f"S0 {kind} ranks differ from P1.6 for a frozen question")
        if method_row["budgets"] is None or baseline["budgets"] is None:
            if method_row["budgets"] != baseline["budgets"]:
                raise RuntimeError("S0 budget eligibility differs from P1.6")
            continue
        for budget in map(str, BUDGETS):
            current_budget = method_row["budgets"][budget]
            baseline_budget = baseline["budgets"][budget]
            for field in ("selected_ids", "tokens_used", "returned_elements", "retrieved_gold_elements", "gold_elements", "recall", "precision", "complete"):
                if current_budget[field] != baseline_budget[field]:
                    raise RuntimeError(f"S0 budget field {field} differs from P1.6")


def prepare_active_inputs(prepared: dict[str, Any], query_vectors: np.ndarray, node_vectors: np.ndarray, mode: str) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    if mode == "full":
        return prepared, query_vectors, node_vectors
    questions = prepared["questions"][:5]
    active_dbs = {question["db_id"] for question in questions}
    selected_node_indices = [index for index, node in enumerate(prepared["nodes"]) if node.db_id in active_dbs]
    subset = dict(prepared)
    subset["questions"] = questions
    subset["nodes"] = [prepared["nodes"][index] for index in selected_node_indices]
    return subset, query_vectors[:5], node_vectors[selected_node_indices]


def run() -> None:
    global p1_module
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse output directory: {args.output_dir}")
    if args.mode == "full" and args.smoke_dir is None:
        raise RuntimeError("Full P2a run requires a completed P2a smoke directory")
    p1_module = load_p1_6_module()
    source = p1_module.assert_committed_source(args.expected_commit)
    if not P2A_PROTOCOL.is_file() or not P1_6_PROTOCOL.is_file():
        raise FileNotFoundError("A registered P1.6/P2a protocol file is missing")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cpu_started = time.process_time()
    run_start: dict[str, Any] = {
        "experiment_id": "p2a_similarity_20261018_01",
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "started",
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "source": source,
        "protocol_sha256": sha256_file(P2A_PROTOCOL),
        "p1_6_protocol_sha256": sha256_file(P1_6_PROTOCOL),
        "resource_snapshot": resource_snapshot(),
        "resource_budget": {"gpu_seconds_max": 0, "cpu_seconds_max": MAX_CPU_SECONDS, "process_maxrss_gib": MAX_RSS_GIB, "max_cpu_threads": MAX_THREADS},
        "environment": {
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "rank_bm25": package_version("rank-bm25"),
            "tokenizer": "stdlib re; frozen P1.5-compatible ASCII alphanumeric tokenizer",
        },
        "no_api_calls": True,
        "no_dependency_installation": True,
        "no_model_download": True,
        "no_training": True,
        "no_sql_execution": True,
        "gpu_used": False,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    try:
        ref, prepared, query_vectors, node_vectors = validate_p1_6_inputs(args, p1_module)
        p1_6_summary = ref["summary"]
        p1_6_rows_aggregate, p1_6_rows, _ = p1_module.score_snapshot(prepared, query_vectors, node_vectors)
        scorer = p1_6_summary["scorer_replay"]
        if p1_6_rows_aggregate["score_matrix_digest_sha256"] != scorer["pass1_score_matrix_digest_sha256"]:
            raise RuntimeError("Recomputed P1.6 S0 score digest differs from its frozen Full Gate")
        if p1_6_rows_aggregate["question_rows_digest_sha256"] != scorer["pass1_question_rows_digest_sha256"]:
            raise RuntimeError("Recomputed P1.6 S0 question-row digest differs from its frozen Full Gate")
        if args.mode == "full":
            smoke_summary_path = args.smoke_dir.resolve() / "smoke_summary.json"
            smoke_receipt_path = args.smoke_dir.resolve() / "smoke_receipt.json"
            smoke_run_start_path = args.smoke_dir.resolve() / "run_start.json"
            if not all(path.is_file() for path in (smoke_summary_path, smoke_receipt_path, smoke_run_start_path)):
                raise FileNotFoundError("P2a smoke evidence is incomplete")
            smoke_summary = json.loads(smoke_summary_path.read_text(encoding="utf-8"))
            smoke_receipt = json.loads(smoke_receipt_path.read_text(encoding="utf-8"))
            smoke_run_start = json.loads(smoke_run_start_path.read_text(encoding="utf-8"))
            if smoke_summary.get("status") != "smoke_passed" or smoke_summary.get("questions") != 5:
                raise RuntimeError("P2a full run blocked because its smoke did not pass")
            if smoke_receipt.get("run_id") != smoke_summary.get("run_id") or smoke_run_start.get("run_id") != smoke_receipt.get("run_id"):
                raise RuntimeError("P2a smoke summary, receipt, and run metadata do not match")
            if smoke_run_start.get("mode") != "smoke" or smoke_run_start.get("state") != "completed":
                raise RuntimeError("P2a smoke run metadata is not completed")
            if smoke_run_start.get("source", {}).get("published_commit") != args.expected_commit:
                raise RuntimeError("P2a smoke was produced by a different code commit")
            if smoke_receipt.get("input_manifest_sha256") != ref["input_manifest_sha256"]:
                raise RuntimeError("P2a smoke used a different frozen input manifest")
            if smoke_summary.get("p1_6_cache_sha256") != sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"):
                raise RuntimeError("P2a smoke used a different frozen P1.6 cache")
            if smoke_receipt.get("question_count") != 5:
                raise RuntimeError("P2a smoke receipt does not cover five questions")
            if smoke_receipt.get("smoke_summary_sha256") != sha256_file(smoke_summary_path):
                raise RuntimeError("P2a smoke summary hash does not match its receipt")
        active_prepared, active_queries, active_nodes = prepare_active_inputs(prepared, query_vectors, node_vectors, args.mode)
        if args.mode == "full":
            baseline_rows = p1_6_rows
        else:
            _, baseline_rows, _ = p1_module.score_snapshot(active_prepared, active_queries, active_nodes)
        summary, rows = evaluate(active_prepared, active_queries, active_nodes)
        assert_s0_parity(rows, baseline_rows)
        active_dbs = {question["db_id"] for question in active_prepared["questions"]}
        if args.mode == "smoke":
            if len(active_prepared["questions"]) != 5 or len(active_dbs) != 1:
                raise RuntimeError("P2a smoke must contain five ordered questions from one database")
            if summary["column_question_denominator"] < 1:
                raise RuntimeError("P2a smoke contains no column-eligible question")
            result = {
                "run_id": args.run_id,
                "mode": "smoke",
                "status": "smoke_passed",
                "questions": len(active_prepared["questions"]),
                "databases": len(active_dbs),
                "nodes": len(active_prepared["nodes"]),
                "table_question_denominator": summary["table_question_denominator"],
                "column_question_denominator": summary["column_question_denominator"],
                "input_manifest_sha256": ref["input_manifest_sha256"],
                "p1_6_cache_sha256": sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"),
                "p1_6_s0_digest_match": True,
                "methods_finite": True,
                "summary": summary,
            }
            write_json(args.output_dir / "smoke_summary.json", result)
            write_json(args.output_dir / "smoke_receipt.json", {
                "run_id": args.run_id,
                "mode": "smoke",
                "status": "smoke_passed",
                "input_manifest_sha256": ref["input_manifest_sha256"],
                "smoke_summary_sha256": sha256_file(args.output_dir / "smoke_summary.json"),
                "question_count": 5,
            })
            summary_path = args.output_dir / "smoke_summary.json"
        else:
            if len(active_prepared["questions"]) != EXPECTED_COUNTS["questions"] or summary["column_question_denominator"] != EXPECTED_COUNTS["column_eligible"]:
                raise RuntimeError("P2a full data/label denominators differ from the registered manifest")
            if summary["non_saturated_2048"]["column_question_denominator"] != 706 or summary["non_saturated_2048"]["database_count"] != 5:
                raise RuntimeError("P2a non-saturated subset differs from the registered 706-question/5-DB cohort")
            comparison = {
                method: paired_comparison(rows, method, subset=False)
                for method in ("S1_bm25", "S2_rrf")
            }
            comparison_non_saturated = {
                method: paired_comparison(rows, method, subset=True)
                for method in ("S1_bm25", "S2_rrf")
            }
            result = {
                "experiment_id": "p2a_similarity_20261018_01",
                "run_id": args.run_id,
                "status": "completed",
                "source_commit": args.expected_commit,
                "p1_6_reference_run_id": P1_6_RUN_ID,
                "p1_6_source_commit": P1_6_COMMIT,
                "p1_6_full_gate": "PASS",
                "input_manifest_sha256": ref["input_manifest_sha256"],
                "ordered_node_manifest_content_sha256": ref["input_record"]["ordered_node_manifest_sha256"],
                "p1_6_cache_sha256": sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"),
                "p1_6_s0_score_matrix_digest_sha256": p1_6_summary["scorer_replay"]["pass1_score_matrix_digest_sha256"],
                "p1_6_s0_question_rows_digest_sha256": p1_6_summary["scorer_replay"]["pass1_question_rows_digest_sha256"],
                "s0_parity": "PASS",
                "integrity_gate": "PASS",
                "metrics": summary,
                "paired_rescue_damage": comparison,
                "paired_rescue_damage_non_saturated": comparison_non_saturated,
                "exploratory_decision": decision_and_uncertainty(summary),
                "private_artifacts": {"per_question_filename": "per_question_private.jsonl"},
            }
            private_path = args.output_dir / "per_question_private.jsonl"
            with private_path.open("w", encoding="utf-8") as file:
                for row in rows:
                    file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            result["private_artifacts"]["per_question_sha256"] = sha256_file(private_path)
            summary_path = args.output_dir / "aggregate_summary.json"
            write_json(summary_path, result)
        cpu_seconds = time.process_time() - cpu_started
        maxrss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if cpu_seconds > MAX_CPU_SECONDS or maxrss_kib > MAX_RSS_GIB * 1024 * 1024:
            raise RuntimeError(f"P2a CPU/RSS budget exceeded: cpu={cpu_seconds:.2f}s rss={maxrss_kib / 1024 / 1024:.2f}GiB")
        run_start.update({
            "state": "completed",
            "input_manifest_sha256": ref["input_manifest_sha256"],
            "p1_6_cache_sha256": sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"),
            "p1_6_s0_parity": "PASS",
            "finished_elapsed_wall_seconds": time.perf_counter() - started,
            "cpu_seconds_process": cpu_seconds,
            "process_maxrss_gib": maxrss_kib / 1024 / 1024,
            "result_summary_sha256": sha256_file(summary_path),
        })
        write_json(args.output_dir / "run_start.json", run_start)
        print(json.dumps({
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "completed",
            "output_dir": str(args.output_dir),
            "elapsed_wall_seconds": run_start["finished_elapsed_wall_seconds"],
            "cpu_seconds_process": cpu_seconds,
            "process_maxrss_gib": run_start["process_maxrss_gib"],
        }, ensure_ascii=False))
    except Exception as error:
        run_start["state"] = "failed"
        run_start["failure_type"] = type(error).__name__
        run_start["failure_message"] = str(error)
        run_start["finished_elapsed_wall_seconds"] = time.perf_counter() - started
        run_start["cpu_seconds_process"] = time.process_time() - cpu_started
        write_json(args.output_dir / "run_start.json", run_start)
        raise


p1_module: Any


if __name__ == "__main__":
    run()
