#!/usr/bin/env python3
"""Synthetic contract checks for the preregistered RAMP-SL V1 replay."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/text2sql/ramp_sl_v1_active_encoding.py"
SPEC = importlib.util.spec_from_file_location("ramp_sl_v1_active_encoding", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ramp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ramp
SPEC.loader.exec_module(ramp)


class CharTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(text)


class ConstantFallback:
    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return np.full(len(x), 0.4), np.full(len(x), 0.2)


class ConstantCalibrator:
    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full(len(x), 0.5)


def make_question(db_id: str = "test_db") -> ramp.QuestionData:
    ids = ["c1", "c2", "c3", "c4"]
    vectors = np.asarray(
        [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0], [-0.6, 0.8]],
        dtype=np.float64,
    )
    return ramp.QuestionData(
        db_id=db_id,
        question_id=1,
        question_index=0,
        text="find customer name",
        candidate_ids=ids,
        texts={cid: f"column:table.{cid}; text" for cid in ids},
        costs={cid: cost for cid, cost in zip(ids, [3, 2, 2, 1])},
        query_vector=np.asarray([1.0, 0.0], dtype=np.float64),
        candidate_vectors=vectors,
    )


def make_fake_store(q: ramp.QuestionData) -> ramp.ScoreReplayStore:
    store = ramp.ScoreReplayStore.__new__(ramp.ScoreReplayStore)
    store._private_scores = {q.key: {cid: 0.2 + index * 0.1 for index, cid in enumerate(q.candidate_ids)}}
    store._static_scores = {q.key: {cid: 0.9 - index * 0.1 for index, cid in enumerate(q.candidate_ids)}}
    store._static_candidate_ids = {q.key: list(q.candidate_ids)}
    store._costs = {q.key: dict(q.costs)}
    store._model_hashes = set()
    store._replay_read_trace = []
    store._test_prediction_seal_sha256 = None
    return store


class RampSLV1ContractTests(unittest.TestCase):
    def test_budget_fill_skips_oversized_item_and_continues(self) -> None:
        selected = ramp.budget_fill(["a", "b", "c"], {"a": 7, "b": 3, "c": 2}, 5)
        self.assertEqual(selected, ["b", "c"])

    def test_score_session_rejects_duplicate_and_over_budget_reads(self) -> None:
        q = make_question()
        store = make_fake_store(q)
        session = store.make_session(q, "unit", 4, "test", {q.db_id})
        session.score_batch(["c1"])
        with self.assertRaises(RuntimeError):
            session.score_batch(["c1"])
        with self.assertRaises(RuntimeError):
            session.score_batch(["c2", "c3"])

    def test_score_session_rejects_database_outside_allowed_split(self) -> None:
        q = make_question()
        store = make_fake_store(q)
        with self.assertRaises(PermissionError):
            store.make_session(q, "unit", 10, "test", {"other_db"})

    def test_shared_initial_batch_uses_historical_scores_then_adaptive_batch_uses_full_cache(self) -> None:
        q = make_question()
        store = make_fake_store(q)
        static = store.make_session(q, "Static-TopM", 10, "test", {q.db_id})
        other = store.make_session(q, "Random-2R", 10, "test", {q.db_id})
        self.assertEqual(static.score_batch(["c1"])["c1"], other.score_batch(["c1"])["c1"])
        self.assertNotEqual(other.score_batch(["c2"])["c2"], store._static_scores[q.key]["c2"])

    def test_initial_column_missing_from_historical_static_set_uses_full_score_cache(self) -> None:
        q = make_question()
        store = make_fake_store(q)
        store._static_scores[q.key] = {"c1": 0.91}
        store._static_candidate_ids[q.key] = ["c1"]
        session = store.make_session(q, "Random-2R", 10, "test", {q.db_id})
        first_scores = session.score_batch(["c1", "c2"])
        self.assertEqual(first_scores["c1"], 0.91)
        self.assertEqual(first_scores["c2"], store._private_scores[q.key]["c2"])
        training_initial = store.training_initial_scores(q, {q.db_id})
        self.assertEqual(training_initial["c1"], 0.91)
        self.assertEqual(training_initial["c2"], store._private_scores[q.key]["c2"])

    def test_ramp_second_round_scores_one_planned_batch(self) -> None:
        q = make_question()
        state = ramp.build_state(q)
        store = make_fake_store(q)
        config = {
            "budgets": {"M_input_tokens_per_question": 6, "M0_first_round_input_tokens": 3,
                        "gp_fallback_if_real_observations_below": 2, "gp_jitter": 1e-6,
                        "residual_scale_floor": 0.05},
            "selection": {"gp_fallback_if_real_observations_below": 2,
                          "gp_jitter": 1e-6, "residual_scale_floor": 0.05},
            "random_seed": 20261124,
        }
        result = ramp.run_method(
            q, state, "RAMP-SL-V1", 8, store, "test", {q.db_id},
            ramp.OutputPacker(CharTokenizer(), q.texts), ConstantFallback(), ConstantCalibrator(), config,
        )
        self.assertGreaterEqual(result["score_read_trace"][-1]["batch_number"], 1)
        second_round_batches = {entry["batch_number"] for entry in result["score_read_trace"] if entry["batch_number"] > 0}
        self.assertEqual(len(second_round_batches), 1)
        self.assertTrue(result["budget_contract_pass"])

    def test_gp_degeneracy_uses_fixed_training_fallback(self) -> None:
        q = make_question()
        state = ramp.build_state(q)
        mean, sigma, used_fallback, reason = ramp.posterior_or_fallback(
            state, {"c1": 0.8}, ConstantFallback(), 2, 0.05, 1e-6
        )
        self.assertTrue(used_fallback)
        self.assertEqual(reason, "insufficient_real_observations")
        self.assertTrue(np.allclose(mean, 0.4))
        self.assertTrue(np.allclose(sigma, 0.2))

    def test_postseal_full_score_reference_requires_matching_seal(self) -> None:
        q = make_question()
        store = make_fake_store(q)
        with self.assertRaises(PermissionError):
            store.reference_scores_after_seal(q, "a" * 64, {q.db_id})
        with tempfile.TemporaryDirectory() as directory:
            sealed = Path(directory) / "private_predictions_sealed.jsonl"
            sealed.write_text('{"prediction":1}\n', encoding="utf-8")
            digest = store.authorize_postseal_reference(sealed, 1)
            self.assertEqual(store.reference_scores_after_seal(q, digest, {q.db_id}), store._private_scores[q.key])

    def test_test_gold_access_requires_matching_prediction_seal(self) -> None:
        with self.assertRaises(PermissionError):
            ramp.load_gold_rows({"test_db"}, test_db_ids={"test_db"})

    def test_gold_loader_skips_uneligible_noncache_rows(self) -> None:
        rows = [
            {"db_id": "train_db", "question_id": 1, "column_eligible": True, "gold_column_ids_private": ["c1"]},
            {"db_id": "train_db", "question_id": 2, "column_eligible": False, "gold_column_ids_private": []},
        ]
        with tempfile.TemporaryDirectory() as directory:
            label_path = Path(directory) / "labels.jsonl"
            label_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with patch.object(ramp, "LABEL_PATH", label_path):
                labels, stats = ramp.load_gold_rows({"train_db"}, expected_count=1, return_stats=True)
        self.assertEqual(labels, {("train_db", 1): {"c1"}})
        self.assertEqual(stats["ineligible_label_rows"], 1)
        self.assertEqual(stats["eligible_label_rows"], 1)

    def test_static_history_regression_skips_heldout_rows_without_parsing_gold(self) -> None:
        q = make_question(db_id="train_db")
        state = ramp.build_state(q)
        candidates = ramp.budget_fill(state.cheap_order, q.costs, 6)
        scores = {cid: float(index) for index, cid in enumerate(candidates)}
        output, output_tokens = ramp.OutputPacker(CharTokenizer(), q.texts).pack(candidates, scores, 512)
        prediction = {"methods": {"Static-TopM": {
            "selected_for_scoring": candidates,
            "replay_input_tokens": sum(q.costs[cid] for cid in candidates),
            "selected_output": output,
            "output_tokens": output_tokens,
        }}}
        historical = {
            "db_id": q.db_id,
            "question_id": q.question_id,
            "static_candidate_ids": candidates,
            "static_candidate_tokens": sum(q.costs[cid] for cid in candidates),
            "static_selected_ids": output,
            "static_output_tokens": output_tokens,
            "gold_ids": ["training-only-label"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history_path = root / "prior.jsonl"
            history_path.write_text(
                '{"db_id":"heldout_db", THIS TEST GOLD ROW MUST NOT BE PARSED\n'
                + json.dumps(historical) + "\n",
                encoding="utf-8",
            )
            result = ramp.verify_static_against_history(
                [q], [prediction], root, history_path, "prior-run"
            )
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["test_database_rows_parsed"], 0)
        self.assertFalse(result["test_gold_used"])

    def test_stable_tie_breaks_and_random_order_are_reproducible(self) -> None:
        q = make_question()
        state = ramp.build_state(q)
        self.assertEqual(ramp.deterministic_random_order(state, 20261124), ramp.deterministic_random_order(state, 20261124))
        self.assertEqual(ramp.stratified_order(state), ramp.stratified_order(state))

    def test_same_packer_respects_each_registered_output_budget(self) -> None:
        q = make_question()
        packer = ramp.OutputPacker(CharTokenizer(), q.texts)
        scores = {cid: float(index) for index, cid in enumerate(q.candidate_ids)}
        for budget in (512, 1024, 2048):
            ids, used = packer.pack(q.candidate_ids, scores, budget)
            self.assertLessEqual(used, budget)
            self.assertEqual(set(ids), set(q.candidate_ids))

    def test_unbudgeted_reference_is_excluded_from_input_gate_but_keeps_output_gate(self) -> None:
        row = {"db_id": "db", "question_id": 1, "methods": {
            "FullScore-Reference-AfterSeal": {
                "selected_for_scoring": ["a", "b"], "scored_count": 2,
                "replay_input_tokens": 9000, "output_tokens": 3, "budget_B": 2048,
                "budget_feasible": False, "budget_contract_pass": False,
            }
        }}
        result = ramp.verify_prediction_rows([row], 4096, {"FullScore-Reference-AfterSeal": 2048})
        self.assertEqual(result["budget_violations"], 0)
        row["methods"]["FullScore-Reference-AfterSeal"]["output_tokens"] = 2049
        with self.assertRaises(RuntimeError):
            ramp.verify_prediction_rows([row], 4096, {"FullScore-Reference-AfterSeal": 2048})

    def test_budgeted_score_trace_must_match_recorded_token_total(self) -> None:
        row = {"db_id": "db", "question_id": 1, "methods": {
            "Static-TopM": {
                "selected_for_scoring": ["a"], "scored_count": 1,
                "replay_input_tokens": 3, "output_tokens": 0, "budget_B": 2048,
                "budget_feasible": True, "budget_contract_pass": True,
                "score_read_trace": [{"column_id_sha256": "x", "input_tokens": 2, "call_order": 0}],
            }
        }}
        with self.assertRaises(RuntimeError):
            ramp.verify_prediction_rows([row], 4096, {"Static-TopM": 2048})

    def test_calibrator_accepts_distinct_preregistered_feature_sets(self) -> None:
        rng = np.random.default_rng(7)
        y = np.asarray([0, 1] * 20, dtype=np.float64)
        rich = ramp.L2LogisticCalibrator(feature_names=ramp.FEATURE_NAMES)
        cheap = ramp.L2LogisticCalibrator(feature_names=ramp.BASE_FEATURE_NAMES)
        rich.fit(rng.normal(size=(40, len(ramp.FEATURE_NAMES))), y)
        cheap.fit(rng.normal(size=(40, len(ramp.BASE_FEATURE_NAMES))), y)
        self.assertEqual(rich.predict(np.zeros((2, len(ramp.FEATURE_NAMES)))).shape, (2,))
        self.assertEqual(cheap.predict(np.zeros((2, len(ramp.BASE_FEATURE_NAMES)))).shape, (2,))

    def test_runner_does_not_import_sql_or_steiner_execution(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        config = json.loads((ROOT / "configs/text2sql/ramp_sl_v1_active_encoding_20261124.json").read_text(encoding="utf-8"))
        self.assertFalse(config["budgets"]["sql_execution"])
        self.assertNotRegex(source, r"(?im)^\s*(?:import|from)\s+(?:sqlite3|sqlglot|networkx)")
        self.assertNotIn(".execute(", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
