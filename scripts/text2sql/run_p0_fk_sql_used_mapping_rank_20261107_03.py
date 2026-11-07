#!/usr/bin/env python3
"""Score fresh SQL-used FK mapping units with frozen G-reasoner and Dense."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_p0_fk_mapping_model_proxy_rank_pilot as base  # noqa: E402
from g0_fk_instance_node_probe import (  # noqa: E402
    EXPECTED_GFM_CONFIG_SHA256,
    EXPECTED_GFM_MODEL_SHA256,
    sha256_file,
    validate_qwen_snapshot,
)

EXPERIMENT_ID = "p0_fk_sql_used_mapping_rank_20261107_03"
EXPECTED_BRANCH = "research/p0-sql-used-proxy-alignment-20261107"
EXPECTED_CONFIG = "configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json"
GPU_AMENDMENT_CONFIG = "configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.json"
CPU_AMENDMENT_CONFIG = "configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu.json"
CPU_RECOVERY_AMENDMENT_CONFIG = "configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.json"
MAX_GPU_BYTES = 8 * 1024**3
MAX_RSS_BYTES = 8 * 1024**3
MAX_WALL_SECONDS = 1800
MAX_CPU_SECONDS = 900


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def adapt_private(manifest: dict[str, Any], selected_ids: set[str]) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    manifest_rows: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    for unit_id in sorted(selected_ids):
        unit = manifest["units"][unit_id]
        candidates = unit["candidate_mappings"]
        candidate_ids = {str(row["mapping_id"]) for row in candidates}
        target_ids = sorted(set(str(value) for value in unit["sql_used_mapping_ids"]))
        require(len(candidate_ids) == len(candidates) and len(candidate_ids) >= 2, "CANDIDATE_IDENTITY_INVALID")
        require(bool(target_ids) and set(target_ids) <= candidate_ids, "SQL_TARGET_OUTSIDE_CANDIDATES")
        items[unit_id] = {"mappings": [{"mapping_id": str(row["mapping_id"])} for row in candidates]}
        manifest_rows[unit_id] = {
            "private_table_pair": unit["table_pair"],
            "private_question_text": unit["question"],
            "question_key_sha256": unit["question_key_sha256"],
            "private_db_id": unit["db_id"],
            "mapping_identities": [
                {"mapping_id": str(row["mapping_id"]), "identity": row["identity"]}
                for row in candidates
            ],
        }
        labels[unit_id] = {"decision": "sql_used_mapping", "accepted_mapping_ids": target_ids}
    return {"items": items, "manifest_rows": manifest_rows, "labels": labels}


def resource_summary(torch: Any, device: Any, wall_seconds: float, cpu_seconds: float) -> dict[str, Any]:
    if device.type == "cuda":
        peak_gpu = int(torch.cuda.max_memory_allocated(device))
        peak_gpu_reserved = int(torch.cuda.max_memory_reserved(device))
    else:
        peak_gpu = 0
        peak_gpu_reserved = 0
    peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    require(peak_gpu <= MAX_GPU_BYTES, "GPU_ALLOCATION_LIMIT_EXCEEDED")
    require(peak_rss <= MAX_RSS_BYTES, "RSS_LIMIT_EXCEEDED")
    require(wall_seconds <= MAX_WALL_SECONDS, "WALL_LIMIT_EXCEEDED")
    require(cpu_seconds <= MAX_CPU_SECONDS, "CPU_LIMIT_EXCEEDED")
    return {
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "peak_gpu_allocated_bytes": peak_gpu,
        "peak_gpu_reserved_bytes": peak_gpu_reserved,
        "peak_rss_bytes": peak_rss,
    }


def anonymous_db_ids(db_counts: dict[str, int]) -> dict[str, int]:
    ordered = sorted(
        db_counts,
        key=lambda db_id: hashlib.sha256(f"{EXPERIMENT_ID}:{db_id}".encode("utf-8")).hexdigest(),
    )
    return {f"db_{index:02d}": db_counts[db_id] for index, db_id in enumerate(ordered, 1)}


def full_metrics(rows: dict[str, dict[str, Any]], private: dict[str, Any], selected_ids: set[str]) -> dict[str, Any]:
    labels = private["labels"]
    metrics = base.metric_summary(rows, labels, sorted(selected_ids))
    paired = base.paired_comparison(rows, labels, sorted(selected_ids))
    db_groups: dict[str, list[str]] = defaultdict(list)
    for unit_id in selected_ids:
        db_groups[private["manifest_rows"][unit_id]["private_db_id"]].append(unit_id)
    per_db: dict[str, Any] = {}
    positive_gate_dbs = 0
    for alias_index, db_id in enumerate(
        sorted(db_groups, key=lambda value: hashlib.sha256(f"{EXPERIMENT_ID}:{value}".encode("utf-8")).hexdigest()),
        start=1,
    ):
        db_ids = db_groups[db_id]
        db_paired = base.paired_comparison(rows, labels, db_ids)
        db_metrics = base.metric_summary(rows, labels, db_ids)
        per_db[f"db_{alias_index:02d}"] = {
            "units": len(db_ids),
            "g_reasoner_mapping_at_1": db_metrics["g_reasoner"]["accepted_at_1"],
            "dense_mapping_at_1": db_metrics["dense_cosine"]["accepted_at_1"],
            "paired": db_paired,
        }
        if len(db_ids) >= 5 and db_paired["net_rescue"] > 0:
            positive_gate_dbs += 1
    delta = metrics["g_reasoner"]["accepted_at_1"]["rate"] - metrics["dense_cosine"]["accepted_at_1"]["rate"]
    pass_screen = delta >= 0.05 and paired["net_rescue"] >= 4 and positive_gate_dbs >= 2
    return {
        "full_unit_count": len(selected_ids),
        "anonymous_database_count": len(db_groups),
        "by_anonymous_database": per_db,
        "methods": metrics,
        "paired_g_reasoner_vs_dense": paired,
        "g_reasoner_minus_dense_mapping_at_1": round(delta, 6),
        "positive_database_count": positive_gate_dbs,
        "registered_positive_screen_pass": pass_screen,
        "interpretation": "SQL-used target ranking only; not semantic Role gold or end-to-end JOIN discovery",
    }


def run(args: argparse.Namespace) -> int:
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    require(cfg.get("experiment_id") == EXPERIMENT_ID, "CONFIG_EXPERIMENT_ID_MISMATCH")
    config_path = args.config.as_posix()
    is_cpu_recovery_amendment = config_path.endswith(CPU_RECOVERY_AMENDMENT_CONFIG)
    is_cpu_amendment = config_path.endswith(CPU_AMENDMENT_CONFIG) or is_cpu_recovery_amendment
    is_amendment = is_cpu_amendment or config_path.endswith(GPU_AMENDMENT_CONFIG)
    require(is_amendment or config_path.endswith(EXPECTED_CONFIG), "CONFIG_PATH_MISMATCH")
    if is_amendment:
        base_config_path = args.config.parent / Path(EXPECTED_CONFIG).name
        require(sha256_file(base_config_path) == cfg.get("base_config_sha256"), "BASE_CONFIG_HASH_MISMATCH")
        registered_run_ids = cfg.get("run_ids", {})
        expected_counts = cfg.get("selected_unit_counts", {})
        prepared_source_commit = cfg.get("prepared_manifest_source_commit")
        require(bool(prepared_source_commit), "PREPARED_SOURCE_COMMIT_NOT_PINNED")
        require(expected_counts == {"smoke": 5, "full": 108}, "AMENDMENT_UNIT_COUNTS_INVALID")
        if is_cpu_amendment:
            predecessor_config = CPU_AMENDMENT_CONFIG if is_cpu_recovery_amendment else GPU_AMENDMENT_CONFIG
            predecessor_path = args.config.parent / Path(predecessor_config).name
            require(
                sha256_file(predecessor_path) == cfg.get("predecessor_amendment_sha256"),
                "PREDECESSOR_AMENDMENT_HASH_MISMATCH",
            )
            require(cfg.get("execution_backend") == "cpu", "CPU_AMENDMENT_BACKEND_MISMATCH")
            cpu_resources = cfg.get("resources", {})
            require(
                cfg.get("cpu_threads") == cpu_resources.get("max_cpu_threads") == 8,
                "CPU_THREAD_BUDGET_MISMATCH",
            )
            require(
                cpu_resources.get("max_cpu_seconds_per_run") == MAX_CPU_SECONDS
                and cpu_resources.get("max_wall_seconds_per_run") == MAX_WALL_SECONDS
                and cpu_resources.get("max_rss_bytes") == MAX_RSS_BYTES
                and cpu_resources.get("max_gpu_allocated_bytes") == 0
                and cpu_resources.get("cuda_visible_devices") == "",
                "CPU_RESOURCE_BUDGET_MISMATCH",
            )
    else:
        registered_run_ids = cfg["resource_budget"]["run_ids"]
        expected_counts = None
        prepared_source_commit = args.expected_commit
    source_root = args.repo_root.resolve(strict=True)
    current_branch = subprocess.run(["git", "-C", str(source_root), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    current_commit = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    git_status = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain"], check=True, capture_output=True, text=True).stdout
    require(current_branch == EXPECTED_BRANCH, "BRANCH_MISMATCH")
    require(current_commit == args.expected_commit, "SOURCE_COMMIT_MISMATCH")
    require(not git_status.strip(), "WORKTREE_NOT_CLEAN")
    require(args.run_id == registered_run_ids[args.mode], "RUN_ID_MISMATCH")
    visible_gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if is_cpu_amendment:
        require(args.device == "cpu", "CPU_AMENDMENT_REQUIRES_CPU_DEVICE")
        require(visible_gpu == "", "CPU_AMENDMENT_REQUIRES_HIDDEN_GPUS")
    else:
        require(args.device == "cuda:0", "ONLY_VISIBLE_CUDA_ZERO_ALLOWED")
        require(bool(visible_gpu) and "," not in visible_gpu, "PIN_ONE_PHYSICAL_GPU")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "OFFLINE_MODE_REQUIRED")
    require(args.output_dir is not None and not args.output_dir.exists(), "OUTPUT_DIRECTORY_EXISTS")

    prepared = json.loads(args.cpu_summary.read_text(encoding="utf-8"))
    manifest_sha = sha256_file(args.prepared_manifest)
    require(prepared.get("status") == "CPU_DATA_GATE_PASS", "CPU_DATA_GATE_NOT_PASSED")
    require(prepared.get("prepared_manifest_sha256") == manifest_sha, "PREPARED_MANIFEST_HASH_MISMATCH")
    if is_amendment:
        require(prepared.get("source_commit") == prepared_source_commit, "CPU_SUMMARY_SOURCE_COMMIT_MISMATCH")
    manifest = json.loads(args.prepared_manifest.read_text(encoding="utf-8"))
    require(manifest.get("source_commit") == prepared_source_commit, "PREPARED_SOURCE_COMMIT_MISMATCH")
    ids_field = f"{args.mode}_unit_ids"
    count_field = f"{args.mode}_unit_count"
    selected_id_list = manifest[ids_field]
    selected_ids = set(selected_id_list)
    registered_count = manifest.get(count_field)
    if registered_count is None and is_amendment:
        registered_count = len(selected_id_list)
    if is_amendment:
        require(registered_count == expected_counts[args.mode], "AMENDMENT_MANIFEST_COUNT_MISMATCH")
    require(
        len(selected_id_list) == len(selected_ids) == registered_count,
        "SELECTED_UNIT_COUNT_MISMATCH",
    )
    require(not (set(manifest["smoke_unit_ids"]) & set(manifest["full_unit_ids"])), "SMOKE_FULL_OVERLAP")
    private = adapt_private(manifest, selected_ids)

    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    output_path = args.output_dir / "private_predictions.jsonl"
    run_meta = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "source_commit": current_commit,
        "prepared_manifest_source_commit": prepared_source_commit,
        "amendment_id": cfg.get("amendment_id") if is_amendment else None,
        "execution_backend": "cpu" if is_cpu_amendment else "cuda",
        "config_sha256": sha256_file(args.config),
        "cpu_summary_sha256": sha256_file(args.cpu_summary),
        "prepared_manifest_sha256": manifest_sha,
        "cuda_visible_devices": visible_gpu,
        "interpreter": sys.executable,
    }
    write_json(args.output_dir / "attempt_manifest.json", {**run_meta, "argv": [sys.executable, *sys.argv]})

    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    with output_path.open("x", encoding="utf-8") as stream:
        os.chmod(output_path, 0o600)
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
            expected = {"python": "3.12.15", "torch": "2.8.0", "torch_geometric": "2.6.1", "transformers": "4.56.1", "sentence_transformers": "5.1.1"}
            require(versions == expected, "ENVIRONMENT_VERSION_MISMATCH")
            device = torch.device(args.device)
            if is_cpu_amendment:
                require(not torch.cuda.is_available() and torch.cuda.device_count() == 0, "GPU_VISIBLE_IN_CPU_RUN")
                thread_limit = int(cfg.get("cpu_threads", 8))
            else:
                require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "ONE_VISIBLE_GPU_REQUIRED")
                torch.cuda.set_device(device)
                thread_limit = 8
            torch.manual_seed(20261107)
            torch.set_num_threads(min(thread_limit, os.cpu_count() or 1))
            torch.set_num_interop_threads(min(4, os.cpu_count() or 1))
            require(torch.get_num_threads() <= thread_limit, "CPU_THREAD_LIMIT_EXCEEDED")
            if device.type == "cuda":
                torch.cuda.reset_peak_memory_stats(device)

            checkpoint = args.checkpoint.resolve(strict=True)
            embedding_path = args.embedding_model.resolve(strict=True)
            require(sha256_file(checkpoint / "model.pth") == EXPECTED_GFM_MODEL_SHA256, "G_REASONER_WEIGHT_HASH_MISMATCH")
            require(sha256_file(checkpoint / "config.json") == EXPECTED_GFM_CONFIG_SHA256, "G_REASONER_CONFIG_HASH_MISMATCH")
            qwen_hashes = validate_qwen_snapshot(embedding_path)

            query_by_pair, table_texts, mapping_texts = base.query_and_passage_texts(set(selected_ids), private)
            all_passages = list(table_texts.values()) + list(base.RELATION_TEXTS)
            for unit_id in sorted(selected_ids):
                all_passages.extend(mapping_texts[unit_id].values())
            embedder = SentenceTransformer(str(embedding_path), device=str(device), trust_remote_code=True, local_files_only=True)
            embedder.eval()
            query_embeddings, query_usage = base.encode_texts(
                embedder, list(query_by_pair.values()), is_query=True, run_id=args.run_id, call_prefix="query", torch=torch
            )
            query_vector_by_pair = {unit_id: query_embeddings[query_by_pair[unit_id]] for unit_id in query_by_pair}
            passage_embeddings, passage_usage = base.encode_texts(
                embedder, all_passages, is_query=False, run_id=args.run_id, call_prefix="passage", torch=torch
            )
            del embedder
            if device.type == "cuda":
                torch.cuda.empty_cache()
            gfm_model, gfm_config = load_model_from_pretrained(str(checkpoint))
            parameter_count = sum(parameter.numel() for parameter in gfm_model.parameters())
            require(parameter_count == 34_640_897, "G_REASONER_PARAMETER_COUNT_MISMATCH")
            model_cfg = gfm_config["model_config"]
            require(int(model_cfg["entity_model"]["input_dim"]) == 1024 and int(model_cfg["feat_dim"]) == 1024, "G_REASONER_DIMENSION_MISMATCH")
            gfm_model.eval().to(device)

            rows: dict[str, dict[str, Any]] = {}
            graph_histogram = Counter()
            forward_seconds = 0.0
            for unit_id in sorted(selected_ids):
                graph_input = base.build_graph(
                    unit_id, private, table_texts, mapping_texts, passage_embeddings,
                    {text: passage_embeddings[text] for text in base.RELATION_TEXTS}, Data, torch,
                )
                graph_meta = graph_input[2]
                require(graph_meta["edge_count"] == graph_meta["mapping_count"] * 4 and graph_meta["start_seed_count"] == 2, "GRAPH_CONTRACT_MISMATCH")
                row = base.score_pair(
                    unit_id, private, query_by_pair, mapping_texts, passage_embeddings,
                    query_vector_by_pair[unit_id], graph_input, gfm_model, device, torch,
                )
                rows[unit_id] = row
                forward_seconds += float(row["g_reasoner_forward_seconds"])
                graph_histogram[str(graph_meta["mapping_count"])] += 1
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                if time.perf_counter() - start_wall > MAX_WALL_SECONDS:
                    raise TimeoutError("WALL_LIMIT_EXCEEDED")

            wall = time.perf_counter() - start_wall
            cpu = time.process_time() - start_cpu
            resources = resource_summary(torch, device, wall, cpu)
            run_summary = {
                **run_meta,
                "status": "SMOKE_PASS" if args.mode == "smoke" else "FULL_COMPLETE",
                "environment": versions,
                "device": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
                "torch_cpu_threads": torch.get_num_threads(),
                "torch_interop_threads": torch.get_num_interop_threads(),
                "pair_count_scored": len(rows),
                "candidate_mapping_count_scored": sum(len(private["items"][unit_id]["mappings"]) for unit_id in selected_ids),
                "g_reasoner_forward_count": len(rows),
                "g_reasoner_forward_seconds_total": round(forward_seconds, 6),
                "qwen_embedding_usage": {
                    "query": query_usage,
                    "passage": passage_usage,
                    "input_tokens": query_usage["input_tokens"] + passage_usage["input_tokens"],
                    "output_tokens": 0,
                },
                "graph_candidate_count_histogram": dict(sorted(graph_histogram.items(), key=lambda item: int(item[0]))),
                "qwen_snapshot_hashes": qwen_hashes,
                "resource_usage": resources,
                "sql_used_metrics": full_metrics(rows, private, selected_ids) if args.mode == "full" else None,
                "privacy": {
                    "question_or_schema_text_in_aggregate": False,
                    "sql_or_gold_target_in_model_input": False,
                    "per_unit_rankings_or_mapping_ids_in_aggregate": False,
                },
            }
            write_json(args.output_dir / "aggregate_summary.json", run_summary)
            write_json(args.output_dir / "run_manifest.json", {
                **run_meta,
                "private_predictions_sha256": sha256_file(output_path),
                "status": run_summary["status"],
                "resource_usage": resources,
            })
            print(json.dumps({"status": run_summary["status"], "pair_count_scored": len(rows), "resource_usage": resources}, sort_keys=True))
            return 0
        except Exception as error:  # preserve partial private output for diagnosis
            write_json(args.output_dir / "failure.json", {
                **run_meta,
                "status": "FAILED",
                "exception_type": type(error).__name__,
                "reason_code": str(error),
                "partial_prediction_count": sum(1 for _ in output_path.open("r", encoding="utf-8")),
            })
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cpu-summary", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    # Capture HEAD directly so the execution identity cannot be mistyped on
    # the command line. run() rechecks it before reading prepared inputs.
    args.expected_commit = subprocess.run(
        ["git", "-C", str(args.repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if args.output_dir.exists():
        print("status=STOP_OUTPUT_DIRECTORY_ALREADY_EXISTS")
        return 2
    try:
        return run(args)
    except Exception as error:
        print(f"status=FAILED reason_code={type(error).__name__}:{error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
