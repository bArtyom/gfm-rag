#!/usr/bin/env python3
"""Frozen P2d Gate A, private smoke and one paired SQL execution pilot."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, '/mnt/liansp3/sources/code')
from api_usage_ledger import record_request, totals
from scripts.text2sql import p2d_inputs as inputs
from scripts.text2sql import p2d_sql_evaluator as evaluator

EXPERIMENT = 'p2d_sql_utility_20261022_01'
REPORT = ROOT / 'docs/research/text2sql/reports' / EXPERIMENT
SOURCES = ('scripts/text2sql/p2d_inputs.py', 'scripts/text2sql/p2d_sql_evaluator.py',
           'scripts/text2sql/p2d_sql_context_eval.py', 'scripts/text2sql/predicate_value_binding.py',
           'scripts/text2sql/audit_p2c_values_risk.py', 'scripts/text2sql/run_p2c_dual_view_factorial.py')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


def extract_sql(content):
    value = content.strip()
    fenced = re.fullmatch(r'```(?:sql|sqlite)?\s*\n?(.*?)\n?```', value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    if value.startswith('SQL:'):
        value = value[4:].strip()
    return value


def compare_execution(predicted, reference):
    if predicted['status'] != 'ok' or reference['status'] != 'ok':
        return {'set_correct': None, 'bag_correct': None, 'comparison_status': 'execution_unavailable'}
    if len(predicted['columns']) != len(reference['columns']):
        return {'set_correct': False, 'bag_correct': False, 'comparison_status': 'column_count_mismatch'}
    return evaluator.compare_rows(predicted['rows'], reference['rows'])


def execute(db, sql, config):
    remaining = config.get('_deadline_epoch', float('inf')) - time.time()
    if remaining <= 0:
        raise RuntimeError('P2d absolute wall budget exhausted before SQL execution')
    return evaluator.execute_readonly(db, sql, timeout=min(config['sql']['timeout_seconds'], remaining),
                                     row_limit=config['sql']['row_limit'], byte_limit=config['sql']['byte_limit'],
                                     sqlite_memory_limit=config['sql']['sqlite_memory_limit'])


def backend_check(prepared):
    backend = read(prepared / 'backend_private.json')
    if hashlib.sha256(Path(f"/proc/{backend['pid']}/cmdline").read_bytes()).hexdigest() != backend['cmdline_sha256']:
        raise RuntimeError('Frozen local service identity changed')
    transport = dict(line.split('=', 1) for line in (prepared / 'transport.env').read_text().splitlines() if '=' in line)
    url = transport['P2D_LOCAL_BASE_URL']
    with urllib.request.urlopen(url + '/v1/models', timeout=10) as response:
        metadata = json.load(response)
    if [(row['id'], row.get('max_model_len')) for row in metadata['data']] != [(backend['model'], backend['max_model_len'])]:
        raise RuntimeError('Frozen service model metadata changed')
    return url


def usage_records(base):
    result = []
    for path in sorted(base.glob('*/requests/*.response.json')):
        result.append(read(path))
    return result


def check_deadline(started, config):
    if time.time() - started >= config['budget']['total_wall_seconds']:
        raise RuntimeError('P2d absolute wall budget exhausted')


def verify_database_hashes(prepared):
    for item in read(prepared / 'sources_private.json')['databases'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('Read-only database snapshot hash changed')


def request_one(base, out, prepared, config, run_id, label, messages, started):
    url = backend_check(prepared)
    history = usage_records(base)
    if len(history) >= config['budget']['max_total_model_calls'] or time.time()-started > config['budget']['total_wall_seconds']:
        raise RuntimeError('Frozen model request/wall budget exhausted')
    used_input = sum(row.get('usage', {}).get('prompt_tokens', 0) for row in history)
    used_output = sum(row.get('usage', {}).get('completion_tokens', 0) for row in history)
    if used_input + 32768 > config['budget']['input_tokens'] or used_output + config['generation']['max_tokens'] > config['budget']['output_tokens']:
        raise RuntimeError('Frozen token budget exhausted')
    call_id = f'{EXPERIMENT}/{run_id}/{label}'
    payload = {'model': config['model']['served_model'], 'messages': messages, **config['generation'], 'n': 1, 'stream': False}
    reqdir = out / 'requests'
    reqdir.mkdir(exist_ok=True)
    save(reqdir / (label + '.request.json'), {'call_id': call_id, 'payload': payload, 'payload_sha256': inputs.digest_object(payload)})
    began = time.perf_counter()
    occurred = datetime.now(timezone.utc).isoformat()
    usage, status, response, error = {}, None, None, None
    timeout = min(config['budget']['request_timeout_seconds'], config['budget']['total_wall_seconds']-(time.time()-started))
    if timeout <= 0:
        raise RuntimeError('P2d absolute wall budget exhausted before request')
    def alarm_handler(signum, frame):
        raise TimeoutError('P2d request absolute deadline')
    previous_handler = signal.signal(signal.SIGALRM, alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        request = urllib.request.Request(url + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=timeout) as handle:
            status = handle.status
            response = json.load(handle)
        usage = response.get('usage') or {}
    except Exception as exc:
        status = getattr(exc, 'code', None)
        error = type(exc).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    record = {'call_id': call_id, 'usage': usage, 'http_status': status, 'occurred_at': occurred,
              'wall_seconds': time.perf_counter()-began, 'error_type': error, 'response': response}
    save(reqdir / (label + '.response.json'), record)
    record_request(call_id=call_id, provider='local_vllm', project='gfm-rag-p2d', run_id=run_id,
                   model=config['model']['served_model'], http_status=status, usage=usage, occurred_at=occurred)
    check_deadline(started, config)
    if error or status != 200 or response is None:
        raise RuntimeError('Local generation attempt failed; frozen no-retry stop')
    if not all(type(usage.get(key)) is int for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')):
        raise RuntimeError('Local generation usage missing; recorded unknown and stopped')
    content = response['choices'][0]['message']['content']
    if not isinstance(content, str):
        raise RuntimeError('Generation did not return a string')
    return {'sql': extract_sql(content), 'finish_reason': response['choices'][0].get('finish_reason'),
            'usage': usage, 'request_wall_seconds': record['wall_seconds'], 'call_id': call_id}


def verify_inputs(prepared, config):
    seal = read(prepared / 'prepare_seal_private.json')
    if sha(prepared / 'prepare_seal_private.json') != config['prepare_seal_sha256']:
        raise RuntimeError('Preparation seal differs from registration')
    for name, expected in seal['files'].items():
        if sha(prepared/name) != expected:
            raise RuntimeError('Prepared artifact changed: ' + name)
    for case in seal['cases']:
        if sha(prepared/case['file']) != case['sha256']:
            raise RuntimeError('Prepared case changed')
    for item in read(prepared / 'sources_private.json')['inputs'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('Frozen source artifact changed')
    manifest = read(prepared / 'model_manifest_private.json')
    for name, expected in manifest['files'].items():
        if not name.endswith('.safetensors') and sha(Path(manifest['root'])/name) != expected:
            raise RuntimeError('Frozen model metadata changed')
    verify_database_hashes(prepared)
    return seal


def check_predecessor(base, stage, expected_source):
    prior = read(base / stage / 'run_receipt.json')
    if prior['state'] != 'completed' or prior['source'] != expected_source:
        raise RuntimeError('Predecessor stage incomplete or code/config differs')
    if sha(base / stage / 'aggregate_summary.json') != prior['aggregate_sha256']:
        raise RuntimeError('Predecessor aggregate changed')
    return prior


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('gate-a', 'smoke', 'full'), required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--result-root', type=Path, required=True)
    args = parser.parse_args()
    config_path = REPORT / 'experiment_config.json'
    config = read(config_path)
    if config['status'] != 'preregistered_not_run' or config['experiment_id'] != EXPERIMENT:
        raise RuntimeError('P2d registration is absent or closed')
    if args.result_root.resolve() != Path(config['private_result_root']).resolve():
        raise RuntimeError('P2d result root is not registered')
    tree = subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip()
    published_tree = subprocess.check_output(['git','rev-parse',args.expected_commit+'^{tree}'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip() != args.expected_commit:
        raise RuntimeError('Expected source is not the verified published origin/main')
    if tree != published_tree or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise RuntimeError('P2d requires a clean tree matching its published source')
    if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip() != 'main':
        raise RuntimeError('P2d checkout must be main')
    base, prepared = args.result_root, args.result_root / 'prepare_01'
    out = base / config['stage_dirs'][args.stage]
    out.mkdir(exist_ok=False)
    source = {'published_commit': args.expected_commit, 'config_sha256': sha(config_path),
              'sources_sha256': {name: sha(ROOT/name) for name in SOURCES},
              'dependencies': {name: importlib.metadata.version(name) for name in ('sqlglot','transformers','tokenizers')}}
    receipt = {'experiment_id': EXPERIMENT, 'run_id': config['run_ids'][args.stage], 'stage': args.stage, 'state': 'started',
               'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source': source, 'command': sys.argv,
               'semantic_review_status': 'unverified', 'human_reviews': 0}
    save(out/'start.json', receipt)
    start_cpu, start_wall, stage_epoch = time.process_time(), time.perf_counter(), time.time()
    try:
        seal = verify_inputs(prepared, config)
        backend_check(prepared)
        if args.stage != 'gate-a':
            gate = check_predecessor(base, config['stage_dirs']['gate-a'], source)
            experiment_start = gate['experiment_start_epoch']
            if args.stage == 'full':
                check_predecessor(base, config['stage_dirs']['smoke'], source)
        else:
            experiment_start = stage_epoch
        receipt['experiment_start_epoch'] = experiment_start
        config['_deadline_epoch'] = experiment_start + config['budget']['total_wall_seconds']
        check_deadline(experiment_start, config)
        if args.stage == 'gate-a':
            db = out/'synthetic.sqlite'
            connection = sqlite3.connect(db)
            connection.execute('CREATE TABLE items(id INTEGER, quantity INTEGER)')
            connection.executemany('INSERT INTO items VALUES (?,?)', [(1,2),(2,3),(3,None)])
            connection.commit(); connection.close()
            questions = [('How many rows are in items?', 'SELECT COUNT(*) FROM items'),
                         ('What is the sum of quantity?', 'SELECT SUM(quantity) FROM items'),
                         ('Return the ids whose quantity is greater than 2.', 'SELECT id FROM items WHERE quantity > 2')]
            records = []
            for index, (question, reference_sql) in enumerate(questions):
                generated = request_one(base,out,prepared,config,receipt['run_id'],f'synthetic-{index+1}',inputs.messages(question,'','Table: items; columns: id, quantity\nColumn: items.id; type: integer\nColumn: items.quantity; type: integer'),experiment_start)
                prediction, reference = execute(db,generated['sql'],config), execute(db,reference_sql,config)
                comparison = compare_execution(prediction,reference)
                records.append({'status':prediction['status'],**comparison})
                if not comparison['set_correct'] or not comparison['bag_correct']:
                    raise RuntimeError('Synthetic generator/SQLite smoke failed; no private pilot launched')
            summary = {'stage':'gate-a','status':'completed','synthetic_cases':3,'synthetic_passed':3,'semantic_review_status':'unverified','human_reviews':0,'engineering_gate':'PASS','records':records}
        else:
            cohort_smoke = args.stage == 'smoke'
            chosen = [item for item in seal['cases'] if (item['cohort']=='smoke') == cohort_smoke]
            predictions = []
            for index, item in enumerate(chosen):
                case = read(prepared/item['file'])
                order = ['E0','E1','E2']; order = order[index%3:]+order[:index%3]
                for arm in order:
                    generated = request_one(base,out,prepared,config,receipt['run_id'],case['case_id']+'-'+arm,case['arms'][arm]['messages'],experiment_start)
                    predictions.append({'case_id':case['case_id'],'arm':arm,**generated})
            save(out/'predictions_private.json',predictions)
            save(out/'prediction_seal.json',{'rows':len(predictions),'predictions_sha256':sha(out/'predictions_private.json'),'prepare_seal_sha256':config['prepare_seal_sha256']})
            # The model cannot access this file; reference SQL is first opened here,
            # after every prediction in this stage is durably sealed.
            references = read(prepared/'evaluation_private.json')
            schema_source = read(prepared/'sources_private.json')['inputs']['schema_json']['path']
            schemas = {row['db_id']: row for row in read(schema_source)}
            evaluations, metrics, slices, failures = [], {arm:Counter(cases=0) for arm in ('E0','E1','E2')}, {}, Counter()
            (out/'executions_private').mkdir()
            for item in chosen:
                case = read(prepared/item['file']); case_id=case['case_id']
                gold = references[case_id]
                reference = execute(gold['database_path'],gold['reference_sql'],config)
                with (out/'executions_private'/(case_id+'-reference.pickle')).open('xb') as target:pickle.dump(reference,target)
                for arm in ('E0','E1','E2'):
                    check_deadline(experiment_start, config)
                    generated = next(row for row in predictions if row['case_id']==case_id and row['arm']==arm)
                    predicted = execute(gold['database_path'],generated['sql'],config)
                    with (out/'executions_private'/(case_id+'-'+arm+'.pickle')).open('xb') as target:pickle.dump(predicted,target)
                    comparison = compare_execution(predicted,reference)
                    db_id = Path(gold['database_path']).stem
                    diagnostic = inputs.predicate_diagnostics(generated['sql'],gold['reference_sql'],schemas[db_id])
                    values=Counter(cases=1,executable=int(predicted['status']=='ok'),reference_executable=int(reference['status']=='ok'),
                                   set_correct=int(comparison['set_correct'] is True),bag_correct=int(comparison['bag_correct'] is True),
                                   comparison_unknown=int(comparison['set_correct'] is None or comparison['bag_correct'] is None),
                                   input_tokens=generated['usage']['prompt_tokens'],output_tokens=generated['usage']['completion_tokens'])
                    values.update(direct_literal_evaluable=int(diagnostic['direct_literal_set_exact'] is not None),
                                  direct_literal_set_exact=int(diagnostic['direct_literal_set_exact'] is True),
                                  direct_column_literal_pairs_evaluable=int(diagnostic['direct_column_literal_pairs_exact'] is not None),
                                  direct_column_literal_pairs_exact=int(diagnostic['direct_column_literal_pairs_exact'] is True),
                                  predicate_kind_set_exact=int(diagnostic['predicate_kind_set_exact'] is True))
                    metrics[arm].update(values)
                    for slice_key in ('cohort','binding_class','coverage_stratum','database_alias'):
                        key=slice_key+':'+case[slice_key]
                        slices.setdefault(key,{name:Counter() for name in ('E0','E1','E2')})[arm].update(values)
                    if predicted['status']!='ok':failures[arm+':'+predicted['status']+':'+predicted.get('error_type','')]+=1
                    evaluations.append({'case_id':case_id,'arm':arm,'cohort':case['cohort'],'database_alias':case['database_alias'],
                                        'prediction_status':predicted['status'],'reference_status':reference['status'],**comparison})
                    evaluations[-1]['predicate_diagnostic'] = diagnostic
            save(out/'evaluation_private.json',evaluations)
            if args.stage=='smoke' and (any(metrics[arm]['executable']==0 for arm in metrics) or sum(row['executable'] for row in metrics.values())<6):
                raise RuntimeError('Private feasibility smoke failed (<6/9 executable or an arm has zero); no retry')
            for arm, value in metrics.items():
                value['set_accuracy_all_selected']=value['set_correct']/value['cases']
                value['bag_accuracy_all_selected']=value['bag_correct']/value['cases']
            pairs={}
            for left,right in (('E0','E1'),('E0','E2'),('E1','E2')):
                paired=Counter()
                for case_id in [read(prepared/item['file'])['case_id'] for item in chosen]:
                    a,b=[next(row for row in evaluations if row['case_id']==case_id and row['arm']==arm)['set_correct'] for arm in (left,right)]
                    paired['unknown' if a is None or b is None else 'both_correct' if a and b else left+'_only' if a else right+'_only' if b else 'both_wrong']+=1
                pairs[left+'_vs_'+right]=paired
            summary={'stage':args.stage,'status':'completed','smoke_only':cohort_smoke,'cases':len(chosen),'arms':metrics,'slices':slices,
                     'paired_set_outcomes':pairs,'failures':failures,'semantic_review_status':'unverified','human_reviews':0,
                     'metric':'BIRD-compatible unordered Set/Bag, fixed projection order; float-only tolerance rel1e-6/abs1e-8; limits retained as unknown',
                     'decision':'diagnostic_pilot_only_no_default_replacement_no_automatic_expansion'}
        records=usage_records(base)
        summary['physical_requests_this_stage']=len(list((out/'requests').glob('*.response.json')))
        summary['api_usage_cumulative_experiment']={'input_tokens':sum(row.get('usage',{}).get('prompt_tokens',0) for row in records),
                                                  'output_tokens':sum(row.get('usage',{}).get('completion_tokens',0) for row in records),
                                                  'requests':len(records),'external_api_cost_CNY':'0.00','shared_gpu_compute_seconds':None,
                                                  'local_compute_cost':'unpriced','request_wall_seconds':sum(row['wall_seconds'] for row in records)}
        verify_database_hashes(prepared)
        check_deadline(experiment_start, config)
        save(out/'aggregate_summary.json',summary)
        check_deadline(experiment_start, config)
        receipt.update(state='completed',aggregate_sha256=sha(out/'aggregate_summary.json'))
    except Exception as error:
        receipt.update(state='failed',error_type=type(error).__name__)
        raise
    finally:
        receipt.update(cpu_seconds=time.process_time()-start_cpu,wall_seconds=time.perf_counter()-start_wall,finished_at_utc=datetime.now(timezone.utc).isoformat())
        save(out/'run_receipt.json',receipt)
        print(json.dumps({key:receipt.get(key) for key in ('run_id','stage','state','cpu_seconds','wall_seconds','error_type')}),flush=True)


if __name__ == '__main__':
    run()
