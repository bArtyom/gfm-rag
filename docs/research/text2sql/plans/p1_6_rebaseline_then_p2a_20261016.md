# P1.6 → P2a 执行指导：重建可信基线后比较相似度（2026-10-16）

> **状态：研究决策/预注册建议，未运行。** 本文件基于 [P1.5 结果复核](../reports/p1_5_review_20261016/README.md) 和 [原始 P1.5](../reports/p1_5_diagnosis_20261016/README.md)。**旧 P1 与 P1.5 的严格复现 FAIL、FK Gate FAIL 均保持，不事后改写。**

## 1. 最关键的调整

旧方案要求 P1.5 必须对历史 P1 逐题 100% 相同才能运行 P2a。但旧 P1 丢失了**原始候选的精确顺序/哈希序列化规则及 Embedding/Rank 缓存**，即使同模型同数据也可能永远不能从现有证据复原“逐字节相同”的历史排序。当前既有 91 项细微差异也不能证明本轮向量检索不可重复。

因此分清：
- **历史复现判断**：FAIL，不得改变；
- **新对照试验是否可靠**：必须通过全新的**冻结输入/模型/排序+同运行基线**标准，方可开始与老报告结果*不可直接逐题等同*的 P2a。新协议必须在新 P2a 结果可见前冻结。

这是一项独立后续实验的 go/no-go，**不是放宽 P1.5 的历史验收**。

## 2. P1.6（只定位旧差异并冻结新基线，先执行）

### 2.1 最低成本溯源，首先用 CPU

1. 对照旧 P1 运行脚本（已归档：`docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/run_gfmrag_p1.py`）、公共输入构造 `gfmrag_p1_common.py` 与现用 `scripts/text2sql/run_p1_5_diagnostics.py`，逐项核查**候选 ID/排序、score dtype、矩阵乘法、归一化顺序、stable tie break、query 拼接、新旧预处理路径**。把每项差异登记为 confirmed/suspected/unresolved。
2. 本地历史 per-question hit 与本轮保留的逐题 scores 若可用，对 91 项不一致做配对表：涉及 DB、候选类型、是否 score tie/近邻差、Top-K 边界间隔。只展示**聚合分类**到公共 GitHub，原题/Gold/逐题分数不上传。
3. 尝试恢复旧 candidate text hash 的确切「排序与序列化」规则；不允许修改 frozen input 或源文件来凑 hash。不依赖未知模型行为猜测结果。
4. 如果旧有序向量/排名确实不可恢复，在报告中明确写**历史严格复现原因未定**，不要无限试新版维度或改文字后假称通过。

### 2.2 冻结新 1024 基线

1. 从本轮 P1.5 *同一版本*的 Qwen3-Embedding-0.6B、模型 revision/文件清单、query instruction、type-first 873 节点文本 hash、数据库/题目/Gold 标签指纹出发，记录 **按序的 node IDs + text hashes**，不只是拼接后的一个 hash。
2. 尽可能复用本地现有 **1024 向量**：对完全相同的向量与代码**两次运行 scorer**，要求所有有资格题目的逐题 Top-K、预算选择、Recall、完整覆盖 bit-exact；不同线程数/候选顺序变化时必须有明确的稳定 tie-break（分数相同按 stable node ID），并说明是否只对 tie 施加该规则。
3. **如果要重新编码**，只允许一次冻结参数的 1024 前向，另跑一次同模型的一致性 smoke 评估 encoder 数值稳定性；明确记录浮点最大误差和 Top-K 边界分差，不能要求浮点向量 bit-exact 才能视为数值稳定，但要求**在冻结得分缓存上排序完全确定**。
4. 重新验算 1024 基线的 Column R@5/10/20、Gold rank、Table R@5/10、512/1024/2048 预算与两类 Top-K 分母；结果数值与 P1.5 不一致时应解释，而不是选择性删除题目。
5. 选择同运行比较原则：P2a **S0 Cosine 必须与 S1 BM25、S2 RRF 在同一个 frozen input + labels + scoring pipeline 中计算**，三者完全共享候选元素集合和预算。这种配对检验与历史严格复现分开报告。

**P1.6 Gate**：冻结输入可重建；1024 baseline 在同一向量缓存上二次排序逐题完全一致；公开的代码/hash/聚合结果可以核验；边界 tie/数值稳定性有记录；全部指标分母一致。否则停止 P2a 并只提交失败诊断。无需通过旧 P1 逐题 100% matching 才能使新协议成立；但必须显式标记原始 FAIL 和新基线与旧 P1 不可逐题直接相当。

资源：先 CPU+现存缓存；如必须重算，固定一次 1024 vLLM 前向，预算参照 P1.5 的 GPU≤900秒、CPU≤1800秒、线程≤8、RSS≤16GiB；**不训练 GNN、无新模型或维度、无 API、无 SQL 执行、无依赖升级**。

## 3. P2a：仅在 P1.6 Gate 通过后（一次冻结的 1024 表列检索对照）

### 3.1 信息对齐的三个 Baselines

| 方法 | 具体定义 | 额外特征/模型 |
|---|---|---|
| S0 原样 Dense | 1024 Qwen3，L2+精确 Cosine，候选使用已冻结的表/列原文 | 无 |
| S1 BM25 | **同一个 table/column 候选文本**；冻结大小写、snake_case 拆分、数字与符号、英文/非英文 tokenizer | 无 |
| S2 RRF | S0+S1 排名融合，先预注册 `k0=60`，全候选宇宙相同；stable node ID 决定 ties | 无 |

