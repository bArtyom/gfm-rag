"""Shared, project-local support for the GFM-RAG-backed QuadGraph P1 rerun."""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = PROJECT_ROOT / "upstream" / "gfm-rag"
DATA_ROOT = Path("/mnt/liansp3/sources/datasets/bird/dev")
DB_ROOT = DATA_ROOT / "dev_databases"
QUESTION_PATH = DATA_ROOT / "dev.json"
SCHEMA_PATH = DATA_ROOT / "dev_tables.json"
P0_AUDIT_PATH = PROJECT_ROOT / "results/p0/full_audit_v3.json"
GOLD_LABELS_PATH = (
    PROJECT_ROOT
    / "results/p1/full_1534_final_20261014/per_question_private.jsonl"
)
MODEL_PATH = Path("/mnt/liansp3/sources/models/qwen3-embedding-0.6b")

EXPECTED_QUESTION_SHA256 = (
    "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06"
)
EXPECTED_SCHEMA_SHA256 = (
    "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97"
)
EXPECTED_P0_AUDIT_SHA256 = (
    "0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf"
)
EXPECTED_GOLD_LABELS_SHA256 = (
    "1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525"
)
EXPECTED_MODEL_MANIFEST_SHA256 = (
    "b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68"
)
QUERY_INSTRUCTION = (
    "Given a natural-language question about a database, retrieve the relevant "
    "tables and columns."
)
QUERY_PREFIX = f"Instruct: {QUERY_INSTRUCTION}\nQuery: "
DIMENSIONS = (128, 256, 512, 768, 1024)
DESCRIPTION_CSV_ENCODINGS: dict[str, str] = {}


@dataclass(frozen=True)
class SchemaNode:
    node_id: str
    db_id: str
    node_type: str
    text: str
    token_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text_sequence(texts: list[str]) -> dict[str, str]:
    compact_json = json.dumps(texts, ensure_ascii=False, separators=(",", ":"))
    normal_json = json.dumps(texts, ensure_ascii=False)
    joined = "\n".join(texts)
    return {
        "newline_join": sha256_bytes(joined.encode("utf-8")),
        "newline_join_with_trailing_newline": sha256_bytes(
            (joined + "\n").encode("utf-8")
        ),
        "compact_json_list": sha256_bytes(compact_json.encode("utf-8")),
        "json_list": sha256_bytes(normal_json.encode("utf-8")),
    }


def verify_frozen_files() -> dict[str, Any]:
    path_hashes = {
        "questions": sha256_file(QUESTION_PATH),
        "schema": sha256_file(SCHEMA_PATH),
        "p0_audit": sha256_file(P0_AUDIT_PATH),
        "gold_labels": sha256_file(GOLD_LABELS_PATH),
    }
    expected = {
        "questions": EXPECTED_QUESTION_SHA256,
        "schema": EXPECTED_SCHEMA_SHA256,
        "p0_audit": EXPECTED_P0_AUDIT_SHA256,
        "gold_labels": EXPECTED_GOLD_LABELS_SHA256,
    }
    mismatches = {
        name: {"expected": expected[name], "actual": value}
        for name, value in path_hashes.items()
        if value != expected[name]
    }
    if mismatches:
        raise RuntimeError(f"Frozen input hash mismatch: {mismatches}")

    model_manifest_path = PROJECT_ROOT / "results/p0/model_files.sha256"
    model_manifest_hash = sha256_file(model_manifest_path)
    if model_manifest_hash != EXPECTED_MODEL_MANIFEST_SHA256:
        raise RuntimeError(
            "Frozen model manifest hash mismatch: "
            f"expected={EXPECTED_MODEL_MANIFEST_SHA256} actual={model_manifest_hash}"
        )

    with P0_AUDIT_PATH.open("r", encoding="utf-8") as file:
        audit = json.load(file)
    csv_entries = [
        entry
        for entry in audit["database_input_hashes"]
        if entry["relative_path"].endswith(".csv")
    ]
    verified_csv_count = 0
    for entry in csv_entries:
        csv_path = DB_ROOT / entry["relative_path"]
        if not csv_path.is_file():
            raise FileNotFoundError(f"Frozen description CSV is missing: {csv_path}")
        actual_size = csv_path.stat().st_size
        actual_hash = sha256_file(csv_path)
        if actual_size != entry["bytes"] or actual_hash != entry["sha256"]:
            raise RuntimeError(
                f"Frozen description CSV mismatch: {entry['relative_path']}"
            )
        verified_csv_count += 1
    if verified_csv_count != 75:
        raise RuntimeError(
            f"Expected 75 frozen description CSVs, verified {verified_csv_count}"
        )

    return {
        "sha256": path_hashes,
        "model_manifest_sha256": model_manifest_hash,
        "description_csv_count_verified": verified_csv_count,
    }


