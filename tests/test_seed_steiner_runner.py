import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/text2sql'))
try:
    import run_seed_steiner as runner
except ModuleNotFoundError:
    runner = None


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(runner, 'frozen runner is not implemented')

    def test_cache_reordering_is_rejected(self):
        online = [{'db_id': 'a', 'question_id': 1}, {'db_id': 'b', 'question_id': 2}]
        with self.assertRaises(ValueError):
            runner.verify_identity(online, list(reversed(online)))

    def test_output_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'attempt'
            runner.new_output(path)
            with self.assertRaises(FileExistsError):
                runner.new_output(path)

    def test_database_snapshot_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            runner.verify_database_hashes({'db': 'original'}, {'db': 'modified'})

    def test_coverage_reports_failures_in_denominator(self):
        metrics = runner.coverage_summary([
            {'gold': {0}, 'tables': [0, 1], 'columns': 5},
            {'gold': None, 'tables': [0], 'columns': 2},
        ])
        self.assertEqual(metrics['questions'], 2)
        self.assertEqual(metrics['reference_parse_failures'], 1)
        self.assertEqual(metrics['complete'], 1)
        self.assertEqual(metrics['complete_rate_all_questions'], 0.5)


if __name__ == '__main__':
    unittest.main()
