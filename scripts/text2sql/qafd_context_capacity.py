"""Cost-certified capacities and feasible paper-dual diffusion; no model calls."""
import importlib.util
import logging
from pathlib import Path
import sys
import types

import networkx as nx
import numpy as np


def load_upstream_core(path):
    """Load unchanged external core/base, replacing only package service imports."""
    path=Path(path)/'src';name='_external_qafd_core'
    for package,folder in [(name,path),(name+'.retrievers',path/'retrievers')]:
        module=types.ModuleType(package);module.__path__=[str(folder)];sys.modules[package]=module
    utilities=types.ModuleType(name+'.utils');utilities.logger=logging.getLogger('qafd_external_core')
    sys.modules[name+'.utils']=utilities
    for label,file in [('base',path/'retrievers/base.py'),('flow_diffusion',path/'retrievers/flow_diffusion.py')]:
        fullname=name+'.retrievers.'+label
        spec=importlib.util.spec_from_file_location(fullname,file);module=importlib.util.module_from_spec(spec)
        sys.modules[fullname]=module;spec.loader.exec_module(module)
    return module.FlowDiffusionRetriever


def cost_capacities(subset_costs,count):
    costs=np.asarray(subset_costs,dtype=float)
    if costs.shape!=(1<<count,) or costs[0]!=0 or not np.isfinite(costs).all() or (costs<0).any():
        raise ValueError('Expected nonnegative exact subset costs and empty cost0')
    caps=[]
    for table in range(count):
        bit=1<<table
        caps.append(max(1.,max(costs[mask|bit]-costs[mask] for mask in range(len(costs)) if not mask&bit)))
    return np.asarray(caps)


def feasible_diffusion(weights,capacities,injection,tolerance=1e-7,max_updates=100000):
    w=np.asarray(weights,dtype=float);cap=np.asarray(capacities,dtype=float);delta=np.asarray(injection,dtype=float)
    n=len(cap)
    if w.shape!=(n,n) or delta.shape!=(n,) or not np.isfinite(w).all() or not np.isfinite(cap).all() or not np.isfinite(delta).all():
        raise ValueError('Invalid flow dimensions/values')
    if (cap<=0).any() or (delta<0).any() or (w<0).any() or not np.allclose(w,w.T) or np.any(np.diag(w)):
        raise ValueError('Positive capacities, nonnegative symmetric conductances required')
    graph=nx.from_numpy_array(w)
    for component in nx.connected_components(graph):
        ids=sorted(component)
        if delta[ids].sum()>0 and delta[ids].sum()>=cap[ids].sum():
            raise ValueError('Injected mass must be below reachable total capacity')
    mass=delta.copy();x=np.zeros(n);degree=w.sum(axis=1);updates=0
    while float(np.maximum(0,mass-cap).sum())>tolerance:
        if updates>=max_updates:raise RuntimeError('Feasible diffusion did not converge within budget')
        v=int(np.argmax(mass-cap));excess=mass[v]-cap[v]
        if degree[v]<=0:raise RuntimeError('Isolated excess mass')
        x[v]+=excess/degree[v]
        mass[v]=cap[v]
        mass+=excess*w[v]/degree[v]
        updates+=1
    support=x>0
    if np.any(mass[support]<cap[support]-1e-6) or not np.isclose(mass.sum(),delta.sum(),atol=1e-6):
        raise RuntimeError('Mass/support invariant failed')
    residual=delta-(np.diag(degree)-w)@x
    if not np.allclose(mass,residual,atol=1e-6):raise RuntimeError('Primal-dual identity failed')
    if cap[support].sum()>delta.sum()+1e-6:raise RuntimeError('Support capacity certificate failed')
    return dict(x=x.tolist(),mass=mass.tolist(),updates=updates,excess=float(np.maximum(0,mass-cap).sum()),
        injected_mass=float(delta.sum()),support_capacity=float(cap[support].sum()),
        mass_error=float(abs(mass.sum()-delta.sum())),primal_dual_error=float(np.max(abs(mass-residual))))


def pack_scores(scores,dense,costs,budget):
    order=sorted(range(len(scores)),key=lambda t:(-float(scores[t]),-float(dense[t]),t))
    mask=0
    for t in order:
        if costs[mask|1<<t]<=budget:mask|=1<<t
    return sorted(t for t in range(len(scores)) if mask>>t&1)
