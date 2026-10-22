# P2d.1 frozen-prediction evaluator audit — recovery run 02

**Status: completed.** The synthetic safety gate and the frozen full replay both passed. This is an exploratory evaluator-coverage and failure audit, not confirmatory evidence for a retrieval method.

## Question and preregistration

The core hypothesis was that a runtime-checked, read-only evaluator could safely compare a limited subset of stored-column date/time expressions without reading the real clock or timezone, while preserving every reference and prediction outcome that the frozen v1 evaluator had already compared.

The run used the preregistered protocol at [`plans/p2d_1_frozen_prediction_eval_audit_20261022.md`](../../plans/p2d_1_frozen_prediction_eval_audit_20261022.md), registered in commit `46e3cfe742454734c5196e8a71355efab02d14dc`. The protocol hash was verified as `96773cc235f932b416c2a461017314d93aa5cf9654ae41800bc3e564de415a89` before execution. A prior incorrect hash field was corrected before the first SQL replay; the correction changed no hypothesis, budget, threshold, or stopping rule.

- **Research layer:** exploratory evaluator coverage and failure attribution.
- **Mainline evidence:** no; no method or model comparison was added.
- **Budget:** CPU-only; at most 8 process threads, 600 CPU seconds, 4 GiB RSS, 10 seconds per SQL, 50,000 result rows, 64 MiB result data, and 256 MiB SQLite heap. No retries, model calls, paid API calls, or GPU time.
- **Success criteria:** all synthetic safety checks pass; exact parity on the old v1-comparable results; Gate 2 runs only after Gate 1 passes; original data and database hashes remain unchanged.
- **Stop condition:** preserve a failed run and stop if a seal, safety gate, parity check, or resource cap fails. Recovery uses a new run ID and output directory.

## Source, data, and execution

- **Project repository:** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p2d1-eval-v2-20261022`.
- **Execution source:** commit [`46e3cfe`](https://github.com/bArtyom/gfm-rag/commit/46e3cfe742454734c5196e8a71355efab02d14dc), tree `65f46b71071817390eff2e803c10a89566088687`.
- **Evaluator fix included in the source:** [`40245f0`](https://github.com/bArtyom/gfm-rag/commit/40245f0745f04ae2d90c271c491e89d63f00a71d), which checks the sealed prediction payload hash separately from the seal-file hash.
- **Guidance read:** repository `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, `reproducibility-contract.md`, and the frozen P2d.1 plan. The run followed the plan; no scientific criterion was changed.
- **Frozen data:** BIRD dev diagnostic subset, 30 questions across 5 databases, 19 priority cases and 11 matched controls; 90 sealed predictions across E0/E1/E2. These cases are not an independent test set. The original frozen payload hash is `e88bf42f22a73b6b56af96a5d3ea88d69252c33509bb72da5b8cfde2f7474ea5`; the prediction seal-file hash is `f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3`.
- **Environment:** `think2sql_20260909`, Python 3.12.14, SQLite 3.53.2, SQLGlot 28.0.0. The existing local tokenizer stack was used only for offline token accounting; no package was installed or upgraded.
- **Hardware:** CPU-only. At startup, 192 CPU threads, 421–422 GiB available memory and 115 TiB free disk were recorded; no GPU was used. Gate 1 used 16.858 CPU seconds and peaked at 60 MiB RSS; Gate 2 used 7.289 CPU seconds and peaked at 47 MiB RSS.
- **Random seeds:** none; replay is deterministic and does not sample.

The execution commands were `conda run -n think2sql_20260909 python3 scripts/text2sql/p2d_v2_saved_replay.py --phase gate1 ...` followed, only after Gate 1 passed, by the same command with `--phase gate2 --gate1-receipt-sha256 <Gate1 receipt SHA>`. The frozen prepared/full inputs and result directory are private local artifacts, so their machine-specific paths are omitted here. The exact public command interface and required seals are documented in the runner and `experiment_config.json`.

## Gate results

Gate 1 ran the synthetic safety suite: **137 passed, 0 skipped, 0 failed**. It replayed the 26 reference SQL and 57 prediction SQL that had succeeded under v1 (E0 19, E1 18, E2 20). Across the **83 paired v1/v2 replays**, output and comparison parity failures were **0**. Frozen database hashes were unchanged. Gate 1 receipt SHA-256: `42239798c3686edf71d60d5c5a30d89d1d8b832949e2d52eddb305053b24f262`.

Gate 2 processed all **30 questions / 90 predictions**. It executed 37 new SQL statements and verified/reused the 83 Gate 1 results, for 120 total v2 executions across references and predictions. The four reference statements blocked by v1 were safely comparable under v2; the other 26 retained their prior availability. No database hash changed. Gate 2 receipt SHA-256: `50220fff76cce53da16e0c27a06dae7a7778149d6a8c3fb3dbff6c9e8662842f`.

## Main results

Counts below use all 30 cases per arm. Set and Bag outcomes were identical for this run. “Unknown” means the evaluator could not compare the prediction; it is not counted as a wrong answer.

