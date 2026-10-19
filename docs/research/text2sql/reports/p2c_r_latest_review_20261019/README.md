# P2c-R 与 Values 风险／绑定实验复核：从 Schema 覆盖走向 SQL 效用（2026-10-19）

> **类型：最新已运行实验的结果复核、下一阶段研究判断；不是新实验。** 复核时 main 最新历史提交：`bb40f5364fa4b61fdb891a418aae4c8712e5ca12`。全部 BIRD dev 观察属于已经反复使用的数据开发证据，**不能作为独立泛化测试**。
>
> 一手结果：[P2c-R 2×2 全量](../p2c_r_recovery_20261019_01/README.md) / [聚合](../p2c_r_recovery_20261019_01/aggregate_summary.json)；[Values 词面风险](../p2c_values_risk_20261019_01/README.md) / [聚合](../p2c_values_risk_20261019_01/aggregate_summary.json)；[19 题直接绑定](../p2c_value_binding_20261019_01/README.md) / [聚合](../p2c_value_binding_20261019_01/aggregate_summary.json)。

## 1. 新完成了什么？哪些 Gate 通过？

- **P2c-R 全量：H1/H2 PASS。** 先经过完整 48 项公开聚合字段契约 Gate，再独立恢复单次 5 题 Smoke 和单次 1,534 题 Full。冻结 P2b CPU vectors、Qwen3-Embedding-0.6B 1024 维、L2/Cosine、原候选/Gold/装包，无模型前向。V01（R0 检索向量，R1 精简 Context）相对 V00（R0/R0）同一 Query/Table/Column 排名。
- **Values 词面风险：扫描完成，语义必要性未验证。** 1,534 SQL 全部解析，主分母 1,460 的 407 题 / 548 个标记涉及被移除的 Values 文本词面线索。**19 题**有至少一个此类常量也未见于问题/evidence；此结论只覆盖冻结的直接谓词 Literal 规则，未覆盖函数/变换/模式等表达。
- **直接列值绑定：冻结 19 题、21 标记审计完成。** 题级 9 `binding_supported`、8 `binding_mismatch`、2 `binding_unresolved`，标记级分别 10/9/2。**人工语义复核=0、语义必要性分母=0，SQL Generator/SQL Execution 未运行**。
- **P2b 原 NO-GO、旧 P2c 原登记未出科学结果、FK/Role Gate NO-GO** 全部保持。P2c-R 作为新恢复登记通过，不反推老实验成功。

## 2. 关键定量结果（BIRD dev，1460 Column-eligible）

| 条件 | 检索向量文本 / Context 文本 | Column R@10 | Complete@1024 | 固定困难706题 Complete@1024 |
|---|---|---:|---:|---:|
| V00 | 完整 Values / 完整 Values | 67.99% | 56.64% | 37.96% |
| **V01** | **完整 Values / 无 Values** | **67.99%** | **67.60%** | **46.18%** |
| V10 | 无 Values / 完整 Values | 67.03% | 53.77% | 34.14% |
| V11 | 无 Values / 无 Values | 67.03% | 65.96% | 43.48% |

- **V01−V00 Complete@1024 全体 +10.9589 pp**，11 库 cluster bootstrap 95% CI **[+5.3669,+18.6988] pp**，达预设 +5 pp；固定 5 库 706 题 **+8.2153 pp**，95% CI **[+4.1116,+13.1195] pp**，达 +3 pp。固定 5 库全部正向；四臂 replay/排名不变量 PASS。
- 全体 **162 题救回、2 题损坏、1296 不变**；净增加 160 道完整 Schema 覆盖题。R0 Context 的内容变短使平均返回 Schema 元素 **30.36→38.88**，平均实际返回 tokens **949.59→915.23**；候选索引里全部节点文本总 token 缩减 **27506→20071（-27.03%）**，但这不等于全 SQL prompt tokens -27%。
- 这次 2×2 因子对照支持：**保留完整 Values 做检索而缩短呈现**比同时去掉检索端 Values 更有效。相同检索向量下 Column R@10 理应不变且已验证；但**“更完整 Schema 节点”不等于更好 SQL**。

## 3. 值信息丢失的证据及正确解释

- 词面审计的 **407/1460（27.88%）** 是“至少一个参考常量命中被移除 Values 描述”的高召回线索，不是 407 道 SQL 受损；其中 **19/1460（1.30%）** 才同时满足“该常量在问题和已有 evidence 中也不可见”的更严格词面条件。
- 19 题中 9 题有**同一源列的参考 SQL 直接谓词关联**，8 题的直接绑定不一致，2 题的目标属于不支持/变换类型。这只提升待复核的证据质量；**9/19 是有偏筛选集合的绑定支持率，不是 SQL EX 错误率或全体风险率**。
- 报告中有 6 个覆盖 rescue 题包含这 19 类不可见常量，其中 3 题直接绑定支持。说明 **Coverage 净收益与潜在 Values 语义损失可同时存在**。
- 词面审计完全排除了函数、计算式、模糊 LIKE 等；是否出现在 Query 也不代表 SQL 可恢复正确列/编码；没有标记不代表安全。
- V01 当前只有离线 Schema Node Coverage 成绩；不能声称 SQL Set EX、Bag EX、value literal accuracy、JOIN correctness 或独立 DB 泛化得到提升。

