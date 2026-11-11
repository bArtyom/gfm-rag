"""Independently recount token costs, flow invariants, packing and metrics."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import time

import networkx as nx
import numpy as np
from transformers import AutoTokenizer

from query_weighted_steiner import weighted_graph
from run_seed_steiner import read_config,load_inputs,sha256,new_output,write_json
from seed_steiner import serialize_schema,reference_tables
from steiner_sql_runtime import read_reference_rows


def main():
    p=argparse.ArgumentParser()
    for label in ['config','cost_cache','execution','output']:p.add_argument('--'+label.replace('_','-'),dest=label,type=Path,required=True)
    args=p.parse_args();new_output(args.output);began=time.monotonic();cfg=read_config(args.config)
    summary=json.loads((args.execution/'aggregate_summary.json').read_text())
    assert sha256(args.execution/'predictions_private.json')==summary['prediction_sha256']==json.loads((args.execution/'prediction_seal.json').read_text())['sha256']
    assert json.loads((args.execution/'run_start.json').read_text())['config_sha256']==sha256(args.config)
    receipt=json.loads((args.cost_cache/'receipt.json').read_text());assert receipt['config_sha256']==sha256(args.config)
    assert sha256(args.cost_cache/'subset_costs_private.npz')==receipt['cache_sha256']
    inputs=load_inputs(cfg);rows=json.loads((args.execution/'predictions_private.json').read_text())
    assert len(rows)==summary['questions']
    old={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(cfg['old_route_predictions']).read_text())}
    if summary['mode']=='pilot':assert len(rows)==100 and len(excluded)==233 and not {(r['db_id'],r['question_id']) for r in rows}&excluded
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
    costs={};caps={};degreecaps={};tablevectors={};graphs={};all_subsets=0
    with np.load(args.cost_cache/'subset_costs_private.npz',allow_pickle=False) as cache:
        for db,schema in inputs['schemas'].items():
            n=len(schema['table_names_original']);costs[db]=cache[db+'_costs'].copy();caps[db]=cache[db+'_caps'].copy()
            texts=[serialize_schema(schema,[t for t in range(n) if mask>>t&1],inputs['constraints'][db]) for mask in range(1<<n)]
            counts=np.array([len(ids) for ids in tokenizer(texts,add_special_tokens=False)['input_ids']])
            assert np.array_equal(counts,costs[db])
            masks=np.arange(1<<n)
            for t in range(n):
                without=masks[(masks&(1<<t))==0]
                assert caps[db][t]==max(1,int(np.max(counts[without|(1<<t)]-counts[without])))
            for mask,cost in enumerate(counts):assert cost<=sum(caps[db][t] for t in range(n) if mask>>t&1)
            all_subsets+=len(counts)
            graph,_=weighted_graph(n,inputs['constraints'][db],np.ones(len(inputs['constraints'][db])));graphs[db]=graph
            d=np.array([max(1,graph.degree(t)) for t in range(n)],dtype=float);degreecaps[db]=d/d.sum()*caps[db].sum()
            lookup={int(node['node_id'].rsplit(':',1)[-1]):i for i,node in enumerate(inputs['nodes']) if node['db_id']==db and node['node_type']=='table'}
            tablevectors[db]=inputs['vectors'][[lookup[t] for t in range(n)]]
    qis={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
    max_error=Counter();flows_checked=0;budget_checks=0
    recounted={a:Counter() for a in ['dense','degree','context']};paired={a:Counter() for a in ['dense','degree']};dbnet=defaultdict(Counter)
    lost=[]
    for row in rows:
        db=row['db_id'];key=(db,row['question_id']);raw=tablevectors[db];n=len(raw);rawq=inputs['queries'][qis[key]]
        v=raw.astype(float);v/=np.linalg.norm(v,axis=1)[:,None]
        q=rawq.astype(float);q/=np.linalg.norm(q)
        dense=raw@rawq;node_sim=(v@q+1)/2
        w=np.zeros((n,n))
        for a,b in graphs[db].edges:
            # The producer's base affinity uses the frozen float32 dot product;
            # only the upstream query factors use normalized float64 cosines.
            base=float(np.clip((raw[a]@raw[b]+1)/2,0,1))
            w[a,b]=w[b,a]=base*node_sim[a]*node_sim[b]
        lap=np.diag(w.sum(axis=1))-w
        assert row['seeds']==old[key]['seeds']
        expectedB=int(costs[db][sum(1<<t for t in old[key]['arms']['weighted']['nodes'])]);assert row['budget_tokens']==expectedB
        for arm,result in row['arms'].items():
            score=np.zeros(n)
            for seed,record in zip(row['seeds'],result['flow_runs']):
                component=sorted(nx.node_connected_component(graphs[db],seed))
                M=min(expectedB/len(row['seeds']),cfg['feasible_mass_fraction']*min(caps[db][component].sum(),degreecaps[db][component].sum()))
                cap=degreecaps[db] if arm=='degree' else caps[db]
                delta=np.zeros(n);delta[seed]=M
                x=np.array(record['x']);mass=np.array(record['mass']);support=x>0
                assert (x>=0).all() and (mass>=-1e-6).all()
                error=float(max(abs(delta-lap@x-mass)));masserror=abs(mass.sum()-M)
                max_error['primal_dual']=max(max_error['primal_dual'],error);max_error['mass']=max(max_error['mass'],float(masserror))
                assert error<1e-5 and masserror<1e-5 and np.maximum(0,mass-cap).sum()<=cfg['flow_tolerance']*1.01
                assert (mass[support]>=cap[support]-1e-5).all() and cap[support].sum()<=M+1e-5
                assert np.isclose(record['injected_mass'],M) and record['updates']<cfg['max_pushes']
                if x.sum()>0:score+=x/x.sum()
                flows_checked+=1
            assert len(result['flow_runs'])==(0 if arm=='dense' else len(row['seeds']))
            assert np.allclose(score,result['scores'])
            mask=0
            for t in sorted(range(n),key=lambda t:(-float(score[t]),-float(dense[t]),t)):
                trial=mask|(1<<t)
                if int(costs[db][trial])<=expectedB:mask=trial
            assert result['nodes']==[t for t in range(n) if mask>>t&1]
            assert result['schema_tokens']==int(costs[db][mask])<=expectedB
            support=np.flatnonzero(score>0).tolist();assert support==result['support']
            if arm=='context':assert costs[db][sum(1<<t for t in support)]<=sum(caps[db][support])<=sum(r['injected_mass'] for r in result['flow_runs'])+1e-5<=expectedB+1e-5
            recounted[arm].update(questions=1,selected_tables=len(result['nodes']),schema_tokens=result['schema_tokens'],
                supports_over_actual_budget=int(result['support_schema_tokens']>expectedB),support_dropped_by_packing=result['support_dropped_by_packing'],
                selected_dense_fallback=result['dense_fallback_selected'],total_flow_updates=sum(r['updates'] for r in result['flow_runs']))
            budget_checks+=1
    # Labels only enter this independent metric recount, never the score checks.
    labels={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    for row in rows:
        gold=reference_tables(labels[(row['db_id'],row['question_id'])],inputs['schemas'][row['db_id']]);correct={}
        for arm,result in row['arms'].items():
            correct[arm]=gold<=set(result['nodes']);recounted[arm].update(complete=int(correct[arm]))
        for base in paired:
            paired[base].update(['rescue' if correct['context'] and not correct[base] else 'damage' if correct[base] and not correct['context'] else 'unchanged'])
            dbnet[row['db_id']][base]+=int(correct['context'])-int(correct[base])
        if correct['dense'] and not correct['context']:
            db=row['db_id'];missed=gold-set(row['arms']['context']['nodes'])
            lost.append(dict(missing_reference_tables=len(missed),budget_tokens=row['budget_tokens'],
                missing_table_columns=[sum(owner==t for owner,_ in inputs['schemas'][db]['column_names_original']) for t in sorted(missed)],
                missing_table_cost_capacities=[float(caps[db][t]) for t in sorted(missed)],
                max_per_source_mass=max(r['injected_mass'] for r in row['arms']['context']['flow_runs']),
                missing_tables_in_context_flow_support=len(missed&set(row['arms']['context']['support'])),
                selected_tables_dense=len(row['arms']['dense']['nodes']),selected_tables_context=len(row['arms']['context']['nodes'])))
    assert {a:dict(c) for a,c in recounted.items()}==summary['arms']
    assert {a:dict(c) for a,c in paired.items()}==summary['paired']
    if summary['mode']=='pilot':
        assert summary['pilot_upgrade_gate']==all(recounted['context']['complete']>=recounted[a]['complete']+2 for a in ['dense','degree'])
    result=dict(status='PASS',questions=len(rows),flow_states_checked=flows_checked,budget_checks=budget_checks,
        exact_schema_subset_costs_retokenized=all_subsets,maximum_errors=dict(max_error),prediction_sha256=sha256(args.execution/'predictions_private.json'),
        verification='independent vectorized query edge weights, primal-dual/KKT/mass identities, exact packing/coverage/gate recount; no re-solve',
        limitations=['shared schema loader/serializer/tokenizer/reference parser','certificate concerns context cost, not semantic correctness'],
        wall_seconds=time.monotonic()-began,new_model_calls=0)
    write_json(args.output/'independent_verification.json',result);print(json.dumps(result,indent=2))
    write_json(args.output/'loss_diagnosis.json',dict(cases=lost,interpretation='posthoc association, not proven cause; no new model calls or method tuning'))


if __name__=='__main__':main()