def _read_description_rows(
    db_id: str, fallback_encoding: str = "cp1252"
) -> dict[str, dict[str, str]]:
    directory = DB_ROOT / db_id / "database_description"
    if not directory.is_dir():
        raise FileNotFoundError(f"Database description directory missing: {directory}")
    rows_by_table: dict[str, dict[str, str]] = {}
    for csv_path in directory.glob("*.csv"):
        decoded_rows = None
        last_decode_error = None
        encoding_used = None
        for encoding in ("utf-8-sig", fallback_encoding):
            try:
                with csv_path.open("r", encoding=encoding, newline="") as file:
                    decoded_rows = list(csv.DictReader(file))
                encoding_used = encoding
                break
            except UnicodeDecodeError as exc:
                last_decode_error = exc
        if decoded_rows is None or encoding_used is None:
            raise RuntimeError(
                f"Could not decode description CSV {csv_path} as UTF-8 or {fallback_encoding}: "
                f"{last_decode_error}"
            ) from last_decode_error

        required_fields = {
            "original_column_name",
            "column_description",
            "data_format",
            "value_description",
        }
        with csv_path.open("r", encoding=encoding_used, newline="") as file:
            reader = csv.DictReader(file)
            missing_fields = required_fields.difference(reader.fieldnames or ())
        if missing_fields:
            raise RuntimeError(
                f"Description CSV schema mismatch in {csv_path}: "
                f"missing={sorted(missing_fields)}"
            )

        DESCRIPTION_CSV_ENCODINGS[str(csv_path.relative_to(DB_ROOT))] = encoding_used
        rows = {}
        for row in decoded_rows:
            key = (row.get("original_column_name") or "").strip()
            if key:
                rows[key] = {
                    name: (row.get(name) or "").strip()
                    for name in (
                        "column_description",
                        "data_format",
                        "value_description",
                    )
                }
        rows_by_table[csv_path.stem.casefold()] = rows
    return rows_by_table


def load_gold_labels() -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    labels: dict[int, dict[str, Any]] = {}
    with GOLD_LABELS_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            row = json.loads(line)
            question_id = int(row["question_id"])
            if question_id in labels:
                raise RuntimeError(f"Duplicate gold-label question_id={question_id}")
            labels[question_id] = {
                "question_id": question_id,
                "db_id": row["db_id"],
                "gold_table_ids": tuple(row["gold_table_ids_private"]),
                "gold_column_ids": tuple(row["gold_column_ids_private"]),
                "column_eligible": bool(row["column_eligible"]),
            }

    counts = {
        "questions": len(labels),
        "table_labeled_questions": sum(bool(row["gold_table_ids"]) for row in labels.values()),
        "table_gold_elements": sum(len(row["gold_table_ids"]) for row in labels.values()),
        "column_eligible_questions": sum(row["column_eligible"] for row in labels.values()),
        "column_gold_elements": sum(
            len(row["gold_column_ids"])
            for row in labels.values()
            if row["column_eligible"]
        ),
        "databases": len({row["db_id"] for row in labels.values()}),
    }
    expected_counts = {
        "questions": 1534,
        "table_labeled_questions": 1534,
        "table_gold_elements": 2978,
        "column_eligible_questions": 1460,
        "column_gold_elements": 6523,
        "databases": 11,
    }
    if counts != expected_counts:
        raise RuntimeError(f"Frozen gold-label count mismatch: {counts}")
    return labels, counts


