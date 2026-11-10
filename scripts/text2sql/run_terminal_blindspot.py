"""Sealed CPU-only diagnosis of the fixed-terminal Steiner model class."""
import argparse
from collections import Counter
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import networkx as nx
import numpy as np

from query_weighted_steiner import weighted_graph
from run_seed_steiner import read_config, load_inputs, sha256, write_json, new_output
from seed_steiner import reference_tables
from steiner_sql import choose_pilot
from steiner_sql_runtime import read_reference_rows
from terminal_envelope import terminal_envelope


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=['smoke', 'full'], required=True)
    args = p.parse_args()
    os.umask(0o077)
    new_output(args.output)
    cfg = read_config(args.config)
    started = time.monotonic()
    write_json(args.output / 'run_start.json', dict(command=sys.argv, config_sha256=sha256(args.config),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(), python=sys.version,
        dependencies={m: importlib.metadata.version(m) for m in ['numpy','networkx','sqlglot']},
        resources={c:subprocess.check_output(c.split(), text=True) for c in ['nvidia-smi','free -h','nproc']}))
    inputs = load_inputs(cfg)
    assert sha256(Path(cfg['previous_predictions'])) == cfg['previous_prediction_sha256']
    previous = {(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    graph_info, graphs = {}, {}
    for db, schema in inputs['schemas'].items():
        graph, _ = weighted_graph(len(schema['table_names_original']), inputs['constraints'][db], np.ones(len(inputs['constraints'][db])))
        graphs[db] = graph
        graph_info[db] = dict(nodes=len(graph), edges=graph.number_of_edges(), components=nx.number_connected_components(graph),
            cycle_rank=graph.number_of_edges()-len(graph)+nx.number_connected_components(graph), is_forest=nx.is_forest(graph))
    chosen = choose_pilot(inputs['questions'],5) if args.mode=='smoke' else inputs['questions']
    envelopes, checks, predictions = {}, Counter(), []
    for question in chosen:
        db = question['db_id']; key = (db,question['question_id']); old = previous[key]
        seeds = old['seeds']; graph = graphs[db]; cachekey = (db,tuple(seeds))
        if cachekey not in envelopes:
            envelope = terminal_envelope(graph,seeds)
            # Structurally independent oracle: enumerate paths, never use weights.
            oracle, count, exhausted = set(seeds), 0, False
            for a,b in itertools.combinations(seeds,2):
                for path in nx.all_simple_paths(graph,a,b):
                    count += 1
                    if count > 100000:
                        exhausted=True; break
                    oracle.update(path)
                if exhausted: break
            if exhausted: checks.update(path_enumeration_budget_exceeded=1)
            else:
                assert oracle == envelope
                checks.update(path_enumeration_verified=1, enumerated_paths=count)
            envelopes[cachekey] = envelope
        envelope = envelopes[cachekey]
        for arm in ['unit','weighted']:
            assert set(old['arms'][arm]['nodes']) <= envelope
        components = set().union(*(nx.node_connected_component(graph,t) for t in seeds))
        predictions.append(dict(db_id=db,question_id=question['question_id'],seeds=seeds,
            envelope=sorted(envelope),seeded_components=sorted(components),unit=old['arms']['unit']['nodes'],weighted=old['arms']['weighted']['nodes']))
        if time.monotonic()-started>cfg['max_wall_seconds']: raise TimeoutError('Budget exhausted')
    path=args.output/'envelope_predictions_private.json'
    write_json(path,predictions)
    seal=sha256(path)
    write_json(args.output/'prediction_seal.json',dict(sha256=seal,rows=len(predictions),labels_not_used_for_envelope=True))
    labels={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    counts=Counter(); perdb={db:Counter() for db in graphs}
    for r in predictions:
        db=r['db_id']
        gold=reference_tables(labels[(db,r['question_id'])],inputs['schemas'][db])
        baseline=set(r['weighted']); envelope=set(r['envelope']); missing=gold-baseline
        outside=gold-envelope
        item=dict(questions=1,weighted_complete=int(not missing),unit_complete=int(gold<=set(r['unit'])),
            envelope_complete=int(not outside),incomplete=int(bool(missing)),
            incomplete_outside_envelope=int(bool(missing) and bool(outside)),
            incomplete_only_inside_envelope=int(bool(missing) and not outside),
            outside_in_seeded_component=int(bool(outside & set(r['seeded_components']))),
            outside_in_unseeded_component=int(bool(outside-set(r['seeded_components']))),
            envelope_identical_to_weighted=int(envelope==baseline),
            forest_database_question=int(graph_info[db]['is_forest']),
            missing_reference_table_occurrences=len(missing),outside_envelope_reference_table_occurrences=len(outside),
            weighted_tables=len(baseline),envelope_tables=len(envelope))
        counts.update(item);perdb[db].update(item)
    assert sha256(path)==seal
    for db,expected in cfg['database_sha256'].items():
        assert sha256(Path(cfg['database_root'])/db/(db+'.sqlite'))==expected
    share=counts['incomplete_outside_envelope']/max(1,counts['incomplete'])
    out=dict(run_id=cfg['run_id'],mode=args.mode,counts=dict(counts),fraction_incomplete_outside_envelope=share,
        fraction_envelope_identical=counts['envelope_identical_to_weighted']/len(predictions),
        diagnostic_maximum_complete_rate=counts['envelope_complete']/len(predictions),
        independent_enumeration=dict(checks),unique_graph_terminal_sets=len(envelopes),
        graphs={f'DB-{i+1:02d}':graph_info[db] for i,db in enumerate(sorted(graphs))},
        per_database={f'DB-{i+1:02d}':dict(perdb[db]) for i,db in enumerate(sorted(graphs))},
        decision='investigate_terminal_intervention' if share>=.5 else 'investigate_path_choice',
        elapsed_wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time(),
        peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2),new_model_calls=0,
        prediction_sha256=seal,limitation='path union is a generous diagnostic envelope, not one feasible solution or SQL utility')
    write_json(args.output/'aggregate_summary.json',out)
    print(json.dumps({k:v for k,v in out.items() if k not in ['per_database','graphs']},indent=2),flush=True)


if __name__=='__main__':main()
