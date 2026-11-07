# Amendment 002: use the frozen model environment interpreter

**Status:** preregistered; protocol-conforming Smoke 002 has not run. Parent experiment: `p0_bird_train_fk_model_proxy_review_20261107_01`.

## Observed protocol deviation

Smoke 001 produced five valid JSON outputs per model and the private aggregator reported `SMOKE_PASS`, but the command `conda run -n think2sql_train_20260909 python ...` resolved `python` to `/root/miniconda3/envs/python39/bin/python`. That runtime is Python 3.9.20, Torch 2.5.1+cu118, and Transformers 4.57.6. The frozen runtime is Python 3.10.21, Torch 2.6.0+cu124, and Transformers 4.57.1. Therefore Smoke 001 is a protocol deviation and is excluded from all validity and agreement gates; it cannot authorize Full.

The model outputs and logs remain private in `smoke_001`. Their ledger entries are retained because ten local model calls occurred. Recorded usage was 3,608 input tokens and 531 output tokens (4,139 total); external API calls and API cost were zero. Aggregate GPU generation time was 15.107 seconds. This is reported as resource usage, not experimental evidence.

## Sole correction

Invoke the frozen environment's explicit executable through `conda run`:

`conda run -n think2sql_train_20260909 /root/miniconda3/envs/think2sql_train_20260909/bin/python ...`

Use fresh IDs `p0_bird_train_fk_model_proxy_review_20261107_01_smoke_002` and `p0_bird_train_fk_model_proxy_review_20261107_01_full_002`, with separate output directories. Keep the same 138 units, five stratified Smoke cases, private packet hashes, two local Qwen models, prompts, deterministic generation settings, confidence and agreement gates, GPU assignments, and resource thresholds. Smoke 002 must meet the original per-model 4/5 validity rule before Full 002 may start. Do not reuse Smoke 001 outputs in the aggregate.

No human labels are created. The result remains an exploratory model-proxy feasibility review. Any G-reasoner/Dense comparison still requires a separate registration.
