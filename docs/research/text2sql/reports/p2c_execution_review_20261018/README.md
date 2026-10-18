# P2c 双视图实验停止原因：结果审计与下一轮决策（2026-10-18）

> **审阅性质：已提交实验回执与源码静态审计；非新实验。** 起始代码提交 `8e35fc282ec7a449e93716e17708bea0cec3e3d2`。证据：[原 P2c 报告](../p2c_dual_view_20261018_01/README.md)、[失败回执](../p2c_dual_view_20261018_01/execution_failure_receipt.json)、[冻结实验配置](../p2c_dual_view_20261018_01/experiment_config.json)、[`run_p2c_dual_view_factorial.py`](https://github.com/bArtyom/gfm-rag/blob/main/scripts/text2sql/run_p2c_dual_view_factorial.py) 与 [原方案](../../plans/p2c_dual_view_retrieval_context_factorial_20261018.md)。

## 1. 这轮结果是什么？

**科学结果：UNAVAILABLE，不是 NO-GO，也不是 PASS。** 初始 P2c 预注册的 Full 恢复额度已耗尽；没有 Full `aggregate_summary.json` 和私有逐题行，不能从过去的 P2b R0/R1 数字反推新组合 V01/V10 的表现。

- Preflight 首次因错误配置键 `final_result` 停止；唯一恢复成功。
- 5 题 Smoke PASS：四臂有限值、同一 score view 的 Top-K 不变量及 P2b 逐题回放 PASS；但 Smoke 不属于正式效果证据。
- Full `..._01`：四臂实际评分和逐题 replay 通过，在查找 P2b 公开聚合条件键 `R0_local_cpu_pass1` 时出错：正确公开键是 `R0_local_cpu_pass_1`；没写结果。
- 唯一 Full 恢复 `..._02`：四臂评分与逐题回放再次通过，但对本地汇总查 `column_r5_query_macro` 报 `KeyError`；没写结果。旧预注册禁止第三次 Full。
- 累计两个 preflight、一个 Smoke 和两次 Full 为 **73.965 CPU s / 73.943 wall s，峰值 0.980 GiB RSS**，模型 forward/GPU/API/SQL 执行均为 0。
- 这是**聚合器契约/字段映射失败**，目前没有证据指向向量模型或方法假设的错误。P2b Values 去除的主结果仍是 **Column R@10 −0.96 pp（CI [-2.06,+0.08]）、Complete@1024 +9.32 pp、总体文本 tokens −27.0%**；P2b 原判 NO-GO 保持。

## 2. 源码静态排查：不是简单一个拼写失误

在 `run_p2c_dual_view_factorial.py`：

- L228–254 `assert_p2b_aggregate_replay` 把 **P2b archive 的字段名**和 **P2c summarize_rows 的字段名**设为同一套。
- 但 L490–529 `summarize_rows` 生成的是嵌套 `column_recall_query_macro` 和 `budgets`；L228–254 却用扁平 `column_r5_query_macro`、`complete_query_macro`、`budget_recall_query_macro`、`mean_tokens_used` 读取。修好第一个 `KeyError`，下一步还可能在预算字段或对象层级再次失败。

经读取仓库 P2b 归档 JSON，映射**必须完整明确**：

| P2b 已归档指标位置（`baseline[group]`） | P2c 现有汇总位置（`replay[group]`） |
|---|---|
| `column_r5_query_macro` | `column_recall_query_macro["5"]` |
| `column_r10_query_macro` | `column_recall_query_macro["10"]` |
| `column_r20_query_macro` | `column_recall_query_macro["20"]` |
| `complete_query_macro[budget]` | `budgets[budget]["complete_query_macro"]` |
| `budget_recall_query_macro[budget]` | `budgets[budget]["gold_schema_recall_query_macro"]` |
| `mean_tokens_used[budget]` | `budgets[budget]["mean_returned_tokens"]` |

其中 `group∈{all,fixed_non_saturated}`、`budget∈{"512","1024","2048"}`、`arm∈{V00,V11}`（以公开键 `R0_local_cpu_pass_1`、`R1_local_cpu_without_values` 为源）。共 **2 arms × 2 groups × (3 Column + 9 budget) = 48 个指标契约比较**，各项比较必须有一致的分母与明确浮点容差（历史 `atol=1e-14,rtol=0`）。

**要求修的是读取映射，不是重新计算/修改实验指标，也不是丢掉 replay 检查。** 审查此映射不代表已经在实验主机执行任何回归测试。

## 3. 研究上有什么值得保持的东西？

P2b 之前已证明表示变化与 prompt 长度变化共同影响预算指标，却未分离二者；P2c 的 V01/V10 正是解决此可识别性问题的合理设计。**原研究问题继续值得完成**，但不值得为一个字段错误继续消耗新的模型训练或反复修改科学阈值。

需要特别注意：

- 同排序、较短的 Context **不保证**完整 Schema 命中单调增加：first-fit / greedy 装包中，之前因过长跳过的早位候选缩短后可能被选择，继而挤掉后面的 Gold。**V01−V00 方向必须实际计算**。
- V01 即使离线 Complete@Budget 改善，也删掉字段 Values 的业务信息，未必提升 SQL 的谓词/枚举理解；SQL EX 必须独立测试，不能用 Schema Gold coverage 替代。
- dual-view 是合理的信息分离与预算工程基础，并非自动成立的 G-reasoner 图算法新贡献。主研究仍是 FK/JoinInstance 保真、Query-conditioned Edge Scoring、合法 JOIN 子图，**FK/Role Gold Gate 未过、没有图模型实测**。

## 4. 下一轮唯一执行判断

**STOP 在旧 `p2c_dual_view_20261018_01` 下再运行 Full**。下一轮首先完成纯 CPU 的 **P2c-R 报告契约修复及全流程离线测试**；再另立带有完整失败历史与独立预算、保持同一科学 H1/H2 的 **新恢复实验记录**，而非在旧注册下非法运行第三次 Full。

建议方案：[P2c-R 恢复与全流程契约测试](../../plans/p2c_r_replay_contract_recovery_20261018.md)。

只有全部测试在真实 P2b 公开 JSON 上能通过、在冻结缓存上能复现 V00/V11 后，才允许**一次**新的独立 Full 恢复（同数据、同向量、同阈值，不以预览结果选择参数）。如果未过契约测试，停止，**不运行新 Full**。

P2c-R 若实际完成才评价 V01 对 Complete@1024 的全体 ≥+5.0 pp、固定困难集 ≥+3.0 pp、两组 CI 下界 >0、固定五库方向门；这些是之前冻结的门槛，**不是本次新观察**。无论完成与否，独立推进 FK/Role 数据治理，并报告 student_club 的元数据缺口，而非抢先上 GNN。
