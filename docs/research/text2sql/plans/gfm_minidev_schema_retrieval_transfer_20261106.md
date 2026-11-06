# G-reasoner on reviewed Mini-Dev: schema-retrieval transfer screen

**Experiment ID:** `gfm_minidev_schema_retrieval_transfer_20261106_01`

**Status:** preregistration; no model result yet.

**Layer:** one exploratory checkpoint-transfer diagnostic.

## Why this is the next bounded question

The local model-review proxy route has completed. On its frozen FK-mapping subset, G-reasoner scored 7/38 against Dense at 27/38, and the registered error analysis found no positive subgroup. That closes further work on those proxy labels. It does not answer whether the same frozen checkpoint behaves differently on whole-schema table/column retrieval.

The prior BIRD-dev schema-retrieval launch stopped before either model loaded, so it produced no scientific result. This registration uses a different question release: BIRD Mini-Dev's 2026 human-reviewed SQLite snapshot. It is a query-set transfer screen, not an independent database test: the 500 questions use the same 11 databases, and the local release comparison found only 13 exact `(db_id, question)` overlaps with the archived 2025 package. The model, feature path, and task family remain related to the earlier diagnostic; this experiment makes no algorithm-novelty claim.

Recent work makes broad novelty claims inappropriate. Context-aware bidirectional retrieval and question decomposition are studied in [Rethinking Schema Linking](https://aclanthology.org/2026.findings-eacl.236/); structural subgraph induction in [Graph-Link](https://proceedings.mlr.press/v306/zhong26s.html); retrieve-expand-refine in [REaR](https://www.microsoft.com/en-us/research/publication/rear-retrieve-expand-and-refine-for-effective-multitable-retrieval/); dual full/pruned schemas in [DSR-SQL](https://aclanthology.org/2026.emnlp-main.1688/); and hierarchical multi-database linking in [MDB-Link](https://arxiv.org/abs/2608.09588). The earlier P2d.2 error taxonomy points to SQL structure and qualifier/scope problems, while recent [Post-SQLFix](https://arxiv.org/abs/2610.41472) and [SCOPE-SQL](https://aclanthology.org/2026.findings-emnlp.951/) directly cover structured diagnostics and repair. This experiment is retained only because it tests the unanswered task-transfer distinction with a reviewed question release and a low-cost frozen-model comparison.

## Research question and hypothesis

**Question:** With the same Mini-Dev questions, database-local table/column candidates, Qwen3 vectors, membership graph, and frozen G-reasoner checkpoint, does graph propagation from Dense Top-3 table and column anchors improve Column Recall@10 over Dense cosine and the Top-1-anchor condition?

**H1:** G3 improves query-macro Column Recall@10 over D0 by at least 2.0 percentage points, has a database-cluster bootstrap 95% confidence-interval lower bound above zero, improves over G1 by at least 1.0 point, and loses no more than 1.0 point of Table Recall@10 versus D0.

The experiment may change the decision to retain or stop frozen G-reasoner for this retrieval task. It cannot establish cross-database generalization, SQL execution gain, FK-role accuracy, or a new schema-linking method.

## Conditions and feature contract

| Condition | Scoring | Start nodes |
|---|---|---|
| D0 | Qwen3 cosine | None |
| G1 | Frozen G-reasoner | Dense Top-1 table and Top-1 column per database |
| G3 | Frozen G-reasoner | Dense Top-3 tables and Top-3 columns per database |

- Query text is only the current question. The BIRD `evidence` field, SQL, database rows, Gold labels, model-review outputs, FK candidates, and business-role annotations are excluded from features.
- The graph contains only bidirectional table/column membership edges. It has no FK edges.
- Schema passages use the pinned 2026 SQLite DDL: table name; column name, declared type, and owning table name for columns. Values and database descriptions are absent. This differs from the earlier BIRD-dev R1 text and means absolute scores must not be compared as a controlled R1-vs-DDL ablation.
- Dense, G1, and G3 share identical vectors, graph nodes, candidates, and stable node-ID tie-breaking. Query embeddings use the frozen G-reasoner query instruction. Relation passages are fixed as `Relation: table contains column.` and `Relation: column belongs to table.`
- The GPU runner receives label-free questions and schema files. It reads the private SQL-derived Gold labels only after all predictions and rankings are written.

## Data and label gate

- Source: `birdsql/bird_mini_dev` immutable revision `38818fcbc46038129592680c51b2c8b597aac27c`, file `data/mini_dev_sqlite.jsonl`; release manifest `Mini-Dev 1024`, revision `colleague_review_fixes_20261025`; license CC BY-SA 4.0. The BIRD project announced its human-in-the-loop correction/replacement update on 2026-10-28.
- Questions: 500; databases: 11; question SHA-256 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`.
- Schema: official SQLite DDL JSON, SHA-256 `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b`.
- Label extraction is CPU-only SQLGlot scope analysis. Physical table references are resolved against DDL. Physical columns are followed through direct CTE/subquery projections; output aliases are not counted as schema columns. `USING`, wildcard-only, ambiguous, unresolved, or otherwise untraceable column cases remain ineligible for the column metric. Their counts are reported; they are not model-reviewed or silently assigned labels.
- Before any Qwen/G-reasoner load, require SQL parse coverage of at least 98%, at least 495/500 resolvable table-labeled questions, at least 490 table-labeled questions in the 495-question Full split, at least 450 column-eligible questions in Full, and all 11 database clusters represented in Full. The deterministic Smoke split must contain five table-labeled questions and at least four column-eligible questions. If any condition fails, stop after the CPU audit.
- Deterministically select 5 questions from 5 distinct databases by SHA-256 ordering of the experiment ID, `db_id`, and source question key. They form Smoke and are excluded from Full. The exact selection and all per-question labels stay local.

## Metrics and decision gates

- Primary: query-macro Column Recall@10 on column-eligible Full questions.
- Guards and diagnostics: Table Recall@5/@10, Column Recall@5/@10/@20, Column Precision@10, per-database deltas, and rescued/damaged/unchanged questions.
- Uncertainty: 10,000 paired bootstrap draws over the 11 database clusters, seed `20261106`.
- Transfer signal passes only if all four H1 thresholds pass. Any failed threshold is `NO_GO`; there is no K, seed, graph, relation-text, checkpoint, or prompt sweep afterward.
- Smoke requires 5/5 selected questions over 5 databases, 5 table-labeled cases, at least 4 column-eligible cases, finite vectors/scores, correct graph membership, and one G1 plus one G3 forward per question. Smoke is excluded from Full metrics.
- If the parser gate or Smoke fails, retain the record and stop; do not alter this experiment ID or reuse its output directories.

## Budget and reproducibility

- One idle RTX 4090, at most 8 GiB allocated GPU memory; 8 CPU threads; at most 8 GiB process RSS; 900 CPU seconds and 1,200 wall seconds per stage.
- Reuse the existing `gfmrag_greasoner_20261022` Python 3.12.15 environment, Qwen3-Embedding-0.6B 1024-D snapshot, its pinned file manifest (`quadgraph_20261014_p0_model_files_sha256`), and frozen G-reasoner-34M checkpoint. Verify the per-file Qwen hashes and manifest before loading; no downloads, dependency changes, fine-tuning, SQL execution, or external API calls.
- Local Qwen tokenizer input tokens are recorded per embedding batch through the shared usage ledger. Local generation tokens are zero; GPU and CPU time are reported separately.
- CPU label prep and model runs use new, unique result/log paths under the registered experiment namespace. Private SQL, questions, table/column names, per-question predictions, and raw logs are never committed.
- Repository: `https://github.com/bArtyom/gfm-rag`; branch `research/gfm-minidev-schema-retrieval-20261106`. The public registration/code commit must be pushed and read back before Smoke. The public report and anonymous aggregate belong in `docs/research/text2sql/reports/gfm_minidev_schema_retrieval_transfer_20261106_01/`.

## Stop and claim boundary

This is one query-set transfer diagnostic on the same 11 databases. Even a passing result permits only a separately registered independent-database replication proposal. It does not reopen model-proxy FK ranking, repair claims, or the stopped BIRD-dev attempt. A failed parser gate, Smoke, resource check, or H1 gate ends this branch.
