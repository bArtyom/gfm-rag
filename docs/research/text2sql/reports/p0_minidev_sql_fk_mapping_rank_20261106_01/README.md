# P0: BIRD Mini-Dev Gold-SQL FK Mapping Transfer Audit

**Status: `STOP_LABEL_GATE_FAILED`.** The SQL parser handled all 500 questions, but it resolved only 78.88% of qualified `JOIN ON` column equalities. The preregistered threshold was 95%. The G-reasoner/Dense ranking stage did not run, so this is a label-coverage stop, not evidence for or against either ranker.

## Research question and hypothesis

This bounded transfer diagnostic asked whether a frozen G-reasoner ranks the FK mapping actually used by a reviewed reference SQL above Dense Cosine, once both endpoint tables and the candidate mappings are known. The frozen positive screen was G-reasoner Mapping@1 at least 5 percentage points above Dense, at least four net rescues, and positive net rescue in at least two databases with at least five cases each.

The label means “this declared mapping appears in the reference SQL's explicit `JOIN ... ON` condition.” It is not a human FK-Role label, a claim that the mapping is the only semantically valid join, an end-to-end Text-to-SQL result, or a cross-database generalization result. The 11 databases overlap with the project's existing BIRD resources.

The official Mini-Dev project describes its 2026 release as a community-informed, human-in-the-loop correction of selected annotations and provides the 500-question SQLite split on Hugging Face ([release notes](https://github.com/bird-bench/mini_dev), [pinned dataset revision](https://huggingface.co/datasets/birdsql/bird_mini_dev/tree/38818fcbc46038129592680c51b2c8b597aac27c)).

## Protocol and registered stop rule

- **Layer:** one bounded transfer diagnostic; exploratory evidence only.
- **Dataset:** 500 reviewed Mini-Dev SQLite rows, fixed revision `38818fcbc46038129592680c51b2c8b597aac27c`, license CC BY-SA 4.0.
- **Labels:** SQLGlot `28.0.0`, SQLite dialect; only qualified, resolvable cross-table column equalities from explicit `JOIN ON` contribute to mapping labels. `WHERE` equalities and `USING` joins do not label mappings. Composite mapping columns must occur in one `JOIN ON` and one alias pair. Repeated complete candidate identities are collapsed, retaining the lexicographically smallest stable ID.
- **Split:** deterministic ascending `SHA256(experiment_id + db_id + question_id)`; 5 smoke questions excluded from the 495-question Full split. The question IDs and selected rows remain private.
- **Label gate before model ranking:** parse success ≥98%; resolution of qualified `JOIN ON` equalities ≥95%; at least 30 scored question×table-pair cases across at least 3 databases; no scope-analysis errors. Any failed gate stops before loading models.
- **Budget:** one successful 5-question smoke after one registered engineering recovery, one Full CPU audit, no training, no parameter sweep, and no further attempt after the coverage gate fails.

## Registration, guidance, and amendment

Work was performed in the user-owned project repository `https://github.com/bArtyom/gfm-rag`, branch `research/minidev-sql-fk-use-rank-20261106`. Before execution, the project README, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md` were read. The plan and code were preregistered at commit `e393dcdd5ca1e2d007ce452496cdb626af1f2f3e`.

The first CPU smoke, `cpu_smoke_001`, stopped before reading or parsing SQL because the initial check incorrectly required the older BIRD `dev_tables.json` to have exactly the same table inventory as the pinned 2026 SQLite DDL. A local, count-only compatibility audit found 10 of 11 database inventories matched exactly; in one inventory the pinned DDL had one additional table and two additional columns. No SQL labels were read in that failed attempt. The official DDL from the pinned Mini-Dev revision is the column authority, so amendment 001 changed the legacy inventory check to require that every legacy table and column exists in the official DDL while permitting official additions. The failed run and its log were retained; `cpu_smoke_002` was registered as the only engineering recovery. The amended code/config were committed before the successful smoke and Full run at `deb0b9ec1e25292f6e1036ba2b4b2259f8129678`.

## Implementation changes

The CPU audit script, `scripts/text2sql/audit_minidev_sql_fk_labels.py`, implements the isolated SQL-label pass. It now:

1. Uses the exact reviewed Mini-Dev DDL as the authoritative schema and validates the older `dev_tables.json` as a compatible subset.
2. Resolves aliases and columns conservatively; repeated aliases remain unresolved.
3. Keeps composite-equality evidence inside one `JOIN ON` and one alias pair, so separate joins or `UNION` branches cannot be combined into a false label.
4. Deduplicates identical complete FK mapping identities and retains the lexicographically smallest stable mapping ID.
5. Validates the smoke run ID, input hashes, unique question keys and audit rows; Full must be disjoint from Smoke and cover exactly all 500 rows.
6. Writes per-question labels only to a private local result directory. The public aggregate contains no question text, SQL, question IDs, database/table names, mapping IDs, or per-question scores.

Eight focused unit tests passed in the fixed CPU environment. The experiment code changed only in the project's own repository; no third-party upstream repository was modified.

## Data, model, environment, and resources

| Input | Frozen source | SHA-256 |
| --- | --- | --- |
| Reviewed SQLite questions | `/mnt/liansp3/sources/datasets/bird_mini_dev_2026_reviewed/mini_dev_sqlite.jsonl` | `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606` |
| Official SQLite DDL | `/mnt/liansp3/sources/datasets/bird_mini_dev_2026_reviewed/sqlite_schema.json` | `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b` |
| Legacy BIRD schema inventory | `/mnt/liansp3/sources/datasets/bird/dev/dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| FK candidates from P1.5 artifact | `/mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json` | `5bc60f6d64429215fa92d3d3a42f1a4881dc77c09839729153fb55a119555060` |

The frozen model settings were G-reasoner-34M (`/mnt/liansp3/sources/models/g-reasoner-34m`, weights SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`, config SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`) and Qwen3-Embedding-0.6B (`/mnt/liansp3/sources/models/qwen3-embedding-0.6b`, weights SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`, config SHA-256 `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`). **Neither model was loaded or called** because the CPU label gate failed.

- CPU environment: existing `think2sql_20260909`, Python `3.12.14`, SQLGlot `28.0.0`, SQLite `3.53.2`; no dependencies installed or changed.
- Preflight: four RTX 4090 GPUs were idle (11–14 MiB used each, 0% utilization); 192 logical CPUs; 450 GiB available RAM; 112 TiB available disk. The audit used CPU only; GPU time was 0.
- Configuration SHA-256: `d67605587492ab3adb5ddba2bfd9075b8ec410f93b0efbe2f0a12c35a554872f`.
- Executed code commit: `deb0b9ec1e25292f6e1036ba2b4b2259f8129678`.
- No random seed was used; smoke selection is deterministic by the registered SHA-256 rule.

## Results

The successful smoke parsed all 5 selected rows. Its 7 qualified `JOIN ON` equalities were all resolved, with no scope errors. It contained no scored mapping pairs, which did not affect its role as a pipeline smoke.

The Full split parsed all 495 non-smoke rows. Combined over the complete 500-row denominator:

| Gate or diagnostic | Result | Registered requirement | Outcome |
| --- | ---: | ---: | --- |
| SQL parse success | 500/500 (100.00%) | ≥98% | Pass |
| Qualified `JOIN ON` equality resolution | 523/663 (78.88%) | ≥95% | **Fail** |
| Full scored question×table-pair cases | 48 | ≥30 | Pass |
| Full databases with scored cases | 4 | ≥3 | Pass |
| Scope-analysis errors | 0 | 0 | Pass |

Across both splits the parser saw 685 `JOIN ON` equalities, of which 663 had two qualified column operands. It resolved 523 and left 140 unresolved. The audit did not further classify those 140 cases by alias, derived-table, or column cause; no finer attribution is claimed. The candidate artifact also contained 3 invalid-endpoint rows that were skipped and 1 duplicate complete mapping identity that was collapsed before candidate counts.

**Decision:** `STOP_LABEL_GATE_FAILED`. No G-reasoner ranking, Dense comparison, BM25 score, or model-generated review was run in this experiment. The result does not establish a ranking failure; it establishes that this parser's eligible-label coverage is below the registered threshold. Do not tune or rerun the same ranking experiment on these partial labels. Any future parser-coverage study needs a separate registration and a bounded error taxonomy.

## Reproduction record

Successful smoke command:

```bash
conda run -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/audit_minidev_sql_fk_labels.py \
  --config configs/text2sql/p0_minidev_sql_fk_mapping_rank_20261106.json \
  --split smoke --attempt 2 \
  --expected-commit deb0b9ec1e25292f6e1036ba2b4b2259f8129678 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/cpu_smoke_002
```

Full command:

```bash
conda run -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/audit_minidev_sql_fk_labels.py \
  --config configs/text2sql/p0_minidev_sql_fk_mapping_rank_20261106.json \
  --split full --attempt 2 \
  --expected-commit deb0b9ec1e25292f6e1036ba2b4b2259f8129678 \
  --smoke-private /mnt/liansp3/sources/results/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/cpu_smoke_002/private_labels.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/cpu_full_002
```

The smoke took 0.159 s wall / 0.041 s CPU and peaked at 31.5 MiB RSS. Full took 0.800 s wall / 0.783 s CPU and peaked at 34.5 MiB RSS. Original question-level labels, IDs, SQL, manifests, and logs remain local under `/mnt/liansp3/sources/results/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/` and `/mnt/liansp3/logs/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/`; `cpu_smoke_001` is preserved separately as the failed pre-parse attempt. Only `aggregate_summary.json` is public.

## Usage and cost

This round made no local-model or external API requests: confirmed input/output/total tokens were `0/0/0`, unknown-usage requests were `0`, estimated model/API cost was `0 CNY`, and GPU time was `0`. No supplier bill was involved; CPU time is reported separately above.

## Limitations

The 140 unresolved qualified equalities prevent reliable label-coverage claims at the preregistered level. Since the audit does not retain per-question failure categories in its public output, one cannot infer which source of ambiguity dominates. The additional table in the newer schema is accepted under the amendment, but a future parser-coverage project would need to verify whether new-schema joins are represented in the frozen FK candidate artifact. None of these diagnostics tests SQL execution correctness, semantic uniqueness of joins, database discovery, or overall QuadGraph/GFM-RAG performance.
