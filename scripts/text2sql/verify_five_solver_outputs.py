"""Independent sealed-output/graph/oracle/certificate/count audit, no solving."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

import networkx as nx
import numpy as np
from run_seed_steiner import load_inputs, read_config, sha256, write_json
from seed_steiner import reference_tables

METHODS = ['greedy', 'kou', 'mehlhorn', 'dreyfus_wagner', 'milp']


def audit(config_path, output):
    started = time.monotonic()
    config = read_config(config_path)
    inputs = load_inputs(config)
    summary = json.loads((output / 'aggregate_summary.json').read_text())
    seal = json.loads((output / 'prediction_seal.json').read_text())
    path = output / 'private_predictions.jsonl'
    if sha256(path) != summary['prediction_sha256'] or seal['sha256'] != summary['prediction_sha256']:
        raise ValueError('Prediction hash mismatch')
    rows = list(map(json.loads, path.read_text().splitlines()))
    ids = {(r['db_id'], r['question_id']) for r in rows}
    assert len(ids) == len(rows) == summary['questions'] == 1534
    assert ids == {(r['db_id'], r['question_id']) for r in inputs['questions']}
    cache = Path(config['relation_cache'])
    for p, key in [(cache/'cache_receipt.json', 'relation_receipt_sha256'),
        (cache/'private_relations.json', 'relation_manifest_sha256'), (cache/'relation_vectors.npz', 'relation_vector_sha256'),
        (Path(config['previous_predictions']), 'previous_prediction_sha256')]:
        assert sha256(p) == config[key]
    records = json.loads((cache / 'private_relations.json').read_text())
    with np.load(cache / 'relation_vectors.npz', allow_pickle=False) as data:
        vectors = data['vectors'].astype('float64')
    prior = {(r['db_id'], r['question_id']): r for r in map(json.loads, Path(config['previous_predictions']).read_text().splitlines())}
    raw = json.loads((Path(config['dataset_root']) / 'dev.json').read_text())
    labels = {(r['db_id'], r['question_id']): r['SQL'] for r in raw}
    complete, table_counts, column_counts, optimal, forest, certified, mipcalls = [Counter() for _ in range(7)]
    costs, excess, ratios, times = ({m: [] for m in METHODS} for _ in range(4))
    pair = {m: Counter({k: 0 for k in ['rescue', 'damage', 'unchanged', 'unknown', 'strictly_cheaper',
        'strictly_costlier', 'changed_tables', 'changed_tables_equal_cost', 'changed_constraints']}) for m in METHODS}
    exact_disagreements_equal_cost = 0
    for r in rows:
        db, qi = r['db_id'], r['qi']
        question = inputs['questions'][qi]
        assert (question['db_id'], question['question_id']) == (db, r['question_id'])
        schema = inputs['schemas'][db]
        scores = {int(node['node_id'].rsplit(':', 1)[-1]): float(inputs['vectors'][i] @ inputs['queries'][qi])
            for i, node in enumerate(inputs['nodes']) if node['db_id'] == db and node['node_type'] == 'table'}
        ranking = sorted(scores, key=lambda t: (-scores[t], t))
        seeds = sorted(ranking[:3])
        assert seeds == r['seeds'] == prior[(db, r['question_id'])]['seeds']
        indices = [i for i, rec in enumerate(records) if rec['db_id'] == db]
        constraints = inputs['constraints'][db]
        assert [records[i]['constraint'] for i in indices] == constraints
        if summary['setting'] == 'unit':
            weights = np.ones(len(indices))
        else:
            q = inputs['queries'][qi].astype('float64')
            v = vectors[indices]
            weights = 1.5 - .5*np.clip(v @ q / (np.linalg.norm(v, axis=1)*np.linalg.norm(q)), -1., 1.)
        graph = nx.Graph()
        graph.add_nodes_from(range(len(ranking)))
        representatives = {}
        for constraint, weight in zip(constraints, weights):
            a, b = sorted([constraint['source_table'], constraint['target_table']])
            if a == b:
                continue
            choice = (float(weight), constraint['id'])
            if (a, b) not in representatives or choice < representatives[(a, b)]:
                representatives[(a, b)] = choice
        for (a, b), (weight, _) in representatives.items():
            graph.add_edge(a, b, weight=weight)
        components, oracle = [], 0.
        for comp in sorted(nx.connected_components(graph), key=lambda c: min(c)):
            terminals = sorted(set(comp) & set(seeds))
            if terminals:
                components.append((comp, terminals))
            if len(terminals) >= 2:
                distances = [nx.single_source_dijkstra_path_length(graph, t, weight='weight') for t in terminals]
                oracle += distances[0][terminals[1]] if len(terminals) == 2 else min(sum(d[u] for d in distances) for u in comp)
        assert math.isclose(oracle, r['oracle_cost'], rel_tol=1e-9, abs_tol=1e-8)
        gold = reference_tables(labels[(db, r['question_id'])], schema)
        base = r['methods']['mehlhorn']
        previous = prior[(db, r['question_id'])]['arms'][summary['setting']]
        assert all(base[k] == previous[k] for k in ['nodes', 'edges', 'constraint_ids'])
        assert math.isclose(base['cost'], previous['cost'], abs_tol=1e-9)
        offset = (qi + (summary['setting'] == 'weighted')) % len(METHODS)
        assert r['method_order'] == METHODS[offset:]+METHODS[:offset]
        for method in METHODS:
            value = r['methods'][method]
            selected = nx.Graph()
            selected.add_nodes_from(value['nodes'])
            selected.add_edges_from(value['edges'])
            assert set(seeds) <= set(selected) and nx.is_forest(selected)
            assert all(graph.has_edge(a,b) for a,b in selected.edges)
            assert all(n in seeds or selected.degree(n) >= 2 for n in selected)
            assert value['constraint_ids'] == [representatives[tuple(e)][1] for e in value['edges']]
            assert value['seed_components'] == len(components)
            assert value['connected'] == (len(components) <= 1)
            for comp, terminals in components:
                assert all(nx.has_path(selected, terminals[0], t) for t in terminals)
            cost = sum(graph[a][b]['weight'] for a,b in selected.edges)
            assert math.isclose(cost, value['cost'], rel_tol=1e-9, abs_tol=1e-8)
            assert cost >= oracle - 1e-7
            exact = method in ['milp', 'dreyfus_wagner']
            assert value['certified_optimal'] == exact
            if exact:
                assert math.isclose(cost, oracle, rel_tol=1e-8, abs_tol=1e-7)
            proofs = value['certificates']
            if method == 'milp':
                relevant = [(comp, ts) for comp, ts in components if len(ts)>=2]
                assert len(proofs) == len(relevant)
                for proof,(comp,terminals) in zip(proofs,relevant):
                    assert proof['status'] == 0 and proof['success'] and 0 <= proof['mip_gap'] <= 1e-8
                    assert proof['terminals'] == terminals and proof['root'] == min(terminals)
                    assert proof['max_primal_violation'] <= 1e-6 and proof['max_binary_integrality_error'] <= 1e-6
                    component_cost = sum(graph[a][b]['weight'] for a,b in selected.edges if a in comp)
                    assert math.isclose(component_cost, proof['primal_objective'], rel_tol=1e-8, abs_tol=1e-7)
                    assert math.isclose(component_cost, proof['mip_dual_bound'], rel_tol=1e-8, abs_tol=1e-7)
            else:
                assert not proofs
            covered = gold <= set(value['nodes'])
            base_covered = gold <= set(base['nodes'])
            complete[method] += covered
            table_counts[method] += len(value['nodes'])
            column_counts[method] += sum(t in value['nodes'] for t,_ in schema['column_names_original'])
            optimal[method] += math.isclose(cost,oracle,rel_tol=1e-8,abs_tol=1e-7)
            certified[method] += exact
            forest[method] += not value['connected']
            mipcalls[method] += len(proofs)
            costs[method].append(cost)
            excess[method].append(cost-oracle)
            times[method].append(value['elapsed_seconds'])
            if oracle>1e-12:
                ratios[method].append(cost/oracle)
            pair[method]['rescue' if covered and not base_covered else 'damage' if base_covered and not covered else 'unchanged'] += 1
            equal = math.isclose(cost,base['cost'],rel_tol=1e-8,abs_tol=1e-7)
            changed = value['nodes'] != base['nodes']
            pair[method]['strictly_cheaper'] += not equal and cost<base['cost']
            pair[method]['strictly_costlier'] += not equal and cost>base['cost']
            pair[method]['changed_tables'] += changed
            pair[method]['changed_tables_equal_cost'] += changed and equal
            pair[method]['changed_constraints'] += sorted(value['constraint_ids']) != sorted(base['constraint_ids'])
        dp,mip=r['methods']['dreyfus_wagner'],r['methods']['milp']
        exact_disagreements_equal_cost += dp['nodes'] != mip['nodes']
    for method in METHODS:
        s=summary['methods'][method]
        assert complete[method]==s['complete'] and s['reference_parse_failures']==0
        assert math.isclose(sum(costs[method]),s['total_cost'],abs_tol=1e-7)
        assert math.isclose(table_counts[method]/len(rows),s['mean_selected_tables'])
        assert math.isclose(column_counts[method]/len(rows),s['mean_selected_columns'])
        assert optimal[method]==s['optimal_cost_questions'] and certified[method]==s['certified_optimal_questions']
        assert forest[method]==s['forest_questions'] and mipcalls[method]==s['MILP_component_calls']==s['MILP_certified_component_calls']
        assert math.isclose(float(np.median(times[method])*1000),s['latency_median_ms'])
        assert math.isclose(float(np.quantile(times[method],.95)*1000),s['latency_p95_ms'])
        assert math.isclose(float(np.mean(excess[method])),s['mean_cost_excess_over_oracle'],abs_tol=1e-8)
        assert all(pair[method][k]==summary['vs_mehlhorn'][method][k] for k in pair[method])
    assert sha256(path)==seal['sha256']
    return {'status':'PASS','setting':summary['setting'],'rows_verified':len(rows),'solver_outputs_verified':len(rows)*len(METHODS),
        'prediction_sha256':seal['sha256'],'complete':dict(complete),'optimal_cost_questions':dict(optimal),
        'MILP_certificates_checked':mipcalls['milp'],'DP_MILP_same_cost_different_table_sets':exact_disagreements_equal_cost,
        'prior_Mehlhorn_replay_verified':True,'wall_seconds':time.monotonic()-started,
        'checks':['full identities and cache/input hashes','independent rankings/costs/FK representatives',
            'original topology/forest/seed feasibility','independent <=3-terminal distance/meeting-node objective',
            'MILP recorded primal-dual/status/gap/integrality metadata','coverage and paired/tie counts',
            'table/column sizes and recorded latency aggregation','prior unit/weighted Mehlhorn replay'],
        'scope':'Post-run audit reuses frozen loader/reference parser; does not rerun solvers or reconstruct full MILP flow variables.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=audit(args.config,args.output)
    write_json(args.output/'independent_verification.json',result)
    print(json.dumps(result,indent=2))
