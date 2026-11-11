"""Three-arm budget-controlled QAFD capacity intervention using frozen caches."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import networkx as nx
import numpy as np

from qafd_context_capacity import load_upstream_core,feasible_diffusion,pack_scores
from query_weighted_steiner import weighted_graph
from run_seed_steiner import read_config,load_inputs,sha256,new_output,write_json
from seed_steiner import reference_tables
from steiner_sql_runtime import read_reference_rows

ARMS=['dense','degree','context']


def choose_cases(rows,excluded,count):
    groups=defaultdict(list)
    for row in rows:
        if (row['db_id'],row['question_id']) not in excluded:groups[row['db_id']].append(row)
    for db in groups:
        groups[db].sort(key=lambda r:hashlib.sha256(f'qafd-context-v1:20261111:{db}:{r["question_id"]}'.encode()).hexdigest())
    result=[]
    while len(result)<count and any(groups.values()):
        for db in sorted(groups):
            if groups[db] and len(result)<count:result.append(groups[db].pop(0))
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ['config','cost_cache','output']:p.add_argument('--'+name.replace('_','-'),dest=name,type=Path,required=True)
    p.add_argument('--mode',choices=['smoke','pilot','full'],required=True)
    p.add_argument('--pilot-summary',type=Path)
    args=p.parse_args();os.umask(0o077);new_output(args.output);began=time.monotonic();cfg=read_config(args.config)
    if args.mode=='full':
        assert args.pilot_summary is not None
        assert json.loads(args.pilot_summary.read_text())['pilot_upgrade_gate'] is True
    up=Path(cfg['qafd_upstream'])
    assert subprocess.check_output(['git','-C',str(up),'rev-parse','HEAD'],text=True).strip()==cfg['qafd_commit']
    assert not subprocess.check_output(['git','-C',str(up),'status','--porcelain'],text=True).strip()
    write_json(args.output/'run_start.json',dict(command=sys.argv,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        config_sha256=sha256(args.config),upstream_commit=cfg['qafd_commit'],python=sys.version,
        resources={c:subprocess.check_output(c.split(),text=True) for c in ['nvidia-smi','free -h','nproc']}))
    inputs=load_inputs(cfg);receipt=json.loads((args.cost_cache/'receipt.json').read_text())
    assert receipt['config_sha256']==sha256(args.config) and receipt['serializer_sha256']==sha256(Path(__file__).parent/'seed_steiner.py')
    assert sha256(args.cost_cache/'subset_costs_private.npz')==receipt['cache_sha256']
    assert sha256(Path(cfg['previous_predictions']))==cfg['previous_prediction_sha256']
    assert sha256(Path(cfg['sql_prepared']))==cfg['sql_prepared_sha256']
    assert sha256(Path(cfg['old_route_predictions']))==cfg['old_route_sha256']
    prior={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(cfg['old_route_predictions']).read_text())}
    assert len(excluded)==233
    selected=inputs['questions'] if args.mode=='full' else choose_cases(inputs['questions'],excluded,100)
    if args.mode=='smoke':selected=selected[:5]
    qis={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
    tables={};graphs={};costs={};caps={};degreecaps={}
    with np.load(args.cost_cache/'subset_costs_private.npz',allow_pickle=False) as cache:
        for db,schema in inputs['schemas'].items():
            costs[db]=cache[db+'_costs'].copy();caps[db]=cache[db+'_caps'].copy()
            lookup={int(n['node_id'].rsplit(':',1)[-1]):i for i,n in enumerate(inputs['nodes']) if n['db_id']==db and n['node_type']=='table'}
            tables[db]=inputs['vectors'][[lookup[t] for t in range(len(lookup))]]
            graphs[db],_=weighted_graph(len(lookup),inputs['constraints'][db],np.ones(len(inputs['constraints'][db])))
            for a,b in graphs[db].edges:graphs[db][a][b]['weight']=float(np.clip((tables[db][a]@tables[db][b]+1)/2,0,1))
            degree=np.array([max(1,graphs[db].degree(t)) for t in range(len(lookup))],dtype=float)
            degreecaps[db]=degree/degree.sum()*caps[db].sum()
    core=load_upstream_core(up);predictions=[]
    for row in selected:
        db=row['db_id'];key=(db,row['question_id']);old=prior[key];seeds=old['seeds'];n=len(graphs[db]);q=inputs['queries'][qis[key]]
        mask=sum(1<<t for t in old['arms']['weighted']['nodes']);budget=int(costs[db][mask])
        original=core(graphs[db],seeds[0],seeds[0],node_embeddings={t:tables[db][t].tolist() for t in range(n)},
            subquery_embedding=q.tolist(),weight_func='multiply',random_seed=42)
        weights=np.zeros((n,n))
        for a,b in graphs[db].edges:weights[a,b]=weights[b,a]=original.get_edge_weight(a,b)
        if any(weights[a,b]<=0 for a,b in graphs[db].edges):raise ValueError('Positive FK conductances required')
        dense=tables[db]@q;scores={a:np.zeros(n) for a in ARMS};runs={a:[] for a in ARMS[1:]}
        for seed in seeds:
            component=sorted(nx.node_connected_component(graphs[db],seed))
            mass=min(budget/len(seeds),cfg['feasible_mass_fraction']*min(caps[db][component].sum(),degreecaps[db][component].sum()))
            delta=np.zeros(n);delta[seed]=mass
            for arm,capacity in [('degree',degreecaps[db]),('context',caps[db])]:
                result=feasible_diffusion(weights,capacity,delta,cfg['flow_tolerance'],cfg['max_pushes'])
                x=np.array(result['x']);normalizer=x.sum()
                if normalizer>0:scores[arm]+=x/normalizer
                runs[arm].append(result)
        arms={}
        for arm in ARMS:
            nodes=pack_scores(scores[arm],dense,costs[db],budget)
            support=sorted(np.flatnonzero(scores[arm]>0).tolist());supportmask=sum(1<<t for t in support)
            countcost=int(costs[db][sum(1<<t for t in nodes)])
            assert countcost<=budget
            injected=sum(r['injected_mass'] for r in runs.get(arm,[]))
            certificate=float(caps[db][support].sum())
            if arm=='context':assert int(costs[db][supportmask])<=certificate<=injected+1e-5<=budget+1e-5
            arms[arm]=dict(nodes=nodes,scores=scores[arm].tolist(),schema_tokens=countcost,support=support,
                support_schema_tokens=int(costs[db][supportmask]),support_context_capacity=certificate,injected_mass=injected,
                support_dropped_by_packing=len(set(support)-set(nodes)),dense_fallback_selected=int(sum(scores[arm][t]==0 for t in nodes)),
                flow_runs=runs.get(arm,[]))
        predictions.append(dict(db_id=db,question_id=row['question_id'],seeds=seeds,budget_tokens=budget,arms=arms))
        if time.monotonic()-began>cfg['max_wall_seconds']:raise TimeoutError('Run wall budget exhausted')
    file=args.output/'predictions_private.json';write_json(file,predictions);seal=sha256(file)
    write_json(args.output/'prediction_seal.json',dict(sha256=seal,questions=len(predictions),labels_not_used_for_prediction=True))
    labels={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    stats={a:Counter() for a in ARMS};pair={b:Counter() for b in ['degree','dense']};dbnet=defaultdict(Counter)
    for row in predictions:
        gold=reference_tables(labels[(row['db_id'],row['question_id'])],inputs['schemas'][row['db_id']]);correct={}
        for arm,r in row['arms'].items():
            correct[arm]=gold<=set(r['nodes'])
            stats[arm].update(questions=1,complete=int(correct[arm]),selected_tables=len(r['nodes']),schema_tokens=r['schema_tokens'],
                supports_over_actual_budget=int(r['support_schema_tokens']>row['budget_tokens']),support_dropped_by_packing=r['support_dropped_by_packing'],
                selected_dense_fallback=r['dense_fallback_selected'],total_flow_updates=sum(v['updates'] for v in r['flow_runs']))
        for base in pair:
            pair[base].update(['rescue' if correct['context'] and not correct[base] else 'damage' if correct[base] and not correct['context'] else 'unchanged'])
            dbnet[row['db_id']][base]+=int(correct['context'])-int(correct[base])
    gate=all(stats['context']['complete']>=stats[a]['complete']+2 for a in ['degree','dense'])
    if args.mode=='full':
        gate=all((stats['context']['complete']-stats[a]['complete'])*100>=2*len(predictions) for a in ['degree','dense']) and sum(all(v.get(a,0)>0 for a in ['degree','dense']) for v in dbnet.values())>=2
    if args.mode=='smoke':gate=None
    assert sha256(file)==seal
    for db,expected in cfg['database_sha256'].items():assert sha256(Path(cfg['database_root'])/db/(db+'.sqlite'))==expected
    output=dict(mode=args.mode,questions=len(predictions),run_id=cfg['run_id'],arms={a:dict(c) for a,c in stats.items()},paired={a:dict(c) for a,c in pair.items()},
        per_database_net={f'DB-{i+1:02d}':dict(dbnet[db]) for i,db in enumerate(sorted(inputs['schemas']))},
        pilot_upgrade_gate=gate if args.mode=='pilot' else None,stage_upgrade_gate=gate,
        decision='engineering_smoke_complete' if args.mode=='smoke' else 'unchanged_CPU_full_allowed' if gate and args.mode=='pilot' else 'SQL_followup_registration_required' if gate else 'STOP_CONTEXT_CAPACITY_CANDIDATE',
        prediction_sha256=seal,new_model_calls=0,elapsed_wall_seconds=time.monotonic()-began,cpu_seconds=time.process_time(),
        peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    write_json(args.output/'aggregate_summary.json',output);print(json.dumps(output,indent=2),flush=True)


if __name__=='__main__':main()
