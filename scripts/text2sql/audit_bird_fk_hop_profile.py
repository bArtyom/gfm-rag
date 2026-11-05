#!/usr/bin/env python3
"""Profile declared-FK graph hop depth for BIRD dev SQL, without scoring methods."""

from __future__ import annotations

import argparse
import collections
import hashlib
import heapq
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MAX_EXACT_TERMINALS = 12
EXPECTED_QUESTIONS = 1534
EXPECTED_SCHEMAS = 11
MAX_THREADS = 4

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = str(MAX_THREADS)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "MISSING"


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        return "unavailable"
    return result.stdout.strip()


def git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def normalize_name(value: Any) -> str:
    name = str(value or "").strip()
    if len(name) >= 2 and name[0] == "[" and name[-1] == "]":
        name = name[1:-1]
    elif len(name) >= 2 and name[0] == name[-1] and name[0] in ('"', "'", "`"):
        name = name[1:-1]
    return name.casefold()


def build_schema_graph(schema: dict[str, Any]) -> dict[str, Any]:
    table_names = list(schema.get("table_names_original", []))
    column_names = list(schema.get("column_names_original", []))
    table_index = {normalize_name(name): idx for idx, name in enumerate(table_names)}
    graph = [set() for _ in table_names]
    raw_fk_count = 0
    invalid_fk_count = 0
    for pair in schema.get("foreign_keys", []):
        raw_fk_count += 1
        try:
            left_col, right_col = int(pair[0]), int(pair[1])
            left_table = int(column_names[left_col][0])
            right_table = int(column_names[right_col][0])
        except (IndexError, TypeError, ValueError):
            invalid_fk_count += 1
            continue
        if not (0 <= left_table < len(table_names) and 0 <= right_table < len(table_names)):
            invalid_fk_count += 1
            continue
        if left_table != right_table:
            graph[left_table].add(right_table)
            graph[right_table].add(left_table)
    return {
        "table_names": table_names,
        "table_index": table_index,
        "graph": graph,
        "raw_fk_count": raw_fk_count,
        "table_edges": sum(len(neighbors) for neighbors in graph) // 2,
        "invalid_fk_count": invalid_fk_count,
    }


def extract_base_tables(sql: str, sqlglot: Any, exp: Any) -> set[str]:
    parsed = sqlglot.parse_one(sql, read="sqlite")
    cte_names = {normalize_name(cte.alias_or_name) for cte in parsed.find_all(exp.CTE)}
    result: set[str] = set()
    for table in parsed.find_all(exp.Table):
        name = normalize_name(table.name)
        if name and name not in cte_names:
            result.add(name)
    return result


def reachable(terminals: list[int], graph: list[set[int]]) -> bool:
    if len(terminals) < 2:
        return True
    seen = {terminals[0]}
    stack = [terminals[0]]
    while stack:
        current = stack.pop()
        for neighbor in graph[current] - seen:
            seen.add(neighbor)
            stack.append(neighbor)
    return all(terminal in seen for terminal in terminals)


def steiner_edge_count(terminals: list[int], graph: list[set[int]]) -> int | None:
    """Return exact unweighted Steiner edge count via Dreyfus-Wagner DP."""
    terminals = sorted(set(terminals))
    if not terminals:
        return 0
    if len(terminals) == 1:
        return 0
    if len(terminals) > MAX_EXACT_TERMINALS:
        return None

    node_count = len(graph)
    state_count = 1 << len(terminals)
    infinity = node_count * state_count + 1
    dp = [[infinity] * node_count for _ in range(state_count)]
    for index, terminal in enumerate(terminals):
        dp[1 << index][terminal] = 0

    for mask in range(1, state_count):
        if mask & (mask - 1):
            sub = (mask - 1) & mask
            while sub:
                other = mask ^ sub
                if other and sub < other:
                    left = dp[sub]
                    right = dp[other]
                    current = dp[mask]
                    for node in range(node_count):
                        candidate = left[node] + right[node]
                        if candidate < current[node]:
                            current[node] = candidate
                sub = (sub - 1) & mask

        current = dp[mask]
        queue = [(distance, node) for node, distance in enumerate(current) if distance < infinity]
        heapq.heapify(queue)
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != current[node]:
                continue
            next_distance = distance + 1
            for neighbor in graph[node]:
                if next_distance < current[neighbor]:
                    current[neighbor] = next_distance
                    heapq.heappush(queue, (next_distance, neighbor))

    result = min(dp[-1], default=infinity)
    return result if result < infinity else None


