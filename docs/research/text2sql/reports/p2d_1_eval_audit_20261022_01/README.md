# P2d.1 attempt 01 — stopped before SQL replay

**Status:** failed during frozen-input validation; no evaluator result was produced. This records an execution-wrapper defect, not a finding about SQL correctness or evaluator-v2 coverage.

## Registered objective

Evaluate whether the v2 read-only evaluator can safely handle a limited set of stored-column date/time expressions while preserving every result that the frozen v1 evaluator could already compare. The run followed the preregistered CPU-only Gate 1/2 protocol at [the experiment plan](../../plans/p2d_1_frozen_prediction_eval_audit_20261022.md), protocol SHA-256 96773cc235f932b416c2a461017314d93aa5cf9654ae41800bc3e564de415a89.

## Execution record

- Source commit: [3b979b4](https://github.com/bArtyom/gfm-rag/commit/3b979b4ce69aa088297b2f9ca20a87fbc3364391)
- Start: 2026-10-22 06:46:29 UTC; environment think2sql_20260909, Python 3.12.14.
- CPU-only; no model, paid API, or GPU calls.
- The synthetic safety suite passed: **136 passed, 0 skipped**.
- Frozen-input validation then stopped before any saved SQL was executed: **0 references, 0 predictions replayed**. Gate 1 parity did not run; Gate 2 was not started.

## Failure cause

The frozen prediction manifest and its payload are separate files with separate hashes. The manifest file prediction_seal.json hashes to f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3; the manifest records the distinct predictions_private.json payload hash e88bf42f22a73b6b56af96a5d3ea88d69252c33509bb72da5b8cfde2f7474ea5. The runner incorrectly used the manifest-file hash to validate both files, so it stopped during input loading. Input seals and frozen data were not modified.

The fix separates these two checks and adds a synthetic regression test. It is published in [commit 40245f0](https://github.com/bArtyom/gfm-rag/commit/40245f0745f04ae2d90c271c491e89d63f00a71d); the relevant safety-test set now passes **137 tests**. The sealed-payload loader was also checked against all 90 frozen predictions without executing SQL.

## Interpretation and recovery

This attempt provides no v2 score and no evidence for or against the evaluator hypothesis. The original P2d v1 results remain unchanged at E0/E1/E2 confirmed Set/Bag **8/7/8 of 30**, with **11/12/10 unknown**. The recovery is separately preregistered as [p2d_1_eval_audit_20261022_02](../p2d_1_eval_audit_20261022_02/experiment_config.json), on a new output root and under the same protocol and budgets. This failed attempt's output and log remain preserved; its run ID will not be reused.
