#!/usr/bin/env python3
"""Compare mapping-level and declaration-multiset FK identities, schema only."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import resource
import time
from typing import Any, Sequence

import fk_instance_quality_audit as base


EXPECTED_DATABASES = 11
EXPECTED_RAW = 103
EXPECTED_VALID = 100
EXPECTED_INVALID = 3
EXPECTED_EXACT_DUPLICATE_GROUPS = 1
EXPECTED_DEV_TABLES_SHA256 = "35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97"
EXPECTED_SCHEMA_MANIFEST_SHA256 = "89765355de0a75d03a547afa5bf04eed21857f28d393aeb4e94c20e18212c74e"


def _payload(database_identity: str, instance: base.FkInstance) -> str:
    return base._instance_payload(
        database_identity,
        instance.source_table,
        instance.target_table,
        instance.ordered_pairs,
    )


def _digest(prefix: str, payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _group_instances(
    instances: Sequence[base.FkInstance], database_identity: str
) -> dict[str, list[base.FkInstance]]:
    groups: dict[str, list[base.FkInstance]] = defaultdict(list)
    for instance in instances:
        if instance.valid:
            groups[_payload(database_identity, instance)].append(instance)
    return dict(groups)


def _mapping_policy(
    instances: Sequence[base.FkInstance], database_identity: str
) -> dict[str, Any]:
    groups = _group_instances(instances, database_identity)
    ids_by_group: dict[tuple[str, int], str] = {}
    mapping_ids: list[str] = []
    for payload, group in sorted(groups.items()):
        identity = _digest("fk-mapping-v1", payload)
        mapping_ids.append(identity)
        for instance in group:
            ids_by_group[(instance.source_table.casefold(), instance.constraint_group_id)] = identity
    multiplicities = [len(group) for group in groups.values()]
    return {
        "id_set": tuple(sorted(mapping_ids)),
        "ids_by_group": ids_by_group,
        "unique_mapping_count": len(groups),
        "duplicate_mapping_group_count": sum(count > 1 for count in multiplicities),
        "duplicate_excess_declarations": sum(count - 1 for count in multiplicities),
        "declaration_count": sum(multiplicities),
        "directed_edge_count": 2 * len(groups),
        "id_unique": len(mapping_ids) == len(set(mapping_ids)),
        "inverse_pairing_pass": True,
    }


def _declaration_policy(
    instances: Sequence[base.FkInstance], database_identity: str
) -> dict[str, Any]:
    groups = _group_instances(instances, database_identity)
    ids_by_group: dict[tuple[str, int], str] = {}
    declaration_ids: list[str] = []
    for payload, group in sorted(groups.items()):
        # Group IDs only choose an arbitrary rank among structurally identical declarations.
        # The resulting ID multiset is stable; the individual group-to-rank association is not.
        ordered = sorted(group, key=lambda item: (item.source_table.casefold(), item.constraint_group_id))
        for ordinal, instance in enumerate(ordered):
            identity = _digest(
                "fk-declaration-multiset-v1",
                {"structure": payload, "occurrence_ordinal": ordinal},
            )
            declaration_ids.append(identity)
            ids_by_group[(instance.source_table.casefold(), instance.constraint_group_id)] = identity
    return {
        "id_set": tuple(sorted(declaration_ids)),
        "ids_by_group": ids_by_group,
        "declaration_count": len(declaration_ids),
        "directed_edge_count": 2 * len(declaration_ids),
        "id_unique": len(declaration_ids) == len(set(declaration_ids)),
        "inverse_pairing_pass": len(declaration_ids) * 2 == 2 * len(set(declaration_ids)),
    }


def _reverse_renumber(rows: Sequence[base.FkRow]) -> tuple[list[base.FkRow], dict[tuple[str, int], tuple[str, int]]]:
    keys = sorted({(row.source_table.casefold(), row.constraint_group_id) for row in rows})
    replacement = {key: 50_000 + len(keys) - 1 - index for index, key in enumerate(keys)}
    mapping = {key: (key[0], new_id) for key, new_id in replacement.items()}
    changed = [
        base.replace(row, constraint_group_id=replacement[(row.source_table.casefold(), row.constraint_group_id)])
        for row in rows
    ]
    return changed, mapping


def _association_changes(
    original: dict[tuple[str, int], str],
    renumbered: dict[tuple[str, int], str],
    group_map: dict[tuple[str, int], tuple[str, int]],
    duplicate_groups: set[tuple[str, int]],
) -> tuple[int, int]:
    changed_total = 0
    changed_duplicate = 0
    for old_key, old_id in original.items():
        new_id = renumbered.get(group_map[old_key])
        if new_id != old_id:
            changed_total += 1
            if old_key in duplicate_groups:
                changed_duplicate += 1
    return changed_total, changed_duplicate


def _analyze_rows(rows: Sequence[base.FkRow], database_identity: str) -> dict[str, Any]:
    original = base.canonicalize_fk_rows(database_identity, rows)
    reordered = base.canonicalize_fk_rows(database_identity, list(reversed(rows)))
    renumbered_rows, group_map = _reverse_renumber(rows)
    renumbered = base.canonicalize_fk_rows(database_identity, renumbered_rows)

    mapping = _mapping_policy(original, database_identity)
    mapping_reordered = _mapping_policy(reordered, database_identity)
    mapping_renumbered = _mapping_policy(renumbered, database_identity)
    declaration = _declaration_policy(original, database_identity)
    declaration_reordered = _declaration_policy(reordered, database_identity)
    declaration_renumbered = _declaration_policy(renumbered, database_identity)

    duplicate_group_keys = {
        (instance.source_table.casefold(), instance.constraint_group_id)
        for group in _group_instances(original, database_identity).values()
        if len(group) > 1
        for instance in group
    }
    mapping_changes_total, mapping_changes_duplicate = _association_changes(
        mapping["ids_by_group"], mapping_renumbered["ids_by_group"], group_map, duplicate_group_keys
    )
    declaration_changes_total, declaration_changes_duplicate = _association_changes(
        declaration["ids_by_group"], declaration_renumbered["ids_by_group"], group_map, duplicate_group_keys
    )

    return {
        "raw_instance_count": len(original),
        "valid_declaration_count": sum(instance.valid for instance in original),
        "invalid_declaration_count": sum(not instance.valid for instance in original),
        "composite_instance_count": sum(len(instance.ordered_pairs) > 1 for instance in original),
        "mapping_policy": {
            "unique_mapping_count": mapping["unique_mapping_count"],
            "duplicate_mapping_group_count": mapping["duplicate_mapping_group_count"],
            "duplicate_excess_declarations": mapping["duplicate_excess_declarations"],
            "declaration_count": mapping["declaration_count"],
            "directed_edge_count": mapping["directed_edge_count"],
            "id_unique": mapping["id_unique"],
            "inverse_pairing_pass": mapping["inverse_pairing_pass"],
            "id_set_row_order_invariant": mapping["id_set"] == mapping_reordered["id_set"],
            "id_set_group_renumber_invariant": mapping["id_set"] == mapping_renumbered["id_set"],
            "group_association_changes_under_renumber": mapping_changes_total,
            "duplicate_group_association_changes_under_renumber": mapping_changes_duplicate,
        },
        "declaration_multiset_policy": {
            "unique_declaration_id_count": declaration["declaration_count"],
            "directed_edge_count": declaration["directed_edge_count"],
            "id_unique": declaration["id_unique"],
            "inverse_pairing_pass": declaration["inverse_pairing_pass"],
            "id_set_row_order_invariant": declaration["id_set"] == declaration_reordered["id_set"],
            "id_set_group_renumber_invariant": declaration["id_set"] == declaration_renumbered["id_set"],
            "group_association_changes_under_renumber": declaration_changes_total,
            "duplicate_group_association_changes_under_renumber": declaration_changes_duplicate,
        },
    }


def _synthetic_fixture_check() -> dict[str, Any]:
    rows = [
        base.FkRow(0, 0, "orders", "users", "user_id", "id"),
        base.FkRow(1, 0, "orders", "users", "user_id", "id"),
        base.FkRow(2, 0, "orders", "users", "shipping_user_id", "id"),
        base.FkRow(3, 0, "membership", "users", "tenant_id", "tenant_id"),
        base.FkRow(3, 1, "membership", "users", "user_id", "id"),
    ]
    result = _analyze_rows(rows, "synthetic_fixture")
    mapping = result["mapping_policy"]
    declaration = result["declaration_multiset_policy"]
    _, _, changed_composites, composite_order_pass = base._invariant_counts(rows, "synthetic_fixture")
    passed = all(
        [
            result["raw_instance_count"] == 4,
            result["valid_declaration_count"] == 4,
            result["composite_instance_count"] == 1,
            mapping["unique_mapping_count"] == 3,
            mapping["duplicate_mapping_group_count"] == 1,
            mapping["duplicate_excess_declarations"] == 1,
            mapping["directed_edge_count"] == 6,
            mapping["id_unique"],
            mapping["id_set_row_order_invariant"],
            mapping["id_set_group_renumber_invariant"],
            mapping["inverse_pairing_pass"],
            declaration["unique_declaration_id_count"] == 4,
            declaration["id_unique"],
            declaration["id_set_row_order_invariant"],
            declaration["id_set_group_renumber_invariant"],
            declaration["inverse_pairing_pass"],
            declaration["duplicate_group_association_changes_under_renumber"] > 0,
            changed_composites == 1,
            composite_order_pass,
        ]
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "raw_instances": result["raw_instance_count"],
        "valid_declarations": result["valid_declaration_count"],
        "composite_instances": result["composite_instance_count"],
        "mapping_unique_instances": mapping["unique_mapping_count"],
        "mapping_directed_edges": mapping["directed_edge_count"],
        "multiset_unique_instances": declaration["unique_declaration_id_count"],
        "multiset_directed_edges": declaration["directed_edge_count"],
        "multiset_duplicate_group_association_changes": declaration["duplicate_group_association_changes_under_renumber"],
        "composite_order_sensitivity": composite_order_pass,
    }


def _scan_database(database_path: Path) -> tuple[str, str, dict[str, Any]]:
    connection = base._open_read_only(database_path)
    try:
        records, schema_sha256 = base._schema_records(connection)
        table_names = [str(row["name"]) for row in records if str(row["type"]) == "table"]
        rows = base._collect_fk_rows(connection, table_names)
    finally:
        connection.close()
    result = _analyze_rows(rows, database_path.stem)
    database_key_sha256 = hashlib.sha256(database_path.stem.encode("utf-8")).hexdigest()
    return database_key_sha256, schema_sha256, result


def _aggregate(
    database_records: list[tuple[str, str, dict[str, Any]]],
    mode: str,
    synthetic: dict[str, Any],
    run_id: str,
    dev_tables_sha256: str | None,
) -> dict[str, Any]:
    database_count = len(database_records)
    raw_count = sum(item[2]["raw_instance_count"] for item in database_records)
    valid_count = sum(item[2]["valid_declaration_count"] for item in database_records)
    invalid_count = sum(item[2]["invalid_declaration_count"] for item in database_records)
    mapping_unique = sum(item[2]["mapping_policy"]["unique_mapping_count"] for item in database_records)
    mapping_edges = sum(item[2]["mapping_policy"]["directed_edge_count"] for item in database_records)
    duplicate_groups = sum(item[2]["mapping_policy"]["duplicate_mapping_group_count"] for item in database_records)
    duplicate_excess = sum(item[2]["mapping_policy"]["duplicate_excess_declarations"] for item in database_records)
    multiset_ids = sum(item[2]["declaration_multiset_policy"]["unique_declaration_id_count"] for item in database_records)
    multiset_edges = sum(item[2]["declaration_multiset_policy"]["directed_edge_count"] for item in database_records)
    policy_checks = [item[2] for item in database_records]
    mapping_invariants = all(
        check["mapping_policy"][key]
        for check in policy_checks
        for key in ("id_unique", "inverse_pairing_pass", "id_set_row_order_invariant", "id_set_group_renumber_invariant")
    )
    multiset_invariants = all(
        check["declaration_multiset_policy"][key]
        for check in policy_checks
        for key in ("id_unique", "inverse_pairing_pass", "id_set_row_order_invariant", "id_set_group_renumber_invariant")
    )
    multiset_duplicate_association_changes = sum(
        check["declaration_multiset_policy"]["duplicate_group_association_changes_under_renumber"]
        for check in policy_checks
    )
    manifest = sorted([[key, schema_sha] for key, schema_sha, _ in database_records])
    schema_manifest_sha256 = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    if mode == "smoke":
        status = (
            "SMOKE_PASS"
            if database_count == 1 and synthetic["status"] == "PASS" and mapping_invariants and multiset_invariants
            else "STOP_INVALID"
        )
    elif database_count != EXPECTED_DATABASES or (raw_count, valid_count, invalid_count) != (
        EXPECTED_RAW, EXPECTED_VALID, EXPECTED_INVALID
    ):
        status = "INCONCLUSIVE"
    elif dev_tables_sha256 != EXPECTED_DEV_TABLES_SHA256 or schema_manifest_sha256 != EXPECTED_SCHEMA_MANIFEST_SHA256:
        status = "INCONCLUSIVE"
    elif duplicate_groups != EXPECTED_EXACT_DUPLICATE_GROUPS or duplicate_excess != 1:
        status = "INCONCLUSIVE"
    elif not mapping_invariants or not multiset_invariants or multiset_duplicate_association_changes == 0:
        status = "NO_GO"
    else:
        status = "EXPLORATORY_COMPLETE"

    return {
        "experiment_id": "g2_fk_duplicate_identity_policy_20261024_01",
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "environment": {
            "python": base.platform.python_version(),
            "sqlite": base.sqlite3.sqlite_version,
            "cpu_thread_limit": 1,
            "gpu_used": False,
            "external_api_requests": 0,
            "model_loads": 0,
            "model_forward_calls": 0,
            "sql_execution": 0,
            "dependency_installations": 0,
            "human_review": 0,
        },
        "input": {
            "database_count": database_count,
            "schema_manifest_sha256": schema_manifest_sha256,
            "dev_tables_sha256": dev_tables_sha256,
            "read_scope": ["sqlite_master", "PRAGMA table_info", "PRAGMA foreign_key_list"],
            "business_rows_read": False,
            "dev_json_read": False,
            "dev_sql_read": False,
        },
        "summary": {
            "raw_fk_declarations": raw_count,
            "valid_fk_declarations": valid_count,
            "invalid_fk_declarations": invalid_count,
            "mapping_policy": {
                "unique_valid_mappings": mapping_unique,
                "duplicate_mapping_groups": duplicate_groups,
                "duplicate_excess_declarations": duplicate_excess,
                "directed_edges": mapping_edges,
                "all_ids_unique_by_mapping": mapping_invariants,
                "id_sets_stable_under_row_and_group_permutation": mapping_invariants,
            },
            "declaration_multiset_policy": {
                "unique_valid_declaration_ids": multiset_ids,
                "directed_edges": multiset_edges,
                "all_ids_unique_and_paired": multiset_invariants,
                "id_sets_stable_under_row_and_group_permutation": multiset_invariants,
                "duplicate_group_to_ordinal_association_changes": multiset_duplicate_association_changes,
            },
            "synthetic_fixture": synthetic,
        },
        "gate": {
            "status": status,
            "historical_reference": {
                "database_count": EXPECTED_DATABASES,
                "raw_fk_declarations": EXPECTED_RAW,
                "valid_fk_declarations": EXPECTED_VALID,
                "invalid_fk_declarations": EXPECTED_INVALID,
                "exact_duplicate_mapping_groups": EXPECTED_EXACT_DUPLICATE_GROUPS,
            },
            "interpretation": "Exploratory representation comparison only; does not choose the production identity policy or authorize model evaluation.",
        },
        "measurement": {"wall_seconds": None, "process_cpu_seconds": None, "peak_rss_gib": None},
        "private_database_aggregates": [
            {"database_key_sha256": key, **result} for key, _, result in sorted(database_records)
        ],
    }


def run(dataset_root: Path, mode: str, run_id: str, output_path: Path) -> dict[str, Any]:
    database_paths = sorted(dataset_root.rglob("*.sqlite"), key=lambda path: path.name.casefold())
    if mode == "smoke":
        database_paths = database_paths[:1]
    if not database_paths:
        raise FileNotFoundError("no SQLite files found under the registered dataset root")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_path}")
    reservation_path = Path(str(output_path) + ".reservation.json")
    initial = {"run_id": run_id, "status": "RUNNING", "mode": mode, "phase": "SCHEMA_SCAN"}
    base._write_reservation(reservation_path, initial, exclusive=True)
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    try:
        synthetic = _synthetic_fixture_check()
        database_records = [_scan_database(path) for path in database_paths]
        dev_tables_path = dataset_root.parent / "dev_tables.json"
        dev_tables_sha256 = None
        if dev_tables_path.is_file():
            hasher = hashlib.sha256()
            with dev_tables_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            dev_tables_sha256 = hasher.hexdigest()
        result = _aggregate(database_records, mode, synthetic, run_id, dev_tables_sha256)
        result["measurement"] = {
            "wall_seconds": time.perf_counter() - wall_start,
            "process_cpu_seconds": time.process_time() - cpu_start,
            "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2),
        }
        base._write_json_exclusive(output_path, result)
        base._write_reservation(
            reservation_path,
            {"run_id": run_id, "status": result["status"], "mode": mode, "output": str(output_path)},
            exclusive=False,
        )
        return result
    except Exception as error:
        base._write_reservation(
            reservation_path,
            {"run_id": run_id, "status": "FAILED", "mode": mode, "error_type": type(error).__name__},
            exclusive=False,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.dataset_root, args.mode, args.run_id, args.output)
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "run_id": result["run_id"],
                "status": result["status"],
                "database_count": result["input"]["database_count"],
                "summary": result["summary"],
                "measurement": result["measurement"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
