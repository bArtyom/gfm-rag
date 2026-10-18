# P2a 最新实验复核与研究决策（2026-10-18）

> **状态：对已归档 P1.6/P2a 正式报告、聚合 JSON、预注册配置进行静态复核；此文档是分析而非新的实验。** 读取仓库起点 commit `41833a75036d58d879749435864731bb83779fb1`。BIRD dev 属于反复使用的开发诊断集，不是独立泛化验证。
>
> **决策：P1.6 新基线 PASS；P2a Cosine/BM25/RRF 方法增益 NO-GO，停止无依据的融合调参。下一轮优先 P2a.5 无训练错误归因与字段文本/预算诊断，并行 FK Join-Instance 数据质量修复。**

## 1. 范围、对照有效性与当前 Gate

- [P1.6 full 报告](../p1_6_rebaseline_20261018_01/README.md)：BIRD dev 1534 问题、11 DB、873 节点，1024-D Qwen3 Encoder，缓存回读 bit-exact、冻结缓存上两次 scorer 的逐题行与 score digest 相同；**P1.6 新缓存/评分基线 PASS**。注意 Smoke 两次编码的 query/node max abs diff 为 **0.002555 / 0.003764**，5/5 题输出行发生改变。**这证明缓存评分可重放，不证明重新编码 bit-exact**。
- [P2a 正式报告](../p2a_similarity_20261018_01/README.md)、[聚合](../p2a_similarity_20261018_01/aggregate_summary.json)、[预注册](../../plans/p2a_similarity_20261018.md)：全量完成，冻结 P1.6 向量；S0 1024 Cosine vs S1 BM25 vs S2 k0=60 RRF，完全相同的 DB 内候选文本、Gold、K 和预算；S0 对 P1.6 parity PASS，输入完整性 PASS。P2a **method gain NO-GO**。
- P1 / P1.5 对更早运行的逐题严格重放仍 FAIL（旧 full-run 缺精确候选/排序/向量缓存）。**不能拿 P1.6 的新 PASS 抹去历史 FAIL**。FK / JOIN Role label Gate 仍 NO-GO；没有 GFM GNN、Jev、SQL 生成与 SQL Execution 结果。

## 2. 关键实测结果（百分比，Query macro）

全部 Column 可评 1460 题（Table 1534）：

| 指标 | S0 Cosine | S1 BM25 | S2 RRF |
|---|---:|---:|---:|
| Table Recall@10 | 99.91 | 99.67 | 99.61 |
| Column Recall@5 | **52.84** | 41.32 | 50.80 |
| Column Recall@10 | **68.00** | 55.91 | 66.90 |
| Column Recall@20 | 79.08 | 72.02 | **80.32** |
| Column MRR / MAP | **82.71 / 55.25** | 71.67 / 44.43 | 82.14 / 54.53 |
| Complete Table+Column @ 512 tokens | **35.55** | 21.51 | 29.32 |
| Complete @ 1024 tokens | **56.16** | 32.88 | 46.23 |
| Complete @ 2048 tokens | **79.66** | 62.67 | 77.05 |

预注册的**非饱和子集**：5 DB/706 列可评题，完整 Schema 文本 >2048 tokens：

| 指标 | S0 Cosine | S1 BM25 | S2 RRF |
|---|---:|---:|---:|
| Column R@10 | 58.20 | 47.70 | 58.29 |
| Column R@20 | 69.12 | 61.79 | **71.06** |
| Complete@2048 | **57.93** | 22.80 | 52.55 |

相对 S0，S1 非饱和 Column@10 **-10.50 pp（0/5 DB 正向）**、Complete@2048 **-35.13 pp（0/5）**；S2 Column@10 **+0.09 pp（2/5）**、Complete@2048 **-5.38 pp（1/5）**。两个方法都未通过预先注册的 +2 pp Column 或 +1 pp Complete、至少 3/5 DB 正向的门。Table@10 保护门通过，但该指标在多数库候选表数≤10，本身高度饱和。

### 救回/损坏与不确定性

- 全 1460 题 Column@10：S1 相对 S0 **215 救回 / 660 损坏**，Gold 列元素净减少 734；S2 **273 救回 / 319 损坏**，净减少 48 个 Gold 列元素。救回/损坏按题发生，不等于增减的 Gold 列元素数。
- Complete@2048：S1 **17 救回 / 265 损坏**；S2 **27 救回 / 65 损坏**，净减少 38 道完整覆盖题。
- S2 在非饱和库的 Column@10 分库 delta（pp）：`california_schools -7.88`、`card_games -1.21`、`european_football_2 +1.45`、`formula_1 -2.82`、`thrombosis_prediction +7.82`；Complete@2048：依次 `-5.75, -2.86, +4.92, -12.27, -8.81`。**这不是稳定跨库提升**。
- 数据库聚类 Bootstrap（5 库，探索性）S2 vs S0：非饱和 Column@10 delta CI **[-4.15,+4.52] pp**；Complete@2048 delta CI **[-9.99,-0.14] pp**。5 个 cluster 区间不稳，不能把这一证据解释为独立数据库外泛化。

