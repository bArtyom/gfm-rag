# Mini-Dev schema retrieval transfer: registration `_01` stopped before labels

**Experiment ID:** `gfm_minidev_schema_retrieval_transfer_20261106_01`

**Run ID:** `gfm_minidev_schema_retrieval_transfer_20261106_labels_001`

**Status:** `STOP_INPUT_HASH_MISMATCH`; no scientific result.

**Layer:** exploratory frozen-checkpoint query-set transfer screen.

## Question and hypothesis

The preregistered question was whether frozen G-reasoner propagation from Dense Top-3 table and column anchors improves query-macro Column Recall@10 on the reviewed BIRD Mini-Dev question release over Dense cosine and the Top-1-anchor condition, while preserving Table Recall@10. The registered thresholds, conditions, and stopping rules are in the [plan](../../plans/gfm_minidev_schema_retrieval_transfer_20261106.md) and [config](../../../../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106.json).

This run stopped during input verification, before SQL parsing, labels, embeddings, or ranking. It does not test the hypothesis.

## Registration and inputs

- Project repository: `https://github.com/bArtyom/gfm-rag`, branch `research/gfm-minidev-schema-retrieval-20261106`.
- Public registration commit: `719efad69fd6adf88d138c3f86b263a8d0dce799`. The code and documentation tree was read back from GitHub and matched the local tree.
- Dataset: BIRD Mini-Dev 2026 reviewed SQLite, pinned Hub revision `38818fcbc46038129592680c51b2c8b597aac27c`; 500 questions, 11 databases.
- The question-file SHA-256 matched the preregistered value: `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`.
- The SQLite schema-file SHA-256 did not match. The registration expected `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b`; the current local source file produced `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`.
- No SQL parsing or label extraction began. The failure happened after hashing the two inputs and before the script created the prepared-data directory.

## Runtime and resources

- The first plan incorrectly assigned CPU SQL parsing to `gfmrag_greasoner_20261022`; that model environment does not include SQLGlot. The existing CPU environment is `think2sql_20260909` / Python 3.12.14 / SQLGlot 28.0.0. The model environment is `gfmrag_greasoner_20261022` / Python 3.12.15.
- The command used `conda run -n gfmrag_greasoner_20261022 python3 ...`, but `python3` resolved to the separate `python39` environment, Python 3.9.20. A later read-only check confirmed the explicit interpreters in both intended environments report their registered versions. Recovery pins each interpreter and checks the stage environment before reading or parsing inputs.
- Qwen and G-reasoner were not loaded. GPU forwards: 0. External inference API calls: 0. Local model input/output tokens: 0/0. No model cost was incurred.
- The failed command log is retained locally under the registered private log namespace; it contains only the hash-gate error and runtime path evidence.

## Decision

The `_001` run ID is closed and will not be retried. The frozen config contained a schema-hash transcription error, while the launcher selected an unintended interpreter. A separate `_02` registration records the observed input hash and explicit target-environment interpreter. It keeps the same research question, features, metrics, budgets, and stop rules, uses fresh run IDs and result directories, and must pass a new CPU label gate before any model load.

The [anonymous aggregate](aggregate_summary.json) records the failure. No per-question data, SQL, evidence, or predictions are included.
