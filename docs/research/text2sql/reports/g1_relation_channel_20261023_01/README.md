# G1 Relation Channel and FK Instance Contract Gate

> **Status: PREREGISTERED — NOT RUN.** This is a synthetic mechanism and compatibility gate, not a SQL accuracy experiment. No G1 model outputs are included yet.

## Research question and hypothesis

Does the frozen official G-reasoner checkpoint respond to relation fields consumed by its forward path, while preserving consistent relation-ID relabel invariance and the FK graph structure contract?

The primary gate passes only when C1 (metadata negative control) and C4 (consistent relation-ID relabel) stay within the frozen numerical tolerance, and at least one of C2 (`edge_type`) or C3 (`rel_attr`) changes the output beyond that tolerance. Define `epsilon = max(1e-6, 10 × max_abs_delta(C0, C0_repeat))`. C5/C6 are reported only as anchor/query sensitivity fingerprints.

## Scope and budget

- Tier: synthetic mechanism/compatibility gate; exploratory and not downstream SQL main-line evidence.
- Fixed seed: `20261023`; one checkpoint load; exactly eight forwards; one RTX 4090; 15-minute ceiling; no training.
- Synthetic graph: 5 nodes, 8 directed edges, 6 relation IDs, two parallel FK roles, one two-component FK with inverse edges.
- No BIRD, Gold SQL, SQL execution, model API, model download, or dependency installation.
- STOP on checkpoint/fixture mismatch, invalid graph contract, non-finite output, C4 invariance failure, resource overrun, or execution error. Do not retry this run ID.

## Source and guidance pins

- Owned report repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/g1-relation-channel-20261023`, based on `33e040327fe13df2703c1c96211b87e83250f1be`.
- Experiment plan: [`g1_relation_channel_and_fk_instance_gate_20261023.md`](../../plans/g1_relation_channel_and_fk_instance_gate_20261023.md).
- Upstream implementation: [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag), commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0. Original checkpoint `rmanluo/G-reasoner-34M`, revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`.
- G0 fixture and result source: owned branch `research/g0-synthetic-compat-20261023` at `7152ab2a75e1bada1bc4d8280728878cbaf73726`; G0 runner blob `d8849d55d6783d8a3eee79404710a77bf1bfae70`; G0 report blob `b13c10ff6a3f04cb1c6fcde56fc9d42fc1c40962`; G0 result blob `1b9b4cefec1232b03e5712d76dcb702c3627b656`. The G1 fixture bundle must remain SHA256 `0ffaa88fbe41a4026bbc8b7263cbbdee1b432c9651a6bc3824a705890bd593f2`.
- The repository's root README, Text2SQL README, experiment roadmap, reproducibility contract, and G1 plan were reviewed at the pinned base commit. No guidance deviation is planned.

## Cases

| Case | Change |
|---|---|
| C0, C0 repeat | Same graph, query, anchor; repeat measures numerical noise. |
| C1 | Change `edge_attr` and bijectively relabel FK-instance IDs; preserve consumed inputs and valid FK structure. |
| C2 | Swap paired forward/inverse role relation IDs; leave relation features fixed. |
| C3 | Permute paired relation-feature rows; leave relation IDs fixed. |
| C4 | Apply the same relation-ID and feature-row permutation; edge-to-feature semantics stay constant. |
| C5 | Change only the start-node mask. |
| C6 | Change only the normalized query embedding. |

## Environment, hardware and command

Use the existing `gfmrag_greasoner_20261022` Conda environment (Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1, Ninja 1.11.1.4), the existing RSPMM extension cache `/root/.cache/torch_extensions/py312_cu128/rspmm/rspmm.so`, local checkpoint alias `/mnt/liansp3/sources/models/g-reasoner-34m`, and physical GPU 1. At preflight, GPU 1 had 0% utilization and 22,397 MiB available. A stale inherited Python 3.9 path was found before the successful test run; no package was installed or changed. Eight focused CPU contract tests pass, including fixture SHA, all cases, inverse/composite structure, negative and role controls, query/anchor isolation, and copy/device round-trip. The execution command clears that inherited path before activating the registered environment:

```bash
timeout --signal=INT --kill-after=10s 900s \
  env -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u CONDA_SHLVL -u CONDA_PREFIX_1 \
  PATH=/usr/bin:/bin CUDA_VISIBLE_DEVICES=1 \
  /root/miniconda3/bin/conda run -n gfmrag_greasoner_20261022 \
  python scripts/text2sql/g1_relation_channel_probe.py \
    --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m \
    --device cuda:0 --run-id g1_relation_channel_20261023_01 \
    --output /mnt/liansp3/sources/results/gfmrag_g1_relation_channel_20261023_01/run_001/result.json
```

Targeted structure tests: `python -m unittest discover -s tests -p 'test_g1_relation_channel_probe.py' -v` in the same cleaned Conda environment. Result JSON and execution log are kept at the local paths in `experiment_config.json`; only synthetic outputs and aggregate runtime metadata are published.

## Results

**NOT RUN.** This section will be replaced only after the single preregistered execution. No result or model sensitivity claim is available at preregistration time.
