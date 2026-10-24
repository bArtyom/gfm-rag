#!/usr/bin/env python3
"""Build private, blinded BIRD-dev FK-role review packets.

This script never writes Gold SQL, model predictions, or raw query IDs into a
packet. Public artifacts contain aggregate counts and hashes only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import platform
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

EXPERIMENT_ID = "p0_role_blind_review_packet_20261025_01"
SEED = 20261024
EXPECTED = {
    "question_count": 1534,
    "parse_ok": 1534,
    "join_on_queries": 1140,
    "fk_matched_queries": 956,
    "multi_fk_candidate_queries": 174,
}
EXPECTED_HASHES = {
    "dev.json": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "dev_tables.json": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
}
MAX_CPU_SECONDS = 600
MAX_RSS_GIB = 4.0
RESPONSE_FIELDS = [
    "case_id",
    "pair_id",
    "decision",
    "selected_mapping_ids",
    "confidence_1_low_2_medium_3_high",
    "rationale_code",
    "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_budget(wall_start: float, cpu_start: float) -> dict[str, float]:
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    peak_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > MAX_CPU_SECONDS:
        raise TimeoutError(f"Wall time exceeded {MAX_CPU_SECONDS}s")
    if cpu_seconds > MAX_CPU_SECONDS:
        raise TimeoutError(f"CPU time exceeded {MAX_CPU_SECONDS}s")
    if peak_rss_gib > MAX_RSS_GIB:
        raise MemoryError(f"Peak RSS exceeded {MAX_RSS_GIB} GiB")
    return {
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "peak_rss_gib": round(peak_rss_gib, 6),
    }


def load_inputs(dev_path: Path, tables_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    hashes = {
        "dev.json": sha256_file(dev_path),
        "dev_tables.json": sha256_file(tables_path),
    }
    for name, expected_hash in EXPECTED_HASHES.items():
        if hashes[name] != expected_hash:
            raise ValueError(f"Frozen input hash mismatch for {name}")
    with dev_path.open("r", encoding="utf-8") as handle:
        questions = json.load(handle)
    with tables_path.open("r", encoding="utf-8") as handle:
        tables = json.load(handle)
    if not isinstance(questions, list) or not isinstance(tables, list):
        raise TypeError("BIRD dev inputs must be JSON arrays")
    schemas = {str(item["db_id"]): item for item in tables}
    if len(schemas) != len(tables):
        raise ValueError("Duplicate db_id entries in dev_tables.json")
    return questions, schemas, hashes


def schema_mappings(db_id: str, schema: dict[str, Any]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], set[tuple[str, str, str, str]]]:
    table_names = schema.get("table_names_original", [])
    column_names = schema.get("column_names_original", [])
    column_records: dict[int, tuple[str, str]] = {}
    for column_index, pair in enumerate(column_names):
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        table_index, column_name = pair
        if isinstance(table_index, int) and 0 <= table_index < len(table_names):
            column_records[column_index] = (
                str(table_names[table_index]),
                str(column_name),
            )

    grouped: dict[tuple[str, str, str, str], int] = Counter()
    for pair in schema.get("foreign_keys", []):
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        source = column_records.get(pair[0])
        target = column_records.get(pair[1])
        if source is None or target is None:
            continue
        grouped[(source[0], source[1], target[0], target[1])] += 1

    by_table_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    fk_keys: set[tuple[str, str, str, str]] = set()
    for identity, multiplicity in grouped.items():
        source_table, source_column, target_table, target_column = identity
        mapping_id = "m_" + stable_hash([db_id, identity])[:12]
        mapping = {
            "mapping_id": mapping_id,
            "identity": identity,
            "source_table": source_table,
            "source_columns": [source_column],
            "target_table": target_table,
            "target_columns": [target_column],
            "multiplicity": multiplicity,
        }
        pair_key = tuple(sorted((source_table.casefold(), target_table.casefold())))
        by_table_pair[pair_key].append(mapping)
        fk_keys.add(
            (
                source_table.casefold(),
                source_column.casefold(),
                target_table.casefold(),
                target_column.casefold(),
            )
        )
    for mappings in by_table_pair.values():
        mappings.sort(key=lambda item: item["mapping_id"])
    return by_table_pair, fk_keys


def unwrap_column(node: Any) -> exp.Column | None:
    while node is not None:
        if isinstance(node, exp.Column):
            return node
        if isinstance(node, (exp.Paren, exp.Cast, exp.TryCast)):
            node = node.this
            continue
        return None
    return None


def column_pair(
    equality: exp.Expression,
    aliases: dict[str, str],
) -> tuple[tuple[str, str], tuple[str, str]] | None:
    left = unwrap_column(equality.args.get("this"))
    right = unwrap_column(equality.args.get("expression"))
    if left is None or right is None or not left.table or not right.table:
        return None
    left_table = aliases.get(left.table.casefold())
    right_table = aliases.get(right.table.casefold())
    if not left_table or not right_table or left_table.casefold() == right_table.casefold():
        return None
    return (
        (left_table, left.name),
        (right_table, right.name),
    )


def equality_matches_fk(
    pair: tuple[tuple[str, str], tuple[str, str]],
    fk_keys: set[tuple[str, str, str, str]],
) -> bool:
    (left_table, left_column), (right_table, right_column) = pair
    forward = (
        left_table.casefold(),
        left_column.casefold(),
        right_table.casefold(),
        right_column.casefold(),
    )
    reverse = (
        right_table.casefold(),
        right_column.casefold(),
        left_table.casefold(),
        left_column.casefold(),
    )
    return forward in fk_keys or reverse in fk_keys


def analyze_question(
    record: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[bool, bool, dict[tuple[str, str], list[dict[str, Any]]]]:
    db_id = str(record["db_id"])
    fk_by_pair, fk_keys = schema_mappings(db_id, schema)
    sql = record.get("SQL")
    if not isinstance(sql, str):
        raise ValueError("Question record is missing SQL text")
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception as exc:
        # Do not expose SQL text in errors or logs.
        raise ValueError(f"SQL parse failed: {type(exc).__name__}") from None
    aliases: dict[str, str] = {}
    valid_tables = {
        str(name).casefold(): str(name)
        for name in schema.get("table_names_original", [])
    }
    for table in tree.find_all(exp.Table):
        physical_name = table.name
        canonical = valid_tables.get(physical_name.casefold())
        if canonical:
            aliases[table.alias_or_name.casefold()] = canonical
            aliases[physical_name.casefold()] = canonical

    joins = list(tree.find_all(exp.Join))
    has_join_on = False
    fk_matched = False
    candidate_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for join in joins:
        on_clause = join.args.get("on")
        if on_clause is None:
            continue
        has_join_on = True
        for equality in on_clause.find_all(exp.EQ):
            pair = column_pair(equality, aliases)
            if pair is None:
                continue
            if equality_matches_fk(pair, fk_keys):
                fk_matched = True
            (left_table, _), (right_table, _) = pair
            pair_key = tuple(sorted((left_table.casefold(), right_table.casefold())))
            alternatives = fk_by_pair.get(pair_key, [])
            if len(alternatives) >= 2:
                candidate_groups[pair_key] = alternatives
    return has_join_on, fk_matched, candidate_groups


def make_case(record: dict[str, Any], groups: dict[tuple[str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    db_id = str(record["db_id"])
    question_id = str(record["question_id"])
    case_id = "case_" + stable_hash([SEED, db_id, question_id])[:12]
    question_text = record.get("question")
    if not isinstance(question_text, str) or not question_text.strip():
        raise ValueError("Candidate question is empty")
    rendered_groups = []
    for pair_key, mappings in sorted(groups.items()):
        pair_payload = [case_id, pair_key]
        pair_id = "pair_" + stable_hash(pair_payload)[:12]
        rendered_groups.append(
            {
                "pair_id": pair_id,
                "left_table": mappings[0]["source_table"]
                if mappings[0]["source_table"].casefold() == pair_key[0]
                else mappings[0]["target_table"],
                "right_table": mappings[0]["target_table"]
                if mappings[0]["target_table"].casefold() == pair_key[1]
                else mappings[0]["source_table"],
                "mappings": mappings,
            }
        )
    return {
        "case_id": case_id,
        "db_id": db_id,
        "question_id": question_id,
        "question": question_text,
        "groups": rendered_groups,
    }


def analyze_dataset(
    questions: list[dict[str, Any]],
    schemas: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    parse_ok = 0
    join_on_query_ids: set[tuple[str, str]] = set()
    fk_matched_query_ids: set[tuple[str, str]] = set()
    multi_fk_cases: dict[str, dict[str, Any]] = {}
    seen_qids: set[tuple[str, str]] = set()
    for record in questions:
        qid = str(record.get("question_id", ""))
        db_id = str(record.get("db_id", ""))
        if not qid or not db_id:
            raise ValueError("Missing question_id or db_id")
        key = (db_id, qid)
        if key in seen_qids:
            raise ValueError("Duplicate (db_id, question_id) in dev.json")
        seen_qids.add(key)
        schema = schemas.get(db_id)
        if schema is None:
            raise ValueError("Question references a database absent from dev_tables.json")
        parse_ok += 1
        has_join_on, fk_matched, groups = analyze_question(record, schema)
        if has_join_on:
            join_on_query_ids.add(key)
        if fk_matched:
            fk_matched_query_ids.add(key)
        if groups:
            case = make_case(record, groups)
            multi_fk_cases[case["case_id"]] = case
    counts = {
        "question_count": len(questions),
        "parse_ok": parse_ok,
        "join_on_queries": len(join_on_query_ids),
        "fk_matched_queries": len(fk_matched_query_ids),
        "multi_fk_candidate_queries": len(multi_fk_cases),
    }
    return counts, list(multi_fk_cases.values())


def pick_cases(cases: list[dict[str, Any]], max_cases: int = 20) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_db[case["db_id"]].append(case)
    for db_id, items in by_db.items():
        items.sort(
            key=lambda case: stable_hash([SEED, db_id, case["question_id"]])
        )
    selected: list[dict[str, Any]] = []
    db_ids = sorted(by_db)
    round_index = 0
    while len(selected) < max_cases:
        added = False
        for db_id in db_ids:
            if round_index < len(by_db[db_id]):
                selected.append(by_db[db_id][round_index])
                added = True
                if len(selected) == max_cases:
                    break
        if not added:
            break
        round_index += 1
    if len(selected) != max_cases:
        raise ValueError(f"Only {len(selected)} eligible candidates; expected {max_cases}")
    db_counts = Counter(case["db_id"] for case in selected)
    return selected, dict(sorted(db_counts.items()))


def md_escape(value: Any) -> str:
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def render_packet(cases: list[dict[str, Any]], reviewer: str) -> tuple[str, list[dict[str, str]]]:
    reviewer_seed = stable_hash([SEED, reviewer])
    ordered_cases = sorted(
        cases,
        key=lambda case: stable_hash([reviewer_seed, case["case_id"]]),
    )
    lines = [
        "# Independent FK-role review",
        "",
        "Review each table-pair group independently. Do not consult another reviewer.",
        "Gold SQL, model outputs, and rankings are intentionally omitted.",
        "Record answers in the matching response CSV using the case and pair IDs.",
        "",
        "Decision values: single_mapping, multiple_mappings, cannot_determine, no_declared_fk, other.",
        "Confidence values: 1=low, 2=medium, 3=high.",
        "Rationale values: question_explicit, context_supports, role_ambiguity, schema_conflict, other.",
        "",
    ]
    response_rows: list[dict[str, str]] = []
    for case in ordered_cases:
        lines.extend(
            [
                f"## Case {case['case_id']}",
                "",
                f"<div>{html.escape(case['question']).replace(chr(10), '<br>')}</div>",
                "",
            ]
        )
        groups = sorted(
            case["groups"],
            key=lambda group: stable_hash([reviewer_seed, group["pair_id"]]),
        )
        for group in groups:
            lines.extend(
                [
                    f"### Pair {group['pair_id']}: {md_escape(group['left_table'])} ↔ {md_escape(group['right_table'])}",
                    "",
                    "| Mapping ID | Declared FK mapping |",
                    "|---|---|",
                ]
            )
            mappings = sorted(
                group["mappings"],
                key=lambda mapping: stable_hash([reviewer_seed, group["pair_id"], mapping["mapping_id"]]),
            )
            for mapping in mappings:
                rendered = (
                    f"{mapping['source_table']}.{', '.join(mapping['source_columns'])}"
                    f" → {mapping['target_table']}.{', '.join(mapping['target_columns'])}"
                )
                lines.append(
                    f"| {mapping['mapping_id']} | {md_escape(rendered)} |"
                )
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
    return "\n".join(lines) + "\n", response_rows


def write_review_bundle(
    output_dir: Path,
    cases: list[dict[str, Any]],
    db_counts: dict[str, int],
    data_hashes: dict[str, str],
    counts: dict[str, int],
    code_hash: str,
    wall_start: float,
    cpu_start: float,
    run_id: str,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    packet_hashes: dict[str, str] = {}
    pair_count = 0
    for reviewer in ("A", "B"):
        packet_text, response_rows = render_packet(cases, reviewer)
        packet_path = output_dir / f"reviewer_{reviewer}_packet.md"
        packet_path.write_text(packet_text, encoding="utf-8")
        response_path = output_dir / f"reviewer_{reviewer}_responses.csv"
        with response_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RESPONSE_FIELDS)
            writer.writeheader()
            writer.writerows(response_rows)
        packet_hashes[packet_path.name] = sha256_file(packet_path)
        packet_hashes[response_path.name] = sha256_file(response_path)
        pair_count = len(response_rows)
    resource_summary = check_budget(wall_start, cpu_start)
    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "status": "REVIEW_PACKET_READY_PENDING_HUMANS",
        "dataset": "BIRD dev; development/diagnostic only",
        "data_hashes": data_hashes,
        "code_sha256": code_hash,
        "sqlglot_version": sqlglot.__version__,
        "counts": counts,
        "sample_case_count": len(cases),
        "sample_pair_count": pair_count,
        "sample_database_count": len(db_counts),
        "private_per_database_sample_counts": db_counts,
        "identity_policy": "unique ordered FK mapping; exact duplicates retained only as multiplicity metadata",
        "packet_sha256": packet_hashes,
        "privacy": {
            "gold_sql_in_packets": False,
            "model_outputs_in_packets": False,
            "raw_query_ids_in_packets": False,
            "question_text_uploaded": False,
            "human_review_completed": False,
            "trusted_role_label_count": 0,
        },
        "resources": resource_summary,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "gpu_count": 0,
        },
    }
    manifest_path = output_dir / "private_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    file_names = sorted(
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "sha256sums.txt"
    )
    sums = "".join(
        f"{sha256_file(output_dir / name)}  {name}\n" for name in file_names
    )
    (output_dir / "sha256sums.txt").write_text(sums, encoding="utf-8")
    return manifest


def validate_render_smoke() -> None:
    case = {
        "case_id": "case_smoke",
        "db_id": "hidden_db",
        "question_id": "hidden_qid",
        "question": "Which customer receives the order shipment?",
        "groups": [
            {
                "pair_id": "pair_smoke",
                "left_table": "orders",
                "right_table": "customers",
                "mappings": [
                    {
                        "mapping_id": "m_billing",
                        "source_table": "orders",
                        "source_columns": ["billing_customer_id"],
                        "target_table": "customers",
                        "target_columns": ["customer_id"],
                    },
                    {
                        "mapping_id": "m_shipping",
                        "source_table": "orders",
                        "source_columns": ["shipping_customer_id"],
                        "target_table": "customers",
                        "target_columns": ["customer_id"],
                    },
                ],
            }
        ],
    }
    packet_a, rows_a = render_packet([case], "A")
    packet_b, rows_b = render_packet([case], "B")
    if "Gold SQL" not in packet_a or "m_billing" not in packet_a:
        raise ValueError("Synthetic packet render is incomplete")
    if "hidden_qid" in packet_a or "hidden_db" in packet_a:
        raise ValueError("Private IDs leaked into rendered reviewer packet")
    if len(rows_a) != 1 or len(rows_b) != 1:
        raise ValueError("Response form does not include one row per FK group")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {args.output_dir}")

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    questions, schemas, data_hashes = load_inputs(args.dev_json, args.tables_json)
    if args.mode == "smoke":
        if len(questions) < 5:
            raise ValueError("Smoke requires at least five BIRD-dev records")
        for record in questions[:5]:
            schema = schemas.get(str(record["db_id"]))
            if schema is None:
                raise ValueError("Smoke record references unknown db_id")
            analyze_question(record, schema)
        validate_render_smoke()
        resources = check_budget(wall_start, cpu_start)
        summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "status": "SMOKE_PASS",
            "records_examined": 5,
            "question_text_written": False,
            "gold_sql_written": False,
            "model_calls": 0,
            "sql_execution": 0,
            "data_hashes": data_hashes,
            "sqlglot_version": sqlglot.__version__,
            "resources": resources,
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "smoke_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.run_id != f"{EXPERIMENT_ID}_packet_001":
        raise ValueError("Unexpected Full run ID")
    counts, candidates = analyze_dataset(questions, schemas)
    if counts != EXPECTED:
        raise ValueError(
            "Historical aggregate gate mismatch; no packet generated. "
            + json.dumps(counts, sort_keys=True)
        )
    if len(candidates) != 174:
        raise ValueError("Candidate universe changed; no packet generated")
    selected, db_counts = pick_cases(candidates, max_cases=20)
    code_hash = sha256_file(Path(__file__).resolve())
    manifest = write_review_bundle(
        args.output_dir,
        selected,
        db_counts,
        data_hashes,
        counts,
        code_hash,
        wall_start,
        cpu_start,
        args.run_id,
    )
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "status": manifest["status"],
        "counts": counts,
        "sample_case_count": manifest["sample_case_count"],
        "sample_pair_count": manifest["sample_pair_count"],
        "sample_database_count": manifest["sample_database_count"],
        "packet_sha256": manifest["packet_sha256"],
        "data_hashes": data_hashes,
        "code_sha256": code_hash,
        "sqlglot_version": sqlglot.__version__,
        "resources": manifest["resources"],
        "human_review_completed": False,
        "trusted_role_label_count": 0,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Error messages intentionally avoid embedding record text or SQL.
        print(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "status": "STOP",
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(2)
