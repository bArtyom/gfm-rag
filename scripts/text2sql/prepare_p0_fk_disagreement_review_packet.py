#!/usr/bin/env python3
"""Prepare private, blinded packets for FK-mapping review.

The script reads frozen BIRD questions and reference SQL only in memory. It
never writes Gold SQL, source IDs, or method strata into reviewer packets.
Packets are local and private; this runner creates no human labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import platform
import re
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


EXPERIMENT_ID = "p0_fk_disagreement_blind_review_20261105_01"
SEED = 20261105
EXPECTED_HASHES = {
    "dev.json": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "dev_tables.json": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
    "fk_artifact": "5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060",
    "crosswalk_private": "7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e",
    "canonical_full": "746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed",
}
EXPECTED_POPULATIONS = {
    "packet_only_canonical_ambiguous": 22,
    "packet_only_canonical_unmatched": 66,
    "canonical_only_fk_match": 15,
    "canonical_only_multi_fk": 21,
    "both_positive_controls": 173,
}
QUOTAS = {
    "packet_only_canonical_ambiguous": 6,
    "packet_only_canonical_unmatched": 6,
    "canonical_only_fk_match": 15,
    "canonical_only_multi_fk": 21,
    "both_positive_controls": 6,
}
RESPONSE_FIELDS = [
    "case_id",
    "pair_id",
    "decision",
    "selected_mapping_ids",
    "confidence_1_low_2_medium_3_high",
    "rationale_code",
    "notes",
]
MAX_SECONDS = 600
MAX_RSS_GIB = 4.0


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


def question_key(record: dict[str, Any]) -> str:
    return stable_hash([str(record.get("db_id", "")), str(record.get("question_id", ""))])


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def budget_snapshot(wall_start: float, cpu_start: float) -> dict[str, float]:
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    peak_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > MAX_SECONDS or cpu_seconds > MAX_SECONDS:
        raise StopRun("RESOURCE_TIME_LIMIT")
    if peak_rss_gib > MAX_RSS_GIB:
        raise StopRun("RESOURCE_RSS_LIMIT")
    return {
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "peak_rss_gib": round(peak_rss_gib, 6),
    }


def file_mode_600(path: Path) -> None:
    path.chmod(0o600)


def load_fks(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    payload = read_json(path)
    by_pair_raw: dict[tuple[str, str, str], dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
    raw_count = valid_count = invalid_count = 0
    database_ids: set[str] = set()
    instances_by_db = payload.get("instances_private")
    if not isinstance(instances_by_db, dict):
        raise StopRun("FK_ARTIFACT_SCHEMA_INVALID")

    for db_id, records in instances_by_db.items():
        database_ids.add(str(db_id))
        if not isinstance(records, list):
            raise StopRun("FK_ARTIFACT_SCHEMA_INVALID")
        for record in records:
            raw_count += 1
            if not isinstance(record, dict):
                raise StopRun("FK_ARTIFACT_SCHEMA_INVALID")
            if record.get("valid_endpoints") is not True:
                invalid_count += 1
                continue
            valid_count += 1
            child = record.get("child_table")
            parent = record.get("parent_table")
            column_pairs = record.get("ordered_column_pairs")
            if not isinstance(child, str) or not isinstance(parent, str):
                raise StopRun("FK_ARTIFACT_ENDPOINT_INVALID")
            if not isinstance(column_pairs, list) or not column_pairs:
                raise StopRun("FK_ARTIFACT_COLUMNS_INVALID")
            if any(
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(value, str) and value for value in pair)
                for pair in column_pairs
            ):
                raise StopRun("FK_ARTIFACT_COLUMNS_INVALID")

            ordered = tuple((pair[0], pair[1]) for pair in column_pairs)
            identity = (
                str(db_id).casefold(),
                child.casefold(),
                tuple((left.casefold(), right.casefold()) for left, right in ordered),
                parent.casefold(),
            )
            pair_key = tuple(sorted((child.casefold(), parent.casefold())))
            db_pair_key = (str(db_id), pair_key[0], pair_key[1])
            entry = by_pair_raw[db_pair_key].get(identity)
            if entry is None:
                by_pair_raw[db_pair_key][identity] = {
                    "identity": identity,
                    "child_table": child,
                    "parent_table": parent,
                    "ordered_column_pairs": ordered,
                    "multiplicity": 1,
                }
            else:
                entry["multiplicity"] += 1

    unique_count = sum(len(items) for items in by_pair_raw.values())
    counts = {
        "database_count": len(database_ids),
        "raw_instances": raw_count,
        "valid_instances": valid_count,
        "invalid_instances": invalid_count,
        "unique_valid_mappings": unique_count,
        "duplicate_declarations_collapsed": valid_count - unique_count,
    }
    expected = {
        "database_count": 11,
        "raw_instances": 103,
        "valid_instances": 100,
        "invalid_instances": 3,
        "unique_valid_mappings": 99,
        "duplicate_declarations_collapsed": 1,
    }
    if counts != expected:
        raise StopRun("FK_ARTIFACT_COUNT_MISMATCH")

    flattened: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (db_id, left, right), mappings in by_pair_raw.items():
        for item in mappings.values():
            item_copy = dict(item)
            item_copy["db_id"] = db_id
            item_copy["pair_key"] = (left, right)
            flattened[db_id].append(item_copy)
    return flattened, counts


def indexed_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows = list(value.values())
    elif isinstance(value, list):
        rows = value
    else:
        raise StopRun("PRIVATE_INPUT_ROWS_INVALID")
    if not all(isinstance(row, dict) for row in rows):
        raise StopRun("PRIVATE_INPUT_ROWS_INVALID")
    return rows


def load_frozen_inputs(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "dev.json": args.dev_json,
        "dev_tables.json": args.tables_json,
        "fk_artifact": args.fk_artifact,
        "crosswalk_private": args.crosswalk_private,
        "canonical_full": args.canonical_full,
    }
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    if hashes != EXPECTED_HASHES:
        raise StopRun("INPUT_HASH_MISMATCH")

    questions = read_json(args.dev_json)
    schemas_raw = read_json(args.tables_json)
    fk_by_db, fk_counts = load_fks(args.fk_artifact)
    crosswalk_payload = read_json(args.crosswalk_private)
    canonical_payload = read_json(args.canonical_full)
    if not isinstance(questions, list) or not isinstance(schemas_raw, list):
        raise StopRun("BIRD_INPUT_SCHEMA_INVALID")
    schemas = {str(row.get("db_id")): row for row in schemas_raw if isinstance(row, dict)}
    if len(questions) != 1534 or len(schemas) != 11 or len(schemas_raw) != 11:
        raise StopRun("BIRD_INPUT_COUNT_MISMATCH")

    pairwise = (
        crosswalk_payload.get("private_pairwise_question_crosswalks", {}).get(
            "packet28_vs_p1_5_canonical"
        )
    )
    crosswalk_rows = indexed_rows(pairwise)
    canonical_rows = indexed_rows(canonical_payload.get("private_question_rows"))
    if len(crosswalk_rows) != 1534 or len(canonical_rows) != 1534:
        raise StopRun("PRIVATE_REFERENCE_COUNT_MISMATCH")

    crosswalk_by_key: dict[str, dict[str, Any]] = {}
    canonical_by_key: dict[str, dict[str, Any]] = {}
    for row in crosswalk_rows:
        key = row.get("question_key_sha256")
        if not isinstance(key, str) or key in crosswalk_by_key:
            raise StopRun("CROSSWALK_KEY_INVALID")
        crosswalk_by_key[key] = row
    for row in canonical_rows:
        key = row.get("question_key_sha256")
        if not isinstance(key, str) or key in canonical_by_key:
            raise StopRun("CANONICAL_KEY_INVALID")
        canonical_by_key[key] = row

    question_by_key: dict[str, dict[str, Any]] = {}
    for record in questions:
        if not isinstance(record, dict):
            raise StopRun("BIRD_RECORD_INVALID")
        key = question_key(record)
        if key in question_by_key or str(record.get("db_id")) not in schemas:
            raise StopRun("BIRD_QUESTION_KEY_INVALID")
        question_by_key[key] = record
    keys = set(crosswalk_by_key)
    if keys != set(canonical_by_key) or keys != set(question_by_key):
        raise StopRun("QUESTION_KEY_UNIVERSE_MISMATCH")
    if any(
        row.get("left_parse_ok") is not True
        or row.get("right_parse_ok") is not True
        or canonical_by_key[key].get("parse_ok") is not True
        for key, row in crosswalk_by_key.items()
    ):
        raise StopRun("FROZEN_PARSE_STATUS_MISMATCH")

    fk_patterns = Counter(
        (row.get("left_fk_match"), row.get("right_fk_match"))
        for row in crosswalk_by_key.values()
    )
    expected_fk_patterns = {
        (True, True): 955,
        (True, False): 88,
        (False, True): 15,
        (False, False): 476,
    }
    if dict(fk_patterns) != expected_fk_patterns:
        raise StopRun("FK_CROSSWALK_PATTERN_MISMATCH")
    multi_patterns = Counter(
        (row.get("left_multi_fk_candidate"), row.get("right_multi_fk_candidate"))
        for row in crosswalk_by_key.values()
    )
    expected_multi_patterns = {
        (True, True): 176,
        (False, True): 21,
        (False, False): 1337,
    }
    if dict(multi_patterns) != expected_multi_patterns:
        raise StopRun("MULTIFK_CROSSWALK_PATTERN_MISMATCH")
    if sum(row.get("has_join_on") is True for row in canonical_by_key.values()) != 1140:
        raise StopRun("JOIN_ON_DENOMINATOR_MISMATCH")
    if (
        sum(row.get("left_has_join_on") is True for row in crosswalk_by_key.values()) != 1140
        or sum(row.get("right_has_join_on") is True for row in crosswalk_by_key.values()) != 1140
    ):
        raise StopRun("CROSSWALK_JOIN_ON_DENOMINATOR_MISMATCH")

    return {
        "questions": question_by_key,
        "schemas": schemas,
        "fk_by_db": fk_by_db,
        "fk_counts": fk_counts,
        "crosswalk": crosswalk_by_key,
        "canonical": canonical_by_key,
        "input_hashes": hashes,
    }


def choose_sample(frozen: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    crosswalk = frozen["crosswalk"]
    canonical = frozen["canonical"]
    predicates = {
        "packet_only_canonical_ambiguous": lambda key: (
            crosswalk[key]["left_fk_match"] is True
            and crosswalk[key]["right_fk_match"] is False
            and int(canonical[key].get("ambiguous_join_count", 0)) > 0
        ),
        "packet_only_canonical_unmatched": lambda key: (
            crosswalk[key]["left_fk_match"] is True
            and crosswalk[key]["right_fk_match"] is False
            and int(canonical[key].get("unmatched_join_count", 0)) > 0
        ),
        "canonical_only_fk_match": lambda key: (
            crosswalk[key]["left_fk_match"] is False
            and crosswalk[key]["right_fk_match"] is True
        ),
        "canonical_only_multi_fk": lambda key: (
            crosswalk[key]["left_multi_fk_candidate"] is False
            and crosswalk[key]["right_multi_fk_candidate"] is True
            and int(canonical[key].get("role_candidate_join_count", 0)) > 0
        ),
        "both_positive_controls": lambda key: all(
            crosswalk[key][name] is True
            for name in (
                "left_fk_match",
                "right_fk_match",
                "left_multi_fk_candidate",
                "right_multi_fk_candidate",
            )
        ),
    }
    selected_tags: dict[str, set[str]] = defaultdict(set)
    population_counts: dict[str, int] = {}
    assignment_counts: dict[str, int] = {}
    for stratum, predicate in predicates.items():
        candidates = [key for key in crosswalk if predicate(key)]
        population_counts[stratum] = len(candidates)
        if len(candidates) != EXPECTED_POPULATIONS[stratum]:
            raise StopRun("SAMPLE_STRATUM_POPULATION_MISMATCH")
        quota = QUOTAS[stratum]
        if len(candidates) < quota:
            raise StopRun("SAMPLE_STRATUM_QUOTA_UNAVAILABLE")
        chosen = sorted(
            candidates,
            key=lambda key: stable_hash([SEED, stratum, key]),
        )[:quota]
        assignment_counts[stratum] = len(chosen)
        for key in chosen:
            selected_tags[key].add(stratum)

    if assignment_counts != QUOTAS:
        raise StopRun("SAMPLE_QUOTA_MISMATCH")
    if len(selected_tags) < 30:
        raise StopRun("SAMPLE_UNIQUE_CASES_BELOW_MINIMUM")

    ordered_keys = sorted(selected_tags, key=lambda key: stable_hash([SEED, "unique", key]))
    cases = []
    for index, key in enumerate(ordered_keys, start=1):
        record = frozen["questions"][key]
        case = {
            "case_id": f"C{index:03d}",
            "question_key_sha256": key,
            "db_id": str(record["db_id"]),
            "question_id": str(record["question_id"]),
            "question": record.get("question"),
            "sql": record.get("SQL"),
            "strata": sorted(selected_tags[key]),
        }
        if not isinstance(case["question"], str) or not case["question"].strip():
            raise StopRun("SAMPLE_QUESTION_TEXT_INVALID")
        if not isinstance(case["sql"], str) or not case["sql"].strip():
            raise StopRun("SAMPLE_GOLD_SQL_INVALID")
        cases.append(case)
    return cases, population_counts, assignment_counts


def unwrap_column(node: Any) -> exp.Column | None:
    while node is not None:
        if isinstance(node, exp.Column):
            return node
        if isinstance(node, (exp.Paren, exp.Cast, exp.TryCast)):
            node = node.this
        else:
            return None
    return None


def parse_target_pairs(case: dict[str, Any], schema: dict[str, Any], mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        tree = sqlglot.parse_one(case["sql"], read="sqlite")
    except Exception:
        raise StopRun("SAMPLED_SQL_PARSE_FAILURE") from None

    table_names = schema.get("table_names_original", [])
    canonical_tables = {str(name).casefold(): str(name) for name in table_names}
    alias_targets: dict[str, set[str]] = defaultdict(set)
    for table in tree.find_all(exp.Table):
        physical_name = table.name
        canonical = canonical_tables.get(str(physical_name).casefold())
        if canonical:
            alias_targets[table.alias_or_name.casefold()].add(canonical)
            alias_targets[physical_name.casefold()].add(canonical)

    pair_names: dict[tuple[str, str], tuple[str, str]] = {}
    joins_with_on = [join for join in tree.find_all(exp.Join) if join.args.get("on") is not None]
    if not joins_with_on:
        raise StopRun("SAMPLED_QUERY_HAS_NO_JOIN_ON")
    for join in joins_with_on:
        join_pairs: set[tuple[str, str]] = set()
        for equality in join.args["on"].find_all(exp.EQ):
            left = unwrap_column(equality.args.get("this"))
            right = unwrap_column(equality.args.get("expression"))
            if left is None or right is None or not left.table or not right.table:
                continue
            if left.table.casefold() == right.table.casefold():
                continue
            left_targets = alias_targets.get(left.table.casefold(), set())
            right_targets = alias_targets.get(right.table.casefold(), set())
            if len(left_targets) != 1 or len(right_targets) != 1:
                continue
            left_table = next(iter(left_targets))
            right_table = next(iter(right_targets))
            pair_key = tuple(sorted((left_table.casefold(), right_table.casefold())))
            pair_names[pair_key] = (
                canonical_tables[pair_key[0]],
                canonical_tables[pair_key[1]],
            )
            join_pairs.add(pair_key)
        if not join_pairs:
            raise StopRun("JOIN_PAIR_EXTRACTION_INCOMPLETE")

    fk_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        fk_by_pair[mapping["pair_key"]].append(mapping)

    groups: list[dict[str, Any]] = []
    for pair_index, pair_key in enumerate(sorted(pair_names), start=1):
        left_table, right_table = pair_names[pair_key]
        pair_id = f"{case['case_id']}-P{pair_index:02d}"
        candidates = sorted(
            fk_by_pair.get(pair_key, []),
            key=lambda item: stable_hash([case["case_id"], pair_key, item["identity"]]),
        )
        shown = []
        for mapping in candidates:
            mapping_id = "M" + stable_hash(
                [case["case_id"], pair_key, mapping["identity"]]
            )[:8].upper()
            shown.append({**mapping, "mapping_id": mapping_id})
        groups.append(
            {
                "pair_id": pair_id,
                "pair_key": pair_key,
                "left_table": left_table,
                "right_table": right_table,
                "mappings": shown,
            }
        )
    if not groups:
        raise StopRun("NO_RENDERABLE_TABLE_PAIR")
    return groups


def prepare_cases(cases: list[dict[str, Any]], frozen: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = []
    for case in cases:
        schema = frozen["schemas"].get(case["db_id"])
        if not isinstance(schema, dict):
            raise StopRun("SAMPLE_SCHEMA_MISSING")
        pair_groups = parse_target_pairs(case, schema, frozen["fk_by_db"].get(case["db_id"], []))
        prepared.append({**case, "groups": pair_groups})
    return prepared


def md_escape(value: Any) -> str:
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def render_packet(cases: list[dict[str, Any]], reviewer: str) -> tuple[str, list[dict[str, str]], list[str]]:
    reviewer_seed = stable_hash([SEED, "reviewer", reviewer])
    ordered_cases = sorted(
        cases,
        key=lambda case: stable_hash([reviewer_seed, case["case_id"]]),
    )
    case_order = [case["case_id"] for case in ordered_cases]
    lines = [
        "# Independent FK mapping review",
        "",
        "For each supplied table pair, judge which declared FK mapping, if any, the question supports.",
        "This task assumes the table pair is given; it does not assess table retrieval.",
        "Do not consult another reviewer. Gold SQL, ON expressions, model outputs, ranks, and source labels are omitted.",
        "Use the matching response CSV. Keep the provided case, pair, and mapping IDs unchanged.",
        "",
        "Decision: single_mapping | multiple_mappings | cannot_determine | no_declared_fk | other.",
        "Confidence: 1=low, 2=medium, 3=high.",
        "Rationale: question_explicit | context_supports | role_ambiguity | schema_conflict | other.",
        "For multiple_mappings, list every acceptable mapping ID. If no declared mapping fits, use no_declared_fk.",
        "",
    ]
    response_rows: list[dict[str, str]] = []
    visible_gold_sql: list[str] = []
    for case in ordered_cases:
        lines.extend(
            [
                f"## Case {case['case_id']}",
                "",
                md_escape(case["question"]),
                "",
            ]
        )
        groups = sorted(
            case["groups"],
            key=lambda group: stable_hash([reviewer_seed, "pair", group["pair_id"]]),
        )
        for group in groups:
            lines.extend(
                [
                    f"### Pair {group['pair_id']}: {md_escape(group['left_table'])} ↔ {md_escape(group['right_table'])}",
                    "",
                    "| Mapping ID | Complete declared FK mapping |",
                    "|---|---|",
                ]
            )
            mappings = sorted(
                group["mappings"],
                key=lambda item: stable_hash([reviewer_seed, "mapping", group["pair_id"], item["mapping_id"]]),
            )
            if not mappings:
                lines.append("| none | No valid declared FK mapping for this table pair in the frozen schema |")
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
                    "Decision: __________   Selected mapping ID(s): __________",
                    "Confidence (1–3): ____   Rationale code: __________",
                    "Notes: __________________________________________________",
                    "",
                ]
            )
            response_rows.append(
                {
                    "case_id": case["case_id"],
                    "pair_id": group["pair_id"],
                    "decision": "",
                    "selected_mapping_ids": "",
                    "confidence_1_low_2_medium_3_high": "",
                    "rationale_code": "",
                    "notes": "",
                }
            )
        visible_gold_sql.append(case["sql"])

    packet = "\n".join(lines) + "\n"
    if any(sql and sql in packet for sql in visible_gold_sql):
        raise StopRun("GOLD_SQL_LEAK_CHECK_FAILED")
    forbidden = ("packet_only_canonical", "canonical_only_multi_fk", "both_positive_controls")
    if any(marker in packet for marker in forbidden):
        raise StopRun("METHOD_STRATUM_LEAK_CHECK_FAILED")
    return packet, response_rows, case_order


def mapping_order_signature(case: dict[str, Any], reviewer: str) -> dict[str, tuple[str, ...]]:
    reviewer_seed = stable_hash([SEED, "reviewer", reviewer])
    signature = {}
    for group in sorted(
        case["groups"],
        key=lambda item: stable_hash([reviewer_seed, "pair", item["pair_id"]]),
    ):
        ordered = sorted(
            group["mappings"],
            key=lambda item: stable_hash(
                [reviewer_seed, "mapping", group["pair_id"], item["mapping_id"]]
            ),
        )
        signature[group["pair_id"]] = tuple(item["mapping_id"] for item in ordered)
    return signature


def private_case_manifest(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for case in cases:
        result.append(
            {
                "case_id": case["case_id"],
                "question_key_sha256": case["question_key_sha256"],
                "private_db_id": case["db_id"],
                "private_question_id": case["question_id"],
                "selected_strata": case["strata"],
                "table_pairs": [
                    {
                        "pair_id": group["pair_id"],
                        "private_pair_key": list(group["pair_key"]),
                        "mapping_ids_and_private_identities": [
                            {
                                "mapping_id": mapping["mapping_id"],
                                "private_identity": [
                                    mapping["identity"][0],
                                    mapping["identity"][1],
                                    [list(pair) for pair in mapping["identity"][2]],
                                    mapping["identity"][3],
                                ],
                                "duplicate_multiplicity": mapping["multiplicity"],
                            }
                            for mapping in group["mappings"]
                        ],
                    }
                    for group in case["groups"]
                ],
            }
        )
    return result


def write_private_outputs(
    output_dir: Path,
    cases: list[dict[str, Any]],
    frozen: dict[str, Any],
    population_counts: dict[str, int],
    assignment_counts: dict[str, int],
    mode: str,
    run_id: str,
    wall_start: float,
    cpu_start: float,
) -> dict[str, Any]:
    if output_dir.exists():
        raise StopRun("OUTPUT_DIRECTORY_EXISTS")
    reviewer_a, rows_a, order_a = render_packet(cases, "A")
    reviewer_b, rows_b, order_b = render_packet(cases, "B")
    pair_ids_a = [(row["case_id"], row["pair_id"]) for row in rows_a]
    pair_ids_b = [(row["case_id"], row["pair_id"]) for row in rows_b]
    if set(pair_ids_a) != set(pair_ids_b) or len(pair_ids_a) != len(pair_ids_b):
        raise StopRun("REVIEWER_PAIR_SET_MISMATCH")
    expected_mapping_ids = {
        mapping["mapping_id"]
        for case in cases
        for group in case["groups"]
        for mapping in group["mappings"]
    }
    mapping_ids_a = set(re.findall(r"\|\s*(M[0-9A-F]{8})\s*\|", reviewer_a))
    mapping_ids_b = set(re.findall(r"\|\s*(M[0-9A-F]{8})\s*\|", reviewer_b))
    if mapping_ids_a != expected_mapping_ids or mapping_ids_b != expected_mapping_ids:
        raise StopRun("REVIEWER_MAPPING_SET_MISMATCH")
    if len(cases) > 1 and order_a == order_b:
        raise StopRun("REVIEWER_CASE_ORDER_NOT_SCRAMBLED")
    mapping_orders_differ = 0
    for case in cases:
        if mapping_order_signature(case, "A") != mapping_order_signature(case, "B"):
            mapping_orders_differ += 1
    if mode == "full" and mapping_orders_differ == 0:
        raise StopRun("REVIEWER_MAPPING_ORDER_NOT_SCRAMBLED")

    resources = budget_snapshot(wall_start, cpu_start)
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "mode": mode,
        "status": "SMOKE_PASS" if mode == "smoke" else "REVIEW_PACKET_READY_PENDING_HUMANS",
        "question_count": 1534,
        "crosswalk_key_count": 1534,
        "canonical_key_count": 1534,
        "population_counts": population_counts,
        "quota_assignments": assignment_counts,
        "unique_sampled_question_count": len(cases),
        "sampled_pair_count": len(rows_a),
        "sampled_database_count_private": len({case["db_id"] for case in cases}),
        "reviewer_case_order_differs": order_a != order_b,
        "case_count_with_different_candidate_display_order": mapping_orders_differ,
        "fk_artifact_counts": frozen["fk_counts"],
        "sqlglot_version": sqlglot.__version__,
        "input_hashes": frozen["input_hashes"],
        "code_sha256": sha256_file(Path(__file__).resolve()),
        "human_review_completed": False,
        "trusted_role_label_count": 0,
        "model_calls": 0,
        "api_calls": 0,
        "sql_execution": 0,
        "gpu_seconds": 0,
        "resources": resources,
    }
    if mode == "smoke":
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(output_dir.parent, 0o700)
        output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        summary_path = output_dir / "smoke_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        file_mode_600(summary_path)
        return summary

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir.parent, 0o700)
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    file_contents = {
        "reviewer_A_packet.md": reviewer_a,
        "reviewer_B_packet.md": reviewer_b,
    }
    packet_hashes: dict[str, str] = {}
    for name, content in file_contents.items():
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
        "selected_cases_private": private_case_manifest(cases),
        "private_database_sample_counts": dict(
            sorted(Counter(case["db_id"] for case in cases).items())
        ),
        "packet_files_sha256": packet_hashes,
        "privacy": {
            "gold_sql_in_packets": False,
            "source_method_labels_in_packets": False,
            "raw_question_or_database_ids_in_packets": False,
            "human_review_completed": False,
            "trusted_role_label_count": 0,
        },
    }
    manifest_path = output_dir / "private_manifest.json"
    manifest_path.write_text(json.dumps(private_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    file_mode_600(manifest_path)

    checksum_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    checksums = "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_files)
    sums_path = output_dir / "sha256sums.txt"
    sums_path.write_text(checksums, encoding="utf-8")
    file_mode_600(sums_path)

    summary_path = output_dir / "private_aggregate.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    file_mode_600(summary_path)
    return summary


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--fk-artifact", type=Path, required=True)
    parser.add_argument("--crosswalk-private", type=Path, required=True)
    parser.add_argument("--canonical-full", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    expected_run_id = (
        "p0_fk_disagreement_blind_review_smoke_20261105_01"
        if args.mode == "smoke"
        else "p0_fk_disagreement_blind_review_full_20261105_01"
    )
    if args.run_id != expected_run_id:
        raise StopRun("RUN_ID_MISMATCH")
    if args.output_dir.exists():
        raise StopRun("OUTPUT_DIRECTORY_EXISTS")

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    frozen = load_frozen_inputs(args)
    all_cases, populations, assignments = choose_sample(frozen)
    if args.mode == "smoke":
        sample = all_cases[:5]
    else:
        sample = all_cases
    prepared = prepare_cases(sample, frozen)
    return_summary = write_private_outputs(
        args.output_dir,
        prepared,
        frozen,
        populations,
        assignments,
        args.mode,
        args.run_id,
        wall_start,
        cpu_start,
    )
    print(json.dumps(return_summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StopRun as exc:
        print(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "status": "STOP",
                    "reason_code": exc.reason_code,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "status": "STOP",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        sys.exit(2)
