"""Prepare evaluation-only metadata after the blind mapping is frozen.

The selected task manifest and output metadata contain private IDs/labels. The
script verifies the frozen mapping hash before reading task labels or SQL.
"""
import argparse
import hashlib
import json
from pathlib import Path


def read_json(path):
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--selection-manifest', type=Path, required=True)
    parser.add_argument('--frozen-mapping', type=Path, required=True)
    parser.add_argument('--expected-mapping-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    actual = hashlib.sha256(args.frozen_mapping.read_bytes()).hexdigest()
    if actual != args.expected_mapping_sha256:
        raise ValueError('Frozen mapping hash does not match the registered amendment')
    tasks = read_json(args.dataset_root / 'BIRD-Ent.json')
    manifest = read_json(args.selection_manifest)
    rows = []
    for index, selected in enumerate(manifest, 1):
        task = tasks[selected['source_order']]
        if task.get('question_id') != selected['question_id']:
            raise ValueError('Private sample manifest no longer matches pinned task order')
        rows.append({
            'case_ref': 'C%02d' % index,
            'source_order': selected['source_order'],
            'question_id': task['question_id'],
            'data_asset': task['data_asset'],
            'eval_db': task['eval_db'],
            'gold_table_ids': task['gold_table_ids'],
            'gold_knowledge_ids': task['gold_knowledge_ids'],
            'sql_characters': len(task['original_SQL']),
        })
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({
        'case_count': len(rows),
        'distinct_data_assets': len({row['data_asset'] for row in rows}),
        'gold_table_labels': sum(len(row['gold_table_ids']) for row in rows),
        'mapping_sha256_verified': actual,
        'private_scoring_metadata': str(args.output),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
