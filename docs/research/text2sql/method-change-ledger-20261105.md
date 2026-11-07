# 方法变更台账：QuadGraph 原方法与 Text2SQL 实验改动

**更新时间：2026-11-07。** 本文按“原始方法 → 本研究实际改动 → 证据与边界”说明目前做过的工作。重点是区分算法修改、检索/上下文改动、评测诊断和仅在合成图上的机制探针。

## 先说结论

目前没有改 QuadGraph/G-reasoner 的核心图消息传播算法、模型权重或训练目标。已完成的大部分 Text2SQL 对照使用 Qwen3-Embedding-0.6B 对表/列文本做稠密检索；主要变化发生在向量维度、候选排序、字段文本、返回上下文长度，以及 P2d.3 的一次 SQL 修复流程。G0/G1/G2 是小型合成图的 FK 实例表示与关系输入敏感性实验；G3 把同一冻结 G-reasoner 用于真实 BIRD dev 的条件式候选图，但只变更 query seed mask。G3 发现部分排序受起点影响，但预设机制门为 INCONCLUSIVE；没有正确性标签，不能宣称图传播或方法变好。P2d.3 Full 已完成并判为 NO-GO；它验证了 authorizer 的越界阻断，但没有达到受限修复的准确率增益门槛。

因此，目前最有证据的正向结果是 **P2c-R 在固定预算下提高离线 Schema 节点覆盖**。它还没有证明 SQL Set EX、JOIN 角色准确率或图推理提升。

2026-11-06 的只读反事实审计显示，8个被拒修复候选中有2个完整 Schema 下可执行且 Set/Bag 正确；另有2个完整 Schema 编译失败。6个初始上下文拒绝中有2条 A0 SQL 正确，但 A2 在这6题里无正确最终输出。该结果只说明本轮 authorizer 拦下少量正确候选，不重算 P2d.3 的66题系统指标，也不改变其 NO-GO。

## 原始 QuadGraph / G-reasoner 做什么

原论文的 QuadGraph 是统一图索引，把 **Community、Document、Knowledge Graph、Attribute** 四层组织进一个图。G-reasoner 接收 Query 表示、起始节点和图结构，通过 query-dependent GNN 传播关系信息，最后输出节点相关性分数供 retriever 选节点。论文报告的模型主干为 6 层、1024 隐藏维、DistMult 消息函数、sum 聚合和关系表示 MLP；它不是一个 Text2SQL 专用 JOIN 角色分类器。

在本研究审查的官方实现中，`edge_type` 和 `rel_attr` 会进入关系消息通道；`edge_attr` 和后来加入的自定义 FK-instance 字段不会自动进入该主干。retriever 的节点 Top-K 也不会自动保证表列归属、JOIN 约束完整、实例身份唯一或 SQL 子图连通。详见[论文与代码审计](paper-and-code-audit.md)、[图算法源码审查](graph-algorithm-code-review-20261016.md)。

我们的表/列实验把数据库表和列当作候选 Schema 节点，但多数实验只用文本 embedding 排序，没有把这套 Schema 图送进 G-reasoner。因此不能把这些结果称作“QuadGraph 图传播变强”。

## 已完成方法与实验逐项对照

