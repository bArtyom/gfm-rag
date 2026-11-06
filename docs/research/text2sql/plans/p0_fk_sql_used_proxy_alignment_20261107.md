# P0：冻结 FK 排序对参考 SQL 映射的配对复核

**状态：预注册；尚未读取 Gold SQL、解析标签或运行 Smoke。** 结果只回答参考 SQL 明确使用的 FK mapping 排序，不回答唯一语义正确的业务关系。

## 研究问题与核心假设

前一轮在三模型代理接受集合上，冻结 G-reasoner 的 Accepted@1 为 7/38，Dense Cosine 为 27/38。该结果可能受代理标签与参考 SQL 选择不一致影响。本实验在**完全相同的 55 个非 Smoke 问题×表对及既有冻结分数**上，改用每题参考 SQL 显式 `JOIN ... ON` 实际使用的已声明 FK mapping 作评价目标，检查 G-reasoner 相对 Dense 的排序差是否仍存在。

**核心假设：** 在解析可可靠确定 SQL-used mapping 的样本上，G-reasoner 的 Mapping@1 比 Dense Cosine 至少高 5 个百分点、净救回至少 4 个单元，且至少两个各有不少于 5 个有效单元的匿名数据库净救回为正。达到此门仅构成独立复现候选，不构成总体方法收益。

SQL-used mapping 只表示“该参考 SQL 的明确连接条件使用了该映射”。它不是人工 FK Role 标签，也不排除其他业务上等价或正确的 mapping。表对与候选集合来自原 BIRD dev 参考 JOIN；任务仍是已知表对后的条件式排序，不能称端到端 JOIN 发现、SQL EX 或跨数据库泛化。

## 方案取舍

1. **再加模型审阅者：不采用。** 同一 60 单元包已由两个本地 Qwen 审阅，后续又由 Gemma 独立审阅；同一代理标签上的排序也已完成并按停止门关闭。增加模型票不会建立独立真值。
2. **修补 2026 Mini-Dev SQL 标签解析器：不采用。** 该独立 500 题迁移审计的 JOIN 等式列解析率为 523/663（78.88%），未过 95% 门；本实验不沿用其部分标签或重开解析器扫描。
3. **复核既有 55 对冻结分数与原 BIRD dev SQL：采用。** 仅用本地 CPU 解析 55 条样本 SQL，并重算已有候选排序的 Mapping@1/@3/MRR；不重新加载或调用任何模型。它直接检查上一轮 NO-GO 是否依赖模型代理标签，且可以在一次有界运行内回答。

## 数据、版本与边界

- 项目仓库：`https://github.com/bArtyom/gfm-rag`；本分支从已归档的最新工作分支 `research/gfm-minidev-scope-binding-20261106`、commit `7f7779480084ccc2a068088579b3a78aaf4a6386` 起步。该分支比仓库 `main` 更新；`main` 仍停留在 2026-10-24，故本计划承接 7f777948 的最新研究指导。
- 数据：本地原版 BIRD dev `dev.json`（1,534 题）与 `dev_tables.json`；只取已有 pair-level 包中的 60 个已冻结 question×table-pair，并严格按已冻结 rank pilot split 分成 5 个 Smoke 和 55 个 Full。Smoke 与 Full 不重叠。
- 代理标签：已有本地 Qwen reviewer A/B 与 Gemma reviewer C 输出；只重用它们，不产生新推理。此前排序诊断的 `private_predictions.jsonl` 为 G-reasoner、Dense、BM25 与稳定顺序的冻结候选排名；主对比只用 G-reasoner 与 Dense。
- 解析器：复用 `audit_minidev_sql_fk_labels.py` 的 scope-aware SQLGlot SQLite AST 规则，但只在本实验抽中的原版 BIRD dev 问题上运行。仅认同一 `JOIN ... ON`、同一 alias pair 内完整匹配的列等式；`WHERE`、`USING`、无法解析/绑定的等式不推断为 FK mapping；复合 FK 必须全部列对在同一 JOIN-ON / alias pair 中出现。
- 关键输入 SHA-256：

