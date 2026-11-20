"""Posthoc algebraic zero-head baseline; no graph or language-model forwards."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np
import torch
from run_budget_repair_attention import Runtime
from run_seed_steiner import read_config,load_inputs,new_output,write_json,sha256
from closure_budget_order import expressibility,reference_read_bindings
from steiner_sql_runtime import read_reference_rows


def main():
    p=argparse.ArgumentParser()
    for n in ['config','execution','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();new_output(a.output);began=time.monotonic();c=read_config(a.config);inp=load_inputs(c);rt=Runtime(c,inp)
    summary=json.loads((a.execution/'aggregate_summary.json').read_text());assert sha256(a.execution/'predictions_private.json')==summary['prediction_sha256'];rows=json.loads((a.execution/'predictions_private.json').read_text())
    initial=torch.load(a.execution/'global_initial.pt',map_location='cpu',weights_only=True);assert not initial['head.weight'].count_nonzero() and not initial['head.bias'].count_nonzero()
    states=[]
    for row in rows:
        db=row['db_id'];q=inp['queries'][rt.qi[(db,row['question_id'])]];raw=rt.meta[db]['vectors']@q
        states.append(dict(db_id=db,question_id=row['question_id'],selection=rt.pack(row,rt.field_scores(db,raw))))
    write_json(a.output/'predictions_private.json',states);seal=sha256(a.output/'predictions_private.json')
    references={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(c)};counts=Counter();paired=Counter()
    for row,state in zip(rows,states):
        db=row['db_id'];s=inp['schemas'][db];sql=references[(db,row['question_id'])];full=expressibility(sql,s,[i for i,(t,n) in enumerate(s['column_names_original']) if t>=0]);bind=reference_read_bindings(sql,s) if full['status']=='compatible' else dict(status='unknown');supported=full['status']=='compatible' and bind['status']=='ok';r=state['selection']
        correct=supported and set(bind['columns'])<=set(r['columns']) and set(bind['tables'])<=set(r['tables']);repair=row['arms']['repair'];better=supported and set(bind['columns'])<=set(repair['columns']) and set(bind['tables'])<=set(repair['tables'])
        counts.update(questions=1,evaluable=int(supported),complete_read_bindings=int(correct),unknown=int(not supported),tokens=r['tokens'],columns=len(r['columns']),tables=len(r['tables']),budget_violations=int(r['tokens']>row['budget']))
        paired['unknown' if not supported else 'rescue' if better and not correct else 'damage' if correct and not better else 'unchanged']+=1
    out=dict(status='exploratory posthoc diagnostic; primary gate unchanged',arm='untrained_algebraic_initial_score',counts=dict(counts),repair_vs_initial=dict(paired),prediction_sha256=seal,graph_forward_calls=0,new_language_model_calls=0,wall_seconds=time.monotonic()-began)
    write_json(a.output/'aggregate_summary.json',out);print(json.dumps(out,indent=2))


if __name__=='__main__':main()