## 3. 对算法的可归因判断

1. **原始 Dense Cosine 仍是最强冻结基线**，尤其在固定上下文预算的完整 Schema 命中上。不要为了追求 Recall@20 单项而将 S2 选为赢家。
2. **BM25 大量并列分数是潜在机制限制**：1530/1534 题 BM25 出现并列（RRF 777 题）。当前 BM25 tokenizer：casefold，`_` 拆分，`[A-Za-z0-9]+`，丢长度为 1 的 token，无同义词/缩写扩展；这是事实，不意味着已证明「分词是唯一性能问题」。
3. **Top-20 轻微受益说明词法信号可能补充长尾相关列**，但它同时可能把部分错误候选推入前列，占据 512/1024/2048 的预算。RRF 的 +1.24 pp 全体 Column R@20 与负的 Complete@budget 并存；应调查救回/损坏与预算长度分配，而非试遍融合常数。
4. **当前 Schema 文本表示、候选组织和返回子图均未做受控消融**。各项 P1/P2 只覆盖 Table/Column 独立文本检索，没有真正输入 GFM 图推理；不能据此宣称 Query-aware Edge Gate 有效，也不能认定「相似度算法都无效」。
5. **编码器重跑数值稳定性风险**：P1.6 5 题双编码向量非 bit-exact 且逐题行变化，P2a 同缓存比较不受此混杂；下一轮若去掉/替换 descriptions 导致新 Embedding，须记录重复编码变异，固定评价 protocol，并附同文本复现误差控制。

## 4. 下一轮，不要直接做新融合网格

**唯一立即实验**：P2a.5 CPU-only、锁定 P2a 的 S0/S1/S2 分数与逐题排名，分类它们的错误转移与信息来源；同时在独立工作包开展 FK metadata/Join-instance 标签清洗。见[下一轮方案](../../plans/p2a_5_diagnostic_and_schema_representation_20261018.md)。

错误归因关键问题：
- BM25 的同分集中在哪里？含有词面命中的分数与大面积 0 分候选混排比例；长度 1 标识符、复合 snake_case、缩写、数字字段是否显著关联损坏？
- S2 273 rescue/319 damage 是哪类列与哪个分库？为什么 Column@20 救回但预算 complete 退化？统计 Gold 列 rank 从 >10→≤10、≤10→>10，budget 内 Table/Column 数和文本 token 分配。
- 检索难度是否被无关长描述/format/values 噪声、表/列文本优先级与贪心装包放大？Gold 仅做离线评测/分析，不可反注入在线字段说明。
- 标签 74 道不可评、6 个 2048-token 全库可装入 DB 的指标饱和、11 DB 规模都必须在报告中保留，不能静默剔除。

若错误归因支持，**后续可选择 P2b Column Representation 消融**，保持 1024 Qwen3 + Cosine，消融 name/type/description/format/values 的文本构成，控制 token 预算与重复编码误差；但这需要**新协议预注册、新实际模型前向和独立对照**，不属于本轮 P2a 的成功复活。另行修复 FK Gate 才能正式研究 Join-Instance / Edge Gate / Path Scoring。

## 5. 未来研究主线与新颖性边界

- 当前发表潜力最高的是 **SQL-aware Join Instance Identity + Query-conditioned Edge Scoring + Constrained Schema Subgraph**；但前提是可追溯的 FK/路径金标与等价 join 审计。Graph-Link / GRAST-SL / SchemaGraphSQL 已包含图/联通子图/重排序元素，不能以「首次图 Schema Linking」或 Steiner 优化本身宣称新颖。
- 文本表示消融属于重要实验诊断；将 Attribute 节点拆出不一定优于存成字段文本。需先控制输入信息和图结构后才能回答 QuadGraph 四类节点有何独特收益。
- P3 Set EX 尚未有任何新运行成绩；后续 SQL Generator/Selector/Jev 均需固定，以避免性能归因被其他模块掩盖。

## 6. 本次交付和下一次所需证据

报告交付 P2a.5 聚合的错误模式矩阵：column/budget transition、非零 BM25 token match + ties、每 DB rescue/damage、字段描述分层、Top-10 vs Top-20 调整及成本；P0-FK 独立交付 FK 实例有效/不可评原因、复合键与多 FK 可信候选分母、Gold-path/角色可判定性。两条工作均可先 CPU，不调用 LLM、GNN 或 SQL 生成；在各自 Gate 通过前不启动正式新评分/训练。

最后更新依据以本仓库 README/此文档为准。
