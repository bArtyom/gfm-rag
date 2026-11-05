# P0 FK 候选定义对账恢复

**状态：`PREREGISTERED`；未启动数据 Smoke。** 本轮独立恢复 `p0_fk_candidate_definition_reconciliation_20261105_01` 的通用错误定位缺口，不改原失败记录或科学定义。

## 研究问题

在固定 BIRD dev 输入 hash 下，旧汇总 956/174、P1.5/P2a.5 的 970/197、P0 packet 的 1,043/176 无法直接视为同一种标签定义。前一轮 packet 两环境 Smoke 通过，P1.5 Smoke 以 `RuntimeError` 结束，输出没有异常位置。当前 trusted human Role label 仍为 0，不能开展 Role 准确率实验。

本轮恢复问题是：用不记录异常消息、SQL、问题文本、数据库名或局部变量的回执定位失败，并在全新 run ID 下重过三个 5 题 Smoke。三臂都通过后才运行全量只读审计。

## 冻结条件

- 计划：[恢复协议](../../plans/p0_fk_candidate_definition_recovery_20261105.md)
- 配置：[experiment_config.json](experiment_config.json)
- 仓库分支：`research/p0-fk-candidate-definition-recovery-20261105`
- 基线 commit：`6c1e29b13d5cd0034fb769d91ed79cc282537157`
- 数据：BIRD dev 1,534 题；`dev.json` / `dev_tables.json` SHA、P1.5 私有 FK artifact SHA、三套源 SHA 见 config。
- 层级：CPU-only exploratory 定义审计；GPU/model/API/SQL execution/training/download/install/human review = 0。
- 固定环境：Python 3.10.22 + SQLGlot 26.33.0（packet）；Python 3.12.14 + SQLGlot 28.0.0（packet/P1.5）。
- 冻结定义、分母、计数、Smoke 与 Full Gate 均沿用已推送的注册计划；不为了复现历史计数修改解析或匹配规则。

## 代码差异

恢复版协调器是原 runner 的独立副本。添加私有 safe failure receipt，仅含阶段、异常类/模块、栈帧模块/函数/行号、当前题键 SHA-256 和处理计数；不保存异常文字、源码行或局部变量。恢复版 comparator 在既有配对标签计数上加预注册的 P1.5 状态分层。旧 runner、旧 comparator 与历史结果保持不变。

## 执行记录

| 阶段 | 状态 | 说明 |
|---|---|---|
| 资源检查 | 完成 | CPU-only；运行前快照见 config。 |
| 注册提交与 GitHub readback | 待完成 | 完成后更新 commit、远端路径与 hash。 |
| 三臂 5 题 Smoke | 未运行 | 任一失败即停止所有 Full。 |
| 三臂 1,534 题 Full | 未运行 | 仅在全部 Smoke 通过后执行。 |
| 匿名差异分类 | 未运行 | 仅在全部 Full 通过后生成。 |

## 预定停止与结论边界

旧 P0 v3 的 956/174 只有聚合数字，无法从本次题级 crosswalk 复原。即使恢复 Full 通过，也只可能解释 packet 与 P1.5 这两个有可运行代码和逐题产物的定义差异。审计完成不等于 Join Role 标签被人工确认，更不代表提出的方法提升 SQL EX。

本文件当前是预注册，不含实验结果。运行后只追加实际命令、环境、hash、smoke/full 结果、异常、安全资源、匿名计数、局限和下一步决定；失败现场另记，不覆盖。
