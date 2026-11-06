#!/usr/bin/env python3
"""Compute a secondary model-proxy ranking view from already frozen scores."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_p0_fk_mapping_model_proxy_rank_pilot as rank_utils  # noqa: E402


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            row = json.loads(line)
            unit_id = row.get("pair_id")
            if not isinstance(unit_id, str) or unit_id in result:
                raise ValueError(f"invalid or duplicate row at line {line_no}")
            result[unit_id] = row
    return result


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rank-summary", type=Path, required=True)
    parser.add_argument("--rank-predictions", type=Path, required=True)
    parser.add_argument("--review-summary", type=Path, required=True)
    parser.add_argument("--review-consensus", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")
    rank_summary = json.loads(args.rank_summary.read_text(encoding="utf-8"))
    review_summary = json.loads(args.review_summary.read_text(encoding="utf-8"))
    consensus_payload = json.loads(args.review_consensus.read_text(encoding="utf-8"))
    prepared = json.loads(args.prepared_manifest.read_text(encoding="utf-8"))
    predictions = read_jsonl(args.rank_predictions)
    selected_ids = set(prepared["full_unit_ids"])
    if set(predictions) != selected_ids:
        raise ValueError("rank prediction coverage differs from frozen Full manifest")
    if review_summary.get("mode") != "full" or review_summary.get("labels_are_human_gold") is not False:
        raise ValueError("model proxy review summary is missing or has an invalid interpretation")
    if consensus_payload.get("mode") != "full":
        raise ValueError("model proxy consensus is not the frozen Full review")
    consensus_rows = {row["unit_id"]: row for row in consensus_payload["units"]}
    if set(consensus_rows) != selected_ids:
        raise ValueError("model proxy consensus coverage differs from Full manifest")

    private_units = prepared["units"]
    consensus_labels: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for unit_id in selected_ids:
        label = consensus_rows[unit_id].get("proxy_consensus")
        if not isinstance(label, dict):
            continue
        accepted = set(label.get("accepted_mapping_ids", []))
        candidates = {row["mapping_id"] for row in private_units[unit_id]["candidate_mappings"]}
        if not accepted or not accepted <= candidates:
            continue
        if accepted == candidates:
            continue
        consensus_labels[unit_id] = {
            "decision": label["decision"],
            "accepted_mapping_ids": sorted(accepted),
        }
        eligible.append(unit_id)

    db_groups: dict[str, list[str]] = defaultdict(list)
    for unit_id in eligible:
        db_groups[str(private_units[unit_id]["db_id"])].append(unit_id)
    aliases = sorted(db_groups, key=lambda db_id: hashlib.sha256(f"p0_fk_sql_used_mapping_rank_20261107_01:{db_id}".encode("utf-8")).hexdigest())
    by_db = {}
    for index, db_id in enumerate(aliases, 1):
        units = db_groups[db_id]
        by_db[f"db_{index:02d}"] = {
            "distinguishable_proxy_units": len(units),
            "methods": rank_utils.metric_summary(predictions, consensus_labels, units),
            "paired_g_reasoner_vs_dense": rank_utils.paired_comparison(predictions, consensus_labels, units),
        }
    minimum_units = 20
    minimum_databases = 3
    gate = len(eligible) >= minimum_units and len(db_groups) >= minimum_databases
    summary = {
        "experiment_id": "p0_fk_sql_used_mapping_rank_20261107_01",
        "mode": "full_model_proxy_secondary",
        "status": "EXPLORATORY_PROXY_METRICS_REPORTED" if gate else "PROXY_COVERAGE_BELOW_DESCRIPTIVE_GATE",
        "reviewer_models": {"A": "Qwen2.5-Coder-7B-Instruct", "B": "Qwen3-4B-Think2SQL"},
        "review_units": len(consensus_rows),
        "both_valid": review_summary["both_valid"],
        "exact_agreement": review_summary["exact_decision_and_set_agreement"],
        "high_confidence_consensus": review_summary["high_confidence_proxy_consensus"],
        "distinguishable_consensus_units": len(eligible),
        "anonymous_database_count": len(db_groups),
        "minimum_for_descriptive_proxy_ranking": {"units": minimum_units, "databases": minimum_databases},
        "proxy_metrics_reported": gate,
        "methods": rank_utils.metric_summary(predictions, consensus_labels, eligible) if gate else None,
        "paired_g_reasoner_vs_dense": rank_utils.paired_comparison(predictions, consensus_labels, eligible) if gate else None,
        "by_anonymous_database": by_db if gate else None,
        "labels_are_human_gold": False,
        "trusted_human_role_labels": 0,
        "interpretation": "secondary model-proxy-only ranking; not human Role accuracy, SQL accuracy, or method confirmation",
        "input_sha256": {
            "rank_summary": file_hash(args.rank_summary),
            "rank_predictions": file_hash(args.rank_predictions),
            "review_summary": file_hash(args.review_summary),
            "review_consensus": file_hash(args.review_consensus),
            "prepared_manifest": file_hash(args.prepared_manifest),
        },
        "privacy": {"per_unit_ids_or_rankings_in_output": False, "raw_model_outputs_in_output": False},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(args.output, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "input_sha256"}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
