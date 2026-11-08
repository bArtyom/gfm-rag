# P0 FK SQL-used rank displacement attribution

**Status:** Full_002 completed; predeclared `NEAR_MISS_SIGNAL` observed. This is a retrospective diagnostic, not a new model evaluation.

## Summary and decision

On the frozen 108-unit BIRD-dev SQL-used ranking run, Dense ranked an SQL-used mapping first in 33 units where G-reasoner did not. In all 33, G-reasoner still ranked an SQL-used target second or third: 31 at rank 2 and 2 at rank 3. The near-miss rate was 33/33 (100%), above the predeclared 50% signal threshold.

G-reasoner had 43/108 Mapping@1 and Dense had 63/108, preserving the earlier 20-unit Top-1 gap. At Mapping@3, G-reasoner had 104/108 and Dense 103/108. All 111 SQL-used target mappings were present in the candidate universe. This points to target ordering within the top three on these Dense-only cases, rather than missing top-three candidate coverage. It does not show that G-reasoner improves SQL accuracy or that a calibration change will help on new data.

This result reuses the same BIRD-dev units and SQL-derived targets. It does not reverse the earlier negative Mapping@1 result, create human Role labels, or authorize parameter tuning, score fusion, or graph changes on BIRD-dev. The same-data ranking line remains closed. An independent-data ranking study may be considered only in a separate registration, after its target labels and success gate are fixed.

## Research question and protocol

The question was whether G-reasoner's Dense-only Top-1 losses are mostly near misses at ranks 2–3, or targets missing below the first three positions. The predeclared classification was `NEAR_MISS_SIGNAL` at a rate ≥50%, `NO_NEAR_MISS_SIGNAL` below 20%, a mixed result in between, and inconclusive if the denominator were zero.

This was an exploratory retrospective error attribution on the existing full set. It reused stored rankings and labels; it made no model/API calls, recomputed no scores, executed no SQL, and used no GPU. Five deterministically selected Smoke units checked input joins and candidate/ranking consistency. Smoke values were excluded from Full. Full used all 108 registered units exactly once. No hypothesis, data, labels, thresholds, or candidate definitions changed in Amendment 001.

## Data, code, and environment

| Item | Value |
|---|---|
| Repository / branch | `https://github.com/bArtyom/gfm-rag`, `research/p0-sql-used-proxy-alignment-20261107` |
| Amendment registration commit | `4c0efa7fb8826e95e06d0c2d20a691b6009e8fef` |
| Upstream run | `p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_full_001` |
| Upstream ranker source commit | `7801d46206a0aeeaaacad05f80e71961297ee475` |
| Upstream config SHA-256 | `ccef27daaf32df29b0344c9a0315d73583b2e06572caf1253177a1004fc54360` |
| Prepared manifest SHA-256 | `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0` |
| Private predictions SHA-256 | `553556a4de85efa48d0b639b899d07b39fa8a35955e6757de0e7a6020308e659` |
| Upstream receipt SHA-256 | `eb0c6e0004e1566783bd655862257a9c221fae1af06620259f32425116e06660` |
| Prepared manifest source commit | `566b8e2d9bb244d8868372ae39c887de02f703e9` |
| Analysis environment | Existing `think2sql_20260909`; Python 3.12.14, invoked by its absolute interpreter path |
| Analysis runner SHA-256 | `35dac945c3aca381b2e77e6d4d40f23241d56df42efcec7f8a96d5d40b9e2fb3` |
| Active amendment config SHA-256 | `1a546a0a64086b95bd80d37f69db731a45f60fbd6cb178f90fb4011a7ef9850a` |
| Seed / sample | 20261107; five Smoke units, 108 Full units |
| Candidate counts | 91 units with 2 candidates; 12 with 3; 5 with 22 |

The analysis environment had affinity limited to four CPU cores. Full used 0.008 seconds of runner wall time, 0.008 CPU seconds, and 0.019 GiB peak RSS; it stayed below the 180-second and 2-GiB limits. GPU, model, external API, and SQL call counts were all zero. These runner timings exclude shell/Conda startup and frozen-file hash verification.

## Results

### Main results

