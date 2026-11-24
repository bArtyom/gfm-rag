# BizWeave：有证据的 Business–Schema 图用于 Schema Linking

**状态：**探索阶段；当前主线按 2026-11-23 用户讨论纪要更新。
**新颖性：**未确认；已发现直接相邻的 Knowledge-Graph-to-Text-to-SQL 先行工作。
**规范来源：**[2026-11-23 原始讨论纪要](bizweave_discussion_minutes_20261123.md)；[Idea 评审](bizweave_review_20261123.md)。

## 当前研究问题

给定数据库 Schema 和业务文档，如何离线自动归纳一个**有证据、可组合、可核验**的 Business–Schema 异构图，把业务概念、指标、事件或规则联系到物理表列；用户提问时，如何利用该图召回必要的表和列，并返回支持映射的证据路径？

### 核心假设

在 Schema、业务文档、候选表列全集及检索预算相同的条件下，显式建模带来源的业务概念—关系—物理表列映射，能否在低词面重合、跨字段依赖、复杂业务术语和冗余大 Schema 场景下，比分别检索 Schema 与文档更完整、准确地召回必要表列？

当前最值得检验的候选机制是**联合 Business-to-Schema 对齐**：对有关联的一组业务 Claim/Metric Components 与一组表列共同评分或约束，而不是只对每个概念各自找一个最相似的列。`MappingAssertion` 应保留 Claim、来源文档跨度、一个或多个目标字段、适用范围及核验/冲突/未决状态。具体优化机制尚未实现，也未验证。

## 当前范围

- **离线输入：**Schema、字段说明、可用键/关系和业务文档。当前构图不得把测试查询的 Gold SQL、表/文档 ID 或人工答案用于建图。
- **离线图：**业务概念、Metric/Event/Rule/Component、DocumentSpan/Claim/MappingAssertion、Table/Column；只保留有依据的边，冲突与未知显式标记。
- **在线任务：**从问题找业务或 Schema 锚点，沿图召回表列；返回 `Tables + Columns + Evidence Paths`。
- **本阶段不把 SQL 生成、最终 JOIN 路径裁决、安全弃答、完整本体构建作为主贡献。**这些属于以后扩展，不改变当前假设。

## 相关工作带来的边界

2026 年 DANKE/Text-to-SQL 论文已经使用业务知识图谱、知识模式到关系 Schema 的映射和图式 Schema Linking；Graph-Link、SchemaGraphSQL、GRASP-SQL 覆盖 Schema 图检索；BIRD-Ent/DRAG 覆盖 Schema 与业务文档双路检索；GeSI/EmSI 覆盖从表格数据推断概念 Schema。因此，不能把“LLM 建图”“Schema 和文档一起放进 KG”“图检索表列”直接作为新颖性主张。

BizWeave 可能成立的差异是：**自动从业务文档和 Schema 归纳带来源证据的映射；把依赖的多个业务概念联合映射到字段集合；在同等信息下证明这种结构比双路检索/描述增强图更有用。**相关工作核对仍未完成；现阶段不要声称“第一个”。细节和来源见[评审报告](bizweave_review_20261123.md)。

## 实验计划（尚未执行）

1. 先核验 BIRD-Ent 发布版本、许可、Schema、业务文档、问题字段和检索标签。该数据集适合做文档检索对照；Spider-Ent 没有外部知识检索任务，不是验证当前文档建图假设的首选。
2. 先人工审 1–5 条，确认存在非平凡 Claim→字段映射、跨字段依赖或低词面重合样本；Gold 表/知识文档/SQL 只用于事后评价。
3. 先测 Oracle Mapping：如果人工正确映射的图检索也不能优于同信息双路检索，就停止自动建图主张。
4. Oracle 结果有信号后，再构建按数据库/领域分组的 30–50 条探索标注，并明确多解、未知和证据不足。
5. 主要对比相同输入/候选池/预算下的 DRAG 双路检索与 BizWeave；加一组同文档的描述增强 Schema 图，以隔离显式关系结构的作用。
6. 主要指标：Table/Column Recall@K、完整必要表列召回、MRR/Recall@1、知识召回、人工映射 Precision/Recall、证据支持准确率及检索成本。SQL EX 留到 Schema Linking 有增量收益后。

## 已做工作与证据边界

以下均是旧主线下的先导试验，不是 2026-11-23 核心假设的直接验证。

### 2026-11-17：合成机制与 BIRD 候选供给

手写合成案例中，约束与证据门通过 8/8 已解决案例、4/4 路径切换、2/2 正确弃答；这是规则和手写映射的可表达性测试，不是模型推断结果。BIRD 的状态/时间/粒度统计只是候选供给扫描，没有业务标签或检索效果评测。见[试验报告](../reports/bizweave_business_semantic_pilot_20261117_001/README.md)。

### 2026-11-21：Spider 2.0-Lite 筛查

筛查了任务与外部文档字段，得到关键词候选；这些是文件级统计，没有人工映射审阅或性能结论。计划见[数据审阅计划](bizweave_spider2_data_plan_20261121.md)。

### 2026-11-21：BIRD 零外键 Schema 图 pilot

`public_review_platform` 有 15 张表、0 个声明外键、381 道题。本地 Qwen 仅看 Schema 和字段说明，生成 15 个节点、15 条边，表列绑定有效，但没有事件、状态、时间依据、指标、粒度节点或未决标记。typed graph 的 Recall@3/@5 高于 BM25，Recall@1/MRR 较低；JOIN 标签是 Gold SQL 使用代理，不是业务语义金标。见[报告](../reports/bizweave_bird_zero_fk_graph_20261121_001/README.md)。

### 2026-11-21：在线需求结构 smoke

需求/跨度结构输出未通过小样本格式与覆盖门槛，后续 40 题 pilot 未启动。它测的是旧在线需求抽取路径，不是新主线的离线文档到 Schema 图归纳。

### 2026-11-22：Spider `bike_1` 低外键 pilot

4 张表、1 组声明外键、104 道训练题。本地 Qwen 仅看 Schema，输出 4 个 Entity 节点和 1 条关系；无事件、状态、时间、指标、粒度。typed graph Recall@3 仅比 BM25 高 0.48 个百分点，但 Recall@1/MRR 明显较低。该结果只支持结构图可生成，不支持业务映射或检索收益。见[报告](../reports/bizweave_spider_low_fk_graph_20261122_001/README.md)。

## 历史范围说明

11 月 17 日以前后曾把 BizWeave 设想成：在多个合法 JOIN 实现中按事件、状态、时间、粒度选择路径，并在证据不足时弃答。**这不再是 11 月 23 日确定的当前主线**；相关合成测试和在线 smoke 作为历史相邻工作保留，不能合并为当前 Idea 的正向或负向结果。完整沿革见[Idea 形成历程与实验记录](bizweave_idea_history_and_experiments_20261123.md)。

## 当前决策

继续保留方向。BIRD-Ent 文档映射与 Oracle Mapping 可行性 Gate 已预注册，尚未读取样本；协议见[实验计划](../plans/bizweave_birdent_oracle_mapping_gate_20261124_001.md)。当前仍没有真实业务文档映射准确率、没有新主线检索成绩、没有端到端 SQL 收益；完成 Gate 前不扩大模型实验、不宣称新颖性。
