#!/usr/bin/env python3
"""Bounded P2c-R: archive-only contract gate, then registered smoke/full."""
from __future__ import annotations

import argparse
import copy
import json
import platform
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.text2sql import run_p2c_dual_view_factorial as core

GATE0_ID = "p2c_r_contract_gate_20261019_01"
EXPERIMENT_ID = "p2c_r_recovery_20261019_01"
PROTOCOL = core.REPO_ROOT / "docs/research/text2sql/plans/p2c_r_replay_contract_recovery_20261018.md"
EXECUTION_SOURCES = (
    Path(__file__).resolve(), Path(core.__file__).resolve(), core.P1_6_RUNNER, core.P2A_RUNNER, core.P2B_RUNNER,
    core.REPO_ROOT / "scripts/text2sql/run_p1_5_diagnostics.py",
    core.REPO_ROOT / "docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/gfmrag_p1_common.py",
)


def execution_source_hashes(paths=EXECUTION_SOURCES, root=core.REPO_ROOT):
    return {str(path.relative_to(root)): core.sha256_file(path) for path in paths}


def assert_gate_code(gate_source, current_source):
    before = gate_source["executed_sources_sha256"]
    after = current_source["executed_sources_sha256"]
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    if not before or changed:
        raise RuntimeError("Execution code changed after Gate 0: " + ", ".join(changed))


def read_stage_receipt(directory, experiment_id, run_id, stage_result, expected_commit=None):
    try:
        receipt = json.loads((directory / "run_start.json").read_text())
        if (receipt["experiment_id"], receipt["run_id"], receipt["state"], receipt["stage_result"]) != (
            experiment_id, run_id, "completed", stage_result
        ):
            raise RuntimeError("Predecessor identity/state differs from registration")
        if expected_commit is not None and receipt["source"]["published_commit"] != expected_commit:
            raise RuntimeError("Predecessor source commit differs from registration")
        if core.sha256_file(directory / "aggregate_summary.json") != receipt["aggregate_summary_sha256"]:
            raise RuntimeError("Predecessor aggregate SHA differs from receipt")
        return receipt
    except (OSError, KeyError, ValueError) as error:
        raise RuntimeError("Predecessor evidence is incomplete or invalid") from error


def validate_registration(config, mode, run_id):
    expected_id = GATE0_ID if mode == "contract" else EXPERIMENT_ID
    if config.get("experiment_id") != expected_id or config.get("status") != "preregistered_not_run":
        raise RuntimeError("Unexpected or closed P2c-R registration")
    expected_run = config.get("run_ids", {}).get(mode)
    if not expected_run or run_id != expected_run or not run_id.startswith("p2c_r_"):
        raise RuntimeError("Run ID/mode is outside the independent P2c-R registration")


def assert_frozen_hashes(config, computed):
    for registered_key, computed_key in (
        ("P2b_cache_sha256", "cpu_cache_sha256"),
        ("P2b_private_rows_sha256", "private_rows_sha256"),
        ("P2b_public_aggregate_sha256", "public_aggregate_sha256"),
        ("input_manifest_sha256", "input_manifest_sha256"),
    ):
        expected = config["frozen_inputs"][registered_key]
        if not isinstance(expected, str) or len(expected) != 64 or computed[computed_key] != expected:
            raise RuntimeError(f"Frozen registration hash differs: {registered_key}")


def archived_rows(prepared, archived, variant):
    """Reconstruct archived Column/budget metrics; Table fields are placeholders."""
    if len(prepared["questions"]) != len(archived):
        raise RuntimeError("Archived contract question count differs")
    rows = []
    for question, saved in zip(prepared["questions"], archived):
        if (question["question_id"], question["db_id"]) != (saved["question_id"], saved["db_id"]):
            raise RuntimeError("Archived contract question order differs")
        old = saved["variants"][variant]
        column = None
        if saved["column_eligible"]:
            gold_count = len(question["label"]["gold_column_ids"])
            if not gold_count:
                raise RuntimeError("Archived eligible row has no Gold columns")
            column = {"topk_ids": copy.deepcopy(old["column_topk_ids"]),
                      "recall": {str(k): old["column_hits"][str(k)] / gold_count for k in (5, 10, 20)},
                      "precision": {str(k): old["column_hits"][str(k)] / len(old["column_topk_ids"][str(k)]) for k in (5, 10, 20)}}
        rows.append({"question_id": saved["question_id"], "db_id": saved["db_id"],
                     "column_eligible": saved["column_eligible"], "methods": {"S0_cosine": {
                         "table": {"topk_ids": {"5": [], "10": []}, "recall": {"5": 0., "10": 0.}, "precision": {"5": 0., "10": 0.}},
                         "column": column, "budgets": copy.deepcopy(old["budgets"])}}})
    return rows


