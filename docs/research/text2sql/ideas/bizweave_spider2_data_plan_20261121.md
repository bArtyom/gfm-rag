# BizWeave × Spider 2.0：业务证据映射与真实歧义检索的下一轮研究计划

**日期：** 2026-11-21  
**状态：** proposal / dataset screening；尚未进行人工金标审阅、真实检索评测或模型训练。  
**仓库分支：** `research/bizweave-event-constraints-20261117`  
**上轮依据：** [`bizweave_business_semantic_pilot_20261117_001`](../reports/bizweave_business_semantic_pilot_20261117_001/README.md)

## 1. 研究判断与目标

上轮手工合成 fixture 的 structured selector 在可回答题上为 8/8，正确弃答 2/2；这只证明手工规则能够表达指定业务区别，不能证明真实检索有效性。BIRD 的严格词面/SQL 候选审计显示：状态类 train/dev 为 15/0，而时间类 365/57、粒度类 2393/340，因此继续仅靠 BIRD 直接验证支付/退款状态歧义的证据供给不足。

新的主路线：**Evidence-Grounded Business Mapping for Text-to-SQL Schema Retrieval**。在候选物理实现均可 JOIN 的前提下，将业务事件、状态谓词、时间依据、统计粒度及证据来源组成可执行语义映射，与自然语言意图匹配。对多种兼容解释或无法核实的映射保留未决状态；核心目标是提升**正确实现选择**并减少**缺乏证据的错误接受**，而非单纯追求更长的 Schema 文本。

核心研究问题：在**同候选、同信息**条件下，结构化、可溯源的业务映射是否比直接使用 Schema/文档的词面或向量检索、最短路径及同标签规则基线更可靠？

## 2. 为什么优先 Spider 2.0-Lite，而不是直接把 Spider 1.0 当主实验

- **Spider 1.0：** 主要适合作传统跨域 Schema Linking、JOIN 与粒度对照；并不自带足量可核实的企业业务事件定义和多解释标签，不能直接证明 BizWeave 主张。
- **Spider 2.0-Lite：** 任务文件公开，部分样本显式引用外部业务文档，包含事件码、指标定义、会话/交易粒度与多时间语义，更适合作**有证据的业务映射选择**的首轮真实数据审阅。
- **BIRD：** 保留时间/粒度方向的辅助候选来源，但 Gold SQL 不能被当作“唯一业务正确解释”的金标；已有 BIRD-dev 为暴露开发集，不能当作全新独立测试集。
- **AmbiQT / AMBROSIA / PRACTIQ：** 考察作为独立的歧义识别、关系路径替代实现及弃答评测；它们不一定有可溯源的业务定义文档，因此不能无条件替代 Spider 2.0-Lite 的 evidence-grounded 实验。
- **Spider 2.0-Snow：** 可作后续外推；本轮先核查数据版本、SQL 方言和云数据库访问成本，尽量先做无需执行 SQL 的离线审阅。

### 2.1 已核验的 Spider 2.0-Lite 文件级候选证据（非金标）

直接对官方 `spider2-lite/spider2-lite.jsonl`（读取时文件 SHA `bb9bb2ecf5b335c587354891a979ff5218c4502c`）做了只看问题文本和 `external_knowledge` 字段的粗略审计：547 条任务；107 条显式关联外部文档；按 purchase/transaction/refund/cart/order/payment/revenue 等词面模式命中 136 条，其中 18 条关联外部文档；SQLite 本地任务为 135 条，其中 13 条关联外部文档。**这些数值仅是文件级词面统计**，并非严格业务约束候选，更不能证明有 136 条可评价的业务歧义。

可优先人工检查的真实任务/文档：

| 条目 | 可核验信息 | BizWeave 候选机制 | 当前限制 |
|---|---|---|---|
| `bq270` | 月度加购/购买转化率，外部文档 `ga360_hits.eCommerceAction.action_type.md` 明确编码：详情浏览=2、加购=3、购买完成=6、退款=7 | `Event → action_type → SQL predicate`，并保留文档来源 | 问题本身相对明确；不能直接视作“存在多种合理解释” |
| `bq001` | 首次访问与首次交易之间的天数；伴随 `google_analytics_sample.ga_sessions.md` | Visit/Transaction 的时间语义、事件角色和粒度 | 需检查实际表字段、SQL 候选与是否有竞争实现 |
| `ga006` / `ga009` | purchase session 和 engaged session 等具体事件与 session 去重 | Session 粒度、事件条件、去重依据 | 某些限制已直接写入问题，需防止伪歧义 |
| `ga010` | 关联 `ga4_dimensions_and_metrics.md`，包含业务渠道分类条件 | 文档定义的业务指标 → 可验证谓词 | 偏指标定义，和主线“事件路径竞争”要分开报告 |

另有 `Food_Event_Cleansing_Logic.md` 对 `date_created` 与 `date_started` 的区分，可用作**时间语义文档例证**，但不能在未核对任务与数据库对应关系时宣称其已构成一个可打分问题。`RFM.md` 可作为后续业务指标扩展，不与首轮事件映射主结论混淆。

