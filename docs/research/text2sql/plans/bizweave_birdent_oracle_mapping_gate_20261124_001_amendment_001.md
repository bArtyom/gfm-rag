# BIRD-Ent Oracle Mapping Gate — Amendment 001

**日期:** 2026-11-24
**状态:** Gold question/SQL labels not yet opened; this amendment is published before scoring.

## Reason

The BIRD-Ent task records expose `gold_table_ids` and `gold_knowledge_ids`, but no `gold_column_ids`. The preregistered primary column-recall metric therefore needs column labels derived from reference SQL after the document-to-schema mapping review is frozen. The benchmark README explains that evaluation restores Ent table and column names; use the published name-mapping files only for evaluation-label normalization.

## Frozen review artifact and evidence boundary

- The blinded mapping review is frozen at SHA-256 `ffd47bdebf172c4ed460c16f7a68f733ed70e5785c2fca63c0c6af9f9afb8934` in the private local result directory.
- The frozen audit contains 30 mapping assertions: 23 direct schema-supported assertions, 7 conflict/proposal/unresolved assertions; all 5 sampled cases have at least one supported field mapping.
- No task question, Gold SQL, `gold_table_ids`, or question-to-answer pairing was opened while preparing the mappings. Those fields may be read now only to score retrieval methods.

## Evaluation-only data and procedure

- Add `BIRD-Ent/table_name_mappings.json` and `BIRD-Ent/column_name_mappings.json` from the same pinned revision. These files are evaluation-only. They must not enter the blind mapping packet, oracle graph construction, or retrieval features.
- Parse `original_SQL` with the already installed SQLGlot version in `qes_rear_refine`; use the published name mappings to resolve source identifiers to Ent table/column IDs. Do not execute SQL. Keep parser failures, ambiguous references, and unresolved columns in the denominator report; do not silently drop them.
- The primary metric remains gold-required column Recall@10 where a SQL-derived column set can be resolved. Gold table Recall@5 is reported on all selected cases using `gold_table_ids`. If a case has no resolvable column labels, mark its column metric unavailable and state the denominator; do not replace it with an invented label.
- All other sampling, blindness, method definitions, BM25 parameters, candidate universes, and resource/stop gates remain as in the original preregistration. No model or API calls, GPU, package installs, or SQL execution are added.
