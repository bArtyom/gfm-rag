#!/usr/bin/env python3
"""Run the preregistered, bounded synthetic G1 relation-channel gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from dataclasses import dataclass
from pathlib import Path

import torch
import torch_geometric
from torch_geometric.data import Data

from gfmrag.utils.util import load_model_from_pretrained


SEED = 20261023
EXPECTED_PARAMETER_COUNT = 34_640_897
FEATURE_DIM = 1024
NUM_NODES = 5
NUM_RELATIONS = 6
EXPECTED_EDGE_COUNT = 8
G0_FIXTURE_SHA256 = "0ffaa88fbe41a4026bbc8b7263cbbdee1b432c9651a6bc3824a705890bd593f2"
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
INVERSE_RELATION = {0: 3, 1: 4, 2: 5, 3: 0, 4: 1, 5: 2}
RELABEL = torch.tensor([1, 0, 2, 4, 3, 5], dtype=torch.long)


@dataclass(frozen=True)
class ProbeCase:
    graph: Data
    question_embeddings: torch.Tensor
    start_nodes_mask: torch.Tensor


def tensor_bundle_sha256(tensors: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in tensors.items():
        normalized = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(normalized.dtype).encode("ascii"))
        digest.update(str(tuple(normalized.shape)).encode("ascii"))
        digest.update(normalized.numpy().tobytes())
    return digest.hexdigest()


def make_fixture() -> Data:
    """Byte-identical G0 fixture, copied from pinned G0 commit 7152ab2."""
    generator = torch.Generator(device="cpu")
    generator.manual_seed(SEED)
    edge_index = torch.tensor(
        [[0, 0, 2, 2, 1, 1, 3, 3], [1, 1, 3, 3, 0, 0, 2, 2]],
        dtype=torch.long,
    )
    edge_type = torch.tensor([0, 1, 2, 2, 3, 4, 5, 5], dtype=torch.long)
    instance_id = torch.tensor([0, 1, 2, 2, 0, 1, 2, 2], dtype=torch.long)
    component_index = torch.tensor([0, 0, 0, 1, 0, 0, 0, 1], dtype=torch.long)
    component_count = torch.tensor([1, 1, 2, 2, 1, 1, 2, 2], dtype=torch.long)
    is_inverse = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1], dtype=torch.long)

    edge_attr = torch.zeros((EXPECTED_EDGE_COUNT, FEATURE_DIM), dtype=torch.float32)
    edge_rows = torch.arange(EXPECTED_EDGE_COUNT)
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
        edge_index=edge_index,
        edge_type=edge_type,
        edge_attr=edge_attr,
        rel_attr=relation_features,
        num_relations=NUM_RELATIONS,
        edge_fk_instance_id=instance_id,
        edge_component_index=component_index,
        edge_component_count=component_count,
        edge_is_inverse=is_inverse,
    )


def validate_graph_contract(graph: Data) -> dict:
    """Validate this fixture's directed FK and inverse-edge structure."""
    if graph.num_nodes != NUM_NODES or graph.num_edges != EXPECTED_EDGE_COUNT:
        raise ValueError("fixture node/edge count changed")
    if int(graph.num_relations) != NUM_RELATIONS:
        raise ValueError("fixture relation count changed")
    if tuple(graph.x.shape) != (NUM_NODES, FEATURE_DIM):
        raise ValueError("node feature shape changed")
    if tuple(graph.rel_attr.shape) != (NUM_RELATIONS, FEATURE_DIM):
        raise ValueError("relation feature shape changed")
    if tuple(graph.edge_attr.shape) != (EXPECTED_EDGE_COUNT, FEATURE_DIM):
        raise ValueError("edge feature shape changed")
    for name in ("edge_type", "edge_fk_instance_id", "edge_component_index", "edge_component_count", "edge_is_inverse"):
        if tuple(getattr(graph, name).shape) != (EXPECTED_EDGE_COUNT,):
            raise ValueError(f"{name} shape changed")
    if graph.edge_index.shape != (2, EXPECTED_EDGE_COUNT):
        raise ValueError("edge_index shape changed")
    if int(graph.edge_index.min()) < 0 or int(graph.edge_index.max()) >= NUM_NODES:
        raise ValueError("edge endpoint out of range")
    if int(graph.edge_type.min()) < 0 or int(graph.edge_type.max()) >= NUM_RELATIONS:
        raise ValueError("edge relation id out of range")
    if set(graph.edge_is_inverse.tolist()) != {0, 1}:
        raise ValueError("inverse flags must contain direct and inverse edges")

    direct = graph.edge_is_inverse == 0
    inverse = graph.edge_is_inverse == 1
    direct_rows = direct.nonzero(as_tuple=True)[0].tolist()
    inverse_rows = inverse.nonzero(as_tuple=True)[0].tolist()
    direct_roles = {
        (int(graph.edge_index[0, i]), int(graph.edge_index[1, i]), int(graph.edge_type[i]))
        for i in direct_rows
    }
    if (0, 1, 0) not in direct_roles or (0, 1, 1) not in direct_roles:
        raise ValueError("parallel FK roles were merged or endpoints changed")

    instance_ids = sorted(set(int(value) for value in graph.edge_fk_instance_id.tolist()))
    if len(instance_ids) != 3:
        raise ValueError("expected two parallel FK instances and one composite instance")
    for instance_id in instance_ids:
        direct_instance_rows = [i for i in direct_rows if int(graph.edge_fk_instance_id[i]) == instance_id]
        inverse_instance_rows = [i for i in inverse_rows if int(graph.edge_fk_instance_id[i]) == instance_id]
        if not direct_instance_rows or len(direct_instance_rows) != len(inverse_instance_rows):
            raise ValueError(f"FK instance {instance_id} is missing its inverse edges")
        counts = {int(graph.edge_component_count[i]) for i in direct_instance_rows + inverse_instance_rows}
        if len(counts) != 1:
            raise ValueError(f"FK instance {instance_id} has inconsistent component counts")
        component_count = counts.pop()
        if component_count != len(direct_instance_rows):
            raise ValueError(f"FK instance {instance_id} component count mismatch")
        ordered_components = [int(graph.edge_component_index[i]) for i in direct_instance_rows]
        if ordered_components != list(range(component_count)):
            raise ValueError(
                f"composite FK component order invalid for instance {instance_id}: {ordered_components}"
            )
        if sorted(int(graph.edge_component_index[i]) for i in inverse_instance_rows) != list(range(component_count)):
            raise ValueError(f"inverse FK component order invalid for instance {instance_id}")

        direct_pairs = sorted(
            (
                int(graph.edge_index[0, i]),
                int(graph.edge_index[1, i]),
                INVERSE_RELATION[int(graph.edge_type[i])],
                int(graph.edge_component_index[i]),
            )
            for i in direct_instance_rows
        )
        inverse_pairs = sorted(
            (
                int(graph.edge_index[1, i]),
                int(graph.edge_index[0, i]),
                int(graph.edge_type[i]),
                int(graph.edge_component_index[i]),
            )
            for i in inverse_instance_rows
        )
        if direct_pairs != inverse_pairs:
            raise ValueError(f"FK instance {instance_id} inverse pairing mismatch")

    # The first four edge_attr columns encode the corresponding metadata.
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
        "num_edges": int(graph.num_edges),
        "num_relations": int(graph.num_relations),
        "parallel_direct_roles": sorted([list(role) for role in direct_roles if role[:2] == (0, 1)]),
        "fk_instance_count": len(instance_ids),
        "composite_component_order": "0,1",
        "inverse_pairs_valid": True,
    }


