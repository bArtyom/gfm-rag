# G0 synthetic graph compatibility — attempt 03

Status: preregistered; execution pending.

## Why this attempt has a new ID

Attempt 01 reached checkpoint loading and fixture transfer, then stopped because direct interpreter invocation did not put the installed Ninja executable on PATH. Attempt 02 stopped before loading any code because the executed command referenced a nonexistent script path. Both attempts are preserved as failed launches and will not be retried under their IDs.

Attempt 03 is the only remaining bounded run in this recovery sequence. Its command will be reviewed against this manifest and the actual file path before execution. If the runner or checkpoint does not load correctly, stop and archive the failure; do not create another retry.

## Research question and hypothesis

Can the pinned official G-reasoner-34M checkpoint execute the fixed five-node, eight-directed-edge synthetic multigraph with 1024-dimensional node and relation features and return finite per-node outputs?

The mechanism check perturbs only edge_attr and custom FK-instance fields. Source inspection predicts those fields are not read by the current model path. Even a successful run establishes only interface feasibility, not JOIN accuracy, retrieval quality, or SQL performance.

## Frozen budget and gates

- Layer: bounded synthetic/interface feasibility gate.
- One model load, one fixed synthetic fixture, one baseline forward, one metadata-perturbed forward, one GPU, seed 20261023, maximum 15 minutes.
- G0-A: pinned checkpoint input/feature dimensions 1024, 34,640,897 parameters, output shape [1,5], all values finite.
- G0-B: preserve two parallel relation roles, two ordered composite-FK components, inverse-edge pairing, edge count and metadata across device transfer.
- G0-C: record exact output equality and maximum absolute difference after metadata-only perturbation; delta <= 1e-6 counts as unchanged.
- No BIRD, Gold labels, business data, SQL, training, model API, dependency changes, tuning, or further retries.
- Stop after this one attempt, regardless of outcome.

## Inputs and implementation

- Own-repository branch: research/g0-synthetic-compat-20261023; latest published commit before this plan: b2fdfba90f4b62b33ef8540fd1e02aee5e64936c.
- Official code: RManLuo/gfm-rag commit b3e43219c49929da505244df4f0ba54c0947e4c4, Apache-2.0.
- Checkpoint: rmanluo/G-reasoner-34M revision a3a4ed2c62281e1c3e0551bd42f2072d9204674f, Apache-2.0.
- Environment: gfmrag_greasoner_20261022, Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1; Ninja 1.11.1.4 already installed. Activate via conda run. No package changes.
- Fixture and seed are unchanged from attempt 01.
- Runner: scripts/text2sql/g0_synthetic_graph_compat_20261023_03.py, identical to attempt 02 except the run ID.

## Exact launch command

Run in /mnt/liansp3. Use this exact command after reviewing the path against the registered runner:

    CUDA_VISIBLE_DEVICES=2 /root/miniconda3/bin/conda run -n gfmrag_greasoner_20261022 --no-capture-output python /mnt/liansp3/ai_temp_code/gfmrag_g0_synthetic_graph_compat_20261023_03.py --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --output /mnt/liansp3/sources/results/gfmrag_g0_synthetic_graph_compat_20261023_03/g0_result.json --device cuda > /mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_03/stdout.log 2> /mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_03/stderr.log

The output path and runner path both include attempt 03. The exact command, preflight, versions, hashes, and logs will be recorded in the local launch manifest.

## Artifact paths

- Local result: /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/g0_synthetic_graph_compat_20261023_03
- Local log: /mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_03
- Public report: docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_03/

## Interpretation boundary

Synthetic outputs are not rankings or quality scores. A finite forward pass does not show that the checkpoint uses FK-instance metadata. The report will separate load/interface gates from metadata sensitivity and state that no JOIN or SQL metric was measured.
