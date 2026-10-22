"""Prepare sealed P2d inputs without any model or benchmark SQL execution."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.request

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from scripts.text2sql import run_p2c_dual_view_factorial as core
from scripts.text2sql import p2d_inputs as helper

BASE = Path(os.environ.get('P2D_RESULT_ROOT', '/mnt/liansp3/sources/results/gfmrag_p2d_sql_utility_20261022_01'))
OUT = BASE / 'prepare_01'
OUT.mkdir(exist_ok=False)
started = time.perf_counter()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


p1 = core.load_module(core.P1_6_RUNNER, 'p1_for_p2d_prepare')
p2a = core.load_module(core.P2A_RUNNER, 'p2a_for_p2d_prepare')
p2b = core.load_module(core.P2B_RUNNER, 'p2b_for_p2d_prepare')
args = argparse.Namespace(
    p1_6_run_dir=Path('/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01'),
    legacy_root=Path('/mnt/liansp3/sources/projects/quadrag'), dataset_root=Path('/mnt/liansp3/sources/datasets/bird/dev'),
    model_path=Path('/mnt/liansp3/sources/models/qwen3-embedding-0.6b'),
    previous_run_dir=Path('/mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01'),
    p1_5_run_dir=Path('/mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03'))
record, prepared, _, _ = p2a.validate_p1_6_inputs(args, p1)
_, common = p1.load_common(args.legacy_root, args.dataset_root, args.model_path)
from transformers import AutoTokenizer
embedding_tokenizer = AutoTokenizer.from_pretrained(str(args.model_path), local_files_only=True, trust_remote_code=True)
r1_nodes, text_audit = p2b.build_r1_nodes(prepared, common, embedding_tokenizer)
assert text_audit['r0_schema_text_sequence_sha256'] == 'b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a'
assert text_audit['r1_schema_text_sequence_sha256'] == '73c59126b931fb72b7c09ba06de76327057e32832e2aeef0c8175b8956ed3e3c'
r0 = {node.node_id: node.text for node in prepared['nodes']}
r1 = {node.node_id: node.text for node in r1_nodes}
sources = {}
def pin(name, path, expected=None):
    sha = core.sha256_file(path)
    if expected is not None:
        assert sha == expected, name
    sources[name] = {'path': str(Path(path).resolve()), 'sha256': sha}
    return Path(path)

p2c_dir = Path('/mnt/liansp3/sources/results/gfmrag_p2c_r_recovery_20261019/full_1534_20261019_01')
pin('p2c_aggregate', p2c_dir / 'aggregate_summary.json', '7e4ce4b2a92df5e17160bb2429402b66ab7caec521c6e4da9ec90abd108e8fdc')
rows_path = pin('p2c_rows', p2c_dir / 'per_question_private.jsonl', '99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff')
binding_path = pin('binding_rows', Path('/mnt/liansp3/sources/results/gfmrag_p2c_value_binding_20261019/full_19q_20261019_01/per_case_private.jsonl'), '9af35480aa5804edba6ea8d772431fc90af96aa91e9771e479ad18f2ec5ffae1')
with rows_path.open() as stream:
    previous = {row['question_id']: row for row in map(json.loads, stream)}
with binding_path.open() as stream:
    priority_rows = list(map(json.loads, stream))
assert len(previous) == 1534 and len(priority_rows) == 19
query_path = pin('query_json', args.dataset_root / 'dev.json', '630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06')
pin('schema_json', args.dataset_root / 'dev_tables.json', '35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97')
raw = {int(row['question_id']): row for row in read(query_path)}
questions = {row['question_id']: row for row in prepared['questions']}
eligible = {qid: helper.feature(raw[qid], row, previous[qid]) for qid, row in questions.items() if row['label']['column_eligible']}
assert len(eligible) == 1460
priority = [row['question_id'] for row in priority_rows]
pairs, gaps = helper.match_controls(priority, eligible, 20261021)
control_ids = [control for _, control in pairs]
full_ids = priority + control_ids
available = sorted(set(eligible) - set(full_ids))
random.Random(20261022).shuffle(available)
smoke_ids = available[:3]
assert len(set(full_ids + smoke_ids)) == len(full_ids) + 3
labels = {}
for row in priority_rows:
    labels[row['question_id']] = 'supported' if row['counts'].get('supported_questions') else 'unresolved' if row['counts'].get('unresolved_questions') else 'mismatch'
aliases = {db: f'db_{index:02d}' for index, db in enumerate(sorted({row['db_id'] for row in raw.values()}), 1)}
model_root = Path('/mnt/liansp3/sources/models/qwen25-coder-7b')
tokenizer = AutoTokenizer.from_pretrained(str(model_root), local_files_only=True)
case_dir = OUT / 'cases'
case_dir.mkdir()
evaluation = {}
manifest = []
db_sources = {}
prompt_tokens = 0
for index, qid in enumerate(full_ids + smoke_ids):
    item = raw[qid]
    cohort = 'priority' if qid in priority else 'control' if qid in control_ids else 'smoke'
    case_id = f'P2D-{index+1:03d}'
    views = helper.contexts(previous[qid], r0, r1)
    arms = {}
    fixed = helper.digest_object({'question': item['question'], 'evidence': item.get('evidence', ''), 'system': helper.SYSTEM})
    for arm, view in views.items():
        msg = helper.messages(item['question'], item.get('evidence', ''), view['text'])
        tokens = len(tokenizer.apply_chat_template(msg, tokenize=True, add_generation_prompt=True))
        assert tokens + 1024 <= 32768
        prompt_tokens += tokens
        arms[arm] = {**view, 'messages': msg, 'messages_sha256': helper.digest_object(msg), 'prompt_tokens_local': tokens, 'common_fields_sha256': fixed}
    assert arms['E0']['node_ids'] == arms['E2']['node_ids']
    assert {arm['common_fields_sha256'] for arm in arms.values()} == {fixed}
    db_path = args.dataset_root / 'dev_databases' / item['db_id'] / (item['db_id'] + '.sqlite')
    assert db_path.is_file()
    if item['db_id'] not in db_sources:
        db_sources[item['db_id']] = {'path': str(db_path.resolve()), 'sha256': core.sha256_file(db_path)}
    a, b = [previous[qid]['arms'][arm]['budgets']['1024']['complete'] for arm in ('V00', 'V01')]
    coverage = 'rescued' if b > a else 'damaged' if b < a else 'unchanged'
    payload = {'case_id': case_id, 'question_id': qid, 'database_alias': aliases[item['db_id']], 'cohort': cohort,
               'binding_class': labels.get(qid, 'not_priority'), 'coverage_stratum': coverage, 'arms': arms}
    path = case_dir / (case_id + '.json')
    save(path, payload)
    manifest.append({'case_id': case_id, 'file': str(path.relative_to(OUT)), 'sha256': core.sha256_file(path), 'cohort': cohort})
    evaluation[case_id] = {'reference_sql': item['SQL'], 'database_path': str(db_path.resolve()), 'database_sha256': db_sources[item['db_id']]['sha256']}
save(OUT / 'evaluation_private.json', evaluation)
save(OUT / 'sources_private.json', {'inputs': sources, 'databases': db_sources, 'input_manifest_sha256': record['input_manifest_sha256']})
save(OUT / 'semantic_review_private.json', {'status': 'unverified', 'human_reviewers': [], 'human_reviews': 0,
     'records': [{'case_id': f'P2D-{index+1:03d}', 'status': 'unknown', 'review_stage_1': None, 'review_stage_2': None} for index in range(19)],
     'raw_agreement': None, 'cohen_kappa': None})
model_files = [model_root / name for name in ('config.json', 'tokenizer_config.json', 'tokenizer.json', 'generation_config.json', 'model.safetensors.index.json')]
index = read(model_root / 'model.safetensors.index.json')
model_files += [model_root / name for name in sorted(set(index['weight_map'].values()))]
model_manifest = {path.name: core.sha256_file(path) for path in model_files}
save(OUT / 'model_manifest_private.json', {'root': str(model_root.resolve()), 'files': model_manifest})
with urllib.request.urlopen(os.environ['P2D_LOCAL_BASE_URL'] + '/v1/models', timeout=10) as response:
    metadata = json.load(response)
assert [(row['id'], row.get('max_model_len')) for row in metadata['data']] == [('Qwen2.5-Coder-7B-Instruct', 32768)]
cmdline = Path('/proc/' + os.environ['P2D_LOCAL_SERVICE_PID'] + '/cmdline').read_bytes().split(b'\0')
arguments = [part.decode() for part in cmdline if part]
assert '--model' in arguments
assert Path(arguments[arguments.index('--model')+1]).resolve() == model_root.resolve()
transport = OUT / 'transport.env'
transport.write_text('P2D_LOCAL_BASE_URL=' + os.environ['P2D_LOCAL_BASE_URL'] + '\n')
transport.chmod(0o600)
save(OUT / 'backend_private.json', {'pid': int(os.environ['P2D_LOCAL_SERVICE_PID']), 'cmdline_sha256': hashlib.sha256(Path('/proc/' + os.environ['P2D_LOCAL_SERVICE_PID'] + '/cmdline').read_bytes()).hexdigest(), 'model': 'Qwen2.5-Coder-7B-Instruct', 'max_model_len': 32768})
sealed = {'cases': manifest, 'priority_ids_sha256': helper.digest_object(priority), 'control_ids_sha256': helper.digest_object(control_ids),
          'smoke_ids_sha256': helper.digest_object(smoke_ids), 'pairs': pairs, 'unmatched_priority_ids': gaps,
          'full_cases': len(full_ids), 'control_cases': len(control_ids), 'private_smoke_cases': 3,
          'predicted_input_tokens_local': prompt_tokens, 'model_manifest_sha256': core.sha256_file(OUT / 'model_manifest_private.json'),
          'max_total_model_calls': 3 + 9 + 3*len(full_ids),
          'files': {path.name: core.sha256_file(path) for path in OUT.iterdir() if path.is_file()},
          'selection_seed': 20261021, 'semantic_review_status': 'unverified', 'human_reviews': 0,
          'prepared_wall_seconds': time.perf_counter()-started}
save(OUT / 'prepare_seal_private.json', sealed)
report = Path(os.environ.get('P2D_REPORT_ROOT', str(ROOT / 'docs/research/text2sql/reports/p2d_sql_utility_20261022_01')))
report.mkdir(exist_ok=False)
summary = {'status': 'prepared_not_run', 'priority_cases': 19, 'control_cases': len(control_ids), 'unmatched_priority_cases': len(gaps),
           'full_cases': len(full_ids), 'private_smoke_cases': 3, 'selection_seed': 20261021,
           'matching': 'exact DB, predicate kind set, gold table and column counts, V00 complete; without replacement; no EX',
           'priority_binding_counts': dict(Counter(labels.values())), 'per_database_alias': dict(Counter(aliases[raw[qid]['db_id']] for qid in full_ids)),
           'priority_ids_sha256': sealed['priority_ids_sha256'], 'control_ids_sha256': sealed['control_ids_sha256'], 'smoke_ids_sha256': sealed['smoke_ids_sha256'],
           'prepare_seal_sha256': core.sha256_file(OUT/'prepare_seal_private.json'), 'model_files_sha256': model_manifest,
           'prompt_template_sha256': helper.digest_object({'system': helper.SYSTEM, 'template_version': 'p2d_descriptive_nodes_v1'}),
           'input_manifest_sha256': record['input_manifest_sha256'], 'source_artifact_sha256': {key: item['sha256'] for key,item in sources.items()},
           'context_policy': 'Exactly archived selected node texts in order; ownership in node text; no FK or other constraints added since original texts contain none and FK gate unresolved',
           'semantic_review_status': 'unverified', 'human_reviews': 0, 'max_total_model_calls': sealed['max_total_model_calls'],
           'tokens_local_full_plus_smoke': prompt_tokens, 'prepared_wall_seconds': sealed['prepared_wall_seconds']}
save(report / 'sample_registration.json', summary)
print(json.dumps({key: summary[key] for key in ('priority_cases','control_cases','unmatched_priority_cases','full_cases','max_total_model_calls','tokens_local_full_plus_smoke','prepared_wall_seconds')}))
