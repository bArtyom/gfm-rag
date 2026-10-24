#!/usr/bin/env python3
"""Run the preregistered G2 asymmetric relation-channel identifiability gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch_geometric
from torch_geometric.data import Data


SEED = 20261023
FEATURE_DIM = 1024
NUM_NODES = 5
NUM_RELATIONS = 6
NUM_EDGES = 8
MAX_CPU_THREADS = 8
EXPECTED_PARAMETER_COUNT = 34_640_897
EXPECTED_MODEL_SHA256 = "2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d"
EXPECTED_CONFIG_SHA256 = "75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5"
TENSOR_FIELDS = (
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
MODEL_INPUT_FIELDS = ("x", "edge_index", "edge_type", "rel_attr")
INVERSE_RELATION = {0: 3, 1: 4, 2: 5, 3: 0, 4: 1, 5: 2}
RELABEL = torch.tensor([1, 0, 2, 4, 3, 5], dtype=torch.long)
G1_EDGE_INDEX = torch.tensor(
    [[0, 0, 2, 2, 1, 1, 3, 3], [1, 1, 3, 3, 0, 0, 2, 2]],
    dtype=torch.long,
)
G2_EDGE_INDEX = torch.tensor(
    [[0, 0, 2, 2, 1, 4, 3, 3], [1, 4, 3, 3, 0, 0, 2, 2]],
    dtype=torch.long,
)


@dataclass(frozen=True)
class ProbeCase:
    graph: Data
    question_embeddings: torch.Tensor
    start_nodes_mask: torch.Tensor


class ProbeForwardError(RuntimeError):
    def __init__(
        self,
        failed_case: str,
        completed_outputs: dict[str, torch.Tensor],
        forward_call_started: bool,
        cause: Exception,
    ) -> None:
        self.failed_case = failed_case
        self.completed_outputs = dict(completed_outputs)
        self.successful_output_count = len(self.completed_outputs)
        self.forward_attempted_count = self.successful_output_count + int(forward_call_started)
        self.error_type = type(cause).__name__
        self.error_message = str(cause)
        super().__init__(f"G2 case {failed_case} failed: {self.error_type}: {self.error_message}")


def _row_sha256(tensor: torch.Tensor) -> str:
    row = tensor.detach().cpu().contiguous()
    return hashlib.sha256(row.numpy().tobytes()).hexdigest()


def tensor_bundle_sha256(tensors: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in tensors.items():
        normalized = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(normalized.dtype).encode("ascii"))
        digest.update(str(tuple(normalized.shape)).encode("ascii"))
        digest.update(normalized.numpy().tobytes())
    return digest.hexdigest()


def _make_graph(edge_index: torch.Tensor) -> Data:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(SEED)
    edge_type = torch.tensor([0, 1, 2, 2, 3, 4, 5, 5], dtype=torch.long)
    instance_id = torch.tensor([0, 1, 2, 2, 0, 1, 2, 2], dtype=torch.long)
    component_index = torch.tensor([0, 0, 0, 1, 0, 0, 0, 1], dtype=torch.long)
    component_count = torch.tensor([1, 1, 2, 2, 1, 1, 2, 2], dtype=torch.long)
    is_inverse = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1], dtype=torch.long)

    edge_attr = torch.zeros((NUM_EDGES, FEATURE_DIM), dtype=torch.float32)
    edge_rows = torch.arange(NUM_EDGES)
    edge_attr[edge_rows, 0] = instance_id.float()
    edge_attr[edge_rows, 1] = component_index.float()
    edge_attr[edge_rows, 2] = component_count.float()
    edge_attr[edge_rows, 3] = is_inverse.float()
    edge_attr[edge_rows, 4 + edge_rows] = 1.0

    node_features = torch.randn((NUM_NODES, FEATURE_DIM), generator=generator)
    relation_features = torch.randn((NUM_RELATIONS, FEATURE_DIM), generator=generator)
    node_features = torch.nn.functional.normalize(node_features, p=2, dim=-1)
    relation_features = torch.nn.functional.normalize(relation_features, p=2, dim=-1)
    return Data(
        x=node_features,
        edge_index=edge_index.clone(),
        edge_type=edge_type,
        edge_attr=edge_attr,
        rel_attr=relation_features,
        num_relations=NUM_RELATIONS,
        edge_fk_instance_id=instance_id,
        edge_component_index=component_index,
        edge_component_count=component_count,
        edge_is_inverse=is_inverse,
    )


def make_fixture() -> Data:
    """Create the frozen five-node G2 graph with non-parallel role endpoints."""
    return _make_graph(G2_EDGE_INDEX)


def make_legacy_g1_fixture() -> Data:
    """Rebuild the symmetric G1 topology for the CPU identifiability control."""
    return _make_graph(G1_EDGE_INDEX)


def validate_graph_contract(graph: Data) -> dict[str, Any]:
    if graph.num_nodes != NUM_NODES or graph.num_edges != NUM_EDGES:
        raise ValueError("fixture node/edge count changed")
    if int(graph.num_relations) != NUM_RELATIONS:
        raise ValueError("fixture relation count changed")
    if tuple(graph.x.shape) != (NUM_NODES, FEATURE_DIM):
        raise ValueError("node feature shape changed")
    if tuple(graph.rel_attr.shape) != (NUM_RELATIONS, FEATURE_DIM):
        raise ValueError("relation feature shape changed")
    if tuple(graph.edge_attr.shape) != (NUM_EDGES, FEATURE_DIM):
        raise ValueError("edge feature shape changed")
    if tuple(graph.edge_index.shape) != (2, NUM_EDGES):
        raise ValueError("edge_index shape changed")
    for name in ("edge_type", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
        if tuple(getattr(graph, name).shape) != (NUM_EDGES,):
            raise ValueError(f"{name} shape changed")
    for name in ("x", "edge_attr", "rel_attr"):
        if not torch.isfinite(getattr(graph, name)).all().item():
            raise ValueError(f"{name} contains non-finite values")
    if int(graph.edge_index.min()) < 0 or int(graph.edge_index.max()) >= NUM_NODES:
        raise ValueError("edge endpoint out of range")
    if int(graph.edge_type.min()) < 0 or int(graph.edge_type.max()) >= NUM_RELATIONS:
        raise ValueError("edge relation id out of range")
    if set(graph.edge_is_inverse.tolist()) != {0, 1}:
        raise ValueError("inverse flags must contain direct and inverse edges")

    direct_rows = (graph.edge_is_inverse == 0).nonzero(as_tuple=True)[0].tolist()
    inverse_rows = (graph.edge_is_inverse == 1).nonzero(as_tuple=True)[0].tolist()
    if len(direct_rows) != 4 or len(inverse_rows) != 4:
        raise ValueError("expected four forward and four inverse edges")

    direct_roles = {
        (int(graph.edge_index[0, row]), int(graph.edge_index[1, row]), int(graph.edge_type[row]))
        for row in direct_rows
    }
    direct_endpoints = {
        (int(graph.edge_index[0, row]), int(graph.edge_index[1, row]))
        for row in direct_rows
    }
    if direct_endpoints != {(0, 1), (0, 4), (2, 3)}:
        raise ValueError("asymmetric forward role endpoints or composite FK changed")
    role_rows = [
        row
        for row in direct_rows
        if (int(graph.edge_index[0, row]), int(graph.edge_index[1, row])) in {(0, 1), (0, 4)}
    ]
    if len(role_rows) != 2 or {int(graph.edge_type[row]) for row in role_rows} != {0, 1}:
        raise ValueError("the two asymmetric role edges must use relation IDs 0 and 1")
    composite_rows = [
        row
        for row in direct_rows
        if (int(graph.edge_index[0, row]), int(graph.edge_index[1, row])) == (2, 3)
    ]
    if len(composite_rows) != 2 or {int(graph.edge_type[row]) for row in composite_rows} != {2}:
        raise ValueError("composite FK must have two components with forward relation ID 2")

    instance_ids = sorted({int(value) for value in graph.edge_fk_instance_id.tolist()})
    if len(instance_ids) != 3:
        raise ValueError("expected exactly three FK instance identities")
    direct_by_key: dict[tuple[int, int], tuple[int, int, int]] = {}
    inverse_by_key: dict[tuple[int, int], tuple[int, int, int]] = {}
    for row in range(NUM_EDGES):
        key = (int(graph.edge_fk_instance_id[row]), int(graph.edge_component_index[row]))
        count = int(graph.edge_component_count[row])
        if graph.edge_is_inverse[row].item() == 0:
            if key in direct_by_key:
                raise ValueError(f"duplicate forward component identity {key}")
            direct_by_key[key] = (
                int(graph.edge_index[0, row]),
                int(graph.edge_index[1, row]),
                int(graph.edge_type[row]),
            )
        else:
            if key in inverse_by_key:
                raise ValueError(f"duplicate inverse component identity {key}")
            inverse_by_key[key] = (
                int(graph.edge_index[0, row]),
                int(graph.edge_index[1, row]),
                int(graph.edge_type[row]),
            )
        if count not in (1, 2):
            raise ValueError(f"invalid component count for FK instance {key[0]}")

    if set(direct_by_key) != set(inverse_by_key):
        raise ValueError("forward and inverse FK component identities differ")
    for key, (source, target, relation) in direct_by_key.items():
        reverse = inverse_by_key[key]
        if reverse != (target, source, INVERSE_RELATION[relation]):
            raise ValueError(f"inverse pair mismatch for FK component {key}")

    for instance_id in instance_ids:
        forward = [key for key in direct_by_key if key[0] == instance_id]
        reverse = [key for key in inverse_by_key if key[0] == instance_id]
        expected_count = len(forward)
        if expected_count not in (1, 2) or len(reverse) != expected_count:
            raise ValueError(f"FK instance {instance_id} has incorrect component count")
        ordered_forward = [component for _, component in forward]
        ordered_inverse = [component for _, component in reverse]
        if ordered_forward != list(range(expected_count)):
            raise ValueError(f"FK instance {instance_id} component order is invalid")
        if ordered_inverse != list(range(expected_count)):
            raise ValueError(f"inverse FK instance {instance_id} component order is invalid")
        for row in range(NUM_EDGES):
            if int(graph.edge_fk_instance_id[row]) == instance_id:
                if int(graph.edge_component_count[row]) != expected_count:
                    raise ValueError(f"FK instance {instance_id} has inconsistent component counts")

    expected_metadata = torch.stack(
        (
            graph.edge_fk_instance_id.float(),
            graph.edge_component_index.float(),
            graph.edge_component_count.float(),
            graph.edge_is_inverse.float(),
        ),
        dim=1,
    )
    if not torch.equal(graph.edge_attr[:, :4], expected_metadata):
        raise ValueError("edge_attr metadata columns disagree with FK fields")
    return {
        "num_nodes": int(graph.num_nodes),
        "num_directed_edges": int(graph.num_edges),
        "num_relations": int(graph.num_relations),
        "forward_roles": sorted([list(role) for role in direct_roles]),
        "fk_instance_count": len(instance_ids),
        "composite_instance_components": [0, 1],
        "inverse_pairs_valid": True,
    }


def _case(graph: Data, query: torch.Tensor, mask: torch.Tensor) -> ProbeCase:
    validate_graph_contract(graph)
    return ProbeCase(graph=graph, question_embeddings=query.clone(), start_nodes_mask=mask.clone())


def build_probe_cases() -> dict[str, ProbeCase]:
    base = make_fixture()
    query_generator = torch.Generator(device="cpu")
    query_generator.manual_seed(SEED + 1)
    query = torch.nn.functional.normalize(
        torch.randn((1, FEATURE_DIM), generator=query_generator), p=2, dim=-1
    )
    alt_generator = torch.Generator(device="cpu")
    alt_generator.manual_seed(SEED + 2)
    alt_query = torch.nn.functional.normalize(
        torch.randn((1, FEATURE_DIM), generator=alt_generator), p=2, dim=-1
    )
    start0 = torch.tensor([[1, 0, 0, 0, 0]], dtype=torch.float32)
    start2 = torch.tensor([[0, 0, 1, 0, 0]], dtype=torch.float32)

    a0 = base.clone()
    a0_repeat = base.clone()

    a1 = base.clone()
    a1.edge_fk_instance_id = torch.tensor([10, 20, 30, 30, 10, 20, 30, 30], dtype=torch.long)
    a1.edge_attr[:, 0] = a1.edge_fk_instance_id.float()
    a1.edge_attr[:, 4:] = torch.flip(base.edge_attr[:, 4:], dims=(1,))

    a2 = base.clone()
    a2.edge_type = RELABEL[base.edge_type]

    a3 = base.clone()
    a3.rel_attr = base.rel_attr.clone()
    a3.rel_attr[0] = torch.roll(base.rel_attr[0], shifts=1, dims=0)
    a3.rel_attr[3] = torch.roll(base.rel_attr[3], shifts=1, dims=0)

    a4 = base.clone()
    a4.edge_type = RELABEL[base.edge_type]
    a4.rel_attr = base.rel_attr[RELABEL].clone()

    return {
        "A0": _case(a0, query, start0),
        "A0_repeat": _case(a0_repeat, query, start0),
        "A1": _case(a1, query, start0),
        "A2": _case(a2, query, start0),
        "A3": _case(a3, query, start0),
        "A4": _case(a4, query, start0),
        "A5": _case(base.clone(), query, start2),
        "A6": _case(base.clone(), alt_query, start0),
    }


def message_multiset_signatures(graph: Data) -> dict[int, str]:
    """Hash each target's unordered (source, source-x, relation-vector) inputs."""
    messages: dict[int, list[tuple[int, str, str]]] = {node: [] for node in range(NUM_NODES)}
    for edge in range(graph.num_edges):
        source = int(graph.edge_index[0, edge])
        target = int(graph.edge_index[1, edge])
        relation_id = int(graph.edge_type[edge])
        messages[target].append(
            (source, _row_sha256(graph.x[source]), _row_sha256(graph.rel_attr[relation_id]))
        )
    signatures = {}
    for target, items in messages.items():
        serialized = json.dumps(sorted(items), separators=(",", ":")).encode("utf-8")
        signatures[target] = hashlib.sha256(serialized).hexdigest()
    return signatures


