#!/usr/bin/env python3
"""Aggregate private local-model review outputs without publishing unit data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

EXPERIMENT_ID = "p0_bird_train_fk_model_proxy_review_20261107_01"
CASE_RE = re.compile(r"(?m)^## Case ([A-Za-z0-9_-]+)\s*$")
PAIR_RE = re.compile(r"(?m)^### Pair ([A-Za-z0-9_-]+): (.+?)\s*$")
MAPPING_RE = re.compile(r"(?m)^\|\s*(M[0-9A-F]+)\s*\|\s*(.*?)\s*\|\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_packet(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    matches = list(CASE_RE.finditer(raw))
    result = []
    for index, case_match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body = raw[case_match.end():end]
        pair_matches = list(PAIR_RE.finditer(body))
        if len(pair_matches) != 1:
            raise ValueError("packet_pair_count_invalid")
        pair_match = pair_matches[0]
        mappings = [
            {"mapping_id": match.group(1), "expression": match.group(2).strip()}
            for match in MAPPING_RE.finditer(body[pair_match.end():])
        ]
        if len(mappings) < 2 or len({item["mapping_id"] for item in mappings}) != len(mappings):
            raise ValueError("packet_mapping_ids_invalid")
        question_lines = [line.strip() for line in body[:pair_match.start()].splitlines() if line.strip()]
        if len(question_lines) != 1:
            raise ValueError("packet_question_line_invalid")
        result.append({
            "case_id": case_match.group(1),
            "pair_id": pair_match.group(1),
            "pair_name": pair_match.group(2).strip(),
            "mappings": mappings,
        })
    if not result:
        raise ValueError("packet_empty")
    return result


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, start=1):
            row = json.loads(line)
            pair_id = row.get("pair_id")
            if not isinstance(pair_id, str) or pair_id in rows:
                raise ValueError(f"review_output_pair_id_invalid_line_{line_no}")
            rows[pair_id] = row
    return rows


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
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=["smoke", "full"], required=True)
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a-jsonl", type=Path, required=True)
    parser.add_argument("--reviewer-b-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("experiment_config_mismatch")
    packet_a = parse_packet(args.packet_a)
    packet_b = parse_packet(args.packet_b)
    expected_units = config["sampling"]["full_units"]
    if len(packet_a) != expected_units or len(packet_b) != expected_units:
        raise ValueError("frozen_packet_unit_count_mismatch")
    units_a = {row["pair_id"]: row for row in packet_a}
    units_b = {row["pair_id"]: row for row in packet_b}
    if set(units_a) != set(units_b):
        raise ValueError("A_B_packet_pair_set_mismatch")
    for pair_id in units_a:
        a, b = units_a[pair_id], units_b[pair_id]
        if a["case_id"] != b["case_id"] or a["pair_name"] != b["pair_name"]:
            raise ValueError("A_B_packet_case_mismatch")
        if {x["mapping_id"]: x["expression"] for x in a["mappings"]} != {
            x["mapping_id"]: x["expression"] for x in b["mappings"]
        }:
            raise ValueError("A_B_mapping_set_mismatch")

    manifest_data = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_rows = manifest_data.get("selected_cases_private")
    if not isinstance(manifest_rows, list):
        raise ValueError("private_manifest_invalid")
    private_db_by_pair = {row["pair_id"]: row["private_db_id"] for row in manifest_rows}
    if len(private_db_by_pair) != expected_units or set(private_db_by_pair) != set(units_a):
        raise ValueError("private_manifest_pair_coverage_mismatch")

    expected_output_count = config["sampling"]["smoke_units"] if args.mode == "smoke" else expected_units
    if args.mode == "smoke":
        selected_ids = {row["pair_id"] for row in packet_a[:expected_output_count]}
        selected_a = {pair_id: units_a[pair_id] for pair_id in selected_ids}
    else:
        selected_ids = set(units_a)
        selected_a = units_a
    selected_b = {pair_id: units_b[pair_id] for pair_id in selected_ids}
    outputs_a = read_jsonl(args.reviewer_a_jsonl)
    outputs_b = read_jsonl(args.reviewer_b_jsonl)
    if set(outputs_a) != selected_ids or set(outputs_b) != selected_ids:
        raise ValueError("review_output_coverage_mismatch")

    valid_a = sum(bool(row.get("valid")) for row in outputs_a.values())
    valid_b = sum(bool(row.get("valid")) for row in outputs_b.values())
    both_valid = [
        pair_id for pair_id in selected_ids
        if outputs_a[pair_id].get("valid") and outputs_b[pair_id].get("valid")
    ]
    exact = [pair_id for pair_id in both_valid if exact_label(outputs_a[pair_id], outputs_b[pair_id])]
    qualified = [
        pair_id for pair_id in exact
        if outputs_a[pair_id]["answer"].get("confidence", 0) >= 2
        and outputs_b[pair_id]["answer"].get("confidence", 0) >= 2
    ]
    consensus_decisions: dict[str, int] = {}
    adjudicable: list[str] = []
    distinguishable: list[str] = []
    for pair_id in qualified:
        answer = outputs_a[pair_id]["answer"]
        decision = answer["decision"]
        consensus_decisions[decision] = consensus_decisions.get(decision, 0) + 1
        if decision not in {"single_mapping", "multiple_mappings"}:
            continue
        accepted = set(answer.get("accepted_mapping_ids", []))
        candidate_ids = {item["mapping_id"] for item in selected_a[pair_id]["mappings"]}
        if accepted and accepted <= candidate_ids:
            adjudicable.append(pair_id)
            if accepted < candidate_ids:
                distinguishable.append(pair_id)
    db_count = len({private_db_by_pair[pair_id] for pair_id in distinguishable})
    invalid: dict[str, dict[str, int]] = {"A": {}, "B": {}}
    for reviewer, rows in (("A", outputs_a), ("B", outputs_b)):
        for row in rows.values():
            reason = row.get("invalid_reason")
            if reason:
                invalid[reviewer][reason] = invalid[reviewer].get(reason, 0) + 1

    if args.mode == "smoke":
        pass_gate = (
            valid_a >= config["gates"]["smoke_min_valid_per_model"]
            and valid_b >= config["gates"]["smoke_min_valid_per_model"]
        )
        gate_name = "SMOKE_PASS" if pass_gate else "STOP_SMOKE_OUTPUT_VALIDITY"
    else:
        pass_gate = (
            len(adjudicable) >= config["gates"]["min_adjudicable_consensus"]
            and len(distinguishable) >= config["gates"]["min_distinguishable_consensus"]
            and db_count >= config["gates"]["min_distinguishable_anonymous_databases"]
        )
        gate_name = "PASS_MODEL_PROXY_ONLY" if pass_gate else "STOP_INSUFFICIENT_MODEL_PROXY_LABELS"

    result = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": f"{args.mode}_model_review_proxy",
        "human_consensus_labels_used": False,
        "trusted_human_role_labels_created": 0,
        "gold_sql_or_reference_join_used_by_models": False,
        "gold_sql_or_reference_join_used_by_aggregator": False,
        "full_packet_units": expected_units,
        "review_units_in_this_aggregate": len(selected_ids),
        "candidate_mapping_count": sum(len(row["mappings"]) for row in selected_a.values()),
        "models": {
            "A": {"model": config["models"]["A"]["name"], "valid_outputs": valid_a},
            "B": {"model": config["models"]["B"]["name"], "valid_outputs": valid_b},
        },
        "invalid_output_reasons": invalid,
        "both_valid_count": len(both_valid),
        "exact_decision_and_set_agreement_count": len(exact),
        "exact_agreement_rate_all_units": round(len(exact) / len(selected_ids), 6),
        "exact_agreement_rate_both_valid": round(len(exact) / len(both_valid), 6) if both_valid else None,
        "exact_agreement_with_both_confidence_at_least_2": len(qualified),
        "qualified_consensus_decision_counts": dict(sorted(consensus_decisions.items())),
        "model_consensus_adjudicable_count": len(adjudicable),
        "model_consensus_distinguishable_count": len(distinguishable),
        "anonymous_database_count_for_distinguishable_consensus": db_count,
        "gate": gate_name,
        "input_sha256": {
            "reviewer_a_packet": sha256_file(args.packet_a),
            "reviewer_b_packet": sha256_file(args.packet_b),
            "private_manifest": sha256_file(args.manifest),
            "reviewer_a_outputs": sha256_file(args.reviewer_a_jsonl),
            "reviewer_b_outputs": sha256_file(args.reviewer_b_jsonl),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.parent.chmod(0o700)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({
        "mode": args.mode,
        "review_units": result["review_units_in_this_aggregate"],
        "valid_outputs_A": valid_a,
        "valid_outputs_B": valid_b,
        "qualified_adjudicable": len(adjudicable),
        "distinguishable": len(distinguishable),
        "anonymous_database_count": db_count,
        "gate": gate_name,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
