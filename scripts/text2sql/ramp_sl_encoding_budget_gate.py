#!/usr/bin/env python3
"""Run the preregistered, local RAMP-SL encoder-budget upper-bound gate.

Question-level ranks/scores and all field IDs stay in the private result folder.
The public summary contains aggregate metrics only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import platform
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "8"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_5_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_5_diagnostics.py"
P1_6_RESULT = Path("/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01")
EMBEDDING_MODEL = Path("/mnt/liansp3/sources/models/qwen3-embedding-0.6b")
PROMPT_PREFIX = """<|im_start|>system
Judge whether the column (Document) is necessary to use when writing the SQL query, based on the provided Query and Instruct. Note that the answer can only be \"yes\" or \"no\".<|im_end|>
<|im_start|>user
"""
PROMPT_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
INSTRUCTION = "Given a natural-language database question (Query) and a Column description (Document), decide if the column may be necessary to answer the question."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load local helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def normalized(vectors: np.ndarray, label: str) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(vectors).all() or not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        raise RuntimeError(f"Invalid or zero {label} embedding vector")
    return np.ascontiguousarray(vectors / norms[:, None], dtype=np.float32)


def stable_order(scores: np.ndarray, ids: list[str]) -> list[int]:
    return [int(i) for i in np.lexsort((np.asarray(ids, dtype=str), -np.asarray(scores, dtype=np.float32)))]


def load_frozen_inputs(config: dict[str, Any]) -> dict[str, Any]:
    helper = load_module(P1_5_RUNNER, "ramp_sl_p1_5_helper")
    dataset_root = Path(config["dataset"]["questions_path"]).parent.resolve()
    legacy_root = Path(config["dataset"]["legacy_p1_root"]).resolve()
    common = helper.load_p1_support(legacy_root, dataset_root, EMBEDDING_MODEL.resolve())
    prepared = common.prepare_p1_inputs(load_tokenizer=True)

    questions = prepared["questions"]
    nodes = sorted(prepared["nodes"], key=lambda node: node.node_type != "table")
    if len(questions) != 1534 or len(nodes) != 873:
        raise RuntimeError(f"Frozen P1.6 input size mismatch: questions={len(questions)} nodes={len(nodes)}")

    cache_path = Path(config["cheap_rank_cache"]["path"])
    rank_path = Path(config["gold_rank_source"])
    manifest_path = P1_6_RESULT / "ordered_node_manifest.json"
    for required in (cache_path, rank_path, manifest_path, P1_6_RESULT / "run_start.json", P1_6_RESULT / "aggregate_summary.json"):
        if not required.is_file():
            raise FileNotFoundError(f"Frozen P1.6 artifact missing: {required}")

    start_record = json.loads((P1_6_RESULT / "run_start.json").read_text(encoding="utf-8"))
    summary = json.loads((P1_6_RESULT / "aggregate_summary.json").read_text(encoding="utf-8"))
    if start_record.get("run_id") != "p1_6_full1534_20261018_01" or start_record.get("state") != "completed":
        raise RuntimeError("Unexpected P1.6 reference run")
    if start_record.get("ordered_node_manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError("P1.6 ordered-node manifest hash mismatch")
    if start_record.get("input_manifest_private_sha256") != sha256_file(P1_6_RESULT / "input_manifest_private.json"):
        raise RuntimeError("P1.6 input manifest hash mismatch")
    if start_record.get("result_summary_sha256") != sha256_file(P1_6_RESULT / "aggregate_summary.json"):
        raise RuntimeError("P1.6 summary hash mismatch")
    if summary.get("p1_6_gate") != "PASS" or summary.get("gate") != "PASS":
        raise RuntimeError("P1.6 frozen reference gate is not PASS")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest) != len(nodes):
        raise RuntimeError("P1.6 ordered-node manifest length mismatch")
    manifest_mismatches = 0
    for index, (node, item) in enumerate(zip(nodes, manifest)):
        if item.get("ordinal") != index or item.get("node_id") != node.node_id or item.get("db_id") != node.db_id or item.get("node_type") != node.node_type:
            raise RuntimeError(f"P1.6 node identity/order mismatch at ordinal {index}")
        if item.get("text_sha256") != sha256_bytes(node.text.encode("utf-8")):
            manifest_mismatches += 1
        if int(item.get("token_count", -1)) != int(node.token_count):
            raise RuntimeError(f"P1.6 node token count mismatch at ordinal {index}")
    if manifest_mismatches:
        raise RuntimeError(f"P1.6 schema-description hashes differ for {manifest_mismatches} nodes")

    with np.load(cache_path, allow_pickle=False) as cache:
        if set(cache.files) != {"query_vectors", "node_vectors"}:
            raise RuntimeError("Unexpected P1.6 embedding cache fields")
        query_vectors = np.ascontiguousarray(cache["query_vectors"], dtype=np.float32)
        node_vectors = np.ascontiguousarray(cache["node_vectors"], dtype=np.float32)
    if query_vectors.shape != (1534, 1024) or node_vectors.shape != (873, 1024):
        raise RuntimeError(f"P1.6 cache shape mismatch: q={query_vectors.shape}, n={node_vectors.shape}")
    query_unit = normalized(query_vectors, "query")
    node_unit = normalized(node_vectors, "node")

    rank_rows = [json.loads(line) for line in rank_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rank_rows) != len(questions):
        raise RuntimeError("P1.6 per-question rank file length mismatch")
    positions_by_db: dict[str, list[int]] = defaultdict(list)
    for index, node in enumerate(nodes):
        if node.node_type == "column":
            positions_by_db[node.db_id].append(index)

    verified = 0
    eligible_count = 0
    question_rows: list[dict[str, Any]] = []
    for q_index, (question, rank_row) in enumerate(zip(questions, rank_rows)):
        key = (question["db_id"], int(question["question_id"]))
        if key != (rank_row.get("db_id"), int(rank_row.get("question_id", -1))):
            raise RuntimeError(f"P1.6 rank/question order mismatch at row {q_index}")
        positions = positions_by_db[question["db_id"]]
        ids = [nodes[index].node_id for index in positions]
        scores = np.asarray(query_unit[q_index] @ node_unit[positions].T, dtype=np.float32)
        order = stable_order(scores, ids)
        ordered_ids = [ids[offset] for offset in order]
        if rank_row.get("column_eligible"):
            eligible_count += 1
            for k in (5, 10, 20):
                if rank_row.get("column_topk_ids", {}).get(str(k)) != ordered_ids[:k]:
                    raise RuntimeError(f"P1.6 exact cosine Top-{k} mismatch at row {q_index}")
            ranks = rank_row.get("column_gold_ranks") or []
            if not ranks or any(int(rank) < 1 or int(rank) > len(ordered_ids) for rank in ranks):
                raise RuntimeError(f"Invalid frozen Gold-column rank list at row {q_index}")
            gold_from_ranks = {ordered_ids[int(rank) - 1] for rank in ranks}
            gold_from_labels = set(question["label"]["gold_column_ids"])
            if gold_from_ranks != gold_from_labels:
                raise RuntimeError(f"Gold IDs reconstructed from frozen ranks mismatch at row {q_index}")
            verified += 1
        elif rank_row.get("column_gold_ranks") not in (None, []):
            raise RuntimeError(f"Unexpected Gold-column ranks for ineligible row {q_index}")
        question_rows.append({
            "index": q_index,
            "question_id": int(question["question_id"]),
            "db_id": question["db_id"],
            "text": question["text"],
            "eligible": bool(rank_row.get("column_eligible")),
            "gold_ids": sorted({ordered_ids[int(rank) - 1] for rank in (rank_row.get("column_gold_ranks") or [])}),
            "static_order": ordered_ids,
            "column_ids": ids,
            "node_texts": {node.node_id: node.text for node in nodes if node.db_id == question["db_id"] and node.node_type == "column"},
        })
    if eligible_count != 1460 or verified != 1460:
        raise RuntimeError(f"Unexpected eligible/rank-verified count: eligible={eligible_count} verified={verified}")

    return {
        "questions": question_rows,
        "nodes": nodes,
        "query_cache_sha256": sha256_file(cache_path),
        "rank_file_sha256": sha256_file(rank_path),
        "node_manifest_sha256": sha256_file(manifest_path),
        "input_hashes": prepared["frozen_hashes"]["sha256"],
        "description_csv_count": prepared["frozen_hashes"]["description_csv_count_verified"],
        "description_encoding_counts": prepared["description_csv_encoding_counts"],
        "schema_text_hashes": prepared["text_hashes"]["schema_nodes"],
        "question_text_hashes": prepared["text_hashes"]["query_prompts"],
        "rank_rows": len(rank_rows),
        "eligible_rows": eligible_count,
        "rank_verifications": verified,
    }


def deterministic_samples(rows: list[dict[str, Any]], seed: int, per_database: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["eligible"]:
            grouped[row["db_id"]].append(row)
    for db_id in grouped:
        grouped[db_id].sort(key=lambda row: (hashlib.sha256(f"{seed}|{db_id}|{row['question_id']}".encode()).hexdigest(), row["question_id"]))
    db_order = sorted(grouped, key=lambda db_id: hashlib.sha256(f"{seed}|database|{db_id}".encode()).hexdigest())
    smoke = [grouped[db_id][0] for db_id in db_order[:5]]
    pilot = [row for db_id in sorted(grouped) for row in grouped[db_id][:per_database]]
    return smoke, pilot


def build_pairs(question: dict[str, Any], ids: list[str]) -> list[str]:
    return [
        PROMPT_PREFIX
        + f"<Instruct>: {INSTRUCTION}\n<Query>: {question['text']}\n<Document>: {question['node_texts'][node_id]}"
        + PROMPT_SUFFIX
        for node_id in ids
    ]


def tokenize_pairs(tokenizer: Any, texts: list[str], max_length: int, chunk_size: int = 64) -> list[list[int]]:
    all_ids: list[list[int]] = []
    for start in range(0, len(texts), chunk_size):
        encoded = tokenizer(
            texts[start : start + chunk_size],
            add_special_tokens=False,
            truncation=True,
            max_length=max_length,
            padding=False,
        )["input_ids"]
        all_ids.extend([[int(token) for token in row] for row in encoded])
    if len(all_ids) != len(texts) or any(not row for row in all_ids):
        raise RuntimeError("Tokenizer returned an empty or incomplete GRAST prompt batch")
    return all_ids


def load_reuse_scores(path: Path | None, config: dict[str, Any], model_sha256: str) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(f"Reuse score file is missing: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_revision = config["high_cost_model"]["revision"]
    reused: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        if row.get("model_revision") != expected_revision or row.get("model_sha256") != model_sha256:
            raise RuntimeError("Cannot reuse scores from another model revision or weight hash")
        key = (row["db_id"], int(row["question_id"]))
        if key in reused:
            raise RuntimeError("Duplicate question in reusable private score file")
        reused[key] = row
    return reused


def score_tokenized(model: Any, tokenizer: Any, token_ids: list[list[int]], yes_id: int, no_id: int, batch_size: int) -> tuple[list[float], int, int, float, int, int]:
    import torch

    if not token_ids:
        return [], 0, 0, 0.0, 0, 0
    device = next(model.parameters()).device
    order = sorted(range(len(token_ids)), key=lambda i: (len(token_ids[i]), i))
    scores = [0.0] * len(token_ids)
    nonpad_tokens = 0
    padded_tokens = 0
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats(device)
    for start in range(0, len(order), batch_size):
        indexes = order[start : start + batch_size]
        batch = tokenizer.pad([{"input_ids": token_ids[i]} for i in indexes], padding=True, return_tensors="pt")
        batch = {key: value.to(device) for key, value in batch.items()}
        attention = batch["attention_mask"]
        nonpad_tokens += int(attention.sum().item())
        padded_tokens += int(attention.numel())
        kwargs = {"input_ids": batch["input_ids"], "attention_mask": attention}
        if "logits_to_keep" in inspect.signature(model.forward).parameters:
            kwargs["logits_to_keep"] = 1
        with torch.inference_mode():
            logits = model(**kwargs).logits[:, -1, :].float()
            pair_logits = torch.stack([logits[:, no_id], logits[:, yes_id]], dim=-1)
            probability_yes = torch.softmax(pair_logits, dim=-1)[:, 1].detach().cpu().tolist()
        for index, score in zip(indexes, probability_yes):
            scores[index] = float(score)
    torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    peak_allocated = int(torch.cuda.max_memory_allocated(device))
    peak_reserved = int(torch.cuda.max_memory_reserved(device))
    if not all(np.isfinite(scores)):
        raise RuntimeError("GRAST reranker returned a non-finite yes probability")
    return scores, nonpad_tokens, padded_tokens, elapsed, peak_allocated, peak_reserved


def check_physical_gpu(config: dict[str, Any]) -> dict[str, Any]:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    expected_gpu = str(config["resource"]["gpu_index"])
    if visible != expected_gpu:
        raise RuntimeError(f"CUDA_VISIBLE_DEVICES must be explicitly set to physical GPU {expected_gpu}; got {visible!r}")
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = []
    for line in query.stdout.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) == 5:
            rows.append({"index": int(fields[0]), "name": fields[1], "total_mib": int(fields[2]), "used_mib": int(fields[3]), "utilization_percent": int(fields[4])})
    selected = next((row for row in rows if row["index"] == int(expected_gpu)), None)
    if selected is None:
        raise RuntimeError(f"Physical GPU {expected_gpu} was not found in nvidia-smi output")
    selected["free_mib"] = selected["total_mib"] - selected["used_mib"]
    if selected["free_mib"] < int(config["resource"]["min_free_vram_mib_before_start"]):
        raise RuntimeError(f"GPU {expected_gpu} has only {selected['free_mib']} MiB free; preregistered minimum is {config['resource']['min_free_vram_mib_before_start']} MiB")
    if selected["utilization_percent"] > int(config["resource"]["max_gpu_utilization_before_start_percent"]):
        raise RuntimeError(f"GPU {expected_gpu} utilization is {selected['utilization_percent']}%; preregistered maximum is {config['resource']['max_gpu_utilization_before_start_percent']}%")
    return selected


def choose_under_token_budget(ids: list[str], costs: dict[str, int], budget: int) -> list[str]:
    selected: list[str] = []
    used = 0
    for node_id in ids:
        cost = int(costs[node_id])
        if cost <= budget - used:
            selected.append(node_id)
            used += cost
    return selected


def pack_output(ids: list[str], scores: dict[str, float], texts: dict[str, str], tokenizer: Any, budget: int) -> tuple[list[str], int]:
    ordered = sorted(ids, key=lambda node_id: (-scores[node_id], node_id))
    selected: list[str] = []
    for node_id in ordered:
        candidate = selected + [node_id]
        serialized = "\n".join(texts[item] for item in candidate)
        if len(tokenizer.encode(serialized, add_special_tokens=False)) <= budget:
            selected = candidate
    exact_tokens = len(tokenizer.encode("\n".join(texts[item] for item in selected), add_special_tokens=False)) if selected else 0
    if exact_tokens > budget:
        raise RuntimeError("Serialized output exceeded the preregistered schema-token budget")
    return selected, exact_tokens


def summarize(records: list[dict[str, Any]], mode: str, config: dict[str, Any], model_input_tokens_this_run: int, model_wall_this_run: float) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        raise RuntimeError("No eligible questions were executed")
    result: dict[str, Any] = {
        "run_id": config["run_id"],
        "mode": mode,
        "status": "completed",
        "question_count": n,
        "database_count": len({row["db_id"] for row in records}),
        "output_schema_budget_tokens": int(config["budgets"]["B_output_schema_tokens_per_question"]),
        "encoder_candidate_budget_tokens": int(config["budgets"]["M_encoder_input_tokens_per_question"]),
        "local_model_input_tokens_scored_this_invocation": model_input_tokens_this_run,
        "local_model_generated_output_tokens": 0,
        "local_model_scoring_wall_seconds_this_invocation": round(model_wall_this_run, 3),
        "static_top_m": {},
        "offline_oracle": {},
    }
    for arm in ("static", "oracle"):
        complete = sum(bool(row[f"{arm}_complete"]) for row in records)
        hits = sum(int(row[f"{arm}_gold_hits"]) for row in records)
        gold = sum(int(row["gold_count"]) for row in records)
        selected = sum(int(row[f"{arm}_selected_count"]) for row in records)
        arm_records = result["static_top_m" if arm == "static" else "offline_oracle"]
        arm_records.update({
            "complete_gold_column_coverage_count": complete,
            "complete_gold_column_coverage_rate": round(complete / n, 6),
            "gold_column_recall_micro": round(hits / gold, 6),
            "gold_column_precision_micro": round(hits / selected, 6) if selected else 0.0,
            "mean_output_schema_tokens": round(sum(int(row[f"{arm}_output_tokens"]) for row in records) / n, 2),
            "mean_encoder_candidate_input_tokens": round(sum(int(row[f"{arm}_candidate_tokens"]) for row in records) / n, 2),
            "mean_all_columns_scored_input_tokens": round(sum(int(row["all_column_scored_tokens"]) for row in records) / n, 2),
            "questions_at_output_budget": sum(int(row[f"{arm}_output_tokens"]) == result["output_schema_budget_tokens"] for row in records),
        })
    result["oracle_minus_static_complete_coverage_pp"] = round(
        (result["offline_oracle"]["complete_gold_column_coverage_rate"] - result["static_top_m"]["complete_gold_column_coverage_rate"]) * 100,
        3,
    )
    if mode == "pilot":
        result["gate"] = "EXPAND_FULL" if n >= 80 and result["database_count"] >= 8 and result["oracle_minus_static_complete_coverage_pp"] >= 3.0 else "STOP_OR_HOLD"
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "configs/text2sql/ramp_sl_encoding_budget_gate_20261123.json")
    parser.add_argument("--mode", choices=("smoke", "pilot", "full"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reuse-private-scores", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite experiment output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True)
    logs_dir = REPO_ROOT / config["output"]["logs_dir"]
    logs_dir.mkdir(parents=True, exist_ok=True)

    model_path = Path(config["high_cost_model"]["local_path"])
    model_file = model_path / "model.safetensors"
    if not model_file.is_file():
        raise FileNotFoundError(f"Pinned GRAST-SQL weights are missing: {model_file}")
    model_hash = sha256_file(model_file)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; local reranker run cannot start")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(f"Expected one CUDA-visible device, found {torch.cuda.device_count()}")
    physical_gpu = check_physical_gpu(config)
    torch.backends.cuda.matmul.allow_tf32 = False
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    yes_tokens = tokenizer("yes", add_special_tokens=False)["input_ids"]
    no_tokens = tokenizer("no", add_special_tokens=False)["input_ids"]
    if len(yes_tokens) != 1 or len(no_tokens) != 1:
        raise RuntimeError(f"yes/no answers must each be one token; got yes={yes_tokens}, no={no_tokens}")
    yes_id, no_id = int(yes_tokens[0]), int(no_tokens[0])

    data = load_frozen_inputs(config)
    smoke_rows, pilot_rows = deterministic_samples(data["questions"], int(config["dataset"]["sampling_seed"]), int(config["dataset"]["pilot_questions_per_database"]))
    if args.mode == "smoke":
        selected_rows = smoke_rows
        if len(selected_rows) != 5 or len({row["db_id"] for row in selected_rows}) != 5:
            raise RuntimeError("Engineering smoke must select five eligible questions from five databases")
    elif args.mode == "pilot":
        selected_rows = pilot_rows
        if len(selected_rows) > 110:
            raise RuntimeError("Pilot sample exceeds the preregistered 110-question maximum")
    else:
        selected_rows = [row for row in data["questions"] if row["eligible"]]
        if len(selected_rows) != 1460:
            raise RuntimeError("Full run must use exactly 1,460 frozen column-eligible questions")

    reuse = load_reuse_scores(args.reuse_private_scores, config, model_hash)
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        local_files_only=True,
        trust_remote_code=False,
    ).to("cuda:0").eval()

    run_start = {
        "run_id": config["run_id"],
        "mode": args.mode,
        "state": "running",
        "started_at_utc": utc_now(),
        "source": {
            "local_branch": subprocess.run(["git", "-C", str(REPO_ROOT), "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip(),
            "local_commit": subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
        },
        "dataset": {
            "question_sha256": data["input_hashes"]["questions"],
            "schema_sha256": data["input_hashes"]["schema"],
            "description_csv_count_verified": data["description_csv_count"],
            "description_csv_encoding_counts": data["description_encoding_counts"],
            "schema_text_hashes": data["schema_text_hashes"],
            "question_prompt_hashes": data["question_text_hashes"],
            "p1_6_embedding_cache_sha256": data["query_cache_sha256"],
            "p1_6_rank_file_sha256": data["rank_file_sha256"],
            "p1_6_node_manifest_sha256": data["node_manifest_sha256"],
            "p1_6_questions": data["rank_rows"],
            "p1_6_column_eligible": data["eligible_rows"],
            "top5_top10_top20_and_gold_id_rank_verifications": data["rank_verifications"],
        },
        "model": {
            "repo_id": config["high_cost_model"]["repo_id"],
            "revision": config["high_cost_model"]["revision"],
            "model_safetensors_sha256": model_hash,
            "dtype": "bfloat16",
            "yes_token_id": yes_id,
            "no_token_id": no_id,
            "max_length": int(config["high_cost_model"]["max_length"]),
            "batch_size": int(config["high_cost_model"]["batch_size"]),
        },
        "experiment": {
            "sample_questions": len(selected_rows),
            "sample_databases": len({row["db_id"] for row in selected_rows}),
            "M_encoder_input_token_budget": int(config["budgets"]["M_encoder_input_tokens_per_question"]),
            "B_serialized_schema_token_budget": int(config["budgets"]["B_output_schema_tokens_per_question"]),
            "registered_full_input_token_cap": int(config["budgets"]["full_run_input_token_cap"]),
            "reuse_score_questions": len(reuse),
            "external_model_api_calls": 0,
            "sql_execution": False,
            "training": False,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "numpy": np.__version__,
            "cuda": torch.version.cuda,
            "visible_cuda_devices": torch.cuda.device_count(),
            "logical_device_name": torch.cuda.get_device_name(0),
        },
        "resource_snapshot": {
            "selected_physical_gpu": physical_gpu,
            "nvidia_smi": subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip(),
            "free_h": subprocess.run(["free", "-h"], capture_output=True, text=True).stdout.strip(),
            "nproc": subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip(),
        },
    }
    write_json(output_dir / "run_start.json", run_start)

    all_detail: list[dict[str, Any]] = []
    reuse_by_key = reuse
    model_tokens_this_run = 0
    total_experiment_model_tokens = 0
    model_wall_this_run = 0.0
    padded_tokens_this_run = 0
    max_allocated = 0
    max_reserved = 0
    score_path = output_dir / "private_model_scores.jsonl"
    detail_path = output_dir / "private_per_question.jsonl"
    max_tokens_total = int(config["budgets"]["full_run_input_token_cap"])
    max_wall_seconds = int(config["budgets"]["full_run_gpu_wall_seconds_cap"])
    elapsed_started = time.perf_counter()
    state = "completed"
    try:
        with score_path.open("w", encoding="utf-8") as score_out, detail_path.open("w", encoding="utf-8") as detail_out:
            for index, question in enumerate(selected_rows, start=1):
                key = (question["db_id"], question["question_id"])
                ids = question["column_ids"]
                pairs = build_pairs(question, ids)
                pair_text_sha256 = sha256_bytes("\n".join(pairs).encode("utf-8"))
                token_ids = tokenize_pairs(tokenizer, pairs, int(config["high_cost_model"]["max_length"]))
                costs = {node_id: len(tokens) for node_id, tokens in zip(ids, token_ids)}
                static_candidates = choose_under_token_budget(question["static_order"], costs, int(config["budgets"]["M_encoder_input_tokens_per_question"]))
                static_input_tokens = sum(costs[node_id] for node_id in static_candidates)
                cached = reuse_by_key.get(key)
                if cached is not None:
                    if cached.get("pair_text_sha256") != pair_text_sha256 or set(cached.get("scores_by_id", {})) != set(ids) or set(cached.get("static_scores_by_id", {})) != set(static_candidates) or cached.get("input_tokens_by_id") != costs:
                        raise RuntimeError(f"Reusable score/token map mismatch for question index {index}")
                    if cached.get("static_candidate_ids") != static_candidates:
                        raise RuntimeError(f"Reusable Static-TopM candidate list mismatch for question index {index}")
                    scores = {node_id: float(value) for node_id, value in cached["scores_by_id"].items()}
                    static_scores = {node_id: float(value) for node_id, value in cached["static_scores_by_id"].items()}
                    all_tokens = int(cached["all_column_input_tokens"])
                    all_padded = int(cached["all_column_padded_tokens"])
                    static_wall = float(cached["static_model_scoring_wall_seconds"])
                    oracle_wall = float(cached["oracle_model_scoring_wall_seconds"])
                    score_wall = static_wall + oracle_wall
                    alloc = int(cached.get("peak_memory_allocated_bytes", 0))
                    reserved = int(cached.get("peak_memory_reserved_bytes", 0))
                    score_record = cached
                    if all_tokens != sum(costs.values()):
                        raise RuntimeError(f"Reusable all-column token count mismatch for question index {index}")
                    total_experiment_model_tokens += static_input_tokens + all_tokens
                else:
                    required_tokens = static_input_tokens + sum(costs.values())
                    if total_experiment_model_tokens + required_tokens > max_tokens_total:
                        state = "stopped_input_token_cap"
                        break
                    if time.perf_counter() - elapsed_started >= max_wall_seconds:
                        state = "stopped_gpu_wall_cap"
                        break
                    static_indexes = [ids.index(node_id) for node_id in static_candidates]
                    static_pair_scores, static_tokens, static_padded, static_wall, static_alloc, static_reserved = score_tokenized(
                        model, tokenizer, [token_ids[i] for i in static_indexes], yes_id, no_id, int(config["high_cost_model"]["batch_size"])
                    )
                    all_pair_scores, all_tokens, all_padded, oracle_wall, oracle_alloc, oracle_reserved = score_tokenized(
                        model, tokenizer, token_ids, yes_id, no_id, int(config["high_cost_model"]["batch_size"])
                    )
                    if static_tokens != static_input_tokens or all_tokens != sum(costs.values()):
                        raise RuntimeError(f"Model input token accounting mismatch for question index {index}")
                    scores = dict(zip(ids, all_pair_scores))
                    static_scores = dict(zip(static_candidates, static_pair_scores))
                    alloc = max(static_alloc, oracle_alloc)
                    reserved = max(static_reserved, oracle_reserved)
                    score_wall = static_wall + oracle_wall
                    all_padded += static_padded
                    model_tokens_this_run += static_tokens + all_tokens
                    padded_tokens_this_run += all_padded
                    model_wall_this_run += score_wall
                    total_experiment_model_tokens += static_tokens + all_tokens
                    score_record = {
                        "question_id": question["question_id"],
                        "db_id": question["db_id"],
                        "model_revision": config["high_cost_model"]["revision"],
                        "model_sha256": model_hash,
                        "pair_text_sha256": pair_text_sha256,
                        "scores_by_id": scores,
                        "static_candidate_ids": static_candidates,
                        "static_scores_by_id": static_scores,
                        "input_tokens_by_id": costs,
                        "all_column_input_tokens": all_tokens,
                        "all_column_padded_tokens": all_padded,
                        "static_model_scoring_wall_seconds": round(static_wall, 6),
                        "oracle_model_scoring_wall_seconds": round(oracle_wall, 6),
                        "peak_memory_allocated_bytes": alloc,
                        "peak_memory_reserved_bytes": reserved,
                    }
                score_out.write(json.dumps(score_record, ensure_ascii=False, allow_nan=False) + "\n")
                score_out.flush()
                max_allocated = max(max_allocated, alloc)
                max_reserved = max(max_reserved, reserved)

                oracle_ranked = sorted(ids, key=lambda node_id: (-scores[node_id], node_id))
                oracle_candidates = choose_under_token_budget(oracle_ranked, costs, int(config["budgets"]["M_encoder_input_tokens_per_question"]))
                static_selected, static_output_tokens = pack_output(static_candidates, static_scores, question["node_texts"], tokenizer, int(config["budgets"]["B_output_schema_tokens_per_question"]))
                oracle_selected, oracle_output_tokens = pack_output(oracle_candidates, scores, question["node_texts"], tokenizer, int(config["budgets"]["B_output_schema_tokens_per_question"]))
                gold = set(question["gold_ids"])
                detail = {
                    "question_id": question["question_id"],
                    "db_id": question["db_id"],
                    "gold_ids": sorted(gold),
                    "gold_count": len(gold),
                    "all_column_scored_tokens": all_tokens,
                    "model_scoring_wall_seconds": round(score_wall, 6),
                    "static_candidate_ids": static_candidates,
                    "static_candidate_tokens": static_input_tokens,
                    "static_selected_ids": static_selected,
                    "static_selected_count": len(static_selected),
                    "static_gold_hits": len(gold.intersection(static_selected)),
                    "static_complete": gold.issubset(static_selected),
                    "static_output_tokens": static_output_tokens,
                    "oracle_candidate_ids": oracle_candidates,
                    "oracle_candidate_tokens": sum(costs[node_id] for node_id in oracle_candidates),
                    "oracle_selected_ids": oracle_selected,
                    "oracle_selected_count": len(oracle_selected),
                    "oracle_gold_hits": len(gold.intersection(oracle_selected)),
                    "oracle_complete": gold.issubset(oracle_selected),
                    "oracle_output_tokens": oracle_output_tokens,
                }
                detail_out.write(json.dumps(detail, ensure_ascii=False, allow_nan=False) + "\n")
                detail_out.flush()
                all_detail.append(detail)
                print(f"completed={len(all_detail)}/{len(selected_rows)}; local_input_tokens={model_tokens_this_run}; gpu_seconds={model_wall_this_run:.1f}", flush=True)
    except Exception:
        run_start["state"] = "failed"
        run_start["finished_at_utc"] = utc_now()
        write_json(output_dir / "run_start.json", run_start)
        raise

    if len(all_detail) != len(selected_rows):
        state = state if state != "completed" else "incomplete"
    result = summarize(all_detail, args.mode, config, model_tokens_this_run, model_wall_this_run) if all_detail else {
        "run_id": config["run_id"], "mode": args.mode, "status": state, "question_count": 0,
        "local_model_input_tokens_scored_this_invocation": model_tokens_this_run,
        "local_model_generated_output_tokens": 0,
    }
    result["status"] = state
    result["padded_token_positions_scored_this_invocation"] = padded_tokens_this_run
    result["total_encoder_input_tokens_for_executed_questions_including_reuse"] = total_experiment_model_tokens
    result["peak_gpu_memory_allocated_bytes"] = max_allocated
    result["peak_gpu_memory_reserved_bytes"] = max_reserved
    result["model_revision"] = config["high_cost_model"]["revision"]
    result["model_safetensors_sha256"] = model_hash
    result["p1_6_rank_verifications"] = data["rank_verifications"]
    result["sample_questions_requested"] = len(selected_rows)
    if args.mode == "smoke":
        result.pop("static_top_m", None)
        result.pop("offline_oracle", None)
        result.pop("oracle_minus_static_complete_coverage_pp", None)
        result["engineering_smoke_only"] = True
    write_json(output_dir / "aggregate_private.json", result)
    public = {
        "run_id": result["run_id"],
        "mode": result["mode"],
        "status": result["status"],
        "question_count": result.get("question_count", 0),
        "database_count": result.get("database_count", 0),
        "M_encoder_input_token_budget": result.get("encoder_candidate_budget_tokens"),
        "B_output_schema_token_budget": result.get("output_schema_budget_tokens"),
        "model_revision": result["model_revision"],
        "p1_6_rank_verifications": result["p1_6_rank_verifications"],
        "local_model_input_tokens_scored_this_invocation": result["local_model_input_tokens_scored_this_invocation"],
        "local_model_generated_output_tokens": 0,
    }
    if args.mode == "pilot" and state == "completed":
        public.update({
            "static_complete_coverage": result["static_top_m"]["complete_gold_column_coverage_rate"],
            "offline_oracle_complete_coverage": result["offline_oracle"]["complete_gold_column_coverage_rate"],
            "oracle_minus_static_complete_coverage_pp": result["oracle_minus_static_complete_coverage_pp"],
            "gate": result["gate"],
        })
    write_json(output_dir / "aggregate_public.json", public)
    run_start["state"] = state
    run_start["finished_at_utc"] = utc_now()
    run_start["completed_questions"] = len(all_detail)
    run_start["local_model_input_tokens_scored_this_invocation"] = model_tokens_this_run
    run_start["local_model_generated_output_tokens"] = 0
    run_start["gpu_scoring_wall_seconds_this_invocation"] = round(model_wall_this_run, 3)
    run_start["elapsed_wall_seconds"] = round(time.perf_counter() - elapsed_started, 3)
    write_json(output_dir / "run_start.json", run_start)
    print(json.dumps(public, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