def changed_targets(left: dict[int, str], right: dict[int, str]) -> list[int]:
    return sorted(target for target in left if left[target] != right[target])


def reachable_nodes(graph: Data, start_nodes_mask: torch.Tensor) -> list[int]:
    starts = {int(i) for i in (start_nodes_mask[0] > 0).nonzero(as_tuple=True)[0].tolist()}
    reachable = set(starts)
    frontier = list(starts)
    outgoing: dict[int, list[int]] = {node: [] for node in range(NUM_NODES)}
    for edge in range(graph.num_edges):
        source = int(graph.edge_index[0, edge])
        target = int(graph.edge_index[1, edge])
        outgoing[source].append(target)
    while frontier:
        source = frontier.pop()
        for target in outgoing[source]:
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    return sorted(reachable)


def audit_legacy_g1_symmetry() -> dict[str, Any]:
    base = make_legacy_g1_fixture()
    c2 = base.clone()
    c2.edge_type = RELABEL[base.edge_type]
    c3 = base.clone()
    c3.rel_attr = base.rel_attr[RELABEL].clone()
    original = message_multiset_signatures(base)
    c2_changed = changed_targets(original, message_multiset_signatures(c2))
    c3_changed = changed_targets(original, message_multiset_signatures(c3))
    return {
        "C2_message_multisets_unchanged": not c2_changed,
        "C3_message_multisets_unchanged": not c3_changed,
        "C2_changed_targets": c2_changed,
        "C3_changed_targets": c3_changed,
        "base_signatures": {str(k): v for k, v in original.items()},
    }


