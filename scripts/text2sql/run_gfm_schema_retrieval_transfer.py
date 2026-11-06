#!/usr/bin/env python3
"""Run the preregistered frozen G-reasoner schema-retrieval transfer screen.

Question IDs, candidate rankings, Gold labels, and per-question metrics are
written only under the private output directory. The public summary contains
anonymous aggregates only.
"""
from __future__ import annotations

import argparse
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
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_THREADS = 8
MAX_WALL_SECONDS = 1200
MAX_CPU_SECONDS = 900
MAX_GPU_BYTES = 8 * 1024**3
MAX_RSS_BYTES = 8 * 1024**3
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20261106
EXPECTED_COUNTS = {
    "questions": 1534,
    "databases": 11,
    "nodes": 873,
    "tables": 75,
    "columns": 798,
    "column_eligible": 1460,
}
EXPECTED_INPUT_HASHES = {
    "question_sha256": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
    "schema_sha256": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
    "p0_audit_sha256": "0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf",
    "gold_labels_sha256": "1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525",
    "qwen_manifest_sha256": "b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68",
}
EXPECTED_R1_TEXT_SHA256 = "73c59126b931fb72b7c09ba06de76327057e32832e2aeef0c8175b8956ed3e3c"
EXPECTED_GFM_MODEL_SHA256 = "2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d"
EXPECTED_GFM_CONFIG_SHA256 = "75d14b97d6a077ebc17b09a21170a3d9272251db59f7ac8cc853165efb2efd5"
EXPECTED_GFM_PARAMETERS = 34_640_897
EXPECTED_QWEN_WEIGHT_SHA256 = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
EXPERIMENT_ID = "gfm_schema_retrieval_transfer_20261106_01"
QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
    "Query: "
)
RELATION_TEXTS = (
    "Relation: table contains column.",
    "Relation: column belongs to table.",
)
CONDITION_NAMES = ("D0", "G1", "G3")

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load project helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "configs/text2sql/gfm_schema_retrieval_transfer_20261106.json")
    parser.add_argument("--legacy-root", type=Path, default=Path("/mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014"))
    parser.add_argument("--dataset-root", type=Path, default=Path("/mnt/liansp3/sources/datasets/bird/dev"))
    parser.add_argument("--embedding-model", type=Path, default=Path("/mnt/liansp3/sources/models/qwen3-embedding-0.6b"))
    parser.add_argument("--checkpoint", type=Path, default=Path("/mnt/liansp3/sources/models/g-reasoner-34m"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--smoke-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else f"unavailable: {result.stderr.strip()}"


def current_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def worktree_status() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"], check=True, capture_output=True, text=True
    ).stdout.strip()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def resource_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nvidia_smi": command_output(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]),
        "free_h": command_output(["free", "-h"]),
        "nproc": command_output(["nproc"]),
        "disk": command_output(["df", "-h", str(REPO_ROOT)]),
    }


def current_rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def assert_budget(start_wall: float, start_cpu: float, torch: Any, device: Any) -> None:
    wall = time.perf_counter() - start_wall
    cpu = time.process_time() - start_cpu
    rss = current_rss_bytes()
    gpu = int(torch.cuda.max_memory_allocated(device))
    if wall > MAX_WALL_SECONDS:
        raise TimeoutError(f"Wall budget exceeded: {wall:.1f}s > {MAX_WALL_SECONDS}s")
    if cpu > MAX_CPU_SECONDS:
        raise TimeoutError(f"CPU budget exceeded: {cpu:.1f}s > {MAX_CPU_SECONDS}s")
    if rss > MAX_RSS_BYTES:
        raise MemoryError(f"RSS budget exceeded: {rss / 1024**3:.2f} GiB > 8 GiB")
    if gpu > MAX_GPU_BYTES:
        raise MemoryError(f"GPU allocation exceeded: {gpu / 1024**3:.2f} GiB > 8 GiB")


def prepare_helpers(legacy_root: Path, dataset_root: Path, embedding_model: Path) -> tuple[Any, Any, Any]:
    p15 = load_module(REPO_ROOT / "scripts/text2sql/run_p1_5_diagnostics.py", "p1_5_for_gfm_transfer")
    p2b = load_module(REPO_ROOT / "scripts/text2sql/run_p2b_values_ablation.py", "p2b_for_gfm_transfer")
    common = p15.load_p1_support(legacy_root.resolve(strict=True), dataset_root.resolve(strict=True), embedding_model.resolve(strict=True))
    return p15, p2b, common


