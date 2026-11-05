#!/usr/bin/env python3
"""Prepare a private, blinded pair-level review packet for FK mappings.

This is a materials-preparation run only. It creates no labels and does not
read previous reviewer response files. Raw questions, SQL, database/table
identities, mappings, packets, and manifests remain in a local 0700/0600 tree.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import html
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

import prepare_p0_fk_disagreement_review_packet as frozen_loader


EXPERIMENT_ID = "p0_fk_mapping_pair_level_blind_review_20261106_01"
EXPECTED_RUN_ID = EXPERIMENT_ID
SEED = 20261106
JOIN_ON_EXPECTED = 1140
PARSED_EXPECTED = 1127
PARSE_FAILURES_EXPECTED = {"JOIN_PAIR_EXTRACTION_INCOMPLETE": 13}
AMBIGUOUS_PAIR_EXPECTED = 176
AMBIGUOUS_QUESTION_EXPECTED = 175
AMBIGUOUS_DATABASE_EXPECTED = 4
SMOKE_SIZE = 5
FULL_SIZE = 60
TARGET_PER_DATABASE = 15
MIN_DATABASES = 3
MAX_WALL_SECONDS = 600.0
MAX_CPU_SECONDS = 300.0
MAX_RSS_GIB = 4.0
RESPONSE_FIELDS = [
    "case_id",
    "pair_id",
    "decision",
    "accepted_mapping_ids",
    "confidence_1_low_2_medium_3_high",
    "rationale_code",
    "notes",
]


class StopRun(Exception):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def peak_rss_gib() -> float:
    # Linux reports ru_maxrss in KiB.
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / (1024**2)


def file_mode_600(path: Path) -> None:
    path.chmod(0o600)


def private_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    file_mode_600(path)


def check_resources(wall_start: float, cpu_start: float) -> dict[str, float]:
    usage = {
        "wall_seconds": round(time.perf_counter() - wall_start, 6),
        "cpu_seconds": round(time.process_time() - cpu_start, 6),
        "peak_rss_gib": round(peak_rss_gib(), 6),
    }
    if usage["wall_seconds"] > MAX_WALL_SECONDS:
        raise StopRun("RESOURCE_WALL_LIMIT")
    if usage["cpu_seconds"] > MAX_CPU_SECONDS:
        raise StopRun("RESOURCE_CPU_LIMIT")
    if usage["peak_rss_gib"] > MAX_RSS_GIB:
        raise StopRun("RESOURCE_RSS_LIMIT")
    return usage


def load_frozen(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "dev.json": args.dev_json,
        "dev_tables.json": args.tables_json,
        "fk_artifact": args.fk_artifact,
        "crosswalk_private": args.crosswalk_private,
        "canonical_full": args.canonical_full,
    }
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    loader_args = argparse.Namespace(
        dev_json=args.dev_json,
        tables_json=args.tables_json,
        fk_artifact=args.fk_artifact,
        crosswalk_private=args.crosswalk_private,
        canonical_full=args.canonical_full,
    )
    # The shared frozen loader pins all five input hashes, question-key joins,
    # FK identity counts, and the historical JOIN-ON denominator. It never
    # reads blind-review packets or response files.
    frozen = frozen_loader.load_frozen_inputs(loader_args)
    frozen["input_hashes"] = hashes
    return frozen


def build_candidate_pool(frozen: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    join_on_questions = 0
    parsed_questions = 0
    parse_failures: collections.Counter[str] = collections.Counter()
    all_ambiguous_pairs = 0
    candidates: list[dict[str, Any]] = []

    for question_key, canonical in sorted(frozen["canonical"].items()):
        if canonical.get("has_join_on") is not True:
            continue
        join_on_questions += 1
        record = frozen["questions"][question_key]
        db_id = str(record["db_id"])
        sql = record.get("SQL")
        if not isinstance(sql, str) or not sql.strip():
            raise StopRun("JOIN_ON_SQL_MISSING")
        try:
            groups = frozen_loader.parse_target_pairs(
                {"case_id": "SOURCE", "sql": sql},
                frozen["schemas"].get(db_id, {}),
                frozen["fk_by_db"].get(db_id, []),
            )
        except frozen_loader.StopRun as exc:
            parse_failures[exc.reason_code] += 1
            continue
        parsed_questions += 1

        ambiguous = [group for group in groups if len(group["mappings"]) >= 2]
        all_ambiguous_pairs += len(ambiguous)
        if not ambiguous:
            continue
        # A question contributes at most one pair. The selection is fixed by
        # the preregistered seed and opaque question/pair keys, never labels or
        # model scores.
        selected = min(
            ambiguous,
            key=lambda group: stable_hash(
                [SEED, "one_pair_per_question", question_key, list(group["pair_key"])]
            ),
        )
        question = record.get("question")
        if not isinstance(question, str) or not question.strip():
            raise StopRun("QUESTION_TEXT_MISSING")
        candidates.append(
            {
                "question_key_sha256": question_key,
                "db_id": db_id,
                "question_id": str(record.get("question_id", "")),
                "question": question,
                "gold_sql_private": sql,
                "pair_key_private": list(selected["pair_key"]),
                "left_table": selected["left_table"],
                "right_table": selected["right_table"],
                "mappings": [
                    {
                        "identity_private": [
                            mapping["identity"][0],
                            mapping["identity"][1],
                            [list(pair) for pair in mapping["identity"][2]],
                            mapping["identity"][3],
                        ],
                        "child_table": mapping["child_table"],
                        "parent_table": mapping["parent_table"],
                        "ordered_column_pairs": [
                            list(pair) for pair in mapping["ordered_column_pairs"]
                        ],
                        "duplicate_multiplicity_private": int(mapping["multiplicity"]),
                    }
                    for mapping in selected["mappings"]
                ],
            }
        )

    if join_on_questions != JOIN_ON_EXPECTED or parsed_questions != PARSED_EXPECTED:
        raise StopRun("JOIN_PARSE_CENSUS_MISMATCH")
    if dict(parse_failures) != PARSE_FAILURES_EXPECTED:
        raise StopRun("JOIN_PARSE_FAILURE_PROFILE_MISMATCH")
    if all_ambiguous_pairs != AMBIGUOUS_PAIR_EXPECTED:
        raise StopRun("AMBIGUOUS_PAIR_CENSUS_MISMATCH")
    if len(candidates) != AMBIGUOUS_QUESTION_EXPECTED:
        raise StopRun("AMBIGUOUS_QUESTION_CENSUS_MISMATCH")

    database_ids = sorted(
        {candidate["db_id"] for candidate in candidates},
        key=lambda db_id: stable_hash([EXPERIMENT_ID, SEED, "anonymous_database", db_id.casefold()]),
    )
    if len(database_ids) != AMBIGUOUS_DATABASE_EXPECTED:
        raise StopRun("AMBIGUOUS_DATABASE_CENSUS_MISMATCH")
    db_labels = {db_id: f"db_{index:02d}" for index, db_id in enumerate(database_ids, start=1)}
    counts = collections.Counter(candidate["db_id"] for candidate in candidates)
    census = {
        "join_on_questions": join_on_questions,
        "parsed_questions": parsed_questions,
        "parse_failures_by_reason": dict(sorted(parse_failures.items())),
        "ambiguous_question_table_pairs": all_ambiguous_pairs,
        "unique_ambiguous_questions": len(candidates),
        "ambiguous_database_count": len(database_ids),
        "ambiguous_questions_by_anonymous_database": {
            db_labels[db_id]: counts[db_id] for db_id in database_ids
        },
    }
    return candidates, {"census": census, "db_labels": db_labels, "database_ids": database_ids}


def select_smoke(
    candidates: list[dict[str, Any]], db_order: list[str]
) -> list[dict[str, Any]]:
    by_db: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for candidate in candidates:
        by_db[candidate["db_id"]].append(candidate)
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    for db_id in db_order:
        rows = by_db[db_id]
        chosen = min(
            rows,
            key=lambda row: stable_hash([SEED, "smoke", row["question_key_sha256"]]),
        )
        selected.append(chosen)
        selected_keys.add(chosen["question_key_sha256"])
    remaining = sorted(
        (row for row in candidates if row["question_key_sha256"] not in selected_keys),
        key=lambda row: stable_hash([SEED, "smoke_fill", row["question_key_sha256"]]),
    )
    selected.extend(remaining[: SMOKE_SIZE - len(selected)])
    if len(selected) != SMOKE_SIZE:
        raise StopRun("SMOKE_SAMPLE_UNAVAILABLE")
    return selected


def select_full(
    candidates: list[dict[str, Any]], smoke: list[dict[str, Any]], db_order: list[str]
) -> list[dict[str, Any]]:
    smoke_keys = {row["question_key_sha256"] for row in smoke}
    eligible = [row for row in candidates if row["question_key_sha256"] not in smoke_keys]
    if len(eligible) < FULL_SIZE:
        raise StopRun("FULL_SAMPLE_BELOW_60_AFTER_SMOKE")
    by_db: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in eligible:
        by_db[row["db_id"]].append(row)
    for db_id in db_order:
        by_db[db_id].sort(
            key=lambda row: stable_hash([SEED, "full", row["question_key_sha256"]])
        )

    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    for db_id in db_order:
        take = min(TARGET_PER_DATABASE, len(by_db[db_id]))
        chosen = by_db[db_id][:take]
        selected.extend(chosen)
        selected_keys.update(row["question_key_sha256"] for row in chosen)

    if len(selected) < FULL_SIZE:
        leftovers = sorted(
            (row for row in eligible if row["question_key_sha256"] not in selected_keys),
            key=lambda row: stable_hash([SEED, "redistribute", row["question_key_sha256"]]),
        )
        selected.extend(leftovers[: FULL_SIZE - len(selected)])
    if len(selected) != FULL_SIZE:
        raise StopRun("FULL_SAMPLE_SIZE_MISMATCH")
    if len({row["db_id"] for row in selected}) < MIN_DATABASES:
        raise StopRun("FULL_DATABASE_COVERAGE_BELOW_MINIMUM")
    if len({row["question_key_sha256"] for row in selected}) != FULL_SIZE:
        raise StopRun("FULL_QUESTION_DUPLICATE")
    return selected


def renderable_cases(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda row: stable_hash([SEED, "case_id", row["question_key_sha256"]]),
    )
    cases: list[dict[str, Any]] = []
    all_mapping_ids: set[str] = set()
    for index, candidate in enumerate(ordered, start=1):
        case_id = f"C{index:03d}"
        pair_id = f"{case_id}-P01"
        mappings = []
        for mapping in candidate["mappings"]:
            mapping_id = "M" + stable_hash(
                [
                    EXPERIMENT_ID,
                    SEED,
                    candidate["question_key_sha256"],
                    candidate["pair_key_private"],
                    mapping["identity_private"],
                ]
            )[:10].upper()
            if mapping_id in all_mapping_ids:
                raise StopRun("ANONYMOUS_MAPPING_ID_COLLISION")
            all_mapping_ids.add(mapping_id)
            mappings.append({**mapping, "mapping_id": mapping_id})
        if len(mappings) < 2:
            raise StopRun("SELECTED_PAIR_NOT_AMBIGUOUS")
        cases.append(
            {
                "case_id": case_id,
                "pair_id": pair_id,
                "question_key_sha256": candidate["question_key_sha256"],
                "db_id_private": candidate["db_id"],
                "question_id_private": candidate["question_id"],
                "question": candidate["question"],
                "gold_sql_private": candidate["gold_sql_private"],
                "pair_key_private": candidate["pair_key_private"],
                "left_table": candidate["left_table"],
                "right_table": candidate["right_table"],
                "mappings": mappings,
            }
        )
    return cases


def md_escape(value: Any) -> str:
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def render_packet(cases: list[dict[str, Any]], reviewer: str) -> tuple[str, list[dict[str, str]], list[str], dict[str, tuple[str, ...]]]:
    reviewer_seed = stable_hash([EXPERIMENT_ID, SEED, "reviewer", reviewer])
    ordered_cases = sorted(
        cases,
        key=lambda case: stable_hash([reviewer_seed, "case", case["case_id"]]),
    )
    case_order = [case["case_id"] for case in ordered_cases]
    lines = [
        "# Independent FK mapping review",
        "",
        "For each supplied table pair, judge which declared FK mappings the question supports.",
        "Assume the table pair is already supplied; this review does not evaluate table retrieval.",
        "Do not consult another reviewer. Gold SQL, JOIN conditions, model outputs, ranks, and source labels are omitted.",
        "Use the matching response CSV. Keep case, pair, and mapping IDs unchanged.",
        "",
        "Decision: single_mapping | multiple_mappings | cannot_determine | no_declared_fk | other.",
        "List every accepted mapping ID. Confidence: 1=low, 2=medium, 3=high.",
        "Rationale: question_explicit | context_supports | role_ambiguity | schema_conflict | other.",
        "A composite FK is shown as one complete mapping; do not split its ordered column pairs.",
        "",
    ]
    response_rows: list[dict[str, str]] = []
    mapping_orders: dict[str, tuple[str, ...]] = {}
    for case in ordered_cases:
        lines.extend(
            [
                f"## Case {case['case_id']}",
                "",
                md_escape(case["question"]),
                "",
                f"### Pair {case['pair_id']}: {md_escape(case['left_table'])} ↔ {md_escape(case['right_table'])}",
                "",
                "| Mapping ID | Complete declared FK mapping |",
                "|---|---|",
            ]
        )
        mappings = sorted(
            case["mappings"],
            key=lambda item: stable_hash(
                [reviewer_seed, "mapping", case["pair_id"], item["mapping_id"]]
            ),
        )
        mapping_orders[case["case_id"]] = tuple(item["mapping_id"] for item in mappings)
        for mapping in mappings:
            child = mapping["child_table"]
            parent = mapping["parent_table"]
            rendered_pairs = "; ".join(
                f"{child}.{child_col} = {parent}.{parent_col}"
                for child_col, parent_col in mapping["ordered_column_pairs"]
            )
            lines.append(f"| {mapping['mapping_id']} | {md_escape(rendered_pairs)} |")
        lines.extend(
            [
                "",
                "Decision: __________   Accepted mapping ID(s): __________",
                "Confidence (1–3): ____   Rationale code: __________",
                "Notes: __________________________________________________",
                "",
            ]
        )
        response_rows.append(
            {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "decision": "",
                "accepted_mapping_ids": "",
                "confidence_1_low_2_medium_3_high": "",
                "rationale_code": "",
                "notes": "",
            }
        )
    packet = "\n".join(lines) + "\n"
    for case in cases:
        if case["gold_sql_private"] and case["gold_sql_private"] in packet:
            raise StopRun("GOLD_SQL_LEAK_CHECK_FAILED")
        if case["question_key_sha256"] in packet:
            raise StopRun("QUESTION_KEY_LEAK_CHECK_FAILED")
    forbidden = (
        "packet_only_canonical",
        "canonical_only_multi_fk",
        "both_positive_controls",
        "crosswalk",
        "P1.5",
        "G-reasoner",
        "Dense cosine",
    )
    if any(marker.casefold() in packet.casefold() for marker in forbidden):
        raise StopRun("SOURCE_LABEL_LEAK_CHECK_FAILED")
    return packet, response_rows, case_order, mapping_orders


def validate_rendering(cases: list[dict[str, Any]], require_randomized: bool) -> dict[str, Any]:
    packet_a, rows_a, order_a, mappings_a = render_packet(cases, "A")
    packet_b, rows_b, order_b, mappings_b = render_packet(cases, "B")
    ids_a = {(row["case_id"], row["pair_id"]) for row in rows_a}
    ids_b = {(row["case_id"], row["pair_id"]) for row in rows_b}
    if ids_a != ids_b or len(ids_a) != len(cases):
        raise StopRun("REVIEWER_PAIR_SET_MISMATCH")
    expected_mapping_ids = {
        mapping["mapping_id"] for case in cases for mapping in case["mappings"]
    }
    seen_a = {mapping_id for mapping_ids in mappings_a.values() for mapping_id in mapping_ids}
    seen_b = {mapping_id for mapping_ids in mappings_b.values() for mapping_id in mapping_ids}
    if seen_a != expected_mapping_ids or seen_b != expected_mapping_ids:
        raise StopRun("REVIEWER_MAPPING_SET_MISMATCH")
    if order_a == order_b and len(cases) > 1:
        raise StopRun("REVIEWER_CASE_ORDER_NOT_SCRAMBLED")
    order_diff_count = sum(mappings_a[key] != mappings_b[key] for key in mappings_a)
    if require_randomized and order_diff_count == 0:
        raise StopRun("REVIEWER_MAPPING_ORDER_NOT_SCRAMBLED")
    return {
        "reviewer_case_order_differs": order_a != order_b,
        "cases_with_different_mapping_display_order": order_diff_count,
        "reviewer_pair_sets_match": True,
        "reviewer_mapping_sets_match": True,
        "packet_a_sha256": hashlib.sha256(packet_a.encode("utf-8")).hexdigest(),
        "packet_b_sha256": hashlib.sha256(packet_b.encode("utf-8")).hexdigest(),
    }


def sample_by_database(cases: list[dict[str, Any]], db_labels: dict[str, str]) -> dict[str, int]:
    counts = collections.Counter(case["db_id_private"] for case in cases)
    return {db_labels[db_id]: counts[db_id] for db_id in sorted(counts, key=lambda d: db_labels[d])}


def public_summary(
    args: argparse.Namespace,
    frozen: dict[str, Any],
    census: dict[str, Any],
    db_labels: dict[str, str],
    smoke_cases: list[dict[str, Any]],
    full_cases: list[dict[str, Any]],
    render_checks: dict[str, Any],
    started_at: str,
    resources: dict[str, float],
) -> dict[str, Any]:
    full_mapping_counts = [len(case["mappings"]) for case in full_cases]
    smoke_keys = {case["question_key_sha256"] for case in smoke_cases}
    full_keys = {case["question_key_sha256"] for case in full_cases}
    if smoke_keys & full_keys:
        raise StopRun("SMOKE_FULL_QUESTION_OVERLAP")
    return {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "SMOKE_PASS" if args.mode == "smoke" else "REVIEW_PACKET_READY_PENDING_HUMANS",
        "started_at_utc": started_at,
        "source_commit": args.expected_commit,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "python_version": platform.python_version(),
        "sqlglot_version": sqlglot.__version__,
        "seed": SEED,
        "input_sha256": frozen["input_hashes"],
        "frozen_candidate_census": census,
        "smoke_question_count": len(smoke_cases),
        "prepared_full_question_pair_count": len(full_cases),
        "prepared_full_database_count": len({case["db_id_private"] for case in full_cases}),
        "full_pair_count_by_anonymous_database": sample_by_database(full_cases, db_labels),
        "smoke_full_question_overlap": 0,
        "full_mapping_count_histogram": {
            str(count): full_mapping_counts.count(count)
            for count in sorted(set(full_mapping_counts))
        },
        "render_checks": render_checks,
        "human_review_completed": False,
        "trusted_role_label_count": 0,
        "reviewer_response_files_read": False,
        "model_calls": 0,
        "api_calls": 0,
        "gpu_seconds": 0,
        "sql_execution_calls": 0,
        "resources": {
            **resources,
            "limits": {
                "wall_seconds": MAX_WALL_SECONDS,
                "cpu_seconds": MAX_CPU_SECONDS,
                "peak_rss_gib": MAX_RSS_GIB,
            },
        },
        "privacy": {
            "gold_sql_in_review_packets": False,
            "database_ids_in_review_packets": False,
            "question_ids_in_review_packets": False,
            "method_labels_in_review_packets": False,
            "question_table_pair_keys_in_public_summary": False,
            "mapping_identities_in_public_summary": False,
        },
    }


def prepare_output_dir(path: Path) -> None:
    if path.exists():
        raise StopRun("OUTPUT_DIRECTORY_EXISTS")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.mkdir(mode=0o700, exist_ok=False)
    path.chmod(0o700)


def write_outputs(
    args: argparse.Namespace,
    cases: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path,
) -> None:
    prepare_output_dir(output_dir)
    log_path = output_dir / "run.log"
    log_records = [
        f"experiment_id={EXPERIMENT_ID}",
        f"run_id={args.run_id}",
        f"mode={args.mode}",
        f"source_commit={args.expected_commit}",
        f"status={summary['status']}",
        f"selected_question_pair_count={len(cases)}",
        "reviewer_response_files_read=false",
        "model_calls=0 api_calls=0 gpu_seconds=0 sql_execution_calls=0",
    ]
    if args.mode == "smoke":
        private_json(output_dir / "smoke_summary.json", summary)
        log_path.write_text("\n".join(log_records) + "\n", encoding="utf-8")
        file_mode_600(log_path)
        return

    packet_a, rows_a, _, _ = render_packet(cases, "A")
    packet_b, rows_b, _, _ = render_packet(cases, "B")
    packet_hashes: dict[str, str] = {}
    for name, content in (
        ("reviewer_A_packet.md", packet_a),
        ("reviewer_B_packet.md", packet_b),
    ):
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        file_mode_600(path)
        packet_hashes[name] = sha256_file(path)
    for reviewer, rows in (("A", rows_a), ("B", rows_b)):
        path = output_dir / f"reviewer_{reviewer}_responses.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RESPONSE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        file_mode_600(path)
        packet_hashes[path.name] = sha256_file(path)

    private_manifest = {
        **summary,
        "selected_cases_private": [
            {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "question_key_sha256": case["question_key_sha256"],
                "private_db_id": case["db_id_private"],
                "private_question_id": case["question_id_private"],
                "private_question_text": case["question"],
                "private_table_pair": case["pair_key_private"],
                "mapping_identities": [
                    {
                        "mapping_id": mapping["mapping_id"],
                        "identity": mapping["identity_private"],
                        "ordered_column_pairs": mapping["ordered_column_pairs"],
                        "duplicate_multiplicity": mapping["duplicate_multiplicity_private"],
                    }
                    for mapping in case["mappings"]
                ],
            }
            for case in cases
        ],
        "private_database_sample_counts": {
            case["db_id_private"]: sum(other["db_id_private"] == case["db_id_private"] for other in cases)
            for case in cases
        },
        "packet_files_sha256": packet_hashes,
    }
    private_json(output_dir / "private_manifest.json", private_manifest)
    private_json(output_dir / "private_aggregate.json", summary)
    log_path.write_text("\n".join(log_records) + "\n", encoding="utf-8")
    file_mode_600(log_path)
    checksum_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    checksum_text = "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_files)
    checksum_path = output_dir / "sha256sums.txt"
    checksum_path.write_text(checksum_text, encoding="utf-8")
    file_mode_600(checksum_path)


def validate_smoke_receipt(path: Path, expected_commit: str, input_hashes: dict[str, str]) -> None:
    if not path.is_file():
        raise StopRun("SMOKE_RECEIPT_MISSING")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise StopRun("SMOKE_RECEIPT_INVALID") from None
    if (
        summary.get("experiment_id") != EXPERIMENT_ID
        or summary.get("run_id") != EXPECTED_RUN_ID
        or summary.get("mode") != "smoke"
        or summary.get("status") != "SMOKE_PASS"
        or summary.get("source_commit") != expected_commit
        or summary.get("input_sha256") != input_hashes
        or summary.get("smoke_question_count") != SMOKE_SIZE
    ):
        raise StopRun("SMOKE_RECEIPT_MISMATCH")


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--fk-artifact", type=Path, required=True)
    parser.add_argument("--crosswalk-private", type=Path, required=True)
    parser.add_argument("--canonical-full", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-summary", type=Path)
    args = parser.parse_args()
    output_existed_at_start = args.output_dir.exists()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        if args.run_id != EXPECTED_RUN_ID:
            raise StopRun("RUN_ID_MISMATCH")
        if current_commit(args.repo_root) != args.expected_commit:
            raise StopRun("SOURCE_COMMIT_MISMATCH")
        if platform.python_version() != "3.12.14" or sqlglot.__version__ != "28.0.0":
            raise StopRun("ENVIRONMENT_VERSION_MISMATCH")
        if args.mode == "full" and args.smoke_summary is None:
            raise StopRun("FULL_REQUIRES_SMOKE_RECEIPT")
        if output_existed_at_start:
            raise StopRun("OUTPUT_DIRECTORY_EXISTS")
        frozen = load_frozen(args)
        candidates, census_result = build_candidate_pool(frozen)
        census = census_result["census"]
        db_labels = census_result["db_labels"]
        db_order = census_result["database_ids"]
        smoke_rows = select_smoke(candidates, db_order)
        full_rows = select_full(candidates, smoke_rows, db_order)

        if args.mode == "smoke":
            if args.smoke_summary is not None:
                raise StopRun("SMOKE_MUST_NOT_USE_PRIOR_RECEIPT")
            selected_rows = smoke_rows
        else:
            validate_smoke_receipt(args.smoke_summary, args.expected_commit, frozen["input_hashes"])
            selected_rows = full_rows

        cases = renderable_cases(selected_rows)
        render_checks = validate_rendering(cases, require_randomized=args.mode == "full")
        resources = check_resources(wall_start, cpu_start)
        summary = public_summary(
            args,
            frozen,
            census,
            db_labels,
            renderable_cases(smoke_rows),
            renderable_cases(full_rows),
            render_checks,
            started_at,
            resources,
        )
        write_outputs(args, cases, summary, args.output_dir)
        print(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": args.run_id,
                    "mode": args.mode,
                    "status": summary["status"],
                    "join_on_questions": census["join_on_questions"],
                    "ambiguous_pairs": census["ambiguous_question_table_pairs"],
                    "prepared_full_question_pair_count": len(full_rows),
                    "full_database_count": len({row["db_id"] for row in full_rows}),
                    "output_dir": str(args.output_dir),
                    "source_commit": args.expected_commit,
                    "runner_sha256": summary["runner_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    except frozen_loader.StopRun as exc:
        reason = exc.reason_code
    except StopRun as exc:
        reason = exc.reason_code
    except Exception as exc:
        # Parser/JSON exceptions can contain source SQL or private identities.
        reason = f"UNEXPECTED_{type(exc).__name__}"
    failure = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": "STOP",
        "reason_code": reason,
        "source_commit": args.expected_commit,
        "reviewer_response_files_read": False,
        "model_calls": 0,
        "api_calls": 0,
        "gpu_seconds": 0,
    }
    if not output_existed_at_start:
        if not args.output_dir.exists():
            prepare_output_dir(args.output_dir)
        private_json(args.output_dir / "failure_receipt.json", failure)
        log_path = args.output_dir / "run.log"
        log_path.write_text(
            f"experiment_id={EXPERIMENT_ID}\nrun_id={args.run_id}\nmode={args.mode}\n"
            f"source_commit={args.expected_commit}\nstatus=STOP\nreason_code={reason}\n"
            "reviewer_response_files_read=false\nmodel_calls=0 api_calls=0 gpu_seconds=0\n",
            encoding="utf-8",
        )
        file_mode_600(log_path)
    print(json.dumps(failure, sort_keys=True), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
