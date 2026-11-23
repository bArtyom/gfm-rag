# BoundaryMORPH for GRAST-SQL: BIRD-dev budget pilot

**Status:** preregistered exploratory pilot; this branch does not change the GFM-RAG main-line priority.

## Scope and source locks

- Owned archive repository: `https://github.com/bArtyom/gfm-rag`, branch `research/boundarymorph-grast-sql-20261123`, base `cb6fe5f4f32a011861d9cf91c0497fb3483450ff`.
- Reference implementation: `https://github.com/thanhdath/grast-sql`, local read-only checkout at `/mnt/liansp3/sources/projects/grast-sql-20261108`, commit `4c698cae31da8299deb5c809101d172d5b2ddeb3`. No `LICENSE` file was present in that checkout. Do not modify or redistribute it.
- Read the GRAST-SQL README and `evaluate_on_the_fly.py`. Its optional coarse-retrieval path crops the graph to `top_m` before it computes query-aware embeddings and runs the graph reranker. This pilot isolates the query-aware column-selection stage and does not load the GNN.
- BoundaryMORPH reference: Caplan et al., arXiv:2609.27213v1, submitted 2026-09-23. The published method uses a MIPS-percentile prior, a vMF cosine kernel with a per-query median bandwidth, a zero-cost query anchor, standardized residual GP conditioning, and a standardized top-k-boundary acquisition. This pilot follows those mechanics; the dataset, models, and target metric differ from that paper.
- The latest project README identifies G2 as the current main-line next experiment. This user-requested work is a separate exploratory branch and will not revise that status.

## Core question and falsifiable hypothesis

**Question:** With a fixed candidate pool and the same 16 expensive query-column scoring calls, does BoundaryMORPH select a more complete set of required BIRD columns than fixed-top-16 or random acquisition when the final core set contains at most 30 columns?

**Hypothesis:** A GP that starts from the cheap dense ranking and propagates a few query-aware score observations through embedding similarity will recover more complete Gold-column sets than a GP receiving fixed-top-16 observations. The mechanism predicts gains specifically when a required column is in the candidate pool but outside the first 16 cheap ranks.

**Falsifier / stop rule:** If BoundaryMORPH does not improve overall FullRecall@30 by at least 1.0 percentage point over both fixed-top-16-GP and random-16-GP, or fewer than 25% of eligible questions have every Gold column in the top-64 candidate pool, classify this variant as `STOP/NO-GO`; do not add a budget sweep or tune kernel parameters on BIRD dev. A positive result remains exploratory and requires a separate protocol using the released GRAST scorer and a large-schema held-out set.

## Frozen inputs and deliberate proxy choices

- Dataset: BIRD dev, 1,534 questions, 11 databases; previously used for development, so no independent-test claim. Column metrics use only the 1,460 questions with complete frozen labels.
- Questions/schema: `/mnt/liansp3/sources/datasets/bird/dev/{dev.json,dev_tables.json}` and its existing `dev_databases/` descriptions. Expected SHA-256: questions `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`; schema `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`.
- Gold labels: existing private P1 artifact at `/mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014/results/p1/full_1534_final_20261014/per_question_private.jsonl`, read only for evaluation. No question, SQL, label, or row-level prediction may enter public GitHub artifacts.
- Cheap vectors: reuse the frozen P1.6 Qwen3-Embedding-0.6B cache at `/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/embedding_cache_private.npz` and its ordered node manifest. Cache shapes are expected to be 1,534×1,024 query and 873×1,024 node vectors. L2-normalize at load time. Do not run another embedding pass.
- Expensive score proxy: local `jina-reranker-v2-base-multilingual`, revision `9cfeff2df7d40d1b78e75e5e9cebec92a99813c9`, using the existing `qes_jina_rerank` environment. Apply sigmoid to its scalar logit. The official GRAST-SQL 0.6B reranker checkpoint was not found locally, so Jina is explicitly a frozen query-aware score proxy, not the GRAST checkpoint or a faithful GRAST reproduction.
- Candidate text: the existing P1 type-first column text (table/column name, type, and available description/format/value text). Gold columns are excluded from query text, candidate generation, priors, acquisition, and scoring.
- Candidate retrieval is a cached Qwen3 cosine proxy, not GRAST's released Stage-I bi-encoder. `N=64` per database, or all columns when the database has fewer than 64. Report candidate-pool coverage as a separate ceiling.
- Keep the full dataset/schema files, cached vectors, local model weights, logs, raw query/SQL, and per-question outputs outside GitHub.

