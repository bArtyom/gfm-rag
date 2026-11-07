# Spider 1.0 FK Mapping Candidate-Capacity Audit

**Status: `STOP_INSUFFICIENT_CAPACITY`.** The CPU-only Full audit parsed all 2,142 non-Smoke official test questions with 100% SQL parse success and zero scope-analysis failures. It found 52 eligible multi-FK question×table-pair units across four anonymous databases, below the preregistered minimum of 60. No model review, G-reasoner inference, Dense ranking, SQL execution, or GPU run followed.

## Question and decision rule

The prior BIRD-dev G-reasoner mapping-ranking screen was negative, and the roadmap closed that BIRD pool to tuning. This independent-dataset capacity audit asked whether Spider 1.0's official test split had enough cases to support one bounded, model-proxy-reviewed replication. Spider is a database-held-out Text-to-SQL benchmark: its official description says train and test contain different databases and queries, requiring generalization to new schemas ([official Spider task page](https://yale-lily.github.io/spider), [original EMNLP 2018 paper](https://aclanthology.org/D18-1425/)).

The pre-registered capacity gate required at least 60 eligible question×table-pair units and at least four anonymous databases after the capacity-audit Smoke. SQL parsing had to reach 98%, with zero scope-analysis failures. A later model-review stage would have required at least 30 high-confidence adjudicable units, 20 distinguishable accepted sets, and three databases before any ranker inference. Those later model gates were not evaluated.

## Source and protocol

- Project repository: `https://github.com/bArtyom/gfm-rag`, branch `research/p0-sql-used-proxy-alignment-20261107`.
- Initial preregistration commit: `196935fa50650a2967d75b825c685b25a330da89`; Amendment 001 and executable source commit: `1d737dece4aa33eaa1bf2d5abbf77ef80fdacb44`.
- Repository guidance read before registration: root `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md`.
- Dataset: Spider 1.0 official archive, CC BY-SA 4.0; SHA-256 `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`. Only `test.json`, `test_gold.sql`, and `test_tables.json` were read from the archive. No raw data or row-level output is included here.
- Source code commit: `1d737dece4aa33eaa1bf2d5abbf77ef80fdacb44`; runner SHA-256 `4dee44eff41a0fe8538d919ae42443301bb35dbdff1709036772f72456f86cda`; SQLGlot 28.0.0.
- Candidate definition: resolve qualified explicit `JOIN ... ON` equalities through SQLGlot scopes, map the referenced physical table pair, and count distinct declared FK column-pair mappings for that pair. One eligible pair is kept per question using a stable hash. `USING` joins, unqualified/unresolved sources, pairs with fewer than two declared FK mappings, and non-FK pairs do not qualify.
- Spider's `foreign_keys` metadata lists column pairs but does not provide composite constraint identities. This audit counts declared column-pair mappings; it does not reconstruct or evaluate composite-FK constraints.
- The capacity audit used no SQL execution, local or hosted model, API, or GPU. Candidate extraction is conditional on a table pair parsed from reference SQL; it is not end-to-end JOIN discovery or semantic-role evaluation.

## Runs and exceptions

