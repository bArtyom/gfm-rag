#!/usr/bin/env python3
"""Replay the preregistered P2c retrieval/context 2x2 on frozen CPU vectors."""

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
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_THREADS = 8
MAX_CPU_SECONDS = 1800
MAX_RSS_GIB = 16
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261020
EXPERIMENT_ID = "p2c_dual_view_20261018_01"
EXPECTED_COUNTS = {
    "questions": 1534,
    "databases": 11,
    "nodes": 873,
    "tables": 75,
    "columns": 798,
    "column_eligible": 1460,
}
ARM_FACTORS = {
    "V00": ("R0", "R0"),
    "V01": ("R0", "R1"),
    "V10": ("R1", "R0"),
    "V11": ("R1", "R1"),
}
P2B_ROW_VARIANTS = {
    "V00": "R0_local_cpu_pass1",
    "V11": "R1_local_cpu_without_values",
}
P2B_AGGREGATE_VARIANTS = {
    "V00": "R0_local_cpu_pass_1",
    "V11": "R1_local_cpu_without_values",
}
RECOVERY_PREDECESSOR_COMMIT = "91fc6fef002edce8f68d78ca4050c4f62688107c"

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_6_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_6_rebaseline.py"
P2A_RUNNER = REPO_ROOT / "scripts/text2sql/run_p2a_similarity.py"
P2B_RUNNER = REPO_ROOT / "scripts/text2sql/run_p2b_values_ablation.py"
PLAN_PATH = REPO_ROOT / "docs/research/text2sql/plans/p2c_dual_view_retrieval_context_factorial_20261018.md"
CONFIG_PATH = REPO_ROOT / "docs/research/text2sql/reports/p2c_dual_view_20261018_01/experiment_config.json"
P2B_PUBLIC_AGGREGATE = REPO_ROOT / "docs/research/text2sql/reports/p2b_values_ablation_20261018_01/aggregate_summary.json"
P2B_CONFIG_PATH = REPO_ROOT / "docs/research/text2sql/reports/p2b_values_ablation_20261018_01/experiment_config.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256_bytes(payload.encode("utf-8"))


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
        "cpu_limit_environment": {name: os.environ.get(name) for name in (
            "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"
        )},
        "disk": command_output(["df", "-h", str(REPO_ROOT)]),
    }


def current_rss_gib() -> float:
    pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE") / (1024**3)


def peak_rss_gib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(value / (1024**2))


