#!/usr/bin/env python3
"""Compare private hashed crosswalks from the frozen FK audit definitions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

EXPECTED_N = 1534


def load_result(path: Path, expected_method: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") != "FULL_COMPLETE" or result.get("mode") != "full":
        raise RuntimeError("Comparison input is not a completed full audit")
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

    pairs = {
        "packet_py310_sqlglot26_vs_packet_py312_sqlglot28": (crosswalks[0], crosswalks[1]),
        "packet_py312_sqlglot28_vs_p1_5_py312_sqlglot28": (crosswalks[1], crosswalks[2]),
    }
    public_pairs: dict[str, Any] = {}
    private_pairs: dict[str, Any] = {}
    for name, (left, right) in pairs.items():
        public_pairs[name] = {
            "fk_match": pair_summary(left, right, "fk_match"),
            "multi_fk_candidate": pair_summary(left, right, "multi_fk_candidate"),
            "parse_ok": pair_summary(left, right, "parse_ok"),
            "join_on": pair_summary(left, right, "has_join_on"),
        }
        private_pairs[name] = []
        for key in sorted(left):
            private_pairs[name].append({
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

    aggregate = {
        "experiment_id": "p0_fk_candidate_definition_reconciliation_20261105_01",
        "status": "CROSSWALK_COMPLETE",
        "question_count": EXPECTED_N,
        "definitions": {
            "packet_py310_sqlglot26": packet26["metadata"]["denominators"],
            "packet_py312_sqlglot28": packet28["metadata"]["denominators"],
            "p1_5_py312_sqlglot28": p1_5_28["metadata"]["denominators"],
        },
        "pairwise_categories": public_pairs,
        "raw_question_text_written": False,
        "raw_sql_written": False,
        "question_hashes_in_public_aggregate": False,
    }
    private = {
        **aggregate,
        "private_pairwise_question_crosswalks": private_pairs,
    }
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.aggregate_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.aggregate_output.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.private_output, 0o600)
    os.chmod(args.aggregate_output, 0o644)
    print(json.dumps({"status": aggregate["status"], "question_count": EXPECTED_N, "pairwise_categories": public_pairs}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "STOP_INVALID", "error_type": type(exc).__name__}, ensure_ascii=False), file=__import__("sys").stderr)
        raise SystemExit(1)
