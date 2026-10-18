#!/usr/bin/env python3
"""Run the preregistered local-CPU P2b Values text ablation.

Question-level rows, IDs, model vectors, and source data stay in the supplied
private output directory. Only the anonymous aggregate is suitable for archive.
"""

from __future__ import annotations

import argparse
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

MAX_THREADS = 8
MAX_CPU_SECONDS = 7200
MAX_WALL_SECONDS = 3600
MAX_RSS_GIB = 16
MAX_LENGTH = 8192
BATCH_SIZE = 32
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261019
EXPERIMENT_ID = "p2b_values_ablation_20261018_01"
P1_6_RUN_ID = "p1_6_full1534_20261018_01"
P1_6_COMMIT = "d948d462f9407a18f4a48c85a76380d54f865cb2"
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
P2A_RUNNER = REPO_ROOT / "scripts/text2sql/run_p2a_similarity.py"
PLAN_PATH = REPO_ROOT / "docs/research/text2sql/plans/p2b_values_ablation_20261018.md"
CONFIG_PATH = REPO_ROOT / "docs/research/text2sql/reports/p2b_values_ablation_20261018_01/experiment_config.json"


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
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else f"unavailable: {result.stderr.strip()}"


def resource_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu_snapshot_not_used": command_output([
            "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]),
        "free_h": command_output(["free", "-h"]),
        "cpu_threads_available": os.cpu_count(),
        "cpu_model": command_output(["bash", "-lc", "lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -n 1"]),
        "disk": command_output(["df", "-h", str(REPO_ROOT)]),
    }


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load experiment helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-dir", type=Path)
    parser.add_argument("--p1-6-run-dir", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--p1-5-run-dir", type=Path, required=True)
    return parser.parse_args()


def load_frozen_inputs(args: argparse.Namespace) -> tuple[Any, Any, dict[str, Any], dict[str, Any], dict[str, Any], np.ndarray, np.ndarray, list[dict[str, Any]]]:
    p1 = load_module(P1_6_RUNNER, "p1_6_for_p2b_values")
    p2a = load_module(P2A_RUNNER, "p2a_for_p2b_values")
    p2a.p1_module = p1
    source = p1.assert_committed_source(args.expected_commit)
    if source.get("worktree_status") != "clean":
        raise RuntimeError("Formal P2b execution requires a clean, committed source tree")
    if not PLAN_PATH.is_file() or not CONFIG_PATH.is_file():
        raise FileNotFoundError("The P2b protocol or experiment config is missing")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("experiment_id") != EXPERIMENT_ID or config.get("status") != "preregistered_not_run":
        raise RuntimeError("The checked-in P2b config does not match the preregistered experiment")

    validation_args = argparse.Namespace(
        p1_6_run_dir=args.p1_6_run_dir,
        legacy_root=args.legacy_root,
        dataset_root=args.dataset_root,
        model_path=args.model_path,
        previous_run_dir=args.previous_run_dir,
        p1_5_run_dir=args.p1_5_run_dir,
    )
    input_record, prepared, query_cache, node_cache = p2a.validate_p1_6_inputs(validation_args, p1)
    counts = input_record["input_record"].get("counts")
    if counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Unexpected frozen input counts: {counts}")

    p1_run_dir = args.p1_6_run_dir.resolve()
    private_rows_path = p1_run_dir / "per_question_private.jsonl"
    if not private_rows_path.is_file():
        raise FileNotFoundError(f"P1.6 per-question parity evidence is missing: {private_rows_path}")
    baseline_rows: list[dict[str, Any]] = []
    with private_rows_path.open("r", encoding="utf-8") as file:
        for line in file:
            baseline_rows.append(json.loads(line))
    if len(baseline_rows) != EXPECTED_COUNTS["questions"]:
        raise RuntimeError("P1.6 private parity row count differs from the frozen 1,534-question denominator")
    return p1, p2a, source, input_record, prepared, query_cache, node_cache, baseline_rows


def select_active_inputs(
    prepared: dict[str, Any], query_vectors: np.ndarray, node_vectors: np.ndarray, mode: str
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, list[int]]:
    if mode == "full":
        return prepared, query_vectors, node_vectors, list(range(len(prepared["nodes"])))
    active_questions = prepared["questions"][:5]
    active_db_ids = {question["db_id"] for question in active_questions}
    node_indexes = [index for index, node in enumerate(prepared["nodes"]) if node.db_id in active_db_ids]
    subset = dict(prepared)
    subset["questions"] = active_questions
    subset["nodes"] = [prepared["nodes"][index] for index in node_indexes]
    if len(active_db_ids) != 1 or len(active_questions) != 5:
        raise RuntimeError("Smoke must cover exactly five questions from one database")
    return subset, query_vectors[:5], node_vectors[node_indexes], node_indexes


def build_r1_nodes(prepared: dict[str, Any], common: Any, tokenizer: Any) -> tuple[list[Any], dict[str, Any]]:
    """Rebuild the archived P1.6 serializer while omitting only value_description."""
    schemas = json.loads(common.SCHEMA_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    values_fields_present = 0
    column_values_removed = 0
    for schema in schemas:
        db_id = schema["db_id"]
        table_names = schema["table_names_original"]
        column_names = schema["column_names_original"]
        column_types = schema["column_types"]
        descriptions = common._read_description_rows(db_id)
        for table_index, table_name in enumerate(table_names):
            table_columns = [
                column_name for table_idx, column_name in column_names if table_idx == table_index
            ]
            records.append({
                "node_id": f"table:{db_id}:{table_index}",
                "db_id": db_id,
                "node_type": "table",
                "text": f"Table: {table_name}; columns: {', '.join(table_columns)}",
                "values_present": False,
                "values_value": "",
            })
            description_rows = descriptions.get(table_name.casefold(), {})
            for column_index, (table_idx, column_name) in enumerate(column_names):
                if table_idx != table_index:
                    continue
                description = description_rows.get(column_name, {})
                parts = [f"Column: {table_name}.{column_name}", f"type: {column_types[column_index]}"]
                for field, label in (("column_description", "description"), ("data_format", "format")):
                    value = description.get(field, "")
                    if value:
                        parts.append(f"{label}: {value}")
                values_value = description.get("value_description", "")
                values_fields_present += int(bool(values_value))
                column_values_removed += int(bool(values_value))
                records.append({
                    "node_id": f"column:{db_id}:{column_index}",
                    "db_id": db_id,
                    "node_type": "column",
                    "text": "; ".join(parts),
                    "values_present": bool(values_value),
                    "values_value": values_value,
                })

    records.sort(key=lambda node: node["node_type"] != "table")
    original_nodes = prepared["nodes"]
    if [record["node_id"] for record in records] != [node.node_id for node in original_nodes]:
        raise RuntimeError("R1 node IDs/order differ from the frozen R0 candidate universe")
    tokenizer_max = int(getattr(tokenizer, "model_max_length", MAX_LENGTH))
    if tokenizer_max > 10**7:
        tokenizer_max = MAX_LENGTH

    values_marker_count = 0
    nodes_r1: list[Any] = []
    for record, original in zip(records, original_nodes):
        if record["db_id"] != original.db_id or record["node_type"] != original.node_type:
            raise RuntimeError("R1 changed a frozen node's database or type")
        values_present = bool(record["values_present"])
        if values_present:
            values_marker_count += 1
            if original.node_type != "column" or record["text"] == original.text:
                raise RuntimeError("R1 did not remove a present Values field")
            expected_original = f"{record['text']}; values: {record['values_value']}"
            if original.text != expected_original:
                raise RuntimeError("R1 changed text beyond the registered trailing Values field")
        elif record["text"] != original.text:
            raise RuntimeError("R1 changed a node that had no Values field")
        token_count = len(tokenizer.encode(record["text"], add_special_tokens=False))
        if token_count > MAX_LENGTH or token_count > tokenizer_max:
            raise RuntimeError("R1 schema text exceeds the registered encoder sequence limit")
        nodes_r1.append(common.SchemaNode(
            node_id=record["node_id"],
            db_id=record["db_id"],
            node_type=record["node_type"],
            text=record["text"],
            token_count=token_count,
        ))
    return nodes_r1, {
        "nodes": len(records),
        "columns_with_values_removed": column_values_removed,
        "nodes_with_values_marker_verified": values_marker_count,
        "r0_schema_text_sequence_sha256": sha256_bytes(
            "\n".join(node.text for node in original_nodes).encode("utf-8")
        ),
        "r1_schema_text_sequence_sha256": sha256_bytes(
            "\n".join(node.text for node in nodes_r1).encode("utf-8")
        ),
        "text_differences_only_in_column_values": True,
    }


def load_cpu_encoder(model_path: Path) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(MAX_THREADS)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_path.resolve()),
        local_files_only=True,
        trust_remote_code=True,
        padding_side="left",
    )
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token_id is None:
        raise RuntimeError("Local Qwen3 tokenizer has no pad token or EOS fallback")
    model = AutoModel.from_pretrained(
        str(model_path.resolve()),
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model.to("cpu")
    model.eval()
    if int(model.config.hidden_size) != 1024:
        raise RuntimeError(f"Unexpected Qwen3 hidden size: {model.config.hidden_size}")
    return (tokenizer, model), torch


def current_rss_gib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(usage / (1024**2))


def check_budget(started_wall: float, started_cpu: float, torch: Any) -> None:
    wall = time.perf_counter() - started_wall
    cpu = time.process_time() - started_cpu
    rss = current_rss_gib()
    if wall > MAX_WALL_SECONDS:
        raise RuntimeError(f"Wall budget exceeded: {wall:.1f}s > {MAX_WALL_SECONDS}s")
    if cpu > MAX_CPU_SECONDS:
        raise RuntimeError(f"CPU budget exceeded: {cpu:.1f}s > {MAX_CPU_SECONDS}s")
    if rss > MAX_RSS_GIB:
        raise RuntimeError(f"RSS budget exceeded: {rss:.2f} GiB > {MAX_RSS_GIB} GiB")
    if torch.get_num_threads() > MAX_THREADS:
        raise RuntimeError(f"CPU thread budget exceeded: {torch.get_num_threads()} > {MAX_THREADS}")


def encode_texts(
    texts: list[str], tokenizer: Any, model: Any, torch: Any,
    label: str, started_wall: float, started_cpu: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    vectors: list[np.ndarray] = []
    input_tokens = 0
    padded_tokens = 0
    batch_count = 0
    encode_started = time.perf_counter()
    cpu_started = time.process_time()
    max_sequence_length = min(MAX_LENGTH, int(getattr(tokenizer, "model_max_length", MAX_LENGTH)))
    if max_sequence_length < 1:
        raise RuntimeError(f"Invalid local tokenizer sequence limit: {max_sequence_length}")
    input_lengths = [len(tokenizer.encode(text, add_special_tokens=True)) for text in texts]
    observed_max_input_length = max(input_lengths, default=0)
    if observed_max_input_length > max_sequence_length:
        raise RuntimeError(
            f"Input sequence length {observed_max_input_length} exceeds limit {max_sequence_length}; truncation is disabled"
        )
    print(json.dumps({"stage": "encode_start", "label": label, "texts": len(texts)}, ensure_ascii=False), flush=True)
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=False,
            return_tensors="pt",
        )
        if int(encoded["input_ids"].shape[1]) > max_sequence_length:
            raise RuntimeError("Tokenizer batch exceeded the validated sequence limit")
        attention_mask = encoded["attention_mask"]
        if not bool(torch.all(attention_mask[:, -1] == 1)):
            raise RuntimeError("Left-padded Qwen3 batch has a padded final token")
        input_tokens += int(attention_mask.sum().item())
        padded_tokens += int(encoded["input_ids"].numel())
        batch_count += 1
        with torch.inference_mode():
            outputs = model(**encoded)
            hidden = outputs.last_hidden_state[:, -1, :].to(dtype=torch.float32)
            batch_vectors = torch.nn.functional.normalize(hidden, p=2, dim=1)
        if batch_vectors.shape != (len(batch), 1024):
            raise RuntimeError(f"Unexpected CPU Qwen3 output shape: {tuple(batch_vectors.shape)}")
        if not bool(torch.isfinite(batch_vectors).all()):
            raise RuntimeError("Local CPU Qwen3 produced non-finite vectors")
        vectors.append(batch_vectors.cpu().numpy().astype(np.float32, copy=True))
        del outputs, hidden, batch_vectors, encoded, attention_mask
        check_budget(started_wall, started_cpu, torch)
        if batch_count % 10 == 0 or start + BATCH_SIZE >= len(texts):
            print(json.dumps({
                "stage": "encode_progress",
                "label": label,
                "batches": batch_count,
                "texts_done": min(start + BATCH_SIZE, len(texts)),
                "cpu_seconds": round(time.process_time() - started_cpu, 2),
                "rss_gib": round(current_rss_gib(), 3),
            }, ensure_ascii=False), flush=True)
    result = np.ascontiguousarray(np.concatenate(vectors, axis=0), dtype=np.float32)
    if result.shape != (len(texts), 1024):
        raise RuntimeError(f"Unexpected encoder result shape: {result.shape}")
    norms = np.linalg.norm(result, axis=1)
    if np.any(norms <= 1e-12) or not np.isfinite(norms).all():
        raise RuntimeError("Local CPU Qwen3 returned zero or invalid normalized vectors")
    details = {
        "texts": len(texts),
        "batches": batch_count,
        "nonpadding_input_tokens": input_tokens,
        "padded_compute_tokens": padded_tokens,
        "generated_output_tokens": 0,
        "wall_seconds": time.perf_counter() - encode_started,
        "cpu_seconds": time.process_time() - cpu_started,
        "max_input_length": observed_max_input_length,
        "l2_norm_min": float(norms.min()) if len(norms) else None,
        "l2_norm_median": float(np.median(norms)) if len(norms) else None,
        "l2_norm_p95": float(np.quantile(norms, 0.95)) if len(norms) else None,
    }
    print(json.dumps({"stage": "encode_done", "label": label, **details}, ensure_ascii=False), flush=True)
    return result, details


def variant_prepared(prepared: dict[str, Any], nodes: list[Any]) -> dict[str, Any]:
    value = dict(prepared)
    value["nodes"] = nodes
    return value


def metric_rows(rows: list[dict[str, Any]], non_saturated_dbs: set[str]) -> dict[str, Any]:
    eligible = [row for row in rows if row["column_eligible"]]
    fixed_subset = [row for row in eligible if row["db_id"] in non_saturated_dbs]

    def mean_column(source: list[dict[str, Any]], k: int) -> float | None:
        values = [row["methods"]["S0_cosine"]["column"]["recall"][str(k)] for row in source]
        return float(np.mean(values)) if values else None

    def mean_complete(source: list[dict[str, Any]], budget: int) -> float | None:
        values = [row["methods"]["S0_cosine"]["budgets"][str(budget)]["complete"] for row in source]
        return float(np.mean(values)) if values else None

    def mean_budget_recall(source: list[dict[str, Any]], budget: int) -> float | None:
        values = [row["methods"]["S0_cosine"]["budgets"][str(budget)]["recall"] for row in source]
        return float(np.mean(values)) if values else None

    def mean_budget_tokens(source: list[dict[str, Any]], budget: int) -> float | None:
        values = [row["methods"]["S0_cosine"]["budgets"][str(budget)]["tokens_used"] for row in source]
        return float(np.mean(values)) if values else None

    return {
        "denominators": {"all_column_eligible_questions": len(eligible), "fixed_non_saturated_questions": len(fixed_subset)},
        "all": {
            "column_r5_query_macro": mean_column(eligible, 5),
            "column_r10_query_macro": mean_column(eligible, 10),
            "column_r20_query_macro": mean_column(eligible, 20),
            "complete_query_macro": {str(b): mean_complete(eligible, b) for b in (512, 1024, 2048)},
            "budget_recall_query_macro": {str(b): mean_budget_recall(eligible, b) for b in (512, 1024, 2048)},
            "mean_tokens_used": {str(b): mean_budget_tokens(eligible, b) for b in (512, 1024, 2048)},
        },
        "fixed_non_saturated": {
            "column_r5_query_macro": mean_column(fixed_subset, 5),
            "column_r10_query_macro": mean_column(fixed_subset, 10),
            "column_r20_query_macro": mean_column(fixed_subset, 20),
            "complete_query_macro": {str(b): mean_complete(fixed_subset, b) for b in (512, 1024, 2048)},
            "budget_recall_query_macro": {str(b): mean_budget_recall(fixed_subset, b) for b in (512, 1024, 2048)},
            "mean_tokens_used": {str(b): mean_budget_tokens(fixed_subset, b) for b in (512, 1024, 2048)},
        },
    }


def per_question_metric_rows(rows: list[dict[str, Any]], metric: tuple[str, int]) -> dict[str, float]:
    field, value = metric
    result: dict[str, float] = {}
    for row in rows:
        if not row["column_eligible"]:
            continue
        if field == "column_recall":
            number = row["methods"]["S0_cosine"]["column"]["recall"][str(value)]
        else:
            number = row["methods"]["S0_cosine"]["budgets"][str(value)]["complete"]
        result[str(row["question_id"])] = float(number)
    return result


def delta_ci(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]],
    non_saturated_dbs: set[str], metric: tuple[str, int], subset: bool,
) -> dict[str, Any]:
    map_a = per_question_metric_rows(rows_a, metric)
    map_b = per_question_metric_rows(rows_b, metric)
    row_meta = {str(row["question_id"]): row for row in rows_a}
    if set(map_a) != set(map_b):
        raise RuntimeError("Paired conditions have different eligible question IDs")
    deltas_by_db: dict[str, list[float]] = {}
    deltas = []
    for question_id, a_value in map_a.items():
        metadata = row_meta[question_id]
        if subset and metadata["db_id"] not in non_saturated_dbs:
            continue
        delta = map_b[question_id] - a_value
        deltas.append(delta)
        deltas_by_db.setdefault(metadata["db_id"], []).append(delta)
    if not deltas or not deltas_by_db:
        raise RuntimeError("No eligible rows for paired metric comparison")
    db_ids = sorted(deltas_by_db)
    sums = np.asarray([sum(deltas_by_db[db]) for db in db_ids], dtype=np.float64)
    counts = np.asarray([len(deltas_by_db[db]) for db in db_ids], dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = np.empty(BOOTSTRAP_DRAWS, dtype=np.float64)
    for draw_index in range(BOOTSTRAP_DRAWS):
        sampled = rng.integers(0, len(db_ids), size=len(db_ids))
        draws[draw_index] = float(sums[sampled].sum() / counts[sampled].sum())
    return {
        "delta_query_macro": float(np.mean(deltas)),
        "delta_pp": float(np.mean(deltas) * 100.0),
        "database_cluster_bootstrap_95_ci": [float(value) for value in np.quantile(draws, [0.025, 0.975])],
        "database_cluster_bootstrap_95_ci_pp": [float(value * 100.0) for value in np.quantile(draws, [0.025, 0.975])],
        "database_clusters": len(db_ids),
        "questions": len(deltas),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def vector_repeat_diagnostics(first: np.ndarray, second: np.ndarray) -> dict[str, Any]:
    if first.shape != second.shape:
        raise RuntimeError("Same-text repeat vectors have different shapes")
    absolute = np.abs(first.astype(np.float64) - second.astype(np.float64))
    first_unit = first.astype(np.float64) / np.maximum(np.linalg.norm(first, axis=1, keepdims=True), 1e-12)
    second_unit = second.astype(np.float64) / np.maximum(np.linalg.norm(second, axis=1, keepdims=True), 1e-12)
    cosine = np.sum(first_unit * second_unit, axis=1)
    return {
        "vectors": int(first.shape[0]),
        "dimension": int(first.shape[1]),
        "bit_exact": bool(np.array_equal(first, second)),
        "max_abs_diff": float(absolute.max()) if absolute.size else 0.0,
        "mean_abs_diff": float(absolute.mean()) if absolute.size else 0.0,
        "p95_abs_diff": float(np.quantile(absolute, 0.95)) if absolute.size else 0.0,
        "cosine_similarity_min": float(cosine.min()) if cosine.size else None,
        "cosine_similarity_p05": float(np.quantile(cosine, 0.05)) if cosine.size else None,
        "cosine_similarity_median": float(np.median(cosine)) if cosine.size else None,
    }


def topk_change_counts(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows_a) != len(rows_b):
        raise RuntimeError("Top-K comparison row counts differ")
    counts = {str(k): {"set_changed_questions": 0, "order_changed_questions": 0, "questions": 0} for k in (5, 10, 20)}
    for first, second in zip(rows_a, rows_b):
        if first["question_id"] != second["question_id"]:
            raise RuntimeError("Top-K comparison question order differs")
        if not first["column_eligible"]:
            continue
        for k in (5, 10, 20):
            first_ids = first["methods"]["S0_cosine"]["column"]["topk_ids"][str(k)]
            second_ids = second["methods"]["S0_cosine"]["column"]["topk_ids"][str(k)]
            counts[str(k)]["questions"] += 1
            counts[str(k)]["set_changed_questions"] += int(set(first_ids) != set(second_ids))
            counts[str(k)]["order_changed_questions"] += int(first_ids != second_ids)
    return counts


def gold_only_fit(prepared: dict[str, Any], budgets: tuple[int, ...], fixed_non_saturated_dbs: set[str]) -> dict[str, Any]:
    token_by_id = {node.node_id: node.token_count for node in prepared["nodes"]}
    stats = {"all": {str(b): {"fit": 0, "questions": 0} for b in budgets}, "fixed_non_saturated": {str(b): {"fit": 0, "questions": 0} for b in budgets}}
    for question in prepared["questions"]:
        label = question["label"]
        if not label["column_eligible"]:
            continue
        gold_ids = set((*label["gold_table_ids"], *label["gold_column_ids"]))
        gold_tokens = sum(token_by_id[node_id] for node_id in gold_ids)
        groups = ["all"]
        if question["db_id"] in fixed_non_saturated_dbs:
            groups.append("fixed_non_saturated")
        for group in groups:
            for budget in budgets:
                stats[group][str(budget)]["questions"] += 1
                stats[group][str(budget)]["fit"] += int(gold_tokens <= budget)
    for values in stats.values():
        for row in values.values():
            row["rate"] = row["fit"] / row["questions"] if row["questions"] else None
    return stats


def token_length_summary(nodes: list[Any]) -> dict[str, Any]:
    columns = [node.token_count for node in nodes if node.node_type == "column"]
    tables = [node.token_count for node in nodes if node.node_type == "table"]
    def qstats(values: list[int]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "median": None, "p90": None, "sum": 0}
        return {"count": len(values), "median": float(np.median(values)), "p90": float(np.quantile(values, 0.90)), "sum": int(sum(values))}
    return {"column": qstats(columns), "table": qstats(tables), "all_nodes": qstats([node.token_count for node in nodes])}


def safe_variant_metrics(rows: list[dict[str, Any]], non_saturated_dbs: set[str]) -> dict[str, Any]:
    return metric_rows(rows, non_saturated_dbs)


def public_aggregate(
    args: argparse.Namespace, source: dict[str, Any], input_record: dict[str, Any],
    prepared: dict[str, Any], fixed_non_saturated_dbs: set[str],
    baseline_rows: list[dict[str, Any]], r0_rows: list[dict[str, Any]],
    r0_repeat_rows: list[dict[str, Any]], r1_rows: list[dict[str, Any]],
    r0_nodes: list[Any], r1_nodes: list[Any], r0_vector: np.ndarray,
    r0_repeat_vector: np.ndarray, r1_vector: np.ndarray,
    encoding: dict[str, Any], r1_audit: dict[str, Any],
    cache_summary: dict[str, Any],
) -> dict[str, Any]:
    r0_metrics = safe_variant_metrics(r0_rows, fixed_non_saturated_dbs)
    r0_repeat_metrics = safe_variant_metrics(r0_repeat_rows, fixed_non_saturated_dbs)
    r1_metrics = safe_variant_metrics(r1_rows, fixed_non_saturated_dbs)
    primary = delta_ci(r0_rows, r1_rows, fixed_non_saturated_dbs, ("column_recall", 10), subset=False)
    non_saturated_r10 = delta_ci(r0_rows, r1_rows, fixed_non_saturated_dbs, ("column_recall", 10), subset=True)
    complete_all = delta_ci(r0_rows, r1_rows, fixed_non_saturated_dbs, ("complete", 1024), subset=False)
    complete_subset = delta_ci(r0_rows, r1_rows, fixed_non_saturated_dbs, ("complete", 1024), subset=True)
    primary_pass = primary["delta_pp"] >= 1.0 and primary["database_cluster_bootstrap_95_ci_pp"][0] > 0
    guards_pass = non_saturated_r10["delta_pp"] >= -1.0 and complete_all["delta_pp"] >= -1.0 and complete_subset["delta_pp"] >= -1.0
    decision = "signal_for_independent_database_validation" if primary_pass and guards_pass else "no_go_stop_values_ablation"

    database_rows: dict[str, Any] = {}
    db_ids = sorted({row["db_id"] for row in prepared["questions"]})
    alias = {db_id: f"db_{index:02d}" for index, db_id in enumerate(db_ids, start=1)}
    per_database_deltas: dict[str, Any] = {}
    for db_id in db_ids:
        db_rows_a = [row for row in r0_rows if row["db_id"] == db_id and row["column_eligible"]]
        db_rows_b = [row for row in r1_rows if row["db_id"] == db_id and row["column_eligible"]]
        if not db_rows_a:
            continue
        def col_mean(source_rows: list[dict[str, Any]], k: int) -> float:
            return float(np.mean([row["methods"]["S0_cosine"]["column"]["recall"][str(k)] for row in source_rows]))
        def complete_mean(source_rows: list[dict[str, Any]], budget: int) -> float:
            return float(np.mean([row["methods"]["S0_cosine"]["budgets"][str(budget)]["complete"] for row in source_rows]))
        database_rows[alias[db_id]] = {
            "column_eligible_questions": len(db_rows_a),
            "fixed_non_saturated": db_id in fixed_non_saturated_dbs,
            "R0_column_r10": col_mean(db_rows_a, 10),
            "R1_column_r10": col_mean(db_rows_b, 10),
            "delta_column_r10_pp": (col_mean(db_rows_b, 10) - col_mean(db_rows_a, 10)) * 100.0,
            "R0_complete_1024": complete_mean(db_rows_a, 1024),
            "R1_complete_1024": complete_mean(db_rows_b, 1024),
            "delta_complete_1024_pp": (complete_mean(db_rows_b, 1024) - complete_mean(db_rows_a, 1024)) * 100.0,
        }
    for db_id in db_ids:
        if db_id not in fixed_non_saturated_dbs:
            continue
        a_rows = [row for row in r0_rows if row["db_id"] == db_id and row["column_eligible"]]
        b_rows = [row for row in r1_rows if row["db_id"] == db_id and row["column_eligible"]]
        if a_rows:
            per_database_deltas[alias[db_id]] = {
                "questions": len(a_rows),
                "delta_column_r10_pp": float(np.mean([
                    r1["methods"]["S0_cosine"]["column"]["recall"]["10"] - r0["methods"]["S0_cosine"]["column"]["recall"]["10"]
                    for r0, r1 in zip(a_rows, b_rows)
                ]) * 100.0),
            }

    saturation = {}
    for name, nodes in (("R0", prepared["nodes"]), ("R1", r1_nodes)):
        totals: dict[str, int] = {}
        for node in nodes:
            totals[node.db_id] = totals.get(node.db_id, 0) + int(node.token_count)
        saturation[name] = {
            "schema_tokens_total": {alias[db_id]: total for db_id, total in sorted(totals.items())},
            "databases_over_2048": sorted(alias[db_id] for db_id, total in totals.items() if total > 2048),
            "database_count_over_2048": sum(total > 2048 for total in totals.values()),
        }

    return {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "completed",
        "source_commit": source["published_commit"],
        "input_manifest_sha256": input_record["input_manifest_sha256"],
        "benchmark": {
            "questions": len(prepared["questions"]),
            "databases": len(db_ids),
            "column_eligible_questions": sum(row["column_eligible"] for row in prepared["questions"]),
            "exploratory": True,
        },
        "encoder": {
            "name": "Qwen3-Embedding-0.6B",
            "dimension": 1024,
            "local_backend": "Transformers AutoModel on CPU with left-padding last-token pooling",
            "weights_dtype": "bfloat16",
            "output_dtype": "float32 L2-normalized",
            "batch_size": BATCH_SIZE,
            "max_sequence_length": MAX_LENGTH,
            "query_vectors_shared_across_cpu_conditions": True,
            "local_input_token_counts": encoding,
        },
        "conditions": {
            "R0_frozen_P1_6_vllm_cache": safe_variant_metrics(baseline_rows, fixed_non_saturated_dbs),
            "R0_local_cpu_pass_1": r0_metrics,
            "R0_local_cpu_repeat": r0_repeat_metrics,
            "R1_local_cpu_without_values": r1_metrics,
        },
        "primary_R1_minus_R0_pass1": {
            "column_r10_all": primary,
            "column_r10_fixed_non_saturated": non_saturated_r10,
            "complete_1024_all": complete_all,
            "complete_1024_fixed_non_saturated": complete_subset,
            "primary_success_gate": primary_pass,
            "guardrails_pass": guards_pass,
            "decision": decision,
        },
        "repeat_encoding_control": {
            "R0_node_vector_repeat": vector_repeat_diagnostics(r0_vector, r0_repeat_vector),
            "column_topk_set_and_order_changes": topk_change_counts(r0_rows, r0_repeat_rows),
            "R0_repeat_minus_R0_pass1_column_r10_all_pp": (
                r0_repeat_metrics["all"]["column_r10_query_macro"] - r0_metrics["all"]["column_r10_query_macro"]
            ) * 100.0,
            "R0_repeat_minus_R0_pass1_complete_1024_all_pp": (
                r0_repeat_metrics["all"]["complete_query_macro"]["1024"] - r0_metrics["all"]["complete_query_macro"]["1024"]
            ) * 100.0,
        },
        "schema_text": {
            "R0": {"sha256": r1_audit["r0_schema_text_sequence_sha256"], "token_lengths": token_length_summary(r0_nodes)},
            "R1": {"sha256": r1_audit["r1_schema_text_sequence_sha256"], "token_lengths": token_length_summary(r1_nodes)},
            "r1_serialization_audit": r1_audit,
            "gold_only_fit": gold_only_fit(prepared, (512, 1024, 2048), fixed_non_saturated_dbs),
            "saturation_by_variant": saturation,
        },
        "per_database_anonymized": database_rows,
        "fixed_non_saturated_database_delta_column_r10_pp_anonymized": per_database_deltas,
        "frozen_cache_parity": cache_summary,
        "bootstrap": {"unit": "database cluster", "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "scope": "exploratory uncertainty interval; not cross-database generalization"},
        "privacy": {"question_ids_published": False, "questions_published": False, "gold_sql_published": False, "per_question_rows_published": False, "model_vectors_published": False},
    }


def write_private_rows(path: Path, rows: dict[str, list[dict[str, Any]]]) -> None:
    variant_names = list(rows)
    base = rows[variant_names[0]]
    with path.open("w", encoding="utf-8") as file:
        for index, row in enumerate(base):
            record = {
                "question_id": row["question_id"],
                "db_id": row["db_id"],
                "column_eligible": row["column_eligible"],
                "variants": {},
            }
            for variant in variant_names:
                variant_row = rows[variant][index]
                if variant_row["question_id"] != row["question_id"]:
                    raise RuntimeError("Per-question variant order mismatch")
                method = variant_row["methods"]["S0_cosine"]
                record["variants"][variant] = {
                    "column_topk_ids": method["column"]["topk_ids"] if method["column"] else {},
                    "column_hits": method["column"]["hits"] if method["column"] else {},
                    "budgets": method["budgets"],
                }
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def run() -> None:
    args = parse_args()
    expected_smoke = "p2b_values_smoke5_20261018_01"
    expected_full = "p2b_values_full1534_20261018_01"
    if args.mode == "smoke" and args.run_id != expected_smoke:
        raise RuntimeError(f"Unexpected smoke run ID: {args.run_id}")
    if args.mode == "full" and args.run_id != expected_full:
        raise RuntimeError(f"Unexpected Full run ID: {args.run_id}")
    if args.mode == "full":
        if args.smoke_dir is None:
            raise RuntimeError("Full P2b requires a completed smoke directory")
        smoke_summary_path = args.smoke_dir / "smoke_summary.json"
        smoke_start_path = args.smoke_dir / "run_start.json"
        if not smoke_summary_path.is_file() or not smoke_start_path.is_file():
            raise FileNotFoundError("Full P2b smoke evidence is incomplete")
        smoke_summary = json.loads(smoke_summary_path.read_text(encoding="utf-8"))
        smoke_start = json.loads(smoke_start_path.read_text(encoding="utf-8"))
        if smoke_summary.get("status") != "smoke_passed" or smoke_summary.get("run_id") != expected_smoke:
            raise RuntimeError("Full P2b is blocked because the registered smoke did not pass")
        if smoke_start.get("state") != "completed" or smoke_start.get("source", {}).get("published_commit") != args.expected_commit:
            raise RuntimeError("Full P2b smoke source/receipt does not match the registered code commit")
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse result directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    run_start: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "started",
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "resource_snapshot": resource_snapshot(),
        "resource_budget": {
            "cpu_seconds_max": MAX_CPU_SECONDS,
            "wall_seconds_max": MAX_WALL_SECONDS,
            "process_maxrss_gib": MAX_RSS_GIB,
            "max_cpu_threads": MAX_THREADS,
            "gpu_seconds": 0,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "torch": package_version("torch"),
            "transformers": package_version("transformers"),
            "tokenizers": package_version("tokenizers"),
            "model_path": str(args.model_path.resolve()),
            "local_only": True,
        },
        "source": {
            "repository": "https://github.com/bArtyom/gfm-rag",
            "branch": "main",
            "expected_commit": args.expected_commit,
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "protocol_sha256": sha256_file(PLAN_PATH),
            "config_sha256": sha256_file(CONFIG_PATH),
        },
        "api_calls": 0,
        "local_model_input_tokens": None,
        "local_model_generated_output_tokens": 0,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    try:
        print(json.dumps({"stage": "validate_frozen_inputs", "run_id": args.run_id}, ensure_ascii=False), flush=True)
        p1, p2a, source, input_record, prepared_full, q_cache, node_cache, frozen_private_rows = load_frozen_inputs(args)
        run_start["source"]["published_commit"] = source["published_commit"]
        run_start["source"]["worktree_status"] = source.get("worktree_status")
        run_start["frozen_input_manifest_sha256"] = input_record["input_manifest_sha256"]
        run_start["p1_6_cache_sha256"] = sha256_file(args.p1_6_run_dir.resolve() / "embedding_cache_private.npz")
        run_start["p1_6_private_rows_sha256"] = sha256_file(args.p1_6_run_dir.resolve() / "per_question_private.jsonl")

        prepared, q_cache_active, node_cache_active, node_indexes = select_active_inputs(
            prepared_full, q_cache, node_cache, args.mode
        )
        if args.mode == "full":
            if len(prepared["questions"]) != EXPECTED_COUNTS["questions"]:
                raise RuntimeError("Full did not select all 1,534 frozen questions")
        elif len(prepared["questions"]) != 5:
            raise RuntimeError("Smoke did not select exactly five questions")
        frozen_private_rows_active = frozen_private_rows[: len(prepared["questions"])]

        helper, common = p1.load_common(args.legacy_root.resolve(), args.dataset_root.resolve(), args.model_path.resolve())
        (tokenizer, model), torch = load_cpu_encoder(args.model_path)
        r1_nodes_full, r1_audit_full = build_r1_nodes(prepared_full, common, tokenizer)
        r1_nodes = [r1_nodes_full[index] for index in node_indexes]
        if len(r1_nodes) != len(prepared["nodes"]):
            raise RuntimeError("R1 node count differs from active R0 nodes")

        # The P1.6 cache is a frozen vLLM/GPU reference; all three new CPU arms
        # use the same locally encoded query vectors and only vary node text.
        query_prompts = [question["prompt"] for question in prepared["questions"]]
        q_cpu, q_details = encode_texts(
            query_prompts, tokenizer, model, torch, "query_shared_cpu", started_wall, started_cpu
        )
        r0_texts = [node.text for node in prepared["nodes"]]
        r1_texts = [node.text for node in r1_nodes]
        r0_vectors, r0_details = encode_texts(
            r0_texts, tokenizer, model, torch, "R0_cpu_pass1", started_wall, started_cpu
        )
        r0_repeat_vectors, r0_repeat_details = encode_texts(
            r0_texts, tokenizer, model, torch, "R0_cpu_repeat", started_wall, started_cpu
        )
        r1_vectors, r1_details = encode_texts(
            r1_texts, tokenizer, model, torch, "R1_cpu_without_values", started_wall, started_cpu
        )
        if next(model.parameters()).device.type != "cpu":
            raise RuntimeError("The local embedding model is not running on CPU")
        del model

        query_vectors_for_reference = q_cache_active
        cache_summary, cache_rows = p2a.evaluate(prepared, query_vectors_for_reference, node_cache_active)
        p2a.assert_s0_parity(cache_rows, frozen_private_rows_active)
        baseline_metrics = metric_rows(cache_rows, set(cache_summary["non_saturated_2048"]["databases"]))
        p2a_fixed_non_saturated = set(cache_summary["non_saturated_2048"]["databases"])
        r0_summary, r0_rows = p2a.evaluate(prepared, q_cpu, r0_vectors)
        r0_repeat_summary, r0_repeat_rows = p2a.evaluate(prepared, q_cpu, r0_repeat_vectors)
        r1_summary, r1_rows = p2a.evaluate(variant_prepared(prepared, r1_nodes), q_cpu, r1_vectors)
        if len(r0_rows) != len(r1_rows) or len(r0_rows) != len(prepared["questions"]):
            raise RuntimeError("Paired R0/R1 scorer row counts differ")

        public = public_aggregate(
            args, source, input_record, prepared, p2a_fixed_non_saturated,
            cache_rows, r0_rows, r0_repeat_rows, r1_rows,
            prepared["nodes"], r1_nodes, r0_vectors, r0_repeat_vectors, r1_vectors,
            {
                "query_shared_cpu": q_details,
                "R0_cpu_pass1": r0_details,
                "R0_cpu_repeat": r0_repeat_details,
                "R1_cpu_without_values": r1_details,
                "total_nonpadding_input_tokens": sum(item["nonpadding_input_tokens"] for item in (q_details, r0_details, r0_repeat_details, r1_details)),
                "total_padded_compute_tokens": sum(item["padded_compute_tokens"] for item in (q_details, r0_details, r0_repeat_details, r1_details)),
                "total_generated_output_tokens": 0,
            },
            r1_audit_full,
            {
                "s0_exact_p1_6_parity": True,
                "p1_6_cache_sha256": run_start["p1_6_cache_sha256"],
                "p1_6_input_manifest_sha256": run_start["frozen_input_manifest_sha256"],
                "p1_6_questions_replayed": len(cache_rows),
            },
        )

        private_cache_path = args.output_dir / "embedding_cache_cpu_private.npz"
        np.savez_compressed(
            private_cache_path,
            query_vectors=q_cpu,
            r0_node_vectors=r0_vectors,
            r0_repeat_node_vectors=r0_repeat_vectors,
            r1_node_vectors=r1_vectors,
        )
        private_rows_path = args.output_dir / "per_question_private.jsonl"
        write_private_rows(private_rows_path, {
            "R0_frozen_P1_6_vllm_cache": cache_rows,
            "R0_local_cpu_pass1": r0_rows,
            "R0_local_cpu_repeat": r0_repeat_rows,
            "R1_local_cpu_without_values": r1_rows,
        })
        aggregate_path = args.output_dir / "aggregate_summary.json"
        write_json(aggregate_path, public)

        run_start.update({
            "state": "completed",
            "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_elapsed_wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds_process": time.process_time() - started_cpu,
            "process_maxrss_gib": current_rss_gib(),
            "selected_questions": len(prepared["questions"]),
            "selected_nodes": len(prepared["nodes"]),
            "frozen_non_saturated_db_aliases": [
                f"db_{index:02d}"
                for index, db_id in enumerate(sorted({row["db_id"] for row in prepared["questions"]}), start=1)
                if db_id in p2a_fixed_non_saturated
            ],
            "r1_text_audit": r1_audit_full,
            "private_embedding_cache_sha256": sha256_file(private_cache_path),
            "private_per_question_sha256": sha256_file(private_rows_path),
            "aggregate_summary_sha256": sha256_file(aggregate_path),
            "local_model_input_tokens": public["encoder"]["local_input_token_counts"]["total_nonpadding_input_tokens"],
            "local_model_generated_output_tokens": 0,
            "api_calls": 0,
        })
        write_json(args.output_dir / "run_start.json", run_start)
        if args.mode == "smoke":
            write_json(args.output_dir / "smoke_summary.json", {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "status": "smoke_passed",
                "questions": len(prepared["questions"]),
                "databases": len({row["db_id"] for row in prepared["questions"]}),
                "nodes": len(prepared["nodes"]),
                "frozen_cache_s0_parity": True,
                "r0_r1_text_audit": r1_audit_full,
                "primary_metric_smoke_only": public["primary_R1_minus_R0_pass1"]["column_r10_all"],
                "not_formal_evidence": True,
            })
        print(json.dumps({
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "completed",
            "decision": public["primary_R1_minus_R0_pass1"]["decision"],
            "output_dir": str(args.output_dir.resolve()),
            "wall_seconds": run_start["finished_elapsed_wall_seconds"],
            "cpu_seconds": run_start["cpu_seconds_process"],
            "rss_gib": run_start["process_maxrss_gib"],
            "local_model_input_tokens": run_start["local_model_input_tokens"],
        }, ensure_ascii=False), flush=True)
    except Exception as error:
        run_start.update({
            "state": "failed",
            "failed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_elapsed_wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds_process": time.process_time() - started_cpu,
            "process_maxrss_gib": current_rss_gib(),
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        write_json(args.output_dir / "run_start.json", run_start)
        write_json(args.output_dir / "failure.json", {
            "run_id": args.run_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        raise


if __name__ == "__main__":
    run()
