"""Budget-matched route reranking with raw and residual column witnesses."""
import argparse
from collections import Counter,defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
from transformers import AutoTokenizer

from query_weighted_steiner import weighted_graph
from residual_routes import tree_catalogue,residual_scores,stage_decision
from run_seed_steiner import read_config,load_inputs,sha256,write_json,new_output
from seed_steiner import reference_tables,serialize_schema
from steiner_sql_runtime import read_reference_rows

ARMS=['frozen','raw','residual']


def choose_cases(rows,excluded,count=100):
    groups=defaultdict(list)
    for r in rows:
        if (r['db_id'],r['question_id']) not in excluded:groups[r['db_id']].append(r)
    for db in groups:
        groups[db].sort(key=lambda r:hashlib.sha256(f'residual-route-v1:20261111:{db}:{r["question_id"]}'.encode()).hexdigest())
    result=[]
    while len(result)<count and any(groups.values()):
        for db in sorted(groups):
            if groups[db] and len(result)<count:result.append(groups[db].pop(0))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['smoke','pilot','full'],required=True)
    args=p.parse_args();os.umask(0o077);new_output(args.output)
    cfg=read_config(args.config);began=time.monotonic()
    write_json(args.output/'run_start.json',dict(command=sys.argv,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        config_sha256=sha256(args.config),python=sys.version,dependencies={m:importlib.metadata.version(m) for m in ['numpy','networkx','sqlglot','transformers']},
        resources={c:subprocess.check_output(c.split(),text=True) for c in ['nvidia-smi','free -h','nproc']}))
    inputs=load_inputs(cfg)
    assert sha256(Path(cfg['previous_predictions']))==cfg['previous_prediction_sha256']
    assert sha256(Path(cfg['sql_prepared']))==cfg['sql_prepared_sha256']
    old={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    assert len(excluded)==133
    selected=inputs['questions'] if args.mode=='full' else choose_cases(inputs['questions'],excluded,100)
    if args.mode=='smoke':selected=selected[:5]
    qis={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
    for name,expected in cfg['model_files_sha256'].items():
        if name in ['tokenizer.json','config.json','tokenizer_config.json']:
            assert sha256(Path(cfg['sql_model'])/name)==expected
    columns={};owners={};graphs={}
    for db,schema in inputs['schemas'].items():
        indices=[i for i,n in enumerate(inputs['nodes']) if n['db_id']==db and n['node_type']=='column']
        columns[db]=inputs['vectors'][indices]
        owners[db]=[schema['column_names_original'][int(inputs['nodes'][i]['node_id'].rsplit(':',1)[-1])][0] for i in indices]
        assert len(indices) and all(t>=0 for t in owners[db])
        graphs[db],_=weighted_graph(len(schema['table_names_original']),inputs['constraints'][db],np.ones(len(inputs['constraints'][db])))
    tokens={};catalogues={};predictions=[]
    def tok(db,nodes):
        key=(db,tuple(nodes))
        if key not in tokens:tokens[key]=len(tokenizer.encode(serialize_schema(inputs['schemas'][db],nodes,inputs['constraints'][db]),add_special_tokens=False))
        return tokens[key]
    for row in selected:
        db=row['db_id'];key=(db,row['question_id']);prior=old[key];seeds=prior['seeds'];base=prior['arms']['weighted']
        graph,_=weighted_graph(len(graphs[db]),inputs['constraints'][db],prior['relation_costs'])
        cachekey=(db,tuple(seeds))
        if cachekey not in catalogues:catalogues[cachekey]=tree_catalogue(graphs[db],seeds)
        catalogue=catalogues[cachekey]
        assert any(c['nodes']==base['nodes'] and c['edges']==base['edges'] for c in catalogue)
        q=inputs['queries'][qis[key]];vecs=columns[db];own=owners[db];sim=vecs@q
        witnesses=[max((i for i,t in enumerate(own) if t==seed),key=lambda i:(sim[i],-i)) for seed in seeds]
        raw,residual,norm=residual_scores(q,vecs,witnesses)
        scores={}
        for arm,values in [('raw',raw),('residual',residual)]:
            scores[arm]={t:max(float(values[i]) for i,owner in enumerate(own) if owner==t) for t in graph}
        cap=tok(db,base['nodes'])
        feasible=[c for c in catalogue if len(c['nodes'])<=len(base['nodes']) and tok(db,c['nodes'])<=cap]
        assert feasible
        arms={'frozen':dict(nodes=base['nodes'],edges=base['edges'],cost=base['cost'],schema_tokens=cap)}
        def cost(c):return sum(graph[a][b]['weight'] for a,b in c['edges'])
        for arm in ['raw','residual']:
            def order(c):
                bridge=set(c['nodes'])-set(seeds)
                score=max((scores[arm][t] for t in bridge),default=0.)
                return (-score,cost(c),tuple(map(tuple,c['edges'])),tuple(c['nodes']))
            winner=min(feasible,key=order)
            arms[arm]={**winner,'cost':cost(winner),'schema_tokens':tok(db,winner['nodes']),'score':-order(winner)[0]}
        predictions.append(dict(db_id=db,question_id=row['question_id'],seeds=seeds,residual_norm=norm,
            catalogue_size=len(catalogue),feasible_size=len(feasible),arms=arms,
            feasible_node_sets=sorted({tuple(c['nodes']) for c in feasible})))
        if time.monotonic()-began>cfg['max_wall_seconds']:raise TimeoutError('CPU budget exceeded')
    file=args.output/'predictions_private.json';write_json(file,predictions);seal=sha256(file)
    write_json(args.output/'prediction_seal.json',dict(sha256=seal,questions=len(predictions),labels_not_used_for_prediction=True))
    labels={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    stats={a:Counter() for a in ARMS};pairs={a:Counter() for a in ['residual_vs_frozen','residual_vs_raw']};dbpairs=defaultdict(Counter)
    oracle=Counter();errors=0
    for row in predictions:
        db=row['db_id'];gold=reference_tables(labels[(db,row['question_id'])],inputs['schemas'][db]);correct={}
        oracle.update(within_budget_complete=int(any(gold<=set(c) for c in row['feasible_node_sets'])),questions=1)
        for arm in ARMS:
            r=row['arms'][arm];correct[arm]=gold<=set(r['nodes'])
            assert len(r['nodes'])<=len(row['arms']['frozen']['nodes']) and r['schema_tokens']<=row['arms']['frozen']['schema_tokens']
            stats[arm].update(questions=1,complete=int(correct[arm]),selected_tables=len(r['nodes']),schema_tokens=r['schema_tokens'],changed_from_frozen=int(r['nodes']!=row['arms']['frozen']['nodes']))
        for base in ['frozen','raw']:
            label='residual_vs_'+base
            pairs[label].update(['rescue' if correct['residual'] and not correct[base] else 'damage' if correct[base] and not correct['residual'] else 'unchanged'])
            dbpairs[db][label]+=int(correct['residual'])-int(correct[base])
    gate,decision=stage_decision(args.mode,len(predictions),stats,dbpairs)
    assert sha256(file)==seal
    for db,expected in cfg['database_sha256'].items():assert sha256(Path(cfg['database_root'])/db/(db+'.sqlite'))==expected
    result=dict(run_id=cfg['run_id'],mode=args.mode,questions=len(predictions),arms={a:dict(c) for a,c in stats.items()},paired={a:dict(c) for a,c in pairs.items()},
        per_database_net={f'DB-{i+1:02d}':dict(dbpairs[db]) for i,db in enumerate(sorted(inputs['schemas']))},diagnostic_oracle=dict(oracle),
        stage_upgrade_gate=gate,decision=decision,
        catalogue_mean=float(np.mean([r['catalogue_size'] for r in predictions])),feasible_mean=float(np.mean([r['feasible_size'] for r in predictions])),
        new_model_calls=0,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),prediction_sha256=seal,
        elapsed_wall_seconds=time.monotonic()-began,cpu_seconds=time.process_time(),peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2))
    write_json(args.output/'aggregate_summary.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
