# Amendment 001: smoke input helper

- Date: 2026-11-23.
- First smoke attempt: `smoke_5q_20261123_01` stopped during input preparation. The archived P1 input helper constructs `SchemaNode` records with a required `token_count`; requesting tokenizer-free input omitted that field and raised `TypeError`.
- The attempt ended before the query-aware scorer was loaded and before any scoring forward pass. No model inference tokens were used. Its `run_start.json` and log are preserved with the failed run.
- Correction: call the already-cached Qwen tokenizer while preparing the schema records. This only populates the helper's required token-count metadata; it does not run an embedding/model forward pass or change query/schema text, cached vectors, candidate generation, acquisition, score budget, evaluation, stop rules, or resource limits.
- The corrected smoke will use a new output directory, `smoke_5q_20261123_02`; the first attempt will not be overwritten.
