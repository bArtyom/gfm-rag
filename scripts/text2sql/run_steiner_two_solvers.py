"""Paired frozen-seed approximate/exact solver experiment, no new model calls."""
from __future__ import annotations

import argparse
from collections import Counter
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

from run_seed_steiner import coverage_summary, load_inputs, new_output, read_config, sha256, verify_database_hashes, write_json
from seed_steiner import choose_split, rank_seed_tables, reference_tables
from steiner_solvers import canonical_graph, small_terminal_optimum, solve_steiner

METHODS = ['mehlhorn', 'dreyfus_wagner']


def summarize_group(rows, schemas, seed):
    output = {'questions': len(rows), 'methods': {}}
    for method in METHODS:
        selected = [{'gold': r['gold'], 'tables': r['methods'][method]['nodes'],
                     'columns': sum(t in r['methods'][method]['nodes'] for t, _ in schemas[r['db_id']]['column_names_original'])} for r in rows]
        summary = coverage_summary(selected)
        costs = [r['methods'][method]['cost'] for r in rows]
        times = [r['methods'][method]['elapsed_seconds'] for r in rows]
        summary.update({'mean_edge_cost': float(np.mean(costs)), 'total_edge_cost': float(sum(costs)),
            'solver_wall_seconds_total': float(sum(times)), 'solver_latency_median_ms': float(np.median(times) * 1000),
            'solver_latency_p95_ms': float(np.quantile(times, .95) * 1000),
            'forest_questions': sum(not r['methods'][method]['connected'] for r in rows)})
        output['methods'][method] = summary
    strict = sum(r['methods']['dreyfus_wagner']['cost'] < r['methods']['mehlhorn']['cost'] - 1e-9 for r in rows)
    differing = [r for r in rows if r['methods']['mehlhorn']['nodes'] != r['methods']['dreyfus_wagner']['nodes']]
    ties = sum(math.isclose(r['methods']['mehlhorn']['cost'], r['methods']['dreyfus_wagner']['cost'], abs_tol=1e-9) for r in differing)
    ratios = [r['methods']['mehlhorn']['cost'] / r['methods']['dreyfus_wagner']['cost'] for r in rows if r['methods']['dreyfus_wagner']['cost'] > 0]
    paired = Counter({'rescue': 0, 'damage': 0, 'unchanged': 0, 'unknown': 0})
    db_delta = {}
    for row in rows:
        db = row['db_id']
        db_delta.setdefault(db, [0, 0])[1] += 1
        if row['gold'] is None:
            paired['unknown'] += 1
            continue
        exact = row['gold'] <= set(row['methods']['dreyfus_wagner']['nodes'])
        approximate = row['gold'] <= set(row['methods']['mehlhorn']['nodes'])
        paired['rescue' if exact and not approximate else 'damage' if approximate and not exact else 'unchanged'] += 1
        db_delta[db][0] += int(exact) - int(approximate)
    values = np.array([db_delta[db] for db in sorted(db_delta)])
    rng = np.random.default_rng(seed)
    draws = values[rng.integers(0, len(values), size=(10000, len(values)))].sum(axis=1)
    interval = np.quantile(draws[:, 0] / draws[:, 1], [.025, .975]).tolist()
    output.update({'strict_exact_cost_improvements': strict, 'equal_cost_questions': len(rows) - strict,
        'different_table_sets': len(differing), 'different_table_sets_equal_cost': ties,
        'different_table_sets_strict_cost': len(differing) - ties,
        'different_edge_sets': sum(r['methods']['mehlhorn']['edges'] != r['methods']['dreyfus_wagner']['edges'] for r in rows),
        'approximation_ratio_positive_optimum_mean': float(np.mean(ratios)) if ratios else None,
        'approximation_ratio_positive_optimum_max': max(ratios) if ratios else None,
        'zero_optimum_questions': len(rows) - len(ratios), 'exact_vs_mehlhorn_coverage': dict(paired),
        'coverage_delta': (paired['rescue'] - paired['damage']) / len(rows),
        'coverage_delta_DB_cluster_95_percentile_interval': interval,
        'positive_task_signal': paired['rescue'] > paired['damage'],
        'decision': 'exact_reduces_graph_cost' if strict else 'same_cost_tie_sensitivity' if differing else 'same_cost_and_schema',
        'per_database': {f'DB-{i+1:02d}': {'questions': db_delta[db][1], 'exact_minus_approximate_complete': db_delta[db][0]}
                         for i, db in enumerate(sorted(db_delta))}})
    return output


