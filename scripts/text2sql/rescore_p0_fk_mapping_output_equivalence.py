#!/usr/bin/env python3
"""Rescore frozen SQL-used mapping rankings under a static-instance Bag label."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


EXPERIMENT_ID = "p0_fk_mapping_output_equivalence_rescore_20261107_01"
METHODS = ("g_reasoner", "dense_cosine", "bm25_okapi", "stable_mapping_id_order")
PRIMARY_METHODS = ("g_reasoner", "dense_cosine")
SMOKE_PREFIX = "p0-output-equivalence-smoke-v1:"


class StopRun(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise StopRun(code)


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - do not leak private input content.
        raise StopRun(f"JSON_READ_{type(error).__name__}") from None


def git_commit(repo_root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception as error:  # noqa: BLE001
        raise StopRun(f"GIT_COMMIT_{type(error).__name__}") from None


def load_predictions(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                require(isinstance(row, dict), f"PREDICTION_ROW_NOT_OBJECT_{line_number}")
                rows.append(row)
    except StopRun:
        raise
    except Exception as error:  # noqa: BLE001 - do not leak private input content.
        raise StopRun(f"PREDICTIONS_READ_{type(error).__name__}") from None
    return rows


def candidate_hash(mapping_id: str) -> str:
    return stable_hash(mapping_id)[:20]


def summarize(rows: list[dict[str, Any]], mode: str, input_hashes: dict[str, str],
              config_hash: str, commit: str, run_id: str, elapsed: float,
              max_rss_gib: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    unit_metrics = {row["unit_hash"]: row for row in rows}
    anonymous_dbs = sorted({row["anonymous_db"] for row in rows})

    methods: dict[str, dict[str, Any]] = {}
    paired: dict[str, dict[str, Any]] = {}
    for method in METHODS:
        exact_hits = sum(row["target_only_hits"][method] for row in rows)
        equiv_hits = sum(row["instance_output_equivalent_hits"][method] for row in rows)
        methods[method] = {
            "n": len(rows),
            "target_only_mapping_at_1": {"hits": exact_hits, "rate": exact_hits / len(rows)},
            "instance_output_equivalent_at_1": {"hits": equiv_hits, "rate": equiv_hits / len(rows)},
            "newly_accepted_by_instance_equivalence": equiv_hits - exact_hits,
        }

    for label in ("target_only_hits", "instance_output_equivalent_hits"):
        both = g_only = dense_only = neither = 0
        for row in rows:
            g_hit = bool(row[label][PRIMARY_METHODS[0]])
            dense_hit = bool(row[label][PRIMARY_METHODS[1]])
            if g_hit and dense_hit:
                both += 1
            elif g_hit:
                g_only += 1
            elif dense_hit:
                dense_only += 1
            else:
                neither += 1
        paired[label] = {
            "both_correct": both,
            "g_reasoner_only": g_only,
            "dense_only": dense_only,
            "both_wrong": neither,
            "net_g_reasoner_minus_dense": g_only - dense_only,
        }

    target_gap = 100 * (
        methods["g_reasoner"]["target_only_mapping_at_1"]["rate"]
        - methods["dense_cosine"]["target_only_mapping_at_1"]["rate"]
    )
    equivalent_gap = 100 * (
        methods["g_reasoner"]["instance_output_equivalent_at_1"]["rate"]
        - methods["dense_cosine"]["instance_output_equivalent_at_1"]["rate"]
    )
    gap_shift = equivalent_gap - target_gap

    by_db: dict[str, Any] = {}
    for db in anonymous_dbs:
        db_rows = [row for row in rows if row["anonymous_db"] == db]
        db_methods: dict[str, Any] = {}
        for method in METHODS:
            exact_hits = sum(row["target_only_hits"][method] for row in db_rows)
            equiv_hits = sum(row["instance_output_equivalent_hits"][method] for row in db_rows)
            db_methods[method] = {
                "n": len(db_rows),
                "target_only_mapping_at_1": {"hits": exact_hits, "rate": exact_hits / len(db_rows)},
                "instance_output_equivalent_at_1": {"hits": equiv_hits, "rate": equiv_hits / len(db_rows)},
                "newly_accepted_by_instance_equivalence": equiv_hits - exact_hits,
            }
        by_db[db] = db_methods

    if mode == "smoke":
        sensitivity = "SMOKE_ONLY_NOT_INTERPRETED"
    elif gap_shift >= 5.0:
        sensitivity = "MATERIAL_SENSITIVITY_SUPPORTED"
    elif equivalent_gap < 0:
        sensitivity = "NEGATIVE_GAP_NOT_MATERIALLY_CHANGED"
    else:
        sensitivity = "DIRECTION_CHANGED_WITHOUT_5PP_SHIFT"

    aggregate = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "mode": mode,
        "status": "SMOKE_PASS" if mode == "smoke" else "FULL_COMPLETE",
        "interpretation": sensitivity,
        "analysis_type": "exploratory_frozen_output_rescoring",
        "input_sha256": input_hashes,
        "config_sha256": config_hash,
        "source_commit": commit,
        "n": len(rows),
        "anonymous_databases": anonymous_dbs,
        "methods": methods,
        "paired_g_reasoner_vs_dense": paired,
        "primary_gap_pp": {
            "target_only_g_minus_dense": target_gap,
            "instance_output_equivalent_g_minus_dense": equivalent_gap,
            "gap_shift_pp": gap_shift,
            "pre_registered_material_sensitivity_threshold_pp": 5.0,
        },
        "by_anonymous_database": by_db,
        "resources": {
            "backend": "cpu",
            "wall_seconds": elapsed,
            "peak_rss_gib": max_rss_gib,
            "model_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "external_api_requests": 0,
            "external_api_cost_cny": "0.00",
            "gpu_seconds": 0,
            "sql_executions": 0,
        },
        "interpretation_limit": (
            "A matching output Bag on one frozen SQLite instance is not proof of SQL semantic equivalence, "
            "business-role correctness, user-intent correctness, human review consensus, or GFM ranking quality."
        ),
        "privacy": "No question, SQL, real database name, pair ID, mapping ID, or row-level result is included.",
    }
    return aggregate, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--private-predictions", type=Path, required=True)
    parser.add_argument("--instance-equivalence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    started = time.monotonic()
    require(args.run_id.startswith(EXPERIMENT_ID.replace("_01", "")), "RUN_ID_MISMATCH")
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")
    commit = git_commit(args.repo_root)
    require(commit == args.expected_commit, "SOURCE_COMMIT_MISMATCH")

    config = read_json(args.config)
    input_paths = {
        "prepared_manifest_sha256": args.prepared_manifest,
        "private_predictions_sha256": args.private_predictions,
        "instance_equivalence_sha256": args.instance_equivalence,
    }
    input_hashes = {key: sha256_file(path) for key, path in input_paths.items()}
    for key, actual in input_hashes.items():
        require(actual == config["expected_inputs"][key], f"INPUT_HASH_MISMATCH_{key}")
    config_hash = sha256_file(args.config)

    manifest = read_json(args.prepared_manifest)
    equivalence = read_json(args.instance_equivalence)
    predictions = load_predictions(args.private_predictions)
    require(isinstance(manifest.get("units"), dict), "MANIFEST_UNITS_INVALID")
    require(isinstance(equivalence.get("units"), list), "EQUIVALENCE_UNITS_INVALID")
    require(isinstance(equivalence.get("candidates"), list), "EQUIVALENCE_CANDIDATES_INVALID")

    full_ids = [str(value) for value in manifest.get("full_unit_ids", [])]
    require(len(full_ids) == 108 and len(set(full_ids)) == len(full_ids), "MANIFEST_FULL_IDS_INVALID")
    full_id_set = set(full_ids)
    require(full_id_set <= set(manifest["units"]), "MANIFEST_UNIT_MISSING")

    unit_hash_to_unit: dict[str, dict[str, Any]] = {}
    pair_id_to_unit: dict[str, dict[str, Any]] = {}
    for unit_id in full_ids:
        unit = manifest["units"][unit_id]
        require(str(unit.get("unit_id", "")) == unit_id, "MANIFEST_UNIT_ID_KEY_MISMATCH")
        unit_hash = stable_hash(unit_id)[:20]
        pair_id = str(unit.get("review_pair_id", ""))
        require(bool(pair_id), "MANIFEST_PAIR_ID_MISSING")
        require(unit_hash not in unit_hash_to_unit, "UNIT_HASH_COLLISION")
        require(pair_id not in pair_id_to_unit, "PAIR_ID_COLLISION")
        unit_hash_to_unit[unit_hash] = unit
        pair_id_to_unit[pair_id] = unit

    summary_by_hash: dict[str, dict[str, Any]] = {}
    for row in equivalence["units"]:
        unit_hash = str(row.get("unit_hash", ""))
        require(unit_hash and unit_hash not in summary_by_hash, "EQUIVALENCE_UNIT_HASH_DUPLICATE")
        summary_by_hash[unit_hash] = row
    require(set(summary_by_hash) == set(unit_hash_to_unit), "UNIT_HASH_COVERAGE_MISMATCH")

    comparisons_by_hash: dict[str, dict[str, Any]] = {}
    for record in equivalence["candidates"]:
        if not record.get("candidate_comparisons"):
            continue
        unit_hash = str(record.get("unit_hash", ""))
        require(unit_hash and unit_hash not in comparisons_by_hash, "CANDIDATE_RECORD_DUPLICATE")
        comparisons_by_hash[unit_hash] = record

    predictions_by_pair: dict[str, dict[str, Any]] = {}
    for row in predictions:
        pair_id = str(row.get("pair_id", ""))
        require(pair_id and pair_id not in predictions_by_pair, "PREDICTION_PAIR_DUPLICATE")
        predictions_by_pair[pair_id] = row
    require(set(predictions_by_pair) == set(pair_id_to_unit), "PREDICTION_PAIR_COVERAGE_MISMATCH")

    eligible: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for unit_hash, summary in summary_by_hash.items():
        status_counts[str(summary.get("status", "missing"))] += 1
        if summary.get("status") != "complete" or summary.get("gold_answer_empty") is not False:
            continue
        require(unit_hash in comparisons_by_hash, "ELIGIBLE_CANDIDATE_COMPARISONS_MISSING")
        unit = unit_hash_to_unit[unit_hash]
        pair_id = str(unit["review_pair_id"])
        prediction = predictions_by_pair[pair_id]
        candidate_rows = summary_candidate_rows(comparisons_by_hash[unit_hash])
        mapping_id_to_hash = {
            str(candidate["mapping_id"]): candidate_hash(str(candidate["mapping_id"]))
            for candidate in unit.get("candidate_mappings", [])
        }
        require(mapping_id_to_hash and len(mapping_id_to_hash) == len(unit.get("candidate_mappings", [])), "MANIFEST_MAPPING_IDS_INVALID")
        if len(set(mapping_id_to_hash.values())) != len(mapping_id_to_hash):
            raise StopRun("CANDIDATE_HASH_COLLISION")
        hash_to_mapping_id = {value: key for key, value in mapping_id_to_hash.items()}
        require(set(hash_to_mapping_id) == set(candidate_rows), "EQUIVALENCE_CANDIDATE_SET_MISMATCH")
        require(set(str(value) for value in prediction.get("candidate_mapping_ids", [])) == set(mapping_id_to_hash), "RANK_CANDIDATE_SET_MISMATCH")

        target_rows = [row for row in candidate_rows.values() if row.get("is_target") is True]
        require(len(target_rows) == 1, "TARGET_CANDIDATE_NOT_SINGLETON")
        target_hash = str(target_rows[0]["candidate_hash"])
        target_id = hash_to_mapping_id[target_hash]
        sql_used_ids = [str(value) for value in unit.get("sql_used_mapping_ids", [])]
        require(len(sql_used_ids) == 1 and target_id == sql_used_ids[0], "SQL_USED_TARGET_MISMATCH")
        require(target_rows[0].get("status") == "ok" and target_rows[0].get("bag_equal") is True, "TARGET_BAG_REPLAY_INVALID")

        accepted_ids = {target_id}
        for digest, row in candidate_rows.items():
            if row.get("status") == "ok" and row.get("bag_equal") is True:
                accepted_ids.add(hash_to_mapping_id[digest])

        ranked = prediction.get("ranked_mapping_ids", {})
        top_ids: dict[str, str] = {}
        for method in METHODS:
            ranking = [str(value) for value in ranked.get(method, [])]
            require(len(ranking) == len(mapping_id_to_hash) and set(ranking) == set(mapping_id_to_hash), f"RANK_ORDER_INVALID_{method}")
            top_ids[method] = ranking[0]

        eligible.append({
            "unit_hash": unit_hash,
            "anonymous_db": str(summary.get("anonymous_db", "")),
            "target_only_hits": {method: top_ids[method] == target_id for method in METHODS},
            "instance_output_equivalent_hits": {method: top_ids[method] in accepted_ids for method in METHODS},
            "expanded_acceptance_size": len(accepted_ids),
            "candidate_count": len(mapping_id_to_hash),
        })

    require(len(eligible) == 94, "ELIGIBLE_UNIT_COUNT_MISMATCH")
    eligible.sort(key=lambda row: hashlib.sha256((SMOKE_PREFIX + row["unit_hash"]).encode("utf-8")).hexdigest())
    smoke_rows = eligible[:5]
    full_rows = eligible[5:]
    require(len(smoke_rows) == 5 and len(full_rows) == 89, "SMOKE_FULL_SPLIT_INVALID")
    chosen = smoke_rows if args.mode == "smoke" else full_rows
    elapsed = time.monotonic() - started
    max_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    require(elapsed <= 120, "WALL_TIME_BUDGET_EXCEEDED")
    require(max_rss_gib <= 2.0, "RSS_BUDGET_EXCEEDED")

    aggregate, private_rows = summarize(
        chosen,
        args.mode,
        input_hashes,
        config_hash,
        commit,
        args.run_id,
        elapsed,
        max_rss_gib,
    )
    aggregate["eligibility_status_counts_all_108"] = dict(sorted(status_counts.items()))
    aggregate["eligible_complete_nonempty_units_before_split"] = len(eligible)
    aggregate["smoke_units_excluded_from_full"] = len(smoke_rows)

    args.output_dir.mkdir(parents=True, mode=0o700)
    args.output_dir.chmod(0o700)
    aggregate_path = args.output_dir / "aggregate_summary.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    aggregate_path.chmod(0o600)
    private_path = args.output_dir / "private_unit_scores.json"
    private_path.write_text(json.dumps(private_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    private_path.chmod(0o600)
    metadata = {
        "experiment_id": EXPERIMENT_ID,
        "run_id": args.run_id,
        "mode": args.mode,
        "status": aggregate["status"],
        "source_commit": commit,
        "config_sha256": config_hash,
        "input_sha256": input_hashes,
        "aggregate_sha256": sha256_file(aggregate_path),
        "private_unit_scores_sha256": sha256_file(private_path),
        "python": sys.version.split()[0],
        "wall_seconds": elapsed,
        "peak_rss_gib": max_rss_gib,
        "argv": sys.argv,
    }
    metadata_path = args.output_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata_path.chmod(0o600)
    print(json.dumps({
        "status": aggregate["status"],
        "mode": args.mode,
        "n": aggregate["n"],
        "eligible_before_split": len(eligible),
        "smoke_excluded_from_full": len(smoke_rows),
        "output_dir": str(args.output_dir),
        "wall_seconds": round(elapsed, 3),
        "peak_rss_gib": round(max_rss_gib, 3),
    }, sort_keys=True))
    return 0


def summary_candidate_rows(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in record.get("candidate_comparisons", []):
        digest = str(row.get("candidate_hash", ""))
        require(digest and digest not in result, "CANDIDATE_HASH_DUPLICATE")
        result[digest] = row
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StopRun as error:
        print(json.dumps({"status": "STOPPED", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