| 阶段 | 原做法 / 对照 | 本研究具体改动 | 结果与可支持结论 |
|---|---|---|---|
| **P1：向量维度筛查** | 1024 维 Qwen3 embedding；按 cosine 排表/列 | 把同一 1024 维输出截成 128/256/512/768/1024 前缀；每个前缀重新 L2 归一化并做精确 cosine。未改 GNN 或 checkpoint | 512 维向量矩阵少 50%，但列 Recall@5/@10 低 1.33/0.77pp，违反召回不下降门槛；没有低维配置通过。见[P1 原报告](reports/gfmrag_p1_official_20261014/report.md)。 |
| **P1.5 / P1.6：诊断与基线冻结** | P1 历史运行的输入文本序列化与评分缓存不能严格逐题复现 | P1.5 加入 gold-rank、候选饱和、预算装包、错误归因与 FK 计数诊断；P1.6 冻结同一 1024 维缓存、节点顺序和 scorer 重放。不改语义打分算法 | 属于测量可靠性和错误归因，不是新检索方法。P1.5 严格复现门未通过；P1.6 建立了可复用的 Dense 基线，但没有方法增益主张。 |
| **P2a：BM25 / RRF** | P1.6 的 1024 维 dense cosine | 固定候选文本和候选全集，新增 BM25 词面排序，以及 Dense 与 BM25 的 RRF（k0=60）；不训练模型、不改图 | 全体 Column R@10：Cosine 68.00%、BM25 55.91%、RRF 66.90%。预先固定的非饱和706题：58.20%、47.70%、58.29%；RRF 只多 0.09pp，Complete@2048 反而低 5.38pp。主成功门 NO-GO。 |
| **P2b：删除 Values 字段** | R0 列文本含 Name、Type、Description、Format、Values | R1 只从列文本删除 `value_description`；仍保留全部873个表/列节点、Query、1024维向量评分和预算。278列有非空 Values | Column R@10 下降0.96pp；Complete@1024 全体提高9.32pp、固定非饱和集提高5.52pp。说明短文本有利于装入更多节点，但检索相关性主门失败；不支持全局删除 Values。 |
| **P2c-R：检索与返回文本拆开** | 原本同一份 Schema 文本既用于 embedding 检索，也用于生成上下文 | 2×2 因子设计：V00=R0排名/R0上下文；V01=R0排名/R1上下文；V10=R1排名/R0上下文；V11=R1排名/R1上下文。V01保持富文本排序，只返回去 Values 的短文本 | V01 与 V00 的 Column Top-K 完全相同；Complete@1024 从56.64%到67.60%（+10.96pp），固定706题从37.96%到46.18%（+8.22pp）。这是“同一检索结果用短表示返回后，预算内完整 Schema 覆盖提高”，不是 SQL EX 或更好的语义排序。 |
| **P2c Values 风险 / 绑定** | P2c-R 只测 Schema 覆盖，没有判定被省略值信息是否影响 SQL | 先对参考 SQL 的直接谓词常量做词面线索审计，再对19个输入不可见常量做 AST 源列绑定；所有 Gold 只作事后诊断，不进入检索 | 407/1460题出现词面线索；19题含至少一个问题/evidence不可见常量。19题中9题/10个 literal 直接绑定到被删 Values 的同一列，8题不匹配、2题未知。不是 Values 语义必要性的人工结论，也不是性能实验。 |
| **P2d：固定生成器的三臂 SQL Pilot** | E0 使用 V00 的节点/完整 R0 文本 | E1 使用 V01 节点/短 R1 文本；E2 保留 V00 节点、只换短 R1 文本。固定本地 Qwen2.5-Coder-7B、每题每臂一次生成、无 SQL 修复；30题（19优先案例+11匹配对照） | 确认 Set/Bag 正确数为 E0/E1/E2 = 8/7/8；未知较多，样本有偏，不能证明 V01 改善 SQL，也不能把 E2 的输入 token 少30.27%称为无损压缩。Jev 没有运行，结果不是 Jev。 |
| **P2d.1：评测器覆盖修订** | P2d v1 因安全规则把4条含存储列时间表达式的参考 SQL 判为不可比较 | 只扩展只读评测器对受限、确定性时间表达式的支持；保存的90条预测不变，做137项合成安全检查及83条旧结果一致性回放 | 更多案例从 unknown 变为可判，但新增判定为错误；Set 正确数仍8/7/8，预测仍有10条解析失败、18条 missing-column。改的是测量覆盖，不是 SQL 生成方法。 |
| **P2d.2：冻结失败归因** | 旧 Pilot 把失败记成 parse/missing-column，无法判断是检索漏字段还是 SQL 引用错误 | 不再生成 SQL；对28条封存失败做 AST 结构检查，并对18条缺列 SQL 做只读 `EXPLAIN`，映射到上下文可见性、标识符存在性和作用域类别 | 分类为10 parse/结构、13限定符/作用域、4不存在字段、1误用可见字段；没有失败字段缺失于上下文。这是错误分析，不是新修复器；用于提出新样本验证问题。 |
| **P2d.3：检索上下文约束修复** | P2d 每臂只生成一次；P2d.2 指向生成 SQL 的作用域/标识符有效性问题 | 三组共用同一初始 SQL：A0不修复；A1失败时用完整 R0 Schema 修复一次；A2只用原 V00 Context 修复一次，并对初始 SQL和修复 SQL都用 SQLite authorizer 禁止超出检索上下文的表/列。Full 66题、Smoke 5题，排除33个旧 P2d 准备样本。 | Full Set EX：A0 18/66（27.27%）、A1 20/66（30.30%）、A2 17/66（25.76%）；A2−A0为−1.52pp，A2−A1为−4.55pp。A1修复尝试13次、候选接受2次；A2尝试19次、候选接受3次，拒绝8个越界字段提案，接受的越界读取为0。最低修复信号与 authorizer 安全门通过；A2未达到“至少比 A0 高5pp”，故按预注册判为 `NO_GO_OR_INCONCLUSIVE`。见[P2d.3 完整报告](reports/p2d3_context_bounded_repair_20261105_01/README.md)及[匿名聚合](reports/p2d3_context_bounded_repair_20261105_01/aggregate_summary.json)。 |

