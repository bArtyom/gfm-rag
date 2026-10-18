# P2a.5 执行计划：失败模式归因 → 条件式 Schema Representation 消融

> **2026-10-18 制定；状态：仅指导、未运行。** 核心依据：[P2a 全量结果](../reports/p2a_similarity_20261018_01/README.md)、[P2a 复核](../reports/p2a_review_20261018/README.md) 与 [P1.6 新冻结基线](../reports/p1_6_rebaseline_20261018_01/README.md)。
>
> **不要把旧的 P2a NO-GO 改为 PASS；停止在 BIRD dev 上继续试 RRF k0、BM25 k1/b 的盲搜索。**

## A. 当前下一次实际执行任务：P2a.5 Error Transfer Audit（CPU-only）

**目标**：找出 BM25、RRF 导致 Column@10、Complete@2048 救回/损坏的原因，是否有可操作的 Schema 信息与候选构造瓶颈。只分析旧缓存/旧分数、**不生成新的模型分数，也不改变 S0/S1/S2 排名**。

### 输入固定与版本

- 数据：BIRD dev 1534 问题、11 DB；Column-eligible 1460；非饱和子集：5 DB/706 Column-eligible。保留 74 个 Gold 标签不完整问题的排除计数。
- 读取已有私有 P2a `per_question_private.jsonl`、P1.6 向量/manifest（如确实可用）、已冻结节点文本及本地 schema metadata；公开仓库只有匿名聚合、代码、hash。
- 先核验 P2a 的源 commit `689b7f681651f312a1db8850d86b8b7dc4f69fd2`、S0 score digest、输入/缓存 SHA 和全部分母；**如缺少 BM25/RRF 逐候选分数或完整排序，不要凭借聚合 CSV/JSON 虚构 rank**，必要时用冻结 runner 的纯 CPU 方法在同一数据上重构，并验证 S0/S1/S2 原汇总完全一致。
- 确认本次分析代码只读、不修改原报告，结果输出独立新目录，哈希冻结，资源 CPU ≤1800s / RSS≤16 GiB / ≤8 线程；无 GPU、无新增 API/模型下载/依赖升级/SQL 执行。

### A1. 定位 RRF 为何 Recall@20 变好但 Complete 变差

对每个候选方法（S1/S2 相对 S0）产生**匿名聚合**：
- Gold Column rank-transition bins：`1–5,6–10,11–20,21–50,>50` 的进出矩阵；统计每库、706 非饱和与 1460 全体、所有 Gold 元素和按题宏平均，分母口径写清。
- 每题 Column@10 rescue/damage 与 Complete@512/1024/2048 rescue/damage，**特别查 S2 的 273/319 和 27/65**（后者是 2048 所有 1460）。
- 预算选集的 `table_count,column_count,token_used`、Gold 信息占用、被错排高位的节点文本长度 p50/p90，以及 Gold 表列因预算挤占而未加入的题比例。
- 2048-token 预算中 6 库可以塞全 Schema：主分析另报告非饱和 5 DB/706 题，**不得只给子集指标而丢掉全体指标**。

### A2. BM25 严重退化机制的无训练核对

- 候选分数 0/非 0 的比例、每题具有 Query token overlap 的候选数、零分并列区数量、Top-K 边界同分/根据 stable ID 排序影响；报告 **1530/1534** 题 BM25 存在分数并列的原始事实，不把任何同分都等同于「Top-K 恰好受影响」。
- 针对 Gold 列误检和非 Gold 假阳性的**运行时可见特征**分层：字段名/问题短 token（长度1）、snake_case、ID/数字/缩写、Column Description/Values/Format 的有无及 token 长度、是否表/列混合池；**Gold 只能用于离线归因，不进入在线评分**。
- 区分：无词面重叠是结构性 BM25 局限、已有词面重叠却未命中是 scoring/tokenization 问题、Gold 列因预算被挤掉是 context packing 问题。无法裁定就标为 unresolved，不编造原因。
- 对照 11 DB 和 706 非饱和、同库配对差异，检查 `thrombosis_prediction` 的 +7.82 pp Column@10 与 `california_schools` 的 -7.88、`formula_1` -2.82，以及完整覆盖在 `formula_1` -12.27 pp 的差异。不可用单库正例证明普遍增益。

### A3. 建立可执行的结果分歧分类

将差异归为 `lexical_lost, semantic_mismatch, schema_text_noise, budget_packing, ties, gold_ambiguity, unknown` 等**互斥主因 + 可多选证据标签**，明确哪些只能自动推断，哪些需要人工盲审；报告样本量、各 DB 分层和审查一致性，不披露原题/Gold SQL。

### P2a.5 Gate（决定是否有必要继续改表示）

- 基于**实际逐题/完整排名、可核对哈希**，能重构归档 P2a 的 S0/S1/S2 主要结果。
- 生成至少：转移矩阵、BM25 同分/词面零分统计、Top-K 与 Budget 分离的误差类别、706/1460 两种分母的救回损坏；
- 给出至少一个有足够样本的、可通过**运行时可见 Schema 信息**改善的错误类；样本太少或判定不可靠则仅交付失败诊断、不启动新方法。
- 所有诊断不改变旧 P2a scorer；不给历史 NO-GO 增加未经预注册的「成功」解释。

交付：`docs/research/text2sql/reports/p2a_5_error_audit_<date>/` 的 README / 匿名 aggregate / runner/version/hash/test results，逐题与私有数据留本地。

