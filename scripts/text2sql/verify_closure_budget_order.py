"""Recount sealed pilot; diagnose retained original read bindings after evaluation."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import time

import networkx as nx
import numpy as np
from transformers import AutoTokenizer
from closure_budget_order import SchemaClosure,serialize_partial,expressibility,reference_read_bindings
from run_closure_budget_order import sample_cases,ARMS
from run_seed_steiner import read_config,load_inputs,sha256,new_output,write_json
from seed_steiner import reference_tables
from steiner_sql_runtime import read_reference_rows


def main():
    p=argparse.ArgumentParser()
    for name in ['config','execution','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();new_output(a.output);began=time.monotonic();cfg=read_config(a.config);inp=load_inputs(cfg)
    summary=json.loads((a.execution/'aggregate_summary.json').read_text());rows=json.loads((a.execution/'predictions_private.json').read_text())
    assert sha256(a.execution/'predictions_private.json')==summary['prediction_sha256']==json.loads((a.execution/'prediction_seal.json').read_text())['sha256']
    assert sha256(a.config)==summary['config_sha256']==json.loads((a.execution/'run_start.json').read_text())['config_sha256']
    excluded={(r['db_id'],r['question_id']) for r in map(json.loads,Path(cfg['sql_prepared']).read_text().splitlines()) if r['primary'] or r['changed_schema']}
    for name in ['old_route_predictions','old_qafd_predictions']:excluded|={(r['db_id'],r['question_id']) for r in json.loads(Path(cfg[name]).read_text())}
    assert len(excluded)==333
    assert [(r['db_id'],r['question_id']) for r in rows]==[(r['db_id'],r['question_id']) for r in sample_cases(inp['questions'],excluded,cfg['sample_salt'],100)]
    tokenizer=AutoTokenizer.from_pretrained(cfg['sql_model'],local_files_only=True)
    prior={(r['db_id'],r['question_id']):r for r in map(json.loads,Path(cfg['previous_predictions']).read_text().splitlines())}
    qi={(r['db_id'],r['question_id']):i for i,r in enumerate(inp['questions'])};checks=0;memo={};closure={db:SchemaClosure(s,inp['constraints'][db]) for db,s in inp['schemas'].items()}
    def token_count(db,columns,fks):
        key=(db,tuple(sorted(columns)),tuple(f['id'] for f in fks))
        if key not in memo:memo[key]=len(tokenizer.encode(serialize_partial(inp['schemas'][db],columns,fks),add_special_tokens=False))
        return memo[key]
    # Selections replayed without reference labels. Shares deterministic closure and serializer.
    for row in rows:
        db=row['db_id'];s=inp['schemas'][db];allcols={c for c,(t,n) in enumerate(s['column_names_original']) if t>=0};key=(db,row['question_id'])
        oldtables=prior[key]['arms']['weighted']['nodes'];oldcols={c for c in allcols if s['column_names_original'][c][0] in oldtables}
        fks=[f for f in inp['constraints'][db] if f['source_table'] in oldtables and f['target_table'] in oldtables]
        assert row['budget']==token_count(db,oldcols,fks)
        query=inp['queries'][qi[key]];nodes=[n for n in inp['nodes'] if n['db_id']==db and n['node_type']=='column']
        scores={int(n['node_id'].rsplit(':',1)[-1]):float(inp['vectors'][n['ordinal']]@query) for n in nodes}
        # BLAS dot reductions can differ at last bits: use producer matrix arithmetic for tie ordering.
        ids=sorted(scores);lookup={int(n['node_id'].rsplit(':',1)[-1]):n['ordinal'] for n in nodes}
        values=inp['vectors'][[lookup[c] for c in ids]]@query;scores=dict(zip(ids,map(float,values)))
        order=sorted(ids,key=lambda c:(-scores[c],c))
        for arm,r in row['arms'].items():
            actualfks=[f for f in inp['constraints'][db] if f['id'] in r['constraint_ids']]
            assert token_count(db,r['columns'],actualfks)==r['tokens']<=row['budget'];checks+=1
            if arm=='whole_dense':
                assert set(r['columns'])=={c for c in allcols if s['column_names_original'][c][0] in r['tables']}
                continue
            sem=[];rejected=0;removed=0
            for c in order:
                proposal=closure[db].expand(sem+[c]) if arm=='early_closure' else {'columns':sem+[c],'constraints':[]}
                if token_count(db,proposal['columns'],proposal['constraints'])<=row['budget']:sem.append(c)
                else:rejected+=1
            candidate=closure[db].expand(sem)
            while token_count(db,candidate['columns'],candidate['constraints'])>row['budget']:
                assert arm=='late_closure';sem.pop();removed+=1;candidate=closure[db].expand(sem)
            assert sorted(sem)==r['semantic_columns'] and candidate['columns']==r['columns'] and candidate['tables']==r['tables']
            assert rejected==r['rejected_columns'] and removed==r['repair_removals']
            expectedfks=[f for f in inp['constraints'][db] if f['source_table'] in r['tables'] and f['target_table'] in r['tables']]
            assert expectedfks==actualfks
            assert set(r['columns'])==set(sem)|{c for f in expectedfks for pair in f['pairs'] for c in pair}
            graph=closure[db].graph;retained=graph.subgraph(r['tables']);terminals={s['column_names_original'][c][0] for c in sem}
            for component in nx.connected_components(graph):
                terms=sorted(component&terminals)
                assert not terms or all(nx.has_path(retained,terms[0],t) for t in terms)
    # Reference labels only below this line. New binding diagnostic does not change registered primary gate.
    refs={(r['db_id'],r['question_id']):r['SQL'] for r in read_reference_rows(cfg)}
    counts={arm:Counter() for arm in ARMS};pair={b:Counter() for b in ARMS[:2]};diag=Counter();losses=[];bindingrows=[]
    for row in rows:
        db=row['db_id'];s=inp['schemas'][db];sql=refs[(db,row['question_id'])];allcols={c for c,(t,n) in enumerate(s['column_names_original']) if t>=0}
        full=expressibility(sql,s,allcols);gold=reference_tables(sql,s);statuses={}
        bind=reference_read_bindings(sql,s) if full['status']=='compatible' else dict(status='unknown',tables=[],columns=[])
        if bind['status']=='ok':
            diag['binding_evaluable']+=1;witness=set(bind['columns'])
            for tid in bind['tables']:
                if not any(s['column_names_original'][c][0]==tid for c in witness):witness.add(min(c for c in allcols if s['column_names_original'][c][0]==tid))
            oracle=closure[db].expand(witness);oraclecost=token_count(db,oracle['columns'],oracle['constraints']);fits=oraclecost<=row['budget']
            diag['reference_binding_closure_fits_budget']+=int(fits)
        else:fits=False;oraclecost=None
        for arm,r in row['arms'].items():
            e=expressibility(sql,s,r['columns']) if full['status']=='compatible' else dict(status='unknown',reason=full['reason']);statuses[arm]=e['status']
            values=dict(questions=1,evaluable=int(full['status']=='compatible'),compatible=int(e['status']=='compatible'),unknown=int(e['status']=='unknown'),complete_tables=int(gold<=set(r['tables'])),tokens=r['tokens'],columns=len(r['columns']),semantic_columns=len(r['semantic_columns']),connector_columns=len(set(r['columns'])-set(r['semantic_columns'])),tables=len(r['tables']),late_repair_removals=r['repair_removals'],late_repair_cases=int(r['repair_removals']>0))
            counts[arm].update(values)
            if bind['status']=='ok':
                missing=set(bind['columns'])-set(r['columns']);binding_ok=not missing and set(bind['tables'])<=set(r['tables'])
                diag[arm+'_retains_original_read_bindings']+=int(binding_ok)
                diag[arm+'_preparable_but_missing_original_bindings']+=int(e['status']=='compatible' and not binding_ok)
                if arm=='early_closure':
                    diag['early_complete_tables_but_not_preparable']+=int(values['complete_tables'] and e['status']=='incompatible')
                    diag['early_missing_binding_despite_feasible_reference_closure']+=int(not binding_ok and fits)
        for base in pair:
            if full['status']!='compatible':pair[base]['unknown']+=1
            else:
                better=statuses['early_closure']=='compatible';b=statuses[base]=='compatible';pair[base]['rescue' if better and not b else 'damage' if b and not better else 'unchanged']+=1
        if statuses['whole_dense']=='compatible' and statuses['early_closure']=='incompatible':
            r=row['arms']['early_closure'];missed=set(bind['columns'])-set(r['columns']) if bind['status']=='ok' else set()
            names={s['column_names_original'][c][1].casefold() for c in r['columns']}
            losses.append(dict(full_reference_tables_retained=gold<=set(r['tables']),original_read_binding_columns_missing=len(missed),
                missing_fields_with_name_present_elsewhere=sum(s['column_names_original'][c][1].casefold() in names for c in missed),
                missing_field_table_widths=[sum(t==s['column_names_original'][c][0] for t,n in s['column_names_original']) for c in sorted(missed)],
                reference_binding_closure_fits_budget=fits,budget=row['budget'],reference_binding_closure_tokens=oraclecost))
        bindingrows.append(dict(db_id=db,question_id=row['question_id'],bindings=bind))
    assert {a:dict(c) for a,c in counts.items()}==summary['arms']
    assert {a:dict(c) for a,c in pair.items()}==summary['paired']
    gate=counts['early_closure']['evaluable']>=90 and counts['early_closure']['compatible']>=counts['late_closure']['compatible']+3 and counts['early_closure']['compatible']>=counts['whole_dense']['compatible']
    assert gate==summary['upgrade_gate']
    write_json(a.output/'bindings_private.json',bindingrows)
    write_json(a.output/'posthoc_binding_diagnosis.json',dict(status='exploratory posthoc; no primary metric or gate replacement',counts=dict(diag),whole_to_early_losses=losses,
        limitation='physical read bindings from full TEXT-type schema stubs, not semantic intent labels or SQL execution accuracy'))
    output=dict(status='PASS',questions=len(rows),budget_checks=checks,selection_replays=2*len(rows),primary_counts_verified=True,gate_verified=True,
        prediction_sha256=sha256(a.execution/'predictions_private.json'),wall_seconds=time.monotonic()-began,new_model_calls=0,
        limitations=['shared tokenizer/serializer/closure/reference-table parser and primary prepare evaluator','binding diagnostic uses a separate full-stub SQLite authorizer and is posthoc','not semantic sufficiency or execution accuracy'])
    write_json(a.output/'verification.json',output);print(json.dumps(output,indent=2))


if __name__=='__main__':main()
