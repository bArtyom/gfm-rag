#!/usr/bin/env python3
"""CPU-only replay and error-attribution audit for the frozen P2a run.

This runner validates and replays the archived P2a outputs before producing
anonymous aggregate diagnostics. It never writes per-question or raw SQL data.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
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
P2A_COMMIT = "689b7f681651f312a1db8850d86b8b7dc4f69fd2"
P1_6_COMMIT = "d948d462f9407a18f4a48c85a76380d54f865cb2"
P2A_RUN_ID = "p2a_similarity_full1534_20261018_02"
P1_6_RUN_ID = "p1_6_full1534_20261018_01"
P1_5_RUN_ID = "p1_5_diag_full_20261016_03"
EXPECTED = {"questions": 1534, "databases": 11, "column_eligible": 1460, "non_saturated_databases": 5, "non_saturated_questions": 746, "non_saturated_column_eligible": 706, "tables": 75, "columns": 798, "nodes": 873}
METHODS = ("S0_cosine", "S1_bm25", "S2_rrf")
TRANSITION_BINS = ((1, 5, "1-5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, 50, "21-50"), (51, math.inf, ">50"))

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
P2A_RUNNER = REPO_ROOT / "scripts/text2sql/run_p2a_similarity.py"
P1_6_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_6_rebaseline.py"
P1_5_RUNNER = REPO_ROOT / "scripts/text2sql/run_p1_5_diagnostics.py"
P2A_PROTOCOL = REPO_ROOT / "docs/research/text2sql/plans/p2a_similarity_20261018.md"
P2A5_PROTOCOL = REPO_ROOT / "docs/research/text2sql/plans/p2a_5_diagnostic_and_schema_representation_20261018.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


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
        "gpu_snapshot_not_used": command_output(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]),
        "free_h": command_output(["free", "-h"]),
        "cpu_threads": os.cpu_count(),
        "disk": command_output(["df", "-h", str(REPO_ROOT)]),
    }


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import registered helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_show_bytes(commit: str, relative_path: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{commit}:{relative_path}"], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Unable to read pinned source {commit}:{relative_path}")
    return result.stdout


def verify_pinned_sources() -> dict[str, str]:
    p2a_relative = "scripts/text2sql/run_p2a_similarity.py"
    p1_relative = "scripts/text2sql/run_p1_6_rebaseline.py"
    p2a_bytes = P2A_RUNNER.read_bytes()
    p1_bytes = P1_6_RUNNER.read_bytes()
    if p2a_bytes != git_show_bytes(P2A_COMMIT, p2a_relative):
        raise RuntimeError("Current P2a scorer differs from the source commit used in the registered Full run")
    if p1_bytes != git_show_bytes(P1_6_COMMIT, p1_relative):
        raise RuntimeError("Current P1.6 helper differs from the frozen cache source commit")
    return {"p2a_scorer_sha256": sha256_bytes(p2a_bytes), "p1_6_runner_sha256": sha256_bytes(p1_bytes)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--p2a-run-dir", type=Path, required=True)
    parser.add_argument("--p1-6-run-dir", type=Path, required=True)
    parser.add_argument("--p1-5-run-dir", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--smoke-dir", type=Path)
    return parser.parse_args()


def load_private_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def validate_p2a_artifacts(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    run_start_path = args.p2a_run_dir / "run_start.json"
    aggregate_path = args.p2a_run_dir / "aggregate_summary.json"
    private_path = args.p2a_run_dir / "per_question_private.jsonl"
    if not all(path.is_file() for path in (run_start_path, aggregate_path, private_path)):
        raise FileNotFoundError("Completed P2a private artifacts are incomplete")
    run_start = json.loads(run_start_path.read_text(encoding="utf-8"))
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if run_start.get("run_id") != P2A_RUN_ID or run_start.get("mode") != "full" or run_start.get("state") != "completed":
        raise RuntimeError("P2a source run is not the registered completed Full run")
    if run_start.get("source", {}).get("published_commit") != P2A_COMMIT or aggregate.get("source_commit") != P2A_COMMIT:
        raise RuntimeError("P2a source commit does not match the preregistered scorer")
    if run_start.get("result_summary_sha256") != sha256_file(aggregate_path):
        raise RuntimeError("P2a aggregate hash does not match run metadata")
    if aggregate.get("private_artifacts", {}).get("per_question_sha256") != sha256_file(private_path):
        raise RuntimeError("P2a per-question artifact hash does not match aggregate metadata")
    if aggregate.get("status") != "completed" or aggregate.get("s0_parity") != "PASS" or aggregate.get("integrity_gate") != "PASS":
        raise RuntimeError("P2a source run did not pass its integrity and S0 parity gates")
    rows = load_private_jsonl(private_path)
    if len(rows) != EXPECTED["questions"]:
        raise RuntimeError(f"P2a row count mismatch: {len(rows)}")
    if len({row["question_id"] for row in rows}) != EXPECTED["questions"]:
        raise RuntimeError("P2a private question IDs are not unique")
    if sum(bool(row["column_eligible"]) for row in rows) != EXPECTED["column_eligible"]:
        raise RuntimeError("P2a column-eligible denominator mismatch")
    for row in rows:
        if set(row.get("methods", {})) != set(METHODS):
            raise RuntimeError("P2a row is missing one of the frozen methods")
        for method in METHODS:
            method_row = row["methods"][method]
            if not isinstance(method_row.get("column"), (dict, type(None))) or not isinstance(method_row.get("budgets"), (dict, type(None))):
                raise RuntimeError("P2a row has an unexpected metric structure")
    return run_start, rows, aggregate


def load_and_validate_inputs(args: argparse.Namespace, p1: Any, p2a: Any, p2a_run_start: dict[str, Any], aggregate: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    p1_module = p2a.load_p1_6_module()
    p2a.p1_module = p1_module
    source_hashes = verify_pinned_sources()
    p1_6_run_start_path = args.p1_6_run_dir / "run_start.json"
    p1_6_summary_path = args.p1_6_run_dir / "aggregate_summary.json"
    p1_6_run_start = json.loads(p1_6_run_start_path.read_text(encoding="utf-8"))
    p1_6_summary = json.loads(p1_6_summary_path.read_text(encoding="utf-8"))
    if p1_6_run_start.get("run_id") != P1_6_RUN_ID or p1_6_run_start.get("mode") != "full" or p1_6_run_start.get("state") != "completed":
        raise RuntimeError("P1.6 cache source is not the registered completed Full run")
    if p1_6_run_start.get("source", {}).get("published_commit") != P1_6_COMMIT:
        raise RuntimeError("P1.6 cache came from an unexpected source commit")
    if p2a_run_start.get("input_manifest_sha256") != p1_6_run_start.get("input_manifest_private_sha256"):
        raise RuntimeError("P2a and P1.6 input manifest hashes differ")
    if p2a_run_start.get("p1_6_cache_sha256") != sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"):
        raise RuntimeError("P2a and P1.6 cache hashes differ")
    if aggregate.get("p1_6_cache_sha256") != p2a_run_start.get("p1_6_cache_sha256"):
        raise RuntimeError("P2a aggregate cache hash differs from run metadata")
    if aggregate.get("input_manifest_sha256") != p2a_run_start.get("input_manifest_sha256"):
        raise RuntimeError("P2a aggregate input manifest hash differs from run metadata")

    validation_args = argparse.Namespace(
        p1_6_run_dir=args.p1_6_run_dir,
        legacy_root=args.legacy_root,
        dataset_root=args.dataset_root,
        model_path=args.model_path,
        previous_run_dir=args.previous_run_dir,
        p1_5_run_dir=args.p1_5_run_dir,
    )
    ref, prepared, query_vectors, node_vectors = p2a.validate_p1_6_inputs(validation_args, p1_module)
    if ref["input_manifest_sha256"] != p2a_run_start.get("input_manifest_sha256"):
        raise RuntimeError("Reconstructed frozen input manifest hash differs from P2a")
    input_counts = ref["input_record"].get("counts", {})
    expected_input_counts = {key: EXPECTED[key] for key in ("questions", "databases", "nodes", "tables", "columns", "column_eligible")}
    if input_counts != expected_input_counts:
        raise RuntimeError(f"Frozen input counts differ from preregistration: {input_counts}")
    p1_summary = json.loads((args.p1_6_run_dir / "aggregate_summary.json").read_text(encoding="utf-8"))
    p1_6_rows_summary, p1_6_rows, _ = p1_module.score_snapshot(prepared, query_vectors, node_vectors)
    scorer = p1_summary["scorer_replay"]
    if p1_6_rows_summary["score_matrix_digest_sha256"] != scorer["pass1_score_matrix_digest_sha256"]:
        raise RuntimeError("Replayed P1.6 S0 matrix digest differs from the frozen cache scorer")
    if p1_6_rows_summary["question_rows_digest_sha256"] != scorer["pass1_question_rows_digest_sha256"]:
        raise RuntimeError("Replayed P1.6 question-row digest differs from the frozen cache scorer")
    if aggregate.get("p1_6_s0_score_matrix_digest_sha256") != p1_6_rows_summary["score_matrix_digest_sha256"]:
        raise RuntimeError("P2a source scorer digest differs from P1.6 cache replay")
    return prepared, query_vectors, node_vectors, p1_6_rows, {**source_hashes, "p1_6_score_digest": p1_6_rows_summary["score_matrix_digest_sha256"], "p1_6_question_digest": p1_6_rows_summary["question_rows_digest_sha256"], "p1_6_cache_sha256": sha256_file(args.p1_6_run_dir / "embedding_cache_private.npz"), "input_manifest_sha256": ref["input_manifest_sha256"]}


def quantiles(values: list[float | int]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p90": None}
    arr = np.asarray(values, dtype=np.float64)
    return {"n": int(arr.size), "mean": float(np.mean(arr)), "p50": float(np.quantile(arr, 0.5)), "p90": float(np.quantile(arr, 0.9))}


def rank_bin(rank: int) -> str:
    for lower, upper, label in TRANSITION_BINS:
        if lower <= rank <= upper:
            return label
    raise ValueError(f"Invalid rank: {rank}")


def normalize_transition_accumulator() -> dict[str, Any]:
    labels = [item[2] for item in TRANSITION_BINS]
    return {"counts": {old: {new: 0 for new in labels} for old in labels}, "query_macro_sum": {old: {new: 0.0 for new in labels} for old in labels}, "questions": 0, "gold_elements": 0}


def finalize_transition(acc: dict[str, Any]) -> dict[str, Any]:
    qn = acc["questions"]
    en = acc["gold_elements"]
    return {
        "questions": qn,
        "gold_elements": en,
        "element_share_pct": {old: {new: 100.0 * count / en if en else None for new, count in row.items()} for old, row in acc["counts"].items()},
        "question_macro_share_pct": {old: {new: 100.0 * value / qn if qn else None for new, value in row.items()} for old, row in acc["query_macro_sum"].items()},
        "element_transition_counts": acc["counts"],
    }


def analyze_p2a(prepared: dict[str, Any], query_vectors: np.ndarray, node_vectors: np.ndarray, p1: Any, p2a: Any, rows: list[dict[str, Any]], replay_summary: dict[str, Any]) -> dict[str, Any]:
    questions = prepared["questions"]
    nodes = prepared["nodes"]
    if len(questions) != EXPECTED["questions"] or len(nodes) != EXPECTED["nodes"]:
        raise RuntimeError("Reconstructed P2a input row or node count mismatch")
    nodes_by_db: dict[str, list[int]] = collections.defaultdict(list)
    nodes_by_id: dict[str, Any] = {}
    for index, node in enumerate(nodes):
        nodes_by_db[node.db_id].append(index)
        nodes_by_id[node.node_id] = node
    schema_tokens = {db: sum(nodes[index].token_count for index in indexes) for db, indexes in nodes_by_db.items()}
    non_saturated = {db for db, count in schema_tokens.items() if count > 2048}
    query_unit, _ = p1.normalized_vectors(query_vectors)
    node_unit, _ = p1.normalized_vectors(node_vectors)

    transition_acc: dict[str, dict[str, dict[str, Any]]] = {
        method: {scope: normalize_transition_accumulator() for scope in ("all", "non_saturated")}
        | {f"db:{db}": normalize_transition_accumulator() for db in sorted(nodes_by_db)}
        for method in ("S1_bm25", "S2_rrf")
    }
    paired = {method: {scope: {"column_r10": collections.Counter(), "budget_complete": {str(b): collections.Counter() for b in (512, 1024, 2048)}} for scope in ("all", "non_saturated")} for method in ("S1_bm25", "S2_rrf")}
    budget_values: dict[str, dict[str, dict[str, list[float]]]] = {
        method: {scope: collections.defaultdict(list) for scope in ("all", "non_saturated")} for method in METHODS
    }
    false_positive_top10_lengths: dict[str, dict[str, list[int]]] = {
        method: {scope: [] for scope in ("all", "non_saturated")} for method in METHODS
    }
    text_feature_acc: dict[str, collections.Counter[str]] = {
        feature: collections.Counter()
        for feature in ("has_description", "has_format", "has_values", "name_snake_case", "name_has_digit", "name_has_short_token", "query_has_single_char_token")
    }
    bm25_overlap = {"all_candidates": [], "column_candidates": [], "all_nonzero": [], "column_nonzero": [], "query_tokens": [], "gold_overlap": 0, "gold_elements": 0, "gold_missed_s1_no_overlap": 0, "gold_missed_s1_with_overlap": 0}
    bm25_lost_classes = collections.Counter()
    tie_boundary = {view: {str(k): {"questions": 0, "tied_candidates": 0, "slots_taken_by_stable_id": 0} for k in ks} for view, ks in (("table", (5, 10)), ("column", (5, 10, 20)), ("all", (5, 10, 20)))}
    candidate_ties = {view: {"questions_with_any_tie": 0, "tie_groups": 0, "extra_candidates": 0} for view in ("all", "table", "column")}

    for q_index, question in enumerate(questions):
        saved = rows[q_index]
        if int(question["question_id"]) != saved["question_id"] or question["db_id"] != saved["db_id"]:
            raise RuntimeError("P2a private output row order does not match the frozen input")
        db = question["db_id"]
        idxs = nodes_by_db[db]
        ids = [nodes[i].node_id for i in idxs]
        dense = np.asarray(query_unit[q_index] @ node_unit[idxs].T, dtype=np.float32)
        if not np.isfinite(dense).all():
            raise RuntimeError("Non-finite dense score encountered during replay")
        corpus = p2a.build_bm25_corpus([nodes[i] for i in idxs])
        sparse = p2a.bm25_scores(question["text"], corpus)
        table_positions = [local for local, global_idx in enumerate(idxs) if nodes[global_idx].node_type == "table"]
        column_positions = [local for local, global_idx in enumerate(idxs) if nodes[global_idx].node_type == "column"]
        all_positions = list(range(len(idxs)))
        positions_by_view = {"all": all_positions, "table": table_positions, "column": column_positions}
        gold_cols = set(saved["gold_column_ids"])
        gold_tables = set(question["label"]["gold_table_ids"])
        gold_all = gold_cols | gold_tables
        q_tokens = set(p2a.tokenize(question["text"]))
        bm25_overlap["query_tokens"].append(len(q_tokens))
        token_sets = [set(tokens) for tokens in corpus["tokens"]]
        column_local_positions = [local for local, global_idx in enumerate(idxs) if nodes[global_idx].node_type == "column"]
        bm25_overlap["all_candidates"].append(len(idxs))
        bm25_overlap["column_candidates"].append(len(column_local_positions))
        bm25_overlap["all_nonzero"].append(sum(bool(q_tokens & tokens) for tokens in token_sets))
        bm25_overlap["column_nonzero"].append(sum(bool(q_tokens & token_sets[local]) for local in column_local_positions))
        method_ranks: dict[str, dict[str, dict[str, int]]] = {}
        method_orders: dict[str, dict[str, list[str]]] = {}
        method_scores: dict[str, dict[str, np.ndarray]] = {}

        for method in METHODS:
            method_ranks[method] = {}
            method_orders[method] = {}
            method_scores[method] = {}
            for view, positions in positions_by_view.items():
                order, values = p2a.method_order(method, positions, dense, sparse, ids)
                ranked_ids = [ids[position] for position in order]
                method_orders[method][view] = ranked_ids
                method_ranks[method][view] = {node_id: rank for rank, node_id in enumerate(ranked_ids, 1)}
                method_scores[method][view] = values
                _, counts = np.unique(values, return_counts=True)
                groups = int(np.count_nonzero(counts > 1))
                candidate_ties[view]["questions_with_any_tie"] += int(groups > 0)
                candidate_ties[view]["tie_groups"] += groups
                candidate_ties[view]["extra_candidates"] += int(np.sum(counts[counts > 1] - 1)) if groups else 0
                if method == "S1_bm25":
                    for k in tie_boundary[view]:
                        boundary = int(k)
                        if len(values) > boundary and values[boundary - 1] == values[boundary]:
                            left = boundary - 1
                            right = boundary
                            while left > 0 and values[left - 1] == values[boundary - 1]:
                                left -= 1
                            while right + 1 < len(values) and values[right + 1] == values[boundary]:
                                right += 1
                            tie_boundary[view][k]["questions"] += 1
                            tie_boundary[view][k]["tied_candidates"] += right - left + 1
                            tie_boundary[view][k]["slots_taken_by_stable_id"] += boundary - left

        # Gold-column rank transitions are aligned by stable node ID, not by sorted rank lists.
        for method in ("S1_bm25", "S2_rrf"):
            method_scope_names = ["all", f"db:{db}"] + (["non_saturated"] if db in non_saturated else [])
            for scope in method_scope_names:
                acc = transition_acc[method][scope]
                if saved["column_eligible"]:
                    acc["questions"] += 1
                    acc["gold_elements"] += len(gold_cols)
                    row_counts = collections.Counter()
                    for node_id in gold_cols:
                        old_bin = rank_bin(method_ranks["S0_cosine"]["column"][node_id])
                        new_bin = rank_bin(method_ranks[method]["column"][node_id])
                        acc["counts"][old_bin][new_bin] += 1
                        row_counts[(old_bin, new_bin)] += 1
                    for (old_bin, new_bin), count in row_counts.items():
                        acc["query_macro_sum"][old_bin][new_bin] += count / len(gold_cols)

        for method in ("S1_bm25", "S2_rrf"):
            for scope in ("all", "non_saturated"):
                if scope == "non_saturated" and db not in non_saturated:
                    continue
                if not saved["column_eligible"]:
                    continue
                base_ids = set(method_orders["S0_cosine"]["column"][:10])
                new_ids = set(method_orders[method]["column"][:10])
                base_gold = base_ids & gold_cols
                new_gold = new_ids & gold_cols
                counter = paired[method][scope]["column_r10"]
                counter["questions"] += 1
                counter["rescued_questions"] += int(len(new_gold) > len(base_gold))
                counter["damaged_questions"] += int(len(new_gold) < len(base_gold))
                counter["unchanged_questions"] += int(len(new_gold) == len(base_gold))
                counter["rescued_gold_elements"] += len(new_gold - base_gold)
                counter["damaged_gold_elements"] += len(base_gold - new_gold)
                counter["net_gold_hit_delta"] += len(new_gold) - len(base_gold)
                for budget in (512, 1024, 2048):
                    base_complete = int(saved["methods"]["S0_cosine"]["budgets"][str(budget)]["complete"])
                    new_complete = int(saved["methods"][method]["budgets"][str(budget)]["complete"])
                    bc = paired[method][scope]["budget_complete"][str(budget)]
                    bc["questions"] += 1
                    bc["rescued"] += int(base_complete == 0 and new_complete == 1)
                    bc["damaged"] += int(base_complete == 1 and new_complete == 0)
                    bc["unchanged_complete"] += int(base_complete == new_complete)

        if saved["column_eligible"]:
            for node_id in gold_cols:
                node = nodes_by_id[node_id]
                text_lower = node.text.casefold()
                prefix = node.text.split(";", 1)[0]
                name = prefix.removeprefix("Column: ").split(".")[-1]
                name_tokens = re.findall(r"[A-Za-z0-9]+", name)
                raw_question_tokens = re.findall(r"[A-Za-z0-9]+", question["text"])
                features = {
                    "has_description": "; description:" in text_lower,
                    "has_format": "; format:" in text_lower,
                    "has_values": "; values:" in text_lower,
                    "name_snake_case": "_" in name,
                    "name_has_digit": any(ch.isdigit() for ch in name),
                    "name_has_short_token": any(len(token) == 1 for token in name_tokens),
                    "query_has_single_char_token": any(len(token) == 1 for token in raw_question_tokens),
                }
                bm25_overlap["gold_elements"] += 1
                overlap = bool(set(p2a.tokenize(node.text)).intersection(q_tokens))
                bm25_overlap["gold_overlap"] += int(overlap)
                if method_ranks["S1_bm25"]["column"][node_id] > 10:
                    bm25_overlap["gold_missed_s1_no_overlap"] += int(not overlap)
                    bm25_overlap["gold_missed_s1_with_overlap"] += int(overlap)
                for feature, flag in features.items():
                    text_feature_acc[feature]["denominator"] += 1
                    text_feature_acc[feature]["true"] += int(flag)
                    text_feature_acc[feature]["false"] += int(not flag)
                    for method in METHODS:
                        text_feature_acc[feature][method + "_hit"] += int(method_ranks[method]["column"][node_id] <= 10 and flag)
                        text_feature_acc[feature][method + "_miss"] += int(method_ranks[method]["column"][node_id] > 10 and flag)
                        text_feature_acc[feature][method + "_no_feature_hit"] += int(method_ranks[method]["column"][node_id] <= 10 and not flag)
                        text_feature_acc[feature][method + "_no_feature_miss"] += int(method_ranks[method]["column"][node_id] > 10 and not flag)

                if method_ranks["S0_cosine"]["column"][node_id] <= 10 and method_ranks["S1_bm25"]["column"][node_id] > 10:
                    bm25_lost_classes["column_r10_gold_loss"] += 1
                    sparse_rank = method_ranks["S1_bm25"]["column"][node_id]
                    sparse_values = method_scores["S1_bm25"]["column"]
                    sparse_score = float(sparse_values[sparse_rank - 1])
                    boundary_score = float(sparse_values[9]) if len(sparse_values) > 9 else None
                    tied_at_boundary = boundary_score is not None and sparse_score == boundary_score and len(sparse_values) > 10 and sparse_values[9] == sparse_values[10]
                    if tied_at_boundary:
                        bm25_lost_classes["ties"] += 1
                    elif not overlap:
                        bm25_lost_classes["lexical_lost"] += 1
                    else:
                        bm25_lost_classes["unknown_positive_overlap_ranked_below_10"] += 1

        for method in METHODS:
            for scope in ("all", "non_saturated"):
                if scope == "non_saturated" and db not in non_saturated:
                    continue
                if not saved["column_eligible"]:
                    continue
                for budget in (512, 1024, 2048):
                    bdata = saved["methods"][method]["budgets"][str(budget)]
                    selected_ids = bdata["selected_ids"]
                    selected = [nodes_by_id[node_id] for node_id in selected_ids]
                    selected_gold = set(selected_ids) & gold_all
                    gold_token_need = sum(nodes_by_id[node_id].token_count for node_id in gold_all)
                    keys = budget_values[method][scope]
                    keys[f"tokens_used_{budget}"].append(int(bdata["tokens_used"]))
                    keys[f"selected_tables_{budget}"].append(sum(node.node_type == "table" for node in selected))
                    keys[f"selected_columns_{budget}"].append(sum(node.node_type == "column" for node in selected))
                    keys[f"gold_tables_selected_{budget}"].append(len(selected_gold & gold_tables))
                    keys[f"gold_columns_selected_{budget}"].append(len(selected_gold & gold_cols))
                    keys[f"gold_elements_selected_{budget}"].append(len(selected_gold))
                    keys[f"gold_elements_total_{budget}"].append(len(gold_all))
                    keys[f"gold_only_tokens_{budget}"].append(gold_token_need)
                    keys[f"gold_oracle_feasible_{budget}"].append(int(gold_token_need <= budget))
                    keys[f"complete_{budget}"].append(int(bdata["complete"]))
                    keys[f"any_gold_missing_{budget}"].append(int(len(selected_gold) < len(gold_all)))
                    keys[f"packing_loss_when_oracle_feasible_{budget}"].append(int(gold_token_need <= budget and len(selected_gold) < len(gold_all)))
                    non_gold_lengths = [node.token_count for node in selected if node.node_id not in gold_all]
                    keys[f"selected_non_gold_text_tokens_{budget}"].extend(non_gold_lengths)
                    missing_gold_ranks = [method_ranks[method]["all"][node_id] for node_id in gold_all if node_id not in selected_gold]
                    keys[f"missing_gold_rank_{budget}"].extend(missing_gold_ranks)
            if saved["column_eligible"]:
                top10 = method_orders[method]["column"][:10]
                false_positive_top10_lengths[method]["all"].extend(nodes_by_id[node_id].token_count for node_id in top10 if node_id not in gold_cols)
                if db in non_saturated:
                    false_positive_top10_lengths[method]["non_saturated"].extend(nodes_by_id[node_id].token_count for node_id in top10 if node_id not in gold_cols)

    if set(non_saturated) != set(replay_summary["non_saturated_2048"]["databases"]):
        raise RuntimeError("Non-saturated DB cohort differs from the archived P2a aggregate")
    if len(non_saturated) != EXPECTED["non_saturated_databases"] or sum(db in non_saturated for db in (q["db_id"] for q in questions)) != EXPECTED["non_saturated_questions"]:
        raise RuntimeError("Non-saturated database/question denominator mismatch")

    transition = {
        method: {scope: finalize_transition(acc) for scope, acc in scopes.items()}
        for method, scopes in transition_acc.items()
    }
    paired_result = {}
    for method, scopes in paired.items():
        paired_result[method] = {}
        for scope, metrics in scopes.items():
            paired_result[method][scope] = {
                "column_r10": dict(metrics["column_r10"]),
                "budget_complete": {budget: dict(counter) for budget, counter in metrics["budget_complete"].items()},
            }
    budget_result = {}
    for method, scopes in budget_values.items():
        budget_result[method] = {scope: {key: quantiles(values) if key.startswith(("tokens_used_", "selected_tables_", "selected_columns_", "gold_tables_selected_", "gold_columns_selected_", "gold_elements_selected_", "gold_elements_total_", "gold_only_tokens_", "selected_non_gold_text_tokens_", "missing_gold_rank_")) else {"n": len(values), "count": int(sum(values)), "rate": float(np.mean(values)) if values else None} for key, values in data.items()} for scope, data in scopes.items()}

    top10_lengths = {method: {scope: quantiles(values) for scope, values in scopes.items()} for method, scopes in false_positive_top10_lengths.items()}
    feature_result = {}
    for feature, counter in text_feature_acc.items():
        total = counter["denominator"]
        feature_result[feature] = {
            "gold_element_denominator": total,
            "gold_elements_with_feature": counter["true"],
            "gold_feature_rate": counter["true"] / total if total else None,
            "methods": {
                method: {
                    "feature_gold_elements": counter["true"],
                    "feature_gold_r10_hits": counter[method + "_hit"],
                    "feature_gold_r10_misses": counter[method + "_miss"],
                    "feature_gold_r10_hit_rate": counter[method + "_hit"] / counter["true"] if counter["true"] else None,
                    "no_feature_gold_elements": counter["false"],
                    "no_feature_gold_r10_hits": counter[method + "_no_feature_hit"],
                    "no_feature_gold_r10_misses": counter[method + "_no_feature_miss"],
                    "no_feature_gold_r10_hit_rate": counter[method + "_no_feature_hit"] / counter["false"] if counter["false"] else None,
                }
                for method in METHODS
            },
        }

    bm25_result = {
        "pool_definition": "per-DB joint table+column candidate pool for scoring; type-specific ranks are evaluated separately",
        "candidate_count_all": quantiles(bm25_overlap["all_candidates"]),
        "candidate_count_columns": quantiles(bm25_overlap["column_candidates"]),
        "query_token_count_after_frozen_tokenizer": quantiles(bm25_overlap["query_tokens"]),
        "candidate_count_with_nonzero_bm25_all": quantiles(bm25_overlap["all_nonzero"]),
        "candidate_count_with_nonzero_bm25_columns": quantiles(bm25_overlap["column_nonzero"]),
        "gold_column_elements_with_any_lexical_overlap": bm25_overlap["gold_overlap"],
        "gold_column_elements_total": bm25_overlap["gold_elements"],
        "gold_columns_ranked_below_10_by_bm25_with_no_overlap": bm25_overlap["gold_missed_s1_no_overlap"],
        "gold_columns_ranked_below_10_by_bm25_with_overlap": bm25_overlap["gold_missed_s1_with_overlap"],
        "tie_diagnostics_from_exact_replay": replay_summary["tie_diagnostics"]["S1_bm25"],
        "topk_boundary_ties": tie_boundary,
        "column_r10_gold_loss_main_category_counts": dict(bm25_lost_classes),
    }
    bm25_result["zero_score_candidates_all"] = quantiles([a - b for a, b in zip(bm25_overlap["all_candidates"], bm25_overlap["all_nonzero"])])
    bm25_result["zero_score_candidates_columns"] = quantiles([a - b for a, b in zip(bm25_overlap["column_candidates"], bm25_overlap["column_nonzero"])])
    bm25_result["question_tie_counts_sanity"] = {
        view: {"questions_with_ties": replay_summary["tie_diagnostics"]["S1_bm25"][view]["questions_with_ties"], "questions": EXPECTED["questions"]}
        for view in ("all", "table", "column")
    }

    database_delta = {}
    for db, per_method in replay_summary["per_database"].items():
        db_row = {}
        for method in ("S1_bm25", "S2_rrf"):
            base = per_method["methods"]["S0_cosine"]
            candidate = per_method["methods"][method]
            db_row[method] = {
                "column_r10_delta_pp": 100 * (candidate["column"]["recall@10"]["query_macro"] - base["column"]["recall@10"]["query_macro"]),
                "complete_2048_delta_pp": 100 * (candidate["budgets"]["2048"]["complete"]["query_macro"] - base["budgets"]["2048"]["complete"]["query_macro"]),
            }
        database_delta[db] = db_row

    return {
        "denominators": {"questions": len(questions), "databases": len(nodes_by_db), "column_eligible_questions": sum(bool(q["label"]["column_eligible"]) for q in questions), "column_ineligible_questions": sum(not bool(q["label"]["column_eligible"]) for q in questions), "column_gold_elements": sum(len(q["label"]["gold_column_ids"]) for q in questions if q["label"]["column_eligible"]), "non_saturated_databases": sorted(non_saturated), "non_saturated_questions": sum(q["db_id"] in non_saturated for q in questions), "non_saturated_column_eligible_questions": sum(q["db_id"] in non_saturated and bool(q["label"]["column_eligible"]) for q in questions), "schema_tokens_by_database": schema_tokens, "databases_whose_full_schema_fits_2048": sorted(db for db, token_count in schema_tokens.items() if token_count <= 2048)},
        "rank_bin_transitions": transition,
        "paired_rescue_damage": paired_result,
        "budget_selection": budget_result,
        "false_positive_column_top10_text_length_tokens": top10_lengths,
        "gold_column_schema_text_feature_strata": feature_result,
        "bm25_lexical_and_tie_audit": bm25_result,
        "database_paired_deltas_pp": database_delta,
        "automatic_error_classification": {
            "BM25_column_r10_gold_losses": dict(bm25_lost_classes),
            "scope_note": "Class labels are mechanical evidence categories. Positive lexical overlap ranked below the cutoff remains unresolved; schema-text correlations do not establish semantic mismatch or causal noise.",
            "not_identifiable_without_blind_human_review": ["semantic_mismatch", "gold_ambiguity", "causal_schema_text_noise"],
            "human_review_count": 0,
        },
    }


def pair_key(left: tuple[str, str], right: tuple[str, str]) -> tuple[tuple[str, str], tuple[str, str]]:
    return tuple(sorted((left, right)))


def schema_json_fk_pairs(schema: dict[str, Any]) -> set[tuple[tuple[str, str], tuple[str, str]]]:
    result = set()
    columns = schema["column_names_original"]
    tables = schema["table_names_original"]
    for left_index, right_index in schema.get("foreign_keys", []):
        left_table, left_col = columns[left_index]
        right_table, right_col = columns[right_index]
        if left_table < 0 or right_table < 0:
            continue
        result.add(pair_key((tables[left_table].casefold(), left_col.casefold()), (tables[right_table].casefold(), right_col.casefold())))
    return result


def canonical_join_id(row: dict[str, Any]) -> str:
    canonical = {
        "db_id": row["db_id"],
        "child_table": row["child_table"],
        "sqlite_constraint_id": row["sqlite_constraint_id"],
        "parent_table": row["parent_table"],
        "ordered_column_pairs": row["ordered_column_pairs"],
    }
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "join:" + hashlib.sha256(payload).hexdigest()


def build_fk_structures(fk_artifact: dict[str, Any], schemas: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, set[tuple[tuple[str, str], tuple[str, str]]]], dict[str, set[tuple[tuple[str, str], tuple[str, str]]]], dict[str, Any]]:
    schema_map = {schema["db_id"]: schema for schema in schemas}
    valid: dict[str, list[dict[str, Any]]] = {}
    json_pairs = {db: schema_json_fk_pairs(schema) for db, schema in schema_map.items()}
    sqlite_pairs: dict[str, set[tuple[tuple[str, str], tuple[str, str]]]] = {}
    id_list: list[str] = []
    database_summary: dict[str, Any] = {}
    for db, instances in fk_artifact["instances_private"].items():
        signatures = collections.Counter()
        sqlite_pairs[db] = set()
        valid[db] = []
        invalid_issues = collections.Counter()
        composites = implicit_count = 0
        for row in instances:
            expected_id = canonical_join_id(row)
            if row.get("join_instance_id") != expected_id:
                raise RuntimeError("A frozen JoinInstance ID does not match its canonical identity")
            id_list.append(expected_id)
            pairs = row.get("ordered_column_pairs", [])
            raw_pairs = row.get("raw_ordered_column_pairs", [])
            if len(pairs) != len(raw_pairs):
                raise RuntimeError("A JoinInstance lost ordered component pairs during FK normalization")
            if len(pairs) > 1:
                composites += 1
            implicit_count += int(bool(row.get("implicit_parent_key_resolved")))
            for issue in row.get("endpoint_issues", []):
                invalid_issues[issue] += 1
            if not row.get("valid_endpoints"):
                continue
            valid[db].append(row)
            signature = (row["child_table"].casefold(), row["parent_table"].casefold(), tuple((str(a).casefold(), str(b).casefold()) for a, b in pairs))
            signatures[signature] += 1
            for child, parent in pairs:
                sqlite_pairs[db].add(pair_key((row["child_table"].casefold(), str(child).casefold()), (row["parent_table"].casefold(), str(parent).casefold())))
        if len({row["join_instance_id"] for row in instances}) != len(instances):
            raise RuntimeError(f"Duplicate stable JoinInstance identity in {db}")
        database_summary[db] = {
            "sqlite_instances_raw": len(instances),
            "valid_join_instances": len(valid[db]),
            "invalid_join_instances": sum(not row.get("valid_endpoints") for row in instances),
            "composite_join_instances": composites,
            "implicit_parent_key_resolved_instances": implicit_count,
            "duplicate_valid_relation_signatures": sum(count - 1 for count in signatures.values() if count > 1),
            "json_fk_pairs": len(json_pairs[db]),
            "sqlite_fk_pairs_valid": len(sqlite_pairs[db]),
            "json_fk_pairs_missing_in_sqlite": len(json_pairs[db] - sqlite_pairs[db]),
            "sqlite_fk_pairs_missing_in_json": len(sqlite_pairs[db] - json_pairs[db]),
            "invalid_endpoint_issue_counts": dict(sorted(invalid_issues.items())),
        }
        archived = fk_artifact["per_database"][db]
        archived_to_rebuilt = {
            "schema_json_fk_pairs": "json_fk_pairs",
            "sqlite_fk_instances_raw": "sqlite_instances_raw",
            "valid_join_instances": "valid_join_instances",
            "composite_join_instances": "composite_join_instances",
            "invalid_join_instances": "invalid_join_instances",
            "duplicate_join_instance_signatures": "duplicate_valid_relation_signatures",
            "implicit_parent_key_instances": "implicit_parent_key_resolved_instances",
            "json_fk_pairs_missing_in_sqlite": "json_fk_pairs_missing_in_sqlite",
            "sqlite_fk_pairs_missing_in_json": "sqlite_fk_pairs_missing_in_json",
        }
        for archived_key, rebuilt_key in archived_to_rebuilt.items():
            if database_summary[db][rebuilt_key] != archived[archived_key]:
                raise RuntimeError(f"FK artifact aggregate mismatch in {db} for {archived_key}")
    ids_payload = json.dumps(sorted(id_list), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return valid, json_pairs, sqlite_pairs, {"per_database": database_summary, "raw_instances": len(id_list), "stable_ids_unique": len(set(id_list)), "stable_id_set_sha256": sha256_bytes(ids_payload)}


def parsed_join_diagnostics(sql: str, valid_fk: list[dict[str, Any]], raw_fk: list[dict[str, Any]], schema_fk: set[tuple[tuple[str, str], tuple[str, str]]], sqlite_fk: set[tuple[tuple[str, str], tuple[str, str]]]) -> list[dict[str, Any]]:
    try:
        import sqlglot
        from sqlglot import exp
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return []
    try:
        from sqlglot.optimizer.scope import traverse_scope
        scopes = list(traverse_scope(parsed))
    except Exception:
        scopes = []
    if not scopes:
        scopes = [type("ScopeLike", (), {"expression": parsed, "sources": {}})()]
    valid_by_pair: dict[frozenset[str], list[dict[str, Any]]] = collections.defaultdict(list)
    raw_by_pair: dict[frozenset[str], list[dict[str, Any]]] = collections.defaultdict(list)
    for instance in valid_fk:
        valid_by_pair[frozenset((instance["child_table"].casefold(), instance["parent_table"].casefold()))].append(instance)
    for instance in raw_fk:
        raw_by_pair[frozenset((instance["child_table"].casefold(), instance["parent_table"].casefold()))].append(instance)
    records = []
    for scope in scopes:
        expression = scope.expression
        source_map = {}
        for alias, source in (getattr(scope, "sources", {}) or {}).items():
            if isinstance(source, exp.Table):
                source_map[str(alias).casefold()] = str(source.name).casefold()
        local_tables = [table for table in expression.find_all(exp.Table) if table.find_ancestor(exp.Select) is expression] if hasattr(expression, "find_all") else []
        for table in local_tables:
            alias, name = str(table.alias_or_name).casefold(), str(table.name).casefold()
            if source_map.get(alias) in (None, name):
                source_map[alias] = name
        for join in expression.args.get("joins") or []:
            on_clause = join.args.get("on")
            if on_clause is None:
                continue
            equality_pairs = set()
            alias_failures = 0
            direct_equalities = 0
            for equality in on_clause.find_all(exp.EQ):
                left, right = equality.this, equality.expression
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                direct_equalities += 1
                left_alias, right_alias = str(left.table).casefold(), str(right.table).casefold()
                left_table, right_table = source_map.get(left_alias), source_map.get(right_alias)
                alias_failures += int(bool(left_alias) and left_table is None) + int(bool(right_alias) and right_table is None)
                if not left_table or not right_table:
                    continue
                if left_table != right_table:
                    equality_pairs.add(pair_key((left_table, str(left.name).casefold()), (right_table, str(right.name).casefold())))
            table_pairs = {frozenset((left[0], right[0])) for left, right in equality_pairs if left[0] != right[0]}
            exact_ids: set[str] = set()
            valid_overlaps: set[str] = set()
            invalid_metadata_overlap = False
            candidate_count_max = 0
            pair_has_candidate = False
            for table_pair in table_pairs:
                candidates = valid_by_pair.get(table_pair, [])
                raw_candidates = raw_by_pair.get(table_pair, [])
                candidate_count_max = max(candidate_count_max, len(candidates))
                pair_has_candidate = pair_has_candidate or bool(candidates)
                for instance in candidates:
                    expected_pairs = {pair_key((instance["child_table"].casefold(), str(child).casefold()), (instance["parent_table"].casefold(), str(parent).casefold())) for child, parent in instance["ordered_column_pairs"]}
                    overlap = expected_pairs & equality_pairs
                    if expected_pairs.issubset(equality_pairs) and expected_pairs:
                        exact_ids.add(instance["join_instance_id"])
                    elif overlap:
                        valid_overlaps.add(instance["join_instance_id"])
                for instance in raw_candidates:
                    raw_pairs = instance.get("raw_ordered_column_pairs", [])
                    raw_signature = {pair_key((instance["child_table"].casefold(), str(child).casefold()), (instance["parent_table"].casefold(), str(parent).casefold())) for child, parent in raw_pairs if child and parent}
                    invalid_metadata_overlap = invalid_metadata_overlap or bool(raw_signature & equality_pairs)
            if len(exact_ids) == 1:
                status = "uniquely_resolvable"
            elif len(exact_ids) > 1:
                status = "multiple_valid"
            elif valid_overlaps:
                status = "partial_or_invalid_metadata"
            elif not table_pairs:
                status = "unresolved_alias" if alias_failures else "unresolved_no_cross_table_equality"
            elif any(pair in schema_fk - sqlite_fk for pair in equality_pairs):
                status = "metadata_incomplete"
            elif invalid_metadata_overlap:
                status = "metadata_incomplete"
            elif pair_has_candidate:
                status = "column_pair_not_matching_fk"
            else:
                status = "non_fk_relation_unverified"
            records.append({"status": status, "has_multi_fk_candidate": candidate_count_max > 1, "alias_failures": alias_failures, "direct_equalities": direct_equalities})
    return records


def audit_fk_gate(args: argparse.Namespace, p1_5: Any) -> dict[str, Any]:
    fk_path = args.p1_5_run_dir / "fk_gate_private.json"
    p1_5_summary_path = args.p1_5_run_dir / "aggregate_summary.json"
    p1_5_run_start_path = args.p1_5_run_dir / "run_start.json"
    if not all(path.is_file() for path in (fk_path, p1_5_summary_path, p1_5_run_start_path)):
        raise FileNotFoundError("P1.5 FK gate artifacts are incomplete")
    p1_5_run = json.loads(p1_5_run_start_path.read_text(encoding="utf-8"))
    p1_5_summary = json.loads(p1_5_summary_path.read_text(encoding="utf-8"))
    if p1_5_run.get("run_id") != P1_5_RUN_ID or p1_5_run.get("state") != "completed":
        raise RuntimeError("P1.5 FK source artifact is not the registered completed run")
    artifact = json.loads(fk_path.read_text(encoding="utf-8"))
    dev_path = args.dataset_root / "dev.json"
    schema_path = args.dataset_root / "dev_tables.json"
    questions = json.loads(dev_path.read_text(encoding="utf-8"))
    schemas = json.loads(schema_path.read_text(encoding="utf-8"))
    if len(questions) != EXPECTED["questions"] or len(schemas) != EXPECTED["databases"]:
        raise RuntimeError("BIRD dev question/schema input denominator mismatch in FK audit")
    valid, json_pairs, sqlite_pairs, instance_summary = build_fk_structures(artifact, schemas)
    summary_by_db: dict[str, collections.Counter[str]] = {schema["db_id"]: collections.Counter() for schema in schemas}
    reason_counts: dict[str, collections.Counter[str]] = {schema["db_id"]: collections.Counter() for schema in schemas}
    multi_fk_query_ids: set[tuple[str, str]] = set()
    role_categories = {"uniquely_resolvable": 0, "multiple_valid": 0, "unresolvable": 0}
    parse_failures = no_on = query_with_on = 0
    fields = ("join_on_count", "join_without_on_count", "matched", "partial", "unmatched", "ambiguous", "role_candidate_joins", "resolved_table_pairs")
    for question_index, question in enumerate(questions):
        db = question["db_id"]
        sql = question.get("SQL", "")
        baseline = p1_5.golden_join_audit(sql, db, valid.get(db, []))
        parse_failures += int(not baseline["parse_ok"])
        query_with_on += int(baseline["join_on_count"] > 0)
        no_on += baseline["join_without_on_count"]
        for field in fields:
            summary_by_db[db][field] += int(baseline[field])
        diagnostics = parsed_join_diagnostics(sql, valid.get(db, []), artifact["instances_private"].get(db, []), json_pairs[db], sqlite_pairs[db])
        counted = collections.Counter(row["status"] for row in diagnostics)
        if baseline["parse_ok"] and sum(counted[key] for key in ("uniquely_resolvable", "multiple_valid", "partial_or_invalid_metadata", "unresolved_alias", "unresolved_no_cross_table_equality", "metadata_incomplete", "column_pair_not_matching_fk", "non_fk_relation_unverified")) != baseline["join_on_count"]:
            raise RuntimeError("FK reason classifier failed to account for each parsed JOIN ON clause")
        expected = collections.Counter({"uniquely_resolvable": baseline["matched"], "multiple_valid": baseline["ambiguous"], "partial_or_invalid_metadata": baseline["partial"]})
        for key, value in expected.items():
            if counted[key] != value:
                raise RuntimeError(f"FK instance classifier disagrees with archived P1.5 on {key}")
        reason_counts[db].update({key: value for key, value in counted.items() if key not in ("uniquely_resolvable", "multiple_valid", "partial_or_invalid_metadata")})
        if any(row["has_multi_fk_candidate"] for row in diagnostics):
            multi_fk_query_ids.add((db, str(question_index)))
        role_categories["uniquely_resolvable"] += baseline["matched"]
        role_categories["multiple_valid"] += baseline["ambiguous"]
        role_categories["unresolvable"] += baseline["partial"] + baseline["unmatched"]

    archived_gold = artifact["gold_joins"]
    total_fields = {field: sum(counter[field] for counter in summary_by_db.values()) for field in fields}
    for db, counts in summary_by_db.items():
        for field in fields:
            if counts[field] != int(archived_gold["per_database"][db][field]):
                raise RuntimeError(f"Recomputed JOIN coverage differs from frozen FK report for {db} / {field}")
    if total_fields != {key: int(value) for key, value in archived_gold["total"].items() if key in fields}:
        raise RuntimeError("Recomputed FK/JOIN coverage differs from frozen P1.5 aggregate")
    if sum(reason_counts[db][key] for db in reason_counts for key in reason_counts[db]) != total_fields["unmatched"]:
        raise RuntimeError("Unmatched JOIN reason categories do not sum to the archived denominator")
    if len(multi_fk_query_ids) != archived_gold["total"]["queries_with_multi_fk_table_pair"]:
        raise RuntimeError("Query-level multi-FK cohort differs from the frozen P1.5 aggregate")
    return {
        "source": {"p1_5_run_id": P1_5_RUN_ID, "p1_5_run_state": p1_5_run["state"], "fk_gate_private_sha256": sha256_file(fk_path), "dev_json_sha256": sha256_file(dev_path), "dev_tables_sha256": sha256_file(schema_path), "sqlglot_version": package_version("sqlglot")},
        "join_instance_identity": instance_summary,
        "per_database_fk_integrity": instance_summary["per_database"],
        "gold_join_coverage": {"questions": len(questions), "parse_failures": parse_failures, "queries_with_join_on": query_with_on, "join_without_on_count": no_on, "join_on_classification": role_categories, "archived_counts": total_fields, "queries_with_more_than_one_fk_candidate": len(multi_fk_query_ids), "multi_fk_candidate_query_overlap": "query count is a candidate-availability indicator, not a count of role-labeled examples"},
        "unmatched_join_reason_counts": {db: dict(counts) for db, counts in sorted(reason_counts.items())},
        "unmatched_join_reason_scope": "Each unmatched parsed JOIN ON is assigned one structural reason. A table pair absent from declared FK metadata is reported as a non-FK relation candidate; SQL validity/semantic legitimacy was not evaluated by executing SQL.",
        "role_label_gate": {"status": "NO-GO", "unique_fk_match_is_not_semantic_role_truth": True, "human_review_count": 0, "eligible_semantic_role_accuracy_denominator": 0},
        "input_hashes": {"p1_5_aggregate_sha256": sha256_file(p1_5_summary_path), "p1_5_run_start_sha256": sha256_file(p1_5_run_start_path)},
    }


def run() -> None:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to reuse existing output directory: {args.output_dir}")
    if args.mode == "full" and args.smoke_dir is None:
        raise RuntimeError("Full error audit requires a completed five-row smoke")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    source_commit = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    current_script_sha = sha256_file(Path(__file__).resolve())
    run_start = {
        "experiment_id": "p2a_5_error_audit_20261018_01",
        "run_id": args.run_id,
        "mode": args.mode,
        "state": "started",
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "audit_source_commit": source_commit,
        "audit_runner_sha256": current_script_sha,
        "p2a_source_commit": P2A_COMMIT,
        "p1_6_source_commit": P1_6_COMMIT,
        "protocol_sha256": sha256_file(P2A5_PROTOCOL),
        "resource_budget": {"gpu_seconds_max": 0, "cpu_seconds_max": MAX_CPU_SECONDS, "process_maxrss_gib": MAX_RSS_GIB, "max_cpu_threads": MAX_THREADS},
        "resource_snapshot": resource_snapshot(),
        "environment": {"python": platform.python_version(), "numpy": package_version("numpy"), "sqlglot": package_version("sqlglot"), "rank_bm25": package_version("rank-bm25")},
        "no_api_calls": True,
        "no_model_forward": True,
        "no_gpu_use": True,
        "no_sql_execution": True,
        "no_dependency_installation": True,
        "no_model_download": True,
    }
    write_json(args.output_dir / "run_start.json", run_start)
    try:
        p1 = load_module("p1_6_for_p2a5", P1_6_RUNNER)
        p2a = load_module("p2a_for_p2a5", P2A_RUNNER)
        p1_5 = load_module("p1_5_for_p2a5", P1_5_RUNNER)
        p2a_run_start, private_rows, p2a_aggregate = validate_p2a_artifacts(args)
        prepared, query_vectors, node_vectors, baseline_rows, input_evidence = load_and_validate_inputs(args, p1, p2a, p2a_run_start, p2a_aggregate)
        fk_path = args.p1_5_run_dir / "fk_gate_private.json"
        fk_artifact = json.loads(fk_path.read_text(encoding="utf-8"))
        fk_records = sum(len(rows) for rows in fk_artifact["instances_private"].values())
        if args.mode == "smoke":
            active, qvec, nvec = p2a.prepare_active_inputs(prepared, query_vectors, node_vectors, "smoke")
            _, baseline_smoke, _ = p1.score_snapshot(active, qvec, nvec)
            smoke_summary, smoke_rows = p2a.evaluate(active, qvec, nvec)
            p2a.assert_s0_parity(smoke_rows, baseline_smoke)
            if smoke_rows != private_rows[:5] or len(smoke_rows) != 5 or len({row["db_id"] for row in smoke_rows}) != 1:
                raise RuntimeError("Five-row replay does not match archived P2a outputs")
            if len(fk_artifact["instances_private"]) != EXPECTED["databases"] or fk_records != 103:
                raise RuntimeError("FK Gate smoke input does not match the frozen 11-database, 103-instance artifact")
            result = {"run_id": args.run_id, "status": "smoke_passed", "questions": 5, "databases": 1, "p2a_input_and_cache_hashes_match": True, "p2a_rows_replay_exact": True, "s0_parity": "PASS", "fk_instance_count": fk_records, "fk_database_count": len(fk_artifact["instances_private"]), "scorer_digest": smoke_summary["question_rows_digest_sha256"]}
            result_path = args.output_dir / "smoke_summary.json"
        else:
            smoke_path = args.smoke_dir / "smoke_summary.json"
            smoke_meta_path = args.smoke_dir / "run_start.json"
            if not smoke_path.is_file() or not smoke_meta_path.is_file():
                raise FileNotFoundError("Smoke summary or run metadata is missing")
            smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
            smoke_meta = json.loads(smoke_meta_path.read_text(encoding="utf-8"))
            if smoke.get("status") != "smoke_passed" or smoke.get("p2a_input_and_cache_hashes_match") is not True or smoke_meta.get("state") != "completed":
                raise RuntimeError("Full audit blocked because the registered smoke did not pass")
            replay_summary, replay_rows = p2a.evaluate(prepared, query_vectors, node_vectors)
            p2a.assert_s0_parity(replay_rows, baseline_rows)
            if replay_rows != private_rows:
                raise RuntimeError("Full P2a replay differs from the preserved per-question artifact")
            if replay_summary != p2a_aggregate["metrics"]:
                raise RuntimeError("Replayed P2a aggregate differs from archived P2a metrics")
            if json_digest(replay_rows) != p2a_aggregate["metrics"]["question_rows_digest_sha256"]:
                raise RuntimeError("P2a question-row digest differs from the archived aggregate")
            p1_5_module = p1_5
            fk_result = audit_fk_gate(args, p1_5_module)
            analysis = analyze_p2a(prepared, query_vectors, node_vectors, p1, p2a, replay_rows, replay_summary)
            result = {
                "experiment_id": "p2a_5_error_audit_20261018_01",
                "run_id": args.run_id,
                "status": "completed",
                "source_replay": {"p2a_run_id": P2A_RUN_ID, "p2a_commit": P2A_COMMIT, "p1_6_run_id": P1_6_RUN_ID, "p1_6_commit": P1_6_COMMIT, **input_evidence, "p2a_private_sha256": sha256_file(args.p2a_run_dir / "per_question_private.jsonl"), "p2a_aggregate_sha256": sha256_file(args.p2a_run_dir / "aggregate_summary.json"), "p2a_replay_rows_exact": True, "p2a_replay_aggregate_exact": True, "p2a_s0_parity": "PASS"},
                "p2a_gate_preserved": p2a_aggregate["exploratory_decision"]["decision"],
                "p2a_results": analysis,
                "fk_join_instance_gate": fk_result,
                "decision": {"p2a_original_no_go_changed": False, "new_scorer_or_model_run": False, "p2b_schema_ablation_authorized_by_this_audit": False, "role_path_or_gnn_authorized": False, "conclusion": "diagnostic evidence only; no new ranking method success claim"},
            }
            result_path = args.output_dir / "aggregate_summary.json"
        elapsed = time.perf_counter() - started_wall
        cpu_seconds = time.process_time() - started_cpu
        maxrss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
        if cpu_seconds > MAX_CPU_SECONDS or maxrss_gib > MAX_RSS_GIB:
            raise RuntimeError(f"P2a.5 resource budget exceeded: cpu={cpu_seconds:.2f}s rss={maxrss_gib:.2f}GiB")
        write_json(result_path, result)
        run_start.update({"state": "completed", "finished_elapsed_wall_seconds": elapsed, "cpu_seconds_process": cpu_seconds, "process_maxrss_gib": maxrss_gib, "result_sha256": sha256_file(result_path)})
        write_json(args.output_dir / "run_start.json", run_start)
        print(json.dumps({"run_id": args.run_id, "mode": args.mode, "status": "completed", "elapsed_wall_seconds": elapsed, "cpu_seconds_process": cpu_seconds, "process_maxrss_gib": maxrss_gib, "result_sha256": run_start["result_sha256"]}, ensure_ascii=False))
    except Exception as error:
        run_start.update({"state": "failed", "failure_type": type(error).__name__, "failure_message": str(error), "finished_elapsed_wall_seconds": time.perf_counter() - started_wall, "cpu_seconds_process": time.process_time() - started_cpu})
        write_json(args.output_dir / "run_start.json", run_start)
        raise


if __name__ == "__main__":
    run()
