"""Own a bounded local SQL service; run frozen paired stages and always clean up."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

import numpy as np
from run_seed_steiner import read_config,sha256,write_json,new_output
from steiner_sql import ARMS,payload_key
from p2d_sql_evaluator import execute_readonly,compare_rows
from steiner_sql_runtime import read_reference_rows,stop_owned_session


def extract_sql(text):
    value=text.strip()
    match=re.fullmatch(r'```(?:sql|sqlite)?\s*\n?(.*?)\n?```',value,re.I|re.S)
    if match:value=match.group(1).strip()
    if value.startswith('SQL:'):value=value[4:].strip()
    return value


def inventory():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.total,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    return [dict(zip(['gpu','total_mib','free_mib','utilization'],map(int,line.split(',')))) for line in raw.splitlines()]


class Experiment:
    def __init__(self,args):
        self.args=args;self.cfg=read_config(args.config);self.root=args.output
        self.started=time.time();self.service=None;self.service_hash=None;self.service_started=None
        self.request_dir=self.root/'requests';self.stop=threading.Event()
        self.request_dir.mkdir()
        self.manifest=json.loads((args.prepared/'manifest.json').read_text())
        if self.manifest['config_sha256']!=sha256(args.config) or sha256(args.prepared/'online_private.jsonl')!=self.manifest['online_sha256']:
            raise ValueError('Prepared manifest identity changed')
        self.rows=list(map(json.loads,(args.prepared/'online_private.jsonl').read_text().splitlines()))
        spec=importlib.util.spec_from_file_location('usage',self.cfg['ledger_module'])
        self.ledger=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.ledger)
        self.url='http://127.0.0.1:'+str(self.cfg['port'])
        self.deadline=self.started+self.cfg['max_wall_seconds']

    def check(self):
        if time.time()>self.deadline:raise RuntimeError('Experiment wall budget exhausted')

    def verify_inputs(self,weights=False):
        if sha256(Path(self.cfg['dataset_root'])/'dev.json')!=self.cfg['questions_sha256']:
            raise ValueError('Frozen reference dataset changed')
        if sha256(self.args.prepared/'online_private.jsonl')!=self.manifest['online_sha256']:
            raise ValueError('Online input changed')
        if sha256(Path(self.cfg['previous_predictions']))!=self.cfg['previous_prediction_sha256']:
            raise ValueError('Frozen selections changed')
        if sha256(Path(__file__).parent/'p2d_sql_evaluator.py')!=self.cfg['evaluator_sha256']:
            raise ValueError('Evaluator changed')
        for db,expected in self.cfg['database_sha256'].items():
            if sha256(Path(self.cfg['database_root'])/db/(db+'.sqlite'))!=expected:
                raise ValueError('Source database changed')
        names=self.cfg['model_files_sha256'] if weights else self.manifest['model_support_sha256']
        for name,expected in names.items():
            if sha256(Path(self.cfg['sql_model'])/name)!=expected:raise ValueError('Model changed')

    def start_service(self):
        self.verify_inputs(weights=True)
        snapshots=[]
        for i in range(2):
            current=inventory();snapshots.append(current)
            selected=[r for r in current if r['gpu'] in self.cfg['gpu_ids']]
            if len(selected)!=2 or any(r['free_mib']<self.cfg['min_free_mib'] or
                r['free_mib']-int(r['total_mib']*self.cfg['gpu_memory_utilization'])<self.cfg['post_allocation_margin_mib'] for r in selected):
                raise RuntimeError('GPU resource gate failed; no paid fallback')
            if i==0:time.sleep(10)
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',self.cfg['port']))==0:raise RuntimeError('Port occupied')
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=','.join(map(str,self.cfg['gpu_ids'])),OMP_NUM_THREADS='8',
            HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',VLLM_USE_V1='0',PYTHONHASHSEED='20261110')
        python=str(Path(self.cfg['vllm_env'])/'bin/python3.10')
        conda=os.environ.get('CONDA_EXE',str(Path(sys.executable).parents[3]/'bin/conda'))
        command=[conda,'run','--no-capture-output','-p',self.cfg['vllm_env'],python,
            '-m','vllm.entrypoints.openai.api_server','--model',self.cfg['sql_model'],'--served-model-name',self.cfg['served_model'],
            '--host','127.0.0.1','--port',str(self.cfg['port']),'--dtype','bfloat16','--tensor-parallel-size','2',
            '--gpu-memory-utilization',str(self.cfg['gpu_memory_utilization']),'--disable-custom-all-reduce',
            '--max-model-len',str(self.cfg['max_context']),'--max-num-seqs','4','--max-num-batched-tokens','4096',
            '--enable-chunked-prefill','--enable-prefix-caching','--enforce-eager','--disable-log-requests','--seed','20261110']
        # Runtime command is private. The public code resolves the existing conda
        # executable from its environment rather than requiring a personal path.
        if not Path(command[0]).is_file():raise RuntimeError('Conda executable unavailable')
        log=(self.root/'service.log').open('x')
        self.service_started=time.time()
        self.service=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        log.close()
        time.sleep(.3)
        self.service_hash=sha256(Path('/proc')/str(self.service.pid)/'cmdline')
        write_json(self.root/'service_start.json',{'pid':self.service.pid,'command':command,'started_epoch':self.service_started,
            'resource_snapshots':snapshots,'cmdline_sha256':self.service_hash,'gpu_ids':self.cfg['gpu_ids']})
        (self.root/'transport.env').write_text('STEINER_LOCAL_BASE_URL='+self.url+'\n')
        ready_deadline=min(self.deadline,time.time()+600)
        while time.time()<ready_deadline:
            if self.service.poll() is not None:raise RuntimeError('Local service exited during startup')
            try:
                with urllib.request.urlopen(self.url+'/v1/models',timeout=2) as r:metadata=json.load(r)
                if metadata['data'][0]['id']!=self.cfg['served_model']:raise ValueError('Wrong served model')
                if metadata['data'][0].get('max_model_len')!=self.cfg['max_context']:raise ValueError('Wrong context')
                write_json(self.root/'service_ready.json',{'pid':self.service.pid,'ready_epoch':time.time(),'model':self.cfg['served_model']})
                print(json.dumps({'stage':'service','status':'ready'}),flush=True);return
            except (OSError,urllib.error.URLError):time.sleep(2)
        raise RuntimeError('Local startup deadline exceeded')

    def stop_service(self):
        if self.service is None:return
        if self.service.poll() is None:
            live=Path('/proc')/str(self.service.pid)/'cmdline'
            if not live.exists() or sha256(live)!=self.service_hash or os.getpgid(self.service.pid)!=self.service.pid:
                raise RuntimeError('Owned service identity changed; refusing to signal')
        cleanup=stop_owned_session(self.service)
        # Child worker teardown can lag the parent process exit.
        for _ in range(10):
            with socket.socket() as sock:closed=sock.connect_ex(('127.0.0.1',self.cfg['port']))!=0
            if closed:break
            time.sleep(1)
        write_json(self.root/'service_stop.json',{**cleanup,'port_closed':closed,
            'service_wall_seconds':time.time()-self.service_started,
            'reserved_GPU_seconds':2*(time.time()-self.service_started),'GPU_cost_monetized':False,'resources_after':inventory()})

    def cached(self):
        return {p.stem:json.loads(p.read_text()) for p in self.request_dir.glob('*.json')}

    def request(self,key,payload):
        if self.stop.is_set():raise RuntimeError('Prior request failed; not attempted')
        self.check()
        began=time.time();usage={};status=None;response=None;error=None
        try:
            req=urllib.request.Request(self.url+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(req,timeout=min(self.cfg['request_timeout'],self.deadline-time.time())) as handle:
                status=handle.status;response=json.load(handle)
            usage=response.get('usage') or {}
        except Exception as exc:
            status=getattr(exc,'code',status);error=type(exc).__name__
        call_id=self.cfg['run_id']+'/'+key
        self.ledger.record_request(call_id=call_id,provider='local-vllm-steiner-sql',project='seed-steiner',run_id=self.cfg['run_id'],
            model=self.cfg['served_model'],http_status=status,usage=usage,occurred_at=datetime.fromtimestamp(began,timezone.utc).isoformat())
        result={'call_id':call_id,'payload_sha256':key,'usage':usage,'http_status':status,'response':response,
            'wall_seconds':time.time()-began,'error_type':error}
        write_json(self.request_dir/(key+'.json'),result)
        if error or status!=200 or not all(type(usage.get(k)) is int for k in ['prompt_tokens','completion_tokens','total_tokens']):
            self.stop.set();raise RuntimeError('Local request/usage failed; attempt recorded')
        return result

    def stage(self,name,rows):
        self.check();self.verify_inputs()
        folder=self.root/name;new_output(folder)
        cache=self.cached();needed={}
        for row in rows:
            for arm in ARMS:
                item=row['arms'][arm];key=item['payload_key']
                payload={'model':self.cfg['served_model'],'messages':item['messages'],**self.cfg['generation']}
                if key!=payload_key(payload):raise ValueError('Prepared payload differs')
                if key not in cache:needed[key]=(payload,item['prompt_tokens_preflight'])
        used_in=sum(r['usage'].get('prompt_tokens',0) for r in cache.values())
        used_out=sum(r['usage'].get('completion_tokens',0) for r in cache.values())
        if (len(cache)+len(needed)>self.cfg['max_physical_requests'] or used_in+sum(v[1] for v in needed.values())>self.cfg['max_input_tokens'] or
            used_out+len(needed)*self.cfg['generation']['max_tokens']>self.cfg['max_output_tokens']):raise RuntimeError('Model budget exceeded')
        with ThreadPoolExecutor(max_workers=self.cfg['http_concurrency']) as pool:
            futures={pool.submit(self.request,key,value[0]):key for key,value in needed.items()}
            for i,future in enumerate(as_completed(futures),1):
                try:cache[futures[future]]=future.result()
                except BaseException:
                    self.stop.set()
                    for pending in futures:pending.cancel()
                    raise
                if i%10==0:print(json.dumps({'stage':name,'physical_responses':i,'needed':len(needed)}),flush=True)
        predictions=[]
        for row in rows:
            for arm in ARMS:
                key=row['arms'][arm]['payload_key'];record=cache[key]
                choice=record['response']['choices'][0]
                content=choice['message']['content']
                if not isinstance(content,str):raise RuntimeError('Nontext response')
                predictions.append({'db_id':row['db_id'],'question_id':row['question_id'],'qi':row['qi'],'arm':arm,
                    'payload_key':key,'sql':extract_sql(content),'finish_reason':choice.get('finish_reason'),
                    'logical_usage':record['usage'],'physical_request_shared':sum(r['arms'][a]['payload_key']==key for r in rows for a in ARMS)>1})
        predfile=folder/'predictions_private.json';write_json(predfile,predictions)
        write_json(folder/'prediction_seal.json',{'sha256':sha256(predfile),'rows':len(predictions),'prepared_sha256':self.manifest['online_sha256']})
        # Only after durable sealing read reference SQL for this completed stage.
        raw=read_reference_rows(self.cfg)
        labels={(r['db_id'],r['question_id']):r['SQL'] for r in raw}
        metrics={arm:Counter() for arm in ARMS};evaluations=[]
        for i,row in enumerate(rows):
            dbpath=Path(self.cfg['database_root'])/row['db_id']/(row['db_id']+'.sqlite')
            def execute(sql):
                self.check()
                return execute_readonly(dbpath,sql,timeout=self.cfg['sql_timeout'],row_limit=self.cfg['sql_row_limit'],
                    byte_limit=self.cfg['sql_byte_limit'],sqlite_memory_limit=self.cfg['sql_memory_limit'])
            reference=execute(labels[(row['db_id'],row['question_id'])])
            for arm in ARMS:
                pred=predictions[i*3+ARMS.index(arm)];answer=execute(pred['sql'])
                comparison={'set_correct':None,'bag_correct':None,'comparison_status':'execution_unavailable'}
                if answer['status']=='ok' and reference['status']=='ok':
                    comparison=compare_rows(answer['rows'],reference['rows']) if len(answer['columns'])==len(reference['columns']) else {'set_correct':False,'bag_correct':False,'comparison_status':'column_count_mismatch'}
                value={'db_id':row['db_id'],'question_id':row['question_id'],'arm':arm,'prediction_status':answer['status'],
                    'reference_status':reference['status'],**comparison}
                evaluations.append(value)
                metrics[arm].update(questions=1,set_correct=int(comparison['set_correct'] is True),bag_correct=int(comparison['bag_correct'] is True),
                    unknown=int(comparison['set_correct'] is None),executable=int(answer['status']=='ok'),
                    input_tokens=pred['logical_usage']['prompt_tokens'],output_tokens=pred['logical_usage']['completion_tokens'],
                    truncated=int(pred['finish_reason']=='length'))
        write_json(folder/'evaluation_private.json',evaluations)
        pairs={}
        for base,ours in [('full','unit'),('full','weighted'),('unit','weighted')]:
            counts=Counter(rescue=0,damage=0,unchanged=0,unknown=0)
            for i in range(len(rows)):
                a=evaluations[i*3+ARMS.index(base)]['set_correct'];b=evaluations[i*3+ARMS.index(ours)]['set_correct']
                counts['unknown' if a is None or b is None else 'rescue' if b and not a else 'damage' if a and not b else 'unchanged']+=1
            pairs[ours+'_vs_'+base]=dict(counts)
        for value in metrics.values():value.update(set_EX=value['set_correct']/len(rows),bag_EX=value['bag_correct']/len(rows))
        saving=1-metrics['weighted']['input_tokens']/metrics['full']['input_tokens']
        gate=metrics['weighted']['set_correct']>=metrics['full']['set_correct']-1 and saving>=.15
        result={'stage':name,'questions':len(rows),'arms':{k:dict(v) for k,v in metrics.items()},'paired':pairs,
            'logical_weighted_input_reduction':saving,'expansion_gate_pass':gate,'new_physical_requests':len(needed),
            'cumulative_physical_requests':len(self.cached()),'prediction_sha256':sha256(predfile),'new_model_backend':'localQwen2.5Coder7B',
            'external_API_cost_CNY':'0.00','local_GPU_cost_monetized':False,'metric':'unordered Set/Bag; fixed projection order; unknowns retained'}
        self.verify_inputs();write_json(folder/'aggregate_summary.json',result)
        print(json.dumps({'stage':name,'questions':len(rows),'correct':{a:metrics[a]['set_correct'] for a in ARMS},'input_reduction':saving,'gate':gate}),flush=True)
        if name=='smoke' and any(metrics[a]['executable']==0 or metrics[a]['truncated'] for a in ARMS):raise RuntimeError('Engineering smoke gate failed')
        return result

    def run(self):
        self.start_service()
        smoke=self.stage('smoke',[r for r in self.rows if r['smoke']])
        pilot=self.stage('pilot',[r for r in self.rows if r['primary']])
        diagnostic=self.stage('diagnostic',[r for r in self.rows if r['changed_schema']])
        full=self.stage('full',self.rows) if pilot['expansion_gate_pass'] else None
        write_json(self.root/'completion.json',{'status':'complete','primary_gate_pass':pilot['expansion_gate_pass'],
            'full_run':full is not None,'decision':'conclude_downstream_SQL_stage','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();os.umask(0o077);new_output(args.output)
    experiment=Experiment(args)
    write_json(args.output/'run_start.json',{'command':sys.argv,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'config_sha256':sha256(args.config),'started_epoch':experiment.started,'python':sys.version,'executable':sys.executable})
    try:experiment.run()
    except BaseException as exc:
        write_json(args.output/'failure.json',{'error_type':type(exc).__name__,'elapsed_seconds':time.time()-experiment.started})
        raise
    finally:experiment.stop_service()
