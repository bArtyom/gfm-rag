# BizWeave Spider low-FK graph pilot

**Run ID:** `bizweave_spider_low_fk_graph_20261122_001`  
**Status:** preregistered before model inference.  
**Evidence level:** one Spider train database; SQL-derived retrieval/JOIN proxies; no human business-semantic labels.

## Question and hypothesis

Can a local model construct a schema-grounded business graph for a low-FK Spider database when only identifiers, SQL types, primary keys, and the declared FK are available? Does adding the generated typed graph to table ranking recover more Gold-SQL table references than BM25 over the same raw schema information?

The graph-generation inputs exclude every natural-language question, Gold SQL string, database row, and query result. Questions and SQL are loaded only after the graph has been frozen, for retrieval and observed-JOIN-use proxies. SQL will not be executed.

## Dataset selection and boundary

The archived official Spider 1.0 package has 166 schemas and 7,000 `train_spider` questions across 140 databases. The audit found two zero-FK databases: `student_1` (2 tables, 68 train questions) and `company_1` (6 tables, 7 train questions). Under the preregistered selection rule—at most two FK column pairs, at least four tables, at least 50 train questions, then prioritize fewer FKs and more questions—`bike_1` is selected: four tables, one declared FK column pair, and 104 train questions. The audit uses no dev/test samples.

Spider 1.0 `tables.json` has no business column descriptions. The model will see only table/column identifiers, SQL type names, primary-key indicators, and the exact declared FK pair. Identifier-derived event, role, metric, time, or grain interpretations remain unverified. No database is extracted from the 1.83 GB expanded archive; the scripts read only the required JSON members directly from the immutable ZIP.

Frozen archive: `/mnt/liansp3/sources/datasets/spider_official/spider_data_20261107_confirmed.zip`, SHA-256 `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`. Schema member SHA-256: `61bb20aa401f03164e2d7f3b16509b7b5f79cc9c943ca7bd159046df1159e2ed`. Train-task member SHA-256: `c43d0d72e59e1a9e1a60837da9bf70d5a6277226bdb7f634d544f380646f527a`.

## Frozen comparison

All methods use the same four-table candidate universe and question set:

1. `schema_bm25`: table and column names, types, primary-key markers, and declared-FK text.
2. `flat_graph_bm25`: generated node text mapped to its physical table.
3. `typed_graph`: the same generated text and mappings with a fixed 0.25 one-hop neighbor contribution through generated edges.

Report table Recall@1/2/3, complete Gold-table coverage@1/2/3, MRR, SQL parse failures, physical binding validity, evidence-ID validity, declared-FK preservation, and candidate JOIN precision/recall against JOIN pairs observed in the reference SQL. Gold SQL is only a proxy: its use does not prove the reference path is the unique business-correct path. No confidence interval or cross-database claim is planned for this single database.

## Budget, gates, and stop rule

- One local Qwen2.5-Coder-7B-Instruct graph-generation request; no paid API, training, SQL execution, prompt tuning, or retry.
- GPU 1, BF16, maximum 32,768-token context, one sequence; maximum 0.5 GPU-hours. CPU evaluation limit 30 minutes.
- Run a five-question CPU evaluator smoke after generation, then the frozen full 104-question evaluation. This adds no model calls.
- Feasibility signal: valid JSON; every reported physical table/column binding and evidence ID resolves; at least one proposed join pair appears in a reference SQL JOIN; and typed-graph Recall@3 exceeds raw-schema BM25.
- Stop after this single run regardless of outcome. Invalid output, missing resources, or an inference error is recorded and not retried.

## Risks and interpretation

The two-table zero-FK `student_1` is too small to meaningfully stress graph-based table retrieval. `bike_1` provides a larger, still low-FK schema and enough train questions for an exploratory comparison. Its missing business descriptions make this a test of what schema identifiers and the declared FK alone support; it cannot establish evidence-grounded enterprise semantics. The Qwen model may also have seen Spider examples during pretraining; contamination is not tested here. A positive retrieval signal remains exploratory and does not establish business-meaning accuracy or Text-to-SQL execution gains.

## Exact code and artifacts

- Selection audit: `scripts/research/bizweave_spider_low_fk_graph_20261122_001/audit_spider_low_fk.py`.
- Input freezer, one-call generator, and evaluator are in the same run-specific script directory.
- Config: `configs/text2sql/bizweave_spider_low_fk_graph_20261122_001.json`.
- Local result root: `/mnt/liansp3/sources/results/bizweave_spider_low_fk_graph_20261122_001/`.
- Local logs: `/mnt/liansp3/logs/bizweave_spider_low_fk_graph_20261122_001/`.
- Run code under the self-maintained `bArtyom/gfm-rag` project repository and branch `research/bizweave-event-constraints-20261117`; do not publish Spider questions, SQL, model graph, per-question scores, or logs.

## References

- Spider 1.0 official benchmark repository and task description: <https://github.com/taoyds/spider>.
- Official Spider dataset page and download information: <https://yale-lily.github.io/spider>.