def archive_contract(info, run_id):
    r0 = archived_rows(info["prepared_full"], info["p2b_rows"], core.P2B_ROW_VARIANTS["V00"])
    r1 = archived_rows(info["prepared_full"], info["p2b_rows"], core.P2B_ROW_VARIANTS["V11"])
    arms = {"V00": r0, "V01": copy.deepcopy(r0), "V10": copy.deepcopy(r1), "V11": r1}
    for arm in ("V00", "V11"):
        core.assert_p2b_replay(info["p2b_rows"], arms[arm], core.P2B_ROW_VARIANTS[arm])
    receipt = core.assert_p2b_aggregate_replay(info["p2b_aggregate"], {
        arm: core.summarize_rows(rows, info["fixed_dbs"]) for arm, rows in arms.items()})
    placeholders = {key: {"digest": "engineering_placeholder_no_scores"}
                    for key in ("R0", "R1", "R0_context_check", "R1_context_check")}
    aggregate = core.build_aggregate(run_id, info["source"], info, arms, placeholders,
                                     info["fixed_dbs"], info["prepared_full"]["nodes"], info["r1_nodes_full"])
    aggregate.update({"experiment_id": GATE0_ID, "status": "engineering_only",
                      "scientific_result": False, "cross_arm_scoring": False,
                      "placeholder_arms": {"V01": "duplicate archived R0", "V10": "duplicate archived R1"},
                      "table_metrics": "synthetic zero placeholders; not historical measurements",
                      "primary_gate": {"evaluated": False, "reason": "Archive-only engineering contract, no new cross-arm scores"}})
    return aggregate, receipt


def subset_reference(prepared, saved_rows, fixed):
    """Reference only for the five-question smoke, derived from archived rows."""
    archive = {"conditions": {}}
    for arm, variant in core.P2B_AGGREGATE_VARIANTS.items():
        rows = archived_rows(prepared, saved_rows, core.P2B_ROW_VARIANTS[arm])
        summary = core.summarize_rows(rows, fixed)
        condition = {"denominators": {
            "all_column_eligible_questions": summary["all"]["denominators"]["column_eligible_questions"],
            "fixed_non_saturated_questions": summary["fixed_non_saturated"]["denominators"]["column_eligible_questions"]}}
        for group in ("all", "fixed_non_saturated"):
            local = summary[group]
            condition[group] = {f"column_r{k}_query_macro": local["column_recall_query_macro"][str(k)] for k in (5, 10, 20)}
            for archived_key, local_key in (("complete_query_macro", "complete_query_macro"),
                                           ("budget_recall_query_macro", "gold_schema_recall_query_macro"),
                                           ("mean_tokens_used", "mean_returned_tokens")):
                condition[group][archived_key] = {str(b): local["budgets"][str(b)][local_key] for b in (512, 1024, 2048)}
        archive["conditions"][variant] = condition
    return archive


def write_roundtrip(path, aggregate):
    core.write_json(path, aggregate)
    restored = json.loads(path.read_text(encoding="utf-8"))
    if restored != aggregate or core.json_digest(restored) != core.json_digest(aggregate):
        raise RuntimeError("Aggregate JSON roundtrip differs")
    return core.sha256_file(path)


