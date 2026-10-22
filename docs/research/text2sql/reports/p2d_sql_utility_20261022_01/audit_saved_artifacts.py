"""Recompute metrics from saved result rows and audit physical usage, no model/SQL calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import pickle
import sqlite3
import sys
import os

ROOT = Path.cwd()
sys.path.insert(0,str(ROOT))
from scripts.text2sql.p2d_sql_context_eval import compare_execution, sha, read, verify_database_hashes
from scripts.text2sql import p2d_inputs

BASE=Path(os.environ.get('P2D_RESULT_ROOT','/mnt/liansp3/sources/results/gfmrag_p2d_sql_utility_20261022_01'))
PREP=BASE/'prepare_01'
seal=read(PREP/'prepare_seal_private.json')
full=BASE/'full_01'
receipts=[read(BASE/name/'run_receipt.json') for name in ('gate_a_01','smoke_3q_01','full_01')]
assert all(row['state']=='completed' for row in receipts)
assert all(row['source']==receipts[0]['source'] for row in receipts)
for row,name in zip(receipts,('gate_a_01','smoke_3q_01','full_01')):
    assert sha(BASE/name/'aggregate_summary.json')==row['aggregate_sha256']
for path,expected in receipts[0]['source']['sources_sha256'].items():assert sha(ROOT/path)==expected
for path,expected in seal['files'].items():assert sha(PREP/path)==expected
for case in seal['cases']:assert sha(PREP/case['file'])==case['sha256']
verify_database_hashes(PREP)
prediction_seal=read(full/'prediction_seal.json')
assert sha(full/'predictions_private.json')==prediction_seal['predictions_sha256']
predictions=read(full/'predictions_private.json')
cases=[read(PREP/case['file']) for case in seal['cases'] if case['cohort']!='smoke']
assert len(cases)==30 and len(predictions)==90 and prediction_seal['rows']==90
assert Counter(case['cohort'] for case in cases)=={'priority':19,'control':11}
assert {(row['case_id'],row['arm']) for row in predictions}=={(case['case_id'],arm) for case in cases for arm in ('E0','E1','E2')}
summary=read(full/'aggregate_summary.json')
metric={arm:Counter() for arm in ('E0','E1','E2')}
outcomes={}
for case in cases:
    assert case['arms']['E0']['node_ids']==case['arms']['E2']['node_ids']
    assert len({value['common_fields_sha256'] for value in case['arms'].values()})==1
    with (full/'executions_private'/(case['case_id']+'-reference.pickle')).open('rb') as source:reference=pickle.load(source)
    for arm in ('E0','E1','E2'):
        with (full/'executions_private'/(case['case_id']+'-'+arm+'.pickle')).open('rb') as source:prediction=pickle.load(source)
        comparison=compare_execution(prediction,reference)
        metric[arm].update(cases=1,executable=int(prediction['status']=='ok'),reference_executable=int(reference['status']=='ok'),
                           set_correct=int(comparison['set_correct'] is True),bag_correct=int(comparison['bag_correct'] is True),
                           comparison_unknown=int(comparison['set_correct'] is None or comparison['bag_correct'] is None))
        outcomes[(case['case_id'],arm)]=comparison
for arm,values in metric.items():
    for key,value in values.items():assert summary['arms'][arm][key]==value
pairs={}
for left,right in (('E0','E1'),('E0','E2'),('E1','E2')):
    counts=Counter()
    for case in cases:
        a,b=[outcomes[(case['case_id'],arm)]['set_correct'] for arm in (left,right)]
        counts['unknown' if a is None or b is None else 'both_correct' if a and b else left+'_only' if a else right+'_only' if b else 'both_wrong']+=1
    assert counts==Counter(summary['paired_set_outcomes'][left+'_vs_'+right])
    pairs[left+'_vs_'+right]=counts
connection=sqlite3.connect('file:/mnt/liansp3/.config/api-usage/usage.sqlite3?mode=ro',uri=True)
connection.row_factory=sqlite3.Row
usage=Counter()
tokenizer_mismatches=0
physical=0
for stage in ('gate_a_01','smoke_3q_01','full_01'):
    for path in sorted((BASE/stage/'requests').glob('*.response.json')):
        response=read(path)
        request=read(path.with_name(path.name.replace('.response.json','.request.json')))
        assert request['call_id']==response['call_id']
        assert p2d_inputs.digest_object(request['payload'])==request['payload_sha256']
        assert response['http_status']==200 and response['error_type'] is None
        event_id=hashlib.sha256(('local_vllm|'+response['call_id']).encode()).hexdigest()
        row=connection.execute('SELECT * FROM calls WHERE event_id=?',(event_id,)).fetchone()
        assert row and row['project']=='gfm-rag-p2d' and row['usage_reported']==1
        for key,field in (('prompt_tokens','input_tokens'),('completion_tokens','output_tokens'),('total_tokens','total_tokens')):
            assert response['usage'][key]==row[field]
            usage[field]+=row[field]
        if stage!='gate_a_01':
            label=path.name.removesuffix('.response.json')
            case_id,arm=label.rsplit('-',1)
            case=next(read(PREP/item['file']) for item in seal['cases'] if item['case_id']==case_id)
            assert request['payload']['messages']==case['arms'][arm]['messages']
            tokenizer_mismatches+=int(case['arms'][arm]['prompt_tokens_local']!=row['input_tokens'])
        physical+=1
connection.close()
assert physical==102 and usage['input_tokens']+usage['output_tokens']==usage['total_tokens']
assert usage['input_tokens']==summary['api_usage_cumulative_experiment']['input_tokens']
assert usage['output_tokens']==summary['api_usage_cumulative_experiment']['output_tokens']
privacy=json.dumps(summary,ensure_ascii=False)
assert not any(name in privacy for name in read(PREP/'sources_private.json')['databases'])
assert not any(key in privacy for key in ('"question_id"','"sql"','"reference_sql"','"messages"','"node_ids"','127.0.0.1'))
result={'status':'verified','full_cases':30,'full_predictions':90,'physical_requests':physical,
        'physical_usage_and_ledger_exact':True,'confirmed_usage':usage,'requests_without_usage':0,
        'prompt_tokenizer_count_mismatches':tokenizer_mismatches,'same_code_config_all_stages':True,
        'prediction_seal_and_source_hashes_verified':True,'database_hashes_unchanged':True,
        'metrics_recomputed_from_private_result_rows':True,'paired_set_outcomes':pairs,
        'public_privacy_scan_passed':True,'semantic_review_performed':False,
        'full_aggregate_sha256':sha(full/'aggregate_summary.json'),
        'prediction_seal_sha256':sha(full/'prediction_seal.json'),
        'evaluation_private_sha256':sha(full/'evaluation_private.json')}
with Path(os.environ.get('P2D_VERIFY_OUTPUT',str(ROOT/'ai_temp_code/p2d_verification_recheck.json'))).open('x') as target:json.dump(result,target,indent=2);target.write('\n')
print(json.dumps(result))
