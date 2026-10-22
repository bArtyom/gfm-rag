# G0 synthetic graph compatibility — recovery attempt 02

Status: preregistered; execution pending.

## Reason for a separate attempt

Attempt 01 loaded the pinned checkpoint and passed its synthetic graph and metadata-transfer assertions, then stopped before model message passing because the launcher did not activate the Conda environment. The required Ninja 1.11.1.4 executable was already installed in that environment. This attempt has a new ID because attempt 01 is frozen as a failed launch and its stop rule prohibits retrying under the same ID.

## Question, hypothesis, and fixed scope

Use the same G0 engineering hypothesis as attempt 01: the official G-reasoner-34M checkpoint accepts the synthetic five-node, eight-directed-edge multigraph with 1024-dimensional node and relation features and returns one finite score per node.

The separate mechanism check perturbs only edge_attr and custom FK-instance fields. Source inspection predicts that the checkpoint path ignores those fields. This is an interface/mechanism feasibility gate only; it cannot establish JOIN accuracy, retrieval quality, or SQL performance.

All model, checkpoint, fixture construction, seed, success gates, and forward-pass budget remain unchanged from attempt 01. The only implementation/launch difference is that the same isolated Conda environment is activated with conda run so its installed Ninja executable is available on PATH. No package installation, update, or environment recreation is planned.

## Layer, budget, criteria, and stop rule

- Layer: one recovery run for the synthetic/interface feasibility gate.
- Budget: one checkpoint load, one five-node/eight-edge fixture, two forward passes total, one GPU, seed 20261023, and at most 15 minutes.
- G0-A: verify the pinned checkpoint's 1024 input dimensions and 34,640,897 parameters; output shape [1,5] and all values finite.
- G0-B: preserve the two parallel relation roles, ordered composite-FK components, inverse-edge pairing, and metadata across device transfer.
- G0-C: record exact equality and maximum absolute output difference after metadata-only perturbation; delta <= 1e-6 counts as unchanged.
- Stop after this one run. Preserve any build, shape, non-finite, or integrity failure without a retry under attempt 02.
- If A/B pass and C is unchanged, conclude only that the interface executes while this checkpoint path ignores the tested FK-instance metadata. Do not claim role reasoning.

## Frozen provenance

- Own repository and required guidance: bArtyom/gfm-rag, current G0 branch after attempt 01 report and recovery preregistration; prior guidance base aa2d21ac710edfe098ac752970571c084ad84731.
- Official source: RManLuo/gfm-rag commit b3e43219c49929da505244df4f0ba54c0947e4c4, Apache-2.0.
- Checkpoint: rmanluo/G-reasoner-34M revision a3a4ed2c62281e1c3e0551bd42f2072d9204674f, Apache-2.0.
- Environment: gfmrag_greasoner_20261022, Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1, installed Ninja 1.11.1.4; no environment changes from attempt 01.
- Runner: scripts/text2sql/g0_synthetic_graph_compat_20261023_02.py; identical to attempt 01 except for its run ID.
- Local synthetic input and logs remain private; no BIRD, Gold, SQL, model API, or training.

## Launch and artifacts

Run from /mnt/liansp3 using the registered environment:

    CUDA_VISIBLE_DEVICES=2 /root/miniconda3/bin/conda run -n gfmrag_greasoner_20261022 --no-capture-output python /mnt/liansp3/ai_temp_code/gfmrag_g0_synthetic_graph_compat_20261023_02.py --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --output /mnt/liansp3/sources/results/gfmrag_g0_synthetic_graph_compat_20261023_02/g0_result.json --device cuda

- Local result: /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/g0_synthetic_graph_compat_20261023_02
- Local logs: /mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_02
- Public report: docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_02/

## Reporting boundary

Record only the interface result, shapes, finite values, metadata preservation/sensitivity, hashes, runtime, and resources. Never treat random synthetic scores as rankings or benchmark results.
