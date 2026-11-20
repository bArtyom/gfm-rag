"""Freeze DB-heldout split and compile only selected training references."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_seed_steiner import read_config,load_inputs,new_output,write_json,sha256
from run_closure_budget_order import sample_cases
from closure_budget_order import expressibility,reference_read_bindings


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();new_output(a.output);began=time.monotonic();c=read_config(a.config);inp=load_inputs(c)
    dbs=sorted(inp['schemas'],key=lambda db:hashlib.sha256(('repair-db-v1:20261121:'+db).encode()).hexdigest());testdb=set(dbs[:3]);traindb=set(dbs[3:])
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(c['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    for name,key in [('old_route_predictions','old_route_sha256'),('old_qafd_predictions','old_qafd_prediction_sha256'),('previous_closure_predictions','previous_closure_prediction_sha256')]:
        assert sha256(c[name])==c[key];excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(c[name]).read_text())}
    assert len(excluded)==433
    train=sample_cases([r for r in inp['questions'] if r['db_id'] in traindb],set(),'repair-train-v1:20261121',c['train_count'])
    test=sample_cases([r for r in inp['questions'] if r['db_id'] in testdb],excluded,'repair-test-v1:20261121',c['test_count'])
    write_json(a.output/'split_private.json',dict(train_databases=sorted(traindb),test_databases=sorted(testdb),
        train=[{k:r[k] for k in ['db_id','question_id']} for r in train],test=[{k:r[k] for k in ['db_id','question_id']} for r in test]))
    keys={(r['db_id'],r['question_id']) for r in train};references={}
    # Mixed source JSON contains reference fields, but only training keys access SQL.
    for row in json.loads((Path(c['dataset_root'])/'dev.json').read_text()):
        key=(row['db_id'],row['question_id'])
        if key in keys:references[key]=row['SQL']
    result=[];unknown=Counter();dbsupported=Counter()
    for row in train:
        db=row['db_id'];s=inp['schemas'][db];sql=references[(db,row['question_id'])];fullcols=[i for i,(t,n) in enumerate(s['column_names_original']) if t>=0]
        status=expressibility(sql,s,fullcols)
        if status['status']!='compatible':unknown[status['reason']]+=1;continue
        bindings=reference_read_bindings(sql,s)
        if bindings['status']!='ok':unknown['binding_unknown']+=1;continue
        result.append(dict(db_id=db,question_id=row['question_id'],required_columns=bindings['columns'],required_tables=bindings['tables']));dbsupported[db]+=1
    write_json(a.output/'training_targets_private.json',result)
    write_json(a.output/'receipt.json',dict(config_sha256=sha256(a.config),split_sha256=sha256(a.output/'split_private.json'),targets_sha256=sha256(a.output/'training_targets_private.json'),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),command=sys.argv,python=sys.version,
        train_requested=len(train),train_supported=len(result),training_label_unknown=dict(unknown),test_count=len(test),excluded_prior_cases=len(excluded),
        train_databases=len(traindb),test_databases=len(testdb),database_overlap=len(traindb&testdb),
        per_database_training={f'DB-{i+1:02d}':dbsupported[db] for i,db in enumerate(sorted(traindb))},
        gate=len(result)>=280,test_reference_values_accessed=False,new_language_model_calls=0,wall_seconds=time.monotonic()-began))
    print((a.output/'receipt.json').read_text())


if __name__=='__main__':main()
