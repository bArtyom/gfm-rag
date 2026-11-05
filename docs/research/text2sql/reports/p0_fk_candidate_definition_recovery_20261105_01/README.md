# P0 FK 候选定义对账恢复

**状态：`STOPPED_BY_SMOKE_GATE`；2/3 个 Smoke 通过，P1.5 臂在冻结文件哈希检查处失败；未启动 Full。** 本轮独立恢复 `p0_fk_candidate_definition_reconciliation_20261105_01` 的通用错误定位缺口，不改原失败记录或科学定义。

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
| 注册提交与 GitHub readback | 完成 | 代码与环境预检修订位于远端 commit `9e8c4fbabe5372340bbb15f2c82d483ffd5ad31f`；6 个实验变更文件逐个与本地内容逐字节核对一致。三条具体 Smoke 命令随本次配置修订在启动前登记。 |
| 输入 / 环境 / 资源预检 | 完成 | 三个数据文件 SHA 与登记值匹配；绝对解释器版本已核对；运行前资源快照见 config。 |
| 三臂 5 题 Smoke | 已运行，2/3 通过 | 两个 P0 packet 环境均通过；P1.5 臂停止在 FK artifact hash gate。 |
| 三臂 1,534 题 Full | 未运行，按预注册门停止 | P1.5 Smoke 失败后不得启动任何 Full。 |
| 匿名差异分类 | 未运行 | 全量 crosswalk 未生成。 |

## Smoke 结果与停止原因

三次运行均从公开执行源码 commit `0f292f1895d0468d3a5da6ab0015af0d2c0a65d3` 的干净工作树启动；输入、源码和目标环境 hash/version 在启动前再次匹配。每个结果和日志都写入独立私有路径，未覆盖旧产物。

| Smoke 臂 | 结果 | 样本 / 解析 | FK 匹配题 / 多 FK 候选题 | CPU 秒 / wall 秒 / 峰值 RSS |
|---|---|---:|---:|---:|
| packet / Python 3.10.22 / SQLGlot 26.33.0 | `SMOKE_PASS` | 5 / 5 | 3 / 0 | 0.0600 / 0.0614 / 0.0264 GiB |
| packet / Python 3.12.14 / SQLGlot 28.0.0 | `SMOKE_PASS` | 5 / 5 | 3 / 0 | 0.0600 / 0.0611 / 0.0293 GiB |
| P1.5 / Python 3.12.14 / SQLGlot 28.0.0 | `STOP_INVALID` | 在问题解析前停止 | 0 题已处理 | 失败运行未写资源回执 |

P1.5 安全失败回执记录阶段 `load_p1_5_inputs_and_fk_artifact`、异常类型 `RuntimeError`，栈帧落在恢复 runner 第 195 行的 frozen FK artifact SHA 校验；处理计数为空。回执不记录异常消息、问题/SQL、数据库名或局部变量。独立启动前检查和停止后的文件复核都得到 artifact SHA-256 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`，与预注册值一致；runner 当时计算出的 digest 未写入回执，因此具体不一致原因尚未查明。按冻结停止门，本轮不重试该臂，也不启动 Full。

安全公开汇总见 [`smoke_summary.json`](smoke_summary.json)。私有结果和日志保存在 `/mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_definition_recovery_20261105_01/smoke/` 与 `/mnt/liansp3/logs/p0_fk_candidate_definition_recovery_20261105_01/`；逐题行、失败回执、原始日志不上传。三臂均无 API / 模型 / GPU / SQL 执行；API token 与外部 API 费用为 0。

## 预定停止与结论边界

旧 P0 v3 的 956/174 只有聚合数字，无法从本次题级 crosswalk 复原。本次两个 packet Smoke 只确认两个冻结解析环境可处理固定五题；P1.5 臂的 artifact hash gate 异常使整轮在 Full 前停止，三套计数差异仍未解释。审计完成不等于 Join Role 标签被人工确认，更不代表提出的方法提升 SQL EX。

本文件当前是预注册，不含实验结果。运行后只追加实际命令、环境、hash、smoke/full 结果、异常、安全资源、匿名计数、局限和下一步决定；失败现场另记，不覆盖。