- BM25 的长度归一化/分词等参数采用统一默认常数并记录版本，不在 BIRD dev 测试题上进行多轮微调；RRF=1/(k0+rank_dense)+1/(k0+rank_bm25)。因所有候选每个 db 均能穷举，**计算两组全排序**，避免缺失 rank 的特殊规则。
- 尽量先做 CPU 同分数缓存的**排序/评价**；无需每种 scorer 再跑一遍大模型。
- 主要对象为 **Column**；Table 作为保护性指标并报告 Table@5 在候选较多的库表现。不要因 Table@10 的天然饱和选择获胜者。
- **禁止在此次 P2a 改 Schema 图拓扑、添加 FK/role/node/edge 文本、引入训练式重排序、生成 SQL 或改变预算**。
- 分析金标困难特征仅做解释；运行时合法特征只有 Query、Table/Column 候选文本和已冻结元数据。

### 3.2 必报评价与分层

1. **全体 1,460 列可评题**（注意 74 道因标签不完整未纳入）；Column R@5/10/20，Column P@5/10/20，MRR、MAP、micro 与题宏/库宏。
2. **非饱和重要子集 706 题**（2048-token 无法容纳全库 Schema 的 5 DB），再测 512/1024/2048 三档 Token Budget 的 Complete Schema@Budget、Precision@Budget、Gold elements per 1000 tokens；**全体 1,460 仍需同时汇报**。
3. Table 类型结果：区分候选表数≤K 的 trivial full recall；不要以整体 Table@10 为主要目标。
4. 数据库级配对 rescue/damage 表、分库宏平均、bootstrap by DB（11 DB，区间不稳时明确探索性），候选返回节点数、token、实际计算成本。
5. 单独报告 `name_token_overlap`、`has_values`、列名缩写/描述长度等错误类型中各方法救回情况；这些特征是**错误归因分层**，不是为正确候选注入 Gold 的在线特征。

### 3.3 预设 P2a Go/No-go（计划阈值，不是实验结果）

拟采用此前 P1.5 计划中的固定目标：
- 在 706 题非饱和分层中，相对 S0 **Column Recall@10 提升≥2.0 pp 或 Complete Schema@同预算提升≥1.0 pp**；
- 全 1,460 题的 Column 主要指标不出现明显负迁移，Table R@10 下降不超过 1.0 pp（保护门，但 Table@10 高度饱和，应同时观察 Table@5）；
- 至少在多个不同数据库上具有一致方向，报告 paired rescue vs damage、DB cluster CI、所有尝试过的融合设置与计算开销。
- **BIRD dev 已用于反复开发，以上只能作“继续探索的工程门”，不能用来判定独立泛化成功。** 在独立数据库验证前，不声称论文级提升。
- S1、S2 是既有算法，不是核心方法创新。

### 3.4 P2a 之后：不是立即训练 GNN

P2a 如果只改善 name overlap 类失误，下一步应把 lex/dense 融合用于更可靠的 query seeds；再与原 `GFMRetriever.prepare_input_for_graph_retriever` Top-1 EL 比较。
若错误显示结构角色占多数，**仅在 FK Gate 通过**后建 Join Instance，考虑可解释、轻量的 relation scorer → Query-aware Edge Gate → Constrained Path 机制消融。
若 S2 无收益，记录负结果，优先字段文本长度/描述噪声审计，不直接跳到复杂 GNN。

## 4. 独立 FK/Role 数据质量修复线（CPU，可并行，但不堵列检索）

P1.5 的静态诊断显示 SQLite FK 103 原始实例/100 有效、JSON 102 pairs/差异 5+2；Gold 显式 JOIN ON 1,428 条中 1,199 可唯一匹配，204 无匹配、25 歧义；只有 932/1140 个有显式 ON 的问题其全部 JOIN 条件可唯一映射。

1. 先就 3 个无效 SQLite 约束和 5/2 JSON–SQLite 元数据差异，逐库核对类型、复合键、隐式父表 PK、大小写、别名以及字段对的映射，公开仅匿名计数/类别。
2. 将 204 个 ON 非匹配分为**合法非 FK 连接 /解析或 alias 错误 / 缺失的元数据 /不可裁定**；不能因非 FK JOIN 而认为参考 SQL 非法。
3. 25 个歧义 ON 和 197 题同表对多 FK 候选须标记**可评 Gold 角色 / 多金标 / 不可评**，避免将 SQL 参考 join 条件直接视为唯一的语义路径。
4. 只在保留 Join Instance 稳定 ID、复合键原子性、候选端点都在图中、并有可靠 Gold role/path 子集时，开展硬负例/路径评分消融；同时公开**总题数、可评子集分母、不可覆盖率和筛选偏差**。
5. **FK Gate 继续 NO-GO**；这项完成前不向用户声称 JOIN Edge/Role/Path 的任何实测性能。

## 5. 提交规范和下一轮需返回的结果

预期 `docs/research/text2sql/reports/p1_6_rebaseline_202610xx/` 包含审计摘要、94? 不——精确 **91** 项的分类、旧文本顺序可恢复性、基线哈希（有序 IDs+Text）、排序稳定性、代码/环境、P1.6 Gate、真实成本。公开仓库不上传逐题用户 Query、Gold SQL、候选向量或数据库。

只有 P1.6 通过后，另建 `reports/p2a_similarity_YYYYMMDD/`，冻结 S0/S1/S2 的比较和分库/预算指标。后续继续只向 [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag) 提交指导。

**执行者下一次应先回传 P1.6 差异定位与新基线结果，不需要额外试维度、不需要训练图模型。**
