#!/usr/bin/env python3
"""Aggregate local A/B model reviews into private proxy labels and safe counts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aggregate_p0_fk_mapping_model_review_proxy import read_jsonl  # noqa: E402
from run_p0_fk_mapping_model_review_proxy import parse_packet, validate_packet_pair  # noqa: E402


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    expected_run = f"p0_fk_sql_used_mapping_rank_20261107_review_{args.mode}_001"
    if args.run_id != expected_run:
        raise ValueError("run ID differs from preregistered model-review run")
    if args.output_dir.exists():
        raise FileExistsError("output directory already exists")
    packet_a, packet_a_hash = parse_packet(args.packet_a)
    packet_b, packet_b_hash = parse_packet(args.packet_b)
    by_pair = validate_packet_pair(packet_a, packet_b)
    expected_count = 5 if args.mode == "smoke" else None
    if expected_count is not None and len(by_pair) != expected_count:
        raise ValueError("Smoke packet must contain five units")
    manifest = json.loads(args.prepared_manifest.read_text(encoding="utf-8"))
    selected_ids = set(manifest[f"{args.mode}_unit_ids"])
    units = manifest["units"]
    id_to_unit = {row["review_pair_id"]: unit_id for unit_id, row in units.items()}
    if len(id_to_unit) != len(units):
        raise ValueError("review pair ID collision in private manifest")
    packet_ids = {item["pair_id"] for item in packet_a}
    if {id_to_unit.get(pair_id) for pair_id in packet_ids} != selected_ids:
        raise ValueError("review packet and selected manifest units differ")
    for item in packet_a:
        unit_id = id_to_unit[item["pair_id"]]
        unit = units[unit_id]
        expected_ids = set(unit["review_mapping_id_to_canonical_id"])
        if {row["mapping_id"] for row in item["mappings"]} != expected_ids:
            raise ValueError("packet mapping IDs differ from private canonical crosswalk")

    reviewer_a = read_jsonl(args.reviewer_a)
    reviewer_b = read_jsonl(args.reviewer_b)
    if set(reviewer_a) != packet_ids or set(reviewer_b) != packet_ids:
        raise ValueError("reviewer output coverage does not match the frozen packet")
    output_rows: list[dict[str, Any]] = []
    counts = Counter()
    agreement_by_db: dict[str, Counter[str]] = defaultdict(Counter)
    for pair_id in sorted(packet_ids):
        unit_id = id_to_unit[pair_id]
        unit = units[unit_id]
        row_a, row_b = reviewer_a[pair_id], reviewer_b[pair_id]
        counts["review_units"] += 1
        counts["valid_a"] += int(bool(row_a.get("valid")))
        counts["valid_b"] += int(bool(row_b.get("valid")))
        answer_a, answer_b = row_a.get("answer"), row_b.get("answer")
        candidate_map = unit["review_mapping_id_to_canonical_id"]
        valid_pair = bool(row_a.get("valid")) and bool(row_b.get("valid")) and isinstance(answer_a, dict) and isinstance(answer_b, dict)
        exact_agreement = False
        consensus = None
        if valid_pair:
            ids_a = answer_a.get("accepted_mapping_ids", [])
            ids_b = answer_b.get("accepted_mapping_ids", [])
            if not set(ids_a) <= set(candidate_map) or not set(ids_b) <= set(candidate_map):
                raise ValueError("reviewer selected an ID outside the candidate universe")
            exact_agreement = (
                answer_a.get("decision") == answer_b.get("decision")
                and set(ids_a) == set(ids_b)
            )
            if exact_agreement:
                counts["exact_agreement"] += 1
                agreement_by_db[str(unit["db_id"])]["exact_agreement"] += 1
            high_confidence_agreement = (
                exact_agreement
                and int(answer_a.get("confidence", 0)) >= 2
                and int(answer_b.get("confidence", 0)) >= 2
            )
            if high_confidence_agreement:
                counts["high_confidence_exact_agreement"] += 1
            qualifies = (
                high_confidence_agreement
                and answer_a.get("decision") in {"single_mapping", "multiple_mappings"}
                and len(set(ids_a)) > 0
            )
            if qualifies:
                canonical_ids = sorted(candidate_map[value] for value in set(ids_a))
                consensus = {"decision": answer_a["decision"], "accepted_mapping_ids": canonical_ids}
                counts["qualified_consensus"] += 1
                agreement_by_db[str(unit["db_id"])]["qualified_consensus"] += 1
                candidate_ids = {row["mapping_id"] for row in unit["candidate_mappings"]}
                if set(canonical_ids) < candidate_ids:
                    counts["distinguishable_consensus"] += 1
                    agreement_by_db[str(unit["db_id"])]["distinguishable_consensus"] += 1
                target_ids = set(unit["sql_used_mapping_ids"])
                accepted_ids = set(canonical_ids)
                if target_ids == accepted_ids:
                    counts["sql_target_exact_set_match"] += 1
                elif target_ids & accepted_ids:
                    counts["sql_target_overlap"] += 1
                else:
                    counts["sql_target_disjoint"] += 1
        output_rows.append({
            "unit_id": unit_id,
            "private_db_id": unit["db_id"],
            "reviewer_a_valid": bool(row_a.get("valid")),
            "reviewer_b_valid": bool(row_b.get("valid")),
            "exact_agreement": exact_agreement,
            "proxy_consensus": consensus,
            "sql_used_mapping_ids": unit["sql_used_mapping_ids"],
        })

    distinguishable_by_db = Counter(
        row["private_db_id"] for row in output_rows
        if row["proxy_consensus"] is not None
        and set(row["proxy_consensus"]["accepted_mapping_ids"])
        < {candidate["mapping_id"] for candidate in units[row["unit_id"]]["candidate_mappings"]}
    )
    ranked_db_ids = sorted(
        distinguishable_by_db,
        key=lambda db_id: hashlib.sha256(f"p0_fk_sql_used_mapping_rank_20261107_02:{db_id}".encode("utf-8")).hexdigest(),
    )
    anonymous_db_counts = {f"db_{index:02d}": distinguishable_by_db[db_id] for index, db_id in enumerate(ranked_db_ids, 1)}
    smoke_gate = (
        args.mode != "smoke"
        or (
            counts["valid_a"] == 5
            and counts["valid_b"] == 5
            and counts["high_confidence_exact_agreement"] >= 4
        )
    )

    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    private_path = args.output_dir / "model_proxy_consensus_private.json"
    write_json(private_path, {"run_id": args.run_id, "mode": args.mode, "units": output_rows})
    public_summary = {
        "experiment_id": "p0_fk_sql_used_mapping_rank_20261107_02",
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "MODEL_REVIEW_SMOKE_PASS" if smoke_gate and args.mode == "smoke" else ("MODEL_REVIEW_COMPLETE" if args.mode == "full" else "MODEL_REVIEW_SMOKE_STOP"),
        "reviewer_models": {"A": "Qwen2.5-Coder-7B-Instruct", "B": "Qwen3-4B-Think2SQL"},
        "review_units": counts["review_units"],
        "valid_outputs": {"A": counts["valid_a"], "B": counts["valid_b"]},
        "both_valid": sum(1 for row in output_rows if row["reviewer_a_valid"] and row["reviewer_b_valid"]),
        "exact_decision_and_set_agreement": counts["exact_agreement"],
        "high_confidence_exact_agreement": counts["high_confidence_exact_agreement"],
        "high_confidence_proxy_consensus": counts["qualified_consensus"],
        "distinguishable_proxy_consensus": counts["distinguishable_consensus"],
        "sql_target_relation_to_proxy_consensus": {
            "exact_set_match": counts["sql_target_exact_set_match"],
            "overlap_nonexact": counts["sql_target_overlap"],
            "disjoint": counts["sql_target_disjoint"],
        },
        "distinguishable_consensus_by_anonymous_database": anonymous_db_counts,
        "smoke_gate_pass": smoke_gate,
        "labels_are_human_gold": False,
        "trusted_human_role_labels": 0,
        "gold_sql_or_sql_used_target_in_model_input": False,
        "private_consensus_sha256": sha256_file(private_path),
        "input_sha256": {
            "prepared_manifest": sha256_file(args.prepared_manifest),
            "packet_a": packet_a_hash,
            "packet_b": packet_b_hash,
            "reviewer_a_output": sha256_file(args.reviewer_a),
            "reviewer_b_output": sha256_file(args.reviewer_b),
        },
    }
    write_json(args.output_dir / "aggregate_summary.json", public_summary)
    print(json.dumps({key: value for key, value in public_summary.items() if key != "input_sha256"}, ensure_ascii=False, sort_keys=True))
    return 0 if smoke_gate else 3


if __name__ == "__main__":
    raise SystemExit(main())
