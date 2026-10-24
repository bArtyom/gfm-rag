#!/usr/bin/env python3
"""Audit deterministic FK Join-Instance identities using SQLite schema only."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import time
from typing import Any, Iterable, Optional, Sequence, Tuple


EXPECTED_DATABASE_COUNT = 11
EXPECTED_RAW_INSTANCE_COUNT = 103
EXPECTED_VALID_INSTANCE_COUNT = 100
EXPECTED_INVALID_INSTANCE_COUNT = 3
IDENTITY_VERSION = "fk-instance-v1"


@dataclass(frozen=True)
class FkRow:
    constraint_group_id: int
    sequence: int
    source_table: str
    target_table: str
    source_column: str
    target_column: Optional[str]
    invalid_reason: Optional[str] = None


@dataclass(frozen=True)
class FkInstance:
    instance_id: str
    source_table: str
    target_table: str
    ordered_pairs: Tuple[Tuple[str, str], ...]
    constraint_group_id: int
    valid: bool
    invalid_reasons: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectedFkEdge:
    instance_id: str
    direction: str
    source_table: str
    target_table: str
    ordered_pairs: Tuple[Tuple[str, str], ...]


@dataclass
class DatabaseAudit:
    database_key_sha256: str
    schema_sha256: str
    table_count: int
    raw_instance_count: int
    valid_instance_count: int
    invalid_instance_count: int
    composite_instance_count: int
    component_count: int
    edges: Tuple[DirectedFkEdge, ...]
    identity_collision_count: int
    multi_fk_endpoint_pair_count: int
    naive_endpoint_dedup_loss: int
    input_order_invariant: bool
    group_id_renumber_invariant: bool
    component_order_sensitive_count: int
    component_order_sensitivity_pass: bool
    reverse_edge_pairing_pass: bool
    invalid_reason_counts: dict[str, int]


def _normalized_identifier(value: str) -> str:
    return value.casefold()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _instance_payload(
    database_identity: str,
    source_table: str,
    target_table: str,
    ordered_pairs: Sequence[Tuple[str, str]],
) -> str:
    payload = {
        "version": IDENTITY_VERSION,
        "database_identity": _normalized_identifier(database_identity),
        "source_table": _normalized_identifier(source_table),
        "target_table": _normalized_identifier(target_table),
        "ordered_pairs": [
            [_normalized_identifier(source), _normalized_identifier(target)]
            for source, target in ordered_pairs
        ],
    }
    return _canonical_json(payload)


def canonicalize_fk_rows(database_identity: str, rows: Iterable[FkRow]) -> list[FkInstance]:
    """Group PRAGMA rows into stable FK instances, ignoring group IDs in identity."""
    grouped: dict[tuple[str, int], list[FkRow]] = defaultdict(list)
    for row in rows:
        grouped[(_normalized_identifier(row.source_table), row.constraint_group_id)].append(row)

    instances: list[FkInstance] = []
    for (_, group_id), components in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        ordered = sorted(components, key=lambda component: component.sequence)
        first = ordered[0]
        reasons = {
            reason
            for row in ordered
            if row.invalid_reason
            for reason in row.invalid_reason.split("|")
            if reason
        }
        if len({row.sequence for row in ordered}) != len(ordered):
            reasons.add("duplicate_component_sequence")
        if [row.sequence for row in ordered] != list(range(len(ordered))):
            reasons.add("non_contiguous_component_sequence")
        if len({_normalized_identifier(row.target_table) for row in ordered}) != 1:
            reasons.add("inconsistent_target_table")

        pairs: list[tuple[str, str]] = []
        for component in ordered:
            source_column = component.source_column or ""
            target_column = component.target_column or ""
            if not source_column or not target_column:
                reasons.add("missing_column_mapping")
            pairs.append((source_column, target_column))

        payload = _instance_payload(
            database_identity,
            first.source_table,
            first.target_table,
            pairs,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        instances.append(
            FkInstance(
                instance_id=f"{IDENTITY_VERSION}:{digest}",
                source_table=first.source_table,
                target_table=first.target_table,
                ordered_pairs=tuple(pairs),
                constraint_group_id=group_id,
                valid=not reasons,
                invalid_reasons=tuple(sorted(reasons)),
            )
        )
    return instances


def build_bidirectional_edges(instances: Iterable[FkInstance]) -> list[DirectedFkEdge]:
    """Emit forward and inverse table edges that share one FK instance ID."""
    edges: list[DirectedFkEdge] = []
    for instance in instances:
        if not instance.valid:
            continue
        edges.append(
            DirectedFkEdge(
                instance_id=instance.instance_id,
                direction="forward",
                source_table=instance.source_table,
                target_table=instance.target_table,
                ordered_pairs=instance.ordered_pairs,
            )
        )
        edges.append(
            DirectedFkEdge(
                instance_id=instance.instance_id,
                direction="inverse",
                source_table=instance.target_table,
                target_table=instance.source_table,
                ordered_pairs=tuple(
                    (target_column, source_column)
                    for source_column, target_column in instance.ordered_pairs
                ),
            )
        )
    return edges


def identity_collision_count(instances: Iterable[FkInstance]) -> int:
    counts = Counter(instance.instance_id for instance in instances)
    return sum(count - 1 for count in counts.values() if count > 1)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _open_read_only(database_path: Path) -> sqlite3.Connection:
    uri = database_path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _schema_records(connection: sqlite3.Connection) -> tuple[list[sqlite3.Row], str]:
    records = list(
        connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name COLLATE NOCASE, name"
        )
    )
    canonical = [
        [str(row["type"]), str(row["name"]), str(row["tbl_name"]), row["sql"] or ""]
        for row in records
    ]
    digest = hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()
    return records, digest


def _collect_fk_rows(
    connection: sqlite3.Connection,
    table_names: Sequence[str],
) -> list[FkRow]:
    columns_by_table: dict[str, dict[str, sqlite3.Row]] = {}
    primary_keys_by_table: dict[str, list[str]] = {}
    names_by_key = {_normalized_identifier(name): name for name in table_names}

    for table_name in table_names:
        info = list(connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})"))
        columns_by_table[_normalized_identifier(table_name)] = {
            _normalized_identifier(str(row["name"])): row for row in info
        }
        primary_keys_by_table[_normalized_identifier(table_name)] = [
            str(row["name"])
            for row in sorted(info, key=lambda row: int(row["pk"]) or 10**9)
            if int(row["pk"]) > 0
        ]

    fk_rows: list[FkRow] = []
    for source_table in table_names:
        pragma_rows = connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(source_table)})"
        )
        for pragma_row in pragma_rows:
            target_table = str(pragma_row["table"] or "")
            source_column = str(pragma_row["from"] or "")
            target_raw = pragma_row["to"]
            target_column = str(target_raw) if target_raw not in (None, "") else None
            reasons: set[str] = set()

            source_key = _normalized_identifier(source_table)
            target_key = _normalized_identifier(target_table)
            source_columns = columns_by_table.get(source_key, {})
            if _normalized_identifier(source_column) not in source_columns:
                reasons.add("source_column_missing")
            if target_key not in names_by_key:
                reasons.add("target_table_missing")
            elif target_column is None:
                target_primary = primary_keys_by_table.get(target_key, [])
                sequence = int(pragma_row["seq"])
                if sequence < len(target_primary):
                    target_column = target_primary[sequence]
                else:
                    reasons.add("target_primary_key_unresolved")
            if target_column is not None and target_key in columns_by_table:
                if _normalized_identifier(target_column) not in columns_by_table[target_key]:
                    reasons.add("target_column_missing")

            fk_rows.append(
                FkRow(
                    constraint_group_id=int(pragma_row["id"]),
                    sequence=int(pragma_row["seq"]),
                    source_table=source_table,
                    target_table=target_table,
                    source_column=source_column,
                    target_column=target_column,
                    invalid_reason="|".join(sorted(reasons)) if reasons else None,
                )
            )
    return fk_rows


def _renumber_constraint_groups(rows: Sequence[FkRow]) -> list[FkRow]:
    group_keys = sorted(
        {(row.source_table.casefold(), row.constraint_group_id) for row in rows}
    )
    replacement = {key: 10_000 + index for index, key in enumerate(group_keys)}
    return [
        replace(
            row,
            constraint_group_id=replacement[
                (row.source_table.casefold(), row.constraint_group_id)
            ],
        )
        for row in rows
    ]


def _invariant_counts(rows: Sequence[FkRow], database_identity: str) -> tuple[bool, bool, int, bool]:
    original = canonicalize_fk_rows(database_identity, rows)
    original_ids = sorted(instance.instance_id for instance in original)
    reordered_ids = sorted(
        instance.instance_id for instance in canonicalize_fk_rows(database_identity, list(reversed(rows)))
    )
    input_order_invariant = original_ids == reordered_ids

    renumbered_ids = sorted(
        instance.instance_id
        for instance in canonicalize_fk_rows(
            database_identity,
            _renumber_constraint_groups(rows),
        )
    )
    group_id_renumber_invariant = original_ids == renumbered_ids

    original_by_group = {
        (instance.source_table.casefold(), instance.constraint_group_id): instance
        for instance in original
    }
    composite_groups = [
        key for key, instance in original_by_group.items() if len(instance.ordered_pairs) > 1
    ]
    changed_count = 0
    for group_key in composite_groups:
        component_total = sum(
            (row.source_table.casefold(), row.constraint_group_id) == group_key
            for row in rows
        )
        group_rows = [
            replace(row, sequence=(component_total - 1 - row.sequence))
            if (row.source_table.casefold(), row.constraint_group_id) == group_key
            else row
            for row in rows
        ]
        # Reverse the component ordinal within this one FK, preserving the FK as one group.
        target_instance = next(
            instance
            for instance in canonicalize_fk_rows(database_identity, group_rows)
            if (instance.source_table.casefold(), instance.constraint_group_id) == group_key
        )
        if target_instance.instance_id != original_by_group[group_key].instance_id:
            changed_count += 1
    sensitivity_pass = changed_count == len(composite_groups)
    return input_order_invariant, group_id_renumber_invariant, changed_count, sensitivity_pass


def scan_database(database_path: Path) -> DatabaseAudit:
    """Read schema metadata in immutable read-only mode; never scan table rows."""
    connection = _open_read_only(database_path)
    try:
        schema_records, schema_digest = _schema_records(connection)
        table_names = [
            str(row["name"])
            for row in schema_records
            if str(row["type"]) == "table"
        ]
        rows = _collect_fk_rows(connection, table_names)
    finally:
        connection.close()

    database_identity = database_path.stem
    instances = canonicalize_fk_rows(database_identity, rows)
    valid_instances = [instance for instance in instances if instance.valid]
    invalid_instances = [instance for instance in instances if not instance.valid]
    edges = build_bidirectional_edges(valid_instances)
    valid_ids = Counter(edge.instance_id for edge in edges)
    directions = defaultdict(set)
    for edge in edges:
        directions[edge.instance_id].add(edge.direction)
    reverse_edge_pairing_pass = (
        len(edges) == 2 * len(valid_instances)
        and all(valid_ids[instance.instance_id] == 2 for instance in valid_instances)
        and all(directions[instance.instance_id] == {"forward", "inverse"} for instance in valid_instances)
    )

    endpoint_counts = Counter(
        (instance.source_table.casefold(), instance.target_table.casefold())
        for instance in valid_instances
    )
    multi_fk_endpoint_pair_count = sum(count > 1 for count in endpoint_counts.values())
    naive_endpoint_dedup_loss = len(valid_instances) - len(endpoint_counts)
    invalid_reason_counts: Counter[str] = Counter()
    for instance in invalid_instances:
        invalid_reason_counts.update(instance.invalid_reasons)

    input_order_invariant, group_id_renumber_invariant, changed_count, sensitivity_pass = (
        _invariant_counts(rows, database_identity)
    )
    database_key = hashlib.sha256(database_identity.encode("utf-8")).hexdigest()
    return DatabaseAudit(
        database_key_sha256=database_key,
        schema_sha256=schema_digest,
        table_count=len(table_names),
        raw_instance_count=len(instances),
        valid_instance_count=len(valid_instances),
        invalid_instance_count=len(invalid_instances),
        composite_instance_count=sum(len(instance.ordered_pairs) > 1 for instance in instances),
        component_count=sum(len(instance.ordered_pairs) for instance in instances),
        edges=tuple(edges),
        identity_collision_count=identity_collision_count(valid_instances),
        multi_fk_endpoint_pair_count=multi_fk_endpoint_pair_count,
        naive_endpoint_dedup_loss=naive_endpoint_dedup_loss,
        input_order_invariant=input_order_invariant,
        group_id_renumber_invariant=group_id_renumber_invariant,
        component_order_sensitive_count=changed_count,
        component_order_sensitivity_pass=sensitivity_pass,
        reverse_edge_pairing_pass=reverse_edge_pairing_pass,
        invalid_reason_counts=dict(sorted(invalid_reason_counts.items())),
    )


def _audit_record(audit: DatabaseAudit) -> dict[str, Any]:
    return {
        "database_key_sha256": audit.database_key_sha256,
        "schema_sha256": audit.schema_sha256,
        "table_count": audit.table_count,
        "raw_instance_count": audit.raw_instance_count,
        "valid_instance_count": audit.valid_instance_count,
        "invalid_instance_count": audit.invalid_instance_count,
        "composite_instance_count": audit.composite_instance_count,
        "component_count": audit.component_count,
        "directed_edge_count": len(audit.edges),
        "identity_collision_count": audit.identity_collision_count,
        "multi_fk_endpoint_pair_count": audit.multi_fk_endpoint_pair_count,
        "naive_endpoint_dedup_loss": audit.naive_endpoint_dedup_loss,
        "input_order_invariant": audit.input_order_invariant,
        "group_id_renumber_invariant": audit.group_id_renumber_invariant,
        "component_order_sensitive_count": audit.component_order_sensitive_count,
        "component_order_sensitivity_pass": audit.component_order_sensitivity_pass,
        "reverse_edge_pairing_pass": audit.reverse_edge_pairing_pass,
        "invalid_reason_counts": audit.invalid_reason_counts,
    }


def _summarize(audits: Sequence[DatabaseAudit], mode: str, run_id: str, dataset_root: Path) -> dict[str, Any]:
    raw_count = sum(audit.raw_instance_count for audit in audits)
    valid_count = sum(audit.valid_instance_count for audit in audits)
    invalid_count = sum(audit.invalid_instance_count for audit in audits)
    composite_count = sum(audit.composite_instance_count for audit in audits)
    component_count = sum(audit.component_count for audit in audits)
    edge_count = sum(len(audit.edges) for audit in audits)
    collision_count = sum(audit.identity_collision_count for audit in audits)
    composite_sensitive = sum(audit.component_order_sensitive_count for audit in audits)
    all_composites_sensitive = composite_sensitive == composite_count
    invariant_pass = all(
        audit.input_order_invariant
        and audit.group_id_renumber_invariant
        and audit.component_order_sensitivity_pass
        and audit.reverse_edge_pairing_pass
        and audit.identity_collision_count == 0
        for audit in audits
    )
    sorted_audits = sorted(audits, key=lambda audit: audit.database_key_sha256)
    schema_manifest = [
        [audit.database_key_sha256, audit.schema_sha256] for audit in sorted_audits
    ]
    schema_manifest_sha256 = hashlib.sha256(
        _canonical_json(schema_manifest).encode("utf-8")
    ).hexdigest()
    dev_tables = dataset_root.parent / "dev_tables.json"
    dev_tables_sha256 = None
    if dev_tables.is_file():
        hasher = hashlib.sha256()
        with dev_tables.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        dev_tables_sha256 = hasher.hexdigest()

    if mode == "smoke":
        status = "SMOKE_PASS" if invariant_pass and len(audits) == 1 else "STOP_INVALID"
    elif len(audits) != EXPECTED_DATABASE_COUNT:
        status = "INCONCLUSIVE"
    elif (raw_count, valid_count, invalid_count) != (
        EXPECTED_RAW_INSTANCE_COUNT,
        EXPECTED_VALID_INSTANCE_COUNT,
        EXPECTED_INVALID_INSTANCE_COUNT,
    ):
        status = "INCONCLUSIVE"
    elif not invariant_pass or not all_composites_sensitive:
        status = "NO_GO"
    else:
        status = "PASS"

    invalid_reasons: Counter[str] = Counter()
    for audit in audits:
        invalid_reasons.update(audit.invalid_reason_counts)
    return {
        "experiment_id": "g2_fk_instance_quality_20261024_01",
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
            "cpu_thread_limit": 1,
            "gpu_used": False,
            "external_api_requests": 0,
            "model_loads": 0,
            "model_forward_calls": 0,
            "sql_execution": 0,
            "dependency_installations": 0,
        },
        "input": {
            "database_count": len(audits),
            "schema_manifest_sha256": schema_manifest_sha256,
            "dev_tables_sha256": dev_tables_sha256,
            "read_scope": ["sqlite_master", "PRAGMA table_info", "PRAGMA foreign_key_list"],
            "business_rows_read": False,
            "dev_json_read": False,
            "dev_sql_read": False,
        },
        "summary": {
            "raw_instance_count": raw_count,
            "valid_instance_count": valid_count,
            "invalid_instance_count": invalid_count,
            "composite_instance_count": composite_count,
            "component_count": component_count,
            "directed_edge_count": edge_count,
            "identity_collision_count": collision_count,
            "multi_fk_endpoint_pair_count": sum(
                audit.multi_fk_endpoint_pair_count for audit in audits
            ),
            "naive_endpoint_dedup_loss": sum(
                audit.naive_endpoint_dedup_loss for audit in audits
            ),
            "all_input_order_invariant": all(a.input_order_invariant for a in audits),
            "all_group_id_renumber_invariant": all(
                a.group_id_renumber_invariant for a in audits
            ),
            "composite_order_sensitive_count": composite_sensitive,
            "all_composite_order_sensitive": all_composites_sensitive,
            "all_reverse_edge_pairing_pass": all(a.reverse_edge_pairing_pass for a in audits),
            "invalid_reason_counts": dict(sorted(invalid_reasons.items())),
        },
        "gate": {
            "status": status,
            "historical_reference": {
                "database_count": EXPECTED_DATABASE_COUNT,
                "raw_instance_count": EXPECTED_RAW_INSTANCE_COUNT,
                "valid_instance_count": EXPECTED_VALID_INSTANCE_COUNT,
                "invalid_instance_count": EXPECTED_INVALID_INSTANCE_COUNT,
            },
            "structural_invariants_pass": invariant_pass,
        },
        "measurement": {
            "wall_seconds": None,
            "process_cpu_seconds": None,
            "peak_rss_gib": None,
        },
        "private_database_aggregates": [_audit_record(audit) for audit in sorted_audits],
    }


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_reservation(path: Path, state: dict[str, Any], exclusive: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_audit(dataset_root: Path, mode: str, run_id: str, output_path: Path) -> dict[str, Any]:
    database_paths = sorted(dataset_root.glob("*.sqlite"), key=lambda path: path.name.casefold())
    if mode == "smoke":
        database_paths = database_paths[:1]
    if not database_paths:
        raise FileNotFoundError(f"no SQLite files found in the registered dataset root: {dataset_root}")

    reservation_path = Path(str(output_path) + ".reservation.json")
    initial_state = {
        "run_id": run_id,
        "status": "RUNNING",
        "phase": "SCHEMA_SCAN",
        "mode": mode,
        "database_count_expected_for_mode": 1 if mode == "smoke" else EXPECTED_DATABASE_COUNT,
    }
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_path}")
    _write_reservation(reservation_path, initial_state, exclusive=True)

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        audits = [scan_database(path) for path in database_paths]
    except Exception as error:
        _write_reservation(
            reservation_path,
            {
                "run_id": run_id,
                "status": "STOP_INVALID",
                "phase": "SCHEMA_SCAN",
                "error_type": type(error).__name__,
                "error": str(error),
            },
            exclusive=False,
        )
        raise
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    peak_rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)

    result = _summarize(audits, mode, run_id, dataset_root)
    result["measurement"].update(
        wall_seconds=wall_seconds,
        process_cpu_seconds=cpu_seconds,
        peak_rss_gib=peak_rss_gib,
    )
    _write_json_exclusive(output_path, result)
    _write_reservation(
        reservation_path,
        {
            "run_id": run_id,
            "status": result["status"],
            "phase": "COMPLETED",
            "database_count": len(audits),
            "output_sha256": _file_sha256(output_path),
        },
        exclusive=False,
    )
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dataset_root.is_dir():
        raise SystemExit(f"dataset root does not exist: {args.dataset_root}")
    result = run_audit(args.dataset_root, args.mode, args.run_id, args.output)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
