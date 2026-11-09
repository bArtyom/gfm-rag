"""Audit sealed weighted outputs without invoking either retriever or model."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

import networkx as nx
import numpy as np
from run_seed_steiner import load_inputs, read_config, sha256, write_json
from seed_steiner import reference_tables, serialize_schema


def audit(config_path, cache, output):
    started = time.monotonic()
    config = read_config(config_path)
    inputs = load_inputs(config)
    summary = json.loads((output / 'aggregate_summary.json').read_text())
    seal = json.loads((output / 'prediction_seal.json').read_text())
    prediction_file = output / 'private_predictions.jsonl'
    if sha256(prediction_file) != seal['sha256'] or seal['sha256'] != summary['prediction_sha256']:
        raise ValueError('Prediction seal mismatch')
    receipt = json.loads((cache / 'cache_receipt.json').read_text())
    for name, key in [('private_relations.json', 'relation_manifest_sha256'), ('relation_vectors.npz', 'relation_vectors_sha256')]:
        if sha256(cache / name) != receipt[key]:
            raise ValueError('Cache hash mismatch')
    records = json.loads((cache / 'private_relations.json').read_text())
    with np.load(cache / 'relation_vectors.npz', allow_pickle=False) as archive:
        vectors = archive['vectors'].astype('float64')
    raw = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in raw}
    rows = [json.loads(line) for line in prediction_file.read_text().splitlines()]
    if len(rows) != summary['questions'] or len({(r['db_id'], r['question_id']) for r in rows}) != len(rows):
        raise ValueError('Bad row count or duplicate identities')
    if summary['mode'] == 'full':
        assert {(r['db_id'], r['question_id']) for r in rows} == {(r['db_id'], r['question_id']) for r in inputs['questions']}
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(config['embedding_model'], local_files_only=True)
    complete = Counter()
    selected_count, token_sum = Counter(), Counter()
    pair = {base: Counter() for base in ['unit', 'dense']}
    costs_all, changed_sizes = [], Counter()
    strata_pair = {flag: Counter() for flag in [False, True]}
    schema_tokens = {}
    for row in rows:
        db, qi = row['db_id'], row['qi']
        source = inputs['questions'][qi]
        assert (source['db_id'], source['question_id']) == (db, row['question_id'])
        schema = inputs['schemas'][db]
        table_scores = {int(n['node_id'].rsplit(':', 1)[-1]): float(inputs['vectors'][i] @ inputs['queries'][qi])
                        for i, n in enumerate(inputs['nodes']) if n['db_id'] == db and n['node_type'] == 'table'}
        ranking = sorted(table_scores, key=lambda t: (-table_scores[t], t))
        assert ranking == row['ranking'] and sorted(ranking[:3]) == row['seeds']
        indices = [i for i, r in enumerate(records) if r['db_id'] == db]
        cs = inputs['constraints'][db]
        assert [records[i]['constraint'] for i in indices] == cs
        v = vectors[indices]
        q = inputs['queries'][qi].astype('float64')
        sim = np.clip(v @ q / (np.linalg.norm(v, axis=1) * np.linalg.norm(q)), -1., 1.)
        costs = 1.5 - .5 * sim
        assert np.allclose(costs, row['relation_costs'], rtol=0, atol=1e-12)
        assert np.all(costs >= 1) and np.all(costs <= 2)
        costs_all.extend(costs.tolist())
        graphs = {}
        for arm in ['unit', 'weighted']:
            graph = nx.Graph()
            graph.add_nodes_from(range(len(schema['table_names_original'])))
            representatives = {}
            for c, cost in zip(cs, np.ones(len(cs)) if arm == 'unit' else costs):
                a, b = sorted([c['source_table'], c['target_table']])
                if a == b:
                    continue
                key = (a, b)
                choice = (float(cost), c['id'])
                if key not in representatives or choice < representatives[key]:
                    representatives[key] = choice
            for (a, b), (cost, _) in representatives.items():
                graph.add_edge(a, b, weight=cost)
            graphs[arm] = graph
            result = row['arms'][arm]
            selected = nx.Graph()
            selected.add_nodes_from(result['nodes'])
            selected.add_edges_from(result['edges'])
            assert set(row['seeds']) <= set(selected) and nx.is_forest(selected)
            assert all(graph.has_edge(a, b) for a, b in selected.edges)
            assert all(n in row['seeds'] or selected.degree(n) >= 2 for n in selected)
            assert result['constraint_ids'] == [representatives[tuple(e)][1] for e in result['edges']]
            assert math.isclose(sum(graph[a][b]['weight'] for a, b in selected.edges), result['cost'], abs_tol=1e-10)
            for comp in nx.connected_components(graph):
                terminals = set(comp) & set(row['seeds'])
                if terminals:
                    root = min(terminals)
                    assert all(nx.has_path(selected, root, t) for t in terminals)
        assert set(graphs['unit'].edges) == set(graphs['weighted'].edges)
        bridge_set = {tuple(sorted(e)) for e in nx.bridges(graphs['unit'])}
        assert row['alternative_route'] == any(tuple(e) not in bridge_set for e in row['arms']['unit']['edges'])
        n = len(row['arms']['weighted']['nodes'])
        assert row['arms']['dense']['nodes'] == sorted(ranking[:n])
        gold = reference_tables(labels[(db, row['question_id'])], schema)
        covered = {}
        for arm in ['unit', 'weighted', 'dense']:
            result = row['arms'][arm]
            covered[arm] = gold <= set(result['nodes'])
            complete[arm] += covered[arm]
            selected_count[arm] += len(result['nodes'])
            key = (db, tuple(result['nodes']))
            if key not in schema_tokens:
                schema_tokens[key] = len(tokenizer.encode(serialize_schema(schema, result['nodes'], cs), add_special_tokens=False))
            assert schema_tokens[key] == result['schema_tokens']
            token_sum[arm] += result['schema_tokens']
        for base in pair:
            category = 'rescue' if covered['weighted'] and not covered[base] else 'damage' if covered[base] and not covered['weighted'] else 'unchanged'
            pair[base][category] += 1
            if base == 'unit':
                strata_pair[row['alternative_route']][category] += 1
        delta = len(row['arms']['weighted']['nodes']) - len(row['arms']['unit']['nodes'])
        changed_sizes[str(delta)] += 1
    for arm in complete:
        assert complete[arm] == summary['all'][arm]['complete']
        assert math.isclose(selected_count[arm] / len(rows), summary['all'][arm]['mean_selected_tables'])
        assert math.isclose(token_sum[arm] / len(rows), summary['all'][arm]['mean_schema_tokens_embedding_tokenizer'])
    for base in pair:
        for name in ['rescue', 'damage', 'unchanged']:
            assert pair[base][name] == summary['paired'][base][name]
    changed = {name: sum(r['arms']['unit'][field] != r['arms']['weighted'][field] for r in rows)
               for name, field in [('changed_table_sets', 'nodes'), ('changed_edge_sets', 'edges'), ('changed_constraint_sets', 'constraint_ids')]}
    for name, count in changed.items():
        assert count == summary[name]
    delta_unit = (complete['weighted'] - complete['unit']) / len(rows)
    delta_dense = (complete['weighted'] - complete['dense']) / len(rows)
    assert summary['pilot_gate_pass'] == (delta_unit > 0 and delta_dense >= 0)
    assert summary['final_upgrade_gate_pass'] == (delta_unit >= .01 and delta_dense > 0)
    assert sha256(prediction_file) == seal['sha256']
    return {'status': 'PASS', 'rows_verified': len(rows), 'arm_outputs_verified': len(rows) * 3,
        'prediction_sha256': seal['sha256'], 'complete': dict(complete),
        'paired': {k: dict(v) for k, v in pair.items()}, 'size_delta_histogram_weighted_minus_unit': dict(changed_sizes),
        **changed, 'final_upgrade_gate_pass_verified': summary['final_upgrade_gate_pass'],
        'strata_paired_vs_unit': {str(k): dict(v) for k, v in strata_pair.items()},
        'observed_cost_min': min(costs_all), 'observed_cost_max': max(costs_all),
        'observed_cost_median': float(np.median(costs_all)), 'wall_seconds': time.monotonic() - started,
        'checks': ['sealed predictions', 'original inputs hashes', 'independent dot/cost and seed ranking',
            'fixed topology', 'parallel/composite FK identity', 'seed connectivity and forests',
            'per-question dense size match', 'coverage and paired counts', 'schema token recount']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--relation-cache', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report-name', default='independent_verification.json')
    args = p.parse_args()
    result = audit(args.config, args.relation_cache, args.output)
    if Path(args.report_name).name != args.report_name:
        raise ValueError('Report name must be a filename')
    write_json(args.output / args.report_name, result)
    print(json.dumps(result, indent=2))
