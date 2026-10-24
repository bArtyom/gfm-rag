"""Contract tests for the registered BIRD FK Instance audit."""

from dataclasses import replace
import sqlite3
import tempfile
from pathlib import Path
import unittest

from scripts.text2sql.fk_instance_quality_audit import (
    FkRow,
    build_bidirectional_edges,
    canonicalize_fk_rows,
    identity_collision_count,
    run_audit,
    scan_database,
)


class FKInstanceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            FkRow(7, 1, "orders", "customers", "billing_region", "region"),
            FkRow(7, 0, "orders", "customers", "billing_customer_id", "id"),
            FkRow(3, 0, "orders", "customers", "shipping_customer_id", "id"),
        ]

    def test_ids_ignore_pragma_group_numbers_and_row_enumeration(self):
        original = canonicalize_fk_rows("bird-dev:db-x", self.rows)
        self.assertEqual(len(original), 2)
        renumbered = [
            replace(row, constraint_group_id=row.constraint_group_id + 100)
            for row in reversed(self.rows)
        ]
        reordered = canonicalize_fk_rows("bird-dev:db-x", renumbered)
        self.assertEqual(
            sorted(instance.instance_id for instance in original),
            sorted(instance.instance_id for instance in reordered),
        )

    def test_composite_column_order_is_preserved_and_identity_sensitive(self):
        original = canonicalize_fk_rows("bird-dev:db-x", self.rows)
        self.assertEqual(len(original), 2)
        composite = next(instance for instance in original if len(instance.ordered_pairs) == 2)
        self.assertEqual(
            composite.ordered_pairs,
            (("billing_customer_id", "id"), ("billing_region", "region")),
        )
        reversed_components = [
            replace(row, sequence=1 - row.sequence)
            if row.constraint_group_id == 7
            else row
            for row in self.rows
        ]
        changed = canonicalize_fk_rows("bird-dev:db-x", reversed_components)
        changed_composite = next(instance for instance in changed if len(instance.ordered_pairs) == 2)
        self.assertNotEqual(composite.instance_id, changed_composite.instance_id)

    def test_same_endpoint_different_fk_mappings_remain_distinct(self):
        instances = canonicalize_fk_rows("bird-dev:db-x", self.rows)
        self.assertEqual(len(instances), 2)
        self.assertEqual(
            {(instance.source_table, instance.target_table) for instance in instances},
            {("orders", "customers")},
        )
        self.assertEqual(len({instance.instance_id for instance in instances}), 2)

    def test_inverse_edges_share_instance_id_and_reverse_ordered_pairs(self):
        instances = canonicalize_fk_rows("bird-dev:db-x", self.rows)
        self.assertEqual(len(instances), 2)
        edges = build_bidirectional_edges(instances)
        self.assertEqual(len(edges), 4)
        for instance in instances:
            paired = [edge for edge in edges if edge.instance_id == instance.instance_id]
            self.assertEqual({edge.direction for edge in paired}, {"forward", "inverse"})
            forward = next(edge for edge in paired if edge.direction == "forward")
            inverse = next(edge for edge in paired if edge.direction == "inverse")
            self.assertEqual(forward.ordered_pairs, instance.ordered_pairs)
            self.assertEqual(
                inverse.ordered_pairs,
                tuple((target, source) for source, target in instance.ordered_pairs),
            )

    def test_duplicate_structural_signatures_are_reported_as_collisions(self):
        duplicate_rows = [
            FkRow(1, 0, "orders", "customers", "customer_id", "id"),
            FkRow(2, 0, "orders", "customers", "customer_id", "id"),
        ]
        instances = canonicalize_fk_rows("bird-dev:db-x", duplicate_rows)
        self.assertEqual(identity_collision_count(instances), 1)


class SQLiteSchemaScanTests(unittest.TestCase):
    def test_smoke_discovers_sqlite_database_nested_under_its_dataset_folder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_root = Path(temporary_directory) / "dev_databases"
            nested_directory = dataset_root / "sample_db"
            nested_directory.mkdir(parents=True)
            database_path = nested_directory / "sample_db.sqlite"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
                "CREATE TABLE child (parent_id INTEGER, FOREIGN KEY(parent_id) REFERENCES parent(id));"
            )
            connection.close()
            output_path = Path(temporary_directory) / "smoke_result.json"

            try:
                result = run_audit(dataset_root, "smoke", "nested-smoke-test", output_path)
            except FileNotFoundError as error:
                self.fail(f"smoke failed to discover a nested SQLite database: {error}")

        self.assertEqual(result["status"], "SMOKE_PASS")
        self.assertEqual(result["input"]["database_count"], 1)

    def test_read_only_scan_preserves_two_same_endpoint_instances_and_composite_fk(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "fixture.sqlite"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                "CREATE TABLE customers (id INTEGER PRIMARY KEY, code TEXT UNIQUE, region TEXT, UNIQUE(code, region));"
                "CREATE TABLE orders (billing_id INTEGER, shipping_code TEXT, shipping_region TEXT, "
                "FOREIGN KEY (billing_id) REFERENCES customers(id), "
                "FOREIGN KEY (shipping_code, shipping_region) REFERENCES customers(code, region));"
            )
            connection.close()

            audit = scan_database(database_path)

        self.assertEqual(audit.raw_instance_count, 2)
        self.assertEqual(audit.valid_instance_count, 2)
        self.assertEqual(audit.invalid_instance_count, 0)
        self.assertEqual(audit.composite_instance_count, 1)
        self.assertEqual(audit.component_order_sensitive_count, 1)
        self.assertTrue(audit.component_order_sensitivity_pass)
        self.assertEqual(len(audit.edges), 4)
        self.assertEqual(audit.identity_collision_count, 0)
        self.assertEqual(audit.multi_fk_endpoint_pair_count, 1)

    def test_implicit_composite_parent_key_is_resolved_in_primary_key_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "implicit_pk.sqlite"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                "CREATE TABLE parent (parent_id INTEGER, parent_region TEXT, "
                "PRIMARY KEY(parent_id, parent_region));"
                "CREATE TABLE child (child_id INTEGER, child_region TEXT, "
                "FOREIGN KEY(child_id, child_region) REFERENCES parent);"
            )
            connection.close()

            audit = scan_database(database_path)

        self.assertEqual(audit.raw_instance_count, 1)
        self.assertEqual(audit.valid_instance_count, 1)
        self.assertEqual(audit.invalid_instance_count, 0)
        self.assertEqual(audit.composite_instance_count, 1)
        self.assertEqual(audit.component_count, 2)
        self.assertTrue(audit.reverse_edge_pairing_pass)

    def test_missing_referenced_table_is_counted_as_invalid_not_discarded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "invalid_fk.sqlite"
            connection = sqlite3.connect(database_path)
            connection.execute(
                "CREATE TABLE child (child_id INTEGER, "
                "FOREIGN KEY(child_id) REFERENCES missing_parent(id))"
            )
            connection.close()

            audit = scan_database(database_path)

        self.assertEqual(audit.raw_instance_count, 1)
        self.assertEqual(audit.valid_instance_count, 0)
        self.assertEqual(audit.invalid_instance_count, 1)
        self.assertEqual(audit.edges, ())
        self.assertEqual(audit.invalid_reason_counts, {"target_table_missing": 1})


if __name__ == "__main__":
    unittest.main()
