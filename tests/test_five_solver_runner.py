from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/text2sql'))
from run_steiner_five_solvers import summarize
from extended_steiner_solvers import METHODS


class FiveSolverRunnerTests(unittest.TestCase):
    def row(self, nodes, cost, gold):
        methods = {m: {'nodes': [0, 1], 'edges': [[0, 1]], 'constraint_ids': ['a'],
            'cost': 1., 'elapsed_seconds': .001, 'certificates': [], 'connected': True,
            'certified_optimal': m in ['milp', 'dreyfus_wagner']} for m in METHODS}
        methods['greedy'] = {**methods['greedy'], 'nodes': nodes, 'cost': cost}
        return {'db_id': 'db', 'oracle_cost': 1., 'gold': gold, 'methods': methods}

    def test_equal_cost_different_schema_is_tie_sensitivity(self):
        result = summarize([self.row([0, 2], 1., {0, 2})], {'db': {'column_names_original': [[0, 'a'], [1, 'b'], [2, 'c']]}})
        pair = result['vs_mehlhorn']['greedy']
        self.assertEqual(pair['changed_tables_equal_cost'], 1)
        self.assertEqual(pair['strictly_cheaper'], 0)
        self.assertEqual(pair['rescue'], 1)

    def test_unknown_labels_keep_denominator(self):
        result = summarize([self.row([0, 1], 1., None)], {'db': {'column_names_original': [[0, 'a'], [1, 'b']]}})
        self.assertEqual(result['methods']['greedy']['complete_rate_all_questions'], 0)
        self.assertEqual(result['vs_mehlhorn']['greedy']['unknown'], 1)


if __name__ == '__main__':
    unittest.main()
