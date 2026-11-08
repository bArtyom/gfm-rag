"""Frozen-cache seed/Steiner pilot. Predictions are sealed before label scoring."""
from __future__ import annotations

import argparse
from collections import Counter
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

import numpy as np

from seed_steiner import choose_split, connect_schema, load_upstream, rank_seed_tables, read_constraints, reference_tables

ARMS = ['seed_only', 'dense_size_matched', 'seed_steiner']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def new_output(path):
    Path(path).mkdir(parents=True, exist_ok=False, mode=0o700)


def read_config(path):
    raw = Path(path).read_text()
    config = json.loads(os.path.expandvars(raw))
    if '${' in json.dumps(config):
        raise ValueError('Unresolved config environment variable')
    return config


def verify_identity(online, cached):
    identities = lambda rows: [(r['db_id'], int(r['question_id'])) for r in rows]
    if identities(online) != identities(cached):
        raise ValueError('Cache row order/identity mismatch')


def verify_database_hashes(expected, actual):
    if expected != actual:
        raise ValueError('Database snapshot differs from the frozen configuration')


def load_inputs(config):
    data = Path(config['dataset_root'])
    cache = Path(config['cache_root'])
    files = {'questions': data / 'dev.json', 'schema': data / 'dev_tables.json',
             'cache': cache / 'embedding_cache_private.npz', 'node_manifest': cache / 'ordered_node_manifest.json'}
    for name, path in files.items():
        if sha256(path) != config[name + '_sha256']:
            raise ValueError('Input hash mismatch: ' + name)
    manifest = json.loads((cache / 'input_manifest_private.json').read_text())
    if manifest['input_hashes']['questions'] != config['questions_sha256'] or manifest['input_hashes']['schema'] != config['schema_sha256']:
        raise ValueError('Cache source manifest mismatch')
    # Expose only online fields to prediction. Reference SQL is reopened later.
    questions = [{k: row[k] for k in ['db_id', 'question_id', 'question', 'evidence']} for row in json.loads(files['questions'].read_text())]
    with (cache / 'per_question_private.jsonl').open() as stream:
        cached_identity = [{k: row[k] for k in ['db_id', 'question_id']} for row in map(json.loads, stream)]
    verify_identity(questions, cached_identity)
    schemas = {s['db_id']: s for s in json.loads(files['schema'].read_text())}
    nodes = json.loads(files['node_manifest'].read_text())
    if [n['ordinal'] for n in nodes] != list(range(len(nodes))):
        raise ValueError('Node manifest order mismatch')
    with np.load(files['cache'], allow_pickle=False) as archive:
        queries = archive['query_vectors'].astype('float32')
        vectors = archive['node_vectors'].astype('float32')
    if queries.shape != (len(questions), 1024) or vectors.shape != (len(nodes), 1024):
        raise ValueError('Cache dimensions mismatch')
    for matrix in [queries, vectors]:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if not np.isfinite(matrix).all() or (norms <= 0).any():
            raise ValueError('Invalid cached embedding')
        matrix /= norms
    upstream_commit = subprocess.check_output(['git', '-C', config['upstream_path'], 'rev-parse', 'HEAD'], text=True).strip()
    if upstream_commit != config['upstream_commit']:
        raise ValueError('Upstream version mismatch')
    if subprocess.check_output(['git', '-C', config['upstream_path'], 'status', '--porcelain'], text=True).strip():
        raise ValueError('Upstream checkout is modified')
    constraints, db_hashes = {}, {}
    for db, schema in schemas.items():
        path = Path(config['database_root']) / db / (db + '.sqlite')
        db_hashes[db] = sha256(path)
    if 'database_sha256' in config:
        verify_database_hashes(config['database_sha256'], db_hashes)
    for db, schema in schemas.items():
        path = Path(config['database_root']) / db / (db + '.sqlite')
        constraints[db] = read_constraints(schema, path)
    return {'questions': questions, 'schemas': schemas, 'nodes': nodes, 'queries': queries,
            'vectors': vectors, 'constraints': constraints, 'database_hashes': db_hashes}


def coverage_summary(rows):
    evaluable = [r for r in rows if r['gold'] is not None]
    complete = sum(r['gold'] <= set(r['tables']) for r in evaluable)
    return {'questions': len(rows), 'reference_parse_failures': len(rows) - len(evaluable),
            'complete': complete, 'complete_rate_all_questions': complete / len(rows) if rows else None,
            'mean_table_recall_evaluable': float(np.mean([len(r['gold'] & set(r['tables'])) / len(r['gold']) for r in evaluable])) if evaluable else None,
            'mean_table_precision_evaluable': float(np.mean([len(r['gold'] & set(r['tables'])) / len(r['tables']) for r in evaluable])) if evaluable else None,
            'mean_selected_tables': float(np.mean([len(r['tables']) for r in rows])) if rows else None,
            'mean_selected_columns': float(np.mean([r['columns'] for r in rows])) if rows else None}


