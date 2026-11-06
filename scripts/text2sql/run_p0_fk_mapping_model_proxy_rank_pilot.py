#!/usr/bin/env python3
"""Exploratory FK mapping ranking pilot against three-model proxy consensus."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
import platform
import re
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from aggregate_p0_fk_mapping_model_review_three_proxy import normalized_label, read_jsonl  # noqa: E402
from run_p0_fk_mapping_model_review_proxy import parse_packet, validate_packet_pair  # noqa: E402
from g0_fk_instance_node_probe import (  # noqa: E402
    DIM,
    EXPECTED_GFM_CONFIG_SHA256,
    EXPECTED_GFM_MODEL_SHA256,
    QUERY_INSTRUCTION,
    sha256_file,
    validate_qwen_snapshot,
)

EXPERIMENT_ID = "p0_fk_mapping_model_proxy_rank_pilot_20261106_01"
SEED = 20261106
EXPECTED_PACKET_A = "0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2"
EXPECTED_PACKET_B = "a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb"
EXPECTED_MANIFEST = "14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7"
EXPECTED_OUTPUT_A = "f3d2beb21290c49790679e53ac0bf8dc50084b7b34ee228843f06330ac120883"
EXPECTED_OUTPUT_B = "2b49a5772f061ed70f02ea21811e392fd6afd086fa7030aca9fe737c2c8af077"
EXPECTED_OUTPUT_C = "88c5b79785af76896055378ece4776b523bdb036588304cd63305db51a10d333"
EXPECTED_QWEN_REVISION = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_GFM_PARAMETERS = 34_640_897
MAX_GPU_BYTES = 8 * 1024**3
MAX_RSS_BYTES = 16 * 1024**3
MAX_WALL_SECONDS = 20 * 60
ENCODE_BATCH_SIZE = 32
RELATION_TEXTS = [
    "Relation: source table participates in a join mapping.",
    "Relation: referenced target table participates in a join mapping.",
    "Inverse relation: join mapping points to its source table.",
    "Inverse relation: join mapping points to its referenced target table.",
]
TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--reviewer-c", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def file_hashes(args: argparse.Namespace) -> dict[str, str]:
    return {
        "packet_a": sha256_file(args.packet_a),
        "packet_b": sha256_file(args.packet_b),
        "private_manifest": sha256_file(args.private_manifest),
        "reviewer_a": sha256_file(args.reviewer_a),
        "reviewer_b": sha256_file(args.reviewer_b),
        "reviewer_c": sha256_file(args.reviewer_c),
        "split_manifest": sha256_file(args.split_manifest),
    }


def get_proxy_consensus(
    pair_id: str,
    candidates: set[str],
    outputs: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    votes: dict[tuple[str, tuple[str, ...]], list[int]] = defaultdict(list)
    for reviewer_rows in outputs.values():
        row = reviewer_rows[pair_id]
        label = normalized_label(row)
        if label is None:
            continue
        accepted = set(label[1])
        require(accepted <= candidates, "model-proxy label references a noncandidate mapping")
        votes[label].append(int(row["answer"]["confidence"]))
    majority = [
        (label, confidences)
        for label, confidences in votes.items()
        if sum(confidence >= 2 for confidence in confidences) >= 2
    ]
    if len(majority) != 1:
        return None
    (decision, accepted_tuple), _ = majority[0]
    if decision not in {"single_mapping", "multiple_mappings"} or not accepted_tuple:
        return None
    return {"decision": decision, "accepted_mapping_ids": list(accepted_tuple)}


def make_frozen_split(
    items: dict[str, dict[str, Any]], manifest_rows: dict[str, dict[str, Any]]
) -> tuple[set[str], set[str], list[str]]:
    question_hashes = sorted({manifest_rows[pair_id]["question_key_sha256"] for pair_id in items})
    smoke_questions = sorted(
        question_hashes,
        key=lambda value: hashlib.sha256(f"{SEED}:{value}".encode("utf-8")).hexdigest(),
    )[:5]
    smoke_question_set = set(smoke_questions)
    smoke_pairs = {
        pair_id for pair_id in items
        if manifest_rows[pair_id]["question_key_sha256"] in smoke_question_set
    }
    full_pairs = set(items) - smoke_pairs
    return smoke_pairs, full_pairs, smoke_questions


def load_private_inputs(args: argparse.Namespace) -> dict[str, Any]:
    packet_a, hash_a = parse_packet(args.packet_a)
    packet_b, hash_b = parse_packet(args.packet_b)
    require(hash_a == EXPECTED_PACKET_A and hash_b == EXPECTED_PACKET_B, "blind packet hash mismatch")
    pair_index = validate_packet_pair(packet_a, packet_b)
    require(len(pair_index) == 60, "frozen packet must contain 60 question-pairs")
    require(sum(len(item["mappings"]) for item in packet_a) == 135, "frozen packet candidate count mismatch")
    items = {item["pair_id"]: item for item in packet_a}
    require(len(items) == 60, "duplicate pair ID in frozen packet")
    manifest = json.loads(args.private_manifest.read_text(encoding="utf-8"))
    manifest_rows = {row["pair_id"]: row for row in manifest["selected_cases_private"]}
    require(set(manifest_rows) == set(items), "private manifest coverage mismatch")
    require(sha256_file(args.private_manifest) == EXPECTED_MANIFEST, "private manifest hash mismatch")
    require(manifest.get("trusted_role_label_count") == 0, "expected zero human Role labels")
    require(manifest.get("human_review_completed") is False, "human review must remain incomplete")

    output_paths = {"A": args.reviewer_a, "B": args.reviewer_b, "C": args.reviewer_c}
    expected_output_hashes = {"A": EXPECTED_OUTPUT_A, "B": EXPECTED_OUTPUT_B, "C": EXPECTED_OUTPUT_C}
    outputs = {}
    for reviewer, path in output_paths.items():
        require(sha256_file(path) == expected_output_hashes[reviewer], f"reviewer {reviewer} output hash mismatch")
        outputs[reviewer] = read_jsonl(path)
        require(set(outputs[reviewer]) == set(items), f"reviewer {reviewer} coverage mismatch")

    labels = {}
    for pair_id, item in items.items():
        candidate_ids = {mapping["mapping_id"] for mapping in item["mappings"]}
        labels[pair_id] = get_proxy_consensus(pair_id, candidate_ids, outputs)
        require(len(candidate_ids) >= 2, "every frozen pair must have multiple candidate mappings")
        require(item["question"] == manifest_rows[pair_id]["private_question_text"], "packet/manifest question mismatch")
        ids_from_manifest = {mapping["mapping_id"] for mapping in manifest_rows[pair_id]["mapping_identities"]}
        require(ids_from_manifest == candidate_ids, "packet/manifest mapping identity mismatch")

    split = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    smoke_pairs, full_pairs, smoke_questions = make_frozen_split(items, manifest_rows)
    require(split.get("fixed_seed") == SEED, "private split seed mismatch")
    require(set(split.get("smoke_pair_ids", [])) == smoke_pairs, "Smoke partition differs from frozen private split")
    require(set(split.get("full_pair_ids", [])) == full_pairs, "Full partition differs from frozen private split")
    require(len(smoke_questions) == 5 and len(smoke_pairs) == 5 and len(full_pairs) == 55, "unexpected question-level split size")

    full_adjudicable = [pair_id for pair_id in full_pairs if labels[pair_id] is not None]
    full_distinguishable = [
        pair_id for pair_id in full_adjudicable
        if set(labels[pair_id]["accepted_mapping_ids"])
        < {mapping["mapping_id"] for mapping in items[pair_id]["mappings"]}
    ]
    require(len(full_adjudicable) == 51 and len(full_distinguishable) == 38, "model-proxy Full data gate changed")
    db_by_pair = {pair_id: manifest_rows[pair_id]["private_db_id"] for pair_id in items}
    db_counts = Counter(db_by_pair[pair_id] for pair_id in full_distinguishable)
    require(len(db_counts) == 4 and sorted(db_counts.values()) == [5, 10, 10, 13], "anonymous database split changed")
    return {
        "items": items,
        "manifest_rows": manifest_rows,
        "outputs": outputs,
        "labels": labels,
        "smoke_pairs": smoke_pairs,
        "full_pairs": full_pairs,
        "full_adjudicable": full_adjudicable,
        "full_distinguishable": full_distinguishable,
        "db_by_pair": db_by_pair,
        "database_counts": db_counts,
    }


def column_sets_for_pair(item: dict[str, Any], private_row: dict[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    table_pair = private_row["private_table_pair"]
    require(isinstance(table_pair, list) and len(table_pair) == 2, "invalid private table pair")
    tables = sorted(str(value) for value in table_pair)
    columns: dict[str, set[str]] = {table: set() for table in tables}
    identity_by_id = {entry["mapping_id"]: entry for entry in private_row["mapping_identities"]}
    for mapping in item["mappings"]:
        identity = identity_by_id[mapping["mapping_id"]]["identity"]
        require(isinstance(identity, list) and len(identity) == 4, "invalid ordered FK identity")
        child_table, parent_table = str(identity[1]), str(identity[3])
        require({child_table, parent_table} == set(tables), "FK mapping endpoints differ from table pair")
        pairs = identity[2]
        require(isinstance(pairs, list) and len(pairs) >= 1, "empty or invalid composite mapping")
        for column_pair in pairs:
            require(isinstance(column_pair, list) and len(column_pair) == 2, "invalid ordered FK column pair")
            child_column, parent_column = str(column_pair[0]), str(column_pair[1])
            columns[child_table].add(child_column)
            columns[parent_table].add(parent_column)
    return tables, {table: sorted(values) for table, values in columns.items()}


def query_and_passage_texts(
    selected_pairs: set[str], private: dict[str, Any]
) -> tuple[dict[str, str], dict[tuple[str, str], str], dict[str, dict[str, str]]]:
    query_by_pair: dict[str, str] = {}
    table_text_by_key: dict[tuple[str, str], str] = {}
    mapping_text_by_pair_and_id: dict[str, dict[str, str]] = {}
    for pair_id in sorted(selected_pairs):
        item = private["items"][pair_id]
        manifest_row = private["manifest_rows"][pair_id]
        question = str(manifest_row["private_question_text"])
        require(question.strip(), "empty query text")
        query_by_pair[pair_id] = question
        tables, columns = column_sets_for_pair(item, manifest_row)
        for table in tables:
            text = f"Table: {table}. Declared FK columns appearing in this candidate set: {', '.join(columns[table])}."
            table_text_by_key[(pair_id, table)] = text
        identity_by_id = {entry["mapping_id"]: entry for entry in manifest_row["mapping_identities"]}
        candidate_texts = {}
        for mapping in item["mappings"]:
            entry = identity_by_id[mapping["mapping_id"]]
            identity = entry["identity"]
            child_table, parent_table = str(identity[1]), str(identity[3])
            rendered_pairs = "; ".join(
                f"{str(child)} = {str(parent)}" for child, parent in identity[2]
            )
            mapping_text = (
                f"Foreign-key join mapping: source table {child_table}; ordered source/target columns "
                f"{rendered_pairs}; referenced table {parent_table}."
            )
            candidate_texts[mapping["mapping_id"]] = mapping_text
        mapping_text_by_pair_and_id[pair_id] = candidate_texts
    return query_by_pair, table_text_by_key, mapping_text_by_pair_and_id


def count_tokens(tokenizer: Any, text: str, *, is_query: bool, max_length: int) -> int:
    serialized = (QUERY_INSTRUCTION if is_query else "") + text
    row = tokenizer(serialized, add_special_tokens=True, truncation=True, max_length=max_length, padding=False)
    return len(row["input_ids"])


def record_embedding_batch(run_id: str, call_id: str, token_count: int | None, succeeded: bool) -> None:
    shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
    if not shared_root or not Path(shared_root).is_dir():
        raise RuntimeError("GFM_SHARED_CODE_ROOT must point to local api_usage_ledger.py")
    if shared_root not in sys.path:
        sys.path.insert(0, shared_root)
    from api_usage_ledger import record_request

    usage = None
    if succeeded and token_count is not None:
        usage = {"input_tokens": token_count, "output_tokens": 0, "total_tokens": token_count}
    record_request(
        call_id=call_id,
        provider="local_sentence_transformers_gpu",
        project="gfm-rag",
        run_id=run_id,
        model=EXPECTED_QWEN_REVISION,
        http_status=None,
        usage=usage,
    )


def encode_texts(
    embedder: Any,
    texts: list[str],
    *,
    is_query: bool,
    run_id: str,
    call_prefix: str,
    torch: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    unique_texts = sorted(set(texts))
    tokenizer = embedder[0].tokenizer
    max_length = int(embedder.max_seq_length)
    vectors: dict[str, Any] = {}
    token_counts: dict[str, int] = {}
    all_norms: list[float] = []
    batch_input_tokens = 0
    for batch_index, start in enumerate(range(0, len(unique_texts), ENCODE_BATCH_SIZE)):
        batch = unique_texts[start : start + ENCODE_BATCH_SIZE]
        counts = [count_tokens(tokenizer, text, is_query=is_query, max_length=max_length) for text in batch]
        total_tokens = sum(counts)
        call_id = f"{run_id}:qwen:{call_prefix}:batch{batch_index:03d}"
        try:
            encoded = embedder.encode(
                batch,
                prompt=QUERY_INSTRUCTION if is_query else "",
                batch_size=ENCODE_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_tensor=True,
                normalize_embeddings=True,
            ).detach().float().cpu()
        except Exception:
            record_embedding_batch(run_id, call_id, None, False)
            raise
        record_embedding_batch(run_id, call_id, total_tokens, True)
        if encoded.ndim != 2 or encoded.shape[0] != len(batch) or encoded.shape[1] != DIM:
            raise ValueError(f"Expected {len(batch)} normalized 1024-D embeddings, got {tuple(encoded.shape)}")
        if not torch.isfinite(encoded).all().item():
            raise ValueError("Embedding model produced non-finite values")
        norms = encoded.norm(dim=1)
        if not torch.allclose(norms, torch.ones_like(norms), atol=2e-3, rtol=0):
            raise ValueError("Embedding model output is not unit-normalized")
        for text, vector, count in zip(batch, encoded, counts, strict=True):
            vectors[text] = vector.contiguous()
            token_counts[text] = count
        all_norms.extend(float(value) for value in norms.tolist())
        batch_input_tokens += total_tokens
    return vectors, {
        "unique_text_count": len(unique_texts),
        "input_tokens": batch_input_tokens,
        "output_tokens": 0,
        "batch_count": math.ceil(len(unique_texts) / ENCODE_BATCH_SIZE),
        "norm_min": min(all_norms) if all_norms else None,
        "norm_median": sorted(all_norms)[len(all_norms) // 2] if all_norms else None,
        "norm_max": max(all_norms) if all_norms else None,
    }


def bm25_scores(query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    tokenized = [[token.casefold() for token in TOKEN_RE.findall(doc)] for doc in documents]
    query_terms = sorted({token.casefold() for token in TOKEN_RE.findall(query)})
    count = len(tokenized)
    lengths = [len(tokens) for tokens in tokenized]
    average_length = sum(lengths) / count if count else 0.0
    document_frequency = Counter(term for tokens in tokenized for term in set(tokens))
    scores = []
    for tokens, length in zip(tokenized, lengths, strict=True):
        frequencies = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            df = document_frequency[term]
            idf = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * length / average_length) if average_length else frequency + k1
            score += idf * frequency * (k1 + 1.0) / denominator
        scores.append(score)
    return scores


def stable_rank(scores: dict[str, float]) -> tuple[list[str], int]:
    ordered = sorted(scores, key=lambda mapping_id: (-scores[mapping_id], mapping_id))
    top_score = scores[ordered[0]] if ordered else 0.0
    top_ties = sum(score == top_score for score in scores.values())
    return ordered, top_ties


def build_graph(
    pair_id: str,
    private: dict[str, Any],
    table_texts: dict[tuple[str, str], str],
    mapping_texts: dict[str, dict[str, str]],
    vectors: dict[str, Any],
    relation_vectors: dict[str, Any],
    Data: Any,
    torch: Any,
) -> tuple[Any, dict[str, int], dict[str, Any]]:
    item = private["items"][pair_id]
    manifest_row = private["manifest_rows"][pair_id]
    tables, _ = column_sets_for_pair(item, manifest_row)
    mappings = sorted(item["mappings"], key=lambda row: row["mapping_id"])
    table_index = {table: index for index, table in enumerate(tables)}
    mapping_node_index = {row["mapping_id"]: len(tables) + index for index, row in enumerate(mappings)}
    identity_by_id = {entry["mapping_id"]: entry for entry in manifest_row["mapping_identities"]}
    node_texts = [table_texts[(pair_id, table)] for table in tables]
    node_texts.extend(mapping_texts[pair_id][row["mapping_id"]] for row in mappings)
    node_features = torch.stack([vectors[text] for text in node_texts]).float().contiguous()
    edge_source: list[int] = []
    edge_target: list[int] = []
    edge_type: list[int] = []
    edge_mapping_index: list[int] = []
    for mapping_index, mapping in enumerate(mappings):
        identity = identity_by_id[mapping["mapping_id"]]["identity"]
        child_table, parent_table = str(identity[1]), str(identity[3])
        mapping_node = mapping_node_index[mapping["mapping_id"]]
        for source, target, relation in (
            (table_index[child_table], mapping_node, 0),
            (table_index[parent_table], mapping_node, 1),
            (mapping_node, table_index[child_table], 2),
            (mapping_node, table_index[parent_table], 3),
        ):
            edge_source.append(source)
            edge_target.append(target)
            edge_type.append(relation)
            edge_mapping_index.append(mapping_index)
    edge_index = torch.tensor([edge_source, edge_target], dtype=torch.long)
    edge_type_tensor = torch.tensor(edge_type, dtype=torch.long)
    relation_features = torch.stack([relation_vectors[text] for text in RELATION_TEXTS]).float().contiguous()
    graph = Data(
        x=node_features,
        edge_index=edge_index,
        edge_type=edge_type_tensor,
        rel_attr=relation_features,
        num_relations=4,
        edge_fk_instance_id=torch.tensor(edge_mapping_index, dtype=torch.long),
    )
    start_mask = torch.zeros((1, graph.num_nodes), dtype=torch.float32)
    start_mask[0, : len(tables)] = 1.0
    return graph, mapping_node_index, {
        "table_count": len(tables),
        "mapping_count": len(mappings),
        "edge_count": int(edge_index.shape[1]),
        "start_seed_count": int(start_mask.sum().item()),
        "start_mask": start_mask,
    }


def run_g_reasoner(model: Any, graph: Any, query: Any, start_mask: Any, device: Any, torch: Any) -> tuple[Any, float]:
    moved = graph.clone().to(device)
    for key in ("x", "edge_index", "edge_type", "rel_attr", "edge_fk_instance_id"):
        if not torch.equal(getattr(moved, key).cpu(), getattr(graph, key).cpu()):
            raise ValueError(f"Graph changed during device transfer: {key}")
    batch = {
        "question_embeddings": query.reshape(1, -1).to(device),
        "start_nodes_mask": start_mask.to(device),
    }
    forward_started = time.perf_counter()
    with torch.inference_mode():
        scores = model(moved, batch)
    torch.cuda.synchronize(device)
    forward_seconds = time.perf_counter() - forward_started
    if scores.ndim != 2 or tuple(scores.shape) != (1, graph.num_nodes):
        raise ValueError(f"Unexpected G-reasoner output shape: {tuple(scores.shape)}")
    scores = scores.detach().float().cpu()[0]
    if not torch.isfinite(scores).all().item():
        raise ValueError("G-reasoner produced non-finite node scores")
    return scores, forward_seconds


def score_pair(
    pair_id: str,
    private: dict[str, Any],
    query_texts: dict[str, str],
    mapping_texts: dict[str, dict[str, str]],
    vectors: dict[str, Any],
    query_vector: Any,
    graph_inputs: tuple[Any, dict[str, int], dict[str, Any]],
    model: Any,
    device: Any,
    torch: Any,
) -> dict[str, Any]:
    item = private["items"][pair_id]
    candidates = sorted(item["mappings"], key=lambda row: row["mapping_id"])
    mapping_ids = [row["mapping_id"] for row in candidates]
    graph, mapping_nodes, graph_meta = graph_inputs
    query_text = query_texts[pair_id]
    dense_scores = {
        mapping["mapping_id"]: float(torch.dot(query_vector, vectors[mapping_texts[pair_id][mapping["mapping_id"]]]))
        for mapping in candidates
    }
    lexical_values = bm25_scores(query_text, [mapping_texts[pair_id][mapping_id] for mapping_id in mapping_ids])
    bm25 = dict(zip(mapping_ids, lexical_values, strict=True))
    gfm_node_scores, gfm_forward_seconds = run_g_reasoner(model, graph, query_vector, graph_meta["start_mask"], device, torch)
    gfm = {mapping_id: float(gfm_node_scores[node_index]) for mapping_id, node_index in mapping_nodes.items()}
    structure = {mapping_id: 0.0 for mapping_id in mapping_ids}
    scores = {"g_reasoner": gfm, "dense_cosine": dense_scores, "bm25_okapi": bm25, "stable_mapping_id_order": structure}
    ranked = {}
    tie_counts = {}
    for method, method_scores in scores.items():
        order, top_ties = stable_rank(method_scores)
        ranked[method] = order
        tie_counts[method] = top_ties
    return {
        "pair_id": pair_id,
        "candidate_mapping_ids": mapping_ids,
        "candidate_scores": scores,
        "ranked_mapping_ids": ranked,
        "top_tie_counts": tie_counts,
        "g_reasoner_forward_seconds": round(gfm_forward_seconds, 6),
        "graph": {key: value for key, value in graph_meta.items() if key != "start_mask"},
    }


def metric_summary(rows: list[dict[str, Any]], labels: dict[str, Any], pair_ids: list[str]) -> dict[str, Any]:
    result = {}
    for method in ("g_reasoner", "dense_cosine", "bm25_okapi", "stable_mapping_id_order"):
        accepted_1 = accepted_3 = 0
        reciprocal_ranks = []
        tie_units = 0
        for pair_id in pair_ids:
            row = rows[pair_id]
            accepted = set(labels[pair_id]["accepted_mapping_ids"])
            ranking = row["ranked_mapping_ids"][method]
            accepted_ranks = [index + 1 for index, mapping_id in enumerate(ranking) if mapping_id in accepted]
            if not accepted_ranks:
                raise ValueError("accepted model-proxy mapping missing from candidate ranking")
            accepted_1 += int(ranking[0] in accepted)
            accepted_3 += int(any(rank <= 3 for rank in accepted_ranks))
            reciprocal_ranks.append(1.0 / min(accepted_ranks))
            tie_units += int(row["top_tie_counts"][method] > 1)
        denominator = len(pair_ids)
        result[method] = {
            "accepted_at_1": {"correct": accepted_1, "denominator": denominator, "rate": round(accepted_1 / denominator, 6) if denominator else None},
            "accepted_at_3": {"correct": accepted_3, "denominator": denominator, "rate": round(accepted_3 / denominator, 6) if denominator else None},
            "mrr_first_accepted": round(sum(reciprocal_ranks) / denominator, 6) if denominator else None,
            "top_tie_units": tie_units,
        }
    return result


def paired_comparison(rows: dict[str, dict[str, Any]], labels: dict[str, Any], pair_ids: list[str]) -> dict[str, int]:
    rescued = damaged = both_correct = both_wrong = 0
    for pair_id in pair_ids:
        accepted = set(labels[pair_id]["accepted_mapping_ids"])
        gfm_top = rows[pair_id]["ranked_mapping_ids"]["g_reasoner"][0] in accepted
        dense_top = rows[pair_id]["ranked_mapping_ids"]["dense_cosine"][0] in accepted
        rescued += int(gfm_top and not dense_top)
        damaged += int(dense_top and not gfm_top)
        both_correct += int(gfm_top and dense_top)
        both_wrong += int(not gfm_top and not dense_top)
    return {
        "g_reasoner_only_correct": rescued,
        "dense_only_correct": damaged,
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "net_rescue": rescued - damaged,
    }


def create_full_summary(
    private: dict[str, Any], rows: dict[str, dict[str, Any]], run_meta: dict[str, Any]
) -> dict[str, Any]:
    distinguishable = private["full_distinguishable"]
    adjudicable = private["full_adjudicable"]
    per_db_private: dict[str, list[str]] = defaultdict(list)
    for pair_id in distinguishable:
        per_db_private[private["db_by_pair"][pair_id]].append(pair_id)
    anonymous_db_order = sorted(
        per_db_private,
        key=lambda db_id: hashlib.sha256((EXPERIMENT_ID + ":" + str(db_id)).encode("utf-8")).hexdigest(),
    )
    per_db = {}
    eligible_db_positive = 0
    for index, db_id in enumerate(anonymous_db_order, start=1):
        pair_ids = per_db_private[db_id]
        comparison = paired_comparison(rows, private["labels"], pair_ids)
        per_db[f"db_{index:02d}"] = {
            "distinguishable_pairs": len(pair_ids),
            "g_reasoner_accepted_at_1": metric_summary(rows, private["labels"], pair_ids)["g_reasoner"]["accepted_at_1"],
            "dense_cosine_accepted_at_1": metric_summary(rows, private["labels"], pair_ids)["dense_cosine"]["accepted_at_1"],
            "paired_g_reasoner_vs_dense": comparison,
        }
        if len(pair_ids) >= 5 and comparison["net_rescue"] > 0:
            eligible_db_positive += 1
    metrics_distinguishable = metric_summary(rows, private["labels"], distinguishable)
    metrics_adjudicable = metric_summary(rows, private["labels"], adjudicable)
    paired = paired_comparison(rows, private["labels"], distinguishable)
    gfm_rate = metrics_distinguishable["g_reasoner"]["accepted_at_1"]["rate"]
    dense_rate = metrics_distinguishable["dense_cosine"]["accepted_at_1"]["rate"]
    difference = gfm_rate - dense_rate
    gate = difference >= 0.05 and paired["net_rescue"] >= 4 and eligible_db_positive >= 2
    return {
        **run_meta,
        "status": "MODEL_PROXY_SCREEN_PASS" if gate else "NO_GO_OR_INCONCLUSIVE",
        "label_source": "three_model_high_confidence_exact_majority_proxy_only",
        "trusted_human_role_labels": 0,
        "question_pair_count_full": len(private["full_pairs"]),
        "adjudicable_count_full": len(adjudicable),
        "distinguishable_count_primary": len(distinguishable),
        "anonymous_database_count": len(per_db_private),
        "distinguishable_counts_by_anonymous_database": [len(per_db_private[key]) for key in anonymous_db_order],
        "primary_metrics_distinguishable": metrics_distinguishable,
        "secondary_metrics_adjudicable": metrics_adjudicable,
        "paired_g_reasoner_vs_dense_primary": paired,
        "g_reasoner_minus_dense_accepted_at_1": round(difference, 6),
        "databases_with_at_least_5_pairs_and_positive_net_rescue": eligible_db_positive,
        "per_anonymous_database": per_db,
        "positive_screen_thresholds": {
            "accepted_at_1_gain_at_least_5pp": difference >= 0.05,
            "net_rescue_at_least_4": paired["net_rescue"] >= 4,
            "two_eligible_databases_positive": eligible_db_positive >= 2,
        },
        "privacy": {
            "contains_question_text": False,
            "contains_database_or_table_names": False,
            "contains_case_pair_or_mapping_ids": False,
            "contains_per_case_rankings_or_scores": False,
            "contains_raw_model_outputs": False,
            "uses_gold_sql_or_reference_join_as_model_input": False,
            "contains_human_role_labels": False,
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def run(args: argparse.Namespace) -> dict[str, Any]:
    expected_run = f"p0_fk_mapping_model_proxy_rank_pilot_20261106_{args.mode}_001"
    require(args.run_id == expected_run, "run ID does not match preregistered mode")
    source_commit = git_commit()
    require(source_commit == args.expected_commit, "source commit differs from frozen pre-run commit")
    require(args.device == "cuda:0", "only the preregistered single visible CUDA device is allowed")
    visible_gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    require(visible_gpu != "" and "," not in visible_gpu, "pin exactly one physical GPU with CUDA_VISIBLE_DEVICES")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "local-only offline mode is required")
    shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
    require(shared_root is not None and Path(shared_root).is_dir(), "local API usage ledger path is missing")
    inputs = load_private_inputs(args)
    selected_pairs = inputs["smoke_pairs"] if args.mode == "smoke" else inputs["full_pairs"]
    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.output_dir.chmod(0o700)
    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "attempted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": source_commit,
        "input_sha256": file_hashes(args),
        "config_sha256": sha256_file(args.config),
        "cuda_visible_devices": visible_gpu,
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt)
    private_prediction_path = args.output_dir / "private_predictions.jsonl"
    os.chmod(args.output_dir, 0o700)
    with private_prediction_path.open("x", encoding="utf-8") as prediction_stream:
        os.chmod(private_prediction_path, 0o600)
        started = time.perf_counter()
        cpu_started = time.process_time()
        try:
            import torch
            import torch_geometric
            import transformers
            import sentence_transformers
            from sentence_transformers import SentenceTransformer
            from torch_geometric.data import Data
            from gfmrag.utils.util import load_model_from_pretrained

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
            normalized_versions = {key: value.split("+", 1)[0] for key, value in versions.items()}
            require(normalized_versions == expected_versions, f"GFM environment version mismatch: {versions}")
            require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "exactly one visible CUDA device is required")
            device = torch.device(args.device)
            torch.cuda.set_device(device)
            torch.cuda.reset_peak_memory_stats(device)
            torch.manual_seed(SEED)
            torch.set_num_threads(min(16, os.cpu_count() or 1))
            torch.set_num_interop_threads(min(8, os.cpu_count() or 1))

            checkpoint = args.checkpoint.resolve(strict=True)
            embedding_path = args.embedding_model.resolve(strict=True)
            require(sha256_file(checkpoint / "model.pth") == EXPECTED_GFM_MODEL_SHA256, "G-reasoner checkpoint weight hash mismatch")
            require(sha256_file(checkpoint / "config.json") == EXPECTED_GFM_CONFIG_SHA256, "G-reasoner checkpoint config hash mismatch")
            qwen_hashes = validate_qwen_snapshot(embedding_path)
            passage_embeddings: dict[str, Any] = {}
            query_embeddings: dict[str, Any] = {}
            query_by_pair, table_texts, mapping_texts = query_and_passage_texts(selected_pairs, inputs)
            all_passages = list(table_texts.values()) + list(RELATION_TEXTS)
            for pair_id in selected_pairs:
                all_passages.extend(mapping_texts[pair_id].values())
            qwen_load_started = time.perf_counter()
            embedder = SentenceTransformer(
                str(embedding_path),
                device=str(device),
                trust_remote_code=True,
                local_files_only=True,
            )
            embedder.eval()
            torch.cuda.synchronize(device)
            qwen_load_seconds = time.perf_counter() - qwen_load_started
            query_embeddings, query_usage = encode_texts(
                embedder,
                list(query_by_pair.values()),
                is_query=True,
                run_id=args.run_id,
                call_prefix="query",
                torch=torch,
            )
            # The private query text keys are distinct from passage keys, even when
            # a byte-identical string appears on both sides of the encoder.
            query_vector_by_pair = {
                pair_id: query_embeddings[query_by_pair[pair_id]] for pair_id in query_by_pair
            }
            passage_embeddings, passage_usage = encode_texts(
                embedder,
                all_passages,
                is_query=False,
                run_id=args.run_id,
                call_prefix="passage",
                torch=torch,
            )
            del embedder
            torch.cuda.empty_cache()
            torch.cuda.synchronize(device)
            qwen_encode_seconds = time.perf_counter() - qwen_load_started - qwen_load_seconds

            for relation_text in RELATION_TEXTS:
                require(relation_text in passage_embeddings, "relation embedding missing")
            model_load_started = time.perf_counter()
            gfm_model, gfm_config = load_model_from_pretrained(str(checkpoint))
            parameter_count = sum(parameter.numel() for parameter in gfm_model.parameters())
            require(parameter_count == EXPECTED_GFM_PARAMETERS, "G-reasoner parameter count mismatch")
            model_config = gfm_config["model_config"]
            require(int(model_config["entity_model"]["input_dim"]) == DIM and int(model_config["feat_dim"]) == DIM, "G-reasoner dimension mismatch")
            gfm_model.eval().to(device)
            torch.cuda.synchronize(device)
            gfm_load_seconds = time.perf_counter() - model_load_started

            pair_rows: dict[str, dict[str, Any]] = {}
            graph_size_counts = Counter()
            forward_seconds = []
            for pair_id in sorted(selected_pairs):
                graph_input = build_graph(
                    pair_id,
                    inputs,
                    table_texts,
                    mapping_texts,
                    passage_embeddings,
                    {text: passage_embeddings[text] for text in RELATION_TEXTS},
                    Data,
                    torch,
                )
                graph, _, graph_meta = graph_input
                require(graph_meta["start_seed_count"] == 2, "all table endpoints must be seeded")
                require(graph_meta["edge_count"] == graph_meta["mapping_count"] * 4, "reified FK graph edge count mismatch")
                query_vector = query_vector_by_pair[pair_id]
                scored = score_pair(
                    pair_id,
                    inputs,
                    query_by_pair,
                    mapping_texts,
                    passage_embeddings,
                    query_vector,
                    graph_input,
                    gfm_model,
                    device,
                    torch,
                )
                torch.cuda.synchronize(device)
                forward_seconds.append(scored["g_reasoner_forward_seconds"])
                pair_rows[pair_id] = scored
                graph_size_counts[str(graph_meta["mapping_count"])] += 1
                prediction_stream.write(json.dumps(scored, ensure_ascii=False, sort_keys=True) + "\n")
                prediction_stream.flush()
                if time.perf_counter() - started > MAX_WALL_SECONDS:
                    raise TimeoutError(f"wall time exceeded {MAX_WALL_SECONDS} seconds")

            peak_gpu_bytes = int(torch.cuda.max_memory_allocated(device))
            peak_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
            wall_seconds = time.perf_counter() - started
            cpu_seconds = time.process_time() - cpu_started
            if peak_gpu_bytes > MAX_GPU_BYTES:
                raise MemoryError(f"GPU allocation exceeded {MAX_GPU_BYTES} bytes: {peak_gpu_bytes}")
            if peak_rss_bytes > MAX_RSS_BYTES:
                raise MemoryError(f"RSS exceeded {MAX_RSS_BYTES} bytes: {peak_rss_bytes}")
            if wall_seconds > MAX_WALL_SECONDS:
                raise TimeoutError(f"wall time exceeded {MAX_WALL_SECONDS} seconds")

            run_meta = {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "mode": args.mode,
                "source_commit": source_commit,
                "config_sha256": sha256_file(args.config),
                "input_sha256": attempt["input_sha256"],
                "checkpoint_sha256": {"model.pth": EXPECTED_GFM_MODEL_SHA256, "config.json": EXPECTED_GFM_CONFIG_SHA256},
                "qwen_snapshot_sha256": qwen_hashes,
                "environment": versions,
                "device": torch.cuda.get_device_name(device),
                "cuda_visible_devices": visible_gpu,
                "pairs_scored": len(selected_pairs),
                "candidate_count_scored": sum(len(inputs["items"][pair_id]["mappings"]) for pair_id in selected_pairs),
                "g_reasoner_forward_count": len(selected_pairs),
                "g_reasoner_forward_seconds_total": round(sum(forward_seconds), 6),
                "qwen_embedding_usage": {
                    "query": query_usage,
                    "passage": passage_usage,
                    "total_input_tokens": query_usage["input_tokens"] + passage_usage["input_tokens"],
                    "total_output_tokens": 0,
                },
                "graph_candidate_count_histogram": dict(sorted(graph_size_counts.items(), key=lambda item: int(item[0]))),
                "qwen_load_seconds": round(qwen_load_seconds, 6),
                "qwen_encode_seconds": round(qwen_encode_seconds, 6),
                "g_reasoner_load_seconds": round(gfm_load_seconds, 6),
                "wall_seconds": round(wall_seconds, 6),
                "cpu_seconds": round(cpu_seconds, 6),
                "peak_gpu_allocated_bytes": peak_gpu_bytes,
                "peak_rss_bytes": peak_rss_bytes,
            }
            if args.mode == "smoke":
                result = {
                    **run_meta,
                    "status": "SMOKE_PASS",
                    "smoke_questions": 5,
                    "full_question_overlap": 0,
                    "finite_score_rows": len(pair_rows),
                    "primary_metrics_included": False,
                    "privacy": {"contains_question_text": False, "contains_case_or_mapping_ids": False, "contains_raw_model_outputs": False},
                }
            else:
                metrics = create_full_summary(inputs, pair_rows, run_meta)
                result = metrics
            write_json(args.output_dir / "aggregate_summary.json", result)
            write_json(args.output_dir / "run_manifest.json", {
                **run_meta,
                "status": result["status"],
                "privacy": result["privacy"],
                "private_predictions_sha256": sha256_file(private_prediction_path),
                "raw_input_paths_uploaded": False,
            })
            return result
        except Exception as exc:
            write_json(args.output_dir / "failure.json", {
                "experiment_id": EXPERIMENT_ID,
                "run_id": args.run_id,
                "mode": args.mode,
                "status": "FAILED",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "source_commit": source_commit,
                "input_sha256": attempt["input_sha256"],
                "partial_prediction_count": sum(1 for _ in private_prediction_path.open("r", encoding="utf-8")),
            })
            raise


def main() -> None:
    args = parse_args()
    result = run(args)
    print(json.dumps({key: value for key, value in result.items() if key not in {"per_anonymous_database"}}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
