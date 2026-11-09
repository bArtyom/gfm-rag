import sys
from pathlib import Path
import unittest

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'text2sql'))
from query_weighted_steiner import relation_descriptor, relation_costs, weighted_graph, predict
from steiner_solvers import solve_steiner
from seed_steiner import serialize_schema


class WeightedSteinerTests(unittest.TestCase):
    def setUp(self):
        self.schema = {'table_names_original': ['orders', 'people'],
                       'column_names_original': [[-1, '*'], [0, 'buyer_id'], [0, 'seller_id'], [1, 'id'], [0, 'tenant'], [1, 'tenant']]}
        self.cs = [{'id': 'fk:0:0', 'source_table': 0, 'target_table': 1, 'pairs': [[1, 3], [4, 5]]},
                   {'id': 'fk:0:1', 'source_table': 0, 'target_table': 1, 'pairs': [[2, 3]]}]

    def test_composite_descriptor_preserves_every_pair_without_claiming_business_meaning(self):
        text = relation_descriptor(self.schema, self.cs[0])
        self.assertIn('orders.buyer_id = people.id', text)
        self.assertIn('orders.tenant = people.tenant', text)
        self.assertNotIn('question', text)

    def test_cosine_becomes_positive_cost_in_correct_direction(self):
        costs = relation_costs(np.array([1., 0.]), np.array([[1., 0.], [0., 1.], [-1., 0.]]))
        np.testing.assert_allclose(costs, [1., 1.5, 2.])

    def test_invalid_vectors_rejected(self):
        for bad in [np.array([[0., 0.]]), np.array([[np.nan, 0.]])]:
            with self.assertRaises(ValueError):
                relation_costs(np.array([1., 0.]), bad)

    def test_parallel_edges_keep_best_constraint_identity_and_composite(self):
        g, picked = weighted_graph(2, self.cs, [1.1, 1.9])
        self.assertEqual(picked[(0, 1)]['pairs'], [[1, 3], [4, 5]])
        self.assertEqual(g[0][1]['weight'], 1.1)
        _, reverse = weighted_graph(2, list(reversed(self.cs)), [1.9, 1.1])
        self.assertEqual(picked, reverse)

    def test_unit_and_weighted_topology_identical(self):
        a, _ = weighted_graph(3, self.cs, [1., 1.])
        b, _ = weighted_graph(3, self.cs, [2., 1.1])
        self.assertEqual(set(a), set(b))
        self.assertEqual(set(a.edges), set(b.edges))
        self.assertIn(2, b)

    def test_weighted_semantic_path_can_replace_shorter_unit_path(self):
        g = nx.Graph()
        g.add_weighted_edges_from([(0, 1, 1.9), (1, 3, 1.9), (0, 2, 1.), (2, 4, 1.), (4, 3, 1.)])
        weighted = solve_steiner(g, [0, 3], 'mehlhorn')
        nx.set_edge_attributes(g, 1., 'weight')
        unit = solve_steiner(g, [0, 3], 'mehlhorn')
        self.assertEqual(weighted['nodes'], [0, 2, 3, 4])
        self.assertEqual(unit['nodes'], [0, 1, 3])

    def test_bad_constraint_cost_alignment_and_negative_cost_rejected(self):
        for costs in [[1.], [1., -1.], [1., float('inf')]]:
            with self.assertRaises(ValueError):
                weighted_graph(2, self.cs, costs)

    def test_prediction_retains_seeds_matches_dense_size_and_never_mutates_input(self):
        schema = {'table_names_original': ['a', 'b', 'c', 'd']}
        cs = [{'id': str(i), 'source_table': a, 'target_table': b, 'pairs': []}
              for i, (a, b) in enumerate([(0, 1), (1, 3), (0, 2), (2, 3)])]
        result = predict(schema, cs, [0, 3, 2, 1], np.array([1., 0.]),
                         np.array([[-1., 0.], [-1., 0.], [1., 0.], [1., 0.]]), 2)
        self.assertEqual(result['arms']['weighted']['nodes'], [0, 2, 3])
        self.assertEqual(len(result['arms']['dense']['nodes']), 3)
        self.assertEqual(result['seeds'], [0, 3])
        self.assertTrue(result['alternative_route'])
        self.assertEqual(cs[0]['id'], '0')

    def test_unique_route_and_disconnected_seeds(self):
        cs = [{'id': 'x', 'source_table': 0, 'target_table': 1, 'pairs': []}]
        result = predict({'table_names_original': ['a', 'b', 'c']}, cs, [0, 1, 2],
                         np.array([1.]), np.array([[1.]]), 3)
        self.assertFalse(result['alternative_route'])
        self.assertFalse(result['arms']['weighted']['connected'])
        self.assertEqual(result['arms']['weighted']['nodes'], [0, 1, 2])

    def test_schema_token_serialization_accepts_nested_composite_primary_keys(self):
        schema = {**self.schema, 'primary_keys': [[1, 4], 3], 'column_types': ['text'] * 6}
        text = serialize_schema(schema, [0, 1], self.cs)
        self.assertIn('PRIMARY KEY ("buyer_id", "tenant")', text)
        self.assertIn('FOREIGN KEY ("buyer_id", "tenant")', text)


if __name__ == '__main__':
    unittest.main()
