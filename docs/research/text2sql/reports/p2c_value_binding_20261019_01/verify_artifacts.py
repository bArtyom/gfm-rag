"""Recount persisted AST-binding categories and verify frozen source artifacts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def verify(run_dir):
    receipt = json.loads((run_dir / 'run_start.json').read_text())
    aggregate = json.loads((run_dir / 'aggregate_summary.json').read_text())
    assert receipt['state'] == 'completed'
    assert digest(run_dir / 'aggregate_summary.json') == receipt['aggregate_summary_sha256']
    assert digest(run_dir / 'per_case_private.jsonl') == receipt['private_rows_sha256']
    assert receipt['source']['published_commit'] == aggregate['source_commit']
    for name, expected in receipt['source']['execution_sources'].items():
        assert digest(Path.cwd() / name) == expected
    parent = Path('/mnt/liansp3/sources/results/gfmrag_p2c_values_risk_20261019/full_1534_20261019_01')
    inputs = receipt['input_hashes']
    for name, filename in (('lexical_private_rows', 'per_question_private.jsonl'),
                           ('lexical_aggregate', 'aggregate_summary.json'), ('priority_queue', 'human_review_priority_private.json')):
        assert digest(parent / filename) == inputs[name]
    original_queue = json.loads((parent / 'human_review_priority_private.json').read_text())
    expected_queue = original_queue[:5] if aggregate['smoke_only'] else original_queue
    with (parent / 'per_question_private.jsonl').open() as source:
        lexical = {row['question_id']: row for row in map(json.loads, source)}
    with (run_dir / 'per_case_private.jsonl').open() as source:
        rows = list(map(json.loads, source))
    assert len(rows) == len(expected_queue)
    totals, per_db, strata, reasons = Counter(), {}, {}, Counter()
    for row, original in zip(rows, expected_queue):
        assert (row['audit_case'], row['question_id'], row['database_alias'], row['coverage_stratum']) == (
            original['audit_case'], original['question_id'], original['database_alias'], original['coverage_stratum'])
        old = {flag['literal_sha256']: flag for flag in lexical[row['question_id']]['flags'] if not flag['input_mentions_literal']}
        assert set(old) == {flag['literal_sha256'] for flag in row['flags']}
        counts = Counter(questions=1, literal_flags=len(row['flags']))
        for flag in row['flags']:
            assert re.fullmatch('[0-9a-f]{64}', flag['literal_sha256'])
            assert flag['matching_values_node_ids'] == old[flag['literal_sha256']]['matching_node_ids']
            bound = flag['binding']
            overlap = sorted(set(bound['node_ids']) & set(flag['matching_values_node_ids']))
            assert overlap == flag['supported_node_ids']
            expected = 'binding_supported' if overlap else 'binding_unresolved' if bound['unresolved_reasons'] or not bound['node_ids'] else 'binding_mismatch'
            assert flag['category'] == expected
            assert bound['occurrences'] >= 1
            counts[expected] += 1
            counts['supported_flags_with_other_unresolved_occurrences'] += int(expected == 'binding_supported' and bool(bound['unresolved_reasons']))
            reasons.update(bound['unresolved_reasons'])
        case_kind = 'supported_questions' if counts['binding_supported'] else 'unresolved_questions' if counts['binding_unresolved'] else 'mismatch_questions'
        counts[case_kind] = 1
        assert counts == Counter(row['counts'])
        totals.update(counts)
        per_db.setdefault(row['database_alias'], Counter()).update(counts)
        strata.setdefault(row['coverage_stratum'], Counter()).update(counts)
    assert totals == Counter(aggregate['counts'])
    assert per_db == {key: Counter(value) for key, value in aggregate['per_database_anonymized'].items()}
    assert strata == {key: Counter(value) for key, value in aggregate['coverage_strata'].items()}
    assert reasons == Counter(aggregate['unresolved_reason_flag_counts'])
    if not aggregate['smoke_only']:
        assert (totals['questions'], totals['literal_flags']) == (19, 21)
    assert sum(totals[name] for name in ('binding_supported', 'binding_mismatch', 'binding_unresolved')) == totals['literal_flags']
    assert sum(totals[name] for name in ('supported_questions', 'mismatch_questions', 'unresolved_questions')) == totals['questions']
    assert aggregate['human_reviews'] == aggregate['semantic_necessity_denominator'] == 0
    text = json.dumps(aggregate)
    assert not any(name in text for name in ('"question_id"', 'literal_sha256', 'supported_node_ids', 'matching_values_node_ids', '"SQL"'))
    databases = {row['db_id'] for row in lexical.values()}
    assert not any(db in text for db in databases)
    return {'status': 'verified', 'trace_rows': len(rows), 'literal_flags_recounted': totals['literal_flags'],
            'partition_counts_exact': True, 'prior_flags_and_identity_exact': True,
            'source_hashes_and_prior_artifact_hashes_verified': True, 'public_privacy_scan_passed': True,
            'aggregate_sha256': receipt['aggregate_summary_sha256'], 'private_rows_sha256': receipt['private_rows_sha256'],
            'semantic_review_performed': False, 'verification_boundary': 'Recounts stored bindings; does not independently prove lineage semantics or necessity'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run_dir)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result))
