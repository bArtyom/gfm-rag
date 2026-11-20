# Requirement-witness budget pilot (preregistered, 2026-11-21)

**Status before inference:** protocol and configuration registered; no new model call or result yet. Initial inspection earlier on 2026-11-21 found GPU 0 idle with 24,196 MiB free. The immediate pre-launch recheck found all four GPUs at 100% utilization, only 9,173 MiB free on GPU 0, and 423 GiB available RAM. This is below the registered 20 GiB GPU launch threshold, so inference is on hold; no vLLM service was started.

CPU preflight `preflight_001` passed: the frozen questions, schema, embedding cache, node manifest and all local Qwen files matched their registered hashes; 1,534 questions / 11 databases loaded; 433 historical exclusions matched; the five smoke cases and 40 pilot cases are disjoint; the fast tokenizer loaded. The preflight made zero model requests and did not read the current questions’ reference SQL. Its private manifest is under the registered local result root.

## Source idea and scope

This pilot operationalizes the next-method hypothesis in the 2026-11-12 closure-cost report: replace one scalar relevance score for the whole question with explicit selection/filter/aggregation/comparison requirements, each linked to an exact source span and alternative schema-column/operator bindings. A selected column witnesses at most one distinct requirement. Binding choices are optimized jointly under exact foreign-key closure and serialized-schema cost; unresolved requirements remain uncovered.

The attached BizWeave proposal recommends centering the study on query-conditioned business-relation retrieval. This pilot is a narrow first slice of that online retrieval layer: it tests whether evidence-backed requirements and verifiable field witnesses help allocate a schema budget. It does not build the offline business ontology or mapping graph, mine business rules from SQL/data/docs, or evaluate business-path accuracy, grain safety, or full constraint satisfaction. A positive result would support only a separately registered BizWeave study, not the full idea.

The project’s closest-work warning remains active: question decomposition and coverage already appear in QAFD and prior Query-aware Coverage. This pilot tests a distinct source-span/witness-binding mechanism. It does not claim novelty, semantic SQL correctness, or reproduce official GRAST/QAFD results.

## Question and hypothesis

On a fixed total token budget, does explicit requirement-witness selection retain more physical columns read by the reference SQL than (1) whole-table query-cosine coverage and (2) scalar query-column cosine with FK closure, after charging the new method’s local Qwen prompt and completion tokens against its schema-context allowance?

The causal chain is: query spans → typed requirements → alternative compatible field/operator bindings → one-to-one witness assignment under shared FK/serialization cost, with a one-for-one displacement pass to withdraw an earlier binding when an uncovered requirement is more budget-efficient → more reference read bindings retained.

The hypothesis is weakened or falsified if the extractor produces invalid spans/bindings, the witness selector does not improve binding coverage over both baselines, or the gain disappears after its inference tokens reduce its schema budget.

## Frozen design

