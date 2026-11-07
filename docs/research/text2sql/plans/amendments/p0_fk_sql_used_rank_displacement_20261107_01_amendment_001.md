# Amendment 001: fix the frozen runner checks and target Python invocation

**Status:** preregistered; corrected Smoke 002 has not run. Parent experiment: `p0_fk_sql_used_rank_displacement_20261107_01`.

## Observed stop

Smoke 001 stopped with `RUNNER_SHA256_MISMATCH` before validating or reading any frozen input. The config stores the runner hash at `analysis_runner.sha256`, while the runner looked for a top-level `analysis_runner_sha256`. It created no result directory. The private log is `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_rank_displacement_20261107_01/smoke_001.log` (SHA-256 `49392a84167ee74d76e53a5b06f1d1b2bac614853d1687c4a29be3533c7325dd`).

The same preflight found that `conda run -n think2sql_20260909 python3` resolved to `/root/miniconda3/envs/python39/bin/python` (Python 3.9.20), even though the registered environment's own interpreter is Python 3.12.14. The run did not reach input loading, so this mismatch did not produce data or metrics.

## Corrections

- Read the runner hash from the frozen nested config field and accept the run ID from the active config. This preserves fixed run IDs while allowing a new amendment's IDs.
- Invoke `/root/miniconda3/envs/think2sql_20260909/bin/python` explicitly through `conda run`; do not use the PATH-resolved `python3` entry.
- Derive the permitted output-directory leaf from the configured stage run ID instead of accepting only `_001` directory names. Smoke 002 and Full 002 must still stay under the frozen private results root.
- Use fresh run IDs `p0_fk_sql_used_rank_displacement_20261107_01_smoke_002` and `p0_fk_sql_used_rank_displacement_20261107_01_full_002`. Preserve the old log and do not reuse Smoke 001.

No input, dataset slice, labels, ranking order, metrics, thresholds, hypothesis, or stop rule changes. The active config pins the corrected runner SHA-256 and interpreter path. Smoke 002 must pass before one Full 002 run is allowed.

## Reproducibility and privacy

The analysis remains CPU-only and retrospective over the same 108 existing BIRD-dev predictions. It uses no model, API, GPU, SQL execution, or dependency change. Private inputs and outputs stay under `/mnt/liansp3/sources/results/`; logs stay under `/mnt/liansp3/logs/`. Public results contain anonymized aggregate counts only.
