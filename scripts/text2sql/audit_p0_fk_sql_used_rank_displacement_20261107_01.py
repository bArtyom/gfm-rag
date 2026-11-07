#!/usr/bin/env python3
"""Retrospective, CPU-only rank-position attribution for a frozen FK rank run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIMENT_ID = "p0_fk_sql_used_rank_displacement_20261107_01"
METHODS = ("g_reasoner", "dense_cosine", "bm25_okapi", "stable_mapping_id_order")
STAGES = {
    "smoke": "p0_fk_sql_used_rank_displacement_20261107_01_smoke_001",
    "full": "p0_fk_sql_used_rank_displacement_20261107_01_full_001",
}


class AuditError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError("JSON_ROOT_NOT_OBJECT")
    return value


def write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def target_rank(ranking: list[str], targets: set[str]) -> int | None:
    for rank, candidate_id in enumerate(ranking, start=1):
        if candidate_id in targets:
            return rank
    return None


def rank_bin(rank: int | None) -> str:
    if rank is None:
        return "target_absent"
    if rank == 1:
        return "rank_1"
    if rank == 2:
        return "rank_2"
    if rank == 3:
        return "rank_3"
    return "rank_4_plus"


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"n": len(rows)}
    method_summary: dict[str, Any] = {}
    for method in METHODS:
        ranks = [row["target_ranks"][method] for row in rows]
        bins = Counter(rank_bin(rank) for rank in ranks)
        method_summary[method] = {
            "target_rank_distribution": {key: bins[key] for key in ("rank_1", "rank_2", "rank_3", "rank_4_plus", "target_absent")},
            "top1_hits": sum(rank == 1 for rank in ranks),
            "top3_hits": sum(rank is not None and rank <= 3 for rank in ranks),
        }
    result["methods"] = method_summary

    paired = Counter()
    rank_delta = Counter()
    dense_only_g_rank = Counter()
    g_only_dense_rank = Counter()
    for row in rows:
        g_rank = row["target_ranks"]["g_reasoner"]
        d_rank = row["target_ranks"]["dense_cosine"]
        g_top1 = g_rank == 1
        d_top1 = d_rank == 1
        if g_top1 and d_top1:
            paired["both_top1_correct"] += 1
        elif g_top1:
            paired["g_reasoner_only_top1_correct"] += 1
            g_only_dense_rank[rank_bin(d_rank)] += 1
        elif d_top1:
            paired["dense_only_top1_correct"] += 1
            dense_only_g_rank[rank_bin(g_rank)] += 1
        else:
            paired["neither_top1_correct"] += 1
        if g_rank is not None and d_rank is not None:
            if g_rank < d_rank:
                rank_delta["g_reasoner_better_rank"] += 1
            elif g_rank > d_rank:
                rank_delta["dense_better_rank"] += 1
            else:
                rank_delta["same_target_rank"] += 1

    dense_only_n = paired["dense_only_top1_correct"]
    near_miss_n = dense_only_g_rank["rank_2"] + dense_only_g_rank["rank_3"]
    near_miss_rate = near_miss_n / dense_only_n if dense_only_n else None
    if dense_only_n == 0:
        decision = "INCONCLUSIVE_NO_DENSE_ONLY_TOP1_CASES"
    elif near_miss_rate >= 0.50:
        decision = "NEAR_MISS_SIGNAL"
    elif near_miss_rate < 0.20:
        decision = "NO_NEAR_MISS_SIGNAL"
    else:
        decision = "MIXED_NEAR_MISS_PATTERN"
    result["g_reasoner_vs_dense"] = {
        "top1_paired_counts": {key: paired[key] for key in ("both_top1_correct", "g_reasoner_only_top1_correct", "dense_only_top1_correct", "neither_top1_correct")},
        "paired_best_target_rank_order": {key: rank_delta[key] for key in ("g_reasoner_better_rank", "same_target_rank", "dense_better_rank")},
        "when_dense_only_top1_correct_g_reasoner_rank": {key: dense_only_g_rank[key] for key in ("rank_2", "rank_3", "rank_4_plus", "target_absent")},
        "when_g_reasoner_only_top1_correct_dense_rank": {key: g_only_dense_rank[key] for key in ("rank_2", "rank_3", "rank_4_plus", "target_absent")},
        "dense_only_g_rank_2_or_3_n": near_miss_n,
        "dense_only_top1_n": dense_only_n,
        "dense_only_near_miss_rate": near_miss_rate,
        "predeclared_diagnostic_decision": decision,
        "decision_rule": "NEAR_MISS_SIGNAL if at least 50% of Dense-only Top-1 wins place a valid SQL-used target at G-reasoner rank 2 or 3; NO_NEAR_MISS_SIGNAL if below 20%; otherwise MIXED. This is descriptive and cannot authorize same-BIRD-dev retuning.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--upstream-run-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    config_path = args.config.resolve()
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    predictions_path = args.predictions.resolve()
    upstream_run_manifest_path = args.upstream_run_manifest.resolve()
    output_dir = args.output_dir.resolve()

    config_sha = sha256_file(config_path)
    if config_sha != args.expected_config_sha256:
        raise AuditError("CONFIG_SHA256_MISMATCH")
    config = read_json(config_path)
    if config.get("experiment_id") != EXPERIMENT_ID:
        raise AuditError("EXPERIMENT_ID_MISMATCH")
    max_cpu_threads = int(config["resources"]["cpu_threads_max"])
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        allowed_cpus = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, set(allowed_cpus[:max_cpu_threads]))
    if config.get("run_ids", {}).get(args.mode) != args.run_id or STAGES[args.mode] != args.run_id:
        raise AuditError("RUN_ID_MISMATCH")
    runner_sha = sha256_file(Path(__file__).resolve())
    if runner_sha != config.get("analysis_runner_sha256"):
        raise AuditError("RUNNER_SHA256_MISMATCH")

    head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if head != args.expected_commit:
        raise AuditError("SOURCE_COMMIT_MISMATCH")
    if config.get("repository", {}).get("branch") != subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"], check=True, capture_output=True, text=True
    ).stdout.strip():
        raise AuditError("SOURCE_BRANCH_MISMATCH")

    input_paths = {
        "manifest": manifest_path,
        "predictions": predictions_path,
        "upstream_run_manifest": upstream_run_manifest_path,
    }
    expected_hashes = config["inputs"]
    actual_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    for name, actual in actual_hashes.items():
        if actual != expected_hashes[name]["sha256"]:
            raise AuditError(f"{name.upper()}_SHA256_MISMATCH")
    upstream_run_manifest = read_json(upstream_run_manifest_path)
    if upstream_run_manifest.get("status") != "FULL_COMPLETE":
        raise AuditError("UPSTREAM_RANK_RUN_NOT_FULL_COMPLETE")
    if upstream_run_manifest.get("config_sha256") != config["inputs"]["upstream_config_sha256"]:
        raise AuditError("UPSTREAM_CONFIG_RECEIPT_MISMATCH")
    if upstream_run_manifest.get("source_commit") != config["inputs"]["upstream_source_commit"]:
        raise AuditError("UPSTREAM_SOURCE_COMMIT_MISMATCH")
    if upstream_run_manifest.get("prepared_manifest_source_commit") != config["inputs"]["prepared_manifest_source_commit"]:
        raise AuditError("PREPARED_MANIFEST_SOURCE_COMMIT_MISMATCH")
    if upstream_run_manifest.get("private_predictions_sha256") != actual_hashes["predictions"]:
        raise AuditError("UPSTREAM_PREDICTION_RECEIPT_MISMATCH")
    if upstream_run_manifest.get("prepared_manifest_sha256") != actual_hashes["manifest"]:
        raise AuditError("UPSTREAM_MANIFEST_RECEIPT_MISMATCH")
    if upstream_run_manifest.get("run_id") != config["inputs"]["upstream_run_id"]:
        raise AuditError("UPSTREAM_RUN_ID_MISMATCH")

    private_root = Path(config["paths"]["private_results_root"]).resolve()
    if output_dir.parent != private_root or output_dir.name not in {"smoke_001", "full_001"}:
        raise AuditError("OUTPUT_PATH_OUTSIDE_FROZEN_ROOT")
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir.parent, 0o700)
    if output_dir.exists():
        raise AuditError("OUTPUT_DIR_ALREADY_EXISTS")
    output_dir.mkdir(mode=0o700)
    os.chmod(output_dir, 0o700)

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    try:
        manifest = read_json(manifest_path)
        units = manifest.get("units")
        full_ids = manifest.get("full_unit_ids")
        if not isinstance(units, dict) or not isinstance(full_ids, list):
            raise AuditError("PRIVATE_MANIFEST_SHAPE_MISMATCH")
        if len(full_ids) != config["sample"]["full_units"]:
            raise AuditError("FULL_UNIT_COUNT_MISMATCH")

        predictions: dict[str, dict[str, Any]] = {}
        with predictions_path.open("r", encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    record = json.loads(line)
                    pair_id = str(record["pair_id"])
                    if pair_id in predictions:
                        raise AuditError("DUPLICATE_PREDICTION_PAIR_ID")
                    predictions[pair_id] = record

        full_id_set = {str(item) for item in full_ids}
        if len(full_id_set) != config["sample"]["full_units"]:
            raise AuditError("DUPLICATE_FULL_UNIT_ID")
        if set(predictions) != full_id_set:
            raise AuditError("FULL_PREDICTION_COVERAGE_MISMATCH")

        stable_ids = sorted(full_id_set, key=lambda item: hashlib.sha256(f'{config["sample"]["seed"]}|{EXPERIMENT_ID}|{item}'.encode()).hexdigest())
        selected_ids = stable_ids[: config["sample"]["smoke_units"]] if args.mode == "smoke" else stable_ids
        db_names = sorted({str(units[item]["db_id"]) for item in selected_ids})
        db_label = {name: f"db_{index:02d}" for index, name in enumerate(db_names, start=1)}
        rows: list[dict[str, Any]] = []
        target_total = 0
        target_candidate_total = 0
        target_candidate_unit_count = 0
        for unit_id in selected_ids:
            unit = units.get(unit_id)
            record = predictions[unit_id]
            if not isinstance(unit, dict):
                raise AuditError("FULL_UNIT_MISSING_FROM_MANIFEST")
            if unit.get("unit_id") != unit_id or record.get("pair_id") != unit_id:
                raise AuditError("PREDICTION_MANIFEST_IDENTITY_MISMATCH")
            target_ids = {str(item) for item in unit.get("sql_used_mapping_ids", [])}
            candidate_ids = {str(item["mapping_id"]) for item in unit.get("candidate_mappings", [])}
            if len(candidate_ids) != len(unit.get("candidate_mappings", [])):
                raise AuditError("DUPLICATE_CANDIDATE_MAPPING_ID")
            candidate_targets = target_ids & candidate_ids
            target_total += len(target_ids)
            target_candidate_total += len(candidate_targets)
            target_candidate_unit_count += bool(candidate_targets)

            rankings = record.get("ranked_mapping_ids")
            if not isinstance(rankings, dict) or set(rankings) != set(METHODS):
                raise AuditError("RANKING_METHOD_SET_MISMATCH")
            target_ranks: dict[str, int | None] = {}
            for method in METHODS:
                ranking = [str(item) for item in rankings[method]]
                if len(ranking) != len(candidate_ids) or len(set(ranking)) != len(ranking) or set(ranking) != candidate_ids:
                    raise AuditError("RANKING_CANDIDATE_UNIVERSE_MISMATCH")
                target_ranks[method] = target_rank(ranking, candidate_targets)
            candidate_count = len(candidate_ids)
            candidate_group = "2" if candidate_count == 2 else "3" if candidate_count == 3 else "4_plus"
            rows.append({
                "db_label": db_label[str(unit["db_id"])],
                "candidate_group": candidate_group,
                "candidate_count": candidate_count,
                "target_ranks": target_ranks,
            })

        overall = summarize_group(rows)
        by_candidate_group = {group: summarize_group([row for row in rows if row["candidate_group"] == group]) for group in ("2", "3", "4_plus") if any(row["candidate_group"] == group for row in rows)}
        by_database = {database: summarize_group([row for row in rows if row["db_label"] == database]) for database in sorted({row["db_label"] for row in rows})}
        public_metrics = {
            "n_units": len(rows),
            "target_mapping_count": target_total,
            "target_mappings_present_in_candidate_universe": target_candidate_total,
            "units_with_at_least_one_target_in_candidate_universe": target_candidate_unit_count,
            "overall": overall,
            "by_candidate_count": by_candidate_group,
            "by_anonymous_database": by_database,
        }
        wall_seconds = time.perf_counter() - started_wall
        process_cpu_seconds = time.process_time() - started_cpu
        peak_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        if wall_seconds > config["resources"]["max_wall_seconds"]:
            raise AuditError("WALL_TIME_BUDGET_EXCEEDED")
        if peak_rss_gib > config["resources"]["max_peak_rss_gib"]:
            raise AuditError("PEAK_RSS_BUDGET_EXCEEDED")
        result = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "SMOKE_COMPLETE" if args.mode == "smoke" else "FULL_COMPLETE",
            "source_commit": head,
            "config_sha256": config_sha,
            "analysis_runner_sha256": runner_sha,
            "upstream_run_id": upstream_run_manifest["run_id"],
            "upstream_source_commit": upstream_run_manifest["source_commit"],
            "input_sha256": actual_hashes,
            "metrics": public_metrics,
            "resource_usage": {
                "wall_seconds": wall_seconds,
                "process_cpu_seconds": process_cpu_seconds,
                "peak_rss_gib": peak_rss_gib,
                "cpu_affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                "gpu_calls": 0,
                "model_calls": 0,
                "external_api_calls": 0,
            },
        }
        write_private_json(output_dir / "aggregate_summary.json", result)
        print(json.dumps({
            "status": result["status"],
            "run_id": args.run_id,
            "n_units": len(rows),
            "target_mappings_present_in_candidates": target_candidate_total,
            "g_reasoner_top1": overall["methods"]["g_reasoner"]["top1_hits"],
            "dense_top1": overall["methods"]["dense_cosine"]["top1_hits"],
            "dense_only_near_miss_rate": overall["g_reasoner_vs_dense"]["dense_only_near_miss_rate"],
        }, ensure_ascii=False, sort_keys=True))
    except Exception as error:
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "FAILED",
            "source_commit": head,
            "config_sha256": config_sha,
            "analysis_runner_sha256": runner_sha,
            "error_class": type(error).__name__,
            "error_code": error.code if isinstance(error, AuditError) else "UNEXPECTED_ERROR",
        }
        write_private_json(output_dir / "failure_receipt.json", failure)
        raise


if __name__ == "__main__":
    main()
