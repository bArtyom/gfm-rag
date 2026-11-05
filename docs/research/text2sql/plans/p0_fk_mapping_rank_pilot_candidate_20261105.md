# 双人裁定后的 FK 映射排序 Pilot 候选方案

**状态：候选方案，未预注册，未运行。** 这是当前盲审之后最值得评估的实验；只有两位真实审阅者完成独立标注并通过下述数据门后，才可冻结独立 run ID、配置和执行代码。本文不代表已有方法增益。

## 1. 痛点与证据

当前研究有三条彼此相关、但不能互相替代的证据：

1. **关系输入会改变 G-reasoner 分数，但尚未证明会选对关系。** G2 在非对称合成图上通过关系敏感性门；关系类型和关系向量干预使分数变化，但所有干预的 top-1 都不变。G0-02 在四个合成映射问题上是 GFM 2/4、Dense cosine 4/4，按预注册门槛为 NO-GO。
2. **BIRD FK 候选集没有统一定义。** canonical P1.5 为 970 个 FK-match / 197 个 multi-FK-candidate 题，packet-28 为 1,043 / 176。逐题对账得到 88 个 packet-only FK-match、15 个 canonical-only FK-match、21 个 canonical-only multi-FK-candidate；这些都是候选生成结果，不是业务 Role 标签。
3. **JOIN 结构覆盖不完整。** 已有 P2a.5 审计的 1,428 个 Gold `JOIN ON` 中，204 个未匹配声明 FK：99 个 `non_fk_relation_unverified`、90 个 `metadata_incomplete`、7 个 `unresolved_alias`、4 个无跨表 equality、4 个与声明 FK 列对不匹配。原因分类只描述结构，不证明 JOIN 语义正确。BIRD 11 个 dev schema 中有103个原始 FK、100个端点有效、99个唯一有效映射；本轮结构审计没有观察到复合 FK。

刚完成的盲审包含 49 道题、51 个“问题×表对”，覆盖 6 个数据库。表对来自参考 JOIN，所以后续 Pilot 只能回答：**给定表对和已声明候选映射时，模型能否排对映射**。它不能回答端到端表发现、缺失 FK 推断或跨库泛化。

## 2. 候选假设筛选

| 来源镜头 | 候选假设 | 判定 |
|---|---|---|
| 边界探测 | 在声明 FK 不完整的 schema 上，增加带来源与置信度的推断边并允许 abstain，可减少 JOIN 候选缺失 | 暂缓：本地 204 个 unmatched 已分为结构原因；`SchemaGraphSQL` 已包含缺失/不一致 FK 的 joinability discovery，且当前没有人类标注的推断边真值。 |
| 边界探测 | 在同一表对存在多个 FK 映射时，给定真实问题，query-conditioned GFM 能否从映射节点中找出人工接受的映射？ | **保留为首选 Pilot**：这是当前 GFM 关系/映射方法在真实问题上的首个可证伪检查；需等待本轮双人标签。 |
| 结构类比 | 将每条 FK 当作带来源证明的编译器符号，先检查端点/列对契约，再生成合法 JOIN 子图 | 暂缓：稳定 mapping ID、复合映射和重复声明语义已有 G0/身份策略工作；没有证据说明再包装成 typed IR 会改变结论。 |
| 矛盾反转 | “关系分数敏感”不等于“关系排序正确”；以人类接受集检验分数变化是否对应正确 top-1 | **并入首选 Pilot**：直接区分 G2 的机制证据与 G0 的排序失败，不重复合成敏感性扫描。 |
| 评测边界 | 转向 Spider 2.0 的超大 schema 与多 dialect 场景评估 | 暂缓：Spider 2.0 数据不在当前本地资源索引中；FK/Role 真值与环境成本需单独调查，而且会改变当前单一核心问题。 |

## 3. 首选 Pilot 的研究问题

