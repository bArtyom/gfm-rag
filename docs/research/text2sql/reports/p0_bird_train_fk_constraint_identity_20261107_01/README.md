# BIRD train FK constraint identity audit

**Experiment:** `p0_bird_train_fk_constraint_identity_20261107_01`  
**Status:** `CAPACITY_SUFFICIENT_FOR_MODEL_REVIEW_PREREGISTRATION`  
**Evidence class:** exploratory data-validity gate; no model ranking result.

## Research question and decision

The previous capacity audit found 384 question × table-pair candidates by counting declared FK column-pair rows. That count could overstate the number of distinct relationships when multiple rows form one composite FK. This audit grouped SQLite metadata by child table, parent table, constraint ID, and column sequence, then compared the resulting column-pair sets with the dataset schema.

The frozen gate required at least 60 exact-alignment units with at least two distinct complete FK constraint signatures across at least four anonymous databases. Full found **138/379 units** meeting that definition across **8 anonymous databases**, so the capacity gate passed. This only authorizes a separate local-model proxy-review registration. It does not establish semantic Role labels, model accuracy, or a G-reasoner result.

## Registration and execution history

- Project repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/p0-sql-used-proxy-alignment-20261107`.
- Parent plan: [`p0_bird_train_fk_constraint_identity_20261107.md`](../../plans/p0_bird_train_fk_constraint_identity_20261107.md).
- Recovery plan: [Amendment 001](../../plans/amendments/p0_bird_train_fk_constraint_identity_20261107_amendment_001.md).
- Frozen parent config: [`p0_bird_train_fk_constraint_identity_20261107_01.json`](../../../../../configs/text2sql/p0_bird_train_fk_constraint_identity_20261107_01.json).
- Recovery config: [`p0_bird_train_fk_constraint_identity_20261107_01_amendment_001.json`](../../../../../configs/text2sql/p0_bird_train_fk_constraint_identity_20261107_01_amendment_001.json).
- Runner: [`audit_p0_bird_train_fk_constraint_identity_20261107.py`](../../../../../scripts/text2sql/audit_p0_bird_train_fk_constraint_identity_20261107.py).
- The first Smoke (`..._smoke_001`) passed. The first Full (`..._full_001`) stopped at its receipt check before opening SQLite: the code compared a five-hash Smoke receipt with a three-key dictionary. The failure receipt and log were preserved. Amendment 001 corrected the check to validate all five required hashes by key; it did not change the sample, thresholds, inputs, or database permissions.
- Amendment Smoke (`..._amendment_001_smoke_001`) passed, followed by the only Amendment Full (`..._amendment_001_full_001`). The Full run used source commit `4a35368ec5744fab0f1ba7411f05c682a8f22e52`, runner SHA-256 `b37e6599bab1aa88065675fe1c676b6c47b84d1402253ad4deafb4ff160adb82`, and config SHA-256 `8bb8f6c6d94b0f50a11fecef2d9cdf6ec7195c31bd2d561d4806bb40358e5ea1`.

## Frozen inputs

| Input | Local source | SHA-256 |
|---|---|---|
| BIRD train questions/SQL | `/mnt/liansp3/sources/datasets/bird/train/train.json` | `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520` |
| BIRD train schema | `/mnt/liansp3/sources/datasets/bird/train/train_tables.json` | `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b` |
| BIRD dev schema, used only for split isolation | `/mnt/liansp3/sources/datasets/bird/dev/dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| BIRD train database root | `/mnt/liansp3/sources/datasets/bird/train/train_databases` | directory of 69 SQLite files; only candidate databases were opened |
| Previous capacity Full aggregate | `/mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_mapping_capacity_20261107_01/full_001/aggregate_summary.json` | `fb7f8498f8fdfefe3f220ed06eaa04aa46d2f91ad7acc7018b9d49bdfcb54a66` |

The train/dev schema database-ID intersection was 0 (69 train databases, 11 dev databases). The previous capacity Full excluded its own five Smoke questions and produced 384 candidates over 12 databases. This audit selected five additional candidate units for Smoke; Full excluded those five and evaluated the remaining 379. Smoke and Full did not overlap.

BIRD train is a public training split that has also been used by another local project. Therefore this is exploratory, database-disjoint transfer evidence, not hidden-test evidence.

## Method and safeguards

- Reconstructed the 384 candidate units using the previous runner's SQL parser, table-pair resolution, stable selection, and prior five-question Smoke exclusion. The anonymous per-database histogram matched the frozen capacity receipt exactly.
- Opened only SQLite files containing selected candidate tables, with `mode=ro&immutable=1`; enabled `query_only` and installed an authorizer that allowed only `PRAGMA foreign_key_list` for allowlisted candidate tables.
- Grouped PRAGMA rows by child table, parent table, constraint `id`, and `seq`. Composite-FK column pairs stayed in one ordered constraint signature. Identical signatures were deduplicated for distinct-candidate counts.
- Compared each candidate table-pair's normalized FK column-pair set from the BIRD schema to the set returned by SQLite. Only exact matches could count toward capacity.
- Did not execute Gold SQL, candidate SQL, `SELECT`, DML, DDL, or `foreign_key_check`; no business table rows were read. SHA-256 of each relevant database file was computed before and after.
- Private row-level candidate and constraint evidence remains under `/mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/`. It is not included in this repository.

