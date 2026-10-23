# G1 Relation Channel and FK Instance Contract Gate — Recovery Run 002

> **Status: PREREGISTERED — NOT RUN.** This independent recovery run uses the same frozen scientific protocol as run 001, with a minimal correction to the graph device-round-trip check. No model output is included yet.

## Why a new run ID

The prior run [`g1_relation_channel_20261023_01`](../g1_relation_channel_20261023_01/README.md) loaded the checkpoint, attempted its first C0 forward, and failed before producing a valid output. PyG `Data.to()` and `Data.cpu()` mutate the receiving graph; the round-trip check returned the same inference graph to CPU. Run 001 is terminal and its failure record remains unchanged. Run 002 was created with its own output/log paths and a new pre-run registration.

The only code correction clones the graph before moving it to the target device, then uses a second clone for CPU round-trip verification. A regression test checks that the forward graph remains on the requested device and the source graph stays unchanged. The focused suite passes 9/9. No dependency or environment was changed.

## Research question and frozen decision rule

Does the frozen official G-reasoner checkpoint respond to relation fields consumed by its forward path, while preserving consistent relation-ID relabel invariance and the FK graph structure contract?

Define `epsilon = max(1e-6, 10 × max_abs_delta(C0, C0_repeat))`. Pass only if C1 and C4 are within epsilon and at least one of C2/C3 exceeds epsilon. If C4 fails, stop. C5/C6 are anchor/query sensitivity fingerprints only, not evidence of SQL-aware reasoning.

## Scope and budget

- Synthetic mechanism/compatibility gate; exploratory, not downstream SQL main-line evidence.
- Same fixture SHA as G0: `0ffaa88fbe41a4026bbc8b7263cbbdee1b432c9651a6bc3824a705890bd593f2` (5 nodes, 8 directed edges, 6 relation IDs).
- Fixed seed `20261023`; one model load; exactly 8 forwards; one RTX 4090; 15-minute ceiling; zero training epochs; one execution, no retry under this ID.
- No BIRD, Gold SQL, SQL execution, model API, model download, or dependency installation.
- The six interventions remain C1 metadata negative control, C2 edge-type role switch, C3 relation-feature permutation, C4 consistent semantic relabel, C5 anchor change, and C6 normalized query change; C0 is repeated twice.

## Source and guide pins

- Owned project/report repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/g1-relation-channel-20261023`.
- Parent preregistration commit: `2fba950459ef833c2def4d48f199b8e6c69c71fe`; this run's code/config/report are being preregistered in the following commit before model execution.
- Governing plan: [`g1_relation_channel_and_fk_instance_gate_20261023.md`](../../plans/g1_relation_channel_and_fk_instance_gate_20261023.md); experiment guidance was read from main commit `33e040327fe13df2703c1c96211b87e83250f1be`.
- Upstream code: [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag), commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0. Checkpoint `rmanluo/G-reasoner-34M` at revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`; weights SHA256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`.

## Environment and reproducibility

Use the existing `gfmrag_greasoner_20261022` environment (Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1, Ninja 1.11.1.4), cached RSPMM extension, checkpoint alias `/mnt/liansp3/sources/models/g-reasoner-34m`, and physical GPU 1. The 2026-10-23 06:44 UTC preflight (the `nvidia-smi` timestamp is host-local UTC+08) showed 0% GPU utilization and 22,397 MiB available, with 432 GiB available RAM and 192 CPU cores. No install, download, training, or external model/API use. The exact bounded launch command and pre-run resource snapshot are in [`experiment_config.json`](experiment_config.json). Raw traceback for run 001 remains local at its registered log path.

## Results

**NOT RUN.** This section is reserved for the single preregistered run 002 and will be updated after execution.
