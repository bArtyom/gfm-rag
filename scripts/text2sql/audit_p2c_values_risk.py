#!/usr/bin/env python3
"""Offline lexical Values-exposure audit; never evaluates or generates SQL."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import unicodedata

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.text2sql import run_p2c_dual_view_factorial as core
from scripts.text2sql import run_p2c_r_recovery as recovery
import sqlglot
from sqlglot import exp

EXPERIMENT_ID = "p2c_values_risk_20261019_01"
REPORT = core.REPO_ROOT / "docs/research/text2sql/reports" / EXPERIMENT_ID
PROTOCOL = core.REPO_ROOT / "docs/research/text2sql/plans/p2c_values_risk_audit_20261019.md"


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


@lru_cache(maxsize=10000)
def literal_pattern(literal):
    value = normalize(literal)
    numeric = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?", value)
    left = r"(?<![\w.+-])" if numeric else r"(?<![\w.])"
    return re.compile(left + re.escape(value) + r"(?![\w.])")


def literal_present(literal, normalized_text):
    return bool(literal_pattern(literal).search(normalized_text))


def extract_predicate_literals(sql):
    tree = sqlglot.parse_one(sql, read="sqlite")
    if tree is None:
        raise ValueError("Empty SQL AST")
    unique, diagnostics = {}, Counter()
    for literal in tree.find_all(exp.Literal):
        if literal.find_ancestor(exp.Limit, exp.Offset) is not None:
            diagnostics["pagination_literals_excluded"] += 1
            continue
        predicate = literal.find_ancestor(exp.Predicate)
        if predicate is None or predicate.find(exp.Column) is None:
            diagnostics["noncolumn_predicate_literals_excluded"] += 1
            continue
        parent = literal.parent
        negations = 0
        while parent is not predicate and isinstance(parent, (exp.Neg, exp.Paren, exp.Tuple)):
            negations += int(isinstance(parent, exp.Neg))
            parent = parent.parent
        if parent is not predicate:
            diagnostics["computed_or_function_literals_excluded"] += 1
            continue
        value = str(literal.this)
        if negations % 2:
            value = "-" + value
        if literal.is_string and isinstance(predicate, (exp.Like, exp.ILike, exp.RegexpLike)) and any(c in value for c in "%_"):
            diagnostics["pattern_literals_excluded"] += 1
            continue
        value = normalize(value)
        if not value:
            diagnostics["empty_literals_excluded"] += 1
            continue
        kind = "string" if literal.is_string else "number"
        unique[(kind, value)] = {"kind": kind, "value": value}
    diagnostics["unique_predicate_literals"] = len(unique)
    return list(unique.values()), dict(diagnostics)


def find_exposures(literals, user_input, old_selected, new_selected, r0, r1, gold_columns):
    old_short = [normalize(r1[node]) for node in old_selected]
    new_short = [normalize(r1[node]) for node in new_selected]
    removed = {}
    for node in old_selected:
        if r0[node] != r1[node]:
            marker = r1[node] + "; values: "
            if not r0[node].startswith(marker):
                raise RuntimeError("Values removal is not the registered trailing field")
            removed[node] = normalize(r0[node][len(marker):])
    flags = []
    for literal in literals:
        value = literal["value"]
        matching = [node for node, text in removed.items() if literal_present(value, text)]
        if not matching or any(literal_present(value, text) for text in old_short + new_short):
            continue
        flags.append({"literal_sha256": hashlib.sha256((literal["kind"] + ":" + value).encode()).hexdigest(),
                      "literal_kind": literal["kind"], "input_mentions_literal": literal_present(value, normalize(user_input)),
                      "matching_node_retained": any(node in new_selected for node in matching),
                      "matching_gold_column": any(node in gold_columns for node in matching),
                      "matching_node_ids": matching})
    return flags


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    for name in ("output-dir", "p2c-run-dir", "p1-6-run-dir", "legacy-root", "dataset-root", "model-path", "previous-run-dir", "p1-5-run-dir", "p2b-run-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--smoke-dir", type=Path)
    return parser.parse_args()


def run():
    args = parse_args()
    config_path = REPORT / "experiment_config.json"
    config = json.loads(config_path.read_text())
    if core.package_version("sqlglot") != config["sqlglot_version"]:
        raise RuntimeError("Registered SQL parser version differs")
    if config["experiment_id"] != EXPERIMENT_ID or config["status"] != "preregistered_not_run" or args.run_id != config["run_ids"][args.mode]:
        raise RuntimeError("Risk audit is outside its frozen registration")
    if args.output_dir.resolve() != Path(config["private_output_dirs"][args.mode]).resolve():
        raise RuntimeError("Risk output directory differs from registration")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    source_files = (*recovery.EXECUTION_SOURCES, Path(__file__).resolve())
    receipt = {"experiment_id": EXPERIMENT_ID, "run_id": args.run_id, "state": "started", "mode": args.mode,
               "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "source": {"published_commit": args.expected_commit, "execution_sources": recovery.execution_source_hashes(source_files),
                          "config_sha256": core.sha256_file(config_path), "protocol_sha256": core.sha256_file(PROTOCOL)},
               "resource_snapshot": core.resource_snapshot(),
               "environment": {name: core.package_version(name) for name in ("numpy", "transformers", "tokenizers", "sqlglot")},
               "api_calls": 0, "model_forwards": 0, "gpu_seconds": 0, "sql_executions": 0, "human_reviews": 0}
    core.write_json(args.output_dir / "run_start.json", receipt)
    try:
        info = core.load_registered_inputs(args, config_path=config_path, plan_path=PROTOCOL, experiment_id=EXPERIMENT_ID)
        recovery.assert_frozen_hashes(config, info["p2b_hashes"])
        receipt["input_hashes"] = info["p2b_hashes"]
        if args.mode == "full":
            if args.smoke_dir is None or args.smoke_dir.resolve() != Path(config["private_output_dirs"]["smoke"]).resolve():
                raise RuntimeError("Risk smoke directory is not the registered one")
            smoke = recovery.read_stage_receipt(args.smoke_dir, EXPERIMENT_ID, config["run_ids"]["smoke"], "smoke_passed", args.expected_commit)
            if smoke["source"]["execution_sources"] != receipt["source"]["execution_sources"] or smoke["input_hashes"] != receipt["input_hashes"]:
                raise RuntimeError("Risk smoke code/inputs differ")
            if smoke["environment"] != receipt["environment"]:
                raise RuntimeError("Risk dependencies changed after smoke")
        query_path = args.dataset_root / "dev.json"
        if core.sha256_file(query_path) != config["query_json_sha256"]:
            raise RuntimeError("Risk query data hash differs")
        old_aggregate = args.p2c_run_dir / "aggregate_summary.json"
        old_rows = args.p2c_run_dir / "per_question_private.jsonl"
        if core.sha256_file(old_aggregate) != config["p2c_aggregate_sha256"] or core.sha256_file(old_rows) != config["p2c_private_rows_sha256"]:
            raise RuntimeError("Risk P2c-R artifacts differ from registration")
        raw = {int(item["question_id"]): item for item in json.loads(query_path.read_text())}
        prepared = info["prepared_full"]
        chosen = prepared["questions"][:5] if args.mode == "smoke" else prepared["questions"]
        r0 = {node.node_id: node.text for node in prepared["nodes"]}
        r1 = {node.node_id: node.text for node in info["r1_nodes_full"]}
        aliases = {db: f"db_{i:02d}" for i, db in enumerate(sorted({q["db_id"] for q in prepared["questions"]}), 1)}
        totals = {"all": Counter(), "column_eligible": Counter(), "fixed_non_saturated": Counter()}
        per_db = {alias: Counter() for alias in aliases.values()}
        coverage = {name: Counter() for name in ("rescued", "damaged", "unchanged")}
        diagnostics, errors = Counter(), Counter()
        traces = args.output_dir / "per_question_private.jsonl"
        with old_rows.open() as source, traces.open("x") as trace:
            for question in chosen:
                previous = json.loads(next(source))
                qid, db = question["question_id"], question["db_id"]
                if (previous["question_id"], previous["db_id"]) != (qid, db) or raw[qid]["db_id"] != db:
                    raise RuntimeError("Risk question order differs")
                item = raw[qid]
                measures = Counter(questions=1)
                flags = []
                parse_error = None
                try:
                    literals, detail = extract_predicate_literals(item["SQL"])
                    diagnostics.update(detail)
                    measures["parsed_queries"] = 1
                    measures["questions_with_predicate_literals"] = int(bool(literals))
                    if previous["column_eligible"]:
                        left, right = previous["arms"]["V00"]["budgets"]["1024"], previous["arms"]["V01"]["budgets"]["1024"]
                        flags = find_exposures(literals, item["question"] + "\n" + item.get("evidence", ""),
                                               left["selected_ids"], right["selected_ids"], r0, r1, set(question["label"]["gold_column_ids"]))
                except (sqlglot.errors.ParseError, ValueError) as error:
                    parse_error = type(error).__name__
                    errors[parse_error] += 1
                    measures["parse_failures"] = 1
                measures.update({"questions_with_values_exposure": int(bool(flags)), "literal_exposures": len(flags),
                                 "questions_with_exposure_absent_from_question_evidence": int(any(not f["input_mentions_literal"] for f in flags)),
                                 "questions_with_exposure_on_gold_schema_column": int(any(f["matching_gold_column"] for f in flags)),
                                 "questions_with_retained_node_exposure": int(any(f["matching_node_retained"] for f in flags))})
                totals["all"].update(measures)
                per_db[aliases[db]].update(measures)
                if previous["column_eligible"]:
                    totals["column_eligible"].update(measures)
                    if db in info["fixed_dbs"]:
                        totals["fixed_non_saturated"].update(measures)
                    a = previous["arms"]["V00"]["budgets"]["1024"]["complete"]
                    b = previous["arms"]["V01"]["budgets"]["1024"]["complete"]
                    category = "rescued" if b > a else "damaged" if b < a else "unchanged"
                    coverage[category].update(measures)
                trace.write(json.dumps({"question_id": qid, "db_id": db, "parse_error": parse_error, "counts": measures, "flags": flags}, ensure_ascii=False) + "\n")
                if time.process_time() - started_cpu > 300 or core.peak_rss_gib() > 4:
                    raise RuntimeError("Risk CPU/RSS budget exceeded")
        if totals["all"]["parsed_queries"] / len(chosen) < (1.0 if args.mode == "smoke" else 0.95):
            raise RuntimeError("Risk parser coverage gate failed")
        aggregate = {"experiment_id": EXPERIMENT_ID, "run_id": args.run_id, "status": "completed",
                     "source_commit": args.expected_commit, "mode": args.mode, "smoke_only": args.mode == "smoke",
                     "interpretation": "Lexical exposure flags only; no semantic necessity, SQL accuracy or safety certification",
                     "counts": totals, "per_database_anonymized": per_db, "coverage_strata": coverage,
                     "exposure_denominator": totals["column_eligible"]["questions"],
                     "unassessed_column_ineligible_questions": totals["all"]["questions"] - totals["column_eligible"]["questions"],
                     "literal_diagnostics": diagnostics, "parse_error_types": errors, "human_reviews": 0,
                     "decision": "retain_offline_candidate_prioritize_human_value_review" if totals["column_eligible"]["questions_with_values_exposure"] else "no_lexical_exposure_detected_semantic_risk_unresolved",
                     "frozen_p2c_aggregate_sha256": config["p2c_aggregate_sha256"], "input_hashes": receipt["input_hashes"],
                     "api_usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_cny": "0.00"},
                     "sql_executions": 0, "model_forwards": 0}
        receipt["aggregate_summary_sha256"] = recovery.write_roundtrip(args.output_dir / "aggregate_summary.json", aggregate)
        receipt["private_rows_sha256"] = core.sha256_file(traces)
        if time.process_time() - started_cpu > 300 or core.peak_rss_gib() > 4:
            raise RuntimeError("Risk CPU/RSS budget exceeded after persistence")
        receipt.update(state="completed", stage_result=args.mode + "_passed", decision=aggregate["decision"])
    except Exception as error:
        receipt.update(state="failed", error_type=type(error).__name__)
        raise
    finally:
        receipt.update(cpu_seconds=time.process_time() - started_cpu, wall_seconds=time.perf_counter() - started_wall,
                       peak_rss_gib=core.peak_rss_gib(), finished_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        core.write_json(args.output_dir / "run_start.json", receipt)
        print(json.dumps({key: receipt.get(key) for key in ("run_id", "state", "stage_result", "cpu_seconds", "wall_seconds", "peak_rss_gib", "decision", "error_type")}), flush=True)


if __name__ == "__main__":
    run()
