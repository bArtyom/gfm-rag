"""Audit scores/checkpoints, repair feasibility, split, compute units and metrics."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import time

import numpy as np
import torch
from budget_repair_attention import BudgetScorer
from run_budget_repair_attention import Runtime,ARMS
from run_seed_steiner import read_config,load_inputs,new_output,write_json,sha256
from run_closure_budget_order import sample_cases
from closure_budget_order import expressibility,reference_read_bindings
from steiner_sql_runtime import read_reference_rows


def main():
    p=argparse.ArgumentParser()
    for k in ['config','prepared','execution','output']:p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();new_output(a.output);began=time.monotonic();c=read_config(a.config);torch.set_num_threads(8);inp=load_inputs(c);rt=Runtime(c,inp)
    summary=json.loads((a.execution/'aggregate_summary.json').read_text());seal=json.loads((a.execution/'prediction_seal.json').read_text());rows=json.loads((a.execution/'predictions_private.json').read_text());prepared=json.loads((a.prepared/'receipt.json').read_text())
    split=json.loads((a.prepared/'split_private.json').read_text());targets=json.loads((a.prepared/'training_targets_private.json').read_text());train={(r['db_id'],r['question_id']):r for r in targets}
    assert sha256(a.execution/'predictions_private.json')==summary['prediction_sha256']==seal['sha256']
    assert sha256(a.config)==summary['config_sha256']==prepared['config_sha256']==json.loads((a.execution/'run_start.json').read_text())['config_sha256']
    assert sha256(a.prepared/'split_private.json')==prepared['split_sha256'] and sha256(a.prepared/'training_targets_private.json')==prepared['targets_sha256']
    assert rows and len(rows)==100 and len(train)==317 and summary['epochs']==3
    assert not set(split['train_databases'])&set(split['test_databases'])
    assert [(r['db_id'],r['question_id']) for r in rows]==[(r['db_id'],r['question_id']) for r in split['test']]
    assert sha256(c['sql_prepared'])==c['sql_prepared_sha256']
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(c['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    for field in ['old_route_predictions','old_qafd_predictions','previous_closure_predictions']:excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(c[field]).read_text())}
    assert len(excluded)==433 and not {(r['db_id'],r['question_id']) for r in rows}&excluded
    assert [(r['db_id'],r['question_id']) for r in rows]==[(r['db_id'],r['question_id']) for r in sample_cases([r for r in inp['questions'] if r['db_id'] in set(split['test_databases'])],excluded,'repair-test-v1:20261121',100)]
    initg=torch.load(a.execution/'global_initial.pt',map_location='cpu',weights_only=True);initr=torch.load(a.execution/'repair_initial.pt',map_location='cpu',weights_only=True)
    assert all(torch.equal(initg[k],initr[k]) for k in initg)
    scores_checked=0;budget_checked=0;maxdiff=0.;checkpoint_changed={}
    for arm in ARMS:
        assert sha256(a.execution/f'{arm}_scores_private.json')==summary['score_seals'][arm]==seal['score_seals'][arm]
        assert sha256(a.execution/f'{arm}_final.pt')==summary['checkpoint_seals'][arm]==seal['checkpoint_seals'][arm]
        state=torch.load(a.execution/f'{arm}_final.pt',map_location='cpu',weights_only=True);initial=torch.load(a.execution/f'{arm}_initial.pt',map_location='cpu',weights_only=True)
        checkpoint_changed[arm]=any(not torch.equal(state[k],initial[k]) for k in state);assert checkpoint_changed[arm]
        model=BudgetScorer('independent' if arm=='independent' else 'global',hidden=c['hidden'],heads=c['heads']).eval();model.load_state_dict(state)
        assert sum(p.numel() for p in model.parameters())==summary['parameter_counts'][arm]
        rawscores=json.loads((a.execution/f'{arm}_scores_private.json').read_text())
        for row,record in zip(rows,rawscores):
            assert (row['db_id'],row['question_id'])==(record['db_id'],record['question_id']);db=row['db_id'];m=rt.meta[db]
            v=torch.as_tensor(m['vectors']);q=torch.as_tensor(inp['queries'][rt.qi[(db,row['question_id'])]]);owners=torch.as_tensor(m['owner_node']);types=torch.as_tensor(m['types'])
            with torch.no_grad():actual=model(torch.cat((v,q.expand_as(v),v*q,v[owners]),dim=1),types,v@q).numpy()
            expected=np.array(record['node_scores']);difference=float(np.max(abs(actual-expected)));maxdiff=max(maxdiff,difference)
            assert np.allclose(actual,expected,atol=5e-5,rtol=1e-5)
            selection=rt.pack(row,rt.field_scores(db,expected));assert selection==record['selection']==row['arms'][arm]
            assert selection['tokens']<=row['budget']==rt.budget(row);scores_checked+=1;budget_checked+=1
    for row in rows:
        assert rt.dense_whole(row)==row['arms']['whole_dense'];assert row['arms']['whole_dense']['tokens']<=row['budget'];budget_checked+=1
    certificates=[json.loads(line) for line in (a.execution/'repair_certificates_private.jsonl').read_text().splitlines()];certdb=set();cert_epochs=Counter()
    for event in certificates:
        key=(event['db_id'],event['question_id']);assert key in train;target=train[key];db=event['db_id'];certificate=event['certificate']
        assert target['required_columns']==event['required_columns'] and target['required_tables']==event['required_tables']
        initial=rt.closures[db].expand(event['initial_semantic']);repaired=rt.closures[db].expand(certificate['repaired_semantic']);required=set(target['required_columns'])
        assert certificate['added'] in required-set(initial['columns'])
        assert set(certificate['removed'])<=set(event['initial_semantic'])-required
        assert set(certificate['repaired_semantic'])==(set(event['initial_semantic'])|{certificate['added']})-set(certificate['removed'])
        assert required&set(initial['columns'])<=set(repaired['columns'])
        assert set(target['required_tables'])&set(initial['tables'])<=set(repaired['tables'])
        assert repaired['columns']==certificate['repaired_columns'] and repaired['tables']==certificate['repaired_tables']
        assert rt.cost(db,repaired)==certificate['tokens']<=event['budget']==rt.budget(event)
        assert certificate['binding_gain']==len(required&set(repaired['columns']))-len(required&set(initial['columns']))>=1
        certdb.add(db);cert_epochs[event['epoch']]+=1
    assert len(certificates)==summary['training_events']['certificates'] and len(certdb)==summary['certificate_databases']
    forward_events=[json.loads(line) for line in (a.execution/'graph_forward_events_private.jsonl').read_text().splitlines()];units=Counter();calls=Counter()
    for i,event in enumerate(forward_events):
        assert event['call_id']==f'{c["run_id"]}:pilot:{i+1}' and event['feature_width']==4096 and event['language_tokens']==0
        calls[(event['arm'],event['stage'])]+=1;units['nodes']+=event['nodes']
    for arm in ARMS:
        assert calls[(arm,'train')]==317*3==summary['training_events'][arm+'_optimizer_steps'] and calls[(arm,'test')]==100
    assert len(forward_events)==summary['graph_forward_calls'] and units['nodes']==summary['input_graph_nodes']
    assert np.isclose(sum(e['gpu_forward_ms'] for e in forward_events)/1000,summary['gpu_forward_seconds'])
    assert len(forward_events)<=c['max_forward_calls'] and summary['elapsed_wall_seconds']<=c['model_wall_seconds'] and summary['peak_GPU_allocated_bytes']<=2*1024**3
    # Recheck reference bindings on frozen bytes only after score/prediction replay.
    refs={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(c) if (r['db_id'],r['question_id']) in set(train)|{(r['db_id'],r['question_id']) for r in rows}}
    for key,target in train.items():
        bindings=reference_read_bindings(refs[key],inp['schemas'][key[0]])
        assert bindings['status']=='ok' and bindings['columns']==target['required_columns'] and bindings['tables']==target['required_tables']
    counts={arm:Counter() for arm in ARMS+['whole_dense']};pairs={arm:Counter() for arm in ['independent','global','whole_dense']};perdb=defaultdict(lambda:{arm:Counter() for arm in counts})
    for row in rows:
        db=row['db_id'];s=inp['schemas'][db];sql=refs[(db,row['question_id'])];full=expressibility(sql,s,[i for i,(t,n) in enumerate(s['column_names_original']) if t>=0]);bindings=reference_read_bindings(sql,s) if full['status']=='compatible' else dict(status='unknown');supported=full['status']=='compatible' and bindings['status']=='ok';correct={}
        for arm,r in row['arms'].items():
            correct[arm]=supported and set(bindings['columns'])<=set(r['columns']) and set(bindings['tables'])<=set(r['tables'])
            values=dict(questions=1,evaluable=int(supported),complete_read_bindings=int(correct[arm]),preparable=int(supported and expressibility(sql,s,r['columns'])['status']=='compatible'),unknown=int(not supported),tokens=r['tokens'],columns=len(r['columns']),tables=len(r['tables']),budget_violations=int(r['tokens']>row['budget']))
            counts[arm].update(values);perdb[db][arm].update(values)
        for base in pairs:pairs[base]['unknown' if not supported else 'rescue' if correct['repair'] and not correct[base] else 'damage' if correct[base] and not correct['repair'] else 'unchanged']+=1
    assert {a:dict(v) for a,v in counts.items()}==summary['arms'] and {a:dict(v) for a,v in pairs.items()}==summary['paired']
    positive=sum(all(v['repair']['complete_read_bindings']>v[b]['complete_read_bindings'] for b in ['independent','global']) for v in perdb.values());source_support=len(certificates)>=30 and len(certdb)>=2
    gate=source_support and counts['repair']['evaluable']>=90 and all(counts['repair']['complete_read_bindings']>=counts[b]['complete_read_bindings']+3 for b in ['independent','global']) and counts['repair']['complete_read_bindings']>=counts['whole_dense']['complete_read_bindings'] and positive>=2 and not any(v['budget_violations'] for v in counts.values())
    assert gate==summary['upgrade_gate'] and positive==summary['positive_test_databases']
    output=dict(status='PASS',questions=100,CPU_checkpoint_forward_replays=scores_checked,maximum_CPU_GPU_score_difference=maxdiff,budget_checks=budget_checked,repair_certificates_verified=len(certificates),training_reference_targets_rechecked=len(train),graph_forward_events_verified=len(forward_events),input_graph_nodes_verified=units['nodes'],checkpoints_changed=checkpoint_changed,split_seals_counts_gate_verified=True,wall_seconds=time.monotonic()-began,
        new_language_model_calls=0,verification_graph_forward_calls=scores_checked,verification_input_graph_nodes=sum(len(rt.meta[r['db_id']]['nodes']) for r in rows)*3,
        limitations=['shared serializer/closure/prepare and reference-binding helper','does not independently replay optimization gradients','CPU graph-vector replay has no language-token usage; CPU time is unpriced'])
    write_json(a.output/'verification.json',output);print(json.dumps(output,indent=2))


if __name__=='__main__':main()