def check_budget(started_cpu: float) -> None:
    cpu_seconds = time.process_time() - started_cpu
    rss_gib = max(current_rss_gib(), peak_rss_gib())
    if cpu_seconds > MAX_CPU_SECONDS:
        raise RuntimeError(f"CPU budget exceeded: {cpu_seconds:.1f}s > {MAX_CPU_SECONDS}s")
    if rss_gib > MAX_RSS_GIB:
        raise RuntimeError(f"RSS budget exceeded: {rss_gib:.2f} GiB > {MAX_RSS_GIB} GiB")
    if any(os.environ.get(name) != str(MAX_THREADS) for name in (
        "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"
    )):
        raise RuntimeError("CPU thread limit environment changed during the run")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load experiment helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preflight", "smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-dir", type=Path)
    parser.add_argument("--smoke-dir", type=Path)
    parser.add_argument("--p1-6-run-dir", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--p1-5-run-dir", type=Path, required=True)
    parser.add_argument("--p2b-run-dir", type=Path, required=True)
    return parser.parse_args()


def select_active_inputs(
    prepared: dict[str, Any], cache: dict[str, np.ndarray], mode: str
) -> tuple[dict[str, Any], dict[str, np.ndarray], list[int]]:
    if mode == "full" or mode == "preflight":
        return prepared, cache, list(range(len(prepared["nodes"])))
    questions = prepared["questions"][:5]
    active_dbs = {question["db_id"] for question in questions}
    indexes = [index for index, node in enumerate(prepared["nodes"]) if node.db_id in active_dbs]
    subset = dict(prepared)
    subset["questions"] = questions
    subset["nodes"] = [prepared["nodes"][index] for index in indexes]
    active_cache = {
        "query_vectors": cache["query_vectors"][:5],
        "r0_node_vectors": cache["r0_node_vectors"][indexes],
        "r0_repeat_node_vectors": cache["r0_repeat_node_vectors"][indexes],
        "r1_node_vectors": cache["r1_node_vectors"][indexes],
    }
    if len(questions) != 5 or len(active_dbs) != 1:
        raise RuntimeError("Registered smoke must contain exactly five questions from one database")
    return subset, active_cache, indexes


def assert_context_only_ranking_invariant(rows_left: list[dict[str, Any]], rows_right: list[dict[str, Any]]) -> None:
    if len(rows_left) != len(rows_right):
        raise RuntimeError("Context-only ranking comparison has different question counts")
    for row_left, row_right in zip(rows_left, rows_right):
        if row_left["question_id"] != row_right["question_id"]:
            raise RuntimeError("Context-only ranking comparison question order differs")
        for kind in ("table", "column"):
            left = row_left["methods"]["S0_cosine"][kind]
            right = row_right["methods"]["S0_cosine"][kind]
            if left is None or right is None:
                if left != right:
                    raise RuntimeError(f"Context-only {kind} eligibility differs")
                continue
            if left["topk_ids"] != right["topk_ids"]:
                raise RuntimeError(f"Context-only change altered {kind} Top-K IDs")


def assert_p2b_replay(
    p2b_rows: list[dict[str, Any]], p2c_rows: list[dict[str, Any]], p2b_variant: str
) -> None:
    if len(p2b_rows) != len(p2c_rows):
        raise RuntimeError("P2b budget replay has different question counts")
    for baseline, replay in zip(p2b_rows, p2c_rows):
        if (baseline["question_id"], baseline["db_id"], baseline["column_eligible"]) != (
            replay["question_id"], replay["db_id"], replay["column_eligible"]
        ):
            raise RuntimeError("P2b replay question order/metadata differs")
        saved = baseline["variants"][p2b_variant]
        current_method = replay["methods"]["S0_cosine"]
        current_column = current_method["column"]
        current_topk = current_column["topk_ids"] if current_column is not None else {}
        if current_topk != saved["column_topk_ids"]:
            raise RuntimeError("P2b Column Top-K replay differs")
        if current_method["budgets"] != saved["budgets"]:
            raise RuntimeError("P2b budget replay differs")


def assert_p2b_aggregate_replay(
    p2b_aggregate: dict[str, Any], metrics_by_arm: dict[str, dict[str, Any]]
) -> None:
    field_map = {
        "column_r5_query_macro": ("column_r5_query_macro", None),
        "column_r10_query_macro": ("column_r10_query_macro", None),
        "column_r20_query_macro": ("column_r20_query_macro", None),
        "complete_query_macro": ("complete_query_macro", "complete"),
        "budget_recall_query_macro": ("budget_recall_query_macro", "recall"),
        "mean_tokens_used": ("mean_tokens_used", "tokens_used"),
    }
    for arm, baseline_key in P2B_AGGREGATE_VARIANTS.items():
        baseline = p2b_aggregate["conditions"][baseline_key]
        replay = metrics_by_arm[arm]
        for group in ("all", "fixed_non_saturated"):
            for field, (metric_key, _) in field_map.items():
                if field in ("complete_query_macro", "budget_recall_query_macro", "mean_tokens_used"):
                    for budget in ("512", "1024", "2048"):
                        expected = baseline[group][field][budget]
                        actual = replay[group][metric_key][budget]
                        if not np.isclose(expected, actual, rtol=0.0, atol=1e-14):
                            raise RuntimeError(f"P2b aggregate replay differs: {arm}/{group}/{field}/{budget}")
                else:
                    expected = baseline[group][field]
                    actual = replay[group][metric_key]
                    if not np.isclose(expected, actual, rtol=0.0, atol=1e-14):
                        raise RuntimeError(f"P2b aggregate replay differs: {arm}/{group}/{field}")


def factorial_contrasts(values: dict[str, float]) -> dict[str, float]:
    required = set(ARM_FACTORS)
    if set(values) != required:
        raise ValueError(f"Factorial contrasts require exactly {sorted(required)}")
    return {
        "context_effect_at_R0": float(values["V01"] - values["V00"]),
        "ranking_effect_at_R0": float(values["V10"] - values["V00"]),
        "context_effect_at_R1": float(values["V11"] - values["V10"]),
        "interaction": float((values["V11"] - values["V10"]) - (values["V01"] - values["V00"])),
    }


def p2b_registered_aggregate_sha256(p2c_config: dict[str, Any], p2b_config: dict[str, Any]) -> str:
    if p2c_config.get("experiment_id") != EXPERIMENT_ID:
        raise RuntimeError("Unexpected P2c configuration while validating P2b inputs")
    if p2b_config.get("experiment_id") != "p2b_values_ablation_20261018_01":
        raise RuntimeError("Unexpected P2b completed experiment configuration")
    try:
        return str(p2b_config["final_result"]["aggregate_summary_sha256"])
    except (KeyError, TypeError) as error:
        raise RuntimeError("Completed P2b configuration has no aggregate checksum") from error


def fixed_non_saturated_dbs(nodes: list[Any]) -> set[str]:
    token_totals: dict[str, int] = defaultdict(int)
    for node in nodes:
        token_totals[node.db_id] += int(node.token_count)
    return {db_id for db_id, total in token_totals.items() if total > 2048}


def token_sequence_hash(nodes: list[Any]) -> str:
    return sha256_bytes("\n".join(node.text for node in nodes).encode("utf-8"))


def load_registered_inputs(args: argparse.Namespace) -> dict[str, Any]:
    p1 = load_module(P1_6_RUNNER, "p1_6_for_p2c_dual_view")
    p2a = load_module(P2A_RUNNER, "p2a_for_p2c_dual_view")
    p2b = load_module(P2B_RUNNER, "p2b_for_p2c_dual_view")
    p2a.p1_module = p1
    source = p1.assert_committed_source(args.expected_commit)
    if source.get("worktree_status") != "clean" or source.get("branch") != "main":
        raise RuntimeError("P2c requires a clean published main checkout")
    if not PLAN_PATH.is_file() or not CONFIG_PATH.is_file() or not P2B_CONFIG_PATH.is_file() or not P2B_PUBLIC_AGGREGATE.is_file():
        raise FileNotFoundError("A registered P2c/P2b protocol or public aggregate is missing")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    p2b_config = json.loads(P2B_CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("experiment_id") != EXPERIMENT_ID or config.get("status") not in {
        "preregistered_not_run", "recovery_preregistered_not_run"
    }:
        raise RuntimeError("P2c experiment config is not in its preregistered state")

    validation_args = argparse.Namespace(
        p1_6_run_dir=args.p1_6_run_dir,
        legacy_root=args.legacy_root,
        dataset_root=args.dataset_root,
        model_path=args.model_path,
        previous_run_dir=args.previous_run_dir,
        p1_5_run_dir=args.p1_5_run_dir,
    )
    input_record, prepared, _, _ = p2a.validate_p1_6_inputs(validation_args, p1)
    if input_record["input_record"].get("counts") != EXPECTED_COUNTS:
        raise RuntimeError("Frozen BIRD input counts differ from the P2c registration")

    p2b_run_dir = args.p2b_run_dir.resolve()
    p2b_start_path = p2b_run_dir / "run_start.json"
    p2b_aggregate_path = p2b_run_dir / "aggregate_summary.json"
    p2b_cache_path = p2b_run_dir / "embedding_cache_cpu_private.npz"
    p2b_rows_path = p2b_run_dir / "per_question_private.jsonl"
    required_paths = (p2b_start_path, p2b_aggregate_path, p2b_cache_path, p2b_rows_path)
    if any(not path.is_file() for path in required_paths):
        raise FileNotFoundError("The registered P2b Full private cache/rows/receipt are incomplete")
    p2b_start = json.loads(p2b_start_path.read_text(encoding="utf-8"))
    p2b_aggregate = json.loads(p2b_aggregate_path.read_text(encoding="utf-8"))
    if p2b_start.get("run_id") != "p2b_values_full1534_20261018_01" or p2b_start.get("state") != "completed":
        raise RuntimeError("P2b Full cache is not the registered completed run")
    if p2b_start.get("source", {}).get("published_commit") != "7cb681000f4da87aeeb71098ff383aaae6b45660":
        raise RuntimeError("P2b Full cache came from an unexpected source commit")
    if p2b_aggregate.get("source_commit") != p2b_start["source"]["published_commit"]:
        raise RuntimeError("P2b aggregate source commit differs from its receipt")
    if p2b_start.get("frozen_input_manifest_sha256") != input_record["input_manifest_sha256"]:
        raise RuntimeError("P2b and current frozen input manifest hashes differ")
    p1_6_cache_path = args.p1_6_run_dir.resolve() / "embedding_cache_private.npz"
    p1_6_rows_path = args.p1_6_run_dir.resolve() / "per_question_private.jsonl"
    if sha256_file(p1_6_cache_path) != p2b_start.get("p1_6_cache_sha256"):
        raise RuntimeError("P2b recorded P1.6 cache hash differs")
    if sha256_file(p1_6_rows_path) != p2b_start.get("p1_6_private_rows_sha256"):
        raise RuntimeError("P2b recorded P1.6 row hash differs")
    p2b_cache_sha = sha256_file(p2b_cache_path)
    if p2b_cache_sha != p2b_start.get("private_embedding_cache_sha256"):
        raise RuntimeError("P2b private CPU vector cache hash differs")
    p2b_rows_sha = sha256_file(p2b_rows_path)
    if p2b_rows_sha != p2b_start.get("private_per_question_sha256"):
        raise RuntimeError("P2b private per-question row hash differs")
    p2b_aggregate_sha = sha256_file(p2b_aggregate_path)
    if p2b_aggregate_sha != p2b_start.get("aggregate_summary_sha256"):
        raise RuntimeError("P2b private Full aggregate checksum differs from the receipt")
    if p2b_aggregate_sha != sha256_file(P2B_PUBLIC_AGGREGATE):
        raise RuntimeError("P2b local aggregate differs from the published report aggregate")
    if p2b_aggregate_sha != p2b_registered_aggregate_sha256(config, p2b_config):
        raise RuntimeError("P2b aggregate checksum differs from the archived experiment config")

    p2b_rows: list[dict[str, Any]] = []
    with p2b_rows_path.open("r", encoding="utf-8") as file:
        for line in file:
            p2b_rows.append(json.loads(line))
    if len(p2b_rows) != EXPECTED_COUNTS["questions"]:
        raise RuntimeError("P2b private row count differs from the frozen 1,534-question denominator")
    for index, row in enumerate(p2b_rows):
        question = prepared["questions"][index]
        if row["question_id"] != question["question_id"] or row["db_id"] != question["db_id"]:
            raise RuntimeError("P2b private question order differs from the frozen input")

    expected_keys = {"query_vectors", "r0_node_vectors", "r0_repeat_node_vectors", "r1_node_vectors"}
    with np.load(p2b_cache_path, allow_pickle=False) as archive:
        if set(archive.files) != expected_keys:
            raise RuntimeError(f"Unexpected P2b CPU cache keys: {sorted(archive.files)}")
        cache = {key: np.ascontiguousarray(archive[key], dtype=np.float32) for key in expected_keys}
    expected_shapes = {
        "query_vectors": (1534, 1024),
        "r0_node_vectors": (873, 1024),
        "r0_repeat_node_vectors": (873, 1024),
        "r1_node_vectors": (873, 1024),
    }
    for key, expected_shape in expected_shapes.items():
        if cache[key].shape != expected_shape or not np.isfinite(cache[key]).all():
            raise RuntimeError(f"P2b cache {key} has invalid shape or non-finite values")

    _, common = p1.load_common(args.legacy_root.resolve(), args.dataset_root.resolve(), args.model_path.resolve())
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model_path.resolve()), local_files_only=True, trust_remote_code=True
    )
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    r1_nodes, r1_audit = p2b.build_r1_nodes(prepared, common, tokenizer)
    if token_sequence_hash(prepared["nodes"]) != p2b_start["r1_text_audit"]["r0_schema_text_sequence_sha256"]:
        raise RuntimeError("Rebuilt R0 text sequence differs from the P2b cache input")
    if r1_audit != p2b_start.get("r1_text_audit"):
        raise RuntimeError("Rebuilt R1 text/order audit differs from the P2b receipt")
    if p2b_aggregate["schema_text"]["R0"]["sha256"] != r1_audit["r0_schema_text_sequence_sha256"]:
        raise RuntimeError("P2b public R0 text hash differs")
    if p2b_aggregate["schema_text"]["R1"]["sha256"] != r1_audit["r1_schema_text_sequence_sha256"]:
        raise RuntimeError("P2b public R1 text hash differs")
    if sum(node.token_count for node in prepared["nodes"]) != 27506:
        raise RuntimeError("R0 context token total differs from the registered 27,506 tokens")
    if sum(node.token_count for node in r1_nodes) != 20071:
        raise RuntimeError("R1 context token total differs from the registered 20,071 tokens")

    fixed_dbs = fixed_non_saturated_dbs(prepared["nodes"])
    fixed_questions = sum(
        question["label"]["column_eligible"] and question["db_id"] in fixed_dbs
        for question in prepared["questions"]
    )
    if len(fixed_dbs) != 5 or fixed_questions != 706:
        raise RuntimeError("Frozen R0 non-saturated subset differs from 5 databases / 706 questions")
    alias = {db_id: f"db_{index:02d}" for index, db_id in enumerate(sorted({row["db_id"] for row in prepared["questions"]}), 1)}
    expected_aliases = [alias[db_id] for db_id in sorted(fixed_dbs)]
    if expected_aliases != p2b_start.get("frozen_non_saturated_db_aliases"):
        raise RuntimeError("Frozen non-saturated databases differ from the P2b registration")

    return {
        "p1": p1,
        "p2a": p2a,
        "p2b": p2b,
        "source": source,
        "input_record": input_record,
        "prepared_full": prepared,
        "r1_nodes_full": r1_nodes,
        "cache_full": cache,
        "p2b_rows": p2b_rows,
        "p2b_start": p2b_start,
        "p2b_aggregate": p2b_aggregate,
        "p2b_audit": r1_audit,
        "p2b_hashes": {
            "cpu_cache_sha256": p2b_cache_sha,
            "private_rows_sha256": p2b_rows_sha,
            "public_aggregate_sha256": p2b_aggregate_sha,
            "p1_6_cache_sha256": p2b_start["p1_6_cache_sha256"],
            "input_manifest_sha256": input_record["input_manifest_sha256"],
        },
        "fixed_dbs": fixed_dbs,
        "fixed_questions": fixed_questions,
    }


