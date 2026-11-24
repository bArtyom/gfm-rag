# RAMP-SL V1 Budget-Feasible Active Encoding

**Run ID:** `ramp_sl_v1_active_encoding_20261124_001`
**Status:** Preregistered; experiment not run yet.
**Protocol:** [`ramp_sl_v1_budget_feasible_active_encoding_20261124.md`](../../plans/ramp_sl_v1_budget_feasible_active_encoding_20261124.md)

This report tracks a database-isolated replay on the 1,046 BIRD-dev questions with complete cached GRAST column scores. The experiment uses five training databases and three held-out databases selected by the frozen hash rule. It tests whether RAMP-SL V1 can improve complete reference-column coverage under a per-question GRAST input budget of 4,096 tokens and a schema-output budget of 2,048 tokens.

The scorer, embeddings, and all-column scores are frozen local artifacts. This run schedules cached score reads only: no new GPU inference, external API calls, SQL generation, or SQL execution. Since BIRD-dev and the GRAST reranker were used in earlier project work, this is exploratory evidence and not an external generalization result or a full GRAST-SQL reproduction.

## Frozen inputs and preflight

- The question and schema files, embedding cache, ordered node manifest, cached score file, scorer revision, test/train database hashes, and token budgets are pinned in the [run configuration](../../../../../configs/text2sql/ramp_sl_v1_active_encoding_20261124.json).
- Gold-blind integrity preflight passed for 1,046 complete questions across eight databases. Token costs and prompt hashes were rechecked against the frozen tokenizer for every cached question. The public receipt is [`preflight_public.json`](preflight_public.json).
- The split contains 741 training cache questions over five databases and 305 held-out cache questions over three databases. A training-only label audit matched all 741 cached training questions to eligible Gold labels; it found 45 additional ineligible label rows with no cached-score question match. These rows are excluded under the existing P1.6 eligibility rule. All held-out cache questions still receive predictions, while coverage metrics use only held-out questions with eligible labels after the prediction seal; the frozen science gate requires at least 80 such questions.
- Before sealing, each policy can retrieve only its explicitly selected test scores through the budgeted replay API. Test Gold labels and the full-score reference are gated until the online prediction file is sealed.
- `scikit-learn` is absent from the frozen environment. Both registered L2 logistic models use the fixed SciPy L-BFGS-B objective; no dependency was installed. RAMP's propensity model uses its preregistered online-visible features. The `Calibrated-2R` comparator uses a separate cheap-only model so it does not consume first-round GRAST-to-GP residual information.

## Execution gates

Before the held-out replay, the runner must pass the registered 5-question training smoke and a training-only replay audit of at least 30 questions. Both compare Static-TopM's scored candidates, input-token count, packed columns, and output-token count with the prior frozen run. The audit reads only training-database detail rows.

The first smoke attempt stopped before creating predictions because the label loader treated ineligible P1.6 rows for unrelated questions in the same training databases as cached replay questions. A training-only audit confirmed exact eligibility matches for all 741 cached training questions. The loader now skips those unrelated rows.

The second smoke attempt found the same Static-TopM candidates and token totals as the historical run for all five sampled training questions, but two packed column lists differed. The cache contains a separate all-column inference pass; replaying those values did not reproduce the archived candidate-only static outputs. Static-TopM uses the archived candidate-only scores. The shared initial M0 batch uses those same cached values where available and the all-column cache for any initial column absent from the historical static set; later adaptive batches use the all-column cache. This pre-test correction changes no database split, budget, primary metric, threshold, or method. No test Gold rows have been parsed.

The held-out policies are run once. Their outputs are sealed before any test Gold labels or full-score reference values are read. The full-score reference is explicitly marked non-budget-feasible and is excluded from the primary baseline gate. Any budget-contract violation, held-out leakage, hash mismatch, or failed train-only gate stops the run.

## Results

Pending. No test predictions or test labels have been read for this run.

## Artifact privacy

Question IDs, question text, database names, SQL, Gold columns, per-column scores, prediction traces, training artifacts, and logs remain in the local private result and log directories. Only aggregate metrics and the hash-only preflight receipt belong in this report.
