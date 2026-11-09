"""Five deterministic Steiner solvers; MILP status is never substituted by DP."""
from __future__ import annotations
import math
import time
import warnings

import networkx as nx
import numpy as np
from networkx.algorithms.approximation import steiner_tree
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from steiner_solvers import canonical_graph, exact_connected_tree, prune_tree

METHODS = ['greedy', 'kou', 'mehlhorn', 'dreyfus_wagner', 'milp']


class UncertifiedMILP(RuntimeError):
    def __init__(self, certificate):
        self.certificate = certificate
        super().__init__('MILP did not certify an optimum: ' + str(certificate['status']))


def greedy_tree(graph, terminals):
    tree = nx.Graph()
    tree.add_node(min(terminals))
    while not set(terminals) <= set(tree):
        distances, paths = nx.multi_source_dijkstra(graph, sorted(tree), weight='weight')
        target = min(set(terminals) - set(tree), key=lambda t: (distances[t], t))
        path = paths[target]
        for a, b in zip(path, path[1:]):
            tree.add_edge(a, b, weight=graph[a][b]['weight'])
    return prune_tree(tree, terminals)


def milp_tree(graph, terminals, time_limit):
    """Undirected binary edge selection + rooted single-commodity continuous flow."""
    nodes = sorted(graph)
    node_pos = {n: i for i, n in enumerate(nodes)}
    edges = sorted((min(a, b), max(a, b)) for a, b in graph.edges)
    n, m = len(nodes), len(edges)
    capacity = len(terminals) - 1
    objective = np.zeros(3 * m)
    objective[:m] = [graph[a][b]['weight'] for a, b in edges]
    integrality = np.zeros(3 * m, dtype=np.uint8)
    integrality[:m] = 1
    row, col, values = [], [], []
    for ei, (a, b) in enumerate(edges):
        for direction, (u, v) in enumerate([(a, b), (b, a)]):
            arc = m + 2 * ei + direction
            coupling = n + 2 * ei + direction
            row.extend([node_pos[u], node_pos[v], coupling, coupling])
            col.extend([arc, arc, arc, ei])
            values.extend([1., -1., 1., -float(capacity)])
    matrix = coo_matrix((values, (row, col)), shape=(n + 2 * m, 3 * m)).tocsc()
    balance = np.zeros(n)
    balance[node_pos[min(terminals)]] = capacity
    for t in sorted(terminals):
        if t != min(terminals):
            balance[node_pos[t]] = -1
    lower = np.concatenate([balance, np.full(2 * m, -np.inf)])
    upper = np.concatenate([balance, np.zeros(2 * m)])
    bounds = Bounds(np.zeros(3 * m), np.concatenate([np.ones(m), np.full(2 * m, capacity)]))
    # SciPy1.16 passes unknown HiGHS options through. Suppress only this documented
    # forwarding warning for threads=1; other warnings/errors remain visible.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Unrecognized options detected:.*threads.*', category=RuntimeWarning)
        result = milp(objective, integrality=integrality, bounds=bounds,
            constraints=LinearConstraint(matrix, lower, upper),
            options={'presolve': True, 'time_limit': float(time_limit), 'mip_rel_gap': 0., 'threads': 1})
    def finite(value):
        return float(value) if value is not None and np.isfinite(value) else None
    certificate = {'status': int(result.status), 'success': bool(result.success),
        'primal_objective': finite(result.fun), 'mip_dual_bound': finite(getattr(result, 'mip_dual_bound', None)),
        'mip_gap': finite(getattr(result, 'mip_gap', None)),
        'mip_node_count': int(result.mip_node_count) if getattr(result, 'mip_node_count', None) is not None else None,
        'message': str(result.message), 'threads': 1, 'relative_gap_requested': 0.,
        'root': min(terminals), 'terminals': sorted(terminals)}
    if (result.status != 0 or not result.success or result.x is None or
        certificate['mip_gap'] is None or certificate['mip_gap'] > 1e-8 or
        certificate['mip_dual_bound'] is None or certificate['primal_objective'] is None):
        raise UncertifiedMILP(certificate)
    x = np.asarray(result.x)
    if not np.isfinite(x).all():
        raise RuntimeError('Nonfinite MILP primal')
    ax = matrix @ x
    violation = max(0., float(np.max(lower - ax)), float(np.max(ax - upper)),
        float(np.max(bounds.lb - x)), float(np.max(x - bounds.ub)))
    integer_error = float(np.max(np.abs(x[:m] - np.rint(x[:m]))))
    if violation > 1e-6 or integer_error > 1e-6:
        raise RuntimeError('MILP primal feasibility/integrality validation failed')
    chosen = nx.Graph()
    chosen.add_nodes_from(terminals)
    for i, (a, b) in enumerate(edges):
        if x[i] > .5:
            chosen.add_edge(a, b, weight=graph[a][b]['weight'])
    if not nx.is_connected(chosen):
        raise RuntimeError('MILP selected edges do not connect terminals')
    tree = prune_tree(chosen, terminals)
    cost = tree.size(weight='weight')
    if not math.isclose(cost, result.fun, rel_tol=1e-8, abs_tol=1e-7) or not math.isclose(cost, certificate['mip_dual_bound'], rel_tol=1e-8, abs_tol=1e-7):
        raise RuntimeError('MILP certificate and reconstructed cost differ')
    certificate.update({'max_primal_violation': violation, 'max_binary_integrality_error': integer_error})
    return tree, certificate


def solve(graph, terminals, method, time_limit=10.):
    started = time.perf_counter()
    if method not in METHODS or not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError('Invalid method or time limit')
    graph = canonical_graph(graph)
    terminals = sorted(set(terminals))
    if not set(terminals) <= set(graph):
        raise ValueError('Unknown terminal')
    forest = nx.Graph()
    forest.add_nodes_from(terminals)
    certificates = []
    seed_components = 0
    for component in sorted(nx.connected_components(graph), key=lambda c: min(c)):
        seeds = sorted(set(component) & set(terminals))
        if not seeds:
            continue
        seed_components += 1
        if len(seeds) < 2:
            continue
        local = canonical_graph(graph.subgraph(component))
        if method == 'greedy':
            tree = greedy_tree(local, seeds)
        elif method in ['kou', 'mehlhorn']:
            tree = prune_tree(steiner_tree(local, seeds, weight='weight', method=method), seeds)
        elif method == 'dreyfus_wagner':
            tree, optimum = exact_connected_tree(local, seeds)
            if not math.isclose(tree.size(weight='weight'), optimum, abs_tol=1e-8):
                raise RuntimeError('DP reconstruction cost differs')
        else:
            tree, proof = milp_tree(local, seeds, time_limit)
            certificates.append(proof)
        if not set(seeds) <= set(tree) or not nx.is_tree(tree):
            raise RuntimeError('Invalid Steiner component')
        forest.add_nodes_from(tree.nodes)
        forest.add_edges_from(tree.edges(data=True))
    if forest and not nx.is_forest(forest):
        raise RuntimeError('Invalid forest')
    if any(not graph.has_edge(a, b) for a, b in forest.edges):
        raise RuntimeError('Fabricated edge')
    return {'nodes': sorted(forest), 'edges': sorted([min(a, b), max(a, b)] for a, b in forest.edges),
        'cost': float(forest.size(weight='weight')), 'connected': seed_components <= 1,
        'seed_components': seed_components, 'elapsed_seconds': time.perf_counter() - started,
        'certified_optimal': method in ['dreyfus_wagner', 'milp'], 'certificates': certificates,
        'status': 'optimal' if method in ['dreyfus_wagner', 'milp'] else 'feasible_heuristic'}
