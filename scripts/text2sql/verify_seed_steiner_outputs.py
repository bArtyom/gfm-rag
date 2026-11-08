"""Read-only postconditions on frozen predictions; never reruns scoring."""
import argparse
import json
from pathlib import Path

import networkx as nx

from run_seed_steiner import read_config, sha256, verify_database_hashes, write_json
from seed_steiner import read_constraints, verify_seed_connectivity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    config = read_config(args.config)
    schemas = {s['db_id']: s for s in json.loads((Path(config['dataset_root']) / 'dev_tables.json').read_text())}
    db_paths = {db: Path(config['database_root']) / db / (db + '.sqlite') for db in schemas}
    verify_database_hashes(config['database_sha256'], {db: sha256(p) for db, p in db_paths.items()})
    graphs = {}
    for db, schema in schemas.items():
        graph = nx.Graph()
        graph.add_nodes_from(range(len(schema['table_names_original'])))
        for c in read_constraints(schema, db_paths[db]):
            graph.add_edge(c['source_table'], c['target_table'])
        graphs[db] = graph
    prediction_path = args.run / 'private_predictions.jsonl'
    seal = json.loads((args.run / 'prediction_seal.json').read_text())
    assert sha256(prediction_path) == seal['sha256']
    count = 0
    with prediction_path.open() as stream:
        for row in map(json.loads, stream):
            selected = row['arms']['seed_steiner']
            assert set(row['seeds']) <= set(selected)
            assert len(selected) == len(row['arms']['dense_size_matched'])
            verify_seed_connectivity(graphs[row['db_id']], row['seeds'], selected)
            count += 1
    assert count == seal['rows']
    result = {'status': 'pass', 'questions_checked': count, 'prediction_sha256': seal['sha256'],
              'seed_retention': True, 'connectable_components_connected': True,
              'table_count_parity': True, 'frozen_database_hashes_verified': True,
              'predictions_changed': False, 'new_model_calls': 0}
    write_json(args.run / 'postcondition_verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