def score_registered_arms(info, mode, run_id, started_cpu):
    prepared, cache, indexes = core.select_active_inputs(info["prepared_full"], info["cache_full"], mode)
    r0 = prepared["nodes"]
    r1 = [info["r1_nodes_full"][index] for index in indexes]
    fixed = info["fixed_dbs"] & {question["db_id"] for question in prepared["questions"]}
    rows_by_arm = {}
    for arm, (score_view, context_view) in core.ARM_FACTORS.items():
        print(json.dumps({"stage": "evaluate_arm", "arm": arm, "questions": len(prepared["questions"])}), flush=True)
        active = dict(prepared, nodes=r0 if context_view == "R0" else r1)
        _, rows_by_arm[arm] = info["p2a"].evaluate(active, cache["query_vectors"], cache[f"{score_view.lower()}_node_vectors"])
        core.check_budget(started_cpu)
    digests = {view: core.score_matrix_digests(prepared, info["p1"], cache["query_vectors"], cache[f"{view.lower()}_node_vectors"])
               for view in ("R0", "R1")}
    digests.update({"R0_context_check": core.score_matrix_digests(prepared, info["p1"], cache["query_vectors"], cache["r0_node_vectors"]),
                    "R1_context_check": core.score_matrix_digests(prepared, info["p1"], cache["query_vectors"], cache["r1_node_vectors"])})
    saved = info["p2b_rows"][:len(prepared["questions"])]
    for arm in ("V00", "V11"):
        core.assert_p2b_replay(saved, rows_by_arm[arm], core.P2B_ROW_VARIANTS[arm])
    active_info = dict(info, prepared_full=prepared)
    if mode == "smoke":
        active_info["p2b_aggregate"] = subset_reference(prepared, saved, fixed)
        active_info["fixed_questions"] = sum(q["label"]["column_eligible"] and q["db_id"] in fixed for q in prepared["questions"])
    aggregate = core.build_aggregate(run_id, info["source"], active_info, rows_by_arm, digests, fixed, r0, r1)
    aggregate["experiment_id"] = EXPERIMENT_ID
    aggregate["scientific_result"] = mode == "full"
    if mode == "smoke":
        aggregate["primary_gate"] = {"evaluated": False, "reason": "Five-question smoke; not formal evidence"}
        aggregate["status"] = "smoke_only"
    return aggregate, rows_by_arm, digests


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("contract", "smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    for name in ("output-dir", "p1-6-run-dir", "legacy-root", "dataset-root", "model-path", "previous-run-dir", "p1-5-run-dir", "p2b-run-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--contract-dir", type=Path)
    parser.add_argument("--smoke-dir", type=Path)
    return parser.parse_args()


def run():
    args = parse_args()
    experiment = GATE0_ID if args.mode == "contract" else EXPERIMENT_ID
    config_path = core.REPO_ROOT / f"docs/research/text2sql/reports/{experiment}/experiment_config.json"
    config = json.loads(config_path.read_text())
    validate_registration(config, args.mode, args.run_id)
    if args.output_dir.resolve() != Path(config["private_output_dirs"][args.mode]).resolve():
        raise RuntimeError("Output path differs from the unique registered directory")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    receipt = {"experiment_id": experiment, "run_id": args.run_id, "mode": args.mode, "state": "started",
               "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               "resource_snapshot": core.resource_snapshot(), "environment": {"python": platform.python_version(),
                  **{name: core.package_version(name) for name in ("numpy", "transformers", "tokenizers")}},
               "source": {"published_commit": args.expected_commit, "script_sha256": core.sha256_file(Path(__file__)),
                          "shared_runner_sha256": core.sha256_file(Path(core.__file__)), "config_sha256": core.sha256_file(config_path),
                          "protocol_sha256": core.sha256_file(PROTOCOL), "executed_sources_sha256": execution_source_hashes()},
               "api_calls": 0, "model_forwards": 0, "model_weights_loaded": False, "gpu_seconds": 0, "sql_executions": 0}
    receipt_path = args.output_dir / "run_start.json"
    core.write_json(receipt_path, receipt)
    try:
        print(json.dumps({"stage": "validate_frozen_inputs", "mode": args.mode}), flush=True)
        info = core.load_registered_inputs(args, config_path=config_path, plan_path=PROTOCOL, experiment_id=experiment)
        assert_frozen_hashes(config, info["p2b_hashes"])
        receipt["input_hashes"] = info["p2b_hashes"]
        receipt["source"].update(info["source"])
        if args.mode != "contract":
            if args.contract_dir is None or args.contract_dir.resolve() != Path(config["gate0_directory"]).resolve():
                raise RuntimeError("Registered Gate 0 directory is required")
            gate_path = args.contract_dir / "run_start.json"
            if core.sha256_file(gate_path) != config["gate0_receipt_sha256"]:
                raise RuntimeError("Gate 0 receipt hash differs from registration")
            gate = read_stage_receipt(args.contract_dir, GATE0_ID, config["gate0_run_id"], "contract_passed")
            if gate.get("stage_result") != "contract_passed" or gate["input_hashes"] != receipt["input_hashes"]:
                raise RuntimeError("Gate 0 did not pass on the same frozen inputs")
            assert_gate_code(gate["source"], receipt["source"])
            if gate["environment"] != receipt["environment"]:
                raise RuntimeError("Dependency versions changed after Gate 0")
            if args.mode == "full":
                if args.smoke_dir is None or args.smoke_dir.resolve() != Path(config["private_output_dirs"]["smoke"]).resolve():
                    raise RuntimeError("Registered smoke directory is required")
                smoke = read_stage_receipt(args.smoke_dir, EXPERIMENT_ID, config["run_ids"]["smoke"], "smoke_passed", args.expected_commit)
                if smoke.get("stage_result") != "smoke_passed" or smoke["source"]["published_commit"] != args.expected_commit or smoke["input_hashes"] != receipt["input_hashes"]:
                    raise RuntimeError("Smoke did not pass with identical source and frozen inputs")
        if args.mode == "contract":
            aggregate, checks = archive_contract(info, args.run_id)
            receipt.update(checks, cross_arm_scoring=False, archived_questions=len(info["p2b_rows"]))
        else:
            aggregate, rows, digests = score_registered_arms(info, args.mode, args.run_id, started_cpu)
            if args.mode == "full":
                receipt["private_per_question_sha256"] = core.write_private_rows(args.output_dir / "per_question_private.jsonl", rows, digests)
                receipt["gate_decision"] = aggregate["primary_gate"]["decision"]
        receipt["aggregate_summary_sha256"] = write_roundtrip(args.output_dir / "aggregate_summary.json", aggregate)
        core.check_budget(started_cpu)
        receipt.update(state="completed", stage_result=args.mode + "_passed", aggregate_roundtrip_verified=True)
    except Exception as error:
        receipt.update(state="failed", error_type=type(error).__name__, error_message=str(error))
        raise
    finally:
        receipt.update(finished_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       wall_seconds=time.perf_counter() - started_wall, cpu_seconds=time.process_time() - started_cpu,
                       peak_rss_gib=core.peak_rss_gib())
        core.write_json(receipt_path, receipt)
        print(json.dumps({key: receipt.get(key) for key in ("run_id", "state", "stage_result", "cpu_seconds", "wall_seconds", "peak_rss_gib", "gate_decision", "error_message")}), flush=True)


if __name__ == "__main__":
    run()
