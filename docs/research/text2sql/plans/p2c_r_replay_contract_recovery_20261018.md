# P2c-R 恢复实验执行协议：先封闭聚合契约，再恢复一次 Full

> **制定 2026-10-18；状态：新计划，尚未修复代码/运行实验。**
>
> 历史 P2c [失败报告](../reports/p2c_dual_view_20261018_01/README.md)必须保持 `STOPPED / no scientific result`；其唯一 Full recovery 已耗尽，**禁止在原 run ID / 原注册下做第三次 Full**。本文件提出一个**独立的后续恢复试验登记**，保持原冻结数据、方法与科学成功门完全不变，公开交代为何要再启动。所有 P2c-R 数据在注册和契约测试通过之后才能产生。先看 [源码核对与原因分析](../reports/p2c_execution_review_20261018/README.md)。

## 0. 执行边界与目标

- 目的仅为让已被前两次 Full 正确完成的**四臂计算/逐题重放**可靠地进入聚合计算及落盘；不扩大候选、不修改 Dense scorer、P2b CPU embedding cache、R0/R1 序列化、tokenizer、分母、Bootstrap seed 或实验指标。
- 原假设 H1：V00/V01 与 V10/V11 每题同 score view 的 Table/Column Top-K 完全一致。
- 原主要 H2：`V01−V00 Complete@1024`，全 1460 题 ≥+5.0 pp，R0 冻结的困难 5 DB/706 题 ≥+3.0 pp，两组 DB-cluster 95% CI 下界都 >0，困难 5 库中 ≥3 库 delta≥0 且 ≥2 库严格>0；BIRD dev 只能说明后续验证资格。
- 旧 P2b 预注册 NO-GO、旧 P2c **无科学结果**、FK/Role Gate NO-GO 都要原样保留。
- 现有的 `tests/test_p2c_dual_view_factorial.py` 约 118 行测试只覆盖了键名/配对的部分合同，没有真实 `assert_p2b_aggregate_replay` 的全字段成功路径，故之前两次字段错误均在 Full 才暴露。

## A. Gate 0 — 纯静态 / CPU 修复与集成回归测试，不运行 Full

### A1. 修正全字段版本适配

在 `scripts/text2sql/run_p2c_dual_view_factorial.py` 的 `assert_p2b_aggregate_replay()` 中**显式解析** P2b archive 与 P2c nested summary 的不同路径：

```text
P2b archive                         P2c local summary
column_r5_query_macro              column_recall_query_macro["5"]
column_r10_query_macro             column_recall_query_macro["10"]
column_r20_query_macro             column_recall_query_macro["20"]
complete_query_macro["512"]         budgets["512"]["complete_query_macro"]
budget_recall_query_macro["512"]    budgets["512"]["gold_schema_recall_query_macro"]
mean_tokens_used["512"]            budgets["512"]["mean_returned_tokens"]
... 1024、2048 相同映射
```

每个归档条件 R0/R1 × all/固定非饱和子集应核对 12 个数，总共**48 个**；容差及分母沿用旧冻结方法。出现任何缺键/非有限值/分母不符要显示**完整指标路径**，不得以 `dict.get(..., default)` 静默跳过。

### A2. 最少必要测试

1. 用仓库已归档 `docs/research/text2sql/reports/p2b_values_ablation_20261018_01/aggregate_summary.json`（**不是 mock 的虚构 key**）做成功路径合同测试，读取其 `conditions.R0_local_cpu_pass_1` 和 `conditions.R1_local_cpu_without_values`、检查 48 个字段及 nested paths。
2. 合成 P2c nested summaries，使每项与对应真实 P2b 归档精确相等，调用完整 `assert_p2b_aggregate_replay()`，必须 PASS；对 48 个字段分别注入单独的 `+0.01` 变动，每项都必须 FAIL 且指出 metric path。对缺键、`None`、`NaN`、空集合分别 FAIL。
3. 对 `build_aggregate()` 做**全路径 CPU 小型集成测试**，在测试构造的 5+ 问题、≥2 DB 的四臂 scorer rows 上覆盖 nested aggregate、factorial contrast、paired rescue/damage、bootstrap、per-DB alias、隐私过滤、`aggregate_summary.json` 写入→读取→SHA 校验。只调用 unit fixtures，禁止私有 BIRD/Gold 上传仓库。
4. 用真实已归档 P2b `per_question_private.jsonl` 和 CPU cache 在本机做 **dry-run complete aggregate**（运行输出到临时私有目录，`mode=test-contract` 或另独立 `scripts` harness）；完整执行 V00/V01/V10/V11 → replay → build_aggregate → 写入/读回，**只检查无异常、48 项 parity、输出 JSON schema、nan/inf、计数和哈希，不读取、打印、比较 V01 或 V10 的 Complete 结果，也不做 H2 门槛判断**。这是工程契约验证不是科学实验，日志不能包含四臂结果值。
5. 作为额外回归测试，模拟“缩短前面高分候选使它从不适合变适合”导致某个后方 Gold 被挤出，验证 Context 更短时 Complete 不被错误地假设单调增加。
6. 不能在单元测试成功前开始任何新的 Full。所有执行代码应独立提交，确保 `git status` clean、锁定 commit 和脚本 SHA，报告旧 P2c 的两次失败根因。

