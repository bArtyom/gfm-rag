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

EXPERIMENT_ID = "g0_fk_instance_node_20261024_01"
SEED = 20261024
DIM = 1024
EXPECTED_PARAMETER_COUNT = 34_640_897
EXPECTED_GFM_MODEL_SHA256 = (
    "2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d"
)
EXPECTED_GFM_CONFIG_SHA256 = (
    "75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5"
)
EXPECTED_QWEN_MODEL_SHA256 = (
    "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
)
EXPECTED_QWEN_CONFIG_SHA256 = (
    "b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9"
)
EXPECTED_QWEN_TOKENIZER_SHA256 = (
    "def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a"
)
EXPECTED_QWEN_MODULES_SHA256 = (
    "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf"
)
EXPECTED_QWEN_ST_CONFIG_SHA256 = (
    "10667c72ddb772627bf1780cb7f86af8e2ae0032b8c243c731172064105c6961"
)
EXPECTED_QWEN_TOKENIZER_CONFIG_SHA256 = (
    "253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0"
)
EXPECTED_QWEN_POOLING_CONFIG_SHA256 = (
    "37bf193fa101f19101bfad9c31d3eb0f786e247b7b1e5cb7f007d730eed1ddbd"
)
RSS_LIMIT_GIB = 8
WALL_LIMIT_SECONDS = 1200
CPU_LIMIT_SECONDS = 300
QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
    "Query: "
)

TABLE_TEXTS = [
    "Table: orders. Columns: order_id; billing_customer_id; shipping_customer_id.",
    "Table: customers. Columns: customer_id; name.",
]
JOIN_DECLARATIONS = [
    {
        "display_name": "billing_map",
        "identity": ("orders", "billing_customer_id", "customers", "customer_id"),
    },
    {
        "display_name": "billing_map",
        "identity": ("orders", "billing_customer_id", "customers", "customer_id"),
    },
    {
        "display_name": "shipping_map",
        "identity": ("orders", "shipping_customer_id", "customers", "customer_id"),
    },
]