**研究问题：** 对双人独立审阅并达成高置信共识的 BIRD dev 问题，在固定表对、完全相同的有效 FK 候选集和相同映射文本下，冻结的 query-conditioned G-reasoner 是否能比 Dense cosine、BM25 和不看问题的结构排序更常把可接受映射排在第一位？

**可证伪预测：** GFM 的 `Accepted@1` 至少比最强固定基线高 5 个百分点，且全样本净救回不少于 4 个问题×表对；增益不能只来自单一数据库。若没有达到，停止在 BIRD dev 上继续调关系文本、prompt、阈值或图拓扑。

这是一项 exploratory transfer pilot，而非确认性主结果。BIRD dev 已用于多轮开发；结果不能作独立测试或跨数据库泛化主张。

## 4. 依赖标签门与标注规则

从现有 A/B 回复表开始，不增加题目、不改题目/表对、不看模型分数后挑样本。两位审阅者必须先分别提交；沿用既定一致规则：决定标签与映射集合完全一致，且两人置信度均至少为 2。

只有同时满足以下条件才进入模型 Smoke：

- 至少 30 个可裁定的问题×表对，来自至少 3 个数据库；
- 所有进入排序分母的候选映射身份能与私有 manifest 一一对应；
- `single_mapping` 与 `multiple_mappings` 作为接受映射集合；`cannot_determine` / `other` 保留为不可裁定统计；`no_declared_fk` 单独报告覆盖/abstention，不伪造候选标签；
- 逐题分层和两位审阅者的私有回复不进入模型输入、公开仓库或日志。

若可裁定样本不足，实验止于人工标签报告；不追加抽样来追逐结果。

## 5. 比较方法与指标

候选集在所有方法之间完全相同，使用完整的有序 child/parent 列映射；不把表级分数、部分复合键命中或单列相似度当作映射命中。

| 方法 | 定义 | 作用 |
|---|---|---|
| Dense cosine | 同一冻结 Qwen3 Embedding 对 Query 与映射文本做 cosine | G0-02 上的强简单基线；不训练 |
| BM25 | Query 与同一映射文本的词面排序 | 名称/字段 token 基线；稳定 tie-break 预先固定 |
| 结构排序 | 忽略 Query 的一跳映射/稳定 ID 顺序 | 检查 query-conditioned 信息是否必要；不同映射同端点时预期会打平 |
| Reified GFM | 沿用 G0 的 FK mapping node、固定官方 G-reasoner-34M checkpoint 与 Qwen Query/映射嵌入；节点分数排序 | 唯一被检验方法；不训练、不改权重 |

**主指标：** `Accepted@1`，预测 top-1 属于审阅共识接受集合即计正确。`multiple_mappings` 按接受集合评分，不强迫单一 Gold。主对比为 GFM 与三种冻结基线各自的配对救回/损坏数；`GFM − strongest baseline` 的差作为筛选门，明确报告 strongest baseline 的选择发生在同一评测集这一限制。

**辅助指标：** MRR、Accepted@3、按数据库宏平均、可裁定覆盖率、abstention/`no_declared_fk` 处理率、置信度分层，以及错误案例类型。数据库级 bootstrap 仅作探索性不确定性描述；不将小样本 p 值包装成确认性结论。

## 6. 最强近邻与新颖性审查

