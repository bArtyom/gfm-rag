#!/usr/bin/env python3
"""Compare canonical P1.5 FK labels against frozen private references."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "p0_fk_canonical_crosswalk_20261105_01"
V3_EXPERIMENT_ID = "p0_fk_candidate_definition_recovery_v3_20261105_01"
EXPECTED_N = 1534
EXPECTED_JOIN_ON = 1140
EXPECTED_INPUT_HASHES = {
    "dev.json": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "dev_tables.json": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
}
EXPECTED_REFERENCE_SHA = {
    "packet28": "13401f39e6744a4c47e3a5f36b59be468335f79f04594db27c3e662ce9ba75f3",
    "p1_5_unfiltered": "4736e320aff6da6bdc56f0ddd56c7887a85014cf9577c6dd568b7f738df0f883",
}
EXPECTED_ARTIFACT_SHA = "5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_result(
    path: Path,
    expected_hash: str,
    expected_experiment_id: str,
    expected_method: str,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    if sha256_file(path) != expected_hash:
        raise RuntimeError("Pinned comparison input hash mismatch")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") != "FULL_COMPLETE" or result.get("mode") != "full":
        raise RuntimeError("Comparison input is not a completed full audit")
    if result.get("experiment_id") != expected_experiment_id:
        raise RuntimeError("Comparison input experiment mismatch")
    if result.get("method") != expected_method:
        raise RuntimeError("Comparison input method mismatch")
    if expected_run_id is not None and result.get("run_id") != expected_run_id:
        raise RuntimeError("Comparison input run ID mismatch")
    if result.get("input_hashes") != EXPECTED_INPUT_HASHES:
        raise RuntimeError("Comparison input dataset hash mismatch")
    denominators = result.get("denominators", {})
    if (
        denominators.get("records_processed") != EXPECTED_N
        or denominators.get("parse_ok") != EXPECTED_N
        or denominators.get("join_on_questions") != EXPECTED_JOIN_ON
    ):
        raise RuntimeError("Comparison input denominator mismatch")
    rows = result.get("private_question_rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_N:
        raise RuntimeError("Comparison input question denominator mismatch")
    indexed = {row["question_key_sha256"]: row for row in rows}
    if len(indexed) != EXPECTED_N:
        raise RuntimeError("Duplicate or missing hashed question key")
    return {"metadata": result, "rows": indexed}


def pair_summary(left: dict[str, Any], right: dict[str, Any], field: str) -> dict[str, int]:
    categories = {"both_false": 0, "left_only": 0, "right_only": 0, "both_true": 0}
    for key in left:
        a, b = bool(left[key].get(field)), bool(right[key].get(field))
        if a and b:
            categories["both_true"] += 1
        elif a:
            categories["left_only"] += 1
        elif b:
            categories["right_only"] += 1
        else:
            categories["both_false"] += 1
    return categories


def p1_5_evidence_stratum(row: dict[str, Any]) -> str:
    if not row.get("parse_ok"):
        return "parse_failure"
    if int(row.get("join_on_count", 0)) == 0:
        return "no_join_on"
    flags = []
    for field, label in (
        ("matched_join_count", "exact"),
        ("ambiguous_join_count", "ambiguous"),
        ("partial_join_count", "partial"),
        ("unmatched_join_count", "unmatched"),
    ):
        if int(row.get(field, 0)) > 0:
            flags.append(label)
    return "+".join(flags) if flags else "join_on_without_classified_match"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet28", type=Path, required=True)
    parser.add_argument("--p1-5-unfiltered", type=Path, required=True)
    parser.add_argument("--p1-5-canonical", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.private_output, args.aggregate_output):
        if path.exists():
            raise FileExistsError("Refusing to overwrite comparison output")

    packet = load_result(
        args.packet28,
        EXPECTED_REFERENCE_SHA["packet28"],
        V3_EXPERIMENT_ID,
        "packet",
        "p0fk_v3_full_packet_py312_sqlg28_20261105_01",
    )
    unfiltered = load_result(
        args.p1_5_unfiltered,
        EXPECTED_REFERENCE_SHA["p1_5_unfiltered"],
        V3_EXPERIMENT_ID,
        "p1_5",
        "p0fk_v3_full_p15_py312_sqlg28_20261105_01",
    )
    canonical = load_result(
        args.p1_5_canonical,
        sha256_file(args.p1_5_canonical),
        EXPERIMENT_ID,
        "p1_5",
        "p0fk_canonical_p15_full_py312_sqlg28_20261105_01",
    )
    if canonical["metadata"].get("p1_5_fk_artifact_sha256") != EXPECTED_ARTIFACT_SHA:
        raise RuntimeError("Canonical P1.5 artifact hash mismatch")
    expected_filter = {
        "database_count": 11,
        "raw_instance_count": 103,
        "valid_instance_count": 100,
        "excluded_invalid_endpoint_count": 3,
        "validity_flag_type": "boolean",
        "canonical_valid_only_filter_applied": True,
    }
    if canonical["metadata"].get("fk_instance_filter_summary") != expected_filter:
        raise RuntimeError("Canonical FK instance filter contract mismatch")

    definitions = {
        "packet_py312_sqlglot28": packet["rows"],
        "p1_5_v3_unfiltered": unfiltered["rows"],
        "p1_5_canonical_valid_only": canonical["rows"],
    }
    key_sets = [set(rows) for rows in definitions.values()]
    if not (key_sets[0] == key_sets[1] == key_sets[2]):
        raise RuntimeError("Question hash universe differs across definitions")

    pair_specs = {
        "p1_5_unfiltered_vs_canonical": ("p1_5_v3_unfiltered", "p1_5_canonical_valid_only"),
        "packet28_vs_p1_5_canonical": ("packet_py312_sqlglot28", "p1_5_canonical_valid_only"),
    }
    fields = ("parse_ok", "has_join_on", "fk_match", "multi_fk_candidate")
    pairwise: dict[str, Any] = {}
    private_pairs: dict[str, list[dict[str, Any]]] = {}
    for pair_name, (left_name, right_name) in pair_specs.items():
        left, right = definitions[left_name], definitions[right_name]
        pairwise[pair_name] = {field: pair_summary(left, right, field) for field in fields}
        private_pairs[pair_name] = []
        for key in sorted(left):
            private_pairs[pair_name].append({
                "question_key_sha256": key,
                **{f"left_{field}": bool(left[key].get(field)) for field in fields},
                **{f"right_{field}": bool(right[key].get(field)) for field in fields},
            })

    filter_effect: Counter[str] = Counter()
    packet_disagreement_by_canonical_evidence: Counter[str] = Counter()
    for key in definitions["p1_5_canonical_valid_only"]:
        old = definitions["p1_5_v3_unfiltered"][key]
        new = definitions["p1_5_canonical_valid_only"][key]
        for field in ("fk_match", "multi_fk_candidate"):
            if bool(old.get(field)) != bool(new.get(field)):
                direction = "unfiltered_only" if old.get(field) else "canonical_only"
                filter_effect[f"{field}:{direction}"] += 1
        packet_row = definitions["packet_py312_sqlglot28"][key]
        if bool(packet_row.get("fk_match")) != bool(new.get("fk_match")):
            direction = "packet_only" if packet_row.get("fk_match") else "canonical_only"
            packet_disagreement_by_canonical_evidence[f"{direction}:{p1_5_evidence_stratum(new)}"] += 1
        if bool(packet_row.get("multi_fk_candidate")) != bool(new.get("multi_fk_candidate")):
            direction = "packet_only" if packet_row.get("multi_fk_candidate") else "canonical_only"
            state = "role_candidates_nonzero" if int(new.get("role_candidate_join_count", 0)) > 0 else "role_candidates_zero"
            packet_disagreement_by_canonical_evidence[f"multi_fk:{direction}:{state}"] += 1

    aggregate = {
        "experiment_id": EXPERIMENT_ID,
        "status": "CROSSWALK_COMPLETE",
        "question_count": EXPECTED_N,
        "definitions": {name: data["metadata"]["denominators"] for name, data in (
            ("packet_py312_sqlglot28", packet),
            ("p1_5_v3_unfiltered", unfiltered),
            ("p1_5_canonical_valid_only", canonical),
        )},
        "reference_hashes": {
            "packet28_result_sha256": EXPECTED_REFERENCE_SHA["packet28"],
            "p1_5_unfiltered_result_sha256": EXPECTED_REFERENCE_SHA["p1_5_unfiltered"],
            "canonical_result_sha256": sha256_file(args.p1_5_canonical),
            "p1_5_fk_artifact_sha256": EXPECTED_ARTIFACT_SHA,
        },
        "pairwise_categories": pairwise,
        "filter_effect_by_label": dict(sorted(filter_effect.items())),
        "packet28_disagreement_strata": dict(sorted(packet_disagreement_by_canonical_evidence.items())),
        "raw_question_text_written": False,
        "raw_sql_written": False,
        "database_names_written": False,
        "question_hashes_in_public_aggregate": False,
    }
    private = {**aggregate, "private_pairwise_question_crosswalks": private_pairs}
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.aggregate_output.parent.mkdir(parents=True, exist_ok=True)
    with args.private_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(private, ensure_ascii=False, indent=2) + "\n")
    os.chmod(args.private_output, 0o600)
    with args.aggregate_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    os.chmod(args.aggregate_output, 0o644)
    print(json.dumps({
        "status": aggregate["status"],
        "question_count": EXPECTED_N,
        "definitions": aggregate["definitions"],
        "filter_effect_by_label": aggregate["filter_effect_by_label"],
        "packet28_disagreement_strata": aggregate["packet28_disagreement_strata"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "STOP_INVALID", "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
