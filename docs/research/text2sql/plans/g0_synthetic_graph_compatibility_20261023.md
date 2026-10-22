# G0 synthetic graph compatibility gate — 2026-10-23

Status: preregistered; execution pending.

## Research question

Can the pinned official G-reasoner-34M checkpoint execute one small, synthetic schema-like PyG graph with its configured 1024-dimensional node/relation features, while preserving distinct FK-instance and composite-key metadata in the input object?

## Hypothesis and scope

H-G0-I (engineering feasibility): the official checkpoint accepts a five-node, eight-directed-edge synthetic multigraph and returns one finite score per node when given 1024-dimensional node features, relation features, and a query embedding.

The companion mechanism check is intentionally stricter: the input object can preserve FK-instance IDs and ordered composite-key component fields, but the pinned model may ignore those fields. The source audit predicts that it does: GraphReasoner reads graph.x and graph.rel_attr; QueryNBFNet message passing reads edge_index and edge_type. It does not read edge_attr or custom FK-instance metadata.

This is an exploratory engineering gate, not evidence of JOIN accuracy, retrieval quality, a new method, or SQL execution performance.

## Layer, budget, success and stop rules

- Layer: standalone synthetic/interface feasibility gate for the graph-method line.
- Budget: one fixed 5-node / 8-edge fixture, six relation embeddings, one pretrained model load, one forward pass, and one paired forward after changing only edge metadata. One GPU, one seed (20261023), at most 15 minutes. No training, tuning, retries, BIRD data, Gold labels, SQL, SQL service, or model API.
- G0-A success: the exact pinned checkpoint loads with 1024 input dimensions and 34,640,897 parameters; the output has shape 1 x 5 and all values are finite.
- G0-B success: both billing/shipping-like parallel relations and both ordered components of one composite FK survive PyG device transfer with their IDs, component indices/counts, inverse flags, and edge count intact.
- G0-C mechanism result: perturb only edge_attr and custom FK-instance fields. Record exact equality and max absolute output delta. Treat outputs as unchanged when the maximum absolute delta is at most 1e-6, allowing minor floating-point reduction noise; source inspection determines whether the fields are read by this path.
- Stop after this single paired run. Preserve and report any load, shape, non-finite, or metadata-integrity failure; do not repair the fixture after seeing a failure and rerun under this ID.
- Overall interpretation is partial interface feasibility only. Even if G0-A/B pass, G0-C equality leaves instance-aware role/path reasoning as unsupported by this checkpoint/input path.

## Frozen inputs and implementation

- Own-repository guidance base: bArtyom/gfm-rag branch research/p2d1-eval-v2-20261022, commit aa2d21ac710edfe098ac752970571c084ad84731.
- Official source code: RManLuo/gfm-rag, commit b3e43219c49929da505244df4f0ba54c0947e4c4, Apache-2.0.
- Checkpoint: rmanluo/G-reasoner-34M, revision a3a4ed2c62281e1c3e0551bd42f2072d9204674f, Apache-2.0; local source is the registered g-reasoner-34m alias.
- Fixture: five abstract nodes; two distinct directed relation types over the same endpoint pair; a two-component composite relation over another pair; inverse edges; six relation IDs total. Vectors are deterministic, synthetic, and generated from seed 20261023.
- Runtime: isolated gfmrag_greasoner_20261022 environment; Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1. Planned device: one currently available RTX 4090, rechecked immediately before launch.
- Public runner: scripts/text2sql/g0_synthetic_graph_compat_20261023.py. Local execution copy: /mnt/liansp3/ai_temp_code/gfmrag_g0_synthetic_graph_compat_20261023.py.
- No upstream model code is modified.

## Commands and records

Run from /mnt/liansp3 with the registered environment's Python executable, CUDA_VISIBLE_DEVICES selecting the chosen physical GPU, and the public runner's required checkpoint and output arguments. The exact command, resource snapshot, stdout/stderr, and private result JSON will be recorded in the local run manifest.

- Local result: /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/g0_synthetic_graph_compat_20261023_01
- Local log: /mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_01
- Public report: docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_01/

## Reporting boundary

Report only model-load status, tensor dimensions, finite-output/shape checks, metadata round-trip integrity, paired-output difference, runtime/resources, hashes, and source-level consumption findings. Do not interpret random synthetic scores as rankings or quality measurements. Do not report JOIN accuracy, SQL EX, model/API token use, or a method gain.
