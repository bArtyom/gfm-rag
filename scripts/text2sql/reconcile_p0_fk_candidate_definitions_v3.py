#!/usr/bin/env python3
"""Reconcile frozen P0 packet and P1.5 FK-candidate definitions.

The output contains only hashed question keys and parser labels. It never
serializes question text, SQL, database names, schema contents, or IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import resource
import stat
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ID = "p0_fk_candidate_definition_recovery_v3_20261105_01"
PACKET_PATH = ROOT / "scripts/text2sql/prepare_p0_role_review_packet.py"
P1_5_PATH = ROOT / "scripts/text2sql/run_p1_5_diagnostics.py"
EXPECTED_DEV_SHA = "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06"
EXPECTED_TABLES_SHA = "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97"
EXPECTED_P1_5_FK_SHA = "5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060"
EXPECTED_PACKET_CODE_SHA = "5c84af91edc6dd39cd1fba39105dfc74b804be17912d91edab5eba2ff180eebc"
EXPECTED_P1_5_CODE_SHA = "af59d01d22a6b5d5538231b38c2bf52e0355a9193a5773f40b14d29470ec40cf"
EXPECTED_FULL_QUESTIONS = 1534
EXPECTED_FULL_JOIN_ON = 1140
EXPECTED_PACKET = {"fk_match_queries": 1043, "multi_fk_candidate_queries": 176}
EXPECTED_P1_5 = {"fk_match_queries": 970, "multi_fk_candidate_queries": 197}
MAX_WALL_SECONDS = 600
MAX_CPU_SECONDS = 600
MAX_RSS_GIB = 4.0
MAX_THREADS = 8
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
DIAGNOSTIC_CONTEXT: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "stage": "argument_parsing",
    "run_id": None,
    "method": None,
    "output_path": None,
    "question_key_sha256": None,
    "counters": {},
    "artifact_hash_diagnostic": None,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(metadata: os.stat_result) -> dict[str, int]:
    return {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
        "size_bytes": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
        "ctime_ns": int(metadata.st_ctime_ns),
    }


def load_frozen_artifact_from_same_bytes(path: Path) -> Any:
    """Hash and parse one bounded byte buffer, checking path identity around reads."""
    diagnostic: dict[str, Any] = {
        "expected_sha256": EXPECTED_P1_5_FK_SHA,
        "same_byte_buffer_for_hash_and_json": False,
        "file_identity_stable": False,
        "size_bytes": None,
        "computed_sha256": None,
        "chunked_path_helper_sha256": None,
        "private_identity_before": None,
        "private_identity_open_before": None,
        "private_identity_open_after": None,
        "private_identity_after": None,
        "private_identity_after_helper": None,
        "o_nofollow_supported": hasattr(os, "O_NOFOLLOW"),
    }
    DIAGNOSTIC_CONTEXT["artifact_hash_diagnostic"] = diagnostic

    before_metadata = path.lstat()
    before_identity = file_identity(before_metadata)
    diagnostic["private_identity_before"] = before_identity
    if stat.S_ISLNK(before_metadata.st_mode) or not stat.S_ISREG(before_metadata.st_mode):
        raise RuntimeError("Frozen P1.5 FK artifact is not a regular non-symlink file")
    if before_metadata.st_size > MAX_ARTIFACT_BYTES:
        raise RuntimeError("Frozen P1.5 FK artifact exceeds the registered byte limit")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        open_before = file_identity(os.fstat(handle.fileno()))
        diagnostic["private_identity_open_before"] = open_before
        payload = handle.read(MAX_ARTIFACT_BYTES + 1)
        if len(payload) > MAX_ARTIFACT_BYTES:
            diagnostic["size_bytes"] = len(payload)
            raise RuntimeError("Frozen P1.5 FK artifact exceeds the registered byte limit")
        open_after = file_identity(os.fstat(handle.fileno()))
        diagnostic["private_identity_open_after"] = open_after

    after_metadata = path.lstat()
    after_identity = file_identity(after_metadata)
    diagnostic["private_identity_after"] = after_identity
    digest = hashlib.sha256(payload).hexdigest()
    diagnostic["computed_sha256"] = digest
    diagnostic["size_bytes"] = len(payload)
    diagnostic["same_byte_buffer_for_hash_and_json"] = True

    helper_digest = sha256_file(path)
    diagnostic["chunked_path_helper_sha256"] = helper_digest
    after_helper_metadata = path.lstat()
    after_helper_identity = file_identity(after_helper_metadata)
    diagnostic["private_identity_after_helper"] = after_helper_identity
    identities = (
        before_identity,
        open_before,
        open_after,
        after_identity,
        after_helper_identity,
    )
    stable = all(identity == identities[0] for identity in identities[1:])
    diagnostic["file_identity_stable"] = stable

    if digest != EXPECTED_P1_5_FK_SHA or helper_digest != digest:
        raise RuntimeError("Frozen P1.5 FK artifact hash mismatch")
    if not stable:
        raise RuntimeError("Frozen P1.5 FK artifact identity changed while being read")

    parsed = json.loads(payload.decode("utf-8"))
    diagnostic["json_parsed_from_same_byte_buffer"] = True
    return parsed


def public_artifact_hash_diagnostic() -> dict[str, Any] | None:
    diagnostic = DIAGNOSTIC_CONTEXT.get("artifact_hash_diagnostic")
    if not isinstance(diagnostic, dict):
        return None
    public_keys = (
        "expected_sha256",
        "computed_sha256",
        "chunked_path_helper_sha256",
        "size_bytes",
        "same_byte_buffer_for_hash_and_json",
        "file_identity_stable",
        "o_nofollow_supported",
        "json_parsed_from_same_byte_buffer",
    )
    return {key: diagnostic.get(key) for key in public_keys}


def import_from_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load pinned source: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def question_key_hash(row: dict[str, Any]) -> str:
    key = json.dumps(
        [str(row.get("db_id", "")), str(row.get("question_id", ""))],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(key).hexdigest()


def write_safe_failure_receipt(exc: BaseException) -> Path | None:
    """Write exception location and counters without text, SQL, or locals."""
    raw_output = DIAGNOSTIC_CONTEXT.get("output_path")
    if not raw_output:
        return None
    output_path = Path(raw_output)
    receipt_path = output_path.with_name(output_path.stem + ".failure.json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    frames: list[dict[str, Any]] = []
    current = exc.__traceback__
    while current is not None:
        code = current.tb_frame.f_code
        source_path = Path(code.co_filename)
        frames.append({
            "module": source_path.stem,
            "function": code.co_name,
            "line": current.tb_lineno,
        })
        current = current.tb_next

    receipt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": DIAGNOSTIC_CONTEXT.get("run_id"),
        "method": DIAGNOSTIC_CONTEXT.get("method"),
        "stage": DIAGNOSTIC_CONTEXT.get("stage"),
        "error_type": type(exc).__name__,
        "error_module": type(exc).__module__,
        "question_key_sha256": DIAGNOSTIC_CONTEXT.get("question_key_sha256"),
        "safe_frames": frames[-20:],
        "counters": DIAGNOSTIC_CONTEXT.get("counters", {}),
        "artifact_hash_diagnostic_private": DIAGNOSTIC_CONTEXT.get("artifact_hash_diagnostic"),
        "exception_message_written": False,
        "source_lines_written": False,
        "locals_written": False,
        "raw_questions_written": False,
        "raw_sql_written": False,
    }
    try:
        with receipt_path.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(receipt_path, 0o600)
    except FileExistsError:
        # Preserve any prior run's failure evidence.
        return None
    return receipt_path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--method", choices=("packet", "p1_5"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--p1-5-fk-artifact", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    DIAGNOSTIC_CONTEXT.update({
        "run_id": args.run_id,
        "method": args.method,
        "output_path": str(args.output),
        "stage": "validate_output_path",
    })
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing private result")
    if args.method == "p1_5" and args.p1_5_fk_artifact is None:
        raise ValueError("P1.5 mode requires the frozen private FK artifact")

    os.environ.setdefault("OMP_NUM_THREADS", str(MAX_THREADS))
    os.environ.setdefault("MKL_NUM_THREADS", str(MAX_THREADS))
    DIAGNOSTIC_CONTEXT["stage"] = "verify_frozen_input_hashes"
    started_wall = time.perf_counter()
    started_cpu = time.process_time()

    dev_sha = sha256_file(args.dev_json)
    tables_sha = sha256_file(args.tables_json)
    if dev_sha != EXPECTED_DEV_SHA or tables_sha != EXPECTED_TABLES_SHA:
        raise RuntimeError("Frozen input hash mismatch")
    if sha256_file(PACKET_PATH) != EXPECTED_PACKET_CODE_SHA:
        raise RuntimeError("Pinned P0 packet source hash mismatch")
    if sha256_file(P1_5_PATH) != EXPECTED_P1_5_CODE_SHA:
        raise RuntimeError("Pinned P1.5 source hash mismatch")

    packet = import_from_path("p0_packet_pinned", PACKET_PATH)
    if args.method == "packet":
        DIAGNOSTIC_CONTEXT["stage"] = "load_packet_inputs"
        questions, schemas, data_hashes = packet.load_inputs(args.dev_json, args.tables_json)
        if data_hashes.get("dev.json") != EXPECTED_DEV_SHA or data_hashes.get("dev_tables.json") != EXPECTED_TABLES_SHA:
            raise RuntimeError("P0 input loader hash contract mismatch")
        active = questions[:5] if args.mode == "smoke" else questions
        if args.mode == "full" and len(questions) != EXPECTED_FULL_QUESTIONS:
            raise RuntimeError("P0 full question denominator mismatch")
        p1_5 = None
        fk_by_db: dict[str, list[dict[str, Any]]] = {}
    else:
        DIAGNOSTIC_CONTEXT["stage"] = "load_p1_5_inputs_and_fk_artifact"
        questions = load_json(args.dev_json)
        schemas_raw = load_json(args.tables_json)
        schemas = {
            str(schema["db_id"]): schema
            for schema in schemas_raw
        }
        data_hashes = {"dev.json": dev_sha, "dev_tables.json": tables_sha}
        active = questions[:5] if args.mode == "smoke" else questions
        if args.mode == "full" and len(questions) != EXPECTED_FULL_QUESTIONS:
            raise RuntimeError("P1.5 full question denominator mismatch")
        DIAGNOSTIC_CONTEXT["stage"] = "hash_and_parse_p1_5_fk_artifact_same_bytes"
        fk_artifact = load_frozen_artifact_from_same_bytes(args.p1_5_fk_artifact)
        DIAGNOSTIC_CONTEXT["stage"] = "validate_p1_5_fk_artifact_structure"
        fk_by_db = fk_artifact.get("instances_private", {})
        if not isinstance(fk_by_db, dict) or len(fk_by_db) != 11:
            raise RuntimeError("Frozen P1.5 FK artifact structure mismatch")
        p1_5 = import_from_path("p1_5_pinned", P1_5_PATH)

    rows: list[dict[str, Any]] = []
    parse_ok = 0
    join_on_queries = 0
    fk_match_queries = 0
    multi_fk_candidate_queries = 0
    for record in active:
        current_question_key = question_key_hash(record)
        DIAGNOSTIC_CONTEXT["question_key_sha256"] = current_question_key
        DIAGNOSTIC_CONTEXT["stage"] = "p0_packet_analyze_question" if args.method == "packet" else "p1_5_golden_join_audit"
        db_id = str(record.get("db_id", ""))
        if db_id not in schemas:
            raise RuntimeError("Input question references an unknown schema")
        if args.method == "packet":
            try:
                has_join_on, fk_matched, candidate_groups = packet.analyze_question(record, schemas[db_id])
            except Exception as exc:
                raise RuntimeError("Pinned P0 parser failed with " + type(exc).__name__) from None
            row = {
                "question_key_sha256": question_key_hash(record),
                "parse_ok": True,
                "has_join_on": bool(has_join_on),
                "fk_match": bool(fk_matched),
                "multi_fk_candidate": bool(candidate_groups),
            }
        else:
            result = p1_5.golden_join_audit(
                str(record.get("SQL", "")),
                db_id,
                fk_by_db.get(db_id, []),
            )
            row = {
                "question_key_sha256": question_key_hash(record),
                "parse_ok": bool(result["parse_ok"]),
                "has_join_on": bool(result["join_on_count"] > 0),
                "fk_match": bool(result["matched"] > 0),
                "multi_fk_candidate": bool(result["role_candidate_joins"] > 0),
                "join_on_count": int(result["join_on_count"]),
                "matched_join_count": int(result["matched"]),
                "partial_join_count": int(result["partial"]),
                "unmatched_join_count": int(result["unmatched"]),
                "ambiguous_join_count": int(result["ambiguous"]),
                "role_candidate_join_count": int(result["role_candidate_joins"]),
            }
        rows.append(row)
        parse_ok += int(row["parse_ok"])
        join_on_queries += int(row["has_join_on"])
        fk_match_queries += int(row["fk_match"])
        multi_fk_candidate_queries += int(row["multi_fk_candidate"])
        DIAGNOSTIC_CONTEXT["counters"] = {
            "records_processed": len(rows),
            "parse_ok": parse_ok,
            "join_on_questions": join_on_queries,
            "fk_match_queries": fk_match_queries,
            "multi_fk_candidate_queries": multi_fk_candidate_queries,
        }

    DIAGNOSTIC_CONTEXT["stage"] = "validate_resource_and_denominator_gates"
    elapsed_wall = time.perf_counter() - started_wall
    elapsed_cpu = time.process_time() - started_cpu
    peak_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    if elapsed_wall > MAX_WALL_SECONDS or elapsed_cpu > MAX_CPU_SECONDS or peak_rss_gib > MAX_RSS_GIB:
        raise RuntimeError("Registered resource budget exceeded")
    if args.mode == "full":
        if parse_ok != EXPECTED_FULL_QUESTIONS or join_on_queries != EXPECTED_FULL_JOIN_ON:
            raise RuntimeError("Full parse or JOIN-ON denominator mismatch")
        expected = EXPECTED_PACKET if args.method == "packet" else EXPECTED_P1_5
        observed = {
            "fk_match_queries": fk_match_queries,
            "multi_fk_candidate_queries": multi_fk_candidate_queries,
        }
        if observed != expected:
            raise RuntimeError("Frozen implementation aggregate did not reproduce its registered counter")
    elif len(rows) != 5:
        raise RuntimeError("Smoke must process exactly five rows")

    output = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "method": args.method,
        "status": "SMOKE_PASS" if args.mode == "smoke" else "FULL_COMPLETE",
        "python_version": platform.python_version(),
        "sqlglot_version": __import__("sqlglot").__version__,
        "source_hashes": {
            "packet_runner": sha256_file(PACKET_PATH),
            "p1_5_runner": sha256_file(P1_5_PATH),
            "reconciliation_runner": sha256_file(Path(__file__).resolve()),
        },
        "input_hashes": data_hashes,
        "p1_5_fk_artifact_sha256": EXPECTED_P1_5_FK_SHA if args.method == "p1_5" else None,
        "artifact_hash_diagnostic": public_artifact_hash_diagnostic(),
        "denominators": {
            "records_processed": len(rows),
            "parse_ok": parse_ok,
            "join_on_questions": join_on_queries,
            "fk_match_queries": fk_match_queries,
            "multi_fk_candidate_queries": multi_fk_candidate_queries,
        },
        "resources": {
            "wall_seconds": elapsed_wall,
            "cpu_seconds": elapsed_cpu,
            "peak_rss_gib": peak_rss_gib,
            "gpu_seconds": 0,
            "model_calls": 0,
            "api_calls": 0,
            "sql_execution": 0,
        },
        "private_question_rows": rows,
        "raw_questions_written": False,
        "raw_sql_written": False,
        "database_names_written": False,
    }
    DIAGNOSTIC_CONTEXT["stage"] = "write_private_result"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({k: output[k] for k in ("run_id", "status", "method", "python_version", "sqlglot_version", "denominators", "resources")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Exception messages from parser/data libraries may include private text.
        try:
            receipt_path = write_safe_failure_receipt(exc)
        except Exception:
            receipt_path = None
        print(json.dumps({
            "status": "STOP_INVALID",
            "error_type": type(exc).__name__,
            "failure_receipt_written": receipt_path is not None,
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
