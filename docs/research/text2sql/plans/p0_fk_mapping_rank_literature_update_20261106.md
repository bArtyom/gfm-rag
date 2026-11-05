# FK 映射排序候选：2026-11-06 文献与实验门更新

**状态：只读文献复核与路线决策；不是新实验预注册。** 未运行模型、SQL、GPU 或 API；不产生方法效果结论。原候选方案保留在 [2026-11-05 版本](p0_fk_mapping_rank_pilot_candidate_20261105.md)。

## 1. 这次要解决的痛点

当前证据指向两个不同问题：

- P2c-R 的 V01 在固定 1,024-token 预算下提高了 Schema 节点完整覆盖，但它没有证明 SQL 执行准确率提高。
- P2d.3 的 A2 受限修复为 17/66 Set EX，低于不修复 A0 的 18/66。后续 6 个初始上下文拒绝都发生在 V00 不完整样本；这些被拒字段可在完整 Schema 中编译，且与 Gold SQL 字段重叠。不过 A0 在这 6 题中已有 2 题答对，因此结果说明硬授权边界会阻断一部分可执行查询，不能单独证明检索遗漏导致了生成失败。

图方法证据也尚未闭合：G0-02 的合成 FK 映射题为 G-reasoner 2/4、Dense 4/4；G2 只证明非对称合成图上的分数会响应关系输入，top-1 没变。下一项若启动，应直接问冻结 G-reasoner 能否在可信人工接受的 FK 映射集合上排对映射，不能再测一般性的图扩展或 SQL 修复。

## 2. 新近邻文献及其影响

### JoinGR（arXiv:2610.01064，2026-10-01）

JoinGR 已把表检索表述为 join graph 上的查询条件遍历：先按语义相似度选 anchor，再沿关系边进行查询条件化的 walk，最后把边证据聚合回表分数。它使用冻结的文本编码器，并训练轻量边评分器和 hop 衰减参数；有 Gold join key 时还提出边级排序损失。论文在 BIRD、Spider、BEAVER 上评估，在 BEAVER 的多跳检索上报告明显收益，在 BIRD/Spider 上与强检索基线竞争。

这直接覆盖“利用关系图扩展表候选”和“学习关系边分数”的宽泛主张，也与原候选的 FK 映射评分相邻。原候选只有一个较窄的区别：使用冻结的官方 G-reasoner checkpoint、不训练边评分头，并在固定表对和固定 FK 映射候选中，用双人接受集合测映射身份排序，而不是测表召回。这个区别足以形成一次迁移诊断，但不足以宣称新的 join-graph retrieval 方法。

### MDB-Link（arXiv:2608.09588，2026-08-10）

MDB-Link 已组合全局列向量检索、数据库定位、表选择、表内列 grounding 和预算感知 Schema 上下文构造。因此，新的“table-first / column-first”流程、按表分配列预算或按 PK/FK 优先的打包实验会与现有方法高度重叠。**本轮不把层级检索作为新方法候选，也不启动相应扫描。**

Graph-Link（ICML 2026）已把 schema linking 写成受语义与结构约束的子图诱导；SchemaGraphSQL（Findings EACL 2026）已用 FK 图与路径搜索挑选连接表列；SchemaScope（SURGeLLM 2026）研究高 hop 查询的错误与分解。一般性的图闭包、路径搜索和子图扩张不构成当前可信的新意来源。

## 3. 更新后的候选实验

盲审通过后，保留一次有界的 **G-reasoner 迁移/证伪 Pilot**：

**问题：** 对两位审阅者独立判断并按冻结规则达成共识的问题×表对，冻结 G-reasoner 是否比相同候选与文本上的 Dense cosine、BM25 和不看 Query 的结构排序更常把可接受 FK 映射排在第一位？

**比较范围：** 候选映射集合完全相同；复合映射按完整有序列对保留；所有方法看到相同的 Query 和映射描述。G-reasoner checkpoint 冻结、不训练、不改权重。结构排序只作不看 Query 的控制。此 Pilot 不测端到端表发现、缺失 FK 推断、SQL EX 或跨库泛化。

**评价：** 主指标 `Accepted@1`，并允许共识接受集合含多个映射；辅助报告 `Accepted@3`、MRR、数据库宏平均、配对救回/损坏及不可裁定覆盖率。不能把参考 SQL 的 JOIN 直接当作唯一业务角色金标。

**启动门：** 两份人工回复必须分别完成；至少 30 个可裁定问题×表对、覆盖至少 3 个数据库；每个映射都能与冻结私有 manifest 一一对应。之后另行冻结运行 commit、配置和结果目录；先 5 题 Smoke，通过后只跑一次 Full。低于样本门时止于标签报告，不追加抽样。

**预设筛选门：** G-reasoner `Accepted@1` 至少比预先列出的最强基线高 5 个百分点，且至少净救回 4 个问题×表对，收益不能只来自一个数据库。即使通过，也只升级为独立数据复现候选；若未通过，停止在当前 BIRD dev 上调图、文本、prompt 或阈值。结果只能称为 BIRD dev 上的小样本迁移证据。

这不是算法新颖性声明。JoinGR 的训练式边评分已是直接近邻；本试验只检查已有预训练 G-reasoner 是否能在一套独立盲审标签上迁移到映射级排序。

