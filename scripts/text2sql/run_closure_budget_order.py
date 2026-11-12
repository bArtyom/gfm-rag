"""Bounded no-inference closure-before-budget intervention with sealed predictions."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sqlite3
import subprocess
import sys
import time

import numpy as np
from transformers import AutoTokenizer
from closure_budget_order import SchemaClosure,serialize_partial,select_columns,expressibility
from qafd_context_capacity import pack_scores
from run_seed_steiner import read_config,load_inputs,new_output,sha256,write_json
from seed_steiner import serialize_schema,reference_tables
from steiner_sql_runtime import read_reference_rows

ARMS=['whole_dense','late_closure','early_closure']


def sample_cases(questions,excluded,salt,count=100):
    groups=defaultdict(list)
    for row in questions:
        if (row['db_id'],row['question_id']) not in excluded:groups[row['db_id']].append(row)
    for db in groups:groups[db].sort(key=lambda r:hashlib.sha256(f'{salt}:{db}:{r["question_id"]}'.encode()).hexdigest())
    result=[]
    while len(result)<count and any(groups.values()):
        for db in sorted(groups):
            if groups[db] and len(result)<count:result.append(groups[db].pop(0))
    assert len(result)==count
    return result


def main():
    p=argparse.ArgumentParser()
    for k in ['config','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--mode',choices=['smoke','pilot','confirmation'],required=True)
    p.add_argument('--previous-pilot',type=Path)
    args=p.parse_args();os.umask(0o077);new_output(args.output);cfg=read_config(args.config);began=time.monotonic()
    write_json(args.output/'run_start.json',dict(started_at_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),config_sha256=sha256(args.config),
        python=sys.version,executable=sys.executable,sqlite=sqlite3.sqlite_version,
        dependencies={p:importlib.metadata.version(p) for p in ['numpy','networkx','transformers','sqlglot']},
        resources={c:subprocess.check_output(c.split(),text=True) for c in ['nvidia-smi','free -h','nproc']}))
    inputs=load_inputs(cfg)
    for field,hashfield in [('previous_predictions','previous_prediction_sha256'),('sql_prepared','sql_prepared_sha256'),('old_route_predictions','old_route_sha256'),('old_qafd_predictions','old_qafd_prediction_sha256')]:assert sha256(cfg[field])==cfg[hashfield]
    previous={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    for field in ['old_route_predictions','old_qafd_predictions']:excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(cfg[field]).read_text())}
    assert len(excluded)==333
    if args.mode=='confirmation':
        assert args.previous_pilot and json.loads((args.previous_pilot/'aggregate_summary.json').read_text())['upgrade_gate']
        excluded|={(r['db_id'],r['question_id']) for r in json.loads((args.previous_pilot/'predictions_private.json').read_text())}
        assert len(excluded)==433
    chosen=sample_cases(inputs['questions'],excluded,cfg['sample_salt']+(':confirm' if args.mode=='confirmation' else ''),100)
    if args.mode=='smoke':chosen=chosen[:5]
    for name in ['tokenizer.json','tokenizer_config.json','config.json']:assert sha256(Path(cfg['sql_model'])/name)==cfg['model_files_sha256'][name]
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True);assert tokenizer.is_fast
    colvec={};tablevec={};closures={};costmemo={};allcolumns={}
    for db,schema in inputs['schemas'].items():
        nodes=[n for n in inputs['nodes'] if n['db_id']==db]
        cols={int(n['node_id'].rsplit(':',1)[-1]):n['ordinal'] for n in nodes if n['node_type']=='column'}
        tables={int(n['node_id'].rsplit(':',1)[-1]):n['ordinal'] for n in nodes if n['node_type']=='table'}
        physical={c for c,(t,_) in enumerate(schema['column_names_original']) if t>=0};assert set(cols)==physical
        allcolumns[db]=physical;colvec[db]=(sorted(cols),inputs['vectors'][[cols[c] for c in sorted(cols)]])
        tablevec[db]=inputs['vectors'][[tables[t] for t in range(len(tables))]]
        closures[db]=SchemaClosure(schema,inputs['constraints'][db]);costmemo[db]={}
        assert serialize_partial(schema,physical,inputs['constraints'][db])==serialize_schema(schema,range(len(tables)),inputs['constraints'][db])
    qi={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])};predictions=[]
    for row in chosen:
        db=row['db_id'];schema=inputs['schemas'][db];q=inputs['queries'][qi[(db,row['question_id'])]]
        cols,v=colvec[db];scores=v@q;order=[cols[i] for i in sorted(range(len(cols)),key=lambda i:(-float(scores[i]),cols[i]))]
        def cost(columns,closed):
            constraints=closed['constraints'] if closed is not None else []
            key=(tuple(sorted(columns)),tuple(f['id'] for f in constraints))
            if key not in costmemo[db]:costmemo[db][key]=len(tokenizer.encode(serialize_partial(schema,columns,constraints),add_special_tokens=False))
            return costmemo[db][key]
        old=previous[(db,row['question_id'])];oldtext=serialize_schema(schema,old['arms']['weighted']['nodes'],inputs['constraints'][db])
        budget=len(tokenizer.encode(oldtext,add_special_tokens=False));dense=tablevec[db]@q
        retained=[]
        for t in sorted(range(len(dense)),key=lambda t:(-float(dense[t]),t)):
            trial=retained+[t];candidate={c for c in allcolumns[db] if schema['column_names_original'][c][0] in trial}
            closed={'constraints':[f for f in inputs['constraints'][db] if f['source_table'] in trial and f['target_table'] in trial]}
            if cost(candidate,closed)<=budget:retained=trial
        selected={c for c in allcolumns[db] if schema['column_names_original'][c][0] in retained}
        r={'columns':sorted(selected),'tables':sorted(retained),'constraints':[f for f in inputs['constraints'][db] if f['source_table'] in retained and f['target_table'] in retained]}
        arms={'whole_dense':dict(**r,semantic_columns=sorted(selected),tokens=cost(selected,r),rejected_columns=0,repair_removals=0)}
        for arm,mode in [('late_closure','late'),('early_closure','early')]:arms[arm]=select_columns(order,budget,closures[db].expand,cost,mode)
        for arm,r in arms.items():
            assert r['tokens']<=budget
            assert set(r['tables'])=={schema['column_names_original'][c][0] for c in r['columns']}
            assert all(a in r['columns'] and b in r['columns'] for f in r['constraints'] for a,b in f['pairs'])
            r['constraint_ids']=[f['id'] for f in r.pop('constraints')]
        predictions.append(dict(db_id=db,question_id=row['question_id'],budget=budget,arms=arms))
        if time.monotonic()-began>cfg['max_wall_seconds']:raise TimeoutError('CPU time budget exceeded')
    pred=args.output/'predictions_private.json';write_json(pred,predictions);seal=sha256(pred)
    write_json(args.output/'prediction_seal.json',dict(sha256=seal,questions=len(predictions),reference_not_used_for_selection=True))
    # Open reference SQL only after every arm's predictions have been sealed.
    references={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    stats={a:Counter() for a in ARMS};pairs={a:Counter() for a in ARMS[:2]};reasons=Counter();dbstats=defaultdict(lambda:{a:Counter() for a in ARMS});evaluations=[]
    for row in predictions:
        db=row['db_id'];s=inputs['schemas'][db];sql=references[(db,row['question_id'])]
        full=expressibility(sql,s,allcolumns[db]);gold=reference_tables(sql,s);out={}
        if full['status']!='compatible':reasons[full['reason']]+=1
        for arm,r in row['arms'].items():
            e=expressibility(sql,s,r['columns']) if full['status']=='compatible' else dict(status='unknown',reason=full['reason'])
            assert full['status']!='compatible' or e['status']!='unknown'
            values=dict(questions=1,evaluable=int(full['status']=='compatible'),compatible=int(e['status']=='compatible'),
                unknown=int(e['status']=='unknown'),complete_tables=int(gold<=set(r['tables'])),tokens=r['tokens'],columns=len(r['columns']),
                semantic_columns=len(r['semantic_columns']),connector_columns=len(set(r['columns'])-set(r['semantic_columns'])),tables=len(r['tables']),
                late_repair_removals=r['repair_removals'],late_repair_cases=int(r['repair_removals']>0))
            stats[arm].update(values);dbstats[db][arm].update(values);out[arm]=e
        for base in pairs:
            if full['status']!='compatible':pairs[base]['unknown']+=1
            else:
                better=out['early_closure']['status']=='compatible';b=out[base]['status']=='compatible'
                pairs[base]['rescue' if better and not b else 'damage' if b and not better else 'unchanged']+=1
        evaluations.append(dict(db_id=db,question_id=row['question_id'],full=full,arms=out))
    assert sha256(pred)==seal
    gate=stats['early_closure']['evaluable']>=.9*len(predictions) and stats['early_closure']['compatible']>=stats['late_closure']['compatible']+3 and stats['early_closure']['compatible']>=stats['whole_dense']['compatible']
    if args.mode=='smoke':gate=None
    for db,h in cfg['database_sha256'].items():assert sha256(Path(cfg['database_root'])/db/(db+'.sqlite'))==h
    write_json(args.output/'evaluations_private.json',evaluations)
    result=dict(run_id=cfg['run_id'],mode=args.mode,questions=len(predictions),excluded_prior_cases=len(excluded),
        arms={a:dict(v) for a,v in stats.items()},paired={a:dict(v) for a,v in pairs.items()},unknown_reasons=dict(reasons),
        per_database={f'DB-{i+1:02d}':{a:dict(v) for a,v in dbstats[db].items()} for i,db in enumerate(sorted(dbstats))},
        upgrade_gate=gate,decision='smoke_complete' if gate is None else 'ONE_UNCHANGED_CONFIRMATION_ALLOWED' if gate and args.mode=='pilot' else 'EXPLORATORY_CONFIRMED_NO_SQL_AUTHORIZATION' if gate else 'STOP_CANDIDATE_OR_MEASUREMENT',
        prediction_sha256=seal,config_sha256=sha256(args.config),new_model_calls=0,
        wall_seconds=time.monotonic()-began,cpu_seconds=time.process_time(),peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2))
    write_json(args.output/'aggregate_summary.json',result);print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