def paired_counts(rows, baseline):
    result = Counter()
    for row in rows:
        if row['gold'] is None:
            result['unknown'] += 1
            continue
        ours = row['gold'] <= set(row['arms']['seed_steiner'])
        base = row['gold'] <= set(row['arms'][baseline])
        result['rescue' if ours and not base else 'damage' if base and not ours else 'unchanged'] += 1
    return dict(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['smoke', 'retrieval'], required=True)
    args = parser.parse_args()
    new_output(args.output)
    os.umask(0o077)
    started = time.monotonic()
    config = read_config(args.config)
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    write_json(args.output / 'run_start.json', {'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_commit': source_commit, 'command': sys.argv, 'config_sha256': sha256(args.config),
        'python': sys.version, 'executable': sys.executable,
        'dependencies': {p: importlib.metadata.version(p) for p in ['numpy', 'networkx', 'sqlglot']},
        'resource_snapshot': {command: subprocess.check_output(command.split(), text=True) for command in ['nvidia-smi', 'free -h', 'nproc']}})
    inputs = load_inputs(config)
    split = choose_split(inputs['questions'], config['seed'], per_database=config['sql_per_database'])
    write_json(args.output / 'private_split.json', split)
    identities = set(map(tuple, split['smoke'])) if args.mode == 'smoke' else None
    upstream = load_upstream(config['upstream_path'])
    node_indices = {db: [i for i, n in enumerate(inputs['nodes']) if n['db_id'] == db] for db in inputs['schemas']}
    predictions = []
    for qi, row in enumerate(inputs['questions']):
        if identities is not None and (row['db_id'], row['question_id']) not in identities:
            continue
        db = row['db_id']
        schema = inputs['schemas'][db]
        positions = node_indices[db]
        scores = inputs['vectors'][positions] @ inputs['queries'][qi]
        ranking = rank_seed_tables(schema, [inputs['nodes'][i] for i in positions], scores, config['seed_count'], config['seed_source'])
        if len(ranking) != len(schema['table_names_original']):
            raise ValueError('Incomplete table ranking')
        seeds = ranking[:config['seed_count']]
        closure = connect_schema(schema, inputs['constraints'][db], seeds, upstream)
        if not set(seeds) <= set(closure['tables']):
            raise AssertionError('Seed dropped')
        predictions.append({'question_id': row['question_id'], 'db_id': db,
            'seeds': seeds, 'ranking': ranking, 'connected': closure['connected'],
            'bridge_tables': closure['bridge_tables'], 'arms': {'seed_only': sorted(seeds),
            'dense_size_matched': sorted(ranking[:len(closure['tables'])]), 'seed_steiner': closure['tables']}})
    path = args.output / 'private_predictions.jsonl'
    with path.open('x') as stream:
        for row in predictions:
            stream.write(json.dumps(row, sort_keys=True) + '\n')
    prediction_hash = sha256(path)
    write_json(args.output / 'prediction_seal.json', {'sha256': prediction_hash,
        'sealed_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': len(predictions)})
    # Label evaluation begins only after prediction sealing.
    raw = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in raw}
    for row in predictions:
        schema = inputs['schemas'][row['db_id']]
        try:
            row['gold'] = reference_tables(labels[(row['db_id'], row['question_id'])], schema)
        except Exception as exc:
            row['gold'] = None
            row['parse_failure'] = type(exc).__name__
    def summarize(rows):
        return {arm: coverage_summary([{'gold': r['gold'], 'tables': r['arms'][arm],
            'columns': sum(t in r['arms'][arm] for t, _ in inputs['schemas'][r['db_id']]['column_names_original'])} for r in rows]) for arm in ARMS}
    expandable = [r for r in predictions if r['bridge_tables']]
    comparisons = {arm: paired_counts(expandable, arm) for arm in ARMS[:2]}
    positive = all(c.get('rescue', 0) > c.get('damage', 0) for c in comparisons.values())
    dbs = sorted({r['db_id'] for r in predictions})
    aggregate = {'run_id': config['run_id'], 'mode': args.mode, 'status': 'completed',
        'source_commit': source_commit, 'prediction_sha256': prediction_hash,
        'questions': len(predictions), 'databases': len(dbs), 'expanded_questions': len(expandable),
        'disconnected_questions': sum(not r['connected'] for r in predictions),
        'all': summarize(predictions), 'expanded': summarize(expandable), 'paired_expanded': comparisons,
        'per_database': {f'DB-{i + 1:02d}': summarize([r for r in predictions if r['db_id'] == db]) for i, db in enumerate(dbs)},
        'structural_signal': positive, 'decision': 'conditional_SQL_pilot' if positive else 'stop_no_structural_signal',
        'new_model_calls': 0, 'new_input_tokens': 0, 'new_output_tokens': 0, 'external_API_cost_CNY': '0',
        'elapsed_wall_seconds': time.monotonic() - started, 'cpu_seconds': time.process_time(),
        'peak_RSS_GiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2),
        'limitations': ['exploratory reused BIRD dev', 'reference-table proxy not unique semantic truth',
            'table counts matched, generator token counts not matched', 'full columns retained per selected table',
            'upstream component adaptation, not full GRAST-SQL reproduction']}
    if sha256(path) != prediction_hash:
        raise AssertionError('Predictions changed after sealing')
    after = {db: sha256(Path(config['database_root']) / db / (db + '.sqlite')) for db in dbs}
    if any(after[db] != inputs['database_hashes'][db] for db in dbs):
        raise ValueError('Source database changed')
    write_json(args.output / 'private_input_receipt.json', {'config': config, 'database_hashes': inputs['database_hashes'],
        'foreign_key_constraints': {db: len(cs) for db, cs in inputs['constraints'].items()}, 'databases_unchanged': True})
    write_json(args.output / 'aggregate_summary.json', aggregate)
    print(json.dumps({k: aggregate[k] for k in ['mode', 'questions', 'expanded_questions', 'disconnected_questions', 'all', 'paired_expanded', 'structural_signal', 'decision', 'elapsed_wall_seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
