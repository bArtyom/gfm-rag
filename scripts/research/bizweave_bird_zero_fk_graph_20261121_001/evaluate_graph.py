#!/usr/bin/env python3
"""Evaluate a frozen graph on BIRD table/JOIN references and compare retrieval."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import sqlglot
from sqlglot import exp


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tokens(text):
    return TOKEN_RE.findall(str(text or "").replace("_", " ").casefold())


def bm25_scores(query, documents, k1=1.5, b=0.75):
    docs = [tokens(document) for document in documents]
    n_docs = len(docs)
    if n_docs == 0:
        return []
    doc_freq = Counter()
    for doc in docs:
        doc_freq.update(set(doc))
    avg_len = sum(map(len, docs)) / n_docs or 1.0
    query_counts = Counter(tokens(query))
    output = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for term, qf in query_counts.items():
            if term not in tf:
                continue
            idf = math.log(1.0 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denom = tf[term] + k1 * (1.0 - b + b * len(doc) / avg_len)
            score += qf * idf * tf[term] * (k1 + 1.0) / denom
        output.append(score)
    return output


def endpoint_key(table_a, column_a, table_b, column_b):
    first = (str(table_a).casefold(), str(column_a).casefold())
    second = (str(table_b).casefold(), str(column_b).casefold())
    return tuple(sorted((first, second)))


def sql_tables_and_joins(sql, allowed_tables):
    tree = sqlglot.parse_one(sql, read="sqlite")
    aliases = {}
    for table in tree.find_all(exp.Table):
        physical_name = table.name
        if physical_name.casefold() in allowed_tables:
            aliases[physical_name.casefold()] = physical_name.casefold()
            alias_name = table.alias_or_name
            aliases[alias_name.casefold()] = physical_name.casefold()

    referenced = {
        table.name.casefold()
        for table in tree.find_all(exp.Table)
        if table.name.casefold() in allowed_tables
    }
    joins = set()
    for join in tree.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue
        for equality in on_expr.find_all(exp.EQ):
            left = equality.this
            right = equality.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            if not left.table or not right.table:
                continue
            left_table = aliases.get(left.table.casefold())
            right_table = aliases.get(right.table.casefold())
            if not left_table or not right_table:
                continue
            if left.name.casefold() not in allowed_tables[left_table]:
                continue
            if right.name.casefold() not in allowed_tables[right_table]:
                continue
            joins.add(endpoint_key(left_table, left.name, right_table, right.name))
    return referenced, joins


def normalized_names(names):
    return {str(name).casefold(): str(name) for name in names}


def graph_text(node):
    parts = [node.get("label", ""), node.get("kind", ""), node.get("description", "")]
    parts.extend(node.get("aliases") or [])
    for binding in node.get("physical_bindings") or []:
        parts.extend([binding.get("table", ""), *(binding.get("columns") or [])])
    return " ".join(str(part) for part in parts if part)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    dataset = config["dataset"]
    run_root = Path(config["paths"]["run_root"])
    graph_path = args.graph or run_root / "generation_001/graph.json"
    input_path = args.input or run_root / "input_001/model_input.json"
    output_dir = args.output_dir or run_root / "evaluation_001"
    if not graph_path.is_file() or not input_path.is_file():
        raise FileNotFoundError("Frozen graph or model input is missing")
    if (output_dir / "aggregate.public.json").exists() or (output_dir / "per_query.local.jsonl").exists():
        raise FileExistsError(f"Refusing to overwrite evaluation outputs: {output_dir}")

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    model_input = json.loads(input_path.read_text(encoding="utf-8"))
    tasks = json.loads(Path(dataset["tasks_file"]).read_text(encoding="utf-8"))
    selected_tasks = [item for item in tasks if item.get("db_id") == dataset["database_id"]]
    tables = [item["name"] for item in model_input["tables"]]
    table_lookup = normalized_names(tables)
    allowed_columns = {
        table.casefold(): {column["name"].casefold() for column in item["columns"]}
        for table, item in zip(tables, model_input["tables"])
    }
    evidence_ids = {entry["evidence_id"] for entry in model_input.get("evidence", [])}

    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    duplicate_node_ids = len(node_by_id) != len(nodes)
    table_binding_total = 0
    table_binding_valid = 0
    column_binding_total = 0
    column_binding_valid = 0
    evidence_reference_total = 0
    evidence_reference_valid = 0
    node_tables = defaultdict(set)
    node_docs = []
    node_doc_ids = []
    invalid_binding_count = 0

    def count_evidence(values):
        nonlocal evidence_reference_total, evidence_reference_valid
        values = values if isinstance(values, list) else []
        evidence_reference_total += len(values)
        evidence_reference_valid += sum(str(value) in evidence_ids for value in values)

    for node in nodes:
        node_id = str(node.get("id", ""))
        count_evidence(node.get("evidence_ids"))
        node_docs.append(graph_text(node))
        node_doc_ids.append(node_id)
        for binding in node.get("physical_bindings") or []:
            table_binding_total += 1
            columns = binding.get("columns") or []
            column_binding_total += len(columns)
            table_name = table_lookup.get(str(binding.get("table", "")).casefold())
            if table_name is None:
                invalid_binding_count += 1
                invalid_binding_count += len(columns)
                continue
            table_binding_valid += 1
            table_key = table_name.casefold()
            node_tables[node_id].add(table_key)
            for column in columns:
                if str(column).casefold() in allowed_columns[table_key]:
                    column_binding_valid += 1
                else:
                    invalid_binding_count += 1
            count_evidence(binding.get("evidence_ids"))

    valid_edges = 0
    edge_table_pairs = []
    edge_docs = []
    predicted_join_keys = set()
    schema_valid_join_keys = set()
    invalid_join_candidate_count = 0
    for edge in edges:
        count_evidence(edge.get("evidence_ids"))
        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        if source_id in node_by_id and target_id in node_by_id:
            valid_edges += 1
        candidates = edge.get("physical_join_candidates") or []
        for candidate in candidates:
            count_evidence(candidate.get("evidence_ids"))
            left_table = table_lookup.get(str(candidate.get("left_table", "")).casefold())
            right_table = table_lookup.get(str(candidate.get("right_table", "")).casefold())
            left_column = str(candidate.get("left_column", ""))
            right_column = str(candidate.get("right_column", ""))
            if (
                left_table is None
                or right_table is None
                or left_column.casefold() not in allowed_columns.get(left_table.casefold(), set())
                or right_column.casefold() not in allowed_columns.get(right_table.casefold(), set())
            ):
                invalid_join_candidate_count += 1
                continue
            key = endpoint_key(left_table, left_column, right_table, right_column)
            schema_valid_join_keys.add(key)
            predicted_join_keys.add(key)
            edge_table_pairs.append((left_table.casefold(), right_table.casefold()))
        if not candidates:
            source_tables = node_tables.get(source_id, set())
            target_tables = node_tables.get(target_id, set())
            for left_table in source_tables:
                for right_table in target_tables:
                    edge_table_pairs.append((left_table, right_table))

    raw_docs_by_table = {table.casefold(): [table] for table in tables}
    for table_item in model_input["tables"]:
        table_key = table_item["name"].casefold()
        raw_docs_by_table[table_key].extend(column["name"] for column in table_item["columns"])
    for evidence in model_input.get("evidence", []):
        table_key = str(evidence.get("table") or "").casefold()
        if table_key in raw_docs_by_table:
            raw_docs_by_table[table_key].append(evidence.get("text", ""))
    raw_documents = [" ".join(raw_docs_by_table[table.casefold()]) for table in tables]

    flat_docs_by_table = {table.casefold(): [] for table in tables}
    for node in nodes:
        text = graph_text(node)
        for table_key in node_tables.get(str(node.get("id", "")), set()):
            flat_docs_by_table[table_key].append(text)
    adjacency = defaultdict(set)
    for left_table, right_table in edge_table_pairs:
        adjacency[left_table].add(right_table)
        adjacency[right_table].add(left_table)
    flat_documents = [" ".join(flat_docs_by_table[table.casefold()]) for table in tables]

    parsed_examples = []
    sql_parse_failures = []
    no_gold_table_examples = 0
    observed_join_keys = set()
    observed_join_frequency = Counter()
    for index, task in enumerate(selected_tasks):
        try:
            gold_tables, gold_joins = sql_tables_and_joins(task["SQL"], allowed_columns)
        except Exception as exc:
            sql_parse_failures.append({"case_index": index, "error_class": type(exc).__name__})
            continue
        if not gold_tables:
            no_gold_table_examples += 1
            continue
        observed_join_keys.update(gold_joins)
        observed_join_frequency.update(gold_joins)
        parsed_examples.append({
            "case_index": index,
            "question": task.get("question", ""),
            "gold_tables": gold_tables,
        })

    if len(selected_tasks) != dataset["expected_task_count"]:
        raise ValueError(f"Evaluation task count changed: {len(selected_tasks)}")

    method_totals = {
        name: {k: {"recall_sum": 0.0, "complete": 0, "mrr_sum": 0.0} for k in config["evaluation"]["top_k"]}
        for name in ["schema_bm25", "flat_graph_bm25", "typed_graph"]
    }
    per_query = []
    for example in parsed_examples:
        question = example["question"]
        gold = example["gold_tables"]
        schema_scores = bm25_scores(question, raw_documents)
        flat_scores = bm25_scores(question, flat_documents)
        node_scores = bm25_scores(question, node_docs)

        table_node_scores = defaultdict(list)
        for position, node_id in enumerate(node_doc_ids):
            for table_key in node_tables.get(node_id, set()):
                table_node_scores[table_key].append(node_scores[position])
        neighbor_node_scores = defaultdict(list)
        for table_key, adjacent in adjacency.items():
            for adjacent_table in adjacent:
                neighbor_node_scores[table_key].extend(table_node_scores.get(adjacent_table, []))
        typed_scores = []
        for table in tables:
            table_key = table.casefold()
            direct = max(table_node_scores.get(table_key, [0.0]))
            neighbor = max(neighbor_node_scores.get(table_key, [0.0]))
            typed_scores.append(direct + 0.25 * neighbor)

        all_method_scores = {
            "schema_bm25": schema_scores,
            "flat_graph_bm25": flat_scores,
            "typed_graph": typed_scores,
        }
        row = {"case_index": example["case_index"], "methods": {}}
        for method_name, scores in all_method_scores.items():
            ranked = sorted(range(len(tables)), key=lambda item: (-scores[item], tables[item].casefold()))
            ranked_tables = [tables[item].casefold() for item in ranked]
            gold_ranks = [rank + 1 for rank, table in enumerate(ranked_tables) if table in gold]
            mrr = 1.0 / min(gold_ranks) if gold_ranks else 0.0
            row["methods"][method_name] = {"top_tables": [tables[item] for item in ranked[:5]]}
            for k in config["evaluation"]["top_k"]:
                top = set(ranked_tables[:k])
                method_totals[method_name][k]["recall_sum"] += len(gold & top) / len(gold)
                method_totals[method_name][k]["complete"] += int(gold <= top)
                method_totals[method_name][k]["mrr_sum"] += mrr
        per_query.append(row)

    n_eval = len(parsed_examples)
    metrics = {}
    for method_name, by_k in method_totals.items():
        metrics[method_name] = {}
        for k, values in by_k.items():
            divisor = n_eval or 1
            metrics[method_name][str(k)] = {
                "mean_table_recall_at_k": values["recall_sum"] / divisor,
                "complete_gold_table_coverage_at_k": values["complete"] / divisor,
                "mean_reciprocal_rank": values["mrr_sum"] / divisor,
            }

    valid_evidence_ratio = evidence_reference_valid / evidence_reference_total if evidence_reference_total else None
    binding_validity = column_binding_valid / column_binding_total if column_binding_total else None
    table_binding_validity = table_binding_valid / table_binding_total if table_binding_total else None
    join_precision = len(predicted_join_keys & observed_join_keys) / len(predicted_join_keys) if predicted_join_keys else None
    join_recall = len(predicted_join_keys & observed_join_keys) / len(observed_join_keys) if observed_join_keys else None
    try:
        git_commit = subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[3]), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        git_commit = "unavailable"

    aggregate = {
        "run_id": config["run_id"],
        "evidence_level": "single-database exploratory; Gold-SQL proxy labels; no human semantic labels",
        "dataset": dataset["name"],
        "database_id": dataset["database_id"],
        "table_count": len(tables),
        "declared_foreign_key_count": model_input["declared_foreign_key_count"],
        "task_count": len(selected_tasks),
        "sql_parsed_count": len(parsed_examples) + no_gold_table_examples,
        "sql_parse_failures": len(sql_parse_failures),
        "parsed_without_physical_gold_table": no_gold_table_examples,
        "ranking_question_count": n_eval,
        "unique_observed_gold_join_pairs": len(observed_join_keys),
        "model_graph_node_count": len(nodes),
        "model_graph_edge_count": len(edges),
        "model_graph_valid_edge_endpoint_count": valid_edges,
        "duplicate_node_ids": duplicate_node_ids,
        "physical_binding_count": table_binding_total,
        "physical_binding_table_validity": table_binding_validity,
        "physical_binding_column_count": column_binding_total,
        "physical_binding_column_validity": binding_validity,
        "invalid_physical_binding_count": invalid_binding_count,
        "evidence_reference_count": evidence_reference_total,
        "evidence_id_validity": valid_evidence_ratio,
        "evidence_id_entailment_reviewed": False,
        "predicted_unique_join_candidates": len(predicted_join_keys),
        "schema_valid_predicted_join_candidates": len(schema_valid_join_keys),
        "invalid_join_candidate_count": invalid_join_candidate_count,
        "predicted_join_candidate_precision_vs_observed_gold_sql": join_precision,
        "predicted_join_candidate_recall_vs_observed_gold_sql": join_recall,
        "retrieval_metrics": metrics,
        "schema_sha256": dataset["expected_schema_sha256"],
        "tasks_sha256": dataset["expected_tasks_sha256"],
        "model_graph_sha256": sha256_file(graph_path),
        "model_input_sha256": sha256_file(input_path),
        "evaluation_code_commit": git_commit,
        "interpretation": "Gold SQL is used only after graph generation for table-use/JOIN-use proxies; these are not semantic gold labels or evidence that the reference SQL is the only correct implementation.",
    }

    public_path = output_dir / "aggregate.public.json"
    local_path = output_dir / "per_query.local.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    if public_path.exists() or local_path.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation outputs: {output_dir}")
    public_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with local_path.open("x", encoding="utf-8") as handle:
        for row in per_query:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    failure_path = output_dir / "parse_failures.local.json"
    if failure_path.exists():
        raise FileExistsError(f"Refusing to overwrite parse-failure file: {failure_path}")
    failure_path.write_text(json.dumps(sql_parse_failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
