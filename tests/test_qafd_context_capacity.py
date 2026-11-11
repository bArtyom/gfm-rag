from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/text2sql'))
from qafd_context_capacity import cost_capacities, feasible_diffusion


def test_marginal_costs_cover_interaction_and_all_subsets():
    costs=np.array([0,2,3,9,1,4,5,12])
    caps=cost_capacities(costs,3)
    assert np.array_equal(caps,[7,8,3])
    for mask,cost in enumerate(costs):assert cost<=sum(caps[t] for t in range(3) if mask>>t&1)


def test_push_mass_conservation_kkt_and_support_cost():
    w=np.array([[0,1,0],[1,0,1],[0,1,0]],dtype=float)
    cap=np.array([1.,2.,3.]);delta=np.array([3.,0.,0.])
    result=feasible_diffusion(w,cap,delta)
    assert np.isclose(sum(result['mass']),3)
    assert result['excess']<=1e-7
    assert sum(cap[i] for i,x in enumerate(result['x']) if x>0)<=3+1e-7
    assert np.allclose(np.array(result['mass']),delta-(np.diag(w.sum(axis=1))-w)@result['x'])


def test_infeasible_or_disconnected_sources_rejected():
    import pytest
    w=np.array([[0,1,0],[1,0,0],[0,0,0]],dtype=float)
    with pytest.raises(ValueError):feasible_diffusion(w,np.ones(3),np.array([2.1,0,0]))
    with pytest.raises(ValueError):feasible_diffusion(w,np.ones(3),np.array([0,0,1.1]))


def test_no_warmstart_support_when_no_capacity_is_exceeded():
    r=feasible_diffusion(np.array([[0.,1],[1,0]]),np.ones(2),np.array([.5,0]))
    assert r['x']==[0.,0.] and r['updates']==0
