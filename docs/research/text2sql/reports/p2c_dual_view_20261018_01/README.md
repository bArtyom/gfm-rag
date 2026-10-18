# P2c Frozen-Cache Dual-View 2×2 Retrieval/Context Factorial

> **Status: execution stopped after the registered Full recovery failed. No Full aggregate was produced, so the scientific hypothesis remains untested.** This is an exploratory BIRD dev experiment. It does not measure SQL execution accuracy or validate JOIN-role selection.

## Question and registered decision rule

The experiment separates the text used to create node vectors from the text charged to the returned Schema Context. `R0` retains Values; `R1` removes only the trailing `value_description` field. The four arms are V00 (R0/R0), V01 (R0/R1), V10 (R1/R0), and V11 (R1/R1).

The primary contrast is V01−V00 Complete Schema@1024. The fixed R0 non-saturated subset must improve by at least 3.0 percentage points, all 1,460 eligible questions by at least 5.0 points, the database-cluster bootstrap 95% CI lower bound must be above zero for both groups, and at least three of five fixed databases must be nonnegative with at least two strictly positive. A pass only qualifies a separate Values-risk audit; it is not a Text2SQL accuracy claim.

## Frozen inputs and execution

The run will reuse the P2b CPU vector cache and question-level rows from `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/full_1534_20261018_01`. It will verify the published P2b aggregate checksum, input manifest, node/text hashes, vector shapes, and the frozen 5-database/706-question denominator before scoring. The only model-adjacent operation is local tokenizer loading to rebuild exact R1 token counts; no model weights, API, SQL, or GPU will be used.

The repository guidance is recorded in [the P2c protocol](../../plans/p2c_dual_view_retrieval_context_factorial_20261018.md). The preregistered machine-readable configuration is [experiment_config.json](experiment_config.json).

## Results

**No Full aggregate or per-question result was written. No Complete@1024 delta, confidence interval, or scientific gate decision is available.** The first preflight (`p2c_dual_view_preflight_20261018_01`) stopped before scoring with a runner `KeyError` while reading the P2b aggregate checksum from the wrong config object. The registered recovery preflight passed (1,534 questions, 11 databases, 873 nodes; fixed subset 5 databases/706 questions). Smoke `p2c_dual_view_smoke5_20261018_01` passed on 5 questions / 1 database / 92 nodes: finite scores, score/context invariants, and archived P2b Column/budget replay all passed (11.217 s wall / 11.152 CPU s / 0.865 GiB peak RSS). Smoke is not formal evidence.

The initial Full (`p2c_dual_view_full1534_20261018_01`) evaluated all four arms and passed the paired row replay, then stopped during aggregate construction because the P2b public aggregate condition key differs from its private row key. It used 20.579 s wall / 20.685 CPU s / 0.969 GiB peak RSS.

The single preregistered Full recovery (`p2c_dual_view_full1534_20261018_02`) also evaluated all four arms and passed row replay, but stopped in the aggregate replay assertion with `KeyError: 'column_r5_query_macro'`. The local P2c summary schema exposes Column recall as `column_recall_query_macro`; the replay assertion attempts to read the archived P2b field name from that local summary. It used 20.575 s wall / 20.681 CPU s / 0.980 GiB peak RSS. This is an implementation/reporting failure, not evidence for or against H1/H2.

Per the registered one-recovery limit, there was no third Full attempt. Both Full failure directories contain only `run_start.json` and `failure.json`; neither an aggregate nor per-question output was written. Failure logs and receipts remain local under `/mnt/liansp3/sources/results/gfmrag_p2c_dual_view_20261018/` and `/mnt/liansp3/logs/`. Across both preflights, smoke, and the two Full attempts, cumulative use was 73.965 CPU seconds / 73.943 wall seconds; peak process RSS was 0.980 GiB. The run used no model weights, API calls, model forwards, SQL executions, or GPU seconds. The registered inputs, question counts, and thresholds were unchanged.

The source commit used by the recovery was `1d6cad835a7b07189a1c6102de013707944a0eeb` on `bArtyom/gfm-rag/main`; the checkout tree matched the published tree. The machine-readable recovery receipt is [execution_failure_receipt.json](execution_failure_receipt.json). BIRD dev remains exploratory, and no SQL execution accuracy claim is supported.

The preflight recovery now reads P2b's aggregate checksum from the completed P2b config. The Full recovery separately maps P2b public aggregate condition keys from its private row variant keys. These fixes did not change the hypothesis, inputs, scoring, metrics, thresholds, or denominators. The recovery still exposed the local summary-to-archive Column recall field mismatch described above.