官方链接：
- Spider 2.0 仓库：https://github.com/xlang-ai/Spider2
- Lite 问题：https://github.com/xlang-ai/Spider2/blob/main/spider2-lite/spider2-lite.jsonl
- Lite 文档目录：https://github.com/xlang-ai/Spider2/tree/main/spider2-lite/resource/documents
- 事件编码文档：https://github.com/xlang-ai/Spider2/blob/main/spider2-lite/resource/documents/ga360_hits.eCommerceAction.action_type.md
- 业务渠道文档：https://github.com/xlang-ai/Spider2/blob/main/spider2-lite/resource/documents/ga4_dimensions_and_metrics.md

## 3. 分开检验两个命题

**H1（证据支持的映射选择）：** 在同候选同信息条件下，结构化 `event/status/time/grain + evidence` 映射能否提高选中业务正确实现的准确率？首选 Spider 2.0-Lite 的文档关联案例，报告 Oracle Mapping 与 Predicted Mapping 两种设置。

**H2（歧义与安全弃答）：** 对确实有多个合理实现、缺少时间依据或证据相互冲突的问题，系统能否避免无证据强选？应使用人工标注的 Spider 2.0 衍生对照与 AmbiQT/AMBROSIA/PRACTIQ 独立测试；不能把官方明确任务擅自标为歧义金标。

**重要边界：** 文档支持的事件编码理解 ≠ 多条有效业务路径的歧义消解 ≠ 端到端 SQL Execution Accuracy。三个结论必须分别获得证据。

## 4. 下一轮最小可执行实验（先审阅，后评分）

### P0 — 冻结数据与候选初筛

1. 固定 Spider 2.0-Lite 的仓库 commit、JSONL/doc/schema 哈希、可用数据库类型与 SQL dialect；不复制私有云库内容。检查本地已有资源与许可/费用。
2. 从有文档、含事件/状态、时间基础、会话/订单/明细粒度线索的题目先抽取约 30–50 条人工审阅；保留硬负例，不因词面命中而自动认定歧义。
3. 对每题确认：业务事件/状态、时间依据、粒度、可用物理 JOIN/过滤实现；标记**单一可核验、多个合理、证据不足、无有效候选**；记录文档 URI/行段、字段和值码，以及是否有真实竞争路径。
4. 按数据库做 grouped review/split；至少双人复核歧义与未决题（记录分歧及仲裁）。在未完成审阅前**不运行真实性能评分**。

### P1 — 固定同候选、同信息的基线

- `Shortest path`、Schema BM25 / Dense（只看 Schema）作为低信息传统基线；
- `Doc BM25 / Dense`（输入相同的业务文档）作为信息公平的非结构化证据基线；
- `Same-label typed-rule baseline`（给定同样人工标签和约束但不使用完整 BizWeave 证据机制），隔离“规则过滤本身”的贡献；
- `BizWeave structured + provenance + unresolved state`；固定候选、意图来源、文档访问范围、预算和 tie-break；不得给 BizWeave 预先正确标签、其他基线却只有表名。
- 另外分列 **Oracle intent/mapping**（机制上限）与 **Predicted intent/mapping**（实际自动化），不混报。

### P2 — 消融与评价

- 消融 Event、State、Time basis、Grain、Evidence gate、Ambiguity gate；
- 指标：valid mapping Recall@K、正确实现选择率、event/state/time/grain exact match、错误接受率、abstention precision/coverage-risk；如有多金标，用合法实现集合评测，而非与一个 SQL 字符串全等；
- 只在可靠标注和足够样本满足预注册门槛后，考虑可执行 SQL/EX 及跨数据库泛化，不抢先训练/GPU。

### P3 — 技术债与止损门槛

- 修复已有 runner 的 `mapping_matches`：`require_evidence=False` 同时改变 `time_basis='unspecified'` 行为，导致 Evidence Gate 与 Time Ambiguity Gate 的消融不独立。
- 明确多合法候选时的策略：返回候选集、按可证实约束过滤、必要时弃答/提问；不要在没有独立支持时用 path cost 强行决断。当前完整 selector 并未实际用 path cost 排序。
- **建议的前置门槛（待在查看标签前正式冻结）：** 初审 30–50 条；仅当出现足够多（目标至少 30 条、跨至少 3 个数据库）的**经审核真实竞争实现/歧义**样本，才将 H2 作为独立定量实验。未达标时把 Spider 2.0-Lite 保留为 H1 证据映射测试，H2 改用专业歧义基准或具有可信文档/查询日志的数据。
- 不把这个候选数量、词面命中率、合成准确率当作论文效果；尚未做统计检验，也没有新 SQL 执行或模型结果。

## 5. 预期产出（现在只是计划）

- 数据审计：带 source hash、候选规则、按 DB 统计和具体核验理由的 `dataset_audit`。
- 人工标签协议和盲审记录：`annotation_guideline` / `adjudication`，包括多金标及证据等级。
- 固定候选实现集合、same-information baseline 与单因素消融脚本。
- 第一轮真实数据对比报告：区分机制上限、预测抽取、弃答收益和失败案例。

**当前决策：** 把 Spider 2.0-Lite 作为下一轮首选**证据来源与数据审阅场景**；暂不宣称它天然具有足够多的多路径歧义题，也暂不开始模型训练或端到端 SQL 效果实验。