| Arm | v1 correct / unknown / wrong | v2 correct / unknown / wrong | v2 confirmed correct / 30 (Wilson 95% interval) | v2 accuracy among comparable cases* |
|---|---:|---:|---:|---:|
| E0 | 8 / 11 / 11 | 8 / 10 / 12 | 26.7% [14.2%, 44.5%] | 8/20 = 40.0% |
| E1 | 7 / 12 / 11 | 7 / 10 / 13 | 23.3% [11.8%, 40.9%] | 7/20 = 35.0% |
| E2 | 8 / 10 / 12 | 8 / 8 / 14 | 26.7% [14.2%, 44.5%] | 8/22 = 36.4% |

\*Comparable-only accuracy is secondary and must not replace the fixed-denominator result.

The v2 evaluator increased the number of comparable cases but **did not add a confirmed correct answer** in any arm. One formerly unknown E0 result and two each in E1/E2 became comparable but wrong. Pairwise E0/E1 and E0/E2 exclusive wins stayed 1 vs 1; E1/E2 had no exclusive wins. Thus this audit improves measurement coverage, not SQL quality or the experiment's method ranking.

Among the six cases in the preregistered “rescued coverage” stratum, **0/6** had all three arms confirmed correct under v2; three still had at least one unknown result, versus four under v1. The unchanged 24-case stratum retained its v1 outcomes exactly. These small, selected strata support no out-of-sample claim.

## Failure attribution

Among the 90 predictions, 28 remained non-executable under v2: **10 SQL parse failures** and **18 SQLite missing-column failures**. By arm:

| Arm | Parse failures | Missing-column failures | Comparable wrong | Confirmed correct |
|---|---:|---:|---:|---:|
| E0 | 4 | 6 | 12 | 8 |
| E1 | 2 | 8 | 13 | 7 |
| E2 | 4 | 4 | 14 | 8 |

For successfully executed but incorrect predictions, automated AST diagnostics found exact table-set matches in 10/12, 10/13, and 9/14 predictions for E0/E1/E2; exact JOIN signature matches in 6/12, 4/13, and 3/14; and exact direct column/literal pair matches in 3/12, 4/13, and 4/14 (with unresolved cases retained separately). These are structural proxies, not human semantic judgments.

Reference-SQL node coverage was also checked against selected context text as an automated name-matching proxy: E0 contained 10/20 referenced table nodes and 39/59 column mentions; E1 20/25 and 55/68; E2 13/26 and 49/71. SQL aliases, CTEs, and equivalent expressions can make name matching uncertain. No human semantic review was performed (0 reviewers); the original Values necessity labels remain unverified.

## Token accounting

The frozen original P2d request records contain **35,074 / 35,591 / 24,458 input tokens** for E0/E1/E2. The current evaluator audit made **zero** model/API requests and incurred **zero new model tokens or API cost**. Local chat-template tokenization matched each frozen input count exactly. E1 used 517 more tokens than E0 (+1.47%); E2 used 10,616 fewer than E0 (−30.27%). Component counts and their limits are in [`token_breakdown.json`](token_breakdown.json). The component residual includes template and token-boundary effects, so it is not a provider billing partition.

## Safety and interpretation limits

The evaluator's temporal-expression policy is restricted to approved deterministic forms over stored values; real clock and timezone expressions remain blocked. SQLite documents `now` as current VFS time and identifies `now`, `localtime`, and `utc` as nondeterministic or special-case inputs ([date/time functions](https://www.sqlite.org/lang_datefunc.html), [deterministic SQL functions](https://www.sqlite.org/deterministic.html)). Synthetic adversarial cases and full old-result parity passed, but this does not make the 30-case cohort representative.

The audit is exploratory, small, and confined to BIRD dev cases selected for prior debugging. It does not establish an official BIRD score, cross-database generalization, Values semantic necessity, or a retrieval-method advantage. The v2 evaluator does not repair generated SQL; the 10 parse and 18 missing-column failures remain generator/evidence issues to diagnose separately.

## Decision and next work

**Retain the original P2d 8/7/8 score as the frozen pilot result. Do not claim an EX improvement from this evaluator audit or tune another prompt on the same 30 cases.** First resolve the execution-validity bottleneck on a fresh, preregistered sample or through a separate diagnosis of the already frozen outputs; keep the fixed denominator and report non-executable outputs explicitly. The graph-method track may proceed as a separate, synthetic/interface-only G0 feasibility gate under the roadmap; it must not be mixed into P2d.1 or treated as JOIN-accuracy evidence. Values semantic review remains pending and cannot be represented as complete.

## Public artifacts

- [`experiment_config.json`](experiment_config.json): completed configuration and budgets.
- [`aggregate.json`](aggregate.json): anonymized metrics and confidence intervals.
- [`failure_taxonomy.json`](failure_taxonomy.json): aggregate-only failure and AST diagnostics.
- [`token_breakdown.json`](token_breakdown.json): offline token reconciliation.
- [`verification.json`](verification.json): source, seal, receipt, and privacy checks.
- Failed wrapper attempt [_01](../p2d_1_eval_audit_20261022_01/README.md) remains preserved separately; this recovery used a new run ID and output directory.
