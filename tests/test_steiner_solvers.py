"""Independent objective checks for approximate and exact Steiner solvers."""
import itertools
from pathlib import Path
import random
import sys
import unittest

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/text2sql'))
try:
    import steiner_solvers as solver
except ModuleNotFoundError:
    solver = None


def brute_force_cost(graph, terminals):
    edges = list(graph.edges(data=True))
    best = float('inf')
    for bits in range(1 << len(edges)):
        candidate = nx.Graph()
        candidate.add_nodes_from(terminals)
        cost = 0
        for i, (a, b, data) in enumerate(edges):
            if bits & (1 << i):
                candidate.add_edge(a, b)
                cost += data.get('weight', 1)
        if cost < best and all(nx.has_path(candidate, terminals[0], t) for t in terminals):
            best = cost
    return best


class SteinerSolverTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(solver, 'paired Steiner solver module is not implemented')

    def test_exact_improves_known_weighted_approximation_counterexample(self):
        graph = nx.Graph()
        graph.add_weighted_edges_from([(0, 1, 5), (0, 2, 5), (1, 2, 5), (0, 3, 3), (1, 3, 3), (2, 3, 3)])
        exact = solver.solve_steiner(graph, [0, 1, 2], 'dreyfus_wagner')
        approximate = solver.solve_steiner(graph, [0, 1, 2], 'mehlhorn')
        self.assertEqual(exact['cost'], 9)
        self.assertEqual(set(exact['nodes']), {0, 1, 2, 3})
        self.assertEqual(approximate['cost'], 10)

    def test_exact_matches_edge_subset_oracle_on_small_graphs(self):
        rng = random.Random(20261108)
        for trial in range(20):
            graph = nx.path_graph(5)
            candidates = [(0, 2), (0, 3), (0, 4), (1, 3), (1, 4), (2, 4)]
            graph.add_edges_from(rng.sample(candidates, 3))
            for a, b in graph.edges:
                graph[a][b]['weight'] = rng.randint(1, 7)
            terminals = rng.sample(list(graph), 4)
            with self.subTest(trial=trial):
                exact = solver.solve_steiner(graph, terminals, 'dreyfus_wagner')
                self.assertEqual(exact['cost'], brute_force_cost(graph, terminals))
                self.assertGreaterEqual(solver.solve_steiner(graph, terminals, 'mehlhorn')['cost'], exact['cost'])

    def test_two_seeds_reduce_to_shortest_path_for_both_solvers(self):
        graph = nx.cycle_graph(7)
        for method in ['mehlhorn', 'dreyfus_wagner']:
            result = solver.solve_steiner(graph, [0, 3], method)
            self.assertEqual(result['cost'], nx.shortest_path_length(graph, 0, 3))

    def test_disconnected_seeds_return_explicit_forest(self):
        graph = nx.path_graph(4)
        graph.add_edge(8, 9)
        for method in ['mehlhorn', 'dreyfus_wagner']:
            result = solver.solve_steiner(graph, [0, 3, 8], method)
            self.assertEqual(result['cost'], 3)
            self.assertEqual(result['seed_components'], 2)
            self.assertFalse(result['connected'])
            self.assertEqual(result['nodes'], [0, 1, 2, 3, 8])

    def test_empty_single_and_zero_weight(self):
        graph = nx.Graph()
        graph.add_weighted_edges_from([(0, 1, 0), (1, 2, 0), (1, 3, 1)])
        for method in ['mehlhorn', 'dreyfus_wagner']:
            self.assertEqual(solver.solve_steiner(graph, [], method)['nodes'], [])
            self.assertEqual(solver.solve_steiner(graph, [2], method)['nodes'], [2])
            self.assertEqual(solver.solve_steiner(graph, [0, 2], method)['cost'], 0)

    def test_node_edge_and_terminal_order_do_not_change_selected_tree(self):
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (1, 4), (3, 4)]
        left, right = nx.Graph(), nx.Graph()
        left.add_edges_from(edges)
        right.add_edges_from(reversed(edges))
        for method in ['mehlhorn', 'dreyfus_wagner']:
            a = solver.solve_steiner(left, [0, 2, 4], method)
            b = solver.solve_steiner(right, [4, 2, 0], method)
            self.assertEqual(a['edges'], b['edges'])

    def test_invalid_weight_terminal_and_method_fail_closed(self):
        graph = nx.path_graph(3)
        for weight in [-1, float('nan'), float('inf')]:
            graph[0][1]['weight'] = weight
            with self.assertRaises(ValueError):
                solver.solve_steiner(graph, [0, 2], 'dreyfus_wagner')
        graph[0][1]['weight'] = 1
        with self.assertRaises(ValueError):
            solver.solve_steiner(graph, [8], 'mehlhorn')
        with self.assertRaises(ValueError):
            solver.solve_steiner(graph, [0, 1], 'unknown')

    def test_independent_three_terminal_oracle_matches_exact(self):
        graph = nx.cycle_graph(6)
        graph.add_edge(0, 3)
        for terminals in itertools.combinations(range(6), 3):
            actual = solver.solve_steiner(graph, terminals, 'dreyfus_wagner')
            self.assertEqual(actual['cost'], solver.small_terminal_optimum(graph, terminals))

    def test_input_graph_is_not_modified_and_output_is_feasible(self):
        graph = nx.cycle_graph(5)
        snapshot = dict(nx.get_edge_attributes(graph, 'weight'))
        for method in ['mehlhorn', 'dreyfus_wagner']:
            result = solver.solve_steiner(graph, [0, 2, 4], method)
            self.assertTrue(set([0, 2, 4]) <= set(result['nodes']))
            selected = nx.Graph()
            selected.add_nodes_from(result['nodes'])
            selected.add_edges_from(result['edges'])
            self.assertTrue(nx.is_tree(selected))
            self.assertTrue(all(graph.has_edge(a, b) for a, b in result['edges']))
        self.assertEqual(snapshot, nx.get_edge_attributes(graph, 'weight'))


if __name__ == '__main__':
    unittest.main()
