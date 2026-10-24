# G0-02 FK instance-node scoring recovery probe

**Status: `SMOKE_PASS`; Full pending.** Experiment ID: `g0_fk_instance_node_20261024_02`. The operational smoke gate passed; the four-query scientific gate has not been evaluated.

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

### Smoke (`g0_fk_instance_node_20261024_02_smoke_001`)

- **Outcome:** `SMOKE_PASS` for the operational gate. The identity contract passed and the single reified output was finite. Smoke is excluded from the four-query scientific denominator; direct-graph shape and permutation gates remain for Full.
- **Observed one-query result:** on synthetic `q_billing_1`, GFM ranked `shipping_map` above the gold `billing_map`; local dense cosine ranked `billing_map` first. This single smoke query is a warning to inspect, not a scientific signal conclusion or a change to the frozen thresholds.
- **Timing and resources:** wall 8.801792 s; Qwen load 1.722135 s and encode 0.447934 s; G-reasoner load 0.363488 s and forward 0.665833 s; process CPU 33.129145 s; peak RSS 4.136650 GiB; peak GPU allocation 2,477,169,152 bytes. One Qwen load and one G-reasoner load; one forward; no training.
- **Local embedding usage:** 242 input tokens (28 query + 214 passages), 13 sequences/vectors; generated-text output tokens do not apply. No external API requests or cost.
- **Reproducibility:** launched 2026-10-24 12:56:59 UTC from public preregistration commit `dcf5bcf7569ebe4dac8cb046cf9b894538fc762a`; local checkout commit `722b463aefd5dec801fd5134970c1e4460754332`; runner blob `a30cfc7c143a4c96cd4bca55e1ad02e129fdc9f8`. Frozen environment and models are in [configuration](experiment_config.json). Exact command is the `smoke` entry there.
- **Artifacts:** private result `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/smoke_001/result.json` (SHA-256 `cf7aa2c48616dbd4b169218eef1dd0ecc4f822e5691f7086844fe3d2223d4517`); log `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/smoke_001.log`; launch manifest `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/smoke_001_launch.json`.

The smoke gate is satisfied, so the single preregistered Full attempt is eligible to start after its required fresh resource check. Full will use its own immutable path `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/full_001/result.json`; logs and launch manifests remain under `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/`. Full is still pending at this checkpoint. Public artifacts contain synthetic results and reproducibility metadata only.
