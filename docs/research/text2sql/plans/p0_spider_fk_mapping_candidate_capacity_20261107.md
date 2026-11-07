# Spider FK Mapping Independent-Replication Capacity Audit

**Status: Amendment 001 preregistered after Smoke 001 stopped before data access.** Run IDs: Smoke 001 is closed; use `p0_spider_fk_mapping_candidate_capacity_20261107_01_smoke_002`, then `p0_spider_fk_mapping_candidate_capacity_20261107_01_full_001` if Smoke passes.

## Why this audit

The frozen BIRD-dev proxy-label ranking pilot was strongly negative for G-reasoner versus Dense Cosine, and the same BIRD candidate pool is closed to further tuning. The next falsifiable question is whether that result transfers to a database-disjoint benchmark. Spider 1.0 is suitable for an independent replication screen because its official task separates databases across train and test. This audit only checks whether the official test split has enough eligible multi-FK mapping cases to justify a later model-review/ranking registration.

This is not a model result, a label-quality result, a semantic-join claim, or evidence for/against G-reasoner. No SQL is executed and no model or GPU is used.

## Frozen source and inputs

- Project: `https://github.com/bArtyom/gfm-rag`; current branch `research/p0-sql-used-proxy-alignment-20261107`; source HEAD before registration: `067f382abf7c4000822b1204f2199c081dd3c3b3`.
- Guidance read before registration: root `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md`.
- Dataset: official Spider 1.0 archive from Yale-LILY, CC BY-SA 4.0; local unified entry `/mnt/liansp3/sources/datasets/spider_official/spider_data_20261107_confirmed.zip`; SHA-256 `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`.
- Read only `spider_data/test.json`, `test_gold.sql`, and `test_tables.json` from the archive. Train/dev data and SQLite contents are not read.
- SQLGlot resolves qualified explicit `JOIN ... ON` equalities through scope-local physical table aliases. `USING`, derived/CTE-unresolved sources, unqualified equalities, non-FK joins, and pairs without at least two distinct declared FK column mappings are excluded and counted by reason.
- Data alignment must be exact between `test.json` and `test_gold.sql`; SQL parse success must be at least 98%, with zero scope-analysis errors. Lower coverage stops the transfer route rather than triggering parser tuning in this registration.
- Spider's FK metadata exposes column pairs, not composite constraint identity. The audit counts distinct declared column-pair mappings only; a later experiment must preserve this limitation and must not call them reconstructed composite constraints.

## Protocol, budget, and gates

- Layer: feasibility audit preceding a possible independent replication; no result-dependent tuning.
- Population: one ambiguous table pair per test question, selected by fixed SHA-256 ordering after extracting explicit JOIN-ON table pairs. Selection and smoke assignment do not use model outputs.
- Smoke: five questions selected by sorting `SHA256("p0_spider_fk_mapping_candidate_capacity_20261107_01:" + db_id + ":" + question_index)`; every selected question is excluded from Full. Smoke is a parser/data-path check only.
- Full: one pass over the remaining official test questions. No retries under the same run ID, no parser threshold changes, and no extra dataset rows.
- Capacity gate for a later registration: at least 60 eligible question×table-pair units across at least four anonymous databases after Smoke exclusion. A future model-review sample would be frozen at 60 units and would require at least 30 high-confidence model-adjudicable labels, at least 20 distinguishable accepted sets, and at least three databases before any ranking forward.
- Resource caps: CPU-only; 600 seconds wall, 300 CPU seconds, 4 GiB RSS. The machine check on 2026-11-07 found all four GPUs occupied; this audit does not request GPU time.
- Runtime: existing Conda `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0. Smoke 001 mistakenly launched in `gfmrag_greasoner_20261022`, which lacks SQLGlot; it stopped at import before hashing or reading the archive. Amendment 001 changes only the environment and Smoke run ID. No dependency installation, source data read, or output directory creation occurred.
- Stop on archive hash mismatch, missing/misaligned test SQL, SQL parser/scope error above the reportable gate, missing schema/FK metadata, resource-limit breach, or output path collision. Preserve the failed run and do not alter the source data.

## Outputs and privacy

- Runner: `scripts/text2sql/audit_p0_spider_fk_mapping_candidate_capacity.py`.
- Frozen config: `configs/text2sql/p0_spider_fk_mapping_candidate_capacity_20261107_01.json`.
- Private local output and logs: `/mnt/liansp3/sources/results/gfmrag_p0_spider_fk_mapping_candidate_capacity_20261107_01/` and `/mnt/liansp3/logs/gfmrag_p0_spider_fk_mapping_candidate_capacity_20261107_01/`.
- Public report: `docs/research/text2sql/reports/p0_spider_fk_mapping_candidate_capacity_20261107_01/`.
- Public material contains only aggregate counts, anonymous database histograms, code/config hashes, and the decision. Questions, SQL, database names, table names, mapping identities, and per-question records remain private or in memory only.
- If the gate passes, separately register model review and ranking before any model inference. Model judgments will remain proxies, not human consensus. If the gate fails, stop this transfer route and synthesize current evidence.

See [Amendment 001](amendments/p0_spider_fk_mapping_candidate_capacity_amendment_001.md) for the environment correction and closed Smoke 001 record.

## Decision and interpretation

The audit can only choose between `CAPACITY_SUFFICIENT_FOR_MODEL_PROXY_REPLICATION` and a documented stop/inconclusive state. Passing permits one separately registered, frozen exploratory replication; it does not guarantee that the G-reasoner ranker can run under available GPU resources. No experimental conclusion may be generalized from this capacity check.
