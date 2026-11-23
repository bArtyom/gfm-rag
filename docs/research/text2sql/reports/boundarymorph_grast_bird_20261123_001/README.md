# BoundaryMORPH for GRAST-SQL: BIRD-dev budget pilot

**Result:** exploratory gate passed; keep the method for a separate replication. This is a column-selection pilot using local proxy models, not a reproduction of GRAST-SQL's released end-to-end system.

## Research question and registered decision rule

With the same high-cost query-column score budget, does BoundaryMORPH improve the completeness of a selected core-column set over a fixed-top-16 or deterministic-random policy? The registered hypothesis was that a Gaussian Process (GP), initialized from a cheap dense ranking and updated at uncertain Top-30 boundary pairs, would recover more required columns than fixed Top-16 scoring.

The gate required (1) at least a 1.0 percentage-point gain in overall `FullRecall@30` over each baseline and (2) full Gold-column coverage in the top-64 candidate pool for at least 25% of eligible questions. We observed +2.53 points over FixedTop16-GP, +8.84 points over Random16-GP, and an 83.97% candidate-complete rate. The registered gate passed. The decision is limited to this exploratory BIRD-dev setup.

## Source locks and execution

- Owned project repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), experiment branch `research/boundarymorph-grast-sql-20261123`; main was not changed. The project main-line priority remains G2.
- Source used for the full run: local execution commit `a193217b23f793f3f213e8e450551628223b0143`, mirrored on GitHub at `5d6364da3ef01486f0b774c43434e32d71bc7c28`. This run commit contains the registered protocol, config, code, and amendments. The report is added in a later archive commit.
- GRAST-SQL reference: [`thanhdath/grast-sql` commit `4c698cae31da8299deb5c809101d172d5b2ddeb3`](https://github.com/thanhdath/grast-sql/tree/4c698cae31da8299deb5c809101d172d5b2ddeb3). Its README and `evaluate_on_the_fly.py` were read. The checkout had no LICENSE file; it was used read-only and no upstream code was copied or changed. Its optional coarse retrieval crops the graph before query-aware encoding; this pilot isolates column selection and does not load the GNN.
- BoundaryMORPH reference: Caplan et al., [arXiv:2609.27213](https://arxiv.org/abs/2609.27213). The implementation follows the MIPS-percentile prior, vMF cosine kernel with per-query median bandwidth, score-1 query anchor, standardized residual GP conditioning, and boundary-pair acquisition.
- Experiment protocol: `experiments/boundarymorph_grast_bird_20261123_001/protocol.md`; config: `configs/text2sql/boundarymorph_grast_bird_20261123_001.json`; runner: `scripts/research/boundarymorph_grast_bird_20261123_001/run_experiment.py`.
- Full-run command:

  ```bash
  CUDA_VISIBLE_DEVICES=1 conda run -n qes_jina_rerank python3.10 -u \
    scripts/research/boundarymorph_grast_bird_20261123_001/run_experiment.py \
    --mode full \
    --config configs/text2sql/boundarymorph_grast_bird_20261123_001.json \
    --output-dir /mnt/liansp3/sources/results/boundarymorph_grast_bird_20261123_001/full_1534_20261123_01 \
    --registered-commit a193217b23f793f3f213e8e450551628223b0143
  ```

The two initial engineering smoke attempts are documented in `experiments/boundarymorph_grast_bird_20261123_001/amendment-001.md` through `amendment-003.md`; their partial outputs were preserved. The corrected 5-question smoke passed input alignment, model loading, finite GP outputs, per-method score budgets, output checks, and independent aggregate recomputation. Smoke results were not used in the full-run metric.

## Data, models, and scope

- Dataset: BIRD dev, 1,534 questions over 11 databases; 1,460 questions have complete column labels (6,523 Gold columns). Question file SHA-256: `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`; schema file SHA-256: `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`. BIRD dev was used in earlier development and is not an independent test set.
- Cheap candidate retriever: frozen P1.6 Qwen3-Embedding-0.6B vectors, reused from `/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/`; no new embedding inference. Vector shapes were 1,534×1,024 query and 873×1,024 schema-node vectors. All 873 cached node texts matched the frozen schema-text manifest.
- Candidate set: top 64 columns by cached Qwen3 cosine similarity, or all columns for smaller schemas. This is a retrieval proxy, not GRAST-SQL's released Stage-I bi-encoder.
- Query-aware score proxy: local `jina-reranker-v2-base-multilingual`, revision `9cfeff2df7d40d1b78e75e5e9cebec92a99813c9`, scalar logit passed through sigmoid. The local checkpoint's weights were hash-verified. The official GRAST-SQL query-aware scorer checkpoint was not available locally, so the Jina result must not be represented as a GRAST scorer result. The Jina model card specifies CC-BY-NC-4.0; weights were not uploaded.
- Three methods, with identical candidate pools, prior, kernel, score transform, and maximum of 16 query-aware calls per question: FixedTop16-GP, Random16-GP (hash seed `20261123`), and BoundaryMORPH. Final core capacity was `K=min(30, |C|)`. Among 1,534 questions, 1,389 used 16 scores and 145 used 11 because their schemas contained fewer than 16 candidate columns. Total was 71,457 scoring pairs; the maximum under 16 scores for every question was 73,632.
- BoundaryMORPH used the MIPS-percentile prior, `exp(kappa*(cosine-1))` vMF kernel with a per-question median-distance bandwidth, query anchor score 1, GP jitter `1e-6`, standardized residuals, and the less-certain member of the minimum standardized Top-30 boundary-gap pair. No kernel, score temperature, or budget tuning was run.
- The experiment returns core columns before Steiner closure. It does not run GNN graph reranking, SQL generation, or SQL execution. The FK/Join-role audit gate had not passed, so closure was excluded to avoid mixing column selection with unverified structure.

## Results

| Method | FullRecall@30 | Macro column recall | Macro column precision | Full recall given candidate-complete |
|---|---:|---:|---:|---:|
| BoundaryMORPH | 69.25% (1,011/1,460) | 86.80% | 14.80% | 82.46% (1,011/1,226) |
| FixedTop16-GP | 66.71% (974/1,460) | 85.51% | 14.58% | 79.45% (974/1,226) |
| Random16-GP | 60.41% (882/1,460) | 83.97% | 14.36% | 71.94% (882/1,226) |

The shared top-64 candidate pool was complete for 1,226/1,460 questions (83.97%). It covered 94.41% of Gold columns on a macro per-question basis and 93.55% micro. This ceiling bounds any selection method using these candidates.

BoundaryMORPH rescued 51 questions and damaged 14 relative to FixedTop16-GP, for a net gain of 37 full-recall questions. Of the Gold-column occurrences ranked below 16 in the cheap pool, 853 appeared in BoundaryMORPH's final core set versus 758 for FixedTop16-GP.

Database-cluster bootstrap, 10,000 resamples with seed `20261123`, gave a 95% interval of **+0.69 to +4.29 percentage points** for BoundaryMORPH minus FixedTop16-GP and **+3.85 to +14.81 points** versus Random16-GP. These intervals are exploratory because there are only 11 databases and BIRD dev is not held out.

The anonymous aggregate is in `aggregate-results.json`. Full per-question predictions, selected column IDs, and labels remain private.

## Resources, usage, and anomalies

- Environment: `qes_jina_rerank`, Python 3.10.22, PyTorch 2.5.1, CUDA 12.4, Transformers 4.57.6, NumPy 2.2.6. No packages were installed, no model downloaded, no training run, and no external API called.
- Hardware: physical GPU 1, RTX 4090 (24 GiB); at full-run start it had 403 MiB in use. Host had 406 GiB available RAM and 192 CPU threads; this job limited numerical-library threads to 8. Full-run process peak RSS was 1.43 GiB, PyTorch peak allocated GPU memory was 0.64 GiB, process CPU time was 635.53 seconds, wall time was 114.64 seconds, and measured GPU inference time was 41.35 seconds. The registered maxima (3,600 GPU seconds, 7,200 wall seconds, 1,800 CPU seconds, 16 GiB RSS) were not reached.
- Full-run Jina usage after truncation: 71,457 query-column pairs, 4,473 forward batches, 4,333,198 input tokens, 0 output tokens. Including the partial smoke and the successful smoke, this experiment's local Jina usage was 71,837 pairs, 4,354,775 input tokens, 0 output tokens, and 43.78 GPU inference seconds. This is local compute, not API usage or zero resource cost. External API fees were CNY 0 / USD 0.
- The model used the PyTorch native-attention fallback because FlashAttention was absent; no installation was attempted. The full-run completion resource snapshot briefly reported 19,286 MiB in use on GPU 1, while the immediate post-exit reading returned to 403 MiB. The snapshot could not be attributed to this process; PyTorch's peak allocated memory was 0.64 GiB. This transient reading did not interrupt inference, but is retained as a resource anomaly.
- The full run ended with `KEEP_FOR_SEPARATE_REPLICATION`. Output verification found 1,534 rows per method, the expected 1,460 eligible questions, identical per-question score-budget distributions across methods, and a passed independent recomputation of the saved aggregate.

## Conclusion and limits

The registered V1 mechanism passed its exploratory gate on this BIRD-dev proxy setup. The result supports continuing to a separately registered replication, not a general claim that BoundaryMORPH improves GRAST-SQL. The next evidence should use the official GRAST query-aware scorer and a genuinely held-out large-schema set; evaluate end-to-end graph closure only after the project's FK/Join-role gate passes. Do not tune further on this BIRD-dev run; Version 2 remains untested.

Private run artifacts are available at `/mnt/liansp3/sources/results/boundarymorph_grast_bird_20261123_001/`; logs are at `/mnt/liansp3/logs/boundarymorph_grast_bird_20261123_001/`. The private directory includes per-question predictions, selected IDs, and input manifests and must not be uploaded.
