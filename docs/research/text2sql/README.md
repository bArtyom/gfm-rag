# Text2SQL × QuadGraph / G-reasoner：研究工作台

> **唯一主仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)。生效日期：2026-10-16。**
>
> 此目录管理该研究线的**想法、论文核对、实验方案、实现决策、结果分析及下一轮指导**。之前的 [`bArtyom/quadrag`](https://github.com/bArtyom/quadrag) 仅作历史来源，不再向其提交新的研究方案或结果。保留旧仓库历史，不强制删除。
>
> **最新决策（2026-10-16）**：已核对历史 P1 官方编码器表/列维度筛查（1,534 题、11 库），**没有低维满足全部已注册质量门，P1 严格 NO-GO**。下一轮唯一实际执行任务是 **P1.5 错误归因、Top-K/预算饱和审计及 P0-FK 修复性诊断**；随后有条件开展 P2a 的 Cosine/BM25/RRF 同信息比较。当前没有任何新 GNN、SQL 或 P2a 实验成绩。

## 现有研究文档

| 文档 | 作用 | 状态 |
|---|---|---|
| [论文与代码审计](paper-and-code-audit.md) | QuadGraph 四层图、Qwen3 Embedding 输出维度、GraphReasoner 投影约束、相似度归一化 | 讨论版，待按当前 fork commit 复核 |
| [实验路线图](experiment-roadmap.md) | P0 数据审计 → P1 维度消融 → P2 评分消融 → P3 Text2SQL EX → P4 可选 GFM 适配 | 研究指导 v1，尚未按本路线图执行 |
| [数据与复现规范](reproducibility-contract.md) | Gold 约束、FK 实例标识、反泄漏、缓存版本、评测模板与 Go/No-go | 待实现/执行 |
| [历史 P1 官方编码器报告](reports/gfmrag_p1_official_20261014/report.md) | BIRD dev 表/列维度筛查结果、配置、代码快照及聚合指标 | 2026-10-14 已运行；exploratory；不满足当前 P0/P1 完整验收范围 |
| [P1 结果复核与决策（最新）](reports/p1_review_20261016/README.md) | 核对 512/1024 配对损益、显著性、预算饱和及实验局限 | 2026-10-16 完成**归档再分析**，不是新实验 |
| [P1.5 → P2a 下一步执行指导（最新）](plans/p1_5_diagnostics_and_p2a_20261016.md) | 离线诊断、FK Gate、条件式 BM25/RRF 检索实验及 Go/No-go | **当前行动指导；P1.5/P2a 均未运行** |
| [G-reasoner 图算法源码精读（新）](graph-algorithm-code-review-20261016.md) | 分析 NER/Top-1 锚点、关系类型与逐边属性、NBFNet 消息传播、SQL 子图结构约束、创新性排序 | 2026-10-16 静态审查与研究建议；未跑新实验 |

论文与代码审计、实验路线图、复现规范从旧仓库**迁移**，部分路径/迁移日期调整；迁移本身不产生新实验结论。上表的 P1 报告记录了 2026-10-14 实际运行，但其范围仅为表/列筛查，FK/角色未测；不得视作当前路线图下 P0 通过或完整 P1 完成。

## 当前研究命题

**固定 Schema Graph 下研究 Query/Node/Join-Instance Embedding 维度与检索评分方式如何影响表列召回、关系角色、合法 JOIN 路径及最终 Set EX。**

1. 同一 Qwen3-Embedding-0.6B 比较 **128、256、512、768、1024** 维；固定输入模板、数据库/Graph、L2+Cosine、候选预算。
2. 在固定维度及同候选宇宙对比 Cosine、BM25、RRF、Relation-description Cosine、Role-aware Path Score。
3. 关注**同表不同 FK 角色、复合 FK、桥表**；不能仅用 Table Recall 替代 JOIN 正确性。
4. 最终用固定 SQL generator / selector 评价 **Set EX（主）/ Bag EX（辅）**，独立报告 token、延迟与实际费用。
5. 发布的 1024 维 G-reasoner checkpoint **不能直接输入 512 维向量**；如需 GFM 侧对照，另建适配器实验并记录训练变量。
6. 本研究中涉及 Jev 时，需要和向量检索模块分开对照归因，不将单纯候选数或下游 SQL 更换归因于 Jev。

## GFM 源码拓展方向（研究储备，不改变当前 Gate）

在 [2026-10-16 的代码级分析](graph-algorithm-code-review-20261016.md) 中，重点确定了 **Top-1 起始锚点、关系实例/逐边属性未纳入默认消息权重、节点 Top-K 非连通、SQL-aware 监督未落地**等可验证机制。最有潜力的后续方向是 **Query-aware JOIN Edge Gate + 实例感知约束子图解码**；但必须先过 FK/Join 标签 Gate，并与 Graph-Link、GRAST-SL、SchemaGraphSQL 同信息比较。**这不是已有实证收益**。

## 当前唯一行动：P1.5 复核诊断（P2a 需通过 Gate）

1. 先完成 [P1.5 错误/预算审计](plans/p1_5_diagnostics_and_p2a_20261016.md)：解释 74 道列标签不可评题、统计每库 Top-K 是否天然饱和、分析 1024 维 gold 列排名/512 配对损益、给出 512/1024/2048 token 预算的 oracle-fit 与完整覆盖。
2. 并行只做 **P0-FK 质量门修复性诊断**；没通过之前**不做 Join Role / Path 准确率**，不宣称完成 QuadGraph Text2SQL。
3. 若数据、排序/缓存和错误来源可信，再冻结条件式 P2a：**1024 维 Cosine vs BM25 vs RRF**，512 仅为资源对照；不提前训练 GNN 或改变 Jev、SQL Generator/Selector。

**当前历史 P1 NO-GO 不改写**；BIRD dev 仅作探索，不可将多轮开发收益写成独立泛化结果。P0/FK 修复、P1.5、P2a 的状态必须分别列示，不把“历史已做的表列筛查”误算为完整新研究 P1 通过。

## 从今往后的提交规范

- **文档：**研究思路/文献核对进入 `docs/research/text2sql/`；每轮计划以明确版本文件记录，前一版保留以供追溯。
- **实现：**沿用本仓库的 `gfmrag/`、`scripts/`、`tests/` 项目约定；先检视现有模块再新增代码，不擅自覆盖上游实现。
- **结果：**新建 `docs/research/text2sql/reports/<experiment-id>/` 保存匿名聚合指标、失败模式、数据/代码 hash、变更前后对照、明确的下一轮 Go/No-go。
- **变更区分：**研究设想、实验计划、已运行证据、未执行行动必须显式区分。统计说明数据集、分母、数据库级拆分、Set/Bag、计算预算以及不确定性。
- **GitHub 权威性：**以后本研究的最新判断以**该仓库真实已提交的版本**为准。分析新结果之前先读取本仓库最新报告与提交；不能拿历史会话里的数字冒充新报告。
- **安全：**不上传数据库内容、原题/Gold SQL、逐题预测、API 密钥、日志或无法公开的数据；公开代码和协议、必要的匿名统计与 hash。
- **代码合并：**原则上研究文档可直接独立提交；涉及主干模型/评测代码的改动，应优先独立分支及 PR，并明确测试与回退方式。

## 历史来源与技术依据

- 历史研究仓库（仅供追溯）：[bArtyom/quadrag](https://github.com/bArtyom/quadrag)。
- 本代码库上游：[RManLuo/gfm-rag](https://github.com/RManLuo/gfm-rag)。
- G-reasoner 论文：[arXiv:2509.24276](https://arxiv.org/abs/2509.24276)。

**下一次接到“看最新报告、分析下一轮、保存到 GitHub”时：先看本仓库，再给出可归因分析，并提交新版本指导。**
