# P0 BIRD-dev evidence reconciliation

**Experiment ID:** `p0_bird_dev_evidence_reconciliation_20261024_01`\
**Run ID:** `p0_bird_dev_evidence_reconciliation_20261024_01_audit_001`\
**Outcome:** `P0_TABLE_COLUMN_ONLY_ROLE_GATE_NO_GO` — all registered integrity checks passed; the Role gate remains NO-GO.\
**Run completed:** 2026-10-24 13:18:33 UTC. A separate archive readback rechecked the hashes at 13:25:12 UTC.

## Research question and scope

Can the previously completed BIRD-dev P0 evidence be reconciled with the current GFM-RAG checklist, and what claims are supported about table/column labels versus FK-role labels? This is a CPU-only, read-only evidence audit. It reuses the existing `quadrag_p0_20261014` artifacts and does not re-parse SQL, encode data, perform retrieval, or conduct human annotation.

The hypothesis and decision target were frozen in the [pre-registration](../../plans/p0_bird_dev_evidence_reconciliation_20261024.md) before execution: matching source hashes and counters can support the archived table/column inventory, but SQL-derived FK matches and multi-FK candidates are not trusted Role labels. Without blinded dual review, no Role accuracy or role-supervision experiment is authorized by this audit.

## Guidance and provenance

- Project repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p0-bird-dev-evidence-20261024`.
- Launch configuration and protocol were frozen at `d4eae8a895cdf15859fbcefe8435bde7d5b52111`; the experiment followed the repository's P0 roadmap and [reproducibility contract](../../reproducibility-contract.md) as registered at base `b69e43929bee7e64601222639635e28ebeaa9e87`.
- Historical source artifacts: `quadrag_p0_20261014/full_audit_v3.json` (SHA-256 `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`) and `encoder_health.json` (SHA-256 `f0dc51f3fb37668a72a58bf7395b6fe1fce964e734201389e1bc3817698efe4a`). Their source project commit was `bArtyom/quadrag@a8f6d1f22c9c683b11639418aa50ac1de0433270`; new reporting is archived only in `bArtyom/gfm-rag`.
- BIRD dev is a repeatedly used development/diagnostic split, not an independent test set. No model or dataset version changed during this audit.

## Method and execution

The run checked the frozen hashes for two dataset JSON files and 86 SQLite/CSV database inputs, then checked the two historical aggregates and the current local Qwen config fingerprint. It evaluated only the preregistered aggregate counters; it did not export question text, Gold SQL, table rows, or row-level predictions.

| Item | Result |
|---|---:|
| Input fingerprint checks | 88/88 passed (2 JSON + 86 database/CSV files) |
| Historical aggregate/model-config fingerprint checks | 3/3 passed |
| Database/CSV bytes in registered input set | 1,493,364,802 bytes |
| Frozen manifest SHA-256 | `cb5652f7cf071b6d482cca032b987cbe2264e8b5023e2484d7de3f8c07f0fba3` |
| Registered run timing | 10.62 s wall; 6.40 s user CPU; 0.48 s system CPU |
| Audit resource use | CPU only; no GPU, model/API calls, SQL execution, training, downloads, or dependency changes |

At archive finalization, the input hashes were independently checked again: 88/88 passed in 8.39 s wall time. The three artifact fingerprints also passed again. The archival readback did not change the registered run or any source file.

The audit ran under Bash 5.0.17, GNU coreutils 8.30, and jq 1.6. It was bounded to 300 CPU seconds, 300 seconds wall time, and a 4 GiB virtual-address limit. Peak RSS was not independently measured because `/usr/bin/time` was unavailable; the virtual-memory limit is not presented as an RSS measurement. The pre-run resource snapshot (2026-10-24 13:16:27 UTC) recorded 420 GiB available RAM, 192 logical CPUs, 114 TiB available disk, and GPU 1 busy at 92%; GPU was not needed or selected.

## Reconciled evidence

### Table and column coverage

The historical aggregate counters matched the preregistered values:

| Evidence | Count |
|---|---:|
| BIRD-dev questions with successful SQL parsing | 1,534 / 1,534 |
| Queries with at least one Gold table label | 1,534 / 1,534 |
| Queries with at least one resolved Gold column | 1,534 / 1,534 |
| Queries with all referenced columns resolved or wildcarded | 1,460 / 1,534 |
| Queries with unresolved column references | 74 |
| Databases / tables | 11 / 75 |

These are historical development-set audit counts. They are not independent test results.

### FK candidates and Role gate

The historical P0 artifact records 1,140 queries with a `JOIN ON` clause, 956 queries matched to a declared FK instance, and 174 queries with a multi-FK table-pair candidate. The 174 items are an unreviewed candidate pool; they are not a Hard Role Set and cannot be used as trusted role labels.

The schema inventory contains 102 JSON FK pairs and 103 SQLite FK instances, zero composite FK instances, and JSON/SQLite differences in two databases. These counts use different sources and definitions and must remain separate. The separate FK identity audit later found a normalized identity collision; it did not supply human role labels. No blinded dual-review labels are recorded (`trusted_role_label_n = 0`). Therefore:

- the table/column evidence is reproducible for this development split;
- the FK/Role gate is **NO-GO**;
- no Role Accuracy, Join-Path Accuracy, or SQL benefit is claimed;
- no P1 role-accuracy or dimension-sweep experiment follows from this result.

### Historical encoder health

The existing local Qwen3-Embedding-0.6B health artifact reports five inputs with output shape `[5, 1024]`, zero non-finite values, and zero maximum absolute difference on a repeated encoding. The raw 1024-D norm min/median/max were 87.6761 / 115.8207 / 118.0208; repeated cosine min/median were 0.99999994 / 1.0. This audit made **zero new encoder calls**; it rechecked the artifact and config fingerprints only. The local model config SHA-256 is `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`.

## Decision, limitations, and next action

The registered integrity audit passed, but the broader P0 scientific gate is **not passed for Role claims**. The result supports only the already audited table/column inventory on BIRD dev. It does not resolve the schema/SQLite FK differences, create an independent database holdout, validate a Hard Role Set, or provide human judgments. The absence of composite FK instances in this split also means real-data composite-FK behavior was not verified.

Next, obtain a small blinded review by two human reviewers for a frozen, privacy-controlled subset of the multi-FK candidates and resolve the FK identity policy explicitly. Until trusted labels exist, stop Role accuracy and query-conditioned Role experiments. BIRD dev remains development-only. Any later experiment must have a new pre-registration, run ID, budget, and report.

## Reproducibility artifacts

- Frozen protocol: [P0 evidence reconciliation plan](../../plans/p0_bird_dev_evidence_reconciliation_20261024.md).
- Frozen configuration and commands: [`experiment_config.json`](experiment_config.json); kept unchanged after registration.
- Public aggregate: [`result_summary.json`](result_summary.json). It contains no question text, SQL, database contents, row-level labels, or predictions.
- Private input manifests, checksum logs, and launch receipt remain under `/mnt/liansp3/sources/results/gfmrag_p0_bird_dev_evidence_reconciliation_20261024_01/` and `/mnt/liansp3/logs/gfmrag_p0_bird_dev_evidence_reconciliation_20261024_01/`.
