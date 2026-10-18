# P2c Frozen-Cache Dual-View 2×2 Retrieval/Context Factorial

> **Status: preregistered, not yet run.** This is an exploratory BIRD dev experiment. It does not measure SQL execution accuracy or validate JOIN-role selection.

## Question and registered decision rule

The experiment separates the text used to create node vectors from the text charged to the returned Schema Context. `R0` retains Values; `R1` removes only the trailing `value_description` field. The four arms are V00 (R0/R0), V01 (R0/R1), V10 (R1/R0), and V11 (R1/R1).

The primary contrast is V01−V00 Complete Schema@1024. The fixed R0 non-saturated subset must improve by at least 3.0 percentage points, all 1,460 eligible questions by at least 5.0 points, the database-cluster bootstrap 95% CI lower bound must be above zero for both groups, and at least three of five fixed databases must be nonnegative with at least two strictly positive. A pass only qualifies a separate Values-risk audit; it is not a Text2SQL accuracy claim.

## Frozen inputs and execution

The run will reuse the P2b CPU vector cache and question-level rows from `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/full_1534_20261018_01`. It will verify the published P2b aggregate checksum, input manifest, node/text hashes, vector shapes, and the frozen 5-database/706-question denominator before scoring. The only model-adjacent operation is local tokenizer loading to rebuild exact R1 token counts; no model weights, API, SQL, or GPU will be used.

The repository guidance is recorded in [the P2c protocol](../../plans/p2c_dual_view_retrieval_context_factorial_20261018.md). The preregistered machine-readable configuration is [experiment_config.json](experiment_config.json).

## Results

**No experiment scores have been computed.** The first preflight (`p2c_dual_view_preflight_20261018_01`) stopped before scoring with a runner `KeyError` while reading the P2b aggregate checksum from the wrong config object. It used 10.55 s wall / 10.31 CPU s / 0.75 GiB peak RSS; model forwards and scoring were zero. The failure receipt and log are retained locally. A single implementation recovery is registered as `p2c_dual_view_preflight_20261018_02`; the hypothesis, inputs, metrics, thresholds, and smoke/Full run IDs are unchanged. If recovery preflight fails, P2c stops.
