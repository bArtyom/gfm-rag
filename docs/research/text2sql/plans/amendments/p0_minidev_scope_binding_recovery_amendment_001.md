# P0 Mini-Dev scope-binding recovery amendment 001

**Status:** registered before retry. This amendment corrects one frozen input-hash transcription and permits one new Smoke attempt. The method, sample selection, metrics, thresholds, and resource budget remain unchanged.

## First attempt

- `smoke_001` ran from source commit `2eb4dbff90d3a9acd886dfc8c320e6299833b053` and stopped at the input-hash assertion before reading the dataset JSONL, selecting SQL rows, or creating its output directory.
- The preserved log is `/mnt/liansp3/logs/gfmrag_p0_minidev_scope_binding_recovery_20261106_01/smoke_001.log`.
- The dataset hash and previous taxonomy-summary hash matched the registered values. The registered schema hash had a transcription error. Recomputed SHA-256 for `/mnt/liansp3/sources/datasets/bird_mini_dev_2026_reviewed/sqlite_schema.json` is `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`.
- No SQL was read, no model/API was called, no GPU was used, and no experiment output or row-level result was produced by attempt 001.

## Recovery

- Correct only `schema_sha256` in the frozen config to the value above. Keep all other input files, hashes, parser logic, five deterministic Smoke questions, fixtures, thresholds, and budgets unchanged.
- Preserve `smoke_001` and use the distinct attempt/output path `smoke_002/`, with the amended source commit recorded in its manifest and log.
- If and only if `smoke_002` passes its preregistered gates, run the single permitted Full attempt as `full_002/`, consuming the exact `smoke_002/private_summary.json`.
- Do not run any further parser variant or retry after attempt 002. If the corrected hash gate or a substantive Smoke gate fails, stop and report it.

## Accounting and privacy

- The amendment does not increase the original CPU limit of 8 threads, 4 GiB RSS, and 1,200 seconds per run. Smoke and Full remain CPU-only, with no dependency changes, model inference, external API, or SQL execution.
- Logs and private summaries remain outside GitHub. Public materials contain only the correction rationale, implementation, and anonymous aggregates; no raw question, SQL, database/table/column name, per-question label, or private digest is published.