def stable_mapping_id(identity: tuple[str, str, str, str]) -> str:
    canonical = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return f"fk_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def derive_join_mappings(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for declaration in declarations:
        identity = tuple(declaration["identity"])
        if len(identity) != 4 or not all(
            isinstance(value, str) and value for value in identity
        ):
            raise ValueError(f"Invalid ordered Join identity: {identity}")
        mapping_id = stable_mapping_id(identity)
        record = grouped.setdefault(
            identity,
            {
                "mapping_id": mapping_id,
                "identity": identity,
                "display_name": declaration["display_name"],
                "multiplicity": 0,
            },
        )
        if record["display_name"] != declaration["display_name"]:
            raise ValueError(
                f"Conflicting display names for the same mapping identity: {identity}"
            )
        record["multiplicity"] += 1
    records = sorted(grouped.values(), key=lambda record: record["display_name"])
    ids = [record["mapping_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Stable mapping ID hash collision")
    return records


JOIN_MAPPINGS = derive_join_mappings(JOIN_DECLARATIONS)
MAPPING_BY_ALIAS = {record["display_name"]: record for record in JOIN_MAPPINGS}
MAPPING_ID_BY_ALIAS = {
    alias: record["mapping_id"] for alias, record in MAPPING_BY_ALIAS.items()
}


def mapping_text(record: dict[str, Any]) -> str:
    source_table, source_column, target_table, target_column = record["identity"]
    return (
        f"Foreign-key join mapping: source table {source_table}; source column "
        f"{source_column}; referenced table {target_table}; target column {target_column}."
    )


JOIN_TEXTS = {record["display_name"]: mapping_text(record) for record in JOIN_MAPPINGS}
QUERIES = [
    {
        "query_id": "q_billing_1",
        "text": "Which customer is billed for the order?",
        "gold": "billing_map",
    },
    {
        "query_id": "q_billing_2",
        "text": "Who is charged on this invoice?",
        "gold": "billing_map",
    },
    {
        "query_id": "q_shipping_1",
        "text": "Which customer receives the order shipment?",
        "gold": "shipping_map",
    },
    {
        "query_id": "q_shipping_2",
        "text": "Who is the delivery recipient for the order?",
        "gold": "shipping_map",
    },
]
DIRECT_RELATION_TEXTS = [
    *(mapping_text(record) for record in JOIN_MAPPINGS),
    *(
        "Inverse foreign-key mapping: "
        f"{record['identity'][2]}.{record['identity'][3]} is referenced by "
        f"{record['identity'][0]}.{record['identity'][1]}."
        for record in JOIN_MAPPINGS
    ),
]
REIFIED_RELATION_TEXTS = [
    "Relation: source table participates in a join mapping.",
    "Relation: referenced target table participates in a join mapping.",
    "Inverse relation: join mapping points to its source table.",
    "Inverse relation: join mapping points to its referenced target table.",
]
TABLE_NODE_IDS = ["table:orders", "table:customers"]
NODE_IDS = TABLE_NODE_IDS + [record["mapping_id"] for record in JOIN_MAPPINGS]
MAPPING_NODE_INDICES = [
    NODE_IDS.index(record["mapping_id"]) for record in JOIN_MAPPINGS
]
INVERSE_RELATION = {0: 2, 1: 3, 2: 0, 3: 1}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_runtime_budget(started: float, cpu_started: float) -> None:
    wall_seconds = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_started
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)
    if wall_seconds > WALL_LIMIT_SECONDS:
        raise TimeoutError(f"Wall time exceeded {WALL_LIMIT_SECONDS}s")
    if cpu_seconds > CPU_LIMIT_SECONDS:
        raise TimeoutError(f"CPU process time exceeded {CPU_LIMIT_SECONDS}s")
    if rss_gib > RSS_LIMIT_GIB:
        raise MemoryError(f"Peak RSS exceeded {RSS_LIMIT_GIB} GiB: {rss_gib:.3f} GiB")


def validate_qwen_snapshot(path: Path) -> dict[str, str]:
    expected = {
        "model.safetensors": EXPECTED_QWEN_MODEL_SHA256,
        "config.json": EXPECTED_QWEN_CONFIG_SHA256,
        "tokenizer.json": EXPECTED_QWEN_TOKENIZER_SHA256,
        "modules.json": EXPECTED_QWEN_MODULES_SHA256,
        "config_sentence_transformers.json": EXPECTED_QWEN_ST_CONFIG_SHA256,
        "tokenizer_config.json": EXPECTED_QWEN_TOKENIZER_CONFIG_SHA256,
        "1_Pooling/config.json": EXPECTED_QWEN_POOLING_CONFIG_SHA256,
    }
    actual = {}
    for relative_path, expected_hash in expected.items():
        file_path = path / relative_path
        if not file_path.is_file():
            raise FileNotFoundError(f"Pinned Qwen file is missing: {file_path}")
        actual[relative_path] = sha256_file(file_path)
        if actual[relative_path] != expected_hash:
            raise ValueError(
                f"Qwen snapshot hash mismatch for {relative_path}: {actual[relative_path]}"
            )
    return actual


def canonical_graph_spec(reified: bool) -> dict[str, Any]:
    edges: list[tuple[int, int, int, int]] = []
    if reified:
        node_ids = NODE_IDS
        for mapping_index, _record in enumerate(JOIN_MAPPINGS):
            mapping_node = len(TABLE_NODE_IDS) + mapping_index
            edges.extend(
                [
                    (0, mapping_node, 0, mapping_index),
                    (1, mapping_node, 1, mapping_index),
                    (mapping_node, 0, 2, mapping_index),
                    (mapping_node, 1, 3, mapping_index),
                ]
            )
    else:
        node_ids = TABLE_NODE_IDS
        for mapping_index, _record in enumerate(JOIN_MAPPINGS):
            edges.append((0, 1, mapping_index, mapping_index))
        for mapping_index, _record in enumerate(JOIN_MAPPINGS):
            edges.append((1, 0, mapping_index + len(JOIN_MAPPINGS), mapping_index))
    return {
        "node_ids": node_ids,
        "edge_index": [[edge[0] for edge in edges], [edge[1] for edge in edges]],
        "edge_type": [edge[2] for edge in edges],
        "edge_mapping_index": [edge[3] for edge in edges],
    }