def validate_frozen_inputs(common: Any, dataset_root: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any], Any, dict[str, str]]:
    hashes = common.verify_frozen_files()
    actual_hashes = {
        "question_sha256": hashes["sha256"]["questions"],
        "schema_sha256": hashes["sha256"]["schema"],
        "p0_audit_sha256": hashes["sha256"]["p0_audit"],
        "gold_labels_sha256": hashes["sha256"]["gold_labels"],
        "qwen_manifest_sha256": hashes["model_manifest_sha256"],
    }
    require(actual_hashes == EXPECTED_INPUT_HASHES, f"Frozen input hashes differ: {actual_hashes}")
    require(actual_hashes["question_sha256"] == config["data"]["question_sha256"], "Question hash differs from config")
    require(actual_hashes["schema_sha256"] == config["data"]["schema_sha256"], "Schema hash differs from config")
    with (dataset_root / "dev.json").open("r", encoding="utf-8") as stream:
        raw_questions = json.load(stream)
    with (dataset_root / "dev_tables.json").open("r", encoding="utf-8") as stream:
        schemas = json.load(stream)
    questions = [
        {"question_id": int(row["question_id"]), "db_id": str(row["db_id"]), "text": str(row["question"])}
        for row in raw_questions
    ]
    require(len(questions) == EXPECTED_COUNTS["questions"], "Unexpected question count")
    require(len({row["question_id"] for row in questions}) == len(questions), "Duplicate question IDs")
    require(len(schemas) == EXPECTED_COUNTS["databases"], "Unexpected database count")
    original_records = common._build_schema_nodes(schemas)
    require(len(original_records) == EXPECTED_COUNTS["nodes"], "Unexpected R0 candidate node count")
    return questions, original_records, schemas, actual_hashes


def build_r1_nodes(original_records: list[dict[str, Any]], p2b: Any, common: Any, tokenizer: Any) -> tuple[list[Any], dict[str, Any]]:
    r0_nodes = [
        common.SchemaNode(
            node_id=row["node_id"],
            db_id=row["db_id"],
            node_type=row["node_type"],
            text=row["text"],
            token_count=len(tokenizer.encode(row["text"], add_special_tokens=False)),
        )
        for row in original_records
    ]
    r0_nodes.sort(key=lambda node: node.node_type != "table")
    r1, meta = p2b.build_r1_nodes({"nodes": r0_nodes}, common, tokenizer)
    require(meta["nodes"] == EXPECTED_COUNTS["nodes"], "Unexpected R1 candidate count")
    require(sum(node.node_type == "table" for node in r1) == EXPECTED_COUNTS["tables"], "Unexpected R1 table count")
    require(sum(node.node_type == "column" for node in r1) == EXPECTED_COUNTS["columns"], "Unexpected R1 column count")
    require(meta["columns_with_values_removed"] == 278, "Values removal count differs from the audited R1 view")
    require(meta["r1_schema_text_sequence_sha256"] == EXPECTED_R1_TEXT_SHA256, "R1 ordered schema text hash mismatch")
    require(meta["text_differences_only_in_column_values"], "R1 changed fields other than Values")
    return r1, meta


