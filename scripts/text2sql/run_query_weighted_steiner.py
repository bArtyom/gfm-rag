"""Fixed-seed query-weighted FK pilot, with predictions sealed before evaluation."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import networkx as nx
import numpy as np
from query_weighted_steiner import predict, relation_descriptor, weighted_graph
from run_seed_steiner import coverage_summary, load_inputs, new_output, read_config, sha256, write_json, verify_database_hashes
from seed_steiner import rank_seed_tables, reference_tables, serialize_schema
from steiner_solvers import solve_steiner

ARMS = ['unit', 'weighted', 'dense']


def select_pilot(rows, count):
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row['alternative_route'], row['db_id'])].append(row)
    def key(row):
        return hashlib.sha256(f'weighted-pilot-v1:20261109:{row["db_id"]}:{row["question_id"]}'.encode()).hexdigest()
    for bucket in buckets.values():
        bucket.sort(key=key)
    strata = {flag: [] for flag in [True, False]}
    for flag in strata:
        keys = sorted(k for k in buckets if k[0] == flag)
        while any(buckets[k] for k in keys):
            for k in keys:
                if buckets[k]:
                    strata[flag].append(buckets[k].pop(0))
    result = []
    while len(result) < min(count, len(rows)):
        for flag in [True, False]:
            if strata[flag] and len(result) < count:
                result.append(strata[flag].pop(0))
    return result


def paired(rows, baseline):
    out = {'rescue': 0, 'damage': 0, 'unchanged': 0, 'unknown': 0}
    dbs = defaultdict(lambda: [0, 0])
    for r in rows:
        dbs[r['db_id']][1] += 1
        if r['gold'] is None:
            out['unknown'] += 1
            continue
        w = r['gold'] <= set(r['arms']['weighted']['nodes'])
        b = r['gold'] <= set(r['arms'][baseline]['nodes'])
        out['rescue' if w and not b else 'damage' if b and not w else 'unchanged'] += 1
        dbs[r['db_id']][0] += int(w) - int(b)
    out['delta_all_questions'] = (out['rescue'] - out['damage']) / len(rows) if rows else None
    if rows:
        values = np.array([dbs[d] for d in sorted(dbs)])
        rng = np.random.default_rng(20261109)
        draws = values[rng.integers(0, len(values), (10000, len(values)))].sum(axis=1)
        out['DB_cluster_descriptive_95_interval'] = np.quantile(draws[:, 0] / draws[:, 1], [.025, .975]).tolist()
    return out


def summarize(rows, schemas):
    out = {}
    for arm in ARMS:
        selected = [{'gold': r['gold'], 'tables': r['arms'][arm]['nodes'],
                     'columns': sum(t in r['arms'][arm]['nodes'] for t, _ in schemas[r['db_id']]['column_names_original'])}
                    for r in rows]
        out[arm] = coverage_summary(selected)
        out[arm]['mean_schema_tokens_embedding_tokenizer'] = float(np.mean([r['arms'][arm]['schema_tokens'] for r in rows])) if rows else None
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--relation-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['smoke', 'pilot', 'full'], required=True)
    args = parser.parse_args()
    os.umask(0o077)
    new_output(args.output)
    started = time.monotonic()
    config = read_config(args.config)
    if config['seed_count'] != 3 or config['solver'] != 'mehlhorn' or config['lambda_value'] != 1:
        raise ValueError('Frozen intervention changed')
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise ValueError('PYTHONHASHSEED=0 required')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    write_json(args.output / 'run_start.json', {'command': sys.argv, 'source_commit': commit,
        'timestamp_UTC': datetime.now(timezone.utc).isoformat(), 'config_sha256': sha256(args.config),
        'python': sys.version, 'executable': sys.executable,
        'dependencies': {p: importlib.metadata.version(p) for p in ['networkx', 'numpy', 'transformers', 'sqlglot']},
        'resources': {c: subprocess.check_output(c.split(), text=True) for c in ['nvidia-smi', 'free -h', 'nproc']},
        'environment': {k: os.environ.get(k) for k in ['CUDA_VISIBLE_DEVICES', 'PYTHONHASHSEED', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']}})
    for name, key in [('input_manifest_private.json', 'cache_source_receipt_sha256'), ('per_question_private.jsonl', 'cache_identity_receipt_sha256')]:
        if sha256(Path(config['cache_root']) / name) != config[key]:
            raise ValueError('Query cache receipt mismatch')
    inputs = load_inputs(config)
    receipt = json.loads((args.relation_cache / 'cache_receipt.json').read_text())
    if receipt['status'] != 'complete' or receipt['config_sha256'] != sha256(args.config):
        raise ValueError('Wrong relation cache configuration')
    for name, key in [('private_relations.json', 'relation_manifest_sha256'), ('relation_vectors.npz', 'relation_vectors_sha256')]:
        if sha256(args.relation_cache / name) != receipt[key]:
            raise ValueError('Relation cache file hash mismatch')
    records = json.loads((args.relation_cache / 'private_relations.json').read_text())
    expected = [{'db_id': db, 'constraint': c, 'text': relation_descriptor(inputs['schemas'][db], c)}
                for db in sorted(inputs['schemas']) for c in inputs['constraints'][db]]
    if records != expected:
        raise ValueError('Relation identity/order mismatch')
    with np.load(args.relation_cache / 'relation_vectors.npz', allow_pickle=False) as archive:
        relation_vectors = archive['vectors'].copy()
    if relation_vectors.shape != (len(records), 1024):
        raise ValueError('Relation vector shape mismatch')
    positions = {db: [i for i, n in enumerate(inputs['nodes']) if n['db_id'] == db] for db in inputs['schemas']}
    rel_positions = {db: [i for i, r in enumerate(records) if r['db_id'] == db] for db in inputs['schemas']}
    graphs, bridges = {}, {}
    for db, schema in inputs['schemas'].items():
        g, _ = weighted_graph(len(schema['table_names_original']), inputs['constraints'][db], np.ones(len(rel_positions[db])))
        graphs[db] = g
        bridges[db] = {tuple(sorted(e)) for e in nx.bridges(g)}
    candidates = []
    for qi, row in enumerate(inputs['questions']):
        db = row['db_id']
        indices = positions[db]
        scores = inputs['vectors'][indices] @ inputs['queries'][qi]
        ranking = rank_seed_tables(inputs['schemas'][db], [inputs['nodes'][i] for i in indices], scores, 3, 'table')
        unit = solve_steiner(graphs[db], ranking[:3], 'mehlhorn')
        candidates.append({'db_id': db, 'question_id': row['question_id'], 'qi': qi, 'ranking': ranking,
            'alternative_route': any(tuple(sorted(e)) not in bridges[db] for e in unit['edges'])})
    if args.mode == 'full':
        chosen = candidates
    else:
        chosen = select_pilot(candidates, 5 if args.mode == 'smoke' else config['pilot_questions'])
    from transformers import AutoTokenizer
    for name, expected_hash in config['embedding_support_sha256'].items():
        if sha256(Path(config['embedding_model']) / name) != expected_hash:
            raise ValueError('Tokenizer/model support changed')
    tokenizer = AutoTokenizer.from_pretrained(config['embedding_model'], local_files_only=True)
    token_counts = {}
    predictions = []
    for item in chosen:
        db, qi = item['db_id'], item['qi']
        result = predict(inputs['schemas'][db], inputs['constraints'][db], item['ranking'],
                         inputs['queries'][qi], relation_vectors[rel_positions[db]], 3)
        if result['alternative_route'] != item['alternative_route']:
            raise RuntimeError('Sampling stratum changed')
        for arm in ARMS:
            tables = result['arms'][arm]['nodes']
            key = (db, tuple(tables))
            if key not in token_counts:
                text = serialize_schema(inputs['schemas'][db], tables, inputs['constraints'][db])
                token_counts[key] = len(tokenizer.encode(text, add_special_tokens=False))
            result['arms'][arm]['schema_tokens'] = token_counts[key]
        if len(result['arms']['weighted']['nodes']) != len(result['arms']['dense']['nodes']):
            raise RuntimeError('Matched table counts differ')
        predictions.append({'db_id': db, 'question_id': item['question_id'], 'qi': qi, **result})
        if time.monotonic() - started > config['max_wall_seconds']:
            raise RuntimeError('Run wall budget exceeded')
    path = args.output / 'private_predictions.jsonl'
    with path.open('x') as f:
        for row in predictions:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
    seal = sha256(path)
    write_json(args.output / 'prediction_seal.json', {'sha256': seal, 'rows': len(predictions),
        'sealed_at_UTC': datetime.now(timezone.utc).isoformat(), 'labels_not_used_for_prediction': True})
    # First access to labels for evaluation, after all output selections are sealed.
    raw = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in raw}
    for row in predictions:
        try:
            row['gold'] = reference_tables(labels[(row['db_id'], row['question_id'])], inputs['schemas'][row['db_id']])
        except Exception as exc:
            row['gold'] = None
            row['parse_failure'] = type(exc).__name__
    comparisons = {arm: paired(predictions, arm) for arm in ['unit', 'dense']}
    pilot_pass = comparisons['unit']['delta_all_questions'] > 0 and comparisons['dense']['delta_all_questions'] >= 0
    final_pass = comparisons['unit']['delta_all_questions'] >= .01 and comparisons['dense']['delta_all_questions'] > 0
    actual = {db: sha256(Path(config['database_root']) / db / (db + '.sqlite')) for db in inputs['schemas']}
    verify_database_hashes(config['database_sha256'], actual)
    if sha256(path) != seal:
        raise RuntimeError('Sealed predictions changed')
    dbs = sorted(inputs['schemas'])
    result = {'run_id': config['run_id'], 'mode': args.mode, 'status': 'complete',
        'source_commit': commit, 'config_sha256': sha256(args.config), 'prediction_sha256': seal,
        'questions': len(predictions), 'candidate_questions': len(candidates),
        'candidate_alternative_route_questions': sum(r['alternative_route'] for r in candidates),
        'sample_alternative_route_questions': sum(r['alternative_route'] for r in predictions),
        'all': summarize(predictions, inputs['schemas']), 'paired': comparisons,
        'strata': {name: {'questions': len(sub), 'all': summarize(sub, inputs['schemas']),
            'paired': {a: paired(sub, a) for a in ['unit', 'dense']}}
            for name, sub in [('alternative_route', [r for r in predictions if r['alternative_route']]),
                              ('unique_route', [r for r in predictions if not r['alternative_route']])]},
        'per_database': {f'DB-{i+1:02d}': summarize([r for r in predictions if r['db_id'] == db], inputs['schemas']) for i, db in enumerate(dbs)},
        'changed_table_sets': sum(r['arms']['unit']['nodes'] != r['arms']['weighted']['nodes'] for r in predictions),
        'changed_edge_sets': sum(r['arms']['unit']['edges'] != r['arms']['weighted']['edges'] for r in predictions),
        'changed_constraint_sets': sum(r['arms']['unit']['constraint_ids'] != r['arms']['weighted']['constraint_ids'] for r in predictions),
        'forest_questions': sum(not r['arms']['weighted']['connected'] for r in predictions),
        'pilot_gate_pass': pilot_pass, 'final_upgrade_gate_pass': final_pass,
        'decision': 'smoke_pass' if args.mode == 'smoke' else
            ('expand_to_full' if pilot_pass else 'stop_negative_pilot') if args.mode == 'pilot' else
            ('conditional_shuffle_ablation' if final_pass else 'conclude_no_upgrade'),
        'wall_seconds': time.monotonic() - started, 'process_CPU_seconds': time.process_time(),
        'peak_RSS_GiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
        'new_model_calls_this_retrieval_run': 0, 'external_API_cost_CNY': '0.00', 'GPU_seconds': 0,
        'local_CPU_monetized': False, 'database_hashes_unchanged': True,
        'limitations': ['exploratory reused BIRD-dev; pilot topology-stratified, not population estimate',
            'reference-table coverage, no SQL EX or adjudicated FK role accuracy',
            'schema tokens measured by Qwen embedding tokenizer, not SQL generation usage',
            'FP32 HF relation vectors vs historical vLLM query cache; five-query compatibility probe only',
            'lambda=1 deliberately bounded costs may not change longer routes',
            'all legitimate intra-sub-schema FK constraints retained; tree is not mandated SQL join plan']}
    write_json(args.output / 'aggregate_summary.json', result)
    print(json.dumps({k: result[k] for k in ['mode', 'questions', 'candidate_alternative_route_questions',
        'sample_alternative_route_questions', 'all', 'paired', 'changed_table_sets', 'changed_constraint_sets', 'decision', 'wall_seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
