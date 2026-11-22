# BizWeave low-FK Spider business-graph pilot

**Run ID:** `bizweave_spider_low_fk_graph_20261122_001`  
**Status:** completed; exploratory, single database.  
**Evidence level:** Spider 1.0 train questions and Gold-SQL table/JOIN proxies; no human business-semantic labels.

## Question and decision

Can a local model draft a schema-linked business graph for a Spider database with few declared foreign keys, using only schema evidence? Does ranking with that graph improve table retrieval over BM25 on the raw schema?

**Decision:** the model produced a structurally valid graph and preserved the one declared FK. The preregistered Recall@3 gate was exceeded by only 0.48 percentage points (99.52% vs. 99.04%). The graph reduced Recall@1 by 32.21 points and MRR from 0.926 to 0.740; typed propagation also scored below flat graph text on Recall@1 and Recall@2. The graph had four nodes, all typed as entities, one edge, and no unresolved claims. Its natural-language definitions went beyond what the schema fields establish. This run therefore shows that Qwen can produce a schema-bound draft, but it does not show a reliable business ontology or a useful retrieval gain. Stop this run and do not tune its prompt.

## Frozen question, budget, and information boundary

The hypothesis was that Qwen2.5-Coder-7B-Instruct could build a schema-grounded graph for a low-FK Spider database and that typed graph retrieval would improve table Recall@3 over raw-schema BM25. The registered narrow success signal required valid JSON, schema-valid bindings and evidence IDs, at least one proposed join observed in the reference SQL, and typed-graph Recall@3 above the raw-schema baseline.

This was one exploratory database, one local model generation, a five-question CPU smoke, then one frozen evaluation of all 104 selected training questions. The stop rule prohibited retries, prompt tuning, extra models, SQL execution, and dev/test inspection. No external model API was called.

Graph generation saw only Spider table names, column names and types, primary-key markers, and the one declared FK pair. It did not see questions, Gold SQL, database rows, or query results. The train questions and SQL entered only after the graph was frozen, for table-use and observed-JOIN proxies. SQL was parsed but not executed.

## Dataset selection

The immutable official Spider 1.0 archive has 166 schemas and 7,000 train questions across 140 databases. The schema audit found two zero-FK databases: `student_1` (two tables, 68 train questions) and `company_1` (six tables, seven questions). The preregistered rule required at most two FK pairs, at least four tables, and at least 50 questions, then preferred fewer FKs and more questions. It selected `bike_1`: four tables (`station`, `status`, `trip`, `weather`), one declared FK column pair, and 104 train questions.

The archive is `/mnt/liansp3/sources/datasets/spider_official/spider_data_20261107_confirmed.zip`, SHA-256 `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`. `tables.json` SHA-256 is `61bb20aa401f03164e2d7f3b16509b7b5f79cc9c943ca7bd159046df1159e2ed`; `train_spider.json` SHA-256 is `c43d0d72e59e1a9e1a60837da9bf70d5a6277226bdb7f634d544f380646f527a`. The schema-only model input SHA-256 is `2f3754baf41c4dab982ec7f2cc79940dd6a143908832f0894463cf8c812f2699`.

`bike_1` is a low-FK, not zero-FK, test. Spider's schema file has no business descriptions, so table and column identifiers alone cannot verify event meaning, time basis, grain, cardinality, or metric definitions.

## Model-generated graph and evidence checks

The graph has four nodes and one edge, with no duplicate node IDs. Its only proposed physical join is the declared `status.station_id → station.id` FK; the candidate uses the correct `declared_fk` status. It is observed in the reference SQL. There were five distinct JOIN column pairs in the 104-query set, so the candidate has 1.00 precision and 0.20 recall against that SQL-use proxy.

All four physical table bindings, all 46 column bindings, and all 60 evidence-ID references resolve to the supplied schema input. The exact declared FK is preserved, and there are no join-status violations. These are structural checks only: evidence-ID validity does not show that a cited schema token entails a business claim.

All four nodes were typed `entity`; the graph had no event, state, time-basis, metric, or grain node and no unresolved entry. For example, its descriptions call `trip` a user journey and `weather` current conditions, although the input provides identifiers and types rather than documentation establishing those meanings. This is a qualitative post-run observation, not a formal semantic annotation. The generated graph stays local at `/mnt/liansp3/sources/results/bizweave_spider_low_fk_graph_20261122_001/generation_001/graph.json`.

## Retrieval results

All methods rank the same four physical tables. `schema_bm25` uses table and column names, types, primary-key markers, and declared-FK text. `flat_graph_bm25` uses generated node text mapped to physical tables. `typed_graph` adds a fixed 0.25 one-hop neighbor contribution. All 104 SQL statements parsed; none was executed.

| Method | Recall@1 | Recall@2 | Recall@3 | Complete table coverage@3 | MRR |
|---|---:|---:|---:|---:|---:|
| Raw schema BM25 | **71.63%** | **89.42%** | 99.04% | 98.08% | **0.926** |
| Flat graph text | 41.35% | 86.06% | 99.52% | 99.04% | 0.761 |
| Typed graph, one-hop | 39.42% | 79.81% | **99.52%** | **99.04%** | 0.740 |

The only threshold-crossing result was the small Recall@3 difference; flat and typed graph text tie there, while the raw-schema baseline ranks relevant tables much earlier. Recall@3 is near ceiling in a four-table database. No confidence interval or significance claim is made.

The five-question smoke had zero SQL parse failures and structurally valid graph bindings, but no observed JOIN pairs. It was a pipeline check and is not pooled with the 104-question result.