def select_questions(questions: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "full":
        return questions
    db_id = sorted({row["db_id"] for row in questions})[0]
    selected = [row for row in questions if row["db_id"] == db_id][:5]
    require(len(selected) == 5, "Smoke could not select five questions from the first database")
    return selected


def build_database_graphs(
    questions: list[dict[str, Any]], nodes: list[Any], schemas: list[dict[str, Any]],
    vectors: dict[str, Any], relation_vectors: dict[str, Any], Data: Any, torch: Any,
) -> tuple[dict[str, Any], dict[str, list[Any]], dict[str, dict[str, list[int]]]]:
    schema_by_db = {str(row["db_id"]): row for row in schemas}
    nodes_by_db: dict[str, list[Any]] = defaultdict(list)
    for node in nodes:
        nodes_by_db[node.db_id].append(node)
    graphs: dict[str, Any] = {}
    type_indexes: dict[str, dict[str, list[int]]] = {}
    for db_id in sorted({row["db_id"] for row in questions}):
        db_nodes = nodes_by_db[db_id]
        require(db_nodes and all(node.db_id == db_id for node in db_nodes), "Database node partition is invalid")
        require([node.node_type for node in db_nodes] == sorted([node.node_type for node in db_nodes], key=lambda value: value != "table"), "Graph nodes are not type-ordered")
        index_by_node_id = {node.node_id: index for index, node in enumerate(db_nodes)}
        table_indexes = [index for index, node in enumerate(db_nodes) if node.node_type == "table"]
        column_indexes = [index for index, node in enumerate(db_nodes) if node.node_type == "column"]
        schema = schema_by_db[db_id]
        table_names = schema["table_names_original"]
        column_names = schema["column_names_original"]
        sources: list[int] = []
        targets: list[int] = []
        edge_types: list[int] = []
        for column_index, (table_index, _column_name) in enumerate(column_names):
            if int(table_index) < 0:
                continue
            table_node_id = f"table:{db_id}:{int(table_index)}"
            column_node_id = f"column:{db_id}:{column_index}"
            if table_node_id not in index_by_node_id or column_node_id not in index_by_node_id:
                continue
            table_node = index_by_node_id[table_node_id]
            column_node = index_by_node_id[column_node_id]
            sources.extend((table_node, column_node))
            targets.extend((column_node, table_node))
            edge_types.extend((0, 1))
        require(len(sources) == len(targets) == len(edge_types), "Membership graph edge arrays differ")
        require(len(sources) == 2 * len(column_indexes), "Not every physical column has two membership edges")
        graph = Data(
            x=torch.stack([vectors[node.text] for node in db_nodes]).float().contiguous(),
            edge_index=torch.tensor([sources, targets], dtype=torch.long),
            edge_type=torch.tensor(edge_types, dtype=torch.long),
            rel_attr=torch.stack([relation_vectors[text] for text in RELATION_TEXTS]).float().contiguous(),
            num_relations=2,
        )
        require(graph.num_nodes == len(db_nodes), "Graph node count mismatch")
        require(graph.num_edges == 2 * len(column_indexes), "Graph edge count mismatch")
        graphs[db_id] = graph
        type_indexes[db_id] = {"table": table_indexes, "column": column_indexes}
    return graphs, nodes_by_db, type_indexes


def ranked_node_ids(scores: Any, nodes: list[Any], indexes: list[int]) -> list[str]:
    entries = [(float(scores[index]), nodes[index].node_id) for index in indexes]
    require(all(math.isfinite(score) for score, _ in entries), "Ranking contains non-finite scores")
    return [node_id for _score, node_id in sorted(entries, key=lambda item: (-item[0], item[1]))]


def run_g_reasoner(model: Any, graph: Any, query: Any, start_indexes: list[int], device: Any, torch: Any) -> tuple[Any, float]:
    moved = graph.clone().to(device)
    for key in ("x", "edge_index", "edge_type", "rel_attr"):
        if not torch.equal(getattr(moved, key).cpu(), getattr(graph, key).cpu()):
            raise RuntimeError(f"Graph changed during device transfer: {key}")
    start_mask = torch.zeros((1, graph.num_nodes), dtype=torch.float32)
    if start_indexes:
        start_mask[0, torch.tensor(start_indexes, dtype=torch.long)] = 1.0
    batch = {
        "question_embeddings": query.reshape(1, -1).to(device),
        "start_nodes_mask": start_mask.to(device),
    }
    started = time.perf_counter()
    with torch.inference_mode():
        scores = model(moved, batch)
    torch.cuda.synchronize(device)
    duration = time.perf_counter() - started
    require(scores.ndim == 2 and tuple(scores.shape) == (1, graph.num_nodes), f"Unexpected G-reasoner score shape {tuple(scores.shape)}")
    scores = scores.detach().float().cpu()[0]
    require(bool(torch.isfinite(scores).all()), "G-reasoner emitted non-finite scores")
    return scores, duration


def safe_metrics(
    questions: list[dict[str, Any]], rows_by_id: dict[int, dict[str, Any]], labels: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[float]]]:
    per_question: dict[str, dict[int, float]] = {name: {} for name in CONDITION_NAMES}
    per_question_table: dict[str, dict[int, float]] = {name: {} for name in CONDITION_NAMES}
    per_database: dict[str, dict[str, Any]] = defaultdict(dict)
    for question in questions:
        qid = question["question_id"]
        label = labels[qid]
        require(label["db_id"] == question["db_id"], "Gold label database differs from question")
        row = rows_by_id[qid]
        for condition in CONDITION_NAMES:
            table_ranking = row["rankings"][condition]["table"]
            table_gold = set(label["gold_table_ids"])
            table_recall = len(set(table_ranking[:10]) & table_gold) / len(table_gold)
            per_question_table[condition][qid] = table_recall
            for k in (5, 10):
                hits = len(set(table_ranking[:k]) & table_gold)
                item = per_database.setdefault(question["db_id"], {}).setdefault(condition, {"table_recall@5": [], "table_recall@10": [], "column_recall@5": [], "column_recall@10": [], "column_recall@20": [], "column_precision@10": []})
                item[f"table_recall@{k}"].append(hits / len(table_gold))
            if label["column_eligible"]:
                column_ranking = row["rankings"][condition]["column"]
                column_gold = set(label["gold_column_ids"])
                values: dict[int, float] = {}
                for k in (5, 10, 20):
                    recall = len(set(column_ranking[:k]) & column_gold) / len(column_gold)
                    values[k] = recall
                    per_database[question["db_id"]][condition][f"column_recall@{k}"].append(recall)
                precision_denominator = min(10, len(column_ranking))
                precision = len(set(column_ranking[:10]) & column_gold) / precision_denominator
                per_database[question["db_id"]][condition]["column_precision@10"].append(precision)
                per_question[condition][qid] = values[10]
    db_names = {db_id: f"db_{index:02d}" for index, db_id in enumerate(sorted({row["db_id"] for row in questions}), start=1)}
    aggregate: dict[str, Any] = {"query_macro": {}, "anonymous_database_aggregates": {}}
    mean_or_none = lambda values: sum(values) / len(values) if values else None
    for condition in CONDITION_NAMES:
        table_questions = list(per_question_table[condition].values())
        column_questions = list(per_question[condition].values())
        p10 = [value for values in per_database.values() for value in values[condition]["column_precision@10"]]
        table_r5 = [value for values in per_database.values() for value in values[condition]["table_recall@5"]]
        column_r5 = [value for values in per_database.values() for value in values[condition]["column_recall@5"]]
        column_r20 = [value for values in per_database.values() for value in values[condition]["column_recall@20"]]
        aggregate["query_macro"][condition] = {
            "table_recall@5": mean_or_none(table_r5),
            "table_recall@10": mean_or_none(table_questions),
            "column_recall@5": mean_or_none(column_r5),
            "column_recall@10": mean_or_none(column_questions),
            "column_recall@20": mean_or_none(column_r20),
            "column_precision@10": mean_or_none(p10),
            "table_question_count": len(table_questions),
            "column_eligible_question_count": len(column_questions),
        }
    for db_id, conditions in per_database.items():
        aggregate["anonymous_database_aggregates"][db_names[db_id]] = {
            condition: {
                metric: sum(values) / len(values) if values else None
                for metric, values in metrics.items()
            }
            for condition, metrics in conditions.items()
        }
    deltas = {
        "G3_minus_D0_column_recall@10": [per_question["G3"][qid] - per_question["D0"][qid] for qid in per_question["G3"]],
        "G3_minus_G1_column_recall@10": [per_question["G3"][qid] - per_question["G1"][qid] for qid in per_question["G3"]],
        "G3_minus_D0_table_recall@10": [per_question_table["G3"][qid] - per_question_table["D0"][qid] for qid in per_question_table["G3"]],
    }
    delta_by_qid = {
        "G3_minus_D0_column_recall@10": dict(zip(per_question["G3"], deltas["G3_minus_D0_column_recall@10"], strict=True)),
        "G3_minus_G1_column_recall@10": dict(zip(per_question["G3"], deltas["G3_minus_G1_column_recall@10"], strict=True)),
        "G3_minus_D0_table_recall@10": dict(zip(per_question_table["G3"], deltas["G3_minus_D0_table_recall@10"], strict=True)),
    }
    aggregate["rescue_damage"] = {}
    for condition_a, condition_b in (("G3", "D0"), ("G3", "G1")):
        left = per_question[condition_a]
        right = per_question[condition_b]
        comparable = sorted(left.keys() & right.keys())
        diffs = [left[qid] - right[qid] for qid in comparable]
        aggregate["rescue_damage"][f"{condition_a}_vs_{condition_b}_column_recall@10"] = {
            "rescued_questions": sum(value > 0 for value in diffs),
            "damaged_questions": sum(value < 0 for value in diffs),
            "unchanged_questions": sum(value == 0 for value in diffs),
        }
    return aggregate, delta_by_qid, deltas


