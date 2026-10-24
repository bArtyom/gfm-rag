# G0-02 FK instance-node scoring recovery probe

**Status: pre-registered; not run.** Experiment ID: `g0_fk_instance_node_20261024_02`. No model result exists yet.

## Why this is separate from G0-01

G0-01 ended as `IMPLEMENTATION_FAILURE` in its Full permutation control because PyG `Data.to()` moved the source graph in place; the CPU inverse mapping then indexed a CUDA edge tensor. G0-01's launch attempts, smoke result, failure sidecar, and report remain preserved under their original ID. This recovery uses new code identity, run IDs, result root, and budget; it does not reuse or overwrite any G0-01 artifact.

The only intended code correction is to clone `Data` before device transfer. The synthetic schema/questions, seed, model/checkpoint, dense and direct-graph baselines, metrics, pass thresholds, resource limits, and stopping rules remain fixed from the earlier preregistration.

## Pre-registered design

- **Layer:** bounded exploratory synthetic engineering and identifiability recovery.
- **Fixture:** two tables; two ordered FK mappings sharing table endpoints; three declarations with one exact billing duplicate. Identity is SHA-256 of the ordered table/column tuple; counts are billing 2, shipping 1.
- **Comparisons:** local Qwen3 dense cosine; direct typed-edge graph with table-node scores; reified G-reasoner graph with mapping-node scores; one-hop FK-path tie baseline.
- **Queries:** four fixed synthetic prompts, two billing and two shipping; seed `20261024`.
- **Pass criteria:** identity/reordering contract; direct `[1,2]` and reified `[1,4]` finite output; mapping-only permutation score delta `<=1e-5` and same top-ranked mapping IDs; GFM correct on at least 3/4 queries, strictly better than dense cosine, and positive mean margins for both role groups. All criteria must pass for `G0_SYNTHETIC_PASS`.
- **Budget:** smoke 1 forward then, only if operationally successful, Full 6 forwards; total max 7 forwards and 2 loads per model, one GPU, 20 minutes/run with a hard timeout, 300 CPU seconds and 8 GiB peak RSS per run. One smoke and one Full attempt maximum.
- **Environment/resources:** frozen `gfmrag_greasoner_20261022`, offline local Qwen3-Embedding-0.6B and G-reasoner-34M; exact paths, hashes, commands, and versions are in the [pre-registration](../../plans/g0_fk_instance_node_recovery_20261024.md) and [configuration](experiment_config.json).

## Execution and results

Pending smoke. Full can start only if smoke passes. Every run will use a fresh immutable result path under `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/`; logs are under `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/`. Public artifacts will contain synthetic aggregate metrics and reproducibility metadata only.