def validate_pair(graph, terminals, results):
    oracle = small_terminal_optimum(graph, terminals)
    exact = results['dreyfus_wagner']['cost']
    approximate = results['mehlhorn']['cost']
    if not math.isclose(exact, oracle, abs_tol=1e-9) or exact > approximate + 1e-9:
        raise RuntimeError('Exact objective oracle or dominance validation failed')
    if len(terminals) == 2 and not math.isclose(approximate, oracle, abs_tol=1e-9):
        raise RuntimeError('Two-terminal shortest-path control failed')
    for result in results.values():
        selected = nx.Graph()
        selected.add_nodes_from(result['nodes'])
        selected.add_edges_from(result['edges'])
        if not set(terminals) <= set(selected):
            raise RuntimeError('Missing terminal')
        if any(not graph.has_edge(a, b) for a, b in selected.edges):
            raise RuntimeError('Non-FK edge')
        if selected and not nx.is_forest(selected):
            raise RuntimeError('Non-forest output')
        for component in nx.connected_components(graph):
            seeds = sorted(set(component) & set(terminals))
            if seeds and any(not nx.has_path(selected, seeds[0], t) for t in seeds):
                raise RuntimeError('Disconnected connectable terminals')
        actual_cost = sum(graph[a][b]['weight'] for a, b in selected.edges)
        if not math.isclose(actual_cost, result['cost'], abs_tol=1e-9):
            raise RuntimeError('Returned objective does not match selected edges')
    return oracle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['smoke', 'full'], required=True)
    args = parser.parse_args()
    new_output(args.output)
    os.umask(0o077)
    started = time.monotonic()
    config = read_config(args.config)
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise ValueError('PYTHONHASHSEED=0 is required for recorded determinism')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    write_json(args.output / 'run_start.json', {'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_commit': commit, 'command': sys.argv, 'config_sha256': sha256(args.config),
        'python': sys.version, 'executable': sys.executable,
        'dependencies': {p: importlib.metadata.version(p) for p in ['networkx', 'numpy', 'sqlglot']},
        'environment': {k: os.environ.get(k) for k in ['PYTHONHASHSEED', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']},
        'resources': {cmd: subprocess.check_output(cmd.split(), text=True) for cmd in ['nvidia-smi', 'free -h', 'nproc']}})
    for filename, key in [('input_manifest_private.json', 'cache_source_receipt_sha256'), ('per_question_private.jsonl', 'cache_identity_receipt_sha256')]:
        if sha256(Path(config['cache_root']) / filename) != config[key]:
            raise ValueError('Cache receipt hash mismatch')
    inputs = load_inputs(config)
    graphs = {}
    for db, schema in inputs['schemas'].items():
        graph = nx.Graph()
        graph.add_nodes_from(range(len(schema['table_names_original'])))
        for constraint in inputs['constraints'][db]:
            graph.add_edge(constraint['source_table'], constraint['target_table'], weight=1.0)
        graphs[db] = canonical_graph(graph)
    split = choose_split(inputs['questions'], config['seed'])
    smoke = set(map(tuple, split['smoke']))
    positions = {db: [i for i, node in enumerate(inputs['nodes']) if node['db_id'] == db] for db in inputs['schemas']}
    predictions = []
    for qi, row in enumerate(inputs['questions']):
        db = row['db_id']
        if args.mode == 'smoke' and (db, row['question_id']) not in smoke:
            continue
        eligible = positions[db]
        scores = inputs['vectors'][eligible] @ inputs['queries'][qi]
        ranking = rank_seed_tables(inputs['schemas'][db], [inputs['nodes'][i] for i in eligible], scores, max(config['seed_counts']), config['seed_source'])
        if len(ranking) < max(config['seed_counts']):
            raise ValueError('Fewer than three eligible tables')
        for k in config['seed_counts']:
            terminals = sorted(ranking[:k])
            methods = METHODS if (qi + k) % 2 == 0 else list(reversed(METHODS))
            results = {method: solve_steiner(graphs[db], terminals, method) for method in methods}
            if any(r['elapsed_seconds'] > config['max_solve_seconds'] for r in results.values()):
                raise RuntimeError('Per-solve time budget exceeded')
            oracle = validate_pair(graphs[db], terminals, results)
            predictions.append({'db_id': db, 'question_id': row['question_id'], 'seed_count': k,
                                'seeds': terminals, 'methods': results, 'oracle_cost': oracle})
        if time.monotonic() - started > config['max_wall_seconds']:
            raise RuntimeError('Overall time budget exceeded')
    path = args.output / 'private_predictions.jsonl'
    with path.open('x') as stream:
        for row in predictions:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
    digest = sha256(path)
    write_json(args.output / 'prediction_seal.json', {'rows': len(predictions), 'sha256': digest,
        'sealed_at_utc': datetime.now(timezone.utc).isoformat(), 'all_independent_cost_oracles_pass': True})
    # Evaluation sees reference SQL only after sealing all algorithm outputs.
    data = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in data}
    for row in predictions:
        try:
            row['gold'] = reference_tables(labels[(row['db_id'], row['question_id'])], inputs['schemas'][row['db_id']])
        except Exception as exc:
            row['gold'] = None
            row['reference_error'] = type(exc).__name__
    groups = {str(k): summarize_group([r for r in predictions if r['seed_count'] == k], inputs['schemas'], config['seed'] + k) for k in config['seed_counts']}
    actual_hashes = {db: sha256(Path(config['database_root']) / db / (db + '.sqlite')) for db in inputs['schemas']}
    verify_database_hashes(config['database_sha256'], actual_hashes)
    if sha256(path) != digest:
        raise RuntimeError('Predictions changed after sealing')
    aggregate = {'run_id': config['run_id'], 'mode': args.mode, 'source_commit': commit, 'status': 'completed',
        'config_sha256': sha256(args.config), 'prediction_sha256': digest, 'paired_instances': len(predictions),
        'solver_calls': len(predictions) * 2, 'groups': groups, 'all_cost_oracles_verified': True,
        'databases_unchanged': True, 'new_model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'GPU_seconds': 0,
        'external_API_cost_CNY': '0.00', 'local_CPU_monetized': False,
        'elapsed_wall_seconds': time.monotonic() - started, 'process_CPU_seconds': time.process_time(),
        'peak_RSS_GiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2),
        'decision': 'conclude_two_solver_comparison_no_automatic_extension',
        'limitations': ['exploratory previously used BIRD-dev', 'reference-table proxy, no SQL EX',
            'unweighted undirected FK-only table graph', 'canonical tie choices may differ from old wrapper',
            'timings include validation/canonicalization inside solver wrapper; no microbenchmark speed claim']}
    write_json(args.output / 'aggregate_summary.json', aggregate)
    write_json(args.output / 'private_input_receipt.json', {'config': config, 'database_hashes': actual_hashes,
        'graphs': {db: {'nodes': g.number_of_nodes(), 'edges': g.number_of_edges(), 'cycle_rank': g.number_of_edges() - g.number_of_nodes() + nx.number_connected_components(g)} for db, g in graphs.items()}})
    print(json.dumps({'mode': args.mode, 'solver_calls': aggregate['solver_calls'],
        'groups': {k: {key: group[key] for key in ['questions', 'methods', 'strict_exact_cost_improvements', 'different_table_sets_equal_cost', 'exact_vs_mehlhorn_coverage', 'decision']} for k, group in groups.items()},
        'wall_seconds': aggregate['elapsed_wall_seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
