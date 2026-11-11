"""Exact small-schema token-cost envelope, no inference or labels."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from transformers import AutoTokenizer
from qafd_context_capacity import cost_capacities
from run_seed_steiner import read_config,load_inputs,sha256,new_output,write_json
from seed_steiner import serialize_schema


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();new_output(args.output);began=time.monotonic();cfg=read_config(args.config)
    inputs=load_inputs(cfg)
    for name in ['tokenizer.json','tokenizer_config.json','config.json']:
        assert sha256(Path(cfg['sql_model'])/name)==cfg['model_files_sha256'][name]
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
    assert tokenizer.is_fast
    arrays={};statistics={}
    for db,schema in inputs['schemas'].items():
        n=len(schema['table_names_original'])
        if n>13:raise ValueError('Exact subset preprocessing limited to13tables')
        text=[serialize_schema(schema,[t for t in range(n) if mask>>t&1],inputs['constraints'][db]) for mask in range(1<<n)]
        costs=np.array([len(ids) for ids in tokenizer(text,add_special_tokens=False)['input_ids']],dtype=np.int64)
        caps=cost_capacities(costs,n)
        gaps=[]
        for mask,cost in enumerate(costs):
            upper=sum(caps[t] for t in range(n) if mask>>t&1)
            assert cost<=upper
            if cost:gaps.append(upper/cost)
        arrays[db+'_costs']=costs;arrays[db+'_caps']=caps
        statistics[db]=dict(tables=n,subsets=len(costs),total_capacity=float(sum(caps)),full_schema_tokens=int(costs[-1]),
            upper_bound_ratio_median=float(np.median(gaps)),upper_bound_ratio_max=float(max(gaps)))
        print(json.dumps(dict(stage='cost_cache',tables=n,subsets=len(costs))),flush=True)
        if time.monotonic()-began>cfg['max_wall_seconds']:raise TimeoutError('Cost cache budget exceeded')
    file=args.output/'subset_costs_private.npz';np.savez_compressed(file,**arrays)
    write_json(args.output/'receipt.json',dict(config_sha256=sha256(args.config),cache_sha256=sha256(file),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),command=sys.argv,
        tokenizer='Qwen2.5-Coder7B fast tokenizer, add_special_tokens=False',
        tokenizer_sha256=cfg['model_files_sha256']['tokenizer.json'],schema_sha256=cfg['schema_sha256'],
        serializer_sha256=sha256(Path(__file__).parent/'seed_steiner.py'),statistics=statistics,
        python=sys.version,dependencies={p:importlib.metadata.version(p) for p in ['numpy','networkx','transformers','sqlglot']},
        wall_seconds=time.monotonic()-began,new_model_calls=0))


if __name__=='__main__':main()
