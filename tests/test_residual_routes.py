import itertools
from pathlib import Path
import sys
import networkx as nx
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/text2sql'))
from residual_routes import tree_catalogue, residual_scores, stage_decision


def test_catalogue_matches_edge_subset_oracle():
    for seed in range(15):
        graph=nx.gnp_random_graph(5,.45,seed=seed)
        if not nx.is_connected(graph): continue
        terminals=[0,2,4]
        expected=set()
        edges=list(graph.edges)
        for mask in range(1<<len(edges)):
            candidate=nx.Graph();candidate.add_nodes_from(terminals)
            candidate.add_edges_from(e for i,e in enumerate(edges) if mask>>i&1)
            if nx.is_tree(candidate) and all(v in terminals for v in candidate if candidate.degree(v)<=1):
                expected.add(tuple(sorted(tuple(sorted(e)) for e in candidate.edges)))
        actual={tuple(map(tuple,r['edges'])) for r in tree_catalogue(graph,terminals)}
        assert actual==expected


def test_disconnected_forest_catalogue_and_singleton():
    graph=nx.Graph([(0,1),(1,2),(0,2)]);graph.add_node(3)
    result=tree_catalogue(graph,[0,2,3])
    assert len(result)==2
    assert all(3 in r['nodes'] for r in result)
    assert tree_catalogue(graph,[3])==[{'nodes':[3],'edges':[]}]


def test_residual_removes_explained_component_and_is_rotation_invariant():
    query=np.array([1.,1.,0.])/np.sqrt(2)
    columns=np.array([[1.,0.,0.],[.99,.01,0.],[0.,1.,0.]])
    raw,residual,norm=residual_scores(query,columns,[0])
    assert raw[1]>raw[2] and residual[1]==residual[2]
    assert np.isclose(norm,1/np.sqrt(2))
    rotation=np.linalg.qr(np.random.default_rng(1).normal(size=(3,3)))[0]
    rotated=residual_scores(query@rotation,columns@rotation,[0])
    assert np.allclose(residual,rotated[1])


def test_fully_explained_query_falls_back_without_nan():
    raw,residual,norm=residual_scores(np.array([1.,0.]),np.eye(2),[0])
    assert norm<1e-8 and np.array_equal(raw,residual)


def test_stage_specific_gates_do_not_repeat_full_or_skip_multidatabase_check():
    stats={'residual':{'complete':84},'frozen':{'complete':82},'raw':{'complete':82}}
    one={'DB1':{'residual_vs_frozen':2,'residual_vs_raw':2}}
    two={d:{'residual_vs_frozen':1,'residual_vs_raw':1} for d in ['DB1','DB2']}
    assert stage_decision('pilot',100,stats,one)==(True,'unchanged_CPU_full_allowed')
    assert stage_decision('full',100,stats,one)==(False,'STOP_RESIDUAL_ROUTE_CANDIDATE')
    assert stage_decision('full',100,stats,two)==(True,'bounded_SQL_followup_eligible')
    assert stage_decision('full',1534,stats,two)[0] is False
