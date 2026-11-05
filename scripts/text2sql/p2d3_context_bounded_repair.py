#!/usr/bin/env python3
"""Run frozen P2d.3 one-shot SQL repair arms against private prepared cases."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.text2sql import p2d_inputs
from scripts.text2sql import p2d_sql_evaluator as evaluator

EXPERIMENT = "p2d3_context_bounded_repair_20261105_01"
PROJECT = "gfm-rag-p2d3-context-repair"
REPORT = ROOT / "docs/research/text2sql/reports" / EXPERIMENT
SOURCE_FILES = (
    "scripts/text2sql/p2d_inputs.py",
    "scripts/text2sql/p2d_sql_evaluator.py",
    "scripts/text2sql/p2d3_prepare_inputs.py",
    "scripts/text2sql/p2d3_context_bounded_repair.py",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path: Path, value) -> None:
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_jsonl_new(path: Path, rows) -> None:
    with Path(path).open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_sql(content: str) -> str:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    if value[:4].casefold() == "sql:":
        value = value[4:].strip()
    return value


def repair_messages(case: dict, context: str, initial_sql: str, diagnostic: str) -> list[dict]:
    system = ("You are a SQLite SQL repair expert. Return exactly one read-only SELECT query, "
              "using only the supplied schema and evidence. Repair only the reported parse, "
              "schema, or scope problem while preserving the question's intent. Do not invent "
              "tables or columns. Return SQL only, without explanations.")
    user = (
        f"Database schema context:\n{context}\n\n"
        f"Question: {case['question']}\nEvidence: {case.get('evidence', '')}\n\n"
        f"Initial SQL:\n{initial_sql}\n\n"
        f"Normalized diagnostic: {diagnostic}\n\n"
        "Return one repaired SQL query only."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def service_identity(model: str, prepared_root: Path) -> dict:
    base_url = os.environ.get("P2D3_LOCAL_BASE_URL")
    pid_text = os.environ.get("P2D3_LOCAL_SERVICE_PID")
    if not base_url or not pid_text:
        raise RuntimeError("The registered local inference service is not configured")
    pid = int(pid_text)
    proc_cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    arguments = [part.decode("utf-8", errors="replace") for part in proc_cmdline.split(b"\0") if part]
    if "--model" in arguments:
        model_index = arguments.index("--model") + 1
    else:
        try:
            model_index = arguments.index("serve") + 1
        except ValueError as exc:
            raise RuntimeError("Local inference process does not expose a model argument") from exc
    if model_index >= len(arguments) or arguments[model_index].startswith("-"):
        raise RuntimeError("Local inference process does not expose a model argument")
    model_root = Path(arguments[model_index]).resolve(strict=True)
    manifest = read(prepared_root / "model_manifest_private.json")
    expected_root = Path(manifest["model_root_private"]).resolve(strict=True)
    if model_root != expected_root:
        raise RuntimeError("Local inference process is serving a different model path")
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/models", method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        metadata = json.load(response)
    models = [(row["id"], row.get("max_model_len")) for row in metadata.get("data", [])]
    if models != [(model, 32768)]:
        raise RuntimeError("Local inference endpoint model metadata differs from registration")
    return {
        "base_url_private": base_url.rstrip("/"),
        "pid": pid,
        "cmdline_sha256": sha_bytes(proc_cmdline),
        "model_root_private": str(model_root),
        "models": models,
    }


def current_source(expected_commit: str) -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    if head != expected_commit or status:
        raise RuntimeError("Run source is not the clean registered published commit")
    remote = subprocess.check_output(["git", "rev-parse", f"origin/{branch}"], cwd=ROOT, text=True).strip()
    if remote != expected_commit:
        raise RuntimeError("Published branch does not point to the registered run source")
    return {
        "commit": head,
        "branch": branch,
        "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
        "source_sha256": {name: sha(ROOT / name) for name in SOURCE_FILES},
        "dependencies": {name: importlib.metadata.version(name) for name in ("sqlglot", "transformers", "tokenizers")},
    }


def verify_prepared(prepared_root: Path, expected_seal: str) -> dict:
    seal_path = prepared_root / "prepare_seal_private.json"
    if sha(seal_path) != expected_seal:
        raise RuntimeError("Private preparation seal differs from registered value")
    seal = read(seal_path)
    for relative, expected in seal["files"].items():
        if sha(prepared_root / relative) != expected:
            raise RuntimeError("Private prepared input changed after sealing")
    for case in seal["cases"]:
        if sha(prepared_root / case["file"]) != case["sha256"]:
            raise RuntimeError("Private case changed after sealing")
    for item in seal["input_hashes_private"].values():
        if sha(Path(item["path_private"])) != item["sha256"]:
            raise RuntimeError("A frozen input artifact changed")
    for item in seal["database_manifest_private"].values():
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Frozen SQLite database snapshot changed")
    model_manifest = read(prepared_root / "model_manifest_private.json")
    model_root = Path(model_manifest["model_root_private"])
    for relative, expected in model_manifest["files"].items():
        if sha(model_root / relative) != expected:
            raise RuntimeError("Frozen local model file changed")
    return seal


def check_database_hashes(evaluation: dict) -> None:
    by_db = {}
    for item in evaluation.values():
        path = Path(item["database_path_private"])
        expected = item["database_sha256"]
        if path not in by_db:
            by_db[path] = expected
    for path, expected in by_db.items():
        if sha(path) != expected:
            raise RuntimeError("Frozen SQLite database hash mismatch")


def parse_one_select(sql: str) -> None:
    trees = __import__("sqlglot").parse(sql, read="sqlite")
    trees = [tree for tree in trees if tree is not None]
    roots = (evaluator.exp.Select, evaluator.exp.Union, evaluator.exp.Intersect, evaluator.exp.Except)
    if len(trees) != 1 or not isinstance(trees[0], roots):
        raise ValueError("not_one_select")
    evaluator._validate_sql(sql)


def compile_readonly(db_path: Path, sql: str, allowed_catalog: dict | None = None) -> dict:
    """Compile only; do not fetch query rows or expose SQLite diagnostics."""
    try:
        parse_one_select(sql)
    except Exception as exc:
        if isinstance(exc, (ValueError, evaluator.ParseError)) or exc.__class__.__module__.startswith("sqlglot"):
            return {"status": "parse_or_structure_failure", "denied_reads": 0}
        return {"status": "unsafe_or_other_failure", "denied_reads": 0}

    denied: list[tuple[str, str]] = []
    read_set: set[tuple[str, str]] = set()
    allowed = None
    if allowed_catalog is not None:
        allowed = allowed_catalog["allowed_columns_by_casefolded_table"]

    def authorize(action, first, second, database, trigger):
        if action == sqlite3.SQLITE_READ:
            table = (first or "").casefold()
            column = (second or "").casefold()
            read_set.add((table, column))
            if allowed is not None:
                permitted = table in allowed and (column == "" or column in allowed[table])
                if not permitted:
                    denied.append((table, column))
                    return sqlite3.SQLITE_DENY
        return evaluator._authorize(action, first, second, database, trigger)

    connection = None
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=0)
        connection.enable_load_extension(False)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.set_authorizer(authorize)
        cursor = connection.execute("EXPLAIN " + sql)
        for _ in cursor:
            pass
        if denied:
            return {"status": "out_of_context_identifier", "denied_reads": len(set(denied)),
                    "read_count": len(read_set)}
        return {"status": "compiled", "denied_reads": 0, "read_count": len(read_set)}
    except sqlite3.Error as exc:
        if denied or "not authorized" in str(exc).casefold() or getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH:
            return {"status": "out_of_context_identifier" if allowed is not None else "schema_or_scope_compile_failure",
                    "denied_reads": max(1, len(set(denied))), "read_count": len(read_set)}
        if getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_ERROR, sqlite3.SQLITE_SCHEMA):
            return {"status": "schema_or_scope_compile_failure", "denied_reads": 0, "read_count": len(read_set)}
        return {"status": "unsafe_or_other_failure", "denied_reads": len(set(denied)), "read_count": len(read_set)}
    finally:
        if connection is not None:
            connection.close()


def authorization_gate() -> dict:
    """Prove selected-column reads pass and unselected table reads are denied."""
    with tempfile.TemporaryDirectory(prefix="p2d3_authorizer_gate_") as directory:
        path = Path(directory) / "gate.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE allowed_table(id INTEGER)")
        connection.execute("CREATE TABLE hidden_table(secret INTEGER)")
        connection.commit()
        connection.close()
        allowed = {"allowed_columns_by_casefolded_table": {"allowed_table": ["id"]}}
        visible = compile_readonly(path, "SELECT id FROM allowed_table", allowed)
        hidden = compile_readonly(path, "SELECT secret FROM hidden_table", allowed)
        if visible["status"] != "compiled" or hidden["status"] != "out_of_context_identifier":
            raise RuntimeError("A2 read-authorizer synthetic gate failed")
        return {"status": "PASS", "visible_read": visible["status"], "hidden_read": hidden["status"]}


def call_history(result_root: Path) -> list[dict]:
    rows = []
    for path in sorted(result_root.glob("*/requests/*.response.json")):
        rows.append(read(path))
    return rows


def request_model(result_root: Path, output_dir: Path, prepared_root: Path, identity: dict,
                  run_id: str, case_id: str, call_kind: str, messages: list[dict], max_tokens: int,
                  config: dict, tokenizer) -> dict:
    history = call_history(result_root)
    if len(history) >= config["runtime"]["max_model_requests"]:
        raise RuntimeError("Registered maximum model request count reached")
    prompt_tokens = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    if prompt_tokens + max_tokens > config["model"]["max_model_len"]:
        raise RuntimeError("Prompt plus output budget exceeds frozen model context")
    used_input = sum(row.get("usage", {}).get("prompt_tokens", 0) for row in history)
    used_output = sum(row.get("usage", {}).get("completion_tokens", 0) for row in history)
    if used_input + prompt_tokens > config["runtime"]["max_input_tokens"]:
        raise RuntimeError("Registered input-token budget reached")
    if used_output + max_tokens > config["runtime"]["max_output_tokens"]:
        raise RuntimeError("Registered output-token budget reached")

    call_id = f"{EXPERIMENT}/{run_id}/{case_id}/{call_kind}"
    payload = {
        "model": config["model"]["served_model_name"],
        "messages": messages,
        "temperature": config["model"]["temperature"],
        "top_p": config["model"]["top_p"],
        "top_k": config["model"]["top_k"],
        "repetition_penalty": config["model"]["repetition_penalty"],
        "seed": config["model"]["seed"],
        "max_tokens": max_tokens,
        "n": 1,
        "stream": False,
    }
    request_dir = output_dir / "requests"
    request_dir.mkdir(exist_ok=True)
    request_path = request_dir / f"{case_id}-{call_kind}.request.json"
    response_path = request_dir / f"{case_id}-{call_kind}.response.json"
    write_new(request_path, {"call_id": call_id, "payload": payload, "payload_sha256": digest(payload)})
    base_url = identity["base_url_private"]
    remaining = config["_deadline_epoch"] - time.time()
    if remaining <= 0:
        raise RuntimeError("Registered total Smoke + Full wall-clock budget is exhausted")
    timeout = min(config["runtime"]["request_timeout_seconds"], remaining)
    began = time.perf_counter()
    occurred = datetime.now(timezone.utc).isoformat()
    http_status = None
    usage = {}
    response = None
    error_type = None
    try:
        request = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as handle:
            http_status = handle.status
            response = json.load(handle)
        usage = response.get("usage") or {}
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        error_type = type(exc).__name__
        try:
            body = json.loads(exc.read())
            usage = body.get("usage") or {}
            response = body if usage else None
        except Exception:
            response = None
    except Exception as exc:
        error_type = type(exc).__name__
    if time.time() >= config["_deadline_epoch"]:
        error_type = error_type or "total_wall_budget_exhausted"

    record = {
        "call_id": call_id,
        "run_id": run_id,
        "case_id": case_id,
        "call_kind": call_kind,
        "usage": usage,
        "http_status": http_status,
        "occurred_at": occurred,
        "wall_seconds": time.perf_counter() - began,
        "error_type": error_type,
        "response": response,
    }
    write_new(response_path, record)

    ledger_dir = Path(os.environ["P2D3_LEDGER_DIR"]).resolve(strict=True)
    if str(ledger_dir) not in sys.path:
        sys.path.insert(0, str(ledger_dir))
    from api_usage_ledger import record_request
    record_request(
        call_id=call_id,
        provider="local_vllm",
        project=PROJECT,
        run_id=run_id,
        model=config["model"]["served_model_name"],
        http_status=http_status,
        usage=usage,
        occurred_at=occurred,
        db_path=Path(os.environ["P2D3_USAGE_DB"]).resolve(strict=True),
    )
    if error_type or http_status != 200 or response is None:
        raise RuntimeError("Local inference request failed; registered no-retry stop")
    if not all(type(usage.get(key)) is int and usage[key] >= 0
               for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
        raise RuntimeError("Local inference usage missing; request recorded as unknown and stopped")
    if usage["prompt_tokens"] != prompt_tokens or usage["total_tokens"] < usage["prompt_tokens"] + usage["completion_tokens"]:
        raise RuntimeError("Local tokenizer/endpoint usage contract mismatch")
    choices = response.get("choices") or []
    if len(choices) != 1 or not isinstance(choices[0].get("message", {}).get("content"), str):
        raise RuntimeError("Local inference response did not contain exactly one text choice")
    return {
        "sql_private": extract_sql(choices[0]["message"]["content"]),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": usage,
        "prompt_tokens_local": prompt_tokens,
        "request_wall_seconds": record["wall_seconds"],
        "call_id": call_id,
    }


def execute_if_compiled(db: Path, sql: str, config: dict) -> dict:
    result = evaluator.execute_readonly(
        db, sql,
        timeout=config["sql"]["timeout_seconds"],
        row_limit=config["sql"]["row_limit"],
        byte_limit=config["sql"]["byte_limit"],
        sqlite_memory_limit=config["sql"]["sqlite_memory_limit"],
    )
    return result


def sql_results_to_public(predicted: dict, reference: dict) -> dict:
    if predicted.get("status") != "ok" or reference.get("status") != "ok":
        return {"set_correct": False, "bag_correct": False, "comparison_status": "execution_unavailable"}
    if len(predicted.get("columns", [])) != len(reference.get("columns", [])):
        return {"set_correct": False, "bag_correct": False, "comparison_status": "column_count_mismatch"}
    result = evaluator.compare_rows(predicted["rows"], reference["rows"])
    return {
        "set_correct": result["set_correct"] is True,
        "bag_correct": result["bag_correct"] is True,
        "comparison_status": result["comparison_status"],
    }


def call_ledger_snapshot(path: Path) -> dict:
    ledger_dir = Path(os.environ["P2D3_LEDGER_DIR"]).resolve(strict=True)
    if str(ledger_dir) not in sys.path:
        sys.path.insert(0, str(ledger_dir))
    from api_usage_ledger import totals
    total = totals(path)
    project_runs = [row for row in total["by_project_and_run"] if row["project"] == PROJECT]
    return {"shared_totals": total, "this_project": project_runs}


def run_stage(args, config: dict) -> None:
    result_root = args.result_root.resolve(strict=True)
    prepared_root = result_root / config["run_dirs"]["prepare"]
    source = current_source(args.expected_commit)
    seal = verify_prepared(prepared_root, args.expected_seal_sha256)
    identity = service_identity(config["model"]["served_model_name"], prepared_root)
    stage_id = config["run_ids"][args.stage]
    output_dir = result_root / config["run_dirs"][args.stage]
    output_dir.mkdir(exist_ok=False)
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    if args.stage == "full":
        experiment_start_epoch = read(result_root / config["run_dirs"]["smoke"] / "run_start.json")["experiment_start_epoch"]
    else:
        experiment_start_epoch = time.time()
    receipt = {
        "experiment_id": EXPERIMENT,
        "run_id": stage_id,
        "stage": args.stage,
        "state": "started",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "service_identity_private": identity,
        "prepare_seal_sha256_private": sha(prepared_root / "prepare_seal_private.json"),
        "experiment_start_epoch": experiment_start_epoch,
        "private_sample_ids_published": False,
        "command": sys.argv,
    }
    config["_deadline_epoch"] = experiment_start_epoch + config["runtime"]["max_total_wall_seconds"]
    write_new(output_dir / "run_start.json", receipt)
    try:
        if time.time() - experiment_start_epoch >= config["runtime"]["max_total_wall_seconds"]:
            raise RuntimeError("Registered total Smoke + Full wall-clock budget is exhausted")
        if args.stage == "full":
            smoke = read(result_root / config["run_dirs"]["smoke"] / "aggregate_summary.json")
            if smoke.get("stage") != "smoke" or smoke.get("smoke_gate") != "PASS":
                raise RuntimeError("Full run requires the registered passing smoke receipt")
            smoke_start = read(result_root / config["run_dirs"]["smoke"] / "run_start.json")
            if smoke_start.get("source") != source or smoke_start.get("service_identity_private") != identity:
                raise RuntimeError("Full run source or inference service differs from smoke")

        auth_gate = authorization_gate()
        selected_cases = [item for item in seal["cases"] if item["cohort"] == args.stage]
        if len(selected_cases) != (5 if args.stage == "smoke" else 66):
            raise RuntimeError("Prepared sample size differs from registration")
        from transformers import AutoTokenizer
        manifest = read(prepared_root / "model_manifest_private.json")
        tokenizer = AutoTokenizer.from_pretrained(
            manifest["model_root_private"], local_files_only=True, trust_remote_code=True,
        )
        predictions = []
        prediction_map = {}
        request_wall = 0.0
        for index, item in enumerate(selected_cases):
            if time.time() >= config["_deadline_epoch"]:
                raise RuntimeError("Registered total Smoke + Full wall-clock budget is exhausted")
            case = read(prepared_root / item["file"])
            db = Path(case["database_path_private"])
            initial = request_model(
                result_root, output_dir, prepared_root, identity, stage_id, item["case_id"], "initial",
                case["initial_messages_private"], config["model"]["initial_max_tokens"], config, tokenizer,
            )
            request_wall += initial["request_wall_seconds"]
            full_catalog = case["allowed_catalog_private"]
            # The full-schema comparator is derived from the same frozen database schema.
            # A1 permits every table/column; A2 uses only selected V00 nodes.
            full_catalog_for_db = {"allowed_columns_by_casefolded_table": None}
            initial_check = compile_readonly(db, initial["sql_private"])
            initial_a2_context_check = (
                compile_readonly(db, initial["sql_private"], full_catalog)
                if initial_check["status"] == "compiled" else initial_check
            )
            initial_exec = None
            if initial_check["status"] == "compiled":
                initial_exec = execute_if_compiled(db, initial["sql_private"], config)
                if initial_exec.get("status") != "ok":
                    # A successful compile followed by a bounded execution failure is not repairable by this protocol.
                    initial_exec = {"status": initial_exec.get("status"), "error_type": initial_exec.get("error_type", "execution_error")}
            initial_public = {
                "parse_or_schema_compile_status": initial_check["status"],
                "a2_context_compile_status": initial_a2_context_check["status"],
                "execution_status": (initial_exec or {}).get("status", initial_check["status"]),
            }
            for arm in ("A0", "A1", "A2"):
                arm_sql = initial["sql_private"]
                arm_initial_check = initial_a2_context_check if arm == "A2" else initial_check
                arm_initial_diagnostic = arm_initial_check["status"]
                if arm == "A2" and arm_initial_diagnostic == "out_of_context_identifier":
                    # Do not expose identifier names; report only the frozen diagnostic category.
                    arm_initial_diagnostic = "schema_or_scope_compile_failure"
                arm_exec = initial_exec if arm_initial_check["status"] == "compiled" else None
                repair_attempted = False
                repair_accepted = False
                repair_status = "not_triggered"
                initial_context_denied = arm == "A2" and initial_a2_context_check["status"] == "out_of_context_identifier"
                denied_reads = (initial_a2_context_check.get("denied_reads", 0) if initial_context_denied else 0)
                if initial_context_denied:
                    repair_status = "initial_rejected_out_of_context"
                if arm != "A0" and arm_initial_diagnostic in {
                    "parse_or_structure_failure", "schema_or_scope_compile_failure"
                }:
                    repair_attempted = True
                    repair_context = (case["full_r0_context_private"] if arm == "A1"
                                      else case["selected_context_private"])
                    repair_prompt = repair_messages(
                        case, repair_context, initial["sql_private"], arm_initial_diagnostic,
                    )
                    repair = request_model(
                        result_root, output_dir, prepared_root, identity, stage_id, item["case_id"], arm,
                        repair_prompt, config["model"]["repair_max_tokens"], config, tokenizer,
                    )
                    request_wall += repair["request_wall_seconds"]
                    allowed = full_catalog_for_db if arm == "A1" else full_catalog
                    candidate_check = compile_readonly(db, repair["sql_private"], allowed)
                    denied_reads += candidate_check.get("denied_reads", 0)
                    repair_status = candidate_check["status"]
                    if candidate_check["status"] == "compiled":
                        candidate_exec = execute_if_compiled(db, repair["sql_private"], config)
                        if candidate_exec.get("status") == "ok":
                            arm_sql = repair["sql_private"]
                            arm_exec = candidate_exec
                            repair_accepted = True
                            repair_status = "accepted_readonly_executable"
                        else:
                            repair_status = "rejected_not_executable"
                    elif candidate_check["status"] == "unsafe_or_other_failure":
                        repair_status = "rejected_unsafe_or_other"
                    elif candidate_check["status"] == "out_of_context_identifier":
                        repair_status = "rejected_out_of_context"

                if arm_initial_check["status"] != "compiled" and not repair_accepted:
                    arm_exec = {"status": "not_executable", "error_type": arm_initial_diagnostic}
                predictions.append({
                    "case_id": item["case_id"],
                    "arm": arm,
                    "sql_private": arm_sql,
                    "repair_attempted": repair_attempted,
                    "repair_accepted": repair_accepted,
                    "repair_status_private": repair_status,
                    "denied_read_count_private": denied_reads,
                    "initial_diagnostic_private": arm_initial_diagnostic,
                    "context_denied_read_count_private": denied_reads,
                    "initial_context_denied_private": initial_context_denied,
                    "initial_result_private": initial_public,
                    "final_execution_private": arm_exec,
                })
                prediction_map[(item["case_id"], arm)] = predictions[-1]

        predictions_path = output_dir / "predictions_private.jsonl"
        write_jsonl_new(predictions_path, predictions)
        prediction_seal = {
            "row_count": len(predictions),
            "predictions_sha256": sha(predictions_path),
            "prepare_seal_sha256": sha(prepared_root / "prepare_seal_private.json"),
        }
        write_new(output_dir / "prediction_seal_private.json", prediction_seal)

        # Gold SQL and database paths are opened only after every generation is sealed.
        evaluation_inputs = read(prepared_root / "evaluation_private.json")
        check_database_hashes(evaluation_inputs)
        reference_cache = {}
        public_rows = []
        pair_counts = {"A2_vs_A0": Counter(), "A1_vs_A0": Counter(), "A2_vs_A1": Counter()}
        metric = {arm: Counter() for arm in ("A0", "A1", "A2")}
        failure_types = Counter()
        repair_by_arm = {arm: Counter() for arm in ("A1", "A2")}

        for item in selected_cases:
            if time.time() >= config["_deadline_epoch"]:
                raise RuntimeError("Registered total Smoke + Full wall-clock budget is exhausted")
            case_id = item["case_id"]
            target = evaluation_inputs[case_id]
            db = Path(target["database_path_private"])
            if case_id not in reference_cache:
                reference_cache[case_id] = execute_if_compiled(db, target["reference_sql_private"], config)
            reference = reference_cache[case_id]
            outcomes = {}
            for arm in ("A0", "A1", "A2"):
                row = prediction_map[(case_id, arm)]
                pred = row["final_execution_private"]
                if pred.get("status") == "ok" and "rows" in pred:
                    compared = sql_results_to_public(pred, reference)
                else:
                    compared = {"set_correct": False, "bag_correct": False, "comparison_status": "execution_unavailable"}
                outcomes[arm] = compared
                metric[arm]["cases"] += 1
                metric[arm]["set_correct"] += int(compared["set_correct"])
                metric[arm]["bag_correct"] += int(compared["bag_correct"])
                metric[arm]["prediction_executable"] += int(pred.get("status") == "ok")
                metric[arm]["reference_executable"] += int(reference.get("status") == "ok")
                metric[arm]["initial_parse_or_compile_failure"] += int(row["initial_diagnostic_private"] != "compiled")
                if pred.get("status") != "ok":
                    failure_types[f"{arm}:{pred.get('status', 'unknown')}"] += 1
                if arm in repair_by_arm:
                    repair_by_arm[arm]["repair_attempted"] += int(row["repair_attempted"])
                    repair_by_arm[arm]["repair_accepted"] += int(row["repair_accepted"])
                    repair_by_arm[arm]["out_of_context_proposals_rejected"] += int(row["repair_status_private"] == "rejected_out_of_context")
                    repair_by_arm[arm]["denied_read_events"] += int(row["denied_read_count_private"])
                    repair_by_arm[arm]["initial_context_denials"] += int(row["initial_context_denied_private"])
            for left, right, key in (("A2", "A0", "A2_vs_A0"), ("A1", "A0", "A1_vs_A0"), ("A2", "A1", "A2_vs_A1")):
                l_ok, r_ok = outcomes[left]["set_correct"], outcomes[right]["set_correct"]
                pair_counts[key]["both_correct"] += int(l_ok and r_ok)
                pair_counts[key]["left_only_correct"] += int(l_ok and not r_ok)
                pair_counts[key]["right_only_correct"] += int(r_ok and not l_ok)
                pair_counts[key]["both_wrong"] += int(not l_ok and not r_ok)
            public_rows.append({
                "case_id": case_id,
                "database_alias": read(prepared_root / item["file"])["database_alias"],
                "v00_complete_1024": read(prepared_root / item["file"])["v00_complete_1024"],
                "reference_status": reference.get("status"),
                "arms": {arm: {
                    "set_correct": outcomes[arm]["set_correct"],
                    "bag_correct": outcomes[arm]["bag_correct"],
                    "execution_status": prediction_map[(case_id, arm)]["final_execution_private"].get("status"),
                    "repair_attempted": prediction_map[(case_id, arm)]["repair_attempted"],
                    "repair_accepted": prediction_map[(case_id, arm)]["repair_accepted"],
                    "repair_status": prediction_map[(case_id, arm)]["repair_status_private"],
                } for arm in ("A0", "A1", "A2")},
            })

        aggregates = {}
        for arm, values in metric.items():
            n = values["cases"]
            aggregates[arm] = {
                "n": n,
                "set_correct": values["set_correct"],
                "set_execution_accuracy": values["set_correct"] / n if n else None,
                "bag_correct": values["bag_correct"],
                "bag_execution_accuracy": values["bag_correct"] / n if n else None,
                "prediction_executable": values["prediction_executable"],
                "reference_executable_cases": values["reference_executable"],
                "initial_parse_or_compile_failures": values["initial_parse_or_compile_failure"],
            }
        per_database = {}
        per_stratum = {}
        for row in public_rows:
            stratum = "complete" if row["v00_complete_1024"] else "incomplete"
            for key, bucket in ((row["database_alias"], per_database), (stratum, per_stratum)):
                current = bucket.setdefault(key, {arm: Counter() for arm in ("A0", "A1", "A2")})
                for arm in ("A0", "A1", "A2"):
                    current[arm]["n"] += 1
                    current[arm]["set_correct"] += int(row["arms"][arm]["set_correct"])
        accepted_out_of_context = 0
        if args.stage == "full" and aggregates["A0"]["initial_parse_or_compile_failures"] < 10:
            decision = "INSUFFICIENT_REPAIR_CASES"
        else:
            a0 = aggregates["A0"]["set_execution_accuracy"]
            a1 = aggregates["A1"]["set_execution_accuracy"]
            a2 = aggregates["A2"]["set_execution_accuracy"]
            candidate_pass = (a2 >= a0 + 0.05 and a2 >= a1 - 0.05
                              and accepted_out_of_context == 0)
            decision = "EXPLORATORY_CANDIDATE_PASS" if candidate_pass else "NO_GO_OR_INCONCLUSIVE"
        public_summary = {
            "experiment_id": EXPERIMENT,
            "stage": args.stage,
            "status": "completed",
            "smoke_gate": "PASS" if args.stage == "smoke" else None,
            "cases": len(selected_cases),
            "arms": aggregates,
            "per_database": {
                db: {
                    **{arm: {"n": values[arm]["n"], "set_correct": values[arm]["set_correct"],
                             "set_execution_accuracy": values[arm]["set_correct"] / values[arm]["n"]}
                       for arm in ("A0", "A1", "A2")},
                    "A2_minus_A0_percentage_points": 100 * (
                        values["A2"]["set_correct"] / values["A2"]["n"]
                        - values["A0"]["set_correct"] / values["A0"]["n"]
                    ),
                }
                for db, values in per_database.items()
            },
            "per_v00_completeness_stratum": {
                name: {
                    **{arm: {"n": values[arm]["n"], "set_correct": values[arm]["set_correct"],
                             "set_execution_accuracy": values[arm]["set_correct"] / values[arm]["n"]}
                       for arm in ("A0", "A1", "A2")},
                    "A2_minus_A0_percentage_points": 100 * (
                        values["A2"]["set_correct"] / values["A2"]["n"]
                        - values["A0"]["set_correct"] / values["A0"]["n"]
                    ),
                }
                for name, values in per_stratum.items()
            },
            "paired_set_outcomes": {key: dict(value) for key, value in pair_counts.items()},
            "repair_counts": {arm: dict(value) for arm, value in repair_by_arm.items()},
            "accepted_out_of_context_identifiers": accepted_out_of_context,
            "failure_categories": dict(failure_types),
            "decision": decision,
            "minimum_repair_signal_met": (aggregates["A0"]["initial_parse_or_compile_failures"] >= 10
                                           if args.stage == "full" else None),
            "reference_unavailable_cases": sum(row["reference_status"] != "ok" for row in public_rows),
            "budget": {
                "stage_model_requests": len([row for row in call_history(result_root) if row.get("run_id") == stage_id]),
                "stage_input_tokens": sum(row.get("usage", {}).get("prompt_tokens", 0) for row in call_history(result_root) if row.get("run_id") == stage_id),
                "stage_output_tokens": sum(row.get("usage", {}).get("completion_tokens", 0) for row in call_history(result_root) if row.get("run_id") == stage_id),
                "experiment_model_requests": len(call_history(result_root)),
                "experiment_input_tokens": sum(row.get("usage", {}).get("prompt_tokens", 0) for row in call_history(result_root)),
                "experiment_output_tokens": sum(row.get("usage", {}).get("completion_tokens", 0) for row in call_history(result_root)),
                "experiment_unknown_usage_requests": sum(
                    not all(type(row.get("usage", {}).get(key)) is int
                            for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
                    for row in call_history(result_root)
                ),
                "request_wall_seconds": request_wall,
                "external_api_cost_CNY": "0.00",
                "local_gpu_compute_seconds": None,
                "local_compute_cost": "unpriced",
            },
            "privacy": {
                "question_text_published": False,
                "gold_sql_published": False,
                "predicted_sql_published": False,
                "database_names_published": False,
                "query_result_rows_published": False,
            },
            "a2_authorization_gate": auth_gate,
        }
        # Smoke is an operational gate only; SQL correctness is not used to tune the pilot.
        if args.stage == "smoke":
            request_records = call_history(result_root)
            smoke_rows = [row for row in request_records if row.get("run_id") == stage_id]
            if len(smoke_rows) < 5 or any(not all(type(row.get("usage", {}).get(key)) is int
                                                 for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
                                         for row in smoke_rows):
                raise RuntimeError("Smoke did not preserve complete model usage")
            if len(public_rows) != 5 or len(predictions) != 15:
                raise RuntimeError("Smoke did not complete all five three-arm cases")
            if any(row["repair_status"] == "error" for case in public_rows for row in case["arms"].values()):
                raise RuntimeError("Smoke encountered a repair gate error")
        write_new(output_dir / "evaluation_aggregate_private.json", public_rows)
        write_new(output_dir / "aggregate_summary.json", public_summary)
        usage_snapshot = call_ledger_snapshot(Path(os.environ["P2D3_USAGE_DB"]).resolve(strict=True))
        write_new(output_dir / "usage_snapshot_private.json", usage_snapshot)
        check_database_hashes(evaluation_inputs)
        receipt.update(
            state="completed",
            aggregate_sha256=sha(output_dir / "aggregate_summary.json"),
            predictions_sha256=sha(predictions_path),
            physical_model_requests=len(call_history(result_root)),
            request_wall_seconds=request_wall,
            cpu_seconds=time.process_time() - start_cpu,
            wall_seconds=time.perf_counter() - start_wall,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        write_new(output_dir / "run_receipt.json", receipt)
    except Exception as exc:
        receipt.update(
            state="failed",
            error_type=type(exc).__name__,
            cpu_seconds=time.process_time() - start_cpu,
            wall_seconds=time.perf_counter() - start_wall,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        write_new(output_dir / "run_receipt.json", receipt)
        raise
    print(json.dumps({key: public_summary.get(key) for key in
                      ("stage", "status", "cases", "decision", "budget")}, ensure_ascii=False))


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke", "full"), required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-seal-sha256", required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    args = parser.parse_args()
    config = read(REPORT / "experiment_config.json")
    if config["status"] not in {"preregistered_not_run", "prepared_not_run", "smoke_pass_full_pending"} or config["experiment_id"] != EXPERIMENT:
        raise RuntimeError("P2d.3 is not open for execution")
    if args.result_root.resolve() != Path(os.environ["P2D3_RESULT_ROOT"]).resolve():
        raise RuntimeError("Output root differs from the registered local alias")
    ledger_dir = Path(os.environ["P2D3_LEDGER_DIR"]).resolve(strict=True)
    if not (ledger_dir / "api_usage_ledger.py").is_file():
        raise RuntimeError("Shared API usage ledger is unavailable")
    run_stage(args, config)


if __name__ == "__main__":
    main()
