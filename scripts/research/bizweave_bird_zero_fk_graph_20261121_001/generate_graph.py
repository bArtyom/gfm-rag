#!/usr/bin/env python3
"""Generate a source-cited business-semantic graph with one local Qwen call."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json"
LEDGER_PATH = Path("/mnt/liansp3/sources/code/api_usage_ledger.py")

SYSTEM_PROMPT = """You build evidence-grounded business-semantic graphs for Text-to-SQL schema retrieval.
Use only the supplied schema and documentation evidence. The database declares no foreign keys, so do not call an inferred relation a declared FK. Separate business entities/events/states/time bases/metric grains from physical tables and columns. Every node and edge must cite one or more supplied evidence_id values; a physical join candidate must cite evidence for both endpoint columns. Do not invent identifiers, column meanings, join keys, time definitions, metrics, states, or values. A shared identifier can support only a candidate join, not a guaranteed business relationship. Mark unsupported or competing event/state/time/grain interpretations as unresolved instead of choosing. If documentation is silent, do not claim its silence is evidence; use an empty evidence_ids list for the unresolved record. Prefer fewer supported nodes and edges over speculative completeness. Return one JSON object only."""


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def load_ledger():
    spec = importlib.util.spec_from_file_location("api_usage_ledger", LEDGER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8769/v1")
    parser.add_argument("--count-tokens-only", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    model_path = Path(config["model"]["path"])
    expected_model_files = {
        "config.json": config["model"]["model_config_sha256"],
        "tokenizer_config.json": config["model"]["tokenizer_config_sha256"],
        "model.safetensors.index.json": config["model"]["weights_index_sha256"],
    }
    actual_model_files = {name: sha256_file(model_path / name) for name in expected_model_files}
    mismatched_model_files = [
        name for name, expected in expected_model_files.items() if actual_model_files[name] != expected
    ]
    if mismatched_model_files:
        raise ValueError(f"Frozen model-file hash mismatch: {mismatched_model_files}")
    output_dir = args.output_dir or Path(config["paths"]["run_root"]) / "generation_001"
    input_path = args.input or Path(config["paths"]["run_root"]) / "input_001/model_input.json"
    if not input_path.is_file():
        raise FileNotFoundError(f"Prepared model input is missing: {input_path}")
    if (output_dir / "graph.json").exists() or (output_dir / "generation_meta.json").exists():
        raise FileExistsError(f"Refusing to overwrite generation output: {output_dir}")

    model_input_text = input_path.read_text(encoding="utf-8")
    prompt = (
        "Create a compact business-semantic graph for schema retrieval. Explicitly represent event, state, time basis, "
        "metric, and grain semantics when documentation supports them; use unresolved entries when the source does not "
        "support a unique interpretation. Node kind should be one of entity, event, state, time_basis, metric, grain, "
        "fact, bridge, dimension, attribute, or lookup when applicable.\n"
        "Output JSON with this shape:\n"
        "{\"database\": string, \"summary\": string, \"nodes\": ["
        "{\"id\": string, \"kind\": string, \"label\": string, \"description\": string, "
        "\"aliases\": [string], \"physical_bindings\": [{\"table\": string, \"columns\": [string], "
        "\"evidence_ids\": [string]}], \"evidence_ids\": [string]}], \"edges\": ["
        "{\"source\": string, \"target\": string, \"kind\": string, \"label\": string, "
        "\"physical_join_candidates\": [{\"left_table\": string, \"left_column\": string, "
        "\"right_table\": string, \"right_column\": string, \"status\": string, "
        "\"evidence_ids\": [string]}], \"evidence_ids\": [string]}], "
        "\"unresolved\": [{\"claim\": string, \"reason\": string, \"candidate_refs\": [string], "
        "\"evidence_ids\": [string]}]}.\n"
        "For every physical join candidate, use status candidate or unknown, cite both pieces of schema evidence, "
        "and preserve direction. Include core entities, fact/event-like tables, bridge/lookup tables, measures, "
        "and time dimensions only when supported. Keep aliases short and evidence-derived.\n\n"
        "Evidence input:\n" + model_input_text
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["path"], local_files_only=True, trust_remote_code=True
    )
    token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
    prompt_token_count = len(token_ids)
    max_model_len = config["model"]["max_model_len"]
    max_new_tokens = config["model"]["max_new_tokens"]
    if prompt_token_count + max_new_tokens > max_model_len:
        raise ValueError(
            f"Prompt plus reserved generation exceeds context: {prompt_token_count}+{max_new_tokens}>{max_model_len}"
        )
    if args.count_tokens_only:
        print(json.dumps({
            "run_id": config["run_id"],
            "model": config["model"]["name"],
            "model_file_hashes_verified": actual_model_files,
            "model_input_sha256": sha256_text(model_input_text),
            "prompt_sha256": sha256_text(SYSTEM_PROMPT + prompt),
            "prompt_tokens_local_tokenizer": prompt_token_count,
            "max_new_tokens": max_new_tokens,
            "context_limit": max_model_len,
            "model_api_calls": 0,
        }, ensure_ascii=False, indent=2))
        return

    payload = {
        "model": config["model"]["served_model_name"],
        "messages": messages,
        "temperature": config["model"]["temperature"],
        "seed": config["model"]["seed"],
        "max_tokens": max_new_tokens,
        "response_format": {"type": "json_object"},
    }
    request_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions",
        data=request_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    call_id = config["run_id"] + "_generate_attempt_001"
    start_utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    status = None
    usage = None
    body = None
    error = None
    ledger = load_ledger()
    request_attempted = False
    try:
        request_attempted = True
        with urllib.request.urlopen(request, timeout=1800) as response:
            status = response.status
            body = response.read()
        response_json = json.loads(body.decode("utf-8"))
        usage = response_json.get("usage")
        ledger.record_request(
            call_id=call_id,
            provider="local_vllm",
            project="gfm-rag-bizweave",
            run_id=config["run_id"],
            model=config["model"]["name"],
            http_status=status,
            usage=usage,
            occurred_at=start_utc,
        )
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = "HTTPError"
        if request_attempted:
            ledger.record_request(
                call_id=call_id,
                provider="local_vllm",
                project="gfm-rag-bizweave",
                run_id=config["run_id"],
                model=config["model"]["name"],
                http_status=status,
                usage=None,
                occurred_at=start_utc,
            )
    except Exception as exc:
        error = type(exc).__name__
        if request_attempted:
            ledger.record_request(
                call_id=call_id,
                provider="local_vllm",
                project="gfm-rag-bizweave",
                run_id=config["run_id"],
                model=config["model"]["name"],
                http_status=status,
                usage=None,
                occurred_at=start_utc,
            )
    elapsed_seconds = time.monotonic() - start
    output_dir.mkdir(parents=True, exist_ok=True)
    if error:
        metadata = {
            "run_id": config["run_id"],
            "call_id": call_id,
            "model": config["model"]["name"],
            "model_input_sha256": sha256_text(model_input_text),
            "prompt_sha256": sha256_text(SYSTEM_PROMPT + prompt),
            "prompt_tokens_local_tokenizer": prompt_token_count,
            "http_status": status,
            "error_class": error,
            "usage_reported": False,
            "elapsed_seconds": elapsed_seconds,
            "occurred_at_utc": start_utc,
        }
        write_once(output_dir / "generation_meta.json", json.dumps(metadata, indent=2) + "\n")
        raise RuntimeError(f"Local generation failed ({error}); attempt recorded in usage ledger")

    response_text = response_json["choices"][0]["message"]["content"]
    write_once(output_dir / "raw_model_output.json.txt", response_text + "\n")
    json_valid = True
    parse_error = None
    try:
        graph = json.loads(response_text)
    except json.JSONDecodeError as exc:
        graph = None
        json_valid = False
        parse_error = type(exc).__name__
    if graph is not None:
        write_once(output_dir / "graph.json", json.dumps(graph, ensure_ascii=False, indent=2) + "\n")
    metadata = {
        "run_id": config["run_id"],
        "call_id": call_id,
        "model": config["model"]["name"],
        "model_path": config["model"]["path"],
        "model_config_sha256": actual_model_files["config.json"],
        "tokenizer_config_sha256": actual_model_files["tokenizer_config.json"],
        "weights_index_sha256": actual_model_files["model.safetensors.index.json"],
        "model_input_sha256": sha256_text(model_input_text),
        "prompt_sha256": sha256_text(SYSTEM_PROMPT + prompt),
        "prompt_tokens_local_tokenizer": prompt_token_count,
        "http_status": status,
        "usage": usage,
        "json_valid": json_valid,
        "parse_error": parse_error,
        "elapsed_seconds": elapsed_seconds,
        "occurred_at_utc": start_utc,
        "external_api_cost": "CNY 0; local inference",
    }
    write_once(output_dir / "generation_meta.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "run_id": config["run_id"],
        "model": config["model"]["name"],
        "http_status": status,
        "prompt_tokens_local_tokenizer": prompt_token_count,
        "usage": usage,
        "json_valid": json_valid,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))
    if not json_valid:
        raise ValueError("Model returned a non-JSON response; no retry is permitted by the frozen budget")


if __name__ == "__main__":
    main()
