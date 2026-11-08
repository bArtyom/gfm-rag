from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/text2sql'))
try:
    import run_steiner_two_solvers as runner
except ModuleNotFoundError:
    runner = None


def row(exact_nodes, approx_nodes, exact_cost, approx_cost, gold):
    return {'db_id': 'synthetic', 'gold': gold, 'methods': {
        'mehlhorn': {'nodes': approx_nodes, 'edges': [], 'cost': approx_cost, 'connected': True, 'elapsed_seconds': .002},
        'dreyfus_wagner': {'nodes': exact_nodes, 'edges': [], 'cost': exact_cost, 'connected': True, 'elapsed_seconds': .003}}}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(runner, 'paired solver runner has not been implemented')
        self.schemas = {'synthetic': {'column_names_original': [[-1, '*'], [0, 'id'], [1, 'id'], [2, 'id'], [3, 'id']]}}

    def test_equal_cost_different_nodes_are_tie_sensitivity(self):
        result = runner.summarize_group([row([0, 1, 2], [0, 1, 3], 2, 2, {0, 2})], self.schemas, 123)
        self.assertEqual(result['strict_exact_cost_improvements'], 0)
        self.assertEqual(result['different_table_sets_equal_cost'], 1)
        self.assertEqual(result['exact_vs_mehlhorn_coverage']['rescue'], 1)
        self.assertEqual(result['decision'], 'same_cost_tie_sensitivity')

    def test_cheaper_tree_can_reduce_reference_table_coverage(self):
        result = runner.summarize_group([row([0, 1], [0, 1, 2], 1, 2, {0, 2})], self.schemas, 123)
        self.assertEqual(result['strict_exact_cost_improvements'], 1)
        self.assertEqual(result['exact_vs_mehlhorn_coverage']['damage'], 1)
        self.assertFalse(result['positive_task_signal'])

    def test_unknown_reference_remains_in_denominator(self):
        result = runner.summarize_group([row([0, 1], [0, 1], 1, 1, None)], self.schemas, 123)
        self.assertEqual(result['questions'], 1)
        self.assertEqual(result['methods']['dreyfus_wagner']['reference_parse_failures'], 1)
        self.assertEqual(result['exact_vs_mehlhorn_coverage']['unknown'], 1)


if __name__ == '__main__':
    unittest.main()