- **Repository/base:** owned `bArtyom/gfm-rag`, execution branch `research/requirement-witness-pilot-20261121`, from public experiment branch `research/closure-budget-order-20261112` at `124fd30b1548106f714d7218c9d6972dc82a4e52`.
- **Data:** frozen BIRD-dev, 1,534 questions / 11 databases; question SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`, schema SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`, aligned SQLite, Qwen3-Embedding-0.6B cache SHA-256 `c7bb9ed942aa793e34e1253a5d1d8f8d8d871c95bdfdc33718dde7396d345250`. Reuse only; no new embeddings or data download.
- **Sampling:** deterministic database-round-robin hashes. Five smoke questions use a separate salt. The 40-question pilot excludes the prior 133 SQL / 100 route / 100 QAFD cases, the 100-question closure-cost pilot, and the five smoke questions. The expected prior exclusion count is exactly 433 before smoke; any mismatch stops before inference. BIRD-dev is repeatedly exposed development data, not held-out evidence.
- **Candidate fields:** the witness prompt receives the top 32 physical columns from the frozen whole-question Qwen cosine ranking, represented by opaque IDs, table/column names, and declared types. It receives the question and supplied natural-language evidence, but no SQL, database rows, or answer. Invalid/non-verbatim source spans, unknown IDs, incompatible operators, and unresolved requirements do not become witnesses. There is one request per question and no retry.
- **Arms:** (A) whole-table query-cosine coverage; (B) all-column query-cosine ranking with deterministic FK closure; (C) local-Qwen requirement witnesses over the top-32 candidate pool, exact one-to-one assignment, shared closure and exact serialization cost. B is a repository adaptation inspired by graph-aware column retrieval, not an official GRAST reproduction. All arms use the same schemas, graph, serializer, tokenizer and cached embeddings.
- **Budget:** 2,048 Qwen2.5-Coder tokens per question for *new online inference plus final serialized schema*. For C, actual prompt+completion tokens are taken from the vLLM response and subtracted before selecting the final schema. A/B spend no new generative tokens and may use the full 2,048-token schema allowance. The cached query embeddings are shared and sunk for all arms; they are excluded from this incremental comparison. Every arm must remain within the cap.
- **Model/runtime:** local Qwen2.5-Coder-7B-Instruct only; vLLM 0.8.5, GPU 0, port 19621, one sequence, max context 4,096, max generation 256 tokens, temperature 0, seed 20261121. Existing model/env only; no API fallback, install, or model download. Every HTTP inference attempt, including failures, is recorded in the shared ledger using an opaque stable call ID; prompts and outputs are not written to that ledger.
- **Primary evaluation:** after all arm predictions are sealed, SQLite authorizer read bindings are extracted by compiling unchanged reference SQL with `EXPLAIN QUERY PLAN` against empty `TEXT` schema stubs. No SQL data-result query runs. Report macro and micro reference-read-column recall and the number of questions retaining every supported read binding. This is a structural proxy, not SQL EX or semantic correctness.
- **Diagnostics:** exact source-span validity; candidate-field recall; JSON validity; operator/type compatibility; unresolved rate; SQL prepare compatibility; table coverage; selected schema/inference tokens; budget violations; per-database paired counts; and reference-only closure feasibility as an explicitly non-deployable upper bound.

## Gates and stop rules

1. **Smoke:** five separate questions; proceed only if at least four outputs parse and validate, HTTP usage is returned for every completed call, and there is no budget invariant failure. Otherwise preserve logs, make at most one code/config amendment before any pilot request, then stop if the recovered smoke fails.
2. **Pilot success gate:** at least 36/40 questions have supported reference read bindings; the witness arm retains all bindings on at least four more questions than each baseline; its macro read-binding recall is at least 0.05 above the better baseline; valid exact source spans are at least 85%; and there are zero budget violations.
3. This is one exploratory pilot. A failed gate stops this method version. A passed gate permits only a separately registered held-out/manual-label study; no automatic confirmation, full BIRD-dev run, SQL generation, model tuning, or GPU expansion.

## Resources, artifacts and privacy

Initial resource inspection earlier on 2026-11-21: four RTX 4090s idle; GPU 0 had 24,196 MiB free; 438 GiB available RAM; 192 CPUs. Immediate pre-launch recheck: all four GPUs at 100% utilization; GPU 0 had 9,173 MiB free; 423 GiB available RAM; 192 CPUs. Reserve GPU 0 for vLLM, four CPU threads for the runner, one HTTP request at a time, 1,200 seconds, 50,000 input-token and 12,000 output-token ceilings. Stop if GPU 0 falls below 20,000 MiB before allocation or leaves under 4,096 MiB after allocation.

Python runner: existing `think2sql_20260909` Python 3.12.14, NumPy 2.2.6, NetworkX 3.6rc0, Transformers 4.57.1, SQLGlot 28.0.0, Requests 2.32.5. Inference environment: existing `qbridge_vllm085_20260829`, vLLM 0.8.5. No dependency change.

Private outputs and logs use fresh run-specific directories under `${LAB_ROOT}/sources/results/requirement_witness_budget_pilot_20261121_01/` and `${LAB_ROOT}/logs/requirement_witness_budget_pilot_20261121_01/`; smoke output stays under project `ai_temp_code/`. Public artifacts may include this protocol, config, runner, anonymous aggregate and report only. Do not upload raw questions, evidence, SQL, database contents, row IDs, prompt/response text, or per-question bindings.

## Result schema

Store the source commit/config/data/model hashes, exact command and environment, sample/exclusion counts, per-attempt input/output/total tokens and latency (without prompt/response), per-arm binding counts/recall, paired rescue/damage, span and candidate validity, token budget use, unknowns/failures, smoke and pilot decisions, CPU/RSS/GPU time, and local result/log paths. Keep failed attempts and the previous closure-cost NO-GO intact.
