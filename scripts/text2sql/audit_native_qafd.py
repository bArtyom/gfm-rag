"""Bounded execution of the original core, not an end-to-end benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import networkx as nx
import numpy as np
from qafd_context_capacity import load_upstream_core
from run_seed_steiner import read_config,load_inputs,new_output,write_json,sha256
from query_weighted_steiner import weighted_graph


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();new_output(args.output);cfg=read_config(args.config);began=time.monotonic()
    up=Path(cfg['qafd_upstream'])
    assert subprocess.check_output(['git','-C',str(up),'rev-parse','HEAD'],text=True).strip()==cfg['qafd_commit']
    assert not subprocess.check_output(['git','-C',str(up),'status','--porcelain'],text=True).strip()
    core=load_upstream_core(up)
    toygraphs=[nx.path_graph(4),nx.star_graph(4),nx.cycle_graph(5)]
    records=[]
    def execute(graph,source,embeddings,query,label):
        retriever=core(graph,source,source,confidence=cfg['native_confidence'],epsilon=.01,
            node_embeddings=embeddings,subquery_embedding=query,weight_func='multiply',random_seed=42)
        retriever.initialize(alpha=cfg['native_alpha'])
        initial=sum(retriever.mass.values());capacity=sum(retriever.sink_capacity.values())
        reachable=sum(retriever.sink_capacity[t] for t in nx.node_connected_component(graph,source))
        retriever.flow_diffusion(max_iterations=cfg['native_iterations'])
        final=sum(retriever.mass.values());excess=sum(max(0,retriever.mass[t]-retriever.sink_capacity[t]) for t in graph)
        record=dict(case=label,nodes=len(graph),edges=graph.number_of_edges(),initial_mass=initial,total_capacity=capacity,
            reachable_capacity=reachable,necessary_capacity_condition=initial<=reachable,final_mass=final,mass_loss=initial-final,
            final_total_excess=excess,remaining_excess_nodes=sum(retriever.mass[t]>retriever.sink_capacity[t]+.01 for t in graph),
            active_scores=sum(x>0 for x in retriever.x.values()),iterations_limit=cfg['native_iterations'])
        records.append({k:(v.item() if isinstance(v,np.generic) else v) for k,v in record.items()})
    for i,g in enumerate(toygraphs):execute(g,0,{t:[1.,float(t)/5] for t in g},[1.,1.],f'toy-{i+1}')
    inputs=load_inputs(cfg)
    selected=sorted(inputs['questions'],key=lambda r:hashlib.sha256(f'qafd-native-v1:{r["db_id"]}:{r["question_id"]}'.encode()).hexdigest())[:5]
    qis={(r['db_id'],r['question_id']):i for i,r in enumerate(inputs['questions'])}
    prior={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    for i,row in enumerate(selected):
        db=row['db_id'];indices=[j for j,n in enumerate(inputs['nodes']) if n['db_id']==db and n['node_type']=='table']
        vectors={int(inputs['nodes'][j]['node_id'].rsplit(':',1)[-1]):inputs['vectors'][j].tolist() for j in indices}
        g,_=weighted_graph(len(vectors),inputs['constraints'][db],np.ones(len(inputs['constraints'][db])))
        for a,b in g.edges:g[a][b]['weight']=(np.dot(vectors[a],vectors[b])+1)/2
        execute(g,prior[(db,row['question_id'])]['seeds'][0],vectors,inputs['queries'][qis[(db,row['question_id'])]].tolist(),f'BIRD-{i+1:02d}')
    write_json(args.output/'native_core_audit.json',dict(status='completed',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        upstream_repository='https://github.com/Tarzanagh/QAFD-RAG',upstream_commit=cfg['qafd_commit'],
        source_sha256={n:sha256(up/n) for n in ['src/retrievers/base.py','src/retrievers/flow_diffusion.py']},
        shim='isolated package + stdlib logger only; original base/core code unchanged',
        alpha=cfg['native_alpha'],confidence=cfg['native_confidence'],cases=records,new_model_calls=0,
        interpretation='bounded core/config audit only; no paper recovery theorem or end-to-end score falsification',
        wall_seconds=time.monotonic()-began))
    print(json.dumps(records,indent=2))


if __name__=='__main__':main()
