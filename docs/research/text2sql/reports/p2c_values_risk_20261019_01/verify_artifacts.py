"""Independently recount persisted risk flags; no SQL/literal text is read."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(directory, p2c_directory):
    receipt = read(directory / 'run_start.json')
    aggregate = read(directory / 'aggregate_summary.json')
    assert receipt['state'] == 'completed'
    assert receipt['aggregate_summary_sha256'] == digest(directory / 'aggregate_summary.json')
    assert receipt['private_rows_sha256'] == digest(directory / 'per_question_private.jsonl')
    assert receipt['source']['published_commit'] == aggregate['source_commit']
    p2c = read(p2c_directory / 'aggregate_summary.json')
    assert digest(p2c_directory / 'aggregate_summary.json') == aggregate['frozen_p2c_aggregate_sha256']
    assert digest(p2c_directory / 'per_question_private.jsonl') == '99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff'
    for path, expected_sha in receipt['source']['execution_sources'].items():
        assert digest(Path.cwd() / path) == expected_sha
    fixed_aliases = set(p2c['primary_gate']['fixed_database_deltas_pp_anonymized'])
    with (p2c_directory / 'per_question_private.jsonl').open() as source:
        prior = [json.loads(line) for line in source]
    aliases = {db: f'db_{i:02d}' for i, db in enumerate(sorted({row['db_id'] for row in prior}), 1)}
    expected = 5 if aggregate['smoke_only'] else 1534
    totals = {name: Counter() for name in aggregate['counts']}
    per_db = {alias: Counter() for alias in aliases.values()}
    strata = {name: Counter() for name in aggregate['coverage_strata']}
    intersections = Counter()
    flag_count = 0
    private_queue = []
    with (directory / 'per_question_private.jsonl').open() as source:
        traces = [json.loads(line) for line in source]
    assert len(traces) == expected
    for index, (row, old) in enumerate(zip(traces, prior)):
        assert (row['question_id'], row['db_id']) == (old['question_id'], old['db_id'])
        assert set(row) == {'question_id', 'db_id', 'parse_error', 'counts', 'flags'}
        flags = row['flags']
        for flag in flags:
            assert set(flag) == {'literal_sha256', 'literal_kind', 'input_mentions_literal',
                                 'matching_node_retained', 'matching_gold_column', 'matching_node_ids'}
            assert re.fullmatch('[0-9a-f]{64}', flag['literal_sha256'])
            assert flag['literal_kind'] in {'string', 'number'}
            assert flag['matching_node_ids']
            for field in ('input_mentions_literal', 'matching_node_retained', 'matching_gold_column'):
                assert isinstance(flag[field], bool)
        counts = Counter(row['counts'])
        assert counts['questions'] == 1
        assert counts['parsed_queries'] == int(row['parse_error'] is None)
        assert counts['parse_failures'] == int(row['parse_error'] is not None)
        expected_flags = {
            'questions_with_values_exposure': int(bool(flags)),
            'literal_exposures': len(flags),
            'questions_with_exposure_absent_from_question_evidence': int(any(not f['input_mentions_literal'] for f in flags)),
            'questions_with_exposure_on_gold_schema_column': int(any(f['matching_gold_column'] for f in flags)),
            'questions_with_retained_node_exposure': int(any(f['matching_node_retained'] for f in flags)),
        }
        for key, value in expected_flags.items():
            assert counts[key] == value
        totals['all'].update(counts)
        per_db[aliases[row['db_id']]].update(counts)
        assert old['column_eligible'] or not flags
        if old['column_eligible']:
            totals['column_eligible'].update(counts)
            if aliases[row['db_id']] in fixed_aliases:
                totals['fixed_non_saturated'].update(counts)
            a, b = [old['arms'][arm]['budgets']['1024']['complete'] for arm in ('V00', 'V01')]
            category = 'rescued' if b > a else 'damaged' if b < a else 'unchanged'
            strata[category].update(counts)
            absent = [f for f in flags if not f['input_mentions_literal']]
            if absent:
                intersections['absent_input_questions'] += 1
                intersections['absent_input_literals'] += len(absent)
                intersections['absent_input_and_gold_same_flag_questions'] += int(any(f['matching_gold_column'] for f in absent))
                intersections['absent_input_and_retained_same_flag_questions'] += int(any(f['matching_node_retained'] for f in absent))
                private_queue.append({'audit_case': f'VR-{len(private_queue)+1:03d}', 'source_ordinal': index,
                                      'question_id': row['question_id'], 'database_alias': aliases[row['db_id']],
                                      'coverage_stratum': category, 'human_review_status': 'not_reviewed',
                                      'semantic_necessity': None, 'reviewer_notes': ''})
        flag_count += len(flags)
    assert totals == {key: Counter(value) for key, value in aggregate['counts'].items()}
    assert per_db == {key: Counter(value) for key, value in aggregate['per_database_anonymized'].items()}
    assert strata == {key: Counter(value) for key, value in aggregate['coverage_strata'].items()}
    assert aggregate['exposure_denominator'] == totals['column_eligible']['questions']
    assert aggregate['human_reviews'] == 0 and aggregate['model_forwards'] == aggregate['sql_executions'] == 0
    assert not aggregate['parse_error_types']
    if not aggregate['smoke_only']:
        assert (totals['all']['questions'], totals['column_eligible']['questions'], totals['fixed_non_saturated']['questions']) == (1534, 1460, 706)
        assert {name: value['questions'] for name, value in strata.items()} == {'rescued': 162, 'damaged': 2, 'unchanged': 1296}
    public_text = json.dumps(aggregate, ensure_ascii=False)
    assert not any(db in public_text for db in aliases)
    assert not any(key in public_text for key in ('question_id', 'matching_node_ids', 'literal_sha256', '"SQL"', '"question"'))
    result = {'status': 'verified', 'trace_rows': expected, 'literal_flags_recounted': flag_count,
              'all_group_and_alias_counts_exact': True, 'strata_recount_exact': True,
              'persisted_hashes_verified': True, 'public_privacy_scan_passed': True,
              'semantic_review_performed': False, 'priority_queue_size': len(private_queue),
              'intersections': intersections, 'aggregate_sha256': receipt['aggregate_summary_sha256'],
              'private_rows_sha256': receipt['private_rows_sha256']}
    return result, private_queue


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--p2c-run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-queue', type=Path)
    args = parser.parse_args()
    result, queue = verify(args.run_dir, args.p2c_run_dir)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    if args.private_queue:
        with args.private_queue.open('x') as target:
            json.dump(queue, target, indent=2)
            target.write('\n')
    print(json.dumps(result))
