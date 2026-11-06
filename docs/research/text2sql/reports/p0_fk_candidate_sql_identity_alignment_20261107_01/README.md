# P0 FK candidate–SQL identity alignment audit

**Experiment ID:** `p0_fk_candidate_sql_identity_alignment_20261107_01`  
**Status:** `FULL_DIAGNOSTIC_COMPLETE`; the SQL-used target-pair mismatch is confirmed on the frozen 60-unit packet.
**Layer:** exploratory data-integrity diagnostic.
**Repository:** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p0-sql-used-proxy-alignment-20261107`.

## Why this diagnostic is registered

The preceding SQL-used alignment Smoke parsed 5/5 queries and resolved 8/8 qualified JOIN equalities, but found no exact candidate mapping in any of the five pairs. Its aggregate could not distinguish a selected pair that the reference SQL does not join, missing FK candidate identities, or a mismatch between direct column-pair identity and the legacy matcher. This separate registration answers that data-integrity question once; it does not restart the stopped model ranking experiment.

## Protocol

The audit freezes the same 60 question×table-pair units and the same 5/55 Smoke/Full split. It independently walks explicit SQL `JOIN ... ON` equalities, resolves qualified columns with the existing scope-aware resolver, and matches complete ordered column-pair identities from the private frozen manifest. It then compares those mapping IDs with the existing candidate-filtered `parse_gold_sql` output.

It reports the preregistered taxonomy, complete-resolution coverage, exact identity coverage, legacy-versus-independent ID agreement, and anonymous database counts. A reference-SQL-used mapping means only that the reference query used that declared FK identity; it is not a unique semantic gold label or human Role annotation.

The Smoke gate requires valid parsing/resolution, but intentionally has no candidate-match threshold. If the Smoke technical gate passes, one CPU Full pass covers the remaining 55 pairs. The audit stops after that pass. It does not load model-review outputs, rankings, checkpoints, or SQLite databases, and it computes no ranking or SQL execution metric.

## Registration evidence

- Preregistered plan: [plan](../../plans/p0_fk_candidate_sql_identity_alignment_20261107.md).
- Frozen config: [config](../../../../../configs/text2sql/p0_fk_candidate_sql_identity_alignment_20261107_01.json).
- Runner: `scripts/text2sql/audit_p0_fk_candidate_sql_identity_alignment_20261107_01.py`.
- Starting repository commit: `275a1d23f642a51621960990fa452ca5534655a9`.
- Initial preregistration commit: `d4341a3c20bf43b6a98305c612affe8bdc37979d` (all registration files read back from GitHub).
- Amendment 001 commit: `dc2a20274855d0089b2979324e3864351d17e64a` (runner/config/report read back before Full).
- Initial Smoke runner SHA-256: `725adf291aacf9a3b412961804996ac61cb1ad0b76a95f2ae2dd54cc8030eb52`.
- Amended Full runner SHA-256: `de00b167213c5999c953b6fba128d7ec1343e12f3b2340cd4be6b4ffb80f9f35`.
- Input hashes, environment, gates, resource limits, and exact run IDs are recorded in the config.

## Smoke result

One CPU Smoke run completed on the five frozen units. SQL parse succeeded on 5/5; all 8/8 qualified JOIN equalities resolved; scope errors were 0; all five units had complete resolution and were categorized. No target table pair appeared in a resolved qualified explicit `JOIN ON` equality in 5/5 units. The legacy candidate-filtered matcher and direct identity matcher agreed on all 5/5 units; both returned no mapping IDs. Therefore this Smoke points to pair-to-SQL target alignment or explicit-ON coverage under the registered label rule; it does not show a mapping-ID bug or a ranking result. `WHERE` and `USING` conditions are outside this registered target definition.

The Smoke technical gate passed. Wall time was 0.045199 s, process CPU 0.028640 s, peak RSS 0.634277 GiB; local model/API/GPU use was zero. The private per-unit evidence remains local.

## Amendment 001 before Full

Post-Smoke review found the runner omitted the preregistered minimum of 50/55 fully resolved queries from its Full gate. The Smoke result remains valid because all five Smoke queries had complete resolution. Amendment 001 adds that existing threshold to the runner before any Full data is read. It changes no sample, label, metric, taxonomy, or budget. The amended code and config must be pushed and read back before the single Full pass.

## Full result

The amended runner completed the one registered Full pass on all remaining 55 units. Parse succeeded for 55/55; all 68/68 qualified JOIN equalities resolved; scope errors were 0. The target pair was absent from resolved explicit `JOIN ON` equalities in 55/55. The direct identity matcher returned no mapping IDs, and the legacy matcher agreed on 55/55; there were zero exact candidate matches and zero ID disagreements. Together with Smoke, this is 60/60 selected pairs with no target-pair equality under the registered explicit-ON rule, across four anonymous databases with 15 pairs each.

This explains why the prior SQL-used evaluation found 0/5 candidate mappings: the selected table pairs do not occur as explicit qualified JOIN equalities in their paired reference SQL. It does **not** establish that the pair is absent from every SQL construct. `WHERE` equalities and `USING` joins are outside the registered label rule. The finding is a pair-to-SQL target/coverage mismatch for this evaluation; it does not indicate a mapping-ID bug, missing mapping columns for an observed target equality, or model ranking failure.

Full resource use: 0.114961 s wall time, 0.098878 s process CPU, peak RSS 0.634277 GiB. Across Smoke and Full, wall time was 0.160160 s and process CPU 0.127518 s. GPU, local model, external API, SQL execution, and confirmed model tokens were all zero.

## Reproduction record

Repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p0-sql-used-proxy-alignment-20261107`. The Smoke used commit `d4341a3c20bf43b6a98305c612affe8bdc37979d`; Full used the preregistered Amendment 001 commit `dc2a20274855d0089b2979324e3864351d17e64a`. Environment: existing Conda `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0; no dependency changes. CPU-only, 8-thread cap; no random sampling occurred because the frozen split was reused.

The exact Smoke and Full launch commands are preserved in `/mnt/liansp3/logs/gfmrag_p0_fk_candidate_sql_identity_alignment_20261107_01/launch_manifest.json` and `full_launch_manifest.json`. Runtime logs are `smoke_001.log` and `full_001.log`. Private row-level output is under `/mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_sql_identity_alignment_20261107_01/`; no raw SQL, names, IDs, or row-level evidence was uploaded.

## Decision and next step

Stop this diagnostic. Do not score the existing 60 review-packet pairs against reference-SQL-used mappings. A follow-up method experiment would need a newly frozen sample whose table pairs are derived from fully resolved SQL JOIN equalities and whose candidate FK identities include those equalities; it must be registered independently and remain explicitly conditional on a known SQL table pair. This report does not launch or claim that ranking experiment.

The final public aggregate is in [aggregate_summary.json](aggregate_summary.json). Raw SQL, table/column names, mapping IDs, and pair-level evidence remain private.