def cpu_contract() -> dict[str, Any]:
    original = derive_join_mappings(JOIN_DECLARATIONS)
    reversed_declarations = derive_join_mappings(list(reversed(JOIN_DECLARATIONS)))
    original_id_counts = {
        record["mapping_id"]: record["multiplicity"] for record in original
    }
    reversed_id_counts = {
        record["mapping_id"]: record["multiplicity"] for record in reversed_declarations
    }
    if original_id_counts != reversed_id_counts:
        raise ValueError(
            "Mapping identity or declaration counts depend on input ordering"
        )
    if len(JOIN_DECLARATIONS) != 3 or len(original) != 2:
        raise ValueError(
            "Fixture must collapse exactly three declarations to two mappings"
        )
    aliases_to_counts = {
        record["display_name"]: record["multiplicity"] for record in original
    }
    if aliases_to_counts != {"billing_map": 2, "shipping_map": 1}:
        raise ValueError(f"Unexpected mapping multiplicities: {aliases_to_counts}")
    query_ids = [item["query_id"] for item in QUERIES]
    query_roles = {
        alias: sum(item["gold"] == alias for item in QUERIES)
        for alias in MAPPING_BY_ALIAS
    }
    if (
        len(query_ids) != 4
        or len(set(query_ids)) != 4
        or query_roles
        != {
            "billing_map": 2,
            "shipping_map": 2,
        }
    ):
        raise ValueError(
            f"Unexpected fixed query fixture: roles={query_roles}, ids={query_ids}"
        )
    identities = [record["identity"] for record in original]
    if (
        len(set(identities)) != 2
        or identities[0][0] != identities[1][0]
        or identities[0][2] != identities[1][2]
    ):
        raise ValueError(
            "Mappings must be distinct ordered Join identities with shared endpoints"
        )

    reified = canonical_graph_spec(reified=True)
    reified_edge_index = torch.tensor(reified["edge_index"], dtype=torch.long)
    reified_edge_type = torch.tensor(reified["edge_type"], dtype=torch.long)
    available = {
        (
            int(reified_edge_index[0, row]),
            int(reified_edge_index[1, row]),
            int(relation),
        )
        for row, relation in enumerate(reified_edge_type.tolist())
    }
    for row, relation in enumerate(reified_edge_type.tolist()):
        source = int(reified_edge_index[0, row])
        target = int(reified_edge_index[1, row])
        if (target, source, INVERSE_RELATION[relation]) not in available:
            raise ValueError(f"Missing inverse pair for edge row {row}")
    if reified_edge_index.shape != (2, 8) or len(reified["node_ids"]) != 4:
        raise ValueError("Reified graph must contain eight directed edges")

    direct = canonical_graph_spec(reified=False)
    direct_edge_index = torch.tensor(direct["edge_index"], dtype=torch.long)
    direct_edge_type = torch.tensor(direct["edge_type"], dtype=torch.long)
    if direct_edge_index.shape != (2, 4) or direct_edge_type.unique().numel() != 4:
        raise ValueError("Direct graph must retain both FK mappings and inverses")
    return {
        "passed": True,
        "declaration_count": len(JOIN_DECLARATIONS),
        "unique_mapping_count": len(original),
        "mapping_ids": original_id_counts,
        "mapping_multiplicity": aliases_to_counts,
        "identity_derived_from_ordered_table_column_tuple": True,
        "identity_stable_under_declaration_reordering": True,
        "reified_node_count": len(reified["node_ids"]),
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
    vectors = (
        model.encode(
            texts,
            prompt=prompt,
            batch_size=16,
            show_progress_bar=False,
            convert_to_tensor=True,
            normalize_embeddings=True,
        )
        .detach()
        .float()
        .cpu()
    )
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
        raise ValueError(
            f"Qwen output dimension must be {DIM}, got {tuple(vectors.shape)}"
        )
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
    spec = canonical_graph_spec(reified=reified)
    edge_index = torch.tensor(spec["edge_index"], dtype=torch.long)
    edge_type = torch.tensor(spec["edge_type"], dtype=torch.long)
    edge_instance_id = torch.tensor(spec["edge_mapping_index"], dtype=torch.long)
    if node_vectors.shape[0] != len(spec["node_ids"]):
        raise ValueError(
            f"Expected {len(spec['node_ids'])} node vectors for graph, got {node_vectors.shape[0]}"
        )
    return Data(
        x=node_vectors.contiguous(),
        edge_index=edge_index,
        edge_type=edge_type,
        rel_attr=relation_vectors.contiguous(),
        num_relations=4,
        edge_fk_instance_id=edge_instance_id,
    )


def rank_candidate_scores(score_values: list[float]) -> list[float]:
    ranks = []
    for score in score_values:
        greater_count = sum(other > score for other in score_values)
        tied_count = sum(other == score for other in score_values)
        ranks.append(1.0 + greater_count + (tied_count - 1) / 2)
    return ranks


def mapping_score_rows(
    score_values: list[float],
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(score_values) != len(JOIN_MAPPINGS):
        raise ValueError("Score count does not match the unique mapping count")
    ranks = rank_candidate_scores(score_values)
    max_score = max(score_values)
    winner_ids = [
        record["mapping_id"]
        for record, score in zip(JOIN_MAPPINGS, score_values, strict=True)
        if score == max_score
    ]
    rows = [
        {
            "mapping_id": record["mapping_id"],
            "mapping_label": record["display_name"],
            "score": score,
            "rank": rank,
        }
        for record, score, rank in zip(JOIN_MAPPINGS, score_values, ranks, strict=True)
    ]
    return rows, winner_ids


def permute_reified_graph(graph: Data) -> tuple[Data, torch.Tensor, dict[int, int]]:
    # new-index -> old-index; reverse all edge rows as a serialization control.
    new_to_old = [2, 0, 3, 1]
    old_to_new = {old: new for new, old in enumerate(new_to_old)}
    inverse = torch.tensor(
        [old_to_new[i] for i in range(len(new_to_old))], dtype=torch.long
    )
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
    batch = {
        "question_embeddings": query.to(device),
        "start_nodes_mask": mask.to(device),
    }
    forward_started = time.perf_counter()
    with torch.inference_mode():
        output = model(moved, batch)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    forward_seconds = time.perf_counter() - forward_started
    if output.ndim != 2 or tuple(output.shape) != (1, graph.num_nodes):
        raise ValueError(
            f"Unexpected output shape {tuple(output.shape)} for {graph.num_nodes} nodes"
        )
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
    if (
        gfm_model_hash != EXPECTED_GFM_MODEL_SHA256
        or gfm_config_hash != EXPECTED_GFM_CONFIG_SHA256
    ):
        raise ValueError("G-reasoner checkpoint hash mismatch")
    qwen_hashes = validate_qwen_snapshot(embedding_path)
    versions = {
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "torch_geometric": str(torch_geometric.__version__),
        "transformers": str(transformers.__version__),
        "sentence_transformers": str(sentence_transformers.__version__),
    }
    expected_versions = {
        "python": "3.12.15",
        "torch": "2.8.0",
        "torch_geometric": "2.6.1",
        "transformers": "4.56.1",
        "sentence_transformers": "5.1.1",
    }
    normalized_versions = {
        key: value.split("+", 1)[0] for key, value in versions.items()
    }
    if normalized_versions != expected_versions:
        raise RuntimeError(f"Environment version mismatch: {versions}")
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
    check_runtime_budget(timer, cpu_timer)
    query_items = QUERIES[:1] if args.mode == "smoke" else QUERIES
    embedding_encode_started = time.perf_counter()
    query_vectors, query_token_counts = embed_texts(
        embedder, [item["text"] for item in query_items], is_query=True
    )
    passage_texts = (
        TABLE_TEXTS
        + list(JOIN_TEXTS.values())
        + DIRECT_RELATION_TEXTS
        + REIFIED_RELATION_TEXTS
    )
    passage_vectors, passage_token_counts = embed_texts(
        embedder, passage_texts, is_query=False
    )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    embedding_encode_seconds = time.perf_counter() - embedding_encode_started
    check_runtime_budget(timer, cpu_timer)

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
        candidate_scores, winner_ids = mapping_score_rows(
            [
                float(scores[mapping_index])
                for mapping_index in range(len(JOIN_MAPPINGS))
            ]
        )
        gold_mapping_id = MAPPING_ID_BY_ALIAS[item["gold"]]
        dense_rows.append(
            {
                "query_id": item["query_id"],
                "gold_mapping_id": gold_mapping_id,
                "gold_mapping_label": item["gold"],
                "predicted_mapping_id": winner_ids[0] if len(winner_ids) == 1 else None,
                "top1_mapping_ids": winner_ids,
                "candidate_scores": candidate_scores,
                "correct": len(winner_ids) == 1 and winner_ids[0] == gold_mapping_id,
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
    if (
        int(model_config["entity_model"]["input_dim"]) != DIM
        or int(model_config["feat_dim"]) != DIM
    ):
        raise ValueError("Checkpoint feature dimension is not 1024")
    model.eval().to(device)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    gfm_load_seconds = time.perf_counter() - gfm_load_started
    check_runtime_budget(timer, cpu_timer)

    model_rows = []
    base_outputs: dict[str, torch.Tensor] = {}
    forward_times = []
    for idx, item in enumerate(query_items):
        output, forward_seconds = run_forward(
            model, reified_graph, query_vectors[idx : idx + 1], 0, device
        )
        check_runtime_budget(timer, cpu_timer)
        forward_times.append(forward_seconds)
        base_outputs[item["query_id"]] = output
        candidate_scores, winner_ids = mapping_score_rows(
            [float(output[0, node_index]) for node_index in MAPPING_NODE_INDICES]
        )
        score_by_id = {row["mapping_id"]: row["score"] for row in candidate_scores}
        gold_mapping_id = MAPPING_ID_BY_ALIAS[item["gold"]]
        model_rows.append(
            {
                "query_id": item["query_id"],
                "gold_mapping_id": gold_mapping_id,
                "gold_mapping_label": item["gold"],
                "predicted_mapping_id": winner_ids[0] if len(winner_ids) == 1 else None,
                "top1_mapping_ids": winner_ids,
                "scores_by_mapping_id": score_by_id,
                "candidate_scores": candidate_scores,
                "correct": len(winner_ids) == 1 and winner_ids[0] == gold_mapping_id,
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
        direct_output, direct_forward_seconds = run_forward(
            model, direct_graph, query_vectors[:1], 0, device
        )
        check_runtime_budget(timer, cpu_timer)
        forward_times.append(direct_forward_seconds)
        direct_output_shape = list(direct_output.shape)
        direct_output_finite = bool(torch.isfinite(direct_output).all().item())
        direct_table_scores = [
            float(direct_output[0, index]) for index in range(direct_graph.num_nodes)
        ]
        direct_table_ranks = rank_candidate_scores(direct_table_scores)
        direct_node_score_rows = [
            {
                "node_id": node_id,
                "score": score,
                "rank": rank,
            }
            for node_id, score, rank in zip(
                TABLE_NODE_IDS, direct_table_scores, direct_table_ranks, strict=True
            )
        ]

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
        check_runtime_budget(timer, cpu_timer)
        forward_times.append(permutation_forward_seconds)
        if (
            tuple(permuted_output.shape) != (1, 4)
            or not torch.isfinite(permuted_output).all().item()
        ):
            raise ValueError("Invalid output for the node/edge-order permutation case")
        restored = permuted_output[:, [old_to_new[i] for i in range(4)]]
        reference = base_outputs[query_items[0]["query_id"]]
        reference_mapping_scores = [
            float(reference[0, index]) for index in MAPPING_NODE_INDICES
        ]
        restored_mapping_scores = [
            float(restored[0, index]) for index in MAPPING_NODE_INDICES
        ]
        permutation_delta = max(
            abs(reference_score - restored_score)
            for reference_score, restored_score in zip(
                reference_mapping_scores, restored_mapping_scores, strict=True
            )
        )
        reference_winners = mapping_score_rows(reference_mapping_scores)[1]
        restored_winners = mapping_score_rows(restored_mapping_scores)[1]
        permutation_top1_same = set(reference_winners) == set(restored_winners)

        billing_id = MAPPING_ID_BY_ALIAS["billing_map"]
        shipping_id = MAPPING_ID_BY_ALIAS["shipping_map"]
        billing_rows = [
            row for row in model_rows if row["gold_mapping_id"] == billing_id
        ]
        shipping_rows = [
            row for row in model_rows if row["gold_mapping_id"] == shipping_id
        ]
        if len(billing_rows) != 2 or len(shipping_rows) != 2:
            raise ValueError(
                "Full fixture must contain two questions for each mapping role"
            )
        bill_margin = sum(
            row["scores_by_mapping_id"][billing_id]
            - row["scores_by_mapping_id"][shipping_id]
            for row in billing_rows
        ) / len(billing_rows)
        ship_margin = sum(
            row["scores_by_mapping_id"][shipping_id]
            - row["scores_by_mapping_id"][billing_id]
            for row in shipping_rows
        ) / len(shipping_rows)
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
        beats_dense_cosine = model_correct > dense_correct
        signal_pass = (
            model_correct >= 3 and beats_dense_cosine and all(flip_pairs.values())
        )
        path_baseline_rows = []
        path_scores, path_winners = mapping_score_rows([1.0] * len(JOIN_MAPPINGS))
        for item in query_items:
            path_baseline_rows.append(
                {
                    "query_id": item["query_id"],
                    "candidate_scores": path_scores,
                    "top1_mapping_ids": path_winners,
                    "resolved_prediction": False,
                }
            )
        synthetic_signal = {
            "gfm_top1_correct": model_correct,
            "dense_cosine_top1_correct": dense_correct,
            "gfm_accuracy_strictly_exceeds_dense_cosine": beats_dense_cosine,
            "billing_mean_score_margin": bill_margin,
            "shipping_mean_score_margin": ship_margin,
            "query_role_flip_pairs_passed": flip_pairs,
            "simple_fk_path_baseline": path_baseline_rows,
            "gfm_signal_pass": signal_pass,
            "technical_interface_and_permutation_pass": technical_pass,
            "interpretation_limit": "4 controlled synthetic query texts; no real-query or business-role claim",
        }
        status = (
            "G0_SYNTHETIC_PASS"
            if technical_pass and signal_pass
            else "G0_SYNTHETIC_NO_GO"
        )

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
            "file_hashes": qwen_hashes,
            "config_sha256": qwen_hashes["config.json"],
            "tokenizer_sha256": qwen_hashes["tokenizer.json"],
            "modules_sha256": qwen_hashes["modules.json"],
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
            "unique_mappings": [
                {
                    "mapping_id": record["mapping_id"],
                    "display_name": record["display_name"],
                    "ordered_identity": list(record["identity"]),
                    "declaration_multiplicity": record["multiplicity"],
                }
                for record in JOIN_MAPPINGS
            ],
            "identity_policy": "SHA-256 of ordered (source_table, source_column, target_table, target_column); duplicate declarations merge and retain multiplicity",
            "synthetic_query_count": len(query_items),
            "trusted_real_role_labels": 0,
        },
        "dense_cosine_baseline": dense_rows,
        "reified_gfm": model_rows,
        "direct_graph_reference": {
            "query_id": query_items[0]["query_id"] if args.mode == "full" else None,
            "output_shape": direct_output_shape,
            "finite": direct_output_finite,
            "table_node_scores": direct_node_score_rows
            if args.mode == "full"
            else None,
            "mapping_node_scores_available": False,
            "mapping_rank": None,
            "note": "Direct table graph reports exact table-node scores/ranks only. It has no candidate-specific FK node, so a mapping score/rank is unidentifiable.",
        },
        "simple_fk_path_baseline": {
            "definition": "score = 1 / shortest table-hop count; both candidates have one hop, so both score 1.0 and receive average tie rank 1.5",
            "query_results": synthetic_signal["simple_fk_path_baseline"]
            if synthetic_signal
            else None,
        },
        "permutation_control": {
            "max_abs_score_delta_after_id_remap": permutation_delta,
            "top1_same": permutation_top1_same,
        },
        "synthetic_signal": synthetic_signal,
        "resources": {
            "device": str(device),
            "gpu_name": gpu_name,
            "peak_gpu_allocated_bytes": peak_gpu_bytes,
            "peak_rss_gib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2), 6
            ),
            "cpu_process_seconds": round(time.process_time() - cpu_timer, 6),
            "qwen_load_seconds": round(embedding_load_seconds, 6),
            "qwen_encode_seconds": round(embedding_encode_seconds, 6),
            "g_reasoner_load_seconds": round(gfm_load_seconds, 6),
            "g_reasoner_forward_seconds_total": round(sum(forward_times), 6),
            "g_reasoner_forward_seconds_each": [
                round(value, 6) for value in forward_times
            ],
            "wall_time_limit_seconds": WALL_LIMIT_SECONDS,
            "cpu_time_limit_seconds": CPU_LIMIT_SECONDS,
            "rss_limit_gib": RSS_LIMIT_GIB,
            "model_loads_in_run": {"qwen_embedding": 1, "g_reasoner": 1},
            "forward_passes": 1 if args.mode == "smoke" else 6,
            "training_epochs": 0,
            "sql_or_database_execution": False,
            "bird_or_gold_data": False,
            "dependency_changes": 0,
        },
        "environment": {
            **versions,
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
    global \
        Data, \
        SentenceTransformer, \
        sentence_transformers, \
        torch, \
        torch_geometric, \
        transformers

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
    failure_path = args.output.with_suffix(args.output.suffix + ".failure.json")
    partial_path = args.output.with_suffix(args.output.suffix + ".partial")
    attempt_path = args.output.with_suffix(args.output.suffix + ".attempt.json")
    existing_artifacts = [
        path
        for path in (args.output, failure_path, partial_path, attempt_path)
        if path.exists()
    ]
    if existing_artifacts:
        raise FileExistsError(
            "Refusing to reuse this run ID; existing artifacts: "
            + ", ".join(str(path) for path in existing_artifacts)
        )
    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "attempted_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    with attempt_path.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(attempt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    try:
        import sentence_transformers
        import torch
        import torch_geometric
        import transformers
        from sentence_transformers import SentenceTransformer
        from torch_geometric.data import Data

        result = run(args)
    except Exception as exc:
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "FAILED",
            "failed_utc": datetime.now(timezone.utc).isoformat(),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }
        failure_payload = (
            json.dumps(failure, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        try:
            with failure_path.open("x", encoding="utf-8") as handle:
                handle.write(failure_payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            pass
        raise
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
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "experiment_id",
                    "run_id",
                    "mode",
                    "status",
                    "elapsed_seconds",
                    "resources",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"RESULT_JSON={args.output}")


if __name__ == "__main__":
    main()
