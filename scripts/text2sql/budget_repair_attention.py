"""Contextual graph-vector scorers and auditable budget-feasible repair targets."""
import torch
from torch import nn


class BudgetScorer(nn.Module):
    def __init__(self,kind,input_size=4096,hidden=96,heads=4):
        super().__init__();self.kind=kind
        self.projection=nn.Linear(input_size,hidden);self.types=nn.Embedding(2,hidden)
        self.norm1=nn.LayerNorm(hidden);self.norm2=nn.LayerNorm(hidden);self.finalnorm=nn.LayerNorm(hidden)
        if kind=='global':
            self.attention=nn.MultiheadAttention(hidden,heads,dropout=0,batch_first=True)
            self.ff=nn.Sequential(nn.Linear(hidden,hidden*2),nn.GELU(),nn.Linear(hidden*2,hidden))
        elif kind=='independent':self.ff=nn.Sequential(nn.Linear(hidden,hidden*4),nn.GELU(),nn.Linear(hidden*4,hidden))
        else:raise ValueError('Unknown scorer type')
        self.head=nn.Linear(hidden,1);nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)

    def forward(self,features,types,base):
        x=self.projection(features)+self.types(types)
        if self.kind=='global':
            z=self.norm1(x).unsqueeze(0);context,_=self.attention(z,z,z,need_weights=False)
            x=x+context.squeeze(0);x=x+self.ff(self.norm2(x))
        else:x=x+self.ff(self.norm1(x))
        return base+self.head(self.finalnorm(x)).squeeze(-1)


def balanced_loss(scores,labels,types):
    losses=[]
    for kind in [0,1]:
        indexes=types==kind;target=labels[indexes];logits=scores[indexes];terms=[]
        if (target==1).any():terms.append(torch.nn.functional.softplus(-logits[target==1]).mean())
        if (target==0).any():terms.append(torch.nn.functional.softplus(logits[target==0]).mean())
        if terms:losses.append(torch.stack(terms).mean())
    return torch.stack(losses).mean()


def feasible_repair(semantic,scores,required_columns,required_tables,budget,expand,cost):
    """One omitted field, greedy distractor removals, protected current bindings."""
    semantic=list(semantic);initial=expand(semantic);needed=set(required_columns)
    missing=needed-set(initial['columns'])
    if not missing:return None
    added=min(missing,key=lambda c:(scores[c],c));work=semantic+[added]
    protected_columns=needed&set(initial['columns']);protected_tables=set(required_tables)&set(initial['tables'])
    removed=[];candidate=expand(work)
    if cost(candidate)<=budget:return None  # This experiment requires a nontrivial exchange.
    for column in sorted(set(semantic)-needed,key=lambda c:(scores[c],c)):
        trial=[c for c in work if c!=column];next_state=expand(trial)
        if not protected_columns<=set(next_state['columns']) or not protected_tables<=set(next_state['tables']):continue
        work=trial;candidate=next_state;removed.append(column)
        if cost(candidate)<=budget:
            assert added in candidate['columns'] and protected_columns<=set(candidate['columns']) and protected_tables<=set(candidate['tables'])
            return dict(added=added,removed=removed,repaired_semantic=sorted(work),repaired_columns=candidate['columns'],
                repaired_tables=candidate['tables'],tokens=int(cost(candidate)),
                binding_gain=len(needed&set(candidate['columns']))-len(needed&set(initial['columns'])))
    return None
