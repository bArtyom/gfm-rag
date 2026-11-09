"""Frozen-seed five-solver experiment; no inference and no labels before sealing."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import networkx as nx
import numpy as np
from extended_steiner_solvers import METHODS, UncertifiedMILP, solve
from query_weighted_steiner import relation_costs, relation_descriptor, weighted_graph
from run_seed_steiner import coverage_summary, load_inputs, new_output, read_config, sha256, write_json, verify_database_hashes
from seed_steiner import choose_split, rank_seed_tables, reference_tables
from steiner_solvers import small_terminal_optimum


def summarize(rows, schemas):
    out = {'questions': len(rows), 'methods': {}, 'vs_mehlhorn': {}}
    for method in METHODS:
        selected = [{'gold': r['gold'], 'tables': r['methods'][method]['nodes'],
            'columns': sum(t in r['methods'][method]['nodes'] for t, _ in schemas[r['db_id']]['column_names_original'])} for r in rows]
        stats = coverage_summary(selected)
        costs = [r['methods'][method]['cost'] for r in rows]
        times = [r['methods'][method]['elapsed_seconds'] for r in rows]
        positive = [r for r in rows if r['oracle_cost'] > 1e-12]
        proofs = [p for r in rows for p in r['methods'][method]['certificates']]
        stats.update({'total_cost': float(sum(costs)), 'mean_cost': float(np.mean(costs)) if rows else None,
            'optimal_cost_questions': sum(math.isclose(r['methods'][method]['cost'], r['oracle_cost'], rel_tol=1e-8, abs_tol=1e-7) for r in rows),
            'mean_cost_excess_over_oracle': float(np.mean([r['methods'][method]['cost'] - r['oracle_cost'] for r in rows])) if rows else None,
            'max_cost_ratio_positive_oracle': max((r['methods'][method]['cost'] / r['oracle_cost'] for r in positive), default=None),
            'zero_oracle_questions': len(rows) - len(positive),
            'latency_median_ms': float(np.median(times) * 1000) if rows else None,
            'latency_p95_ms': float(np.quantile(times, .95) * 1000) if rows else None,
            'solver_wall_seconds': sum(times), 'MILP_component_calls': len(proofs),
            'MILP_certified_component_calls': sum(p['status'] == 0 and p['mip_gap'] <= 1e-8 for p in proofs),
            'certified_optimal_questions': sum(r['methods'][method]['certified_optimal'] for r in rows),
            'forest_questions': sum(not r['methods'][method]['connected'] for r in rows)})
        out['methods'][method] = stats
        pair = Counter({k: 0 for k in ['rescue', 'damage', 'unchanged', 'unknown', 'strictly_cheaper',
            'strictly_costlier', 'changed_tables', 'changed_tables_equal_cost', 'changed_constraints']})
        db_delta = defaultdict(lambda: [0, 0])
        for r in rows:
            value, baseline = r['methods'][method], r['methods']['mehlhorn']
            equal = math.isclose(value['cost'], baseline['cost'], rel_tol=1e-8, abs_tol=1e-7)
            changed = value['nodes'] != baseline['nodes']
            pair['strictly_cheaper'] += not equal and value['cost'] < baseline['cost']
            pair['strictly_costlier'] += not equal and value['cost'] > baseline['cost']
            pair['changed_tables'] += changed
            pair['changed_tables_equal_cost'] += changed and equal
            pair['changed_constraints'] += sorted(value['constraint_ids']) != sorted(baseline['constraint_ids'])
            db_delta[r['db_id']][1] += 1
            if r['gold'] is None:
                pair['unknown'] += 1
                continue
            ours = r['gold'] <= set(value['nodes'])
            base = r['gold'] <= set(baseline['nodes'])
            pair['rescue' if ours and not base else 'damage' if base and not ours else 'unchanged'] += 1
            db_delta[r['db_id']][0] += int(ours) - int(base)
        result = dict(pair)
        result['coverage_delta'] = (pair['rescue'] - pair['damage']) / len(rows) if rows else None
        if rows:
            values = np.array([db_delta[k] for k in sorted(db_delta)])
            draws = values[np.random.default_rng(20261109).integers(0, len(values), (10000, len(values)))].sum(axis=1)
            result['DB_cluster_descriptive_95_interval'] = np.quantile(draws[:, 0] / draws[:, 1], [.025, .975]).tolist()
        out['vs_mehlhorn'][method] = result
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--setting', choices=['unit', 'weighted'], required=True)
    parser.add_argument('--mode', choices=['smoke', 'full'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    new_output(args.output)
    started = time.monotonic()
    config = read_config(args.config)
    if config['methods'] != METHODS or config['seed_count'] != 3 or config['lambda_value'] != 1 or config['milp_rel_gap'] != 0 or config['milp_threads'] != 1:
        raise ValueError('Frozen configuration changed')
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise ValueError('PYTHONHASHSEED=0 required')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    write_json(args.output / 'run_start.json', {'source_commit': commit, 'command': sys.argv,
        'started_at_UTC': datetime.now(timezone.utc).isoformat(), 'config_sha256': sha256(args.config),
        'python': sys.version, 'executable': sys.executable,
        'dependencies': {p: importlib.metadata.version(p) for p in ['numpy', 'scipy', 'networkx', 'sqlglot']},
        'environment': {k: os.environ.get(k) for k in ['PYTHONHASHSEED', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'CUDA_VISIBLE_DEVICES']},
        'resources': {c: subprocess.check_output(c.split(), text=True) for c in ['nvidia-smi', 'free -h', 'nproc']}})
    cache = Path(config['relation_cache'])
    for path, expected in [(cache / 'cache_receipt.json', config['relation_receipt_sha256']),
        (cache / 'relation_vectors.npz', config['relation_vector_sha256']),
        (cache / 'private_relations.json', config['relation_manifest_sha256']),
        (Path(config['previous_predictions']), config['previous_prediction_sha256'])]:
        if sha256(path) != expected:
            raise ValueError('Frozen cache/prior prediction hash mismatch')
    for name, key in [('input_manifest_private.json', 'cache_source_receipt_sha256'), ('per_question_private.jsonl', 'cache_identity_receipt_sha256')]:
        if sha256(Path(config['cache_root']) / name) != config[key]:
            raise ValueError('Frozen query receipt mismatch')
    inputs = load_inputs(config)
    records = json.loads((cache / 'private_relations.json').read_text())
    expected = [{'db_id': db, 'constraint': c, 'text': relation_descriptor(inputs['schemas'][db], c)}
                for db in sorted(inputs['schemas']) for c in inputs['constraints'][db]]
    if records != expected:
        raise ValueError('Relation ordering or identity mismatch')
    with np.load(cache / 'relation_vectors.npz', allow_pickle=False) as archive:
        vectors = archive['vectors'].copy()
    if vectors.shape != (len(records), 1024):
        raise ValueError('Relation shape mismatch')
    previous = {(r['db_id'], r['question_id']): r for r in map(json.loads, Path(config['previous_predictions']).read_text().splitlines())}
    node_positions = {db: [i for i, r in enumerate(inputs['nodes']) if r['db_id'] == db] for db in inputs['schemas']}
    rel_positions = {db: [i for i, r in enumerate(records) if r['db_id'] == db] for db in inputs['schemas']}
    smoke = set(map(tuple, choose_split(inputs['questions'], config['seed'])['smoke']))
    predictions = []
    path = args.output / 'private_predictions.jsonl'
    with path.open('x') as stream:
        for qi, row in enumerate(inputs['questions']):
            db = row['db_id']
            if args.mode == 'smoke' and (db, row['question_id']) not in smoke:
                continue
            positions = node_positions[db]
            ranking = rank_seed_tables(inputs['schemas'][db], [inputs['nodes'][i] for i in positions],
                inputs['vectors'][positions] @ inputs['queries'][qi], 3, 'table')
            seeds = sorted(ranking[:3])
            relation_weights = relation_costs(inputs['queries'][qi], vectors[rel_positions[db]])
            if args.setting == 'unit':
                relation_weights = np.ones(len(relation_weights))
            graph, identities = weighted_graph(len(ranking), inputs['constraints'][db], relation_weights)
            oracle = small_terminal_optimum(graph, seeds)
            offset = (qi + (args.setting == 'weighted')) % len(METHODS)
            order = METHODS[offset:] + METHODS[:offset]
            results = {}
            for method in order:
                try:
                    result = solve(graph, seeds, method, config['milp_time_limit_seconds'])
                except BaseException as exc:
                    write_json(args.output / 'failure_receipt.json', {'completed_questions': len(predictions),
                        'question_ordinal': qi, 'method': method, 'exception': type(exc).__name__,
                        'MILP_certificate': exc.certificate if isinstance(exc, UncertifiedMILP) else None})
                    raise
                if result['cost'] < oracle - 1e-7 or (result['certified_optimal'] and not math.isclose(result['cost'], oracle, rel_tol=1e-8, abs_tol=1e-7)):
                    raise RuntimeError('Independent objective oracle mismatch')
                result['constraint_ids'] = [identities[tuple(e)]['id'] for e in result['edges']]
                results[method] = result
            prior = previous[(db, row['question_id'])]
            baseline = prior['arms'][args.setting]
            if prior['seeds'] != seeds or any(results['mehlhorn'][k] != baseline[k] for k in ['nodes', 'edges', 'constraint_ids']):
                raise RuntimeError('Mehlhorn replay of previous frozen experiment differs')
            if not math.isclose(results['mehlhorn']['cost'], baseline['cost'], abs_tol=1e-9):
                raise RuntimeError('Previous objective replay differs')
            prediction = {'db_id': db, 'question_id': row['question_id'], 'qi': qi, 'seeds': seeds,
                'oracle_cost': oracle, 'method_order': order, 'methods': results}
            stream.write(json.dumps(prediction, sort_keys=True, allow_nan=False) + '\n')
            predictions.append(prediction)
            if len(predictions) % 100 == 0:
                stream.flush()
                print(json.dumps({'setting': args.setting, 'completed': len(predictions), 'wall_seconds': time.monotonic() - started}), flush=True)
            if time.monotonic() - started > config['max_wall_seconds']:
                raise RuntimeError('Overall wall budget exceeded')
    digest = sha256(path)
    write_json(args.output / 'prediction_seal.json', {'sha256': digest, 'rows': len(predictions),
        'sealed_at_UTC': datetime.now(timezone.utc).isoformat(), 'prior_Mehlhorn_replay': True})
    # Evaluation only after complete predictions have been sealed.
    raw = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in raw}
    for r in predictions:
        try:
            r['gold'] = reference_tables(labels[(r['db_id'], r['question_id'])], inputs['schemas'][r['db_id']])
        except Exception as exc:
            r['gold'] = None
            r['parse_failure'] = type(exc).__name__
    aggregate = summarize(predictions, inputs['schemas'])
    actual = {db: sha256(Path(config['database_root']) / db / (db + '.sqlite')) for db in inputs['schemas']}
    verify_database_hashes(config['database_sha256'], actual)
    if sha256(path) != digest:
        raise RuntimeError('Predictions changed after evaluation')
    aggregate.update({'run_id': config['run_id'], 'setting': args.setting, 'mode': args.mode,
        'status': 'complete', 'source_commit': commit, 'config_sha256': sha256(args.config),
        'prediction_sha256': digest, 'solver_calls': len(predictions) * len(METHODS),
        'per_database': {f'DB-{i+1:02d}': summarize([r for r in predictions if r['db_id'] == db], inputs['schemas'])
                         for i, db in enumerate(sorted({r['db_id'] for r in predictions}))},
        'new_model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'GPU_seconds': 0,
        'external_API_cost_CNY': '0.00', 'local_CPU_monetized': False,
        'prior_Mehlhorn_replay': True, 'database_hashes_unchanged': True,
        'wall_seconds': time.monotonic() - started, 'process_CPU_seconds': time.process_time(),
        'peak_RSS_GiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
        'decision': 'conclude_solver_matrix_no_automatic_extension',
        'limitations': ['exploratory previously exposed BIRD-dev; reference-table proxy, no SQL EX',
            'equal objective different schemas are tie sensitivity', 'fixed top3 terminals, small schema graphs',
            'timing includes wrapper/pruning/certificate checks; not general scalability benchmark',
            'frozen question-weight formula/cache; no weight or model tuning']})
    write_json(args.output / 'aggregate_summary.json', aggregate)
    print(json.dumps({k: aggregate[k] for k in ['setting', 'mode', 'questions', 'methods', 'vs_mehlhorn', 'solver_calls', 'wall_seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
