#!/usr/bin/env python3
"""One bounded, CPU-only AST binding audit of the frozen 19-case queue."""
import argparse
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.text2sql import audit_p2c_values_risk as risk
from scripts.text2sql import predicate_value_binding as binding

core, recovery = risk.core, risk.recovery
EXPERIMENT_ID = 'p2c_value_binding_20261019_01'
REPORT = core.REPO_ROOT / 'docs/research/text2sql/reports' / EXPERIMENT_ID
PROTOCOL = core.REPO_ROOT / 'docs/research/text2sql/plans/p2c_value_binding_20261019.md'


def schema_catalog(schema):
    tables = schema['table_names_original']
    result = {table: {} for table in tables}
    for index, (table_index, name) in enumerate(schema['column_names_original']):
        if table_index >= 0:
            result[tables[table_index]][name] = f"column:{schema['db_id']}:{index}"
    return result


def validate_registration(config, args):
    if config.get('experiment_id') != EXPERIMENT_ID or config.get('status') != 'preregistered_not_run':
        raise RuntimeError('Binding audit registration is absent or closed')
    if args.run_id != config['run_ids'][args.mode] or args.output_dir.resolve() != Path(config['private_output_dirs'][args.mode]).resolve():
        raise RuntimeError('Binding run identity/path differs from registration')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('smoke', 'full'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--expected-commit', required=True)
    for name in ('output-dir', 'p2c-run-dir', 'lexical-run-dir', 'p1-6-run-dir', 'legacy-root', 'dataset-root', 'model-path', 'previous-run-dir', 'p1-5-run-dir', 'p2b-run-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--smoke-dir', type=Path)
    return parser.parse_args()


def run():
    args = parse_args()
    config_path = REPORT / 'experiment_config.json'
    config = json.loads(config_path.read_text())
    validate_registration(config, args)
    if core.package_version('sqlglot') != config['sqlglot_version']:
        raise RuntimeError('SQL parser differs from registration')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    sources = (*recovery.EXECUTION_SOURCES, Path(risk.__file__), Path(binding.__file__), Path(__file__).resolve())
    receipt = {'experiment_id': EXPERIMENT_ID, 'run_id': args.run_id, 'mode': args.mode, 'state': 'started',
               'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'command': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               'source': {'published_commit': args.expected_commit, 'execution_sources': recovery.execution_source_hashes(sources),
                          'config_sha256': core.sha256_file(config_path), 'protocol_sha256': core.sha256_file(PROTOCOL)},
               'dependency_source_sha256': {Path(inspect.getfile(obj)).name: core.sha256_file(Path(inspect.getfile(obj))) for obj in (binding.qualify, binding.Scope)},
               'environment': {name: core.package_version(name) for name in ('numpy', 'transformers', 'tokenizers', 'sqlglot')},
               'resource_snapshot': core.resource_snapshot(), 'api_calls': 0, 'model_forwards': 0,
               'gpu_seconds': 0, 'sql_executions': 0, 'human_reviews': 0}
    core.write_json(args.output_dir / 'run_start.json', receipt)
    try:
        info = core.load_registered_inputs(args, config_path=config_path, plan_path=PROTOCOL, experiment_id=EXPERIMENT_ID)
        recovery.assert_frozen_hashes(config, info['p2b_hashes'])
        receipt['input_hashes'] = dict(info['p2b_hashes'])
        required = {
            'query_json': args.dataset_root / 'dev.json', 'schema_json': args.dataset_root / 'dev_tables.json',
            'p2c_aggregate': args.p2c_run_dir / 'aggregate_summary.json',
            'p2c_private_rows': args.p2c_run_dir / 'per_question_private.jsonl',
            'lexical_aggregate': args.lexical_run_dir / 'aggregate_summary.json',
            'lexical_private_rows': args.lexical_run_dir / 'per_question_private.jsonl',
            'priority_queue': args.lexical_run_dir / 'human_review_priority_private.json',
        }
        for key, path in required.items():
            actual = core.sha256_file(path)
            if actual != config['audit_inputs_sha256'][key]:
                raise RuntimeError('Binding input hash differs: ' + key)
            receipt['input_hashes'][key] = actual
        if args.mode == 'full':
            if args.smoke_dir is None or args.smoke_dir.resolve() != Path(config['private_output_dirs']['smoke']).resolve():
                raise RuntimeError('Binding smoke path differs')
            smoke = recovery.read_stage_receipt(args.smoke_dir, EXPERIMENT_ID, config['run_ids']['smoke'], 'smoke_passed', args.expected_commit)
            for key in ('source', 'input_hashes', 'environment', 'dependency_source_sha256'):
                if smoke[key] != receipt[key]:
                    raise RuntimeError('Binding smoke/full differs: ' + key)
        queue = json.loads(required['priority_queue'].read_text())
        if len(queue) != 19 or len({row['question_id'] for row in queue}) != 19:
            raise RuntimeError('Frozen priority queue is not exactly 19 unique questions')
        if any(row['human_review_status'] != 'not_reviewed' or row['semantic_necessity'] is not None for row in queue):
            raise RuntimeError('Frozen blank review queue changed')
        chosen = queue[:5] if args.mode == 'smoke' else queue
        wanted = {row['source_ordinal']: row for row in chosen}
        lexical, old = {}, {}
        for destination, path in ((lexical, required['lexical_private_rows']), (old, required['p2c_private_rows'])):
            with path.open() as stream:
                count = 0
                for index, line in enumerate(stream):
                    count += 1
                    if index in wanted:
                        destination[index] = json.loads(line)
                if count != 1534:
                    raise RuntimeError('Frozen source row denominator differs')
        raw = {int(row['question_id']): row for row in json.loads(required['query_json'].read_text())}
        schemas = {row['db_id']: row for row in json.loads(required['schema_json'].read_text())}
        prepared = info['prepared_full']
        questions = {row['question_id']: row for row in prepared['questions']}
        r0 = {node.node_id: node.text for node in prepared['nodes']}
        r1 = {node.node_id: node.text for node in info['r1_nodes_full']}
        aliases = {db: f'db_{i:02d}' for i, db in enumerate(sorted(schemas), 1)}
        totals, per_db, strata, unknowns = Counter(), {}, {}, Counter()
        trace_path = args.output_dir / 'per_case_private.jsonl'
        with trace_path.open('x') as target:
            for case in chosen:
                index, qid = case['source_ordinal'], case['question_id']
                saved, previous, item, question = lexical[index], old[index], raw[qid], questions[qid]
                db = item['db_id']
                if (saved['question_id'], previous['question_id'], aliases[db]) != (qid, qid, case['database_alias']) or saved['db_id'] != db or previous['db_id'] != db:
                    raise RuntimeError('Binding case order/identity differs')
                literals, _ = risk.extract_predicate_literals(item['SQL'])
                left, right = [previous['arms'][arm]['budgets']['1024'] for arm in ('V00', 'V01')]
                replay = risk.find_exposures(literals, item['question'] + '\n' + item.get('evidence', ''), left['selected_ids'], right['selected_ids'], r0, r1, set(question['label']['gold_column_ids']))
                if replay != saved['flags']:
                    raise RuntimeError('Frozen lexical exposure replay differs')
                bindings = binding.bind_sql_literals(item['SQL'], schema_catalog(schemas[db]))
                literal_keys = {hashlib.sha256((row['kind'] + ':' + row['value']).encode()).hexdigest() for row in literals}
                if set(bindings) != literal_keys:
                    raise RuntimeError('Binding and frozen lexical extraction disagree')
                flags = []
                for flag in saved['flags']:
                    if flag['input_mentions_literal']:
                        continue
                    resolved = bindings[flag['literal_sha256']]
                    category = binding.classify_binding(resolved, flag['matching_node_ids'])
                    flags.append({'literal_sha256': flag['literal_sha256'], 'category': category,
                                  'binding': resolved, 'matching_values_node_ids': flag['matching_node_ids'],
                                  'supported_node_ids': sorted(set(resolved['node_ids']).intersection(flag['matching_node_ids']))})
                    unknowns.update(resolved['unresolved_reasons'])
                if not flags:
                    raise RuntimeError('Priority case has no input-absent literal')
                counts = Counter(questions=1, literal_flags=len(flags))
                counts.update(flag['category'] for flag in flags)
                case_category = 'supported_questions' if counts['binding_supported'] else 'unresolved_questions' if counts['binding_unresolved'] else 'mismatch_questions'
                counts[case_category] = 1
                counts['supported_flags_with_other_unresolved_occurrences'] = sum(flag['category'] == 'binding_supported' and bool(flag['binding']['unresolved_reasons']) for flag in flags)
                totals.update(counts)
                per_db.setdefault(aliases[db], Counter()).update(counts)
                strata.setdefault(case['coverage_stratum'], Counter()).update(counts)
                target.write(json.dumps({'audit_case': case['audit_case'], 'question_id': qid, 'database_alias': aliases[db],
                                         'coverage_stratum': case['coverage_stratum'], 'counts': counts, 'flags': flags}) + '\n')
                if time.process_time() - started_cpu > 300 or core.peak_rss_gib() > 4:
                    raise RuntimeError('Binding CPU/RSS budget exceeded')
        if args.mode == 'full' and (totals['questions'], totals['literal_flags']) != (19, 21):
            raise RuntimeError('Binding final denominator differs from 19 questions/21 flags')
        if sum(totals[name] for name in ('binding_supported', 'binding_mismatch', 'binding_unresolved')) != totals['literal_flags']:
            raise RuntimeError('Binding categories do not partition flags')
        aggregate = {'experiment_id': EXPERIMENT_ID, 'run_id': args.run_id, 'mode': args.mode,
                     'smoke_only': args.mode == 'smoke', 'status': 'completed', 'source_commit': args.expected_commit,
                     'counts': totals, 'per_database_anonymized': per_db, 'coverage_strata': strata,
                     'unresolved_reason_flag_counts': unknowns, 'input_hashes': receipt['input_hashes'],
                     'decision': 'prioritize_binding_supported_cases_for_semantic_review' if totals['binding_supported'] else 'no_direct_binding_support_in_frozen_queue',
                     'interpretation': 'AST incidence only; mismatch does not rule out indirect utility; unknowns are not negatives; no semantic necessity or SQL accuracy assessment',
                     'human_reviews': 0, 'semantic_necessity_denominator': 0,
                     'api_usage': {'requests': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_cny': '0.00'},
                     'model_forwards': 0, 'gpu_seconds': 0, 'sql_executions': 0}
        receipt['aggregate_summary_sha256'] = recovery.write_roundtrip(args.output_dir / 'aggregate_summary.json', aggregate)
        receipt['private_rows_sha256'] = core.sha256_file(trace_path)
        if time.process_time() - started_cpu > 300 or core.peak_rss_gib() > 4:
            raise RuntimeError('Binding CPU/RSS budget exceeded after persistence')
        receipt.update(state='completed', stage_result=args.mode + '_passed', decision=aggregate['decision'])
    except Exception as error:
        receipt.update(state='failed', error_type=type(error).__name__)
        raise
    finally:
        receipt.update(cpu_seconds=time.process_time() - started_cpu, wall_seconds=time.perf_counter() - started_wall,
                       peak_rss_gib=core.peak_rss_gib(), finished_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        core.write_json(args.output_dir / 'run_start.json', receipt)
        print(json.dumps({key: receipt.get(key) for key in ('run_id', 'state', 'stage_result', 'cpu_seconds', 'wall_seconds', 'peak_rss_gib', 'decision', 'error_type')}), flush=True)


if __name__ == '__main__':
    run()
