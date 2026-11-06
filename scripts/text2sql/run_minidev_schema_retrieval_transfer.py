#!/usr/bin/env python3
"""Run the frozen Mini-Dev schema-retrieval transfer screen locally."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MAX_THREADS = 8
MAX_WALL_SECONDS = 1200
MAX_CPU_SECONDS = 900
MAX_GPU_BYTES = 8 * 1024**3
MAX_RSS_BYTES = 8 * 1024**3
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20261106
EXPERIMENT_ID = "gfm_minidev_schema_retrieval_transfer_20261106_01"
QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
    "Query: "
)
RELATION_TEXTS = (
    "Relation: table contains column.",
    "Relation: column belongs to table.",
)
CONDITIONS = ("D0", "G1", "G3")
EXPECTED = {
    "python": "3.12.15",
    "torch": "2.8.0",
    "torch_geometric": "2.6.1",
    "transformers": "4.56.1",
    "sentence_transformers": "5.1.1",
    "g_reasoner_parameters": 34_640_897,
    "g_reasoner_weights_sha256": "2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d",
    "g_reasoner_config_sha256": "75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5",
    "qwen_weight_sha256": "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd",
    "qwen_manifest_sha256": "b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68",
}

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


@dataclass(frozen=True)
class SchemaNode:
    node_id: str
    db_id: str
    node_type: str
    text: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Required local embedding helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_status() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def resources() -> dict[str, Any]:
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nvidia_smi": command_output([
            "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]),
        "free_h": command_output(["free", "-h"]),
        "nproc": command_output(["nproc"]),
    }


def rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def check_budget(wall_start: float, cpu_start: float, torch: Any, device: Any) -> None:
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    gpu = int(torch.cuda.max_memory_allocated(device))
    rss = rss_bytes()
    require(wall <= MAX_WALL_SECONDS, f"Wall budget exceeded: {wall:.1f}s")
    require(cpu <= MAX_CPU_SECONDS, f"CPU budget exceeded: {cpu:.1f}s")
    require(gpu <= MAX_GPU_BYTES, f"GPU allocation exceeded: {gpu / 1024**3:.2f} GiB")
    require(rss <= MAX_RSS_BYTES, f"Process RSS exceeded: {rss / 1024**3:.2f} GiB")


def read_private_inputs(prepared_dir: Path, mode: str) -> tuple[list[dict[str, Any]], list[SchemaNode], list[dict[str, Any]], dict[str, Any]]:
    audit_path = prepared_dir / "cpu_label_audit.json"
    question_path = prepared_dir / "questions_label_free.jsonl"
    node_path = prepared_dir / "schema_nodes_private.jsonl"
    schema_path = prepared_dir / "schema_manifest_private.json"
    for path in (audit_path, question_path, node_path, schema_path):
        require(path.is_file(), "A prepared private experiment input is missing")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    require(audit.get("status") == "LABEL_GATE_PASS", "CPU label gate did not pass")
    require(audit.get("experiment_id") == EXPERIMENT_ID, "CPU audit belongs to a different experiment")
    require(audit.get("contains_raw_question_sql_database_names_or_row_results") is False, "Public-safety audit flag mismatch")
    questions = read_jsonl(question_path)
    raw_nodes = read_jsonl(node_path)
    nodes = [SchemaNode(**row) for row in raw_nodes]
    schemas = json.loads(schema_path.read_text(encoding="utf-8"))
    require(len(questions) == 500 and len({row["question_id"] for row in questions}) == 500, "Prepared question count or IDs are invalid")
    require(len(schemas) == 11, "Prepared schema count is invalid")
    require(len({node.node_id for node in nodes}) == len(nodes), "Duplicate schema node ID")
    require(all(node.node_type in {"table", "column"} for node in nodes), "Unknown node type")
    for schema in schemas:
        db_id = schema["db_id"]
        local_nodes = [node for node in nodes if node.db_id == db_id]
        require(local_nodes, "A database has no schema nodes")
        table_ids = {node.node_id for node in local_nodes if node.node_type == "table"}
        column_ids = {node.node_id for node in local_nodes if node.node_type == "column"}
        for column_index, (table_index, _column_name) in enumerate(schema["column_names_original"]):
            if int(table_index) < 0:
                continue
            require(f"table:{db_id}:{int(table_index)}" in table_ids, "Schema table node is missing")
            require(f"column:{db_id}:{column_index}" in column_ids, "Schema column node is missing")
    selected = [row for row in questions if bool(row["is_smoke"])] if mode == "smoke" else [row for row in questions if not bool(row["is_smoke"])]
    require(len(selected) == (5 if mode == "smoke" else 495), "Prepared split size differs from preregistration")
    if mode == "smoke":
        require(len({row["db_id"] for row in selected}) == 5, "Smoke does not cover five databases")
        require(audit["smoke_column_eligible_questions"] >= 4 and audit["smoke_table_labeled_questions"] == 5, "Smoke label gates failed")
    return selected, nodes, schemas, audit


def build_graphs(
    questions: list[dict[str, Any]], nodes: list[SchemaNode], schemas: list[dict[str, Any]], vectors: dict[str, Any],
    relation_vectors: dict[str, Any], Data: Any, torch: Any,
) -> tuple[dict[str, Any], dict[str, list[SchemaNode]], dict[str, dict[str, list[int]]]]:
    schema_by_db = {row["db_id"]: row for row in schemas}
    nodes_by_db: dict[str, list[SchemaNode]] = defaultdict(list)
    for node in nodes:
        nodes_by_db[node.db_id].append(node)
    graphs: dict[str, Any] = {}
    indexes: dict[str, dict[str, list[int]]] = {}
    for db_id in sorted({row["db_id"] for row in questions}):
        local_nodes = sorted(nodes_by_db[db_id], key=lambda node: (node.node_type != "table", node.node_id))
        index = {node.node_id: position for position, node in enumerate(local_nodes)}
        table_indexes = [position for position, node in enumerate(local_nodes) if node.node_type == "table"]
        column_indexes = [position for position, node in enumerate(local_nodes) if node.node_type == "column"]
        sources: list[int] = []
        targets: list[int] = []
        edge_types: list[int] = []
        for column_index, (table_index, _column_name) in enumerate(schema_by_db[db_id]["column_names_original"]):
            if int(table_index) < 0:
                continue
            table_id = f"table:{db_id}:{int(table_index)}"
            column_id = f"column:{db_id}:{column_index}"
            require(table_id in index and column_id in index, "Membership graph refers to a missing schema node")
            sources.extend((index[table_id], index[column_id]))
            targets.extend((index[column_id], index[table_id]))
            edge_types.extend((0, 1))
        require(len(sources) == len(targets) == len(edge_types) == 2 * len(column_indexes), "Membership graph is incomplete")
        graph = Data(
            x=torch.stack([vectors[node.text] for node in local_nodes]).float().contiguous(),
            edge_index=torch.tensor([sources, targets], dtype=torch.long),
            edge_type=torch.tensor(edge_types, dtype=torch.long),
            rel_attr=torch.stack([relation_vectors[text] for text in RELATION_TEXTS]).float().contiguous(),
            num_relations=2,
        )
        require(graph.num_nodes == len(local_nodes) and graph.num_edges == 2 * len(column_indexes), "Membership graph shape mismatch")
        graphs[db_id] = graph
        nodes_by_db[db_id] = local_nodes
        indexes[db_id] = {"table": table_indexes, "column": column_indexes}
    return graphs, nodes_by_db, indexes


def rank_ids(scores: Any, nodes: list[SchemaNode], indexes: list[int], torch: Any) -> list[str]:
    selected = [(float(scores[index]), nodes[index].node_id) for index in indexes]
    require(all(math.isfinite(score) for score, _node_id in selected), "Ranking contains a non-finite score")
    return [node_id for _score, node_id in sorted(selected, key=lambda item: (-item[0], item[1]))]


def metrics(
    questions: list[dict[str, Any]], predictions: dict[str, dict[str, Any]], labels: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, float]], dict[str, list[float]]]:
    table_values: dict[str, dict[str, float]] = {condition: {} for condition in CONDITIONS}
    column_values: dict[str, dict[str, float]] = {condition: {} for condition in CONDITIONS}
    db_metrics: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for question in questions:
        qid = question["question_id"]
        label = labels[qid]
        require(label["db_id"] == question["db_id"], "Label database differs from the question database")
        gold_tables = set(label["gold_table_ids"])
        gold_columns = set(label["gold_column_ids"])
        for condition in CONDITIONS:
            rankings = predictions[qid]["rankings"][condition]
            if gold_tables:
                for k in (5, 10):
                    value = len(set(rankings["table"][:k]) & gold_tables) / len(gold_tables)
                    db_metrics[question["db_id"]][condition][f"table_recall@{k}"].append(value)
                    if k == 10:
                        table_values[condition][qid] = value
            if label["column_eligible"]:
                require(gold_columns, "Column-eligible label has no physical columns")
                for k in (5, 10, 20):
                    value = len(set(rankings["column"][:k]) & gold_columns) / len(gold_columns)
                    db_metrics[question["db_id"]][condition][f"column_recall@{k}"].append(value)
                    if k == 10:
                        column_values[condition][qid] = value
                p10 = len(set(rankings["column"][:10]) & gold_columns) / min(10, len(rankings["column"]))
                db_metrics[question["db_id"]][condition]["column_precision@10"].append(p10)

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    aggregate: dict[str, Any] = {"query_macro": {}, "anonymous_database_aggregates": {}}
    for condition in CONDITIONS:
        per_metric: dict[str, list[float]] = defaultdict(list)
        for database in db_metrics.values():
            for metric_name, values in database[condition].items():
                per_metric[metric_name].extend(values)
        aggregate["query_macro"][condition] = {
            "table_recall@5": mean(per_metric.get("table_recall@5", [])),
            "table_recall@10": mean(list(table_values[condition].values())),
            "column_recall@5": mean(per_metric.get("column_recall@5", [])),
            "column_recall@10": mean(list(column_values[condition].values())),
            "column_recall@20": mean(per_metric.get("column_recall@20", [])),
            "column_precision@10": mean(per_metric.get("column_precision@10", [])),
            "table_labeled_question_count": len(table_values[condition]),
            "column_eligible_question_count": len(column_values[condition]),
        }
    for db_index, db_id in enumerate(sorted(db_metrics), start=1):
        aggregate["anonymous_database_aggregates"][f"db_{db_index:02d}"] = {
            condition: {key: mean(values) for key, values in db_metrics[db_id][condition].items()}
            for condition in CONDITIONS
        }
    deltas = {
        "G3_minus_D0_column_recall@10": [column_values["G3"][qid] - column_values["D0"][qid] for qid in column_values["G3"]],
        "G3_minus_G1_column_recall@10": [column_values["G3"][qid] - column_values["G1"][qid] for qid in column_values["G3"]],
        "G3_minus_D0_table_recall@10": [table_values["G3"][qid] - table_values["D0"][qid] for qid in table_values["G3"]],
    }
    delta_by_qid = {
        "G3_minus_D0_column_recall@10": dict(zip(column_values["G3"], deltas["G3_minus_D0_column_recall@10"], strict=True)),
        "G3_minus_G1_column_recall@10": dict(zip(column_values["G3"], deltas["G3_minus_G1_column_recall@10"], strict=True)),
        "G3_minus_D0_table_recall@10": dict(zip(table_values["G3"], deltas["G3_minus_D0_table_recall@10"], strict=True)),
    }
    aggregate["rescue_damage"] = {}
    for left_name, right_name in (("G3", "D0"), ("G3", "G1")):
        common_ids = column_values[left_name].keys() & column_values[right_name].keys()
        differences = [column_values[left_name][qid] - column_values[right_name][qid] for qid in common_ids]
        aggregate["rescue_damage"][f"{left_name}_vs_{right_name}_column_recall@10"] = {
            "rescued_questions": sum(value > 0 for value in differences),
            "damaged_questions": sum(value < 0 for value in differences),
            "unchanged_questions": sum(value == 0 for value in differences),
        }
    return aggregate, delta_by_qid, deltas


def cluster_bootstrap(questions: list[dict[str, Any]], delta_by_qid: dict[str, float]) -> dict[str, Any]:
    import numpy as np

    grouped: dict[str, list[float]] = defaultdict(list)
    for question in questions:
        qid = question["question_id"]
        if qid in delta_by_qid:
            grouped[question["db_id"]].append(float(delta_by_qid[qid]))
    require(len(grouped) == 11 and all(values for values in grouped.values()), "Bootstrap requires 11 represented database clusters")
    cluster_keys = sorted(grouped)
    cluster_sums = np.asarray([sum(grouped[key]) for key in cluster_keys], dtype=np.float64)
    cluster_counts = np.asarray([len(grouped[key]) for key in cluster_keys], dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indexes = rng.integers(0, len(cluster_keys), size=(BOOTSTRAP_DRAWS, len(cluster_keys)))
    sampled_means = cluster_sums[indexes].sum(axis=1) / cluster_counts[indexes].sum(axis=1)
    low, high = np.quantile(sampled_means, [0.025, 0.975])
    return {
        "unit": "paired database-cluster bootstrap; query-macro statistic within draw",
        "database_clusters": len(cluster_keys),
        "draws": BOOTSTRAP_DRAWS,
        "seed": BOOTSTRAP_SEED,
        "observed_query_macro_delta": float(cluster_sums.sum() / cluster_counts.sum()),
        "ci_95_percentile": [float(low), float(high)],
        "database_level_delta_means": [float(cluster_sums[i] / cluster_counts[i]) for i in range(len(cluster_keys))],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--embedding-manifest", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--smoke-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config.get("experiment_id") == EXPERIMENT_ID, "Experiment config ID mismatch")
    require(config["feature_contract"]["query_instruction"] == QUERY_INSTRUCTION, "Query instruction differs from preregistration")
    require(tuple(config["feature_contract"]["relation_texts"]) == RELATION_TEXTS, "Relation text differs from preregistration")
    require(args.run_id == config["run_ids"][args.mode], "Run ID differs from preregistration")
    commit = git_commit()
    require(commit == args.expected_commit and not git_status(), "Repository commit or cleanliness differs from the registered source")
    require(args.device == "cuda:0" and os.environ.get("CUDA_VISIBLE_DEVICES") == "0", "Use the preregistered physical GPU 0 only")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "Offline local model mode is required")
    require(args.config.resolve(strict=True).is_file(), "Frozen config is missing")
    smoke_summary: dict[str, Any] | None = None
    if args.mode == "full":
        require(args.smoke_summary is not None and args.smoke_summary.is_file(), "Full run requires a passing Smoke summary")
        smoke_summary = json.loads(args.smoke_summary.read_text(encoding="utf-8"))
        require(smoke_summary.get("status") == "smoke_passed" and smoke_summary.get("question_count") == 5, "Smoke gate did not pass")
        require(smoke_summary.get("source_commit") == commit, "Smoke and Full commits differ")
        require(smoke_summary.get("config_sha256") == sha256_file(args.config), "Smoke and Full configs differ")
    require(not args.output_dir.exists(), "Output directory already exists; refusing overwrite")
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": commit,
        "source_tree": subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip(),
        "config_sha256": sha256_file(args.config),
        "prepared_dir": str(args.prepared_dir.resolve(strict=True)),
        "embedding_model": str(args.embedding_model.resolve(strict=True)),
        "embedding_manifest": str(args.embedding_manifest.resolve(strict=True)),
        "checkpoint": str(args.checkpoint.resolve(strict=True)),
        "command_argv": [sys.executable, *sys.argv],
        "resources_preflight": resources(),
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt)
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        import torch
        import torch_geometric
        import transformers
        import sentence_transformers
        from sentence_transformers import SentenceTransformer
        from torch_geometric.data import Data
        from gfmrag.utils.util import load_model_from_pretrained

        actual_versions = {
            "python": platform.python_version(),
            "torch": str(torch.__version__).split("+", 1)[0],
            "torch_geometric": str(torch_geometric.__version__),
            "transformers": str(transformers.__version__),
            "sentence_transformers": str(sentence_transformers.__version__),
        }
        expected_versions = {key: value for key, value in EXPECTED.items() if key in actual_versions}
        require(actual_versions == expected_versions, "Model environment versions differ from the frozen environment")
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "Exactly one visible CUDA device is required")
        device = torch.device(args.device)
        torch.cuda.set_device(device)
        torch.manual_seed(BOOTSTRAP_SEED)
        torch.set_num_threads(MAX_THREADS)
        torch.set_num_interop_threads(MAX_THREADS)
        torch.cuda.reset_peak_memory_stats(device)

        selected_questions, nodes, schemas, audit = read_private_inputs(args.prepared_dir.resolve(strict=True), args.mode)
        if smoke_summary is not None:
            require(smoke_summary.get("prepared_audit_sha256") == sha256_file(args.prepared_dir / "cpu_label_audit.json"), "Smoke and Full prepared inputs differ")
        shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
        require(shared_root is not None and (Path(shared_root) / "api_usage_ledger.py").is_file(), "Shared local token ledger is unavailable")
        qwen_dir = args.embedding_model.resolve(strict=True)
        embedding_manifest = args.embedding_manifest.resolve(strict=True)
        checkpoint = args.checkpoint.resolve(strict=True)
        require(sha256_file(checkpoint / "model.pth") == EXPECTED["g_reasoner_weights_sha256"], "G-reasoner checkpoint hash mismatch")
        require(sha256_file(checkpoint / "config.json") == EXPECTED["g_reasoner_config_sha256"], "G-reasoner config hash mismatch")
        pilot = load_module(SCRIPT_DIR / "run_p0_fk_mapping_model_proxy_rank_pilot.py", "minidev_embedding_ledger_helpers")
        qwen_hashes = pilot.validate_qwen_snapshot(qwen_dir)
        require(qwen_hashes["model.safetensors"] == EXPECTED["qwen_weight_sha256"], "Qwen embedding weights hash mismatch")
        require(sha256_file(embedding_manifest) == EXPECTED["qwen_manifest_sha256"], "Pinned Qwen file manifest hash mismatch")

        embedder = SentenceTransformer(str(qwen_dir), device=str(device), trust_remote_code=True, local_files_only=True)
        embedder.eval()
        passage_texts = [node.text for node in nodes] + list(RELATION_TEXTS)
        query_vectors, query_usage = pilot.encode_texts(
            embedder,
            [row["question"] for row in selected_questions],
            is_query=True,
            run_id=args.run_id,
            call_prefix="query",
            torch=torch,
        )
        passage_vectors, passage_usage = pilot.encode_texts(
            embedder,
            passage_texts,
            is_query=False,
            run_id=args.run_id,
            call_prefix="passage",
            torch=torch,
        )
        query_vector_by_id = {row["question_id"]: query_vectors[row["question"]] for row in selected_questions}
        del embedder
        torch.cuda.empty_cache()
        torch.cuda.synchronize(device)
        graphs, nodes_by_db, node_type_indexes = build_graphs(
            selected_questions,
            nodes,
            schemas,
            passage_vectors,
            {text: passage_vectors[text] for text in RELATION_TEXTS},
            Data,
            torch,
        )
        model, model_config = load_model_from_pretrained(str(checkpoint))
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        require(parameter_count == EXPECTED["g_reasoner_parameters"], "G-reasoner parameter count mismatch")
        inner_config = model_config["model_config"]
        require(int(inner_config["entity_model"]["input_dim"]) == 1024 and int(inner_config["feat_dim"]) == 1024, "G-reasoner embedding dimensions mismatch")
        model.eval().to(device)

        predictions: dict[str, dict[str, Any]] = {}
        forward_counts = {"G1": 0, "G3": 0}
        for number, question in enumerate(selected_questions, start=1):
            qid = question["question_id"]
            db_id = question["db_id"]
            local_nodes = nodes_by_db[db_id]
            graph = graphs[db_id]
            query_vector = query_vector_by_id[qid]
            scores_dense = torch.mv(graph.x, query_vector.float())
            require(bool(torch.isfinite(scores_dense).all()), "Dense cosine emitted a non-finite score")
            dense = {
                node_type: rank_ids(scores_dense, local_nodes, node_type_indexes[db_id][node_type], torch)
                for node_type in ("table", "column")
            }
            id_to_index = {node.node_id: index for index, node in enumerate(local_nodes)}
            predictions_for_question: dict[str, Any] = {}
            for condition, top_k in (("G1", 1), ("G3", 3)):
                anchors = {node_type: dense[node_type][:top_k] for node_type in ("table", "column")}
                require(all(len(ids) == top_k for ids in anchors.values()), "A database has too few nodes for the frozen anchor setting")
                seed_indexes = [id_to_index[node_id] for node_type in ("table", "column") for node_id in anchors[node_type]]
                graph_device = graph.clone().to(device)
                for key in ("x", "edge_index", "edge_type", "rel_attr"):
                    require(torch.equal(getattr(graph_device, key).cpu(), getattr(graph, key).cpu()), "Graph changed during device transfer")
                start_mask = torch.zeros((1, graph.num_nodes), dtype=torch.float32)
                start_mask[0, torch.tensor(seed_indexes, dtype=torch.long)] = 1.0
                batch = {
                    "question_embeddings": query_vector.reshape(1, -1).to(device),
                    "start_nodes_mask": start_mask.to(device),
                }
                with torch.inference_mode():
                    propagated = model(graph_device, batch)
                torch.cuda.synchronize(device)
                require(propagated.ndim == 2 and tuple(propagated.shape) == (1, graph.num_nodes), "G-reasoner score shape mismatch")
                propagated = propagated.detach().float().cpu()[0]
                require(bool(torch.isfinite(propagated).all()), "G-reasoner emitted non-finite scores")
                predictions_for_question[condition] = {
                    "rankings": {
                        node_type: rank_ids(propagated, local_nodes, node_type_indexes[db_id][node_type], torch)
                        for node_type in ("table", "column")
                    },
                    "anchors": anchors,
                }
                forward_counts[condition] += 1
            predictions[qid] = {
                "question_id": qid,
                "db_id": db_id,
                "rankings": {"D0": dense, "G1": predictions_for_question["G1"]["rankings"], "G3": predictions_for_question["G3"]["rankings"]},
                "anchors": {"G1": predictions_for_question["G1"]["anchors"], "G3": predictions_for_question["G3"]["anchors"]},
            }
            if number % 100 == 0 or number == len(selected_questions):
                print(json.dumps({"stage": "ranking_progress", "questions_done": number, "questions_total": len(selected_questions), "wall_seconds": round(time.perf_counter() - wall_start, 2), "rss_gib": round(rss_bytes() / 1024**3, 3)}, ensure_ascii=False), flush=True)
            check_budget(wall_start, cpu_start, torch, device)

        # Freeze label-free rankings to disk before opening the private SQL-derived labels.
        ranking_path = args.output_dir / "predictions_label_free_private.jsonl"
        with ranking_path.open("x", encoding="utf-8") as stream:
            for qid in sorted(predictions):
                stream.write(json.dumps(predictions[qid], ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        os.chmod(ranking_path, 0o600)
        label_rows = read_jsonl(args.prepared_dir / "gold_labels_private.jsonl")
        labels = {row["question_id"]: row for row in label_rows if row["question_id"] in predictions}
        require(set(labels) == set(predictions), "Gold label coverage differs from ranked question IDs")
        aggregate, delta_by_qid, _deltas = metrics(selected_questions, predictions, labels)
        if args.mode == "smoke":
            require(len(selected_questions) == 5 and len({row["db_id"] for row in selected_questions}) == 5, "Smoke split shape mismatch")
            require(sum(row["column_eligible"] for row in labels.values()) >= 4, "Smoke column eligibility gate failed")
            require(forward_counts == {"G1": 5, "G3": 5}, "Smoke G-reasoner forward count mismatch")
            status = "smoke_passed"
        else:
            require(len(selected_questions) == 495 and len({row["db_id"] for row in selected_questions}) == 11, "Full split shape mismatch")
            bootstrap = cluster_bootstrap(selected_questions, delta_by_qid["G3_minus_D0_column_recall@10"])
            aggregate["g3_minus_d0_column_recall@10_database_cluster_bootstrap"] = bootstrap
            point = aggregate["query_macro"]
            delta_g3_d0 = point["G3"]["column_recall@10"] - point["D0"]["column_recall@10"]
            delta_g3_g1 = point["G3"]["column_recall@10"] - point["G1"]["column_recall@10"]
            delta_table = point["G3"]["table_recall@10"] - point["D0"]["table_recall@10"]
            criteria = {
                "g3_minus_d0_column_recall@10_at_least_2pp": 100 * delta_g3_d0 >= 2.0,
                "database_cluster_bootstrap_lower_bound_above_zero": bootstrap["ci_95_percentile"][0] > 0,
                "g3_minus_g1_column_recall@10_at_least_1pp": 100 * delta_g3_g1 >= 1.0,
                "table_recall@10_loss_no_worse_than_1pp": 100 * delta_table >= -1.0,
            }
            aggregate["transfer_gate"] = {
                "g3_minus_d0_column_recall@10_pp": 100 * delta_g3_d0,
                "g3_minus_d0_ci_95_lower_pp": 100 * bootstrap["ci_95_percentile"][0],
                "g3_minus_g1_column_recall@10_pp": 100 * delta_g3_g1,
                "g3_minus_d0_table_recall@10_pp": 100 * delta_table,
                "criteria": criteria,
                "status": "TRANSFER_SIGNAL_PASS" if all(criteria.values()) else "NO_GO",
            }
            status = "full_complete"

        with (args.output_dir / "predictions_with_sql_labels_private.jsonl").open("x", encoding="utf-8") as stream:
            for qid in sorted(predictions):
                enriched = dict(predictions[qid])
                enriched["gold"] = {
                    "table_ids": labels[qid]["gold_table_ids"],
                    "column_ids": labels[qid]["gold_column_ids"],
                    "column_eligible": labels[qid]["column_eligible"],
                    "label_status": labels[qid]["label_status"],
                }
                stream.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        os.chmod(args.output_dir / "predictions_with_sql_labels_private.jsonl", 0o600)
        peak_gpu = int(torch.cuda.max_memory_allocated(device))
        peak_rss = rss_bytes()
        check_budget(wall_start, cpu_start, torch, device)
        summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": status,
            "question_count": len(selected_questions),
            "database_count": len({row["db_id"] for row in selected_questions}),
            "column_eligible_question_count": sum(row["column_eligible"] for row in labels.values()),
            "source_commit": commit,
            "source_tree": attempt["source_tree"],
            "config_sha256": attempt["config_sha256"],
            "prepared_audit_sha256": sha256_file(args.prepared_dir / "cpu_label_audit.json"),
            "prepared_questions_sha256": sha256_file(args.prepared_dir / "questions_label_free.jsonl"),
            "prepared_schema_nodes_sha256": sha256_file(args.prepared_dir / "schema_nodes_private.jsonl"),
            "metrics": aggregate,
            "embedding_usage": {
                "query": query_usage,
                "passages_and_relations": passage_usage,
                "input_tokens": query_usage["input_tokens"] + passage_usage["input_tokens"],
                "output_tokens": 0,
            },
            "resources": {
                "gpu_name": torch.cuda.get_device_name(device),
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "peak_gpu_allocated_bytes": peak_gpu,
                "peak_process_rss_bytes": peak_rss,
                "process_cpu_seconds": time.process_time() - cpu_start,
                "wall_seconds": time.perf_counter() - wall_start,
                "g_reasoner_forward_count": sum(forward_counts.values()),
            },
            "models": {
                "qwen_embedding_snapshot": "Qwen3-Embedding-0.6B",
                "qwen_weight_sha256": EXPECTED["qwen_weight_sha256"],
                "qwen_manifest_sha256": EXPECTED["qwen_manifest_sha256"],
                "qwen_file_hashes": qwen_hashes,
                "g_reasoner_parameter_count": parameter_count,
                "g_reasoner_weight_sha256": EXPECTED["g_reasoner_weights_sha256"],
                "g_reasoner_config_sha256": EXPECTED["g_reasoner_config_sha256"],
            },
            "environment": actual_versions,
            "external_api_requests": 0,
            "model_review_used_for_labels": False,
        }
        write_json(args.output_dir / "aggregate_summary.json", summary)
        print(json.dumps({
            "stage": "run_complete",
            "run_id": args.run_id,
            "status": status,
            "question_count": summary["question_count"],
            "column_eligible_question_count": summary["column_eligible_question_count"],
            "query_macro": aggregate["query_macro"],
            "transfer_gate": aggregate.get("transfer_gate"),
            "local_input_tokens": summary["embedding_usage"]["input_tokens"],
            "peak_gpu_allocated_bytes": peak_gpu,
            "peak_process_rss_bytes": peak_rss,
        }, ensure_ascii=False), flush=True)
        return summary
    except Exception as error:
        write_json(args.output_dir / "failure_manifest.json", {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "failed",
            "source_commit": commit,
            "config_sha256": sha256_file(args.config),
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "elapsed_wall_seconds": time.perf_counter() - wall_start,
            "elapsed_process_cpu_seconds": time.process_time() - cpu_start,
        })
        raise


def main() -> None:
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
