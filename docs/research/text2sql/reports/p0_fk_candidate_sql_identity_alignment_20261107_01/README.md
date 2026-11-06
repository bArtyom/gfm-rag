# P0 FK candidate–SQL identity alignment audit

**Experiment ID:** `p0_fk_candidate_sql_identity_alignment_20261107_01`  
**Status:** preregistered; not run.  
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
- Runner SHA-256: `725adf291aacf9a3b412961804996ac61cb1ad0b76a95f2ae2dd54cc8030eb52`.
- Input hashes, environment, gates, resource limits, and exact run IDs are recorded in the config.

## Results

No sample has been read and no run has started. Results will be appended after the registration commit is pushed and remotely verified. Raw SQL, names, mapping IDs, and pair-level evidence will remain private. The GitHub aggregate will contain anonymous counts only.
