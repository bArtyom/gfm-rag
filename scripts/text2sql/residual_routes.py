"""Exact small-k tree alternatives and conditional cosine, without labels."""
import itertools
import networkx as nx
import numpy as np


def tree_catalogue(graph, terminals, limit=100000):
    terminals=sorted(set(terminals))
    if len(terminals)>3 or not set(terminals)<=set(graph):
        raise ValueError('Requires at most three valid terminals')
    groups=[]
    for component in sorted(nx.connected_components(graph),key=lambda c:min(c)):
        local=sorted(set(component)&set(terminals))
        if not local: continue
        if len(local)==1:
            groups.append([{'nodes':local,'edges':[]}]);continue
        root=local[0]
        paths=[list(nx.all_simple_paths(graph,root,t)) for t in local[1:]]
        if any(len(x)>limit for x in paths) or np.prod([len(x) for x in paths])>limit*10:
            raise RuntimeError('Path catalogue enumeration budget exceeded')
        choices={}
        for combination in itertools.product(*paths):
            tree=nx.Graph();tree.add_nodes_from(local)
            for path in combination:tree.add_edges_from(zip(path,path[1:]))
            if not nx.is_tree(tree):continue
            assert all(v in local for v in tree if tree.degree(v)<=1)
            edges=tuple(sorted(tuple(sorted(e)) for e in tree.edges))
            choices[edges]={'nodes':sorted(tree),'edges':[list(e) for e in edges]}
            if len(choices)>limit:raise RuntimeError('Tree catalogue budget exceeded')
        groups.append([choices[key] for key in sorted(choices)])
    if not groups:return [{'nodes':[],'edges':[]}]
    if np.prod([len(g) for g in groups])>limit:raise RuntimeError('Forest catalogue budget exceeded')
    result=[]
    for combination in itertools.product(*groups):
        result.append({'nodes':sorted(v for r in combination for v in r['nodes']),
            'edges':sorted(e for r in combination for e in r['edges'])})
    return result


def residual_scores(query, columns, witness_indices):
    query=np.asarray(query,dtype=np.float64);columns=np.asarray(columns,dtype=np.float64)
    if query.ndim!=1 or columns.ndim!=2 or columns.shape[1]!=len(query):
        raise ValueError('Dimension mismatch')
    qnorm=np.linalg.norm(query);norms=np.linalg.norm(columns,axis=1)
    if qnorm<=0 or (norms<=0).any() or not np.isfinite(query).all() or not np.isfinite(columns).all():
        raise ValueError('Invalid vectors')
    query=query/qnorm;columns=columns/norms[:,None]
    raw=columns@query
    basis=np.empty((0,len(query)))
    if witness_indices:
        _,singular,right=np.linalg.svd(columns[list(witness_indices)],full_matrices=False)
        basis=right[singular>1e-8]
    qres=query-(query@basis.T)@basis
    norm=float(np.linalg.norm(qres))
    if norm<=1e-8:return raw,raw.copy(),norm
    cres=columns-(columns@basis.T)@basis
    cnorm=np.linalg.norm(cres,axis=1)
    residual=np.zeros(len(columns))
    usable=cnorm>1e-8
    residual[usable]=(cres[usable]@qres)/(cnorm[usable]*norm)
    return np.clip(raw,-1,1),np.clip(residual,-1,1),norm


def stage_decision(mode,count,stats,per_database):
    residual=stats['residual']['complete']
    if mode=='smoke':return None,'engineering_smoke_complete'
    if mode=='pilot':
        passed=residual>=stats['frozen']['complete'] and residual>=stats['raw']['complete']+2
        return passed,'unchanged_CPU_full_allowed' if passed else 'STOP_RESIDUAL_ROUTE_CANDIDATE'
    if mode!='full':raise ValueError('Unknown stage')
    passed=all((residual-stats[a]['complete'])*100>=2*count for a in ['frozen','raw'])
    positive=sum(all(v.get('residual_vs_'+a,0)>0 for a in ['frozen','raw']) for v in per_database.values())
    passed=passed and positive>=2
    return passed,'bounded_SQL_followup_eligible' if passed else 'STOP_RESIDUAL_ROUTE_CANDIDATE'