**Gate 0 = 所有测试通过 + 真实 P2b archive 48 项 PASS + 私有缓存 dry-run aggregate 成功落盘且检查值不用于调参 + 版本/资源完整**。无法验证就 STOP，并只提交工程失败报告。

## B. Gate 1 — 独立 P2c-R 注册和正式恢复

- **只在 Gate 0 通过后**，新建 `docs/research/text2sql/reports/p2c_r_recovery_YYYYMMDD/experiment_config.json`：记录前一轮 2 次 Full 失败、原预注册 SHA、数据/模型/CPU 向量哈希、冻结四臂定义、H1/H2 判据、审查记录、最新 commit、全量限额以及新 run ID。
- 明确声明这是在发生报告层执行失败后的**独立恢复试验**，不得将它冒充原 P2c 预注册允许的第三次 Full；科学对照及评测阈值保持原样。
- 先执行固定 5 题 Smoke，验证 P2b row parity 与全链路 aggregate **写出和读回**；再执行一轮 1534 题 Full，测试和 Full 必须使用同 commit/输入/缓存 hash。即使之前两次 Full 十几秒完成，本次仍只允许一次注册 Full；新增跑次或变更科学参数需要另行明确决策，禁止观察结果后补修复重跑。
- 建议单次 Full 的资源上限：CPU ≤1800 s、≤8 threads、峰值 RSS≤16 GiB；GPU/API/SQL/模型前向均为 0；无新增依赖/模型下载。全部失败尝试计入账本。
- 新输出仅安全的 DB 匿名聚合、配置、报告和源码 hash 推送至 GitHub；逐题、向量和 Gold SQL 留本地。**禁用打印真实题、预测或业务数据库内容到公共 artifacts**。

## C. 实验完成后如何判断下一步？

| 结果 | 下一步 | 不能宣称什么 |
|---|---|---|
| Gate 0 没通过 / 正式恢复再次报工程错 | 只修实验基础设施并停机，优先转向 FK/Role 数据治理和 GFM baseline engineering | 没有 P2c 的方法效果结论 |
| H1 排名不变量失败 / V00/V11 与 P2b replay 不同 | 科学结果作废，审查 scorer 与 context 分离边界 | 不可以选择性报告有利的 Complete |
| H1 PASS，H2 PASS | 冻结 V01 为**离线候选方案**；下一研究是 **Values-critical SQL 信息风险**审计以及冻结 generator/selector 的数据库级 SQL EX 对照 | 不等于 SQL EX 提升、不代表跨数据库泛化 |
| H1 PASS，H2 NO-GO | 不继续调截断长度/Values 拼接规则；保留旧 R0 检索/展示基线，转向 FK/JoinInstance 标签与 GFM 图检索工程基线 | 不得改写 P2b/P2c-R 失败或为新方案找事后阈值 |

记录原始四臂 complete/column/topk 指标，全体 1460 / 固定非饱和 706，512/1024/2048 budgets、paired rescue/damage、按库 bootstrap 10k(seed=20261020) 和 5 DB 方向，预算 tokens 与 Values 缺失风险。任何 H2 通过仍只是**Schema Gold 节点覆盖代理指标**。

## D. 平行科研主线：T0 FK / JOIN Role 的可评性

现有 P2a.5：103 SQLite FK/100 有效/3 无效；1428 Gold JOIN ON 条件中 1199 唯一匹配 FK、204 未匹配/非声明、25 歧义；197 道有同表多 FK 候选。当前 human role review=0、正式角色准确率可评样本=0。

- 优先审计 `student_club` 的 **90 个 metadata_incomplete ON**、3 个无效 SQLite FK 与 JSON/SQLite 的 5/2 差异；区分元数据缺失、合法非 FK 和解析失败，任何补边都要证据。
- 建立保留 FK instance ID 与多列约束原子性的多关系图构建测试；合成 billing/shipping、桥表、复合 FK 与非 FK 连接。
- 在人工标注标准与一致性检查前，不训练 Query-aware Edge Gate、不报告 Join Path Accuracy；不把这些数据质量问题与 P2c 预算效果混淆。
- 准备另一个明示为工程性质的 GFM GraphReasoner checkpoint/schema graph compatibility smoke，只有确立原始 GFM 的 Text2SQL 基线后才适合评价图新算法。

## E. 交付与下一次分析输入

本计划的**最近唯一优先级**：修复完整字段映射 + 48 项回归合同 + 完整 aggregate 写入的 dry-run；**未完成之前不开展任何新科学方法 sweep**。

执行者下次需回报：合同测试通过数、旧归档 replay 结果、真实 cache 与源码 hash、是否已新注册 P2c-R、正式 Full 是否有合法聚合和 Gate 结果、全体/固定子集真实 H2 指标、对后续 SQL Values 风险的建议。若没有运行，就保留所有性能单元为空，不可把 P2b 的 +9.32pp 写成 P2c 的 V01 增益。
