"""Audit sealed route pilot and diagnose relaxed feasible sets; no model calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

import networkx as nx
import numpy as np
from transformers import AutoTokenizer

from residual_routes import tree_catalogue
from query_weighted_steiner import weighted_graph
from run_seed_steiner import read_config,load_inputs,sha256,new_output,write_json
from seed_steiner import serialize_schema,reference_tables
from steiner_sql_runtime import read_reference_rows


def main():
    p=argparse.ArgumentParser()
    for name in ['config','predictions','output']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();new_output(args.output);began=time.monotonic();cfg=read_config(args.config)
    assert sha256(args.predictions)==json.loads((args.predictions.parent/'prediction_seal.json').read_text())['sha256']
    rows=json.loads(args.predictions.read_text());summary=json.loads((args.predictions.parent/'aggregate_summary.json').read_text())
    assert len(rows)==100 and summary['mode']=='pilot'
    # Historical execution7764afd used the pilot-specific field name.
    assert summary.get('stage_upgrade_gate',summary.get('pilot_upgrade_gate')) is False
    inputs=load_inputs(cfg)
    assert sha256(Path(cfg['previous_predictions']))==cfg['previous_prediction_sha256']
    assert sha256(Path(cfg['sql_prepared']))==cfg['sql_prepared_sha256']
    old={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    assert len(excluded)==133 and not {(r['db_id'],r['question_id']) for r in rows}&excluded
    qis={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
    tok=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True);cache={};catalogues={}
    def tokens(db,nodes):
        key=(db,tuple(sorted(nodes)))
        if key not in cache:cache[key]=len(tok.encode(serialize_schema(inputs['schemas'][db],sorted(nodes),inputs['constraints'][db]),add_special_tokens=False))
        return cache[key]
    candidates={};hist=Counter();alternate_node_sets=0;recomputed={a:Counter() for a in ['frozen','raw','residual']}
    for row in rows:
        db=row['db_id'];key=(db,row['question_id']);prior=old[key];seeds=row['seeds'];assert seeds==prior['seeds']
        assert row['arms']['frozen']['nodes']==prior['arms']['weighted']['nodes']
        graph,_=weighted_graph(len(inputs['schemas'][db]['table_names_original']),inputs['constraints'][db],prior['relation_costs'])
        ck=(db,tuple(seeds))
        if ck not in catalogues:catalogues[ck]=tree_catalogue(graph,seeds)
        catalogue=catalogues[ck]
        for c in catalogue:
            tree=nx.Graph();tree.add_nodes_from(c['nodes']);tree.add_edges_from(c['edges'])
            assert nx.is_forest(tree) and set(seeds)<=set(tree)
            assert all(v in seeds for v in tree if tree.degree(v)<=1)
            assert all(graph.has_edge(a,b) for a,b in tree.edges)
        cap=tokens(db,row['arms']['frozen']['nodes']);ncap=len(row['arms']['frozen']['nodes'])
        feasible=[c for c in catalogue if len(c['nodes'])<=ncap and tokens(db,c['nodes'])<=cap]
        assert len(catalogue)==row['catalogue_size'] and len(feasible)==row['feasible_size']
        assert sorted({tuple(c['nodes']) for c in feasible})==list(map(tuple,row['feasible_node_sets']))
        hist[len(feasible)]+=1
        alternate_node_sets+=int(len({tuple(c['nodes']) for c in feasible})>1)
        indices=[i for i,n in enumerate(inputs['nodes']) if n['db_id']==db and n['node_type']=='column']
        cols=inputs['vectors'][indices].astype(float);cols/=np.linalg.norm(cols,axis=1)[:,None]
        owners=[inputs['schemas'][db]['column_names_original'][int(inputs['nodes'][i]['node_id'].rsplit(':',1)[-1])][0] for i in indices]
        q=inputs['queries'][qis[key]].astype(float);q/=np.linalg.norm(q)
        raw=cols@q
        witnesses=[max((i for i,t in enumerate(owners) if t==s),key=lambda i:(raw[i],-i)) for s in seeds]
        anchors=cols[witnesses]
        # Independent Gram-matrix projection, rather than the producer's SVD basis.
        gram_inverse=np.linalg.pinv(anchors@anchors.T,rcond=1e-16)
        qres=q-(q@anchors.T)@gram_inverse@anchors
        cres=cols-(cols@anchors.T)@gram_inverse@anchors
        norm=np.linalg.norm(qres);cnorm=np.linalg.norm(cres,axis=1)
        residual=raw.copy() if norm<=1e-8 else np.divide(cres@qres,cnorm*norm,out=np.zeros(len(cols)),where=cnorm>1e-8)
        for arm,scores in [('raw',raw),('residual',np.clip(residual,-1,1))]:
            def order(c):
                score=max((float(scores[i]) for i,t in enumerate(owners) if t in set(c['nodes'])-set(seeds)),default=0.)
                return (-score,sum(graph[a][b]['weight'] for a,b in c['edges']),tuple(map(tuple,c['edges'])),tuple(c['nodes']))
            choice=min(feasible,key=order)
            assert choice['nodes']==row['arms'][arm]['nodes'] and choice['edges']==row['arms'][arm]['edges']
        for arm,r in row['arms'].items():
            assert r['schema_tokens']==tokens(db,r['nodes'])<=cap and len(r['nodes'])<=ncap
            recomputed[arm].update(questions=1,selected_tables=len(r['nodes']),schema_tokens=r['schema_tokens'],changed_from_frozen=int(r['nodes']!=row['arms']['frozen']['nodes']))
        candidates[key]=(catalogue,feasible,cap,ncap)
    labels={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    bound=Counter();required_extra_tokens=[];pairs={a:Counter() for a in ['residual_vs_frozen','residual_vs_raw']}
    for row in rows:
        db=row['db_id'];key=(db,row['question_id']);gold=reference_tables(labels[key],inputs['schemas'][db])
        catalogue,feasible,cap,ncap=candidates[key]
        correct={a:gold<=set(r['nodes']) for a,r in row['arms'].items()}
        for arm in recomputed:recomputed[arm].update(complete=int(correct[arm]))
        for base in ['frozen','raw']:
            pairs['residual_vs_'+base].update(['rescue' if correct['residual'] and not correct[base] else 'damage' if correct[base] and not correct['residual'] else 'unchanged'])
        good=[c for c in catalogue if gold<=set(c['nodes'])]
        bound.update(questions=1,strict_budget_oracle=int(any(gold<=set(c['nodes']) for c in feasible)),
            token_only_cap_oracle=int(any(tokens(db,c['nodes'])<=cap for c in good)),
            table_only_cap_oracle=int(any(len(c['nodes'])<=ncap for c in good)),
            unlimited_minimal_tree_oracle=int(bool(good)),
            reference_only_schema_fits_both_caps=int(len(gold)<=ncap and tokens(db,gold)<=cap),
            baseline_incomplete=int(not correct['frozen']),
            baseline_incomplete_but_reference_only_fits=int(not correct['frozen'] and len(gold)<=ncap and tokens(db,gold)<=cap),
            baseline_incomplete_unlimited_tree_recoverable=int(not correct['frozen'] and bool(good)))
        if good:required_extra_tokens.append(max(0,min(tokens(db,c['nodes']) for c in good)-cap))
    for arm in recomputed:assert dict(recomputed[arm])==summary['arms'][arm]
    assert {a:dict(c) for a,c in pairs.items()}==summary['paired']
    assert bound['strict_budget_oracle']==summary['diagnostic_oracle']['within_budget_complete']
    write_json(args.output/'independent_verification.json',dict(status='PASS',questions=100,labels_used_for_ranking=False,
        ranking_recomputed_via='Gram pseudoinverse, independent of producer SVD',budget_checks=300,
        catalogue_validation='shared enumerator plus independent graph feasibility; completeness checked by tiny edge-subset tests',
        sealed_prediction_sha256=sha256(args.predictions),recomputed={a:dict(c) for a,c in recomputed.items()},
        stop_decision_verified=True,wall_seconds=time.monotonic()-began))
    write_json(args.output/'feasibility_bounds.json',dict(counts=dict(bound),feasible_tree_count_histogram=dict(hist),
        cases_with_multiple_feasible_table_sets=alternate_node_sets,
        extra_tokens_to_best_unlimited_tree_quantiles=np.quantile(required_extra_tokens,[0,.5,.9,1]).tolist(),
        limitations=['posthoc reference-informed bounds, not a deployable method',
            'reference-only removes BOTH fixed-terminal and connectivity requirements; effects not separated',
            'shared tokenizer/serializer/reference parser; not independent implementations',
            'no extra table/token budget tested as a deployed algorithm; no new SQL/model result']))
    print(json.dumps(dict(audit='PASS',bounds=dict(bound),multiple_feasible_node_sets=alternate_node_sets),indent=2))


if __name__=='__main__':main()