## Interpretation and next decision

This is evidence that a local LLM can map schema elements into a graph-shaped JSON object while preserving a declared FK in a low-FK Spider schema. It is not evidence that the graph captures business semantics: the model made plausible but under-supported definitions and did not represent the event/state/time/grain distinctions the research idea needs. It is also not evidence of better table retrieval: raw-schema BM25 has much stronger Recall@1, Recall@2, and MRR, while the graph's small Recall@3 difference is near a four-table ceiling.

The main research direction remains a provenance- and verification-aware mapping from business event, state, time basis, and grain to physical columns and candidate paths, with unresolved status when evidence is insufficient. “Build a business table/graph” by itself is not supported as a differentiating contribution by this experiment. Further prompt tuning on `bike_1` is stopped. A next research stage should first inspect real business documentation and independently reviewed ambiguity labels, such as the existing Spider 2.0-Lite data plan, before running another model experiment.

## Execution record

- **Project repository:** `bArtyom/gfm-rag`, branch `research/bizweave-event-constraints-20261117`. Preregistration commit: [`a55d87035ff455260652e97698a60ecf128adc08`](https://github.com/bArtyom/gfm-rag/commit/a55d87035ff455260652e97698a60ecf128adc08). The preregistration's config, plan, and four scripts were read back from GitHub and matched by blob SHA before inference. The final report and anonymous aggregate are published in a subsequent commit.
- **Reference materials read:** repository `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md`; Spider's [official repository](https://github.com/taoyds/spider) and [official dataset page](https://yale-lily.github.io/spider). No third-party upstream repository was modified.
- **Code and config:** run-specific preparation, generator, audit, and evaluator are in `scripts/research/bizweave_spider_low_fk_graph_20261122_001/`; frozen config is [`configs/text2sql/bizweave_spider_low_fk_graph_20261122_001.json`](../../../../../configs/text2sql/bizweave_spider_low_fk_graph_20261122_001.json), and protocol is [`the preregistration plan`](../../plans/bizweave_spider_low_fk_graph_20261122_001.md). No core GFM-RAG API was changed. The evaluator's `evaluation_code_commit` field records the worktree base HEAD `63c2787d849b359ad1a71818b8286f46669a0728`; the exact evaluator file content is the preregistered GitHub blob `ecaa9fbeb39300dfe004a2fe2640f716ebe607e9` in commit `a55d87035ff455260652e97698a60ecf128adc08`.
- **Model:** local `Qwen2.5-Coder-7B-Instruct`, `/mnt/liansp3/sources/models/qwen25-coder-7b`; config, tokenizer-config, and weight-index SHA-256 values are frozen in the linked config. The request returned HTTP 200 and valid JSON in 26.790 seconds, with 7,187 input, 1,201 output, and 8,388 total tokens. The shared ledger records exactly one call with usage. External API cost: CNY 0.
- **Runtime:** inference Python 3.10.20, vLLM 0.8.5, PyTorch 2.6.0, Transformers 4.51.3; evaluation Python 3.9.20, SQLGlot 30.8.0 in `gmn_alphasql`. No package was installed or upgraded. vLLM used BF16, GPU 1 only, context 32,768, maximum generation 4,096, eager execution, one sequence; the request used temperature 0, seed 20261122, and JSON-object mode. The startup log reported Hugging Face generation defaults; the effective request log showed repetition penalty 1.1. The evaluator emitted a SQLGlot/sqlglotrs deprecation warning, with no parse failures.
- **Resources:** before startup GPU 1 had 24,161 MiB free and 0% utilization; GPU 0 and GPU 3 were already occupied by other processes and were not used. RAM available was 427 GiB with 192 CPU cores; port 8780 was free. vLLM loaded 14.248 GiB of model weights; peak observed GPU 1 use was about 19,915 MiB. The model server ran for about three minutes (roughly 0.05 GPU-hours, estimated from the launch/log window) and was stopped after the generation. GPU 1 returned to 403 MiB used and port 8780 was no longer listening. Local GPU time is reported separately and is not assigned a currency price.
- **Commands:** input preparation: `conda run -n gmn_alphasql python3 scripts/research/bizweave_spider_low_fk_graph_20261122_001/prepare_spider_inputs.py --config configs/text2sql/bizweave_spider_low_fk_graph_20261122_001.json`. Service launch and one generation request are recorded in `/mnt/liansp3/logs/bizweave_spider_low_fk_graph_20261122_001/inference_001/launch_manifest.json`; request stdout and server log remain local. Evaluation commands used the same run config, first with `--limit 5`, then over all selected tasks.
- **Local artifacts:** result root `/mnt/liansp3/sources/results/bizweave_spider_low_fk_graph_20261122_001/`; logs `/mnt/liansp3/logs/bizweave_spider_low_fk_graph_20261122_001/`. The model graph, raw response, Spider question text/SQL, per-question rankings, and logs are local only. This repository contains the protocol, source code, this report, and anonymous aggregate metrics.
- **Limitations:** one database and one generation; Spider identifiers provide weak semantic evidence; no evidence-entailment audit, human labels, confidence intervals, cross-database replication, model-contamination check, or SQL execution. Gold SQL usage is only a retrieval/JOIN proxy, not a unique business-correct answer.

## Anonymous aggregate

See [`aggregate.public.json`](aggregate.public.json). It includes only run-level metrics and hashes; it contains no questions, SQL text, model graph, or per-question scores.
