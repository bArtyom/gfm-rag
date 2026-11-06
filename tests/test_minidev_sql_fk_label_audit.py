import json
from pathlib import Path
import tempfile
import unittest

from scripts.text2sql import audit_minidev_sql_fk_labels as audit
from scripts.text2sql.audit_minidev_sql_fk_labels import parse_gold_sql


def _candidate(mapping_id, child_column, parent_column, child="child", parent="parent"):
    return {
        "mapping_id": mapping_id,
        "child_table": child,
        "parent_table": parent,
        "ordered_column_pairs": [[child_column, parent_column]],
    }


class GoldSqlLabelAuditTests(unittest.TestCase):
    def test_join_on_alias_resolution_labels_only_used_mapping_and_counts_where_join(self):
        result = parse_gold_sql(
            "SELECT c.id FROM child AS c JOIN parent AS p ON c.parent_id = p.id "
            "WHERE c.other_id = p.id",
            db_id="toy",
            known_columns={
                "child": {"id", "parent_id", "other_id"},
                "parent": {"id"},
            },
            candidate_mappings=[
                _candidate("fk_parent", "parent_id", "id"),
                _candidate("fk_other", "other_id", "id"),
            ],
        )

        self.assertTrue(result["parse_success"])
        self.assertEqual(result["qualified_join_equality_count"], 1)
        self.assertEqual(result["resolved_qualified_join_equality_count"], 1)
        self.assertEqual(result["implicit_where_cross_table_equality_count"], 1)
        self.assertEqual(
            result["gold_mapping_ids_by_table_pair"], {("child", "parent"): ["fk_parent"]}
        )

    def test_composite_mapping_requires_every_ordered_pair_in_one_join_condition(self):
        result = parse_gold_sql(
            "SELECT c.id FROM child AS c JOIN parent AS p ON c.parent_id = p.id",
            db_id="toy",
            known_columns={
                "child": {"id", "parent_id", "year_id"},
                "parent": {"id", "year_id"},
            },
            candidate_mappings=[
                {
                    "mapping_id": "fk_composite",
                    "child_table": "child",
                    "parent_table": "parent",
                    "ordered_column_pairs": [["parent_id", "id"], ["year_id", "year_id"]],
                },
                _candidate("fk_alternate", "year_id", "year_id"),
            ],
        )

        self.assertEqual(result["gold_mapping_ids_by_table_pair"], {})

    def test_composite_mapping_is_not_assembled_across_union_scopes(self):
        result = parse_gold_sql(
            "SELECT c.id FROM child AS c JOIN parent AS p ON c.parent_id = p.id "
            "UNION ALL "
            "SELECT c.id FROM child AS c JOIN parent AS p ON c.year_id = p.year_id",
            db_id="toy",
            known_columns={
                "child": {"id", "parent_id", "year_id", "backup_id"},
                "parent": {"id", "year_id"},
            },
            candidate_mappings=[
                {
                    "mapping_id": "fk_composite",
                    "child_table": "child",
                    "parent_table": "parent",
                    "ordered_column_pairs": [["parent_id", "id"], ["year_id", "year_id"]],
                },
                _candidate("fk_backup", "backup_id", "id"),
            ],
        )

        self.assertEqual(result["gold_mapping_ids_by_table_pair"], {})

    def test_join_equality_without_resolvable_qualified_columns_is_counted_as_unresolved(self):
        result = parse_gold_sql(
            "SELECT c.id FROM child AS c JOIN parent AS p ON missing.parent_id = p.id",
            db_id="toy",
            known_columns={"child": {"id", "parent_id"}, "parent": {"id"}},
            candidate_mappings=[
                _candidate("fk_parent", "parent_id", "id"),
                _candidate("fk_other", "id", "id"),
            ],
        )

        self.assertEqual(result["qualified_join_equality_count"], 1)
        self.assertEqual(result["resolved_qualified_join_equality_count"], 0)
        self.assertEqual(result["unresolved_qualified_join_equality_count"], 1)
        self.assertEqual(result["gold_mapping_ids_by_table_pair"], {})

    def test_duplicate_case_insensitive_alias_is_unresolved(self):
        result = parse_gold_sql(
            "SELECT c.id FROM child AS c JOIN parent AS c ON c.parent_id = c.id",
            db_id="toy",
            known_columns={"child": {"id", "parent_id"}, "parent": {"id"}},
            candidate_mappings=[
                _candidate("fk_parent", "parent_id", "id"),
                _candidate("fk_other", "id", "id"),
            ],
        )

        self.assertEqual(result["qualified_join_equality_count"], 1)
        self.assertEqual(result["resolved_qualified_join_equality_count"], 0)
        self.assertEqual(result["unresolved_qualified_join_equality_count"], 1)
        self.assertEqual(result["gold_mapping_ids_by_table_pair"], {})

    def test_duplicate_fk_identities_collapse_to_one_candidate(self):
        rows = [
            {
                "join_instance_id": mapping_id,
                "child_table": "child",
                "parent_table": "parent",
                "ordered_column_pairs": [["parent_id", "id"]],
                "valid_endpoints": True,
            }
            for mapping_id in ("z_mapping", "a_mapping")
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "fk_artifact.json"
            artifact_path.write_text(
                json.dumps({"instances_private": {"toy": rows}}), encoding="utf-8"
            )
            candidates, skipped_invalid, duplicate_identities = audit.load_candidate_mappings(
                artifact_path,
                {"toy": {"child": {"parent_id"}, "parent": {"id"}}},
            )

        pair_candidates = candidates["toy"][("child", "parent")]
        self.assertEqual(skipped_invalid, 0)
        self.assertEqual(duplicate_identities, 1)
        self.assertEqual([row["mapping_id"] for row in pair_candidates], ["a_mapping"])

    def test_smoke_output_requires_matching_hashes_and_exact_unique_rows(self):
        keys = [(f"db_{index}", str(index)) for index in range(5)]
        input_hashes = {"dataset": "frozen-hash"}
        rows = [
            {
                "db_id": db_id,
                "question_id": question_id,
                "question_key_sha256": audit.stable_digest(db_id, question_id),
                "parse_success": True,
                "parse_counters": {},
            }
            for db_id, question_id in keys
        ]
        payload = {
            "experiment_id": audit.EXPERIMENT_ID,
            "run_id": f"{audit.EXPERIMENT_ID}_cpu_smoke_001",
            "split": "smoke",
            "input_sha256": input_hashes,
            "smoke_question_keys": [list(key) for key in keys],
            "selected_question_keys": [list(key) for key in keys],
            "question_audit_rows": rows,
        }

        self.assertEqual(audit.validate_smoke_private(payload, set(keys), input_hashes), rows)
        duplicate_payload = {**payload, "question_audit_rows": rows[:-1] + [rows[0]]}
        with self.assertRaises(ValueError):
            audit.validate_smoke_private(duplicate_payload, set(keys), input_hashes)
        wrong_hash_payload = {**payload, "input_sha256": {"dataset": "other-hash"}}
        with self.assertRaises(ValueError):
            audit.validate_smoke_private(wrong_hash_payload, set(keys), input_hashes)
