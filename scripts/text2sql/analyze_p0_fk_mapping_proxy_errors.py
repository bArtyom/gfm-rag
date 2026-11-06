#!/usr/bin/env python3
"""Descriptive, privacy-preserving error analysis of a frozen FK ranking pilot."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import statistics
import subprocess
import time
from typing import Any


METHODS = ("g_reasoner", "dense_cosine", "bm25_okapi", "stable_mapping_id_order")
EXPECTED_INPUT_HASHES_COMMON = {
    "private_manifest": "14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7",
    "reviewer_a": "f3d2beb21290c49790679e53ac0bf8dc50084b7b34ee228843f06330ac120883",
    "reviewer_b": "2b49a5772f061ed70f02ea21811e392fd6afd086fa7030aca9fe737c2c8af077",
    "reviewer_c": "88c5b79785af76896055378ece4776b523bdb036588304cd63305db51a10d333",
    "split_manifest": "40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0",
}
EXPECTED_PREDICTIONS_HASHES = {
    "smoke": "483842d1349f4f820ee11447ebff3692acbd6ef87bf33acf6c97cc89356004f4",
    "full": "d06f07b2b1000e40dbc0614e9bdbe224a79130010011721b97eccaf3dd9b2484",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--reviewer-c", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            row = json.loads(line)
            pair_id = row.get("pair_id")
            if not isinstance(pair_id, str) or pair_id in rows:
                raise ValueError(f"invalid or duplicate row key at line {line_number}")
            rows[pair_id] = row
    return rows


def label_for_reviewer(row: dict[str, Any]) -> tuple[str, tuple[str, ...], int] | None:
    if row.get("valid") is not True:
        return None
    answer = row.get("answer")
    if not isinstance(answer, dict):
        return None
    decision = answer.get("decision")
    accepted = answer.get("accepted_mapping_ids")
    confidence = answer.get("confidence")
    valid_decisions = {"single_mapping", "multiple_mappings", "cannot_determine", "no_declared_fk", "other"}
    if decision not in valid_decisions or not isinstance(accepted, list):
        return None
    if any(not isinstance(value, str) for value in accepted) or len(accepted) != len(set(accepted)):
        return None
    if type(confidence) is not int or confidence not in {1, 2, 3}:
        return None
    if decision == "single_mapping" and len(accepted) != 1:
        return None
    if decision == "multiple_mappings" and len(accepted) < 2:
        return None
    if decision in {"cannot_determine", "no_declared_fk"} and accepted:
        return None
    return decision, tuple(sorted(accepted)), confidence


def build_proxy_labels(
    reviewer_rows: dict[str, dict[str, dict[str, Any]]],
    candidate_ids: dict[str, set[str]],
) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = {}
    for pair_id, candidates in candidate_ids.items():
        votes: dict[tuple[str, tuple[str, ...]], list[int]] = defaultdict(list)
        for rows in reviewer_rows.values():
            label = label_for_reviewer(rows[pair_id])
            if label is None:
                continue
            decision, accepted, confidence = label
            if not set(accepted) <= candidates:
                raise ValueError("proxy label contains a noncandidate mapping")
            votes[(decision, accepted)].append(confidence)
        majority = [
            (label, confidences)
            for label, confidences in votes.items()
            if sum(confidence >= 2 for confidence in confidences) >= 2
        ]
        if len(majority) != 1:
            continue
        (decision, accepted), _ = majority[0]
        if decision in {"single_mapping", "multiple_mappings"} and accepted:
            labels[pair_id] = set(accepted)
    return labels


def candidate_structure(
    candidate_ids: list[str], identity_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    mapping_columns: list[dict[str, set[str]]] = []
    has_composite = False
    endpoints: set[str] = set()
    for mapping_id in candidate_ids:
        row = identity_by_id[mapping_id]
        identity = row["identity"]
        if not isinstance(identity, list) or len(identity) != 4:
            raise ValueError("unexpected frozen FK identity shape")
        child_table, column_pairs, parent_table = str(identity[1]), identity[2], str(identity[3])
        if not isinstance(column_pairs, list) or not column_pairs:
            raise ValueError("empty or invalid FK column-pair list")
        has_composite = has_composite or len(column_pairs) > 1
        current: dict[str, set[str]] = {child_table: set(), parent_table: set()}
        for pair in column_pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("invalid ordered FK column pair")
            current[child_table].add(str(pair[0]))
            current[parent_table].add(str(pair[1]))
        endpoints.update(current)
        mapping_columns.append(current)

    if len(endpoints) != 2:
        raise ValueError("candidate mappings do not share exactly two table endpoints")
    ordered_endpoints = sorted(endpoints)
    max_shared_endpoints = 0
    for left_index, left in enumerate(mapping_columns):
        for right in mapping_columns[left_index + 1:]:
            shared = sum(bool(left[table] & right[table]) for table in ordered_endpoints)
            max_shared_endpoints = max(max_shared_endpoints, shared)
    overlap = {0: "none", 1: "one_endpoint", 2: "both_endpoints"}[max_shared_endpoints]
    return {
        "candidate_count": len(candidate_ids),
        "accepted_set_size": None,
        "has_composite_fk": has_composite,
        "column_overlap": overlap,
    }


def stable_rank(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda mapping_id: (-scores[mapping_id], mapping_id))


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"n": len(rows), "methods": {}}
    for method in METHODS:
        accepted_at_1 = accepted_at_3 = 0
        reciprocal_ranks: list[float] = []
        first_accepted_ranks: list[int] = []
        positive_margin_count = zero_margin_count = negative_margin_count = 0
        for row in rows:
            ranking = row["ranked_mapping_ids"][method]
            accepted = row["accepted_mapping_ids"]
            accepted_ranks = [index + 1 for index, mapping_id in enumerate(ranking) if mapping_id in accepted]
            if not accepted_ranks:
                raise ValueError("accepted mapping is missing from ranking")
            accepted_at_1 += int(ranking[0] in accepted)
            accepted_at_3 += int(min(accepted_ranks) <= 3)
            reciprocal_ranks.append(1.0 / min(accepted_ranks))
            first_accepted_ranks.append(min(accepted_ranks))
            scores = row["candidate_scores"][method]
            best_accepted = max(scores[mapping_id] for mapping_id in accepted)
            rejected = [score for mapping_id, score in scores.items() if mapping_id not in accepted]
            if not rejected:
                raise ValueError("primary set unexpectedly has no rejected candidate")
            margin = best_accepted - max(rejected)
            positive_margin_count += int(margin > 0)
            zero_margin_count += int(margin == 0)
            negative_margin_count += int(margin < 0)
        denominator = len(rows)
        result["methods"][method] = {
            "accepted_at_1": accepted_at_1,
            "accepted_at_3": accepted_at_3,
            "mrr_first_accepted": round(sum(reciprocal_ranks) / denominator, 6) if denominator else None,
            "first_accepted_rank": {
                "mean": round(sum(first_accepted_ranks) / denominator, 6) if denominator else None,
                "median": statistics.median(first_accepted_ranks) if denominator else None,
            },
            "accepted_vs_rejected_score_margin": {
                "positive": positive_margin_count,
                "zero": zero_margin_count,
                "negative": negative_margin_count,
            },
        }
    paired = {"g_reasoner_only_correct": 0, "dense_only_correct": 0, "both_correct": 0, "both_wrong": 0}
    for row in rows:
        accepted = row["accepted_mapping_ids"]
        gfm_ok = row["ranked_mapping_ids"]["g_reasoner"][0] in accepted
        dense_ok = row["ranked_mapping_ids"]["dense_cosine"][0] in accepted
        paired["g_reasoner_only_correct"] += int(gfm_ok and not dense_ok)
        paired["dense_only_correct"] += int(dense_ok and not gfm_ok)
        paired["both_correct"] += int(gfm_ok and dense_ok)
        paired["both_wrong"] += int(not gfm_ok and not dense_ok)
    paired["net_rescue"] = paired["g_reasoner_only_correct"] - paired["dense_only_correct"]
    result["paired_g_reasoner_vs_dense"] = paired
    return result


def grouped_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["strata"][field])].append(row)
    public_groups: dict[str, Any] = {}
    small_rows: list[dict[str, Any]] = []
    for name in sorted(groups):
        group = groups[name]
        if len(group) < 5:
            small_rows.extend(group)
        else:
            public_groups[name] = summarize_rows(group)
    if small_rows:
        public_groups["small_n_merged"] = summarize_rows(small_rows)
    return public_groups


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    cpu_started = time.process_time()
    inputs = {
        "private_predictions": args.predictions,
        "private_manifest": args.private_manifest,
        "reviewer_a": args.reviewer_a,
        "reviewer_b": args.reviewer_b,
        "reviewer_c": args.reviewer_c,
        "split_manifest": args.split_manifest,
    }
    actual_hashes = {name: sha256_file(path) for name, path in inputs.items()}
    expected_hashes = {"private_predictions": EXPECTED_PREDICTIONS_HASHES[args.mode], **EXPECTED_INPUT_HASHES_COMMON}
    if actual_hashes != expected_hashes:
        raise ValueError("frozen input SHA-256 mismatch")

    predictions = read_jsonl(args.predictions)
    reviewer_rows = {
        "A": read_jsonl(args.reviewer_a),
        "B": read_jsonl(args.reviewer_b),
        "C": read_jsonl(args.reviewer_c),
    }
    manifest = json.loads(args.private_manifest.read_text(encoding="utf-8"))
    split = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    manifest_rows = {row["pair_id"]: row for row in manifest["selected_cases_private"]}
    candidate_ids = {pair_id: set(row["candidate_mapping_ids"]) for pair_id, row in predictions.items()}
    if any(not set(predictions) <= set(rows) for rows in reviewer_rows.values()):
        raise ValueError("review output does not cover selected predictions")
    if not set(predictions) <= set(manifest_rows):
        raise ValueError("manifest does not cover selected predictions")

    labels = build_proxy_labels(reviewer_rows, candidate_ids)
    smoke_pairs = set(split["smoke_pair_ids"])
    full_pairs = set(split["full_pair_ids"])
    if smoke_pairs & full_pairs or smoke_pairs | full_pairs != set(reviewer_rows["A"]):
        raise ValueError("frozen Smoke/Full partition mismatch")
    if len(smoke_pairs) != 5 or len(full_pairs) != 55:
        raise ValueError("frozen partition counts changed")
    selected_pairs = smoke_pairs if args.mode == "smoke" else full_pairs
    if set(predictions) != selected_pairs:
        raise ValueError("selected prediction file does not match the frozen mode split")

    primary_rows: list[dict[str, Any]] = []
    adjudicable_count = 0
    candidate_count_scored = 0
    for pair_id in sorted(selected_pairs):
        prediction = predictions[pair_id]
        identities = {row["mapping_id"]: row for row in manifest_rows[pair_id]["mapping_identities"]}
        structural = candidate_structure(prediction["candidate_mapping_ids"], identities)
        candidate_count_scored += structural["candidate_count"]
        for method in METHODS:
            if set(prediction["ranked_mapping_ids"][method]) != candidate_ids[pair_id]:
                raise ValueError("method ranking does not cover the frozen candidate set")
            if set(prediction["candidate_scores"][method]) != candidate_ids[pair_id]:
                raise ValueError("method scores do not cover the frozen candidate set")
        if pair_id not in labels:
            continue
        accepted = labels[pair_id]
        candidates = candidate_ids[pair_id]
        if not accepted:
            continue
        adjudicable_count += 1
        if args.mode == "smoke":
            continue
        if accepted == candidates:
            continue
        structural["accepted_set_size"] = "single" if len(accepted) == 1 else "multiple"
        primary_rows.append({
            "accepted_mapping_ids": accepted,
            "candidate_scores": prediction["candidate_scores"],
            "ranked_mapping_ids": prediction["ranked_mapping_ids"],
            "strata": structural,
        })

    if args.mode == "smoke":
        summary = {
            "experiment_id": "p0_fk_mapping_proxy_error_analysis_20261106_01",
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "SMOKE_PASS",
            "analysis_type": "operational_contract_check_only",
            "counts": {
                "pairs_processed": len(predictions),
                "candidate_mappings_scored": candidate_count_scored,
                "proxy_labels_available": adjudicable_count,
            },
            "input_sha256": actual_hashes,
            "privacy": {
                "contains_case_ids": False,
                "contains_question_text": False,
                "contains_database_names": False,
                "contains_mapping_ids_or_identities": False,
                "contains_raw_model_outputs": False,
                "contains_gold_sql_or_execution_results": False,
            },
            "resources": {
                "wall_seconds": round(time.monotonic() - started, 6),
                "process_cpu_seconds": round(time.process_time() - cpu_started, 6),
                "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
                "gpu_or_model_inference": False,
                "external_api_requests": 0,
            },
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        output_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output.exists():
            raise FileExistsError("refusing to overwrite analysis output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(output_text)
        print(json.dumps({"status": summary["status"], "run_id": args.run_id, "counts": summary["counts"], "output_sha256": sha256_file(args.output)}, ensure_ascii=False, sort_keys=True))
        return

    database_count = len({str(manifest_rows[pair_id]["private_db_id"]) for pair_id in selected_pairs})
    if adjudicable_count != 51 or len(primary_rows) != 38 or database_count != 4:
        raise ValueError("proxy label denominators differ from the frozen pilot")

    overall = summarize_rows(primary_rows)
    expected_at_1 = {"g_reasoner": 7, "dense_cosine": 27, "bm25_okapi": 22, "stable_mapping_id_order": 22}
    if any(overall["methods"][method]["accepted_at_1"] != expected for method, expected in expected_at_1.items()):
        raise ValueError("frozen Accepted@1 metrics differ from the source pilot")
    if overall["paired_g_reasoner_vs_dense"] != {
        "g_reasoner_only_correct": 1,
        "dense_only_correct": 21,
        "both_correct": 6,
        "both_wrong": 10,
        "net_rescue": -20,
    }:
        raise ValueError("paired frozen comparison mismatch")

    strata_fields = ("candidate_count", "accepted_set_size", "has_composite_fk", "column_overlap")
    summary = {
        "experiment_id": "p0_fk_mapping_proxy_error_analysis_20261106_01",
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "ANALYSIS_COMPLETE",
        "analysis_type": "read_only_descriptive_proxy_label_error_analysis",
        "source_pilot_run_id": "p0_fk_mapping_model_proxy_rank_pilot_20261106_full_002",
        "denominators": {
            "smoke_pairs_excluded": len(smoke_pairs),
            "full_pairs": len(full_pairs),
            "adjudicable_full": adjudicable_count,
            "distinguishable_primary": len(primary_rows),
            "anonymous_database_count": database_count,
        },
        "overall": overall,
        "strata": {field: grouped_summary(primary_rows, field) for field in strata_fields},
        "input_sha256": actual_hashes,
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "privacy": {
            "contains_case_ids": False,
            "contains_question_text": False,
            "contains_database_names": False,
            "contains_mapping_ids_or_identities": False,
            "contains_raw_model_outputs": False,
            "contains_gold_sql_or_execution_results": False,
            "small_cells_suppressed_or_merged": True,
        },
        "resources": {
            "wall_seconds": round(time.monotonic() - started, 6),
            "process_cpu_seconds": round(time.process_time() - cpu_started, 6),
            "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "gpu_or_model_inference": False,
            "external_api_requests": 0,
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output.exists():
        raise FileExistsError("refusing to overwrite analysis output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(output_text)
    print(json.dumps({
        "status": summary["status"],
        "run_id": args.run_id,
        "denominators": summary["denominators"],
        "g_reasoner_accepted_at_1": overall["methods"]["g_reasoner"]["accepted_at_1"],
        "dense_accepted_at_1": overall["methods"]["dense_cosine"]["accepted_at_1"],
        "net_rescue": overall["paired_g_reasoner_vs_dense"]["net_rescue"],
        "output_sha256": sha256_file(args.output),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
