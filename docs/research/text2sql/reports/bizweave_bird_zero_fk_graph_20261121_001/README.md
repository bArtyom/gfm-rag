# BizWeave zero-FK business graph feasibility pilot

**Run ID:** `bizweave_bird_zero_fk_graph_20261121_001`
**Status:** completed; retain as an exploratory signal, stop this BIRD run.
**Evidence level:** one database from BIRD train; SQL-derived retrieval proxies; no human semantic labels and no cross-database claim.

## Question and decision

Can a local model build a business-semantic graph from schema documentation when a database has no declared foreign keys, and can its typed graph connections help retrieve the tables used by held-out questions?

**Decision:** the feasibility gate passed narrowly. Qwen produced a valid graph with exact schema bindings, cited evidence IDs, and eight join candidates that all occur in the reference SQL. Typed-graph table Recall@3 improved by 3.8 percentage points over raw-schema BM25, and Recall@5 improved by 6.7 points. However, top-one recall fell by 7.9 points, MRR fell from 0.871 to 0.810, and the graph contained no event, state, time-basis, metric, or grain nodes. It also returned no unresolved entries. This supports testing model-generated graph retrieval in a zero-FK setting; it does not validate BizWeave's central event/state/time/grain evidence gate. No further BIRD prompt tuning is scheduled.

## Frozen hypothesis, budget, and information boundary

The preregistered hypothesis was that a local Qwen model could create an evidence-linked graph with useful physical relations for a zero-declared-FK database and improve table retrieval over schema BM25. The registered success signal required a valid graph, exact schema bindings, at least one proposed join observed in reference SQL, and higher Recall@3 or MRR than schema BM25. The success signal passed through Recall@3; MRR did not improve.

This was an exploratory feasibility layer with one database, one graph-generation request, one GPU, a 30-minute CPU-evaluation cap, and a strict stop after one generation plus one evaluation. No model training, SQL execution, paid API, prompt retry, or second generation was run.

The model saw only the BIRD schema, primary-key metadata, and column/value descriptions. It did not see any benchmark question, Gold SQL, database row value, or query result. The 381 questions and their Gold SQL were read only after the graph was written, for table-use and join-use proxies.

## Dataset selection

The local BIRD train schema audit found 13 of 69 databases with zero declared foreign keys and 25 of 69 with at most two. This run used `public_review_platform`: 15 tables, zero declared foreign keys, 381 questions, and 15 field-description CSVs. All 381 Gold SQL statements parsed; none was executed. Schema and task file hashes are in [the anonymous aggregate](aggregate.public.json).

This makes BIRD useful as a Spider-like sparse-FK stress setting, but BIRD as a whole is not a low-FK dataset. Spider 2.0-Lite remains a separate route for richer business documentation, pending the database-level review in the existing [Spider 2.0 data plan](../../ideas/bizweave_spider2_data_plan_20261121.md).

## Model-generated graph

The output had 15 nodes and 15 edges: 11 nodes typed as entities and four as bridges. All 15 table bindings and 75 column bindings resolved against the frozen schema; all 54 evidence-ID references pointed to supplied evidence records. These are structural integrity checks only. We did not review whether each cited record semantically entails its claim.

The model emitted eight explicit physical join candidates. Each had status `unknown`; all eight column pairs were valid schema fields and appeared in at least one Gold SQL JOIN. That is 8/8 precision and 8/29 recall against the 29 distinct join pairs observed in this query set. Gold-SQL use is not proof that an edge is the only business-correct relation.

The graph contained no event, state, time-basis, metric, or grain nodes and no unresolved records. It therefore did not express the distinction this research line ultimately needs. The full graph is kept locally at `/mnt/liansp3/sources/results/bizweave_bird_zero_fk_graph_20261121_001/generation_001/graph.json`; the repository does not include the database schema or model output.

Representative generated relations were `Business → Business_Hours` (`operates_on_day`), `Business → Business_Categories` (`belongs_to_category`), and `User → Review` (`has_review`). For the first two, the model proposed physical keys `Business_Hours.business_id = Business.business_id` and `Business_Categories.business_id = Business.business_id`; both remained `unknown` verification status. These illustrate that the output is a plausible schema graph, not a reviewed business ontology.

## Retrieval results

All methods ranked the same 15-table candidate universe. `flat_graph_bm25` used the same generated node text and physical bindings as `typed_graph`; the latter added only a frozen 0.25 one-hop neighbor contribution through graph edges. There was no per-question tuning.

| Method | Recall@1 | Recall@3 | Recall@5 | Complete table coverage@5 | MRR |
|---|---:|---:|---:|---:|---:|
| Raw schema BM25 | 44.9% | 69.2% | 79.8% | 62.7% | **0.871** |
| Flat generated graph text | 36.8% | 70.1% | 83.2% | 64.3% | 0.811 |
| Typed graph, one-hop | 37.0% | **73.0%** | **86.5%** | **71.4%** | 0.810 |

The graph gained coverage when the budget rose to three and five tables, but it ranked the first relevant table worse. The retrieval result is a small, single-database proxy on BIRD train; we report no confidence interval and make no significance claim.

## Novelty boundary and next decision