### P2d.3 authorizer 只读反事实审计

**原方法：** A2 对检索上下文外的表列拒绝读取；被拒候选只记录为拒绝。**本轮改动：** 不改变 A2，也不重新生成 SQL，只对封存的6个初始拒绝和8个被拒修复 SQL 做离线回放；去掉 V00 标识符 allowlist，但保留只读 SQL 检查、执行限制和同一结果比较。**结果：** 8个修复候选里6个完整 Schema 可执行，2个可比较候选正确，4个错误，2个编译失败；6个初始拒绝中2条正确，A2最终在该子集为0/6。结论仅限候选归因，不改变原 A2 17/66 的系统分数或 NO-GO。[完整报告](reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md)。

## 图方法探针到底改了什么

### G0：从平行 FK 边到 FK mapping 实例节点

**原始/直接表示：** FK 可表示为两个表节点之间带关系类型的边；同一对表可能同时有 billing 与 shipping 两种 FK，边的映射身份容易被表级节点分数混在一起。

**尝试的表示：** 在合成图中把每个不同的有序表/列映射显式变成一个 Join mapping 节点，再连到端点表；结构 ID 由有序表和列元组确定。完全相同的 FK 声明合并成同一 mapping ID，声明次数作为 multiplicity 元数据保留。另比较 Dense cosine、直接 typed-edge 图、reified mapping-node G-reasoner 与简单 FK path。

**结果：** G0-01 Full 因 PyG 图转设备时原对象被原地移动导致 permutation 对照失败，属于实现错误，未得科学结果。G0-02 修复为设备移动前 clone 后完成：置换稳定性通过，但 G-reasoner 在4个合成问题中2/4正确，Dense cosine 4/4，预注册信号门 NO-GO。只说明该 checkpoint 在这个合成任务上未达到预设阈值，不说明真实 BIRD Role 效果。

### G1 / G2：关系通道敏感性

G1 固定 checkpoint、Query、起点和五节点合成图，分别扰动 metadata、`edge_type`、`rel_attr`、一致 ID 重标、起点与 Query。G1 的两条关系边同源同目标，交换关系后送入每个目标的消息多重集合没有变化；置换不变的 sum 等聚合自然可能输出不变。因此 C2/C3 的 delta=0 使 G1 预注册门 NO-GO，但不能据此说模型不读关系通道。

G2 只改变合成拓扑以打破上述对称：两个关系角色分别走 `0→1` 和 `0→4`，同时保留反向边及 FK instance 结构。官方 checkpoint 对关系 ID/关系向量干预的分数变化分别为0.7588和3.7813；metadata-only 负控与同步语义重标保持0。G2-A PASS 仅表示此非对称 fixture 上分数对关系输入敏感，所有条件的 top-1 都未改变；没有真实 JOIN 角色准确率或 SQL EX。

### G3：固定 FK 候选图上的起点敏感性

**原始 QuadGraph 机制：** 查询先取得图中的 query-linked entity/start node，再由 G-reasoner 沿关系传播并给节点打分。**此前的 Text2SQL 适配：** 已知表对的两个表端点都标为 seed，FK mapping 节点通过四条有向边连到端点；这只是给定表对后的 mapping 诊断，不是论文的端到端实体发现。**G3 实际改动：** A0 保持双端 seed，A1 只 seed 稳定字典序第一端，A2 只 seed 第二端；只改 `start_nodes_mask`。Query/mapping/table/relation embeddings、mapping 候选、图边、G-reasoner checkpoint、参数和排序 tie-break 全部冻结，没有改 GNN、训练或 loss。

