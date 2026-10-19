"""Exercise the archive/local-summary boundary that previously failed in Full."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.text2sql import run_p2c_dual_view_factorial as p2c

ARCHIVE_PATH = p2c.P2B_PUBLIC_AGGREGATE
VARIANTS = {"V00": "R0_local_cpu_pass_1", "V11": "R1_local_cpu_without_values"}
PATHS = [((f"column_r{k}_query_macro",), ("column_recall_query_macro", str(k))) for k in (5, 10, 20)] + [
    ((archived, str(budget)), ("budgets", str(budget), local))
    for budget in (512, 1024, 2048)
    for archived, local in (
        ("complete_query_macro", "complete_query_macro"),
        ("budget_recall_query_macro", "gold_schema_recall_query_macro"),
        ("mean_tokens_used", "mean_returned_tokens"),
    )
]


def put(root, path, value):
    for key in path[:-1]:
        root = root.setdefault(key, {})
    root[path[-1]] = value


def get(root, path):
    for key in path:
        root = root[key]
    return root


def archived_summaries():
    """Independent test adapter, using actual published archive values."""
    archive = json.loads(ARCHIVE_PATH.read_text())
    summaries = {}
    for arm, variant in VARIANTS.items():
        condition = archive["conditions"][variant]
        summaries[arm] = {}
        for group, denominator in (("all", "all_column_eligible_questions"), ("fixed_non_saturated", "fixed_non_saturated_questions")):
            local = {"denominators": {"column_eligible_questions": condition["denominators"][denominator]}}
            for archived_path, local_path in PATHS:
                put(local, local_path, get(condition[group], archived_path))
            summaries[arm][group] = local
    return archive, summaries


def test_real_p2b_archive_all_48_values_replay():
    archive, summaries = archived_summaries()
    receipt = p2c.assert_p2b_aggregate_replay(archive, summaries)
    assert receipt == {"metric_comparisons": 48, "denominator_comparisons": 4}


@pytest.mark.parametrize("arm", VARIANTS)
@pytest.mark.parametrize("group", ("all", "fixed_non_saturated"))
@pytest.mark.parametrize("archived_path,local_path", PATHS)
def test_every_replayed_metric_rejects_individual_corruption(arm, group, archived_path, local_path):
    archive, summaries = archived_summaries()
    put(summaries[arm][group], local_path, get(summaries[arm][group], local_path) + 0.01)
    with pytest.raises(RuntimeError) as caught:
        p2c.assert_p2b_aggregate_replay(archive, summaries)
    assert "/".join((arm, group, *local_path)) in str(caught.value)


@pytest.mark.parametrize("invalid", (None, float("nan"), float("inf"), {}, [], True))
@pytest.mark.parametrize("side", ("archive", "local"))
def test_invalid_metric_is_rejected_with_full_path(invalid, side):
    archive, summaries = archived_summaries()
    if side == "archive":
        archive["conditions"][VARIANTS["V00"]]["all"]["column_r5_query_macro"] = invalid
    else:
        summaries["V00"]["all"]["column_recall_query_macro"]["5"] = invalid
    with pytest.raises(RuntimeError) as caught:
        p2c.assert_p2b_aggregate_replay(archive, summaries)
    assert "column" in str(caught.value) and "all" in str(caught.value)


@pytest.mark.parametrize("side", ("archive", "local"))
def test_missing_metric_is_rejected_with_full_path(side):
    archive, summaries = archived_summaries()
    if side == "archive":
        del archive["conditions"][VARIANTS["V00"]]["all"]["complete_query_macro"]["512"]
    else:
        del summaries["V00"]["all"]["budgets"]["512"]["complete_query_macro"]
    with pytest.raises(RuntimeError) as caught:
        p2c.assert_p2b_aggregate_replay(archive, summaries)
    assert "512" in str(caught.value) and "complete" in str(caught.value)


def test_wrong_denominator_and_empty_summaries_cannot_pass():
    archive, summaries = archived_summaries()
    summaries["V00"]["all"]["denominators"]["column_eligible_questions"] -= 1
    with pytest.raises(RuntimeError, match="denominators"):
        p2c.assert_p2b_aggregate_replay(archive, summaries)
    with pytest.raises(RuntimeError, match="V00"):
        p2c.assert_p2b_aggregate_replay(archive, {})


def test_new_registration_validates_p2b_checksum_without_reopening_old_experiment():
    new_id = "p2c_r_contract_gate_20261019_01"
    config = {"experiment_id": new_id}
    completed = {"experiment_id": "p2b_values_ablation_20261018_01", "final_result": {"aggregate_summary_sha256": "a" * 64}}
    assert p2c.p2b_registered_aggregate_sha256(config, completed, expected_experiment_id=new_id) == "a" * 64
    with pytest.raises(RuntimeError, match="Unexpected"):
        p2c.p2b_registered_aggregate_sha256(config, completed)


def synthetic_aggregate_inputs():
    """Six synthetic questions on two databases; baseline complete = 3/6."""
    nodes = [SimpleNamespace(node_id=f"{db}_{kind}", db_id=db, node_type=kind, text=f"private_{db}_{kind}", token_count=50)
             for db in ("private_alpha", "private_beta") for kind in ("table", "column")]
    shorter = [SimpleNamespace(**vars(n)) for n in nodes]
    for node in shorter:
        if node.node_type == "column":
            node.text += "_short"
            node.token_count = 25
    rows_by_arm = {}
    questions = []
    for arm in p2c.ARM_FACTORS:
        rows = []
        for index in range(6):
            db = "private_alpha" if index < 3 else "private_beta"
            ids = [f"{db}_table", f"{db}_column"]
            complete = int(index in ({0, 1, 3, 4, 5} if arm == "V01" else {1, 3, 5}))
            typed = lambda kind: {"topk_ids": {str(k): [f"{db}_{kind}"] for k in (5, 10, 20)},
                                 "recall": {str(k): 1.0 for k in (5, 10, 20)},
                                 "precision": {str(k): 1.0 for k in (5, 10, 20)}}
            rows.append({"question_id": index, "db_id": db, "column_eligible": True, "methods": {"S0_cosine": {
                "table": typed("table"), "column": typed("column"), "budgets": {
                    str(b): {"complete": complete, "recall": float(complete), "tokens_used": 100,
                             "returned_elements": 2, "selected_ids": ids if complete else []}
                    for b in (512, 1024, 2048)}}}})
            if arm == "V00":
                questions.append({"db_id": db, "question_id": index, "text": "private_question_marker",
                                  "label": {"column_eligible": True, "gold_table_ids": [ids[0]], "gold_column_ids": [ids[1]]}})
        rows_by_arm[arm] = rows
    condition = {"denominators": {"all_column_eligible_questions": 6, "fixed_non_saturated_questions": 3}}
    for group, complete in (("all", 0.5), ("fixed_non_saturated", 1 / 3)):
        condition[group] = {"column_r5_query_macro": 1.0, "column_r10_query_macro": 1.0, "column_r20_query_macro": 1.0,
                            "complete_query_macro": {str(b): complete for b in (512, 1024, 2048)},
                            "budget_recall_query_macro": {str(b): complete for b in (512, 1024, 2048)},
                            "mean_tokens_used": {str(b): 100 for b in (512, 1024, 2048)}}
    info = {"p2b_aggregate": {"conditions": {variant: copy.deepcopy(condition) for variant in VARIANTS.values()}},
            "prepared_full": {"questions": questions}, "fixed_questions": 3,
            "p2b_audit": {"r0_schema_text_sequence_sha256": "0" * 64, "r1_schema_text_sequence_sha256": "1" * 64},
            "p2b_hashes": {"input_manifest_sha256": "2" * 64}}
    digests = {key: {"digest": "3" * 64} for key in ("R0", "R1", "R0_context_check", "R1_context_check")}
    return info, rows_by_arm, digests, {"private_alpha"}, nodes, shorter


def test_full_aggregate_path_roundtrip_rescue_bootstrap_and_privacy(tmp_path):
    info, rows, digests, fixed, nodes, shorter = synthetic_aggregate_inputs()
    result = p2c.build_aggregate("synthetic_contract_only", {"published_commit": "4" * 40}, info, rows, digests, fixed, nodes, shorter)
    assert result["benchmark"]["questions"] == 6
    assert result["benchmark"]["databases"] == 2
    assert result["primary_gate"]["all"]["delta_pp"] == pytest.approx(100 / 3)
    assert result["paired_rescue_damage"]["V01_minus_V00"]["all"]["complete_1024"] == {
        "rescued": 2, "damaged": 0, "unchanged": 4, "questions": 6}
    assert result["factorial_contrasts"]["complete_1024"]["all"]["interaction"] == pytest.approx(-1 / 3)
    assert result["bootstrap"] == {"unit": "database cluster", "draws": 10000, "seed": 20261020}
    assert set(result["per_database_anonymized"]) == {"db_01", "db_02"}
    target = tmp_path / "aggregate_summary.json"
    p2c.write_json(target, result)
    assert json.loads(target.read_text()) == result
    assert p2c.sha256_file(target) == hashlib.sha256(target.read_bytes()).hexdigest()
    published = target.read_text()
    for forbidden in ("private_alpha", "private_beta", "private_question_marker", '"question_id"', '"selected_ids"'):
        assert forbidden not in published


def test_shorter_early_candidate_can_displace_later_gold():
    p1 = p2c.load_module(p2c.P1_6_RUNNER, "p1_for_p2c_r_packing_test")
    p2a = p2c.load_module(p2c.P2A_RUNNER, "p2a_for_p2c_r_packing_test")
    p2a.p1_module = p1
    nodes = [SimpleNamespace(node_id=name, db_id="synthetic", node_type=kind, text=name, token_count=tokens)
             for name, kind, tokens in (("table", "table", 100), ("distractor", "column", 1100), ("gold", "column", 100))]
    question = {"question_id": 0, "db_id": "synthetic", "text": "gold", "label": {
        "column_eligible": True, "gold_table_ids": ["table"], "gold_column_ids": ["gold"]}}
    vectors = np.array([[1.0, 0], [0.8, 0.6], [0.6, 0.8]], dtype=np.float32)
    _, before = p2a.evaluate({"questions": [question], "nodes": nodes}, vectors[:1], vectors)
    shortened = [SimpleNamespace(**vars(node)) for node in nodes]
    shortened[1].token_count = 900
    _, after = p2a.evaluate({"questions": [question], "nodes": shortened}, vectors[:1], vectors)
    assert before[0]["methods"]["S0_cosine"]["budgets"]["1024"]["complete"] == 1
    assert after[0]["methods"]["S0_cosine"]["budgets"]["1024"]["complete"] == 0
    p2c.assert_context_only_ranking_invariant(before, after)
