import itertools
from pathlib import Path
import random
import sys
import unittest

import networkx as nx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/text2sql'))
from extended_steiner_solvers import METHODS, solve
from test_steiner_solvers import brute_force_cost


class ExtendedSolverTests(unittest.TestCase):
    def test_all_five_methods_are_distinct_and_known_example(self):
        self.assertEqual(METHODS, ['greedy', 'kou', 'mehlhorn', 'dreyfus_wagner', 'milp'])
        g = nx.Graph()
        g.add_weighted_edges_from([(0, 1, 5), (0, 2, 5), (1, 2, 5), (0, 3, 3), (1, 3, 3), (2, 3, 3)])
        for method in METHODS:
            result = solve(g, [0, 1, 2], method)
            self.assertGreaterEqual(result['cost'], 9)
            if method in ['dreyfus_wagner', 'milp']:
                self.assertEqual(result['cost'], 9)
                self.assertTrue(result['certified_optimal'])
        self.assertEqual(solve(g, [0, 1, 2], 'greedy')['cost'], 10)

    def test_exact_milp_and_dp_match_brute_force(self):
        rng = random.Random(20261109)
        for trial in range(12):
            g = nx.path_graph(5)
            g.add_edges_from(rng.sample([(0, 2), (0, 3), (0, 4), (1, 3), (1, 4), (2, 4)], 2))
            for a, b in g.edges:
                g[a][b]['weight'] = rng.randint(1, 8) / 3
            terminals = rng.sample(list(g), 4)
            optimum = brute_force_cost(g, terminals)
            with self.subTest(trial=trial):
                for method in METHODS:
                    result = solve(g, terminals, method)
                    self.assertGreaterEqual(result['cost'] + 1e-7, optimum)
                    if method in ['milp', 'dreyfus_wagner']:
                        self.assertAlmostEqual(result['cost'], optimum, places=7)
                    if method == 'milp':
                        self.assertTrue(result['certificates'])
                        for c in result['certificates']:
                            self.assertEqual(c['status'], 0)
                            self.assertLessEqual(c['mip_gap'], 1e-8)

    def test_forests_empty_single_and_zero_cost(self):
        g = nx.Graph()
        g.add_weighted_edges_from([(0, 1, 0), (1, 2, 0), (8, 9, 1)])
        for method in METHODS:
            self.assertEqual(solve(g, [], method)['nodes'], [])
            self.assertEqual(solve(g, [1], method)['nodes'], [1])
            result = solve(g, [0, 2, 8], method)
            self.assertEqual(result['cost'], 0)
            self.assertFalse(result['connected'])
            self.assertEqual(result['seed_components'], 2)

    def test_stable_ties_and_original_graph_unchanged(self):
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (3, 4)]
        a, b = nx.Graph(), nx.Graph()
        a.add_edges_from(edges)
        b.add_edges_from(reversed(edges))
        for method in METHODS:
            left, right = solve(a, [0, 2, 4], method), solve(b, [4, 2, 0], method)
            self.assertEqual(left['edges'], right['edges'])
        self.assertEqual(nx.get_edge_attributes(a, 'weight'), {})

    def test_invalid_inputs_rejected(self):
        for method in METHODS:
            g = nx.path_graph(3)
            for bad in [-1., float('nan'), float('inf')]:
                g[0][1]['weight'] = bad
                with self.assertRaises(ValueError):
                    solve(g, [0, 2], method)
            with self.assertRaises(ValueError):
                solve(nx.path_graph(3), [9], method)
        with self.assertRaises(ValueError):
            solve(nx.path_graph(3), [0, 2], 'not_a_solver')


if __name__ == '__main__':
    unittest.main()
