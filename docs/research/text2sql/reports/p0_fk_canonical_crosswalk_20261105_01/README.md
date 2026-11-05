# P0 canonical P1.5 FK crosswalk 复核

> **当前状态：`PREREGISTERED_NOT_RUN`。** 新实验用 canonical `valid_instances_private` 输入重放 P1.5 FK 对账；没有运行 Smoke 或 Full。只有代码、计划、配置和新分支已推送并核对后才允许启动。

## 研究问题与边界

P0 v3 wrapper 把原始 `instances_private` 直接交给 P1.5 `golden_join_audit`，但原 P1.5 汇总路径使用过滤后的 `valid_instances_private`。本轮只修正这一处适配输入，在同一冻结题目、SQLGlot 28 环境下，与既有 packet-28 结果和 v3 未过滤 P1.5 结果做匿名逐题对照。

本轮不改 P1.5 `golden_join_audit`、packet 的 FK 匹配定义、SQLGlot、BIRD 输入、分母或阈值；不使用 Gold 生成运行时特征，不判定业务 Role 正误。它是标签口径/数据契约审计，不是方法效果实验。

## 预注册资料

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)
- 计划：[canonical P1.5 crosswalk 复核计划](../../plans/p0_fk_canonical_crosswalk_20261105.md)
- 代码：`scripts/text2sql/reconcile_p0_fk_candidate_definitions_canonical.py`、`scripts/text2sql/compare_p0_fk_candidate_definitions_canonical.py`
- 运行配置：[`experiment_config.json`](experiment_config.json)
- 数据：BIRD dev，1,534 题 / 11 DB；仅开发诊断用途。公开报告不含问题、Gold SQL、数据库名、逐题标签或私有 artifact 内容。
- 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；CPU-only，最多 8 线程。
- 资源上限：单进程 wall/CPU 600 秒、RSS 4 GiB；累计 CPU 1,800 秒。
- 预算：1 次 5 题 Smoke；通过后 1 次 1,534 题 Full；1 次只读 crosswalk；失败不重试。
- 方法收益/SQL EX/Role accuracy：不适用，不纳入本轮结论。

## 运行记录

| 阶段 | 状态 | 结果 |
|---|---|---|
| 预检 / 冻结输入摘要 | 已完成 | 数据文件摘要与已登记版本一致；FK artifact 对应 11 DB / 103 原始 / 100 有效 / 3 无效记录。 |
| Smoke | `NOT RUN` | 等待计划、runner、配置推送并完成远端回读。 |
| Full | `NOT RUN` | 仅在 Smoke 数据门通过后运行。 |
| 匿名 crosswalk | `NOT RUN` | 仅在 Full 及参考题目键集合验证通过后运行。 |

## 解释边界与决策

当前结果尚无科学判断。若本轮运行完成，FK-match 和 multi-FK-candidate 计数及与 packet 的差异只说明解析/标签定义的一致性；不能把它们解释成 Gold Role、JOIN 路径准确率、图推理效果或 SQL EX。历史 956/174 没有可复算源码及逐题标签，仍不可恢复；可信人工 Role 标签目前为 0。
