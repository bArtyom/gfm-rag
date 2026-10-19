import copy
import json

import pytest

from scripts.text2sql import run_p2c_r_recovery as recovery
from tests.test_p2c_r_contract import synthetic_aggregate_inputs


def test_gate_code_guard_detects_changes_in_dynamically_loaded_helpers(tmp_path):
    helper = tmp_path / "scorer.py"
    helper.write_text("version = 1\n")
    before = {"executed_sources_sha256": recovery.execution_source_hashes([helper], tmp_path)}
    recovery.assert_gate_code(before, before)
    helper.write_text("version = 2\n")
    after = {"executed_sources_sha256": recovery.execution_source_hashes([helper], tmp_path)}
    with pytest.raises(RuntimeError, match="scorer.py"):
        recovery.assert_gate_code(before, after)


@pytest.mark.parametrize("corruption", ("none", "delete", "alter", "identity", "state"))
def test_predecessor_requires_intact_persisted_aggregate_and_receipt(tmp_path, corruption):
    target = tmp_path / "aggregate_summary.json"
    target.write_text('{"engineering": true}\n')
    receipt = {"experiment_id": recovery.EXPERIMENT_ID, "run_id": "registered_smoke", "state": "completed",
               "stage_result": "smoke_passed", "source": {"published_commit": "a" * 40},
               "aggregate_summary_sha256": recovery.core.sha256_file(target)}
    if corruption == "delete":
        target.unlink()
    elif corruption == "alter":
        target.write_text('{"engineering": false}\n')
    elif corruption == "identity":
        receipt["run_id"] = "another_run"
    elif corruption == "state":
        receipt["state"] = "failed"
    (tmp_path / "run_start.json").write_text(json.dumps(receipt))
    if corruption == "none":
        recovery.read_stage_receipt(tmp_path, recovery.EXPERIMENT_ID, "registered_smoke", "smoke_passed", "a" * 40)
    else:
        with pytest.raises(RuntimeError):
            recovery.read_stage_receipt(tmp_path, recovery.EXPERIMENT_ID, "registered_smoke", "smoke_passed", "a" * 40)


def test_contract_mode_cannot_accept_old_or_scientific_run_ids():
    config = {"experiment_id": recovery.GATE0_ID, "status": "preregistered_not_run",
              "run_ids": {"contract": "p2c_r_contract_20261019_01"}}
    recovery.validate_registration(config, "contract", "p2c_r_contract_20261019_01")
    with pytest.raises(RuntimeError):
        recovery.validate_registration(config, "full", "p2c_dual_view_full1534_20261018_03")
    with pytest.raises(RuntimeError):
        recovery.validate_registration(config, "contract", "p2c_dual_view_full1534_20261018_02")


@pytest.mark.parametrize("registered,computed", (
    ("P2b_cache_sha256", "cpu_cache_sha256"),
    ("P2b_private_rows_sha256", "private_rows_sha256"),
    ("P2b_public_aggregate_sha256", "public_aggregate_sha256"),
    ("input_manifest_sha256", "input_manifest_sha256"),
))
def test_registered_frozen_hashes_are_enforced_before_scoring(registered, computed):
    pairs = {"P2b_cache_sha256": "cpu_cache_sha256", "P2b_private_rows_sha256": "private_rows_sha256",
             "P2b_public_aggregate_sha256": "public_aggregate_sha256", "input_manifest_sha256": "input_manifest_sha256"}
    config = {"frozen_inputs": {key: "a" * 64 for key in pairs}}
    hashes = {key: "a" * 64 for key in pairs.values()}
    recovery.assert_frozen_hashes(config, hashes)
    hashes[computed] = "b" * 64
    with pytest.raises(RuntimeError, match=registered):
        recovery.assert_frozen_hashes(config, hashes)


def test_archived_rows_roundtrip_uses_duplicate_placeholders_not_cross_scoring():
    info, arms, _, fixed, nodes, shorter = synthetic_aggregate_inputs()
    info.update({"fixed_dbs": fixed, "r1_nodes_full": shorter,
                 "source": {"published_commit": "0" * 40}})
    info["prepared_full"]["nodes"] = nodes
    saved = []
    for row in arms["V00"]:
        method = row["methods"]["S0_cosine"]
        variant = {"column_topk_ids": method["column"]["topk_ids"],
                   "column_hits": {"5": 1, "10": 1, "20": 1}, "budgets": method["budgets"]}
        saved.append({"question_id": row["question_id"], "db_id": row["db_id"], "column_eligible": True,
                      "variants": {"R0_local_cpu_pass1": copy.deepcopy(variant), "R1_local_cpu_without_values": copy.deepcopy(variant)}})
    info["p2b_rows"] = saved
    aggregate, receipt = recovery.archive_contract(info, "synthetic_contract")
    assert receipt["metric_comparisons"] == 48
    assert aggregate["cross_arm_scoring"] is False
    assert aggregate["scientific_result"] is False
    assert aggregate["primary_gate"]["evaluated"] is False
    assert aggregate["arms"]["V01"]["metrics"] == aggregate["arms"]["V00"]["metrics"]
    assert aggregate["arms"]["V10"]["metrics"] == aggregate["arms"]["V11"]["metrics"]