def _case(graph: Data, query: torch.Tensor, mask: torch.Tensor) -> ProbeCase:
    validate_graph_contract(graph)
    return ProbeCase(graph=graph, question_embeddings=query.clone(), start_nodes_mask=mask.clone())


def build_probe_cases() -> dict[str, ProbeCase]:
    base = make_fixture()
    if tensor_bundle_sha256({name: getattr(base, name) for name in TENSOR_FIELDS}) != G0_FIXTURE_SHA256:
        raise RuntimeError("G1 fixture no longer matches pinned G0 fixture SHA256")
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
    node0 = torch.tensor([[1, 0, 0, 0, 0]], dtype=torch.float32)
    node2 = torch.tensor([[0, 0, 1, 0, 0]], dtype=torch.float32)

    c0 = base.clone()
    c0_repeat = base.clone()

    c1 = base.clone()
    instance_relabel = {0: 10, 1: 20, 2: 30}
    c1.edge_fk_instance_id = torch.tensor(
        [instance_relabel[int(value)] for value in base.edge_fk_instance_id.tolist()], dtype=torch.long
    )
    c1.edge_attr[:, 0] = c1.edge_fk_instance_id.float()
    c1.edge_attr[:, 4:] = torch.flip(base.edge_attr[:, 4:], dims=(1,))

    c2 = base.clone()
    c2.edge_type = RELABEL[base.edge_type]

    c3 = base.clone()
    c3.rel_attr = base.rel_attr[RELABEL].clone()

    c4 = base.clone()
    c4.edge_type = RELABEL[base.edge_type]
    c4.rel_attr = base.rel_attr[RELABEL].clone()

    return {
        "C0": _case(c0, query, node0),
        "C0_repeat": _case(c0_repeat, query, node0),
        "C1": _case(c1, query, node0),
        "C2": _case(c2, query, node0),
        "C3": _case(c3, query, node0),
        "C4": _case(c4, query, node0),
        "C5": _case(base.clone(), query, node2),
        "C6": _case(base.clone(), alt_query, node0),
    }


