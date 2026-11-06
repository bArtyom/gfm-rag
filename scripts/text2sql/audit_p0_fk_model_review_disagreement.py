#!/usr/bin/env python3
"""Aggregate anonymous, descriptive features of a frozen two-model review."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

EXPECTED_HASHES = {
    "packet_a": "0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2",
    "packet_b": "a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb",
    "reviewer_a": "f3d2beb21290c49790679e53ac0bf8dc50084b7b34ee228843f06330ac120883",
    "reviewer_b": "2b49a5772f061ed70f02ea21811e392fd6afd086fa7030aca9fe737c2c8af077",
}
CASE_RE = re.compile(r"(?m)^## Case ([A-Za-z0-9_-]+)\s*$")
PAIR_RE = re.compile(r"(?m)^### Pair ([A-Za-z0-9_-]+): (.+?)\s*$")
MAPPING_RE = re.compile(r"(?m)^\|\s*(M[0-9A-F]+)\s*\|\s*(.*?)\s*\|\s*$")
VALID_DECISIONS = {
    "single_mapping", "multiple_mappings", "cannot_determine", "no_declared_fk", "other"
}
VALID_RATIONALES = {
    "question_explicit", "context_supports", "role_ambiguity", "schema_conflict", "other"
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_packet(path: Path) -> dict[str, list[str]]:
    raw = path.read_text(encoding="utf-8")
    cases = list(CASE_RE.finditer(raw))
    result: dict[str, list[str]] = {}
    for i, case in enumerate(cases):
        end = cases[i + 1].start() if i + 1 < len(cases) else len(raw)
        body = raw[case.end():end]
        pairs = list(PAIR_RE.finditer(body))
        for j, pair in enumerate(pairs):
            pair_end = pairs[j + 1].start() if j + 1 < len(pairs) else len(body)
            pair_body = body[pair.end():pair_end]
            mapping_ids = [match.group(1) for match in MAPPING_RE.finditer(pair_body)]
            pair_id = pair.group(1)
            if pair_id in result or len(mapping_ids) < 2 or len(set(mapping_ids)) != len(mapping_ids):
                raise ValueError("packet structural validation failed")
            result[pair_id] = mapping_ids
    if len(result) != 60:
        raise ValueError("expected exactly 60 frozen review units")
    return result


def read_outputs(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            pair_id = record.get("pair_id")
            if not isinstance(pair_id, str) or pair_id in result:
                raise ValueError("review output has invalid or duplicated unit key")
            # Raw generations are parsed by JSON but never copied into any result.
            result[pair_id] = {
                "valid": record.get("valid") is True,
                "invalid_reason": record.get("invalid_reason"),
                "answer": record.get("answer") if record.get("valid") is True else None,
            }
    if len(result) != 60:
        raise ValueError("expected exactly 60 output rows per reviewer")
    return result


def checked_answer(record: dict, candidate_ids: list[str]) -> dict | None:
    answer = record.get("answer")
    if not record["valid"]:
        return None
    if not isinstance(answer, dict):
        raise ValueError("valid output is missing structured answer")
    if answer.get("decision") not in VALID_DECISIONS:
        raise ValueError("answer contains an unknown decision category")
    if answer.get("rationale_code") not in VALID_RATIONALES:
        raise ValueError("answer contains an unknown rationale category")
    confidence = answer.get("confidence")
    if type(confidence) is not int or confidence not in {1, 2, 3}:
        raise ValueError("answer contains an invalid confidence value")
    accepted = answer.get("accepted_mapping_ids")
    if not isinstance(accepted, list) or any(not isinstance(value, str) for value in accepted):
        raise ValueError("answer contains an invalid accepted-ID list")
    if len(accepted) != len(set(accepted)) or not set(accepted) <= set(candidate_ids):
        raise ValueError("answer has duplicate or out-of-packet mapping IDs")
    return answer


def rate_cell(total: int, numerator: int) -> dict[str, float | int]:
    return {
        "units": total,
        "exact_agreements": numerator,
        "agreement_rate": round(numerator / total, 6) if total else None,
    }


def summarize_reviewer(rows: dict[str, dict], packet: dict[str, list[str]]) -> dict:
    decisions: Counter[str] = Counter()
    rationales: Counter[str] = Counter()
    confidences: Counter[str] = Counter()
    position = {"single_first": 0, "single_later": 0, "multiple_includes_first": 0,
                "multiple_excludes_first": 0}
    for pair_id, row in rows.items():
        if not row["valid"]:
            continue
        answer = checked_answer(row, packet[pair_id])
        assert answer is not None
        decision = answer["decision"]
        decisions[decision] += 1
        rationales[answer["rationale_code"]] += 1
        confidences[str(answer["confidence"])] += 1
        accepted = set(answer["accepted_mapping_ids"])
        if decision == "single_mapping":
            chosen = next(iter(accepted))
            position["single_first" if packet[pair_id].index(chosen) == 0 else "single_later"] += 1
        elif decision == "multiple_mappings":
            key = "multiple_includes_first" if packet[pair_id][0] in accepted else "multiple_excludes_first"
            position[key] += 1
    invalid = Counter(row["invalid_reason"] for row in rows.values() if row["invalid_reason"])
    return {
        "valid_outputs": sum(row["valid"] for row in rows.values()),
        "invalid_reasons": dict(sorted(invalid.items())),
        "decision_counts": dict(sorted(decisions.items())),
        "rationale_counts": dict(sorted(rationales.items())),
        "confidence_counts": dict(sorted(confidences.items())),
        "selection_position_counts": position,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--output-a", type=Path, required=True)
    parser.add_argument("--output-b", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if current_commit != args.expected_commit:
        raise ValueError("source commit does not match the registered commit")

    input_paths = {
        "packet_a": args.packet_a,
        "packet_b": args.packet_b,
        "reviewer_a": args.output_a,
        "reviewer_b": args.output_b,
    }
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    if input_hashes != EXPECTED_HASHES:
        raise ValueError("a frozen review input hash does not match the registered value")

    packet_a, packet_b = parse_packet(args.packet_a), parse_packet(args.packet_b)
    if set(packet_a) != set(packet_b):
        raise ValueError("A/B packet unit sets differ")
    if any(set(packet_a[pair]) != set(packet_b[pair]) for pair in packet_a):
        raise ValueError("A/B candidate sets differ")
    rows_a, rows_b = read_outputs(args.output_a), read_outputs(args.output_b)
    if set(rows_a) != set(packet_a) or set(rows_b) != set(packet_b):
        raise ValueError("review output coverage differs from frozen packet")

    candidate_hist: Counter[str] = Counter()
    order_hist: Counter[str] = Counter()
    groups_candidate: dict[str, list[int]] = {}
    groups_order: dict[str, list[int]] = {}
    decision_pairs: Counter[str] = Counter()
    rationale_pairs: Counter[str] = Counter()
    both_valid = 0
    exact = 0
    different_decision = 0
    same_decision_different_set = 0
    both_confident = 0
    high_confidence_exact = 0
    for pair_id, ids_a in packet_a.items():
        ids_b = packet_b[pair_id]
        candidate_bucket = str(len(ids_a))
        order_bucket = "same_order" if ids_a == ids_b else "different_order"
        candidate_hist[candidate_bucket] += 1
        order_hist[order_bucket] += 1
        groups_candidate.setdefault(candidate_bucket, [0, 0, 0])
        groups_order.setdefault(order_bucket, [0, 0, 0])
        groups_candidate[candidate_bucket][0] += 1
        groups_order[order_bucket][0] += 1

        a = checked_answer(rows_a[pair_id], ids_a)
        b = checked_answer(rows_b[pair_id], ids_b)
        if a is None or b is None:
            continue
        both_valid += 1
        groups_candidate[candidate_bucket][1] += 1
        groups_order[order_bucket][1] += 1
        decision_pairs[f"{a['decision']}|{b['decision']}"] += 1
        rationale_pairs[f"{a['rationale_code']}|{b['rationale_code']}"] += 1
        same_decision = a["decision"] == b["decision"]
        same_set = set(a["accepted_mapping_ids"]) == set(b["accepted_mapping_ids"])
        is_exact = same_decision and same_set
        if is_exact:
            exact += 1
            groups_candidate[candidate_bucket][2] += 1
            groups_order[order_bucket][2] += 1
        elif not same_decision:
            different_decision += 1
        else:
            same_decision_different_set += 1
        if a["confidence"] >= 2 and b["confidence"] >= 2:
            both_confident += 1
            high_confidence_exact += int(is_exact)

    reviewer_a = summarize_reviewer(rows_a, packet_a)
    reviewer_b = summarize_reviewer(rows_b, packet_b)
    candidate_groups = {
        key: {
            "units": values[0],
            "both_valid": values[1],
            "exact_agreements": values[2],
            "agreement_rate_among_both_valid": round(values[2] / values[1], 6) if values[1] else None,
        }
        for key, values in sorted(groups_candidate.items())
    }
    order_groups = {
        key: {
            "units": values[0],
            "both_valid": values[1],
            "exact_agreements": values[2],
            "agreement_rate_among_both_valid": round(values[2] / values[1], 6) if values[1] else None,
        }
        for key, values in sorted(groups_order.items())
    }
    result = {
        "analysis_id": "p0_fk_model_review_disagreement_audit_20261106_01",
        "run_id": args.run_id,
        "source_commit": current_commit,
        "analysis_type": "read_only_exploratory_error_attribution",
        "model_calls": 0,
        "gold_sql_or_human_reply_files_read": False,
        "review_units": 60,
        "candidate_mapping_count": sum(candidate_hist[key] * int(key) for key in candidate_hist),
        "candidate_count_histogram": dict(sorted(candidate_hist.items())),
        "candidate_order_different_count": order_hist["different_order"],
        "candidate_order_histogram": dict(sorted(order_hist.items())),
        "reviewer_a": reviewer_a,
        "reviewer_b": reviewer_b,
        "both_valid_count": both_valid,
        "exact_decision_and_set_agreement_count": exact,
        "exact_agreement_rate_both_valid": round(exact / both_valid, 6) if both_valid else None,
        "different_decision_count": different_decision,
        "same_decision_different_accepted_set_count": same_decision_different_set,
        "both_confidence_at_least_2_count": both_confident,
        "exact_agreement_among_both_confidence_at_least_2_count": high_confidence_exact,
        "agreement_by_candidate_count": candidate_groups,
        "agreement_by_candidate_order": order_groups,
        "decision_pair_counts": dict(sorted(decision_pairs.items())),
        "rationale_pair_counts": dict(sorted(rationale_pairs.items())),
        "privacy": {
            "contains_questions_or_schema_names": False,
            "contains_mapping_ids_or_case_ids": False,
            "contains_model_raw_outputs": False,
            "contains_gold_sql_or_human_review": False,
        },
        "input_sha256": input_hashes,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }

    if not (
        reviewer_a["valid_outputs"] == 59
        and reviewer_b["valid_outputs"] == 58
        and both_valid == 57
        and exact == 28
        and candidate_hist == Counter({"2": 45, "3": 15})
        and order_hist == Counter({"same_order": 29, "different_order": 31})
    ):
        raise ValueError("frozen public-summary integrity gate failed")

    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    output_path = args.output_dir / "aggregate_summary.json"
    with output_path.open("x", encoding="utf-8") as stream:
        os.chmod(output_path, 0o600)
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