| 输入 | SHA-256 |
|---|---|
| BIRD dev `dev.json` | `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` |
| BIRD dev `dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| Pair-level private manifest | `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7` |
| Frozen rank predictions, Full 55 | `d06f07b2b1000e40dbc0614e9bdbe224a79130010011721b97eccaf3dd9b2484` |
| Frozen Smoke/Full split | `40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0` |
| Qwen reviewer A output | `f3d2beb21290c49790679e53ac0bf8dc50084b7b34ee228843f06330ac120883` |
| Qwen reviewer B output | `2b49a5772f061ed70f02ea21811e392fd6afd086fa7030aca9fe737c2c8af077` |
| Gemma reviewer C output | `88c5b79785af76896055378ece4776b523bdb036588304cd63305db51a10d333` |

The public repository will contain only the protocol, runner, sanitized aggregates, and report. Questions, SQL, database/table names, mapping IDs, reviewer text, scores by pair, and row-level outputs remain private under `sources/results/` and `logs/`.

## Registration gates, budget, and stopping

- **Layer:** one exploratory label-target validity / frozen-score re-evaluation. No model or method changes.
- **Budget:** one CPU Smoke over the five pre-frozen Smoke cases, followed by one CPU Full pass over the 55 pre-frozen Full cases if Smoke passes. No retry, parser variant, sample expansion, training, GPU, model, or external API call.
- **Smoke gate:** all five SQL statements parse; zero scope-analysis errors; every qualified explicit JOIN-ON equality in each scored Smoke question resolves; candidate IDs, pair IDs, question-key hashes, and database/question joins match the frozen manifests; at least four of five cases have a complete equality parse and map to one or more frozen candidates.
- **Full label gate:** at least 54/55 SQL parse successfully; zero scope-analysis errors; at least 30 cases have no unresolved qualified JOIN-ON equality anywhere in that question and have one or more SQL-used mappings inside the frozen candidate set; those cases span at least three anonymous databases. This conservative question-level completeness rule may exclude a row because of an unrelated join. A case with no complete parse or no matched candidate is reported separately and never counted as a ranking error.
- **Primary metric:** set-valued SQL-used Mapping@1, where a ranked mapping is accepted if it is among the complete mapping IDs extracted from that sample's explicit reference JOIN-ON conditions. Report G-reasoner and Dense counts/rates, paired rescue and damage, and per-anonymous-database counts.
- **Secondary metrics:** Mapping@3 and MRR to the first SQL-used mapping; proxy-set inclusion of at least one SQL-used mapping and exact set equality, reported descriptively. A proxy that accepts extra mappings is not labeled a false positive because SQL is not a complete semantic equivalence set.
- **Success screen:** same thresholds as the prior pilot: G-reasoner at least +5 pp, net rescue ≥4, and positive net rescue in at least two databases with `n≥5`. If the evaluable gate fails, status `STOP_SQL_LABEL_COVERAGE`; if the success screen fails, stop without adjusting the model or graph.
- **No leakage:** SQL and derived labels enter only after frozen predictions are loaded and validated; they are not used to create features, candidates, rank scores, prompts, or splits.

## Environment and execution record

- CPU environment: existing `think2sql_20260909`, Python 3.12.14, SQLGlot 28.0.0. No dependency installation or changes.
- Expected use: CPU-only. At preflight, all four RTX 4090 GPUs were 80–82% occupied (about 15.9–16.3 GiB used per GPU); this experiment must not request any GPU. RAM available was 447 GiB, 192 logical CPUs, disk free 112 TiB.
- Initial project commit: `7f7779480084ccc2a068088579b3a78aaf4a6386`; current runner/config commit will be recorded before the first Smoke and pinned by `--expected-commit`.
- No local or hosted model/API calls are planned; confirmed inference tokens and API cost for this run are expected to be 0. CPU wall time and peak RSS will be recorded separately.
- Run IDs: `p0_fk_sql_used_mapping_alignment_20261107_smoke_001` and `p0_fk_sql_used_mapping_alignment_20261107_full_001`.
- Private outputs: `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_01/`; logs: `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_01/`.

## Outcome interpretation

This audit can show whether the previously observed G-reasoner/Dense ordering transfers to the reference SQL's explicit mapping choice on these same 55 BIRD dev pairs. Agreement with SQL-used mappings is one-sided evidence for the proxy labels; disagreement does not prove the reviewers' alternative mappings are semantically wrong. Even a positive G-reasoner result would remain an exploratory same-dataset diagnostic and would require an independently sampled evaluation before a broader method claim.

## Amendment 001 — freeze complete-equality eligibility before execution

Before any sample SQL was parsed, the Full eligibility rule was tightened to require that every qualified explicit JOIN-ON equality in a question resolves. The parser helper returns query-level resolution counters, not counters isolated to the selected table pair; therefore this conservative rule may drop a question because of an unrelated join, but it avoids treating a partially extracted mapping set as complete. No input, sample, model, ranking, success threshold, run budget, or result was read or changed. This is the only pre-execution amendment.
