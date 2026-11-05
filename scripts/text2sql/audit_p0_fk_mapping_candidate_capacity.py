#!/usr/bin/env python3
"""Aggregate-only capacity audit for the frozen BIRD FK-mapping pilot pool.

Gold SQL is parsed in memory via the existing packet helper. No question,
database, table, column, mapping, SQL, packet, or reviewer-response identity is
written to disk or stdout.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import sqlglot

import prepare_p0_fk_disagreement_review_packet as prep


EXPERIMENT_ID = "p0_fk_mapping_candidate_capacity_20261106_01"
EXPECTED_RUN_ID = "p0_fk_mapping_candidate_capacity_20261106_01"
MAX_WALL_SECONDS = 600.0
MAX_CPU_SECONDS = 300.0
MAX_RSS_GIB = 4.0
SMOKE_QUESTION_COUNT = 5
MIN_FK_BEARING_PAIRS = 30
MIN_AMBIGUOUS_PAIRS = 20
MIN_DATABASES = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def peak_rss_gib() -> float:
    # Linux reports ru_maxrss in KiB.
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / (1024**2)


def histogram(values: list[int]) -> dict[str, int]:
    counts = collections.Counter(values)
    return {str(key): counts[key] for key in sorted(counts)}


def remaining_range(per_question: list[int]) -> dict[str, int]:
    if len(per_question) < SMOKE_QUESTION_COUNT:
        raise prep.StopRun("JOIN_QUESTION_POOL_BELOW_SMOKE_SIZE")
    total = sum(per_question)
    largest_removed = sum(sorted(per_question, reverse=True)[:SMOKE_QUESTION_COUNT])
    smallest_removed = sum(sorted(per_question)[:SMOKE_QUESTION_COUNT])
    return {
        "minimum_after_any_five_question_smoke": total - largest_removed,
        "maximum_after_any_five_question_smoke": total - smallest_removed,
    }


def anonymous_database_histogram(counts: list[int]) -> dict[str, int]:
    buckets = {"0": 0, "1": 0, "2-5": 0, "6+": 0}
    for count in counts:
        if count == 0:
            buckets["0"] += 1
        elif count == 1:
            buckets["1"] += 1
        elif count <= 5:
            buckets["2-5"] += 1
        else:
            buckets["6+"] += 1
    return buckets


def db_coverage_worst_case_after_smoke(per_db_question_support: dict[str, int]) -> int:
    supported = [count for count in per_db_question_support.values() if count > 0]
    best_wipe = 0
    for mask in range(1 << len(supported)):
        wiped_questions = sum(
            supported[index]
            for index in range(len(supported))
            if mask & (1 << index)
        )
        if wiped_questions <= SMOKE_QUESTION_COUNT:
            best_wipe = max(best_wipe, mask.bit_count())
    return len(supported) - best_wipe


def write_json_private(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_log(path: Path, records: list[str]) -> None:
    path.write_text("\n".join(records) + "\n", encoding="utf-8")
    path.chmod(0o600)


def make_summary(
    frozen: dict[str, Any],
    args: argparse.Namespace,
    repo_root: Path,
    started_at: str,
    wall_start: float,
    cpu_start: float,
    parse_failures: collections.Counter[str],
    pair_counts: collections.Counter[int],
    question_pair_counts: list[dict[str, Any]],
    db_pair_counts: dict[str, collections.Counter[str]],
    join_questions: int,
    parsed_questions: int,
) -> dict[str, Any]:
    pair_total = sum(pair_counts.values())
    fk_bearing = sum(count for multiplicity, count in pair_counts.items() if multiplicity >= 1)
    ambiguous = sum(count for multiplicity, count in pair_counts.items() if multiplicity >= 2)
    per_question_fk = [row["fk_bearing_pairs"] for row in question_pair_counts]
    per_question_ambiguous = [row["ambiguous_pairs"] for row in question_pair_counts]
    per_question_any_fk = [int(value > 0) for value in per_question_fk]

    per_db_fk = [counts["fk_bearing_pairs"] for counts in db_pair_counts.values()]
    per_db_ambiguous = [counts["ambiguous_pairs"] for counts in db_pair_counts.values()]
    databases_with_fk = sum(value > 0 for value in per_db_fk)
    databases_with_ambiguous = sum(value > 0 for value in per_db_ambiguous)
    db_question_support = {
        db_key: counts["ambiguous_questions"]
        for db_key, counts in db_pair_counts.items()
    }

    min_after_smoke = {
        "fk_bearing_pairs": remaining_range(per_question_fk)["minimum_after_any_five_question_smoke"],
        "ambiguous_pairs": remaining_range(per_question_ambiguous)["minimum_after_any_five_question_smoke"],
        "questions_with_any_fk_pair": join_questions
        - sum(sorted(per_question_any_fk, reverse=True)[:SMOKE_QUESTION_COUNT]),
        "databases_with_ambiguous_pairs": db_coverage_worst_case_after_smoke(db_question_support),
    }
    max_after_smoke = {
        "fk_bearing_pairs": remaining_range(per_question_fk)["maximum_after_any_five_question_smoke"],
        "ambiguous_pairs": remaining_range(per_question_ambiguous)["maximum_after_any_five_question_smoke"],
        "questions_with_any_fk_pair": join_questions
        - sum(sorted(per_question_any_fk)[:SMOKE_QUESTION_COUNT]),
        "databases_with_ambiguous_pairs": databases_with_ambiguous,
    }

    best_case_meets_capacity = (
        max_after_smoke["fk_bearing_pairs"] >= MIN_FK_BEARING_PAIRS
        and max_after_smoke["ambiguous_pairs"] >= MIN_AMBIGUOUS_PAIRS
        and max_after_smoke["databases_with_ambiguous_pairs"] >= MIN_DATABASES
    )
    worst_case_meets_capacity = (
        min_after_smoke["fk_bearing_pairs"] >= MIN_FK_BEARING_PAIRS
        and min_after_smoke["ambiguous_pairs"] >= MIN_AMBIGUOUS_PAIRS
        and min_after_smoke["databases_with_ambiguous_pairs"] >= MIN_DATABASES
    )
    if len(parse_failures) > 0 and not best_case_meets_capacity:
        decision = "INCONCLUSIVE_PARSE_FAILURES"
    elif len(parse_failures) > 0:
        decision = "CAPACITY_POSSIBLE_ON_PARSED_SUBSET_PARSE_FAILURES_PRESENT"
    elif not best_case_meets_capacity:
        decision = "CAPACITY_INSUFFICIENT"
    elif worst_case_meets_capacity:
        decision = "CAPACITY_SUFFICIENT_FOR_ANY_FIVE_QUESTION_SMOKE"
    else:
        decision = "CAPACITY_POSSIBLE_WITH_SMOKE_SELECTION"

    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    rss_gib = peak_rss_gib()
    if wall_seconds > MAX_WALL_SECONDS:
        raise prep.StopRun("RESOURCE_WALL_LIMIT")
    if cpu_seconds > MAX_CPU_SECONDS:
        raise prep.StopRun("RESOURCE_CPU_LIMIT")
    if rss_gib > MAX_RSS_GIB:
        raise prep.StopRun("RESOURCE_RSS_LIMIT")

    return {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "status": "COMPLETED",
        "capacity_decision": decision,
        "started_at_utc": started_at,
        "source_commit": current_commit(repo_root),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "python_version": platform.python_version(),
        "sqlglot_version": sqlglot.__version__,
        "input_sha256": frozen["input_hashes"],
        "frozen_population": {
            "join_on_questions": join_questions,
            "parsed_questions": parsed_questions,
            "target_parse_failures_by_reason": dict(sorted(parse_failures.items())),
            "question_table_pairs": pair_total,
            "fk_bearing_question_table_pairs": fk_bearing,
            "ambiguous_question_table_pairs_with_two_or_more_mappings": ambiguous,
            "questions_with_any_fk_bearing_pair": sum(value > 0 for value in per_question_fk),
            "questions_with_any_ambiguous_pair": sum(value > 0 for value in per_question_ambiguous),
            "database_count": len(db_pair_counts),
            "databases_with_fk_bearing_pairs": databases_with_fk,
            "databases_with_ambiguous_pairs": databases_with_ambiguous,
            "mapping_multiplicity_histogram": histogram(
                [multiplicity for multiplicity, count in pair_counts.items() for _ in range(count)]
            ),
            "per_database_fk_pair_count_bucket_histogram": anonymous_database_histogram(per_db_fk),
            "per_database_ambiguous_pair_count_bucket_histogram": anonymous_database_histogram(
                per_db_ambiguous
            ),
        },
        "after_removing_any_five_join_question_smoke": {
            "best_case_remaining_capacity": max_after_smoke,
            "worst_case_remaining_capacity": min_after_smoke,
            "range_complete": len(parse_failures) == 0,
            "range_basis": "all JOIN ON questions; parse failures contribute zero observed pairs",
        },
        "necessary_capacity_thresholds": {
            "fk_bearing_question_table_pairs": MIN_FK_BEARING_PAIRS,
            "ambiguous_question_table_pairs": MIN_AMBIGUOUS_PAIRS,
            "databases_with_ambiguous_pairs": MIN_DATABASES,
        },
        "resource_usage": {
            "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6),
            "peak_rss_gib": round(rss_gib, 6),
            "limits": {
                "wall_seconds": MAX_WALL_SECONDS,
                "cpu_seconds": MAX_CPU_SECONDS,
                "peak_rss_gib": MAX_RSS_GIB,
            },
            "gpu_seconds": 0,
            "model_calls": 0,
            "api_calls": 0,
            "sql_execution_calls": 0,
        },
        "privacy": {
            "question_ids_written": False,
            "database_ids_written": False,
            "sql_written": False,
            "table_or_column_names_written": False,
            "mapping_ids_written": False,
            "reviewer_response_files_read": False,
        },
    }


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--fk-artifact", type=Path, required=True)
    parser.add_argument("--crosswalk-private", type=Path, required=True)
    parser.add_argument("--canonical-full", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.run_id != EXPECTED_RUN_ID:
        raise prep.StopRun("RUN_ID_MISMATCH")
    if not args.repo_root.is_dir():
        raise prep.StopRun("REPO_ROOT_MISSING")
    if current_commit(args.repo_root) != args.expected_commit:
        raise prep.StopRun("SOURCE_COMMIT_MISMATCH")
    if args.output_dir.exists():
        raise prep.StopRun("OUTPUT_DIRECTORY_EXISTS")

    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    log_path = args.output_dir / "run.log"
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log_records = [
        f"experiment_id={EXPERIMENT_ID}",
        f"run_id={args.run_id}",
        f"source_commit={args.expected_commit}",
        "stage=load_frozen_inputs",
    ]

    try:
        frozen = prep.load_frozen_inputs(args)
        log_records.append("stage=scan_join_on_questions")
        pair_counts: collections.Counter[int] = collections.Counter()
        parse_failures: collections.Counter[str] = collections.Counter()
        question_pair_counts: list[dict[str, Any]] = []
        db_pair_counts: dict[str, collections.Counter[str]] = collections.defaultdict(
            collections.Counter
        )
        join_questions = 0
        parsed_questions = 0
        for index, (question_key, canonical) in enumerate(frozen["canonical"].items(), start=1):
            if canonical.get("has_join_on") is not True:
                continue
            join_questions += 1
            question = frozen["questions"][question_key]
            db_id = str(question["db_id"])
            case = {
                "case_id": f"Q{index:04d}",
                "sql": question.get("SQL"),
            }
            try:
                groups = prep.parse_target_pairs(
                    case,
                    frozen["schemas"].get(db_id, {}),
                    frozen["fk_by_db"].get(db_id, []),
                )
            except prep.StopRun as exc:
                parse_failures[exc.reason_code] += 1
                question_pair_counts.append(
                    {"fk_bearing_pairs": 0, "ambiguous_pairs": 0}
                )
                continue

            parsed_questions += 1
            db_id_folded = db_id.casefold()
            for group in groups:
                identities = {mapping["identity"] for mapping in group["mappings"]}
                multiplicity = len(identities)
                pair_counts[multiplicity] += 1
                if multiplicity >= 1:
                    db_pair_counts[db_id_folded]["fk_bearing_pairs"] += 1
                if multiplicity >= 2:
                    db_pair_counts[db_id_folded]["ambiguous_pairs"] += 1

            fk_pair_count = sum(bool(group["mappings"]) for group in groups)
            ambiguous_pair_count = sum(len(group["mappings"]) >= 2 for group in groups)
            question_pair_counts.append(
                {
                    "fk_bearing_pairs": fk_pair_count,
                    "ambiguous_pairs": ambiguous_pair_count,
                }
            )
            if ambiguous_pair_count > 0:
                db_pair_counts[db_id_folded]["ambiguous_questions"] += 1

        for db_id in frozen["schemas"]:
            db_pair_counts.setdefault(str(db_id).casefold(), collections.Counter())

        summary = make_summary(
            frozen,
            args,
            args.repo_root,
            started_at,
            wall_start,
            cpu_start,
            parse_failures,
            pair_counts,
            question_pair_counts,
            db_pair_counts,
            join_questions,
            parsed_questions,
        )
        write_json_private(args.output_dir / "aggregate_summary.json", summary)
        log_records.extend(
            [
                f"status={summary['status']}",
                f"capacity_decision={summary['capacity_decision']}",
                f"join_on_questions={join_questions}",
                f"parsed_questions={parsed_questions}",
                f"parse_failure_count={sum(parse_failures.values())}",
                "private_aggregate_written=true",
            ]
        )
        write_log(log_path, log_records)
        print(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": args.run_id,
                    "status": summary["status"],
                    "capacity_decision": summary["capacity_decision"],
                    "aggregate_summary": str(args.output_dir / "aggregate_summary.json"),
                    "source_commit": summary["source_commit"],
                    "script_sha256": summary["script_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    except prep.StopRun as exc:
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "STOP",
            "reason_code": exc.reason_code,
            "source_commit": args.expected_commit,
            "input_hashes_verified": exc.reason_code != "INPUT_HASH_MISMATCH",
            "privacy": {
                "question_ids_written": False,
                "database_ids_written": False,
                "sql_written": False,
                "reviewer_response_files_read": False,
            },
        }
        write_json_private(args.output_dir / "failure_receipt.json", failure)
        log_records.append(f"status=STOP reason_code={exc.reason_code}")
        write_log(log_path, log_records)
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not print exception text: parser exceptions may contain source SQL.
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "STOP_UNEXPECTED_EXCEPTION",
            "exception_type": type(exc).__name__,
            "source_commit": args.expected_commit,
            "privacy": {"raw_exception_text_written": False, "reviewer_response_files_read": False},
        }
        write_json_private(args.output_dir / "failure_receipt.json", failure)
        log_records.append(f"status=STOP_UNEXPECTED_EXCEPTION type={type(exc).__name__}")
        write_log(log_path, log_records)
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
