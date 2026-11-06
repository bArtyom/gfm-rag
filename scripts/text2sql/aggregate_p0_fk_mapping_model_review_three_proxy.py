#!/usr/bin/env python3
"""Aggregate three blind FK-mapping reviews without exporting case-level data."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from run_p0_fk_mapping_model_review_proxy import parse_packet  # noqa: E402


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
                raise ValueError(f"invalid or duplicate pair key at row {line_number}")
            rows[pair_id] = row
    return rows


def normalized_label(row: dict[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    if row.get("valid") is not True:
        return None
    answer = row.get("answer")
    if not isinstance(answer, dict):
        return None
    decision = answer.get("decision")
    accepted = answer.get("accepted_mapping_ids")
    confidence = answer.get("confidence")
    if decision not in {"single_mapping", "multiple_mappings", "cannot_determine", "no_declared_fk", "other"}:
        return None
    if not isinstance(accepted, list) or any(not isinstance(value, str) for value in accepted):
        return None
    if len(accepted) != len(set(accepted)) or type(confidence) is not int or confidence not in {1, 2, 3}:
        return None
    return decision, tuple(sorted(accepted))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a-jsonl", type=Path, required=True)
    parser.add_argument("--reviewer-b-jsonl", type=Path, required=True)
    parser.add_argument("--reviewer-c-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    packet_a, packet_a_hash = parse_packet(args.packet_a)
    packet_b, packet_b_hash = parse_packet(args.packet_b)
    units_a = {row["pair_id"]: row for row in packet_a}
    units_b = {row["pair_id"]: row for row in packet_b}
    if len(units_a) != 60 or set(units_a) != set(units_b):
        raise ValueError("frozen A/B packet coverage mismatch")
    if any({m["mapping_id"] for m in units_a[p]["mappings"]} !=
           {m["mapping_id"] for m in units_b[p]["mappings"]} for p in units_a):
        raise ValueError("frozen A/B candidate sets differ")

    outputs = {
        "A": read_jsonl(args.reviewer_a_jsonl),
        "B": read_jsonl(args.reviewer_b_jsonl),
        "C": read_jsonl(args.reviewer_c_jsonl),
    }
    if any(set(rows) != set(units_a) for rows in outputs.values()):
        raise ValueError("review output coverage differs from frozen 60 units")

    manifest = json.loads(args.private_manifest.read_text(encoding="utf-8"))
    db_by_pair = {row["pair_id"]: row["private_db_id"]
                  for row in manifest["selected_cases_private"]}
    if set(db_by_pair) != set(units_a):
        raise ValueError("private manifest coverage differs from frozen packet")

    valid_counts = {reviewer: sum(row.get("valid") is True for row in rows.values())
                    for reviewer, rows in outputs.items()}
    pair_agreement: dict[str, dict[str, int]] = {}
    for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
        jointly_valid = 0
        exact = 0
        for pair_id in units_a:
            lrow, rrow = outputs[left][pair_id], outputs[right][pair_id]
            ll, rr = normalized_label(lrow), normalized_label(rrow)
            if ll is None or rr is None:
                continue
            jointly_valid += 1
            exact += int(ll == rr)
        pair_agreement[f"{left}_{right}"] = {
            "jointly_valid": jointly_valid,
            "exact_decision_and_set_agreements": exact,
            "agreement_rate": round(exact / jointly_valid, 6) if jointly_valid else 0.0,
        }

    winner_counts: Counter[str] = Counter()
    high_confidence_majority = 0
    adjudicable: list[str] = []
    distinguishable: list[str] = []
    unanimous = 0
    two_of_three = 0
    decision_counts: Counter[str] = Counter()
    vote_cardinality_patterns: Counter[str] = Counter()

    for pair_id, item in units_a.items():
        votes: dict[tuple[str, tuple[str, ...]], list[tuple[str, int]]] = {}
        valid_labels = []
        for reviewer, rows in outputs.items():
            row = rows[pair_id]
            label = normalized_label(row)
            if label is None:
                continue
            answer = row["answer"]
            accepted = set(label[1])
            candidates = {entry["mapping_id"] for entry in item["mappings"]}
            if not accepted <= candidates:
                raise ValueError("review answer references an ID outside the frozen candidates")
            votes.setdefault(label, []).append((reviewer, answer["confidence"]))
            valid_labels.append(label)

        vote_cardinality_patterns[str(len(set(valid_labels)))] += 1
        if len(valid_labels) == 3 and len(set(valid_labels)) == 1:
            unanimous += 1
        elif len(valid_labels) == 3 and max(Counter(valid_labels).values(), default=0) == 2:
            two_of_three += 1

        majority = [(label, members) for label, members in votes.items()
                    if sum(confidence >= 2 for _, confidence in members) >= 2]
        if len(majority) != 1:
            continue
        (decision, accepted_tuple), members = majority[0]
        high_confidence_majority += 1
        winner_counts["+".join(sorted(reviewer for reviewer, confidence in members
                                     if confidence >= 2))] += 1
        decision_counts[decision] += 1
        if decision not in {"single_mapping", "multiple_mappings"}:
            continue
        accepted = set(accepted_tuple)
        candidates = {entry["mapping_id"] for entry in item["mappings"]}
        if not accepted:
            continue
        adjudicable.append(pair_id)
        if accepted < candidates:
            distinguishable.append(pair_id)

    db_coverage = len({db_by_pair[pair_id] for pair_id in distinguishable})
    gate_pass = len(adjudicable) >= 30 and len(distinguishable) >= 20 and db_coverage >= 3
    result = {
        "experiment_id": "p0_fk_mapping_model_review_third_proxy_20261106_01",
        "run_id": args.run_id,
        "review_unit_count": len(units_a),
        "candidate_mapping_count": sum(len(item["mappings"]) for item in units_a.values()),
        "human_labels_used": False,
        "gold_sql_or_reference_join_used_by_aggregator": False,
        "trusted_human_role_labels_created": 0,
        "valid_outputs": valid_counts,
        "pairwise_exact_agreement": pair_agreement,
        "three_valid_reviewer_units_unanimous": unanimous,
        "three_valid_reviewer_units_two_of_three_pattern": two_of_three,
        "valid_vote_cardinality_pattern_counts": dict(sorted(vote_cardinality_patterns.items())),
        "high_confidence_exact_majority_count": high_confidence_majority,
        "majority_vote_pair_counts": dict(sorted(winner_counts.items())),
        "high_confidence_majority_decision_counts": dict(sorted(decision_counts.items())),
        "model_consensus_adjudicable_count": len(adjudicable),
        "model_consensus_distinguishable_count": len(distinguishable),
        "anonymous_database_count_for_distinguishable_consensus": db_coverage,
        "separate_exploratory_ranking_registration_gate": (
            "PASS_MODEL_PROXY_ONLY" if gate_pass else "STOP_INSUFFICIENT_MODEL_PROXY_LABELS"
        ),
        "input_sha256": {
            "reviewer_a_packet": packet_a_hash,
            "reviewer_b_packet": packet_b_hash,
            "private_manifest": sha256_file(args.private_manifest),
            "reviewer_a_outputs": sha256_file(args.reviewer_a_jsonl),
            "reviewer_b_outputs": sha256_file(args.reviewer_b_jsonl),
            "reviewer_c_outputs": sha256_file(args.reviewer_c_jsonl),
        },
        "privacy": {
            "contains_questions_or_schema_names": False,
            "contains_pair_or_case_ids": False,
            "contains_mapping_ids": False,
            "contains_model_raw_outputs": False,
            "contains_gold_sql_or_human_review": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({key: value for key, value in result.items() if key != "input_sha256"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