def cpu_preflight(cases: dict[str, ProbeCase] | None = None) -> dict[str, Any]:
    if torch.get_num_threads() > MAX_CPU_THREADS:
        torch.set_num_threads(MAX_CPU_THREADS)
    cases = cases or build_probe_cases()
    for case in cases.values():
        validate_graph_contract(case.graph)
        if tuple(case.question_embeddings.shape) != (1, FEATURE_DIM):
            raise ValueError("query embedding shape changed")
        if not torch.isfinite(case.question_embeddings).all().item():
            raise ValueError("query embedding contains non-finite values")
        if tuple(case.start_nodes_mask.shape) != (1, NUM_NODES):
            raise ValueError("start node mask shape changed")

    a0 = cases["A0"]
    a1, a2, a3, a4 = cases["A1"], cases["A2"], cases["A3"], cases["A4"]
    a0_signature = message_multiset_signatures(a0.graph)
    signatures = {
        name: message_multiset_signatures(case.graph)
        for name, case in cases.items()
    }
    a2_changed = changed_targets(a0_signature, signatures["A2"])
    a3_changed = changed_targets(a0_signature, signatures["A3"])
    a4_changed = changed_targets(a0_signature, signatures["A4"])
    a1_model_inputs_unchanged = all(
        torch.equal(getattr(a0.graph, name), getattr(a1.graph, name)) for name in MODEL_INPUT_FIELDS
    )
    a1_metadata_changed = (
        not torch.equal(a0.graph.edge_attr, a1.graph.edge_attr)
        and not torch.equal(a0.graph.edge_fk_instance_id, a1.graph.edge_fk_instance_id)
    )
    a3_norms_preserved = torch.allclose(
        a0.graph.rel_attr[[0, 3]].norm(dim=1),
        a3.graph.rel_attr[[0, 3]].norm(dim=1),
        atol=1e-6,
        rtol=0,
    )
    a4_edge_relation_semantics_preserved = torch.equal(
        a0.graph.rel_attr[a0.graph.edge_type], a4.graph.rel_attr[a4.graph.edge_type]
    )
    reachable = reachable_nodes(a0.graph, a0.start_nodes_mask)
    legacy = audit_legacy_g1_symmetry()
    gates = {
        "fixture_contract_valid_all_cases": True,
        "A0_repeat_input_multisets_unchanged": not changed_targets(a0_signature, signatures["A0_repeat"]),
        "A1_consumed_fields_unchanged": a1_model_inputs_unchanged,
        "A1_metadata_changed": a1_metadata_changed,
        "A2_message_multiset_changed_on_reachable_target": bool(set(a2_changed) & set(reachable)),
        "A3_message_multiset_changed_on_reachable_target": bool(set(a3_changed) & set(reachable)),
        "A3_only_frozen_rows_0_3_and_norms_preserved": a3_norms_preserved
        and changed_relation_rows(a0.graph, a3.graph) == [0, 3],
        "A4_edge_relation_semantics_preserved": a4_edge_relation_semantics_preserved,
        "A4_all_message_multisets_unchanged": not a4_changed,
        "legacy_G1_C2_message_multisets_unchanged": legacy["C2_message_multisets_unchanged"],
        "legacy_G1_C3_message_multisets_unchanged": legacy["C3_message_multisets_unchanged"],
    }
    return {
        "status": "PASS" if all(gates.values()) else "STOP-INVALID",
        "passed": all(gates.values()),
        "cpu_thread_count": torch.get_num_threads(),
        "gates": gates,
        "reachable_targets_from_anchor": reachable,
        "changed_targets": {"A2": a2_changed, "A3": a3_changed, "A4": a4_changed},
        "fixture_contract": validate_graph_contract(a0.graph),
        "fixture_tensor_bundle_sha256": tensor_bundle_sha256(
            {name: getattr(a0.graph, name) for name in TENSOR_FIELDS}
        ),
        "per_case_message_multiset_sha256": {
            name: {str(target): signature for target, signature in value.items()}
            for name, value in signatures.items()
        },
        "legacy_g1_symmetry_audit": legacy,
        "interpretation_note": "These hashes certify CPU input multiset changes only; they are not internal model-message activations or evidence of business-role understanding.",
    }


