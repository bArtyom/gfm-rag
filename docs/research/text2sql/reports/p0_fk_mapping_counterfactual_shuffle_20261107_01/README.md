# P0 FK mapping counterfactual-shuffle diagnostic

**Final status:** `INCONCLUSIVE_ELIGIBILITY_COVERAGE` — stopped at the preregistered eligibility gate. The sensitivity hypothesis was not tested.

**Experiment ID:** `p0_fk_mapping_counterfactual_shuffle_20261107_01`  
**Run that completed the coverage screen:** `p0_fk_mapping_counterfactual_shuffle_20261107_01_smoke_005_20261107_04`  
**Project:** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p0-sql-used-proxy-alignment-20261107`  
**Run source commit:** [`d068b1596ff55cb459b47ca509f00c0ccebec4c2`](https://github.com/bArtyom/gfm-rag/commit/d068b1596ff55cb459b47ca509f00c0ccebec4c2)

## Question and preregistered decision

The preceding static-instance audit found 55 alternate FK candidate comparisons with the same result Bag as the SQL-used mapping, drawn from 94 complete units. This bounded exploratory diagnostic asked whether the matches persist after seeded, referentially valid permutations of eligible single-column FK child values.

The frozen hypothesis required at least 50% of eligible fixed pairs to show a Bag divergence on one or more of 20 valid counterfactual views. The positive screen also required at least 40 eligible pairs across at least three anonymous databases. At most 25% divergence would be a weak sensitivity signal; intermediate results or insufficient coverage are inconclusive. The fixed sample, 20-seed interval (`20261107`–`20261126`), thresholds, and stop-after-one-Full rule were not changed during recovery.

## Repository guidance and implementation

Before execution, the work followed the project instructions in `AGENTS.md` and read the repository `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md`. The registration and Amendments 001/002 define the eligibility rules, hash gates, resource limits, privacy boundary, and stop conditions:

- [Registration plan](../../plans/p0_fk_mapping_counterfactual_shuffle_20261107.md)
- [Amendment 001](../../plans/p0_fk_mapping_counterfactual_shuffle_20261107_amendment_001.md)
- [Amendment 002](../../plans/p0_fk_mapping_counterfactual_shuffle_20261107_amendment_002.md)
- [Amendment 002 config](../../../../configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_amendment_002.json)
- [Execution config](../../../../configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_execution_001.json)
- [Runner](../../../../scripts/text2sql/run_p0_fk_mapping_counterfactual_shuffle.py)

Two local Qwen models reviewed only the protocol before execution. Their feedback led to explicit FK-domain and uniqueness checks. The models did not see questions, SQL, candidate identities, database names, or results; their outputs are process feedback, not labels. The execution runner was then corrected to read the frozen per-database expectations from the same nested `reconstructed_source_expectations` object as the aggregate expectations. That correction did not change the experiment design.

## Data, code, and environment

The fixed 55-pair sample was reconstructed from the existing BIRD dev snapshot and prior Full_002 artifacts. Hash validation passed before database eligibility checks:

| Input | SHA-256 |
|---|---|
| BIRD `dev.json` | `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` |
| BIRD `dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| Frozen source manifest | `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0` |
| Prior private Full metrics | `f996213f2d6e657f518c5440843eaa7f61e6f91fd57e5d0393d8022d6d5a4337` |
| Prior aggregate | `27d3411496e5fd4fb829c30c110018ea33b2275c751bccc437f5dd0835dac582` |

The four SQLite snapshots were opened read-only for eligibility checks. Their byte sizes and SHA-256 hashes were rechecked after the run and all matched the pre-run hashes in Amendment 002. No source database was changed. Per-pair hashes, SQL, question text, row values, and private progress records remain local.

The completed run used the explicit `think2sql_20260909` interpreter: Python 3.12.14, SQLite 3.53.2, and SQLGlot 28.0.0. The diagnostic was CPU-only, capped at eight threads, 1,800 CPU seconds, 3,600 wall seconds, and 4 GiB RSS. At launch the host had 192 logical CPUs and about 446 GiB available memory; the four RTX 4090 GPUs were occupied, so no GPU was used. No dependency was installed or changed.

The run receipt records runner SHA-256 `4959dce11f28be60146542a6da2c72c565f1c299b69fa0a2d73a32dea350c824`, protocol-config SHA-256 `75579568bf3d16d010e5a5c6bbd137521e552799d8ce718cd25ba0cd0a830d76`, and execution-config SHA-256 `7f39d2a1ffa8765d2efad78ecc4ba21f78fc8676d83de844219df58f9e63ef01`.

## Execution history