## Results

| Measure | Smoke | Full |
|---|---:|---:|
| Candidate units | 5 | 379 |
| Anonymous databases opened | 5 | 12 |
| Metadata/PRAGMA exact table-pair sets | 5/5 | 379/379 |
| Distinct-signature multi-constraint units | 2/5 | 138/379 |
| Anonymous databases with eligible units | 2 | 8 |
| PRAGMA calls | 10 | 41 |
| PRAGMA FK rows | 26 | 98 |
| Constraint-group occurrences | 19 | 68 |
| Database SHA-256 changes | 0 | 0 |
| Unexpected SQLite authorizer operations | 0 | 0 |
| Model/API/GPU calls | 0 | 0 |

Full's distinct complete-signature count per question × table-pair unit was: 241 units with one signature, 78 with two, 27 with three, and 33 with four. All 379 units aligned exactly. The 138 eligible units were distributed across eight anonymous databases: `db_01` 30, `db_02` 27, `db_03` 6, `db_04` 34, `db_05` 13, `db_06` 7, `db_07` 14, and `db_09` 7. A single PRAGMA row lacked a fully specified target column; it did not create a metadata mismatch in any candidate pair.

The Amendment Smoke used 7.76 seconds wall / 7.75 CPU seconds / 0.0463 GiB peak RSS. Full used 223.88 seconds wall / 67.41 CPU seconds / 0.0463 GiB peak RSS. Both were CPU-only with an eight-thread cap.

## Environment, resources, and command

- Conda environment: `think2sql_20260909`, invoked with `/root/miniconda3/envs/think2sql_20260909/bin/python3.12` (Python 3.12.14, SQLGlot 28.0.0, SQLite 3.53.2). The short name alone resolved to Python 3.9 in this shell, so the absolute interpreter path was frozen.
- Hardware at Full start: 4× RTX 4090 were already 80%, 96%, 96%, and 81% utilized; available RAM 439 GiB; swap 2 GiB fully used; 192 CPU threads; 112 TiB disk free. The experiment used no GPU.
- External API calls: 0; model calls: 0; confirmed input/output/total model tokens: 0/0/0; external API cost: CNY 0.00. CPU wall time is reported above and is a local compute cost.

The executed Full command was:

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 PYTHONHASHSEED=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 timeout --signal=INT 1800s conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/audit_p0_bird_train_fk_constraint_identity_20261107.py \
  --mode full \
  --run-id p0_bird_train_fk_constraint_identity_20261107_01_amendment_001_full_001 \
  --expected-commit 4a35368ec5744fab0f1ba7411f05c682a8f22e52 \
  --expected-config-sha256 8bb8f6c6d94b0f50a11fecef2d9cdf6ec7195c31bd2d561d4806bb40358e5ea1 \
  --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 \
  --config configs/text2sql/p0_bird_train_fk_constraint_identity_20261107_01_amendment_001.json \
  --train-json /mnt/liansp3/sources/datasets/bird/train/train.json \
  --train-tables /mnt/liansp3/sources/datasets/bird/train/train_tables.json \
  --dev-tables /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --database-root /mnt/liansp3/sources/datasets/bird/train/train_databases \
  --capacity-aggregate /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_mapping_capacity_20261107_01/full_001/aggregate_summary.json \
  --smoke-summary /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/amendment_001_smoke_001/aggregate_summary.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/amendment_001_full_001
```

The public Full and Smoke aggregates are [`aggregate_summary.json`](aggregate_summary.json) and [`smoke_summary.json`](smoke_summary.json). Full execution log and all row-level evidence remain local under `/mnt/liansp3/logs/` and `/mnt/liansp3/sources/results/`.

## Conclusion and next action

The FK column-pair upper bound was not entirely an artifact of composite FKs: 138 question × table-pair units retained at least two distinct, exact-alignment constraint signatures. This passes the pre-registered **capacity-only** gate for a separate local-model proxy-review study. The next stage must have its own frozen prompt, sample, model versions, resource and token caps, confidence/agreement rule, and stop condition. Any model judgments remain proxy labels, not human consensus or ground truth. No G-reasoner/Dense ranking was run here.

## Limitations

- BIRD train is public training data with prior local use; results do not establish generalization to a hidden test set.
- Exact schema/PRAGMA agreement establishes metadata identity, not whether a mapping expresses the user's intended business role.
- The 138 units are capacity counts, not accuracy, ranking, or SQL execution results.
- One PRAGMA row had no explicit target column, and units with metadata mismatches would be ineligible by design.
