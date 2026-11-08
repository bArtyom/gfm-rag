"""Behavioral tests for seed retention, FK integrity and label-blind selection."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    spec = importlib.util.spec_from_file_location('seed_steiner', ROOT / 'scripts/text2sql/seed_steiner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except FileNotFoundError:
    module = None


def fixture():
    return {
        'db_id': 'synthetic',
        'table_names_original': ['people.v1', 'enrolments', 'courses', 'isolated'],
        'column_names_original': [[-1, '*'], [0, 'id'], [0, 'name'], [1, 'person_id'], [1, 'course_id'], [2, 'id'], [2, 'title'], [3, 'id']],
        'column_types': ['text', 'number', 'text', 'number', 'number', 'number', 'text', 'number'],
        'primary_keys': [1, 5, 7],
        'foreign_keys': [[3, 1], [4, 5]],
    }


def constraints():
    return [
        {'id': 'fk:1:0', 'source_table': 1, 'target_table': 0, 'pairs': [[3, 1]]},
        {'id': 'fk:1:1', 'source_table': 1, 'target_table': 2, 'pairs': [[4, 5]]},
    ]


class SeedSteinerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(module, 'seed-to-Steiner adapter has not been implemented')

    def test_actual_upstream_bridge_recovery_and_dot_names(self):
        result = module.connect_schema(fixture(), constraints(), [0, 2], module.load_upstream())
        self.assertEqual(result['tables'], [0, 1, 2])
        self.assertEqual(result['bridge_tables'], [1])
        self.assertTrue(result['connected'])
        ddl = module.serialize_schema(fixture(), result['tables'], result['constraints'])
        self.assertIn('"people.v1"', ddl)
        self.assertIn('"person_id"', ddl)

    def test_disconnected_seeds_are_preserved_without_fabricated_edges(self):
        result = module.connect_schema(fixture(), constraints(), [0, 3], module.load_upstream())
        self.assertEqual(result['tables'], [0, 3])
        self.assertFalse(result['connected'])
        self.assertEqual(result['constraints'], [])

    def test_silent_upstream_path_failure_cannot_look_like_a_valid_result(self):
        class FailedHelper:
            def get_steiner_subgraph(self, graph, terminals):
                return graph.subgraph(terminals).copy()
        with self.assertRaises(RuntimeError):
            module.connect_schema(fixture(), constraints(), [0, 2], FailedHelper())

    def test_parallel_roles_and_composite_keys_are_not_collapsed(self):
        fks = constraints() + [{'id': 'fk:1:2', 'source_table': 1, 'target_table': 0, 'pairs': [[3, 1], [4, 2]]}]
        result = module.connect_schema(fixture(), fks, [1, 0], module.load_upstream())
        self.assertEqual(len(result['constraints']), 2)
        self.assertEqual(result['constraints'][1]['pairs'], [[3, 1], [4, 2]])

    def test_empty_and_single_seed(self):
        for seeds in [[], [3]]:
            result = module.connect_schema(fixture(), constraints(), seeds, module.load_upstream())
            self.assertEqual(result['tables'], seeds)
            self.assertTrue(result['connected'])

    def test_column_seeds_map_to_distinct_tables_and_stable_ties(self):
        nodes = [{'node_id': f'column:synthetic:{c}', 'node_type': 'column'} for c in [1, 2, 5]]
        ranked = module.rank_seed_tables(fixture(), nodes, [0.8, 0.9, 0.9], 2, 'column')
        self.assertEqual(ranked[:2], [0, 2])

    def test_nonfinite_similarity_fails_closed(self):
        with self.assertRaises(ValueError):
            module.rank_seed_tables(fixture(), [{'node_id': 'table:synthetic:0', 'node_type': 'table'}], [float('nan')], 2, 'table')

    def test_cte_shadowing_is_not_a_physical_table(self):
        schema = fixture()
        query = 'WITH courses AS (SELECT * FROM "people.v1") SELECT * FROM courses'
        self.assertEqual(module.reference_tables(query, schema), {0})

    def test_split_is_independent_of_labels_and_input_order(self):
        rows = [{'question_id': i, 'db_id': f'd{i % 3}', 'SQL': 'unused'} for i in range(24)]
        a = module.choose_split(rows, 123, smoke_count=5, per_database=2)
        b = module.choose_split([{**r, 'SQL': 'different'} for r in reversed(rows)], 123, smoke_count=5, per_database=2)
        self.assertEqual(a, b)
        self.assertEqual(len(a['smoke']), 5)
        self.assertEqual(len(a['pilot']), 6)
        self.assertFalse(set(a['smoke']) & set(a['pilot']))


if __name__ == '__main__':
    unittest.main()
