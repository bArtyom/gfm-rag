#!/usr/bin/env python3
"""Create private blinded packets from the frozen BIRD-train FK audit."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys

EXPERIMENT_ID = "p0_bird_train_fk_model_proxy_review_20261107_01"
CAPACITY_ID = "p0_bird_train_fk_mapping_capacity_20261107_01"
SEED = 20261107


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_join_hash(parts: list[str]) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def file_mode_600(path: Path) -> None:
    path.chmod(0o600)


def write_private_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    file_mode_600(path)


def md_escape(value: str) -> str:
    return html.escape(value, quote=False).replace("|", "&#124;").replace("\n", " ")


def mapping_expression(signature: list[list[str]]) -> str:
    components = []
    for index, edge in enumerate(signature, start=1):
        if not isinstance(edge, list) or len(edge) != 4 or any(not isinstance(x, str) for x in edge):
            raise ValueError("constraint_signature_component_invalid")
        child, child_column, parent, parent_column = edge
        components.append(
            f"{child}.{child_column} = {parent}.{parent_column}"
        )
    if not components:
        raise ValueError("empty_constraint_signature")
    suffix = " (complete composite constraint)" if len(components) > 1 else ""
    return " AND ".join(components) + suffix


def build_cases(evidence: list[dict], train_rows: list[dict], config: dict) -> tuple[list[dict], dict]:
    identity_audit = config["inputs"]["identity_audit"]
    expected = identity_audit["eligible_units_by_anonymous_database"]
    eligible: list[dict] = []
    candidate_hashes: set[str] = set()
    question_indices: set[int] = set()
    all_exact = 0
    for row in evidence:
        if row.get("metadata_pragma_exact") is True:
            all_exact += 1
        signatures = row.get("constraint_signatures_private")
        if (row.get("metadata_pragma_exact") is not True
                or not isinstance(signatures, list)
                or len(signatures) < 2
                or row.get("distinct_constraint_signature_count") != len(signatures)):
            continue
        if row.get("database_sha256_before") != row.get("database_sha256_after"):
            raise ValueError("sqlite_hash_change_in_frozen_audit_evidence")
        candidate_id = row.get("candidate_id_sha256")
        db_id = row.get("database_id_private")
        anon_db = row.get("anonymous_database")
        pair = row.get("table_pair_private")
        index = row.get("question_index_private")
        question_key_hash = row.get("question_key_hash_private")
        if (not isinstance(candidate_id, str) or len(candidate_id) != 64
                or not isinstance(db_id, str) or not isinstance(anon_db, str)
                or not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(x, str) and x for x in pair)
                or type(index) is not int or index < 0 or index >= len(train_rows)
                or not isinstance(question_key_hash, str)):
            raise ValueError("private_candidate_fields_invalid")
        normalized_pair = sorted(name.casefold() for name in pair)
        candidate_key_payload = [db_id, question_key_hash, normalized_pair]
        expected_candidate_id = hashlib.sha256(
            json.dumps(candidate_key_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if candidate_id != expected_candidate_id:
            raise ValueError("candidate_identity_hash_mismatch")
        if candidate_id in candidate_hashes or index in question_indices:
            raise ValueError("duplicate_candidate_or_question")
        candidate_hashes.add(candidate_id)
        question_indices.add(index)
        source_row = train_rows[index]
        if str(source_row.get("db_id")) != db_id:
            raise ValueError("question_database_join_mismatch")
        question_key = str(source_row.get("question_id", index))
        if stable_join_hash([CAPACITY_ID, db_id, question_key]) != question_key_hash:
            raise ValueError("question_key_hash_mismatch")
        question = source_row.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question_text_missing")
        pair_keys = {name.casefold() for name in pair}
        mapping_rows = []
        mapping_signatures: set[str] = set()
        for signature in signatures:
            if not isinstance(signature, list) or not signature:
                raise ValueError("constraint_signature_invalid")
            endpoints: set[str] = set()
            for edge in signature:
                if not isinstance(edge, list) or len(edge) != 4:
                    raise ValueError("constraint_signature_component_invalid")
                child, child_column, parent, parent_column = edge
                if not all(isinstance(x, str) and x for x in edge):
                    raise ValueError("constraint_signature_component_empty")
                endpoints.update((child.casefold(), parent.casefold()))
            if endpoints != pair_keys:
                raise ValueError("constraint_signature_table_pair_mismatch")
            signature_hash = stable_hash(signature)
            if signature_hash in mapping_signatures:
                raise ValueError("duplicate_complete_constraint_signature")
            mapping_signatures.add(signature_hash)
            mapping_id = "M" + stable_hash(
                [EXPERIMENT_ID, SEED, candidate_id, signature]
            )[:10].upper()
            mapping_rows.append({
                "mapping_id": mapping_id,
                "expression": mapping_expression(signature),
                "signature_private": signature,
            })
        if len({item["mapping_id"] for item in mapping_rows}) != len(mapping_rows):
            raise ValueError("mapping_id_collision")
        eligible.append({
            "candidate_id_sha256": candidate_id,
            "anonymous_database": anon_db,
            "private_db_id": db_id,
            "question_index_private": index,
            "question_key_hash_private": question_key_hash,
            "question": " ".join(question.split()),
            "table_pair_private": pair,
            "mappings": mapping_rows,
        })

    if len(evidence) != identity_audit["full_candidate_units"]:
        raise ValueError("identity_audit_candidate_count_mismatch")
    if all_exact != identity_audit["exact_alignment_units"]:
        raise ValueError("identity_audit_exact_alignment_count_mismatch")
    if len(eligible) != config["sampling"]["full_units"]:
        raise ValueError("eligible_candidate_count_mismatch")
    actual_histogram = dict(sorted(Counter(row["anonymous_database"] for row in eligible).items()))
    if actual_histogram != dict(sorted(expected.items())):
        raise ValueError("eligible_database_histogram_mismatch")
    return eligible, actual_histogram


def assign_case_ids(cases: list[dict]) -> None:
    ordered = sorted(
        cases,
        key=lambda row: stable_hash([EXPERIMENT_ID, SEED, "case_id", row["candidate_id_sha256"]]),
    )
    for index, row in enumerate(ordered, start=1):
        row["case_id"] = f"C{index:03d}"
        row["pair_id"] = f"{row['case_id']}-P01"


def render_packet(cases: list[dict], reviewer: str, smoke_ids: set[str]) -> str:
    smoke = [row for row in cases if row["pair_id"] in smoke_ids]
    rest = [row for row in cases if row["pair_id"] not in smoke_ids]
    smoke.sort(key=lambda row: (
        row["anonymous_database"],
        stable_hash([EXPERIMENT_ID, SEED, reviewer, "smoke", row["candidate_id_sha256"]]),
    ))
    rest.sort(key=lambda row: stable_hash(
        [EXPERIMENT_ID, SEED, reviewer, "full", row["candidate_id_sha256"]]
    ))
    ordered = smoke + rest
    rendered: list[str] = []
    for row in ordered:
        rendered.append(f"## Case {row['case_id']}")
        rendered.append(md_escape(row["question"]))
        left, right = row["table_pair_private"]
        pair_name = md_escape(f"{left} ↔ {right}")
        rendered.append(f"### Pair {row['pair_id']}: {pair_name}")
        rendered.append("| Mapping ID | Complete declared FK constraint |")
        rendered.append("| --- | --- |")
        mappings = sorted(
            row["mappings"],
            key=lambda item: stable_hash([
                EXPERIMENT_ID, SEED, reviewer, "mapping", row["candidate_id_sha256"],
                item["signature_private"],
            ]),
        )
        for mapping in mappings:
            rendered.append(
                f"| {mapping['mapping_id']} | {md_escape(mapping['expression'])} |"
            )
        rendered.append("")
    return "\n".join(rendered)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--train-tables", type=Path, required=True)
    parser.add_argument("--dev-tables", type=Path, required=True)
    parser.add_argument("--audit-evidence", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("experiment_config_mismatch")
    if args.run_id != config["generation"]["packet_preparation_run_id"]:
        raise ValueError("packet_preparation_run_id_mismatch")
    git_head = subprocess.run(
        ["git", "-C", str(args.repo_root.resolve()), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(args.repo_root.resolve()), "branch", "--show-current"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if git_head != args.expected_commit or branch != config["repository"]["branch"]:
        raise ValueError("source_commit_or_branch_mismatch")
    if sha256_file(config_path) != args.expected_config_sha256:
        raise ValueError("config_hash_mismatch")
    if sha256_file(Path(__file__).resolve()) != config["implementation"]["preparer_sha256"]:
        raise ValueError("preparer_hash_mismatch")
    paths = {
        "train_json": args.train_json,
        "train_tables": args.train_tables,
        "dev_tables": args.dev_tables,
        "audit_evidence": args.audit_evidence,
        "audit_summary": args.audit_summary,
    }
    actual_hashes = {name: sha256_file(path) for name, path in paths.items()}
    if actual_hashes != config["inputs"]["sha256"]:
        raise ValueError("frozen_input_hash_mismatch")

    args.output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output_dir.parent.chmod(0o700)
    args.output_dir.mkdir(parents=False, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    try:
        evidence = json.loads(args.audit_evidence.read_text(encoding="utf-8"))
        train_rows = json.loads(args.train_json.read_text(encoding="utf-8"))
        if not isinstance(evidence, list) or not isinstance(train_rows, list):
            raise ValueError("frozen_input_type_invalid")
        if len(train_rows) != config["inputs"]["train_question_count"]:
            raise ValueError("train_question_count_mismatch")
        cases, histogram = build_cases(evidence, train_rows, config)
        assign_case_ids(cases)

        ordered_db_labels = sorted(histogram)
        if len(ordered_db_labels) < config["sampling"]["smoke_units"]:
            raise ValueError("smoke_database_coverage_unavailable")
        smoke_candidates = []
        for anon_db in ordered_db_labels[:config["sampling"]["smoke_units"]]:
            pool = [row for row in cases if row["anonymous_database"] == anon_db]
            smoke_candidates.append(min(
                pool,
                key=lambda row: stable_hash([SEED, "smoke", row["candidate_id_sha256"]]),
            ))
        smoke_ids = {row["pair_id"] for row in smoke_candidates}
        if len(smoke_ids) != config["sampling"]["smoke_units"]:
            raise ValueError("smoke_sample_duplicate")

        private_rows = []
        for row in sorted(cases, key=lambda item: item["case_id"]):
            private_rows.append({
                "case_id": row["case_id"],
                "pair_id": row["pair_id"],
                "candidate_id_sha256": row["candidate_id_sha256"],
                "private_db_id": row["private_db_id"],
                "anonymous_database": row["anonymous_database"],
                "question_index_private": row["question_index_private"],
                "question_key_hash_private": row["question_key_hash_private"],
                "table_pair_private": row["table_pair_private"],
                "mapping_ids_private": [item["mapping_id"] for item in row["mappings"]],
                "constraint_signature_count": len(row["mappings"]),
            })
        manifest_path = args.output_dir / "candidate_manifest_private.json"
        write_private_json(manifest_path, {"selected_cases_private": private_rows})

        packet_hashes = {}
        for reviewer in ("A", "B"):
            packet_path = args.output_dir / f"reviewer_{reviewer}_packet.md"
            packet_path.write_text(render_packet(cases, reviewer, smoke_ids), encoding="utf-8")
            file_mode_600(packet_path)
            packet_hashes[reviewer] = sha256_file(packet_path)

        receipt = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "source_commit": git_head,
            "source_branch": branch,
            "input_sha256": actual_hashes,
            "eligible_units": len(cases),
            "candidate_mapping_count": sum(len(row["mappings"]) for row in cases),
            "eligible_units_by_anonymous_database": histogram,
            "smoke_units": len(smoke_ids),
            "smoke_anonymous_database_count": len({
                row["anonymous_database"] for row in smoke_candidates
            }),
            "reviewer_packet_sha256": packet_hashes,
            "private_manifest_sha256": sha256_file(manifest_path),
            "sql_copied_to_packet": False,
            "database_opened": False,
            "model_calls": 0,
        }
        write_private_json(args.output_dir / "preparation_receipt.json", receipt)
        print(json.dumps({
            "status": "PACKETS_READY",
            "eligible_units": receipt["eligible_units"],
            "candidate_mapping_count": receipt["candidate_mapping_count"],
            "anonymous_database_count": len(histogram),
            "smoke_units": receipt["smoke_units"],
            "sql_copied_to_packet": False,
            "model_calls": 0,
        }, ensure_ascii=False))
    except Exception as error:
        write_private_json(args.output_dir / "failure_receipt.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "source_commit": git_head,
            "error_type": type(error).__name__,
            "error": str(error),
            "input_sha256": actual_hashes,
            "model_calls": 0,
        })
        raise


if __name__ == "__main__":
    main()
