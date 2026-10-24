# G0-02 FK instance-node scoring recovery probe

**Status: `G0_SYNTHETIC_NO_GO`.** Experiment ID: `g0_fk_instance_node_20261024_02`. The recovery fixed the execution issue and passed structural/permutation gates, but the frozen synthetic signal criterion failed.

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

### Full preflight

At 2026-10-24 13:01:36 UTC, the required launch recheck passed: selected physical GPU 2 (RTX 4090) had 5,213/24,564 MiB used, 19,351 MiB free, and 0% utilization; RAM available was 423 GiB, CPU count 192, and disk available 114 TiB. GPU 3 was busy at 91% utilization and was not selected. Model symlinks resolved to the preregistered checkpoint and encoder; the Full output directory was absent, and no G0 probe process was active. Exact preflight values are in [configuration](experiment_config.json).

The preregistered Full attempt ran on 2026-10-24 13:03 UTC from the same code tree as registration (`dcf5bcf7569ebe4dac8cb046cf9b894538fc762a`); the launch archive/report head was `0c8d40124650cba097da2655c8294ae49ede76c3`. It completed six forwards in 9.133374 s with no execution error.

| Frozen gate | Result | Decision |
|---|---|---|
| Mapping identity and duplicate multiplicity | 3 declarations → 2 stable mapping IDs; multiplicities 2/1; order invariant | Pass |
| Direct graph output | finite `[1,2]` table-node scores; mapping-level scores are not identifiable from this output | Pass for registered shape; mapping comparison unavailable by design |
| Reified mapping output | finite candidate scores produced | Pass |
| Mapping-only permutation | maximum remapped score delta `0`; same top-ranked mapping set | Pass (`<=1e-5`) |
| GFM synthetic top-1 | 2/4 correct; one miss in each role group | Fail (required at least 3/4) |
| Dense cosine comparison | 4/4 correct | Fail (GFM did not strictly exceed dense cosine) |
| Mean score margin | billing `+0.057074`; shipping `+0.069802` | Pass for both groups |

**Overall:** `G0_SYNTHETIC_NO_GO`. The positive group-average margins and exact permutation invariance show that the reified scoring path emits separate, stable scores on this fixture. They do not offset 2/4 GFM accuracy versus 4/4 dense cosine, so the preregistered signal claim is not supported. The two GFM errors occur once in billing and once in shipping; the simple one-hop path baseline ties both mappings on all four queries.

- **Full runtime/resources:** Qwen load 2.187793 s and encode 0.352361 s; G-reasoner load 0.336024 s and forward total 0.685558 s; process CPU 35.414223 s; peak RSS 4.123600 GiB; peak GPU allocation 2,477,169,152 bytes. One Qwen load, one G-reasoner load, six forwards; no training. Within every registered limit.
- **Local embedding usage:** 325 input tokens (111 query + 214 passages), 16 sequences/vectors. Across Smoke and Full: 567 local input tokens and 29 vectors; generated-text output tokens do not apply. External model API requests and cost: 0 and 0 CNY.
- **Artifacts:** private result `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/full_001/result.json` (SHA-256 `37eba3591792a6d62e1a4fa3747e21665bc8312de32df1aa6c4aad532373f9fc`); log `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/full_001.log`; launch manifest `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/full_001_launch.json`.

## Conclusion and stop

The engineering recovery succeeded: cloning the PyG graph before device transfer allowed all six registered forwards and the permutation control to finish, with stable mapping identity and exactly invariant scores under mapping-node reorder. The scientific result is a no-go for this frozen synthetic probe: the pretrained checkpoint did not beat the local dense baseline, despite positive group-average score margins. This result does not establish real-world FK-role accuracy, failure on BIRD, or SQL execution impact; the fixture uses explicit billing/shipping column names and has no trusted real-role labels.

The G0-02 budget is exhausted and its stopping rule says to stop on any frozen gate failure. Do not repeat this fixture, tune thresholds, or expand synthetic prompts under this experiment ID. Public artifacts contain only aggregate synthetic metrics and reproducibility metadata; no private dataset or raw model files are included.
