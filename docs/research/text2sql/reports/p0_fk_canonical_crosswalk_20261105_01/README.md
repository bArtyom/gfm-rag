# P0 canonical P1.5 FK crosswalk 复核

> **状态：`CROSSWALK_COMPLETE`（2026-11-05）。** 5题 Smoke、1,534题 Full 及匿名逐题 crosswalk 均完成。过滤无效 FK 实例后，P1.5 的结果仍为 970/197，与 v3 未过滤适配器逐题相同；packet-28 的 1,043/176 差异仍存在。此为标签定义审计，不是方法效果实验。

## 研究问题与边界

P0 v3 wrapper 把原始 `instances_private` 直接交给 P1.5 `golden_join_audit`，但原 P1.5 汇总路径使用过滤后的 `valid_instances_private`。本轮只修正这一处适配输入，在同一冻结题目、SQLGlot 28 环境下，与既有 packet-28 结果和 v3 未过滤 P1.5 结果做匿名逐题对照。

本轮不改 P1.5 `golden_join_audit`、packet 的 FK 匹配定义、SQLGlot、BIRD 输入、分母或阈值；不使用 Gold 生成运行时特征，不判定业务 Role 正误。它是标签口径/数据契约审计，不是方法效果实验。

## 预注册资料

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)
- 计划：[canonical P1.5 crosswalk 复核计划](../../plans/p0_fk_canonical_crosswalk_20261105.md)
- 代码：`scripts/text2sql/reconcile_p0_fk_candidate_definitions_canonical.py`、`scripts/text2sql/compare_p0_fk_candidate_definitions_canonical.py`
- 运行配置：[`experiment_config.json`](experiment_config.json)
- 预注册分支：`research/p0-fk-canonical-crosswalk-20261105`；参考基点 `1409fbc00bdd13fe41ea93a03db0d0030a72e15c`。
- 数据：BIRD dev，1,534 题 / 11 DB；仅开发诊断用途。公开报告不含问题、Gold SQL、数据库名、逐题标签或私有 artifact 内容。
- 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；CPU-only，最多 8 线程。
- 资源上限：单进程 wall/CPU 600 秒、RSS 4 GiB；累计 CPU 1,800 秒。
- 预算：1 次 5 题 Smoke；通过后 1 次 1,534 题 Full；1 次只读 crosswalk；失败不重试。
- 方法收益/SQL EX/Role accuracy：不适用，不纳入本轮结论。

## 运行记录与结果

| 阶段 | 状态 | 样本 / 分母 | 结果 |
|---|---|---:|---|
| 预检 | PASS | 1,534题输入、11库 FK artifact | 数据、代码、artifact 与两份冻结参考 SHA-256 均匹配；Python 3.12.14 / SQLGlot 28.0.0。 |
| Smoke | `SMOKE_PASS` | 5/5 解析；3题含 `JOIN ON` | 过滤 103 条原始 FK 中的 3 条无效端点实例，只向 P1.5 审计传入 100 条有效实例。Wall 0.123 秒、CPU 0.419 秒、峰值 RSS 0.045 GiB。 |
| Full | `FULL_COMPLETE` | 1,534/1,534 解析；1,140题含 `JOIN ON` | 970题至少有一个唯一 FK match；197题存在 multi-FK candidate。Wall 1.223 秒、CPU 1.843 秒、峰值 RSS 0.045 GiB。 |
| 匿名 crosswalk | `CROSSWALK_COMPLETE` | 1,534/1,534 相同哈希题键 | 三个结果题集相同；逐题字段比较见下表与[安全聚合](crosswalk_aggregate.json)。 |

### 三种定义的汇总计数

| 定义 | 解析题 | JOIN-ON题 | FK-match题 | multi-FK-candidate题 |
|---|---:|---:|---:|---:|
| packet-28 | 1,534 | 1,140 | 1,043 | 176 |
| P1.5 v3 wrapper（raw instances） | 1,534 | 1,140 | 970 | 197 |
| P1.5 canonical adapter（仅 valid endpoints） | 1,534 | 1,140 | 970 | 197 |

过滤前后的逐题布尔标签完全相同：FK-match 的 970 题一致、564 题双方均未匹配；multi-FK 的197题一致、1,337题双方均无候选。因此，3条无效端点实例并未造成 v3 wrapper 与 canonical P1.5 的观测差异。

packet-28 与 canonical P1.5 的逐题交叉结果：

- FK-match：955题双方都匹配，476题双方都不匹配；88题只有 packet-28 匹配，15题只有 P1.5 匹配。
- multi-FK-candidate：176题双方都有候选，1,337题双方均无；另有21题只有 P1.5 标记候选，没有 packet-only 题。
- 在88个 packet-only FK-match 中，P1.5 证据标签为 ambiguous 的有22题、unmatched 的有66题。15个 P1.5-only FK-match 中，14题为 exact，1题同时含 exact 与 unmatched 条件。21个 P1.5-only multi-FK 题的 `role_candidate_join_count` 均非零。

这些差异反映两套程序对完整 FK instance、单个列对命中、歧义及候选的定义不同；它们不代表 Gold business Role 正误。历史956/174只有旧聚合数，没有可复算 runner 或逐题标签，本实验不能恢复其定义。

## 复现信息、资源与结论

- 执行源码为本分支 `scripts/text2sql/reconcile_p0_fk_candidate_definitions_canonical.py` 和 `scripts/text2sql/compare_p0_fk_candidate_definitions_canonical.py`；SHA-256 分别为 `5384c7e94a5814c50a3ff3505029ecc86bd7accad8982beb14fad3b2fa6017a8`、`263f60a2db0570a2ff3d4d9e2e833b518785143e62c60b54625f1a88870ddb55`。数据、FK artifact 与参考输出哈希固定在 [`experiment_config.json`](experiment_config.json)。
- 运行环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；CPU 最多8线程。GPU、模型、API、SQL 执行、训练、下载与依赖安装均为0。Smoke 和 Full 的分阶段 wall/CPU/RSS 见上表；crosswalk 比较器成功退出，但没有单独的进程计时回执，不把工具调用耗时当作 CPU 统计。
- Smoke 与 Full 私有逐题输出、hashed question keys、日志、启动清单保存在权限受限的本地资源入口 `local:results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/` 和 `local:logs/p0_fk_canonical_crosswalk_20261105_01/`，不上传 GitHub。公开 crosswalk 不含题目文本、SQL、数据库名或逐题键。
- [公开匿名 crosswalk](crosswalk_aggregate.json)，SHA-256 `f2360ae188f7a70c75f194b815ed9a5417206e15a0029e4e6b486671e998643d`；私有 canonical Full SHA-256 `746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed`。

**结论：** canonical 输入过滤已与 P1.5 汇总入口对齐，但过滤不改变任何题级标签或汇总计数。packet-28 与 P1.5 的差异仍是可复现的实现定义差异，不能据此判断哪种是 Gold Role，也不能作为 JOIN 检索或图推理效果。可信双人 Role 标签仍为0；真实 Role Accuracy、Join-Path Accuracy、SQL EX 和 Query-aware Role 训练继续保持 NO-GO。

## 解释边界与决策

本轮结果只支持解析及标签口径的逐题一致性检查。过滤后与未过滤 P1.5 的标签相同；packet/P1.5 差异仍未被历史956/174解决。FK-match 或 multi-FK-candidate 都不是 Gold Role 标签；没有人工双审，也没有 JOIN 路径、图推理或 SQL EX 结果。
