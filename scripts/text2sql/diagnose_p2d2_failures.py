#!/usr/bin/env python3
"""Attribute frozen P2d failures without exposing private SQL or identifiers."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import re
import resource
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope


ARMS = ("E0", "E1", "E2")
EXPECTED_PREPARE_SEAL = "334e388af338c7f20575aa81a86ff7184e526716b251cd1b48955b4134172aaa"
EXPECTED_PREDICTIONS = "e88bf42f22a73b6b56af96a5d3ea88d69252c33509bb72da5b8cfde2f7474ea5"
EXPECTED_PREDICTION_SEAL_FILE = "f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3"
EXPECTED_P2D1_OUTCOMES = "9b7fec27ee0d23cddf76b4bf842ddde530a2f1bbb001fa449218d3b049b3711d"
EXPECTED_SCHEMA = "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97"
EXPECTED_FAILURES = {
    "E0": {"sql_parse_error": 4, "missing_column": 6},
    "E1": {"sql_parse_error": 2, "missing_column": 8},
    "E2": {"sql_parse_error": 4, "missing_column": 4},
}
ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
FORBIDDEN_NODE_NAMES = frozenset(
    "Insert Update Delete Create Drop Alter Merge Into Command Pragma Attach Detach "
    "Transaction Commit Rollback Grant Revoke Use Set Execute Analyze Vacuum Cache "
    "Uncache LoadData Copy TruncateTable Lock Unlock Kill Fetch Show Describe".split()
)
SAFE_FUNCTIONS = frozenset("""
abs avg ceil ceiling char coalesce concat concat_ws count cume_dist dense_rank
exp first_value floor format glob group_concat hex if ifnull iif instr json
json_array json_array_length json_error_position json_extract json_insert json_object
json_patch json_quote json_remove json_replace json_set json_type json_valid
json_group_array json_group_object lag last_value lead length like likelihood likely
ln log log10 log2 lower ltrim max min mod nth_value ntile nullif percent_rank pi
pow power printf quote rank replace round row_number rtrim sign sin cos tan asin acos
atan atan2 sinh cosh tanh asinh acosh atanh sqrt string_agg substr substring sum
total trim trunc typeof unhex unicode unlikely upper zeroblob date time datetime
julianday unixepoch strftime timediff cast extract
""".split())
TEMPORAL_FUNCTIONS = frozenset({"date", "time", "datetime", "julianday", "unixepoch", "strftime", "timediff"})
CLOCK_WORDS = frozenset({"now", "localtime", "utc", "subsec", "subsecond"})
SQLITE_PROGRESS_LIMIT = 100_000
SQLITE_EXPLAIN_SECONDS = 2.0
CPU_SECONDS_LIMIT = 300
RSS_BYTES_LIMIT = 4 * 1024 * 1024 * 1024


class StopRun(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_pickle(path: Path):
    with path.open("rb") as source:
        return pickle.load(source)


def safe_identifier_text(name: str, text: str) -> bool:
    if not name:
        return False
    return re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text, flags=re.IGNORECASE) is not None


def parse_failure_subtype(sql: str) -> str:
    value = sql.strip()
    if value.startswith("```") or value.casefold().startswith("sql:"):
        return "parse_format_issue"
    first = re.match(r"(?is)^([a-z_]+)", value)
    if not first or first.group(1).casefold() not in {"select", "with"}:
        return "parse_format_issue"
    quote = None
    escaped = False
    depth = 0
    for char in value:
        if quote:
            if char == quote and not escaped:
                quote = None
            if char == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return "parse_structure_issue"
    if quote or depth:
        return "parse_structure_issue"
    return "parse_structure_issue"


def validate_explainable_select(sql: str):
    try:
        trees = [tree for tree in sqlglot.parse(sql, read="sqlite") if tree is not None]
    except ParseError as exc:
        raise StopRun("frozen SQL failed static parse before EXPLAIN") from exc
    if len(trees) != 1 or not isinstance(trees[0], ALLOWED_ROOTS):
        raise StopRun("frozen SQL is not one read-only query")
    tree = trees[0]
    for node in tree.walk():
        if type(node).__name__ in FORBIDDEN_NODE_NAMES or isinstance(node, (exp.DDL, exp.DML)):
            raise StopRun("frozen SQL contains a non-read-only AST node")
        if isinstance(node, exp.Func):
            function = node.name.casefold() if isinstance(node, exp.Anonymous) else node.sql_name().casefold()
            if isinstance(node, exp.Anonymous) and function not in SAFE_FUNCTIONS:
                raise StopRun("frozen SQL contains an unapproved function")
            if function in {"current_date", "current_time", "current_timestamp", "current_datetime"}:
                raise StopRun("frozen SQL contains a clock expression")
            if function in TEMPORAL_FUNCTIONS:
                for argument in node.iter_expressions():
                    if isinstance(argument, exp.Literal):
                        if not argument.is_string:
                            continue
                        if argument.this.strip().casefold() in CLOCK_WORDS:
                            raise StopRun("frozen SQL contains a clock argument")
                    else:
                        raise StopRun("frozen SQL contains a dynamic temporal argument")
    return tree


def sqlite_authorizer(action, first, second, database, trigger):
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        name = (second or first or "").casefold()
        return sqlite3.SQLITE_OK if name in SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


def explain_missing_identifier(db_path: Path, sql: str):
    started = time.monotonic()
    validate_explainable_select(sql)
    uri = db_path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=0)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.set_authorizer(sqlite_authorizer)

        def progress():
            return int(time.monotonic() - started > SQLITE_EXPLAIN_SECONDS)

        connection.set_progress_handler(progress, 1000)
        previous_handler = signal.getsignal(signal.SIGALRM)

        def alarm_handler(signum, frame):
            raise TimeoutError("EXPLAIN compile budget exceeded")

        signal.signal(signal.SIGALRM, alarm_handler)
        signal.setitimer(signal.ITIMER_REAL, SQLITE_EXPLAIN_SECONDS)
        try:
            cursor = connection.execute("EXPLAIN " + sql)
            cursor.fetchone()
            cursor.close()
            return {"status": "prepared", "identifier": None}
        except TimeoutError:
            return {"status": "explain_timeout", "identifier": None}
        except sqlite3.Error as exc:
            message = str(exc)
            prefix = "no such column:"
            if prefix not in message.casefold():
                return {"status": "other_error", "identifier": None}
            raw = message[message.casefold().index(prefix) + len(prefix):].strip()
            parts = [part.strip().strip('"`[]') for part in raw.split(".")]
            if not parts or not parts[-1] or len(parts) > 2:
                return {"status": "identifier_unparsed", "identifier": None}
            return {
                "status": "missing_column",
                "qualifier": parts[-2].casefold() if len(parts) == 2 else None,
                "name": parts[-1].casefold(),
                "identifier": tuple(part.casefold() for part in parts),
            }
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
    finally:
        connection.close()


def schema_catalog(schema):
    table_names = [str(name) for name in schema["table_names_original"]]
    columns = []
    for index, (table_index, column_name) in enumerate(schema["column_names_original"]):
        if table_index >= 0 and column_name:
            columns.append({"index": index, "table_index": table_index, "name": str(column_name).casefold()})
    by_table_and_name = defaultdict(list)
    by_name = defaultdict(list)
    for column in columns:
        by_table_and_name[(column["table_index"], column["name"])].append(column)
        by_name[column["name"]].append(column)
    table_by_name = {name.casefold(): index for index, name in enumerate(table_names)}
    return table_names, columns, by_table_and_name, by_name, table_by_name


def selected_column_indices(case_arm, db_id):
    prefix = f"column:{db_id}:"
    selected = set()
    for node_id in case_arm["node_ids"]:
        if not isinstance(node_id, str) or not node_id.startswith(prefix):
            continue
        try:
            selected.add(int(node_id[len(prefix):]))
        except ValueError:
            continue
    return selected


def extract_context_text(case_arm):
    messages = case_arm.get("messages") or []
    if len(messages) < 2 or not isinstance(messages[1].get("content"), str):
        return None
    content = messages[1]["content"]
    match = re.search(r"Database schema context:\n(.*?)\n\nQuestion:", content, flags=re.DOTALL)
    return match.group(1) if match else None


def resolve_table_source(source, table_by_name):
    if not isinstance(source, exp.Table):
        return None
    name = source.name.casefold()
    return table_by_name.get(name)


def find_referenced_column(tree, qualifier, column_name, schema_tuple):
    table_names, _, by_table_and_name, by_name, table_by_name = schema_tuple
    matching = []
    for scope in traverse_scope(tree):
        scoped_columns = [column for column in scope.columns if column.name.casefold() == column_name]
        if not scoped_columns:
            continue
        selected = {name.casefold(): row for name, row in scope.selected_sources.items()}
        if qualifier:
            qualified_columns = [column for column in scoped_columns if column.table.casefold() == qualifier]
            if not qualified_columns:
                continue
            source_row = selected.get(qualifier)
            if source_row:
                _, source = source_row
                table_index = resolve_table_source(source, table_by_name)
                if table_index is None:
                    return {"status": "derived_scope", "column_index": None}
                matching.append((column_name, table_index))
            elif qualifier in table_by_name:
                matching.append((column_name, table_by_name[qualifier]))
            else:
                return {"status": "unknown_qualifier", "column_index": None}
        else:
            source_tables = []
            for _, source in selected.values():
                table_index = resolve_table_source(source, table_by_name)
                if table_index is not None:
                    source_tables.append(table_index)
            candidates = []
            for table_index in set(source_tables):
                candidates.extend(by_table_and_name.get((table_index, column_name), []))
            if len(candidates) == 1:
                return {"status": "resolved", "column_index": candidates[0]["index"]}
            if len(candidates) > 1:
                return {"status": "ambiguous", "column_index": None}
            if by_name.get(column_name):
                return {"status": "outside_query_sources", "column_index": None}
            return {"status": "absent_from_schema", "column_index": None}
    if len(matching) != 1:
        if len(matching) > 1:
            return {"status": "ambiguous", "column_index": None}
        if by_name.get(column_name):
            return {"status": "outside_query_sources", "column_index": None}
        return {"status": "absent_from_schema", "column_index": None}
    _, table_index = matching[0]
    candidates = by_table_and_name.get((table_index, column_name), [])
    if len(candidates) == 1:
        return {"status": "resolved", "column_index": candidates[0]["index"]}
    if by_name.get(column_name):
        return {"status": "wrong_qualifier", "column_index": None}
    return {"status": "absent_from_schema", "column_index": None}


def classify_missing_column(db_path, sql, case_arm, schema, db_id):
    explained = explain_missing_identifier(db_path, sql)
    if explained["status"] != "missing_column":
        return {"category": "explain_status_disagreement", "column_index": None}
    tree = validate_explainable_select(sql)
    schema_tuple = schema_catalog(schema)
    resolved = find_referenced_column(tree, explained.get("qualifier"), explained["name"], schema_tuple)
    if resolved["status"] == "absent_from_schema":
        return {"category": "column_not_in_schema", "column_index": None}
    if resolved["status"] == "wrong_qualifier":
        return {"category": "qualifier_or_scope_mismatch", "column_index": None}
    if resolved["status"] == "outside_query_sources":
        return {"category": "qualifier_or_scope_mismatch", "column_index": None}
    if resolved["status"] in {"ambiguous", "derived_scope", "unknown_qualifier"}:
        return {"category": "unresolved", "column_index": None}
    if resolved["status"] != "resolved":
        return {"category": "unresolved", "column_index": None}

    column_index = resolved["column_index"]
    selected = selected_column_indices(case_arm, db_id)
    context = extract_context_text(case_arm)
    if context is None:
        return {"category": "unresolved", "column_index": column_index}
    column_name = next(column["name"] for column in schema_tuple[1] if column["index"] == column_index)
    if column_index in selected:
        return {"category": "column_visible_but_reference_invalid", "column_index": column_index}
    if safe_identifier_text(column_name, context):
        return {"category": "column_visible_but_reference_invalid", "column_index": column_index}
    return {"category": "schema_column_omitted_from_context", "column_index": column_index}


def verify_source(expected_commit: str, expected_tree: str):
    root = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    if head != expected_commit or tree != expected_tree or dirty:
        raise StopRun("source commit/tree is not the clean registered source")
    return {"commit": head, "tree": tree}


def verify_private_inputs(prepared_root: Path, p2d_full_root: Path, p2d1_root: Path):
    prepare_seal_path = prepared_root / "prepare_seal_private.json"
    if sha256_file(prepare_seal_path) != EXPECTED_PREPARE_SEAL:
        raise StopRun("prepared seal mismatch")
    prepare_seal = read_json(prepare_seal_path)
    for relative, expected in prepare_seal["files"].items():
        source_path = (prepared_root / relative).resolve()
        if prepared_root.resolve() not in source_path.parents or sha256_file(source_path) != expected:
            raise StopRun("prepared source artifact hash mismatch")
    case_rows = []
    for item in prepare_seal["cases"]:
        case_path = (prepared_root / item["file"]).resolve()
        if prepared_root.resolve() not in case_path.parents or sha256_file(case_path) != item["sha256"]:
            raise StopRun("prepared case hash mismatch")
        if item.get("cohort") != "smoke":
            case_rows.append(read_json(case_path))
    if len(case_rows) != 30:
        raise StopRun("prepared case count mismatch")
    case_map = {row["case_id"]: row for row in case_rows}
    if len(case_map) != 30:
        raise StopRun("prepared case identities are not unique")

    predictions_path = p2d_full_root / "predictions_private.json"
    seal_path = p2d_full_root / "prediction_seal.json"
    if sha256_file(predictions_path) != EXPECTED_PREDICTIONS:
        raise StopRun("frozen predictions hash mismatch")
    if sha256_file(seal_path) != EXPECTED_PREDICTION_SEAL_FILE:
        raise StopRun("frozen prediction seal file hash mismatch")
    prediction_seal = read_json(seal_path)
    if prediction_seal.get("predictions_sha256") != EXPECTED_PREDICTIONS or prediction_seal.get("rows") != 90:
        raise StopRun("frozen prediction seal mismatch")
    predictions = read_json(predictions_path)
    prediction_map = {(row["case_id"], row["arm"]): row for row in predictions}
    if len(prediction_map) != 90 or set(case_map) != {case_id for case_id, _ in prediction_map}:
        raise StopRun("frozen prediction count/identity mismatch")

    outcomes_path = p2d1_root / "gate2" / "private_case_outcomes.json"
    if sha256_file(outcomes_path) != EXPECTED_P2D1_OUTCOMES:
        raise StopRun("P2d.1 private outcomes hash mismatch")
    outcomes = read_json(outcomes_path)
    outcome_map = {(row["case_id"], row["arm"]): row for row in outcomes}
    if len(outcome_map) != 90 or set(outcome_map) != set(prediction_map):
        raise StopRun("P2d.1 outcome count/identity mismatch")

    failures = defaultdict(Counter)
    for row in outcomes:
        status = row["v2_prediction_status"]
        if status == "ok":
            continue
        if row.get("v2_prediction_error_type") == "sql_parse_error":
            failures[row["arm"]]["sql_parse_error"] += 1
        elif row.get("v2_prediction_error_category") == "missing_column":
            failures[row["arm"]]["missing_column"] += 1
        else:
            failures[row["arm"]][row.get("v2_prediction_error_category") or row.get("v2_prediction_error_type") or "other"] += 1
    if {arm: dict(failures[arm]) for arm in ARMS} != EXPECTED_FAILURES:
        raise StopRun("frozen failure categories no longer match preregistration")

    evaluation = read_json(prepared_root / "evaluation_private.json")
    sources = read_json(prepared_root / "sources_private.json")
    schema_info = sources["inputs"]["schema_json"]
    schema_path = Path(schema_info["path"])
    if schema_info["sha256"] != EXPECTED_SCHEMA or sha256_file(schema_path) != EXPECTED_SCHEMA:
        raise StopRun("schema source hash mismatch")
    schema_rows = read_json(schema_path)
    schema_map = {row["db_id"]: row for row in schema_rows}
    database_manifest = sources["databases"]
    before_hashes = {}
    for db_id, info in database_manifest.items():
        path = Path(info["path"])
        if sha256_file(path) != info["sha256"]:
            raise StopRun("database snapshot hash mismatch")
        before_hashes[db_id] = info["sha256"]
    return case_map, prediction_map, outcome_map, evaluation, schema_map, database_manifest, before_hashes


def database_id_from_case(case, evaluation, schema_map):
    alias = case.get("database_alias")
    # The private evaluation map resolves the file path; only the basename is used in memory.
    case_id = case["case_id"]
    db_id = Path(evaluation[case_id]["database_path"]).stem
    if db_id not in schema_map:
        raise StopRun("database/schema mapping failed")
    expected_alias = None
    sorted_ids = sorted(schema_map)
    for index, candidate in enumerate(sorted_ids, 1):
        if candidate == db_id:
            expected_alias = f"db_{index:02d}"
            break
    if alias != expected_alias:
        raise StopRun("database alias mapping mismatch")
    return db_id


def full_analysis(args):
    source = verify_source(args.expected_commit, args.expected_tree)
    case_map, prediction_map, outcome_map, evaluation, schema_map, database_manifest, before_hashes = verify_private_inputs(
        args.prepared_root, args.p2d_full_root, args.p2d1_root
    )
    output = args.output_root
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(output, 0o700)
    started_cpu = time.process_time()
    started_wall = time.monotonic()
    classifications = []
    detail_categories = Counter()
    missing_identifier_indices = {}
    for key, outcome in outcome_map.items():
        case_id, arm = key
        if outcome["v2_prediction_status"] == "ok":
            continue
        case = case_map[case_id]
        prediction = prediction_map[key]
        if outcome.get("v2_prediction_error_type") == "sql_parse_error":
            category = parse_failure_subtype(prediction["sql"])
            classification = {"category": category, "column_index": None}
        elif outcome.get("v2_prediction_error_category") == "missing_column":
            db_id = database_id_from_case(case, evaluation, schema_map)
            db_path = Path(evaluation[case_id]["database_path"])
            classification = classify_missing_column(
                db_path, prediction["sql"], case["arms"][arm], schema_map[db_id], db_id
            )
            category = classification["category"]
            if classification.get("column_index") is not None:
                missing_identifier_indices[key] = classification["column_index"]
        else:
            category = "unresolved"
            classification = {"category": category, "column_index": None}
        detail_categories[arm + ":" + category] += 1
        classifications.append({"key": key, **classification})

    if len(classifications) != 28:
        raise StopRun("failure analysis denominator mismatch")
    after_hashes = {
        db_id: sha256_file(Path(info["path"])) for db_id, info in database_manifest.items()
    }
    if after_hashes != before_hashes:
        raise StopRun("database snapshot changed during analysis")

    category_counts = Counter(row["category"] for row in classifications)
    high_confidence = sum(category_counts[name] for name in (
        "schema_column_omitted_from_context", "column_visible_but_reference_invalid",
        "column_not_in_schema", "qualifier_or_scope_mismatch", "parse_format_issue", "parse_structure_issue"
    ))
    context_omission_keys = {tuple(row["key"]) for row in classifications if row["category"] == "schema_column_omitted_from_context"}
    cross_arm_visibility_pairs = 0
    cross_arm_visibility_cases = set()
    cross_arm_visibility_executable = 0
    for key in context_omission_keys:
        case_id, failing_arm = key
        column_index = missing_identifier_indices.get(key)
        if column_index is None:
            continue
        for other_arm in ARMS:
            if other_arm == failing_arm:
                continue
            other_case_arm = case_map[case_id]["arms"][other_arm]
            db_id = database_id_from_case(case_map[case_id], evaluation, schema_map)
            if column_index in selected_column_indices(other_case_arm, db_id):
                cross_arm_visibility_pairs += 1
                cross_arm_visibility_cases.add(case_id)
                if outcome_map[(case_id, other_arm)]["v2_prediction_status"] == "ok":
                    cross_arm_visibility_executable += 1

    missing_column_total = sum(EXPECTED_FAILURES[arm]["missing_column"] for arm in ARMS)
    generation_side = sum(category_counts[name] for name in (
        "column_visible_but_reference_invalid", "column_not_in_schema", "qualifier_or_scope_mismatch"
    ))
    if high_confidence < 23:
        decision = "INCONCLUSIVE_LOW_CLASSIFICATION_COVERAGE"
    elif category_counts["schema_column_omitted_from_context"] >= 9 and len(cross_arm_visibility_cases) >= 4:
        decision = "VISIBILITY_CANDIDATE_FOR_FRESH_FROZEN_SAMPLE"
    elif generation_side >= 9:
        decision = "GENERATION_VALIDITY_CANDIDATE_FOR_FRESH_FROZEN_SAMPLE"
    else:
        decision = "NO_SINGLE_ROOT_CAUSE_GATE_MET_STOP_ON_CURRENT_SAMPLE"

    elapsed_cpu = time.process_time() - started_cpu
    elapsed_wall = time.monotonic() - started_wall
    rss_unit = 1024 if sys.platform.startswith("linux") else 1
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * rss_unit
    if elapsed_cpu > CPU_SECONDS_LIMIT or peak_rss > RSS_BYTES_LIMIT:
        raise StopRun("analysis resource budget exceeded")
    result = {
        "experiment_id": "p2d2_frozen_failure_attribution_20261105_01",
        "status": "COMPLETED",
        "denominators": {"cases": 30, "arms": 3, "predictions": 90, "failures": len(classifications), "missing_column": missing_column_total},
        "failure_categories": dict(sorted(category_counts.items())),
        "failure_categories_by_arm": {
            arm: dict(sorted((name.split(":", 1)[1], count) for name, count in detail_categories.items() if name.startswith(arm + ":")))
            for arm in ARMS
        },
        "context_visibility_cross_arm": {
            "distinct_cases_with_same_missing_column_visible_in_other_arm": len(cross_arm_visibility_cases),
            "failure_to_other_arm_visibility_pairs": cross_arm_visibility_pairs,
            "pairs_where_other_arm_prediction_was_executable": cross_arm_visibility_executable
        },
        "high_confidence_classifications": high_confidence,
        "next_step_decision": decision,
        "interpretation_limits": [
            "BIRD dev is a repeatedly used diagnostic subset, not an independent test set.",
            "Context omission is a structural diagnosis, not proof that omission caused the SQL failure.",
            "Other-arm node visibility is a paired association, not a causal retrieval effect.",
            "SQLite EXPLAIN compiled only the 18 already failed queries; no SELECT rows were evaluated."
        ],
        "source": source,
        "inputs_sha256": {
            "predictions": EXPECTED_PREDICTIONS,
            "prediction_seal_file": EXPECTED_PREDICTION_SEAL_FILE,
            "p2d1_private_outcomes": EXPECTED_P2D1_OUTCOMES,
            "schema": EXPECTED_SCHEMA,
            "database_snapshots_unchanged": True
        },
        "runtime": {
            "python": sys.version.split()[0],
            "sqlglot": importlib.metadata.version("sqlglot"),
            "sqlite": sqlite3.sqlite_version,
            "process_cpu_seconds": round(elapsed_cpu, 6),
            "elapsed_wall_seconds": round(elapsed_wall, 6),
            "peak_rss_bytes": peak_rss,
            "model_calls": 0,
            "api_calls": 0,
            "gpu_seconds": 0,
            "select_queries_executed": 0,
            "readonly_explain_compiles": 18
        }
    }
    result_path = output / "aggregate.json"
    with result_path.open("x", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
    receipt = {
        "status": "COMPLETED",
        "aggregate_sha256": sha256_file(result_path),
        "source_commit": source["commit"],
        "source_tree": source["tree"],
        "input_hashes_verified": True,
        "database_hashes_unchanged": True,
        "private_rows_or_identifiers_written": False
    }
    with (output / "receipt.json").open("x", encoding="utf-8") as target:
        json.dump(receipt, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def self_check():
    checks = 0
    assert parse_failure_subtype("```sql\nSELECT (1\n```") == "parse_format_issue"
    checks += 1
    assert parse_failure_subtype("Answer: SELECT 1") == "parse_format_issue"
    checks += 1
    assert parse_failure_subtype("SELECT (1") == "parse_structure_issue"
    checks += 1

    synthetic_schema = {
        "db_id": "demo",
        "table_names_original": ["alpha", "beta"],
        "column_names_original": [[-1, "*"], [0, "known"], [0, "secret"], [1, "known"]]
    }
    arm = {
        "node_ids": ["table:demo:0", "column:demo:1"],
        "messages": [{"role": "system", "content": ""}, {
            "role": "user", "content": "Database schema context:\nTable alpha; Column alpha.known\n\nQuestion:\n"}],
    }
    tree = validate_explainable_select("SELECT a.secret FROM alpha AS a")
    schema_tuple = schema_catalog(synthetic_schema)
    ref = find_referenced_column(tree, "a", "secret", schema_tuple)
    assert ref == {"status": "resolved", "column_index": 2}
    checks += 1
    tree = validate_explainable_select("SELECT b.secret FROM beta AS b")
    mismatch = find_referenced_column(tree, "b", "secret", schema_tuple)
    assert mismatch["status"] == "wrong_qualifier"
    checks += 1
    tree = validate_explainable_select("SELECT a.made_up FROM alpha AS a")
    absent = find_referenced_column(tree, "a", "made_up", schema_tuple)
    assert absent["status"] == "absent_from_schema"
    checks += 1
    for unsafe_sql in (
        "SELECT current_date",
        "SELECT datetime('now')",
        "SELECT load_extension('x')",
    ):
        try:
            validate_explainable_select(unsafe_sql)
        except StopRun:
            checks += 1
        else:
            raise AssertionError("read-only SQL guard accepted an unsafe fixture")
    with tempfile.TemporaryDirectory(prefix="p2d2_smoke_") as directory:
        database = Path(directory) / "synthetic.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE alpha (known TEXT)")
        connection.commit()
        connection.close()
        explained = explain_missing_identifier(database, "SELECT a.secret FROM alpha AS a")
        assert explained["status"] == "missing_column" and explained["name"] == "secret"
    checks += 1
    print(json.dumps({"status": "PASS", "synthetic_checks": checks, "private_inputs_read": 0, "select_rows_read": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-tree")
    parser.add_argument("--prepared-root", type=Path)
    parser.add_argument("--p2d-full-root", type=Path)
    parser.add_argument("--p2d1-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    required = (args.expected_commit, args.expected_tree, args.prepared_root, args.p2d_full_root, args.p2d1_root, args.output_root)
    if any(value is None for value in required):
        raise StopRun("required argument missing")
    full_analysis(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "STOP", "error_type": type(error).__name__}))
        sys.exit(2)
