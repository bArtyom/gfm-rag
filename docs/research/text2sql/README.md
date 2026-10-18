# Text2SQL × QuadGraph / G-reasoner：研究工作台

> **唯一主仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)。生效日期：2026-10-16。**
>
> 此目录管理该研究线的**想法、论文核对、实验方案、实现决策、结果分析及下一轮指导**。之前的 [`bArtyom/quadrag`](https://github.com/bArtyom/quadrag) 仅作历史来源，不再向其提交新的研究方案或结果。保留旧仓库历史，不强制删除。
>
> **最新状态（2026-10-18）**：P1.6 修复后 Smoke 与 1,534 题 Full 已完成，Full Gate PASS。随后 P2a 修复版 smoke 和 1,534 题 Cosine/BM25/RRF Full 已完成，完整性与 S0 parity 均通过；预注册成功门未通过，结论为 NO-GO 并停止本轮方法扩展。详见 [P2a 全量报告](reports/p2a_similarity_20261018_01/README.md)。BM25 在 706 题非饱和子集上 Column R@10 为 −10.50 pp；RRF 为 +0.09 pp，但 Complete@2048 为 −5.38 pp。首次全量汇总错误和修复版运行均保留记录。历史 P1/P1.5 复现 FAIL 与 FK/Role Gate FAIL 不变；不启动 Role/Path、GNN、P3 或 P4。

## 现有研究文档

| 文档 | 作用 | 状态 |
|---|---|---|
| [论文与代码审计](paper-and-code-audit.md) | QuadGraph 四层图、Qwen3 Embedding 输出维度、GraphReasoner 投影约束、相似度归一化 | 讨论版，待按当前 fork commit 复核 |
| [实验路线图](experiment-roadmap.md) | P0 数据审计 → P1 维度消融 → P2 评分消融 → P3 Text2SQL EX → P4 可选 GFM 适配 | 研究指导 v1，尚未按本路线图执行 |
| [数据与复现规范](reproducibility-contract.md) | Gold 约束、FK 实例标识、反泄漏、缓存版本、评测模板与 Go/No-go | 待实现/执行 |
| [历史 P1 官方编码器报告](reports/gfmrag_p1_official_20261014/report.md) | BIRD dev 表/列维度筛查结果、配置、代码快照及聚合指标 | 2026-10-14 已运行；exploratory；不满足当前 P0/P1 完整验收范围 |
| [P1 结果复核与决策（最新）](reports/p1_review_20261016/README.md) | 核对 512/1024 配对损益、显著性、预算饱和及实验局限 | 2026-10-16 完成**归档再分析**，不是新实验 |
| [P1.5 诊断报告](reports/p1_5_diagnosis_20261016/README.md) | 列检索、Top-K/预算饱和、复现核对及 FK 实例质量 | 2026-10-16 已运行；严格逐题复现 Gate 未通过；exploratory |
| [P1.5 最新复核与决策](reports/p1_5_review_20261016/README.md) | 汇总预算/列 rank、历史 91 项差异、FK/Role Gate、继续实验的逻辑 | 2026-10-16 静态分析；非新实验 |
| [P1.6 → P2a 新执行协议（当前有效）](plans/p1_6_rebaseline_then_p2a_20261016.md) | 冻结新基线、同数据 Cosine/BM25/RRF 与 Go/No-go | P1.6 已完成；P2a 为下一步 |
| [P1.6 最新 Smoke/代码审计](reports/p1_6_smoke_review_20261017/README.md) | 两次 Smoke 失败、manifest 校验问题与源代码检查 | 2026-10-17 静态审计；后续修复和测试见 P1.6 阶段报告 |
| [P1.6 Smoke 恢复 → P2a 当前执行方案](plans/p1_6_smoke_recovery_then_p2a_20261017.md) | CPU manifest 回归、Smoke/Full Gate、后续 Cosine/BM25/RRF | Smoke 与 Full 已按此计划完成；见 2026-10-18 报告 |
| [P1.6 冻结基线重建报告](reports/p1_6_rebaseline_20261018_01/README.md) | 修复后 Smoke 与 1,534 题 Full；新 1024-D Dense 基线及 Gate | 2026-10-18 完成；Full Gate PASS，encoder 跨前向浮点差异已披露 |
| [P2a Cosine/BM25/RRF 全量对照](reports/p2a_similarity_20261018_01/README.md) | 固定缓存、候选全集和预算的评分方法对照及数据库级不确定性 | 2026-10-18 完成；S0 parity / integrity PASS，预注册收益门未通过，停止方法扩展 |
| [P2a 相似度对照预注册](plans/p2a_similarity_20261018.md) | 1024-D Cosine / BM25 / RRF 的冻结分词、候选集、指标、门槛与资源 | 修复版 Smoke 与 Full 已完成；预注册方法成功门未通过，见 P2a 全量报告 |
| [P1.5 → P2a 执行指导](plans/p1_5_diagnostics_and_p2a_20261016.md) | 离线诊断、FK Gate、条件式 BM25/RRF 检索实验及 Go/No-go | P1.5 与 P2a 已运行；结果及停止决定见各自报告；原指导保留 |
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

## 最新行动结果与下一步（2026-10-18）

P1.6 [报告](reports/p1_6_rebaseline_20261018_01/README.md)记录冻结 1024-D Dense 基线。之后 P2a [报告](reports/p2a_similarity_20261018_01/README.md)记录 1,534 题 S0/S1/S2 全量比较及非饱和子集分析。S0 与 P1.6 排名 parity 通过；BM25 显著低于 S0，RRF 的 Column R@10 仅小幅提高且 Complete@2048 下降，均未通过预注册成功门。P2a 最终决策为 NO-GO，停止扩展评分方法。

**当前行动：** 先基于已归档匿名汇总做错误模式分析和研究叙事整理，不自动安排新的 GPU 运行。只有出现会改变核心结论的明确未决问题，并为独立数据库数据预先冻结预算与判据后，才重新规划验证实验。FK/Role Gate 仍不通过，不启动 JOIN Edge/Role/Path、GNN、SQL EX、Jev 或 P4。BIRD dev 仍仅是开发诊断集，不具备独立泛化证据。


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
