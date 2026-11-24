# RAMP-SL V1 Budget-Feasible Active Encoding

**Run ID:** `ramp_sl_v1_active_encoding_20261124_001`
**Status:** `INCOMPLETE_BUDGET_LIMIT` — the held-out prediction pass stopped at the preregistered CPU-time cap. No held-out metric or scientific GO/STOP decision is available.
**Protocol:** [`ramp_sl_v1_budget_feasible_active_encoding_20261124.md`](../../plans/ramp_sl_v1_budget_feasible_active_encoding_20261124.md)
**Public execution receipt:** [`execution_status_public.json`](execution_status_public.json)

## Research question and frozen criteria

This experiment asks whether RAMP-SL V1 can improve complete reference-column coverage over static and other budget-feasible baselines when every method receives the same candidate universe, cached GRAST scorer, 4,096 input-token budget, and 2,048 output-schema-token budget. The database-isolated BIRD-dev split was fixed before test execution: 741 cached questions in five training databases and 305 in three held-out databases. The random seed is `20261124`; the first-round input budget is 2,048 tokens. Sensitivity outputs at 512 and 1,024 tokens are part of the frozen analysis.

The preregistered GO criteria are at least +3.0 percentage points over Static-TopM, +1.0 point over the strongest feasible baseline, positive net rescue on at least two of three test databases, and zero budget or leakage violations. These criteria were not evaluated because the held-out predictions did not finish and were never sealed. This run is not a negative result and is not classified `STOP_THIS_V1`.

## Repository, code, data, and environment

- Project repository: [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag), branch `research/ramp-sl-v1-active-encoding-20261124`.
- Protocol base: `bdecff28b1f35b66423aff6f5663455d31f4874b`; analysis base: `c8c75d3c53e0cf73e80d56fe995a4e99a425c4d6`; local execution code commit: `8c58826de43ee6bc7768183cb6520659aa085d73`.
- Runner: [`scripts/text2sql/ramp_sl_v1_active_encoding.py`](../../../../../scripts/text2sql/ramp_sl_v1_active_encoding.py), SHA-256 `9b990ef096f17d807190a97f4f3a0541a34f9da81195a2c7046b08631af16a1c`.
- Frozen config: [`configs/text2sql/ramp_sl_v1_active_encoding_20261124.json`](../../../../../configs/text2sql/ramp_sl_v1_active_encoding_20261124.json), SHA-256 `5d721d78dee0857d9fbb41dcf9d86fe3fffbb47c40a14d5be2ec85e1e664fe61`.
- Dataset, schema, embedding cache, node manifest, cached GRAST scores, model revision, database split hashes, budgets, and thresholds are pinned in that config and the [Gold-blind preflight receipt](preflight_public.json). The scorer revision is `50b224a1e8557ad6629c7dafddeba7b73c603acb`; all score reads replayed existing local cache entries. No new model inference, external model API, SQL generation, or SQL execution was used.
- Environment: `think2sql_20260909`, Python 3.12.14, NumPy 2.2.6, SciPy 1.16.3, Transformers 4.57.1, tokenizers 0.22.1. `scikit-learn` was absent; the preregistered L2 models used the existing SciPy L-BFGS-B implementation, with no dependency installation.
- Hardware: CPU-only replay, configured for 8 threads; the process used about one CPU core. No GPU inference was run. The test process used about 1.2 GiB resident memory, below the 16 GiB cap.

## Execution and results

### Smoke and training-only gate

The first three smoke attempts exposed and corrected training-only issues: skipping unrelated ineligible P1.6 label rows, matching archived candidate-only Static-TopM scores, and applying the same initial-score fallback in training features as in replay. No test Gold was read during these attempts. An earlier five-question smoke and the optimized `smoke_005` passed. The optimized smoke took 48.45 CPU seconds, used about 1.13 GiB peak RSS, passed all seven policy budget checks, and reproduced historical Static-TopM exactly on all five questions.

The registered `train_audit_001` then passed on 100 questions (20 from each of the five training databases). All seven methods produced 100 rows and passed the output-token budget. Static-TopM matched the historical run on scored candidates, input-token count, packed columns, and output-token count for 100/100 questions (zero mismatches). The audit took 749.63 wall seconds and 750.06 CPU seconds, with peak RSS about 1.126 GiB. It parsed zero test-database rows and did not use test Gold.

### Held-out replay

The one-time command was:

```bash
conda run -n think2sql_20260909 python3.12 scripts/text2sql/ramp_sl_v1_active_encoding.py \
  --mode full \
  --output-dir results/ramp_sl_v1_active_encoding_20261124_001/test_replay_001
```

The run began at `2026-11-24T05:04:58Z`. It stopped at the registered 3,600-second CPU-time cap with `TimeoutError: registered CPU-time budget exceeded`, after about 61 minutes wall time. The runner had written 234 of 305 held-out prediction rows to a private, **unsealed** file. Its SHA-256 is `4d9263751aa5281b1e720e2c47a95c092967b73852a5ced1e09fc7a212887c8f`.

There is no `private_predictions_sealed.jsonl`, no public metric aggregate, and no completed verification summary. Test Gold rows and full-score reference values were not loaded. The partial prediction file was not evaluated, and no coverage, rescue, baseline-comparison, sensitivity, or bootstrap metrics are reported. The GO/STOP science gate remains unevaluated. No restart, test-set retuning, or sample reduction was performed.

## Interpretation and limitations

The training-only implementation gate passed, but the held-out science experiment is incomplete because the frozen CPU budget was insufficient for 305 questions. The partial file is retained only as run evidence and must not be used for metrics or paper claims. Any future continuation requires a separately reviewed execution plan that improves throughput or sets a justified budget before a new test run; the current test databases must not be retuned against partial predictions.

Even if completed, this is exploratory evidence on BIRD-dev, whose data and GRAST scorer have appeared in prior project work. It is not an external generalization result or a complete GRAST-SQL reproduction, and only three databases are held out.

## Artifact locations and privacy

- Private local results: `/mnt/liansp3/sources/results/ramp_sl_v1_active_encoding_20261124_001` (symlink to this project's `results/ramp_sl_v1_active_encoding_20261124_001/`).
- Training audit summary: `results/ramp_sl_v1_active_encoding_20261124_001/train_audit_001/verification_summary.json` (local only).
- Partial held-out predictions: `results/ramp_sl_v1_active_encoding_20261124_001/test_replay_001/private_predictions_unsealed.jsonl` (local only).
- Logs: `logs/ramp_sl_v1_active_encoding_20261124_001/` (local only).

Question IDs, question text, database names, SQL, Gold columns, per-column scores, private prediction rows, training artifacts, and logs remain local. The GitHub report contains only protocol material, aggregate execution status, and hashes.
