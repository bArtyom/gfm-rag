# P0：FK 域违例的 SQLite 原生语义交叉核验

**Experiment ID:** `p0_fk_domain_violation_crosscheck_20261107_01`
**Status:** preregistered
**Layer:** bounded exploratory data/validator audit; no GFM ranking or method-effectiveness claim
**Project:** user-owned `bArtyom/gfm-rag`, branch `research/p0-sql-used-proxy-alignment-20261107`

## Pain point and question

The closed `p0_fk_mapping_counterfactual_shuffle_20261107_01` diagnostic screened 55 fixed alternative-mapping pairs. Its eligibility gate stopped at 14 pairs across two anonymous databases; 32 pairs were classified as `original_fk_domain_violation`, and 9 as a changed primary-key column. The planned counterfactual comparisons never ran. Before deciding whether this line is a dataset limitation or a validator issue, this audit asks:

> For the exact 32 fixed pairs flagged by the custom anti-join check, does SQLite's own `PRAGMA foreign_key_check` identify a violation on at least one of the same declared single-column FK mappings?

The core hypothesis is exact agreement between the existing predicate and SQLite's native FK checker for the candidate declarations in this fixed set. SQLite documents that FK comparison uses the parent-key column's affinity and collation, treats a NULL child key as satisfied, and exposes violations with the corresponding `foreign_key_list` ID through `foreign_key_check` ([FK semantics](https://www.sqlite.org/foreignkeys.html), [PRAGMA reference](https://sqlite.org/pragma.html)). This audit tests that implementation boundary on the actual declarations; it does not estimate BIRD-wide FK violation prevalence.

## Frozen scope and data

- Fixed population: exactly the 32 `original_fk_domain_violation` pairs in the prior run's `eligibility_progress_private.jsonl`; no new questions, pairs, mappings, or database snapshots.
- Provenance: reconstruct the prior 55 pairs from the exact BIRD dev manifest and Full_002 artifacts, then join by the already recorded private pair hashes. Require counts 55 total, 32 domain exclusions, 9 primary-key exclusions, and 14 eligible pairs before opening SQLite.
- Candidate declarations: target and alternate mapping for each selected pair. Both were previously verified as unique, declared, single-column FK constraints by the frozen eligibility code.
- Smoke: five fixed pairs selected by ascending `SHA256(experiment_id || pair_hash)`; it checks runner/input compatibility and produces a separate operational receipt.
- Full: rechecks the complete fixed 32-pair population in its own run directory. Smoke outputs are not pooled into the Full result.
- BIRD dev is a previously used development snapshot. Results are targeted data-integrity evidence, not an independent benchmark or general prevalence estimate.

## Method and measures

1. Verify the preregistered hashes of BIRD `dev.json`/`dev_tables.json`, the source manifest, prior Full_002 metrics/aggregate/run metadata, previous coverage-stop outputs, prior configs/runners, and all four SQLite files before parsing private manifests or opening a database.
2. Reconstruct the fixed pairs using the versioned counterfactual runner helpers and confirm the 32 frozen failure reasons by pair hash.
3. Open each required SQLite database with `mode=ro&immutable=1`, disable extensions, set `query_only`, and preserve original file hashes.
4. For each unique candidate FK declaration, rerun the original non-NULL anti-join predicate and compare its Boolean result with the declaration's `fkid` count from `PRAGMA foreign_key_check(child_table)`. Run the PRAGMA once per relevant child table and stream its rows; never store or print row values.
5. Report exact pair-level and unique-declaration agreement, disagreement, unresolved PRAGMA errors, anonymized database slices, and resource use. No confidence interval is used: the 32 pairs are a targeted census of the exclusions, not an IID sample.

**Primary metric:** pair-level agreement: both methods say at least one of the pair's two candidate declarations violates the FK domain, or both say neither does.

**Secondary metrics:** unique-declaration agreement; counts of custom-only, PRAGMA-only, both-flagged, neither-flagged, and PRAGMA-error declarations; violation-row-count distribution without raw row IDs or values.

## Decision and stop rules

- `PREDICATE_EQUIVALENCE_CONFIRMED_ON_FIXED_SET`: all 32 pairs and every uniquely identified candidate declaration are resolved and the custom checker agrees with SQLite on all of them. Treat the prior exclusions as confirmed SQLite FK violations for this targeted set. Close this counterfactual-shuffle line; do not lower its 40-pair/3-database gate or relaunch the prior run.
- `PREDICATE_DISAGREEMENT_FOUND`: at least one resolved declaration disagrees. Report the exact disagreement counts and anonymous cause category; do not reclassify or rerun the old experiment. Any corrective perturbation study requires its own registration.
- `INCONCLUSIVE_NATIVE_CHECK`: SQLite reports a schema/check error or resource limit prevents resolving a declaration. Report unresolved counts; do not infer equivalence.
- Stop on any input/database hash mismatch, wrong source count, ambiguous FK ID, dirty/unregistered code, or unsafe/read-write access. Preserve the failure receipt and do not repair inputs in place.
- One Smoke (5 pairs), then at most one Full (all 32); no additional model votes, SQL execution, perturbation, ranking, parameter search, data download, or dependency change.

## Resources, provenance, and privacy

- CPU only, maximum 8 threads, 900 process CPU seconds, 1,800 wall seconds, 4 GiB RSS, and 120 seconds per `foreign_key_check` table scan. No GPU/model/API requests.
- Reuse `think2sql_20260909` with explicit Python 3.12.14 and SQLite 3.53.2; no environment mutation.
- Reuse the user-owned repository's frozen counterfactual runner at SHA-256 `4959dce11f28be60146542a6da2c72c565f1c299b69fa0a2d73a32dea350c824` only for pair reconstruction and the already registered anti-join predicate. The original upstream reference is `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`; this audit does not execute or modify upstream code.
- Private result root: `/mnt/liansp3/sources/results/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/`; logs: `/mnt/liansp3/logs/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/`.
- Public report path: `docs/research/text2sql/reports/p0_fk_domain_violation_crosscheck_20261107_01/`. Publish only anonymized counts, hashes, code/config, and protocol. Keep DB/table/column names, question text, SQL, FK IDs, row IDs, and values local with restrictive permissions.

## Reproducibility and commands

Runner: `scripts/text2sql/audit_p0_fk_domain_violation_crosscheck_20261107.py`
Frozen config: `configs/text2sql/p0_fk_domain_violation_crosscheck_20261107_01.json`

Smoke and Full use the same checked-in runner/config and explicit `think2sql_20260909` interpreter. Exact commands, source commit, logs, input hashes, aggregate results, and any failure receipt will be added to the report after execution. The registered run IDs are:

- `p0_fk_domain_violation_crosscheck_20261107_01_smoke_001`
- `p0_fk_domain_violation_crosscheck_20261107_01_full_001`