## 4. 当前门状态与行动

项目路线图规定：真实 FK mapping 方法实验要等两位真实审阅者提交独立标注。检查本地盲审 A/B 回复文件的元数据时，两份文件均为 2026-11-05 20:56:11 创建时的时间戳和相同初始大小；没有新回复已写入的证据。此次仅检查文件元数据，没有读取或推断盲审答案。

因此现在**不启动 Smoke、Full、GPU 前向或人工标签替代流程**。这项外部人工审阅是当前唯一实验门。已有盲审材料和候选方案保持原样，等待真实回复；收到回复后先按冻结共识规则汇总一致性，再检查上述样本门。

## 5. 来源

- [JoinGR: Learning to Traverse Join Graphs for Table Retrieval, arXiv:2610.01064](https://arxiv.org/abs/2610.01064)
- [MDB-Link: Hierarchical Schema Linking for Multi-Database Text-to-SQL, arXiv:2608.09588](https://arxiv.org/abs/2608.09588)
- [Graph-Link, ICML 2026 / PMLR](https://proceedings.mlr.press/v306/zhong26s.html)
- [SchemaGraphSQL, Findings of EACL 2026](https://aclanthology.org/2026.findings-eacl.134/)
- [SchemaScope, SURGeLLM 2026](https://aclanthology.org/2026.surgellm-1.17/)
- [DSR-SQL, EMNLP 2026](https://aclanthology.org/2026.emnlp-main.1688/) — dual-schema generation already addresses pruned/full-schema complementarity.
- [Post-SQLFix, arXiv:2610.41472](https://arxiv.org/abs/2610.41472) — property-guided SQL repair with schema-aware diagnostics and bounded acceptance.
- 本仓库：[P2d.3 最终报告](../reports/p2d3_context_bounded_repair_20261105_01/README.md)、[G0-02 报告](../reports/g0_fk_instance_node_20261024_02/README.md)、[G2 报告](../reports/g2_asymmetric_relation_20261024_01/README.md)、[盲审准备报告](../reports/p0_fk_disagreement_blind_review_20261105_01/README.md)。

## 6. P2d.3 反事实审计后的路线更新（2026-11-06）

最新只读审计对冻结的 8 个被拒修复候选做了完整 Schema 回放：6 个可执行，其中 2 个 Set/Bag 正确；另 2 个完整 Schema 编译失败。6 个初始上下文拒绝 SQL 全部可执行，其中 2 个正确。该结果支持“上下文 authorizer 在少数已封存候选上拒绝过正确 SQL”，不改变 A2 的原始 17/66 Set EX，也不估算移除 allowlist 后的新系统分数。完整数字、执行限制及局限见[独立审计报告](../reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md)。

这个结果没有推翻本计划的优先级：它说明生成候选与检索边界有局部冲突，但不能证明修复该冲突会提升端到端正确率；继续做一般 SQL 修复、双 Schema 生成或 Schema packing 又分别与 Post-SQLFix、DSR-SQL 及已有压缩/检索工作重叠。故不追加 SQL Repair 实验。

下一项仍是本计划第 3 节的冻结 G-reasoner 映射排序证伪 Pilot，唯一未满足的启动条件是两位真实审阅者独立完成现有 A/B 表单并达到冻结的一致性及样本门。2026-11-06 仅检查了表单元数据：两份仍为材料生成时的 1,121 字节文件，可信标签数仍为 0；没有读取或生成任何标签。条件未满足前，不运行模型、GPU 或替代标注。

### 三个研究镜头下的候选池

| 镜头 | 候选假设 | 决定 |
|---|---|---|
| 边界探测 | 在同一表对有多个有效 FK 映射时，查询条件能否让预训练 G-reasoner 把人类接受集合排在前面？ | 保留为唯一 Pilot；需要真实双审标签。 |
| 边界探测 | 在缺失或不完整 FK 的 schema 上加入来源可追溯的推断边，能否恢复连接候选？ | 暂缓：SchemaGraphSQL 已覆盖 joinability discovery，本地也没有推断边金标。 |
| 结构类比 | 把 FK 映射视为带完整端点契约的符号对象，能否用稳定身份消除重复/复合映射混淆？ | 已做 identity 审计；未显示该身份定义本身带来任务收益，不重复包装成新方法。 |
| 结构类比 | 用图遍历替代独立表排序，能否恢复未被文本命中的桥表？ | 不保留为新点：JoinGR 与 Graph-Link 已直接覆盖相关机制，且本地高跳数审计已停止扩展。 |
| 矛盾反转 | 关系通道分数会随输入变化，是否就意味着关系选择正确？ | 保留为首选 Pilot 的核心对照：G2 的 score sensitivity 与 G0 的 2/4 排序结果相冲突，需以可审阅映射 Accepted@1 判别。 |
| 评测边界 | 双 Schema 或静态修复能否救回被检索边界挡住的 SQL？ | 不追加：DSR-SQL、Post-SQLFix 及本地 P2d.3 已覆盖相邻路线，且本地系统级提升未成立。 |

上述候选没有一个可据此称为“新颖算法”。保留项是一次受限的 checkpoint 迁移/证伪实验；新颖性仍为 `unknown / likely limited`。如果双审标签无法取得，本方向停在标签准备结果，不以合成题或模型伪标签替代。
