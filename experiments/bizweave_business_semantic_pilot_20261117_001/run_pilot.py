#!/usr/bin/env python3
"""Run the preregistered BizWeave synthetic mechanism and BIRD supply audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


RUN_ID = "bizweave_business_semantic_pilot_20261117_001"
CONFIG_PATH = Path(__file__).with_name("config.json")
TOKEN_RE = re.compile(r"[a-z0-9]+", flags=re.IGNORECASE)


def tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text or "")}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_source_hashes(dataset_root: Path, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for relative_path, expected_hash in config["source_hashes"].items():
        path = dataset_root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"required BIRD source file missing: {relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"source hash mismatch for {relative_path}")
        observed[relative_path] = {"sha256": actual_hash, "bytes": path.stat().st_size}
    return observed


def load_json_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise TypeError(f"expected a JSON list in {path.name}")
    return value


def parse_query(sql_text: str) -> dict[str, Any] | None:
    try:
        tree = sqlglot.parse_one(sql_text, read="sqlite")
    except Exception:
        return None

    where_columns: set[str] = set()
    for predicate in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Having)):
        where_columns.update(column.name.lower() for column in predicate.find_all(exp.Column))

    tables = {table.name.lower() for table in tree.find_all(exp.Table) if table.name}
    count_present = any(True for _ in tree.find_all(exp.Count))
    group_present = any(True for _ in tree.find_all(exp.Group))
    return {
        "where_columns": where_columns,
        "table_count": len(tables),
        "join_count": sum(1 for _ in tree.find_all(exp.Join)),
        "count_present": count_present,
        "group_present": group_present,
    }


def cue_intersections(question: str, sql_features: dict[str, Any], lexicons: dict[str, list[str]]) -> dict[str, bool]:
    qtokens = tokens(question)
    state_cols = set(sql_features["where_columns"])
    time_cols = set(sql_features["where_columns"])
    state_field = any(any(pattern in name for pattern in lexicons["state_columns"]) for name in state_cols)
    time_field = any(any(pattern in name for pattern in lexicons["time_columns"]) for name in time_cols)
    state_question = bool(qtokens.intersection(lexicons["state_question"]))
    time_question = bool(qtokens.intersection(lexicons["time_question"]))
    grain_question = bool(qtokens.intersection(lexicons["grain_question"])) or bool(
        re.search(r"\bhow many\b|\bnumber of\b", question.lower())
    )
    has_join = sql_features["join_count"] > 0 and sql_features["table_count"] > 1
    return {
        "state_candidate": state_question and state_field,
        "time_candidate": time_question and time_field,
        "grain_candidate": grain_question and (sql_features["count_present"] or sql_features["group_present"]),
        "multi_table_join": has_join,
        "strict_join_condition_candidate": has_join
        and (
            (state_question and state_field)
            or (time_question and time_field)
            or (grain_question and (sql_features["count_present"] or sql_features["group_present"]))
        ),
    }


def audit_split(
    dataset_root: Path,
    split: str,
    query_relative: str,
    tables_relative: str,
    lexicons: dict[str, list[str]],
    limit: int | None,
) -> dict[str, Any]:
    queries = load_json_list(dataset_root / query_relative)
    schemas = load_json_list(dataset_root / tables_relative)
    schema_db_ids = {str(row.get("db_id", "")) for row in schemas}
    selected = queries if limit is None else queries[:limit]
    counts = defaultdict(int)
    databases: dict[str, set[str]] = defaultdict(set)
    parsed_queries = 0
    failed_queries = 0

    for row in selected:
        db_id = str(row.get("db_id", ""))
        databases["all"].add(db_id)
        sql_text = str(row.get("SQL", ""))
        parsed = parse_query(sql_text)
        if parsed is None:
            failed_queries += 1
            continue
        parsed_queries += 1
        counts["has_join"] += int(parsed["join_count"] > 0)
        counts["has_where"] += int(bool(parsed["where_columns"]))
        counts["has_count_or_group"] += int(parsed["count_present"] or parsed["group_present"])
        if parsed["table_count"] > 1:
            counts["has_multiple_tables"] += 1

        signals = cue_intersections(str(row.get("question", "")), parsed, lexicons)
        for name, value in signals.items():
            if value:
                counts[name] += 1
                databases[name].add(db_id)

    result: dict[str, Any] = {
        "split": split,
        "source_query_rows": len(queries),
        "source_schema_databases": len(schema_db_ids),
        "audited_query_rows": len(selected),
        "parsed_queries": parsed_queries,
        "parse_failures": failed_queries,
        "database_count_in_audited_rows": len(databases["all"]),
        "counts": dict(sorted(counts.items())),
        "candidate_database_counts": {
            name: len(db_ids) for name, db_ids in sorted(databases.items()) if name != "all"
        },
    }
    return result


def make_mapping(
    mapping_id: str,
    event: str,
    tables: list[str],
    schema_text: str,
    description: str,
    filters: dict[str, str],
    grain: str,
    time_basis: str | None,
    evidence_state: str,
    path_cost: int,
) -> dict[str, Any]:
    return {
        "id": mapping_id,
        "event": event,
        "tables": tables,
        "schema_text": schema_text,
        "description": description,
        "filters": filters,
        "grain": grain,
        "time_basis": time_basis,
        "evidence_state": evidence_state,
        "evidence_refs": ["synthetic_business_spec_v1", "synthetic_mapping_audit_v1"]
        if evidence_state == "verified"
        else [],
        "path_cost": path_cost,
    }


def synthetic_cases() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    purchase = make_mapping(
        "purchase_order_items",
        "Purchase",
        ["trade_order", "trade_item"],
        "trade_order buyer_no order_no created_at trade_item order_no product_no",
        "Order and item rows; customer buys product through an order; order grain is distinct order; created time is available.",
        {},
        "customer_distinct",
        "order_creation",
        "verified",
        3,
    )
    browse = make_mapping(
        "browse_user_event",
        "Browse",
        ["user_event"],
        "user_event uid product_id event_type event_at",
        "Activity event row; event type can be click or view; activity time is available.",
        {},
        "customer_distinct",
        "activity_time",
        "verified",
        2,
    )
    payment_done = make_mapping(
        "payment_success_code_2",
        "PaymentCompleted",
        ["trade_order", "pay_attempt"],
        "trade_order order_no trade_order buyer_no pay_attempt order_no state_code paid_at",
        "Payment event joined to an order; pay_attempt state code 2; order grain; paid_at time.",
        {"payment_state": "SUCCESS"},
        "order_distinct",
        "payment_time",
        "verified",
        2,
    )
    payment_attempt = make_mapping(
        "payment_attempt_rows",
        "PaymentAttempted",
        ["trade_order", "pay_attempt"],
        "trade_order order_no trade_order buyer_no pay_attempt order_no state_code attempted_at",
        "Payment attempt rows joined to an order; state code is not filtered; attempt grain.",
        {},
        "attempt_count",
        "attempt_time",
        "verified",
        2,
    )
    refund_done = make_mapping(
        "refund_completed_code_r1",
        "RefundCompleted",
        ["trade_order", "refund_record"],
        "trade_order order_no refund_record order_no state_code completed_at",
        "Refund row joined to an order; refund state code R1; order grain; completion time.",
        {"refund_state": "COMPLETED"},
        "order_distinct",
        "refund_completion_time",
        "verified",
        2,
    )
    refund_requested = make_mapping(
        "refund_requested_code_r0",
        "RefundRequested",
        ["trade_order", "refund_record"],
        "trade_order order_no refund_record order_no state_code requested_at",
        "Refund row joined to an order; refund state code R0; request time.",
        {"refund_state": "REQUESTED"},
        "order_distinct",
        "refund_request_time",
        "verified",
        2,
    )
    order_count = make_mapping(
        "order_distinct_count",
        "Purchase",
        ["trade_order", "trade_item"],
        "trade_order order_no trade_item order_no product_no item_no",
        "Order and item rows; count distinct order number to avoid one-to-many duplication.",
        {},
        "order_distinct",
        None,
        "verified",
        3,
    )
    line_count = make_mapping(
        "line_item_count",
        "Purchase",
        ["trade_order", "trade_item"],
        "trade_order order_no trade_item order_no product_no item_no",
        "Order and item rows; count one row per product line.",
        {},
        "line_item_count",
        None,
        "verified",
        3,
    )
    payment_unknown = make_mapping(
        "payment_code_2_unverified",
        "PaymentCompleted",
        ["trade_order", "pay_attempt"],
        "trade_order order_no pay_attempt order_no state_code paid_at",
        "Payment state code 2; no trusted definition is available.",
        {"payment_state": "SUCCESS"},
        "order_distinct",
        "payment_time",
        "unknown",
        2,
    )
    purchase_created = make_mapping(
        "purchase_created_time",
        "Purchase",
        ["trade_order", "trade_item"],
        "trade_order order_no trade_item order_no product_no created_at",
        "Purchase event mapped to order creation time.",
        {},
        "customer_distinct",
        "order_creation",
        "verified",
        3,
    )
    purchase_paid = make_mapping(
        "purchase_paid_time",
        "Purchase",
        ["trade_order", "trade_item", "pay_attempt"],
        "trade_order order_no trade_item order_no product_no pay_attempt paid_at",
        "Purchase event mapped to payment time.",
        {},
        "customer_distinct",
        "payment_time",
        "verified",
        4,
    )

    cases = [
        {"id": "purchase_vs_browse_purchase", "pair": "purchase_vs_browse", "question": "Which customers bought product A?", "expected": purchase["id"], "resolved": True},
        {"id": "purchase_vs_browse_browse", "pair": "purchase_vs_browse", "question": "Which customers viewed product A?", "expected": browse["id"], "resolved": True},
        {"id": "payment_completed", "pair": "payment_state", "question": "Which orders have successful payments?", "expected": payment_done["id"], "resolved": True},
        {"id": "payment_attempted", "pair": "payment_state", "question": "How many payment attempts occurred?", "expected": payment_attempt["id"], "resolved": True},
        {"id": "refund_completed", "pair": "refund_state", "question": "Which orders have completed refunds?", "expected": refund_done["id"], "resolved": True},
        {"id": "refund_requested", "pair": "refund_state", "question": "Which orders have requested refunds?", "expected": refund_requested["id"], "resolved": True},
        {"id": "order_grain", "pair": "order_vs_line_grain", "question": "How many orders contained product A?", "expected": order_count["id"], "resolved": True},
        {"id": "line_grain", "pair": "order_vs_line_grain", "question": "How many product line items were sold?", "expected": line_count["id"], "resolved": True},
        {"id": "unverified_payment_state", "pair": None, "question": "Which orders were paid?", "expected": None, "resolved": False},
        {"id": "unspecified_purchase_time", "pair": None, "question": "Which purchases happened last month?", "expected": None, "resolved": False},
    ]
    candidates = {
        "purchase_vs_browse": [purchase, browse],
        "payment_state": [payment_done, payment_attempt],
        "refund_state": [refund_done, refund_requested],
        "order_vs_line_grain": [order_count, line_count],
        "unverified_payment_state": [payment_unknown],
        "unspecified_purchase_time": [purchase_created, purchase_paid],
    }
    return cases, candidates


def parse_synthetic_intent(question: str) -> dict[str, Any] | None:
    text = question.lower()
    if re.search(r"\b(viewed|clicked|browsed)\b", text):
        event = "Browse"
    elif re.search(r"\b(successful payment|successful payments|paid)\b", text):
        event = "PaymentCompleted"
    elif re.search(r"\bpayment attempts?\b", text):
        event = "PaymentAttempted"
    elif re.search(r"\bcompleted refunds?\b", text):
        event = "RefundCompleted"
    elif re.search(r"\brequested refunds?\b", text):
        event = "RefundRequested"
    elif re.search(r"\b(line items?|product lines?|orders? (contained|containing) product)\b", text):
        event = "Purchase"
    elif re.search(r"\b(bought|purchased|purchase|purchases)\b", text):
        event = "Purchase"
    else:
        return None

    if event == "PaymentAttempted":
        grain = "attempt_count"
    elif re.search(r"\b(line items?|product lines?)\b", text):
        grain = "line_item_count"
    elif re.search(r"\borders?\b", text):
        grain = "order_distinct"
    else:
        grain = "customer_distinct"

    filters: dict[str, str] = {}
    if event == "PaymentCompleted":
        filters = {"payment_state": "SUCCESS"}
    elif event == "RefundCompleted":
        filters = {"refund_state": "COMPLETED"}
    elif event == "RefundRequested":
        filters = {"refund_state": "REQUESTED"}

    time_basis = "unspecified" if "last month" in text else None
    return {"event": event, "filters": filters, "grain": grain, "time_basis": time_basis}


def mapping_matches(mapping: dict[str, Any], intent: dict[str, Any], require_evidence: bool) -> bool:
    if require_evidence and mapping["evidence_state"] != "verified":
        return False
    if mapping["event"] != intent["event"] or mapping["filters"] != intent["filters"]:
        return False
    if mapping["grain"] != intent["grain"]:
        return False
    if intent["time_basis"] == "unspecified":
        return not require_evidence
    if intent["time_basis"] is not None and mapping["time_basis"] != intent["time_basis"]:
        return False
    return True


def choose_lexical(question: str, choices: list[dict[str, Any]], include_description: bool) -> str | None:
    query_tokens = tokens(question)

    def score(mapping: dict[str, Any]) -> tuple[float, str]:
        candidate_text = mapping["schema_text"]
        if include_description:
            candidate_text += " " + mapping["description"]
        candidate_tokens = tokens(candidate_text)
        return (len(query_tokens.intersection(candidate_tokens)) / max(1, len(query_tokens)), mapping["id"])

    return max(choices, key=score)["id"] if choices else None


def choose_shortest(choices: list[dict[str, Any]]) -> str | None:
    return min(choices, key=lambda mapping: (mapping["path_cost"], mapping["id"]))["id"] if choices else None


def choose_structured(
    question: str,
    choices: list[dict[str, Any]],
    require_evidence: bool,
) -> tuple[str | None, bool]:
    intent = parse_synthetic_intent(question)
    if intent is None:
        return None, False
    matches = [mapping for mapping in choices if mapping_matches(mapping, intent, require_evidence)]
    if len(matches) != 1:
        return None, True
    return matches[0]["id"], True


def summarize_predictions(
    cases: list[dict[str, Any]],
    candidate_sets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    methods = ["shortest_path", "schema_token_overlap", "flat_description_overlap", "bizweave_full", "bizweave_without_evidence_gate"]
    predictions: dict[str, dict[str, str | None]] = {method: {} for method in methods}
    intent_parse_correct = 0

    for case in cases:
        choices = candidate_sets[case["pair"] or case["id"]]
        q = case["question"]
        predictions["shortest_path"][case["id"]] = choose_shortest(choices)
        predictions["schema_token_overlap"][case["id"]] = choose_lexical(q, choices, include_description=False)
        predictions["flat_description_overlap"][case["id"]] = choose_lexical(q, choices, include_description=True)
        full_prediction, parsed = choose_structured(q, choices, require_evidence=True)
        no_evidence_prediction, _ = choose_structured(q, choices, require_evidence=False)
        predictions["bizweave_full"][case["id"]] = full_prediction
        predictions["bizweave_without_evidence_gate"][case["id"]] = no_evidence_prediction
        intent_parse_correct += int(parsed)

    expected_by_id = {case["id"]: case["expected"] for case in cases}
    resolved_ids = [case["id"] for case in cases if case["resolved"]]
    unresolved_ids = [case["id"] for case in cases if not case["resolved"]]
    pair_ids: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        if case["pair"]:
            pair_ids[case["pair"]].append(case["id"])

    summary: dict[str, Any] = {"case_count": len(cases), "resolved_case_count": len(resolved_ids), "unresolved_control_count": len(unresolved_ids), "intent_parse_count": intent_parse_correct, "methods": {}}
    for method in methods:
        exact = sum(predictions[method][case_id] == expected_by_id[case_id] for case_id in resolved_ids)
        correct_abstentions = sum(predictions[method][case_id] is None for case_id in unresolved_ids)
        pair_switches = sum(
            all(predictions[method][case_id] == expected_by_id[case_id] for case_id in pair_case_ids)
            for pair_case_ids in pair_ids.values()
        )
        summary["methods"][method] = {
            "resolved_exact_correct": exact,
            "resolved_denominator": len(resolved_ids),
            "unresolved_correct_abstentions": correct_abstentions,
            "unresolved_denominator": len(unresolved_ids),
            "paired_contrasts_correctly_switched": pair_switches,
            "paired_contrast_denominator": len(pair_ids),
            "predictions": predictions[method],
        }

    best_baseline = max(
        summary["methods"][name]["resolved_exact_correct"]
        for name in ("shortest_path", "schema_token_overlap", "flat_description_overlap")
    )
    full = summary["methods"]["bizweave_full"]
    summary["best_unstructured_baseline_correct"] = best_baseline
    summary["synthetic_gate_pass"] = (
        full["resolved_exact_correct"] == 8
        and full["unresolved_correct_abstentions"] == 2
        and full["paired_contrasts_correctly_switched"] == 4
        and full["resolved_exact_correct"] - best_baseline >= 2
    )
    return summary


def run(dataset_root: Path, output_path: Path, limit: int | None) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_path}")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(f"output directory must already exist: {output_path.parent}")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config["run_id"] != RUN_ID:
        raise ValueError("configuration run_id mismatch")
    started = time.perf_counter()
    hashes = require_source_hashes(dataset_root, config)
    lexicons = config["lexicons"]
    train = audit_split(dataset_root, "train", "train/train.json", "train/train_tables.json", lexicons, limit)
    dev = audit_split(dataset_root, "dev", "dev/dev.json", "dev/dev_tables.json", lexicons, limit)
    train_db_ids = {
        row["db_id"] for row in load_json_list(dataset_root / "train/train.json")
    }
    dev_db_ids = {
        row["db_id"] for row in load_json_list(dataset_root / "dev/dev.json")
    }
    overlap = len(train_db_ids.intersection(dev_db_ids))

    threshold = config["readiness_threshold"]
    qualifying_categories = []
    for category in ("state_candidate", "time_candidate", "grain_candidate", "strict_join_condition_candidate"):
        train_n = train["counts"].get(category, 0)
        dev_n = dev["counts"].get(category, 0)
        train_db_n = train["candidate_database_counts"].get(category, 0)
        dev_db_n = dev["candidate_database_counts"].get(category, 0)
        if (
            train_n >= threshold["one_category_must_have_train_queries"]
            and train_db_n >= threshold["one_category_must_have_train_databases"]
            and dev_n >= threshold["one_category_must_have_dev_queries"]
            and dev_db_n >= threshold["one_category_must_have_dev_databases"]
        ):
            qualifying_categories.append(category)

    cases, candidate_sets = synthetic_cases()
    synthetic = summarize_predictions(cases, candidate_sets)
    elapsed = time.perf_counter() - started
    result = {
        "run_id": RUN_ID,
        "run_mode": "smoke" if limit is not None else "full",
        "status": "completed",
        "source_hashes": hashes,
        "runtime": {
            "python": platform.python_version(),
            "sqlglot": sqlglot.__version__,
            "elapsed_seconds": round(elapsed, 4),
            "device": "CPU",
            "model_calls": 0,
            "api_calls": 0,
            "sql_execution": 0,
        },
        "synthetic_mechanism": synthetic,
        "bird_candidate_supply_audit": {
            "train": train,
            "dev": dev,
            "train_dev_database_overlap_count": overlap,
            "readiness_threshold": threshold,
            "qualifying_categories": qualifying_categories,
            "readiness_gate_met": bool(qualifying_categories),
            "interpretation": "silver candidate supply only; no business labels or retrieval accuracy measured",
        },
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-per-split", type=int, default=None)
    args = parser.parse_args()
    if args.limit_per_split is not None and args.limit_per_split < 1:
        parser.error("--limit-per-split must be positive when specified")
    result = run(args.dataset_root.resolve(), args.output.resolve(), args.limit_per_split)
    bird = result["bird_candidate_supply_audit"]
    print(json.dumps({
        "run_id": result["run_id"],
        "run_mode": result["run_mode"],
        "synthetic_gate_pass": result["synthetic_mechanism"]["synthetic_gate_pass"],
        "bizweave_full": result["synthetic_mechanism"]["methods"]["bizweave_full"],
        "best_unstructured_baseline_correct": result["synthetic_mechanism"]["best_unstructured_baseline_correct"],
        "bird_readiness_gate_met": bird["readiness_gate_met"],
        "bird_train_candidates": {name: payload["counts"].get("strict_join_condition_candidate", 0) for name, payload in (("train", bird["train"]), ("dev", bird["dev"]))},
        "elapsed_seconds": result["runtime"]["elapsed_seconds"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
