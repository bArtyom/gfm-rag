# P0：Frozen FK Rank Displacement Attribution (Independent Diagnostic)

**Status:** initial registration; Smoke 001 stopped before reading inputs. Amendment 001 is the active protocol; Smoke 002 has not run.
**Experiment ID:** `p0_fk_sql_used_rank_displacement_20261107_01`
**Layer:** exploratory retrospective error attribution. This is not a new ranking method or a new model evaluation.

## Pain point and research question

On the frozen BIRD-dev SQL-used set, G-reasoner scored 43/108 at Mapping@1 versus Dense cosine at 63/108. G-reasoner was only one unit higher at Mapping@3, while its MRR was lower by 0.0941. The aggregate does not show whether G-reasoner often places the SQL-used mapping at rank 2–3 (a possible candidate-ordering problem) or leaves it below rank 3 (a candidate-relevance problem).

**Question:** Among units where Dense ranks an SQL-used mapping first and G-reasoner does not, how often does G-reasoner still rank a valid SQL-used mapping second or third? This determines whether G-reasoner has a useful near-miss signal worth studying on independent data.

## Hypothesis and evidence boundary

- **H1, near-miss hypothesis:** At least half of Dense-only Top-1 wins have a SQL-used target at G-reasoner rank 2 or 3.
- **Alternative:** Fewer than one fifth of those units are near misses; graph propagation usually fails to keep the target in the first three positions on Dense-correct cases.
- A value from 20% through less than 50% is mixed and does not justify another method run.
- The result is a descriptive error analysis of the same 108 previously scored units. It cannot reverse the registered negative Mapping@1 conclusion, establish human Role accuracy, or authorize tuning on BIRD-dev.

## Frozen inputs and method

- Reuse only the private Full prediction JSONL and prepared manifest from upstream run `p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_full_001`; do not regenerate embeddings or G-reasoner scores.
- Full universe: the upstream manifest's fixed 108 Full units. Each unit has one or two SQL-used target mappings. The reported candidate-count distribution is 91 units with 2 candidates, 12 with 3, and 5 with 22.
- Smoke: deterministic SHA-256 selection of five units from the Full universe. Smoke validates the join between frozen unit IDs, candidate IDs, and ranked IDs. Its values are excluded from Full metrics.
- For each method, target rank is the first (best) one-based rank occupied by any SQL-used target mapping. Preserve the upstream deterministic tie order; do not recompute scores or resolve ties differently.
- Record target presence in the candidate universe separately. A target absent from the universe is a miss, not a dropped example.
- No SQL, question text, database contents, reviewer output, or raw mapping ID is needed for this analysis.

## Measures and decision rule

Primary measures:

1. G-reasoner target-rank distribution: rank 1, rank 2, rank 3, rank 4+, and target absent from ranked candidates.
2. Paired G-reasoner/Dense Top-1 table: both correct, G-reasoner only, Dense only, neither.
3. Among Dense-only Top-1 wins, the count and fraction for which G-reasoner ranks a SQL-used target at 2–3.
4. Best-target-rank comparisons: G-reasoner better, equal, or Dense better.

Candidate-count and anonymous-database breakouts are descriptive only. Cells with fewer than 10 units are shown with their denominator and are not used for inferential claims.

The follow-up classification is frozen as:

- `NEAR_MISS_SIGNAL` at ≥50% of Dense-only Top-1 wins having G-reasoner rank 2–3;
- `NO_NEAR_MISS_SIGNAL` below 20%;
- `MIXED_NEAR_MISS_PATTERN` otherwise;
- `INCONCLUSIVE_NO_DENSE_ONLY_TOP1_CASES` if the denominator is zero.

Even a near-miss result only supports considering a separately registered diagnostic on independent data. It does not authorize a BIRD-dev reranker, score fusion, or graph-parameter search. A no-near-miss result closes the candidate-calibration hypothesis for this evidence line.

## Budget, gates, and stop conditions

- CPU-only, maximum 4 threads, 180 seconds wall time, 2 GiB RSS. No GPU, model, API, SQL execution, package installation, or dependency changes.
- Verify repository commit, config hash, analysis-code hash, upstream run receipt, and all three frozen input hashes before reading prediction rows.
- Smoke must reconcile all five selected unit IDs and candidate universes exactly. If it passes, run one Full analysis over 108 units. No retries, sample extensions, or metric changes.
- Any hash mismatch, missing/duplicate unit, ranking/candidate-set mismatch, or output-path collision stops the run and preserves a failure receipt.

## Reproducibility and artifacts

- Repository: `https://github.com/bArtyom/gfm-rag`, branch `research/p0-sql-used-proxy-alignment-20261107`.
- Registration parent: `55166f4e28379cd702cdedee60f230719ca17b80`.
- Config: `configs/text2sql/p0_fk_sql_used_rank_displacement_20261107_01.json`.
- Runner: `scripts/text2sql/audit_p0_fk_sql_used_rank_displacement_20261107_01.py`.
- Private inputs and outputs remain under `/mnt/liansp3/sources/results/`; logs remain under `/mnt/liansp3/logs/`.
- Public report: `docs/research/text2sql/reports/p0_fk_sql_used_rank_displacement_20261107_01/README.md`, containing anonymized aggregates only.

This attribution is scheduled as the next bounded step in the existing error-analysis phase. It does not reopen the stopped BIRD-dev ranking campaign.
