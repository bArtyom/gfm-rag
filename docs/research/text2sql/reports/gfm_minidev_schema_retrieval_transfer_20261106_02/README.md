# Mini-Dev schema retrieval transfer `_02`: stopped at CPU label gate

**Experiment ID:** `gfm_minidev_schema_retrieval_transfer_20261106_02`

**Run ID:** `gfm_minidev_schema_retrieval_transfer_20261106_labels_002`

**Status:** `STOP_LABEL_GATE_FAILED`; no model ranking result.

**Layer:** exploratory frozen-checkpoint query-set transfer screen.

## Research question and decision rule

The question was whether frozen G-reasoner propagation from Dense Top-3 table and column anchors improves query-macro Column Recall@10 on BIRD Mini-Dev 2026 reviewed questions, compared with Dense cosine and Top-1 anchors, without materially reducing Table Recall@10. The registered Full gate required at least 450 column-eligible questions, all 11 database clusters, and the registered performance thresholds. See the [base plan](../../plans/gfm_minidev_schema_retrieval_transfer_20261106.md), [Amendment 001](../../plans/gfm_minidev_schema_retrieval_transfer_20261106_amendment_001.md), and [config](../../../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106_02.json).

The CPU label gate failed: Full had 340 eligible questions out of 495, below the required 450. Qwen, G-reasoner, GPU ranking, Smoke, and Full were not started. The hypothesis is untested; no retrieval metric is available.

## Reference repositories and guidance

- Project and experiment record: `https://github.com/bArtyom/gfm-rag`, branch `research/gfm-minidev-schema-retrieval-20261106`.
- The registration, amendment, code, and `_01` failure record were read back from this user-owned repository before execution. The exact `_02` source tree was `2d584f1bc43a6da184603b1f598ad8212bd35358`; the public preregistration commit was `7c11648c018e5daa9dc8852f856282595508c6ab`. The local execution commit was `f11aa93ffcfd2e24a0fa972f699cbf880cb7b9e2` with the same tree.
- Upstream implementation reference: `https://github.com/RManLuo/gfm-rag`, commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0. The frozen checkpoint was not loaded in this run.
- The repository's README, Text2SQL research README, experiment roadmap, and reproducibility contract were followed. Amendment 001 records the initial hash and environment failures; this report records the recovery gate result.

## Data, code, and runtime

- Dataset: BIRD Mini-Dev 2026 reviewed SQLite, Hub revision `38818fcbc46038129592680c51b2c8b597aac27c`; 500 questions and 11 databases.
- Question SHA-256: `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`.
- SQLite schema SHA-256: `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`.
- Gold labels were derived by SQLGlot 28.0.0 scope analysis against the pinned SQLite DDL. Ambiguous or unresolved physical columns made the whole question column-ineligible. Gold labels and SQL were not model features; no model ran.
- CPU environment: `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0. The CPU script checked the active environment, input hashes, and clean source commit before parsing.
- Model environment, Qwen snapshot, and G-reasoner checkpoint were preregistered but unused. No packages were installed or changed.
- Resource use: CPU wall 0.985 s, process CPU 0.933 s, peak RSS 33,030,144 bytes (31.5 MiB); GPU time and GPU forwards 0.

## Command and sample

The label audit used the deterministic five-question Smoke split from five distinct databases; those cases were excluded from the 495-question Full split. No random seed was used for SQL parsing. The script recorded command arguments and hardware snapshot in the private preparation manifest.

```bash
conda run -n think2sql_20260909 "$THINK2SQL_PYTHON" \
  scripts/text2sql/prepare_minidev_schema_retrieval_inputs.py \
  --questions "$MINIDEV_QUESTIONS" \
  --sqlite-schema "$MINIDEV_SQLITE_SCHEMA" \
  --output-dir "$PRIVATE_RESULTS/prepared_002" \
  --expected-commit f11aa93ffcfd2e24a0fa972f699cbf880cb7b9e2
```

`THINK2SQL_PYTHON`, `MINIDEV_QUESTIONS`, `MINIDEV_SQLITE_SCHEMA`, and `PRIVATE_RESULTS` resolve to the registered local environment and source aliases. No model inference API or database SQL execution was used.

## Results

| CPU audit measure | Observed | Gate |
|---|---:|---:|
| SQL statements parsed | 500/500 (100%) | pass, ≥98% |
| Questions with physical table labels | 500/500 | pass, ≥495 |
| Full questions with table labels | 495/495 | pass, ≥490 |
| Smoke column-eligible questions | 4/5 | pass, ≥4 |
| Full column-eligible questions | 340/495 (68.69%) | **fail, ≥450** |
| Full database clusters with column labels | 11/11 | pass, 11 |
| Overall label statuses | 344 eligible; 156 unresolved/ambiguous | reported |
| Schema graph inventory | 76 table nodes; 800 column nodes | recorded |

The audit summary used the condition name `at_least_10_full_database_clusters`; the frozen threshold in code/config was 11, and the observed count was 11, so this label mismatch did not affect the failed column-coverage gate. The parser reports unresolved and ambiguous cases in one bucket; it does not attribute their sub-causes.

## Conclusion and stop

This is a label-coverage failure, not evidence for or against G-reasoner. The 5-question GPU Smoke and 495-question model run were blocked by the preregistered gate. No same-ID parser change or model run is authorized by this registration. Any follow-up must first diagnose the 156 unresolved/ambiguous cases under a separate bounded CPU analysis and register new IDs before another retrieval run.

Private files remain under `sources/results/gfmrag_minidev_schema_retrieval_20261106_02/prepared_002/`; the private launch log remains under `logs/gfmrag_minidev_schema_retrieval_20261106_02/`. This public report and its [anonymous aggregate](aggregate_summary.json) contain no questions, SQL, evidence, database names, labels by row, or predictions.

Token use: local model input/output/total 0/0/0; external inference API calls 0; unknown-usage requests 0. Estimated external API cost: CNY 0. GPU compute cost/time: 0. CPU use is reported separately above.