def changed_relation_rows(left: Data, right: Data) -> list[int]:
    return (left.rel_attr != right.rel_attr).any(dim=1).nonzero(as_tuple=True)[0].tolist()


def move_graph_for_forward(graph: Data, device: torch.device | str) -> tuple[Data, bool]:
    """Move one clone to the device; validate round-trip on another clone."""
    moved = graph.clone().to(device)
    roundtrip = moved.clone().cpu()
    roundtrip_ok = all(
        torch.equal(getattr(roundtrip, name), getattr(graph, name)) for name in TENSOR_FIELDS
    )
    return moved, roundtrip_ok


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_checkpoint_hashes(
    actual_model_sha256: str,
    actual_config_sha256: str,
    expected_model_sha256: str,
    expected_config_sha256: str,
) -> dict[str, Any]:
    if actual_model_sha256 != expected_model_sha256:
        raise RuntimeError("model.pth SHA-256 mismatch with the preregistered checkpoint")
    if actual_config_sha256 != expected_config_sha256:
        raise RuntimeError("config.json SHA-256 mismatch with the preregistered checkpoint")
    return {"matches": True, "model_sha256": actual_model_sha256, "config_sha256": actual_config_sha256}


def _delta(reference: torch.Tensor, candidate: torch.Tensor) -> dict[str, Any]:
    difference = (reference - candidate).abs()
    return {
        "max_abs": float(difference.max().item()),
        "mean_abs": float(difference.mean().item()),
        "top1_same": int(reference.argmax(dim=-1).item()) == int(candidate.argmax(dim=-1).item()),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    cpu_gate = cpu_preflight()
    if not cpu_gate["passed"]:
        raise RuntimeError(f"CPU preflight failed; GPU launch forbidden: {cpu_gate['gates']}")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")

    checkpoint_hashes = validate_checkpoint_hashes(
        actual_model_sha256=sha256_file(args.checkpoint / "model.pth"),
        actual_config_sha256=sha256_file(args.checkpoint / "config.json"),
        expected_model_sha256=EXPECTED_MODEL_SHA256,
        expected_config_sha256=EXPECTED_CONFIG_SHA256,
    )

    # Import the official loader only after every CPU input gate has passed.
    from gfmrag.utils.util import load_model_from_pretrained

    random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    device = torch.device(args.device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    model, config = load_model_from_pretrained(str(args.checkpoint))
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    model_config = config["model_config"]
    input_dim = int(model_config["entity_model"]["input_dim"])
    feature_dim = int(model_config["feat_dim"])
    if parameter_count != EXPECTED_PARAMETER_COUNT:
        raise RuntimeError(f"Unexpected parameter count {parameter_count} != {EXPECTED_PARAMETER_COUNT}")
    if input_dim != FEATURE_DIM or feature_dim != FEATURE_DIM:
        raise RuntimeError(f"Checkpoint dimensions are {input_dim}/{feature_dim}, expected {FEATURE_DIM}")
    model.eval().to(device)

    cases = build_probe_cases()
    outputs: dict[str, torch.Tensor] = {}
    device_roundtrip: dict[str, bool] = {}
    forward_times: dict[str, float] = {}
    with torch.inference_mode():
        for case_name, case in cases.items():
            forward_call_started = False
            try:
                graph, roundtrip_ok = move_graph_for_forward(case.graph, device)
                if not roundtrip_ok:
                    raise RuntimeError(f"Graph fields changed during device transfer for {case_name}")
                device_roundtrip[case_name] = roundtrip_ok
                batch = {
                    "question_embeddings": case.question_embeddings.to(device),
                    "start_nodes_mask": case.start_nodes_mask.to(device),
                }
                case_started = time.perf_counter()
                forward_call_started = True
                output = model(graph, batch)
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                forward_times[case_name] = round(time.perf_counter() - case_started, 6)
                if tuple(output.shape) != (1, NUM_NODES) or not torch.isfinite(output).all().item():
                    raise RuntimeError(f"Invalid model output for {case_name}: shape={tuple(output.shape)}")
                outputs[case_name] = output.detach().float().cpu()
            except Exception as exc:
                raise ProbeForwardError(
                    failed_case=case_name,
                    completed_outputs=outputs,
                    forward_call_started=forward_call_started,
                    cause=exc,
                ) from exc

    deltas = {
        name: _delta(outputs["A0"], outputs[name])
        for name in cases
        if name not in ("A0", "A0_repeat")
    }
    repeat_delta = _delta(outputs["A0"], outputs["A0_repeat"])
    epsilon = max(1e-6, 10.0 * repeat_delta["max_abs"])
    a1_ok = deltas["A1"]["max_abs"] <= epsilon
    a4_ok = deltas["A4"]["max_abs"] <= epsilon
    relation_sensitive = deltas["A2"]["max_abs"] > epsilon or deltas["A3"]["max_abs"] > epsilon
    if not a1_ok or not a4_ok:
        status = "STOP-INVALID"
    elif relation_sensitive:
        status = "G2_A_PASS"
    else:
        status = "G2_A_NO_GO"

    return {
        "experiment_id": args.run_id,
        "status": status,
        "forward_count": len(outputs),
        "training_epochs": 0,
        "external_dataset_used": False,
        "model_api_calls": 0,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "torch_geometric": torch_geometric.__version__,
        "device": torch.cuda.get_device_name(device) if device.type == "cuda" else str(device),
        "checkpoint_path": str(args.checkpoint.resolve()),
        "checkpoint_parameter_count": parameter_count,
        "checkpoint_feature_dim": feature_dim,
        "checkpoint_input_dim": input_dim,
        "checkpoint_model_sha256": checkpoint_hashes["model_sha256"],
        "checkpoint_config_sha256": checkpoint_hashes["config_sha256"],
        "checkpoint_hashes_match_preregistered": checkpoint_hashes["matches"],
        "cpu_preflight": cpu_gate,
        "device_roundtrip_passed_by_case": device_roundtrip,
        "repeat_max_abs_delta": repeat_delta["max_abs"],
        "epsilon": epsilon,
        "deltas_vs_A0": deltas,
        "outputs": {name: value.tolist() for name, value in outputs.items()},
        "forward_seconds_by_case": forward_times,
        "gate": {
            "A1_negative_control_within_epsilon": a1_ok,
            "A4_semantic_relabel_within_epsilon": a4_ok,
            "A2_or_A3_relation_channel_sensitive": relation_sensitive,
        },
        "peak_gpu_memory_allocated_bytes": torch.cuda.max_memory_allocated(device)
        if device.type == "cuda"
        else None,
        "peak_gpu_memory_reserved_bytes": torch.cuda.max_memory_reserved(device)
        if device.type == "cuda"
        else None,
        "source_runner_sha256": sha256_file(Path(__file__).resolve()),
        "elapsed_seconds_including_load_and_forwards": round(time.perf_counter() - started, 4),
        "interpretation_limit": "Synthetic non-symmetric mechanism gate only; not FK-instance role accuracy, SQL EX, or a real-schema method result.",
    }


def write_result(output: Path, result: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    with output.open("x", encoding="utf-8") as handle:
        handle.write(serialized)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--run-id", default="g2_asymmetric_relation_20261024_01")
    parser.add_argument("--cpu-preflight-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists; refusing to overwrite: {args.output}")

    try:
        if args.cpu_preflight_only:
            result = {
                "experiment_id": args.run_id,
                "phase": "CPU_PRECHECK_ONLY",
                "cpu_preflight": cpu_preflight(),
                "model_loaded": False,
                "forward_count": 0,
            }
            result["status"] = result["cpu_preflight"]["status"]
            if not result["cpu_preflight"]["passed"]:
                write_result(args.output, result)
                raise RuntimeError("CPU preflight gate failed; no GPU work was started")
        else:
            if args.checkpoint is None:
                parser.error("--checkpoint is required unless --cpu-preflight-only is set")
            result = run(args)
        write_result(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
    except ProbeForwardError as exc:
        failure = {
            "experiment_id": args.run_id,
            "status": "STOP-INVALID",
            "phase": "MODEL_FORWARD",
            "successful_output_count": exc.successful_output_count,
            "forward_attempted_count": exc.forward_attempted_count,
            "completed_cases": list(exc.completed_outputs),
            "failed_case": exc.failed_case,
            "partial_outputs": {name: value.tolist() for name, value in exc.completed_outputs.items()},
            "error_type": exc.error_type,
            "error": exc.error_message,
        }
        if not args.output.exists():
            write_result(args.output, failure)
        print(json.dumps(failure, indent=2, sort_keys=True))
        raise
    except Exception as exc:
        failure = {
            "experiment_id": args.run_id,
            "status": "STOP-INVALID",
            "phase": "CPU_PRECHECK" if args.cpu_preflight_only else "MODEL_RUN",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "forward_count": 0,
        }
        if not args.output.exists():
            write_result(args.output, failure)
        print(json.dumps(failure, indent=2, sort_keys=True))
        raise


if __name__ == "__main__":
    main()
