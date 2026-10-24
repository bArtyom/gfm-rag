#!/usr/bin/env python3
"""Bounded synthetic G0 probe for reified FK-instance node scoring.

The fixture is synthetic and contains no BIRD questions, SQL, or table rows.
It checks whether a frozen G-reasoner can emit one stable node score per
unique FK mapping when the mapping is represented as a graph node.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import resource
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch
import torch_geometric
from sentence_transformers import SentenceTransformer
from torch_geometric.data import Data


EXPERIMENT_ID = "g0_fk_instance_node_20261024_01"
SEED = 20261024
DIM = 1024
EXPECTED_PARAMETER_COUNT = 34_640_897
EXPECTED_GFM_MODEL_SHA256 = "2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d"
EXPECTED_GFM_CONFIG_SHA256 = "75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5"
EXPECTED_QWEN_MODEL_SHA256 = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
    "Query: "
)

TABLE_TEXTS = [
    "Table: orders. Columns: order_id; billing_customer_id; shipping_customer_id.",
    "Table: customers. Columns: customer_id; name.",
]
JOIN_TEXTS = {
    "billing_map": (
        "Foreign-key join mapping: source table orders; source column "
        "billing_customer_id; referenced table customers; target column customer_id."
    ),
    "shipping_map": (
        "Foreign-key join mapping: source table orders; source column "
        "shipping_customer_id; referenced table customers; target column customer_id."
    ),
}
QUERIES = [
    {"query_id": "q_billing_1", "text": "Which customer is billed for the order?", "gold": "billing_map"},
    {"query_id": "q_billing_2", "text": "Who is charged on this invoice?", "gold": "billing_map"},
    {"query_id": "q_shipping_1", "text": "Which customer receives the order shipment?", "gold": "shipping_map"},
    {"query_id": "q_shipping_2", "text": "Who is the delivery recipient for the order?", "gold": "shipping_map"},
]
DIRECT_RELATION_TEXTS = [
    JOIN_TEXTS["billing_map"],
    JOIN_TEXTS["shipping_map"],
    "Inverse foreign-key mapping: customers.customer_id is referenced by orders.billing_customer_id.",
    "Inverse foreign-key mapping: customers.customer_id is referenced by orders.shipping_customer_id.",
]
REIFIED_RELATION_TEXTS = [
    "Relation: source table participates in a join mapping.",
    "Relation: referenced target table participates in a join mapping.",
    "Inverse relation: join mapping points to its source table.",
    "Inverse relation: join mapping points to its referenced target table.",
]
NODE_IDS = ["table:orders", "table:customers", "billing_map", "shipping_map"]
FK_ID_BY_EDGE = [0, 0, 0, 0, 1, 1, 1, 1]
INVERSE_RELATION = {0: 2, 1: 3, 2: 0, 3: 1}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cpu_contract() -> dict[str, Any]:
    declarations = ["billing_map", "billing_map", "shipping_map"]
    multiplicity = {key: declarations.count(key) for key in JOIN_TEXTS}
    if multiplicity != {"billing_map": 2, "shipping_map": 1}:
        raise ValueError(f"Unexpected mapping multiplicities: {multiplicity}")
    if len(JOIN_TEXTS) != len(set(JOIN_TEXTS)):
        raise ValueError("Unique mapping IDs are not unique")

    reified_edge_index = torch.tensor(
        [[0, 1, 2, 2, 0, 1, 3, 3], [2, 2, 0, 1, 3, 3, 0, 1]],
        dtype=torch.long,
    )
    reified_edge_type = torch.tensor([0, 1, 2, 3, 0, 1, 2, 3], dtype=torch.long)
    available = {
        (int(reified_edge_index[0, row]), int(reified_edge_index[1, row]), int(relation))
        for row, relation in enumerate(reified_edge_type.tolist())
    }
    for row, relation in enumerate(reified_edge_type.tolist()):
        source = int(reified_edge_index[0, row])
        target = int(reified_edge_index[1, row])
        if (target, source, INVERSE_RELATION[relation]) not in available:
            raise ValueError(f"Missing inverse pair for edge row {row}")
    if reified_edge_index.shape != (2, 8):
        raise ValueError("Reified graph must contain eight directed edges")

    direct_edge_index = torch.tensor([[0, 0, 1, 1], [1, 1, 0, 0]], dtype=torch.long)
    direct_edge_type = torch.tensor([0, 1, 2, 3], dtype=torch.long)
    if direct_edge_index.shape != (2, 4) or direct_edge_type.unique().numel() != 4:
        raise ValueError("Direct graph must retain both FK mappings and inverses")
    return {
        "passed": True,
        "declaration_count": len(declarations),
        "unique_mapping_count": len(JOIN_TEXTS),
        "mapping_multiplicity": multiplicity,
        "reified_node_count": len(NODE_IDS),
        "reified_directed_edge_count": int(reified_edge_index.shape[1]),
        "direct_table_node_count": 2,
        "direct_directed_edge_count": int(direct_edge_index.shape[1]),
        "same_endpoint_distinct_mappings": True,
        "inverse_pairing": True,
        "composite_fk_in_this_fixture": False,
    }


def embed_texts(
    model: SentenceTransformer,
    texts: list[str],
    *,
    is_query: bool,
) -> tuple[torch.Tensor, list[int]]:
    prompt = QUERY_INSTRUCTION if is_query else ""
    vectors = model.encode(
        texts,
        prompt=prompt,
        batch_size=16,
        show_progress_bar=False,
        convert_to_tensor=True,
        normalize_embeddings=True,
    ).detach().float().cpu()
    tokenizer = model[0].tokenizer
    token_counts = []
    for text in texts:
        tokenized = tokenizer(
            prompt + text,
            add_special_tokens=True,
            truncation=True,
            max_length=model.max_seq_length,
            padding=False,
        )
        token_counts.append(len(tokenized["input_ids"]))
    if vectors.ndim != 2 or vectors.shape[1] != DIM:
        raise ValueError(f"Qwen output dimension must be {DIM}, got {tuple(vectors.shape)}")
    if not torch.isfinite(vectors).all().item():
        raise ValueError("Qwen embeddings contain NaN/Inf")
    if (vectors.norm(dim=1) <= 0).any().item():
        raise ValueError("Qwen emitted a zero vector")
    return vectors, token_counts


def build_graph(
    node_vectors: torch.Tensor,
    relation_vectors: torch.Tensor,
    *,
    reified: bool,
) -> Data:
    if reified:
        edge_index = torch.tensor(
            [[0, 1, 2, 2, 0, 1, 3, 3], [2, 2, 0, 1, 3, 3, 0, 1]],
            dtype=torch.long,
        )
        edge_type = torch.tensor([0, 1, 2, 3, 0, 1, 2, 3], dtype=torch.long)
        edge_instance_id = torch.tensor(FK_ID_BY_EDGE, dtype=torch.long)
    else:
        edge_index = torch.tensor([[0, 0, 1, 1], [1, 1, 0, 0]], dtype=torch.long)
        edge_type = torch.tensor([0, 1, 2, 3], dtype=torch.long)
        edge_instance_id = torch.tensor([0, 1, 0, 1], dtype=torch.long)
    return Data(
        x=node_vectors.contiguous(),
        edge_index=edge_index,
        edge_type=edge_type,
        rel_attr=relation_vectors.contiguous(),
        num_relations=4,
        edge_fk_instance_id=edge_instance_id,
    )


def permute_reified_graph(graph: Data) -> tuple[Data, torch.Tensor, dict[int, int]]:
    # new-index -> old-index; reverse all edge rows as a serialization control.
    new_to_old = [2, 0, 3, 1]
    old_to_new = {old: new for new, old in enumerate(new_to_old)}
    inverse = torch.tensor([old_to_new[i] for i in range(len(new_to_old))], dtype=torch.long)
    edge_rows = torch.arange(graph.edge_index.shape[1] - 1, -1, -1)
    permuted = Data(
        x=graph.x[new_to_old].clone(),
        edge_index=inverse[graph.edge_index[:, edge_rows]],
        edge_type=graph.edge_type[edge_rows].clone(),
        rel_attr=graph.rel_attr.clone(),
        num_relations=graph.num_relations,
        edge_fk_instance_id=graph.edge_fk_instance_id[edge_rows].clone(),
    )
    mask = torch.zeros((1, len(new_to_old)), dtype=torch.float32)
    mask[0, old_to_new[0]] = 1.0
    return permuted, mask, old_to_new


def move_graph(graph: Data, device: torch.device) -> Data:
    moved = graph.to(device)
    for key in ("x", "edge_index", "edge_type", "rel_attr", "edge_fk_instance_id"):
        if not torch.equal(getattr(moved, key).cpu(), getattr(graph, key).cpu()):
            raise ValueError(f"Graph field changed during device transfer: {key}")
    return moved


def run_forward(
    model: torch.nn.Module,
    graph: Data,
    query: torch.Tensor,
    start: int,
    device: torch.device,
) -> tuple[torch.Tensor, float]:
    moved = move_graph(graph, device)
    mask = torch.zeros((1, graph.num_nodes), dtype=torch.float32)
    mask[0, start] = 1.0
    batch = {"question_embeddings": query.to(device), "start_nodes_mask": mask.to(device)}
    forward_started = time.perf_counter()
    with torch.inference_mode():
        output = model(moved, batch)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    forward_seconds = time.perf_counter() - forward_started
    if output.ndim != 2 or tuple(output.shape) != (1, graph.num_nodes):
        raise ValueError(f"Unexpected output shape {tuple(output.shape)} for {graph.num_nodes} nodes")
    output = output.detach().float().cpu()
    if not torch.isfinite(output).all().item():
        raise ValueError("G-reasoner output contains NaN/Inf")
    return output, forward_seconds


def run(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    cpu_timer = time.process_time()
    cpu = cpu_contract()
    checkpoint = Path(args.checkpoint).resolve()
    embedding_path = Path(args.embedding_model).resolve()
    gfm_model_hash = sha256_file(checkpoint / "model.pth")
    gfm_config_hash = sha256_file(checkpoint / "config.json")
    if gfm_model_hash != EXPECTED_GFM_MODEL_SHA256 or gfm_config_hash != EXPECTED_GFM_CONFIG_SHA256:
        raise ValueError("G-reasoner checkpoint hash mismatch")
    if sha256_file(embedding_path / "model.safetensors") != EXPECTED_QWEN_MODEL_SHA256:
        raise ValueError("Qwen checkpoint hash mismatch")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    device = torch.device(args.device)
    if device.type == "cuda":
        torch.cuda.init()
        torch.cuda.set_device(device)
        torch.cuda.reset_peak_memory_stats(device)

    # Strict local-only load. No service/API fallback is allowed.
    embedding_load_started = time.perf_counter()
    embedder = SentenceTransformer(
        str(embedding_path),
        device=str(device),
        trust_remote_code=True,
        local_files_only=True,
    )
    embedder.eval()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    embedding_load_seconds = time.perf_counter() - embedding_load_started
    query_items = QUERIES[:1] if args.mode == "smoke" else QUERIES
    embedding_encode_started = time.perf_counter()
    query_vectors, query_token_counts = embed_texts(
        embedder, [item["text"] for item in query_items], is_query=True
    )
    passage_texts = TABLE_TEXTS + list(JOIN_TEXTS.values()) + DIRECT_RELATION_TEXTS + REIFIED_RELATION_TEXTS
    passage_vectors, passage_token_counts = embed_texts(embedder, passage_texts, is_query=False)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    embedding_encode_seconds = time.perf_counter() - embedding_encode_started

    table_vectors = passage_vectors[:2]
    join_vectors = passage_vectors[2:4]
    direct_relation_vectors = passage_vectors[4:8]
    reified_relation_vectors = passage_vectors[8:12]
    reified_graph = build_graph(
        torch.cat([table_vectors, join_vectors], dim=0),
        reified_relation_vectors,
        reified=True,
    )
    direct_graph = build_graph(table_vectors, direct_relation_vectors, reified=False)
    del embedder
    if device.type == "cuda":
        torch.cuda.empty_cache()

    dense_rows = []
    for idx, item in enumerate(query_items):
        scores = query_vectors[idx] @ join_vectors.T
        pred = "billing_map" if int(scores.argmax().item()) == 0 else "shipping_map"
        dense_rows.append(
            {
                "query_id": item["query_id"],
                "gold_mapping_id": item["gold"],
                "predicted_mapping_id": pred,
                "scores": {"billing_map": float(scores[0]), "shipping_map": float(scores[1])},
                "correct": pred == item["gold"],
            }
        )

    from gfmrag.utils.util import load_model_from_pretrained

    random.seed(SEED)
    torch.manual_seed(SEED)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(SEED)
    gfm_load_started = time.perf_counter()
    model, config = load_model_from_pretrained(str(checkpoint))
    parameter_count = sum(param.numel() for param in model.parameters())
    model_config = config["model_config"]
    if parameter_count != EXPECTED_PARAMETER_COUNT:
        raise ValueError(f"Unexpected parameter count {parameter_count}")
    if int(model_config["entity_model"]["input_dim"]) != DIM or int(model_config["feat_dim"]) != DIM:
        raise ValueError("Checkpoint feature dimension is not 1024")
    model.eval().to(device)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    gfm_load_seconds = time.perf_counter() - gfm_load_started

    model_rows = []
    base_outputs: dict[str, torch.Tensor] = {}
    forward_times = []
    for idx, item in enumerate(query_items):
        output, forward_seconds = run_forward(model, reified_graph, query_vectors[idx : idx + 1], 0, device)
        forward_times.append(forward_seconds)
        base_outputs[item["query_id"]] = output
        bill_score, ship_score = float(output[0, 2]), float(output[0, 3])
        pred = "billing_map" if bill_score >= ship_score else "shipping_map"
        model_rows.append(
            {
                "query_id": item["query_id"],
                "gold_mapping_id": item["gold"],
                "predicted_mapping_id": pred,
                "scores": {"billing_map": bill_score, "shipping_map": ship_score},
                "correct": pred == item["gold"],
                "forward_seconds": round(forward_seconds, 6),
            }
        )

    direct_output_shape = None
    direct_output_finite = None
    permutation_delta = None
    permutation_top1_same = None
    synthetic_signal = None
    status = "SMOKE_PASS"
    if args.mode == "full":
        direct_output, direct_forward_seconds = run_forward(model, direct_graph, query_vectors[:1], 0, device)
        forward_times.append(direct_forward_seconds)
        direct_output_shape = list(direct_output.shape)
        direct_output_finite = bool(torch.isfinite(direct_output).all().item())

        permuted_graph, permuted_mask, old_to_new = permute_reified_graph(reified_graph)
        moved = move_graph(permuted_graph, device)
        batch = {
            "question_embeddings": query_vectors[:1].to(device),
            "start_nodes_mask": permuted_mask.to(device),
        }
        permutation_started = time.perf_counter()
        with torch.inference_mode():
            permuted_output = model(moved, batch).detach().float().cpu()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        permutation_forward_seconds = time.perf_counter() - permutation_started
        forward_times.append(permutation_forward_seconds)
        if tuple(permuted_output.shape) != (1, 4) or not torch.isfinite(permuted_output).all().item():
            raise ValueError("Invalid output for the node/edge-order permutation case")
        restored = permuted_output[:, [old_to_new[i] for i in range(4)]]
        reference = base_outputs[query_items[0]["query_id"]]
        permutation_delta = float((reference - restored).abs().max())
        permutation_top1_same = int(reference[0].argmax()) == int(restored[0].argmax())

        bill_margin = sum(row["scores"]["billing_map"] - row["scores"]["shipping_map"] for row in model_rows[:2]) / 2
        ship_margin = sum(row["scores"]["shipping_map"] - row["scores"]["billing_map"] for row in model_rows[2:]) / 2
        model_correct = sum(row["correct"] for row in model_rows)
        dense_correct = sum(row["correct"] for row in dense_rows)
        flip_pairs = {
            "billing_queries_mean_margin_positive": bill_margin > 0,
            "shipping_queries_mean_margin_positive": ship_margin > 0,
        }
        technical_pass = (
            direct_output_shape == [1, 2]
            and direct_output_finite
            and permutation_delta <= 1e-5
            and permutation_top1_same
        )
        signal_pass = model_correct >= 3 and all(flip_pairs.values())
        synthetic_signal = {
            "gfm_top1_correct": model_correct,
            "dense_cosine_top1_correct": dense_correct,
            "billing_mean_score_margin": bill_margin,
            "shipping_mean_score_margin": ship_margin,
            "query_role_flip_pairs_passed": flip_pairs,
            "simple_fk_path_baseline": "tie on all queries: both unique mappings share the same one-hop endpoint path",
            "gfm_signal_pass": signal_pass,
            "technical_interface_and_permutation_pass": technical_pass,
            "interpretation_limit": "4 controlled synthetic query texts; no real-query or business-role claim",
        }
        status = "G0_SYNTHETIC_PASS" if technical_pass and signal_pass else "G0_SYNTHETIC_NO_GO"

    if device.type == "cuda":
        torch.cuda.synchronize(device)
        peak_gpu_bytes = int(torch.cuda.max_memory_allocated(device))
        gpu_name = torch.cuda.get_device_name(device)
    else:
        peak_gpu_bytes = None
        gpu_name = "CPU"

    result = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": status,
        "started_utc": started_at,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.perf_counter() - timer, 6),
        "seed": SEED,
        "cpu_contract": cpu,
        "gfm": {
            "official_source_repository": "https://github.com/RManLuo/gfm-rag",
            "official_source_commit": "b3e43219c49929da505244df4f0ba54c0947e4c4",
            "license": "Apache-2.0",
            "checkpoint_revision": "a3a4ed2c62281e1c3e0551bd42f2072d9204674f",
            "model_sha256": gfm_model_hash,
            "config_sha256": gfm_config_hash,
            "parameter_count": parameter_count,
            "feature_dim": DIM,
        },
        "embedding_model": {
            "model_id": "Qwen/Qwen3-Embedding-0.6B",
            "local_path": str(embedding_path),
            "model_safetensors_sha256": EXPECTED_QWEN_MODEL_SHA256,
            "config_sha256": sha256_file(embedding_path / "config.json"),
            "tokenizer_sha256": sha256_file(embedding_path / "tokenizer.json"),
            "output_dimension": DIM,
            "normalized": True,
            "query_instruction": QUERY_INSTRUCTION,
            "backend": "SentenceTransformers local PyTorch; offline-only; no vLLM server or remote API",
        },
        "local_embedding_usage": {
            "provider": "local GPU inference",
            "requests": [
                {
                    "call_id": f"{args.run_id}:qwen:queries",
                    "sequence_count": len(query_token_counts),
                    "input_tokens": sum(query_token_counts),
                },
                {
                    "call_id": f"{args.run_id}:qwen:passages",
                    "sequence_count": len(passage_token_counts),
                    "input_tokens": sum(passage_token_counts),
                },
            ],
            "input_sequences": len(query_token_counts) + len(passage_token_counts),
            "input_tokens": sum(query_token_counts) + sum(passage_token_counts),
            "query_input_tokens": sum(query_token_counts),
            "passage_input_tokens": sum(passage_token_counts),
            "output_token_count": None,
            "output_token_note": "Embedding model returns vectors, not generated text tokens.",
            "output_vectors": len(query_token_counts) + len(passage_token_counts),
            "external_api_requests": 0,
            "external_api_cost": "0 CNY",
        },
        "fixture": {
            "type": "synthetic same-endpoint FK role fixture",
            "unique_mapping_ids": ["billing_map", "shipping_map"],
            "declaration_multiplicity": {"billing_map": 2, "shipping_map": 1},
            "synthetic_query_count": len(query_items),
            "trusted_real_role_labels": 0,
        },
        "dense_cosine_baseline": dense_rows,
        "reified_gfm": model_rows,
        "direct_graph_reference": {
            "output_shape": direct_output_shape,
            "finite": direct_output_finite,
            "mapping_node_scores_available": False,
            "note": "Direct table graph has two table nodes; both FK mappings share the same endpoint nodes.",
        },
        "simple_fk_path_baseline": "tie: both unique mappings have the same one-hop endpoint path",
        "permutation_control": {
            "max_abs_score_delta_after_id_remap": permutation_delta,
            "top1_same": permutation_top1_same,
        },
        "synthetic_signal": synthetic_signal,
        "resources": {
            "device": str(device),
            "gpu_name": gpu_name,
            "peak_gpu_allocated_bytes": peak_gpu_bytes,
            "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6),
            "cpu_process_seconds": round(time.process_time() - cpu_timer, 6),
            "qwen_load_seconds": round(embedding_load_seconds, 6),
            "qwen_encode_seconds": round(embedding_encode_seconds, 6),
            "g_reasoner_load_seconds": round(gfm_load_seconds, 6),
            "g_reasoner_forward_seconds_total": round(sum(forward_times), 6),
            "g_reasoner_forward_seconds_each": [round(value, 6) for value in forward_times],
            "wall_time_limit_seconds": 1200,
            "cpu_time_limit_seconds": 300,
            "rss_limit_gib": 2,
            "model_loads_in_run": {"qwen_embedding": 1, "g_reasoner": 1},
            "forward_passes": 1 if args.mode == "smoke" else 6,
            "training_epochs": 0,
            "sql_or_database_execution": False,
            "bird_or_gold_data": False,
            "dependency_changes": 0,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
            "sentence_transformers": "5.1.1 (pre-registered environment)",
        },
        "limitations": [
            "The synthetic fixture contains only explicit billing/shipping column names.",
            "This is an engineering and synthetic signal probe, not Role Accuracy, Join Path Accuracy, SQL EX, or evidence on BIRD.",
            "The direct table-node score cannot identify an individual parallel FK mapping; this is an output-granularity limitation, not proof of model inability.",
            "No human review or trusted real-world role labels were used.",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.run_id.startswith(EXPERIMENT_ID + "_"):
        parser.error("run-id must use the preregistered experiment prefix")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite result: {args.output}")
    result = run(args)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary = args.output.with_suffix(args.output.suffix + ".partial")
    if temporary.exists():
        raise FileExistsError(f"Refusing to overwrite partial output: {temporary}")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(temporary, args.output)
    temporary.unlink()
    print(json.dumps({k: result[k] for k in ("experiment_id", "run_id", "mode", "status", "elapsed_seconds", "resources")}, ensure_ascii=False, indent=2))
    print(f"RESULT_JSON={args.output}")


if __name__ == "__main__":
    main()
