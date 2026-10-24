from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/text2sql/g2_asymmetric_relation_probe.py"


def load_probe():
    assert RUNNER_PATH.is_file(), f"G2 probe not implemented: {RUNNER_PATH}"
    spec = importlib.util.spec_from_file_location("g2_asymmetric_relation_probe", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class G2ProbeContractTests(unittest.TestCase):
    def test_fixture_has_asymmetric_roles_composite_fk_and_inverse_pairs(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base = cases["A0"].graph
        self.assertEqual(base.num_nodes, 5)
        self.assertEqual(base.num_edges, 8)
        self.assertEqual(base.num_relations, 6)
        self.assertEqual(
            base.edge_index.tolist(),
            [[0, 0, 2, 2, 1, 4, 3, 3], [1, 4, 3, 3, 0, 0, 2, 2]],
        )
        self.assertEqual(base.edge_type.tolist(), [0, 1, 2, 2, 3, 4, 5, 5])
        self.assertEqual(base.edge_fk_instance_id.tolist(), [0, 1, 2, 2, 0, 1, 2, 2])
        self.assertEqual(base.edge_component_index.tolist(), [0, 0, 0, 1, 0, 0, 0, 1])
        self.assertEqual(base.edge_component_count.tolist(), [1, 1, 2, 2, 1, 1, 2, 2])
        self.assertEqual(probe.validate_graph_contract(base)["inverse_pairs_valid"], True)

    def test_a2_and_a3_change_anchor_reachable_message_multisets(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        preflight = probe.cpu_preflight(cases)
        self.assertLessEqual(preflight["cpu_thread_count"], 8)
        self.assertTrue(preflight["gates"]["A2_message_multiset_changed_on_reachable_target"])
        self.assertTrue(preflight["gates"]["A3_message_multiset_changed_on_reachable_target"])
        self.assertTrue(preflight["gates"]["A4_all_message_multisets_unchanged"])
        self.assertEqual(preflight["changed_targets"]["A2"], [0, 1, 4])
        self.assertEqual(preflight["changed_targets"]["A3"], [0, 1])

    def test_legacy_symmetric_g1_relation_swaps_keep_message_multisets(self):
        probe = load_probe()
        audit = probe.audit_legacy_g1_symmetry()
        self.assertTrue(audit["C2_message_multisets_unchanged"])
        self.assertTrue(audit["C3_message_multisets_unchanged"])

    def test_a1_changes_only_unconsumed_metadata(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base = cases["A0"].graph
        negative = cases["A1"].graph
        for name in ("x", "edge_index", "edge_type", "rel_attr"):
            self.assertTrue(torch.equal(getattr(base, name), getattr(negative, name)), name)
        self.assertFalse(torch.equal(base.edge_attr, negative.edge_attr))
        self.assertFalse(torch.equal(base.edge_fk_instance_id, negative.edge_fk_instance_id))

    def test_a2_changes_only_inverse_paired_edge_types(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, changed = cases["A0"].graph, cases["A2"].graph
        for name in ("x", "edge_index", "edge_attr", "rel_attr", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
            self.assertTrue(torch.equal(getattr(base, name), getattr(changed, name)), name)
        self.assertEqual(changed.edge_type.tolist(), [1, 0, 2, 2, 4, 3, 5, 5])
        self.assertTrue(torch.equal(base.rel_attr, changed.rel_attr))

    def test_a3_changes_only_two_relation_rows_and_preserves_their_norms(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, changed = cases["A0"].graph, cases["A3"].graph
        for name in ("x", "edge_index", "edge_type", "edge_attr", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
            self.assertTrue(torch.equal(getattr(base, name), getattr(changed, name)), name)
        changed_rows = (base.rel_attr != changed.rel_attr).any(dim=1).nonzero(as_tuple=True)[0].tolist()
        self.assertEqual(changed_rows, [0, 3])
        self.assertTrue(torch.allclose(base.rel_attr[[0, 3]].norm(dim=1), changed.rel_attr[[0, 3]].norm(dim=1), atol=1e-6, rtol=0))

    def test_a4_keeps_every_edge_relation_feature_pair_identical(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, relabeled = cases["A0"].graph, cases["A4"].graph
        self.assertTrue(torch.equal(base.rel_attr[base.edge_type], relabeled.rel_attr[relabeled.edge_type]))
        self.assertTrue(probe.cpu_preflight(cases)["gates"]["A4_all_message_multisets_unchanged"])

    def test_device_roundtrip_uses_a_clone_and_keeps_forward_graph_on_device(self):
        probe = load_probe()
        source = probe.build_probe_cases()["A0"].graph

        class DeviceTrackingGraph:
            def __init__(self, wrapped, device="cpu"):
                self.wrapped = wrapped
                self.device = device

            def __getattr__(self, name):
                return getattr(self.wrapped, name)

            def clone(self):
                return DeviceTrackingGraph(self.wrapped.clone(), self.device)

            def to(self, device):
                self.device = str(device)
                return self

            def cpu(self):
                self.device = "cpu"
                return self

        wrapped = DeviceTrackingGraph(source)
        forward_graph, roundtrip_ok = probe.move_graph_for_forward(wrapped, "cuda:0")
        self.assertTrue(roundtrip_ok)
        self.assertEqual(forward_graph.device, "cuda:0")
        self.assertEqual(wrapped.device, "cpu")

    def test_probe_preflight_rejects_a_broken_composite_instance(self):
        probe = load_probe()
        graph = probe.build_probe_cases()["A0"].graph.clone()
        graph.edge_component_index[2], graph.edge_component_index[3] = 1, 0
        graph.edge_attr[2, 1], graph.edge_attr[3, 1] = 1.0, 0.0
        with self.assertRaisesRegex(ValueError, "component order"):
            probe.validate_graph_contract(graph)

    def test_result_writer_refuses_to_overwrite_an_existing_receipt(self):
        probe = load_probe()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            probe.write_result(output, {"status": "first"})
            with self.assertRaises(FileExistsError):
                probe.write_result(output, {"status": "second"})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"status": "first"})

    def test_forward_failure_record_keeps_completed_and_attempted_counts(self):
        probe = load_probe()
        completed = {"A0": torch.tensor([[0.1, 0.2]])}
        failure = probe.ProbeForwardError(
            failed_case="A0_repeat",
            completed_outputs=completed,
            forward_call_started=True,
            cause=RuntimeError("simulated forward failure"),
        )
        self.assertEqual(failure.failed_case, "A0_repeat")
        self.assertEqual(failure.successful_output_count, 1)
        self.assertEqual(failure.forward_attempted_count, 2)
        self.assertEqual(failure.error_type, "RuntimeError")

    def test_checkpoint_hash_guard_accepts_frozen_values_and_rejects_drift(self):
        probe = load_probe()
        expected = probe.validate_checkpoint_hashes(
            actual_model_sha256="model-sha",
            actual_config_sha256="config-sha",
            expected_model_sha256="model-sha",
            expected_config_sha256="config-sha",
        )
        self.assertTrue(expected["matches"])
        with self.assertRaisesRegex(RuntimeError, "model.pth SHA-256 mismatch"):
            probe.validate_checkpoint_hashes(
                actual_model_sha256="changed-model-sha",
                actual_config_sha256="config-sha",
                expected_model_sha256="model-sha",
                expected_config_sha256="config-sha",
            )


if __name__ == "__main__":
    unittest.main()