- [SchemaGraphSQL（Findings of EACL 2026）](https://aclanthology.org/2026.findings-eacl.134/) 已先用外部提示抽取 source/destination tables，再用 FK schema graph 与传统 pathfinding 选择 JOIN 表/列；其方案还包含 FK 缺失/不一致时的 LLM-guided joinability discovery。故“FK 图 + 找 JOIN 路径”不能作为新意。本 Pilot 的狭窄差别是固定表对/候选集内，用预训练 GFM 的 query-conditioned 节点分数排序，并以双人接受集合评价；这仍不足以证明方法新颖。
- [Graph-Link（ICML 2026）](https://proceedings.mlr.press/v306/zhong26s.html) 已把 schema linking 建模为同时满足语义相关性与图结构约束的子图诱导；[SchemaScope（SURGeLLM 2026）](https://aclanthology.org/2026.surgellm-1.17/) 又报告高跳数下 wrong-join-path 是主要错误。通用 schema graph/路径约束不是本方向的创新点；当前候选仅检验“固定已知表对下，G-reasoner 的实例节点分数能否区分可接受 FK 映射”。
- [AmbiQT（EMNLP 2023）](https://aclanthology.org/2023.emnlp-main.436/) 展示单个自然语言问题可能对应多个有效 SQL，包含结构关系路径歧义。它支持本 Pilot 保留 set-valued 标签的必要性；多标签评价本身不是新颖贡献。
- [G-reasoner / GFM-RAG](https://arxiv.org/abs/2509.24276) 提供跨图预训练的关系/文本联合图推理器，但其论文结果不等于 Text2SQL FK mapping accuracy。把 checkpoint 用在此处是迁移性试验，不自动形成新算法。
- 本地 Text-to-SQL 知识库还包含 EXP-129/130/131/132/136/137/138/139/140/142 的 role-map oracle、词面/类型对齐、Qwen role-map 生成、确定性图修补、采样 lattice 与 dynamic SQL gate；这些工作与本 Pilot 问题相邻，但没有直接用 G-reasoner 排序固定 FK mapping nodes。它们已暴露 role alignment 与 graph repair 的负迁移风险，因此本候选应定位为一次有界迁移诊断，而非新方法。
- 本地 `DEDUPLICATED_IDEA_INDEX.md` 将 D01–D27、N01–N07 归为废案；已有 G0/G1/G2 结果也说明合成关系分数敏感性和 FK identity 已被探索。当前真实标签是新的测量资源，但本候选的**方法新颖性仍为 unknown / likely limited**，需在确认性设计前再做代码级近邻审计。

## 7. 资源、代码与止损

- 数据、FK schema、crosswalk 和映射定义沿用当前盲审登记的哈希；模型输入遵循 G0-02 的 1024 维设置。下一次运行前重新检查 checkpoint、tokenizer、环境和每份人工表单哈希。
- 环境优先复用 `gfmrag_greasoner_20261022` 与 `think2sql_20260909`；本地模型之外不调用付费 API。预计 CPU 生成 49 个 Query 和映射向量，GPU 一次加载 34M G-reasoner、最多 60 次正式/控制前向；真实额度必须在 preflight 后重新核定，不能沿用旧空闲显存。
- 先用 5 个已共识样本做 smoke；通过后只运行一次 Full。独立 run ID、配置、日志、GPU/CPU/RSS/磁盘快照和输入/输出哈希均须先写入 GitHub 分支，再启动。
- Full 通过数据门后若 GFM 未超过冻结的 5pp / 4 个净救回门，判定 `NO_GO` 并停止该 BIRD dev 方向；若通过，也只升级为独立数据库级复现的候选，不直接宣布 Role 方法有效。
- 任何启动都必须先收到两份人工回复；当前状态是**等待标注，不创建结果目录、不加载模型**。

## 8. 指导来源

- 当前项目指导与盲审报告：[`docs/research/text2sql/README.md`](../README.md)、[`experiment-roadmap.md`](../experiment-roadmap.md)、[`reproducibility-contract.md`](../reproducibility-contract.md)、[`P0 FK 双人盲审报告`](../reports/p0_fk_disagreement_blind_review_20261105_01/README.md)。
- 本地证据：[`P0 canonical crosswalk`](../reports/p0_fk_canonical_crosswalk_20261105_01/README.md)、[`G0-02`](../reports/g0_fk_instance_node_20261024_02/README.md)、[`G2`](../reports/g2_asymmetric_relation_20261024_01/README.md)、[`方法变更台账`](../method-change-ledger-20261105.md)。
- 该候选设计目前没有引用人类回复、逐题标签、Gold SQL、题目文本或数据库 ID；这些数据一律只留在本地受限路径。