**结果：** Full 55 对、123 个候选。A1 相对 A0 改变 Top-1 4/55（7.27%），反转候选对6/81（7.41%）；A2 为6/55（10.91%）和7/81（8.64%）。A0 重复误差0、最高分并列0。信号门要求同一条件同时达到 Top-1 改变≥20%及候选对反转≥10%；无实质影响门要求两单端条件两项指标都≤5%。本次两门都未满足，判定 `INCONCLUSIVE` 并停止。因为没有读人工/模型审阅标签，不能知道任何变化是纠正还是损坏；这不是准确率或方法收益。详见[G3完整报告](reports/g3_fk_seed_direction_sensitivity_20261106_01/README.md)。

### P0：模型代理 mapping 排序错误归因

**本轮原方法/改动：** 不改上一轮的排序器；只对冻结的 G-reasoner、Dense Cosine、BM25 和稳定 ID 排序做预注册分层。分析38个可区分的 Full 单元，使用三模型高置信精确多数作为探索性代理标签；不读 Gold SQL、参考 JOIN 或 SQL 执行。

**结果：** G-reasoner Accepted@1 为7/38（18.42%），Dense为27/38（71.05%），配对净差−20。2候选和3候选两层，以及无列重叠/单端点重叠两层，G-reasoner 均无正向净差。全部38题都只有一个接受 mapping，且没有复合FK，故不能分析多正确 mapping 或复合FK。按预注册停止，不在同一代理标签上继续调参或挑图结构。该结果不估计真实FK Role准确率。见[归因报告](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/README.md)及[匿名聚合](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/aggregate_summary.json)。

### P0：SQL-used 候选—目标身份对齐诊断（2026-11-07）

**原方法/问题：** 上一轮将模型审阅包里的问题×表对样本，直接拿对应 BIRD 参考 SQL 的显式 `JOIN ON` FK mapping 作标签；Smoke 的 SQL 解析成功，但 0/5 对齐到候选映射，因而不能评分。

**本轮实际改动：** 不改候选图、G-reasoner、Dense、分数或任何模型审阅输出。固定同一 60 对，新增一条 CPU 审计路径：从参考 SQL 按 JOIN 和 alias pair 直接抽取已解析列等式，与冻结 mapping 的完整有序列对身份逐一比较；同时运行旧的候选过滤 matcher，并比较两套 mapping ID。复合 FK 要在同一 JOIN/alias pair 内完整匹配。WHERE 和 USING 不纳入本轮标签。

**结果与边界：** 60/60 对目标表对都不在对应参考 SQL 的已解析显式 `JOIN ON` 等式中；76/76 个限定 JOIN 等式解析且作用域错误为0。两种 matcher 在60/60上一致且都无 mapping ID。故 0/5 的直接原因是这批问题×表对与显式 SQL-used 评测目标不对齐，而不是两套身份 matcher 不一致。本审计没有 G-reasoner/Dense 排名指标，也不能判断这些表对是否通过 WHERE、USING 或其他 SQL 结构关联。停止复用这批样本。详见[报告](reports/p0_fk_candidate_sql_identity_alignment_20261107_01/README.md)。

### P0：SQL-used FK mapping 独立注册 03（2026-11-07）

**原排序方法：** 冻结 G-reasoner-34M 在显式 FK mapping 候选图上传播；Dense cosine 复用同一 Qwen3-Embedding-0.6B 向量。前序 7/38 对 27/38 的对照使用三模型代理语义标签，但这些代理不是人工 Role 真值；本注册不改图、编码器、checkpoint、消息传递、排序公式或训练。

**本次实际改动：** 只更换评测样本与目标：从参考 SQL 中已解析的显式 `JOIN ON` 表对重新筛选新样本，把 SQL-used 完整 FK mapping 当离线标签；同时按用户要求让两名本地 Qwen 模型作盲审次要代理。Smoke/Full 由新 experiment ID 确定，排除原60题审阅包。

**结果与边界：** CPU 标签门通过，5题 Smoke +108题 Full、覆盖4个匿名数据库，候选覆盖174/176。A/B 各有5/5有效输出，但只有2/5高置信精确一致，未达4/5门，模型审阅 Full 停止。随后 G-reasoner Smoke 在模型导入前因 CPU manifest 缺少运行器要求的样本计数键而停止；没有 embedding/GFM 前向或排名指标。这是实现契约错误，不是模型正负结果。按连续工程错误暂停规则不重用失败 run ID。详见[独立报告](reports/p0_fk_sql_used_mapping_rank_20261107_03/README.md)和[匿名聚合](reports/p0_fk_sql_used_mapping_rank_20261107_03/aggregate_summary.json)。

### FK 结构 Gate 与身份政策

