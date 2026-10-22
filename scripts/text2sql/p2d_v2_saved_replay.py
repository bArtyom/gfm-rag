"""Re-evaluate frozen P2d SQL privately with v1/v2 parity gates.

This script never calls a model or prints SQL, database paths, row values, or
case identifiers. Input and output roots must stay outside the repository.
Gate 1 replays only SQL that v1 had executed successfully and stores v2 rows
privately. Gate 2 reuses those rows and executes each remaining frozen SQL once.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import pickle
import re
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.text2sql.p2d_sql_context_eval import verify_database_hashes  # noqa: E402
from scripts.text2sql.p2d_sql_evaluator import compare_rows as compare_v1  # noqa: E402
from scripts.text2sql.p2d_sql_evaluator import execute_readonly as execute_v1  # noqa: E402
from scripts.text2sql.p2d_sql_evaluator_v2 import compare_rows as compare_v2  # noqa: E402
from scripts.text2sql.p2d_sql_evaluator_v2 import execute_readonly as execute_v2  # noqa: E402

EXPECTED_PREDICTIONS_SHA256 = "f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3"
EXPECTED_AGGREGATE_SHA256 = "091b3b68b2a24a693c8e12a2783d9630d6f467c521616a0b366bc81c41fea1f2"
EXPECTED_EVALUATION_SHA256 = "bbd53dcf5c3c97890269b2f74e03e9551d1970b0e84ae6e0f08585655f97f809"
EXPECTED_PREPARE_SEAL_SHA256 = "334e388af338c7f20575aa81a86ff7184e526716b251cd1b48955b4134172aaa"
ARMS = ("E0", "E1", "E2")
CPU_SECONDS_MAX = 600
RSS_BYTES_MAX = 4 * 1024 * 1024 * 1024


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_value(value):
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is bytes:
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if type(value) is str:
        return ["str", value]
    raise TypeError("unsupported SQLite result type")


def result_signature(result):
    signature = {"status": result.get("status"), "error_type": result.get("error_type")}
    if result.get("status") == "ok":
        rows = [json.dumps([canonical_value(cell) for cell in row], ensure_ascii=False, separators=(",", ":"))
                for row in result["rows"]]
        rows.sort()
        signature.update({
            "columns": result["columns"],
            "row_count": len(rows),
            "row_multiset_sha256": hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(),
        })
    return signature


def load_pickle(path: Path):
    with path.open("rb") as source:
        return pickle.load(source)


def load_inputs(prepared_root: Path, full_root: Path):
    seal_path = prepared_root / "prepare_seal_private.json"
    if sha(seal_path) != EXPECTED_PREPARE_SEAL_SHA256:
        raise RuntimeError("prepared source seal mismatch")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    for relative, expected in seal["files"].items():
        if sha(prepared_root / relative) != expected:
            raise RuntimeError("prepared source hash mismatch")
    case_rows = [json.loads((prepared_root / item["file"]).read_text(encoding="utf-8"))
                 for item in seal["cases"] if item.get("cohort") != "smoke"]
    if len(case_rows) != 30:
        raise RuntimeError("frozen case count mismatch")
    evaluation_path = full_root / "evaluation_private.json"
    if sha(evaluation_path) != EXPECTED_EVALUATION_SHA256:
        raise RuntimeError("frozen evaluation hash mismatch")
    evaluation = json.loads((prepared_root / "evaluation_private.json").read_text(encoding="utf-8"))
    predictions_path = full_root / "predictions_private.json"
    prediction_seal = json.loads((full_root / "prediction_seal.json").read_text(encoding="utf-8"))
    if sha(predictions_path) != EXPECTED_PREDICTIONS_SHA256:
        raise RuntimeError("frozen prediction hash mismatch")
    if sha(full_root / "aggregate_summary.json") != EXPECTED_AGGREGATE_SHA256:
        raise RuntimeError("frozen aggregate hash mismatch")
    if prediction_seal.get("predictions_sha256") != EXPECTED_PREDICTIONS_SHA256:
        raise RuntimeError("prediction seal mismatch")
    if prediction_seal.get("prepare_seal_sha256") != EXPECTED_PREPARE_SEAL_SHA256:
        raise RuntimeError("prediction preparation seal mismatch")
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    if len(predictions) != 90:
        raise RuntimeError("frozen prediction count mismatch")
    prediction_map = {(item["case_id"], item["arm"]): item for item in predictions}
    if len(prediction_map) != 90:
        raise RuntimeError("duplicate frozen prediction")
    case_map = {item["case_id"]: item for item in case_rows}
    if set(case_map) != {case_id for case_id, _ in prediction_map}:
        raise RuntimeError("frozen case/prediction mismatch")
    recorded_evaluation = json.loads((full_root / "evaluation_private.json").read_text(encoding="utf-8"))
    recorded_evaluation = {(row["case_id"], row["arm"]): row for row in recorded_evaluation}
    if len(recorded_evaluation) != 90:
        raise RuntimeError("frozen evaluation count mismatch")
    return case_rows, case_map, evaluation, prediction_map, recorded_evaluation


def verify_runtime(expected_commit: str):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    if head != expected_commit or dirty:
        raise RuntimeError("source must be clean at the published commit")
    return head


def execution_file(full_root: Path, case_id: str, arm: str) -> Path:
    return full_root / "executions_private" / f"{case_id}-{arm}.pickle"


def private_v2_file(output_root: Path, case_id: str, arm: str) -> Path:
    return output_root / "private_results" / f"{case_id}-{arm}.pickle"


def save_private_v2(output_root: Path, case_id: str, arm: str, result):
    path = private_v2_file(output_root, case_id, arm)
    path.parent.mkdir(exist_ok=True)
    with path.open("xb") as target:
        pickle.dump(result, target, protocol=pickle.HIGHEST_PROTOCOL)


def resource_snapshot(start_cpu: float):
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_seconds = time.process_time() - start_cpu + child.ru_utime + child.ru_stime
    rss_unit = 1024 if sys.platform.startswith("linux") else 1
    peak_rss_bytes = max(self_usage.ru_maxrss, child.ru_maxrss) * rss_unit
    if cpu_seconds > CPU_SECONDS_MAX or peak_rss_bytes > RSS_BYTES_MAX:
        raise RuntimeError("resource budget exceeded")
    return cpu_seconds, peak_rss_bytes


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tested_file_hashes():
    paths = (
        "scripts/text2sql/p2d_sql_evaluator.py",
        "scripts/text2sql/p2d_sql_evaluator_v2.py",
        "scripts/text2sql/p2d_v2_saved_replay.py",
        "tests/test_p2d_sql_evaluator.py",
        "tests/test_p2d_sql_evaluator_v2.py",
        "tests/test_p2d_inputs.py",
        "tests/test_p2d_pipeline.py",
    )
    return {name: sha(ROOT / name) for name in paths}


def run_synthetic_tests(out: Path, source_commit: str, start_cpu: float):
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_p2d_sql_evaluator_v2.py",
        "tests/test_p2d_sql_evaluator.py",
        "tests/test_p2d_inputs.py",
        "tests/test_p2d_pipeline.py",
        "-q",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, timeout=180)
    resource_snapshot(start_cpu)
    log = completed.stdout + completed.stderr
    log_path = out / "synthetic_test_log.txt"
    log_path.write_text(log, encoding="utf-8")
    match = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
    passed = int(match.group(1)) if match else 0
    skipped = int(match.group(2) or 0) if match else 0
    result = {
        "status": "PASS" if completed.returncode == 0 and passed > 0 else "FAIL",
        "source_commit": source_commit,
        "command": command,
        "return_code": completed.returncode,
        "passed": passed,
        "skipped": skipped,
        "failed": 0 if completed.returncode == 0 else 1,
        "tested_files_sha256": tested_file_hashes(),
        "test_log_sha256": sha(log_path),
        "model_calls": 0,
        "api_calls": 0,
    }
    write_json(out / "synthetic_test_receipt.json", result)
    return result


def private_result_manifest(output_root: Path, parity_details):
    results_dir = output_root / "private_results"
    result_entries = {}
    for detail in parity_details:
        case_id, arm = detail["case_id"], detail["arm"]
        name = f"{case_id}-{arm}.pickle"
        path = results_dir / name
        result = load_pickle(path)
        result_entries[name] = {
            "sha256": sha(path),
            "signature": result_signature(result),
            "case_id": case_id,
            "arm": arm,
        }
    manifest_path = output_root / "gate1" / "private_result_manifest.json"
    write_json(manifest_path, {"result_count": len(result_entries), "results": result_entries})
    return manifest_path


def verify_cache_membership(results_dir: Path, expected_names):
    if results_dir.is_symlink() or not results_dir.is_dir():
        raise RuntimeError("Gate 1 cache directory is missing or unsafe")
    entries = list(results_dir.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RuntimeError("Gate 1 cache contains a non-file or symlink")
    if {path.name for path in entries} != set(expected_names):
        raise RuntimeError("Gate 1 cache contains missing or unmanifested files")


def initialize_private_results_cache(results_dir: Path):
    if results_dir.is_symlink():
        raise RuntimeError("private result cache directory cannot be a symlink")
    if results_dir.exists():
        if not results_dir.is_dir() or any(results_dir.iterdir()):
            raise RuntimeError("private result cache must be an empty directory")
    else:
        results_dir.mkdir()


def verify_gate1_private_artifacts(output_root: Path, receipt: dict, source_commit: str):
    gate1 = output_root / "gate1"
    test_receipt_path = gate1 / "synthetic_test_receipt.json"
    parity_path = gate1 / "private_parity.json"
    manifest_path = gate1 / "private_result_manifest.json"
    if sha(test_receipt_path) != receipt.get("synthetic_test_receipt_sha256"):
        raise RuntimeError("synthetic test receipt changed")
    test_receipt = json.loads(test_receipt_path.read_text(encoding="utf-8"))
    if (test_receipt.get("status") != "PASS" or test_receipt.get("source_commit") != source_commit
            or test_receipt.get("tested_files_sha256") != tested_file_hashes()
            or sha(gate1 / "synthetic_test_log.txt") != test_receipt.get("test_log_sha256")):
        raise RuntimeError("synthetic safety test evidence is incomplete")
    if sha(parity_path) != receipt.get("private_parity_sha256"):
        raise RuntimeError("Gate 1 parity details changed")
    if sha(manifest_path) != receipt.get("private_result_manifest_sha256"):
        raise RuntimeError("Gate 1 cached-result manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    if manifest.get("result_count") != 83 or len(manifest.get("results", {})) != 83 or len(parity) != 83:
        raise RuntimeError("Gate 1 cache manifest count mismatch")
    expected = {}
    for detail in parity:
        name = f"{detail['case_id']}-{detail['arm']}.pickle"
        expected[name] = detail
    if set(expected) != set(manifest["results"]):
        raise RuntimeError("Gate 1 cache membership mismatch")
    results_dir = output_root / "private_results"
    verify_cache_membership(results_dir, manifest["results"])
    for name, entry in manifest["results"].items():
        if Path(name).name != name or entry.get("case_id") + "-" + entry.get("arm") + ".pickle" != name:
            raise RuntimeError("Gate 1 cache path mismatch")
        path = output_root / "private_results" / name
        if sha(path) != entry.get("sha256"):
            raise RuntimeError("Gate 1 cached result changed")
        if result_signature(load_pickle(path)) != entry.get("signature"):
            raise RuntimeError("Gate 1 cached result signature changed")
        parity_row = expected[name]
        if not parity_row.get("result_parity") or parity_row.get("comparison_parity") is False:
            raise RuntimeError("Gate 1 cached result does not satisfy parity")
        if result_signature(load_pickle(path)) != parity_row.get("replayed_v2"):
            raise RuntimeError("Gate 1 cached result differs from its parity evidence")
    return manifest


def compare_executions(prediction, reference, compare_rows):
    if prediction.get("status") != "ok" or reference.get("status") != "ok":
        return {"set_correct": None, "bag_correct": None, "comparison_status": "execution_unavailable"}
    if len(prediction.get("columns", ())) != len(reference.get("columns", ())):
        return {"set_correct": False, "bag_correct": False, "comparison_status": "column_count_mismatch"}
    return compare_rows(prediction["rows"], reference["rows"])


def phase_gate1(args, prepared_root: Path, full_root: Path, output_root: Path, source_commit: str):
    out = output_root / "gate1"
    initialize_private_results_cache(output_root / "private_results")
    out.mkdir(exist_ok=False)
    start_cpu = time.process_time()
    verify_database_hashes(prepared_root)
    synthetic_tests = run_synthetic_tests(out, source_commit, start_cpu)
    if synthetic_tests["status"] != "PASS":
        test_receipt_path = out / "synthetic_test_receipt.json"
        receipt = {
            "phase": "gate1",
            "status": "FAIL",
            "source_commit": source_commit,
            "synthetic_tests": "FAIL",
            "synthetic_test_receipt_sha256": sha(test_receipt_path),
            "reference_v1_successes_replayed": 0,
            "prediction_v1_successes_replayed": 0,
            "paired_sql_replays_v1_and_v2": 0,
            "real_saved_sql_executed": 0,
            "new_model_calls": 0,
            "new_api_calls": 0,
            "gpu_seconds": 0,
        }
        write_json(out / "receipt.json", receipt)
        print(json.dumps(receipt))
        return 2
    _, case_map, evaluation, prediction_map, recorded_evaluation = load_inputs(prepared_root, full_root)
    details = []
    reused = {}
    parity_failures = 0
    reference_successes = prediction_successes = 0
    successes_by_arm = Counter()

    for case_id in sorted(case_map):
        gold = evaluation[case_id]
        db_path = gold["database_path"]
        for arm in ("reference", *ARMS):
            old = load_pickle(execution_file(full_root, case_id, arm))
            if old.get("status") != "ok":
                continue
            if arm == "reference":
                sql = gold["reference_sql"]
                reference_successes += 1
            else:
                sql = prediction_map[(case_id, arm)]["sql"]
                prediction_successes += 1
                successes_by_arm[arm] += 1
            v1_result = execute_v1(db_path, sql, timeout=10, row_limit=50000,
                                   byte_limit=64 * 1024 * 1024, sqlite_memory_limit=256 * 1024 * 1024)
            resource_snapshot(start_cpu)
            v2_result = execute_v2(db_path, sql, timeout=10, row_limit=50000,
                                   byte_limit=64 * 1024 * 1024, sqlite_memory_limit=256 * 1024 * 1024)
            resource_snapshot(start_cpu)
            old_sig, v1_sig, v2_sig = map(result_signature, (old, v1_result, v2_result))
            parity = old_sig == v1_sig == v2_sig
            parity_failures += int(not parity)
            reused[(case_id, arm)] = v2_result
            save_private_v2(output_root, case_id, arm, v2_result)
            comparison_parity = None
            if arm != "reference" and old.get("status") == "ok":
                old_reference = load_pickle(execution_file(full_root, case_id, "reference"))
                if old_reference.get("status") == "ok":
                    old_score = compare_executions(old, old_reference, compare_v1)
                    new_reference = reused.get((case_id, "reference"))
                    if new_reference is None:
                        new_reference = load_pickle(private_v2_file(output_root, case_id, "reference"))
                    new_score = compare_executions(v2_result, new_reference, compare_v2)
                    saved_score = recorded_evaluation[(case_id, arm)]
                    saved_outcome = {key: saved_score.get(key) for key in
                                     ("set_correct", "bag_correct", "comparison_status")}
                    comparison_parity = old_score == new_score == saved_outcome
                    parity_failures += int(not comparison_parity)
            details.append({
                "case_id": case_id,
                "arm": arm,
                "old_v1": old_sig,
                "replayed_v1": v1_sig,
                "replayed_v2": v2_sig,
                "result_parity": parity,
                "comparison_parity": comparison_parity,
            })

    if (reference_successes != 26 or prediction_successes != 57 or len(details) != 83
            or dict(successes_by_arm) != {"E0": 19, "E1": 18, "E2": 20}):
        parity_failures += 1
    verify_database_hashes(prepared_root)
    cpu_seconds, peak_rss_bytes = resource_snapshot(start_cpu)
    status = "PASS" if parity_failures == 0 else "FAIL"
    private_path = out / "private_parity.json"
    write_json(private_path, details)
    manifest_path = private_result_manifest(output_root, details)
    test_receipt_path = out / "synthetic_test_receipt.json"
    receipt = {
        "phase": "gate1",
        "status": status,
        "source_commit": source_commit,
        "prediction_sha256": EXPECTED_PREDICTIONS_SHA256,
        "aggregate_sha256": EXPECTED_AGGREGATE_SHA256,
        "reference_v1_successes_replayed": reference_successes,
        "prediction_v1_successes_replayed": prediction_successes,
        "prediction_v1_successes_by_arm": dict(successes_by_arm),
        "paired_sql_replays_v1_and_v2": len(details),
        "output_and_comparison_parity_failures": parity_failures,
        "synthetic_tests": synthetic_tests["status"],
        "synthetic_test_count_passed": synthetic_tests["passed"],
        "synthetic_test_count_skipped": synthetic_tests["skipped"],
        "synthetic_test_receipt_sha256": sha(test_receipt_path),
        "private_parity_sha256": sha(private_path),
        "private_result_manifest_sha256": sha(manifest_path),
        "database_hashes_unchanged": True,
        "process_cpu_seconds": round(cpu_seconds, 3),
        "peak_rss_bytes": peak_rss_bytes,
        "new_model_calls": 0,
        "new_api_calls": 0,
        "gpu_seconds": 0,
    }
    write_json(out / "receipt.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "private_parity_sha256"}))
    return 0 if status == "PASS" else 2


def funnel_category(reference, prediction, comparison):
    if reference.get("status") != "ok":
        return "reference_unavailable"
    if prediction.get("status") != "ok":
        status = prediction.get("status")
        error = prediction.get("error_type")
        if status == "timeout":
            return "timeout"
        if status in {"row_limit", "byte_limit", "memory_limit"}:
            return "row_bytes_heap"
        if error == "sql_parse_error":
            return "prediction_parse"
        if error in {"unsafe_sql", "sqlite_authorizer_denied", "temporal_runtime_unsafe_argument"}:
            return "prediction_ast_policy"
        if error == "sqlite_error":
            return "prediction_sqlite"
        return "other_unavailable"
    if comparison.get("set_correct") is None or comparison.get("bag_correct") is None:
        return "compare_nonexact"
    if comparison["set_correct"] and comparison["bag_correct"]:
        return "comparable_correct"
    return "comparable_wrong"


def phase_gate2(args, prepared_root: Path, full_root: Path, output_root: Path, source_commit: str):
    gate1_root = output_root / "gate1"
    gate1_receipt_path = gate1_root / "receipt.json"
    gate1_receipt = json.loads(gate1_receipt_path.read_text(encoding="utf-8"))
    if gate1_receipt.get("status") != "PASS" or gate1_receipt.get("source_commit") != source_commit:
        raise RuntimeError("Gate 1 must pass at the same source commit")
    if sha(gate1_receipt_path) != args.gate1_receipt_sha256:
        raise RuntimeError("Gate 1 receipt changed after it passed")
    manifest = verify_gate1_private_artifacts(output_root, gate1_receipt, source_commit)
    out = output_root / "gate2"
    out.mkdir(exist_ok=False)
    start_cpu = time.process_time()
    verify_database_hashes(prepared_root)
    _, case_map, evaluation, prediction_map, recorded_evaluation = load_inputs(prepared_root, full_root)
    details = []
    executions = 0

    for case_id in sorted(case_map):
        gold = evaluation[case_id]
        db_path = gold["database_path"]
        reference_path = private_v2_file(output_root, case_id, "reference")
        if reference_path.name in manifest["results"]:
            reference = load_pickle(reference_path)
        else:
            reference = execute_v2(db_path, gold["reference_sql"], timeout=10, row_limit=50000,
                                   byte_limit=64 * 1024 * 1024, sqlite_memory_limit=256 * 1024 * 1024)
            resource_snapshot(start_cpu)
            save_private_v2(output_root, case_id, "reference", reference)
            executions += 1
        old_reference = load_pickle(execution_file(full_root, case_id, "reference"))
        for arm in ARMS:
            prediction_path = private_v2_file(output_root, case_id, arm)
            if prediction_path.name in manifest["results"]:
                prediction = load_pickle(prediction_path)
            else:
                sql = prediction_map[(case_id, arm)]["sql"]
                prediction = execute_v2(db_path, sql, timeout=10, row_limit=50000,
                                        byte_limit=64 * 1024 * 1024, sqlite_memory_limit=256 * 1024 * 1024)
                resource_snapshot(start_cpu)
                save_private_v2(output_root, case_id, arm, prediction)
                executions += 1
            old_prediction = load_pickle(execution_file(full_root, case_id, arm))
            comparison = compare_executions(prediction, reference, compare_v2)
            category = funnel_category(reference, prediction, comparison)
            recorded = recorded_evaluation[(case_id, arm)]
            details.append({
                "case_id": case_id,
                "arm": arm,
                "cohort": case_map[case_id].get("cohort"),
                "v1_reference_status": old_reference.get("status"),
                "v2_reference_status": reference.get("status"),
                "v1_prediction_status": old_prediction.get("status"),
                "v2_prediction_status": prediction.get("status"),
                "v1_set_correct": recorded.get("set_correct"),
                "v1_bag_correct": recorded.get("bag_correct"),
                "v1_comparison_status": recorded.get("comparison_status"),
                "v2_prediction_error_type": prediction.get("error_type"),
                "v2_prediction_error_category": prediction.get("error_category"),
                "v2_set_correct": comparison["set_correct"],
                "v2_bag_correct": comparison["bag_correct"],
                "v2_comparison_status": comparison["comparison_status"],
                "v2_funnel_category": category,
            })

    verify_database_hashes(prepared_root)
    cpu_seconds, peak_rss_bytes = resource_snapshot(start_cpu)
    counts = {arm: Counter(row["v2_funnel_category"] for row in details if row["arm"] == arm) for arm in ARMS}
    prediction_errors = {
        arm: Counter(row["v2_prediction_error_category"] or row["v2_prediction_error_type"]
                     for row in details if row["arm"] == arm and row["v2_prediction_status"] != "ok")
        for arm in ARMS
    }
    paired = {}
    indexed = {(row["case_id"], row["arm"]): row for row in details}
    for left, right in (("E0", "E1"), ("E0", "E2"), ("E1", "E2")):
        for version, field in (("v1", "v1_set_correct"), ("v2", "v2_set_correct")):
            outcomes = Counter()
            for case_id in case_map:
                a = indexed[(case_id, left)][field]
                b = indexed[(case_id, right)][field]
                outcomes["unknown" if a is None or b is None else
                         "both_correct" if a and b else left + "_only" if a else
                         right + "_only" if b else "both_wrong"] += 1
            paired[f"{version}_{left}_vs_{right}"] = outcomes
    private_path = out / "private_case_outcomes.json"
    private_path.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "phase": "gate2",
        "status": "completed",
        "source_commit": source_commit,
        "prediction_sha256": EXPECTED_PREDICTIONS_SHA256,
        "aggregate_sha256": EXPECTED_AGGREGATE_SHA256,
        "full_cases": len(case_map),
        "full_predictions": len(prediction_map),
        "v2_sql_executions_in_gate2": executions,
        "v2_sql_executions_reused_from_gate1": 83,
        "v2_sql_executions_total": executions + 83,
        "gate1_cached_results_verified": len(manifest["results"]),
        "funnel_by_arm": {arm: dict(counts[arm]) for arm in ARMS},
        "prediction_failure_categories_by_arm": {arm: dict(prediction_errors[arm]) for arm in ARMS},
        "paired_set_outcomes": {key: dict(value) for key, value in paired.items()},
        "private_outcomes_sha256": sha(private_path),
        "database_hashes_unchanged": True,
        "process_cpu_seconds": round(cpu_seconds, 3),
        "peak_rss_bytes": peak_rss_bytes,
        "new_model_calls": 0,
        "new_api_calls": 0,
        "gpu_seconds": 0,
    }
    write_json(out / "receipt.json", receipt)
    print(json.dumps(receipt))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("gate1", "gate2"), required=True)
    parser.add_argument("--prepared-root", type=Path, required=True)
    parser.add_argument("--full-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--gate1-receipt-sha256")
    args = parser.parse_args()
    prepared_root, full_root, output_root = (path.resolve() for path in
                                              (args.prepared_root, args.full_root, args.output_root))
    if any(ROOT == path or ROOT in path.parents for path in (prepared_root, full_root, output_root)):
        parser.error("private roots must remain outside the repository")
    for index, left in enumerate((prepared_root, full_root, output_root)):
        for right in (prepared_root, full_root, output_root)[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                parser.error("prepared, frozen-full, and output roots must not overlap")
    if args.phase == "gate2" and not args.gate1_receipt_sha256:
        parser.error("gate2 requires the frozen Gate 1 receipt SHA256")
    source_commit = verify_runtime(args.expected_commit)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (RSS_BYTES_MAX, RSS_BYTES_MAX))
        if args.phase == "gate1":
            code = phase_gate1(args, prepared_root, full_root, output_root, source_commit)
        else:
            code = phase_gate2(args, prepared_root, full_root, output_root, source_commit)
    except Exception as exc:
        print(json.dumps({"phase": args.phase, "status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(2) from None
    raise SystemExit(code)


if __name__ == "__main__":
    main()
