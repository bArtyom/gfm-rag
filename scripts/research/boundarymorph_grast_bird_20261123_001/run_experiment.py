#!/usr/bin/env python3
"""Run the registered BoundaryMORPH-for-GRAST-SQL BIRD-dev pilot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "8"
os.environ["MKL_NUM_THREADS"] = "8"
os.environ["OPENBLAS_NUM_THREADS"] = "8"
os.environ["NUMEXPR_NUM_THREADS"] = "8"

import numpy as np


EXPERIMENT_ID = "boundarymorph_grast_bird_20261123_001"
METHODS = ("FixedTop16-GP", "Random16-GP", "BoundaryMORPH")
CONFIG_DEFAULT = Path(__file__).resolve().parents[3] / "configs/text2sql" / f"{EXPERIMENT_ID}.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object, atomic: bool = False) -> None:
    target = path.with_suffix(path.suffix + ".tmp") if atomic else path
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if atomic:
        os.replace(str(target), str(path))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def command_output(*args: str) -> str:
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {type(exc).__name__}"


def resource_snapshot(gpu_id: int) -> dict:
    gpu = command_output(
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    )
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "physical_gpu_id": gpu_id,
        "nvidia_smi_all_gpus": gpu,
        "free_h": command_output("free", "-h"),
        "cpu_threads": command_output("nproc"),
        "process_maxrss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024),
    }


def check_gpu_headroom(gpu_id: int, minimum_free_gib: float) -> None:
    output = command_output(
        "nvidia-smi",
        "--query-gpu=index,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    )
    if output.startswith("unavailable:"):
        raise RuntimeError(output)
    rows = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 3:
            rows[int(parts[0])] = (int(parts[1]), int(parts[2]))
    if gpu_id not in rows:
        raise RuntimeError(f"Physical GPU {gpu_id} is not visible in nvidia-smi")
    total_mib, used_mib = rows[gpu_id]
    free_gib = (total_mib - used_mib) / 1024.0
    if free_gib < minimum_free_gib:
        raise RuntimeError(
            f"GPU {gpu_id} has only {free_gib:.2f} GiB free; require {minimum_free_gib:.2f} GiB"
        )


def import_p1_support(config: dict, repo_root: Path):
    support_path = Path(config["historical_support"]["archive_support"])
    if sha256_file(support_path) != config["historical_support"]["archive_support_sha256"]:
        raise RuntimeError("Archived P1 schema-text helper hash mismatch")
    spec = importlib.util.spec_from_file_location("boundarymorph_gfmrag_p1_common", support_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import archived input helper: {support_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    dataset_root = Path(config["dataset"]["root"]).resolve()
    legacy_root = Path(config["historical_support"]["legacy_root"]).resolve()
    module.PROJECT_ROOT = legacy_root
    module.UPSTREAM_ROOT = repo_root
    module.DATA_ROOT = dataset_root
    module.DB_ROOT = dataset_root / "dev_databases"
    module.QUESTION_PATH = dataset_root / "dev.json"
    module.SCHEMA_PATH = dataset_root / "dev_tables.json"
    module.P0_AUDIT_PATH = legacy_root / "results/p0/full_audit_v3.json"
    module.GOLD_LABELS_PATH = legacy_root / "results/p1/full_1534_final_20261014/per_question_private.jsonl"
    module.MODEL_PATH = Path(config["cheap_retriever"]["model_path"]).resolve()
    module.DESCRIPTION_CSV_ENCODINGS.clear()
    return module


def read_query_order(path: Path) -> list[int]:
    question_ids = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                question_ids.append(int(json.loads(line)["question_id"]))
    return question_ids


def load_inputs(config: dict, repo_root: Path):
    common = import_p1_support(config, repo_root)
    # The archived SchemaNode dataclass requires token_count even when the
    # experiment does not use token lengths. Reuse the local Qwen tokenizer to
    # populate that field; this performs no model forward pass.
    prepared = common.prepare_p1_inputs(load_tokenizer=True)
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    if len(questions) != 1534 or len(nodes) != 873:
        raise RuntimeError(f"Unexpected frozen input size: q={len(questions)} nodes={len(nodes)}")
    if prepared["frozen_hashes"]["sha256"]["questions"] != config["dataset"]["questions_sha256"]:
        raise RuntimeError("BIRD question-file hash does not match the registered hash")
    if prepared["frozen_hashes"]["sha256"]["schema"] != config["dataset"]["schema_sha256"]:
        raise RuntimeError("BIRD schema-file hash does not match the registered hash")
    if prepared["frozen_hashes"]["sha256"]["gold_labels"] != config["historical_support"]["gold_labels_sha256"]:
        raise RuntimeError("Private frozen label hash does not match the registered hash")
    order_reference = read_query_order(Path(config["historical_support"]["query_order_reference"]))
    current_order = [int(row["question_id"]) for row in questions]
    if current_order != order_reference:
        raise RuntimeError("Question order differs from the cached Qwen query-vector order")
    return common, prepared


def load_vectors(config: dict, prepared: dict):
    cache_path = Path(config["cheap_retriever"]["cache_path"])
    if sha256_file(cache_path) != config["cheap_retriever"]["cache_sha256"]:
        raise RuntimeError("Cached Qwen embedding file hash mismatch")
    with np.load(str(cache_path), allow_pickle=False) as cache:
        if "query_vectors" not in cache or "node_vectors" not in cache:
            raise RuntimeError(f"Unexpected embedding cache members: {cache.files}")
        query_vectors = np.asarray(cache["query_vectors"], dtype=np.float32)
        node_vectors = np.asarray(cache["node_vectors"], dtype=np.float32)
    manifest_path = Path(config["cheap_retriever"]["ordered_node_manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if query_vectors.shape != (1534, 1024) or node_vectors.shape != (873, 1024):
        raise RuntimeError(
            f"Unexpected vector shapes: queries={query_vectors.shape} nodes={node_vectors.shape}"
        )
    if len(manifest) != node_vectors.shape[0]:
        raise RuntimeError("Ordered node manifest length does not match the cached vector rows")
    manifest = sorted(manifest, key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in manifest] != list(range(len(manifest))):
        raise RuntimeError("Node manifest ordinals are not contiguous")
    nodes_by_id = {node.node_id: node for node in prepared["nodes"]}
    if len(nodes_by_id) != len(prepared["nodes"]):
        raise RuntimeError("Duplicate schema node IDs")
    node_vector_by_id = {}
    ordinal_by_id = {}
    for row in manifest:
        node_id = row["node_id"]
        if node_id not in nodes_by_id or node_id in node_vector_by_id:
            raise RuntimeError(f"Cached node manifest has an unknown or duplicate node ID: {node_id}")
        if sha256_text(nodes_by_id[node_id].text) != row["text_sha256"]:
            raise RuntimeError(f"Cached vector text mismatch for schema node {node_id}")
        ordinal = int(row["ordinal"])
        node_vector_by_id[node_id] = node_vectors[ordinal]
        ordinal_by_id[node_id] = ordinal
    if len(node_vector_by_id) != len(nodes_by_id):
        raise RuntimeError("Cached vectors do not cover the full frozen schema")
    q_norms = np.linalg.norm(query_vectors, axis=1)
    if not np.isfinite(query_vectors).all() or np.any(q_norms <= 1e-12):
        raise RuntimeError("Cached query vectors contain non-finite values or zero norms")
    query_vectors = np.ascontiguousarray(query_vectors / q_norms[:, None], dtype=np.float32)
    for node_id, vector in node_vector_by_id.items():
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise RuntimeError(f"Cached schema vector has invalid norm: {node_id}")
        node_vector_by_id[node_id] = np.ascontiguousarray(vector / norm, dtype=np.float32)
    integrity = {
        "cache_sha256": sha256_file(cache_path),
        "manifest_sha256": sha256_file(manifest_path),
        "query_vector_shape": list(query_vectors.shape),
        "node_vector_shape": list(node_vectors.shape),
        "node_manifest_rows": len(manifest),
        "node_texts_aligned": True,
    }
    return query_vectors, node_vector_by_id, ordinal_by_id, integrity


def build_question_states(questions: list, prepared: dict, query_vectors: np.ndarray,
                          node_vector_by_id: dict, config: dict) -> list[dict]:
    pool_size = int(config["cheap_retriever"]["candidate_pool_size"])
    states = []
    for q_index, question in enumerate(questions):
        db_columns = [node for node in prepared["nodes_by_db"][question["db_id"]]
                      if node.node_type == "column"]
        if not db_columns:
            raise RuntimeError(f"Database has no column candidates: {question['db_id']}")
        qvec = query_vectors[q_index]
        scored = []
        for node in db_columns:
            vector = node_vector_by_id[node.node_id]
            scored.append((float(np.dot(qvec, vector)), node.node_id, node, vector))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[:min(pool_size, len(scored))]
        candidate_ids = [item[1] for item in selected]
        candidate_vectors = np.stack([item[3] for item in selected]).astype(np.float64)
        cheap_scores = np.asarray([item[0] for item in selected], dtype=np.float64)
        n = len(selected)
        if n == 1:
            prior = np.ones(1, dtype=np.float64)
        else:
            prior = np.linspace(1.0, 0.0, num=n, dtype=np.float64)
        cosine = np.clip(candidate_vectors @ candidate_vectors.T, -1.0, 1.0)
        off_diagonal = 1.0 - cosine[np.triu_indices(n, k=1)] if n > 1 else np.asarray([0.5])
        median_distance = max(float(np.median(off_diagonal)), 1e-6)
        kappa = float(np.log(2.0) / median_distance)
        kernel = np.exp(kappa * (cosine - 1.0))
        query_cosine = np.clip(candidate_vectors @ qvec.astype(np.float64), -1.0, 1.0)
        anchor_kernel = np.exp(kappa * (query_cosine - 1.0))
        augmented_kernel = np.empty((n + 1, n + 1), dtype=np.float64)
        augmented_kernel[0, 0] = 1.0
        augmented_kernel[0, 1:] = anchor_kernel
        augmented_kernel[1:, 0] = anchor_kernel
        augmented_kernel[1:, 1:] = kernel
        states.append({
            "question_id": int(question["question_id"]),
            "db_id": question["db_id"],
            "question_text": question["text"],
            "label": question["label"],
            "candidate_ids": candidate_ids,
            "candidate_texts": [item[2].text for item in selected],
            "cheap_scores": cheap_scores,
            "prior": prior,
            "kernel": augmented_kernel,
            "kappa": kappa,
            "median_distance": median_distance,
            "budget": min(int(config["selection"]["score_budget"]), n),
            "capacity": min(int(config["selection"]["final_core_capacity"]), n),
            "n": n,
            "boundary_fallback_count": 0,
        })
    return states


def gp_posterior(state: dict, observations: list[tuple[int, float]], config: dict):
    n = state["n"]
    prior = state["prior"]
    kernel = state["kernel"]
    observed_candidate_ids = [int(observation[0]) for observation in observations]
    observed_augmented = [0] + [index + 1 for index in observed_candidate_ids]
    observed_scores = [1.0] + [float(observation[1]) for observation in observations]
    observed_prior = [1.0] + [float(prior[index]) for index in observed_candidate_ids]
    residual = np.asarray(observed_scores, dtype=np.float64) - np.asarray(observed_prior, dtype=np.float64)
    residual_mean = float(np.mean(residual))
    residual_scale = max(
        float(np.std(residual)),
        float(config["selection"]["residual_standardization_floor"]),
    )
    standardized = (residual - residual_mean) / residual_scale
    k_oo = kernel[np.ix_(observed_augmented, observed_augmented)].copy()
    k_oo.flat[::len(k_oo) + 1] += float(config["selection"]["gp_jitter"])
    k_xo = kernel[1:, observed_augmented]
    try:
        alpha = np.linalg.solve(k_oo, standardized)
        solved = np.linalg.solve(k_oo, k_xo.T)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError("GP covariance solve failed") from exc
    mean = prior + residual_mean + residual_scale * (k_xo @ alpha)
    variance = np.maximum(np.diag(kernel)[1:] - np.sum(k_xo * solved.T, axis=1), 0.0)
    sigma = residual_scale * np.sqrt(variance)
    if not np.isfinite(mean).all() or not np.isfinite(sigma).all():
        raise RuntimeError("GP posterior produced non-finite values")
    return mean, sigma


def choose_boundary_candidate(state: dict, observations: list[tuple[int, float]],
                              config: dict) -> int:
    mean, sigma = gp_posterior(state, observations, config)
    observed = {index for index, _score in observations}
    unobserved = [index for index in range(state["n"]) if index not in observed]
    if not unobserved:
        raise RuntimeError("Boundary acquisition exhausted the candidate pool")
    capacity = state["capacity"]
    if capacity >= state["n"]:
        state["boundary_fallback_count"] += 1
        return min(unobserved, key=lambda index: (-sigma[index], state["candidate_ids"][index]))
    ranked = sorted(range(state["n"]), key=lambda index: (-mean[index], state["candidate_ids"][index]))
    inside = ranked[:capacity]
    outside = ranked[capacity:]
    best = None
    for left in inside:
        for right in outside:
            possible = [index for index in (left, right) if index not in observed]
            if not possible:
                continue
            gap = (mean[left] - mean[right]) / (sigma[left] + sigma[right] + 1e-12)
            chosen = min(possible, key=lambda index: (-sigma[index], state["candidate_ids"][index]))
            pair_key = tuple(sorted((state["candidate_ids"][left], state["candidate_ids"][right])))
            key = (float(gap), pair_key, state["candidate_ids"][chosen])
            if best is None or key < best[0]:
                best = (key, chosen)
    if best is None:
        state["boundary_fallback_count"] += 1
        return min(unobserved, key=lambda index: (-sigma[index], state["candidate_ids"][index]))
    return best[1]


def deterministic_random_order(state: dict, seed: int) -> list[int]:
    question_id = state["question_id"]
    return sorted(
        range(state["n"]),
        key=lambda index: (
            hashlib.sha256(
                f"{seed}:{question_id}:{state['candidate_ids'][index]}".encode("utf-8")
            ).hexdigest(),
            state["candidate_ids"][index],
        ),
    )


def load_scorer(config: dict, device: str):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_path = Path(config["query_aware_score_proxy"]["model_path"]).resolve()
    revision_path = model_path / "revision.txt"
    if revision_path.read_text(encoding="utf-8").strip() != config["query_aware_score_proxy"]["revision"]:
        raise RuntimeError("Local Jina reranker revision does not match the registered revision")
    weights_path = model_path / "model.safetensors"
    if sha256_file(weights_path) != config["query_aware_score_proxy"]["weights_sha256"]:
        raise RuntimeError("Local Jina reranker weights hash mismatch")
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_path), local_files_only=True, trust_remote_code=True
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_path),
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model.to(device)
    model.eval()
    if int(model.config.num_labels) != 1:
        raise RuntimeError(f"Expected a scalar reranker logit; found {model.config.num_labels} labels")
    return tokenizer, model


def infer_pairs(pairs: list[tuple[str, str]], tokenizer, model, device: str,
                config: dict, runtime: dict) -> list[tuple[float, int]]:
    import torch

    results = []
    batch_size = int(config["query_aware_score_proxy"]["batch_size"])
    max_length = int(config["query_aware_score_proxy"]["max_length"])
    for start in range(0, len(pairs), batch_size):
        check_runtime_budget(runtime, config)
        batch = pairs[start:start + batch_size]
        queries = [pair[0] for pair in batch]
        documents = [pair[1] for pair in batch]
        encoded = tokenizer(
            queries,
            documents,
            max_length=max_length,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )
        token_counts = encoded["attention_mask"].sum(dim=1).tolist()
        token_count = int(sum(token_counts))
        encoded = {key: value.to(device) for key, value in encoded.items()}
        start_event = torch.cuda.Event(enable_timing=True)
        end_event = torch.cuda.Event(enable_timing=True)
        start_event.record()
        with torch.inference_mode():
            logits = model(**encoded).logits.float().reshape(-1)
            probabilities = torch.sigmoid(logits)
        end_event.record()
        end_event.synchronize()
        scores = probabilities.detach().cpu().tolist()
        if len(scores) != len(batch) or not np.isfinite(np.asarray(scores)).all():
            raise RuntimeError("Reranker returned malformed or non-finite scores")
        runtime["gpu_inference_seconds"] += float(start_event.elapsed_time(end_event)) / 1000.0
        runtime["scorer_wall_seconds"] += 0.0
        runtime["forward_batches"] += 1
        runtime["query_column_pairs"] += len(batch)
        runtime["input_tokens"] += token_count
        runtime["max_pair_input_tokens"] = max(runtime["max_pair_input_tokens"], max(token_counts))
        results.extend((float(score), int(tokens)) for score, tokens in zip(scores, token_counts))
        del encoded, logits, probabilities
    return results


def check_runtime_budget(runtime: dict, config: dict) -> None:
    resources = config["resources"]
    wall = time.perf_counter() - runtime["wall_started"]
    cpu = time.process_time() - runtime["cpu_started"]
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    if wall > float(resources["wall_seconds_max"]):
        raise RuntimeError("Overall wall-time ceiling reached; partial state is preserved")
    if cpu > float(resources["cpu_seconds_max"]):
        raise RuntimeError("CPU-time budget reached; partial state is preserved")
    if rss_gib > float(resources["rss_gib_max"]):
        raise RuntimeError("RSS budget reached; partial state is preserved")
    if runtime["gpu_inference_seconds"] > float(resources["gpu_seconds_max"]):
        raise RuntimeError("GPU inference budget reached; partial state is preserved")


def summarize_question(state: dict, method: str, observations: list[tuple[int, float, int]],
                       config: dict) -> dict:
    gp_observations = [(index, score) for index, score, _tokens in observations]
    posterior_mean, posterior_sigma = gp_posterior(state, gp_observations, config)
    core = sorted(
        range(state["n"]),
        key=lambda index: (-posterior_mean[index], state["candidate_ids"][index]),
    )[:state["capacity"]]
    core_ids = [state["candidate_ids"][index] for index in core]
    gold_ids = list(state["label"]["gold_column_ids"])
    gold_set = set(gold_ids)
    candidate_set = set(state["candidate_ids"])
    candidate_rank = {node_id: index + 1 for index, node_id in enumerate(state["candidate_ids"])}
    below16 = [node_id for node_id in gold_set
               if node_id in candidate_rank and candidate_rank[node_id] > 16]
    hit_count = len(gold_set.intersection(core_ids))
    candidate_hit_count = len(gold_set.intersection(candidate_set))
    eligible = bool(state["label"]["column_eligible"])
    return {
        "question_id": state["question_id"],
        "db_id": state["db_id"],
        "method": method,
        "column_eligible": eligible,
        "gold_column_count": len(gold_ids) if eligible else None,
        "gold_column_ids_private": gold_ids if eligible else [],
        "candidate_ids_private": state["candidate_ids"],
        "candidate_pool_complete": bool(eligible and gold_set.issubset(candidate_set)),
        "candidate_column_hits": candidate_hit_count if eligible else None,
        "gold_columns_ranked_below16_in_pool": len(below16) if eligible else None,
        "below16_gold_columns_recovered": len(gold_set.intersection(below16).intersection(core_ids)) if eligible else None,
        "selected_core_ids_private": core_ids,
        "selected_gold_hits": hit_count if eligible else None,
        "full_recall_at_capacity": bool(eligible and gold_set.issubset(set(core_ids))),
        "column_recall_at_capacity": (hit_count / len(gold_ids)) if eligible and gold_ids else None,
        "column_precision_at_capacity": (hit_count / len(core_ids)) if eligible and core_ids else None,
        "score_budget": len(observations),
        "selected_observations_private": [
            {"node_id": state["candidate_ids"][index], "score": float(score), "input_tokens": int(tokens)}
            for index, score, tokens in observations
        ],
        "boundary_fallback_count": state["boundary_fallback_count"] if method == "BoundaryMORPH" else 0,
        "posterior_score_range": [float(np.min(posterior_mean)), float(np.max(posterior_mean))],
        "posterior_sigma_median": float(np.median(posterior_sigma)),
    }


def make_method_output(states: list[dict], method: str, observations_by_qid: dict,
                       config: dict, path: Path) -> list[dict]:
    rows = []
    for state in states:
        obs = observations_by_qid.get(state["question_id"], [])
        rows.append(summarize_question(state, method, obs, config))
    write_jsonl(path, rows)
    return rows


def aggregate_method(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row["column_eligible"]]
    if not eligible:
        return {"eligible_questions": 0, "full_recall_at_30": None,
                "macro_column_recall_at_30": None, "macro_column_precision_at_30": None}
    complete = [row for row in eligible if row["candidate_pool_complete"]]
    full_count = sum(bool(row["full_recall_at_capacity"]) for row in eligible)
    pool_full_count = sum(bool(row["candidate_pool_complete"]) for row in eligible)
    gold_total = sum(int(row["gold_column_count"]) for row in eligible)
    candidate_hits = sum(int(row["candidate_column_hits"]) for row in eligible)
    column_hits = sum(int(row["selected_gold_hits"]) for row in eligible)
    recalls = [float(row["column_recall_at_capacity"]) for row in eligible]
    precisions = [float(row["column_precision_at_capacity"]) for row in eligible]
    complete_full = sum(bool(row["full_recall_at_capacity"]) for row in complete)
    return {
        "eligible_questions": len(eligible),
        "full_recall_at_30": full_count / len(eligible),
        "full_recall_count": full_count,
        "candidate_pool_full_recall": pool_full_count / len(eligible),
        "candidate_pool_complete_questions": pool_full_count,
        "macro_candidate_column_recall": float(np.mean([
            int(row["candidate_column_hits"]) / int(row["gold_column_count"]) for row in eligible
        ])),
        "micro_candidate_column_recall": candidate_hits / gold_total,
        "conditional_full_recall_given_candidate_complete": (
            complete_full / len(complete) if complete else None
        ),
        "candidate_complete_denominator": len(complete),
        "macro_column_recall_at_30": float(np.mean(recalls)),
        "micro_column_recall_at_30": column_hits / gold_total,
        "macro_column_precision_at_30": float(np.mean(precisions)),
        "gold_columns_ranked_below16_in_pool": sum(
            int(row["gold_columns_ranked_below16_in_pool"]) for row in eligible
        ),
        "below16_gold_columns_recovered": sum(
            int(row["below16_gold_columns_recovered"]) for row in eligible
        ),
        "gold_columns_total": gold_total,
    }


def cluster_bootstrap(method_rows: dict, draws: int, seed: int) -> dict:
    eligible_by_method = {
        method: {row["question_id"]: row for row in rows if row["column_eligible"]}
        for method, rows in method_rows.items()
    }
    base_rows = next(iter(eligible_by_method.values()))
    dbs = sorted({row["db_id"] for row in base_rows.values()})
    db_indices = {db: [] for db in dbs}
    for index, row in enumerate(base_rows.values()):
        db_indices[row["db_id"]].append(index)
    qids = list(base_rows.keys())
    qid_index = {qid: index for index, qid in enumerate(qids)}
    count_by_db = np.asarray([len(db_indices[db]) for db in dbs], dtype=np.int64)
    hits_by_method = {}
    for method, rows in eligible_by_method.items():
        if set(rows) != set(qids):
            raise RuntimeError("Method outputs do not contain the same eligible question IDs")
        hits_by_method[method] = np.asarray(
            [int(rows[qid]["full_recall_at_capacity"]) for qid in qids], dtype=np.int64
        )
    hits_by_db = {
        method: np.asarray([
            sum(int(eligible_by_method[method][qid]["full_recall_at_capacity"])
                for qid in base_rows if base_rows[qid]["db_id"] == db)
            for db in dbs
        ], dtype=np.int64)
        for method in eligible_by_method
    }
    rng = np.random.default_rng(seed)
    rates = {method: np.empty(draws, dtype=np.float64) for method in eligible_by_method}
    differences = {
        "BoundaryMORPH_minus_FixedTop16-GP": np.empty(draws, dtype=np.float64),
        "BoundaryMORPH_minus_Random16-GP": np.empty(draws, dtype=np.float64),
    }
    for draw in range(draws):
        sampled = rng.integers(0, len(dbs), size=len(dbs))
        denominator = int(count_by_db[sampled].sum())
        for method in eligible_by_method:
            rates[method][draw] = float(hits_by_db[method][sampled].sum()) / denominator
        differences["BoundaryMORPH_minus_FixedTop16-GP"][draw] = (
            rates["BoundaryMORPH"][draw] - rates["FixedTop16-GP"][draw]
        )
        differences["BoundaryMORPH_minus_Random16-GP"][draw] = (
            rates["BoundaryMORPH"][draw] - rates["Random16-GP"][draw]
        )
    return {
        "replicates": draws,
        "seed": seed,
        "cluster": "db_id",
        "method_rate_95_ci": {
            method: [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
            for method, values in rates.items()
        },
        "paired_difference_95_ci": {
            name: [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
            for name, values in differences.items()
        },
    }


def compute_aggregate(method_rows: dict, config: dict, mode: str) -> dict:
    aggregates = {method: aggregate_method(rows) for method, rows in method_rows.items()}
    eligible_count = aggregates["FixedTop16-GP"]["eligible_questions"]
    if eligible_count == 0:
        if mode != "smoke":
            raise RuntimeError("Full run unexpectedly has no eligible questions")
        return {
            "experiment_id": EXPERIMENT_ID,
            "methods": aggregates,
            "candidate_pool_ceiling": {"supports_selection_analysis": None},
            "paired_rescue_damage_vs_fixed": {},
            "boundary_gain_percentage_points": {},
            "bootstrap_95_ci": None,
            "exploratory_decision": "SMOKE_ONLY_NO_ELIGIBLE_QUESTIONS",
            "decision_gate_passed": None,
        }
    base = {row["question_id"]: row for row in method_rows["FixedTop16-GP"]}
    paired = {}
    for method in ("Random16-GP", "BoundaryMORPH"):
        rows = {row["question_id"]: row for row in method_rows[method]}
        eligible_qids = [qid for qid, row in base.items() if row["column_eligible"]]
        rescued = sum(
            bool(rows[qid]["full_recall_at_capacity"])
            and not bool(base[qid]["full_recall_at_capacity"])
            for qid in eligible_qids
        )
        damaged = sum(
            not bool(rows[qid]["full_recall_at_capacity"])
            and bool(base[qid]["full_recall_at_capacity"])
            for qid in eligible_qids
        )
        paired[method] = {"rescued_vs_fixed": rescued, "damaged_vs_fixed": damaged}
    pool_fraction = aggregates["FixedTop16-GP"]["candidate_pool_full_recall"]
    gains_pp = {
        "vs_fixed": 100.0 * (aggregates["BoundaryMORPH"]["full_recall_at_30"]
                              - aggregates["FixedTop16-GP"]["full_recall_at_30"]),
        "vs_random": 100.0 * (aggregates["BoundaryMORPH"]["full_recall_at_30"]
                               - aggregates["Random16-GP"]["full_recall_at_30"]),
    }
    threshold = float(config["selection"]["candidate_complete_min_fraction"])
    required_gain = float(config["evaluation"]["minimum_gain_over_each_baseline_pp"])
    ceiling_supports_analysis = pool_fraction >= threshold
    gate_pass = ceiling_supports_analysis and all(value >= required_gain for value in gains_pp.values())
    per_database = {}
    for db_id in sorted({row["db_id"] for row in base.values()}):
        per_database[db_id] = {
            method: aggregate_method([
                row for row in method_rows[method]
                if row["db_id"] == db_id and row["column_eligible"]
            ])
            for method in METHODS
        }
    bootstrap = None if mode == "smoke" else cluster_bootstrap(
        method_rows,
        int(config["evaluation"]["bootstrap_replicates"]),
        int(config["evaluation"]["bootstrap_seed"]),
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "methods": aggregates,
        "per_database_private": per_database,
        "candidate_pool_ceiling": {
            "candidate_pool_full_recall": pool_fraction,
            "minimum_fraction_for_selection_analysis": threshold,
            "supports_selection_analysis": ceiling_supports_analysis,
            "macro_candidate_column_recall": aggregates["FixedTop16-GP"]["macro_candidate_column_recall"],
            "micro_candidate_column_recall": aggregates["FixedTop16-GP"]["micro_candidate_column_recall"],
        },
        "paired_rescue_damage_vs_fixed": paired,
        "boundary_gain_percentage_points": gains_pp,
        "bootstrap_95_ci": bootstrap,
        "exploratory_decision": (
            "SMOKE_ONLY" if mode == "smoke" else
            ("KEEP_FOR_SEPARATE_REPLICATION" if gate_pass else "STOP_NO_GO")
        ),
        "decision_gate_passed": None if mode == "smoke" else gate_pass,
    }


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--registered-commit", required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    repo_root = Path(__file__).resolve().parents[3]
    if config["experiment_id"] != EXPERIMENT_ID:
        raise RuntimeError("Experiment ID in config does not match this runner")
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse existing output directory: {args.output_dir}")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(config["resources"]["physical_gpu_id"]):
        raise RuntimeError("CUDA_VISIBLE_DEVICES does not match the registered physical GPU")
    check_gpu_headroom(
        int(config["resources"]["physical_gpu_id"]),
        float(config["resources"]["minimum_free_gpu_gib"]),
    )
    head = git_output(repo_root, "rev-parse", "HEAD")
    branch = git_output(repo_root, "branch", "--show-current")
    status = git_output(repo_root, "status", "--short")
    if head != args.registered_commit:
        raise RuntimeError(f"Registered source commit mismatch: expected={args.registered_commit} actual={head}")
    if status:
        raise RuntimeError(f"Repository is dirty before run start: {status}")
    if not platform.python_version().startswith("3.10."):
        raise RuntimeError(f"Expected qes_jina_rerank Python 3.10, found {platform.python_version()}")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in the selected environment")
    device = "cuda:0"
    source_files = {
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(args.config.resolve()),
        "protocol_sha256": sha256_file(repo_root / "experiments" / EXPERIMENT_ID / "protocol.md"),
        "archive_support_sha256": sha256_file(Path(config["historical_support"]["archive_support"])),
    }
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    runtime = {
        "wall_started": started_wall,
        "cpu_started": started_cpu,
        "gpu_inference_seconds": 0.0,
        "scorer_wall_seconds": 0.0,
        "forward_batches": 0,
        "query_column_pairs": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "max_pair_input_tokens": 0,
    }
    run_start = {
        "experiment_id": EXPERIMENT_ID,
        "mode": args.mode,
        "run_id": args.output_dir.name,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "project_repository": "https://github.com/bArtyom/gfm-rag",
        "project_branch": branch,
        "project_commit": head,
        "project_worktree_status": status,
        "source_files": source_files,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "transformers": __import__("transformers").__version__,
            "numpy": np.__version__,
        },
        "gpu": {
            "physical_id": int(config["resources"]["physical_gpu_id"]),
            "logical_device": device,
            "name": torch.cuda.get_device_name(0),
        },
        "resource_budget": config["resources"],
        "resource_snapshot_start": resource_snapshot(int(config["resources"]["physical_gpu_id"])),
        "no_external_api_calls": True,
        "no_model_download": True,
        "no_dependency_installation": True,
        "no_training": True,
        "no_sql_execution": True,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    print(f"[{args.mode}] source={head} branch={branch} gpu=1", flush=True)

    common, prepared = load_inputs(config, repo_root)
    query_vectors, node_vector_by_id, ordinal_by_id, vector_integrity = load_vectors(config, prepared)
    states = build_question_states(prepared["questions"], prepared, query_vectors,
                                   node_vector_by_id, config)
    if args.mode == "smoke":
        count = int(config["evaluation"]["smoke_question_count"])
        states = sorted(
            states,
            key=lambda state: hashlib.sha256(str(state["question_id"]).encode("utf-8")).hexdigest(),
        )[:count]
    if args.mode == "smoke" and len(states) != int(config["evaluation"]["smoke_question_count"]):
        raise RuntimeError("Smoke sample does not contain the registered number of questions")
    input_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "mode": args.mode,
        "question_count_scored": len(states),
        "column_eligible_scored": sum(bool(state["label"]["column_eligible"]) for state in states),
        "database_count_scored": len({state["db_id"] for state in states}),
        "schema_node_count": len(prepared["nodes"]),
        "column_node_count": sum(node.node_type == "column" for node in prepared["nodes"]),
        "label_counts": prepared["label_counts"],
        "input_hashes": prepared["frozen_hashes"]["sha256"],
        "vector_integrity": vector_integrity,
        "node_ordinals_by_id_sha256": sha256_text(json.dumps(ordinal_by_id, sort_keys=True)),
        "description_csv_encoding_counts": prepared["description_csv_encoding_counts"],
        "candidate_pool_size": int(config["cheap_retriever"]["candidate_pool_size"]),
        "score_budget": int(config["selection"]["score_budget"]),
        "final_core_capacity": int(config["selection"]["final_core_capacity"]),
        "gold_used_for_candidate_generation_or_acquisition": False,
        "gold_used_for_evaluation_only": True,
    }
    write_json(args.output_dir / "input_manifest_private.json", input_manifest)
    tokenizer, model = load_scorer(config, device)
    torch.cuda.reset_peak_memory_stats(0)
    print(f"[{args.mode}] inputs aligned; selected_questions={len(states)}; scorer loaded", flush=True)

    method_rows = {}
    for method in METHODS:
        observations_by_qid = {state["question_id"]: [] for state in states}
        random_orders = {
            state["question_id"]: deterministic_random_order(
                state, int(config["selection"]["random_seed"])
            )
            for state in states
        }
        max_budget = max((state["budget"] for state in states), default=0)
        for round_index in range(max_budget):
            pending = []
            pairs = []
            for state in states:
                observations = observations_by_qid[state["question_id"]]
                if len(observations) >= state["budget"]:
                    continue
                if method == "FixedTop16-GP":
                    candidate_index = len(observations)
                elif method == "Random16-GP":
                    candidate_index = random_orders[state["question_id"]][len(observations)]
                else:
                    candidate_index = choose_boundary_candidate(state, observations, config)
                pending.append((state, candidate_index))
                pairs.append((state["question_text"], state["candidate_texts"][candidate_index]))
            if not pending:
                break
            scoring_started = time.perf_counter()
            scores = infer_pairs(pairs, tokenizer, model, device, config, runtime)
            runtime["scorer_wall_seconds"] += time.perf_counter() - scoring_started
            for (state, candidate_index), (score, token_count) in zip(pending, scores):
                observations_by_qid[state["question_id"]].append((candidate_index, score, token_count))
            progress = {
                "mode": args.mode,
                "method": method,
                "completed_rounds": round_index + 1,
                "max_rounds": max_budget,
                "scored_questions_this_round": len(pending),
                "query_column_pairs": runtime["query_column_pairs"],
                "input_tokens": runtime["input_tokens"],
                "gpu_inference_seconds": runtime["gpu_inference_seconds"],
                "wall_seconds": time.perf_counter() - started_wall,
            }
            write_json(args.output_dir / "progress.json", progress, atomic=True)
            print(
                f"[{args.mode}] {method} round={round_index + 1}/{max_budget} "
                f"pairs={runtime['query_column_pairs']} gpu_s={runtime['gpu_inference_seconds']:.1f}",
                flush=True,
            )
        method_path = args.output_dir / f"{method.replace('-', '_').replace(' ', '_')}_private.jsonl"
        method_rows[method] = make_method_output(states, method, observations_by_qid, config, method_path)
        for state in states:
            if len(observations_by_qid[state["question_id"]]) != state["budget"]:
                raise RuntimeError(
                    f"Score-budget mismatch for {method}, question_id={state['question_id']}"
                )
        check_runtime_budget(runtime, config)

    if args.mode == "full":
        if len(states) != 1534 or sum(bool(state["label"]["column_eligible"]) for state in states) != int(
            config["dataset"]["eligible_questions_expected"]
        ):
            raise RuntimeError("Full-run question or eligibility count does not match registration")
    aggregate = compute_aggregate(method_rows, config, args.mode)
    write_json(args.output_dir / "aggregate_private.json", aggregate)
    combined = [
        {"question_id": row["question_id"], "db_id": row["db_id"], "method": method,
         "column_eligible": row["column_eligible"],
         "full_recall_at_capacity": row["full_recall_at_capacity"],
         "candidate_pool_complete": row["candidate_pool_complete"],
         "column_recall_at_capacity": row["column_recall_at_capacity"],
         "column_precision_at_capacity": row["column_precision_at_capacity"]}
        for method in METHODS for row in method_rows[method]
    ]
    write_jsonl(args.output_dir / "per_question_private.jsonl", combined)
    reread = {method: read_jsonl(args.output_dir / f"{method.replace('-', '_').replace(' ', '_')}_private.jsonl")
              for method in METHODS}
    independently_recomputed = compute_aggregate(reread, config, args.mode)
    if json.dumps(aggregate, sort_keys=True) != json.dumps(independently_recomputed, sort_keys=True):
        raise RuntimeError("Independent aggregate recomputation did not match the saved rows")
    run_complete = {
        "experiment_id": EXPERIMENT_ID,
        "mode": args.mode,
        "run_id": args.output_dir.name,
        "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "completed",
        "project_commit": head,
        "aggregate_sha256": sha256_file(args.output_dir / "aggregate_private.json"),
        "per_question_private_sha256": sha256_file(args.output_dir / "per_question_private.jsonl"),
        "model_usage": {
            "scorer_query_column_pairs": runtime["query_column_pairs"],
            "forward_batches": runtime["forward_batches"],
            "actual_input_tokens_after_truncation": runtime["input_tokens"],
            "output_tokens": runtime["output_tokens"],
            "scorer_max_pair_input_tokens": runtime["max_pair_input_tokens"],
        },
        "runtime": {
            "wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds_process": time.process_time() - started_cpu,
            "gpu_inference_seconds": runtime["gpu_inference_seconds"],
            "scorer_wall_seconds": runtime["scorer_wall_seconds"],
            "process_maxrss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024),
            "gpu_peak_allocated_gib": torch.cuda.max_memory_allocated(0) / (1024 ** 3),
        },
        "resource_snapshot_end": resource_snapshot(int(config["resources"]["physical_gpu_id"])),
        "external_api_attempts": 0,
        "independent_aggregate_recomputation": "passed",
        "exploratory_decision": aggregate["exploratory_decision"],
    }
    write_json(args.output_dir / "run_complete.json", run_complete)
    print(
        f"[{args.mode}] completed; eligible={aggregate['methods']['BoundaryMORPH']['eligible_questions']} "
        f"boundary_full_recall={aggregate['methods']['BoundaryMORPH']['full_recall_at_30']:.4f} "
        f"decision={aggregate['exploratory_decision']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
