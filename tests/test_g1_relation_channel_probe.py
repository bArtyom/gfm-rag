from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/text2sql/g1_relation_channel_probe.py"


def load_probe():
    assert RUNNER_PATH.is_file(), f"G1 probe not implemented: {RUNNER_PATH}"
    spec = importlib.util.spec_from_file_location("g1_relation_channel_probe", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def graph_fields(graph):
    return (
        "x",
        "edge_index",
        "edge_type",
        "edge_attr",
        "rel_attr",
        "edge_fk_instance_id",
        "edge_component_index",
        "edge_component_count",
        "edge_is_inverse",
    )


class G1ProbeContractTests(unittest.TestCase):
    def test_fixture_is_byte_identical_to_pinned_g0_fixture(self):
        probe = load_probe()
        graph = probe.build_probe_cases()["C0"].graph
        bundle = {name: getattr(graph, name) for name in graph_fields(graph)}
        self.assertEqual(
            probe.tensor_bundle_sha256(bundle),
            "0ffaa88fbe41a4026bbc8b7263cbbdee1b432c9651a6bc3824a705890bd593f2",
        )
        self.assertEqual(graph.edge_type.tolist(), [0, 1, 2, 2, 3, 4, 5, 5])
        self.assertEqual(
            graph.edge_index.tolist(),
            [[0, 0, 2, 2, 1, 1, 3, 3], [1, 1, 3, 3, 0, 0, 2, 2]],
        )

    def test_tensor_fields_survive_graph_copy_and_cpu_device_roundtrip(self):
        probe = load_probe()
        graph = probe.build_probe_cases()["C0"].graph
        copied = graph.clone().to("cpu")
        for name in graph_fields(graph):
            self.assertTrue(torch.equal(getattr(graph, name), getattr(copied, name)), name)

    def test_all_conditions_preserve_parallel_roles_composite_fk_and_inverse_pairs(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        self.assertEqual(set(cases), {"C0", "C0_repeat", "C1", "C2", "C3", "C4", "C5", "C6"})
        for case in cases.values():
            probe.validate_graph_contract(case.graph)
        self.assertEqual(cases["C2"].graph.edge_type.tolist(), [1, 0, 2, 2, 4, 3, 5, 5])
        self.assertEqual(cases["C0"].graph.edge_fk_instance_id.tolist(), [0, 1, 2, 2, 0, 1, 2, 2])
        self.assertEqual(cases["C0"].graph.edge_component_index.tolist(), [0, 0, 0, 1, 0, 0, 0, 1])
        self.assertEqual(cases["C0"].graph.edge_component_count.tolist(), [1, 1, 2, 2, 1, 1, 2, 2])

    def test_negative_control_changes_only_unused_fields_and_keeps_instance_relabel_bijective(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, negative = cases["C0"], cases["C1"]
        for name in ("x", "edge_index", "edge_type", "rel_attr", "edge_component_index", "edge_component_count", "edge_is_inverse"):
            self.assertTrue(torch.equal(getattr(base.graph, name), getattr(negative.graph, name)), name)
        self.assertFalse(torch.equal(base.graph.edge_attr, negative.graph.edge_attr))
        self.assertEqual(negative.graph.edge_fk_instance_id.tolist(), [10, 20, 30, 30, 10, 20, 30, 30])
        probe.validate_graph_contract(negative.graph)

    def test_relation_type_and_feature_perturbations_are_isolated_and_inverse_paired(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, edge_type_case, feature_case = cases["C0"], cases["C2"], cases["C3"]
        for name in ("x", "edge_index", "edge_attr", "rel_attr", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
            self.assertTrue(torch.equal(getattr(base.graph, name), getattr(edge_type_case.graph, name)), name)
        self.assertFalse(torch.equal(base.graph.edge_type, edge_type_case.graph.edge_type))
        for name in ("x", "edge_index", "edge_type", "edge_attr", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
            self.assertTrue(torch.equal(getattr(base.graph, name), getattr(feature_case.graph, name)), name)
        self.assertTrue(torch.equal(base.graph.rel_attr[[1, 0, 2, 4, 3, 5]], feature_case.graph.rel_attr))

    def test_consistent_relation_id_relabel_preserves_edge_to_feature_semantics(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, relabeled = cases["C0"].graph, cases["C4"].graph
        self.assertTrue(torch.equal(base.rel_attr[base.edge_type], relabeled.rel_attr[relabeled.edge_type]))
        self.assertEqual(relabeled.edge_type.tolist(), [1, 0, 2, 2, 4, 3, 5, 5])
        probe.validate_graph_contract(relabeled)

    def test_anchor_and_query_conditions_change_only_the_declared_input(self):
        probe = load_probe()
        cases = probe.build_probe_cases()
        base, anchor, query = cases["C0"], cases["C5"], cases["C6"]
        self.assertEqual(anchor.start_nodes_mask.tolist(), [[0.0, 0.0, 1.0, 0.0, 0.0]])
        self.assertTrue(torch.equal(base.question_embeddings, anchor.question_embeddings))
        self.assertTrue(all(torch.equal(getattr(base.graph, name), getattr(anchor.graph, name)) for name in graph_fields(base.graph)))
        self.assertTrue(torch.equal(base.start_nodes_mask, query.start_nodes_mask))
        self.assertTrue(all(torch.equal(getattr(base.graph, name), getattr(query.graph, name)) for name in graph_fields(base.graph)))
        self.assertFalse(torch.equal(base.question_embeddings, query.question_embeddings))
        self.assertTrue(torch.isclose(query.question_embeddings.norm(dim=-1), torch.ones(1), atol=1e-6).all())

    def test_validator_rejects_broken_composite_component_order(self):
        probe = load_probe()
        graph = probe.build_probe_cases()["C0"].graph.clone()
        graph.edge_component_index[2], graph.edge_component_index[3] = 1, 0
        with self.assertRaisesRegex(ValueError, "composite FK component order"):
            probe.validate_graph_contract(graph)


if __name__ == "__main__":
    unittest.main()
