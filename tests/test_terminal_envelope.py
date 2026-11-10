import itertools
from pathlib import Path
import sys
import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/text2sql'))
from terminal_envelope import terminal_envelope


def enumerated(graph, terminals):
    result = set(terminals)
    for a, b in itertools.combinations(terminals, 2):
        for path in nx.all_simple_paths(graph, a, b):
            result.update(path)
    return result


def test_branch_cannot_be_recovered_by_edge_reweighting():
    graph = nx.Graph([(0, 1), (1, 2), (1, 3), (3, 4)])
    assert terminal_envelope(graph, [0, 2]) == {0, 1, 2}
    assert terminal_envelope(graph, [0, 2, 4]) == {0, 1, 2, 3, 4}


def test_cycles_and_unseeded_components():
    graph = nx.Graph([(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (4, 5), (5, 3), (6, 7)])
    assert terminal_envelope(graph, [0, 1, 6]) == {0, 1, 2, 6}
    assert terminal_envelope(graph, [0, 4]) == set(range(6))


def test_block_algorithm_matches_independent_simple_path_enumeration():
    for seed in range(40):
        graph = nx.gnp_random_graph(7, .32, seed=seed)
        for terminals in [(0,), (0, 6), (0, 3, 6), ()]:
            assert terminal_envelope(graph, terminals) == enumerated(graph, terminals)