def _build_schema_nodes(
    schemas: list[dict[str, Any]], fallback_encoding: str = "cp1252"
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for schema in schemas:
        db_id = schema["db_id"]
        table_names = schema["table_names_original"]
        column_names = schema["column_names_original"]
        column_types = schema["column_types"]
        descriptions = _read_description_rows(db_id, fallback_encoding)

        for table_index, table_name in enumerate(table_names):
            table_columns = [
                column_name
                for table_idx, column_name in column_names
                if table_idx == table_index
            ]
            table_text = (
                f"Table: {table_name}; columns: {', '.join(table_columns)}"
            )
            nodes.append(
                {
                    "node_id": f"table:{db_id}:{table_index}",
                    "db_id": db_id,
                    "node_type": "table",
                    "text": table_text,
                }
            )

            description_rows = descriptions.get(table_name.casefold(), {})
            for column_index, (table_idx, column_name) in enumerate(column_names):
                if table_idx != table_index:
                    continue
                description = description_rows.get(column_name, {})
                parts = [
                    f"Column: {table_name}.{column_name}",
                    f"type: {column_types[column_index]}",
                ]
                for field, label in (
                    ("column_description", "description"),
                    ("data_format", "format"),
                    ("value_description", "values"),
                ):
                    value = description.get(field, "")
                    if value:
                        parts.append(f"{label}: {value}")
                nodes.append(
                    {
                        "node_id": f"column:{db_id}:{column_index}",
                        "db_id": db_id,
                        "node_type": "column",
                        "text": "; ".join(parts),
                    }
                )
    return nodes


def _install_source_packages(upstream_root: Path) -> None:
    """Skip GFM-RAG's unrelated eager trainer/export imports, without editing it."""
    gfmrag_root = upstream_root / "gfmrag"
    package_paths = {
        "gfmrag": gfmrag_root,
        "gfmrag.text_emb_models": gfmrag_root / "text_emb_models",
    }
    for name in list(sys.modules):
        if name == "gfmrag" or name.startswith("gfmrag."):
            del sys.modules[name]
    for name, package_path in package_paths.items():
        spec = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        spec.submodule_search_locations = [str(package_path)]
        module = types.ModuleType(name)
        module.__file__ = str(package_path / "__init__.py")
        module.__package__ = name
        module.__path__ = [str(package_path)]
        module.__spec__ = spec
        sys.modules[name] = module

    try:
        sentence_transformers_spec = importlib.util.find_spec("sentence_transformers")
    except (ImportError, ValueError):
        sentence_transformers_spec = None
    if sentence_transformers_spec is None and "sentence_transformers" not in sys.modules:
        unused_module = types.ModuleType("sentence_transformers")

        class UnusedSentenceTransformer:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError(
                    "SentenceTransformer is not used by the official Qwen3 backend"
                )

        unused_module.SentenceTransformer = UnusedSentenceTransformer
        sys.modules["sentence_transformers"] = unused_module


def load_official_qwen3_class():
    if str(UPSTREAM_ROOT) not in sys.path:
        sys.path.insert(0, str(UPSTREAM_ROOT))
    _install_source_packages(UPSTREAM_ROOT)
    module = importlib.import_module("gfmrag.text_emb_models.qwen3_model")
    return module.Qwen3TextEmbModel


def prepare_p1_inputs(
    load_tokenizer: bool = True, description_fallback_encoding: str = "cp1252"
) -> dict[str, Any]:
    frozen_hashes = verify_frozen_files()
    with QUESTION_PATH.open("r", encoding="utf-8") as file:
        questions = json.load(file)
    with SCHEMA_PATH.open("r", encoding="utf-8") as file:
        schemas = json.load(file)
    labels, label_counts = load_gold_labels()

    if len(questions) != 1534 or len(schemas) != 11:
        raise RuntimeError(
            f"Unexpected input size: questions={len(questions)} schemas={len(schemas)}"
        )

    question_rows: list[dict[str, Any]] = []
    for question in questions:
        question_id = int(question["question_id"])
        label = labels.get(question_id)
        if label is None or label["db_id"] != question["db_id"]:
            raise RuntimeError(f"Question/label mapping mismatch at question_id={question_id}")
        prompt = QUERY_PREFIX + question["question"]
        question_rows.append(
            {
                "question_id": question_id,
                "db_id": question["db_id"],
                "text": question["question"],
                "prompt": prompt,
                "label": label,
            }
        )
    if len({row["question_id"] for row in question_rows}) != 1534:
        raise RuntimeError("Question IDs are not unique")

    node_records = _build_schema_nodes(schemas, description_fallback_encoding)
    node_ids = [row["node_id"] for row in node_records]
    if len(node_records) != 873 or len(set(node_ids)) != 873:
        raise RuntimeError(
            f"Unexpected schema node count/IDs: count={len(node_records)} unique={len(set(node_ids))}"
        )
    node_id_set = set(node_ids)
    nodes_by_db: dict[str, list[dict[str, Any]]] = {}
    for node in node_records:
        nodes_by_db.setdefault(node["db_id"], []).append(node)
    for question in question_rows:
        label = question["label"]
        db_node_ids = {node["node_id"] for node in nodes_by_db[label["db_id"]]}
        for node_id in (*label["gold_table_ids"], *label["gold_column_ids"]):
            if node_id not in node_id_set or node_id not in db_node_ids:
                raise RuntimeError(
                    f"Gold label is not a candidate for question_id={question['question_id']}"
                )
        if not label["gold_table_ids"]:
            raise RuntimeError(f"Missing table labels for question_id={question['question_id']}")

    token_stats = None
    if load_tokenizer:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            str(MODEL_PATH), local_files_only=True, trust_remote_code=True
        )
        if tokenizer.pad_token is None and tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
        for node in node_records:
            node["token_count"] = len(
                tokenizer.encode(node["text"], add_special_tokens=False)
            )
        prompt_token_lengths = [
            len(tokenizer.encode(row["prompt"], add_special_tokens=False))
            for row in question_rows
        ]
        node_token_lengths = [node["token_count"] for node in node_records]
        max_positions = int(
            getattr(tokenizer, "model_max_length", 32768)
            if getattr(tokenizer, "model_max_length", 32768) < 10**7
            else 32768
        )
        if max(prompt_token_lengths) > max_positions or max(node_token_lengths) > max_positions:
            raise RuntimeError(
                "Input exceeds model max positions: "
                f"query_max={max(prompt_token_lengths)}, node_max={max(node_token_lengths)}, "
                f"limit={max_positions}"
            )
        token_stats = {
            "tokenizer_class": type(tokenizer).__name__,
            "model_max_positions": max_positions,
            "query_prompt_max_tokens": max(prompt_token_lengths),
            "schema_node_max_tokens": max(node_token_lengths),
            "schema_node_token_median": sorted(node_token_lengths)[len(node_token_lengths) // 2],
            "schema_node_token_p95": sorted(node_token_lengths)[int(0.95 * (len(node_token_lengths) - 1))],
            "schema_nodes_over_model_limit": 0,
        }

    return {
        "questions": question_rows,
        "nodes": [SchemaNode(**node) for node in node_records],
        "nodes_by_db": {
            db_id: [SchemaNode(**node) for node in rows]
            for db_id, rows in nodes_by_db.items()
        },
        "frozen_hashes": frozen_hashes,
        "description_csv_encodings": dict(sorted(DESCRIPTION_CSV_ENCODINGS.items())),
        "description_csv_encoding_counts": {
            encoding: sum(value == encoding for value in DESCRIPTION_CSV_ENCODINGS.values())
            for encoding in sorted(set(DESCRIPTION_CSV_ENCODINGS.values()))
        },
        "description_csv_fallback_encoding": description_fallback_encoding,
        "label_counts": label_counts,
        "text_hashes": {
            "query_prompts": sha256_text_sequence(
                [row["prompt"] for row in question_rows]
            ),
            "schema_nodes": sha256_text_sequence(
                [node["text"] for node in node_records]
            ),
        },
        "token_stats": token_stats,
    }
