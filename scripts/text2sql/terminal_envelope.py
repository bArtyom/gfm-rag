"""All vertices on some simple terminal-to-terminal path, per graph component."""
from collections import deque
import networkx as nx


def terminal_envelope(graph, terminals):
    if graph.is_directed() or graph.is_multigraph():
        raise ValueError('A simple undirected graph is required')
    required = set(terminals)
    if not required <= set(graph):
        raise ValueError('Unknown terminal')
    incidence = nx.Graph()
    incidence.add_nodes_from(('v', v) for v in graph)
    blocks = list(nx.biconnected_components(graph))
    for index, vertices in enumerate(blocks):
        incidence.add_edges_from((('b', index), ('v', v)) for v in vertices)
    assert nx.is_forest(incidence)
    pinned = {('v', v) for v in required}
    queue = deque(v for v in incidence if incidence.degree(v) <= 1 and v not in pinned)
    while queue:
        v = queue.popleft()
        if v not in incidence or v in pinned or incidence.degree(v) > 1:
            continue
        neighbors = list(incidence[v])
        incidence.remove_node(v)
        queue.extend(neighbors)
    result = set(required)
    for kind, index in incidence:
        if kind == 'b':
            result.update(blocks[index])
    return result