def aggregate_profile(
    questions: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    limit: int | None,
) -> dict[str, Any]:
    import sqlglot
    from sqlglot import exp

    schema_by_db = {str(schema["db_id"]): build_schema_graph(schema) for schema in schemas}
    selected = questions[:limit] if limit is not None else questions
    status_counts: collections.Counter[str] = collections.Counter()
    hop_histogram: collections.Counter[int] = collections.Counter()
    by_db_h3: collections.Counter[str] = collections.Counter()
    by_db_h4: collections.Counter[str] = collections.Counter()
    parsed_tables_total = 0
    mapped_questions = 0
    raw_fk_total = sum(item["raw_fk_count"] for item in schema_by_db.values())
    table_edge_total = sum(item["table_edges"] for item in schema_by_db.values())
    invalid_fk_total = sum(item["invalid_fk_count"] for item in schema_by_db.values())
    dbs_with_schema = set(schema_by_db)

    for question in selected:
        db_id = str(question.get("db_id", ""))
        schema = schema_by_db.get(db_id)
        sql = question.get("SQL") or question.get("sql")
        if schema is None:
            status_counts["unknown_database"] += 1
            continue
        if not isinstance(sql, str) or not sql.strip():
            status_counts["missing_sql"] += 1
            continue
        try:
            table_names = extract_base_tables(sql, sqlglot, exp)
        except Exception:
            status_counts["parse_failure"] += 1
            continue
        parsed_tables_total += len(table_names)
        if not table_names:
            status_counts["no_base_table_reference"] += 1
            continue
        unmapped = table_names - set(schema["table_index"])
        if unmapped:
            status_counts["unknown_table_reference"] += 1
            continue
        mapped_questions += 1
        terminals = sorted({schema["table_index"][name] for name in table_names})
        graph = schema["graph"]
        if len(terminals) == 1:
            status_counts["connected"] += 1
            hop_histogram[0] += 1
            continue
        if not reachable(terminals, graph):
            status_counts["disconnected_fk_graph"] += 1
            continue
        hop_count = steiner_edge_count(terminals, graph)
        if hop_count is None:
            status_counts["terminal_limit_exceeded"] += 1
            continue
        status_counts["connected"] += 1
        hop_histogram[hop_count] += 1
        if hop_count >= 3:
            by_db_h3[db_id] += 1
        if hop_count >= 4:
            by_db_h4[db_id] += 1

    histogram = {str(depth): int(hop_histogram[depth]) for depth in sorted(hop_histogram)}
    classified = sum(status_counts.values())
    return {
        "denominators": {
            "questions_processed": len(selected),
            "schemas_loaded": len(schemas),
            "distinct_schema_databases": len(dbs_with_schema),
            "statuses_sum_to_questions": classified == len(selected),
            "questions_with_all_table_refs_mapped": mapped_questions,
            "base_table_references_parsed": parsed_tables_total,
        },
        "fk_table_graph": {
            "declared_fk_column_pairs": raw_fk_total,
            "unique_undirected_table_edges": table_edge_total,
            "invalid_fk_endpoints": invalid_fk_total,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "hop_histogram_connected_only": histogram,
        "connected_questions_hop_ge_3": int(sum(by_db_h3.values())),
        "databases_with_connected_questions_hop_ge_3": len(by_db_h3),
        "max_hop_ge_3_questions_in_one_database": int(max(by_db_h3.values(), default=0)),
        "connected_questions_hop_ge_4": int(sum(by_db_h4.values())),
        "databases_with_connected_questions_hop_ge_4": len(by_db_h4),
        "max_hop_ge_4_questions_in_one_database": int(max(by_db_h4.values(), default=0)),
        "interpretation_scope": (
            "Unweighted exact minimum Steiner-tree edge count over the declared, undirected, table-level FK graph. "
            "This is structural coverage only; it does not establish that an FK path is semantically correct, "
            "does not count Role accuracy, and does not evaluate a JOIN method."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dev-json", type=Path, required=True)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Refusing to reuse an existing result directory")
    if not args.config.is_file() or not args.dev_json.is_file() or not args.tables_json.is_file():
        raise FileNotFoundError("Registered BIRD input file is missing")
    import yaml

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "preregistered_exploratory_structural_audit":
        raise RuntimeError("Experiment config status is not preregistered")
    if int(config["dataset"]["questions"]) != EXPECTED_QUESTIONS or int(config["dataset"]["schemas"]) != EXPECTED_SCHEMAS:
        raise RuntimeError("Config denominator differs from the frozen runner")
    if int(config["analysis"]["max_exact_terminals"]) != MAX_EXACT_TERMINALS:
        raise RuntimeError("Config Steiner limit differs from the frozen runner")
    if int(config["resources"]["max_threads"]) != MAX_THREADS or config["resources"]["compute"] != "CPU only":
        raise RuntimeError("Config resource limit differs from the frozen runner")
    dev_sha = sha256_file(args.dev_json)
    tables_sha = sha256_file(args.tables_json)
    if dev_sha != config["dataset"]["dev_json_sha256"] or tables_sha != config["dataset"]["dev_tables_sha256"]:
        raise RuntimeError("Input SHA-256 differs from preregistration")
    args.output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(args.output_dir, 0o700)
    started = time.time()
    start = {
        "run_id": args.run_id,
        "mode": args.mode,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_commit": git_commit(),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(args.config),
        "environment": {
            "python": platform.python_version(),
            "sqlglot": package_version("sqlglot"),
            "platform": platform.platform(),
            "max_threads": MAX_THREADS,
        },
        "inputs": {
            "dev_json_sha256": dev_sha,
            "dev_tables_json_sha256": tables_sha,
        },
        "resource_snapshot": {
            "gpu_snapshot_cpu_only": command_output(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]),
            "free_h": command_output(["free", "-h"]),
            "cpu_threads": os.cpu_count(),
            "disk": command_output(["df", "-h", str(args.output_dir)]),
        },
        "command_argv": sys.argv,
    }
    (args.output_dir / "run_start.json").write_text(json.dumps(start, indent=2) + "\n", encoding="utf-8")

    questions = json.loads(args.dev_json.read_text(encoding="utf-8"))
    schemas = json.loads(args.tables_json.read_text(encoding="utf-8"))
    if args.mode == "full" and (len(questions) != EXPECTED_QUESTIONS or len(schemas) != EXPECTED_SCHEMAS):
        raise RuntimeError("BIRD denominator does not match the preregistered full run")
    profile = aggregate_profile(questions, schemas, limit=5 if args.mode == "smoke" else None)
    processed = profile["denominators"]["questions_processed"]
    profile["run_id"] = args.run_id
    profile["mode"] = args.mode
    profile["elapsed_seconds"] = round(time.time() - started, 6)
    profile["inputs"] = start["inputs"]
    profile["source"] = {
        "project_commit": start["project_commit"],
        "script_sha256": start["script_sha256"],
        "config_sha256": start["config_sha256"],
        "sqlglot_version": start["environment"]["sqlglot"],
        "python_version": start["environment"]["python"],
    }
    if not profile["denominators"]["statuses_sum_to_questions"]:
        raise RuntimeError("Question statuses failed to exhaustively account for the denominator")
    if args.mode == "smoke" and processed != 5:
        raise RuntimeError("Smoke did not process exactly five questions")
    if args.mode == "smoke":
        smoke_errors = sum(profile["status_counts"].get(key, 0) for key in (
            "unknown_database", "missing_sql", "parse_failure", "no_base_table_reference", "unknown_table_reference"
        ))
        if smoke_errors:
            raise RuntimeError("Smoke input/schema parsing gate failed")
        profile["status"] = "SMOKE_PASS"
    if args.mode == "full":
        parseable = sum(profile["status_counts"].get(key, 0) for key in ("connected", "disconnected_fk_graph", "unknown_table_reference", "terminal_limit_exceeded"))
        parseable += profile["status_counts"].get("no_base_table_reference", 0)
        parseable_rate = parseable / EXPECTED_QUESTIONS
        h3 = profile["connected_questions_hop_ge_3"]
        db_count = profile["databases_with_connected_questions_hop_ge_3"]
        profile["full_audit_gate"] = {
            "table_extraction_parse_rate": round(parseable_rate, 6),
            "parse_rate_at_least_95_percent": parseable_rate >= 0.95,
            "high_hop_screen": "BIRD_H_GE_3_SCREEN_PASS" if h3 >= 30 and db_count >= 3 else "BIRD_H_GE_3_SCREEN_NO_GO",
            "high_hop_screen_threshold": {"connected_questions_hop_ge_3": 30, "databases_with_at_least_one": 3},
            "screen_is_not_a_power_calculation": True,
        }
        profile["status"] = "FULL_COMPLETED" if parseable_rate >= 0.95 else "INCOMPLETE"
    (args.output_dir / "aggregate_summary.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output_dir / "run_end.json").write_text(json.dumps({
        "run_id": args.run_id,
        "status": profile["status"],
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aggregate_summary_sha256": sha256_file(args.output_dir / "aggregate_summary.json"),
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "run_id": args.run_id,
        "status": profile["status"],
        "questions_processed": processed,
        "status_counts": profile["status_counts"],
        "hop_histogram_connected_only": profile["hop_histogram_connected_only"],
        "high_hop_screen": profile.get("full_audit_gate", {}).get("high_hop_screen", "not_applicable"),
        "result_file": str(args.output_dir / "aggregate_summary.json"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
