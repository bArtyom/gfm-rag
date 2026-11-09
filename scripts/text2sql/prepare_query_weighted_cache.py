"""Encode only fixed FK descriptions locally; retain no labels in relation cache."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
from run_seed_steiner import load_inputs, new_output, read_config, sha256, write_json
from query_weighted_steiner import relation_descriptor

QUERY_PREFIX = 'Instruct: Given a natural-language question about a database, retrieve the relevant tables and columns.\nQuery: '


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    new_output(args.output)
    started = time.monotonic()
    config = read_config(args.config)
    if config['cpu_backend'] != 'transformers-fp32-last-token':
        raise ValueError('Backend differs from frozen configuration')
    model_path = Path(config['embedding_model'])
    for name, expected in {**config['embedding_support_sha256'], 'model.safetensors': config['embedding_weight_sha256']}.items():
        if sha256(model_path / name) != expected:
            raise ValueError('Model identity mismatch: ' + name)
    for name, key in [('input_manifest_private.json', 'cache_source_receipt_sha256'), ('per_question_private.jsonl', 'cache_identity_receipt_sha256')]:
        if sha256(Path(config['cache_root']) / name) != config[key]:
            raise ValueError('Cache receipt mismatch')
    inputs = load_inputs(config)
    records = [{'db_id': db, 'constraint': c, 'text': relation_descriptor(inputs['schemas'][db], c)}
               for db in sorted(inputs['schemas']) for c in inputs['constraints'][db]]
    if not records or len(records) > config['max_relations']:
        raise ValueError('Relation count exceeds budget')
    # Five deterministic queries, one per database where possible; no SQL used.
    probe = []
    for db in sorted(inputs['schemas'])[:5]:
        probe.append(next(i for i, q in enumerate(inputs['questions']) if q['db_id'] == db))
    texts = [r['text'] for r in records]
    query_texts = [QUERY_PREFIX + inputs['questions'][i]['question'] for i in probe]
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(config['threads'])
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, padding_side='left')
    lengths = [len(tokenizer.encode(t)) for t in texts + query_texts]
    if max(lengths) > config['embedding_max_length'] or sum(lengths) > config['max_new_embedding_tokens']:
        raise ValueError('Token budget exceeded; truncation is forbidden')
    spec = importlib.util.spec_from_file_location('weighted_usage', config['ledger_module'])
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    requests, tokens = 0, 0
    write_json(args.output / 'run_start.json', {'config_sha256': sha256(args.config),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'command': sys.argv, 'python': sys.version, 'executable': sys.executable,
        'timestamp_UTC': datetime.now(timezone.utc).isoformat(), 'model_weight_sha256': config['embedding_weight_sha256'],
        'dependencies': {p: importlib.metadata.version(p) for p in ['torch', 'transformers', 'numpy']},
        'backend': config['cpu_backend'], 'pooling': 'last-nonpadding-token; L2; full1024D',
        'resources': {c: subprocess.check_output(c.split(), text=True) for c in ['nvidia-smi', 'free -h', 'nproc']},
        'planned_texts': len(lengths), 'planned_input_tokens': sum(lengths)})
    model = AutoModel.from_pretrained(str(model_path), local_files_only=True,
                                      torch_dtype=torch.float32, attn_implementation='sdpa').eval().to('cpu')

    def encode(batch):
        nonlocal requests, tokens
        if time.monotonic() - started > config['max_wall_seconds']:
            raise RuntimeError('Encoding wall budget exceeded')
        encoded = tokenizer(batch, padding=True, truncation=False, return_tensors='pt')
        count = int(encoded['attention_mask'].sum().item())
        requests += 1
        call_id = f'{config["run_id"]}:{args.output.resolve().name}:forward:{requests:04d}'
        attempted_at = datetime.now(timezone.utc).isoformat()
        try:
            with torch.inference_mode():
                hidden = model(**encoded).last_hidden_state
                vectors = torch.nn.functional.normalize(hidden[:, -1, :], p=2, dim=1).numpy().copy()
            if vectors.shape != (len(batch), 1024) or not np.isfinite(vectors).all():
                raise RuntimeError('Invalid model output')
        except BaseException:
            ledger.record_request(call_id=call_id, provider='local-transformers-cpu', project='seed-steiner',
                run_id=config['run_id'], model='Qwen3-Embedding-0.6B', http_status=None, usage=None, occurred_at=attempted_at)
            raise
        ledger.record_request(call_id=call_id, provider='local-transformers-cpu', project='seed-steiner',
            run_id=config['run_id'], model='Qwen3-Embedding-0.6B', http_status=None,
            usage={'input_tokens': count, 'output_tokens': 0, 'total_tokens': count}, occurred_at=attempted_at)
        tokens += count
        print(json.dumps({'batch': requests, 'texts': len(batch), 'input_tokens': count}), flush=True)
        return vectors

    first = encode(texts[:5])
    probes = encode(query_texts)
    cosines = np.sum(probes * inputs['queries'][probe], axis=1)
    write_json(args.output / 'embedding_smoke.json', {'relation_texts': len(first),
        'compatibility_probe_queries': len(probe), 'cached_query_cosines': cosines.tolist(),
        'input_tokens_so_far': tokens, 'requests_so_far': requests})
    if float(cosines.min()) < config['query_cosine_gate']:
        raise RuntimeError('Cached query / CPU backend compatibility gate failed')
    parts = [first]
    for i in range(5, len(texts), config['embedding_batch_size']):
        parts.append(encode(texts[i:i + config['embedding_batch_size']]))
    vectors = np.concatenate(parts)
    with (args.output / 'relation_vectors.npz').open('xb') as stream:
        np.savez_compressed(stream, vectors=vectors, probe_vectors=probes, probe_indices=np.array(probe))
    write_json(args.output / 'private_relations.json', records)
    identity = {'config_sha256': sha256(args.config), 'model_weight_sha256': config['embedding_weight_sha256'],
        'model_support_sha256': config['embedding_support_sha256'], 'backend': config['cpu_backend'],
        'pooling': 'left-padding-last-token; L2; full1024D', 'query_prefix': QUERY_PREFIX,
        'relation_template': 'Foreign key relationship: <ordered qualified pairs joined by AND>.',
        'relation_manifest_sha256': sha256(args.output / 'private_relations.json'),
        'relation_vectors_sha256': sha256(args.output / 'relation_vectors.npz'),
        'source_query_cache_sha256': config['cache_sha256']}
    identity['cache_key'] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    write_json(args.output / 'cache_receipt.json', {**identity, 'relations': len(records), 'shape': list(vectors.shape),
        'database_sha256': inputs['database_hashes'], 'new_local_forward_attempts': requests,
        'input_tokens': tokens, 'output_tokens': 0, 'total_tokens': tokens,
        'unknown_usage_requests': 0, 'external_API_cost_CNY': '0.00', 'GPU_seconds': 0,
        'local_CPU_monetized': False, 'wall_seconds': time.monotonic() - started,
        'process_CPU_seconds': time.process_time(), 'peak_RSS_GiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
        'norm_min': float(np.linalg.norm(vectors, axis=1).min()), 'norm_max': float(np.linalg.norm(vectors, axis=1).max()),
        'probe_min_cosine': float(cosines.min()), 'status': 'complete'})
    print(json.dumps({'status': 'complete', 'relations': len(records), 'input_tokens': tokens,
                      'wall_seconds': time.monotonic() - started}), flush=True)


if __name__ == '__main__':
    main()
