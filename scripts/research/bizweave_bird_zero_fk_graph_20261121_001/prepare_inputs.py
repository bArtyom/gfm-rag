#!/usr/bin/env python3
"""Freeze schema-only evidence for the BizWeave zero-FK graph pilot."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_once(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite frozen artifact: {path}")
    path.write_text(content, encoding="utf-8")


def read_description(path):
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
        encoding = "cp1252-fallback"
    return list(csv.DictReader(io.StringIO(content, newline=""))), encoding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    dataset = config["dataset"]
    schema_path = Path(dataset["schema_file"])
    tasks_path = Path(dataset["tasks_file"])
    description_dir = Path(dataset["description_dir"])
    schema_sha = sha256_file(schema_path)
    tasks_sha = sha256_file(tasks_path)
    if schema_sha != dataset["expected_schema_sha256"]:
        raise ValueError(f"Schema hash mismatch: {schema_sha}")
    if tasks_sha != dataset["expected_tasks_sha256"]:
        raise ValueError(f"Task hash mismatch: {tasks_sha}")

    schemas = json.loads(schema_path.read_text(encoding="utf-8"))
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    db_id = dataset["database_id"]
    selected = [item for item in schemas if item.get("db_id") == db_id]
    if len(selected) != 1:
        raise ValueError(f"Expected one schema for {db_id}, found {len(selected)}")
    schema = selected[0]
    task_count = sum(item.get("db_id") == db_id for item in tasks)
    table_names = schema["table_names_original"]
    foreign_key_count = len(schema.get("foreign_keys", []))
    if len(table_names) != dataset["expected_tables"]:
        raise ValueError(f"Expected {dataset['expected_tables']} tables, found {len(table_names)}")
    if foreign_key_count != dataset["expected_declared_foreign_keys"]:
        raise ValueError(f"Expected {dataset['expected_declared_foreign_keys']} declared FKs, found {foreign_key_count}")
    if task_count != dataset["expected_task_count"]:
        raise ValueError(f"Expected {dataset['expected_task_count']} tasks, found {task_count}")

    primary_keys = set()
    for primary_key in schema.get("primary_keys", []):
        if isinstance(primary_key, list):
            primary_keys.update(key for key in primary_key if isinstance(key, int))
        elif isinstance(primary_key, int):
            primary_keys.add(primary_key)
    columns_by_table = {index: [] for index in range(len(table_names))}
    for column_index, (table_index, column_name) in enumerate(schema["column_names_original"]):
        if table_index >= 0:
            columns_by_table[table_index].append({
                "name": column_name,
                "type": schema["column_types"][column_index],
                "primary_key": column_index in primary_keys,
            })

    evidences = []
    tables = []
    for table_index, table_name in enumerate(table_names):
        table_evidence_id = f"E_T_{table_index:03d}"
        table_columns = columns_by_table[table_index]
        evidences.append({
            "evidence_id": table_evidence_id,
            "evidence_type": "schema_table",
            "table": table_name,
            "column": None,
            "source_file": "train_tables.json",
            "text": f"Table name: {table_name}. Columns: " + ", ".join(column["name"] for column in table_columns),
        })
        tables.append({"name": table_name, "columns": table_columns, "evidence_ids": [table_evidence_id]})
        for column_index, column in enumerate(table_columns):
            evidence_id = f"E_C_{table_index:03d}_{column_index:03d}"
            evidence_text = (
                f"Table: {table_name}; column: {column['name']}; type: {column['type']}; "
                f"primary_key: {str(column['primary_key']).lower()}"
            )
            evidences.append({
                "evidence_id": evidence_id,
                "evidence_type": "schema_column",
                "table": table_name,
                "column": column["name"],
                "source_file": "train_tables.json",
                "text": evidence_text,
            })
            column["evidence_ids"] = [evidence_id]

    description_sources = []
    table_by_folded_name = {name.casefold(): name for name in table_names}
    for description_path in sorted(description_dir.glob("*.csv")):
        rows, encoding = read_description(description_path)
        source_table = table_by_folded_name.get(description_path.stem.casefold())
        description_sources.append({
            "file": description_path.name,
            "sha256": sha256_file(description_path),
            "row_count": len(rows),
            "decode": encoding,
            "matched_table": source_table,
        })
        for row_index, row in enumerate(rows):
            if not source_table:
                continue
            column_candidate = (row.get("column_name") or row.get("original_column_name") or "").strip()
            known_columns = {column["name"].casefold(): column["name"] for column in columns_by_table[table_names.index(source_table)]}
            column = known_columns.get(column_candidate.casefold()) if column_candidate else None
            parts = []
            for key, label in [
                ("column_name", "documented_column"),
                ("original_column_name", "original_column"),
                ("column_description", "description"),
                ("data_format", "format"),
                ("value_description", "value_meaning"),
            ]:
                value = (row.get(key) or "").strip()
                if value:
                    parts.append(f"{label}: {value}")
            if not parts:
                continue
            evidence_id = f"E_D_{len(description_sources):03d}_{row_index:03d}"
            evidences.append({
                "evidence_id": evidence_id,
                "evidence_type": "database_description",
                "table": source_table,
                "column": column,
                "source_file": description_path.name,
                "text": f"Table: {source_table}; " + "; ".join(parts),
            })
            if column:
                table_slot = tables[table_names.index(source_table)]
                for item in table_slot["columns"]:
                    if item["name"] == column:
                        item["evidence_ids"].append(evidence_id)

    model_input = {
        "database_id": db_id,
        "declared_foreign_key_count": foreign_key_count,
        "tables": tables,
        "evidence": evidences,
        "generation_boundary": "Schema and database-description metadata only. No questions, Gold SQL, row values, or query results are included.",
    }
    model_input_bytes = json.dumps(model_input, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    input_sha = hashlib.sha256(model_input_bytes).hexdigest()
    output_dir = args.output_dir or Path(config["paths"]["run_root"]) / "input_001"
    write_once(output_dir / "model_input.json", model_input_bytes.decode("utf-8"))

    manifest = {
        "run_id": config["run_id"],
        "database_id": db_id,
        "table_count": len(table_names),
        "declared_foreign_key_count": foreign_key_count,
        "evaluation_question_count_not_sent_to_model": task_count,
        "schema_sha256": schema_sha,
        "tasks_sha256_evaluation_only": tasks_sha,
        "model_input_sha256": input_sha,
        "model_input_evidence_count": len(evidences),
        "description_sources": description_sources,
        "information_boundary": model_input["generation_boundary"],
    }
    write_once(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "run_id": config["run_id"],
        "database_id": db_id,
        "tables": len(table_names),
        "declared_foreign_keys": foreign_key_count,
        "evaluation_questions_not_sent_to_model": task_count,
        "evidence_records": len(evidences),
        "description_csv_files": len(description_sources),
        "model_input_sha256": input_sha,
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
