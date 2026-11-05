#!/usr/bin/env python3
"""Prepare the private, frozen P2d.3 sample without model calls or SQL execution."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.text2sql import p2d_inputs

EXPERIMENT = "p2d3_context_bounded_repair_20261105_01"
EXPECTED_COUNTS = {"questions": 1534, "databases": 11, "column_eligible": 1460}
P2C_ROWS_SHA = "99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff"
P2C_AGGREGATE_SHA = "7e4ce4b2a92df5e17160bb2429402b66ab7caec521c6e4da9ec90abd108e8fdc"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Frozen helper module could not be loaded")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required local resource alias is unset: {name}")
    path = Path(value).expanduser().resolve(strict=True)
    return path


def rank_key(seed: int, question_id: int) -> str:
    return hashlib.sha256(f"{seed}|{question_id}".encode()).hexdigest()


def complete_flag(row: dict) -> bool:
    value = row["arms"]["V00"]["budgets"]["1024"]["complete"]
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise RuntimeError("V00 Complete Schema@1024 must be encoded as boolean or 0/1")


def select_sample(rows: dict[int, dict], seed: int, count: int = 66) -> list[int]:
    cells: dict[tuple[str, bool], list[int]] = {}
    by_database: dict[str, list[int]] = {}
    for question_id, row in rows.items():
        db = row["db_id"]
        complete = complete_flag(row)
        cells.setdefault((db, complete), []).append(question_id)
        by_database.setdefault(db, []).append(question_id)

    selected: list[int] = []
    selected_set: set[int] = set()
    for db in sorted(by_database):
        for complete in (False, True):
            candidates = sorted(cells.get((db, complete), []), key=lambda qid: rank_key(seed, qid))
            for question_id in candidates[:3]:
                selected.append(question_id)
                selected_set.add(question_id)

    # First balance every database to six when enough eligible cases remain.
    for db in sorted(by_database):
        candidates = sorted((qid for qid in by_database[db] if qid not in selected_set),
                            key=lambda qid: rank_key(seed, qid))
        need = min(max(0, 6 - sum(rows[qid]["db_id"] == db for qid in selected)), len(candidates))
        for question_id in candidates[:need]:
            selected.append(question_id)
            selected_set.add(question_id)

    # If some databases cannot reach six, round-robin from the least represented.
    while len(selected) < count:
        remaining_by_database = {
            db: sorted((qid for qid in qids if qid not in selected_set), key=lambda qid: rank_key(seed, qid))
            for db, qids in by_database.items()
        }
        available = [db for db, qids in remaining_by_database.items() if qids]
        if not available:
            raise RuntimeError("Fewer than 66 eligible unseen questions remain")
        counts = {db: sum(rows[qid]["db_id"] == db for qid in selected) for db in available}
        db = min(available, key=lambda item: (counts[item], item))
        question_id = remaining_by_database[db][0]
        selected.append(question_id)
        selected_set.add(question_id)
    if len(selected) != count or len(set(selected)) != count:
        raise RuntimeError("Frozen sample selection is not unique and complete")
    return selected


def make_catalog(schema: dict, db_id: str, selected_ids: list[str]) -> dict:
    table_names = schema["table_names_original"]
    columns_by_table: dict[str, set[str]] = {name.casefold(): set() for name in table_names}
    original_names = {name.casefold(): name for name in table_names}
    for table_index, column_name in schema["column_names_original"]:
        if table_index >= 0:
            columns_by_table[table_names[table_index].casefold()].add(column_name.casefold())

    all_columns: dict[str, set[str]] = {key: set(values) for key, values in columns_by_table.items()}
    selected_tables: set[str] = set()
    selected_columns: dict[str, set[str]] = {key: set() for key in columns_by_table}
    for node_id in selected_ids:
        kind, owner, raw_index = node_id.split(":", 2)
        if owner != db_id:
            raise RuntimeError("Selected P2c node belongs to a different database")
        index = int(raw_index)
        if kind == "table":
            if not 0 <= index < len(table_names):
                raise RuntimeError("Selected table node index is out of range")
            selected_tables.add(table_names[index].casefold())
        elif kind == "column":
            if not 0 <= index < len(schema["column_names_original"]):
                raise RuntimeError("Selected column node index is out of range")
            table_index, column_name = schema["column_names_original"][index]
            if table_index >= 0:
                selected_columns[table_names[table_index].casefold()].add(column_name.casefold())
        else:
            raise RuntimeError("Unexpected selected Schema node kind")

    allowed = {}
    for folded_table in columns_by_table:
        if folded_table in selected_tables:
            allowed[folded_table] = sorted(all_columns[folded_table])
        elif selected_columns[folded_table]:
            allowed[folded_table] = sorted(selected_columns[folded_table])
    return {
        "allowed_columns_by_casefolded_table": allowed,
        "allowed_tables_casefolded": sorted(allowed),
        "table_names_by_casefold": original_names,
    }


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--prepare-dir", required=True)
    args = parser.parse_args()

    if not args.prepare_dir.startswith("prepare_") or Path(args.prepare_dir).name != args.prepare_dir:
        raise RuntimeError("Preparation directory must be a local prepare_* name")

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != args.expected_commit:
        raise RuntimeError("Preparation source is not the registered published commit")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("Preparation requires a clean source tree")
    data_root = env_path("P2D3_BIRD_ROOT")
    embedding_model_root = env_path("P2D3_EMBEDDING_MODEL_ROOT")
    generation_model_root = env_path("P2D3_GENERATION_MODEL_ROOT")
    p1_run = env_path("P2D3_P1_6_RUN")
    legacy_root = env_path("P2D3_LEGACY_ROOT")
    p2c_root = env_path("P2D3_P2C_RESULT")
    old_p2d_root = env_path("P2D3_OLD_P2D_RESULT")

    result_root = args.result_root.resolve()
    if result_root.exists():
        existing = list(result_root.iterdir()) if result_root.is_dir() else []
        if (not result_root.is_dir()
                or result_root.stat().st_mode & 0o777 != 0o700
                or any(not child.is_dir() or not child.name.startswith("prepare_") for child in existing)):
            raise RuntimeError("Existing result root must be mode 0700 and contain only preserved prepare_* directories")
    else:
        result_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        result_root.chmod(0o700)
    prepared_root = result_root / args.prepare_dir
    prepared_root.mkdir(exist_ok=False, mode=0o700)
    cases_dir = prepared_root / "cases"
    cases_dir.mkdir(exist_ok=False, mode=0o700)
    start = time.perf_counter()

    for filename, expected in (("dev.json", "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06"),
                               ("dev_tables.json", "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97")):
        if sha(data_root / filename) != expected:
            raise RuntimeError("Frozen BIRD metadata hash mismatch")
    if sha(p2c_root / "aggregate_summary.json") != P2C_AGGREGATE_SHA:
        raise RuntimeError("P2c-R aggregate hash mismatch")
    p2c_rows_path = p2c_root / "per_question_private.jsonl"
    if sha(p2c_rows_path) != P2C_ROWS_SHA:
        raise RuntimeError("P2c-R private row hash mismatch")

    # Rebuild only the frozen P2c-R R0 text/node order from the registered P1.6 inputs.
    p1 = module(ROOT / "scripts/text2sql/run_p1_6_rebaseline.py", "p1_for_p2d3")
    p2a = module(ROOT / "scripts/text2sql/run_p2a_similarity.py", "p2a_for_p2d3")
    p2b = module(ROOT / "scripts/text2sql/run_p2b_values_ablation.py", "p2b_for_p2d3")
    p1_args = argparse.Namespace(
        p1_6_run_dir=p1_run,
        legacy_root=legacy_root,
        dataset_root=data_root,
        model_path=embedding_model_root,
        previous_run_dir=env_path("P2D3_P1_LEGACY_RESULT"),
        p1_5_run_dir=env_path("P2D3_P1_5_RESULT"),
    )
    input_record, frozen, _, _ = p2a.validate_p1_6_inputs(p1_args, p1)
    _, common = p1.load_common(legacy_root, data_root, embedding_model_root)
    from transformers import AutoTokenizer
    embedding_tokenizer = AutoTokenizer.from_pretrained(
        str(embedding_model_root), local_files_only=True, trust_remote_code=True,
    )
    generation_tokenizer = AutoTokenizer.from_pretrained(
        str(generation_model_root), local_files_only=True, trust_remote_code=True,
    )
    r0_nodes = {node.node_id: node.text for node in frozen["nodes"]}
    r1_nodes, text_audit = p2b.build_r1_nodes(frozen, common, embedding_tokenizer)
    if (len(r0_nodes) != 873
            or text_audit["r0_schema_text_sequence_sha256"] != "b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a"
            or text_audit["r1_schema_text_sequence_sha256"] != "73c59126b931fb72b7c09ba06de76327057e32832e2aeef0c8175b8956ed3e3c"):
        raise RuntimeError("Frozen P2c-R schema serialization mismatch")

    rows_by_id = {}
    with p2c_rows_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            rows_by_id[int(row["question_id"])] = row
    if len(rows_by_id) != 1534:
        raise RuntimeError("P2c-R row count mismatch")

    old_seal_path = old_p2d_root / "prepare_01" / "prepare_seal_private.json"
    old_seal = read(old_seal_path)
    excluded = set()
    for item in old_seal["cases"]:
        old_case = read(old_p2d_root / "prepare_01" / item["file"])
        excluded.add(int(old_case["question_id"]))
    if len(excluded) < 30:
        raise RuntimeError("Could not recover all previous P2d sample exclusions")

    questions = {int(row["question_id"]): row for row in read(data_root / "dev.json")}
    schemas = {row["db_id"]: row for row in read(data_root / "dev_tables.json")}
    if len(questions) != EXPECTED_COUNTS["questions"] or len(schemas) != EXPECTED_COUNTS["databases"]:
        raise RuntimeError("Frozen BIRD row or database counts differ")
    eligible = {}
    for question_id, p2c in rows_by_id.items():
        if question_id not in questions:
            raise RuntimeError("P2c-R contains an unknown question id")
        if p2c["column_eligible"] is not True:
            continue
        complete_flag(p2c)
        eligible[question_id] = p2c
    if len(eligible) != EXPECTED_COUNTS["column_eligible"]:
        raise RuntimeError("Frozen eligible sample count differs")
    candidate = {qid: row for qid, row in eligible.items() if qid not in excluded}
    full_ids = select_sample(candidate, seed=20261105, count=66)
    if len({questions[qid]["db_id"] for qid in full_ids}) != EXPECTED_COUNTS["databases"]:
        raise RuntimeError("Frozen Full sample does not cover all 11 registered databases")
    remaining = sorted(set(candidate) - set(full_ids), key=lambda qid: rank_key(20261106, qid))
    smoke_ids = remaining[:5]
    if len(smoke_ids) != 5 or set(smoke_ids) & set(full_ids) or set(smoke_ids) & excluded:
        raise RuntimeError("Frozen smoke sample is insufficient or overlaps prior samples")

    db_names = sorted(schemas)
    db_aliases = {db_id: f"db_{index:02d}" for index, db_id in enumerate(db_names, start=1)}
    database_manifest = {}
    full_contexts = {}
    for db_id in db_names:
        ordered = [node for node in frozen["nodes"] if node.db_id == db_id]
        full_contexts[db_id] = "\n".join(node.text for node in ordered)
        db_path = (data_root / "dev_databases" / db_id / f"{db_id}.sqlite").resolve(strict=True)
        database_manifest[db_id] = {"path": str(db_path), "sha256": sha(db_path)}

    case_manifest = []
    evaluation = {}
    group_counts = {}
    prepared_cases = full_ids + smoke_ids
    for index, question_id in enumerate(prepared_cases, start=1):
        raw = questions[question_id]
        db_id = raw["db_id"]
        row = rows_by_id[question_id]
        selected_ids = row["arms"]["V00"]["budgets"]["1024"]["selected_ids"]
        selected_text = "\n".join(r0_nodes[node_id] for node_id in selected_ids)
        allowed_catalog = make_catalog(schemas[db_id], db_id, selected_ids)
        messages = p2d_inputs.messages(raw["question"], raw.get("evidence", "") or "", selected_text)
        prompt_tokens = len(generation_tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
        ))
        if prompt_tokens + 1024 > 32768:
            raise RuntimeError("Frozen initial prompt exceeds registered model context")
        cohort = "full" if question_id in set(full_ids) else "smoke"
        complete = complete_flag(row)
        case_id = f"P2D3-{index:03d}"
        payload = {
            "case_id": case_id,
            "question_id": question_id,
            "database_alias": db_aliases[db_id],
            "cohort": cohort,
            "v00_complete_1024": complete,
            "db_id_private": db_id,
            "database_path_private": database_manifest[db_id]["path"],
            "database_sha256_private": database_manifest[db_id]["sha256"],
            "question": raw["question"],
            "evidence": raw.get("evidence", "") or "",
            "selected_node_ids_private": selected_ids,
            "selected_context_private": selected_text,
            "full_r0_context_private": full_contexts[db_id],
            "allowed_catalog_private": allowed_catalog,
            "initial_messages_private": messages,
            "initial_prompt_tokens_local": prompt_tokens,
        }
        case_path = cases_dir / f"{case_id}.json"
        write_new(case_path, payload)
        case_manifest.append({"case_id": case_id, "file": f"cases/{case_path.name}", "sha256": sha(case_path), "cohort": cohort})
        db_record = database_manifest[db_id]
        evaluation[case_id] = {
            "database_path_private": db_record["path"],
            "database_sha256": db_record["sha256"],
            "reference_sql_private": raw["SQL"],
        }
        stratum = f"{db_aliases[db_id]}|{'complete' if complete else 'incomplete'}"
        group_counts[stratum] = group_counts.get(stratum, 0) + int(cohort == "full")

    evaluation_path = prepared_root / "evaluation_private.json"
    write_new(evaluation_path, evaluation)
    source_paths = {
        "bird_questions": data_root / "dev.json",
        "bird_schema": data_root / "dev_tables.json",
        "p2c_aggregate": p2c_root / "aggregate_summary.json",
        "p2c_rows": p2c_rows_path,
        "old_p2d_prepare_seal": old_seal_path,
    }
    source_hashes = {name: {"sha256": sha(path), "path_private": str(path.resolve())}
                     for name, path in source_paths.items()}
    model_files = sorted(path for path in generation_model_root.rglob("*") if path.is_file())
    model_hashes = {str(path.relative_to(generation_model_root)): sha(path) for path in model_files}
    model_manifest_path = prepared_root / "model_manifest_private.json"
    write_new(model_manifest_path, {
        "model_root_private": str(generation_model_root),
        "files": model_hashes,
    })
    seal = {
        "experiment_id": EXPERIMENT,
        "cases": case_manifest,
        "full_question_count": len(full_ids),
        "smoke_question_count": len(smoke_ids),
        "excluded_old_question_count": len(excluded),
        "eligible_candidate_count_before_exclusion": len(eligible),
        "eligible_candidate_count_after_exclusion": len(candidate),
        "seed_full": 20261105,
        "seed_smoke": 20261106,
        "full_question_ids_sha256_private": digest(full_ids),
        "smoke_question_ids_sha256_private": digest(smoke_ids),
        "database_alias_counts_full": group_counts,
        "input_hashes_private": source_hashes,
        "database_hashes_private": {db_aliases[db]: database_manifest[db]["sha256"] for db in db_names},
        "database_manifest_private": database_manifest,
        "model_manifest_sha256": sha(model_manifest_path),
        "frozen_input_manifest_sha256": input_record["input_manifest_sha256"],
        "p2c_row_sha256": P2C_ROWS_SHA,
        "files": {str(path.relative_to(prepared_root)): sha(path)
                  for path in [evaluation_path, model_manifest_path] + [prepared_root / item["file"] for item in case_manifest]},
        "prepared_wall_seconds": time.perf_counter() - start,
    }
    seal_path = prepared_root / "prepare_seal_private.json"
    write_new(seal_path, seal)
    public_registration = {
        "status": "prepared_not_run",
        "experiment_id": EXPERIMENT,
        "full_cases": len(full_ids),
        "smoke_cases": len(smoke_ids),
        "excluded_prior_p2d_cases": len(excluded),
        "stratification": "11 anonymized databases x V00 Complete Schema@1024, eligible cases only",
        "full_database_alias_counts": group_counts,
        "sample_ids_or_questions_published": False,
        "gold_sql_or_database_paths_published": False,
        "seed_full": 20261105,
        "seed_smoke": 20261106,
        "input_hashes_public": {
            "dev_json": "630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06",
            "dev_tables_json": "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97",
            "p2c_aggregate": P2C_AGGREGATE_SHA,
            "p2c_rows": P2C_ROWS_SHA,
        },
        "prepared_wall_seconds": seal["prepared_wall_seconds"],
    }
    public_path = ROOT / "docs/research/text2sql/reports" / EXPERIMENT / "sample_registration.json"
    if public_path.exists():
        raise RuntimeError("Public sample registration already exists; preserve prior material")
    write_new(public_path, public_registration)
    print(json.dumps({key: public_registration[key] for key in
                      ("status", "full_cases", "smoke_cases", "excluded_prior_p2d_cases", "full_database_alias_counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
