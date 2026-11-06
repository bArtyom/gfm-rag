# P0: FK candidate–SQL identity alignment audit (2026-11-07)

**Status: preregistered, not run.** Experiment ID: `p0_fk_candidate_sql_identity_alignment_20261107_01`.

## Research question and core hypothesis

The prior SQL-used label Smoke parsed 5/5 SQL queries and resolved 8/8 qualified JOIN-ON equalities, but found zero exact FK mappings in the frozen candidate set. Its public aggregate could not tell whether the selected table pair was absent from the reference SQL, the SQL columns did not match any frozen FK identity, or the candidate-filtered parser/ID alignment was wrong.

This bounded CPU audit asks: **Which of those mechanisms explains the zero-of-five candidate matches?** It independently extracts resolved qualified JOIN-ON column-pair signatures for each selected table pair, matches those signatures against the frozen mapping identities, and compares the resulting mapping IDs with the existing candidate-filtered matcher.

The diagnostic hypothesis is that a row-level identity alignment audit will distinguish the failure source without changing the SQL parser, candidate set, rankings, model outputs, or reviewer labels. This is not a method-performance hypothesis and does not claim that a reference SQL mapping is the unique semantically correct Role.

## Layer, budget, success criterion, and stopping rule

- Layer: one `exploratory_data_integrity_diagnostic`; no main-line performance evidence.
- Frozen sample: the same 60 question×table-pair units and same split as the previous SQL-used alignment audit: 5 Smoke units and 55 Full units, with no overlap.
- Smoke budget: one CPU pass over the 5 frozen Smoke units.
- Full budget: one CPU pass over the 55 remaining units, only if the Smoke technical gate passes.
- Smoke gate: 5/5 SQL parses, zero scope-analysis errors, complete resolution of every qualified JOIN equality in each Smoke query, and one taxonomy category assigned per unit. Candidate mapping hits are deliberately not a gate.
- Full sufficiency criterion: at least 54/55 SQL parses, zero scope-analysis errors, at least 50/55 queries with complete qualified JOIN-equality resolution, and all 55 units categorized. Otherwise stop as technically inconclusive; do not retry or expand.
- Stop after this one Full pass. No parser tuning, sample replacement, model calls, reviewer calls, SQL execution, ranking metrics, or GPU use.

## Frozen comparisons and taxonomy

The audit uses SQLGlot 28.0.0 with the SQLite dialect and the same scope-aware alias/column resolver as the prior label extractor. It separately walks the SQL AST and records resolved equality signatures by JOIN and alias pair. Candidate identities are matched directly against those signatures, requiring every ordered column pair of a composite FK to occur in the same JOIN and alias pair. The legacy candidate-filtered helper is run once on the same SQL, solely to compare mapping IDs.

Each unit receives exactly one primary class:

1. `SQL_PARSE_FAILURE`
2. `SCOPE_ANALYSIS_FAILURE`
3. `INCOMPLETE_QUALIFIED_JOIN_RESOLUTION`
4. `NO_TARGET_PAIR_EQUALITY_IN_EXPLICIT_ON`
5. `EXACT_MATCH_BOTH_AGREE`
6. `EXACT_MATCH_BOTH_ID_DISAGREEMENT`
7. `EXACT_MATCH_INDEPENDENT_ONLY`
8. `EXACT_MATCH_LEGACY_ONLY`
9. `PARTIAL_COMPOSITE_MAPPING_MATCH`
10. `TARGET_PAIR_ON_EQUALITY_NO_CANDIDATE_IDENTITY_MATCH`

Primary outputs are taxonomy counts, the number of exact candidate identities under complete SQL resolution, and legacy-vs-independent mapping-ID agreement. Secondary outputs are anonymous database-level counts and parser counters. These are coverage/integrity findings, not ranking accuracy.

Interpretation is fixed before reading the sample:

- Any fully resolved independent exact match that the legacy helper misses indicates a matcher/ID-alignment discrepancy.
- A fully resolved SQL equality for the target table pair with no exact frozen mapping indicates that the candidate identities do not cover the reference SQL-used equality (or the selected mapping universe is misaligned).
- A fully resolved query with no target-pair equality indicates a selected-pair/reference-SQL mismatch for this evaluation target.
- Incomplete SQL resolution makes that unit inconclusive; it must not be counted as evidence of candidate absence.
- Agreement between the two matchers with no candidate hit rules out only the tested helper-vs-identity discrepancy; it does not prove the FK candidate source is correct.

## Data and privacy

- BIRD dev original local snapshot: 1,534 questions.
- Frozen candidate packet: 60 question×table-pair units; same private manifest and split as experiment `_02`.
- Input hashes are pinned in `configs/text2sql/p0_fk_candidate_sql_identity_alignment_20261107_01.json`.
- This run reads no model reviewer responses, no rank predictions, no checkpoint, no SQLite database, and no generated SQL.
- Raw SQL, question text, database IDs, table/column names, mapping IDs, and per-unit evidence remain in mode-0600 private output. GitHub receives only this protocol, code, config, aggregate class counts, and anonymized database counts.

## Environment and resources

- Repository: `https://github.com/bArtyom/gfm-rag`, branch `research/p0-sql-used-proxy-alignment-20261107`.
- Starting commit: `275a1d23f642a51621960990fa452ca5534655a9`.
- Environment: existing `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0. No installation or upgrade.
- CPU only; maximum 8 threads, 600 seconds wall time, 300 seconds process CPU, 4 GiB peak RSS. No GPU, local model, external API, training, or new download.
- Inputs: the pinned BIRD `dev.json`, `dev_tables.json`, pair-level private manifest, and frozen Smoke/Full split. The runner checks every SHA-256 before reading records.

## Reproduction

Run from the repository root after the registration commit has been pushed and read back:

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
scripts/text2sql/audit_p0_fk_candidate_sql_identity_alignment_20261107_01.py \
--mode smoke \
--run-id p0_fk_candidate_sql_identity_alignment_20261107_01_smoke_001 \
--expected-commit <registered-commit> \
--repo-root . \
--config configs/text2sql/p0_fk_candidate_sql_identity_alignment_20261107_01.json \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_sql_identity_alignment_20261107_01/smoke_001
```

Run Full only after the Smoke technical gate passes, replacing `smoke` with `full` and the run/output IDs with `..._full_001`.

## Deviations and expected claims

The prior roadmap calls for error-mode synthesis after the model-proxy rank experiment. This audit is a single, CPU-only follow-up explicitly recommended by the `_02` report because its 0/5 result left the cause unidentified. It does not reopen the stopped ranking line. The repository roadmap and experiment report will record this deviation and its stopping point.

No claim about G-reasoner, Dense ranking quality, SQL execution accuracy, unique business Role, or cross-database generalization is authorized by this diagnostic.
