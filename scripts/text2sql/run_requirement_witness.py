"""Run the bounded, local-Qwen requirement-witness BIRD-dev pilot."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sqlite3
import subprocess
import sys
import time

import numpy as np
import requests
from transformers import AutoTokenizer

from closure_budget_order import (
    SchemaClosure,
    expressibility,
    reference_read_bindings,
    serialize_partial,
)
from run_seed_steiner import load_inputs, new_output, read_config, sha256, write_json
from steiner_sql_runtime import read_reference_rows


BASELINE_TABLE = "table_coverage"
BASELINE_COLUMN = "scalar_column_closure"
WITNESS = "requirement_witness"
ARMS = [BASELINE_TABLE, BASELINE_COLUMN, WITNESS]
ALLOWED_OPERATIONS = {
    "projection", "filter_eq", "filter_range", "aggregate_count",
    "aggregate_sum", "aggregate_avg", "group", "order", "compare", "other",
}
SYSTEM_PROMPT = """You map a natural-language database question to schema requirements.
Return one JSON object only: {\"requirements\":[...]}. Do not answer the question.
Extract at most 8 non-duplicate selection, filter, aggregation, grouping, ordering,
or comparison requirements. Do not create a join requirement; joins are handled by
the schema graph. Each requirement must include a `span` that is an exact,
contiguous, verbatim substring of the question; `operation` from projection,
filter_eq, filter_range, aggregate_count, aggregate_sum, aggregate_avg, group,
order, compare, other; `status` from resolved, ambiguous, unresolved; and up to
three ordered `bindings`, each with `candidate_id` copied exactly from the supplied
list and a compatible `operator` from the same operation set. Preserve plausible
alternatives and mark status ambiguous when multiple fields remain plausible.
Do not guess a field missing from the candidate list. If no candidate is supported,
use unresolved with an empty bindings list. Evidence and field names must support
the binding; do not invent values or business facts."""


def write_jsonl(path, rows):
    path = Path(path)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sample_cases(questions, excluded, salt, count):
    groups = defaultdict(list)
    for row in questions:
        key = (row["db_id"], int(row["question_id"]))
        if key not in excluded:
            groups[row["db_id"]].append(row)
    for db in groups:
        groups[db].sort(key=lambda r: hashlib.sha256(
            f"{salt}:{db}:{int(r['question_id'])}".encode()).hexdigest())
    selected = []
    while len(selected) < count and any(groups.values()):
        for db in sorted(groups):
            if groups[db] and len(selected) < count:
                selected.append(groups[db].pop(0))
    if len(selected) != count:
        raise ValueError(f"Need {count} cases but found {len(selected)}")
    return selected


def build_exclusions(config):
    excluded = set()
    for row in read_jsonl(config["sql_prepared"]):
        if row.get("primary") or row.get("changed_schema"):
            excluded.add((row["db_id"], int(row["question_id"])))
    for field in ["old_route_predictions", "old_qafd_predictions"]:
        rows = json.loads(Path(config[field]).read_text(encoding="utf-8"))
        excluded |= {(r["db_id"], int(r["question_id"])) for r in rows}
    closure_path = Path(config["closure_previous_predictions"])
    if sha256(closure_path) != config["closure_previous_predictions_sha256"]:
        raise ValueError("Prior closure pilot prediction seal mismatch")
    closure_rows = json.loads(closure_path.read_text(encoding="utf-8"))
    closure_ids = {(r["db_id"], int(r["question_id"])) for r in closure_rows}
    if len(closure_ids) != 100:
        raise ValueError("Expected exactly 100 unique prior closure pilot cases")
    excluded |= closure_ids
    if len(excluded) != 433:
        raise ValueError(f"Prior exclusion count changed: {len(excluded)} != 433")
    return excluded


def verify_model_files(config, receipt_path=None):
    model_root = Path(config["sql_model"])
    expected = config["model_files_sha256"]
    if receipt_path and Path(receipt_path).exists():
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        if receipt.get("expected_sha256") != expected:
            raise ValueError("Smoke model receipt belongs to another model config")
        current_stat = {}
        for name in expected:
            path = model_root / name
            stat = path.stat()
            current_stat[name] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if current_stat != receipt.get("files_stat"):
            raise ValueError("Model files changed since smoke")
        return receipt
    actual = {name: sha256(model_root / name) for name in expected}
    if actual != expected:
        raise ValueError("Qwen2.5-Coder model hash mismatch")
    stats = {}
    for name in expected:
        stat = (model_root / name).stat()
        stats[name] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return {"expected_sha256": expected, "actual_sha256": actual, "files_stat": stats}


def column_type_class(value):
    value = str(value).casefold()
    if any(x in value for x in ["int", "number", "numeric", "real", "float", "decimal"]):
        return "numeric"
    if any(x in value for x in ["time", "date", "year"]):
        return "temporal"
    if any(x in value for x in ["bool"]):
        return "boolean"
    if any(x in value for x in ["text", "char", "string"]):
        return "text"
    return "unknown"


def compatible(operation, column_type):
    kind = column_type_class(column_type)
    if operation in {"aggregate_sum", "aggregate_avg"}:
        return kind == "numeric"
    if operation == "filter_range":
        return kind in {"numeric", "temporal"}
    return True


def make_messages(row, candidates):
    user_content = {
        "question": row["question"],
        "evidence": str(row.get("evidence") or ""),
        "candidate_columns": candidates,
        "output_rules": {
            "max_requirements": 8,
            "max_bindings_per_requirement": 3,
            "span_must_be_exact_substring": True,
            "column_bindings_must_use_candidate_id": True,
            "unresolved_is_allowed": True,
        },
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
    ]


def parse_requirements(content, question, candidate_by_id, config):
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"valid_json": False, "requirements": [], "raw_requirement_count": 0,
                "valid_span_count": 0, "invalid_binding_count": 0}
    raw = payload.get("requirements") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return {"valid_json": False, "requirements": [], "raw_requirement_count": 0,
                "valid_span_count": 0, "invalid_binding_count": 0}
    reqs = []
    valid_span_count = 0
    invalid_binding_count = 0
    seen = set()
    for index, item in enumerate(raw[:config["max_requirements"]]):
        if not isinstance(item, dict):
            continue
        span = item.get("span")
        if not isinstance(span, str) or not span:
            continue
        start = question.find(span)
        valid_span = start >= 0
        if valid_span:
            valid_span_count += 1
        operation = item.get("operation")
        if operation not in ALLOWED_OPERATIONS:
            operation = "other"
        key = (span, operation)
        if key in seen:
            continue
        seen.add(key)
        bindings = []
        raw_bindings = item.get("bindings", [])
        if isinstance(raw_bindings, list):
            for rank, binding in enumerate(raw_bindings[:config["max_alternatives"]]):
                if not isinstance(binding, dict):
                    invalid_binding_count += 1
                    continue
                cid = binding.get("candidate_id")
                operator = binding.get("operator", operation)
                candidate = candidate_by_id.get(cid)
                if candidate is None or operator not in ALLOWED_OPERATIONS:
                    invalid_binding_count += 1
                    continue
                if not compatible(operator, candidate["column_type"]):
                    invalid_binding_count += 1
                    continue
                if cid not in [entry["candidate_id"] for entry in bindings]:
                    bindings.append({"candidate_id": cid, "operator": operator, "rank": rank})
        status = item.get("status", "unresolved")
        if status not in {"resolved", "ambiguous", "unresolved"}:
            status = "unresolved"
        if not valid_span or not bindings:
            status = "unresolved"
        if status == "unresolved":
            bindings = []
        reqs.append({
            "requirement_id": f"R{len(reqs):02d}", "span": span,
            "start": start if valid_span else None,
            "end": start + len(span) if valid_span else None,
            "valid_span": valid_span, "operation": operation,
            "status": status, "bindings": bindings,
        })
    return {"valid_json": True, "requirements": reqs,
            "raw_requirement_count": len(raw), "valid_span_count": valid_span_count,
            "invalid_binding_count": invalid_binding_count}


def ledger_record(config, call_id, status, usage):
    module_path = Path(config["ledger_module"])
    sys.path.insert(0, str(module_path.parent))
    from api_usage_ledger import record_request
    record_request(
        call_id=call_id,
        provider="local_vllm",
        project="bArtyom/gfm-rag",
        run_id=config["run_id"],
        model="Qwen2.5-Coder-7B-Instruct-local",
        http_status=status,
        usage=usage,
    )


def call_qwen(config, tokenizer, row, candidates, mode, attempt_number):
    messages = make_messages(row, candidates)
    estimated_input = len(tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True))
    if estimated_input > config["max_context"] - config["generation"]["max_tokens"]:
        raise ValueError(f"Prompt context over limit: {estimated_input}")
    call_id = hashlib.sha256(
        f"{config['run_id']}|{mode}|{row['db_id']}|{row['question_id']}|{attempt_number}".encode()
    ).hexdigest()
    payload = {
        "model": config["served_model"], "messages": messages,
        "temperature": config["generation"]["temperature"],
        "top_p": config["generation"]["top_p"],
        "max_tokens": config["generation"]["max_tokens"],
        "seed": config["generation"]["seed"], "n": 1, "stream": False,
    }
    started = time.monotonic()
    status = None
    usage_dict = None
    content = None
    failure_type = None
    try:
        response = requests.post(
            f"http://127.0.0.1:{config['port']}/v1/chat/completions",
            json=payload, timeout=config["request_timeout"],
        )
        status = response.status_code
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {}
        reported = response_payload.get("usage") if isinstance(response_payload, dict) else None
        if isinstance(reported, dict):
            usage_dict = {
                "prompt_tokens": reported.get("prompt_tokens"),
                "completion_tokens": reported.get("completion_tokens"),
                "total_tokens": reported.get("total_tokens"),
            }
            if not all(type(usage_dict[k]) is int and usage_dict[k] >= 0
                       for k in ["prompt_tokens", "completion_tokens", "total_tokens"]):
                usage_dict = None
        ledger_record(config, call_id, status, usage_dict)
        if status == 200:
            try:
                content = response_payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                failure_type = "missing_chat_content"
        else:
            failure_type = "http_error"
    except requests.RequestException as error:
        failure_type = type(error).__name__
        ledger_record(config, call_id, status, None)
    elapsed = time.monotonic() - started
    attempt = {
        "call_id_sha256": call_id, "mode": mode,
        "http_status": status, "usage": usage_dict,
        "latency_seconds": elapsed, "estimated_prompt_tokens": estimated_input,
        "failure_type": failure_type,
    }
    return content, attempt


def exact_schema_cost(tokenizer, schema, columns, constraints, cache):
    columns = tuple(sorted(set(columns)))
    constraint_ids = tuple(sorted(f["id"] for f in constraints))
    key = (columns, constraint_ids)
    if key not in cache:
        if not columns:
            cache[key] = 0
        else:
            text = serialize_partial(schema, columns, constraints)
            cache[key] = len(tokenizer.encode(text, add_special_tokens=False))
    return cache[key]


def table_coverage_selection(config, tokenizer, schema, table_order, physical_columns,
                             constraints, budget, cost_cache):
    selected_tables = []
    selected = {"columns": [], "tables": [], "constraints": []}
    for table in table_order:
        trial_tables = selected_tables + [table]
        trial_columns = [c for c in physical_columns
                         if schema["column_names_original"][c][0] in trial_tables]
        trial_constraints = [f for f in constraints
                             if f["source_table"] in trial_tables and f["target_table"] in trial_tables]
        tokens = exact_schema_cost(tokenizer, schema, trial_columns, trial_constraints, cost_cache)
        if tokens <= budget:
            selected_tables = trial_tables
            selected = {"columns": trial_columns, "tables": list(selected_tables),
                        "constraints": trial_constraints}
    tokens = exact_schema_cost(tokenizer, schema, selected["columns"],
                               selected["constraints"], cost_cache)
    return {**selected, "semantic_columns": sorted(selected["columns"]),
            "schema_tokens": tokens, "inference_tokens": 0,
            "total_budget_used": tokens, "rejected_columns": 0}


def scalar_column_selection(config, tokenizer, schema, physical_columns, column_order,
                            closure, constraints, budget, cost_cache):
    semantic = []
    rejected = 0
    for column in column_order:
        candidate = closure.expand(semantic + [column])
        tokens = exact_schema_cost(tokenizer, schema, candidate["columns"],
                                   candidate["constraints"], cost_cache)
        if tokens <= budget:
            semantic.append(column)
        else:
            rejected += 1
    closed = closure.expand(semantic)
    tokens = exact_schema_cost(tokenizer, schema, closed["columns"], closed["constraints"], cost_cache)
    return {**closed, "semantic_columns": sorted(semantic), "schema_tokens": tokens,
            "inference_tokens": 0, "total_budget_used": tokens,
            "rejected_columns": rejected}


def witness_selection(tokenizer, schema, requirements, candidate_by_id, closure,
                      constraints, budget, cost_cache, cosine_by_column):
    by_req = [r for r in requirements if r["valid_span"] and r["bindings"]]
    assignments = []

    def selection_cost(rows):
        semantic = sorted({candidate_by_id[x["candidate_id"]]["column_id"] for x in rows})
        closed = closure.expand(semantic)
        tokens = exact_schema_cost(tokenizer, schema, closed["columns"], closed["constraints"], cost_cache)
        return semantic, closed, tokens

    def preference(rows):
        return sum(1.0 / (x["alternative_rank"] + 1) for x in rows)

    while True:
        _, _, current_tokens = selection_cost(assignments)
        covered = {x["requirement_id"] for x in assignments}
        used = {candidate_by_id[x["candidate_id"]]["column_id"] for x in assignments}
        options = []
        for req in by_req:
            if req["requirement_id"] in covered:
                continue
            for binding in req["bindings"]:
                cid = binding["candidate_id"]
                column_id = candidate_by_id[cid]["column_id"]
                if column_id in used:
                    continue
                proposal = assignments + [{
                    "requirement_id": req["requirement_id"],
                    "candidate_id": cid,
                    "operator": binding["operator"],
                    "alternative_rank": binding["rank"],
                }]
                _, _, tokens = selection_cost(proposal)
                if tokens > budget:
                    continue
                delta = max(1, tokens - current_tokens)
                utility = (1.0 / delta, -binding["rank"],
                           float(cosine_by_column.get(column_id, -1.0)), -tokens,
                           req["requirement_id"], cid)
                options.append((utility, proposal))
        if options:
            options.sort(key=lambda x: x[0], reverse=True)
            assignments = options[0][1]
            continue

        # Reassign an earlier witness when an alternative lowers exact shared cost.
        current_signature = (
            current_tokens,
            -preference(assignments),
            tuple(sorted((x["requirement_id"], x["candidate_id"], x["operator"])
                         for x in assignments)),
        )
        replacement = None
        for index, existing in enumerate(assignments):
            other_used = {candidate_by_id[x["candidate_id"]]["column_id"]
                          for j, x in enumerate(assignments) if j != index}
            replaceable = [
                req for req in by_req
                if req["requirement_id"] == existing["requirement_id"]
                or req["requirement_id"] not in covered
            ]
            for req in replaceable:
                for binding in req["bindings"]:
                    cid = binding["candidate_id"]
                    if (req["requirement_id"] == existing["requirement_id"]
                            and cid == existing["candidate_id"]):
                        continue
                    column_id = candidate_by_id[cid]["column_id"]
                    if column_id in other_used:
                        continue
                    proposal = list(assignments)
                    proposal[index] = {
                        "requirement_id": req["requirement_id"], "candidate_id": cid,
                        "operator": binding["operator"], "alternative_rank": binding["rank"],
                    }
                    _, _, tokens = selection_cost(proposal)
                    if tokens > budget:
                        continue
                    signature = (
                        tokens,
                        -preference(proposal),
                        tuple(sorted((x["requirement_id"], x["candidate_id"], x["operator"])
                                     for x in proposal)),
                    )
                    if signature < current_signature:
                        if replacement is None or signature < replacement[0]:
                            replacement = (signature, proposal)
        if replacement is None:
            break
        assignments = replacement[1]

    semantic, closed, tokens = selection_cost(assignments)
    assignments.sort(key=lambda x: x["requirement_id"])
    return {**closed, "semantic_columns": semantic, "schema_tokens": tokens,
            "inference_tokens": None, "total_budget_used": None,
            "binding_assignments": assignments,
            "requirements_total": len(requirements),
            "requirements_with_candidates": len(by_req),
            "requirements_witnessed": len(assignments)}


def gpu_free_mib(gpu_id):
    raw = subprocess.check_output([
        "nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"
    ], text=True)
    for line in raw.splitlines():
        index, free = [part.strip() for part in line.split(",", 1)]
        if int(index) == gpu_id:
            return int(free)
    raise RuntimeError(f"GPU {gpu_id} missing from nvidia-smi")


def build_sample(config, inputs, mode):
    excluded = build_exclusions(config)
    prior_count = len(excluded)
    smoke = sample_cases(inputs["questions"], excluded,
                         config["smoke_salt"], config["smoke_count"])
    smoke_ids = {(r["db_id"], int(r["question_id"])) for r in smoke}
    if mode == "smoke":
        return smoke, prior_count, 0
    if len(smoke_ids) != config["smoke_count"]:
        raise ValueError("Smoke sample contains duplicate identities")
    pilot = sample_cases(inputs["questions"], excluded | smoke_ids,
                         config["sample_salt"], config["primary_count"])
    if smoke_ids & {(r["db_id"], int(r["question_id"])) for r in pilot}:
        raise ValueError("Smoke and pilot samples overlap")
    return pilot, prior_count, len(smoke_ids)


def calculate_aggregates(evaluations, attempts, config):
    totals = {arm: Counter() for arm in ARMS}
    macro_recall = {arm: [] for arm in ARMS}
    per_db = defaultdict(lambda: {arm: Counter() for arm in ARMS})
    paired = {BASELINE_TABLE: Counter(), BASELINE_COLUMN: Counter()}
    witness_span_count = witness_req_count = 0
    candidate_reference_columns = candidate_reference_hits = 0
    witness_json_valid = 0
    for row in evaluations:
        rb = row["reference_bindings"]
        if rb["status"] != "ok" or not rb["columns"]:
            for arm in ARMS:
                totals[arm]["unknown_questions"] += 1
            continue
        required = set(rb["columns"])
        complete_flags = {}
        recalls = {}
        for arm in ARMS:
            result = row["arms"][arm]
            selected = set(result["columns"])
            hits = required & selected
            recall = len(hits) / len(required)
            complete = required <= selected
            complete_flags[arm] = complete
            recalls[arm] = recall
            totals[arm]["evaluable_questions"] += 1
            totals[arm]["reference_read_columns"] += len(required)
            totals[arm]["retained_read_columns"] += len(hits)
            totals[arm]["complete_binding_questions"] += int(complete)
            totals[arm]["preparable_questions"] += int(result["expressibility"]["status"] == "compatible")
            totals[arm]["selected_columns"] += len(selected)
            totals[arm]["schema_tokens"] += result["schema_tokens"]
            totals[arm]["inference_tokens"] += result["inference_tokens"] or 0
            totals[arm]["total_budget_used"] += result["total_budget_used"]
            totals[arm]["budget_violations"] += int(result["total_budget_used"] > config["total_budget_tokens"])
            macro_recall[arm].append(recall)
            per_db[row["db_id"]][arm]["evaluable_questions"] += 1
            per_db[row["db_id"]][arm]["reference_read_columns"] += len(required)
            per_db[row["db_id"]][arm]["retained_read_columns"] += len(hits)
            per_db[row["db_id"]][arm]["complete_binding_questions"] += int(complete)
        for baseline in paired:
            left, right = complete_flags[WITNESS], complete_flags[baseline]
            paired[baseline]["rescue"] += int(left and not right)
            paired[baseline]["damage"] += int(right and not left)
            paired[baseline]["unchanged"] += int(left == right)
        pred = row["prediction"][WITNESS]
        witness_json_valid += int(pred["valid_json"])
        witness_req_count += pred["raw_requirement_count"]
        witness_span_count += pred["valid_span_count"]
        candidate_reference_columns += pred.get("candidate_reference_columns", 0)
        candidate_reference_hits += pred.get("candidate_reference_hits", 0)

    requests_with_usage = sum(1 for r in attempts if r.get("usage") is not None)
    request_input = sum(r["usage"]["prompt_tokens"] for r in attempts if r.get("usage"))
    request_output = sum(r["usage"]["completion_tokens"] for r in attempts if r.get("usage"))
    summary = {}
    for arm in ARMS:
        row = dict(totals[arm])
        row["mean_read_binding_recall"] = float(np.mean(macro_recall[arm])) if macro_recall[arm] else None
        row["micro_read_binding_recall"] = (
            row.get("retained_read_columns", 0) / row.get("reference_read_columns", 1)
            if row.get("reference_read_columns", 0) else None)
        denom = row.get("evaluable_questions", 0)
        for key in ["complete_binding_questions", "preparable_questions", "selected_columns",
                    "schema_tokens", "inference_tokens", "total_budget_used"]:
            row["mean_" + key] = row.get(key, 0) / denom if denom else None
        summary[arm] = row
    span_fraction = witness_span_count / witness_req_count if witness_req_count else 0.0
    primary_supported = min(summary[a].get("evaluable_questions", 0) for a in ARMS)
    gate = (
        primary_supported >= config["min_evaluable_questions"]
        and all(summary[WITNESS].get("complete_binding_questions", 0)
                >= summary[b].get("complete_binding_questions", 0) + config["min_complete_binding_delta"]
                for b in [BASELINE_TABLE, BASELINE_COLUMN])
        and summary[WITNESS].get("mean_read_binding_recall", 0)
        >= max(summary[b].get("mean_read_binding_recall", 0) or 0
               for b in [BASELINE_TABLE, BASELINE_COLUMN]) + config["min_mean_binding_recall_delta"]
        and span_fraction >= config["min_valid_span_fraction"]
        and summary[WITNESS].get("budget_violations", 0) == 0
    )
    sorted_dbs = sorted(per_db)
    return {
        "run_id": config["run_id"], "questions": len(evaluations),
        "arms": summary, "paired_complete_bindings": {k: dict(v) for k, v in paired.items()},
        "unknown_reference_binding_questions": sum(
            1 for r in evaluations if r["reference_bindings"]["status"] != "ok" or not r["reference_bindings"]["columns"]),
        "witness_output_json_valid": witness_json_valid,
        "witness_raw_requirements": witness_req_count,
        "witness_exact_spans": witness_span_count,
        "witness_exact_span_fraction": span_fraction,
        "top_candidate_reference_columns": candidate_reference_columns,
        "top_candidate_reference_hits": candidate_reference_hits,
        "top_candidate_reference_recall": (
            candidate_reference_hits / candidate_reference_columns
            if candidate_reference_columns else None),
        "local_model_requests": len(attempts),
        "local_model_requests_with_usage": requests_with_usage,
        "local_model_requests_without_usage": len(attempts) - requests_with_usage,
        "local_model_input_tokens": request_input,
        "local_model_output_tokens": request_output,
        "local_model_total_tokens": request_input + request_output,
        "per_database_anonymized": {
            f"DB-{i + 1:02d}": {arm: dict(per_db[db][arm]) for arm in ARMS}
            for i, db in enumerate(sorted_dbs)
        },
        "pilot_gate": bool(gate),
        "decision": "SEPARATE_HELDOUT_STUDY_ALLOWED" if gate else "STOP_THIS_VERSION",
        "interpretation": "BIRD-dev structural read-binding proxy; not semantic SQL correctness or SQL EX",
    }


def run(args):
    os.umask(0o077)
    config = read_config(args.config)
    if args.mode == "preflight":
        output = Path(config["result_root"]) / "preflight_001"
        new_output(output)
        model_receipt = verify_model_files(config)
        inputs = load_inputs(config)
        smoke, excluded_count, _ = build_sample(config, inputs, "smoke")
        pilot, pilot_excluded, smoke_excluded = build_sample(config, inputs, "pilot")
        tokenizer = AutoTokenizer.from_pretrained(
            config["sql_model"], local_files_only=True, use_fast=True)
        if not tokenizer.is_fast:
            raise ValueError("Qwen tokenizer must be fast for stable token accounting")
        manifest = {
            "run_id": config["run_id"], "mode": "preflight",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True).strip(),
            "config_sha256": sha256(args.config),
            "input_hashes_verified": {
                "questions": config["questions_sha256"],
                "schema": config["schema_sha256"],
                "cache": config["cache_sha256"],
                "node_manifest": config["node_manifest_sha256"],
            },
            "model_files_hashes_verified": model_receipt["actual_sha256"],
            "question_count": len(inputs["questions"]),
            "database_count": len(inputs["schemas"]),
            "smoke_count": len(smoke), "pilot_count": len(pilot),
            "prior_exclusion_count": excluded_count,
            "pilot_exclusion_count": pilot_excluded,
            "smoke_excluded_from_pilot": smoke_excluded,
            "sample_overlap": bool({(r["db_id"], r["question_id"]) for r in smoke}
                                   & {(r["db_id"], r["question_id"]) for r in pilot}),
            "tokenizer_fast": tokenizer.is_fast,
            "model_requests": 0,
            "reference_sql_read": False,
            "decision": "READY_FOR_RESOURCE_GATE",
        }
        if (len(smoke) != config["smoke_count"]
                or len(pilot) != config["primary_count"]
                or excluded_count != 433 or pilot_excluded != 433
                or smoke_excluded != config["smoke_count"]
                or manifest["sample_overlap"]):
            manifest["decision"] = "STOP_PREFLIGHT"
            write_json(output / "preflight_manifest.json", manifest)
            raise ValueError("Sample or exclusion preflight gate failed")
        write_json(output / "preflight_manifest.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
        return
    if args.mode not in {"smoke", "pilot"}:
        raise ValueError("Invalid mode")
    if args.mode == "smoke":
        output = Path(config["smoke_output"])
    else:
        smoke_summary_path = Path(config["smoke_output"]) / "aggregate_summary.json"
        if not smoke_summary_path.exists():
            raise FileNotFoundError("Smoke must complete before pilot")
        smoke_summary = json.loads(smoke_summary_path.read_text(encoding="utf-8"))
        if not smoke_summary.get("smoke_gate"):
            raise ValueError("Pilot blocked by failed smoke gate")
        output = Path(config["result_root"]) / "pilot_001"
    new_output(output)
    started_wall, started_cpu = time.monotonic(), time.process_time()
    receipt_path = Path(config["smoke_output"]) / "model_hash_receipt.json"
    model_receipt = verify_model_files(config, receipt_path if args.mode == "pilot" else None)
    if args.mode == "smoke":
        write_json(receipt_path, model_receipt)
    if gpu_free_mib(config["gpu_ids"][0]) < config["post_allocation_margin_mib"]:
        raise RuntimeError("GPU post-allocation free-memory margin below registered threshold")
    config_sha = sha256(args.config)
    write_json(output / "run_start.json", {
        "run_id": config["run_id"], "mode": args.mode,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv, "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "config_sha256": config_sha, "python": sys.version, "executable": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ["numpy", "networkx", "transformers", "sqlglot", "requests"]},
        "model": "Qwen2.5-Coder-7B-Instruct-local", "served_model": config["served_model"],
        "vllm_version": "0.8.5", "model_file_hashes": model_receipt["actual_sha256"],
        "resources": {
            "nvidia_smi": subprocess.check_output(["nvidia-smi"], text=True),
            "free_h": subprocess.check_output(["free", "-h"], text=True),
            "nproc": subprocess.check_output(["nproc"], text=True).strip(),
            "gpu0_free_mib_after_service_load": gpu_free_mib(config["gpu_ids"][0]),
        },
    })
    attempts = []
    try:
        inputs = load_inputs(config)
        chosen, excluded_count, smoke_excluded = build_sample(config, inputs, args.mode)
        if args.mode == "pilot" and (excluded_count != 433 or smoke_excluded != 5):
            raise ValueError("Pilot sample exclusion counts differ from preregistration")
        tokenizer = AutoTokenizer.from_pretrained(config["sql_model"], local_files_only=True, use_fast=True)
        if not tokenizer.is_fast:
            raise ValueError("Qwen tokenizer must be fast for stable token accounting")
        schemas = inputs["schemas"]
        physical_by_db = {}
        column_ord_by_db = {}
        table_ord_by_db = {}
        column_vectors = {}
        table_vectors = {}
        closure_by_db = {}
        cost_cache_by_db = {}
        for db, schema in schemas.items():
            nodes = [node for node in inputs["nodes"] if node["db_id"] == db]
            column_ord = {int(n["node_id"].rsplit(":", 1)[-1]): n["ordinal"]
                          for n in nodes if n["node_type"] == "column"}
            table_ord = {int(n["node_id"].rsplit(":", 1)[-1]): n["ordinal"]
                         for n in nodes if n["node_type"] == "table"}
            physical = sorted(c for c, (owner, _) in enumerate(schema["column_names_original"]) if owner >= 0)
            if set(column_ord) != set(physical):
                raise ValueError(f"Physical column node identity mismatch for {db}")
            if set(table_ord) != set(range(len(schema["table_names_original"]))):
                raise ValueError(f"Table node identity mismatch for {db}")
            physical_by_db[db] = physical
            column_ord_by_db[db] = column_ord
            table_ord_by_db[db] = table_ord
            column_vectors[db] = {c: inputs["vectors"][column_ord[c]] for c in physical}
            table_vectors[db] = {t: inputs["vectors"][table_ord[t]]
                                 for t in range(len(schema["table_names_original"]))}
            closure_by_db[db] = SchemaClosure(schema, inputs["constraints"][db])
            cost_cache_by_db[db] = {}

        query_index = {(r["db_id"], int(r["question_id"])): i for i, r in enumerate(inputs["questions"])}
        predictions = []
        input_tokens_so_far = output_tokens_so_far = 0
        for row in chosen:
            db, qid = row["db_id"], int(row["question_id"])
            schema = schemas[db]
            qvec = inputs["queries"][query_index[(db, qid)]]
            physical = physical_by_db[db]
            constraints = inputs["constraints"][db]
            closure = closure_by_db[db]
            cost_cache = cost_cache_by_db[db]
            query_scores = {c: float(np.dot(column_vectors[db][c], qvec)) for c in physical}
            column_order = sorted(physical, key=lambda c: (-query_scores[c], c))
            table_ids = list(range(len(schema["table_names_original"])) )
            table_order = sorted(table_ids, key=lambda t: (-float(np.dot(table_vectors[db][t], qvec)), t))

            table_arm = table_coverage_selection(
                config, tokenizer, schema, table_order, physical, constraints,
                config["total_budget_tokens"], cost_cache,
            )
            column_arm = scalar_column_selection(
                config, tokenizer, schema, physical, column_order, closure, constraints,
                config["total_budget_tokens"], cost_cache,
            )
            candidates = []
            candidate_by_id = {}
            for rank, column_id in enumerate(column_order[:config["candidate_limit"]]):
                candidate_id = f"C{rank:02d}"
                table_id, column_name = schema["column_names_original"][column_id]
                candidate = {
                    "candidate_id": candidate_id,
                    "table": schema["table_names_original"][table_id],
                    "column": column_name,
                    "column_type": schema["column_types"][column_id],
                }
                candidates.append(candidate)
                candidate_by_id[candidate_id] = {**candidate, "column_id": column_id, "rank": rank}
            content, attempt = call_qwen(config, tokenizer, row, candidates, args.mode, 1)
            attempts.append(attempt)
            if attempt["usage"] is None or attempt["http_status"] != 200:
                write_jsonl(output / "model_usage_private.jsonl", attempts)
                raise RuntimeError("Local inference failed or usage is missing; no retry is permitted")
            input_tokens_so_far += attempt["usage"]["prompt_tokens"]
            output_tokens_so_far += attempt["usage"]["completion_tokens"]
            if input_tokens_so_far > config["max_input_tokens"] or output_tokens_so_far > config["max_output_tokens"]:
                write_jsonl(output / "model_usage_private.jsonl", attempts)
                raise RuntimeError("Registered aggregate token budget exceeded")
            parsed = parse_requirements(content, row["question"], candidate_by_id, config)
            inference_tokens = attempt["usage"]["prompt_tokens"] + attempt["usage"]["completion_tokens"]
            context_budget = max(0, config["total_budget_tokens"] - inference_tokens)
            witness = witness_selection(
                tokenizer, schema, parsed["requirements"], candidate_by_id, closure,
                constraints, context_budget, cost_cache,
                {c: query_scores[c] for c in physical},
            )
            schema_tokens = witness["schema_tokens"]
            total_used = inference_tokens + schema_tokens
            witness.update({
                "inference_tokens": inference_tokens,
                "total_budget_used": total_used,
                "context_budget": context_budget,
                "valid_json": parsed["valid_json"],
                "raw_requirement_count": parsed["raw_requirement_count"],
                "valid_span_count": parsed["valid_span_count"],
                "invalid_binding_count": parsed["invalid_binding_count"],
                "requirements": parsed["requirements"],
                "candidate_ids": [c["candidate_id"] for c in candidates],
                "candidate_limit": len(candidates),
                "candidate_reference_recall_pending": True,
                "request_call_id_sha256": attempt["call_id_sha256"],
            })
            arms = {BASELINE_TABLE: table_arm, BASELINE_COLUMN: column_arm, WITNESS: witness}
            for arm, result in arms.items():
                if arm != WITNESS:
                    result["context_budget"] = config["total_budget_tokens"]
                    result["total_budget_used"] = result["schema_tokens"]
                if result["schema_tokens"] > config["total_budget_tokens"]:
                    raise RuntimeError("Schema context exceeds registered total-token budget")
                if result["total_budget_used"] > config["total_budget_tokens"]:
                    raise RuntimeError("Inference plus schema exceeds registered total-token budget")
                result["constraints"] = [f["id"] for f in result.pop("constraints")]
            predictions.append({
                "db_id": db, "question_id": qid,
                "candidate_reference_recall_pending": True,
                "arms": {arm: {
                    **{k: v for k, v in value.items() if k != "requirements"},
                } for arm, value in arms.items()},
                "witness_requirements_private": witness["requirements"],
                "candidate_columns_private": candidates,
            })

        predictions_path = output / "predictions_private.json"
        write_json(predictions_path, predictions)
        prediction_seal = sha256(predictions_path)
        write_json(output / "prediction_seal.json", {
            "sha256": prediction_seal, "questions": len(predictions),
            "reference_not_used_for_sampling_or_selection": True,
        })
        write_jsonl(output / "model_usage_private.jsonl", attempts)

        # Reference SQL and its physical read bindings are opened only after predictions are sealed.
        references = {(r["db_id"], int(r["question_id"])): r["SQL"]
                      for r in read_reference_rows(config)}
        by_key = {(r["db_id"], int(r["question_id"])): r for r in predictions}
        evaluations = []
        aggregate_predictions = []
        for pred in predictions:
            key = (pred["db_id"], int(pred["question_id"]))
            db = pred["db_id"]
            schema = schemas[db]
            sql = references[key]
            read_bindings = reference_read_bindings(sql, schema)
            arms_eval = {}
            for arm in ARMS:
                choice = pred["arms"][arm]
                result = expressibility(sql, schema, choice["columns"])
                arms_eval[arm] = {
                    "columns": choice["columns"],
                    "tables": choice["tables"],
                    "schema_tokens": choice["schema_tokens"],
                    "inference_tokens": choice["inference_tokens"],
                    "total_budget_used": choice["total_budget_used"],
                    "expressibility": result,
                }
            gold_columns = set(read_bindings.get("columns", [])) if read_bindings["status"] == "ok" else set()
            witness_candidates = {
                item["candidate_id"]: item["column_id"]
                for item in pred["candidate_columns_private"]
            }
            candidate_hits = sum(1 for c in gold_columns if c in set(witness_candidates.values()))
            prediction_view = pred["arms"][WITNESS]
            prediction_view["candidate_reference_columns"] = len(gold_columns)
            prediction_view["candidate_reference_hits"] = candidate_hits
            prediction_view["candidate_reference_recall"] = (
                candidate_hits / len(gold_columns) if gold_columns else None)
            evaluation = {
                "db_id": db, "question_id": key[1],
                "reference_bindings": read_bindings,
                "arms": arms_eval,
                "prediction": {WITNESS: {
                    "valid_json": prediction_view["valid_json"],
                    "raw_requirement_count": prediction_view["raw_requirement_count"],
                    "valid_span_count": prediction_view["valid_span_count"],
                    "candidate_reference_columns": prediction_view["candidate_reference_columns"],
                    "candidate_reference_hits": prediction_view["candidate_reference_hits"],
                    "candidate_reference_recall": prediction_view["candidate_reference_recall"],
                }},
            }
            evaluations.append(evaluation)
            aggregate_predictions.append(evaluation)
        if sha256(predictions_path) != prediction_seal:
            raise RuntimeError("Prediction seal changed during evaluation")
        write_json(output / "evaluations_private.json", evaluations)
        summary = calculate_aggregates(aggregate_predictions, attempts, config)
        summary["mode"] = args.mode
        summary["excluded_prior_cases"] = excluded_count
        summary["smoke_cases_excluded_from_pilot"] = smoke_excluded
        summary["prediction_sha256"] = prediction_seal
        summary["config_sha256"] = config_sha
        summary["wall_seconds"] = time.monotonic() - started_wall
        summary["cpu_seconds"] = time.process_time() - started_cpu
        summary["peak_RSS_GiB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2)
        if args.mode == "smoke":
            summary["smoke_gate"] = (
                summary["local_model_requests_with_usage"] == config["smoke_count"]
                and summary["witness_output_json_valid"] >= 4
                and summary["arms"][WITNESS]["budget_violations"] == 0
            )
            summary["decision"] = "PILOT_ALLOWED" if summary["smoke_gate"] else "STOP_SMOKE_GATE"
        write_json(output / "aggregate_summary.json", summary)
        write_json(output / "verification.json", {
            "prediction_seal_unchanged": sha256(predictions_path) == prediction_seal,
            "predictions_match_sample_count": len(predictions) == (config["smoke_count"] if args.mode == "smoke" else config["primary_count"]),
            "no_duplicate_question_identity": len({(r["db_id"], r["question_id"]) for r in predictions}) == len(predictions),
            "all_arms_within_total_token_budget": all(
                all(r["arms"][arm]["total_budget_used"] <= config["total_budget_tokens"] for arm in ARMS)
                for r in predictions),
            "no_reference_used_before_prediction_seal": True,
            "verified_reference_questions": len(evaluations),
            "aggregate_recomputed_from_sealed_evaluations": True,
        })
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    except Exception as error:
        write_jsonl(output / "model_usage_private.jsonl", attempts)
        write_json(output / "failure_manifest.json", {
            "run_id": config["run_id"], "mode": args.mode,
            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            "exception_type": type(error).__name__, "prediction_count_written": len(locals().get("predictions", [])),
            "local_model_attempts": len(attempts),
        })
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=["preflight", "smoke", "pilot"], required=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
