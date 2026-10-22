# Text2SQL × QuadGraph / G-reasoner：研究工作台

> **唯一主仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)。生效日期：2026-10-16。**
>
> 此目录管理该研究线的**想法、论文核对、实验方案、实现决策、结果分析及下一轮指导**。之前的 [`bArtyom/quadrag`](https://github.com/bArtyom/quadrag) 仅作历史来源，不再向其提交新的研究方案或结果。保留旧仓库历史，不强制删除。
>
> **最新决策（2026-10-22，P2d 7B SQL Pilot结果复核）**：P2d已实测30题×3臂，确认 Set/Bag 正确为 E0/E1/E2 **8/7/8**，未知 **11/12/10**；目前 **V01 无被证实的 SQL EX 增益，不默认替换 V00**。E1 总生成器输入 tokens 反比 E0 多 1.47%，E2 固定原节点后减短 Values 节约 30.27%；四条参考 SQL 被保守时间函数策略拒绝、其余多条预测本身不可执行。**唯一优先下一轮：[P2d.1 冻结预测/评测可判定性与失败归因](plans/p2d_1_frozen_prediction_eval_audit_20261022.md)**；先测试安全评测器 v2，不重新请求模型或覆盖原8/7/8；另行人工Values语义复核。原 P2c-R 节点覆盖 PASS 保持，FK/Role Gate NO-GO、G0尚未运行。

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
| [P1.6 → P2a 旧执行协议（历史）](plans/p1_6_rebaseline_then_p2a_20261016.md) | 冻结新基线、同数据 Cosine/BM25/RRF 与 Go/No-go | P1.6 已完成；P2a 为下一步 |
| [P1.6 全量冻结基线（已通过）](reports/p1_6_rebaseline_20261018_01/README.md) | 1024-D cache/scorer replay，smoke 编码不稳定性记录 | 2026-10-18 PASS，新基线 |
| [P2a Cosine/BM25/RRF 全量实验](reports/p2a_similarity_20261018_01/README.md) | 全体/非饱和 DB 的三种方法对比，NO-GO | 2026-10-18 已运行 |
| [P2a 最新结果复核（当前）](reports/p2a_review_20261018/README.md) | 失败机制、RRF rescue/damage、排序/预算冲突和未来研究边界 | 2026-10-18 只读复核 |
| [P2a.5 错误归因与 FK Gate 报告](reports/p2a_5_error_audit_20261018_01/README.md) | 冻结排名错误归因、预算 / 字段特征、FK / JOIN 覆盖与下一步决策 | 2026-10-18 完成；原 P2a NO-GO 与 Role Gate NO-GO 均保留 |
| [P2a.5 执行计划与后续消融指导](plans/p2a_5_diagnostic_and_schema_representation_20261018.md) | P2a.5 已执行范围、复现约束、条件式 P2b / packing 选择 | P2a.5 A/C 已完成；R0/R1 已按专项计划另行预注册 |
| [P2b R0/R1 Values 文本消融预注册](plans/p2b_values_ablation_20261018.md) | 固定 1024-D Cosine 下只移除列 Values 文本，含 CPU 编码控制、成功门与停止条件 | Full 完成；预注册成功门 NO-GO，停止 Values 扩展 |
| [P2b R0/R1 Values 消融记录](reports/p2b_values_ablation_20261018_01/README.md) | 预注册、运行状态、匿名结果及下一步决策 | 2026-10-18 完成，匿名聚合已归档 |
| [P2c 双视图 2×2 实验报告](reports/p2c_dual_view_20261018_01/README.md) | 预注册、smoke 与两次 Full 执行故障、停止决定 | 执行器恢复额度耗尽；未产生 Full 科学结果 |
| [P2c 最新执行分析（2026-10-18）](reports/p2c_execution_review_20261018/README.md) | Full 两次聚合失败、逐字段源码映射审计、科学结论边界 | **最新复核；无新实验成绩** |
| [P2c-R 聚合契约恢复协议](plans/p2c_r_replay_contract_recovery_20261018.md) | 48 项源归档字段映射测试、全流程合成/归档回归、新恢复试验 Gate | Gate 0 与一次正式恢复已完成 |
| [P2c-R Gate 0 工程记录](reports/p2c_r_contract_gate_20261019_01/README.md) | 完整字段适配、缺失/非有限值与分母验证、占位臂聚合写盘 | 93 项测试、真实归档 48 指标/4 分母和 JSON 写盘 Gate PASS |
| [P2c-R 独立恢复全量结果](reports/p2c_r_recovery_20261019_01/README.md) | Gate 0 后同四臂、同阈值恢复及独立产物复核 | H1/H2 PASS；V01为Values风险审计候选，无SQL EX结论 |
| [Values 词面信息风险审计](reports/p2c_values_risk_20261019_01/README.md) | 冻结1024预算下的参考谓词常量可见性，CPU一次有界扫描 | 完成；407/1460题有线索，19题优先复核；非语义安全门 |
| [Values 直接列值绑定核验](reports/p2c_value_binding_20261019_01/README.md) | 冻结19题/21个输入不可见常量的AST源列绑定 | 完成；9题绑定支持/8题不一致/2题未知，仍无语义必要性结论 |
| [P2c-R + Values 最新实验复核（当前）](reports/p2c_r_latest_review_20261019/README.md) | 四臂 PASS、407题风险线索、19题绑定结果和局限 | 2026-10-19 分析，非新实验 |
| [P2d 语义必要性与 SQL EX 配对 Pilot（上位指导）](plans/p2d_value_utility_and_sql_pilot_20261019.md) | 原19题和匹配对照，固定 Generator/Selector/SQL evaluator，E0/E1/E2 与 Go/No-go | 工程/SQL Pilot已按2026-10-22独立登记完成；人工审核未完成 |
| [P2d 2026-10-22 SQL实验报告](reports/p2d_sql_utility_20261022_01/README.md) | 固定本地7B、19优先+11严格对照、三臂一次生成与只读SQLite评测 | Gate A/Smoke/30题Full完成；8/7/8确认正确，语义标签unverified |
| [P2d 最新SQL Pilot复核（当前）](reports/p2d_latest_review_20261022/README.md) | 30题三臂可判/不可判、Token机制、时间函数策略与研究主线 | **2026-10-22分析；非新实验** |
| [P2d.1 评测覆盖和失败归因（当前下一轮）](plans/p2d_1_frozen_prediction_eval_audit_20261022.md) | 封存SQL复核、safe temporal evaluator v2测试、19题语义审核与Go/No-go | **下一轮已登记，尚未执行** |
| [P1.6 最新 Smoke/代码审计](reports/p1_6_smoke_review_20261017/README.md) | 两次 Smoke 失败、manifest 校验问题与源代码检查 | 2026-10-17 静态审计；后续修复和测试见 P1.6 阶段报告 |
| [P1.6 Smoke 恢复 → P2a 历史执行方案](plans/p1_6_smoke_recovery_then_p2a_20261017.md) | CPU manifest 回归、Smoke/Full Gate、后续 Cosine/BM25/RRF | Smoke 与 Full 已按此计划完成；见 2026-10-18 报告 |
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

## 最新行动结果与下一步（2026-10-22，P2d结果复核）

[P2d真实SQL Pilot](reports/p2d_sql_utility_20261022_01/README.md)是固定Qwen2.5-Coder-7B-Instruct在BIRD dev 30道有偏诊断题、5DB上的首次生成/执行结果。E0=V00原节点+完整Values，E1=V01新增节点+精简文本，E2=E0原节点+精简文本，**确认正确 Set/Bag = 8/7/8（各30分母）**、未知=11/12/10。E0/E1 共同可判17题，各仅1题独有正确，远远不足以判定Values缺失对总体EX的方向。原19题未做人类语义必要性审查、严格匹配控制仅11题，不得将本次当作独立分布估计或官方BIRD分数。

**新增重要机制：** 全30题模型输入 tokens：E0 **35074**、E1 **35591（+1.47%）**、E2 **24458（−30.27%）**。在固定1024 Schema budget下，双视图召回更多节点实际上使Generator上下文总长度未下降，而固定原节点的短文本大幅节省tokens；E0/E2虽然各有8道正确但并非相同题，不能宣称省略Values语义无损。历史[P2c-R](reports/p2c_r_recovery_20261019_01/README.md)离线Complete@1024 +10.96pp PASS仍成立，但没有被此小样本证明为SQL EX收益。

另有 **4/30参考SQL被保守时间函数“非字面量参数”规则阻止**，其他各7/8/6预测在参考可执行时本身不可执行；需区分评测覆盖缺口与生成器错误，不修改历史P2d数据。本轮新分析见[P2d复核](reports/p2d_latest_review_20261022/README.md)。

**唯一近期新实验：[P2d.1 冻结预测评测器可判定性/失败归因](plans/p2d_1_frozen_prediction_eval_audit_20261022.md)**。先用合成正反例确保“时间函数安全扩展”仍完全禁止真实时钟和写操作，原26道Gold可执行结果完全回放一致后，才对旧封存90条预测在新结果目录中另行CPU-only复算；不能以多执行请求增加样本或静默更改8/7/8。细化7/8/6失败类别、原19条人工Values语义审核状态、Generator真实token开销构成。Gate不通过就只报告失败原因。**此工作尚未执行**。

下一科研方法仅条件式提出：在P2d.1后如有足够可信的生成器错误模式，另立 `P2e` 在相同真实Generator-token预算下测试有选择的Schema Context Packing，避免简单扩大候选；要使用新冻结样本、真实SQL EX而不是事后优化开发集。并行推进真实G-reasoner→Schema graph G0兼容性测试及FK/JoinInstance标签质量，**G0尚未运行，FK/Role Gate NO-GO**。所有旧P1/P2负结论照实保留。


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
