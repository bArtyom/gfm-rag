# P0 BIRD-dev evidence reconciliation

**Status: preregistered; preflight passed; audit pending.** Experiment ID: `p0_bird_dev_evidence_reconciliation_20261024_01`.

This bounded CPU audit will verify the existing P0 v3 input fingerprints and reconcile archived table/column, FK-instance, and encoder-health aggregates against the current GFM-RAG P0 checklist. It will not parse SQL again, invoke a model, or export raw BIRD content.

The P0 v3 artifact reports 1,534 parsed queries, 1,534 table labels, 1,460 complete column labels, 956 queries matching declared FK instances, and 174 multi-FK table-pair candidates. These candidate counts are not trusted Role labels. The FK identity follow-up found schema/SQLite differences and an identity collision; no blinded dual-review Role label set is recorded.

The audit protocol, registered hashes, resource budget, and stop conditions are in the [pre-registration](../../plans/p0_bird_dev_evidence_reconciliation_20261024.md) and [configuration](experiment_config.json). Results are pending. All source datasets, Gold SQL, and row-level outputs remain private.

Launch preflight on 2026-10-24 13:12:46 UTC passed: all registered data/model symlinks and the two historical P0 artifacts exist; output and log paths were absent. This is a CPU-only hash/metadata audit, so the busy GPU 1 was not selected. Available RAM was 420 GiB, CPU count 192, and disk available 114 TiB. The exact snapshot is frozen in the configuration.
