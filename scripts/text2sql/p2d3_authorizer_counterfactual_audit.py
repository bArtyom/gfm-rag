#!/usr/bin/env python3
"""Offline, read-only outcome audit of P2d.3 authorizer-rejected SQL candidates."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.text2sql import p2d3_context_bounded_repair as p2d3

EXPERIMENT = "p2d3_authorizer_counterfactual_audit_20261106_01"
SOURCE_EXPERIMENT = "p2d3_context_bounded_repair_20261105_01"
EXPECTED_INITIAL_DENIALS = 6
EXPECTED_REJECTED_REPAIRS = 8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_source(expected_commit: str) -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    remote = subprocess.check_output(["git", "rev-parse", f"origin/{branch}"], cwd=ROOT, text=True).strip()
    require(head == expected_commit, "Registered experiment source commit mismatch")
    require(not status, "Experiment source worktree is dirty")
    require(remote == expected_commit, "Published experiment branch does not match source commit")
    return {"commit": head, "branch": branch}


def load_artifacts(args) -> dict:
    source = check_source(args.expected_source_commit)
    result_root = args.source_result_root.resolve(strict=True)
    prepared_root = (result_root / "prepare_002").resolve(strict=True)
    full_root = (result_root / "full_003").resolve(strict=True)
    prep_seal_path = prepared_root / "prepare_seal_private.json"
    pred_seal_path = full_root / "prediction_seal_private.json"
    predictions_path = full_root / "predictions_private.jsonl"
    evaluation_path = prepared_root / "evaluation_private.json"
    private_evaluation_path = full_root / "evaluation_aggregate_private.json"

    require(sha256(prep_seal_path) == args.expected_preparation_seal,
            "Frozen preparation seal SHA-256 mismatch")
    prep_seal = read_json(prep_seal_path)
    for relative, expected in prep_seal["files"].items():
        require(sha256(prepared_root / relative) == expected,
                "Frozen prepared artifact SHA-256 mismatch")
    for case in prep_seal["cases"]:
        require(sha256(prepared_root / case["file"]) == case["sha256"],
                "Frozen prepared case SHA-256 mismatch")
    for item in prep_seal.get("input_hashes_private", {}).values():
        require(sha256(Path(item["path_private"])) == item["sha256"],
                "Frozen source input SHA-256 mismatch")

    pred_seal = read_json(pred_seal_path)
    require(sha256(predictions_path) == args.expected_predictions_sha,
            "Frozen prediction SHA-256 mismatch")
    require(pred_seal["predictions_sha256"] == args.expected_predictions_sha,
            "Prediction receipt does not match registered SHA-256")
    require(pred_seal["prepare_seal_sha256"] == args.expected_preparation_seal,
            "Prediction receipt references a different preparation seal")
    predictions = read_jsonl(predictions_path)
    require(len(predictions) == 198, "Expected 198 sealed predictions from 66 cases × 3 arms")

    evaluation = read_json(evaluation_path)
    p2d3.check_database_hashes(evaluation)
    saved_evaluation = read_json(private_evaluation_path)
    require(len(saved_evaluation) == 66, "Frozen P2d.3 private evaluation must contain 66 rows")
    saved_evaluation_by_case = {row["case_id"]: row for row in saved_evaluation}
    require(len(saved_evaluation_by_case) == 66, "Duplicate case key in frozen evaluation")

    by_arm_case = {}
    for row in predictions:
        key = (row["case_id"], row["arm"])
        require(key not in by_arm_case, "Duplicate prediction arm/case key")
        by_arm_case[key] = row
    require(all(sum(1 for row in predictions if row["arm"] == arm) == 66
                for arm in ("A0", "A1", "A2")), "Prediction arm denominators changed")

    a2_rows = [row for row in predictions if row["arm"] == "A2"]
    initial_denials = sorted(row["case_id"] for row in a2_rows
                             if row["initial_context_denied_private"] is True)
    rejected_repairs = sorted(
        row["case_id"] for row in a2_rows
        if row["repair_attempted"] is True
        and row["repair_accepted"] is False
        and row["repair_status_private"] == "rejected_out_of_context"
    )
    require(len(initial_denials) == EXPECTED_INITIAL_DENIALS,
            "Initial A2 context denial count differs from preregistration")
    require(len(rejected_repairs) == EXPECTED_REJECTED_REPAIRS,
            "A2 rejected repair count differs from preregistration")
    require(set(initial_denials).issubset(saved_evaluation_by_case),
            "An initial-denial case has no frozen evaluation row")
    require(set(rejected_repairs).issubset(evaluation),
            "A rejected repair case has no frozen reference evaluation input")
    return {
        "source": source,
        "result_root": result_root,
        "prepared_root": prepared_root,
        "full_root": full_root,
        "prep_seal_path": prep_seal_path,
        "pred_seal_path": pred_seal_path,
        "predictions_path": predictions_path,
        "evaluation": evaluation,
        "saved_evaluation_by_case": saved_evaluation_by_case,
        "by_arm_case": by_arm_case,
        "initial_denials": initial_denials,
        "rejected_repairs": rejected_repairs,
    }


def response_record(full_root: Path, case_id: str, kind: str) -> tuple[Path, dict, str]:
    path = full_root / "requests" / f"{case_id}-{kind}.response.json"
    record = read_json(path)
    require(record.get("http_status") == 200 and record.get("error_type") is None,
            "A frozen response record is not a successful HTTP response")
    response = record.get("response") or {}
    choices = response.get("choices") or []
    require(len(choices) == 1 and isinstance(choices[0].get("message", {}).get("content"), str),
            "A frozen response does not contain one text completion")
    return path, record, p2d3.extract_sql(choices[0]["message"]["content"])


def build_registration(args, artifacts: dict) -> dict:
    descriptors = []
    for case_id in artifacts["initial_denials"]:
        path, _, initial_sql = response_record(artifacts["full_root"], case_id, "initial")
        a0_sql = artifacts["by_arm_case"][(case_id, "A0")]["sql_private"]
        require(initial_sql == a0_sql, "Shared initial SQL differs from the frozen A0 output")
        descriptors.append({
            "stratum": "initial_context_denial",
            "case_id_private": case_id,
            "response_path_private": str(path.relative_to(artifacts["full_root"])),
            "response_sha256": sha256(path),
            "sql_source": "frozen A0 initial output; verified against saved initial response",
        })
    for case_id in artifacts["rejected_repairs"]:
        path, _, _ = response_record(artifacts["full_root"], case_id, "A2")
        descriptors.append({
            "stratum": "authorizer_rejected_repair",
            "case_id_private": case_id,
            "response_path_private": str(path.relative_to(artifacts["full_root"])),
            "response_sha256": sha256(path),
            "sql_source": "frozen A2 repair response",
        })
    database_hashes = {}
    for item in artifacts["evaluation"].values():
        path = Path(item["database_path_private"])
        database_hashes[str(path)] = item["database_sha256"]
    return {
        "experiment_id": EXPERIMENT,
        "source": artifacts["source"],
        "source_experiment": SOURCE_EXPERIMENT,
        "preparation_seal_sha256": sha256(artifacts["prep_seal_path"]),
        "prediction_seal_sha256": sha256(artifacts["pred_seal_path"]),
        "predictions_sha256": sha256(artifacts["predictions_path"]),
        "private_case_count": 66,
        "initial_context_denial_count": len(artifacts["initial_denials"]),
        "rejected_repair_count": len(artifacts["rejected_repairs"]),
        "response_records_private": descriptors,
        "database_manifest_private": database_hashes,
        "evaluation_input_sha256_private": sha256(artifacts["prepared_root"] / "evaluation_private.json"),
    }


def load_registration(args, artifacts: dict) -> tuple[Path, dict, str]:
    path = args.output_dir / "registration_private.json"
    registration = read_json(path)
    registration_sha = sha256(path)
    require(registration_sha == args.expected_registration_sha,
            "Private response registration SHA-256 mismatch")
    require(registration["source"] == artifacts["source"],
            "Private response registration references a different source commit")
    require(registration["preparation_seal_sha256"] == sha256(artifacts["prep_seal_path"]),
            "Private response registration preparation seal changed")
    require(registration["predictions_sha256"] == sha256(artifacts["predictions_path"]),
            "Private response registration prediction source changed")
    require(registration["evaluation_input_sha256_private"] ==
            sha256(artifacts["prepared_root"] / "evaluation_private.json"),
            "Private response registration evaluation input changed")
    descriptors = registration.get("response_records_private", [])
    require(len(descriptors) == EXPECTED_INITIAL_DENIALS + EXPECTED_REJECTED_REPAIRS,
            "Private response registration candidate count changed")
    require(sum(item.get("stratum") == "initial_context_denial" for item in descriptors)
            == EXPECTED_INITIAL_DENIALS,
            "Private response registration initial-denial count changed")
    require(sum(item.get("stratum") == "authorizer_rejected_repair" for item in descriptors)
            == EXPECTED_REJECTED_REPAIRS,
            "Private response registration rejected-repair count changed")
    for path_text, expected in registration["database_manifest_private"].items():
        require(sha256(Path(path_text)) == expected, "Registered SQLite database SHA-256 changed")
    for descriptor in descriptors:
        path = artifacts["full_root"] / descriptor["response_path_private"]
        require(sha256(path) == descriptor["response_sha256"],
                "Registered frozen response SHA-256 changed")
        _, _, sql = response_record(artifacts["full_root"], descriptor["case_id_private"],
                                    "initial" if descriptor["stratum"] == "initial_context_denial" else "A2")
        require(bool(sql), "A frozen SQL candidate is empty")
    return path, registration, registration_sha


def replay_candidate(case_id: str, sql: str, kind: str, evaluation: dict,
                     config: dict, reference_cache: dict) -> dict:
    target = evaluation[case_id]
    db = Path(target["database_path_private"])
    if case_id not in reference_cache:
        reference_cache[case_id] = p2d3.execute_if_compiled(db, target["reference_sql_private"], config)
    reference = reference_cache[case_id]
    compile_result = p2d3.compile_readonly(db, sql)
    if compile_result["status"] != "compiled":
        return {"kind": kind, "status": compile_result["status"],
                "reference_status": reference.get("status", "unknown"),
                "set_correct_comparable": None, "bag_correct_comparable": None,
                "set_correct_as_frozen_evaluator": None, "bag_correct_as_frozen_evaluator": None,
                "comparison_status": "not_executed"}
    predicted = p2d3.execute_if_compiled(db, sql, config)
    if predicted.get("status") != "ok":
        return {"kind": kind, "status": predicted.get("status", "unknown"),
                "reference_status": reference.get("status", "unknown"),
                "set_correct_comparable": None, "bag_correct_comparable": None,
                "set_correct_as_frozen_evaluator": None, "bag_correct_as_frozen_evaluator": None,
                "comparison_status": "execution_unavailable"}
    compared = p2d3.sql_results_to_public(predicted, reference)
    return {
        "kind": kind,
        "status": "executable",
        "reference_status": reference.get("status", "unknown"),
        "set_correct_as_frozen_evaluator": compared["set_correct"],
        "bag_correct_as_frozen_evaluator": compared["bag_correct"],
        "set_correct_comparable": compared["set_correct"] if reference.get("status") == "ok" else None,
        "bag_correct_comparable": compared["bag_correct"] if reference.get("status") == "ok" else None,
        "comparison_status": compared["comparison_status"],
    }


def aggregate_replays(rows: list[dict]) -> dict:
    status_counts = Counter(row["status"] for row in rows)
    reference_available = sum(row.get("reference_status") == "ok" for row in rows)
    return {
        "n": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "reference_available": reference_available,
        "reference_unavailable": sum(row.get("reference_status") not in (None, "ok") for row in rows),
        "read_only_executable": sum(row["status"] == "executable" for row in rows),
        "set_correct_comparable": sum(row.get("set_correct_comparable") is True for row in rows),
        "bag_correct_comparable": sum(row.get("bag_correct_comparable") is True for row in rows),
        "set_correct_as_frozen_evaluator": sum(row.get("set_correct_as_frozen_evaluator") is True for row in rows),
        "bag_correct_as_frozen_evaluator": sum(row.get("bag_correct_as_frozen_evaluator") is True for row in rows),
        "set_incomparable": sum(row.get("set_correct_comparable") is None for row in rows),
    }


def run_replay(args, artifacts: dict, registration: dict, registration_sha: str) -> dict:
    if args.stage == "smoke":
        selected = []
        initial = [row for row in registration["response_records_private"]
                   if row["stratum"] == "initial_context_denial"]
        repairs = [row for row in registration["response_records_private"]
                   if row["stratum"] == "authorizer_rejected_repair"]
        selected.extend(initial[:1])
        selected.extend(repairs[:2])
    else:
        selected = registration["response_records_private"]

    reference_cache = {}
    replay_rows = []
    for descriptor in selected:
        kind = descriptor["stratum"]
        if kind == "initial_context_denial":
            sql = artifacts["by_arm_case"][(descriptor["case_id_private"], "A0")]["sql_private"]
        else:
            _, _, sql = response_record(artifacts["full_root"], descriptor["case_id_private"], "A2")
        replay_rows.append(replay_candidate(descriptor["case_id_private"], sql, kind,
                                            artifacts["evaluation"], args.sql_config,
                                            reference_cache))

    initial_rows = [row for row in replay_rows if row["kind"] == "initial_context_denial"]
    repair_rows = [row for row in replay_rows if row["kind"] == "authorizer_rejected_repair"]
    if args.stage == "full":
        # Same initial SQL must reproduce the original A0 execution comparison.
        for descriptor, replay in zip(selected, replay_rows):
            if descriptor["stratum"] != "initial_context_denial":
                continue
            case_id = descriptor["case_id_private"]
            saved_a0 = artifacts["saved_evaluation_by_case"][case_id]["arms"]["A0"]
            require(replay["set_correct_as_frozen_evaluator"] == saved_a0["set_correct"] and
                    replay["bag_correct_as_frozen_evaluator"] == saved_a0["bag_correct"],
                    "Initial SQL replay differs from frozen A0 Set/Bag outcome")

        case_ids = [row["case_id_private"] for row in selected
                    if row["stratum"] == "initial_context_denial"]
        a0_a2 = {"n": len(case_ids), "a0_set_correct": 0, "a2_set_correct": 0,
                 "a0_bag_correct": 0, "a2_bag_correct": 0,
                 "a0_only_set_correct": 0, "a2_only_set_correct": 0}
        for case_id in case_ids:
            arms = artifacts["saved_evaluation_by_case"][case_id]["arms"]
            a0_set = arms["A0"]["set_correct"] is True
            a2_set = arms["A2"]["set_correct"] is True
            a0_bag = arms["A0"]["bag_correct"] is True
            a2_bag = arms["A2"]["bag_correct"] is True
            a0_a2["a0_set_correct"] += int(a0_set)
            a0_a2["a2_set_correct"] += int(a2_set)
            a0_a2["a0_bag_correct"] += int(a0_bag)
            a0_a2["a2_bag_correct"] += int(a2_bag)
            a0_a2["a0_only_set_correct"] += int(a0_set and not a2_set)
            a0_a2["a2_only_set_correct"] += int(a2_set and not a0_set)
    else:
        a0_a2 = None

    summary = {
        "experiment_id": EXPERIMENT,
        "stage": args.stage,
        "status": "SMOKE_PASS" if args.stage == "smoke" else "FULL_COMPLETED",
        "source_commit": artifacts["source"]["commit"],
        "source_experiment": SOURCE_EXPERIMENT,
        "preparation_seal_sha256": sha256(artifacts["prep_seal_path"]),
        "predictions_sha256": sha256(artifacts["predictions_path"]),
        "private_registration_sha256": registration_sha,
        "sample_counts": {
            "initial_context_denials": len(initial_rows),
            "authorizer_rejected_repair_candidates": len(repair_rows),
            "candidate_replays": len(replay_rows),
        },
        "initial_context_denial_replay": aggregate_replays(initial_rows),
        "rejected_repair_candidate_replay": aggregate_replays(repair_rows),
        "a0_vs_frozen_a2_on_initial_denials": a0_a2,
        "privacy": {
            "questions_published": False,
            "sql_published": False,
            "database_names_or_paths_published": False,
            "per_case_results_published": False,
            "query_result_rows_published": False,
        },
    }
    output_path = args.output_dir / f"{args.stage}_summary.json"
    write_new(output_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("register", "smoke", "full"), required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-preparation-seal", required=True)
    parser.add_argument("--expected-predictions-sha", required=True)
    parser.add_argument("--expected-registration-sha", default=None)
    parser.add_argument("--source-result-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sql-config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.source_result_root = args.source_result_root.resolve(strict=True)
    args.output_dir = args.output_dir.resolve()
    args.sql_config = args.sql_config.resolve(strict=True)
    artifacts = load_artifacts(args)
    if args.stage == "register":
        require(not args.output_dir.exists(), "Audit output directory already exists; refusing overwrite")
        registration = build_registration(args, artifacts)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        path = args.output_dir / "registration_private.json"
        write_new(path, registration)
        result = {"status": "REGISTERED", "registration_sha256": sha256(path),
                  "initial_context_denials": registration["initial_context_denial_count"],
                  "authorizer_rejected_repairs": registration["rejected_repair_count"]}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return

    require(args.expected_registration_sha is not None,
            "Smoke and Full require the frozen private registration SHA-256")
    _, registration, registration_sha = load_registration(args, artifacts)
    if args.stage == "full":
        smoke_path = args.output_dir / "smoke_summary.json"
        require(smoke_path.is_file() and read_json(smoke_path).get("status") == "SMOKE_PASS",
                "Full requires the registered passing offline Smoke")
    args.sql_config = read_json(args.sql_config).get("sql")
    require(isinstance(args.sql_config, dict), "Frozen SQL limits are missing from P2d.3 config")
    result = run_replay(args, artifacts, registration, registration_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
