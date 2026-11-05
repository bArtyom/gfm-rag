#!/usr/bin/env python3
"""Create a private hashed crosswalk and anonymous strata for recovery runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "p0_fk_candidate_definition_recovery_v3_20261105_01"
EXPECTED_N = 1534


def load_result(path: Path, expected_method: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") != "FULL_COMPLETE" or result.get("mode") != "full":
        raise RuntimeError("Comparison input is not a completed full audit")
    if result.get("experiment_id") != EXPERIMENT_ID:
        raise RuntimeError("Comparison input experiment mismatch")
    if result.get("method") != expected_method:
        raise RuntimeError("Comparison input method mismatch")
    rows = result.get("private_question_rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_N:
        raise RuntimeError("Comparison input denominator mismatch")
    indexed = {row["question_key_sha256"]: row for row in rows}
    if len(indexed) != EXPECTED_N:
        raise RuntimeError("Duplicate/missing hashed question key")
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
    parser.add_argument("--packet-26", type=Path, required=True)
    parser.add_argument("--packet-28", type=Path, required=True)
    parser.add_argument("--p1-5-28", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.private_output, args.aggregate_output):
        if path.exists():
            raise FileExistsError("Refusing to overwrite comparison output")

    packet26 = load_result(args.packet_26, "packet")
    packet28 = load_result(args.packet_28, "packet")
    p1_5_28 = load_result(args.p1_5_28, "p1_5")
    crosswalks = [packet26["rows"], packet28["rows"], p1_5_28["rows"]]
    if set(crosswalks[0]) != set(crosswalks[1]) or set(crosswalks[1]) != set(crosswalks[2]):
        raise RuntimeError("Question hash universe differs across definitions")

    definitions = {
        "packet_py310_sqlglot26": crosswalks[0],
        "packet_py312_sqlglot28": crosswalks[1],
        "p1_5_py312_sqlglot28": crosswalks[2],
    }
    pair_specs = {
        "packet_py310_sqlglot26_vs_packet_py312_sqlglot28": (
            "packet_py310_sqlglot26", "packet_py312_sqlglot28"
        ),
        "packet_py312_sqlglot28_vs_p1_5_py312_sqlglot28": (
            "packet_py312_sqlglot28", "p1_5_py312_sqlglot28"
        ),
    }
    pairwise: dict[str, Any] = {}
    private_pairs: dict[str, list[dict[str, Any]]] = {}
    for pair_name, (left_name, right_name) in pair_specs.items():
        left, right = definitions[left_name], definitions[right_name]
        pairwise[pair_name] = {
            "fk_match": pair_summary(left, right, "fk_match"),
            "multi_fk_candidate": pair_summary(left, right, "multi_fk_candidate"),
            "parse_ok": pair_summary(left, right, "parse_ok"),
            "join_on": pair_summary(left, right, "has_join_on"),
        }
        private_pairs[pair_name] = []
        for key in sorted(left):
            private_pairs[pair_name].append({
                "question_key_sha256": key,
                "left_fk_match": bool(left[key].get("fk_match")),
                "right_fk_match": bool(right[key].get("fk_match")),
                "left_multi_fk_candidate": bool(left[key].get("multi_fk_candidate")),
                "right_multi_fk_candidate": bool(right[key].get("multi_fk_candidate")),
                "left_parse_ok": bool(left[key].get("parse_ok")),
                "right_parse_ok": bool(right[key].get("parse_ok")),
                "left_has_join_on": bool(left[key].get("has_join_on")),
                "right_has_join_on": bool(right[key].get("has_join_on")),
            })

    packet_version_deltas: Counter[str] = Counter()
    p1_5_match_strata: Counter[str] = Counter()
    p1_5_multi_candidate_strata: Counter[str] = Counter()
    p1_5_source = definitions["p1_5_py312_sqlglot28"]
    packet_source = definitions["packet_py312_sqlglot28"]
    for key in definitions["packet_py310_sqlglot26"]:
        old = definitions["packet_py310_sqlglot26"][key]
        new = definitions["packet_py312_sqlglot28"][key]
        if bool(old.get("fk_match")) != bool(new.get("fk_match")):
            packet_version_deltas[f"fk_match:{'26_only' if old.get('fk_match') else '28_only'}"] += 1
        if bool(old.get("multi_fk_candidate")) != bool(new.get("multi_fk_candidate")):
            packet_version_deltas[f"multi_fk_candidate:{'26_only' if old.get('multi_fk_candidate') else '28_only'}"] += 1

        packet_match = bool(packet_source[key].get("fk_match"))
        p1_match = bool(p1_5_source[key].get("fk_match"))
        if packet_match != p1_match:
            direction = "packet_only" if packet_match else "p1_5_only"
            p1_5_match_strata[f"{direction}:{p1_5_evidence_stratum(p1_5_source[key])}"] += 1

        packet_multi = bool(packet_source[key].get("multi_fk_candidate"))
        p1_multi = bool(p1_5_source[key].get("multi_fk_candidate"))
        if packet_multi != p1_multi:
            direction = "packet_only" if packet_multi else "p1_5_only"
            count_state = "p1_5_role_candidates_nonzero" if int(p1_5_source[key].get("role_candidate_join_count", 0)) > 0 else "p1_5_role_candidates_zero"
            p1_5_multi_candidate_strata[f"{direction}:{count_state}"] += 1

    aggregate = {
        "experiment_id": EXPERIMENT_ID,
        "status": "CROSSWALK_COMPLETE",
        "question_count": EXPECTED_N,
        "definitions": {
            name: data["denominators"] for name, data in (
                ("packet_py310_sqlglot26", packet26["metadata"]),
                ("packet_py312_sqlglot28", packet28["metadata"]),
                ("p1_5_py312_sqlglot28", p1_5_28["metadata"]),
            )
        },
        "pairwise_categories": pairwise,
        "pre_registered_disagreement_strata": {
            "packet_version_deltas": dict(sorted(packet_version_deltas.items())),
            "packet28_vs_p1_5_fk_match_by_p1_5_evidence": dict(sorted(p1_5_match_strata.items())),
            "packet28_vs_p1_5_multi_fk_by_p1_5_candidate_count": dict(sorted(p1_5_multi_candidate_strata.items())),
        },
        "raw_question_text_written": False,
        "raw_sql_written": False,
        "question_hashes_in_public_aggregate": False,
    }
    private = {**aggregate, "private_pairwise_question_crosswalks": private_pairs}
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.aggregate_output.parent.mkdir(parents=True, exist_ok=True)
    with args.private_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(private, ensure_ascii=False, indent=2) + "\n")
    with args.aggregate_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    os.chmod(args.private_output, 0o600)
    os.chmod(args.aggregate_output, 0o644)
    print(json.dumps({"status": aggregate["status"], "question_count": EXPECTED_N, "pre_registered_disagreement_strata": aggregate["pre_registered_disagreement_strata"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Keep private SQL, questions, and local values out of CLI error output.
        print(json.dumps({"status": "STOP_INVALID", "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
