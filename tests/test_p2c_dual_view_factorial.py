from __future__ import annotations

import pytest

from scripts.text2sql.run_p2c_dual_view_factorial import (
    ARM_FACTORS,
    assert_context_only_ranking_invariant,
    assert_p2b_replay,
    factorial_contrasts,
    p2b_registered_aggregate_sha256,
)


def make_row(question_id: int, table_ids: list[str], column_ids: list[str], budgets: dict) -> dict:
    return {
        "question_id": question_id,
        "db_id": "db_a",
        "column_eligible": True,
        "methods": {
            "S0_cosine": {
                "table": {"topk_ids": {"5": table_ids, "10": table_ids}},
                "column": {"topk_ids": {"5": column_ids, "10": column_ids, "20": column_ids}},
                "budgets": budgets,
            }
        },
    }


def test_arm_matrix_separates_rank_and_context_views() -> None:
    assert ARM_FACTORS == {
        "V00": ("R0", "R0"),
        "V01": ("R0", "R1"),
        "V10": ("R1", "R0"),
        "V11": ("R1", "R1"),
    }


def test_context_only_change_preserves_every_table_and_column_topk() -> None:
    rows_r0 = [make_row(1, ["t1"], ["c1"], {})]
    rows_r1 = [make_row(1, ["t1"], ["c1"], {"1024": {"selected_ids": ["t1"]}})]

    assert_context_only_ranking_invariant(rows_r0, rows_r1)


def test_context_only_change_rejects_a_ranking_difference() -> None:
    rows_r0 = [make_row(1, ["t1"], ["c1"], {})]
    rows_r1 = [make_row(1, ["t2"], ["c1"], {})]

    with pytest.raises(RuntimeError, match="table Top-K"):
        assert_context_only_ranking_invariant(rows_r0, rows_r1)


def test_p2b_replay_checks_preserved_column_ranks_and_budget_rows() -> None:
    budgets = {str(budget): {"selected_ids": [f"n{budget}"], "tokens_used": budget} for budget in (512, 1024, 2048)}
    expected = [{
        "question_id": 1,
        "db_id": "db_a",
        "column_eligible": True,
        "variants": {
            "R0_local_cpu_pass1": {
                "column_topk_ids": {"5": ["c1"], "10": ["c1"], "20": ["c1"]},
                "budgets": budgets,
            },
        },
    }]
    replay = [make_row(1, ["t1"], ["c1"], budgets)]

    assert_p2b_replay(expected, replay, "R0_local_cpu_pass1")


def test_p2b_replay_rejects_changed_budget_selection() -> None:
    expected = [{
        "question_id": 1,
        "db_id": "db_a",
        "column_eligible": True,
        "variants": {
            "R1_local_cpu_without_values": {
                "column_topk_ids": {"5": ["c1"], "10": ["c1"], "20": ["c1"]},
                "budgets": {"1024": {"selected_ids": ["old"]}},
            },
        },
    }]
    replay = [make_row(1, ["t1"], ["c1"], {"1024": {"selected_ids": ["new"]}})]

    with pytest.raises(RuntimeError, match="budget replay"):
        assert_p2b_replay(expected, replay, "R1_local_cpu_without_values")


def test_factorial_contrasts_separate_context_ranking_and_interaction() -> None:
    actual = factorial_contrasts({"V00": 0.40, "V01": 0.50, "V10": 0.45, "V11": 0.62})

    assert actual["context_effect_at_R0"] == pytest.approx(0.10)
    assert actual["ranking_effect_at_R0"] == pytest.approx(0.05)
    assert actual["context_effect_at_R1"] == pytest.approx(0.17)
    assert actual["interaction"] == pytest.approx(0.07)


def test_p2b_aggregate_hash_comes_from_completed_p2b_config() -> None:
    p2c_config = {"experiment_id": "p2c_dual_view_20261018_01", "status": "recovery_preregistered_not_run"}
    p2b_config = {"experiment_id": "p2b_values_ablation_20261018_01", "final_result": {"aggregate_summary_sha256": "abc123"}}

    assert p2b_registered_aggregate_sha256(p2c_config, p2b_config) == "abc123"