def score_matrix_digests(prepared: dict[str, Any], p1: Any, query_vectors: np.ndarray, node_vectors: np.ndarray) -> dict[str, Any]:
    query_unit, _ = p1.normalized_vectors(query_vectors)
    node_unit, _ = p1.normalized_vectors(node_vectors)
    node_indexes_by_db: dict[str, list[int]] = defaultdict(list)
    for index, node in enumerate(prepared["nodes"]):
        node_indexes_by_db[node.db_id].append(index)
    per_question: list[dict[str, Any]] = []
    for query_index, question in enumerate(prepared["questions"]):
        indexes = node_indexes_by_db[question["db_id"]]
        scores = np.asarray(query_unit[query_index] @ node_unit[indexes].T, dtype=np.float32)
        if not np.isfinite(scores).all():
            raise RuntimeError("Non-finite cosine score in P2c score digest")
        node_ids = [prepared["nodes"][index].node_id for index in indexes]
        payload = json.dumps(node_ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + scores.tobytes()
        per_question.append({"question_id": question["question_id"], "digest": sha256_bytes(payload)})
    return {
        "questions": len(per_question),
        "digest": json_digest(per_question),
        "private_question_digests": per_question,
    }


def topk_rows_digest(rows: list[dict[str, Any]]) -> str:
    projection = []
    for row in rows:
        methods = row["methods"]["S0_cosine"]
        projection.append({
            "question_id": row["question_id"],
            "table": methods["table"]["topk_ids"],
            "column": methods["column"]["topk_ids"] if methods["column"] else {},
        })
    return json_digest(projection)


def metric_value(row: dict[str, Any], metric: tuple[str, str, str]) -> float | None:
    area, key, field = metric
    result = row["methods"]["S0_cosine"][area]
    if result is None:
        return None
    if area == "budgets":
        result = result[key]
    value = result[field]
    if field in ("recall", "precision") and area != "budgets":
        value = result[field][key]
    return float(value) if value is not None else None


def summarize_rows(rows: list[dict[str, Any]], fixed_dbs: set[str]) -> dict[str, Any]:
    groups = {
        "all": rows,
        "fixed_non_saturated": [row for row in rows if row["db_id"] in fixed_dbs],
    }
    result: dict[str, Any] = {}
    for group, group_rows in groups.items():
        table_rows = group_rows
        column_rows = [row for row in group_rows if row["column_eligible"]]

        def mean_metric(source: list[dict[str, Any]], metric: tuple[str, str, str]) -> float | None:
            values = [metric_value(row, metric) for row in source]
            present = [value for value in values if value is not None]
            return float(np.mean(np.asarray(present, dtype=np.float64))) if present else None

        result[group] = {
            "denominators": {
                "table_questions": len(table_rows),
                "column_eligible_questions": len(column_rows),
            },
            "table_recall_query_macro": {
                str(k): mean_metric(table_rows, ("table", str(k), "recall")) for k in (5, 10)
            },
            "column_recall_query_macro": {
                str(k): mean_metric(column_rows, ("column", str(k), "recall")) for k in (5, 10, 20)
            },
            "column_precision_query_macro": {
                str(k): mean_metric(column_rows, ("column", str(k), "precision")) for k in (5, 10, 20)
            },
            "budgets": {
                str(budget): {
                    "complete_query_macro": mean_metric(column_rows, ("budgets", str(budget), "complete")),
                    "gold_schema_recall_query_macro": mean_metric(column_rows, ("budgets", str(budget), "recall")),
                    "mean_returned_tokens": mean_metric(column_rows, ("budgets", str(budget), "tokens_used")),
                    "mean_returned_elements": mean_metric(column_rows, ("budgets", str(budget), "returned_elements")),
                }
                for budget in (512, 1024, 2048)
            },
        }
    return result


def paired_delta(
    rows_base: list[dict[str, Any]], rows_candidate: list[dict[str, Any]], metric: tuple[str, str, str],
    fixed_dbs: set[str], subset: bool,
) -> dict[str, Any]:
    if len(rows_base) != len(rows_candidate):
        raise RuntimeError("Paired P2c arms have different row counts")
    by_db: dict[str, list[float]] = defaultdict(list)
    for base, candidate in zip(rows_base, rows_candidate):
        if base["question_id"] != candidate["question_id"] or base["db_id"] != candidate["db_id"]:
            raise RuntimeError("Paired P2c arms have different question order")
        if subset and base["db_id"] not in fixed_dbs:
            continue
        base_value = metric_value(base, metric)
        candidate_value = metric_value(candidate, metric)
        if base_value is None or candidate_value is None:
            if base_value != candidate_value:
                raise RuntimeError("Paired P2c metric eligibility differs")
            continue
        by_db[base["db_id"]].append(candidate_value - base_value)
    db_ids = sorted(by_db)
    if not db_ids:
        raise RuntimeError("No rows available for P2c paired contrast")
    values = [value for db in db_ids for value in by_db[db]]
    sums = np.asarray([sum(by_db[db]) for db in db_ids], dtype=np.float64)
    counts = np.asarray([len(by_db[db]) for db in db_ids], dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = np.empty(BOOTSTRAP_DRAWS, dtype=np.float64)
    for index in range(BOOTSTRAP_DRAWS):
        sampled = rng.integers(0, len(db_ids), size=len(db_ids))
        draws[index] = float(sums[sampled].sum() / counts[sampled].sum())
    interval = np.quantile(draws, [0.025, 0.975])
    delta = float(np.mean(np.asarray(values, dtype=np.float64)))
    return {
        "delta_query_macro": delta,
        "delta_pp": delta * 100.0,
        "database_cluster_bootstrap_95_ci": [float(interval[0]), float(interval[1])],
        "database_cluster_bootstrap_95_ci_pp": [float(interval[0] * 100.0), float(interval[1] * 100.0)],
        "databases": len(db_ids),
        "questions": len(values),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def rescue_damage(
    rows_base: list[dict[str, Any]], rows_candidate: list[dict[str, Any]], fixed_dbs: set[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for subset_name, allowed in (("all", None), ("fixed_non_saturated", fixed_dbs)):
        eligible = [
            (base, candidate)
            for base, candidate in zip(rows_base, rows_candidate)
            if base["column_eligible"] and (allowed is None or base["db_id"] in allowed)
        ]
        complete = {"rescued": 0, "damaged": 0, "unchanged": 0, "questions": len(eligible)}
        r10 = {"improved": 0, "regressed": 0, "unchanged": 0, "questions": len(eligible)}
        for base, candidate in eligible:
            left = int(base["methods"]["S0_cosine"]["budgets"]["1024"]["complete"])
            right = int(candidate["methods"]["S0_cosine"]["budgets"]["1024"]["complete"])
            complete["rescued"] += int(left == 0 and right == 1)
            complete["damaged"] += int(left == 1 and right == 0)
            complete["unchanged"] += int(left == right)
            recall_left = float(base["methods"]["S0_cosine"]["column"]["recall"]["10"])
            recall_right = float(candidate["methods"]["S0_cosine"]["column"]["recall"]["10"])
            r10["improved"] += int(recall_right > recall_left)
            r10["regressed"] += int(recall_right < recall_left)
            r10["unchanged"] += int(recall_right == recall_left)
        result[subset_name] = {"complete_1024": complete, "column_recall_10": r10}
    return result


def gold_only_fit(prepared: dict[str, Any], nodes: list[Any], fixed_dbs: set[str]) -> dict[str, Any]:
    token_by_id = {node.node_id: int(node.token_count) for node in nodes}
    output = {
        group: {str(budget): {"fit": 0, "questions": 0} for budget in (512, 1024, 2048)}
        for group in ("all", "fixed_non_saturated")
    }
    for question in prepared["questions"]:
        if not question["label"]["column_eligible"]:
            continue
        ids = set((*question["label"]["gold_table_ids"], *question["label"]["gold_column_ids"]))
        gold_tokens = sum(token_by_id[node_id] for node_id in ids)
        groups = ["all"] + (["fixed_non_saturated"] if question["db_id"] in fixed_dbs else [])
        for group in groups:
            for budget in (512, 1024, 2048):
                target = output[group][str(budget)]
                target["questions"] += 1
                target["fit"] += int(gold_tokens <= budget)
    for group in output.values():
        for row in group.values():
            row["rate"] = row["fit"] / row["questions"] if row["questions"] else None
    return output


def value_context_coverage(rows_by_arm: dict[str, list[dict[str, Any]]], r0_nodes: list[Any], r1_nodes: list[Any]) -> dict[str, Any]:
    r1_by_id = {node.node_id: node for node in r1_nodes}
    r1_ids = {
        node.node_id
        for node in r0_nodes
        if node.node_type == "column" and node.text != r1_by_id[node.node_id].text
    }
    token_reduction = sum(
        int(r0.token_count - r1.token_count)
        for r0, r1 in zip(r0_nodes, r1_nodes)
        if r0.node_type == "column" and r0.node_id in r1_ids
    )
    result: dict[str, Any] = {"candidate_columns_with_values_removed": len(r1_ids), "removed_text_token_reduction": token_reduction, "by_arm": {}}
    for arm, rows in rows_by_arm.items():
        selected: dict[str, dict[str, int]] = {}
        for budget in (512, 1024, 2048):
            counts = []
            for row in rows:
                if not row["column_eligible"]:
                    continue
                ids = row["methods"]["S0_cosine"]["budgets"][str(budget)]["selected_ids"]
                counts.append(sum(node_id in r1_ids for node_id in ids))
            selected[str(budget)] = {
                "mean_values_bearing_columns_selected_per_question": float(np.mean(counts)) if counts else None,
                "sum_values_bearing_columns_selected_across_questions": int(sum(counts)),
            }
        result["by_arm"][arm] = {
            "context_view": ARM_FACTORS[arm][1],
            "selected_values_bearing_columns": selected,
            "values_present_in_context": ARM_FACTORS[arm][1] == "R0",
        }
    return result


def per_database_metrics(rows_by_arm: dict[str, list[dict[str, Any]]], fixed_dbs: set[str], db_alias: dict[str, str]) -> dict[str, Any]:
    db_ids = sorted({row["db_id"] for rows in rows_by_arm.values() for row in rows})
    output: dict[str, Any] = {}
    for db_id in db_ids:
        output[db_alias[db_id]] = {"fixed_non_saturated": db_id in fixed_dbs, "conditions": {}}
        for arm, rows in rows_by_arm.items():
            selected = [row for row in rows if row["db_id"] == db_id]
            summary = summarize_rows(selected, fixed_dbs)
            output[db_alias[db_id]]["conditions"][arm] = summary["all"]
    return output


def build_aggregate(
    run_id: str, source: dict[str, Any], input_info: dict[str, Any], rows_by_arm: dict[str, list[dict[str, Any]]],
    score_digests: dict[str, dict[str, Any]], fixed_dbs: set[str], r0_nodes: list[Any], r1_nodes: list[Any],
) -> dict[str, Any]:
    p2b_aggregate = input_info["p2b_aggregate"]
    summary_by_arm = {arm: summarize_rows(rows, fixed_dbs) for arm, rows in rows_by_arm.items()}
    assert_p2b_aggregate_replay(p2b_aggregate, summary_by_arm)

    topk_invariants = {
        "V00_vs_V01": True,
        "V10_vs_V11": True,
    }
    assert_context_only_ranking_invariant(rows_by_arm["V00"], rows_by_arm["V01"])
    assert_context_only_ranking_invariant(rows_by_arm["V10"], rows_by_arm["V11"])
    score_invariants = {
        "V00_vs_V01": score_digests["R0"]["digest"] == score_digests["R0_context_check"]["digest"],
        "V10_vs_V11": score_digests["R1"]["digest"] == score_digests["R1_context_check"]["digest"],
    }
    if not all(score_invariants.values()):
        raise RuntimeError("Context-only score digest changed")

    metrics = {
        "all_complete_1024": {
            arm: summary_by_arm[arm]["all"]["budgets"]["1024"]["complete_query_macro"]
            for arm in ARM_FACTORS
        },
        "fixed_complete_1024": {
            arm: summary_by_arm[arm]["fixed_non_saturated"]["budgets"]["1024"]["complete_query_macro"]
            for arm in ARM_FACTORS
        },
        "all_column_r10": {
            arm: summary_by_arm[arm]["all"]["column_recall_query_macro"]["10"] for arm in ARM_FACTORS
        },
        "fixed_column_r10": {
            arm: summary_by_arm[arm]["fixed_non_saturated"]["column_recall_query_macro"]["10"] for arm in ARM_FACTORS
        },
    }
    factorial = {
        metric_name: {
            "all": factorial_contrasts(metrics[f"all_{metric_name}"]),
            "fixed_non_saturated": factorial_contrasts(metrics[f"fixed_{metric_name}"]),
        }
        for metric_name in ("complete_1024", "column_r10")
    }
    primary_all = paired_delta(
        rows_by_arm["V00"], rows_by_arm["V01"], ("budgets", "1024", "complete"), fixed_dbs, subset=False
    )
    primary_fixed = paired_delta(
        rows_by_arm["V00"], rows_by_arm["V01"], ("budgets", "1024", "complete"), fixed_dbs, subset=True
    )
    fixed_db_deltas: dict[str, float] = {}
    for db_id in sorted(fixed_dbs):
        base = [row for row in rows_by_arm["V00"] if row["db_id"] == db_id and row["column_eligible"]]
        candidate = [row for row in rows_by_arm["V01"] if row["db_id"] == db_id and row["column_eligible"]]
        fixed_db_deltas[db_id] = float(np.mean([
            metric_value(candidate_row, ("budgets", "1024", "complete")) - metric_value(base_row, ("budgets", "1024", "complete"))
            for base_row, candidate_row in zip(base, candidate)
        ]) * 100.0)
    nonnegative_dbs = sum(delta >= 0.0 for delta in fixed_db_deltas.values())
    positive_dbs = sum(delta > 0.0 for delta in fixed_db_deltas.values())
    primary_pass = (
        primary_fixed["delta_pp"] >= 3.0
        and primary_all["delta_pp"] >= 5.0
        and primary_fixed["database_cluster_bootstrap_95_ci_pp"][0] > 0.0
        and primary_all["database_cluster_bootstrap_95_ci_pp"][0] > 0.0
        and nonnegative_dbs >= 3
        and positive_dbs >= 2
    )
    db_alias = {db_id: f"db_{index:02d}" for index, db_id in enumerate(sorted({row["db_id"] for row in rows_by_arm["V00"]}), 1)}
    public_db_deltas = {db_alias[db_id]: fixed_db_deltas[db_id] for db_id in sorted(fixed_db_deltas)}
    r0_r1_rescue: dict[str, Any] = {}
    for comparison, base_arm, candidate_arm in (
        ("V01_minus_V00", "V00", "V01"),
        ("V10_minus_V00", "V00", "V10"),
        ("V11_minus_V10", "V10", "V11"),
    ):
        r0_r1_rescue[comparison] = rescue_damage(rows_by_arm[base_arm], rows_by_arm[candidate_arm], fixed_dbs)
    views = {
        "R0": {
            "text_sequence_sha256": input_info["p2b_audit"]["r0_schema_text_sequence_sha256"],
            "token_count": int(sum(node.token_count for node in r0_nodes)),
        },
        "R1": {
            "text_sequence_sha256": input_info["p2b_audit"]["r1_schema_text_sequence_sha256"],
            "token_count": int(sum(node.token_count for node in r1_nodes)),
        },
    }
    return {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "status": "completed",
        "source_commit": source["published_commit"],
        "input_manifest_sha256": input_info["p2b_hashes"]["input_manifest_sha256"],
        "benchmark": {
            "name": "BIRD dev",
            "questions": len(rows_by_arm["V00"]),
            "databases": len(db_alias),
            "column_eligible_questions": sum(row["column_eligible"] for row in rows_by_arm["V00"]),
            "fixed_non_saturated_databases": len(fixed_dbs),
            "fixed_non_saturated_column_eligible_questions": input_info["fixed_questions"],
            "exploratory_only": True,
        },
        "input_hashes": input_info["p2b_hashes"],
        "views": views,
        "arms": {
            arm: {
                "score_view": ARM_FACTORS[arm][0],
                "context_view": ARM_FACTORS[arm][1],
                "score_matrix_digest": score_digests[ARM_FACTORS[arm][0]]["digest"],
                "topk_question_rows_digest": topk_rows_digest(rows_by_arm[arm]),
                "metrics": summary_by_arm[arm],
            }
            for arm in ARM_FACTORS
        },
        "replay_checks": {
            "p2b_preserved_column_and_budget_rows_exact": True,
            "p2b_aggregate_metrics_exact_within_1e-14": True,
            "archived_p2b_table_topk_rows_available": False,
            "archived_p2b_table_topk_note": "P2b private rows archived only Column Top-K IDs and budget selections; P2c verifies table rank invariance across context-only pairs and records new Table results.",
            "context_only_score_digest_identical": score_invariants,
            "context_only_table_and_column_topk_identical": topk_invariants,
            "fixed_subset_rebuilt_from_R0_context": True,
        },
        "primary_gate": {
            "comparison": "V01_minus_V00 Complete Schema@1024",
            "all": primary_all,
            "fixed_non_saturated": primary_fixed,
            "fixed_database_deltas_pp_anonymized": public_db_deltas,
            "nonnegative_fixed_databases": nonnegative_dbs,
            "positive_fixed_databases": positive_dbs,
            "success": primary_pass,
            "decision": "candidate_for_value_risk_audit" if primary_pass else "no_go_stop_dual_view",
        },
        "factorial_contrasts": factorial,
        "paired_rescue_damage": r0_r1_rescue,
        "gold_only_fit": {
            "R0_context": gold_only_fit(input_info["prepared_full"], r0_nodes, fixed_dbs),
            "R1_context": gold_only_fit(input_info["prepared_full"], r1_nodes, fixed_dbs),
        },
        "value_context_coverage": value_context_coverage(rows_by_arm, r0_nodes, r1_nodes),
        "per_database_anonymized": per_database_metrics(rows_by_arm, fixed_dbs, db_alias),
        "bootstrap": {"unit": "database cluster", "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED},
        "limitations": [
            "BIRD dev has been used for iterative development and is exploratory, not an independent test set.",
            "Schema-node recall/coverage does not measure SQL execution accuracy, predicate-value usefulness, or JOIN-role correctness.",
            "No model forward, SQL execution, API request, or independent database validation was part of P2c.",
            "P2b archived private rows omit per-question Table Top-K IDs; exact historical replay is available for archived Column Top-K and budget rows, while Table rankings are checked across context-only P2c pairs.",
        ],
        "privacy": {
            "question_ids_published": False,
            "questions_published": False,
            "gold_sql_published": False,
            "per_question_rows_published": False,
            "database_names_published": False,
            "vectors_published": False,
        },
        "api_usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_cny": "0.00"},
        "local_model_usage": {"model_weights_loaded": False, "forward_passes": 0, "input_tokens": 0, "output_tokens": 0},
    }


def write_private_rows(path: Path, rows_by_arm: dict[str, list[dict[str, Any]]], score_digests: dict[str, dict[str, Any]]) -> str:
    digest_by_arm = {
        arm: {item["question_id"]: item["digest"] for item in score_digests[ARM_FACTORS[arm][0]]["private_question_digests"]}
        for arm in ARM_FACTORS
    }
    with path.open("w", encoding="utf-8") as file:
        base_rows = rows_by_arm["V00"]
        for index, base in enumerate(base_rows):
            record: dict[str, Any] = {
                "question_id": base["question_id"],
                "db_id": base["db_id"],
                "column_eligible": base["column_eligible"],
                "arms": {},
            }
            for arm in ARM_FACTORS:
                row = rows_by_arm[arm][index]
                method = row["methods"]["S0_cosine"]
                record["arms"][arm] = {
                    "score_matrix_digest": digest_by_arm[arm][row["question_id"]],
                    "table_topk_ids": method["table"]["topk_ids"],
                    "column_topk_ids": method["column"]["topk_ids"] if method["column"] else {},
                    "column_recall": method["column"]["recall"] if method["column"] else {},
                    "budgets": method["budgets"],
                }
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    return sha256_file(path)


def predecessor_commit_is_registered(actual_commit: str, expected_commit: str, registered_prior_commits: set[str]) -> bool:
    return actual_commit == expected_commit or actual_commit in registered_prior_commits


def check_registered_predecessor(
    path: Path | None, expected_status: str, expected_commit: str,
    registered_prior_commits: set[str] | None = None,
) -> None:
    if path is None:
        raise RuntimeError("A registered prior-stage result directory is required")
    summary_path = path / ("preflight_summary.json" if expected_status == "preflight_passed" else "smoke_summary.json")
    start_path = path / "run_start.json"
    if not summary_path.is_file() or not start_path.is_file():
        raise FileNotFoundError(f"Prior-stage evidence is missing: {path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    start = json.loads(start_path.read_text(encoding="utf-8"))
    if summary.get("status") != expected_status or start.get("state") != "completed":
        raise RuntimeError(f"Prior stage did not pass: expected {expected_status}")
    actual_commit = start.get("source", {}).get("published_commit")
    if not predecessor_commit_is_registered(actual_commit, expected_commit, registered_prior_commits or set()):
        raise RuntimeError("Prior stage source commit differs from this run")


def run() -> None:
    args = parse_args()
    expected_ids = {
        "preflight": "p2c_dual_view_preflight_20261018_02",
        "smoke": "p2c_dual_view_smoke5_20261018_01",
        "full": "p2c_dual_view_full1534_20261018_02",
    }
    if args.run_id != expected_ids[args.mode]:
        raise RuntimeError(f"Unexpected {args.mode} run ID: {args.run_id}")
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse P2c output directory: {args.output_dir}")
    if args.mode == "smoke":
        check_registered_predecessor(args.preflight_dir, "preflight_passed", args.expected_commit)
    if args.mode == "full":
        check_registered_predecessor(
            args.preflight_dir, "preflight_passed", args.expected_commit, {RECOVERY_PREDECESSOR_COMMIT}
        )
        check_registered_predecessor(
            args.smoke_dir, "smoke_passed", args.expected_commit, {RECOVERY_PREDECESSOR_COMMIT}
        )
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
        "resource_budget": {"cpu_seconds_max": MAX_CPU_SECONDS, "process_maxrss_gib": MAX_RSS_GIB, "max_cpu_threads": MAX_THREADS, "gpu_seconds": 0},
        "environment": {
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "transformers": package_version("transformers"),
            "tokenizers": package_version("tokenizers"),
            "model_path": str(args.model_path.resolve()),
            "local_only": True,
            "model_weights_loaded": False,
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
        "model_forwards": 0,
        "sql_executions": 0,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    try:
        print(json.dumps({"stage": "validate_frozen_p2b_cache", "run_id": args.run_id}, ensure_ascii=False), flush=True)
        input_info = load_registered_inputs(args)
        source = input_info["source"]
        run_start["source"]["published_commit"] = source["published_commit"]
        run_start["source"]["local_commit"] = source["local_commit"]
        run_start["source"]["tree_sha"] = source["tree_sha"]
        run_start["source"]["checkout_tree_matches_published_commit"] = True
        run_start["source"]["worktree_status"] = source["worktree_status"]
        run_start["input_manifest_sha256"] = input_info["p2b_hashes"]["input_manifest_sha256"]
        run_start["p2b_hashes"] = input_info["p2b_hashes"]
        run_start["selected_questions"] = len(input_info["prepared_full"]["questions"])
        run_start["selected_nodes"] = len(input_info["prepared_full"]["nodes"])
        run_start["fixed_non_saturated_questions"] = input_info["fixed_questions"]
        check_budget(started_cpu)

        if args.mode == "preflight":
            summary = {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "status": "preflight_passed",
                "questions": len(input_info["prepared_full"]["questions"]),
                "databases": len({q["db_id"] for q in input_info["prepared_full"]["questions"]}),
                "nodes": len(input_info["prepared_full"]["nodes"]),
                "fixed_non_saturated_databases": len(input_info["fixed_dbs"]),
                "fixed_non_saturated_column_eligible_questions": input_info["fixed_questions"],
                "cache_vectors_valid": True,
                "p2b_text_order_and_token_counts_match": True,
                "published_aggregate_hash_matches_local": True,
                "no_model_weights_or_forward_passes": True,
                "not_experiment_evidence": True,
            }
            write_json(args.output_dir / "preflight_summary.json", summary)
        else:
            prepared, cache, node_indexes = select_active_inputs(
                input_info["prepared_full"], input_info["cache_full"], args.mode
            )
            r1_nodes = [input_info["r1_nodes_full"][index] for index in node_indexes]
            r0_nodes = prepared["nodes"]
            q_vectors = cache["query_vectors"]
            score_vectors = {"R0": cache["r0_node_vectors"], "R1": cache["r1_node_vectors"]}
            p1 = input_info["p1"]
            p2a = input_info["p2a"]
            rows_by_arm: dict[str, list[dict[str, Any]]] = {}
            for arm, (score_view, context_view) in ARM_FACTORS.items():
                print(json.dumps({"stage": "evaluate_arm", "arm": arm, "score_view": score_view, "context_view": context_view}, ensure_ascii=False), flush=True)
                context_nodes = r0_nodes if context_view == "R0" else r1_nodes
                context_prepared = dict(prepared)
                context_prepared["nodes"] = context_nodes
                _, rows = p2a.evaluate(context_prepared, q_vectors, score_vectors[score_view])
                if len(rows) != len(prepared["questions"]):
                    raise RuntimeError(f"{arm} returned an unexpected number of question rows")
                rows_by_arm[arm] = rows
                check_budget(started_cpu)

            score_digests = {
                "R0": score_matrix_digests(prepared, p1, q_vectors, score_vectors["R0"]),
                "R1": score_matrix_digests(prepared, p1, q_vectors, score_vectors["R1"]),
                "R0_context_check": score_matrix_digests(prepared, p1, q_vectors, score_vectors["R0"]),
                "R1_context_check": score_matrix_digests(prepared, p1, q_vectors, score_vectors["R1"]),
            }
            assert_context_only_ranking_invariant(rows_by_arm["V00"], rows_by_arm["V01"])
            assert_context_only_ranking_invariant(rows_by_arm["V10"], rows_by_arm["V11"])
            assert_p2b_replay(input_info["p2b_rows"][:len(prepared["questions"])], rows_by_arm["V00"], P2B_ROW_VARIANTS["V00"])
            assert_p2b_replay(input_info["p2b_rows"][:len(prepared["questions"])], rows_by_arm["V11"], P2B_ROW_VARIANTS["V11"])

            if args.mode == "smoke":
                summary = {
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": args.run_id,
                    "status": "smoke_passed",
                    "questions": len(prepared["questions"]),
                    "databases": len({q["db_id"] for q in prepared["questions"]}),
                    "nodes": len(prepared["nodes"]),
                    "all_scores_finite": True,
                    "score_view_context_invariants_exact": True,
                    "p2b_column_and_budget_replay_exact": True,
                    "formal_result": False,
                    "not_formal_evidence": True,
                }
                write_json(args.output_dir / "smoke_summary.json", summary)
            else:
                aggregate = build_aggregate(
                    args.run_id, source, input_info, rows_by_arm, score_digests,
                    input_info["fixed_dbs"], r0_nodes, r1_nodes,
                )
                aggregate_path = args.output_dir / "aggregate_summary.json"
                write_json(aggregate_path, aggregate)
                private_path = args.output_dir / "per_question_private.jsonl"
                private_hash = write_private_rows(private_path, rows_by_arm, score_digests)
                run_start["aggregate_summary_sha256"] = sha256_file(aggregate_path)
                run_start["private_per_question_sha256"] = private_hash
                run_start["p2b_replay_exact"] = True
                run_start["gate_decision"] = aggregate["primary_gate"]["decision"]
                run_start["primary_success"] = aggregate["primary_gate"]["success"]
                summary = {
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": args.run_id,
                    "status": "full_completed",
                    "questions": len(prepared["questions"]),
                    "databases": len({q["db_id"] for q in prepared["questions"]}),
                    "column_eligible_questions": sum(q["column_eligible"] for q in rows_by_arm["V00"]),
                    "gate_decision": aggregate["primary_gate"]["decision"],
                    "not_text2sql_execution_accuracy": True,
                    "aggregate_summary_sha256": run_start["aggregate_summary_sha256"],
                }
                write_json(args.output_dir / "full_summary.json", summary)

        run_start.update({
            "state": "completed",
            "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_elapsed_wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds_process": time.process_time() - started_cpu,
            "process_maxrss_gib": peak_rss_gib(),
        })
        if args.mode == "preflight":
            run_start["preflight_summary_sha256"] = sha256_file(args.output_dir / "preflight_summary.json")
        elif args.mode == "smoke":
            run_start["smoke_summary_sha256"] = sha256_file(args.output_dir / "smoke_summary.json")
        write_json(args.output_dir / "run_start.json", run_start)
        print(json.dumps({
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "completed",
            "output_dir": str(args.output_dir.resolve()),
            "wall_seconds": run_start["finished_elapsed_wall_seconds"],
            "cpu_seconds": run_start["cpu_seconds_process"],
            "rss_gib": run_start["process_maxrss_gib"],
            "decision": run_start.get("gate_decision"),
        }, ensure_ascii=False), flush=True)
    except Exception as error:
        run_start.update({
            "state": "failed",
            "failed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_elapsed_wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds_process": time.process_time() - started_cpu,
            "process_maxrss_gib": peak_rss_gib(),
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