def move_graph_for_forward(graph: Data, device: torch.device | str) -> tuple[Data, bool]:
    """Move a copy for inference and validate on a second copy.

    PyG ``Data.to`` and ``Data.cpu`` mutate the receiving Data object through
    ``apply``. Keeping the round-trip on a clone prevents validation from
    moving the model input back to CPU.
    """
    moved = graph.clone().to(device)
    roundtrip = moved.clone().cpu()
    roundtrip_ok = all(
        torch.equal(getattr(roundtrip, name), getattr(graph, name))
        for name in TENSOR_FIELDS
    )
    return moved, roundtrip_ok


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _delta(reference: torch.Tensor, candidate: torch.Tensor) -> dict:
    difference = (reference - candidate).abs()
    return {
        "max_abs": float(difference.max().item()),
        "mean_abs": float(difference.mean().item()),
        "top1_same": int(reference.argmax(dim=-1).item()) == int(candidate.argmax(dim=-1).item()),
    }


def run(args: argparse.Namespace) -> dict:
    started = time.perf_counter()
    random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    device = torch.device(args.device)

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
    fixture_hash = tensor_bundle_sha256({name: getattr(cases["C0"].graph, name) for name in TENSOR_FIELDS})
    outputs: dict[str, torch.Tensor] = {}
    device_roundtrip: dict[str, bool] = {}
    with torch.inference_mode():
        for case_name, case in cases.items():
            graph, roundtrip_ok = move_graph_for_forward(case.graph, device)
            if not roundtrip_ok:
                raise RuntimeError(f"Graph tensor fields changed during device transfer for {case_name}")
            device_roundtrip[case_name] = roundtrip_ok
            batch = {
                "question_embeddings": case.question_embeddings.to(device),
                "start_nodes_mask": case.start_nodes_mask.to(device),
            }
            output = model(graph, batch)
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            if tuple(output.shape) != (1, NUM_NODES) or not torch.isfinite(output).all().item():
                raise RuntimeError(f"Invalid model output for {case_name}: shape={tuple(output.shape)}")
            outputs[case_name] = output.detach().float().cpu()

    deltas = {name: _delta(outputs["C0"], outputs[name]) for name in cases if name not in ("C0", "C0_repeat")}
    repeat_delta = _delta(outputs["C0"], outputs["C0_repeat"])
    epsilon = max(1e-6, 10.0 * repeat_delta["max_abs"])
    c1_ok = deltas["C1"]["max_abs"] <= epsilon
    c4_ok = deltas["C4"]["max_abs"] <= epsilon
    relation_sensitive = deltas["C2"]["max_abs"] > epsilon or deltas["C3"]["max_abs"] > epsilon
    if not c4_ok:
        status = "STOP_C4_INVARIANCE_FAIL"
    elif c1_ok and relation_sensitive:
        status = "G1_A_PASS"
    elif c1_ok:
        status = "G1_A_NO_GO_NO_RELATION_CHANNEL_SENSITIVITY"
    else:
        status = "G1_A_INVALID_C1_NEGATIVE_CONTROL"

    return {
        "experiment_id": args.run_id,
        "status": status,
        "seed": SEED,
        "forward_count": len(cases),
        "training_epochs": 0,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "torch_geometric": torch_geometric.__version__,
        "device": torch.cuda.get_device_name(device) if device.type == "cuda" else str(device),
        "checkpoint_path": str(args.checkpoint.resolve()),
        "checkpoint_parameter_count": parameter_count,
        "checkpoint_feature_dim": feature_dim,
        "checkpoint_input_dim": input_dim,
        "checkpoint_model_sha256": sha256_file(args.checkpoint / "model.pth"),
        "checkpoint_config_sha256": sha256_file(args.checkpoint / "config.json"),
        "fixture": validate_graph_contract(cases["C0"].graph),
        "fixture_tensor_bundle_sha256": fixture_hash,
        "g0_fixture_sha256_match": fixture_hash == G0_FIXTURE_SHA256,
        "device_roundtrip_passed_by_case": device_roundtrip,
        "c0_repeat_max_abs_delta": repeat_delta["max_abs"],
        "epsilon": epsilon,
        "deltas_vs_c0": deltas,
        "outputs": {name: value.tolist() for name, value in outputs.items()},
        "gate": {
            "c1_negative_control_within_epsilon": c1_ok,
            "c4_consistent_relabel_within_epsilon": c4_ok,
            "c2_or_c3_relation_channel_sensitive": relation_sensitive,
            "c5_anchor_sensitive": deltas["C5"]["max_abs"] > epsilon,
            "c6_query_sensitive": deltas["C6"]["max_abs"] > epsilon,
        },
        "source_runner_sha256": sha256_file(Path(__file__).resolve()),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "interpretation_limit": "Synthetic mechanism fingerprint only; no SQL accuracy, role accuracy, training, or real-schema quality was measured.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--run-id", default="g1_relation_channel_20261023_01")
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
