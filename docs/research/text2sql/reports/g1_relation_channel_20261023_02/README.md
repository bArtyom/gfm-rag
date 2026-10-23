# G1 Relation Channel and FK Instance Contract Gate — Run 002

> **Result: formal G1-A NO-GO.** All eight forwards completed and produced finite `[1,5]` outputs. The frozen relation-channel interventions were exactly invariant on this symmetric fixture, so the registered success gate did not pass. This does **not** establish that G-reasoner ignores relation channels in general.

## Research question and registered decision

Does the frozen official G-reasoner checkpoint respond to relation fields consumed by its forward path, while preserving consistent relation-ID relabel invariance and the FK graph structure contract?

The preregistered tolerance was `epsilon = max(1e-6, 10 × max_abs_delta(C0, C0_repeat))`. G1-A passes only if C1 and C4 are within epsilon and at least one of C2/C3 is above epsilon. C5/C6 are only query/anchor sensitivity fingerprints.

## Why this is run 002

Run 001 loaded the same checkpoint and failed on its first C0 forward before producing an output. The graph had been moved to CUDA, then PyG's mutating `Data.cpu()` round-trip check moved that same object back to CPU. The failure and its sanitized result are preserved in the [run 001 report](../g1_relation_channel_20261023_01/README.md) and [result JSON](../g1_relation_channel_20261023_01/result.json); the traceback remains local at `/mnt/liansp3/logs/gfmrag_g1_relation_channel_20261023_01/run_001/run.log`.

Run 002 has a distinct ID and output path. The only implementation correction clones the graph before device transfer, then validates a second clone's CPU round-trip. A regression test checks that the forward graph remains on the requested device and the source graph remains unchanged. The focused contract suite passed **9/9**; the CLI preflight passed. No environment or dependency changed.

## Protocol, code and resources

- Tier: synthetic mechanism/compatibility gate; exploratory, not downstream SQL main-line evidence.
- Seed `20261023`; 5 nodes, 8 directed edges, 6 relation IDs; two parallel FK roles and one ordered two-component FK with inverse edges.
- One model load, exactly 8 forwards, zero training epochs, one RTX 4090, 15-minute hard timeout. No BIRD, Gold SQL, SQL execution, API call, download, or dependency installation.
- Owned repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/g1-relation-channel-20261023`. Run 002 was preregistered in commit `17ac0d021b7297a55210d5016fd1a22d078a8833`; the runner blob is `9b63db0c5d1886841413c035ee74d66eee6b191d` and its SHA256 is `684c1fc727b51e9b5bee1e84340dfd9c3bff217286526a0def9cac57e803042e`.
- Experiment guidance and plan: main commit `33e040327fe13df2703c1c96211b87e83250f1be`, [`G1 plan`](../../plans/g1_relation_channel_and_fk_instance_gate_20261023.md). The report, config and result are committed on the research branch; no third-party upstream was modified.
- Upstream source: [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag), commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0. Checkpoint `rmanluo/G-reasoner-34M` at revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`; model SHA256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`; config SHA256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`.
- Environment: `gfmrag_greasoner_20261022`, Python 3.12.15, PyTorch 2.8.0+cu128 / CUDA 12.8, PyG 2.6.1, Ninja 1.11.1.4; existing RSPMM extension cache. Pre-run check at 2026-10-23 06:44 UTC showed physical GPU 1 at 0% utilization with 22,397 MiB available, 432 GiB available RAM, and 192 CPU cores. A final check at 06:46 UTC showed GPU memory unchanged and 430 GiB available RAM. Peak process GPU memory was not sampled.
- Runner-measured elapsed time, including model load and all forwards: `1.7147 s`. No separate kernel-only GPU duration was recorded.
- Exact launch command, all C0–C6 definitions, limits, and result paths are in [`experiment_config.json`](experiment_config.json).

## Results

G0 fixture SHA matched exactly: `0ffaa88fbe41a4026bbc8b7263cbbdee1b432c9651a6bc3824a705890bd593f2`. All eight graph device round-trips passed. Outputs were finite and shaped `[1,5]`. The repeated baseline had zero difference, so `epsilon = 1e-6`.

| Case | Max absolute delta vs C0 | Mean absolute delta | Top-1 same | Interpretation |
|---|---:|---:|---|---|
| C1 metadata negative control | 0.000000 | 0.000000 | yes | Expected negative control; passes. |
| C2 paired `edge_type` role switch | 0.000000 | 0.000000 | yes | No output change on this fixture. |
| C3 `rel_attr` row permutation | 0.000000 | 0.000000 | yes | No output change on this fixture. |
| C4 consistent relation-ID and feature relabel | 0.000000 | 0.000000 | yes | Expected semantic relabel invariance; passes. |
| C5 start-node mask change | 30.975285 | 9.959518 | yes | Anchor changes scores; top-1 remains the same. |
| C6 normalized query change | 8.307732 | 5.366384 | no | Query changes scores and top-1. |

The raw `[1,5]` scores, all case outputs, environment versions, checkpoint hashes, and deltas are preserved in [`result.json`](result.json) (SHA256 `ce55d5a84fbae298bc19f608f65f072cd505db2025a97246e9195743a762f691`). The local execution log is `/mnt/liansp3/logs/gfmrag_g1_relation_channel_20261023_01/run_002/run.log` (SHA256 `8d442e3c383c9596c519e1baa8d0c0a5231c1de730b6edc34d05920db5fafb98`).

## Interpretation and next decision

The registered gate is **NO-GO** because both C2 and C3 have zero delta. Source inspection confirms the official forward path computes relation representations from `graph.rel_attr`, passes them into QueryNBFNet, indexes them by `edge_type`, and aggregates messages by destination with permutation-invariant reductions.

The fixture makes the two direct role edges share the exact same source and target (`0 → 1`), and their inverse edges likewise share endpoints (`1 → 0`). C2 only swaps relation IDs across those parallel edges; C3 only swaps the corresponding relation feature rows. Each intervention therefore preserves the multiset of messages entering each endpoint. Under the model's order-independent aggregation, exact output invariance is expected even when the relation channel is consumed. The zero deltas are thus **uninformative about general relation-channel use**; they are not evidence that `edge_type` or `rel_attr` is globally ignored.

C5/C6 show this checkpoint responds to the anchor and query on the synthetic fixture. They do not establish SQL-aware reasoning, FK-role accuracy, or downstream SQL improvement. No SQL, real schema, or human label was evaluated.

**Stop further G1 model or training runs for this fixture.** The next action is a read-only implementation/design audit to define a symmetry-breaking synthetic intervention (for example, distinct neighborhoods or a downstream target that separates the paired roles) while preserving FK-instance and inverse-edge semantics. Any new forward experiment requires a fresh preregistration and a fixture whose relation intervention changes the aggregated message multiset.

## Real FK label gate status

No new CPU FK-label replay or private review queue was created in this G1 turn. The archived P2a.5 structure audit reports 103 raw SQLite FK instances (100 valid, 3 invalid); among 1,428 Gold `JOIN ON` clauses, 1,199 uniquely matched a declared FK, 25 had multiple matches, and 204 were unmatched; 197 queries had multi-FK table-pair candidates. These counts describe structure matching, not business-role labels. The archived report records no human blind review; `human_review=0` and `trusted_role_label_n=0` remain the status. See the [P2a.5 FK audit](../p2a_5_error_audit_20261018_01/README.md).
