# FK mapping 排序候选：前沿文献复核与实验保留理由

**日期：2026-11-06。状态：只读研究复核，不是实验注册或实验报告。** 本次没有运行模型、SQL、GPU 或 API，也没有读取盲审答案。

## 结论

本次复核没有找到一个同时满足“能回答当前 QuadGraph 痛点、不会重复已有路线、无需替代双人盲审”的新实验。因此保留已登记的唯一候选：在两位审阅者的可信接受集合上，测试冻结 G-reasoner 能否把正确的 FK mapping 排在 Dense Cosine 前面。未达到人工标签门之前不运行。

这个 Pilot 是 checkpoint 迁移/证伪诊断，不是新算法主张。即使通过，也只说明冻结 G-reasoner 在当前 BIRD dev 标注子集上有映射级排序信号；不说明端到端 JOIN 发现、SQL EX 或跨库泛化。

## 本地痛点与证据

- P2c-R 的 V01 在固定预算下把 Complete@1024 从 56.64% 提高到 67.60%，但没有 SQL EX 证据。
- P2d.3 的受限修复 A2 为 17/66，低于不修复 A0 的 18/66；后续反事实审计发现少量正确 SQL 被上下文 authorizer 拒绝，但不足以推算取消限制后的系统增益。因此不再追加通用 SQL 修复实验。
- G0-02 合成映射任务中，G-reasoner 为 2/4，Dense 为 4/4；G2 证明关系输入可以改变非对称图上的分数，但所有条件的 top-1 都不变。
- 这组证据共同指出缺口：**分数是否响应关系输入，不等于模型能否把业务接受的映射排在前面。** 需要映射级真标签才能回答。

## 新核对的近邻工作

| 论文 | 论文中直接覆盖的路线 | 对本项目的影响 |
|---|---|---|
| [Rethinking Schema Linking: A Context-Aware Bidirectional Retrieval Approach for Text-to-SQL](https://aclanthology.org/2026.findings-eacl.236/) | 同时研究 table-first→column selection 与 column-first→table selection，并结合问题拆解、关键词和关键短语。 | 不再把一般的双向表列检索或问题拆解作为新方法候选。与我们的 P2c-R 目标并非完全相同，但“换一种检索方向”本身已不是空白。 |
| [REaR: Retrieve, Expand and Refine for Effective Multitable Retrieval](https://aclanthology.org/2026.acl-long.1826/) | 先检索问题相关表，再用预计算列向量扩展结构上可连接的表，最后剪除噪声候选；论文报告其适用于 BIRD 等多表任务。 | 普通的“Dense 召回后沿 joinability 扩表”已被直接覆盖；不新增这类图扩展或候选打包实验。 |
| [ARCS: Towards Precise Text-to-SQL via Structured Disambiguation](https://arxiv.org/abs/2610.09396) | 为问题中的歧义点枚举多个有效解释和 SQL，并通过结构化交互选择解释；论文最终统计表报告 311 个任务实例、101 个独立问题、413 条 SQL，涉及 6 个数据库。正文另有一处写 331 个实例，计数存在内部不一致。 | 支持“多种解释/映射不能被压成唯一 Gold”的评测原则。它处理的是更广的问题歧义，不能直接提供本项目所需的 FK mapping identity，也不能替代当前两位独立审阅者的回复；如要复用，须先核实数据版本与计数。 |
| [From Benchmarks to Production: A Text-to-SQL System for Complex Financial Data](https://aclanthology.org/2026.emnlp-industry.42/) | 面向生产金融库的 opaque IDs，使用领域 lookup、模板检索和 FK-chain traversal。 | 提醒 BIRD 对业务值和领域知识的覆盖有限；这篇工作需要领域知识资源，不能在没有相同外部资源时直接复用成当前 BIRD 实验。 |

结合此前已核对的 JoinGR、Graph-Link、SchemaGraphSQL、MDB-Link、CORE-T、Post-SQLFix、DSR-SQL、BASS、DBCC 与 PASCAL，以下方向不作为新的本地方法主张：一般 join-graph 遍历、学习边分数、Steiner 子图诱导、层级表列检索、相干表扩展、Schema 压缩、双 Schema 生成、静态 SQL 修复或增加测试时搜索预算。

## 保留的实验问题与冻结对照

**核心问题：** 对同一个问题、同一个候选表对和同一个 FK mapping 候选集合，冻结的 G-reasoner 能否把双人共识接受的 mapping 排在 Dense Cosine 之前？

- 候选映射、复合 FK 的有序列对、查询文本和映射文本对各评分方法完全相同。
- 主比较是 reified G-reasoner 对 Dense Cosine；BM25 与不看 Query 的结构排序是次级控制，不在 Full 后挑选最弱对照。
- G-reasoner checkpoint、权重及关系传播均冻结；不训练、不微调、不修改图模型。
- 对每个候选统一使用表对两端作为 binary seeds，避免因 FK 方向不同而让候选拿到不同起点。
- 主指标为可区分样本上的 Accepted@1；辅助报告 Accepted@3、MRR、按问题聚类的不确定性、数据库结果、救回/损坏和标签覆盖。
- 完成双人盲审后，排除 Smoke 问题，Full 至少需要 30 个可裁定问题×表对、20 个可区分映射对和 3 个数据库；少于门槛则只归档标签覆盖，不扩样。
- 预设筛选门保持为 G-reasoner Accepted@1 比 Dense 高至少 5 个百分点、净救回至少 4 个可区分样本，并且至少两个各有 5 个以上可区分样本的数据库都呈正向净救回。即使通过也只升级为独立复现候选。

## 为什么现在不换公开数据集绕开盲审

ARCS 的多解释标注是有用的旁证，但它回答的是“问题有哪些有效语义解释”，不是“给定这个 BIRD 表对，哪一条已声明 FK mapping 符合业务意图”。在未逐项核对公开数据、许可证、mapping identity 对齐与数据库结构前，把 ARCS SQL 直接转成 mapping 标签会重新引入本项目正在避免的 Gold SQL 唯一性假设。故本次不把 ARCS 当作当前盲审的替代品，也不启动第二条 GFM 实验支线。

如果 A/B 回复最终未完成，按既有停止规则结束此 mapping Pilot 设计与结果线；不自动抽新题、不用 LLM 代标、不改用其他数据集悄悄保留同一假设。新的数据集路线需另行形成可改变论文主结论的研究问题与独立注册。

## 当前门状态

2026-11-06 对本地 A/B 回复文件只核对文件元数据；两份仍为 1,121 字节，时间戳仍是盲审材料生成时的 2026-11-05 20:56:11，可信双人标签数为 0。没有读取文件内容或推断答案。当前不运行模型、SQL、GPU、Smoke 或 Full。

## 项目内依据

- [FK mapping 文献与实验门更新](p0_fk_mapping_rank_literature_update_20261106.md)
- [Pilot 设计审计](p0_fk_mapping_rank_pilot_design_audit_20261106.md)
- [Pilot 输入语义审计](p0_fk_mapping_rank_pilot_input_semantics_audit_20261106.md)
- [G0-02 合成 FK mapping 报告](../reports/g0_fk_instance_node_20261024_02/README.md)
- [G2 非对称关系通道报告](../reports/g2_asymmetric_relation_20261024_01/README.md)
- [P2d.3 authorizer 反事实审计](../reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md)