def cluster_bootstrap(
    questions: list[dict[str, Any]], delta_by_qid: dict[int, float], draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    import numpy as np

    grouped: dict[str, list[float]] = defaultdict(list)
    for question in questions:
        if question["question_id"] in delta_by_qid:
            grouped[question["db_id"]].append(float(delta_by_qid[question["question_id"]]))
    db_keys = sorted(grouped)
    db_sums = np.asarray([np.sum(grouped[key]) for key in db_keys], dtype=np.float64)
    db_counts = np.asarray([len(grouped[key]) for key in db_keys], dtype=np.float64)
    db_means = db_sums / db_counts
    require(len(db_means) == EXPECTED_COUNTS["databases"], "Bootstrap did not include all database clusters")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sampled = rng.integers(0, len(db_means), size=(draws, len(db_means)))
    bootstrap = db_sums[sampled].sum(axis=1) / db_counts[sampled].sum(axis=1)
    low, high = np.quantile(bootstrap, [0.025, 0.975])
    return {
        "unit": "database cluster resampling; query-macro statistic within each bootstrap draw",
        "database_clusters": int(len(db_means)),
        "draws": draws,
        "seed": BOOTSTRAP_SEED,
        "observed_query_macro_delta": float(db_sums.sum() / db_counts.sum()),
        "ci_95_percentile": [float(low), float(high)],
        "database_level_delta_means": [float(value) for value in db_means],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config.get("experiment_id") == EXPERIMENT_ID, "Experiment config ID mismatch")
    require(config["feature_contract"]["query_instruction"] == QUERY_INSTRUCTION, "Query instruction differs from the frozen config")
    require(config["feature_contract"]["relation_texts"] == list(RELATION_TEXTS), "Relation text differs from the frozen config")
    require(config["models"]["g_reasoner"]["model_pth_sha256"] == EXPECTED_GFM_MODEL_SHA256, "G-reasoner hash differs from the frozen config")
    require(config["models"]["embedding"]["weight_sha256"] == EXPECTED_QWEN_WEIGHT_SHA256, "Qwen hash differs from the frozen config")
    expected_run_id = config["run_ids"][args.mode]
    require(args.run_id == expected_run_id, "Run ID differs from the frozen config")
    source_commit = current_commit()
    require(source_commit == args.expected_commit, "Current source commit differs from --expected-commit")
    require(not worktree_status(), "The source worktree must be clean before a formal run")
    require(args.device == "cuda:0", "Only the preregistered single visible CUDA device is allowed")
    visible_gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    require(visible_gpu == "0", "Pin physical GPU 0 using CUDA_VISIBLE_DEVICES=0")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "Local-only offline mode is required")
    shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
    require(shared_root and (Path(shared_root) / "api_usage_ledger.py").is_file(), "Shared API usage ledger module is unavailable")
    if args.mode == "full":
        require(args.smoke_summary is not None and args.smoke_summary.is_file(), "Full run requires the passed smoke summary")
        smoke = json.loads(args.smoke_summary.read_text(encoding="utf-8"))
        require(smoke.get("status") == "smoke_passed" and smoke.get("question_count") == 5, "Full run blocked because 5-question smoke did not pass")
        require(smoke.get("source_commit") == source_commit, "Smoke and Full commits differ")
        require(smoke.get("config_sha256") == sha256_file(args.config), "Smoke and Full configs differ")
    require(not args.output_dir.exists(), f"Output directory already exists; refusing overwrite: {args.output_dir}")
    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    (args.output_dir / "private_predictions.jsonl").touch(mode=0o600, exist_ok=False)

    attempt = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "attempted_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": source_commit,
        "source_tree": subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip(),
        "interpreter": sys.executable,
        "command_argv": [sys.executable, *sys.argv],
        "config_sha256": sha256_file(args.config),
        "legacy_artifact_root_resolved": str(args.legacy_root.resolve(strict=True)),
        "dataset_root_resolved": str(args.dataset_root.resolve(strict=True)),
        "embedding_model_resolved": str(args.embedding_model.resolve(strict=True)),
        "checkpoint_resolved": str(args.checkpoint.resolve(strict=True)),
        "execution_environment": {key: os.environ.get(key) for key in ("CUDA_VISIBLE_DEVICES", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "GFM_SHARED_CODE_ROOT")},
        "resource_preflight": resource_snapshot(),
    }
    write_json(args.output_dir / "attempt_manifest.json", attempt)
    os.chmod(args.output_dir / "attempt_manifest.json", 0o600)

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    try:
        import torch
        import torch_geometric
        import transformers
        import sentence_transformers
        from sentence_transformers import SentenceTransformer
        from torch_geometric.data import Data
        from gfmrag.utils.util import load_model_from_pretrained
        import numpy as np

        expected_versions = {"python": "3.12.15", "torch": "2.8.0", "torch_geometric": "2.6.1", "transformers": "4.56.1", "sentence_transformers": "5.1.1"}
        actual_versions = {
            "python": platform.python_version(),
            "torch": str(torch.__version__).split("+", 1)[0],
            "torch_geometric": str(torch_geometric.__version__),
            "transformers": str(transformers.__version__),
            "sentence_transformers": str(sentence_transformers.__version__),
        }
        require(actual_versions == expected_versions, f"Environment version mismatch: {actual_versions}")
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "Exactly one visible CUDA device is required")
        device = torch.device(args.device)
        torch.cuda.set_device(device)
        torch.manual_seed(BOOTSTRAP_SEED)
        torch.set_num_threads(MAX_THREADS)
        torch.set_num_interop_threads(MAX_THREADS)
        torch.cuda.reset_peak_memory_stats(device)

        _p15, p2b, common = prepare_helpers(args.legacy_root, args.dataset_root, args.embedding_model)
        questions_all, original_records, schemas, input_hashes = validate_frozen_inputs(common, args.dataset_root, config)
        selected_questions = select_questions(questions_all, args.mode)

        embedding_path = args.embedding_model.resolve(strict=True)
        checkpoint = args.checkpoint.resolve(strict=True)
        require(sha256_file(checkpoint / "model.pth") == EXPECTED_GFM_MODEL_SHA256, "G-reasoner weights hash mismatch")
        require(sha256_file(checkpoint / "config.json") == EXPECTED_GFM_CONFIG_SHA256, "G-reasoner config hash mismatch")
        pilot = load_module(REPO_ROOT / "scripts/text2sql/run_p0_fk_mapping_model_proxy_rank_pilot.py", "pilot_helpers_for_gfm_transfer")
        qwen_snapshot_hashes = pilot.validate_qwen_snapshot(embedding_path)
        require(qwen_snapshot_hashes["model.safetensors"] == EXPECTED_QWEN_WEIGHT_SHA256, "Qwen weight hash mismatch")

        encoder_started = time.perf_counter()
        embedder = SentenceTransformer(str(embedding_path), device=str(device), trust_remote_code=True, local_files_only=True)
        embedder.eval()
        tokenizer = embedder[0].tokenizer
        r1_nodes, r1_meta = build_r1_nodes(original_records, p2b, common, tokenizer)
        require(len(r1_nodes) == EXPECTED_COUNTS["nodes"], "R1 node count mismatch")
        questions_for_encoding = [row["text"] for row in selected_questions]
        passage_texts = [node.text for node in r1_nodes] + list(RELATION_TEXTS)
        query_embeddings, query_usage = pilot.encode_texts(
            embedder, questions_for_encoding, is_query=True, run_id=args.run_id, call_prefix="query", torch=torch,
        )
        passage_embeddings, passage_usage = pilot.encode_texts(
            embedder, passage_texts, is_query=False, run_id=args.run_id, call_prefix="passage", torch=torch,
        )
        query_vector_by_id = {row["question_id"]: query_embeddings[row["text"]] for row in selected_questions}
        del embedder
        torch.cuda.empty_cache()
        torch.cuda.synchronize(device)
        encoder_seconds = time.perf_counter() - encoder_started
        assert_budget(started_wall, started_cpu, torch, device)

        graphs, nodes_by_db, type_indexes = build_database_graphs(
            selected_questions, r1_nodes, schemas, passage_embeddings,
            {text: passage_embeddings[text] for text in RELATION_TEXTS}, Data, torch,
        )
        model_started = time.perf_counter()
        model, model_config = load_model_from_pretrained(str(checkpoint))
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        require(parameter_count == EXPECTED_GFM_PARAMETERS, "G-reasoner parameter count mismatch")
        model_config_inner = model_config["model_config"]
        require(int(model_config_inner["entity_model"]["input_dim"]) == 1024 and int(model_config_inner["feat_dim"]) == 1024, "G-reasoner input dimension mismatch")
        model.eval().to(device)
        model_seconds = time.perf_counter() - model_started

        predictions: dict[int, dict[str, Any]] = {}
        g1_forward_seconds: list[float] = []
        g3_forward_seconds: list[float] = []
        for question_index, question in enumerate(selected_questions):
            qid = question["question_id"]
            db_id = question["db_id"]
            db_nodes = nodes_by_db[db_id]
            graph = graphs[db_id]
            indexes = type_indexes[db_id]
            query_vector = query_vector_by_id[qid]
            dense_scores = torch.mv(graph.x, query_vector.float())
            require(bool(torch.isfinite(dense_scores).all()), "Dense cosine produced non-finite scores")
            dense_rankings = {
                node_type: ranked_node_ids(dense_scores, db_nodes, indexes[node_type])
                for node_type in ("table", "column")
            }
            id_to_index = {node.node_id: index for index, node in enumerate(db_nodes)}
            condition_scores: dict[str, Any] = {"D0": dense_scores}
            anchor_ids: dict[str, dict[str, list[str]]] = {}
            for condition, anchor_k in (("G1", 1), ("G3", 3)):
                anchors = {
                    node_type: dense_rankings[node_type][:anchor_k]
                    for node_type in ("table", "column")
                }
                anchor_indexes = [id_to_index[node_id] for rows in anchors.values() for node_id in rows]
                scores, elapsed = run_g_reasoner(model, graph, query_vector, anchor_indexes, device, torch)
                condition_scores[condition] = scores
                anchor_ids[condition] = anchors
                if condition == "G1":
                    g1_forward_seconds.append(elapsed)
                else:
                    g3_forward_seconds.append(elapsed)
            rankings = {
                "D0": dense_rankings,
                "G1": {node_type: ranked_node_ids(condition_scores["G1"], db_nodes, indexes[node_type]) for node_type in ("table", "column")},
                "G3": {node_type: ranked_node_ids(condition_scores["G3"], db_nodes, indexes[node_type]) for node_type in ("table", "column")},
            }
            predictions[qid] = {"question_id": qid, "db_id": db_id, "rankings": rankings, "anchors": anchor_ids}
            if (question_index + 1) % 100 == 0 or question_index + 1 == len(selected_questions):
                print(json.dumps({"stage": "ranking_progress", "questions_done": question_index + 1, "questions_total": len(selected_questions), "wall_seconds": round(time.perf_counter() - started_wall, 2), "rss_gib": round(current_rss_bytes() / 1024**3, 3)}, ensure_ascii=False), flush=True)
            assert_budget(started_wall, started_cpu, torch, device)

        # Gold labels are read only after all query/node embeddings and rankings are fixed.
        gold_labels, gold_counts = common.load_gold_labels()
        require(gold_counts["questions"] == EXPECTED_COUNTS["questions"] and gold_counts["column_eligible_questions"] == EXPECTED_COUNTS["column_eligible"], "Gold-label counts mismatch")
        aggregate, delta_by_qid, deltas = safe_metrics(selected_questions, predictions, gold_labels)
        if args.mode == "full":
            bootstrap = cluster_bootstrap(selected_questions, delta_by_qid["G3_minus_D0_column_recall@10"])
            aggregate["g3_minus_d0_column_recall@10_database_cluster_bootstrap"] = bootstrap
            point = aggregate["query_macro"]
            g3_d0 = point["G3"]["column_recall@10"] - point["D0"]["column_recall@10"]
            g3_g1 = point["G3"]["column_recall@10"] - point["G1"]["column_recall@10"]
            table_delta = point["G3"]["table_recall@10"] - point["D0"]["table_recall@10"]
            gate = {
                "g3_minus_d0_column_recall@10_pp": 100 * g3_d0,
                "g3_minus_d0_ci_95_lower_pp": 100 * bootstrap["ci_95_percentile"][0],
                "g3_minus_g1_column_recall@10_pp": 100 * g3_g1,
                "g3_minus_d0_table_recall@10_pp": 100 * table_delta,
                "criteria": {
                    "g3_minus_d0_at_least_2pp": 100 * g3_d0 >= 2.0,
                    "cluster_ci_lower_above_zero": bootstrap["ci_95_percentile"][0] > 0,
                    "g3_minus_g1_at_least_1pp": 100 * g3_g1 >= 1.0,
                    "table_recall_loss_no_worse_than_1pp": 100 * table_delta >= -1.0,
                },
            }
            gate["status"] = "TRANSFER_SIGNAL_PASS" if all(gate["criteria"].values()) else "NO_GO"
            aggregate["transfer_gate"] = gate

        for question in selected_questions:
            qid = question["question_id"]
            row = predictions[qid]
            label = gold_labels[qid]
            row["gold"] = {
                "table_ids": list(label["gold_table_ids"]),
                "column_ids": list(label["gold_column_ids"]),
                "column_eligible": bool(label["column_eligible"]),
            }
        private_path = args.output_dir / "private_predictions.jsonl"
        with private_path.open("w", encoding="utf-8") as stream:
            for qid in sorted(predictions):
                stream.write(json.dumps(predictions[qid], ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        os.chmod(private_path, 0o600)

        peak_gpu_bytes = int(torch.cuda.max_memory_allocated(device))
        peak_rss_bytes = current_rss_bytes()
        wall_seconds = time.perf_counter() - started_wall
        cpu_seconds = time.process_time() - started_cpu
        require(peak_gpu_bytes <= MAX_GPU_BYTES, f"Peak GPU allocation exceeded cap: {peak_gpu_bytes}")
        require(peak_rss_bytes <= MAX_RSS_BYTES, f"Peak RSS exceeded cap: {peak_rss_bytes}")
        require(wall_seconds <= MAX_WALL_SECONDS and cpu_seconds <= MAX_CPU_SECONDS, "Stage resource budget exceeded")

        counts = {
            "question_count": len(selected_questions),
            "database_count": len({row["db_id"] for row in selected_questions}),
            "column_eligible_question_count": sum(bool(gold_labels[row["question_id"]]["column_eligible"]) for row in selected_questions),
            "table_node_count": sum(node.node_type == "table" for node in r1_nodes),
            "column_node_count": sum(node.node_type == "column" for node in r1_nodes),
            "graph_count": len(graphs),
            "membership_edge_count": sum(graph.num_edges for graph in graphs.values()),
        }
        if args.mode == "smoke":
            require(counts["question_count"] == 5 and counts["database_count"] == 1, "Smoke sample shape mismatch")
            require(len(g1_forward_seconds) == len(selected_questions), "G1 forward count mismatch")
            require(len(g3_forward_seconds) == len(selected_questions), "G3 forward count mismatch")
            status = "smoke_passed"
        else:
            require(counts["question_count"] == EXPECTED_COUNTS["questions"], "Full sample shape mismatch")
            require(counts["database_count"] == EXPECTED_COUNTS["databases"], "Full database count mismatch")
            status = "full_complete"
        summary = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": status,
            "question_count": counts["question_count"],
            "database_count": counts["database_count"],
            "source_commit": source_commit,
            "source_tree": attempt["source_tree"],
            "config_sha256": attempt["config_sha256"],
            "input_sha256": input_hashes,
            "r1_schema": r1_meta,
            "counts": counts,
            "metrics": aggregate,
            "embedding_usage": {"query": query_usage, "passage": passage_usage, "input_tokens": query_usage["input_tokens"] + passage_usage["input_tokens"], "output_tokens": 0},
            "timing": {
                "encoder_wall_seconds": encoder_seconds,
                "g_reasoner_g1_forward_seconds_total": sum(g1_forward_seconds),
                "g_reasoner_g3_forward_seconds_total": sum(g3_forward_seconds),
                "g_reasoner_forward_count": len(g1_forward_seconds) + len(g3_forward_seconds),
                "total_wall_seconds": wall_seconds,
                "process_cpu_seconds": cpu_seconds,
                "g_reasoner_model_load_seconds": model_seconds,
            },
            "resources": {"device": torch.cuda.get_device_name(device), "cuda_visible_devices": visible_gpu, "peak_gpu_allocated_bytes": peak_gpu_bytes, "peak_rss_bytes": peak_rss_bytes, "resource_preflight": attempt["resource_preflight"]},
            "model": {"g_reasoner_parameter_count": parameter_count, "g_reasoner_weights_sha256": EXPECTED_GFM_MODEL_SHA256, "g_reasoner_config_sha256": EXPECTED_GFM_CONFIG_SHA256, "qwen_snapshot_hashes": qwen_snapshot_hashes},
            "environment": actual_versions,
            "contains_raw_question_or_sql": False,
            "external_api_requests": 0,
        }
        write_json(args.output_dir / "aggregate_summary.json", summary)
        os.chmod(args.output_dir / "aggregate_summary.json", 0o600)
        print(json.dumps({"stage": "run_complete", "run_id": args.run_id, "status": status, "question_count": counts["question_count"], "metrics": aggregate.get("query_macro"), "transfer_gate": aggregate.get("transfer_gate"), "input_tokens": summary["embedding_usage"]["input_tokens"], "peak_gpu_allocated_bytes": peak_gpu_bytes, "peak_rss_bytes": peak_rss_bytes}, ensure_ascii=False), flush=True)
        return summary
    except Exception as error:
        failure = {
            "experiment_id": EXPERIMENT_ID,
            "run_id": args.run_id,
            "mode": args.mode,
            "status": "failed",
            "source_commit": source_commit,
            "config_sha256": sha256_file(args.config),
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "elapsed_wall_seconds": time.perf_counter() - started_wall,
            "elapsed_process_cpu_seconds": time.process_time() - started_cpu,
        }
        write_json(args.output_dir / "failure_manifest.json", failure)
        os.chmod(args.output_dir / "failure_manifest.json", 0o600)
        raise


def main() -> None:
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