Building a schema or business knowledge graph for Text-to-SQL is not enough for a novelty claim. BEAVER already annotates multi-table retrieval, join-key detection, column mapping, domain knowledge, and query decomposition. A 2026 preprint, *Schema-Free Text-to-SQL: Learning Enterprise Database Structure from Query Logs*, constructs a knowledge graph from query logs and uses entity-driven GraphRAG. “Use an LLM to build a graph” or “choose a database with few foreign keys” is therefore not the differentiator.

The remaining candidate contribution is narrower: an evidence-grounded mapping of business events and states, time basis, metric grain, and physical join candidates, with provenance and explicit unresolved status, used to select between genuinely competing implementations or abstain. The next useful step is blinded review of business-document cases in Spider 2.0-Lite (or an accessible equivalent) to verify that real alternatives and source evidence exist. Do not expand this BIRD run or claim business ambiguity resolution from these results.

## Execution record

- **Project repository:** `bArtyom/gfm-rag`, branch `research/bizweave-event-constraints-20261117`.
- **Prerecorded code/config:** local execution snapshot `3e8c86d75421a8b9f469df756e647050677c4803`; preregistration was published as GitHub commit `06c05f5df0ea095f3086b94a72212ee7383cb3d5`, and all five config/plan/script blobs were read back and matched.
- **Reference repository/worktree:** `https://github.com/bArtyom/gfm-rag`; original proposal branch head before this run was `e012eec8fb12879a31261449ceb91a3a70f8e0a4`. The model did not use third-party Spider2 or BEAVER pipelines.
- **Code changes:** added an isolated schema-only input freezer, one-call local graph generator with JSON mode and per-attempt token-ledger recording, and a CPU evaluator. No core GFM-RAG model API changed.
- **Data:** local BIRD entry `/mnt/liansp3/sources/datasets/bird`; schema SHA-256 `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b`; task SHA-256 `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520`. Frozen model input had 165 evidence records and SHA-256 `5cf62d00c382cc88886314e05f02da6925953ded7a0de606e4d8cfe2ab9b3c2e`.
- **Model:** local `Qwen2.5-Coder-7B-Instruct` from `/mnt/liansp3/sources/models/qwen25-coder-7b`; config/tokenizer/weights-index SHA-256 values are frozen in [the run config](../../../../../configs/text2sql/bizweave_bird_zero_fk_graph_20261121_001.json). One HTTP 200 generation took 71.945 seconds and returned 19,727 input, 3,518 output, 23,245 total tokens. The shared API ledger recorded one call with complete usage. External API cost was CNY 0; GPU time is a separate local resource cost and is not monetized.
- **Runtime:** Python 3.10.20, vLLM 0.8.5, PyTorch 2.6.0, Transformers 4.51.3, SQLGlot 30.8.0. vLLM served BF16 on GPU 3 only, max context 32,768, max generation 4,096, eager execution, and one sequence. The model configuration supports 32,768 tokens. vLLM used chunked prefill with a 2,048-token batch default. Its startup log showed model defaults of repetition penalty 1.1, top-k 20, and top-p 0.8; the request explicitly set temperature 0 and seed 20261121. No package was installed or upgraded.
- **Resources:** before startup, GPU 3 had 24,163 MiB free, while GPUs 1 and 2 were in use by other work; system memory had 420 GiB available and 192 CPU cores. Peak observed GPU 3 use during inference was 19,915 MiB at 92% utilization; memory returned to 401 MiB after stopping the server. The service was resident for about three minutes; the generation call itself took 71.945 seconds. CPU evaluation completed in under two seconds.
- **Commands:** exact service and request commands are recorded in the local `preflight_005/launch_command.txt`. The CPU evaluation command was `/root/miniconda3/envs/gmn_alphasql/bin/python scripts/research/bizweave_bird_zero_fk_graph_20261121_001/evaluate_graph.py`.
- **Preflight exceptions:** a first input-preparation attempt rejected BIRD's list-encoded primary-key metadata; the parser was corrected before inference and the failed log was preserved. A tokenizer-only run found that the original 8,192-token setting was too short; before inference, the serving limit was amended to 32,768 based on the model config and measured prompt length. Neither failure made a model request. The frozen input, data, candidate set, evaluation, and stop rule did not change.
- **Result files:** local root `/mnt/liansp3/sources/results/bizweave_bird_zero_fk_graph_20261121_001/`; logs `/mnt/liansp3/logs/bizweave_bird_zero_fk_graph_20261121_001/`. Only this report and [anonymous aggregate metrics](aggregate.public.json) are public; graph JSON, questions, per-question scores, and logs remain local.

## References

- BIRD benchmark: <https://bird-bench.github.io/>.
- Spider 2.0-Lite official repository and task documentation: <https://github.com/xlang-ai/Spider2/tree/main/spider2-lite>.
- BEAVER benchmark and annotation tasks: <https://beaverbench.github.io/>.
- Ömer Faruk Akgül, Nikhil Kapahi, and Prajit Reddy Muppidi. “Schema-Free Text-to-SQL: Learning Enterprise Database Structure from Query Logs.” 2026 preprint: <https://arxiv.org/abs/2610.33946>.
