 scripts/text2sql/run_g3_fk_seed_direction_sensitivity.py | 8 ++++++--
 1 file changed, 6 insertions(+), 2 deletions(-)
#!/usr/bin/env python3
"""Run the preregistered label-free G3 seed-direction sensitivity diagnostic."""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_p0_fk_mapping_model_proxy_rank_pilot as baseline  # noqa: E402
from run_p0_fk_mapping_model_review_proxy import parse_packet, validate_packet_pair  # noqa: E402

EXPERIMENT_ID = "g3_fk_seed_direction_sensitivity_20261106"
SEED = 20261106
EXPECTED_CONFIG_SHA256 = "b5c4b4bc4ded01b2f442354bcac6b64f16669a46b180cf4a01be93158aea3652"
EXPECTED_PACKET_A = "0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2"
EXPECTED_PACKET_B = "a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb"
EXPECTED_MANIFEST = "14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7"
EXPECTED_SPLIT = "40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0"
EXPECTED_GFM_MODEL = baseline.EXPECTED_GFM_MODEL_SHA256
EXPECTED_GFM_CONFIG = baseline.EXPECTED_GFM_CONFIG_SHA256
MAX_GPU_BYTES = 8 * 1024**3
MAX_RSS_BYTES = 8 * 1024**3
MAX_CPU_SECONDS = 900
MAX_WALL_SECONDS = 1200
CONDITIONS = ("A0_both", "A0_repeat", "A1_first", "A2_second")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    return baseline.sha256_file(path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_private_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Load only packets, mapping identities and the frozen split; never reviewer outputs."""
    packet_a, hash_a = parse_packet(args.packet_a)
    packet_b, hash_b = parse_packet(args.packet_b)
    require(hash_a == EXPECTED_PACKET_A and hash_b == EXPECTED_PACKET_B, "blind packet hash mismatch")
    require(sha256_file(args.private_manifest) == EXPECTED_MANIFEST, "private mapping manifest hash mismatch")
    require(sha256_file(args.split_manifest) == EXPECTED_SPLIT, "frozen split manifest hash mismatch")
    pair_index = validate_packet_pair(packet_a, packet_b)
    require(len(pair_index) == 60, "frozen packet must contain 60 question-pairs")
    require(sum(len(item["mappings"]) for item in packet_a) == 135, "candidate count changed")
    items = {item["pair_id"]: item for item in packet_a}
    require(len(items) == 60, "duplicate pair ID in packets")

    manifest = json.loads(args.private_manifest.read_text(encoding="utf-8"))
    manifest_rows = {row["pair_id"]: row for row in manifest["selected_cases_private"]}
    require(set(manifest_rows) == set(items), "packet/manifest coverage mismatch")
    require(manifest.get("trusted_role_label_count") == 0, "trusted labels unexpectedly exist")
    require(manifest.get("human_review_completed") is False, "human-review state changed")
    normalization_count = 0
    for pair_id, item in items.items():
        row = manifest_rows[pair_id]
        candidate_ids = {mapping["mapping_id"] for mapping in item["mappings"]}
        require(len(candidate_ids) >= 2, "candidate set has fewer than two mappings")
        manifest_ids = {entry["mapping_id"] for entry in row["mapping_identities"]}
        require(candidate_ids == manifest_ids, "mapping identity coverage mismatch")
        if item["question"] != row["private_question_text"]:
            require(item["question"].replace("<br>", "\n") == row["private_question_text"], "unexpected packet serialization mismatch")
            normalization_count += 1
    require(normalization_count == 1, "frozen packet serialization anomaly changed")

    split = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    smoke_pairs, full_pairs, smoke_questions = baseline.make_frozen_split(items, manifest_rows)
    require(split.get("fixed_seed") == SEED, "split seed mismatch")
    require(set(split.get("smoke_pair_ids", [])) == smoke_pairs, "smoke split differs from frozen split")
    require(set(split.get("full_pair_ids", [])) == full_pairs, "full split differs from frozen split")
    require(len(smoke_questions) == 5 and len(smoke_pairs) == 5 and len(full_pairs) == 55, "split size changed")
    full_candidates = sum(len(items[pair_id]["mappings"]) for pair_id in full_pairs)
    require(full_candidates == 123, "Full candidate count changed")
    return {
        "items": items,
        "manifest_rows": manifest_rows,
        "smoke_pairs": smoke_pairs,
        "full_pairs": full_pairs,
        "normalization_count": normalization_count,
    }


def score_conditions(
    pair_id: str,
    graph: Any,
    mapping_node_index: dict[str, int],
    graph_meta: dict[str, Any],
    query: Any,
    model: Any,
    device: Any,
    torch: Any,
) -> tuple[dict[str, dict[str, float]], list[float]]:
    require(graph_meta["table_count"] == 2, "each graph must have two table endpoints")
    require(graph_meta["edge_count"] == graph_meta["mapping_count"] * 4, "FK reification edge count mismatch")
    base_mask = graph_meta["start_mask"].clone()
    require(int(base_mask.sum().item()) == 2, "A0 must seed both endpoints")
    first_mask = torch.zeros_like(base_mask)
    second_mask = torch.zeros_like(base_mask)
    first_mask[0, 0] = 1.0
    second_mask[0, 1] = 1.0
    masks = {
        "A0_both": base_mask,
        "A0_repeat": base_mask.clone(),
        "A1_first": first_mask,
        "A2_second": second_mask,
    }
    result: dict[str, dict[str, float]] = {}
    forward_seconds: list[float] = []
    for condition in CONDITIONS:
        node_scores, elapsed = baseline.run_g_reasoner(model, graph, query, masks[condition], device, torch)
        forward_seconds.append(elapsed)
        result[condition] = {
            mapping_id: float(node_scores[node_index])
            for mapping_id, node_index in mapping_node_index.items()
        }
        require(all(math.isfinite(value) for value in result[condition].values()), "non-finite mapping score")
    return result, forward_seconds


def score_summary(rows: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for condition in CONDITIONS:
        ranges = []
        top_tie_graphs = 0
        top_tie_count_total = 0
        candidate_count = 0
        for condition_rows in rows.values():
            scores = condition_rows[condition]
            values = list(scores.values())
            candidate_count += len(values)
            top = max(values)
            ties = sum(value == top for value in values)
            top_tie_count_total += ties
            top_tie_graphs += int(ties > 1)
            ranges.append(max(values) - min(values))
        summaries[condition] = {
            "candidate_count": candidate_count,
            "graphs_with_top_score_tie": top_tie_graphs,
            "mean_top_score_tie_count": round(top_tie_count_total / len(rows), 6) if rows else None,
            "mean_within_graph_score_range": round(sum(ranges) / len(ranges), 9) if ranges else None,
            "min_within_graph_score_range": round(min(ranges), 9) if ranges else None,
            "max_within_graph_score_range": round(max(ranges), 9) if ranges else None,
        }
    return summaries


def comparison_summary(rows: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    pair_count = len(rows)
    summaries: dict[str, Any] = {}
    for condition in ("A1_first", "A2_second"):
        top1_flips = 0
        eligible_candidate_pairs = 0
        reversed_candidate_pairs = 0
        tied_candidate_pairs_excluded = 0
        for per_pair in rows.values():
            baseline_scores = per_pair["A0_both"]
            condition_scores = per_pair[condition]
            candidate_ids = sorted(baseline_scores)
            baseline_top = sorted(candidate_ids, key=lambda key: (-baseline_scores[key], key))[0]
            condition_top = sorted(candidate_ids, key=lambda key: (-condition_scores[key], key))[0]
            top1_flips += int(baseline_top != condition_top)
            for first, second in combinations(candidate_ids, 2):
                baseline_delta = baseline_scores[first] - baseline_scores[second]
                condition_delta = condition_scores[first] - condition_scores[second]
                if baseline_delta == 0.0 or condition_delta == 0.0:
                    tied_candidate_pairs_excluded += 1
                    continue
                eligible_candidate_pairs += 1
                reversed_candidate_pairs += int((baseline_delta > 0) != (condition_delta > 0))
        summaries[condition] = {
            "top1_flips": top1_flips,
            "top1_flip_rate": round(top1_flips / pair_count, 6) if pair_count else None,
            "top1_denominator_multi_candidate_pairs": pair_count,
            "candidate_pair_order_reversals": reversed_candidate_pairs,
            "candidate_pair_order_reversal_rate": round(reversed_candidate_pairs / eligible_candidate_pairs, 6) if eligible_candidate_pairs else None,
            "candidate_pairs_with_strict_order_in_both_conditions": eligible_candidate_pairs,
            "candidate_pairs_excluded_for_exact_ties": tied_candidate_pairs_excluded,
            "candidate_pair_rate_denominator_note": "candidate pairs tied under A0 or this condition are excluded",
        }
    a1 = summaries["A1_first"]
    a2 = summaries["A2_second"]
    if any(
        value["top1_flip_rate"] is not None
        and value["candidate_pair_order_reversal_rate"] is not None
        and value["top1_flip_rate"] >= 0.20
        and value["candidate_pair_order_reversal_rate"] >= 0.10
        for value in (a1, a2)
    ):
        decision = "MECHANISM_SENSITIVITY_SIGNAL"
    elif all(
        value["top1_flip_rate"] is not None
        and value["candidate_pair_order_reversal_rate"] is not None
        and value["top1_flip_rate"] <= 0.05
        and value["candidate_pair_order_reversal_rate"] <= 0.05
        for value in (a1, a2)
    ):
        decision = "NO_MATERIAL_ORDER_EFFECT"
    else:
        decision = "INCONCLUSIVE"
    return {"comparisons": summaries, "preregistered_mechanism_decision": decision}


def run(args: argparse.Namespace) -> dict[str, Any]:
    expected_run_prefix = f"{EXPERIMENT_ID}_{args.mode}_"
    attempt_suffix = args.run_id.removeprefix(expected_run_prefix)
    require(
        args.run_id.startswith(expected_run_prefix) and attempt_suffix in {"001", "002", "003"},
        "run ID must use the preregistered experiment/mode and a unique attempt suffix",
    )
    require(args.device == "cuda:0", "only the preregistered single visible CUDA device is allowed")
    visible_gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    require(visible_gpu == "1", "pin the preregistered physical GPU 1")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "offline local model loading is required")
    shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
    require(shared_root is not None and Path(shared_root).is_dir(), "local token ledger module is unavailable")
    source_commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    require(source_commit == args.expected_commit, "source commit differs from frozen run commit")
    require(sha256_file(args.config) == EXPECTED_CONFIG_SHA256, "config differs from preregistered file")
    private = load_private_inputs(args)
    selected_pairs = private["smoke_pairs"] if args.mode == "smoke" else private["full_pairs"]
    require(not args.output_dir.exists(), "output directory already exists; refusing to overwrite")
    args.output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.output_dir.chmod(0o700)
    prediction_path = args.output_dir / "private_scores.jsonl"
    command = [sys.executable, *sys.argv]
    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "attempted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": source_commit,
        "config_sha256": sha256_file(args.config),
        "input_sha256": {
            "packet_a": sha256_file(args.packet_a),
            "packet_b": sha256_file(args.packet_b),
            "private_mapping_manifest": sha256_file(args.private_manifest),
            "split_manifest": sha256_file(args.split_manifest),
        },
        "command_argv": command,
        "execution_environment": {
            "CUDA_VISIBLE_DEVICES": visible_gpu,
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "reviewer_outputs_opened": False,
        "gold_sql_or_execution_results_opened": False,
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt)
    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        import torch
        import torch_geometric
        import transformers
        import sentence_transformers
        from sentence_transformers import SentenceTransformer
        from torch_geometric.data import Data
        from gfmrag.utils.util import load_model_from_pretrained

        versions = {
            "python": platform.python_version(),
            "torch": str(torch.__version__).split("+", 1)[0],
            "torch_geometric": str(torch_geometric.__version__),
            "transformers": str(transformers.__version__),
            "sentence_transformers": str(sentence_transformers.__version__),
        }
        expected_versions = {
            "python": "3.12.15",
            "torch": "2.8.0",
            "torch_geometric": "2.6.1",
            "transformers": "4.56.1",
            "sentence_transformers": "5.1.1",
        }
        require(versions == expected_versions, f"environment version mismatch: {versions}")
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "exactly one visible GPU is required")
        device = torch.device(args.device)
        torch.cuda.set_device(device)
        torch.cuda.reset_peak_memory_stats(device)
        torch.manual_seed(SEED)
        torch.set_num_threads(min(16, os.cpu_count() or 1))
        torch.set_num_interop_threads(min(8, os.cpu_count() or 1))

        checkpoint = args.checkpoint.resolve(strict=True)
        embedding_path = args.embedding_model.resolve(strict=True)
        require(sha256_file(checkpoint / "model.pth") == EXPECTED_GFM_MODEL, "G-reasoner weights hash mismatch")
        require(sha256_file(checkpoint / "config.json") == EXPECTED_GFM_CONFIG, "G-reasoner config hash mismatch")
        qwen_hashes = baseline.validate_qwen_snapshot(embedding_path)

        query_by_pair, table_texts, mapping_texts = baseline.query_and_passage_texts(selected_pairs, private)
        passage_texts = list(table_texts.values()) + list(baseline.RELATION_TEXTS)
        for pair_id in selected_pairs:
            passage_texts.extend(mapping_texts[pair_id].values())
        qwen_load_started = time.perf_counter()
        embedder = SentenceTransformer(
            str(embedding_path),
            device=str(device),
            trust_remote_code=True,
            local_files_only=True,
        )
        embedder.eval()
        torch.cuda.synchronize(device)
        qwen_load_seconds = time.perf_counter() - qwen_load_started
        query_embeddings, query_usage = baseline.encode_texts(
            embedder,
            list(query_by_pair.values()),
            is_query=True,
            run_id=args.run_id,
            call_prefix="query",
            torch=torch,
        )
        query_vector_by_pair = {pair_id: query_embeddings[query_by_pair[pair_id]] for pair_id in query_by_pair}
        passage_embeddings, passage_usage = baseline.encode_texts(
            embedder,
            passage_texts,
            is_query=False,
            run_id=args.run_id,
            call_prefix="passage",
            torch=torch,
        )
        del embedder
        torch.cuda.empty_cache()
        torch.cuda.synchronize(device)
        qwen_encode_seconds = time.perf_counter() - qwen_load_started - qwen_load_seconds
        relation_vectors = {text: passage_embeddings[text] for text in baseline.RELATION_TEXTS}

        model_load_started = time.perf_counter()
        model, config = load_model_from_pretrained(str(checkpoint))
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        require(parameter_count == baseline.EXPECTED_GFM_PARAMETERS, "G-reasoner parameter count mismatch")
        model_config = config["model_config"]
        require(int(model_config["entity_model"]["input_dim"]) == baseline.DIM, "input dimension mismatch")
        require(int(model_config["feat_dim"]) == baseline.DIM, "feature dimension mismatch")
        model.eval().to(device)
        torch.cuda.synchronize(device)
        model_load_seconds = time.perf_counter() - model_load_started

        rows: dict[str, dict[str, dict[str, float]]] = {}
        graph_size_counts: Counter[str] = Counter()
        forward_seconds: list[float] = []
        with prediction_path.open("x", encoding="utf-8") as stream:
            prediction_path.chmod(0o600)
            for pair_id in sorted(selected_pairs):
                graph, node_index, graph_meta = baseline.build_graph(
                    pair_id,
                    private,
                    table_texts,
                    mapping_texts,
                    passage_embeddings,
                    relation_vectors,
                    Data,
                    torch,
                )
                scores, elapsed_values = score_conditions(
                    pair_id,
                    graph,
                    node_index,
                    graph_meta,
                    query_vector_by_pair[pair_id],
                    model,
                    device,
                    torch,
                )
                forward_seconds.extend(elapsed_values)
                rows[pair_id] = scores
                graph_size_counts[str(graph_meta["mapping_count"])] += 1
                private_row = {"pair_id": pair_id, "conditions": scores, "candidate_count": graph_meta["mapping_count"]}
                stream.write(json.dumps(private_row, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                if time.perf_counter() - started > MAX_WALL_SECONDS:
                    raise TimeoutError("wall-time budget exceeded")

        repeat_errors = [
            abs(rows[pair_id]["A0_both"][mapping_id] - rows[pair_id]["A0_repeat"][mapping_id])
            for pair_id in rows
            for mapping_id in rows[pair_id]["A0_both"]
        ]
        peak_gpu_bytes = int(torch.cuda.max_memory_allocated(device))
        peak_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        wall_seconds = time.perf_counter() - started
        cpu_seconds = time.process_time() - cpu_started
        require(peak_gpu_bytes <= MAX_GPU_BYTES, "GPU allocation exceeded preregistered limit")
        require(peak_rss_bytes <= MAX_RSS_BYTES, "RSS exceeded preregistered limit")
        require(cpu_seconds <= MAX_CPU_SECONDS, "CPU-time budget exceeded")
        require(wall_seconds <= MAX_WALL_SECONDS, "wall-time budget exceeded")

        result: dict[str, Any] = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "SMOKE_PASS" if args.mode == "smoke" else "FULL_COMPLETE",
            "source_commit": source_commit,
            "config_sha256": sha256_file(args.config),
            "input_sha256": attempt["input_sha256"],
            "checkpoint_sha256": {"model.pth": EXPECTED_GFM_MODEL, "config.json": EXPECTED_GFM_CONFIG},
            "qwen_snapshot_sha256": qwen_hashes,
            "environment": versions,
            "device": torch.cuda.get_device_name(device),
            "physical_gpu": 1,
            "pairs_scored": len(rows),
            "candidate_count_scored": sum(len(private["items"][pair_id]["mappings"]) for pair_id in selected_pairs),
            "forward_count": len(forward_seconds),
            "forward_seconds_total": round(sum(forward_seconds), 6),
            "qwen_embedding_usage": {
                "query": query_usage,
                "passage": passage_usage,
                "input_tokens_total": query_usage["input_tokens"] + passage_usage["input_tokens"],
                "output_tokens_total": 0,
            },
            "graph_candidate_count_histogram": dict(sorted(graph_size_counts.items(), key=lambda item: int(item[0]))),
            "mean_a0_repeat_max_absolute_error": round(max(repeat_errors, default=0.0), 12),
            "qwen_load_seconds": round(qwen_load_seconds, 6),
            "qwen_encode_seconds": round(qwen_encode_seconds, 6),
            "g_reasoner_load_seconds": round(model_load_seconds, 6),
            "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6),
            "peak_gpu_allocated_bytes": peak_gpu_bytes,
            "peak_rss_bytes": peak_rss_bytes,
            "reviewer_outputs_opened": False,
            "gold_sql_or_execution_results_opened": False,
            "privacy": {
                "contains_question_text": False,
                "contains_case_or_mapping_ids": False,
                "contains_per_case_scores": False,
                "contains_raw_model_outputs": False,
            },
        }
        if args.mode == "smoke":
            result["primary_metrics_included"] = False
            result["full_question_overlap"] = 0
        else:
            result["condition_score_summary"] = score_summary(rows)
            result.update(comparison_summary(rows))
            result["interpretation_boundary"] = "Ranking sensitivity only; no correctness, accuracy, or improvement claim."
        write_json(args.output_dir / "aggregate_summary.json", result)
        run_manifest = {
            **attempt,
            "status": result["status"],
            "environment": versions,
            "device": torch.cuda.get_device_name(device),
            "forward_count": len(forward_seconds),
            "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6),
            "peak_gpu_allocated_bytes": peak_gpu_bytes,
            "peak_rss_bytes": peak_rss_bytes,
            "private_scores_sha256": sha256_file(prediction_path),
        }
        write_json(args.output_dir / "run_manifest.json", run_manifest)
        return result
    except Exception as exc:
        write_json(args.output_dir / "failure.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "FAILED",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "source_commit": source_commit,
            "input_sha256": attempt["input_sha256"],
            "partial_private_rows": sum(1 for _ in prediction_path.open("r", encoding="utf-8")) if prediction_path.exists() else 0,
        })
        raise


def main() -> None:
    args = parse_args()
    print(json.dumps(run(args), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
