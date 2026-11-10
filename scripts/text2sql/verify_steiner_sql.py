"""Independent sealed-output/ledger audit and bounded SQL re-execution; no inference."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import time

import numpy as np

from run_seed_steiner import read_config, sha256, write_json, new_output
from seed_steiner import reference_tables
from steiner_sql import ARMS, choose_pilot, payload_key
from steiner_sql_runtime import read_reference_rows, session_members
from p2d_sql_evaluator import execute_readonly, compare_rows


def load(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser()
    for name in ['config', 'prepared', 'execution', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    new_output(args.output)
    began = time.monotonic()
    cfg = read_config(args.config)
    manifest = load(args.prepared / 'manifest.json')
    assert sha256(args.config) == manifest['config_sha256']
    assert sha256(args.prepared / 'online_private.jsonl') == manifest['online_sha256']
    assert sha256(Path(cfg['previous_predictions'])) == cfg['previous_prediction_sha256']
    assert sha256(Path(__file__).parent / 'p2d_sql_evaluator.py') == cfg['evaluator_sha256']
    for db, expected in cfg['database_sha256'].items():
        assert sha256(Path(cfg['database_root']) / db / (db + '.sqlite')) == expected
    rows = list(map(json.loads, (args.prepared / 'online_private.jsonl').read_text().splitlines()))
    identity = lambda r: (r['db_id'], r['question_id'])
    primary = {identity(r) for r in choose_pilot(rows, 100)}
    assert primary == {identity(r) for r in rows if r['primary']}
    assert len(primary) == 100
    previous = {identity(r): r for r in map(json.loads, Path(cfg['previous_predictions']).read_text().splitlines())}
    payloads = {}
    for row in rows:
        for arm in ARMS:
            item = row['arms'][arm]
            assert set(item['messages'][0]) == {'role', 'content'}
            payload = {'model': cfg['served_model'], 'messages': item['messages'], **cfg['generation']}
            assert payload_key(payload) == item['payload_key']
            payloads[item['payload_key']] = item
            if arm != 'full':
                assert item['tables'] == previous[identity(row)]['arms'][arm]['nodes']
        assert row['changed_schema'] == (row['arms']['unit']['tables'] != row['arms']['weighted']['tables'])
    cohorts = {'smoke': [r for r in rows if r['smoke']], 'pilot': [r for r in rows if r['primary']],
               'diagnostic': [r for r in rows if r['changed_schema']]}
    assert [len(v) for v in cohorts.values()] == [5, 100, 37]
    assert {identity(r) for r in cohorts['smoke']} <= primary
    requests = {f.stem: load(f) for f in (args.execution / 'requests').glob('*.json')}
    requested = set()
    totals = Counter()
    for key, record in requests.items():
        assert key in payloads and record['payload_sha256'] == key
        assert record['call_id'] == cfg['run_id'] + '/' + key
        assert record['http_status'] == 200 and record['error_type'] is None
        usage = record['usage']
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        assert usage['prompt_tokens'] == payloads[key]['prompt_tokens_preflight']
        totals.update(requests=1, input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'], total_tokens=usage['total_tokens'])
    spec = importlib.util.spec_from_file_location('usage', cfg['ledger_module'])
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    with sqlite3.connect('file:' + str(ledger.DEFAULT_DB) + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        entries = list(conn.execute('SELECT * FROM calls WHERE project=? AND run_id=?', ('seed-steiner', cfg['run_id'])))
    assert len(entries) == len(requests)
    expected_events = {hashlib.sha256(('local-vllm-steiner-sql|' + r['call_id']).encode()).hexdigest(): r for r in requests.values()}
    for entry in entries:
        record = expected_events[entry['event_id']]
        assert entry['usage_reported'] == 1
        assert entry['input_tokens'] == record['usage']['prompt_tokens']
        assert entry['output_tokens'] == record['usage']['completion_tokens']
        assert entry['total_tokens'] == record['usage']['total_tokens']
    labels = {identity(r): r['SQL'] for r in read_reference_rows(cfg)}
    schema_file = Path(cfg['dataset_root']) / 'dev_tables.json'
    assert sha256(schema_file) == cfg['schema_sha256']
    schemas = {s['db_id']: s for s in load(schema_file)}
    executed = {}
    def execute(db, sql):
        key = (db, sql)
        if key not in executed:
            executed[key] = execute_readonly(Path(cfg['database_root']) / db / (db + '.sqlite'), sql,
                timeout=cfg['sql_timeout'], row_limit=cfg['sql_row_limit'], byte_limit=cfg['sql_byte_limit'], sqlite_memory_limit=cfg['sql_memory_limit'])
        return executed[key]
    reports = {}
    replay_differences = []
    for stage, selected in cohorts.items():
        folder = args.execution / stage
        summary = load(folder / 'aggregate_summary.json')
        predictions = load(folder / 'predictions_private.json')
        seal = load(folder / 'prediction_seal.json')
        assert sha256(folder / 'predictions_private.json') == seal['sha256'] == summary['prediction_sha256']
        assert seal['rows'] == len(selected) * 3 == len(predictions)
        saved = load(folder / 'evaluation_private.json')
        assert len(saved) == len(predictions)
        logical = {a: Counter() for a in ARMS}
        statuses = {a: Counter() for a in ARMS}
        coverage = {a: Counter() for a in ARMS}
        per_question = {}
        new_keys = set()
        for index, row in enumerate(selected):
            ref = execute(row['db_id'], labels[identity(row)])
            gold_tables = reference_tables(labels[identity(row)], schemas[row['db_id']])
            per_question[identity(row)] = {}
            for ai, arm in enumerate(ARMS):
                pred, old = predictions[index * 3 + ai], saved[index * 3 + ai]
                assert identity(pred) == identity(row) and pred['arm'] == arm
                key = row['arms'][arm]['payload_key']
                assert key == pred['payload_key'] and requests[key]['usage'] == pred['logical_usage']
                content = requests[key]['response']['choices'][0]['message']['content'].strip()
                import re
                match = re.fullmatch(r'```(?:sql|sqlite)?\s*\n?(.*?)\n?```', content, re.I | re.S)
                if match: content = match.group(1).strip()
                if content.startswith('SQL:'): content = content[4:].strip()
                assert content == pred['sql']
                new_keys.add(key)
                answer = execute(row['db_id'], pred['sql'])
                comparison = {'set_correct': None, 'bag_correct': None, 'comparison_status': 'execution_unavailable'}
                if ref['status'] == answer['status'] == 'ok':
                    comparison = compare_rows(answer['rows'], ref['rows']) if len(answer['columns']) == len(ref['columns']) else dict(set_correct=False, bag_correct=False, comparison_status='column_count_mismatch')
                replay = dict(prediction_status=answer['status'], reference_status=ref['status'], **comparison)
                if any(old[k] != v for k, v in replay.items()):
                    replay_differences.append(dict(stage=stage, identity_sha256=hashlib.sha256(repr(identity(row)).encode()).hexdigest(), arm=arm, original={k: old[k] for k in replay}, replay=replay))
                # Frozen first evaluations are the reported outcomes, not best-of replay.
                logical[arm].update(questions=1, set_correct=int(old['set_correct'] is True), bag_correct=int(old['bag_correct'] is True), unknown=int(old['set_correct'] is None),
                    executable=int(old['prediction_status'] == 'ok'), input_tokens=pred['logical_usage']['prompt_tokens'], output_tokens=pred['logical_usage']['completion_tokens'], truncated=int(pred['finish_reason'] == 'length'))
                statuses[arm].update(['reference:' + old['reference_status'], 'prediction:' + old['prediction_status'], 'comparison:' + old['comparison_status']])
                covered = gold_tables <= set(row['arms'][arm]['tables'])
                coverage[arm].update(covered=int(covered), missing=int(not covered), correct_with_missing=int(not covered and old['set_correct'] is True), correct_with_coverage=int(covered and old['set_correct'] is True))
                per_question[identity(row)][arm] = old['set_correct'] is True
        assert summary['new_physical_requests'] == len(new_keys - requested)
        requested.update(new_keys)
        assert summary['cumulative_physical_requests'] == len(requested)
        for arm in ARMS:
            assert all(summary['arms'][arm][k] == v for k, v in logical[arm].items())
        rng = np.random.default_rng(20261110)
        dbs = sorted({r['db_id'] for r in selected})
        differences = []
        for _ in range(10000):
            draw = rng.choice(dbs, size=len(dbs), replace=True)
            vals = [int(v['weighted']) - int(v['full']) for db in draw for (d, _), v in per_question.items() if d == db]
            differences.append(float(np.mean(vals)))
        binary_pairs = {}
        for baseline, arm in [('full', 'unit'), ('full', 'weighted'), ('unit', 'weighted')]:
            binary_pairs[arm + '_vs_' + baseline] = dict(Counter('rescue' if v[arm] and not v[baseline] else 'damage' if v[baseline] and not v[arm] else 'unchanged' for v in per_question.values()))
        reports[stage] = dict(summary=summary, statuses={a: dict(c) for a, c in statuses.items()}, coverage={a: dict(c) for a, c in coverage.items()},
            binary_pairs_unknown_as_unconfirmed=binary_pairs,
            descriptive_cluster_bootstrap_weighted_minus_full_95pct=np.quantile(differences, [.025, .975]).tolist(), cluster_count=len(dbs))
        print(json.dumps({'audit_stage': stage, 'questions': len(selected), 'replay_differences': len(replay_differences)}), flush=True)
    assert requested == set(requests)
    completion = load(args.execution / 'completion.json')
    pilot = reports['pilot']['summary']
    gate = pilot['arms']['weighted']['set_correct'] >= pilot['arms']['full']['set_correct'] - 1 and pilot['logical_weighted_input_reduction'] >= .15
    assert completion['primary_gate_pass'] == gate == False
    assert completion['full_run'] is False and not (args.execution / 'full').exists()
    cleanup = load(args.execution / 'service_stop.json')
    assert cleanup['all_owned_processes_exited'] and cleanup['port_closed']
    assert not session_members(cleanup['owned_session_id'])
    startup = load(args.execution.parent / 'execution_001' / 'service_stop.json')
    assert not list((args.execution.parent / 'execution_001' / 'requests').glob('*.json'))
    accounting = ledger.totals()
    this_run = next(r for r in accounting.pop('by_project_and_run') if r['project'] == 'seed-steiner' and r['run_id'] == cfg['run_id'])
    assert this_run['reported_total_tokens'] == totals['total_tokens']
    write_json(args.output / 'usage.json', dict(this_run=this_run, cross_project_cumulative=accounting,
        external_API_cost_CNY='0.00', local_GPU_cost_monetized=False,
        total_reserved_GPU_seconds=startup['reserved_GPU_seconds'] + cleanup['reserved_GPU_seconds'],
        resource_time_basis='two allocated GPUs times service wall; includes interrupted startup, not measured kernel time'))
    write_json(args.output / 'audit.json', dict(status='PASS' if not replay_differences else 'PASS_WITH_REPLAY_DIFFERENCES',
        stages=reports, physical_requests=dict(totals), unique_SQL_executions=len(executed), replay_differences=replay_differences,
        cohort_overlap_primary_diagnostic=len(primary & {identity(r) for r in cohorts['diagnostic']}),
        decision='stop; primary expansion gate failed', cleanup_verified=True, wall_seconds=time.monotonic() - began))


if __name__ == '__main__':
    main()
