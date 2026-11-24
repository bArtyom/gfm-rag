"""Select a private, question/SQL-blind BIRD-Ent document-schema review packet.

The selector uses task fields data_asset, eval_db, and gold_knowledge_ids only.
It never reads or emits question text, SQL, or gold table/column labels.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

SEED = "bizweave-codex-review-20261124-001"
EXCLUDED_DOC_IDS = {"0"}
EXCLUDED_DATABASES = {"california_schools"}
EXCLUDED_PHYSICAL_TABLES = {"xelion11_bkpub_ttl_metadata_drop"}
STRATUM_COUNTS = {"balanced_hash_sample": 18, "low_overlap": 6, "multi_component_cue": 6}
CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+TABLE\s+[`\"\[]?([^`\"\]\s(]+)", re.I)
COLUMN_DECL_RE = re.compile(r"^\s*[`\"]([^`\"]+)[`\"]\s+([A-Za-z][A-Za-z0-9_]*(?:\s*\([^)]*\))?)")
MULTI_COMPONENT_CUE_RE = re.compile(
    r"\b(?:ratio|rate|margin|percentage|percent|conversion|per\s+\w+|divided\s+by|"
    r"difference\s+between|subtract(?:ed|ing)?|minus|sum\s+of|weighted|net|gross|share\s+of|average\s+of)\b",
    re.I,
)


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def stable_hash(value):
    return sha256_bytes(value.encode("utf-8"))


def tokens(text):
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", str(text))
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def table_name(ddl):
    match = CREATE_TABLE_RE.search(ddl)
    if not match:
        raise ValueError("Selected schema DDL has no CREATE TABLE name")
    return match.group(1)


def columns_for_ddl(ddl):
    found = []
    for line in ddl.splitlines():
        match = COLUMN_DECL_RE.match(line)
        if match:
            found.append({"name": match.group(1), "type": match.group(2)})
    if not found:
        raise ValueError("Selected schema DDL has no recognizable column declarations")
    return found


def load_documents(raw):
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items() if isinstance(value, str)}
    output = {}
    for row in raw:
        key = str(row.get("knowledge_id", row.get("id")))
        value = row.get("content", row.get("text", row.get("document")))
        if key != "None" and isinstance(value, str):
            output[key] = value
    return output


def choose_unique_document_assignments(tasks, assets, table_maps):
    by_doc = defaultdict(dict)
    for task in tasks:
        asset_id = task.get("data_asset")
        database = task.get("eval_db")
        doc_ids = task.get("gold_knowledge_ids")
        if not asset_id or not database or database in EXCLUDED_DATABASES:
            continue
        if not isinstance(doc_ids, list) or asset_id not in assets or database not in table_maps:
            continue
        physical_names = set(table_maps[database].values())
        if physical_names & EXCLUDED_PHYSICAL_TABLES:
            continue
        ddl_by_physical = {}
        for asset_id_key, ddl in assets[asset_id].items():
            physical = table_name(ddl)
            ddl_by_physical[physical] = (str(asset_id_key), ddl)
        if not physical_names or not physical_names.issubset(ddl_by_physical):
            continue
        for raw_doc_id in doc_ids:
            doc_id = str(raw_doc_id)
            if doc_id in EXCLUDED_DOC_IDS:
                continue
            pair = {"document_id": doc_id, "data_asset": asset_id, "eval_db": database}
            key = "|".join((doc_id, asset_id, database))
            by_doc[doc_id][stable_hash(SEED + "|assignment|" + key)] = pair
    assignments = []
    for doc_id, variants in by_doc.items():
        if variants:
            assignments.append(min(variants.items(), key=lambda item: item[0])[1])
    return assignments


def schema_for_case(asset_id, database, assets, table_maps):
    physical_to_ddl = {}
    for schema_id, ddl in assets[asset_id].items():
        physical_to_ddl[table_name(ddl)] = (str(schema_id), ddl)
    tables = []
    for _, physical in sorted(table_maps[database].items(), key=lambda item: item[1]):
        if physical not in physical_to_ddl:
            raise ValueError("Evaluation database table has no paired data-asset DDL")
        ddl_id, ddl = physical_to_ddl[physical]
        tables.append({"name": physical, "columns": columns_for_ddl(ddl), "_source_schema_id": ddl_id})
    return tables


def overlap_score(document, tables):
    doc_tokens = tokens(document)
    schema_text = " ".join(
        [table["name"] + " " + " ".join(column["name"] for column in table["columns"]) for table in tables]
    )
    schema_tokens = tokens(schema_text)
    union = doc_tokens | schema_tokens
    return len(doc_tokens & schema_tokens) / len(union) if union else 0.0


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def write_jsonl(path, rows):
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def take_balanced(pool_by_asset, count, selected_ids, *, sort_key, max_per_asset=None):
    chosen = []
    candidates = []
    for asset_id, rows in pool_by_asset.items():
        for row in rows:
            if row["document_id"] not in selected_ids:
                candidates.append(row)
    candidates.sort(key=sort_key)
    selected_per_asset = defaultdict(int)
    for row in candidates:
        if len(chosen) >= count:
            break
        if max_per_asset is not None and selected_per_asset[row["data_asset"]] >= max_per_asset:
            continue
        chosen.append(row)
        selected_ids.add(row["document_id"])
        selected_per_asset[row["data_asset"]] += 1
    if len(chosen) != count:
        raise ValueError("A registered sample stratum cannot reach its requested size")
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tasks_path = args.dataset_root / "BIRD-Ent.json"
    assets_path = args.dataset_root / "data_assets.json"
    docs_path = args.dataset_root / "knowledge_documents.json"
    table_maps_path = args.dataset_root / "table_name_mappings.json"
    tasks, assets = read_json(tasks_path), read_json(assets_path)
    documents = load_documents(read_json(docs_path))
    table_maps = read_json(table_maps_path)
    assignments = choose_unique_document_assignments(tasks, assets, table_maps)

    candidates = []
    for row in assignments:
        doc_id = row["document_id"]
        document = documents.get(doc_id)
        if not isinstance(document, str) or not document.strip():
            continue
        tables = schema_for_case(row["data_asset"], row["eval_db"], assets, table_maps)
        row = dict(row)
        row["document_text"] = document
        row["document_chars"] = len(document)
        row["schema_tables"] = tables
        row["schema_columns"] = sum(len(table["columns"]) for table in tables)
        row["lexical_overlap_jaccard"] = overlap_score(document, tables)
        row["has_multi_component_cue"] = bool(MULTI_COMPONENT_CUE_RE.search(document))
        row["sample_hash"] = stable_hash(SEED + "|sample|" + doc_id)
        candidates.append(row)

    grouped = defaultdict(list)
    for row in candidates:
        grouped[row["data_asset"]].append(row)
    for asset_id in grouped:
        grouped[asset_id].sort(key=lambda row: row["sample_hash"])

    selected_ids = set()
    random_sample = []
    asset_order = sorted(grouped, key=lambda asset_id: stable_hash(SEED + "|asset|" + asset_id))
    for asset_id in asset_order:
        rows = [row for row in grouped[asset_id] if row["document_id"] not in selected_ids]
        for row in rows[:2]:
            random_sample.append(row)
            selected_ids.add(row["document_id"])
    while len(random_sample) < STRATUM_COUNTS["balanced_hash_sample"]:
        added = False
        for asset_id in asset_order:
            rows = [row for row in grouped[asset_id] if row["document_id"] not in selected_ids]
            if rows:
                random_sample.append(rows[0])
                selected_ids.add(rows[0]["document_id"])
                added = True
                if len(random_sample) == STRATUM_COUNTS["balanced_hash_sample"]:
                    break
        if not added:
            raise ValueError("Balanced hash stratum cannot reach its registered size")

    low_overlap = take_balanced(
        grouped,
        STRATUM_COUNTS["low_overlap"],
        selected_ids,
        sort_key=lambda row: (row["lexical_overlap_jaccard"], row["sample_hash"]),
        max_per_asset=1,
    )
    cue_rows = [row for row in candidates if row["has_multi_component_cue"]]
    cue_grouped = defaultdict(list)
    for row in cue_rows:
        cue_grouped[row["data_asset"]].append(row)
    multi_cue = take_balanced(
        cue_grouped,
        STRATUM_COUNTS["multi_component_cue"],
        selected_ids,
        sort_key=lambda row: row["sample_hash"],
        max_per_asset=1,
    )

    sample = [(row, "balanced_hash_sample") for row in random_sample]
    sample.extend((row, "low_overlap") for row in low_overlap)
    sample.extend((row, "multi_component_cue") for row in multi_cue)
    if len(sample) != 30 or len(selected_ids) != 30:
        raise ValueError("Selected sample does not match the preregistered 30 unique documents")

    manifest, packet = [], []
    for index, (row, stratum) in enumerate(sample, 1):
        case_id = "C%02d" % index
        document = row["document_text"]
        schema_tables = [
            {"name": table["name"], "columns": table["columns"]}
            for table in row["schema_tables"]
        ]
        manifest.append({
            "case_id": case_id,
            "document_id": row["document_id"],
            "data_asset": row["data_asset"],
            "eval_db": row["eval_db"],
            "stratum": stratum,
            "document_chars": row["document_chars"],
            "document_sha256": sha256_bytes(document.encode("utf-8")),
            "schema_tables": len(schema_tables),
            "schema_columns": row["schema_columns"],
            "lexical_overlap_jaccard": row["lexical_overlap_jaccard"],
            "multi_component_cue": row["has_multi_component_cue"],
        })
        packet.append({"case_id": case_id, "document": document, "schema": schema_tables})

    output_files = {
        "BIRD-Ent.json": tasks_path,
        "data_assets.json": assets_path,
        "knowledge_documents.json": docs_path,
        "table_name_mappings.json": table_maps_path,
    }
    input_hashes = {name: sha256_bytes(path.read_bytes()) for name, path in output_files.items()}
    summary = {
        "run_id": "bizweave_birdent_codex_review_pilot_20261124_001",
        "dataset_revision": "cde16ccf0eb606585642d6b06209760d73fd28dc",
        "seed": SEED,
        "candidate_unique_documents": len(candidates),
        "selected_cases": len(manifest),
        "selected_data_assets": len({row["data_asset"] for row in manifest}),
        "stratum_counts": {name: sum(row["stratum"] == name for row in manifest) for name in STRATUM_COUNTS},
        "input_sha256": input_hashes,
        "privacy": "manifest and review packet are private; no question, SQL, or gold table/column labels included",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "selection_summary.private.json", summary)
    write_json(args.output_dir / "selected_cases.private.json", manifest)
    write_jsonl(args.output_dir / "review_packet.private.jsonl", packet)
    print(json.dumps({
        "candidate_unique_documents": len(candidates),
        "selected_cases": len(manifest),
        "selected_data_assets": summary["selected_data_assets"],
        "stratum_counts": summary["stratum_counts"],
        "input_hashes_recorded": len(input_hashes),
        "private_output_dir": str(args.output_dir),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
