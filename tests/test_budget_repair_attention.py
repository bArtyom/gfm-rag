from pathlib import Path
import sys
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/text2sql'))
from budget_repair_attention import BudgetScorer,feasible_repair


def test_global_scorer_is_permutation_equivariant():
    torch.manual_seed(17);m=BudgetScorer('global',input_size=12,hidden=8,heads=2).eval()
    torch.nn.init.normal_(m.head.weight,std=.2)
    features=torch.randn(6,12);types=torch.tensor([0,1,1,0,1,1]);base=torch.randn(6);perm=torch.tensor([3,0,5,1,4,2])
    with torch.no_grad():assert torch.allclose(m(features[perm],types[perm],base[perm]),m(features,types,base)[perm],atol=1e-6)


def test_independent_score_ignores_other_nodes_but_global_can_change():
    for kind in ['independent','global']:
        torch.manual_seed(13);m=BudgetScorer(kind,input_size=12,hidden=8,heads=2).eval();torch.nn.init.normal_(m.head.weight,std=.2)
        x=torch.randn(4,12);t=torch.tensor([0,1,1,1]);b=torch.zeros(4);y=x.clone();y[3]+=5
        a=m(x,t,b)[0];c=m(y,t,b)[0]
        assert bool(torch.isclose(a,c,atol=1e-6))==(kind=='independent')


def test_repair_fits_budget_and_never_drops_already_retained_required_binding():
    def expand(cols):return {'columns':sorted(set(cols)),'tables':[0],'constraints':[]}
    def cost(r):return len(r['columns'])
    r=feasible_repair([1,2,3],{1:.1,2:.2,3:.3,4:-.1},{3,4},{0},3,expand,cost)
    assert r and r['added']==4 and r['removed']==[1] and set(r['repaired_columns'])=={2,3,4}
    assert r['binding_gain']==1 and r['tokens']<=3


def test_no_repair_when_removing_distractor_loses_required_count_table():
    def expand(cols):return {'columns':sorted(set(cols)),'tables':sorted({0 if c==1 else 1 for c in cols}),'constraints':[]}
    r=feasible_repair([1,2],{1:.1,2:.2,3:-.1},{2,3},{0,1},2,expand,lambda r:len(r['columns']))
    assert r is None


def test_budget_certificate_uses_actual_closure_not_number_of_columns():
    def expand(cols):
        cols=set(cols)
        if 3 in cols:cols.add(4)
        return {'columns':sorted(cols),'tables':[0],'constraints':[]}
    r=feasible_repair([1,2],{1:.1,2:.2,3:-1},{3},{0},2,expand,lambda r:len(r['columns']))
    assert r and r['removed']==[1,2] and r['repaired_columns']==[3,4]
