#!/usr/bin/env python3
"""Aggregate two local-model FK-mapping reviews without exposing case-level data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from run_p0_fk_mapping_model_review_proxy import parse_packet


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            record = json.loads(line)
            pair_id = record.get("pair_id")
            if not isinstance(pair_id, str) or pair_id in records:
                raise ValueError(f"invalid or duplicated pair entry at line {line_number}")
            records[pair_id] = record
    return records


def exact_label(a: dict[str, Any], b: dict[str, Any]) -> bool:
    aa, bb = a.get("answer"), b.get("answer")
    if not isinstance(aa, dict) or not isinstance(bb, dict):
        return False
    return (
        aa.get("decision") == bb.get("decision")
        and set(aa.get("accepted_mapping_ids", [])) == set(bb.get("accepted_mapping_ids", []))
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a-jsonl", type=Path, required=True)
    parser.add_argument("--reviewer-b-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    packet_a, packet_a_hash = parse_packet(args.packet_a)
    packet_b, packet_b_hash = parse_packet(args.packet_b)
    if len(packet_a) != 60 or len(packet_b) != 60:
        raise ValueError("expected the frozen 60-unit A/B packet")
    units_a = {row["pair_id"]: row for row in packet_a}
    units_b = {row["pair_id"]: row for row in packet_b}
    if set(units_a) != set(units_b):
        raise ValueError("A/B packet unit sets differ")

    a = read_jsonl(args.reviewer_a_jsonl)
    b = read_jsonl(args.reviewer_b_jsonl)
    if set(a) != set(units_a) or set(b) != set(units_a):
        raise ValueError("review output coverage differs from the frozen packet")

    # Read only pair-to-private-database membership from this private manifest.
    # Raw questions, SQL, identities and per-case judgments never enter output.
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    private_db_by_pair = {
        row["pair_id"]: row["private_db_id"]
        for row in manifest["selected_cases_private"]
    }
    if set(private_db_by_pair) != set(units_a):
        raise ValueError("private manifest pair coverage differs from the frozen packet")

    valid_a = sum(bool(row.get("valid")) for row in a.values())
    valid_b = sum(bool(row.get("valid")) for row in b.values())
    both_valid = [pair_id for pair_id in units_a if a[pair_id].get("valid") and b[pair_id].get("valid")]
    exact_pairs = [pair_id for pair_id in both_valid if exact_label(a[pair_id], b[pair_id])]
    qualified_pairs = [
        pair_id for pair_id in exact_pairs
        if a[pair_id]["answer"].get("confidence", 0) >= 2
        and b[pair_id]["answer"].get("confidence", 0) >= 2
    ]

    consensus_decisions: dict[str, int] = {}
    adjudicable: list[str] = []
    distinguishable: list[str] = []
    for pair_id in qualified_pairs:
        answer = a[pair_id]["answer"]
        decision = answer["decision"]
        consensus_decisions[decision] = consensus_decisions.get(decision, 0) + 1
        if decision not in {"single_mapping", "multiple_mappings"}:
            continue
        accepted = set(answer.get("accepted_mapping_ids", []))
        candidate_ids = {mapping["mapping_id"] for mapping in units_a[pair_id]["mappings"]}
        if accepted and accepted <= candidate_ids:
            adjudicable.append(pair_id)
            if accepted < candidate_ids:
                distinguishable.append(pair_id)

    eligible_database_count = len({private_db_by_pair[pair_id] for pair_id in distinguishable})
    gate_pass = len(adjudicable) >= 30 and len(distinguishable) >= 20 and eligible_database_count >= 3
    invalid_reasons: dict[str, dict[str, int]] = {"A": {}, "B": {}}
    for reviewer, rows in (("A", a), ("B", b)):
        for row in rows.values():
            reason = row.get("invalid_reason")
            if reason:
                invalid_reasons[reviewer][reason] = invalid_reasons[reviewer].get(reason, 0) + 1

    result = {
        "experiment_id": "p0_fk_mapping_model_review_proxy_20261106_01",
        "run_id": args.run_id,
        "mode": "full_model_review_proxy",
        "human_consensus_labels_used": False,
        "trusted_human_role_labels_created": 0,
        "gold_sql_or_reference_join_used_by_aggregator": False,
        "review_unit_count": len(units_a),
        "candidate_mapping_count": sum(len(row["mappings"]) for row in units_a.values()),
        "models": {
            "A": {"model": "Qwen2.5-Coder-7B-Instruct", "valid_outputs": valid_a},
            "B": {"model": "Qwen3-4B-Think2SQL", "valid_outputs": valid_b},
        },
        "invalid_output_reasons": invalid_reasons,
        "both_valid_count": len(both_valid),
        "exact_decision_and_set_agreement_count": len(exact_pairs),
        "exact_agreement_rate_all_units": round(len(exact_pairs) / len(units_a), 6),
        "exact_agreement_rate_both_valid": round(len(exact_pairs) / len(both_valid), 6) if both_valid else None,
        "exact_agreement_with_both_confidence_at_least_2": len(qualified_pairs),
        "qualified_consensus_decision_counts": dict(sorted(consensus_decisions.items())),
        "model_consensus_adjudicable_count": len(adjudicable),
        "model_consensus_distinguishable_count": len(distinguishable),
        "anonymous_database_count_for_distinguishable_consensus": eligible_database_count,
        "separate_exploratory_ranking_registration_gate": (
            "PASS_MODEL_PROXY_ONLY" if gate_pass else "STOP_INSUFFICIENT_MODEL_PROXY_LABELS"
        ),
        "input_sha256": {
            "reviewer_a_packet": packet_a_hash,
            "reviewer_b_packet": packet_b_hash,
            "private_manifest": sha256_file(args.manifest),
            "reviewer_a_outputs": sha256_file(args.reviewer_a_jsonl),
            "reviewer_b_outputs": sha256_file(args.reviewer_b_jsonl),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({key: value for key, value in result.items() if key != "input_sha256"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