| Measure | G-reasoner | Dense cosine |
|---|---:|---:|
| Mapping@1 | 43/108 (39.81%) | 63/108 (58.33%) |
| Mapping@3 | 104/108 (96.30%) | 103/108 (95.37%) |
| Best target rank = 1 | 43 | 63 |
| Best target rank = 2 | 58 | 40 |
| Best target rank = 3 | 3 | 0 |
| Best target rank ≥4 | 4 | 5 |
| Target absent from candidate universe | 0 | 0 |

The paired Top-1 table was 30 both correct, 13 G-reasoner only, 33 Dense only, and 32 neither. Comparing each method's best rank across the same target set, G-reasoner ranked better in 16 units, tied in 57, and ranked worse in 35.

Among the 33 Dense-only Top-1 units, G-reasoner put an SQL-used target at rank 2 in 31 and rank 3 in 2. No target fell to rank 4 or below, and none was absent from the candidate universe. This is the exact denominator behind the predeclared 100% near-miss rate.

### Candidate-count strata

| Candidate mappings | Units | G-reasoner @1 / @3 | Dense @1 / @3 | Dense-only cases with G at rank 2–3 |
|---|---:|---:|---:|---:|
| 2 | 91 | 39 / 91, 91 / 91 | 51 / 91, 91 / 91 | 25/25 |
| 3 | 12 | 4 / 12, 12 / 12 | 12 / 12, 12 / 12 | 8/8 |
| 22 (grouped as 4+) | 5 | 0 / 5, 1 / 5 | 0 / 5, 0 / 5 | 0/0; inconclusive |

These strata are descriptive. The five-unit 22-candidate group has no Dense-only Top-1 cases, so it does not support a near-miss comparison.

## Smoke and run history

- Smoke 001 stopped before reading experiment inputs with `RUNNER_SHA256_MISMATCH`. The runner looked for a top-level hash while the frozen config stored it under `analysis_runner.sha256`; the attempted `conda run` also resolved Python 3.9.20 instead of the registered Python 3.12.14. No result directory was created. Its private log SHA-256 is `49392a84167ee74d76e53a5b06f1d1b2bac614853d1687c4a29be3533c7325dd`.
- Amendment 001 fixed the hash lookup, run-ID and output-path checks, and pinned the target environment's absolute Python executable. The failed Smoke ID was not reused.
- Smoke 002 completed all five selected units and all hash, target, candidate, and ranking-universe checks. Its aggregate is diagnostic only and is excluded from Full metrics.
- Full 002 completed all 108 units. The private receipt matched all three frozen input hashes. The public aggregate contains only anonymized counts; questions, SQL, database names, mapping IDs, and row-level rankings remain private.

The exact aggregate is in [`aggregate_summary.json`](aggregate_summary.json). Private outputs and logs are under `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_rank_displacement_20261107_01/` and `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_rank_displacement_20261107_01/`.

## Reproduction

From the repository root, the Full command was:

```bash
timeout --signal=TERM --kill-after=10s 180s \
  conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python \
  scripts/text2sql/audit_p0_fk_sql_used_rank_displacement_20261107_01.py \
  --config configs/text2sql/p0_fk_sql_used_rank_displacement_20261107_01_amendment_001.json \
  --expected-config-sha256 1a546a0a64086b95bd80d37f69db731a45f60fbd6cb178f90fb4011a7ef9850a \
  --expected-commit 4c0efa7fb8826e95e06d0c2d20a691b6009e8fef \
  --repo-root . --mode full \
  --run-id p0_fk_sql_used_rank_displacement_20261107_01_full_002 \
  --manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json \
  --predictions /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/ranker_gpu_full/private_predictions.jsonl \
  --upstream-run-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/ranker_gpu_full/run_manifest.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_rank_displacement_20261107_01/full_002
```

The authoritative protocol and active amendment are in [the plan](../../plans/p0_fk_sql_used_rank_displacement_20261107_01.md), [Amendment 001](../../plans/amendments/p0_fk_sql_used_rank_displacement_20261107_01_amendment_001.md), and [the amendment config](../../../../configs/text2sql/p0_fk_sql_used_rank_displacement_20261107_01_amendment_001.json).