| Run | Result | Details |
|---|---|---|
| `..._smoke_001` | stopped before data access | The first launch used `gfmrag_greasoner_20261022`, which lacks SQLGlot. Failure occurred at import, before archive hashing or reading. No output directory was created. The private log remains under `/mnt/liansp3/logs/gfmrag_p0_spider_fk_mapping_candidate_capacity_20261107_01/smoke_001.log`. |
| `..._smoke_002` | passed | Existing `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0. All five frozen Smoke questions parsed. None had an explicit `JOIN ON`; Smoke is excluded from Full and no capacity decision was made from it. |
| `..._full_001` | completed; capacity gate failed | Parsed the remaining 2,142 questions. No parse failures or scope errors. Output has aggregate counts only. |

Amendment 001 changed only the environment and Smoke run ID. It did not alter the dataset, selection, thresholds, or parser rules. No dependencies were installed or upgraded.

## Full result

| Measure | Result | Gate |
|---|---:|---:|
| Test questions in Full | 2,142 | — |
| SQL parse success | 2,142/2,142 (100%) | ≥98%, pass |
| Scope-analysis errors | 0 | 0, pass |
| Questions with explicit `JOIN ON` | 858 | descriptive |
| Qualified `JOIN ON` equalities | 1,250 | descriptive |
| Resolved cross-table equalities | 1,226/1,250 (98.08%) | descriptive; 24 remained unresolved |
| Resolved table-pair occurrences with no declared FK | 100 | excluded |
| Resolved table-pair occurrences with one declared FK mapping | 966 | excluded |
| Ambiguous question×table-pair occurrences (at least two mappings) | 52 | descriptive |
| One-pair-per-question eligible units | 52 | ≥60, **fail** |
| Anonymous databases with eligible units | 4 | ≥4, pass |

Eligible-unit counts by anonymous database were `db_01: 10`, `db_02: 12`, `db_03: 4`, and `db_04: 26`. The histogram of resolved table-pair occurrences by declared mapping count was 100 with zero mappings, 966 with one, and 52 with two. The exact anonymous aggregates are in [`aggregate_summary.json`](aggregate_summary.json); the Smoke output is in [`smoke_summary.json`](smoke_summary.json).

## Resource record and commands

Before execution, the resource check found all four RTX 4090 GPUs occupied (GPU 3 was using 15.6 GiB and 79% utilization at the Full pre-check), 433 GiB host memory available, and 192 CPU cores. The audit ran on CPU. Smoke used 0.541 seconds wall time, 0.539 CPU seconds, and 0.053 GiB peak RSS. Full used 1.587 seconds wall time and CPU time, with 0.055 GiB peak RSS. No API calls or model tokens were generated; external API cost was CNY 0.00.

Smoke 002 command:

```bash
CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4 \
conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/audit_p0_spider_fk_mapping_candidate_capacity.py \
  --archive /mnt/liansp3/sources/datasets/spider_official/spider_data_20261107_confirmed.zip \
  --mode smoke --run-id p0_spider_fk_mapping_candidate_capacity_20261107_01_smoke_002 \
  --expected-commit 1d737dece4aa33eaa1bf2d5abbf77ef80fdacb44 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_spider_fk_mapping_candidate_capacity_20261107_01/smoke_002
```

Full used the same command and inputs with `--mode full`, run ID `p0_spider_fk_mapping_candidate_capacity_20261107_01_full_001`, and output directory ending in `/full_001`.

## Conclusion and next step

The candidate pool is insufficient under the frozen 60-unit gate. Lowering that gate after seeing 52 would be a protocol change on the same test population, so this registration is closed without model review or ranking. The model-review preference is recorded, but proxy labels cannot compensate for the failed independent-sample capacity gate.

This audit says nothing about G-reasoner versus Dense on Spider: neither ranker was run. It also does not prove the underlying method is ineffective. It only shows that the chosen one-pair-per-question, explicit-`JOIN ON`, multiple-declared-FK slice is too small for the pre-registered independent replication. The current FK-mapping branch should move to error synthesis rather than add another label source or lower thresholds on this same sample.

## Files

- [Registration plan](../../plans/p0_spider_fk_mapping_candidate_capacity_20261107.md)
- [Amendment 001](../../plans/amendments/p0_spider_fk_mapping_candidate_capacity_amendment_001.md)
- [Frozen config](../../../../../configs/text2sql/p0_spider_fk_mapping_candidate_capacity_20261107_01.json)
- [Runner](../../../../../scripts/text2sql/audit_p0_spider_fk_mapping_candidate_capacity.py)
- [Anonymous aggregate](aggregate_summary.json)
- [Smoke summary](smoke_summary.json)