## Methods and fixed budget

One experimental layer, three acquisition policies, one frozen encoder/scorer setup:

| Method | Query-aware calls | Selection/prediction |
|---|---:|---|
| FixedTop16-GP | `min(16, |C|)` | Observe the highest-ranked cheap candidates, then use the shared GP posterior. |
| Random16-GP | `min(16, |C|)` | Observe a deterministic hash-seeded random subset, then use the same GP posterior. |
| BoundaryMORPH | `min(16, |C|)` | At each step, score the less certain member of the minimum standardized top-30 boundary-gap pair. |

All policies use the same per-question candidate set, Qwen3 cosine prior, vMF kernel with median-heuristic bandwidth, query anchor at score 1, jitter `1e-6`, residual standardization, Jina sigmoid scores, and stable node-ID tie breaks. There is no kernel or temperature tuning. `K=min(30, |C|)`. A question with no more than `K` candidates is retained in the denominator and is already fully selectable within the candidate-pool ceiling.

The experiment returns core columns before Steiner closure. It does not run Steiner, GNN reranking, SQL generation, or SQL execution. This keeps the acquisition comparison isolated; the current FK/Join-role audit gate is not passed, and using closure here could conflate selection with unverified FK metadata.

## Evaluation and decision

- **Primary:** overall `FullRecall@30` = fraction of 1,460 eligible questions whose entire frozen Gold-column set is in the selected core columns.
- **Selection diagnostic:** `FullRecall@30 | candidate-complete`, conditioned on every Gold column being in the top-64 candidate pool.
- **Ceiling:** candidate-pool full recall and macro Gold-column candidate recall.
- **Secondary:** macro Column Recall@30, Precision@30, per-database FullRecall, number of recoveries where a Gold column ranked below 16 cheaply, and paired rescue/damage counts.
- Report paired differences and a database-cluster bootstrap 95% interval over the 11 databases (10,000 draws, seed `20261123`). The interval is exploratory; BIRD dev is not held out.
- Same logical score-call budget for all three methods. Record actual Jina input tokens after truncation, number of local forward batches, wall time, GPU time, CPU time, peak RSS, and resource snapshots. Local model output is one scalar per pair; output tokens are zero. No external API call or external fee is planned.

## Execution gates and budgets

1. Read-only input/hash/resource preflight; create this protocol and the independent config first.
2. Deterministic 5-question engineering smoke, selected by question-ID hash without inspecting labels. Verify cache/question/node alignment, model load, finite scores, GP posterior, budget counts, output schema, and independent aggregate recomputation.
3. Only after smoke passes, run all 1,534 questions with the fixed methods; use eligible labels only in evaluation. The maximum planned query-column score volume is 73,632 pairs (3×1,534×16), subject to `min(B, |C|)`.

Resources: explicit physical GPU 1 only; max 3,600 GPU-seconds, 7,200 wall-seconds, 1,800 CPU-seconds, 8 CPU threads, 16 GiB RSS; no service, model download, dependency installation, training, or paid API. Recheck `nvidia-smi`, `free -h`, `nproc`, and target directories immediately before the smoke and full run. Stop on insufficient GPU headroom, data/hash mismatch, failed independent output validation, repeated model failure, or budget overrun.

## Artifacts

- Private results: `/mnt/liansp3/sources/results/boundarymorph_grast_bird_20261123_001/`.
- Private logs: `/mnt/liansp3/logs/boundarymorph_grast_bird_20261123_001/`.
- Public report and anonymized aggregate: `docs/research/text2sql/reports/boundarymorph_grast_bird_20261123_001/`.
- Experiment-specific code/config: this `experiments/` directory, `scripts/research/boundarymorph_grast_bird_20261123_001/`, and `configs/text2sql/boundarymorph_grast_bird_20261123_001.json`.
- Never publish private input data, raw prompts, SQL, per-question rankings, model weights, cache arrays, or logs.
