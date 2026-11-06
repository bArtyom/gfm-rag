# Amendment 001: Mini-Dev input hash and interpreter recovery

**Applies to:** `gfm_minidev_schema_retrieval_transfer_20261106_01`

**Recovery registration:** `gfm_minidev_schema_retrieval_transfer_20261106_02`

**Status:** amendment registered; recovery CPU label audit not yet run.

## Why the first registration stopped

The `_01` CPU preflight verified the 500-question file, then stopped before SQL parsing because the registered SQLite schema SHA-256 did not match the current file. The registration contained `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b`; a fresh hash of the configured source path is `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`. The question-file hash matched. The first run ID is closed and its failure record is preserved at [report `_01`](../reports/gfm_minidev_schema_retrieval_transfer_20261106_01/README.md).

The command also resolved `python3` to Python 3.9.20 although it requested the existing `gfmrag_greasoner_20261022` environment. The first plan also assigned SQL parsing to the model environment, which does not contain SQLGlot. The existing `think2sql_20260909` CPU environment provides Python 3.12.14 and SQLGlot 28.0.0; the model environment provides Python 3.12.15. Both interpreter paths are invoked explicitly inside `conda run`, and each script checks its environment before processing inputs. No dependencies were installed or changed.

## Recovery scope

The `_02` registration uses a separate experiment ID, stable question IDs, run IDs, and output directories. It keeps the same research question, 500-question reviewed Mini-Dev release, 11 databases, Dense/G1/G3 conditions, features, labels, metrics, thresholds, and resource caps. It changes only:

1. The schema input hash to the observed value above, while retaining the same source alias and release revision.
2. The CPU label stage to use `think2sql_20260909` / Python 3.12.14 / SQLGlot 28.0.0, and the model stages to use `gfmrag_greasoner_20261022` / Python 3.12.15. Each stage invokes the explicit environment interpreter and checks its versions before processing inputs.
3. The experiment/run identifiers and private output paths, so the stopped `_001` evidence is immutable.

The recovery config is [gfm_minidev_schema_retrieval_transfer_20261106_02.json](../../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106_02.json). The hypothesis and all acceptance/stop rules remain as originally registered in the [base plan](gfm_minidev_schema_retrieval_transfer_20261106.md). A failed `_002` hash gate still stops before model load; there will be no additional recovery under this amendment.

## Recovery run IDs

- CPU label audit: `gfm_minidev_schema_retrieval_transfer_20261106_labels_002`
- Five-question Smoke: `gfm_minidev_schema_retrieval_transfer_20261106_smoke_002`
- Conditional Full: `gfm_minidev_schema_retrieval_transfer_20261106_full_002`

Smoke and Full run only if the frozen CPU label gates pass. Full runs only if the five-question Smoke passes, and excludes those five questions.
