# BizWeave：Idea 沿革与实验证据记录

**更新日期：**2026-11-23
**当前权威定义：**[BizWeave 讨论纪要](bizweave_discussion_minutes_20261123.md)
**当前 Idea 摘要：**[bizweave.md](bizweave.md)
**研究评审：**[BizWeave Idea 评审](bizweave_review_20261123.md)
**项目：**[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，当前本地研究分支 `research/bizweave-event-constraints-20261117`。

> 本文件把研究问题变化、已做的试验和证据边界放在一起。当前主线以 11 月 23 日纪要为准；之前关于 JOIN 路径选择、弃答和在线需求抽取的表述保留为历史，不与当前主张混算。

## 当前一句话

BizWeave 当前研究：**从数据库 Schema 与业务文档自动归纳带证据、可核验的 Business–Schema 异构图，并用它做 Schema Linking / Retrieval。**拟研究的差异不是“建一张图”，而是从分散业务 Claim 中联合对齐相互依赖的多个业务概念与一组物理表列，并验证这种映射结构是否比同信息的 Schema/文档双路检索更能找全字段。

当前核心假设：在 Schema、文档、候选表列集合与检索预算相同的情况下，有来源证据的显式业务映射图能提高低词面重合、跨字段依赖或复杂术语问题的必要表列召回与排序质量。

当前阶段不把 SQL 生成、最终 JOIN 路径裁决、安全弃答或完整业务本体构建作为主贡献。联合对齐目前仍是待具体化、待验证的方法设计。

## 1. Idea 的变化

### 起点：低外键 Schema 上的业务语义图

最初的动机是：在 Spider/BIRD 这类任务上，不只依赖数据库声明的外键，而让模型结合 Schema 与其他可用信息恢复业务语义关系，协助 Text-to-SQL 找到相关表和列。早期讨论把图进一步扩展为事件、状态、时间口径、粒度、JOIN 路径选择和证据不足时弃答。

### 早期探索：事件约束和 JOIN 实现选择

11 月 17 日合成试验及 BIRD 标签供给审计采用了“多个物理路径都可连接时，按事件/状态/时间/粒度选择业务实现”的问题定义。11 月 21 日在线需求见证 smoke 也尝试从问题抽取结构化业务约束。

### 当前收敛：离线建 Business–Schema 图，在线做 Schema Linking

11 月 23 日用户提供的纪要把当前任务改得更清楚：先从 Schema 和业务文档离线抽取 Claim、业务概念及映射声明，再在问题到来时用图召回表列并返回证据路径。JOIN 裁决、弃答及 SQL 生成被明确排除在当前主贡献之外。

**范围变化：**早期“Query-conditioned JOIN 路径选择/弃答”是历史相邻问题，不是当前论文主线。旧试验结果仍有效，但只能说明那些旧问题上验证过或失败过什么。

### 文献核对带来的新边界

2026 年 DANKE/Text-to-SQL 工作已在知识图谱中表达业务知识，显式保存知识 Schema 到关系 Schema 的映射，并用于 Schema Linking。Graph-Link、SchemaGraphSQL、GRASP-SQL 处理图式 Schema Linking，DRAG 分别检索 Schema 与外部文档。因此，“把业务图映射到表列”或“用图来检索 Schema”不足以单独构成新颖性。

仍可研究的窄差异是：**从非结构化业务文档自动构建带证据的映射，并对有关联的 Claim/Metric Components 与多列映射进行联合对齐。**能否成立需靠系统文献核查和实验回答，当前新颖性未知。详细分析见[评审报告](bizweave_review_20261123.md)。

## 2. 按时间整理的实验历程

### 2026-11-17：合成机制检查与 BIRD 数据供给审计

**内容：**用手工构造的订单例子区分购买/浏览、支付完成/支付尝试、退款完成/退款申请和订单/明细粒度，并在 BIRD train/dev 上扫描状态、时间和粒度候选。

**结果：**合成案例中，结构化约束加证据门通过 8/8 已解决案例、4/4 对照切换和 2/2 正确弃答；移除证据门后，未验证支付状态映射有 1/2 次被错误接受。最短路径正确 4/8，Schema token 和扁平映射描述基线各 5/8。BIRD 严格状态线索候选为 train 15 条/4 个库、dev 0；时间候选 train/dev 为 365/57；粒度候选为 2,393/340。

**边界：**规则与映射均为人工编写；BIRD 数字只是候选供给统计，没有人工业务金标，也没有真实检索评分。

报告：[合成机制与 BIRD 供给 pilot](../reports/bizweave_business_semantic_pilot_20261117_001/README.md)

### 2026-11-21：Spider 2.0-Lite 文档数据初筛

**内容：**扫描 Spider 2.0-Lite 的任务、外部文档和业务关键词。

**结果：**547 条任务中 107 条显式关联外部文档；词面筛查命中 136 条任务，其中 18 条关联外部文档。

**边界：**文件级关键词命中不是人工语义标签，也没有验证映射或效果。此前计划见[Spider 2.0 数据计划](bizweave_spider2_data_plan_20261121.md)。当前 11 月 23 日主线的文档资源评估优先转向 BIRD-Ent；Spider-Ent 没有外部知识检索任务。

### 2026-11-21：BIRD `public_review_platform` 零外键图 pilot

**设置：**15 张表、0 条声明外键、381 道问题。Local Qwen2.5-Coder-7B-Instruct 只看 Schema 和字段描述，运行一次构图。

**图结果：**15 节点、15 条边，物理表列绑定有效；没有事件、状态、时间依据、指标、粒度节点或未决项。参考 SQL 中观察到 29 种 JOIN 对，图候选覆盖 8 种；8 个图候选 JOIN 对都在参考 SQL 中出现（这是使用代理，不是业务语义标注）。

**检索：**BM25 vs typed graph：Recall@1 为 44.9% vs 37.0%；Recall@3 为 69.2% vs 73.0%；Recall@5 为 79.8% vs 86.5%；MRR 为 0.871 vs 0.810。

**结论：**图结构绑定有效；Top-K 覆盖有所增加但首位排序变差。没有输入业务文档，所以不是当前 Business–Schema 图假设的验证。

报告：[BIRD 零外键图 pilot](../reports/bizweave_bird_zero_fk_graph_20261121_001/README.md)

### 2026-11-21：在线需求见证 smoke

**内容：**要求模型把问题解析成业务需求及精确文本跨度，再用于表列筛选。两次 5 题 smoke 的有效 JSON 均为 0/5；修复评估器后，恢复的需求项/跨度仍为 0/22。完整绑定为 5/5；Schema 候选 Top-32 命中 16/22 个参考读取列。按 smoke 门槛停止，没有执行 40 题 pilot，GPU 路径未启动。

**边界：**该失败针对旧在线需求抽取协议，不是新主线的离线文档 Claim 抽取或 Business–Schema 对齐。

### 2026-11-22：Spider `bike_1` 低外键图 pilot

**设置：**Spider 1.0 的 `bike_1`：4 张表、1 组声明外键列对、104 条训练问题。满足预设表数/问题数条件的零外键库未找到，因此选择该低外键库。Local Qwen 只看 Schema。

**图结果：**4 个节点（全部标为 Entity）、1 条关系；FK、表列绑定和证据 ID 结构有效，但没有事件、状态、时间、指标、粒度节点或未决项。104 条 SQL 均解析，未执行。5 个训练题中唯一观察到的 SQL JOIN 代理覆盖 1/5 个独立 JOIN 列对。

**检索：**BM25 vs typed graph：Recall@1 71.63% vs 39.42%；Recall@2 89.42% vs 79.81%；Recall@3 99.04% vs 99.52%；完整覆盖@3 98.08% vs 99.04%；MRR 0.926 vs 0.740。Typed graph 与 flat graph 的 Recall@3 相同。

**资源记录：**本地模型一次请求 7,187 输入 token + 1,201 输出 token = 8,388；外部 API 费用 CNY 0；估算本地 GPU 时间约 0.05 GPU-hours。

**结论：**只支持“Schema-only 模型能生成结构图草稿”，不支持业务语义准确率或稳定检索收益；单库样本且 Recall@3 接近上限，不再在 `bike_1` 调 prompt。

报告：[Spider 低外键图 pilot](../reports/bizweave_spider_low_fk_graph_20261122_001/README.md)

## 3. 不能计入 BizWeave 主张的相邻结果

同期 Query-aware JOIN/path 工作与早期 BizWeave 的在线选择部分有关，但不等于当前离线 Business–Schema 映射研究。

- QJSP 严格路径标签为 BIRD train 43 组/4 库、dev 7 组/2 库；训练侧优势集中于一个库，dev 可评分组打平，没有足够跨库证据。
- QES Phase21/22 在旧开发数据上出现小幅表覆盖变化；Phase24 Spider 914 题中训练版 912/914、原版 911/914，未通过预设稳定提升门槛；Phase25 达 24 小时上限停止，未完成 SQL EX 对照。

这些数字不能作为 BizWeave 新主线的有效性证据。原始记录见 [QJSP](https://github.com/bArtyom/Query-aware-Edge-Score/blob/research/qjsp-role-aware-paths-20261117/reports/experiments/qjsp_role_aware_paths_20261117_001.md) 和 [QES Phase25](https://github.com/bArtyom/Query-aware-Edge-Score/blob/research/phase20-refine-attribution-20261121/experiments/phase25_trained_refine_sql_20261121/amendment-001.md)。

## 4. 到目前为止的证据判定

| 问题 | 当前回答 |
|---|---|
| 能否用本地模型从少外键 Schema 生成结构有效的图？ | 单库小试中初步能；目前生成的是粗 Schema 图。 |
| 是否能从真实业务文档自动找出概念并映射到物理字段？ | 未测试。 |
| 显式映射图是否胜过相同信息量的 DRAG 双路检索/描述增强 Schema？ | 未测试。 |
| 是否有业务概念—表列人工金标？ | 当前未建立。 |
| 是否证明端到端 SQL EX 提升？ | 没有。BizWeave 图试验未运行 SQL EX；相邻 QES 结果也不属于当前主张。 |
| 新颖性是否确认？ | 未确认。已发现 DANKE 等直接相邻工作，需系统对照后再定。 |

现有 pilot 对新的问题定义有一个有用启示：**仅凭少外键 Schema 和字段描述，模型不会自然补出可靠的业务语义层。**这说明新的实验必须真实给出业务文档并检查它们是否支持映射；不是对完整新方案的失败结论。

## 5. 下一步建议与 Go/No-go

1. 扩大相关工作核对，优先 DANKE/ontology-to-relational mapping、企业语义层与自动 schema matching。
2. 审计 BIRD-Ent 的公开版本和字段。它有业务文档、`gold_table_ids` 和 `gold_knowledge_ids` 等检索标签，是现阶段的候选数据；但没有因此自动得到 Claim↔Column 人工金标。确认许可和内容后先人工看 1–5 条。
3. 建立人工 Oracle Mapping 上界。如果人工映射也不能提升必要表列完整召回，停止图检索主张。
4. Oracle 有信号后，才扩到 30–50 条按 domain 分组的探索映射；标注证据跨度、映射集合、候选冲突和多解。
5. 主要对照用相同 Schema、文档、候选池和预算的 DRAG 与 BizWeave；加入文档增强 Schema 图，判断增益来自显式映射关系还是额外文本。
6. 首轮只研究 Schema Linking；若 Mapping Precision/证据支持率低，或 Oracle 不增益，停止大模型构图实验。只有在低重合/跨字段样本上出现可信收益才继续扩大。

**当前状态：**Idea 和评审记录已保存到项目本地文档；这次没有运行实验、模型推理或数据标注。该本地工作树中还有其他研究文件的未提交变更，因此本次文档调整尚未提交/推送到 GitHub。
