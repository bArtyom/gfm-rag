#!/usr/bin/env python3
"""Run a blind Gemma FK-mapping review pass on CPU with local Transformers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from run_p0_fk_mapping_model_review_proxy import (  # noqa: E402
    build_messages,
    parse_json_answer,
    parse_packet,
    validate_answer,
    validate_packet_pair,
)

EXPECTED_PACKET_A = "0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2"
EXPECTED_PACKET_B = "a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb"
EXPECTED_MODEL_SHA256 = "cfbd3d2f1cd71bd471c37fe2bf8546d5028d41e5736f64e1ca6c6b8893125503"
EXPECTED_MODEL_BYTES = 15992595884
MODEL_REVISION = "c53e9d33178b12afbad4a48334d21e19b8c29761"
MAX_RSS_BYTES = 64 * 1024**3


def record_local_request(*, call_id: str, run_id: str, model_name: str,
                         prompt_tokens: int | None, completion_tokens: int | None,
                         succeeded: bool) -> None:
    shared_root = os.environ.get("GFM_SHARED_CODE_ROOT")
    if not shared_root or not Path(shared_root).is_dir():
        raise RuntimeError("GFM_SHARED_CODE_ROOT must point to the local shared-code directory")
    if str(shared_root) not in sys.path:
        sys.path.insert(0, str(shared_root))
    from api_usage_ledger import record_request

    usage = None
    if prompt_tokens is not None and completion_tokens is not None:
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    record_request(
        call_id=call_id,
        provider="local_transformers_cpu",
        project="gfm-rag",
        run_id=run_id,
        model=model_name,
        http_status=200 if succeeded else None,
        usage=usage,
    )


def permuted_item(item: dict[str, Any], seed: int) -> dict[str, Any]:
    copied = dict(item)
    mappings = list(item["mappings"])
    random.Random(f"{seed}:{item['pair_id']}").shuffle(mappings)
    copied["mappings"] = mappings
    return copied


def peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-a", type=Path, required=True)
    parser.add_argument("--packet-b", type=Path, required=True)
    parser.add_argument("--mode", choices=["smoke", "full"], required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-name", default="google/gemma-4-E4B-it")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if source_commit != args.expected_commit:
        raise ValueError("source commit differs from the preregistered commit")

    items_a, hash_a = parse_packet(args.packet_a)
    items_b, hash_b = parse_packet(args.packet_b)
    if hash_a != EXPECTED_PACKET_A or hash_b != EXPECTED_PACKET_B:
        raise ValueError("frozen A/B packet hash mismatch")
    pair_index = validate_packet_pair(items_a, items_b)
    if len(pair_index) != 60 or sum(len(row["mappings"]) for row in items_a) != 135:
        raise ValueError("frozen review-packet size mismatch")

    model_dir = args.model.resolve(strict=True)
    model_file = model_dir / "model.safetensors"
    if not model_file.is_file() or model_file.stat().st_size != EXPECTED_MODEL_BYTES:
        raise ValueError("local Gemma checkpoint is missing or differs in size from preflight")
    if os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>") != "":
        raise ValueError("CPU recovery requires CUDA_VISIBLE_DEVICES to be empty")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_dir.chmod(0o700)
    output_path = output_dir / "reviewer_C.jsonl"
    summary_path = output_dir / "reviewer_C_summary.json"

    ordered_items = items_a
    if args.mode == "smoke":
        smoke_pairs = {item["pair_id"] for item in items_a[:5]}
        ordered_items = [item for item in items_a if item["pair_id"] in smoke_pairs]
        if len(ordered_items) != 5:
            raise ValueError("Smoke packet must contain exactly five frozen units")

    torch.set_num_threads(min(64, os.cpu_count() or 1))
    torch.set_num_interop_threads(min(8, os.cpu_count() or 1))
    run_started = time.perf_counter()
    tokenizer_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir), local_files_only=True, trust_remote_code=False
    )
    tokenizer_load_seconds = time.perf_counter() - tokenizer_started
    model_started = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir),
        dtype=torch.bfloat16,
        local_files_only=True,
        trust_remote_code=False,
        low_cpu_mem_usage=False,
    )
    model.to(torch.device("cpu"))
    model.eval()
    model_load_seconds = time.perf_counter() - model_started
    if peak_rss_bytes() > MAX_RSS_BYTES:
        raise MemoryError("process RSS exceeded the preregistered 64 GiB budget after model load")

    valid_count = 0
    invalid_reasons: dict[str, int] = {}
    input_tokens_total = 0
    output_tokens_total = 0
    generation_seconds = 0.0
    with output_path.open("x", encoding="utf-8") as sink:
        os.chmod(output_path, 0o600)
        for ordinal, source_item in enumerate(ordered_items, start=1):
            item = permuted_item(source_item, seed=20261106)
            messages = build_messages(item)
            encoded = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
                enable_thinking=False,
            )
            encoded = {key: value.to("cpu") for key, value in encoded.items()}
            prompt_count = int(encoded["input_ids"].shape[-1])
            call_id = f"{args.run_id}:C:{item['case_id']}:{item['pair_id']}:attempt01"
            started = time.perf_counter()
            try:
                with torch.inference_mode():
                    generated = model.generate(
                        **encoded,
                        max_new_tokens=384,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
            except Exception as error:
                record_local_request(
                    call_id=call_id,
                    run_id=args.run_id,
                    model_name=f"{args.model_name}@{MODEL_REVISION}",
                    prompt_tokens=None,
                    completion_tokens=None,
                    succeeded=False,
                )
                row = {
                    "case_id": item["case_id"],
                    "pair_id": item["pair_id"],
                    "ordinal": ordinal,
                    "candidate_order_seed": 20261106,
                    "valid": False,
                    "invalid_reason": "generation_error",
                    "error_type": type(error).__name__,
                    "input_tokens": None,
                    "output_tokens": None,
                }
                sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                sink.flush()
                os.fsync(sink.fileno())
                raise

            duration = time.perf_counter() - started
            generation_seconds += duration
            new_tokens = generated[0, prompt_count:]
            completion_count = int(new_tokens.shape[-1])
            output_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            record_local_request(
                call_id=call_id,
                run_id=args.run_id,
                model_name=f"{args.model_name}@{MODEL_REVISION}",
                prompt_tokens=prompt_count,
                completion_tokens=completion_count,
                succeeded=True,
            )
            input_tokens_total += prompt_count
            output_tokens_total += completion_count
            answer = parse_json_answer(output_text)
            valid, invalid_reason = validate_answer(answer, item)
            if valid:
                valid_count += 1
            else:
                key = invalid_reason or "unknown"
                invalid_reasons[key] = invalid_reasons.get(key, 0) + 1
            row = {
                "case_id": item["case_id"],
                "pair_id": item["pair_id"],
                "ordinal": ordinal,
                "candidate_order_seed": 20261106,
                "valid": valid,
                "invalid_reason": invalid_reason,
                "answer": answer if valid else None,
                "raw_output": output_text,
                "input_tokens": prompt_count,
                "output_tokens": completion_count,
                "generation_seconds": round(duration, 6),
            }
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()
            os.fsync(sink.fileno())
            if peak_rss_bytes() > MAX_RSS_BYTES:
                raise MemoryError("process RSS exceeded the preregistered 64 GiB budget")

    summary = {
        "experiment_id": "p0_fk_mapping_model_review_third_proxy_cpu_20261106_01",
        "run_id": args.run_id,
        "mode": args.mode,
        "reviewer": "C",
        "model": args.model_name,
        "model_revision": MODEL_REVISION,
        "model_artifact_sha256": EXPECTED_MODEL_SHA256,
        "source_commit": source_commit,
        "packet_a_sha256": hash_a,
        "packet_b_sha256": hash_b,
        "review_units": len(ordered_items),
        "candidate_mappings_in_full_packet": 135,
        "valid_outputs": valid_count,
        "invalid_output_reasons": invalid_reasons,
        "input_tokens": input_tokens_total,
        "output_tokens": output_tokens_total,
        "total_tokens": input_tokens_total + output_tokens_total,
        "tokenizer_load_seconds": round(tokenizer_load_seconds, 6),
        "model_load_seconds": round(model_load_seconds, 6),
        "generation_seconds": round(generation_seconds, 6),
        "process_wall_seconds": round(time.perf_counter() - run_started, 6),
        "peak_rss_bytes": peak_rss_bytes(),
        "cpu_threads": torch.get_num_threads(),
        "gpu_used": False,
        "raw_review_file": output_path.name,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(summary_path, 0o600)
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"packet_a_sha256", "packet_b_sha256"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
