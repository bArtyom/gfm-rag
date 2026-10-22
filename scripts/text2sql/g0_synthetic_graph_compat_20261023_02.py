#!/usr/bin/env python3
"""Run one bounded synthetic compatibility gate for official G-reasoner."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from pathlib import Path

import torch
import torch_geometric
from torch_geometric.data import Data

from gfmrag.utils.util import load_model_from_pretrained


SEED = 20261023
EXPECTED_PARAMETER_COUNT = 34_640_897
FEATURE_DIM = 1024
NUM_NODES = 5
EXPECTED_EDGE_COUNT = 8
METADATA_DELTA_TOLERANCE = 1e-6


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    generator = torch.Generator(device="cpu")
    generator.manual_seed(SEED)

    # Two role-specific parallel edges over nodes 0 -> 1; a composite FK
    # consists of two ordered components over nodes 2 -> 3. Add inverse edges.
    edge_index = torch.tensor(
        [
            [0, 0, 2, 2, 1, 1, 3, 3],
            [1, 1, 3, 3, 0, 0, 2, 2],
        ],
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
    relation_features = torch.randn((6, FEATURE_DIM), generator=generator)
    node_features = torch.nn.functional.normalize(node_features, p=2, dim=-1)
    relation_features = torch.nn.functional.normalize(relation_features, p=2, dim=-1)

    graph = Data(
        x=node_features,
        edge_index=edge_index,
        edge_type=edge_type,
        edge_attr=edge_attr,
        rel_attr=relation_features,
        num_relations=6,
        edge_fk_instance_id=instance_id,
        edge_component_index=component_index,
        edge_component_count=component_count,
        edge_is_inverse=is_inverse,
    )
    return graph


def check_fixture(graph: Data) -> dict:
    assert graph.num_nodes == NUM_NODES
    assert graph.num_edges == EXPECTED_EDGE_COUNT
    assert graph.num_relations == 6
    assert graph.x.shape == (NUM_NODES, FEATURE_DIM)
    assert graph.rel_attr.shape == (6, FEATURE_DIM)
    assert graph.edge_attr.shape == (EXPECTED_EDGE_COUNT, FEATURE_DIM)

    direct = graph.edge_is_inverse == 0
    role_pairs = [
        (int(graph.edge_index[0, i]), int(graph.edge_index[1, i]), int(graph.edge_type[i]))
        for i in direct.nonzero(as_tuple=True)[0].tolist()
    ]
    assert (0, 1, 0) in role_pairs and (0, 1, 1) in role_pairs

    composite_indices = graph.edge_component_index[
        (graph.edge_fk_instance_id == 2) & direct
    ].tolist()
    assert composite_indices == [0, 1]
    composite_counts = graph.edge_component_count[
        (graph.edge_fk_instance_id == 2) & direct
    ].tolist()
    assert composite_counts == [2, 2]

    inverse = graph.edge_is_inverse == 1
    for instance_id in (0, 1, 2):
        direct_rows = (graph.edge_fk_instance_id == instance_id) & direct
        inverse_rows = (graph.edge_fk_instance_id == instance_id) & inverse
        direct_pairs = sorted(
            (
                int(graph.edge_index[0, i]),
                int(graph.edge_index[1, i]),
                int(graph.edge_type[i]) + 3,
                int(graph.edge_component_index[i]),
            )
            for i in direct_rows.nonzero(as_tuple=True)[0].tolist()
        )
        inverse_pairs = sorted(
            (
                int(graph.edge_index[1, i]),
                int(graph.edge_index[0, i]),
                int(graph.edge_type[i]),
                int(graph.edge_component_index[i]),
            )
            for i in inverse_rows.nonzero(as_tuple=True)[0].tolist()
        )
        assert direct_pairs == inverse_pairs

    return {
        "num_nodes": int(graph.num_nodes),
        "num_edges": int(graph.num_edges),
        "num_relations": int(graph.num_relations),
        "node_feature_shape": list(graph.x.shape),
        "relation_feature_shape": list(graph.rel_attr.shape),
        "edge_feature_shape": list(graph.edge_attr.shape),
        "parallel_role_edge_types": [0, 1],
        "composite_fk_direct_component_indices": composite_indices,
        "composite_fk_direct_component_counts": composite_counts,
        "inverse_edge_pairing_passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
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
        raise RuntimeError(
            f"Unexpected parameter count: {parameter_count} != {EXPECTED_PARAMETER_COUNT}"
        )
    if input_dim != FEATURE_DIM or feature_dim != FEATURE_DIM:
        raise RuntimeError(
            f"Checkpoint dimensions are {input_dim}/{feature_dim}, expected {FEATURE_DIM}"
        )

    model.eval().to(device)
    graph = make_fixture()
    fixture_summary = check_fixture(graph)
    fixture_hash = tensor_bundle_sha256(
        {
            name: getattr(graph, name)
            for name in (
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
        }
    )
    cpu_metadata = {
        name: getattr(graph, name).clone()
        for name in (
            "edge_index",
            "edge_type",
            "edge_attr",
            "edge_fk_instance_id",
            "edge_component_index",
            "edge_component_count",
            "edge_is_inverse",
        )
    }
    graph = graph.to(device)
    metadata_roundtrip = all(
        torch.equal(getattr(graph, name).cpu(), expected)
        for name, expected in cpu_metadata.items()
    )
    if not metadata_roundtrip:
        raise RuntimeError("Graph topology or FK metadata changed during device transfer")

    query_generator = torch.Generator(device="cpu")
    query_generator.manual_seed(SEED + 1)
    question_embedding = torch.nn.functional.normalize(
        torch.randn((1, FEATURE_DIM), generator=query_generator), p=2, dim=-1
    ).to(device)
    start_nodes_mask = torch.tensor([[1, 0, 0, 0, 0]], dtype=torch.float32, device=device)
    batch = {
        "question_embeddings": question_embedding,
        "start_nodes_mask": start_nodes_mask,
    }

    with torch.inference_mode():
        output = model(graph, batch)
        if device.type == "cuda":
            torch.cuda.synchronize(device)

        changed = graph.clone()
        changed.edge_attr = torch.randn_like(graph.edge_attr) * 100.0
        changed.edge_fk_instance_id = graph.edge_fk_instance_id + 100
        changed.edge_component_index = graph.edge_component_index + 7
        changed.edge_component_count = graph.edge_component_count + 9
        changed.edge_is_inverse = 1 - graph.edge_is_inverse
        altered_output = model(changed, batch)
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    expected_shape = (1, NUM_NODES)
    if tuple(output.shape) != expected_shape:
        raise RuntimeError(f"Unexpected output shape: {tuple(output.shape)}")
    if not torch.isfinite(output).all().item():
        raise RuntimeError("Model output contains NaN or Inf")
    if not torch.isfinite(altered_output).all().item():
        raise RuntimeError("Metadata-perturbed output contains NaN or Inf")

    max_abs_delta = float((output - altered_output).abs().max().item())
    metadata_ignored_exactly = torch.equal(output, altered_output)
    metadata_ignored_within_tolerance = max_abs_delta <= METADATA_DELTA_TOLERANCE
    runner_path = Path(__file__).resolve()
    result = {
        "experiment_id": "g0_synthetic_graph_compat_20261023_02",
        "status": "PASS_INTERFACE_METADATA_IGNORED"
        if metadata_ignored_within_tolerance
        else "PASS_INTERFACE_METADATA_SENSITIVE",
        "seed": SEED,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "torch_geometric": torch_geometric.__version__,
        "visible_device": torch.cuda.get_device_name(device)
        if device.type == "cuda"
        else str(device),
        "checkpoint_model_class": f"{type(model).__module__}.{type(model).__name__}",
        "checkpoint_parameter_count": parameter_count,
        "checkpoint_feature_dim": feature_dim,
        "checkpoint_input_dim": input_dim,
        "checkpoint_model_sha256": sha256_file(args.checkpoint / "model.pth"),
        "checkpoint_config_sha256": sha256_file(args.checkpoint / "config.json"),
        "fixture": fixture_summary,
        "fixture_tensor_bundle_sha256": fixture_hash,
        "metadata_roundtrip_passed": metadata_roundtrip,
        "output_shape": list(output.shape),
        "output_finite": bool(torch.isfinite(output).all().item()),
        "metadata_perturbation_max_abs_delta": max_abs_delta,
        "metadata_perturbation_exactly_equal": metadata_ignored_exactly,
        "metadata_perturbation_ignored_within_tolerance": metadata_ignored_within_tolerance,
        "metadata_delta_tolerance": METADATA_DELTA_TOLERANCE,
        "source_runner_sha256": sha256_file(runner_path),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "interpretation": (
            "Interface forward succeeded; the current checkpoint path ignores "
            "edge_attr and custom FK-instance metadata. No JOIN accuracy was measured."
            if metadata_ignored_within_tolerance
            else "Interface forward succeeded and outputs changed under metadata perturbation; "
            "inspect exact consumed fields before any role-reasoning claim."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