## B. 条件式下一轮：P2b Schema Representation Ablation（先验证文字，不急于增加图层）

只有 P2a.5 支持存在**可改进的字段描述/文本冗余问题**后，再另行冻结 P2b 预注册，保持 1024-D Qwen3、固定 Cosine、相同 questions / Gold / labels / DB、相同 K 和预算；只改变一个 Schema 文本组成项：

| ID | 文本设计 | 核心目的 |
|---|---|---|
| R0 | 现有原文本：Name + Type + Description + Format + Values（已有才用） | 已冻结最佳 Dense 基线 |
| R1 | R0 - Values | Values 是否真实帮助语义 vs 成本 |
| R2 | R0 - Format | 可能冗余的字段格式是否占用预算 |
| R3 | R0 - Description | 业务语义是否必要 |
| R4 | Name + Table Context + Type，去掉额外说明 | 简单短字段基线 |

- 文本模板设计和 token 序列化必须在看结果前冻结。不能让某组使用 Gold SQL 填写 role hint。
- **主指标同时用 type-specific Column@5/10/20 和 combined 完整 Schema@512/1024/2048**；前者评价表示/排序，后者受到节点文本长度改变的共同影响，必须分别呈现信息有效性与压缩效应（报告平均/分位 token 和 Gold-only oracle-fit）。
- **数值稳定性控制**：P1.6 Smoke 两次重新编码的 query/node 向量存在最大绝对差 0.002555/0.003764 且部分结果变动。R0 可优先复用原缓存，但必须另做至少一个同文本再编码控制，报告随机/数值变动尺度与 rank 边界敏感性；不能把单次微小差异全部归因于删掉某一字段。增加重复次数时预先固定预算，不允许结果不好再重复直到有利。
- 每组使用同一 encoder revision、设备、batch、query instruction、归一化、稳定 tie-break；不要借 P2b 偷换到更大的 Embedding 模型或修改 GNN 主干。
- 预先冻结非劣标准、错误子集与独立 DB 验证策略；BIRD dev 历史用得多，必须明确探索性质。
- **不要在同一次 P2b 把 Attribute 独立变节点、Document/Community 加到图里**；那是下一轮额外控制图结构后的实验，不然无法分辨文本信息增加与图传播的效应。

若 P2a.5 显示主要是预算装包而非表示，则将后续探索改为**同一冻结 Cosine 排名下的简单、可解释 token-budget packing 基线**（按长度/固定表列配额），先不训练 GNN。必须预注册方法，并且保证所需表与列在输出 Schema 时一致。

## C. 并行但独立的图结构质量任务：FK / Join Instance Gate 修复

P1.5 有原始 SQLite FK 103、有效 100、3 无效；BIRD JSON vs SQLite 有 5+2 差异；Gold 显式 JOIN ON 1428 条中唯一匹配 1199、未匹配 204、歧义 25；同表对多 FK 候选问题 197。**这些统计不等于现成的 197 个可评业务角色分类样本。**

- 对 `3 invalid FK`、`5 JSON-only`、`2 SQLite-only` 差异逐库确认 `source,target,ordered_column_pairs`、隐式主键、复合 FK；稳定 JoinInstance ID，保存来源和缺失/歧义标签。
- 将 204 个未匹配 JOIN 分类为合法非 FK、别名解析失效、元数据不全、其他；25 个歧义与 197 同表多 FK 候选按 **uniquely-resolvable / multiple-valid / unresolvable** 记录。
- 先定义一个透明的、**不依赖 Gold 注入运行时表示**的可评子集，报告全部到子集的筛选流失，若高可信局部子集的条件可成立，可注册 G0（原始 GFM 的 Schema graph node retrieval）探索；**全局 FK Gate 仍 NO-GO 时不可对全 BIRD 称 JOIN Role/Path 提升**。
- 查询感知逐实例 Edge Gate、SQL-aware Path Loss 与完整 QuadGraph 的四层消融仍须建立真实可评路径标签之后才做。
- Graph-Link / SchemaGraphSQL / GRAST-SL 已有相关子图选择思路，创新必须通过相同 Schema 信息/相同预算的公平对照证明。

## D. 近期禁止的动作

- BM25 / RRF 的 k0/k1/b 网格搜索，靠开发集挑赢家；对归一化向量重复测试 Dot 与 Cosine；
- 直接使用 GNN/GFM checkpoint 并宣称 P2a 已验证图推理；
- 未审计 FK 的情况下大规模训练 JOIN scorer / 构造 Gold-hard negatives；
- 单独报告大于表数的 Table@10 或可放下整个 Schema 的 2048 budget 完整覆盖；
- 仅看 RRF R@20 +1.24 pp 就说整体优于 Cosine；
- 在 Text Schema 表示变化又重编码不稳定时，对 ~0.1pp 的小增益做确定性结论；
- 将 P1.6 Full Gate PASS 错当作 P1 / P1.5 历史严格复现已经通过。

## E. 下次需要的唯一回报

**先提交 P2a.5 错误归因报告与 FK Gate 清洗进度，不要先跑新 GNN 或 RRF 调参。** 提交中明确区分「已测结果、审计发现、待验证新假设」，附代码/输入/缓存 hash、实际成本和本仓库提交 ID，下一次再依据错误类型决定是否进入 P2b 表示消融或 token-budget 子图选择。
