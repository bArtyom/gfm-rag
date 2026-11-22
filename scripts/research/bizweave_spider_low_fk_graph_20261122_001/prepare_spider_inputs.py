#!/usr/bin/env python3
"""Freeze schema-only evidence for the Spider bike_1 BizWeave pilot."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/text2sql/bizweave_spider_low_fk_graph_20261122_001.json"


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    dataset = config["dataset"]
    archive_path = Path(dataset["archive_file"])
    archive_sha = sha256_file(archive_path)
    if archive_sha != dataset["archive_sha256"]:
        raise ValueError(f"Spider archive hash mismatch: {archive_sha}")

    with zipfile.ZipFile(archive_path) as archive:
        schema_bytes = archive.read(dataset["schema_member"])
    schema_sha = sha256_bytes(schema_bytes)
    if schema_sha != dataset["expected_schema_sha256"]:
        raise ValueError(f"Spider schema-member hash mismatch: {schema_sha}")
    schemas = json.loads(schema_bytes)
    matches = [schema for schema in schemas if schema.get("db_id") == dataset["database_id"]]
    if len(matches) != 1:
        raise ValueError(f"Expected one schema for {dataset['database_id']}, found {len(matches)}")
    schema = matches[0]

    table_names = schema["table_names_original"]
    if len(table_names) != dataset["expected_tables"]:
        raise ValueError(f"Expected {dataset['expected_tables']} tables, found {len(table_names)}")
    if len(schema.get("foreign_keys", [])) != dataset["expected_declared_fk_column_pairs"]:
        raise ValueError("Declared Spider FK column-pair count changed")

    primary_keys = set()
    for key in schema.get("primary_keys", []):
        if isinstance(key, list):
            primary_keys.update(item for item in key if isinstance(item, int))
        elif isinstance(key, int):
            primary_keys.add(key)

    column_index = {}
    columns_by_table = {index: [] for index in range(len(table_names))}
    for original_index, (table_index, column_name) in enumerate(schema["column_names_original"]):
        if table_index < 0:
            continue
        record = {
            "name": column_name,
            "type": schema["column_types"][original_index],
            "primary_key": original_index in primary_keys,
            "evidence_ids": [f"E_C_{original_index:03d}"],
        }
        column_index[original_index] = (table_index, column_name)
        columns_by_table[table_index].append(record)

    evidence = []
    tables = []
    for table_index, table_name in enumerate(table_names):
        table_evidence_id = f"E_T_{table_index:03d}"
        table_columns = columns_by_table[table_index]
        evidence.append({
            "evidence_id": table_evidence_id,
            "evidence_type": "schema_table",
            "table": table_name,
            "source_file": dataset["schema_member"],
            "text": f"Table name: {table_name}. Columns: " + ", ".join(column["name"] for column in table_columns),
        })
        tables.append({"name": table_name, "columns": table_columns, "evidence_ids": [table_evidence_id]})
        for original_index, (mapped_table, column_name) in column_index.items():
            if mapped_table != table_index:
                continue
            column_id = f"E_C_{original_index:03d}"
            column_record = next(item for item in table_columns if item["name"] == column_name and column_id in item["evidence_ids"])
            evidence.append({
                "evidence_id": column_id,
                "evidence_type": "schema_column",
                "table": table_name,
                "column": column_name,
                "source_file": dataset["schema_member"],
                "text": (
                    f"Table: {table_name}; column: {column_name}; type: {column_record['type']}; "
                    f"primary_key: {str(column_record['primary_key']).lower()}"
                ),
            })

    declared_foreign_keys = []
    for fk_index, pair in enumerate(schema.get("foreign_keys", [])):
        source_index, target_index = pair
        if source_index not in column_index or target_index not in column_index:
            raise ValueError(f"FK {fk_index} references a missing physical column")
        source_table_index, source_column = column_index[source_index]
        target_table_index, target_column = column_index[target_index]
        source_table = table_names[source_table_index]
        target_table = table_names[target_table_index]
        fk_evidence_id = f"E_FK_{fk_index:03d}"
        evidence.append({
            "evidence_id": fk_evidence_id,
            "evidence_type": "declared_foreign_key",
            "source_table": source_table,
            "source_column": source_column,
            "target_table": target_table,
            "target_column": target_column,
            "source_file": dataset["schema_member"],
            "text": f"Declared FK column pair: {source_table}.{source_column} -> {target_table}.{target_column}",
        })
        declared_foreign_keys.append({
            "id": f"FK_{fk_index:03d}",
            "source_table": source_table,
            "source_column": source_column,
            "target_table": target_table,
            "target_column": target_column,
            "evidence_ids": [fk_evidence_id, f"E_C_{source_index:03d}", f"E_C_{target_index:03d}"],
        })

    model_input = {
        "database_id": dataset["database_id"],
        "declared_foreign_key_column_pair_count": len(declared_foreign_keys),
        "tables": tables,
        "declared_foreign_keys": declared_foreign_keys,
        "evidence": evidence,
        "generation_boundary": (
            "Spider schema metadata only: table/column names, SQL types, primary-key markers, and exact declared FK pair. "
            "No question, Gold SQL, database rows, or query result is included. The schema has no business descriptions."
        ),
    }
    model_input_bytes = json.dumps(model_input, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    input_sha = sha256_bytes(model_input_bytes)
    output_dir = args.output_dir or Path(config["paths"]["run_root"]) / "input_001"
    write_once(output_dir / "model_input.json", model_input_bytes.decode("utf-8"))

    manifest = {
        "run_id": config["run_id"],
        "database_id": dataset["database_id"],
        "archive_sha256": archive_sha,
        "schema_member_sha256": schema_sha,
        "model_input_sha256": input_sha,
        "table_count": len(tables),
        "declared_fk_column_pair_count": len(declared_foreign_keys),
        "evidence_record_count": len(evidence),
        "question_records_read_for_generation": 0,
        "gold_sql_records_read_for_generation": 0,
        "query_results_read_for_generation": 0,
        "model_visible_description_fields": 0,
        "information_boundary": model_input["generation_boundary"],
    }
    write_once(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "run_id": config["run_id"],
        "database_id": dataset["database_id"],
        "tables": len(tables),
        "declared_fk_column_pairs": len(declared_foreign_keys),
        "evidence_records": len(evidence),
        "model_input_sha256": input_sha,
        "questions_or_sql_read": 0,
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
