"""Train small graph-vector rankers; exact schema-budget repair, no LLM calls."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import importlib.metadata
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

import numpy as np
import torch
from transformers import AutoTokenizer
from budget_repair_attention import BudgetScorer,balanced_loss,feasible_repair
from closure_budget_order import SchemaClosure,serialize_partial,select_columns,expressibility,reference_read_bindings
from run_seed_steiner import read_config,load_inputs,new_output,write_json,sha256
from seed_steiner import serialize_schema

ARMS=['independent','global','repair']


class Runtime:
    def __init__(self,cfg,inputs):
        self.cfg=cfg;self.inputs=inputs;self.meta={};self.memo={};self.closures={};self.tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
        self.qi={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
        assert sha256(cfg['previous_predictions'])==cfg['previous_prediction_sha256']
        self.prior={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
        for db,s in inputs['schemas'].items():
            nodes=[n for n in inputs['nodes'] if n['db_id']==db];ids=[int(n['node_id'].rsplit(':',1)[-1]) for n in nodes];types=np.array([0 if n['node_type']=='table' else 1 for n in nodes])
            tables={cid:i for i,(cid,typ) in enumerate(zip(ids,types)) if typ==0};columns={cid:i for i,(cid,typ) in enumerate(zip(ids,types)) if typ==1}
            assert set(columns)=={i for i,(t,n) in enumerate(s['column_names_original']) if t>=0}
            owners=[cid if typ==0 else s['column_names_original'][cid][0] for cid,typ in zip(ids,types)]
            vectors=inputs['vectors'][[n['ordinal'] for n in nodes]]
            self.meta[db]=dict(nodes=nodes,ids=ids,types=types,tables=tables,columns=columns,owner_node=[tables[t] for t in owners],vectors=vectors)
            self.closures[db]=SchemaClosure(s,inputs['constraints'][db])

    def budget(self,row):
        db=row['db_id'];tables=self.prior[(db,row['question_id'])]['arms']['weighted']['nodes']
        return len(self.tokenizer.encode(serialize_schema(self.inputs['schemas'][db],tables,self.inputs['constraints'][db]),add_special_tokens=False))

    def cost(self,db,state):
        key=(db,tuple(state['columns']),tuple(f['id'] for f in state['constraints']))
        if key not in self.memo:self.memo[key]=len(self.tokenizer.encode(serialize_partial(self.inputs['schemas'][db],state['columns'],state['constraints']),add_special_tokens=False))
        return self.memo[key]

    def field_scores(self,db,node_scores):
        m=self.meta[db]
        return {cid:float(node_scores[i]+.25*node_scores[m['owner_node'][i]]) for cid,i in m['columns'].items()}

    def pack(self,row,field_scores):
        db=row['db_id'];order=sorted(field_scores,key=lambda c:(-field_scores[c],c));budget=self.budget(row)
        state=select_columns(order,budget,self.closures[db].expand,lambda cols,closed:self.cost(db,closed),'early')
        state['constraint_ids']=[f['id'] for f in state.pop('constraints')];assert state['tokens']<=budget
        return state

    def dense_whole(self,row):
        db=row['db_id'];m=self.meta[db];q=self.inputs['queries'][self.qi[(db,row['question_id'])]];s=self.inputs['schemas'][db];scores=m['vectors']@q
        selected=[];state={'columns':[],'tables':[],'constraints':[]}
        for t in sorted(m['tables'],key=lambda t:(-float(scores[m['tables'][t]]),t)):
            trial=selected+[t];cols=[i for i,(owner,n) in enumerate(s['column_names_original']) if owner in trial]
            fks=[f for f in self.inputs['constraints'][db] if f['source_table'] in trial and f['target_table'] in trial];proposal={'columns':cols,'tables':sorted(trial),'constraints':fks}
            if self.cost(db,proposal)<=self.budget(row):selected=trial;state=proposal
        return dict(columns=state['columns'],tables=state['tables'],constraint_ids=[f['id'] for f in state['constraints']],tokens=self.cost(db,state))


def main():
    p=argparse.ArgumentParser()
    for key in ['config','prepared','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--mode',choices=['smoke','pilot'],required=True);a=p.parse_args();os.umask(0o077);new_output(a.output);cfg=read_config(a.config);began=time.monotonic()
    torch.set_num_threads(8);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.use_deterministic_algorithms(True)
    assert os.environ.get('CUDA_VISIBLE_DEVICES')==str(cfg['gpu_index'])
    resources={c:subprocess.check_output(c.split(),text=True) for c in ['nvidia-smi','free -h','nproc']}
    gpu_lines=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True).splitlines()
    free={int(line.split(',')[0]):int(line.split(',')[1]) for line in gpu_lines};assert free[cfg['gpu_index']]>=4096
    write_json(a.output/'run_start.json',dict(started_at_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),config_sha256=sha256(a.config),python=sys.version,
        dependencies={p:importlib.metadata.version(p) for p in ['torch','numpy','networkx','transformers','sqlglot']},resources=resources,
        visible_gpu=cfg['gpu_index'],language_model_calls=0,language_tokens=0))
    receipt=json.loads((a.prepared/'receipt.json').read_text());assert receipt['gate'] and receipt['config_sha256']==sha256(a.config)
    assert sha256(a.prepared/'split_private.json')==receipt['split_sha256'] and sha256(a.prepared/'training_targets_private.json')==receipt['targets_sha256']
    targets=json.loads((a.prepared/'training_targets_private.json').read_text());split=json.loads((a.prepared/'split_private.json').read_text())
    assert not set(split['train_databases'])&set(split['test_databases'])
    inp=load_inputs(cfg);runtime=Runtime(cfg,inp);device=torch.device('cuda:0');gpu_meta={}
    for db,m in runtime.meta.items():gpu_meta[db]=(torch.as_tensor(m['vectors'],device=device),torch.as_tensor(m['types'],device=device),torch.as_tensor(m['owner_node'],device=device))
    trainrows=targets[:5] if a.mode=='smoke' else targets;testrows=split['test'][:5] if a.mode=='smoke' else split['test'];epochs=1 if a.mode=='smoke' else cfg['epochs']
    calls=0;nodeunits=0;gpu_forward_ms=0.;gpu_backward_ms=0.;events=Counter();certdb=set();epoch_history=[];parameters={};initial_hashes={};checkpoint_hashes={};testpred={};node_score_files={}
    forward_log=(a.output/'graph_forward_events_private.jsonl').open('x');repairs_log=(a.output/'repair_certificates_private.jsonl').open('x')
    def forward(model,row,stage,arm):
        nonlocal calls,nodeunits,gpu_forward_ms
        if calls>=cfg['max_forward_calls'] or time.monotonic()-began>cfg['model_wall_seconds']:raise RuntimeError('Forward/wall budget exhausted')
        db=row['db_id'];v,types,owners=gpu_meta[db];q=torch.as_tensor(inp['queries'][runtime.qi[(db,row['question_id'])]],device=device)
        features=torch.cat((v,q.expand_as(v),v*q,v[owners]),dim=1);base=v@q
        start=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True);start.record();scores=model(features,types,base);end.record();end.synchronize()
        duration=start.elapsed_time(end);calls+=1;nodeunits+=len(v);gpu_forward_ms+=duration
        record=dict(call_id=f'{cfg["run_id"]}:{a.mode}:{calls}',arm=arm,stage=stage,nodes=len(v),feature_width=features.shape[1],gpu_forward_ms=duration,language_tokens=0)
        forward_log.write(json.dumps(record)+'\n');forward_log.flush()
        if torch.cuda.max_memory_allocated()>2*1024**3:raise RuntimeError('GPU memory budget exceeded')
        return scores,types
    for arm in ARMS:
        random.seed(cfg['seed']);np.random.seed(cfg['seed']);torch.manual_seed(cfg['seed']);torch.cuda.manual_seed_all(cfg['seed'])
        kind='independent' if arm=='independent' else 'global';model=BudgetScorer(kind,hidden=cfg['hidden'],heads=cfg['heads']).to(device)
        parameters[arm]=sum(p.numel() for p in model.parameters());initial=a.output/f'{arm}_initial.pt';torch.save(model.state_dict(),initial);initial_hashes[arm]=sha256(initial)
        # Serialization includes filename; tensor equality is the initialization contract.
        if arm=='global':global_initial={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        if arm=='repair':assert all(torch.equal(global_initial[k],v.detach().cpu()) for k,v in model.state_dict().items())
        optimizer=torch.optim.AdamW(model.parameters(),lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
        for epoch in range(epochs):
            order=list(range(len(trainrows)));random.Random(cfg['seed']+epoch).shuffle(order);losses=[];epochcert=0
            model.train()
            for iteration,i in enumerate(order):
                row=trainrows[i];db=row['db_id'];m=runtime.meta[db];scores,types=forward(model,row,'train',arm);labels=torch.zeros_like(scores)
                for t in row['required_tables']:labels[m['tables'][t]]=1
                for c in row['required_columns']:labels[m['columns'][c]]=1
                loss=balanced_loss(scores,labels,types);certificate=None
                if arm=='repair':
                    field_scores=runtime.field_scores(db,scores.detach().cpu().numpy());state=runtime.pack(row,field_scores)
                    certificate=feasible_repair(state['semantic_columns'],field_scores,row['required_columns'],row['required_tables'],runtime.budget(row),runtime.closures[db].expand,lambda x:runtime.cost(db,x))
                    if certificate:
                        def differentiable(c):return scores[m['columns'][c]]+.25*scores[m['tables'][inp['schemas'][db]['column_names_original'][c][0]]]
                        term=torch.nn.functional.softplus(torch.stack([differentiable(c) for c in certificate['removed']]).mean()-differentiable(certificate['added'])+cfg['repair_margin'])
                        loss=loss+cfg['repair_weight']*term;events['certificates']+=1;epochcert+=1;certdb.add(db)
                        repairs_log.write(json.dumps(dict(db_id=db,question_id=row['question_id'],epoch=epoch,budget=runtime.budget(row),initial_semantic=state['semantic_columns'],required_columns=row['required_columns'],required_tables=row['required_tables'],certificate=certificate))+'\n');repairs_log.flush()
                if not torch.isfinite(loss):raise RuntimeError('Nonfinite loss')
                optimizer.zero_grad(set_to_none=True);start=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True);start.record();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();end.record();end.synchronize();gpu_backward_ms+=start.elapsed_time(end)
                losses.append(float(loss.detach().cpu()));events[arm+'_optimizer_steps']+=1
            rowstats=dict(arm=arm,epoch=epoch,steps=len(order),mean_loss=float(np.mean(losses)),certificates=epochcert);epoch_history.append(rowstats);print(json.dumps(rowstats),flush=True)
        checkpoint=a.output/f'{arm}_final.pt';torch.save(model.state_dict(),checkpoint);checkpoint_hashes[arm]=sha256(checkpoint)
        model.eval();predictions=[]
        with torch.no_grad():
            for row in testrows:
                scores,_=forward(model,row,'test',arm);raw=scores.detach().cpu().numpy();state=runtime.pack(row,runtime.field_scores(row['db_id'],raw))
                predictions.append(dict(**row,node_scores=raw.tolist(),selection=state))
        scorefile=a.output/f'{arm}_scores_private.json';write_json(scorefile,predictions);node_score_files[arm]=sha256(scorefile);testpred[arm]=predictions
        del optimizer,model;torch.cuda.empty_cache()
    forward_log.close();repairs_log.close()
    predictions=[]
    for i,row in enumerate(testrows):
        arms={arm:testpred[arm][i]['selection'] for arm in ARMS};arms['whole_dense']=runtime.dense_whole(row)
        predictions.append(dict(**row,budget=runtime.budget(row),arms=arms))
    pred=a.output/'predictions_private.json';write_json(pred,predictions);seal=sha256(pred);write_json(a.output/'prediction_seal.json',dict(sha256=seal,questions=len(predictions),test_reference_values_not_used=True,score_seals=node_score_files,checkpoint_seals=checkpoint_hashes))
    # All model checkpoints, scores and selections are now frozen. Test SQL first used below.
    wanted={(r['db_id'],r['question_id']) for r in testrows};references={}
    for row in json.loads((Path(cfg['dataset_root'])/'dev.json').read_text()):
        key=(row['db_id'],row['question_id'])
        if key in wanted:references[key]=row['SQL']
    counts={arm:Counter() for arm in ARMS+['whole_dense']};pairs={arm:Counter() for arm in ['independent','global','whole_dense']};perdb=defaultdict(lambda:{a:Counter() for a in counts});evaluations=[];unknown=Counter()
    for row in predictions:
        db=row['db_id'];s=inp['schemas'][db];sql=references[(db,row['question_id'])];allcols=[c for c,(t,n) in enumerate(s['column_names_original']) if t>=0];full=expressibility(sql,s,allcols)
        bindings=reference_read_bindings(sql,s) if full['status']=='compatible' else dict(status='unknown',tables=[],columns=[]);correct={}
        supported=full['status']=='compatible' and bindings['status']=='ok'
        if not supported:unknown[full['reason'] if full['status']!='compatible' else 'binding_unknown']+=1
        evaluation={'db_id':db,'question_id':row['question_id'],'supported':supported,'bindings':bindings,'arms':{}}
        for arm,r in row['arms'].items():
            correct[arm]=supported and set(bindings['columns'])<=set(r['columns']) and set(bindings['tables'])<=set(r['tables'])
            prepared=expressibility(sql,s,r['columns'])['status']=='compatible' if supported else False
            values=dict(questions=1,evaluable=int(supported),complete_read_bindings=int(correct[arm]),preparable=int(prepared),unknown=int(not supported),tokens=r['tokens'],columns=len(r['columns']),tables=len(r['tables']),budget_violations=int(r['tokens']>row['budget']))
            counts[arm].update(values);perdb[db][arm].update(values);evaluation['arms'][arm]=dict(complete_read_bindings=correct[arm],preparable=prepared)
        for base in pairs:pairs[base]['unknown' if not supported else 'rescue' if correct['repair'] and not correct[base] else 'damage' if correct[base] and not correct['repair'] else 'unchanged']+=1
        evaluations.append(evaluation)
    write_json(a.output/'evaluations_private.json',evaluations);assert sha256(pred)==seal
    source_support=events['certificates']>=30 and len(certdb)>=2
    positive_dbs=sum(all(v['repair']['complete_read_bindings']>v[b]['complete_read_bindings'] for b in ['independent','global']) for v in perdb.values())
    gate=source_support and counts['repair']['evaluable']>=90 and all(counts['repair']['complete_read_bindings']>=counts[b]['complete_read_bindings']+3 for b in ['independent','global']) and counts['repair']['complete_read_bindings']>=counts['whole_dense']['complete_read_bindings'] and positive_dbs>=2 and not any(c['budget_violations'] for c in counts.values())
    if a.mode=='smoke':gate=None
    for db,h in cfg['database_sha256'].items():assert sha256(Path(cfg['database_root'])/db/(db+'.sqlite'))==h
    summary=dict(mode=a.mode,run_id=cfg['run_id'],questions=len(predictions),train_supported=len(trainrows),epochs=epochs,arms={a:dict(c) for a,c in counts.items()},paired={a:dict(c) for a,c in pairs.items()},unknown_reasons=dict(unknown),
        per_database={f'DB-{i+1:02d}':{a:dict(c) for a,c in perdb[db].items()} for i,db in enumerate(sorted(perdb))},
        parameter_counts=parameters,epoch_history=epoch_history,training_events=dict(events),certificate_databases=len(certdb),certificate_support_gate=source_support,positive_test_databases=positive_dbs,
        upgrade_gate=gate,decision='SMOKE_COMPLETE_DISCARD_WEIGHTS' if gate is None else 'SEPARATE_REPRODUCIBILITY_REGISTRATION_ALLOWED' if gate else 'STOP_THIS_VERSION',
        graph_forward_calls=calls,input_graph_nodes=nodeunits,gpu_forward_seconds=gpu_forward_ms/1000,gpu_backward_optimizer_seconds=gpu_backward_ms/1000,peak_GPU_allocated_bytes=torch.cuda.max_memory_allocated(),
        elapsed_wall_seconds=time.monotonic()-began,cpu_seconds=time.process_time(),peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2),
        new_language_model_calls=0,input_language_tokens=0,output_language_tokens=0,new_external_API_cost_CNY='0',local_compute_priced=False,
        prediction_sha256=seal,score_seals=node_score_files,checkpoint_seals=checkpoint_hashes,config_sha256=sha256(a.config))
    write_json(a.output/'aggregate_summary.json',summary);print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
