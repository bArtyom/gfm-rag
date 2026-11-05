# P0 FK 候选定义恢复 v3：更正冻结指纹后的三臂复核

> **状态：`CROSSWALK_COMPLETE`（2026-11-05）。** 三臂 Smoke、三臂 Full 和预注册匿名 crosswalk 全部完成。本轮是 CPU-only 文件完整性与 FK 定义审计，不是 QuadGraph/GFM 方法增益实验。

## 研究问题与假设

v1/v2 两次 P1.5 Smoke 使用了同一个错误冻结摘要并在解析前停止。v2 中同一字节缓冲区、分块 helper 与独立 `sha256sum` 对目标文件计算出相同摘要，文件身份稳定。v3 仅把此摘要更正到经独立确认的文件指纹，重跑三臂的 smoke 门，并在三臂全部通过时按既定门槛运行 Full。

核心假设：失败原因是先前登记的输入指纹与指定 artifact 不匹配；纠正后，P1.5 同字节摘要/JSON 解析门及三臂 smoke 均通过。任一完整性、解析、环境、计数或资源门失败即可证伪并停止。

## 预注册

- **实验 ID：** `p0_fk_candidate_definition_recovery_v3_20261105_01`
- **层级：** exploratory CPU-only 输入完整性与 FK 标签定义审计；不属于方法效果证据。
- **核心假设、预算、成功与停止门：** 见 [实验计划](../../plans/p0_fk_candidate_definition_recovery_v3_20261105.md) 和 [机器可读配置](experiment_config.json)。
- **项目仓库/基线：** `bArtyom/gfm-rag`，v2 结果 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e`；新分支 `research/p0-fk-definition-recovery-v3-20261105`。
- **执行源码：** `scripts/text2sql/reconcile_p0_fk_candidate_definitions_v3.py` 与 `scripts/text2sql/compare_p0_fk_candidate_definitions_v3.py`；哈希见配置。只更新 runner 的 run ID 和 FK artifact 冻结摘要，不改 packet/P1.5 算法及计数定义。
- **数据：** 固定 BIRD dev 1,534 题，只用于开发/诊断。输入 SHA 与 artifact 正确冻结值见配置；SQL、问题文本、逐题哈希和私有 artifact 内容不上传。
- **环境：** Python 3.10.22/SQLGlot 26.33.0 与 Python 3.12.14/SQLGlot 28.0.0，复用已存在 Conda 环境。
- **执行命令、run ID、资源预算、硬件快照、输出路径：** 见配置、运行日志和最终回执。

## 执行记录与结果

### 注册、实现与输入

- **项目仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-definition-recovery-v3-20261105`。预注册 commit 为 [`1514a20`](https://github.com/bArtyom/gfm-rag/commit/1514a2017afa245439d6e7a3bd28bbd47d949a0a)；注册代码、配置和报告已在运行前逐项做 GitHub blob SHA 回读。
- **本轮实现差异：** v3 runner 只更改实验 ID 和 P1.5 artifact 的冻结 SHA；crosswalk runner 只更改实验 ID。packet/P1.5 解析与候选定义、题序、分母、预期 Full 计数和停止门均沿用 v2。运行器及比较器 SHA-256 见 [配置](experiment_config.json)。
- **指导版本：** 运行前已阅读远端基线 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e` 的根 README、研究 README、路线图及复现规范；文件 blob SHA 见配置。
- **数据：** BIRD dev 1,534 题，11 个数据库；这是重复使用过的开发/诊断数据，不是独立测试集。运行时 `dev.json` 和 `dev_tables.json` SHA 分别匹配 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` 和 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- **纠正后的 FK artifact SHA：** `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。Smoke 和 Full 的同字节缓冲区 SHA、旧分块 helper SHA 与冻结值一致；文件大小 76,177 字节，身份稳定，JSON 从已校验字节解析。
- **环境：** packet/SQLGlot 26 使用 Python 3.10.22；packet 与 P1.5/SQLGlot 28 使用 Python 3.12.14；沿用 `t2sql_code_audit_20261005` 和 `think2sql_20260909`，没有安装或升级依赖。
- **硬件/预算：** CPU-only，最多 8 线程；每进程 wall/CPU ≤600 秒、RSS ≤4 GiB；三组 Smoke、三组 Full、一次比较器运行，累计 runner CPU 约 5.52 秒；峰值 RSS 0.0454 GiB。运行前可用内存约 443 GiB、磁盘约 112 TiB；GPU 未分配。外部 API、模型推理、GPU 任务、SQL 执行、训练均为 0。

### Smoke 与 Full

| 定义 | Smoke | Full 解析 / JOIN-ON | FK 匹配题 | 多 FK 候选题 | Full wall / CPU / 峰值 RSS |
|---|---:|---:|---:|---:|---|
| packet / Python 3.10 / SQLGlot 26 | 5/5 parse | 1,534 / 1,140 | 1,043 | 176 | 1.675 / 1.674 秒 / 0.0264 GiB |
| packet / Python 3.12 / SQLGlot 28 | 5/5 parse | 1,534 / 1,140 | 1,043 | 176 | 1.159 / 1.155 秒 / 0.0308 GiB |
| P1.5 `golden_join_audit` / Python 3.12 / SQLGlot 28 | 5/5 parse | 1,534 / 1,140 | 970 | 197 | 1.235 / 1.856 秒 / 0.0454 GiB |

所有 Smoke 均为 5 题解析成功。P1.5 的 Smoke 同时确认实际摘要、旧 helper 摘要与冻结摘要一致，文件身份稳定，JSON 解析通过。三个 Full 都达到 1,534 题、1,534 parse 成功、1,140 个 JOIN-ON 分母及各自预登记 FK 计数。

### 匿名 crosswalk

三份 Full 结果的题目 SHA 集合一致（1,534/1,534）。两个 packet 环境的题级 FK-match 与 multi-FK 标签完全一致。Packet-28 与 P1.5 在相同 Python 3.12/SQLGlot 28 环境下仍有定义差异：

- **FK 匹配：** 两者都匹配 955 题；packet-only 88 题；P1.5-only 15 题；两者都不匹配 476 题。差异总数 103，与 1,043 对 970 的汇总差一致。
- **多 FK 候选：** 两者都有 176 题；P1.5-only 21 题；packet-only 0 题；两者都无候选 1,337 题。差异总数 21，与 176 对 197 的汇总差一致。
- **按 P1.5 证据类分层：** packet-only FK match 中 22 题被 P1.5 标为 ambiguous、66 题标为 unmatched；P1.5-only 中 14 题为 exact、1 题同时含 exact 与 unmatched 证据。多 FK 候选新增的 21 题在 P1.5 结果中均有非零 role-candidate joins。
- 所有定义的 parse 与 JOIN-ON 标签一致。完整匿名聚合见 [crosswalk_aggregate.json](crosswalk_aggregate.json)；逐题哈希和交叉表只保存在权限 `0600` 的本地私有结果中。

## 结论与下一步

1. v1/v2 的 P1.5 Smoke 失败可归因于错误冻结摘要：v3 在更正后完整通过了同字节哈希与解析门。这不是数据变化，也不是 SHA-256/文件读取故障。
2. packet 的题级结果不受 Python 3.10/SQLGlot 26 与 Python 3.12/SQLGlot 28 变化影响。Packet-28 与 P1.5 在相同解析器环境下仍有 103 题 FK-match 标签差异和 21 题 multi-FK 候选差异，说明差别来自两套定义/实现，而不是仅由 Python/SQLGlot 版本解释。
3. 本实验复现并定位了实现差异，但没有判定哪一套 JOIN/FK 语义更正确。历史 P0 v3 的 956/174 只有聚合计数，仍没有可用于题级 crosswalk 的旧标签；可信双人 Role 标签仍为 0。不能用当前多 FK 候选数替代 Gold Role，也不能把此结果解释为检索、GraphReasoner 或 SQL EX 收益。
4. **研究决策：** 关闭本轮 P0 定义对账；停止继续扫描同类计数。下一步先做历史 P0 v3 的源代码/配置/产物可追溯性审计，并为需要语义判断的分歧另行设计盲审材料；在可信标签可用前，Role Accuracy 和任何基于它的主张保持 NO-GO。当前没有理由启动新的 GPU 或模型实验。

## 产物与调用

- 配置、命令模板、所有 run ID 和哈希：[`experiment_config.json`](experiment_config.json)。
- 安全聚合：[`crosswalk_aggregate.json`](crosswalk_aggregate.json)，SHA-256 `8751fa1930434b2ed1af49c8ec63cd4ff2ddb37d6364513beb752aa409c0e55d`。
- 私有 Smoke/Full 逐题结果：`/mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_definition_recovery_v3_20261105_01/`；私有 crosswalk 在同一目录 `crosswalk_private.json`。日志和启动快照：`/mnt/liansp3/logs/p0_fk_candidate_definition_recovery_v3_20261105_01/`。
- **模型 API usage：** 0 请求，0 输入/输出/总 tokens，0.00 CNY；无外部费用。CPU 时间未货币化。

## 解释边界

即使所有门通过，本轮也只验证输入完整性、三套 parser/标签定义的运行复现及匿名计数差异。它不能说明哪套 FK 定义在语义上正确，不能恢复没有逐题记录的历史 P0 v3 的 956/174 计数，也不会产生可信 Gold Role 标签或 QuadGraph/GFM 方法收益结论。
