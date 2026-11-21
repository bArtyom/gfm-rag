# BizWeave: zero-FK business graph feasibility pilot

**Run ID:** `bizweave_bird_zero_fk_graph_20261121_001`

**Status:** preregistered; model generation and retrieval evaluation not yet run.

**Evidence level:** one-database exploratory feasibility only; not mainline paper evidence.

### Pre-inference amendment 1 — context capacity

The first tokenizer-only preflight counted 19,573 input tokens, so the originally registered 8,192-token serving limit could not fit the frozen schema-only prompt plus the 4,096-token output reserve. Before any model request, the serving context was amended to 32,768, which matches the local model configuration. The prompt, data boundary, model, evaluation, and success/stop criteria were not changed. The run remains on one selected GPU with `gpu_memory_utilization=0.82`, one concurrent sequence, and eager execution; if the memory gate fails, inference stops without a paid-API fallback. The failed context preflight is preserved under the local run directory and did not make a model request.

## Research question

Can a local model convert schema and column documentation into a source-grounded business-semantic graph for a database with no declared foreign keys? Does typed graph retrieval help recover the physical tables referenced by held-out questions compared with BM25 over the same database's raw schema documentation?

The pilot uses BIRD train's `public_review_platform` database: 15 tables, zero declared foreign keys, and 381 question/SQL examples. Its table/column description CSVs make it possible to distinguish “the model can draw a graph” from “the graph is tied to evidence.” The BIRD train questions and SQL are reserved for evaluation; neither is sent to the model.

## Core hypothesis

A Qwen-generated graph with business concepts, physical table/column bindings, evidence IDs, and candidate relation edges can recover useful relationships in this zero-FK database and improve retrieval over raw-schema BM25.

This is a bounded feasibility check. BIRD Gold SQL table references and JOIN predicates are weak retrieval/usage proxies. They are not human labels for the only correct business interpretation. A positive result will not establish semantic correctness, ambiguity resolution, or cross-database generalization.

## Frozen data and information boundary

- Schema: `/mnt/liansp3/sources/datasets/bird/train/train_tables.json`, SHA-256 `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b`.
- Tasks: `/mnt/liansp3/sources/datasets/bird/train/train.json`, SHA-256 `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520`.
- Model-visible sources: only the selected database's schema names, primary-key metadata, and `database_description/*.csv` field/value descriptions.
- Excluded from graph generation: all questions, Gold SQL, database row values, and execution results.
- Evaluation-only sources: question text and Gold SQL table/JOIN references. SQL will not be executed.
- Input and hash manifests remain local. No dataset rows, questions, SQL, or per-query predictions will be committed.

## Baselines and metrics

Candidate tables are fixed to the same 15 tables for every method.

1. `schema_bm25`: BM25 over table names, column names, and available column/value descriptions.
2. `flat_graph_bm25`: BM25 over generated node text flattened by each physically bound table.
3. `typed_graph`: BM25 relevance for mapped nodes plus a fixed 0.25 one-hop neighboring-node contribution through generated graph edges. It uses the same node text and physical bindings as the flat baseline; only graph connectivity changes. No parameters will be tuned on these questions.

Report mean table Recall@1/3/5, complete Gold-table coverage@1/3/5, MRR, parse failures, exact-schema physical binding validity, evidence-ID validity, and candidate JOIN-edge precision/recall against observed Gold-SQL JOIN predicates. Report every denominator.

## Execution budget and gates

- One local generation request with `Qwen2.5-Coder-7B-Instruct`; one GPU, no training, no external API, no paid API.
- Maximum 4,096 generated tokens; maximum 30 minutes of allocated GPU time; CPU audit/evaluation maximum 30 minutes.
- Success signal: valid graph structure; every physical binding resolves against the frozen schema; cited evidence IDs exist; at least one proposed physical JOIN is observed in the reference SQL; and typed-graph Recall@3 or MRR is above raw-schema BM25.
- Stop after one generation and one frozen CPU evaluation. No prompt tuning, retry, or expanded model sweep if the gate fails.
- Any positive outcome remains exploratory because this is one database from BIRD train and labels are SQL-derived.

## Novelty boundary

Constructing a generic schema KG and using it for retrieval is already close to enterprise text-to-SQL work. BEAVER itself includes annotations for multi-table retrieval, join-key detection, column mapping, domain knowledge, and query decomposition. A 2026 preprint, *Schema-Free Text-to-SQL: Learning Enterprise Database Structure from Query Logs*, builds a knowledge graph from SQL logs and applies entity-driven GraphRAG. Therefore, “use an LLM to build a graph” or “the database has few foreign keys” is not, by itself, the proposed contribution.

The candidate differentiator remains an evidence-grounded business mapping layer that explicitly represents event/state, time basis, metric grain, physical join candidates, evidence provenance, and unresolved status—and uses those constraints to select among genuinely competing implementations or abstain. This BIRD Yelp-like pilot checks only graph construction and retrieval feasibility; it does not test those harder claims. Spider 2.0-Lite remains a separate next data-review route for richer enterprise documentation; this pilot does not replace its review protocol.

## Reproducibility references

- Project experiment config: [`configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json`](../../../../configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json).
- Official BIRD benchmark: <https://bird-bench.github.io/>.
- Spider 2.0-Lite official repository: <https://github.com/xlang-ai/Spider2>.
- BEAVER benchmark annotations: <https://beaverbench.github.io/>.
- Related 2026 preprint: <https://arxiv.org/abs/2610.33946>.