对11个 BIRD dev SQLite schema 的结构审计得到103条原始 FK、100条有效、3条无效。100条有效声明中有一对结构完全重复，因此内容唯一 mapping 是99个。映射级身份方案保留99个唯一映射、198条方向边，并另存1个重复声明的 multiplicity；声明 multiset 方案保留100个 ID、200条方向边，但完全重复项的出现序号不能稳定绑定回具体 PRAGMA 组。原 Gate 因身份碰撞仍为 NO-GO；这解决的是“如何表示重复映射”，没有生成角色标签。

2026-11-05 canonical P1.5 crosswalk 又确认：把原始103条过滤为100条有效 FK 后，P1.5 的970/197逐题计数完全不变；因此3条无效 FK 不是 packet-28 与 P1.5 的差异来源。packet-28 为1043/176，仍与 P1.5 不同；这是两套实现对 FK 列对匹配、完整复合 instance、歧义和候选的定义差异。旧956/174缺可复算源码与逐题标签，尚不能恢复。

## 目前还没有实现或证明的部分

- 没有更改 G-reasoner 的6层传播、DistMult 消息、sum 聚合、关系 MLP、模型参数或训练损失；没有训练新的 GFM checkpoint。
- 没有把真实 BIRD 查询上的 `Query-aware FK-instance edge gate` 接入消息传播；也没有输出合法、连通、列归属正确的 JOIN 子图解码器。
- 没有完成可信双人 Join Role 标签（当前为0），没有报告 Role F1 / Join-Path Accuracy。
- 没有证明 P2c-R 的覆盖收益提升 SQL Set EX；P2d 只是30题有偏 Pilot。
- P1/P2 使用的 BIRD dev 是反复开发集；不能把结果说成独立数据库泛化或论文确认性证据。

## 资料来源

- G-reasoner 论文（QuadGraph 四层和模型配置）：[ICLR 2026 正式论文页](https://proceedings.iclr.cc/paper_files/paper/2026/hash/67e2da8af2476c7441c881fc253042a6-Abstract-Conference.html)。
- 官方实现：[RManLuo/gfm-rag](https://github.com/RManLuo/gfm-rag)。
- 本项目源码核查：[GraphReasoner 源码审计](graph-algorithm-code-review-20261016.md)。
- 主要结果： [P1](reports/gfmrag_p1_official_20261014/report.md)、[P2a](reports/p2a_similarity_20261018_01/README.md)、[P2b](reports/p2b_values_ablation_20261018_01/README.md)、[P2c-R](reports/p2c_r_recovery_20261019_01/README.md)、[P2d](reports/p2d_sql_utility_20261022_01/README.md)、[G0-02](reports/g0_fk_instance_node_20261024_02/README.md)、[G2](reports/g2_asymmetric_relation_20261024_01/README.md)、[canonical P1.5 FK crosswalk](reports/p0_fk_canonical_crosswalk_20261105_01/README.md)。

### P0：FK-domain 检查器与 SQLite 原生语义对账（2026-11-07）

**原方法：** eligibility runner 用非 NULL anti-join 检查 child 值能否在 parent key 找到相等值；target 或 alternate 中任一映射有不匹配值，就将候选对标为 original_fk_domain_violation。前一轮 32/55 个候选对因此被排除，14/55 的覆盖量未通过 40 对/3库门槛，反事实 shuffle 没有运行。

**本次实际改动：** 不改 G-reasoner、图、消息传播、embedding、排名、SQL、eligibility 规则或覆盖门。新增只读 CPU 审计，把同一批32个固定候选对的 target/alternate 声明分别用 SQLite PRAGMA foreign_key_check 再判一次，并按 foreign_key_list.fkid 对齐到每个声明；旧 anti-join 直接从冻结运行器复用。

**结果与边界：** pair-level 32/32、声明级2/2一致，零 PRAGMA 错误，数据库哈希未变。32对实际只复用同一匿名数据库的两个唯一声明：一个两种检查均计49条违规，另一个均为0。由此支持“旧检查器在这组声明上忠实反映 SQLite 外键语义”，并说明本次观察的旧排除不是比较器实现错误。不能把32对当作32个独立声明、估计全数据违规率或判断业务 JOIN Role。该审计没有 GFM/Dense 前向或 SQL EX；counterfactual-shuffle 支线保持关闭。见[完整报告](reports/p0_fk_domain_violation_crosscheck_20261107_01/README.md)与[匿名聚合](reports/p0_fk_domain_violation_crosscheck_20261107_01/aggregate_summary.json)。
