"""Select the preregistered first eligible task per distinct data asset.

The output manifest contains identifiers and gold knowledge-document IDs, so
write it only to a private local results directory. This script does not read
or print question text or reference SQL.
"""
import argparse
import json
from pathlib import Path


def read_json(path):
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True, help='Path containing BIRD-Ent.json and the companion JSON assets')
    parser.add_argument('--output', type=Path, required=True, help='New private output manifest path')
    parser.add_argument('--max-tasks', type=int, default=5)
    args = parser.parse_args()
    tasks = read_json(args.dataset_root / 'BIRD-Ent.json')
    assets = read_json(args.dataset_root / 'data_assets.json')
    docs = read_json(args.dataset_root / 'knowledge_documents.json')
    selected, seen_assets = [], set()
    for source_order, task in enumerate(tasks):
        asset_id = task.get('data_asset')
        doc_ids = task.get('gold_knowledge_ids')
        if not asset_id or not isinstance(doc_ids, list) or not doc_ids or asset_id in seen_assets:
            continue
        schema = assets.get(asset_id)
        if not isinstance(schema, dict) or not schema:
            raise ValueError('Selected task references a missing or invalid data asset')
        missing = [str(doc_id) for doc_id in doc_ids if str(doc_id) not in docs]
        if missing:
            raise ValueError('Selected task references missing knowledge documents')
        selected.append({
            'source_order': source_order,
            'question_id': task.get('question_id'),
            'data_asset': asset_id,
            'gold_knowledge_ids': doc_ids,
            'schema_table_count': len(schema),
            'linked_document_char_lengths': [len(docs[str(doc_id)]) for doc_id in doc_ids],
        })
        seen_assets.add(asset_id)
        if len(selected) == args.max_tasks:
            break
    if len(selected) != args.max_tasks:
        raise ValueError('Could not reach the preregistered sample count')
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(selected, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({
        'selected_tasks': len(selected),
        'distinct_data_assets': len(seen_assets),
        'linked_documents_total': sum(len(row['gold_knowledge_ids']) for row in selected),
        'private_manifest': str(args.output),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
