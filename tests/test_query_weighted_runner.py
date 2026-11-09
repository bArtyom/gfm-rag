import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'text2sql'))
from run_query_weighted_steiner import select_pilot, paired


class WeightedRunnerTests(unittest.TestCase):
    def test_pilot_is_order_independent_and_uses_structure_only(self):
        rows = [{'db_id': str(i % 3), 'question_id': i, 'alternative_route': bool(i % 2)} for i in range(120)]
        a = select_pilot(rows, 100)
        b = select_pilot(list(reversed(rows)), 100)
        identity = lambda rs: {(r['db_id'], r['question_id']) for r in rs}
        self.assertEqual(identity(a), identity(b))
        self.assertEqual(len(identity(a)), 100)
        self.assertEqual(sum(r['alternative_route'] for r in a), 50)

    def test_pair_counts_rescue_damage_and_unknown(self):
        rows = [{'db_id': 'a', 'gold': gold, 'arms': {'weighted': {'nodes': w}, 'unit': {'nodes': u}}}
                for gold, w, u in [({1}, [1], [0]), ({1}, [0], [1]), ({1}, [1], [1]), (None, [0], [0])]]
        result = paired(rows, 'unit')
        self.assertEqual((result['rescue'], result['damage'], result['unchanged'], result['unknown']), (1, 1, 1, 1))
        self.assertEqual(result['delta_all_questions'], 0)


if __name__ == '__main__':
    unittest.main()
