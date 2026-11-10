import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from run_seed_steiner import load_inputs,read_config,sha256,new_output,write_json
from seed_steiner import serialize_schema
from steiner_sql import ARMS,choose_pilot,make_messages,payload_key


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    os.umask(0o077)
    new_output(args.output)
    cfg=read_config(args.config)
    began=time.monotonic()
    write_json(args.output/'run_start.json',{'command':sys.argv,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'python':sys.version,'executable':sys.executable,'config_sha256':sha256(args.config)})
    inputs=load_inputs(cfg)
    if sha256(Path(cfg['previous_predictions']))!=cfg['previous_prediction_sha256']:
        raise ValueError('Selection seal differs')
    if sha256(Path(__file__).parent/'p2d_sql_evaluator.py')!=cfg['evaluator_sha256']:
        raise ValueError('Evaluator version differs')
    for name,expected in cfg['model_files_sha256'].items():
        if sha256(Path(cfg['sql_model'])/name)!=expected:
            raise ValueError('Model files differ: '+name)
    extra={name:sha256(Path(cfg['sql_model'])/name) for name in ['tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','config.json','generation_config.json']}
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
    prior={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    primary={(r['db_id'],r['question_id']) for r in choose_pilot(inputs['questions'],cfg['primary_count'])}
    smoke={(r['db_id'],r['question_id']) for r in choose_pilot([r for r in inputs['questions'] if (r['db_id'],r['question_id']) in primary],5)}
    rows=[]
    ddl={}
    for qi,row in enumerate(inputs['questions']):
        db=row['db_id']; old=prior[(db,row['question_id'])]
        selections={'full':list(range(len(inputs['schemas'][db]['table_names_original']))),
            'unit':old['arms']['unit']['nodes'],'weighted':old['arms']['weighted']['nodes']}
        arms={}
        for arm,tables in selections.items():
            key=(db,tuple(tables))
            if key not in ddl:
                ddl[key]=serialize_schema(inputs['schemas'][db],tables,inputs['constraints'][db])
            messages=make_messages(row,ddl[key])
            tokens=len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True))
            if tokens+cfg['generation']['max_tokens']>cfg['max_context']:
                raise ValueError('Prompt exceeds frozen context; no truncation')
            payload={'model':cfg['served_model'],'messages':messages,**cfg['generation']}
            arms[arm]={'tables':tables,'messages':messages,'prompt_tokens_preflight':tokens,'payload_key':payload_key(payload)}
        rows.append({'db_id':db,'question_id':row['question_id'],'qi':qi,'primary':(db,row['question_id']) in primary,
            'smoke':(db,row['question_id']) in smoke,'changed_schema':selections['unit']!=selections['weighted'],'arms':arms})
    file=args.output/'online_private.jsonl'
    with file.open('x') as f:
        for row in rows:f.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n')
    write_json(args.output/'manifest.json',{'online_sha256':sha256(file),'config_sha256':sha256(args.config),
        'questions':len(rows),'primary':sum(r['primary'] for r in rows),'smoke':sum(r['smoke'] for r in rows),
        'diagnostic':sum(r['changed_schema'] for r in rows),'maximum_prompt_tokens':max(r['arms'][a]['prompt_tokens_preflight'] for r in rows for a in ARMS),
        'model_support_sha256':extra,'model_files_sha256':cfg['model_files_sha256'],'database_sha256':inputs['database_hashes'],
        'dependencies':{n:importlib.metadata.version(n) for n in ['transformers','numpy','sqlglot']},
        'wall_seconds':time.monotonic()-began,'new_model_calls':0})
    print(json.dumps(json.loads((args.output/'manifest.json').read_text())|{'model_files_sha256':'verified; retained privately','database_sha256':'verified; retained privately'},indent=2))

if __name__=='__main__':main()
