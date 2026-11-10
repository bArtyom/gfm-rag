# Steiner sub-schema downstream SQL experiment

User-authorized next step 2026-11-10; exploratory. One hypothesis: frozen Steiner
sub-schemas reduce generation input tokens without materially reducing SQL Set EX
versus full schema, using identical question/evidence and a fixed local generator.
Three arms only: full schema, unit-cost Mehlhorn schema, query-weighted Mehlhorn
schema. Frozen k3 selections from the sealed1534 weighted experiment; no reranking,
new embeddings, solver/weight/prompt tuning, Jev, candidate voting or SQL repair.
This is single-generation utility evaluation, not a full DeepEye reproduction.

Owned bArtyom/gfm-rag branch research/steiner-sql-pilot-20261110, localbase5350b83,
publicparent377e7ec93dad2f786b1f5a181fcf8dfc39ecec03. Read repository README,
text2sql hub/roadmap/contract, current reports, frozen serializer and existing
p2d_sql_evaluator. Legacy stopped protocols remain unchanged; this explicit user
request authorizes downstream SQL as a new stage. Use existing independent clone.

## Frozen protocol

- BIRD-dev1534/11DB aligned snapshot/eleven hashes and sealed old selection SHA
 232d5ff471f9f06181929aa1148c853e42c8172c28f6fdda373c0434dc959e3b.
- Question+provided evidence identical across all generator arms; retrieval seeds
  remain historical question-only. Same serializer for full/unit/weighted; all
  selected-table columns and intra-schema legitimate FK constraints retained.
- Primary pilot100: deterministic hash seed20261110, round-robin DB-balanced,
  chosen before opening reference SQL for evaluation. Five pilot questions are
  engineering smoke (reused once in pilot via exact response cache, not counted as
  independent evidence). Diagnostic cohort all37 questions whose unit/weighted
  table sets differ, reported separately; no population estimate from that cohort.
- Local Qwen2.5-Coder7B existing weights, tokenizer/model manifest pinned before
  serving. Greedy temperature0/top_p1/n1/seed20261110/max_new_tokens1024, fixed
  prompt asks exactly one SQLite SELECT, no repair/retry/prompt sweep.
- Model context16384; every prepared prompt chat-tokenized before service startup,
  no truncation. No reference SQL/gold table fields in prepared online inputs.
- Reuse identical payloads within this run once (model/prompt/sampling exact SHA);
  deterministic shared response across arms. Report physical requests/tokens once
  in shared ledger, and logical per-arm token requirements separately. No old SQL
  responses imported, no charging cached calls as new model requests.
- 5-question/3-arm smoke before pilot100+37diagnostics. Engineering gate requires
  valid local responses/usage/EOS and at least one executable SQL per arm, no
  missing inputs. Evaluation failures/limits stay in full selected denominators.
- Expand to all1534 only if pilot weighted EX >= full EX-1question AND weighted
  logical prompt-token reduction >=15%. Diagnostic cohort never controls expansion.
  Otherwise stop after pilot/diagnostic and report. Positive gate authorizes one
  full run with same settings, no further datasets/models. Full final criterion:
  Set EX within1pp of full and prompt reduction>=15%, descriptive DB-cluster CI.

## Resources and accounting

- Existing qbridge_vllm085_20260829 service environment, existing target CPU env.
  No installation/download/quantization/external paid fallback.
- No usable local service at preflight. GPU1,2 each~18GiB free. New loopback-only
  port19610, TP2/BF16, memory.45/card, maxseq4/batchedtokens4096, eager V0.
  Before launch twice check free>=14336MiB and remaining>=3072MiB after allocation.
  Do not interrupt other tasks; abort if resources/port unsafe.
- Service budget4wall hours/8reservedGPUh, request timeout180s, <=5000physical
  requests, <=20M input/5M outputtokens. Bounded HTTP concurrency4; stop on any
  transport/usage failure (retain unknown attempts), no paid fallback.
- Only stop service process group started by this experiment, after verifying its
  saved /proc commandline hash; cleanup in finally, record wall*2 reservedGPUtime
  separately from summed request latency. GPU/CPU cost unpriced, externalAPI0CNY.
- Existing SQLite evaluator: readonly immutable snapshots, bounded subprocess,
  timeout5s/50000rows/64MiB result/256MiBSQLiteheap. Set EX primary, Bag EX secondary,
  fixed projection order, existing float-only tolerance. Unknown/reference/limit
  cases retained and separately reported, no silent exclusions.

## Implementation/execution tasks

- [x] Tests RED->GREEN for prompt scope, same visible evidence, deterministic
  cohorting and exact-payload reuse; preparation uses online fields only.
- [x] Prepare/hash all inputs/model files and chat token lengths, persist private
  cases/manifest; commit protocol/config/code to owned branch before model calls.
- [x] Independent service startup/resource identity and logfile; smoke then
  pilot100 plus diagnostic37, seal all stage predictions before evaluating labels.
  Freeze gate decision, optionally full; no tunings based on exposed results.
- [x] Independently audit predictions/requests/shared ledger/selection hashes,
  recompute execution metrics and per-arm logical token figures, verify DBs and
  service cleanup. Appropriate tests and independent review.
- [x] Aggregate report with hypothesis/budget/source/model/data/env/commands,
  sample IDs hashed, metrics/paired outcomes/token costs/limitations; no private
  questions/SQL/prompts uploaded. Archive to docs/research/text2sql/reports/
  steiner_sql_pilot_bird_20261110_01 with GitHub commit and exact readback.

Preflight: clean existing branch,192CPU/~442GiBfree, GPU0 other active workload;
GPU1/2 suitable at initial check, no existing vLLM listener. Model alias valid.

Execution completed: main pilot gate failed; nofull. Audit PASS/96 tests. See report; GitHub archive verified after commit, not a prerequisite model claim.
