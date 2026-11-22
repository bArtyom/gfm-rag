#!/usr/bin/env python3
"""Audit Spider train databases for a sparse-FK single-database pilot.

Reads only Spider tables.json and train_spider.json from the archived ZIP.
It does not extract or alter the upstream dataset and emits aggregate counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with zipfile.ZipFile(args.archive) as archive:
        schema_bytes = archive.read("spider_data/tables.json")
        train_bytes = archive.read("spider_data/train_spider.json")
        schemas = json.loads(schema_bytes)
        train_tasks = json.loads(train_bytes)

    train_counts = Counter(task["db_id"] for task in train_tasks)
    rows = []
    for schema in schemas:
        db_id = schema["db_id"]
        fks = schema.get("foreign_keys", [])
        rows.append(
            {
                "db_id": db_id,
                "table_count": len(schema.get("table_names_original", [])),
                "foreign_key_column_pair_count": len(fks),
                "train_question_count": train_counts[db_id],
                "has_column_descriptions": bool(schema.get("column_descriptions")),
            }
        )

    eligible = [r for r in rows if r["train_question_count"] > 0]
    eligible.sort(
        key=lambda r: (
            r["foreign_key_column_pair_count"],
            -r["train_question_count"],
            r["db_id"],
        )
    )
    zero_fk = [r for r in eligible if r["foreign_key_column_pair_count"] == 0]
    at_most_two_fk = [
        r for r in eligible if r["foreign_key_column_pair_count"] <= 2
    ]

    result = {
        "dataset": "Spider 1.0 official train split",
        "archive_path": str(args.archive),
        "schema_member_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "train_member_sha256": hashlib.sha256(train_bytes).hexdigest(),
        "schema_database_count": len(rows),
        "train_question_count": len(train_tasks),
        "databases_with_train_questions": len(eligible),
        "zero_fk_database_count": sum(
            r["foreign_key_column_pair_count"] == 0 for r in rows
        ),
        "at_most_two_fk_database_count": sum(
            r["foreign_key_column_pair_count"] <= 2 for r in rows
        ),
        "zero_fk_with_train_count": len(zero_fk),
        "at_most_two_fk_with_train_count": len(at_most_two_fk),
        "zero_fk_top_candidates": zero_fk[:20],
        "at_most_two_fk_top_candidates": at_most_two_fk[:30],
        "notes": [
            "Foreign key count is the number of ordered column-pair entries in Spider tables.json.",
            "Ranking uses only train_spider task counts; dev/test data and SQL text are not used for selection.",
            "Spider schemas do not provide business column descriptions in tables.json.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
