"""Structural tests for closure budgeting and one-sided expressibility."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/text2sql'))
from closure_budget_order import SchemaClosure,serialize_partial,expressibility,select_columns
from seed_steiner import serialize_schema


def fixture():
    s={'table_names_original':['a','bridge','b','island'],
       'column_names_original':[[-1,'*'],[0,'id'],[0,'label'],[1,'aid'],[1,'bid'],[2,'id'],[2,'value'],[3,'other']],
       'column_types':['text','number','text','number','number','number','text','text'],'primary_keys':[1,5]}
    f=[{'id':'ab','source_table':0,'target_table':1,'pairs':[[1,3]]},
       {'id':'bc','source_table':1,'target_table':2,'pairs':[[4,5]]}]
    return s,f


def test_closure_adds_only_keys_and_preserves_disconnected_components():
    s,f=fixture();r=SchemaClosure(s,f).expand({2,6,7})
    assert set(r['columns'])==set(range(1,8)) and r['tables']==[0,1,2,3]
    assert len(r['constraints'])==2


def test_composite_fk_is_atomic_and_full_serializer_matches():
    s,f=fixture();f[0]['pairs'].append([2,4])
    r=SchemaClosure(s,f).expand({2,6})
    assert set(range(1,7))<=set(r['columns'])
    assert serialize_partial(s,range(1,8),f)==serialize_schema(s,range(4),f)


def test_partial_schema_preparation_detects_missing_field_and_nested_alias():
    s,f=fixture()
    assert expressibility('SELECT x.label FROM a x WHERE x.id IN (SELECT aid FROM bridge)',s,{1,2,3})['status']=='compatible'
    assert expressibility('SELECT x.label FROM a x',s,{1})['status']=='incompatible'
    assert expressibility('SELECT COUNT(*) FROM a',s,{1})['status']=='compatible'


def test_projection_and_quoted_identifier_semantics_are_not_silently_accepted():
    s,f=fixture()
    for sql in ['SELECT * FROM a','SELECT a.* FROM a','SELECT "label" FROM a','SELECT label FROM a NATURAL JOIN b','SELECT id FROM a JOIN b USING(id)']:
        assert expressibility(sql,s,{1,2,5})['status']=='unknown'


def test_early_closure_skips_expensive_column_and_continues():
    # Cheap column can be admitted after an expensive rejected candidate.
    def expand(cols):return {'columns':sorted(cols),'tables':[0],'constraints':[]}
    def cost(cols,closed):return sum({1:7,2:9,3:2}[c] for c in cols)
    early=select_columns([1,2,3],9,expand,cost,'early')
    assert early['semantic_columns']==[1,3] and early['tokens']==9
    late=select_columns([1,2,3],9,expand,cost,'late')
    assert late['tokens']<=9


def test_late_repair_can_discard_a_cheaper_tail_column():
    def expand(cols):return {'columns':sorted(cols),'tables':[0],'constraints':[]}
    def cost(cols,closed):return sum({1:4,2:4,3:1}[c] for c in cols)+(5 if closed is not None and 2 in cols else 0)
    assert select_columns([1,2,3],9,expand,cost,'late')['semantic_columns']==[1]
    assert select_columns([1,2,3],9,expand,cost,'early')['semantic_columns']==[1,3]


def test_reference_binding_audit_catches_correlated_rebinding():
    from closure_budget_order import reference_read_bindings
    s,_=fixture();sql='SELECT a.id FROM a WHERE EXISTS (SELECT 1 FROM b WHERE id > 0)'
    assert expressibility(sql,s,{1,6})['status']=='compatible'
    binds=reference_read_bindings(sql,s)
    assert binds['status']=='ok' and set(binds['columns'])=={1,5}
