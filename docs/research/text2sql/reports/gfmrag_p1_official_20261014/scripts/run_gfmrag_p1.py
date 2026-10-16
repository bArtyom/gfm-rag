"""Run the registered P1 sweep through the official GFM-RAG Qwen3 class."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from gfmrag_p1_common import (
    DIMENSIONS,
    MODEL_PATH,
    PROJECT_ROOT,
    UPSTREAM_ROOT,
    load_official_qwen3_class,
    prepare_p1_inputs,
    sha256_bytes,
    sha256_file,
)


CONFIG_PATH = PROJECT_ROOT / "configs/gfmrag_p1_official_20261014.json"
RUN_CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
PHYSICAL_GPU_ID = int(RUN_CONFIG["resources"]["physical_gpu_id"])
MAX_GPU_SECONDS = int(RUN_CONFIG["resources"]["gpu_seconds_max"])
MAX_CPU_SECONDS = int(RUN_CONFIG["resources"]["cpu_seconds_max"])
MAX_THREADS = int(RUN_CONFIG["resources"]["cpu_threads_max"])
BOOTSTRAP_REPLICATES = int(RUN_CONFIG["evaluation"]["cluster_bootstrap"]["replicates"])
BOOTSTRAP_SEED = int(RUN_CONFIG["evaluation"]["cluster_bootstrap"]["seed"])
TOKEN_BUDGET = int(RUN_CONFIG["evaluation"]["complete_schema_budget_tokens"])
EXPECTED_SCHEMA_TEXT_HASH_OLD = (
    "2089cf5c7d10aa4056c98a19edca44a3fa0bfa17e2c1f0593848f7c935d4f226"
)
EXPECTED_SMOKE_SCHEMA_TEXT_HASH_OLD = (
    "580f3eaa6b4fe6783c0cde6c11570aa6fd812036b1143720c5a873ac4ec40806"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def hash_texts(texts: list[str]) -> str:
    return sha256_bytes("\n".join(texts).encode("utf-8"))


def package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(UPSTREAM_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def resource_cpu_seconds() -> float:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def normalize_prefixes(vectors: np.ndarray) -> tuple[dict[int, np.ndarray], dict[int, dict[str, float]]]:
    normalized: dict[int, np.ndarray] = {}
    norm_stats: dict[int, dict[str, float]] = {}
    for dimension in DIMENSIONS:
        prefix = np.asarray(vectors[:, :dimension], dtype=np.float32)
        raw_norms = np.linalg.norm(prefix, axis=1)
        if not np.isfinite(prefix).all() or not np.isfinite(raw_norms).all():
            raise RuntimeError(f"Non-finite embedding values at dimension={dimension}")
        if np.any(raw_norms <= 1e-12):
            raise RuntimeError(f"Zero-length embedding at dimension={dimension}")
        unit = prefix / raw_norms[:, None]
        normalized[dimension] = np.ascontiguousarray(unit, dtype=np.float32)
        unit_norms = np.linalg.norm(unit, axis=1)
        norm_stats[dimension] = {
            "raw_prefix_norm_min": float(raw_norms.min()),
            "raw_prefix_norm_median": float(np.median(raw_norms)),
            "raw_prefix_norm_p95": float(np.quantile(raw_norms, 0.95)),
            "normalized_norm_max_abs_error": float(np.max(np.abs(unit_norms - 1.0))),
        }
    return normalized, norm_stats


def recall_value(scores: np.ndarray, candidate_positions: list[int], gold_ids: tuple[str, ...], node_ids: list[str], top_k: int) -> tuple[float, int]:
    if not gold_ids:
        raise RuntimeError("Recall denominator is empty")
    local_scores = scores[candidate_positions]
    order = np.argsort(-local_scores, kind="stable")[:top_k]
    retrieved = {node_ids[candidate_positions[int(index)]] for index in order}
    hits = sum(gold_id in retrieved for gold_id in gold_ids)
    return hits / len(gold_ids), hits


def score_dimension(
    dimension: int,
    query_vectors: np.ndarray,
    node_vectors: np.ndarray,
    questions: list[dict[str, Any]],
    ordered_nodes: list[Any],
    nodes_by_db: dict[str, list[int]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, float]]:
    node_ids = [node.node_id for node in ordered_nodes]
    per_question: dict[str, dict[str, Any]] = {}
    per_database_values: dict[str, dict[str, list[float]]] = {}
    latencies_ms: list[float] = []
    metric_names = (
        "table_r5",
        "table_r10",
        "column_r5",
        "column_r10",
        "budget_recall",
        "budget_complete",
    )

    db_query_indexes: dict[str, list[int]] = {}
    for query_index, question in enumerate(questions):
        db_query_indexes.setdefault(question["db_id"], []).append(query_index)

    for db_id, query_indexes in db_query_indexes.items():
        candidate_indexes = nodes_by_db[db_id]
        table_positions = [
            local_index
            for local_index, global_index in enumerate(candidate_indexes)
            if ordered_nodes[global_index].node_type == "table"
        ]
        column_positions = [
            local_index
            for local_index, global_index in enumerate(candidate_indexes)
            if ordered_nodes[global_index].node_type == "column"
        ]
        candidate_matrix = node_vectors[candidate_indexes]
        database_values = {name: [] for name in metric_names}

        for query_index in query_indexes:
            question = questions[query_index]
            started = time.perf_counter()
            scores = query_vectors[query_index] @ candidate_matrix.T
            local_node_ids = [node_ids[index] for index in candidate_indexes]
            label = question["label"]
            qid = str(question["question_id"])

            table_r5, table_hits5 = recall_value(
                scores, table_positions, label["gold_table_ids"], local_node_ids, 5
            )
            table_r10, table_hits10 = recall_value(
                scores, table_positions, label["gold_table_ids"], local_node_ids, 10
            )
            row: dict[str, Any] = {
                "question_id": question["question_id"],
                "db_id": db_id,
                "column_eligible": label["column_eligible"],
                "table_gold_elements": len(label["gold_table_ids"]),
                "table_r5": table_r5,
                "table_r5_hits": table_hits5,
                "table_r10": table_r10,
                "table_r10_hits": table_hits10,
            }
            database_values["table_r5"].append(table_r5)
            database_values["table_r10"].append(table_r10)

            if label["column_eligible"]:
                column_r5, column_hits5 = recall_value(
                    scores, column_positions, label["gold_column_ids"], local_node_ids, 5
                )
                column_r10, column_hits10 = recall_value(
                    scores, column_positions, label["gold_column_ids"], local_node_ids, 10
                )
                gold_budget = (*label["gold_table_ids"], *label["gold_column_ids"])
                score_order = np.argsort(-scores, kind="stable")
                selected: set[str] = set()
                remaining_tokens = TOKEN_BUDGET
                for local_position in score_order:
                    global_index = candidate_indexes[int(local_position)]
                    node = ordered_nodes[global_index]
                    if node.token_count <= remaining_tokens:
                        selected.add(node.node_id)
                        remaining_tokens -= node.token_count
                found_budget = sum(node_id in selected for node_id in gold_budget)
                budget_recall = found_budget / len(gold_budget)
                budget_complete = float(all(node_id in selected for node_id in gold_budget))
                row.update(
                    {
                        "column_gold_elements": len(label["gold_column_ids"]),
                        "column_r5": column_r5,
                        "column_r5_hits": column_hits5,
                        "column_r10": column_r10,
                        "column_r10_hits": column_hits10,
                        "budget_gold_elements": len(gold_budget),
                        "budget_recall": budget_recall,
                        "budget_retrieved_gold_elements": found_budget,
                        "budget_complete": int(budget_complete),
                    }
                )
                database_values["column_r5"].append(column_r5)
                database_values["column_r10"].append(column_r10)
                database_values["budget_recall"].append(budget_recall)
                database_values["budget_complete"].append(budget_complete)

            latencies_ms.append((time.perf_counter() - started) * 1000.0)
            per_question[qid] = row
        per_database_values[db_id] = database_values

    def metric_summary(name: str) -> dict[str, Any]:
        query_values = [
            per_question[str(question["question_id"])][name]
            for question in questions
            if name in per_question[str(question["question_id"]) ]
        ]
        db_means = {
            db_id: float(np.mean(values[name]))
            for db_id, values in per_database_values.items()
            if values[name]
        }
        element_name = {
            "table_r5": "table_gold_elements",
            "table_r10": "table_gold_elements",
            "column_r5": "column_gold_elements",
            "column_r10": "column_gold_elements",
            "budget_recall": "budget_gold_elements",
        }.get(name)
        if element_name:
            total_hits = sum(
                per_question[str(question["question_id"])][name + "_hits"]
                if name in ("table_r5", "table_r10", "column_r5", "column_r10")
                else per_question[str(question["question_id"])]["budget_retrieved_gold_elements"]
                for question in questions
                if name in per_question[str(question["question_id"]) ]
            )
            total_gold = sum(
                per_question[str(question["question_id"])][element_name]
                for question in questions
                if name in per_question[str(question["question_id"]) ]
            )
            return {
                "queries": len(query_values),
                "gold_elements": total_gold,
                "macro_query_recall": float(np.mean(query_values)),
                "micro_element_recall": float(total_hits / total_gold),
                "macro_database_recall": float(np.mean(list(db_means.values()))),
                "database_means": db_means,
            }
        return {
            "queries": len(query_values),
            "macro_query_rate": float(np.mean(query_values)),
            "macro_database_rate": float(np.mean(list(db_means.values()))),
            "database_means": db_means,
        }

    # Match the registered denominator policy: all questions for tables,
    # only fully resolved questions for columns and complete-schema coverage.
    metric_specs = {
        "table_recall_at_5": "table_r5",
        "table_recall_at_10": "table_r10",
        "column_recall_at_5": "column_r5",
        "column_recall_at_10": "column_r10",
        "schema_coverage_at_2048": "budget_recall",
        "complete_schema_question_rate_at_2048": "budget_complete",
    }
    metrics = {
        output_name: metric_summary(metric_name)
        for output_name, metric_name in metric_specs.items()
    }
    metrics.update(
        {
            "retrieval_latency_ms": {
                "median": float(np.median(latencies_ms)),
                "p95": float(np.quantile(latencies_ms, 0.95)),
            },
            "scoring_seconds": float(sum(latencies_ms) / 1000.0),
            "node_vector_bytes": int(len(ordered_nodes) * dimension * 4),
            "node_vector_storage_saving_percent_vs_1024": float(
                100.0 * (1.0 - dimension / 1024.0)
            ),
        }
    )
    normalized_error = float(
        np.max(np.abs(np.linalg.norm(query_vectors, axis=1) - 1.0))
    )
    metrics["normalized_output_norm_max_abs_error"] = normalized_error
    per_database = {
        db_id: {
            "table_r5": float(np.mean(values["table_r5"])),
            "table_r10": float(np.mean(values["table_r10"])),
            "column_r5": float(np.mean(values["column_r5"])) if values["column_r5"] else None,
            "column_r10": float(np.mean(values["column_r10"])) if values["column_r10"] else None,
            "schema_coverage_at_2048": float(np.mean(values["budget_recall"])) if values["budget_recall"] else None,
            "complete_schema_rate_at_2048": float(np.mean(values["budget_complete"])) if values["budget_complete"] else None,
        }
        for db_id, values in per_database_values.items()
    }
    raw_metric_values = {
        name: {
            str(question["question_id"]): per_question[str(question["question_id"])].get(name)
            for question in questions
        }
        for name in metric_names
    }
    return metrics, per_question, {"per_database": per_database, "raw_metric_values": raw_metric_values}


def bootstrap_samples(database_means: dict[str, float], sampled_database_indexes: np.ndarray, database_order: list[str]) -> np.ndarray:
    values = np.array([database_means[db_id] for db_id in database_order], dtype=np.float64)
    return values[sampled_database_indexes].mean(axis=1)


def summarize_paired(
    question_results: dict[int, dict[str, dict[str, Any]]],
    per_dimension_aux: dict[int, dict[str, Any]],
    database_order: list[str],
) -> dict[str, Any]:
    paired: dict[str, Any] = {}
    question_db = {
        qid: rows[1024]["db_id"]
        for qid, rows in question_results.items()
        if 1024 in rows
    }
    baseline_dim = 1024
    metric_pairs = {
        "table_r5": "table_recall_at_5",
        "table_r10": "table_recall_at_10",
        "column_r5": "column_recall_at_5",
        "column_r10": "column_recall_at_10",
        "budget_recall": "schema_coverage_at_2048",
        "budget_complete": "complete_schema_question_rate_at_2048",
    }
    for dimension in DIMENSIONS:
        if dimension == baseline_dim:
            continue
        paired[str(dimension)] = {}
        for metric_name, summary_name in metric_pairs.items():
            question_ids = [
                qid
                for qid, dimensions in question_results.items()
                if metric_name in dimensions[dimension]
                and metric_name in dimensions[baseline_dim]
            ]
            delta_values = {
                qid: float(question_results[qid][dimension][metric_name])
                - float(question_results[qid][baseline_dim][metric_name])
                for qid in question_ids
            }
            better = sum(value > 1e-12 for value in delta_values.values())
            worse = sum(value < -1e-12 for value in delta_values.values())
            same = len(delta_values) - better - worse
            if metric_name == "budget_complete":
                rescued = sum(
                    question_results[qid][dimension][metric_name]
                    and not question_results[qid][baseline_dim][metric_name]
                    for qid in question_ids
                )
                damaged = sum(
                    question_results[qid][baseline_dim][metric_name]
                    and not question_results[qid][dimension][metric_name]
                    for qid in question_ids
                )
            else:
                rescued = 0
                damaged = 0

            dimension_means = per_dimension_aux[dimension]["raw_metric_values"]
            baseline_means = per_dimension_aux[baseline_dim]["raw_metric_values"]
            dimension_db_means = {
                db_id: float(
                    np.mean(
                        [
                            float(dimension_means[metric_name][str(qid)])
                            for qid in question_ids
                            if question_db[qid] == db_id
                        ]
                    )
                )
                for db_id in database_order
                if any(question_db[qid] == db_id for qid in question_ids)
            }
            baseline_db_means = {
                db_id: float(
                    np.mean(
                        [
                            float(baseline_means[metric_name][str(qid)])
                            for qid in question_ids
                            if question_db[qid] == db_id
                        ]
                    )
                )
                for db_id in database_order
                if any(question_db[qid] == db_id for qid in question_ids)
            }
            common_db_order = [
                db_id
                for db_id in database_order
                if db_id in dimension_db_means and db_id in baseline_db_means
            ]
            db_differences = {
                db_id: dimension_db_means[db_id] - baseline_db_means[db_id]
                for db_id in common_db_order
            }
            rng = np.random.default_rng(BOOTSTRAP_SEED)
            sampled_database_indexes = rng.integers(
                0,
                len(common_db_order),
                size=(BOOTSTRAP_REPLICATES, len(common_db_order)),
            )
            samples = bootstrap_samples(
                db_differences, sampled_database_indexes, common_db_order
            )
            paired[str(dimension)][metric_name] = {
                "question_level": {
                    "better": int(better),
                    "worse": int(worse),
                    "same": int(same),
                    "rescued_complete_queries": int(rescued),
                    "damaged_complete_queries": int(damaged),
                },
                "database_cluster_bootstrap_95": {
                    "database_clusters": len(common_db_order),
                    "mean_difference": float(np.mean(list(db_differences.values()))),
                    "ci95": [float(value) for value in np.quantile(samples, [0.025, 0.975])],
                },
            }
    return paired


def run(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    if run_dir.exists():
        raise FileExistsError(f"Refusing to reuse existing result directory: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    started_utc = utc_now()
    wall_started = time.perf_counter()
    cpu_started = resource_cpu_seconds()
    run_start: dict[str, Any] = {
        "experiment_id": RUN_CONFIG["experiment_id"],
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": started_utc,
        "state": "input_validation",
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "config_path": str(CONFIG_PATH),
        "config_sha256": sha256_file(CONFIG_PATH),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "shared_support_sha256": sha256_file(Path(__file__).with_name("gfmrag_p1_common.py")),
        "physical_gpu_id": PHYSICAL_GPU_ID,
        "cuda_visible_devices_at_start": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "local_rank_at_start": os.environ.get("LOCAL_RANK"),
        "upstream_path": str(UPSTREAM_ROOT),
    }
    write_json(run_dir / "run_start.json", run_start)

    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != str(PHYSICAL_GPU_ID):
            raise RuntimeError(
                f"Expected CUDA_VISIBLE_DEVICES={PHYSICAL_GPU_ID}, got "
                f"{os.environ.get('CUDA_VISIBLE_DEVICES')}"
            )
        if os.environ.get("LOCAL_RANK") != str(PHYSICAL_GPU_ID):
            raise RuntimeError(
                f"Expected LOCAL_RANK={PHYSICAL_GPU_ID} for the official upstream selector, "
                f"got {os.environ.get('LOCAL_RANK')}"
            )
        source_commit = git_output("rev-parse", "HEAD")
        source_dirty = git_output("status", "--porcelain")
        if source_commit != RUN_CONFIG["source"]["commit"] or source_dirty:
            raise RuntimeError(
                f"Upstream checkout mismatch or dirty source: commit={source_commit}, "
                f"dirty={source_dirty!r}"
            )

        prepared = prepare_p1_inputs(load_tokenizer=True, description_fallback_encoding="cp1252")
        all_questions = prepared["questions"]
        if args.mode == "smoke":
            questions = all_questions[:5]
            if len(questions) != 5:
                raise RuntimeError(f"Expected exactly five smoke questions, got {len(questions)}")
        else:
            questions = all_questions
            if len(questions) != 1534:
                raise RuntimeError(f"Expected 1,534 full questions, got {len(questions)}")

        question_db_ids = set(question["db_id"] for question in questions)
        all_nodes = sorted(
            prepared["nodes"], key=lambda node: node.node_type != "table"
        )
        ordered_nodes = [node for node in all_nodes if node.db_id in question_db_ids]
        if args.mode == "smoke" and len(ordered_nodes) != 92:
            raise RuntimeError(
                f"Expected 92 candidates for the registered first-five smoke, got {len(ordered_nodes)}"
            )
        nodes_by_db: dict[str, list[int]] = {}
        for node_index, node in enumerate(ordered_nodes):
            nodes_by_db.setdefault(node.db_id, []).append(node_index)

        node_ids = {node.node_id for node in ordered_nodes}
        for question in questions:
            label = question["label"]
            if not set(label["gold_table_ids"]).issubset(node_ids):
                raise RuntimeError(f"Missing table label candidates for question {question['question_id']}")
            if not set(label["gold_column_ids"]).issubset(node_ids):
                raise RuntimeError(f"Missing column label candidates for question {question['question_id']}")

        query_prompts = [question["prompt"] for question in questions]
        schema_texts = [node.text for node in ordered_nodes]
        query_text_hash = hash_texts(query_prompts)
        schema_text_hash = hash_texts(schema_texts)
        first_db_nodes = [node.text for node in ordered_nodes if node.db_id == questions[0]["db_id"]]
        first_db_hash = hash_texts(first_db_nodes)
        input_audit = {
            "mode": args.mode,
            "question_count": len(questions),
            "database_count": len(question_db_ids),
            "question_ids": [question["question_id"] for question in questions],
            "question_text_sha256_newline_join": query_text_hash,
            "schema_node_text_sha256_newline_join_type_first": schema_text_hash,
            "first_database_schema_text_sha256_newline_join_type_first": first_db_hash,
            "legacy_full_schema_text_sha256_recorded": EXPECTED_SCHEMA_TEXT_HASH_OLD,
            "legacy_full_hash_direct_match": schema_text_hash == EXPECTED_SCHEMA_TEXT_HASH_OLD,
            "legacy_hash_comparison_note": "The earlier full-run record does not document node ordering or hash serialization. The registered text definition, source hashes, node counts, and first-database five-question text fingerprint were independently checked; this rerun records its own deterministic type-first full text fingerprint.",
            "legacy_five_question_schema_text_sha256_recorded": EXPECTED_SMOKE_SCHEMA_TEXT_HASH_OLD,
            "legacy_five_question_first_database_hash_match": first_db_hash == EXPECTED_SMOKE_SCHEMA_TEXT_HASH_OLD,
            "node_count": len(ordered_nodes),
            "table_node_count": sum(node.node_type == "table" for node in ordered_nodes),
            "column_node_count": sum(node.node_type == "column" for node in ordered_nodes),
            "label_counts_full_frozen_source": prepared["label_counts"],
            "frozen_input_hashes": prepared["frozen_hashes"],
            "description_csv_encodings": prepared["description_csv_encodings"],
            "description_csv_encoding_counts": prepared["description_csv_encoding_counts"],
            "description_csv_fallback_encoding": prepared["description_csv_fallback_encoding"],
            "token_stats": prepared["token_stats"],
            "candidate_order": "all table nodes then all column nodes; stable within BIRD dev_tables.json order",
        }
        write_json(run_dir / "input_audit.json", input_audit)

        torch_threads = MAX_THREADS
        os.environ["OMP_NUM_THREADS"] = str(torch_threads)
        os.environ["MKL_NUM_THREADS"] = str(torch_threads)
        os.environ["OPENBLAS_NUM_THREADS"] = str(torch_threads)
        os.environ["NUMEXPR_NUM_THREADS"] = str(torch_threads)
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["LOCAL_RANK"] = str(PHYSICAL_GPU_ID)
        os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
        import torch

        torch.set_num_threads(torch_threads)
        backend_class = load_official_qwen3_class()
        backend_source = Path(sys.modules[backend_class.__module__].__file__).resolve()
        if UPSTREAM_ROOT.resolve() not in backend_source.parents:
            raise RuntimeError(f"Loaded encoder is outside the official checkout: {backend_source}")

        run_start.update(
            {
                "state": "model_load_started",
                "source_commit": source_commit,
                "source_dirty": False,
                "source_license_sha256": sha256_file(UPSTREAM_ROOT / "LICENSE"),
                "upstream_encoder_source": str(backend_source),
                "upstream_encoder_source_sha256": sha256_file(backend_source),
                "upstream_base_source_sha256": sha256_file(UPSTREAM_ROOT / "gfmrag/text_emb_models/base_model.py"),
                "input_audit_path": str(run_dir / "input_audit.json"),
                "input_audit_sha256": sha256_file(run_dir / "input_audit.json"),
                "input_question_text_sha256": query_text_hash,
                "input_schema_text_sha256": schema_text_hash,
                "started_model_load_at_utc": utc_now(),
            }
        )
        write_json(run_dir / "run_start.json", run_start)

        gpu_started = time.perf_counter()
        encoder = backend_class(
            text_emb_model_name=str(MODEL_PATH),
            normalize=True,
            batch_size=int(RUN_CONFIG["model"]["batch_size"]),
            query_instruct=None,
            passage_instruct=None,
            truncate_dim=int(RUN_CONFIG["model"]["upstream_truncate_dim"]),
            model_kwargs=None,
            tokenizer_kwargs={"local_files_only": True},
        )
        # Upstream maps LOCAL_RANK to CUDA_VISIBLE_DEVICES and then removes
        # CUDA_VISIBLE_DEVICES. Restore the registered physical-GPU selector
        # before its encode() method checks/clears CUDA state.
        os.environ["CUDA_VISIBLE_DEVICES"] = str(PHYSICAL_GPU_ID)
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError(
                "Expected one visible CUDA device after upstream model initialization: "
                f"available={torch.cuda.is_available()} count={torch.cuda.device_count()}"
            )
        selected_gpu_name = torch.cuda.get_device_name(0)
        model_load_seconds = time.perf_counter() - gpu_started
        if model_load_seconds > MAX_GPU_SECONDS:
            raise RuntimeError(f"GPU wall-time budget exceeded during model load: {model_load_seconds:.2f}s")

        query_encode_started = time.perf_counter()
        query_tensor = encoder.encode(query_prompts, is_query=True, show_progress_bar=False)
        query_encode_seconds = time.perf_counter() - query_encode_started
        if not torch.is_tensor(query_tensor):
            raise RuntimeError(f"Official encode returned unexpected query type: {type(query_tensor)}")
        query_vectors_full = query_tensor.detach().to(device="cpu", dtype=torch.float32).numpy()
        del query_tensor
        if query_vectors_full.shape != (len(questions), 1024):
            raise RuntimeError(f"Unexpected query embedding shape: {query_vectors_full.shape}")

        schema_encode_started = time.perf_counter()
        node_tensor = encoder.encode(schema_texts, is_query=False, show_progress_bar=False)
        schema_encode_seconds = time.perf_counter() - schema_encode_started
        if not torch.is_tensor(node_tensor):
            raise RuntimeError(f"Official encode returned unexpected schema type: {type(node_tensor)}")
        node_vectors_full = node_tensor.detach().to(device="cpu", dtype=torch.float32).numpy()
        del node_tensor
        if node_vectors_full.shape != (len(ordered_nodes), 1024):
            raise RuntimeError(f"Unexpected schema embedding shape: {node_vectors_full.shape}")
        del encoder
        gc.collect()
        gpu_elapsed = time.perf_counter() - gpu_started
        if gpu_elapsed > MAX_GPU_SECONDS:
            raise RuntimeError(f"GPU wall-time budget exceeded: {gpu_elapsed:.2f}s > {MAX_GPU_SECONDS}s")

        query_norms = np.linalg.norm(query_vectors_full, axis=1)
        node_norms = np.linalg.norm(node_vectors_full, axis=1)
        if not np.isfinite(query_vectors_full).all() or not np.isfinite(node_vectors_full).all():
            raise RuntimeError("Official encoder returned non-finite vectors")
        query_vectors_by_dim, query_norm_stats = normalize_prefixes(query_vectors_full)
        node_vectors_by_dim, node_norm_stats = normalize_prefixes(node_vectors_full)

        dimension_metrics: dict[str, Any] = {}
        dimension_aux: dict[int, dict[str, Any]] = {}
        question_results: dict[int, dict[str, dict[str, Any]]] = {
            int(question["question_id"]): {} for question in questions
        }
        per_database: dict[str, dict[str, Any]] = {db_id: {} for db_id in nodes_by_db}
        scoring_started = time.perf_counter()
        scoring_seconds_by_dim: dict[str, float] = {}
        for dimension in DIMENSIONS:
            dim_started = time.perf_counter()
            normalized_queries = query_vectors_by_dim[dimension]
            normalized_nodes = node_vectors_by_dim[dimension]
            metrics, rows, auxiliary = score_dimension(
                dimension,
                normalized_queries,
                normalized_nodes,
                questions,
                ordered_nodes,
                nodes_by_db,
            )
            dim_started_seconds = time.perf_counter() - dim_started
            scoring_seconds_by_dim[str(dimension)] = dim_started_seconds
            metrics["scoring_seconds"] = dim_started_seconds
            metrics["node_vector_bytes"] = int(len(ordered_nodes) * dimension * 4)
            metrics["node_vector_storage_saving_percent_vs_1024"] = float(
                100.0 * (1.0 - dimension / 1024.0)
            )
            metrics["normalized_output_norm_max_abs_error"] = max(
                query_norm_stats[dimension]["normalized_norm_max_abs_error"],
                node_norm_stats[dimension]["normalized_norm_max_abs_error"],
            )
            dimension_metrics[str(dimension)] = metrics
            dimension_aux[dimension] = auxiliary
            for qid_text, row in rows.items():
                question_results[int(qid_text)][dimension] = row
            for db_id, values in auxiliary["per_database"].items():
                per_database.setdefault(db_id, {})[str(dimension)] = values

        paired = summarize_paired(question_results, dimension_aux, list(nodes_by_db))
        baseline_coverage = dimension_metrics["1024"]["complete_schema_question_rate_at_2048"]["macro_query_rate"]
        baseline_schema_element = dimension_metrics["1024"]["schema_coverage_at_2048"]["macro_query_recall"]
        gate_losses: dict[str, float] = {}
        partial_losses: dict[str, float] = {}
        storage_savings: dict[str, float] = {}
        passed_dimensions: list[int] = []
        for dimension in DIMENSIONS:
            dim_key = str(dimension)
            if dimension == 1024:
                continue
            complete_rate = dimension_metrics[dim_key]["complete_schema_question_rate_at_2048"]["macro_query_rate"]
            partial_recall = dimension_metrics[dim_key]["schema_coverage_at_2048"]["macro_query_recall"]
            gate_losses[dim_key] = float((baseline_coverage - complete_rate) * 100.0)
            partial_losses[dim_key] = float((baseline_schema_element - partial_recall) * 100.0)
            storage_savings[dim_key] = float(dimension_metrics[dim_key]["node_vector_storage_saving_percent_vs_1024"])
            no_recall_drop = all(
                dimension_metrics[dim_key][metric]["macro_query_recall"]
                >= dimension_metrics["1024"][metric]["macro_query_recall"] - 1e-12
                for metric in (
                    "table_recall_at_5",
                    "table_recall_at_10",
                    "column_recall_at_5",
                    "column_recall_at_10",
                )
            )
            if (
                gate_losses[dim_key] <= 1.0 + 1e-12
                and storage_savings[dim_key] >= 45.0 - 1e-12
                and no_recall_drop
            ):
                passed_dimensions.append(dimension)

        elapsed_wall = time.perf_counter() - wall_started
        elapsed_cpu = resource_cpu_seconds() - cpu_started
        process_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        summary = {
            "experiment_id": RUN_CONFIG["experiment_id"],
            "run_id": args.run_id,
            "stage": "P1 official backend dimension sweep, table/column only",
            "upstream_url": RUN_CONFIG["source"]["url"],
            "upstream_commit": source_commit,
            "upstream_license": RUN_CONFIG["source"]["license"],
            "upstream_encoder": f"{backend_class.__module__}.{backend_class.__name__}",
            "upstream_encoder_source": str(backend_source),
            "upstream_encoder_source_sha256": sha256_file(backend_source),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "shared_support_sha256": sha256_file(Path(__file__).with_name("gfmrag_p1_common.py")),
            "config_sha256": sha256_file(CONFIG_PATH),
            "input_hashes": {
                "questions_sha256": prepared["frozen_hashes"]["sha256"]["questions"],
                "schema_sha256": prepared["frozen_hashes"]["sha256"]["schema"],
                "p0_audit_sha256": prepared["frozen_hashes"]["sha256"]["p0_audit"],
                "gold_labels_sha256": prepared["frozen_hashes"]["sha256"]["gold_labels"],
                "model_manifest_sha256": prepared["frozen_hashes"]["model_manifest_sha256"],
                "question_text_sha256": query_text_hash,
                "schema_node_text_sha256_newline_join_type_first": schema_text_hash,
                "legacy_full_schema_text_sha256_recorded": EXPECTED_SCHEMA_TEXT_HASH_OLD,
                "legacy_full_schema_text_hash_direct_match": schema_text_hash == EXPECTED_SCHEMA_TEXT_HASH_OLD,
                "legacy_schema_hash_comparison_note": "The earlier full-run record does not document node ordering or hash serialization; the current rerun stores a deterministic type-first fingerprint and separately records frozen source hashes.",
                "description_csv_encoding_counts": prepared["description_csv_encoding_counts"],
                "description_csv_encodings": prepared["description_csv_encodings"],
                "verified_description_csv_count": prepared["frozen_hashes"]["description_csv_count_verified"],
            },
            "dataset": {
                "split": "BIRD dev; exploratory",
                "questions": len(questions),
                "databases": len(question_db_ids),
                "schema_nodes": len(ordered_nodes),
                "table_nodes": sum(node.node_type == "table" for node in ordered_nodes),
                "column_nodes": sum(node.node_type == "column" for node in ordered_nodes),
                "gold_label_counts_full_source": prepared["label_counts"],
                "question_ids": [question["question_id"] for question in questions],
            },
            "method": {
                "backend": "official GFM-RAG Qwen3TextEmbModel, local vLLM LLM(task=embed)",
                "precision": "vLLM/model default; backend vectors returned as float32 CPU tensors",
                "query_instruction": RUN_CONFIG["evaluation"]["query_instruction"],
                "dimensions": list(DIMENSIONS),
                "score": RUN_CONFIG["evaluation"]["score"],
                "top_k_by_type": [5, 10],
                "schema_token_budget": TOKEN_BUDGET,
                "token_counting_rule": RUN_CONFIG["evaluation"]["budget_tokenization"],
                "column_denominator_policy": "only fully resolved gold-column questions",
                "candidate_truncated_at_max_input_tokens": {
                    "queries": 0,
                    "schema_nodes": 0,
                },
                "query_instruction_application": "preformatted query strings passed unchanged through official encode(is_query=True); query_instruct=None",
                "official_normalize_attribute": bool(RUN_CONFIG["model"]["normalization"].startswith("explicit")),
                "explicit_prefix_l2_normalization": True,
                "raw_query_vector_norm_min_median_p95_max": [
                    float(np.min(query_norms)),
                    float(np.median(query_norms)),
                    float(np.quantile(query_norms, 0.95)),
                    float(np.max(query_norms)),
                ],
                "raw_node_vector_norm_min_median_p95_max": [
                    float(np.min(node_norms)),
                    float(np.median(node_norms)),
                    float(np.quantile(node_norms, 0.95)),
                    float(np.max(node_norms)),
                ],
                "dimension_norms": {
                    str(dimension): {
                        "query": query_norm_stats[dimension],
                        "node": node_norm_stats[dimension],
                        "normalized_norm_max_abs_error": dimension_metrics[str(dimension)]["normalized_output_norm_max_abs_error"],
                    }
                    for dimension in DIMENSIONS
                },
                "retrieval_scoring_performed": True,
                "sql_execution_count": 0,
                "api_call_count": 0,
                "training_steps": 0,
                "dependency_installations": 0,
                "model_downloads": 0,
            },
            "metrics_by_dimension": dimension_metrics,
            "per_database": per_database,
            "paired_vs_1024": paired,
            "screening_gate": {
                "table_column_screen_pass_dimensions": passed_dimensions,
                "complete_schema_question_rate_loss_percentage_points_vs_1024": gate_losses,
                "partial_schema_element_recall_loss_percentage_points_vs_1024": partial_losses,
                "vector_storage_saving_percentage_vs_1024": storage_savings,
                "full_h1_pass_dimensions": [],
                "full_h1_status": "not testable: FK/role metrics were excluded by the registered P0 data-quality gate",
                "screen_threshold": "complete required Table+Column question rate loss <=1.0 percentage point, storage saving >=45%, and no Table/Column Recall@5 or @10 drop",
            },
            "runtime": {
                "model_load_seconds": model_load_seconds,
                "query_encode_seconds": query_encode_seconds,
                "schema_encode_seconds": schema_encode_seconds,
                "gpu_wall_seconds_model_load_and_encode": gpu_elapsed,
                "scoring_seconds_by_dimension": scoring_seconds_by_dim,
                "scoring_seconds_total": time.perf_counter() - scoring_started,
                "wall_seconds_total": elapsed_wall,
                "cpu_seconds_total_with_reaped_children": elapsed_cpu,
                "process_maxrss_kib": int(process_maxrss),
                "limits": {
                    "gpu_seconds_max": MAX_GPU_SECONDS,
                    "cpu_seconds_max": MAX_CPU_SECONDS,
                    "cpu_threads_max": MAX_THREADS,
                    "ram_gib_max": RUN_CONFIG["resources"]["ram_gib_max"],
                },
                "budget_status": {
                    "gpu_within_budget": gpu_elapsed <= MAX_GPU_SECONDS,
                    "cpu_within_budget": elapsed_cpu <= MAX_CPU_SECONDS,
                    "process_maxrss_within_16gib": int(process_maxrss) <= 16 * 1024 * 1024,
                },
            },
            "question_limit": len(questions),
            "smoke_only": args.mode == "smoke",
            "smoke_status": "passed" if args.mode == "smoke" else None,
            "environment": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "torch_cuda_build": torch.version.cuda,
                "torch_cuda_available": bool(torch.cuda.is_available()),
                "visible_cuda_device_count": int(torch.cuda.device_count()),
                "selected_gpu_physical_id": PHYSICAL_GPU_ID,
                "selected_gpu_name": selected_gpu_name,
                "vllm": package_version("vllm"),
                "transformers": package_version("transformers"),
                "numpy": np.__version__,
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "local_rank": os.environ.get("LOCAL_RANK"),
                "model_path": str(MODEL_PATH),
                "model_path_resolved": str(MODEL_PATH.resolve()),
            },
            "created_at_utc": utc_now(),
        }
        if elapsed_cpu > MAX_CPU_SECONDS:
            raise RuntimeError(f"CPU budget exceeded: {elapsed_cpu:.2f}s > {MAX_CPU_SECONDS}s")
        if int(process_maxrss) > 16 * 1024 * 1024:
            raise RuntimeError(f"Runner process exceeded registered 16 GiB RSS limit: {process_maxrss} KiB")

        with (run_dir / "per_question_private.jsonl").open("w", encoding="utf-8") as file:
            for question in questions:
                qid = int(question["question_id"])
                label = question["label"]
                row = {
                    "question_id": qid,
                    "db_id": question["db_id"],
                    "column_eligible": label["column_eligible"],
                    "gold_table_ids_private": list(label["gold_table_ids"]),
                    "gold_column_ids_private": list(label["gold_column_ids"]),
                    "metrics": {
                        str(dimension): question_results[qid][dimension]
                        for dimension in DIMENSIONS
                    },
                }
                file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        write_json(run_dir / "summary.json", summary)
        run_start.update(
            {
                "state": "completed",
                "finished_at_utc": utc_now(),
                "summary_sha256": sha256_file(run_dir / "summary.json"),
                "per_question_sha256": sha256_file(run_dir / "per_question_private.jsonl"),
            }
        )
        write_json(run_dir / "run_start.json", run_start)
        print(json.dumps({
            "status": "completed",
            "run_id": args.run_id,
            "run_dir": str(run_dir),
            "mode": args.mode,
            "questions": len(questions),
            "databases": len(question_db_ids),
            "schema_nodes": len(ordered_nodes),
            "gpu_wall_seconds": gpu_elapsed,
            "wall_seconds": elapsed_wall,
            "screen_pass_dimensions": passed_dimensions,
        }, ensure_ascii=False))
    except Exception as exc:
        run_start.update(
            {
                "state": "failed",
                "failed_at_utc": utc_now(),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "wall_seconds_until_failure": time.perf_counter() - wall_started,
                "cpu_seconds_until_failure": resource_cpu_seconds() - cpu_started,
            }
        )
        write_json(run_dir / "run_start.json", run_start)
        write_json(
            run_dir / "failure.json",
            {
                "failed_at_utc": utc_now(),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
