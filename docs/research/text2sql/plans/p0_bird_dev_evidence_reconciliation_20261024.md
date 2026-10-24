# P0 BIRD-dev evidence reconciliation

**Status: preregistered; audit run pending.** Experiment ID: `p0_bird_dev_evidence_reconciliation_20261024_01`.

## Research question and scope

Can the existing BIRD-dev P0 evidence be reconciled to the current GFM-RAG P0 checklist, and what claims are supported about table/column labels versus FK-role labels? This is a CPU-only, read-only evidence audit. It reuses the completed `quadrag_p0_20261014` artifacts and current GFM-RAG FK identity reports. It is not a new SQL parse, embedding run, retrieval experiment, or human annotation study.

## Hypothesis and decision target

The archived P0 v3 audit and encoder check can support a frozen BIRD-dev table/column inventory if source hashes still match. They do not by themselves establish a trustworthy hard Role set: SQL-derived FK matches and multi-FK candidate queries are candidates for review, not adjudicated business-role labels. The expected decision is table/column-only evidence with a Role gate of `NO_GO` unless a trusted, blinded review artifact exists.

## Frozen inputs and provenance

- BIRD dev is development/diagnostic data, not an independent test set. Canonical links: `/mnt/liansp3/sources/datasets/bird/dev/dev.json`, `/mnt/liansp3/sources/datasets/bird/dev/dev_tables.json`, and `/mnt/liansp3/sources/datasets/bird_dev_databases`.
- Reuse P0 v3 aggregate `/mnt/liansp3/sources/results/quadrag_p0_20261014/full_audit_v3.json` (SHA-256 `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`) and encoder-health aggregate `/mnt/liansp3/sources/results/quadrag_p0_20261014/encoder_health.json` (SHA-256 `f0dc51f3fb37668a72a58bf7395b6fe1fce964e734201389e1bc3817698efe4a`). Historical implementation source: `bArtyom/quadrag@a8f6d1f22c9c683b11639418aa50ac1de0433270`; new report and audit artifacts go only to `bArtyom/gfm-rag`.
- Expected content hashes: `dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`; `dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`; 86 SQLite/CSV inputs totaling 1,493,364,802 bytes, with individual hashes frozen in the P0 v3 artifact. Qwen config hash is `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`; weights use the already-verified local Qwen3-Embedding-0.6B snapshot, SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`.
- Current GFM-RAG FK follow-ups: `g2_fk_instance_quality_20261024_01` (final report commit `79f2bba7d1065a75c2bf4baf1d905d056ceb3473`) and duplicate-identity policy report (commit `0bf7dc357bdcfdb86895d8e3c83518542a634ebf`). G0-02 synthetic result commit at registration is `b69e43929bee7e64601222639635e28ebeaa9e87`.

## Registered evidence and checks

The historical aggregate reports 1,534/1,534 SQLite-dialect SQL parses; at least one Gold table and one resolved Gold column for all 1,534; complete referenced-column resolution for 1,460, with 74 unresolved; 1,140 queries with a JOIN `ON` clause; 956 queries matching a declared FK instance; and 174 multi-FK table-pair candidate queries. Those 174 are an unreviewed candidate pool, not a Role-hard set with trusted labels.

Across 11 databases and 75 tables, P0 v3 recorded 86 hashed database inputs, 102 schema-JSON FK pairs, 103 SQLite FK instances, 0 composite FK instances, and JSON/SQLite FK-pair differences in 2 databases. The later FK identity gate used a separate normalization and reported 103 declarations, 100 effective mappings, 3 invalid declarations, and a duplicate-identity collision. Preserve these counting definitions side by side; do not force them into one count without row-level evidence.

The existing encoder health check used five inputs and reported `[5,1024]` output, no non-finite values, 1024-D raw norms 87.6761/115.8207/118.0208 (min/median/max), repeat cosine min/median 0.99999994/1.0 and max absolute difference 0. It is historical local inference; this audit must not rerun the encoder.

## Success criteria, budget, and stop conditions

- Audit execution succeeds only if both dataset JSON hashes, all 86 frozen SQLite/CSV hashes, both aggregate artifact hashes, and the local model config fingerprint match the registered values, and the aggregate counters are read without exporting question text, SQL, or row-level predictions.
- Decision output must explicitly distinguish table/column coverage from FK-instance candidates and trusted Role labels. If no double-reviewed, blinded Role labels exist, record `ROLE_GATE_NO_GO`; do not claim Role Accuracy or start Role supervision.
- Budget: at most 300 CPU seconds, 4 GiB RSS, 1.5 GiB database-file reads; GPU 0, model/API calls 0, SQL execution 0, training 0, downloads/installs 0.
- Stop immediately on a missing input, symlink drift, any hash mismatch, a broken aggregate invariant, or resource cap. Preserve the mismatch evidence and do not repair/overwrite source data.
- P0 audit success is distinct from scientific gate success. Even with all hashes matching, the Role gate remains `NO_GO` without trusted dual review. The output may authorize only already-supported table/column claims; it cannot authorize a new P1 role-accuracy sweep.

## Outputs and report boundary

- Private verification summary and `sha256sum` log: `/mnt/liansp3/sources/results/gfmrag_p0_bird_dev_evidence_reconciliation_20261024_01/` and `/mnt/liansp3/logs/gfmrag_p0_bird_dev_evidence_reconciliation_20261024_01/`.
- Public report: `docs/research/text2sql/reports/p0_bird_dev_evidence_reconciliation_20261024_01/README.md`; public aggregate only, with file hashes/counts and no question, SQL, or database content.
- There are no implementation changes to GFM-RAG. The local audit uses only JSON metadata, file hashing, and the already frozen summary artifacts.

## Repository guidance

This registration follows `experiment-roadmap.md`'s P0-only immediate task and `reproducibility-contract.md`'s P0 acceptance list as read at `b69e43929bee7e64601222639635e28ebeaa9e87`. It records the full BIRD-dev set as repeatedly used development data, retains the prior FK/schema `NO_GO`, and does not treat the synthetic G0 result as Role evidence.
