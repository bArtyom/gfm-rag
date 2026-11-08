"""Deterministic approximate/exact Steiner forests on nonnegative table graphs."""
from __future__ import annotations

import math
import time

import networkx as nx
from networkx.algorithms.approximation import steiner_tree


def canonical_graph(graph):
    if graph.is_directed() or graph.is_multigraph():
        raise ValueError('Expected a simple undirected graph')
    result = nx.Graph()
    result.add_nodes_from(sorted(graph.nodes))
    edges = []
    for a, b, data in graph.edges(data=True):
        weight = float(data.get('weight', 1))
        if not math.isfinite(weight) or weight < 0:
            raise ValueError('Edge weights must be finite and nonnegative')
        if a != b:
            edges.append((min(a, b), max(a, b), weight))
    result.add_weighted_edges_from(sorted(edges))
    return result


def prune_tree(graph, terminals):
    tree = nx.minimum_spanning_tree(canonical_graph(graph), weight='weight')
    required = set(terminals)
    while True:
        leaves = [v for v in sorted(tree) if v not in required and tree.degree(v) <= 1]
        if not leaves:
            return tree
        tree.remove_nodes_from(leaves)


def exact_connected_tree(graph, terminals):
    """Dreyfus–Wagner recurrence with explicit path/subset reconstruction."""
    terminals = sorted(set(terminals))
    if not terminals or len(terminals) == 1:
        tree = nx.Graph()
        tree.add_nodes_from(terminals)
        return tree, 0.0
    if len(terminals) > 12:
        raise ValueError('Exact DP terminal budget exceeded')
    nodes = sorted(graph)
    shortest = {v: nx.single_source_dijkstra(graph, v, weight='weight') for v in nodes}
    full = (1 << len(terminals)) - 1
    dp, trace = {}, {}
    for index, terminal in enumerate(terminals):
        mask = 1 << index
        dp[mask] = {v: shortest[terminal][0][v] for v in nodes}
    for mask in range(1, full + 1):
        if mask & (mask - 1) == 0:
            continue
        merged, partition = {}, {}
        for v in nodes:
            best = (float('inf'), None)
            sub = (mask - 1) & mask
            while sub:
                complement = mask ^ sub
                if sub < complement:
                    candidate = (dp[sub][v] + dp[complement][v], sub)
                    if candidate < best:
                        best = candidate
                sub = (sub - 1) & mask
            merged[v], partition[v] = best
        dp[mask], trace[mask] = {}, {}
        for v in nodes:
            cost, meeting = min((merged[u] + shortest[u][0][v], u) for u in nodes)
            dp[mask][v] = cost
            trace[mask][v] = (meeting, partition[meeting])
    optimum, root = min((dp[full][v], v) for v in nodes)
    union = nx.Graph()
    union.add_nodes_from(terminals)

    def add_path(a, b):
        path = shortest[a][1][b]
        for u, v in zip(path, path[1:]):
            union.add_edge(u, v, weight=graph[u][v]['weight'])

    def reconstruct(mask, endpoint):
        if mask & (mask - 1) == 0:
            terminal = terminals[mask.bit_length() - 1]
            add_path(terminal, endpoint)
            return
        meeting, sub = trace[mask][endpoint]
        add_path(meeting, endpoint)
        reconstruct(sub, meeting)
        reconstruct(mask ^ sub, meeting)

    reconstruct(full, root)
    tree = prune_tree(union, terminals)
    actual = tree.size(weight='weight')
    if not math.isclose(actual, optimum, rel_tol=1e-9, abs_tol=1e-9):
        raise RuntimeError('Reconstructed tree cost does not match exact DP')
    return tree, float(optimum)


def solve_steiner(graph, terminals, method):
    started = time.perf_counter()
    if method not in {'mehlhorn', 'dreyfus_wagner'}:
        raise ValueError('Unknown solver')
    graph = canonical_graph(graph)
    terminals = sorted(set(terminals))
    if not set(terminals) <= set(graph):
        raise ValueError('Unknown terminal')
    forest = nx.Graph()
    forest.add_nodes_from(terminals)
    component_count = 0
    optimum = 0.0
    for component in sorted(nx.connected_components(graph), key=lambda comp: min(comp)):
        seeds = sorted(set(component) & set(terminals))
        if not seeds:
            continue
        component_count += 1
        if len(seeds) < 2:
            continue
        local = canonical_graph(graph.subgraph(component))
        if method == 'mehlhorn':
            tree = prune_tree(steiner_tree(local, seeds, weight='weight', method='mehlhorn'), seeds)
        else:
            tree, local_optimum = exact_connected_tree(local, seeds)
            optimum += local_optimum
        if not set(seeds) <= set(tree) or not nx.is_tree(tree):
            raise RuntimeError('Solver returned an infeasible tree')
        forest.add_nodes_from(tree.nodes)
        forest.add_edges_from(tree.edges(data=True))
    if forest and not nx.is_forest(forest):
        raise RuntimeError('Solver returned cyclic forest')
    cost = float(forest.size(weight='weight'))
    if method == 'dreyfus_wagner' and not math.isclose(cost, optimum, abs_tol=1e-9):
        raise RuntimeError('Forest objective differs from DP optimum')
    if any(not graph.has_edge(a, b) for a, b in forest.edges):
        raise RuntimeError('Fabricated edge')
    return {'nodes': sorted(forest.nodes), 'edges': sorted([min(a, b), max(a, b)] for a, b in forest.edges),
            'cost': cost, 'seed_components': component_count, 'connected': component_count <= 1,
            'elapsed_seconds': time.perf_counter() - started}


def small_terminal_optimum(graph, terminals):
    """Independent distance/meeting-point identity for <=3 terminals per component."""
    terminals = set(terminals)
    if len(terminals) > 3 or not terminals <= set(graph):
        raise ValueError('Oracle requires up to three known terminals')
    total = 0.0
    for component in nx.connected_components(graph):
        seeds = sorted(component & terminals)
        if len(seeds) < 2:
            continue
        distances = [nx.single_source_dijkstra_path_length(graph, t, weight='weight') for t in seeds]
        if len(seeds) == 2:
            total += distances[0][seeds[1]]
        else:
            total += min(sum(dist[v] for dist in distances) for v in component)
    return float(total)
