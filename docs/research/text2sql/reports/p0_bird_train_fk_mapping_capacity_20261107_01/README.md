# BIRD train FK mapping capacity audit

**Status: `CAPACITY_SUFFICIENT_FOR_CONSTRAINT_IDENTITY_STAGE`.** The audit found 384 one-pair-per-question candidates across 12 anonymous databases after excluding the five-question Smoke. All 9,423 Full SQL statements parsed, with zero scope-analysis errors. This is a **schema column-pair capacity upper bound**: BIRD's schema list does not identify whole FK constraints, so the 384 units are not yet confirmed independent mapping alternatives. No model review or ranker inference was run.

## Research question and decision

The prior BIRD-dev ranking screen was negative, while the Spider official test capacity audit found only 52 eligible units against its frozen 60-unit gate. This CPU-only stage asked whether the public BIRD train split contains enough database-disjoint candidate pairs to justify a separately registered FK constraint-identity check. It did not test G-reasoner or Dense ranking quality.

The user selected model reviewers for any follow-on label review. Their decisions will be reported as **model-proxy labels**, not human consensus or business-role gold. No reviewer was called in this experiment.

## Repository guidance, protocol, and sources

- Project repository: `https://github.com/bArtyom/gfm-rag`.
- Branch: `research/p0-sql-used-proxy-alignment-20261107`.
- Evidence synthesis and registration commit: `3397a92761abd763f06a45a32e7bef9e756bf380`.
- Amendment, config, and runner commit used for execution: `cfe5b0c330451236e541ae93a0f2aef4db970537`.
- The root README, text2sql README, experiment roadmap, reproducibility contract, and `/mnt/liansp3/sources.md` were read before registration. Amendment 001 clarified that split metadata is checked before opening train SQL and that FK column-pair multiplicity is only a capacity upper bound.
- Dataset inputs: `/mnt/liansp3/sources/datasets/bird/train/train.json` and `train_tables.json`; dev schema metadata: `/mnt/liansp3/sources/datasets/bird/dev/dev_tables.json`.
- SHA-256: train questions `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520`; train schema `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b`; dev schema `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`.
- The split check read schema `db_id` metadata first: 69 train databases, 11 dev databases, and 0 overlapping IDs. Only after the zero-overlap check did the runner open `train.json`.
- BIRD train is public training data and has also been used by other local projects. Results are exploratory database-disjoint train-split transfer, not hidden-test evidence or a clean independent benchmark. BIRD's [official datasheet](https://papers.nips.cc/paper/2023/file/83fc8fab1710363050bbd1d4b8cc0021-Paper-Datasets_and_Benchmarks.pdf) describes train/dev as public and the test databases as hidden to reduce exposure concerns; the [official BIRD site](https://bird-bench.github.io/) documents the benchmark.

## Frozen selection and execution

The runner used SQLGlot SQLite parsing and scope-aware alias resolution for explicit, qualified cross-table `JOIN ... ON` equalities. It considered a table pair capacity-eligible when `train_tables.json` listed at least two distinct FK column-pair rows for that pair. It then retained at most one pair per question using the registered stable SHA-256 order. `USING`, unresolved sources, and pairs with fewer than two declared column-pair rows were excluded.

The Smoke selected five questions by the frozen hash and was excluded from Full. Full covered the remaining 9,423 of 9,428 train questions. This audit did not open SQLite databases, execute SQL, read database rows, call models or APIs, or run G-reasoner/Dense.

| Stage | SQL parse | Scope errors | Candidate capacity | Result |
|---|---:|---:|---:|---|
| Smoke, 5 questions | 5/5 | 0 | 0 eligible units (Smoke excluded) | `SMOKE_PASS` |
| Full, 9,423 questions | 9,423/9,423 (100%) | 0 | 384 units / 12 anonymous DBs | Capacity gate passed |

Full also parsed 9,671 `JOIN ON` equalities, of which 9,647 were qualified and 9,396 resolved to cross-table columns. The declared-column-pair multiplicity histogram for resolved table-pair occurrences was: zero rows 2,767; one row 5,982; two rows 370; three rows 22; four rows 34. The 426 occurrences with two or more declared rows yielded 384 one-pair-per-question units. Counts by anonymous database are in [`aggregate_summary.json`](aggregate_summary.json); no actual database IDs or schema names are published.

The 384 are **not** a count of independent FK constraints: one composite constraint can contribute multiple column-pair rows. Passing this gate only authorizes a new pre-registration to group actual FK constraints and compare their identities with the schema rows. If fewer than 60 true multi-constraint units across four databases remain, model review will stop before any model call.

## Environment, resources, and reproducibility

- Environment: `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0; no dependencies installed or upgraded.
- Hardware check immediately before execution: four RTX 4090 cards were occupied (GPU 0: 17,371 MiB / 80%; GPU 1: 22,415 MiB / 100%; GPU 2: 22,825 MiB / 100%; GPU 3: 16,299 MiB / 83%). Available host RAM was 439 GiB; 192 logical CPUs. The audit used CPU, capped to 8 threads.
- Smoke: 0.217184 s wall, 0.091374 CPU s, 0.040234 GiB peak RSS.
- Full: 6.722025 s wall, 6.707659 CPU s, 0.043327 GiB peak RSS.
- Model/API/GPU/SQLite/SQL execution calls: 0. Token use: 0 input / 0 output / 0 total. External API cost: CNY 0.00.
- Runner SHA-256: `c98422fa518b0fa5c929ed77c27585f363f075fa3546b707cfd2d52dc9288871`.
- Smoke aggregate: [`smoke_summary.json`](smoke_summary.json). Full anonymous aggregate: [`aggregate_summary.json`](aggregate_summary.json). Private logs and outputs remain under `/mnt/liansp3/logs/gfmrag_p0_bird_train_fk_mapping_capacity_20261107_01/` and `/mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_mapping_capacity_20261107_01/`.

Reproduction commands from the execution commit:

```bash
CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/audit_p0_bird_train_fk_mapping_capacity_20261107.py \
  --mode smoke \
  --run-id p0_bird_train_fk_mapping_capacity_20261107_01_smoke_001 \
  --expected-commit cfe5b0c330451236e541ae93a0f2aef4db970537 \
  --repo-root "/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106" \
  --train-json /mnt/liansp3/sources/datasets/bird/train/train.json \
  --train-tables /mnt/liansp3/sources/datasets/bird/train/train_tables.json \
  --dev-tables /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_mapping_capacity_20261107_01/smoke_001
```

Full uses the same arguments with `--mode full`, run ID `p0_bird_train_fk_mapping_capacity_20261107_01_full_001`, the Smoke aggregate passed as `--smoke-summary`, and output directory ending in `/full_001`.

## Conclusion and next step

The parser and split checks passed, and the column-pair capacity upper bound is large enough to justify one separate constraint-identity audit. This is not a positive or negative model result. Do not start model review from the 384 candidates until composite members are grouped by actual SQLite FK constraint identity and the frozen true-ambiguity gate passes. If that validation passes, register the user's requested local model review as a proxy-label study with its own model, token, confidence, agreement, and stop criteria.