Each stop is preserved under a separate run record or command/log file. None was overwritten.

| Attempt | Outcome | Stage and effect |
|---|---|---|
| Smoke `_01` | `EXECUTION_SAMPLE_ASSERTION_MISMATCH` | Input hashes and fixed-pair reconstruction completed. A configuration lookup failed before SQL parsing or SQLite access. |
| Invocation recorded as `_02` | argparse stop | The command omitted required `--mode`, `--run-id`, and `--config` flags. It exited before reading inputs and created no result directory. |
| Smoke `_03` | `EXECUTION_STRATA_ASSERTION_MISMATCH` | Input hashes passed; the runner loaded the manifest, prior metrics, BIRD JSON files, and reconstructed 55 pairs. It then stopped because the per-database expectations were read from the wrong config level. SQL was not parsed or executed and no SQLite connection was opened. |
| Smoke `_04` | `INCONCLUSIVE_ELIGIBILITY_COVERAGE` | The corrected runner screened all 55 pairs and reached the registered coverage decision. Fourteen pairs were eligible across two databases, below the required 40 pairs and three databases. No candidate-pair query comparisons were run and Full was not started. |

The `_04` eligibility stage generated and validated 20 distinct, referentially valid temporary-view assignment plans for each of the 14 eligible pairs (280 plans total). It did **not** execute either SQL variant on those views. The five-pair comparison Smoke was never entered because the global coverage gate failed first.

## Results

| Measure | Observed | Registered gate | Decision |
|---|---:|---:|---|
| Fixed candidate pairs screened | 55 | exactly 55 | Pass |
| Structurally eligible pairs | 14 | at least 40 before Smoke | Fail |
| Eligible anonymous databases | 2 (`DB-B`: 12; `DB-C`: 2) | at least 3 | Fail |
| Excluded: original FK values outside declared target domain | 32 | reported, no relaxation | — |
| Excluded: changed FK column is a primary key | 9 | reported, no relaxation | — |
| Valid temporary-view plans preflighted | 280 | 20 per eligible pair | Complete for eligible pairs |
| SQL-variant comparisons on counterfactual views | 0 | only after coverage gate | Not run |
| Full pairs / Full seed comparisons | 0 / 0 | one Full only after Smoke passes | Not run |

The status is therefore an eligibility-coverage stop, not evidence for or against the sensitivity hypothesis. In particular, the 14 eligible pairs cannot be treated as a smaller replacement sample; the registration forbids widening or relaxing the eligibility rules after observing coverage.

The completed screen took 15.110 seconds wall time, 14.893 seconds CPU time, and 0.636 GiB peak RSS. GPU time was 0. The SQL diagnostic made zero model or external API requests. The protocol reviews were two local-model calls and are reported separately: combined 4,054 input tokens, 335 output tokens, 4,389 total local tokens; GPU time was 10.546 seconds generating plus 10.494 seconds loading the models (21.040 seconds total). They incurred no external API charge.

## Reproduction command

The following is the exact `_04` invocation. The BIRD files, source manifest, and prior private artifacts are local inputs and are not included in this public report.

```bash
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/run_p0_fk_mapping_counterfactual_shuffle.py \
  --mode smoke \
  --run-id p0_fk_mapping_counterfactual_shuffle_20261107_01_smoke_005_20261107_04 \
  --config configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_amendment_002.json \
  --execution-config configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_execution_001.json \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --source-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json \
  --prior-full-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/full_002 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/smoke_005_20261107_04
```

## Conclusion and limits

The fixed-sample perturbation experiment could not answer whether the earlier Bag equalities persist under changed FK assignments. Most candidate pairs were ineligible because the existing database values did not satisfy the declared FK target-domain check, and the eligible pairs covered only two of four anonymous databases. The pre-registered response is to stop. Do not report an `EverBagDiverged@20` estimate, infer semantic equivalence, or proceed to G-reasoner ranking from this run.

This remains a fixed BIRD dev exploratory diagnostic. It is not official Test Suite Accuracy, semantic-equivalence proof, business Role gold, user-intent validation, or a GFM ranking result. Any future study would need a separately registered question about FK-domain violations or a new, independently justified dataset/protocol; this report does not authorize that follow-up.

## Artifacts

- Public anonymous aggregate: [aggregate_summary.json](aggregate_summary.json)
- Registration: [plan](../../plans/p0_fk_mapping_counterfactual_shuffle_20261107.md)
- Local outputs: `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/smoke_005_20261107_04/`
- Local logs and prior failed invocations: `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/`
- Public files intentionally exclude question text, SQL, candidate IDs, row values, detailed progress, and local logs.
