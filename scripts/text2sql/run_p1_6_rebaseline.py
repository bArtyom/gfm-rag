#!/usr/bin/env python3
"""Audit the historical P1 mismatch and freeze a repeatable 1024 baseline.

Question-level artifacts and embedding arrays are written only to the supplied
private output directory. This runner never writes questions, SQL, scores, or
embeddings to the public repository.
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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MAX_GPU_SECONDS = 900
MAX_CPU_SECONDS = 1800
MAX_RSS_GIB = 16
MAX_THREADS = 8
EXPECTED_COUNTS = {"questions": 1534, "databases": 11, "nodes": 873, "tables": 75, "columns": 798, "column_eligible": 1460}
EXPECTED_INPUT_HASHES = {
    "questions": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "schema": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
    "p0_audit": "0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf",
    "gold_labels": "1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525",
    "model_manifest": "b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68",
}
EXPECTED_SCHEMA_TEXT_SHA256 = "b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a"
EXPECTED_QUERY_PROMPT_SHA256 = "a33e140e6ae5a362b5480a437bc77431b8c878f000e3ea03dadba38108b25634"
EXPECTED_P1_ROWS_SHA256 = "c28776ed47a30f1c898cb0a849a9834d7668999c26eb3c643e00474928b249cb"
EXPECTED_P1_SUMMARY_SHA256 = "33aed3af07201515aa59d3d4bd03894befec597ea3853c07e815db8db2dda97a"
QUERY_INSTRUCTION = "Given a natural-language question about a database, retrieve the relevant tables and columns."
QUERY_PREFIX = f"Instruct: {QUERY_INSTRUCTION}\nQuery: "
TOKEN_BUDGETS = (512, 1024, 2048)
TOP_K = {"table": (5, 10), "column": (5, 10, 20)}

for _thread_env in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_thread_env] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_ARCHIVE_SUPPORT = REPO_ROOT / "docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/gfmrag_p1_common.py"
P1_ARCHIVE_RUNNER = REPO_ROOT / "docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/run_gfmrag_p1.py"
P1_5_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_5_diagnostics.py"


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


def json_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def git_output(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def resource_snapshot(gpu_id: int) -> dict[str, Any]:
    def command_output(command: list[str]) -> str:
        result = subprocess.run(command, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else f"unavailable: {result.stderr.strip()}"

    gpu = command_output([
        "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ])
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu_id": gpu_id,
        "nvidia_smi": gpu,
        "free_h": command_output(["free", "-h"]),
        "cpu_threads": os.cpu_count(),
        "disk": command_output(["df", "-h", str(REPO_ROOT)]),
    }


def load_p1_5_module() -> Any:
    spec = importlib.util.spec_from_file_location("p1_5_diagnostics_for_p1_6", P1_5_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load P1.5 input helper: {P1_5_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_common(legacy_root: Path, dataset_root: Path, model_path: Path) -> tuple[Any, Any]:
    helper = load_p1_5_module()
    common = helper.load_p1_support(legacy_root.resolve(), dataset_root.resolve(), model_path.resolve())
    return helper, common


def prepare_inputs(common: Any) -> dict[str, Any]:
    prepared = common.prepare_p1_inputs(load_tokenizer=True)
    prepared["nodes_interleaved_builder_order"] = list(prepared["nodes"])
    prepared["nodes"] = sorted(prepared["nodes"], key=lambda node: node.node_type != "table")
    prepared["nodes_by_db"] = {
        db_id: sorted(rows, key=lambda node: node.node_type != "table")
        for db_id, rows in prepared["nodes_by_db"].items()
    }
    return prepared


def ordered_node_manifest(nodes: list[Any]) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "ordinal": index,
            "node_id": node.node_id,
            "db_id": node.db_id,
            "node_type": node.node_type,
            "text_sha256": sha256_bytes(node.text.encode("utf-8")),
            "token_count": int(node.token_count),
        }
        for index, node in enumerate(nodes)
    ]
    data = (json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return rows, sha256_bytes(data)


def legacy_text_hash_hypotheses(prepared: dict[str, Any], common: Any) -> dict[str, Any]:
    recorded_hash = "2089cf5c7d10aa4056c98a19edca44a3fa0bfa17e2c1f0593848f7c935d4f226"
    interleaved = prepared["nodes_interleaved_builder_order"]
    candidates = {
        "builder_interleaved": interleaved,
        "type_first_global": prepared["nodes"],
        "database_then_type_first": sorted(interleaved, key=lambda node: (node.db_id, node.node_type != "table")),
    }
    evaluated: dict[str, Any] = {}
    for order_name, nodes in candidates.items():
        hashes = common.sha256_text_sequence([node.text for node in nodes])
        evaluated[order_name] = hashes
    matches = [
        f"{order_name}.{serialization}"
        for order_name, serializations in evaluated.items()
        for serialization, value in serializations.items()
        if value == recorded_hash
    ]
    return {
        "recorded_legacy_full_schema_hash": recorded_hash,
        "tested_orders": list(candidates),
        "tested_serializations": list(next(iter(evaluated.values()))),
        "hashes": evaluated,
        "matching_hypotheses": matches,
        "recovered": bool(matches),
        "scope": "Only candidate orderings and serialization forms implemented in the archived P1 input/hash helpers were tested; no text or source files were changed.",
    }


def validate_inputs(prepared: dict[str, Any], common: Any, args: argparse.Namespace) -> dict[str, Any]:
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    input_hashes = prepared["frozen_hashes"]["sha256"]
    for key, expected in EXPECTED_INPUT_HASHES.items():
        actual_key = key
        if key == "model_manifest":
            actual = sha256_file(args.legacy_root / "results/p0/model_files.sha256")
        else:
            actual = input_hashes.get(actual_key)
        if actual != expected:
            raise RuntimeError(f"Frozen {key} hash mismatch: expected={expected} actual={actual}")

    counts = {
        "questions": len(questions),
        "databases": len(prepared["nodes_by_db"]),
        "nodes": len(nodes),
        "tables": sum(node.node_type == "table" for node in nodes),
        "columns": sum(node.node_type == "column" for node in nodes),
        "column_eligible": sum(bool(question["label"]["column_eligible"]) for question in questions),
    }
    if counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Frozen input count mismatch: {counts}")
    if len({question["question_id"] for question in questions}) != counts["questions"]:
        raise RuntimeError("Duplicate question IDs in frozen question order")

    helper = load_p1_5_module()
    model_integrity = helper.verify_model_manifest(common, args.legacy_root.resolve(), args.model_path.resolve())
    database_integrity = helper.verify_database_hashes(common)

    node_rows, node_manifest_hash = ordered_node_manifest(nodes)
    schema_hash = sha256_bytes("\n".join(node.text for node in nodes).encode("utf-8"))
    query_hash = sha256_bytes("\n".join(question["prompt"] for question in questions).encode("utf-8"))
    if schema_hash != EXPECTED_SCHEMA_TEXT_SHA256:
        raise RuntimeError(f"Schema serialization hash mismatch: {schema_hash}")
    if query_hash != EXPECTED_QUERY_PROMPT_SHA256:
        raise RuntimeError(f"Query prompt hash mismatch: {query_hash}")

    p1_5_run = args.p1_5_run_dir.resolve()
    p1_5_manifest_path = p1_5_run / "input_manifest.json"
    p1_5_rows_path = p1_5_run / "per_question_private.jsonl"
    p1_5_summary_path = p1_5_run / "aggregate_summary.json"
    p1_5_manifest = json.loads(p1_5_manifest_path.read_text(encoding="utf-8"))
    p1_5_run_start = json.loads((p1_5_run / "run_start.json").read_text(encoding="utf-8"))
    if p1_5_manifest.get("project_commit") != "1d3a05773cd4305fdd591e6bd729a03e22326e8c":
        raise RuntimeError("P1.5 project commit differs from the archived baseline")
    if p1_5_manifest.get("official_encoder_commit") != "b3e43219c49929da505244df4f0ba54c0947e4c4":
        raise RuntimeError("P1.5 official encoder commit differs from the registered source")
    if p1_5_run_start.get("project_base_commit") != p1_5_manifest["project_commit"] or p1_5_run_start.get("mode") != "full" or p1_5_run_start.get("state") != "completed":
        raise RuntimeError("P1.5 full-run metadata does not match its manifest")
    if p1_5_run_start.get("run_id") != "p1_5_diag_full_20261016_03":
        raise RuntimeError("Unexpected P1.5 run ID")
    for name, path, key in (
        ("P1.5 query", args.previous_run_dir / "per_question_private.jsonl", "historical_p1_per_question_sha256"),
        ("P1.5 summary", args.previous_run_dir / "summary.json", "historical_p1_summary_sha256"),
    ):
        expected = p1_5_manifest["source"].get(key) or p1_5_manifest.get(key)
        actual = sha256_file(path)
        if expected and actual != expected:
            raise RuntimeError(f"{name} artifact SHA mismatch: expected={expected} actual={actual}")
    if sha256_file(p1_5_rows_path) != p1_5_run_start.get("private_rows_sha256"):
        raise RuntimeError("P1.5 private per-question artifact hash mismatch")
    if sha256_file(p1_5_summary_path) != p1_5_run_start.get("aggregate_summary_sha256"):
        raise RuntimeError("P1.5 aggregate summary hash mismatch")
    if p1_5_manifest["data"]["schema_text_sha256"] != schema_hash:
        raise RuntimeError("P1.6 schema text differs from P1.5 frozen input")
    if p1_5_manifest["data"]["query_prompt_sha256"] != query_hash:
        raise RuntimeError("P1.6 query prompts differ from P1.5 frozen input")
    if p1_5_manifest["model"]["local_model_manifest"]["manifest_sha256"] != EXPECTED_INPUT_HASHES["model_manifest"]:
        raise RuntimeError("P1.5 model manifest differs from registered model")
    if p1_5_manifest["model"].get("output_dimension") != 1024 or p1_5_manifest["model"].get("batch_size") != 32 or p1_5_manifest["model"].get("query_instruction") != QUERY_INSTRUCTION:
        raise RuntimeError("P1.5 model settings differ from the frozen 1024 baseline")

    legacy_runner_sha = sha256_file(P1_ARCHIVE_RUNNER)
    legacy_support_sha = sha256_file(P1_ARCHIVE_SUPPORT)
    if legacy_runner_sha != "824cbfbd0e18b2ecadada6738b447300c8725515d7867cac4cb1467ff1d2bd4f":
        raise RuntimeError("Archived P1 runner SHA changed")
    if legacy_support_sha != "54fadef342ba6eb5e19d16f2121d9e078b258de909a1c9ed1a52b32a1b2c26de":
        raise RuntimeError("Archived P1 input helper SHA changed")

    return {
        "counts": counts,
        "input_hashes": input_hashes,
        "model_manifest_sha256": EXPECTED_INPUT_HASHES["model_manifest"],
        "verified_model_files": model_integrity,
        "verified_database_files": database_integrity,
        "schema_text_sha256": schema_hash,
        "query_prompt_sha256": query_hash,
        "ordered_node_manifest_sha256": node_manifest_hash,
        "legacy_text_hash_hypotheses": legacy_text_hash_hypotheses(prepared, common),
        "ordered_node_manifest": node_rows,
        "p1_5_run_id": p1_5_manifest["historical_p1_run_id"],
        "p1_5_runner_sha256": p1_5_manifest["source"]["p1_5_runner_sha256"],
        "p1_5_input_manifest_sha256": sha256_file(p1_5_manifest_path),
        "p1_5_summary_sha256": sha256_file(p1_5_summary_path),
        "p1_5_per_question_sha256": sha256_file(p1_5_rows_path),
        "archived_p1_runner_sha256": legacy_runner_sha,
        "archived_p1_support_sha256": legacy_support_sha,
        "description_csv_encodings": prepared["description_csv_encodings"],
        "description_csv_encoding_counts": prepared["description_csv_encoding_counts"],
        "tokenizer_stats": prepared["token_stats"],
        "p1_5_input_manifest": p1_5_manifest,
        "historical_cache_inventory": {
            "p1_vector_cache_files": sorted(path.name for path in args.previous_run_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".npz", ".npy", ".pt", ".safetensors"}),
            "p1_5_vector_cache_files": sorted(path.name for path in p1_5_run.rglob("*") if path.is_file() and path.suffix.lower() in {".npz", ".npy", ".pt", ".safetensors"}),
        },
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def historical_mismatch_audit(args: argparse.Namespace) -> dict[str, Any]:
    previous_path = args.previous_run_dir / "per_question_private.jsonl"
    if sha256_file(previous_path) != EXPECTED_P1_ROWS_SHA256:
        raise RuntimeError("Historical P1 per-question hash mismatch")
    previous_summary = args.previous_run_dir / "summary.json"
    if sha256_file(previous_summary) != EXPECTED_P1_SUMMARY_SHA256:
        raise RuntimeError("Historical P1 summary hash mismatch")
    old_rows = {str(row["question_id"]): row for row in read_jsonl(previous_path)}
    p1_5_rows = {str(row["question_id"]): row for row in read_jsonl(args.p1_5_run_dir / "per_question_private.jsonl")}
    previous_run_start = json.loads((args.previous_run_dir / "run_start.json").read_text(encoding="utf-8"))
    if previous_run_start.get("source_commit") != "b3e43219c49929da505244df4f0ba54c0947e4c4" or previous_run_start.get("run_id") != "gfmrag_official_full1534_20261014_01":
        raise RuntimeError("Historical P1 full-run metadata differs from the registered artifact")
    if len(old_rows) != 1534 or len(p1_5_rows) != 1534 or old_rows.keys() != p1_5_rows.keys():
        raise RuntimeError("Historical/P1.5 question keys are incomplete or differ")

    fields = (
        ("table_r5_hits", "table", "5"),
        ("table_r10_hits", "table", "10"),
        ("column_r5_hits", "column", "5"),
        ("column_r10_hits", "column", "10"),
        ("budget_complete", "budget", "2048"),
    )
    per_metric: collections.Counter[str] = collections.Counter()
    per_db: collections.Counter[str] = collections.Counter()
    near_column_boundary: collections.Counter[str] = collections.Counter()
    checks = matches = 0
    for qid in old_rows:
        old = old_rows[qid]
        new = p1_5_rows[qid]
        if str(old["db_id"]) != str(new["db_id"]):
            raise RuntimeError("Historical/P1.5 database mapping differs")
        for dimension in ("512", "1024"):
            old_metrics = old["metrics"][dimension]
            new_metrics = new["dimensions"][dimension]
            question_fields = fields[:2] + (fields[2:] if new["column_eligible"] else ())
            for field, kind, cutoff in question_fields:
                if kind == "table":
                    current = new_metrics["table_hits"][cutoff]
                elif kind == "column":
                    current = new_metrics["column_hits"][cutoff]
                else:
                    current = new_metrics["budgets"][cutoff]["complete"]
                checks += 1
                if old_metrics[field] == current:
                    matches += 1
                    continue
                key = f"{dimension}_{field}"
                per_metric[key] += 1
                per_db[f"{new['db_id']}|{key}"] += 1
                if kind == "column":
                    ranks = new_metrics["column_gold_ranks"] or []
                    boundary = int(any(abs(int(rank) - int(cutoff)) <= 1 for rank in ranks))
                    near_column_boundary[f"{key}|within_1_rank"] += boundary
                    near_column_boundary[f"{key}|not_within_1_rank"] += 1 - boundary

    if checks != 14896 or matches != 14805:
        raise RuntimeError(f"P1.5 historical mismatch totals changed: checks={checks}, matches={matches}")
    return {
        "comparison": "archived P1 full-run per-question metrics vs P1.5 full-run metrics",
        "checks": checks,
        "matches": matches,
        "mismatches": checks - matches,
        "match_rate": matches / checks,
        "mismatches_by_dimension_metric": dict(sorted(per_metric.items())),
        "mismatches_by_database_and_metric": dict(sorted(per_db.items())),
        "column_mismatch_questions_near_p1_5_gold_rank_boundary": dict(sorted(near_column_boundary.items())),
        "historical_scores_and_embeddings_available": False,
        "interpretation": "Old vectors, per-candidate scores and complete rank lists are absent; current-side ranks can locate boundary-adjacent Gold columns but cannot attribute historical changes to a score tie, score gap, or encoder perturbation.",
    }


def current_resources(gpu_id: int) -> dict[str, Any]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True,
    )
    records = []
    for line in result.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 5:
            records.append({"index": int(parts[0]), "name": parts[1], "memory_total_mib": int(parts[2]), "memory_used_mib": int(parts[3]), "utilization_percent": int(parts[4])})
    selected = next((row for row in records if row["index"] == gpu_id), None)
    if selected is None:
        raise RuntimeError(f"GPU {gpu_id} not found in nvidia-smi output")
    return {"gpu": selected, "all_gpus": records}


def initialize_encoder(common: Any, model_path: Path, gpu_id: int) -> tuple[Any, Any, str]:
    import torch

    torch.set_num_threads(MAX_THREADS)
    encoder_class = common.load_official_qwen3_class()
    encoder = encoder_class(
        text_emb_model_name=str(model_path.resolve()),
        normalize=True,
        batch_size=32,
        query_instruct=None,
        passage_instruct=None,
        truncate_dim=1024,
        model_kwargs=None,
        tokenizer_kwargs={"local_files_only": True},
    )
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Expected exactly one visible CUDA device after official encoder initialization")
    return encoder, torch, torch.cuda.get_device_name(0)


def encode_texts(encoder: Any, torch: Any, texts: list[str], is_query: bool) -> np.ndarray:
    tensor = encoder.encode(texts, is_query=is_query, show_progress_bar=False)
    if not torch.is_tensor(tensor):
        raise RuntimeError(f"Official encode returned unexpected type: {type(tensor)}")
    vectors = tensor.detach().to(device="cpu", dtype=torch.float32).numpy()
    del tensor
    if vectors.ndim != 2 or vectors.shape != (len(texts), 1024):
        raise RuntimeError(f"Unexpected embedding shape: got={vectors.shape}, expected=({len(texts)}, 1024)")
    if not np.isfinite(vectors).all():
        raise RuntimeError("Encoder returned non-finite values")
    norms = np.linalg.norm(vectors, axis=1)
    if np.any(norms <= 1e-12):
        raise RuntimeError("Encoder returned a zero vector")
    return np.ascontiguousarray(vectors, dtype=np.float32)


def normalized_vectors(vectors: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    vector32 = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vector32, axis=1)
    if not np.isfinite(vector32).all() or not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        raise RuntimeError("Invalid vector in frozen scorer input")
    unit = np.ascontiguousarray(vector32 / norms[:, None], dtype=np.float32)
    unit_norms = np.linalg.norm(unit, axis=1)
    return unit, {
        "raw_norm_min": float(norms.min()),
        "raw_norm_median": float(np.median(norms)),
        "raw_norm_p95": float(np.quantile(norms, 0.95)),
        "normalized_norm_max_abs_error": float(np.max(np.abs(unit_norms - 1.0))),
    }


def stable_order(scores: np.ndarray, node_ids: list[str]) -> np.ndarray:
    # Score descending; stable node-ID lexicographic ordering applies only to exact score ties.
    return np.lexsort((np.asarray(node_ids, dtype=str), -np.asarray(scores, dtype=np.float32)))


def qstats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p10": None, "median": None, "p90": None, "max": None, "exact_zero_count": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(len(values)),
        "min": float(np.min(arr)),
        "p10": float(np.quantile(arr, 0.10)),
        "median": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.90)),
        "max": float(np.max(arr)),
        "exact_zero_count": int(np.count_nonzero(arr == 0.0)),
    }


def score_snapshot(prepared: dict[str, Any], query_vectors: np.ndarray, node_vectors: np.ndarray) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    query_unit, query_norm_stats = normalized_vectors(query_vectors)
    node_unit, node_norm_stats = normalized_vectors(node_vectors)
    nodes_by_db: dict[str, list[int]] = {}
    for index, node in enumerate(nodes):
        nodes_by_db.setdefault(node.db_id, []).append(index)

    metrics: dict[str, dict[str, list[float]]] = {
        "global": collections.defaultdict(list),
        "database": collections.defaultdict(list),
    }
    sums: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    rank_values: list[int] = []
    boundary_values: dict[str, list[float]] = collections.defaultdict(list)
    tie_groups = tie_excess_candidates = questions_with_ties = 0
    score_digest = hashlib.sha256()
    rows: list[dict[str, Any]] = []

    for question_index, question in enumerate(questions):
        db_id = question["db_id"]
        candidate_indexes = nodes_by_db[db_id]
        candidate_ids = [nodes[index].node_id for index in candidate_indexes]
        scores = np.asarray(query_unit[question_index] @ node_unit[candidate_indexes].T, dtype=np.float32)
        if not np.isfinite(scores).all():
            raise RuntimeError(f"Non-finite cosine score for database {db_id}")
        score_digest.update(np.ascontiguousarray(scores, dtype=np.float32).tobytes())
        unique_scores, tie_counts = np.unique(scores, return_counts=True)
        tied_groups_here = int(np.count_nonzero(tie_counts > 1))
        tie_groups += tied_groups_here
        tie_excess_candidates += int(np.sum(tie_counts[tie_counts > 1] - 1)) if tied_groups_here else 0
        questions_with_ties += int(tied_groups_here > 0)

        table_positions = [i for i, global_index in enumerate(candidate_indexes) if nodes[global_index].node_type == "table"]
        column_positions = [i for i, global_index in enumerate(candidate_indexes) if nodes[global_index].node_type == "column"]

        def ranked_positions(positions: list[int]) -> tuple[list[int], dict[str, int]]:
            ids = [candidate_ids[position] for position in positions]
            order = stable_order(scores[positions], ids)
            ranked = [positions[int(offset)] for offset in order]
            ranks = {candidate_ids[position]: rank for rank, position in enumerate(ranked, start=1)}
            return ranked, ranks

        table_order, table_rank = ranked_positions(table_positions)
        column_order, column_rank = ranked_positions(column_positions)
        all_order, _ = ranked_positions(list(range(len(candidate_indexes))))
        label = question["label"]
        gold_tables = tuple(label["gold_table_ids"])
        table_gold_ranks = sorted(table_rank[node_id] for node_id in gold_tables)
        row: dict[str, Any] = {
            "question_id": int(question["question_id"]),
            "db_id": db_id,
            "column_eligible": bool(label["column_eligible"]),
            "table_gold_ranks": table_gold_ranks,
            "table_topk_ids": {},
            "table_hits": {},
            "column_gold_ranks": None,
            "column_topk_ids": {},
            "column_hits": {},
            "budgets": None,
        }
        for k in TOP_K["table"]:
            key = f"table_r{k}"
            retrieved = [candidate_ids[position] for position in table_order[:k]]
            hits = sum(rank <= k for rank in table_gold_ranks)
            recall = hits / len(gold_tables)
            row["table_topk_ids"][str(k)] = retrieved
            row["table_hits"][str(k)] = hits
            metrics["global"][key].append(recall)
            metrics["database"][f"{db_id}|{key}"].append(recall)
            sums[f"global|{key}"]["hits"] += hits
            sums[f"global|{key}"]["gold"] += len(gold_tables)
            sums[f"database|{db_id}|{key}"]["hits"] += hits
            sums[f"database|{db_id}|{key}"]["gold"] += len(gold_tables)
            counts[f"global|{key}"]["questions"] += 1
            counts[f"database|{db_id}|{key}"]["questions"] += 1
            if len(table_positions) > k:
                sorted_scores = np.sort(scores[table_positions])[::-1]
                boundary_values[key].append(float(sorted_scores[k - 1] - sorted_scores[k]))

        if label["column_eligible"]:
            gold_columns = tuple(label["gold_column_ids"])
            column_gold_ranks = sorted(column_rank[node_id] for node_id in gold_columns)
            row["column_gold_ranks"] = column_gold_ranks
            rank_values.extend(column_gold_ranks)
            for k in TOP_K["column"]:
                key = f"column_r{k}"
                retrieved = [candidate_ids[position] for position in column_order[:k]]
                hits = sum(rank <= k for rank in column_gold_ranks)
                recall = hits / len(gold_columns)
                row["column_topk_ids"][str(k)] = retrieved
                row["column_hits"][str(k)] = hits
                metrics["global"][key].append(recall)
                metrics["database"][f"{db_id}|{key}"].append(recall)
                sums[f"global|{key}"]["hits"] += hits
                sums[f"global|{key}"]["gold"] += len(gold_columns)
                sums[f"database|{db_id}|{key}"]["hits"] += hits
                sums[f"database|{db_id}|{key}"]["gold"] += len(gold_columns)
                counts[f"global|{key}"]["questions"] += 1
                counts[f"database|{db_id}|{key}"]["questions"] += 1
                if len(column_positions) > k:
                    sorted_scores = np.sort(scores[column_positions])[::-1]
                    boundary_values[key].append(float(sorted_scores[k - 1] - sorted_scores[k]))

            gold_ids = set((*gold_tables, *gold_columns))
            selected_by_budget: dict[str, Any] = {}
            for budget in TOKEN_BUDGETS:
                remaining = budget
                selected: list[str] = []
                used = 0
                for position in all_order:
                    node = nodes[candidate_indexes[position]]
                    if node.token_count <= remaining:
                        selected.append(node.node_id)
                        remaining -= node.token_count
                        used += node.token_count
                hits = len(gold_ids.intersection(selected))
                precision = hits / len(selected) if selected else 0.0
                recall = hits / len(gold_ids)
                complete = int(hits == len(gold_ids))
                bkey = str(budget)
                selected_by_budget[bkey] = {
                    "selected_ids": selected,
                    "tokens_used": used,
                    "returned_elements": len(selected),
                    "retrieved_gold_elements": hits,
                    "gold_elements": len(gold_ids),
                    "recall": recall,
                    "precision": precision,
                    "complete": complete,
                }
                for metric, value in (("budget_recall", recall), ("budget_precision", precision), ("budget_complete", float(complete)), ("budget_returned_elements", float(len(selected))), ("budget_tokens_used", float(used))):
                    metric_key = f"{metric}_{budget}"
                    metrics["global"][metric_key].append(value)
                    metrics["database"][f"{db_id}|{metric_key}"].append(value)
                sums[f"global|budget_{budget}"]["hits"] += hits
                sums[f"global|budget_{budget}"]["gold"] += len(gold_ids)
                sums[f"global|budget_{budget}"]["selected"] += len(selected)
                sums[f"global|budget_{budget}"]["tokens"] += used
                counts[f"global|budget_{budget}"]["questions"] += 1
                sums[f"database|{db_id}|budget_{budget}"]["hits"] += hits
                sums[f"database|{db_id}|budget_{budget}"]["gold"] += len(gold_ids)
                sums[f"database|{db_id}|budget_{budget}"]["selected"] += len(selected)
                sums[f"database|{db_id}|budget_{budget}"]["tokens"] += used
                counts[f"database|{db_id}|budget_{budget}"]["questions"] += 1
            row["budgets"] = selected_by_budget
        rows.append(row)

    def summarize(key: str, metric_key: str) -> dict[str, Any]:
        global_values = metrics["global"].get(metric_key, [])
        db_values = [float(np.mean(values)) for name, values in metrics["database"].items() if name.endswith("|" + metric_key) and values]
        global_sum = sums[f"global|{metric_key}"]
        return {
            "query_macro": float(np.mean(global_values)) if global_values else None,
            "database_macro": float(np.mean(db_values)) if db_values else None,
            "element_micro": float(global_sum["hits"] / global_sum["gold"]) if global_sum["gold"] else None,
            "questions": len(global_values),
            "gold_elements": int(global_sum["gold"]),
            "retrieved_gold_elements": int(global_sum["hits"]),
        }

    global_summary: dict[str, Any] = {}
    for key in ("table_r5", "table_r10", "column_r5", "column_r10", "column_r20"):
        global_summary[key] = summarize(key, key)
    global_summary["column_mrr"] = {
        "query_macro": float(np.mean([1.0 / row["column_gold_ranks"][0] for row in rows if row["column_eligible"]]))
    }
    global_summary["column_map"] = {
        "query_macro": float(np.mean([
            sum(index / rank for index, rank in enumerate(row["column_gold_ranks"], start=1)) / len(row["column_gold_ranks"])
            for row in rows if row["column_eligible"]
        ]))
    }
    global_summary["column_gold_rank_elements"] = {
        "count": len(rank_values),
        "p50": float(np.quantile(rank_values, 0.5)),
        "p90": float(np.quantile(rank_values, 0.9)),
        "max": int(max(rank_values)),
    }
    global_summary["budgets"] = {}
    for budget in TOKEN_BUDGETS:
        bkey = f"budget_{budget}"
        raw = sums[f"global|{bkey}"]
        global_summary["budgets"][str(budget)] = {
            "gold_element_recall_query_macro": float(np.mean(metrics["global"][f"budget_recall_{budget}"])),
            "gold_element_recall_database_macro": float(np.mean([
                np.mean(values) for key, values in metrics["database"].items()
                if key.endswith(f"|budget_recall_{budget}") and values
            ])),
            "gold_element_recall_micro": float(raw["hits"] / raw["gold"]),
            "precision_query_macro": float(np.mean(metrics["global"][f"budget_precision_{budget}"])),
            "complete_schema_query_macro": float(np.mean(metrics["global"][f"budget_complete_{budget}"])),
            "complete_schema_database_macro": float(np.mean([
                np.mean(values) for key, values in metrics["database"].items()
                if key.endswith(f"|budget_complete_{budget}") and values
            ])),
            "mean_returned_elements": float(np.mean(metrics["global"][f"budget_returned_elements_{budget}"])),
            "mean_tokens_used": float(np.mean(metrics["global"][f"budget_tokens_used_{budget}"])),
            "total_gold_elements": int(raw["gold"]),
            "total_retrieved_gold_elements": int(raw["hits"]),
            "total_selected_elements": int(raw["selected"]),
            "total_tokens_used": int(raw["tokens"]),
        }

    per_database: dict[str, Any] = {}
    for db_id in sorted(nodes_by_db):
        db_rows = [row for row in rows if row["db_id"] == db_id]
        eligible_rows = [row for row in db_rows if row["column_eligible"]]
        db_summary: dict[str, Any] = {
            "questions": len(db_rows),
            "column_eligible_questions": len(eligible_rows),
            "candidate_tables": sum(node.db_id == db_id and node.node_type == "table" for node in nodes),
            "candidate_columns": sum(node.db_id == db_id and node.node_type == "column" for node in nodes),
            "schema_tokens": sum(node.token_count for node in nodes_by_db[db_id]),
        }
        for key in ("table_r5", "table_r10", "column_r5", "column_r10", "column_r20"):
            db_values = metrics["database"].get(f"{db_id}|{key}", [])
            db_sum = sums[f"database|{db_id}|{key}"]
            db_summary[key] = {
                "query_macro": float(np.mean(db_values)) if db_values else None,
                "element_micro": float(db_sum["hits"] / db_sum["gold"]) if db_sum["gold"] else None,
                "retrieved_gold_elements": int(db_sum["hits"]),
                "gold_elements": int(db_sum["gold"]),
            }
        db_summary["budgets"] = {}
        for budget in TOKEN_BUDGETS:
            raw = sums[f"database|{db_id}|budget_{budget}"]
            db_summary["budgets"][str(budget)] = {
                "gold_element_recall_query_macro": float(np.mean(metrics["database"][f"{db_id}|budget_recall_{budget}"])) if eligible_rows else None,
                "precision_query_macro": float(np.mean(metrics["database"][f"{db_id}|budget_precision_{budget}"])) if eligible_rows else None,
                "complete_schema_query_macro": float(np.mean(metrics["database"][f"{db_id}|budget_complete_{budget}"])) if eligible_rows else None,
                "gold_element_recall_micro": float(raw["hits"] / raw["gold"]) if raw["gold"] else None,
                "mean_returned_elements": float(np.mean(metrics["database"][f"{db_id}|budget_returned_elements_{budget}"])) if eligible_rows else None,
                "mean_tokens_used": float(np.mean(metrics["database"][f"{db_id}|budget_tokens_used_{budget}"])) if eligible_rows else None,
                "complete_schema_fit": db_summary["schema_tokens"] <= budget,
            }
        per_database[db_id] = db_summary

    aggregate = {
        "questions": len(questions),
        "databases": len(nodes_by_db),
        "table_question_denominator": len(questions),
        "column_question_denominator": sum(bool(row["column_eligible"]) for row in rows),
        "column_gold_element_denominator": sum(len(question["label"]["gold_column_ids"]) for question in questions if question["label"]["column_eligible"]),
        "tie_policy": "float32 score descending; exact score ties broken by lexicographically ascending stable node_id; no epsilon tie grouping",
        "global": global_summary,
        "per_database": per_database,
        "score_matrix_digest_sha256": score_digest.hexdigest(),
        "tie_diagnostics": {
            "questions_with_any_exact_score_tie": questions_with_ties,
            "exact_tie_groups": tie_groups,
            "extra_candidates_in_exact_tie_groups": tie_excess_candidates,
        },
        "ranking_boundary_gaps": {key: qstats(values) for key, values in sorted(boundary_values.items())},
        "vector_norm_health": {"queries": query_norm_stats, "nodes": node_norm_stats},
        "question_rows_digest_sha256": json_digest(rows),
    }
    return aggregate, rows, {"score_matrix_digest_sha256": score_digest.hexdigest(), "question_rows_digest_sha256": json_digest(rows)}


def compare_new_to_p1_5(rows: list[dict[str, Any]], p1_5_rows_path: Path) -> dict[str, Any]:
    p1_5 = {str(row["question_id"]): row for row in read_jsonl(p1_5_rows_path)}
    by_metric: collections.Counter[str] = collections.Counter()
    by_db: collections.Counter[str] = collections.Counter()
    checks = matches = 0
    for row in rows:
        prior = p1_5[str(row["question_id"])]["dimensions"]["1024"]
        comparisons: list[tuple[str, Any, Any]] = [
            ("table_r5_hits", row["table_hits"]["5"], prior["table_hits"]["5"]),
            ("table_r10_hits", row["table_hits"]["10"], prior["table_hits"]["10"]),
        ]
        if row["column_eligible"]:
            comparisons.extend([
                ("column_r5_hits", row["column_hits"]["5"], prior["column_hits"]["5"]),
                ("column_r10_hits", row["column_hits"]["10"], prior["column_hits"]["10"]),
                ("budget_complete_2048", row["budgets"]["2048"]["complete"], prior["budgets"]["2048"]["complete"]),
            ])
        for metric, current, previous in comparisons:
            checks += 1
            if current == previous:
                matches += 1
            else:
                by_metric[metric] += 1
                by_db[f"{row['db_id']}|{metric}"] += 1
    if checks != 7448:
        raise RuntimeError(f"Unexpected P1.6/P1.5 comparison denominator: {checks}")
    return {
        "comparison": "new P1.6 1024 encoder/cache/tie policy vs P1.5 recorded 1024 metrics",
        "checks": checks,
        "matches": matches,
        "mismatches": checks - matches,
        "match_rate": matches / checks if checks else None,
        "mismatches_by_metric": dict(sorted(by_metric.items())),
        "mismatches_by_database_and_metric": dict(sorted(by_db.items())),
        "interpretation": "P1.6 re-encodes once and adopts node-ID tie-break; differences from P1.5 cannot isolate encoder variation from changed exact-tie policy because P1.5 did not retain vectors or per-candidate scores.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preflight", "smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--p1-5-run-dir", type=Path, required=True)
    parser.add_argument("--smoke-dir", type=Path)
    parser.add_argument("--gpu-id", type=int, default=1)
    return parser.parse_args()


def assert_committed_source(expected_commit: str) -> dict[str, str]:
    actual = git_output("rev-parse", "HEAD")
    remote = git_output("rev-parse", "origin/main")
    local_tree = git_output("rev-parse", "HEAD^{tree}")
    remote_tree = git_output("rev-parse", f"{expected_commit}^{{tree}}")
    status = git_output("status", "--porcelain")
    branch = git_output("branch", "--show-current")
    if remote != expected_commit:
        raise RuntimeError(f"Expected origin/main at {expected_commit}; found {remote}")
    if local_tree != remote_tree:
        raise RuntimeError(f"Local execution tree does not match published commit tree: local={local_tree} remote={remote_tree}")
    if status:
        raise RuntimeError(f"Refusing to run with a dirty repository: {status}")
    if branch != "main":
        raise RuntimeError(f"Expected registered main branch, found {branch}")
    return {"published_commit": expected_commit, "local_commit": actual, "tree_sha": remote_tree, "branch": branch, "worktree_status": status or "clean"}


def encode_and_score(args: argparse.Namespace, common: Any, prepared: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import torch

    gpu_started = time.perf_counter()
    encoder, torch, gpu_name = initialize_encoder(common, args.model_path, args.gpu_id)
    queries = prepared["questions"] if args.mode == "full" else prepared["questions"][:5]
    active_dbs = {question["db_id"] for question in queries}
    nodes = [node for node in prepared["nodes"] if node.db_id in active_dbs]
    query_prompts = [question["prompt"] for question in queries]
    node_texts = [node.text for node in nodes]

    if args.mode == "smoke":
        first_query = encode_texts(encoder, torch, query_prompts, is_query=True)
        first_node = encode_texts(encoder, torch, node_texts, is_query=False)
        second_query = encode_texts(encoder, torch, query_prompts, is_query=True)
        second_node = encode_texts(encoder, torch, node_texts, is_query=False)
        query_error = float(np.max(np.abs(first_query - second_query)))
        node_error = float(np.max(np.abs(first_node - second_node)))
        repeat_prepared = dict(prepared)
        repeat_prepared["questions"] = queries
        repeat_prepared["nodes"] = nodes
        first_aggregate, first_rows, _ = score_snapshot(repeat_prepared, first_query, first_node)
        second_aggregate, second_rows, _ = score_snapshot(repeat_prepared, second_query, second_node)
        changed_rows = sum(left != right for left, right in zip(first_rows, second_rows))
        topk_boundary = {
            metric: stats for metric, stats in first_aggregate["ranking_boundary_gaps"].items()
        }
        result = {
            "run_id": args.run_id,
            "mode": "smoke",
            "status": "smoke_passed",
            "questions": len(queries),
            "databases": len(active_dbs),
            "nodes": len(nodes),
            "gpu_name": gpu_name,
            "repeat_encoder_max_abs_error": {"query": query_error, "node": node_error},
            "repeat_encoder_vectors_bit_exact": {"query": bool(np.array_equal(first_query, second_query)), "node": bool(np.array_equal(first_node, second_node))},
            "repeat_encoder_question_rows_changed": changed_rows,
            "repeat_encoder_question_rows_equal": first_rows == second_rows,
            "first_encoding_score_digest": first_aggregate["score_matrix_digest_sha256"],
            "second_encoding_score_digest": second_aggregate["score_matrix_digest_sha256"],
            "topk_boundary_gaps_first_encoding": topk_boundary,
            "topk_boundary_gaps_second_encoding": second_aggregate["ranking_boundary_gaps"],
            "table_question_denominator": first_aggregate["table_question_denominator"],
            "column_question_denominator": first_aggregate["column_question_denominator"],
            "runtime": {"gpu_wall_seconds_load_and_encode": time.perf_counter() - gpu_started},
        }
        if len(queries) != 5 or first_aggregate["table_question_denominator"] != 5 or not np.isfinite([query_error, node_error]).all():
            raise RuntimeError("P1.6 smoke did not meet the frozen 5-question data/embedding check")
        if result["column_question_denominator"] == 0:
            raise RuntimeError("P1.6 smoke has no eligible column-labeled questions")
        write_json(output_dir / "smoke_summary.json", result)
        return result

    query_vectors = encode_texts(encoder, torch, query_prompts, is_query=True)
    node_vectors = encode_texts(encoder, torch, node_texts, is_query=False)
    del encoder
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gpu_elapsed = time.perf_counter() - gpu_started
    if gpu_elapsed > MAX_GPU_SECONDS:
        raise RuntimeError(f"GPU wall budget exceeded: {gpu_elapsed:.2f}s")
    if query_vectors.shape != (1534, 1024) or node_vectors.shape != (873, 1024):
        raise RuntimeError("Full vector cache has unexpected shape")

    # Full mode must include all questions and every node, so preserve canonical order.
    if queries is not prepared["questions"] or len(nodes) != len(prepared["nodes"]):
        raise RuntimeError("Full run failed to select the complete frozen input")
    cache_path = output_dir / "embedding_cache_private.npz"
    np.savez_compressed(cache_path, query_vectors=query_vectors, node_vectors=node_vectors)
    vector_digest = sha256_bytes(query_vectors.tobytes() + node_vectors.tobytes())
    with np.load(cache_path, allow_pickle=False) as cache:
        cached_query_vectors = np.ascontiguousarray(cache["query_vectors"], dtype=np.float32)
        cached_node_vectors = np.ascontiguousarray(cache["node_vectors"], dtype=np.float32)
    cache_reload_bit_exact = np.array_equal(query_vectors, cached_query_vectors) and np.array_equal(node_vectors, cached_node_vectors)
    if not cache_reload_bit_exact:
        raise RuntimeError("Compressed private vector cache did not round-trip bit-exactly")

    pass1_aggregate, pass1_rows, pass1_digests = score_snapshot(prepared, cached_query_vectors, cached_node_vectors)
    pass2_aggregate, pass2_rows, pass2_digests = score_snapshot(prepared, cached_query_vectors, cached_node_vectors)
    exact_equal = (
        pass1_digests == pass2_digests
        and pass1_rows == pass2_rows
        and pass1_aggregate["score_matrix_digest_sha256"] == pass2_aggregate["score_matrix_digest_sha256"]
    )
    comparison = compare_new_to_p1_5(pass1_rows, args.p1_5_run_dir / "per_question_private.jsonl")
    if not exact_equal:
        raise RuntimeError("P1.6 scorer replay was not bit-exact on the frozen vector cache")
    if pass1_aggregate["table_question_denominator"] != 1534 or pass1_aggregate["column_question_denominator"] != 1460:
        raise RuntimeError("P1.6 denominator differs from the frozen protocol")

    private_rows_path = output_dir / "per_question_private.jsonl"
    with private_rows_path.open("w", encoding="utf-8") as file:
        for row in pass1_rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    public_aggregate = {
        "experiment_id": "p1_6_rebaseline_20261016",
        "run_id": args.run_id,
        "status": "completed",
        "source_commit": args.expected_commit,
        "encoding": {
            "queries": len(query_vectors),
            "schema_nodes": len(node_vectors),
            "dimension": 1024,
            "query_vectors_sha256": sha256_bytes(query_vectors.tobytes()),
            "node_vectors_sha256": sha256_bytes(node_vectors.tobytes()),
            "combined_vector_array_sha256": vector_digest,
        "private_npz_sha256": sha256_file(cache_path),
            "gpu_name": gpu_name,
            "gpu_id": args.gpu_id,
            "gpu_wall_seconds_load_and_encode": gpu_elapsed,
        },
        "scorer_replay": {
            "passes": 2,
            "bit_exact": exact_equal,
            "vector_cache_reload_bit_exact": cache_reload_bit_exact,
            "pass1_score_matrix_digest_sha256": pass1_digests["score_matrix_digest_sha256"],
            "pass2_score_matrix_digest_sha256": pass2_digests["score_matrix_digest_sha256"],
            "pass1_question_rows_digest_sha256": pass1_digests["question_rows_digest_sha256"],
            "pass2_question_rows_digest_sha256": pass2_digests["question_rows_digest_sha256"],
        },
        "p1_5_comparison": comparison,
        "metrics": pass1_aggregate,
        "private_artifacts": {
            "per_question_filename": private_rows_path.name,
            "per_question_sha256": sha256_file(private_rows_path),
        },
        "gate": "PASS" if exact_equal else "FAIL",
    }
    write_json(output_dir / "aggregate_summary.json", public_aggregate)
    return public_aggregate


def main() -> None:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cpu_started = time.process_time()
    source = assert_committed_source(args.expected_commit)
    resource_state = resource_snapshot(args.gpu_id)
    run_start: dict[str, Any] = {
        "experiment_id": "p1_6_rebaseline_20261016",
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "started",
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "source": source,
        "resource_snapshot": resource_state,
        "resource_budget": {"gpu_wall_seconds_max": MAX_GPU_SECONDS, "cpu_seconds_max": MAX_CPU_SECONDS, "process_maxrss_gib": MAX_RSS_GIB, "max_cpu_threads": MAX_THREADS},
        "environment": {"python": platform.python_version(), "numpy": package_version("numpy"), "torch": package_version("torch"), "vllm": package_version("vllm"), "transformers": package_version("transformers"), "sqlglot": package_version("sqlglot")},
        "no_api_calls": True,
        "no_dependency_installation": True,
        "no_model_download": True,
        "no_training": True,
        "no_sql_execution": True,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    if args.mode in ("smoke", "full"):
        selected_gpu = next((gpu for gpu in resource_state["nvidia_smi"].splitlines() if gpu.strip().startswith(f"{args.gpu_id},")), None)
        if selected_gpu is None:
            run_start["state"] = "stopped_resource_gate"
            run_start["resource_gate"] = {"reason": "selected GPU missing from nvidia-smi"}
            write_json(args.output_dir / "run_start.json", run_start)
            raise RuntimeError(f"Selected GPU {args.gpu_id} missing from resource snapshot")
        values = [value.strip() for value in selected_gpu.split(",")]
        if len(values) == 5:
            free_memory_mib = int(values[2]) - int(values[3])
            utilization = int(values[4])
            if free_memory_mib < 8192 or utilization > 50:
                run_start["state"] = "stopped_resource_gate"
                run_start["resource_gate"] = {"free_memory_mib": free_memory_mib, "utilization_percent": utilization, "minimum_free_memory_mib": 8192, "maximum_utilization_percent": 50}
                write_json(args.output_dir / "run_start.json", run_start)
                raise RuntimeError(f"Selected GPU is too busy for the registered run: free={free_memory_mib} MiB utilization={utilization}%")

    if args.mode == "full":
        if args.smoke_dir is None:
            raise RuntimeError("Full run requires the completed 5-question smoke directory")
        smoke_path = args.smoke_dir.resolve() / "smoke_summary.json"
        if not smoke_path.is_file():
            raise FileNotFoundError(f"Smoke receipt missing: {smoke_path}")
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if smoke.get("status") != "smoke_passed" or smoke.get("questions") != 5:
            raise RuntimeError("Full run blocked because the 5-question smoke did not pass")
    else:
        smoke = None
    if args.mode in ("smoke", "full"):
        if os.environ.get("CUDA_VISIBLE_DEVICES") != str(args.gpu_id) or os.environ.get("LOCAL_RANK") != str(args.gpu_id):
            raise RuntimeError(f"Expected CUDA_VISIBLE_DEVICES={args.gpu_id} and LOCAL_RANK={args.gpu_id}")

    helper, common = load_common(args.legacy_root, args.dataset_root, args.model_path)
    prepared = prepare_inputs(common)
    input_record = validate_inputs(prepared, common, args)
    if smoke is not None:
        smoke_input_hash = smoke.get("input_manifest_sha256")
        current_input_json = json.dumps(input_record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        current_input_hash = sha256_bytes(current_input_json.encode("utf-8"))
        smoke_input_record_path = args.smoke_dir.resolve() / "input_manifest_private.json"
        if not smoke_input_record_path.is_file() or sha256_file(smoke_input_record_path) != smoke_input_hash:
            raise RuntimeError("Smoke input manifest receipt does not match its saved file")
        if current_input_hash != smoke_input_hash:
            raise RuntimeError("Full input manifest differs from the smoke input manifest")
    mismatch_audit = historical_mismatch_audit(args)
    node_manifest = input_record.pop("ordered_node_manifest")
    write_json(args.output_dir / "ordered_node_manifest.json", node_manifest)
    write_json(args.output_dir / "input_manifest_private.json", input_record)
    write_json(args.output_dir / "historical_mismatch_audit.json", mismatch_audit)
    run_start.update({
        "state": "preflight_passed",
        "input_manifest_private_sha256": sha256_file(args.output_dir / "input_manifest_private.json"),
        "ordered_node_manifest_sha256": sha256_file(args.output_dir / "ordered_node_manifest.json"),
        "ordered_node_manifest_content_sha256": input_record["ordered_node_manifest_sha256"],
        "historical_mismatch_audit_sha256": sha256_file(args.output_dir / "historical_mismatch_audit.json"),
        "historical_vector_cache_available": False,
        "historical_per_candidate_scores_available": False,
        "historical_complete_rank_lists_available": False,
        "private_vector_cache_path": str(args.output_dir / "embedding_cache_private.npz") if args.mode == "full" else None,
    })
    write_json(args.output_dir / "run_start.json", run_start)

    if args.mode == "preflight":
        result = {"run_id": args.run_id, "mode": "preflight", "status": "preflight_passed", "counts": input_record["counts"], "schema_text_sha256": input_record["schema_text_sha256"], "query_prompt_sha256": input_record["query_prompt_sha256"], "ordered_node_manifest_content_sha256": input_record["ordered_node_manifest_sha256"], "historical_mismatch_audit": mismatch_audit}
        write_json(args.output_dir / "preflight_receipt.json", result)
    else:
        result = encode_and_score(args, common, prepared, args.output_dir)
        if args.mode == "smoke":
            receipt = {
                "run_id": args.run_id,
                "mode": "smoke",
                "status": "smoke_passed",
                "input_manifest_sha256": sha256_file(args.output_dir / "input_manifest_private.json"),
                "question_count": result["questions"],
                "schema_node_count": result["nodes"],
                "smoke_summary_sha256": sha256_file(args.output_dir / "smoke_summary.json"),
            }
            write_json(args.output_dir / "smoke_receipt.json", receipt)
        else:
            # The encoder/cache scorer replay is the P1.6 Gate; old P1/P1.5 remain failed historical checks.
            result["historical_p1_strict_reproduction_gate"] = "FAIL (unchanged)"
            result["historical_p1_5_strict_reproduction_gate"] = "FAIL (unchanged)"
            result["p1_6_gate"] = "PASS" if result["scorer_replay"]["bit_exact"] else "FAIL"
            write_json(args.output_dir / "aggregate_summary.json", result)

    cpu_seconds = time.process_time() - cpu_started
    maxrss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if cpu_seconds > MAX_CPU_SECONDS or maxrss_kib > MAX_RSS_GIB * 1024 * 1024:
        raise RuntimeError(f"CPU/RSS budget exceeded: cpu={cpu_seconds:.2f}s rss={maxrss_kib / 1024 / 1024:.2f}GiB")
    run_start.update({
        "state": "completed",
        "finished_elapsed_wall_seconds": time.perf_counter() - started,
        "cpu_seconds_process": cpu_seconds,
        "process_maxrss_gib": maxrss_kib / 1024 / 1024,
        "result_summary_sha256": sha256_file(args.output_dir / ("aggregate_summary.json" if args.mode == "full" else "smoke_summary.json" if args.mode == "smoke" else "preflight_receipt.json")),
    })
    write_json(args.output_dir / "run_start.json", run_start)
    print(json.dumps({"run_id": args.run_id, "mode": args.mode, "status": "completed", "output_dir": str(args.output_dir), "elapsed_wall_seconds": run_start["finished_elapsed_wall_seconds"], "cpu_seconds_process": cpu_seconds, "process_maxrss_gib": run_start["process_maxrss_gib"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