## 4. 到底应不应该继续做 Values 匹配规则？

**不应该继续扩展词面和 AST 规则网格。** 这两轮规定的一次 Full 已结束，也没有新的“完整语义必要性”证据；继续做更多静态近似判断收益递减，且容易事后调标注以匹配预期结论。

**唯一最高优先级转为 P2d：小规模 Values 语义必要性复核 + 固定 SQL Generator 配对执行 Pilot。** 将 19 题做结构化复核，明确哪些映射/编码说明在给定原问题、Evidence、可见 Schema 下确实不可替代；再选冻结的对照题组，比较“同一查询、同一生成器、不同 Context”是否对谓词列/值和 SQL Set EX 造成可测的实际差异。

这是**新的科学问题**，与 P2c-R H2（覆盖率）不同，不可沿用原成功门代替新预注册。方案详见 [P2d 协议](../../plans/p2d_value_utility_and_sql_pilot_20261019.md)。

## 5. 下一轮的严谨设计边界

1. 预注册两级 Gate：**Gate A：语义复核/生成器/只读 SQL 评测可行性**；**Gate B：固定小样本的成对 SQL 生成 Pilot**。必须先确保 Generator/Selector/DB evaluation 可调用并冻结，不能假定 `gfm-rag` 当前已经含完整 Text2SQL Executor。
2. 样本分层：冻结全部 19 个优先题（9 supported、8 mismatch、2 unknown，不删除 unknown），另从其他可评题按 DB/SQL 谓词类型/Schema 规模等**在观察生成结果之前**锁定同样数量的随机对照（不足则如实报告）。19 + 匹配对照都是便利性样本，**只能诊断机制，不能估计总体 EX**。
3. 主要臂 E0=V00 原节点选择+完整 Context，E1=V01 的新节点选择+短 Context；可加 E2=**固定 E0 节点集合+去掉 Values 的 Context** 来区分“Values 内容消失”与“更多节点进入”。所有臂同一 SQL Generator checkpoint、同一 Query/Evidence、同一 Prompt 模板、同一随机参数、同一个 **generator tokenizer** 的上下文预算；不在独立臂变化 SELECTOR/后处理。
4. 下游 SQL Set EX 主指标、Bag EX 辅助，以及正确常量/谓词绑定、SQL Parse Rate、执行错误、实际 prompt tokens、成本、paired rescue/damage，均报告**所有选定题**和原 19 分层。执行评测使用受控只读 DB 与超时/行数限制；不要以精确 SQL 字符串匹配替代 Execution Accuracy。
5. 允许模型输出不完全确定，需固定重复次数（建议 pilot 每臂每题一次，若要复现另行登记），不得反复采样挑最优 SQL；保留 Prompt 与 SQL 原文仅本地。
6. 如没有能稳定运行的固定生成器、SQLite/BIRD EX harness 或双审阅能力，Gate A 标记 **BLOCKED**，先交付可重复的接口/标注协议，不承诺 SQL EX 已开跑；不可改用未经授权的付费 API。
7. 即使 pilot E1 更好，也不等于 V01 可以生产替换 V00。下一步仍需**完整 1460 问题或另一个独立、未反复查看的数据库级 Holdout**，预先冻结模型/阈值/预算；BIRD dev 只是开发集合。
8. 用户的图创新方向独立并行推进：FK/Join Instance 的完整性/角色标签 Gate、官方 GraphReasoner 在 Schema Graph 上的**G0 基线**。截至最新报告 human JOIN role labels=0，**不要在此时宣称 Query-aware Edge Gate 增益**。

## 6. 产出与后续决定

- P2d 完成后提供：语义复核一致性、19 优先样本的 `necessary/replaceable/unknown` 判断及理由类别（匿名汇总），冻结生成器和 SQL 评测协议，预设 pilot 样本与三臂真实执行结果/失败原因；并将下一步 go/no-go 交由实测结果决定。
- 只有新实测可以支持是否尝试“检索富文本 + 紧凑 Context”的进一步 SQL 效用验证；没有跑就不得填入 EX 数字。
- 不新增 Qwen Embedding 维度、BM25/RRF 权重搜索，不混入 GNN 训练/Values 文本截断等多因素变更。

**决策：先审查值绑定的实际语义效用，再以冻结 Generator、Selector 与 SQL Execution 评价真正 Text2SQL 表现；同时独立准备 FK/GraphReasoner 基线，避免一直停留在纯文本检索研究。**
