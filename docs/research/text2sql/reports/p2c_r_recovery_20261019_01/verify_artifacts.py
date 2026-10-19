"""Independently verify persisted P2c-R rows, metrics, CI, gate and privacy."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--p2b-run-dir", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

def read(path):
    return json.loads(path.read_text())

def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()

def close(left, right):
    assert np.isclose(left, right, atol=1e-12, rtol=0), "Persisted metric differs"

aggregate = read(args.run_dir / "aggregate_summary.json")
receipt = read(args.run_dir / "run_start.json")
old_receipt = read(args.p2b_run_dir / "run_start.json")
old_aggregate = read(args.p2b_run_dir / "aggregate_summary.json")
assert receipt["state"] == "completed" and receipt["stage_result"] == "full_passed"
assert digest(args.run_dir / "aggregate_summary.json") == receipt["aggregate_summary_sha256"]
assert digest(args.run_dir / "per_question_private.jsonl") == receipt["private_per_question_sha256"]
assert aggregate["source_commit"] == receipt["source"]["published_commit"]

arms = ("V00", "V01", "V10", "V11")
stats = defaultdict(lambda: {arm: defaultdict(float) for arm in arms})
questions_by_db, eligible_by_db, deltas_by_db = defaultdict(int), defaultdict(int), defaultdict(int)
total, eligible, invariant_checks, archived_row_checks = 0, 0, 0, 0
rescued_by_db, damaged_by_db = defaultdict(int), defaultdict(int)
with (args.run_dir / "per_question_private.jsonl").open() as current, (args.p2b_run_dir / "per_question_private.jsonl").open() as archived:
    for line in current:
        row = json.loads(line)
        previous_line = next(archived, None)
        assert previous_line is not None, "Archive has fewer rows"
        previous = json.loads(previous_line)
        assert (row["question_id"], row["db_id"], row["column_eligible"]) == (
            previous["question_id"], previous["db_id"], previous["column_eligible"])
        total += 1
        db = row["db_id"]
        questions_by_db[db] += 1
        for left, right in (("V00", "V01"), ("V10", "V11")):
            for field in ("table_topk_ids", "column_topk_ids", "score_matrix_digest"):
                assert row["arms"][left][field] == row["arms"][right][field], "Context-only ranking/score changed"
                invariant_checks += 1
        for arm, variant in (("V00", "R0_local_cpu_pass1"), ("V11", "R1_local_cpu_without_values")):
            for field in ("column_topk_ids", "budgets"):
                assert row["arms"][arm][field] == previous["variants"][variant][field], "Archived row replay differs"
            archived_row_checks += 1
        if not row["column_eligible"]:
            continue
        eligible += 1
        eligible_by_db[db] += 1
        a = int(row["arms"]["V00"]["budgets"]["1024"]["complete"])
        b = int(row["arms"]["V01"]["budgets"]["1024"]["complete"])
        deltas_by_db[db] += b - a
        rescued_by_db[db] += int(a == 0 and b == 1)
        damaged_by_db[db] += int(a == 1 and b == 0)
        for arm in arms:
            value = row["arms"][arm]
            for k in ("5", "10", "20"):
                stats[db][arm]["column_" + k] += float(value["column_recall"][k])
            for budget in ("512", "1024", "2048"):
                for field in ("complete", "recall", "tokens_used", "returned_elements"):
                    number = value["budgets"][budget][field]
                    assert np.isfinite(number)
                    stats[db][arm][budget + "/" + field] += number
    assert next(archived, None) is None, "Archive has extra rows"

assert (total, eligible, len(questions_by_db)) == (1534, 1460, 11)
aliases = {db: f"db_{index:02d}" for index, db in enumerate(sorted(questions_by_db), 1)}
fixed_aliases = set(old_receipt["frozen_non_saturated_db_aliases"])
fixed = {db for db, alias in aliases.items() if alias in fixed_aliases}
assert len(fixed) == 5 and sum(eligible_by_db[db] for db in fixed) == 706
metric_checks = 0
for group, dbs in (("all", list(questions_by_db)), ("fixed_non_saturated", fixed)):
    count = sum(eligible_by_db[db] for db in dbs)
    for arm in arms:
        summary = aggregate["arms"][arm]["metrics"][group]
        assert summary["denominators"]["column_eligible_questions"] == count
        assert summary["denominators"]["table_questions"] == sum(questions_by_db[db] for db in dbs)
        for k in ("5", "10", "20"):
            close(sum(stats[db][arm]["column_" + k] for db in dbs) / count, summary["column_recall_query_macro"][k])
            metric_checks += 1
        for budget in ("512", "1024", "2048"):
            for private, public in (("complete", "complete_query_macro"), ("recall", "gold_schema_recall_query_macro"),
                                    ("tokens_used", "mean_returned_tokens"), ("returned_elements", "mean_returned_elements")):
                close(sum(stats[db][arm][budget + "/" + private] for db in dbs) / count, summary["budgets"][budget][public])
                metric_checks += 1
    primary = aggregate["primary_gate"][group]
    ids = sorted(dbs)
    sums = np.array([deltas_by_db[db] for db in ids], dtype=float)
    counts = np.array([eligible_by_db[db] for db in ids], dtype=float)
    samples = np.random.default_rng(20261020).integers(0, len(ids), size=(10000, len(ids)))
    interval = np.quantile(sums[samples].sum(axis=1) / counts[samples].sum(axis=1), [0.025, 0.975]) * 100
    close(sums.sum() / counts.sum() * 100, primary["delta_pp"])
    for left, right in zip(interval, primary["database_cluster_bootstrap_95_ci_pp"]):
        close(left, right)
    paired = aggregate["paired_rescue_damage"]["V01_minus_V00"][group]["complete_1024"]
    assert paired["rescued"] == sum(rescued_by_db[db] for db in ids)
    assert paired["damaged"] == sum(damaged_by_db[db] for db in ids)

archive_metric_checks = 0
for arm, variant in (("V00", "R0_local_cpu_pass_1"), ("V11", "R1_local_cpu_without_values")):
    for group in ("all", "fixed_non_saturated"):
        previous = old_aggregate["conditions"][variant][group]
        actual = aggregate["arms"][arm]["metrics"][group]
        for k in ("5", "10", "20"):
            close(previous[f"column_r{k}_query_macro"], actual["column_recall_query_macro"][k])
            archive_metric_checks += 1
        for budget in ("512", "1024", "2048"):
            for flat, nested in (("complete_query_macro", "complete_query_macro"),
                                 ("budget_recall_query_macro", "gold_schema_recall_query_macro"),
                                 ("mean_tokens_used", "mean_returned_tokens")):
                close(previous[flat][budget], actual["budgets"][budget][nested])
                archive_metric_checks += 1

positive = sum(deltas_by_db[db] > 0 for db in fixed)
nonnegative = sum(deltas_by_db[db] >= 0 for db in fixed)
gate = aggregate["primary_gate"]
expected_gate = gate["all"]["delta_pp"] >= 5 and gate["fixed_non_saturated"]["delta_pp"] >= 3 and positive >= 2 and nonnegative >= 3
expected_gate &= all(gate[group]["database_cluster_bootstrap_95_ci_pp"][0] > 0 for group in ("all", "fixed_non_saturated"))
assert gate["success"] == bool(expected_gate)
assert positive == gate["positive_fixed_databases"] and nonnegative == gate["nonnegative_fixed_databases"]

serialized = json.dumps(aggregate, ensure_ascii=False)
assert all(db not in serialized for db in questions_by_db), "Public artifact contains a database name"
def privacy_keys(obj):
    if isinstance(obj, dict):
        assert not {"question_id", "db_id", "selected_ids", "sql", "prompt", "query_vectors"}.intersection(obj)
        for value in obj.values():
            privacy_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            privacy_keys(value)
privacy_keys(aggregate)
output = {"status": "verified", "questions": total, "eligible_questions": eligible,
          "fixed_eligible_questions": 706, "ranking_and_score_invariant_checks": invariant_checks,
          "archived_row_replays": archived_row_checks, "independent_metric_checks": metric_checks,
          "archived_aggregate_metric_checks": archive_metric_checks, "bootstrap_intervals_recomputed": 2,
          "primary_gate_recomputed": True, "privacy_scan": "passed", "primary_success": bool(expected_gate),
          "aggregate_sha256": receipt["aggregate_summary_sha256"], "private_rows_sha256": receipt["private_per_question_sha256"],
          "source_commit": receipt["source"]["published_commit"], "verification_tolerance": "atol=1e-12, rtol=0 (independent sum order)"}
args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(output))
