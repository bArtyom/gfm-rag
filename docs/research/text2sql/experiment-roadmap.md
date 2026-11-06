# 2026-11-07 bounded candidate–SQL identity diagnosis

The prior SQL-used mapping Smoke stopped at 0/5 candidate coverage after successful SQL and qualified-column parsing. Its aggregate did not locate whether the selected table pair was absent from explicit SQL joins, the frozen FK candidate set lacked the SQL-used column identity, or the candidate-filtered matcher disagreed with direct identity comparison. One separate CPU-only diagnostic is preregistered at `docs/research/text2sql/plans/p0_fk_candidate_sql_identity_alignment_20261107.md`. It uses the same frozen 60 pairs, no rankings or model-review outputs, and reports anonymous coverage/error categories only. It does not reopen model ranking. Smoke and the single Full pass are bounded by the registered technical gates; no retry, parser tuning, or sample expansion is allowed.

# 阶段实验方案：Dimension → Similarity → Role/Path → Text2SQL

> **研究指导 v1（2026-10-14 制订；2026-10-16 迁入主仓库；原文保留，后续进展以状态更新为准）**。任务是找出“表示维度 vs 评分方法 vs 业务 JOIN 角色”各自可归因的影响；先使用最小可复现检索实验，再决定是否接入 GFM/GNN。

> **2026-10-16 状态更新（优先于本 v1 原始执行顺序）**：历史 P1 表/列维度筛查已完成并复核，所有低维严格 NO-GO；FK/Join Role 尚未评测。当前唯一下一步为 [P1.5 错误/预算诊断与 P0-FK 审计](plans/p1_5_diagnostics_and_p2a_20261016.md)，P1.5 Gate 通过后才做 P2a 的 1024 Cosine/BM25/RRF。见 [P1 结果复核](reports/p1_review_20261016/README.md)。**下文 v1 描述是原始计划留档，不代表当前阶段仍未有任何历史 P1 实验。**

> **2026-11-05 最新状态（优先于上述历史顺序）**：canonical P1.5 crosswalk 已完成，103 条原始 SQLite FK 中过滤 3 条无效实例后，P1.5 仍为 970/197；packet-28 为 1043/176。逐题差异是候选定义差异，不能当作业务 Role 标签。双人盲审包 Smoke/Full 已通过：54个分层名额去重为49题、51个问题×表对，完整覆盖1,534个问题键；结果只支持材料生成流程可行，人工审阅与可信标签仍为0。当前唯一下一步是等待两名真实审阅者独立提交；在此之前不启动 Role Accuracy、query-conditioned Role 训练或真实 JOIN 方法主实验。见 [canonical crosswalk](reports/p0_fk_canonical_crosswalk_20261105_01/README.md)、[预注册](plans/p0_fk_disagreement_blind_review_20261105.md)与[运行报告](reports/p0_fk_disagreement_blind_review_20261105_01/README.md)。

> **2026-11-05 非方法结构审计补充**：在人工标签等待期间，可执行一次独立 CPU-only BIRD dev FK 图 hop-depth profile，判断该开发集是否包含足够、跨数据库分布的 h≥3 结构样本。此审计不输出题目级/数据库级数据、不验证业务路径正确性，也不放宽前述 Role 标签门。详见 [P0-BIRD-FK Hop Profile 计划](plans/p0_bird_fk_hop_profile_20261105.md)。
>
> **2026-11-05 实施更正与停止决定**：hop profile v1 曾使用全局 CTE 名称过滤，可能跨作用域误删同名基础表；v1 原报告/产物保留。v2 使用 SQLGlot scope-aware `selected_sources` 解析器，Smoke/Full 通过且匿名聚合与 v1 相同：36/1,534 题连通 `h≥3`、覆盖5库，77题声明FK图不连通。与 SchemaScope 报告的约22%差异仍未解释；按预注册规则停止更多切片或解析器扫描，暂不在 BIRD dev 扩展高跳数方法。见 [v1报告](reports/p0_bird_fk_hop_profile_20261105_01/README.md)、[v2更正计划](plans/p0_bird_fk_hop_profile_v2_correction_20261105.md)和[v2结果](reports/p0_bird_fk_hop_profile_20261105_02/README.md)。双人可信 Role 标签仍是任何真实 FK mapping 方法评估的前置。

## 0. 预注册研究问题及假设

- H1：在**不改变编码模型、文本模板、Schema 图和 Cosine**时，某个低于 1024 的 Embedding 维度能够以明显更低的向量索引/计算成本维持 Table/Column/FK 检索，困难 JOIN 角色子集也不显著退化。**待验证，不默认 512 最优。**
- H2：同一查询和相同候选预算下，RRF 能相对纯 Cosine 减少短列名、缩写的检索错误。已有融合方法，只当 baseline。
- H3：显式 Join-Instance 的 Role-aware + Path-level 评分在相同可见信息下优于节点检索、关系文本 Cosine 及 RRF，尤其是同一对表有两个合法 FK 的硬负例。
- H4：改善 JOIN 角色和完整子图检索能够在冻结的 SQL 生成/选择器下改善 Set EX 或产生精度—成本 Pareto 优势；不保证排序代理指标提升必然转化为 SQL。

## P0：零训练、零模型 API 的数据审计（唯一立即执行）

### P0.1 固定实验边界

- 首选 **BIRD dev 的 1,534 道问题**作历史可对照的开发/诊断集；它已经反复用于历史探索，**不能再被描述为独立测试集**。
- 冻结数据库列表/版本、DDL/注释、外键与复合键、查询 ID、数据许可/访问路径、查询原文、Schema 文本序列化、下游模型及调用预算。
- 如已有独立数据库级留出集，预先登记；没有就先完成开发集研究，最终泛化结论暂不成立。不得拆同一个数据库的问题到 train/test 后宣称 cross-database generalization。
- 实验只改变 Embedding/Scorer；P1 不引入新 Attribute/Document/Community 节点，不更改 PK/FK、图拓扑。
- P0 构建两个文本版本作为**独立可选结构因子**，首轮固定 A：A=表/列名+已有描述+必要上下文；B=A+可追溯的 FK 业务角色描述。不能在 P1 维度实验中切换 A/B。

### P0.2 标签与错误审计

对每道题自动从可解析 SQL 提取：
- Gold Table/Column（排除 SQL AST 解析失败，并记录失败分母）；
- FK / Join Condition：保留外键实例身份、复合键的多列条件；非声明式 JOIN 的派生、无 FK JOIN 另标；
- Role-hard：同一对表间有多种合法关系，或有同名/同义的 billing/shipping、created_by/approved_by、订单额/实付额候选；只用图结构确定可比较候选，问题要求的 gold role 作为**评测标签**并开展盲审。
- 允许多个等价 Gold Schema/Path 标签或设为“不可唯一裁定”；禁止把所有 reference SQL 所用路径一律视为唯一业务正确路径。
- 报告可解析覆盖率、无 FK/多跳/桥表/复合键数量、困难角色样本数量、歧义率与库级分布。人工审核至少双人小样本并记录分歧；样本不足就只做探索性质结论。

### P0.3 编码健康检查

Qwen3-Embedding-0.6B、相同模型 revision、相同 Query Instruction、相同 DDL 文本、相同 vLLM 后端、固定随机种子/硬件与批量大小。测输出 d、范数、重复编码稳定性、缓存散列、零向量和 NaN。检索层显式 L2 后 Cosine。固定精确穷举 Top-K，首轮不用 ANN 索引，以免索引近似误差影响结论。

**P0 Gate：** 数据/标注/文本来源可追溯，至少有可评估的 Join-Instance 正/负候选；若不能可靠定义 Gold FK/role，则 P1 只报告表/列检索，不报告“JOIN Role Accuracy”。

## P1：Embedding 维度纯消融

| ID | model | dim | score | 图结构/模板 |
|---|---|---:|---|---|
| E128 | Qwen3-Embedding-0.6B | 128 | L2+Cosine | 固定 |
| E256 | 同上 | 256 | L2+Cosine | 固定 |
| E512 | 同上 | 512 | L2+Cosine | 固定 |
| E768 | 同上 | 768 | L2+Cosine | 固定 |
| E1024 | 同上 | 1024 | L2+Cosine | 固定基准 |

按 Query、Node、Relation/Join-Instance 分别编码，同一端到端 Query instruction 与 passage 格式；必要时分别列出 Table/Column/Edge 三类索引。各维度可调用模型的 Matryoshka 截断机制生成，不能静默改用不同模型，或在仅一种维度下使用额外语义描述。

**主要评价：** Table Recall@K、Column Recall@K、Join-Instance Recall@K、Complete Required Schema Coverage@Budget、同表多角色选择准确率（限定经审计、可唯一裁定子集）。辅以 MRR/NDCG、每数据库宏平均、错误题交集、向量内存（float32 原始大小 N×d×4）、编码/检索时间（均值/中位/p95）以及索引实际内存。

**K / budget：** 预先给出至少两个 K（建议 5、10，且分别按元素类型记录）；另以**相同 Schema token 预算**评估，避免高维方案返回更长文本占用更多输入而隐形改变条件。对于所需元素数超过 K 的题要标注不可达而不是归为随机失败。

**判断原则：** 不只看整体 Table Recall；如果 512 在多 FK 角色 Hard Set 退化明显，即使全局 Column Recall 接近也不能宣布成功。数据集多轮选择最优维度时必须用独立 held-out db 验证。

**P1 Gate：** 先写清允许的召回非劣界与性能/内存目标，再查看 P1 数据。可用的*预设示例*：对 1024 的完整 Schema Recall@Budget 差不超过 -1 个百分点、向量存储节省至少 45%，且角色困难子集无明显不可接受损失；需报告数据库聚类置信区间，不能事后将阈值按结果改写。若都不满足，保留 1024 进入 P2。

## P2：评分方式消融（固定图、同信息、同候选池）

建议始终包含 **1024 基线** 与 P1 在冻结协议下选择的一种候选维度；不要事后挑选多个在开发集上表现好的维度却只报告最好结果。

| ID | Score | 是否需训练 | 作用 |
|---|---|---|---|
| S0 | L2 + Cosine | 否 | 稠密语义基线 |
| S1 | BM25 | 否 | 列名、缩写、业务词词面匹配 |
| S2 | Cosine + BM25 的 RRF | 否 | 标准稠密/稀疏融合基线 |
| S3 | Relation-description Cosine | 否 | **同信息**的边语义基线 |
| S4 | Role-sensitive / Path-aware Score | 初版否 | 我们提出的受约束排序尝试 |

RRF 例子：

$$
S_{\mathrm{RRF}}(x,q)=\sum_{m\in\{\mathrm{dense},\mathrm{bm25}\}}\frac{1}{k_0+\operatorname{rank}_m(x\mid q)}
$$

设定 $k_0$ 的预注册默认值，并在验证集一次确定，不在测试集调参。RRF 是既有方法，不主张新颖性。

### P2.1 Join Instance 表达

固定每条 FK 的稳定键：db_id + constraint_id + ordered column pairs；无约束 ID 则用确定性序列化 hash。端点列集合需保持完整：复合 FK 不能拆成彼此独立可选边。Join Instance 表达至少包含：

- source/target table 与有序 column pairs；
- FK 实际结构、可信 description、可用的 role_hint、文档来源 ID；
- 如有基数/唯一性/Nullable，可作证据，但不能编造；
- join semantic description 模板固定（字段名别名、business role、来源），**对 S3/S4 使用同一原始信息**；避免仅给我们的方法额外正确提示。

### P2.2 Role/Path 得分（待实验的设计，不是论文公式）

先由真实 FK 图生成可达候选 Join Path $P$，将 SQL 合法性作为硬约束。然后排序：

$$
S(P,q)=\alpha S_{\rm rel}(P,q)+\beta S_{\rm cov}(P,q)+\gamma S_{\rm lex}(P,q)-\delta C(P)
$$

- $S_{\rm rel}$：问题与路径内 JOIN 实例角色描述语义得分（聚合方式 max/mean 或覆盖加权作为预注册消融）。
- $S_{\rm cov}$：路径覆盖已经被检索定位的必需表/列/业务约束的比例；不得直接用 Gold 来计算线上特征。
- $S_{\rm lex}$：名称、注释、角色同义词的词面证据，来源必须可引用。
- $C(P)$：路径复杂度、冗余桥表、非必要长度的代价；不能盲目偏好短路径而牺牲必要多跳。
- $\alpha,\beta,\gamma,\delta$ 只在训练/验证数据库上设定，并保存版本与选择理由。**至少与不训练的等权、单项和仅 Relation Cosine 比较**，防止“多项融合”掩盖真实收益。

候选集缺少真实 FK、SQL 涉及非 FK join、或者多种关系等价不能判定时：标注不可覆盖/abstain 并回退，禁止为了提高覆盖率捏造 FK。

### P2.3 不可缺少的对照

1. **同图、同 role 文本、仅改 scoring**：区分评分增益。
2. **S4 去 role hint**：衡量业务角色语义贡献。
3. **S4 去 path term**：衡量连通路径约束增益。
4. **S3/S4 同候选 FK 对/同预算**：避免方法因召回候选更多而显得更好。
5. **复杂情况分层**：同表多 FK、复合 FK、桥表、多跳、无 FK、短列名/别名、中文/英文业务同义。
6. **错误配对分析**：每个新方法救回/损坏题数，至少提供匿名实例类型和源 hash，而不只报告均分。

**P2 Gate：** 在冻结的数据上角色判别或整条路径 Recall 出现可信改进，且不是从额外可见信息、不同候选数、不同数据拆分获得；独立数据库留出仍有一致信号，否则不扩展到复杂学习式评分。

## P3：端到端 Text2SQL

只有 P1/P2 显示出可归因检索收益后开展。固定：
- SQL Generator / 修复器 / Selector、prompt 模板、生成 SQL 候选数、随机种子、解码设置、证据卡与预算；
- 同一数据库环境、超时、执行一致性路由；
- 如果使用 Jev，保持原逻辑和调用策略不变，**不得将 Schema 召回收益说成 Jev 本身收益**。

按每题固定候选 Schema budget 注入检索结果；列出不同 Schema 输入导致的候选 SQL 池变化。评价：
- **主要：Set Execution Accuracy (EX)**；
- 辅助：Bag EX、SQL Candidate-Pool Oracle、Table/Column/FK/Role 诊断召回；
- 效率：向量索引大小、编码时间、检索 p95、完整增量逻辑 token、实际 USD 成本/延迟、失败重试率；
- 统计：同库配对结果、救回 vs 损坏、按数据库聚类 CI、与 baseline 的显著性/不确定性。BIRD dev 仅开发诊断，不推断跨库泛化。

**P3 Gate：** 独立数据库评估支持稳定 Set EX / 质量—成本 Pareto 收益，且角色/路径增益可以通过消融归因。若检索代理指标改善而 EX 不变，记录负结果，避免过度声称。

## P4：可选 GFM 适配（不要提前启动）

若需要用 G-reasoner pretrained GFM 来验证结构推理：
- 1024 维原输入 + 原始 checkpoint 先跑可复现基线；
- 若低维，明确比较：只训练输入适配投影 / 冻结主干微调投影 / 相同训练预算重训投影或全部模型；
- 每组记录 trainable params、训练数据/标签、训练 tokens、GPU-hour，且相同 holdout；
- 评价的是**适配过的 GFM**，不能称“只更换 Embedding 维度、原 GFM 不变”；
- 如 P1–P3 已有充分结论，可不执行 P4。

## 风险及停止标准

| 风险 | 预防或止损 |
|---|---|
| 维度低，JOIN role 严重混淆 | 保留 1024；先检查 role 文本质量，再研究 scoring |
| 关系分数只复制 Cosine | 强制 S3、S4 同信息同候选；跑去 role/path 消融 |
| Gold JOIN 唯一性假设错误 | 多金标/人工复核；不可裁定剔除角色准确率分母 |
| 数据泄漏 | role hint 只来自运行时 DDL/注释/可信文档；Gold 严格仅用于评测 |
| 过拟合 BIRD dev | 数据库级独立 held-out；明确报告多次开发选择 |
| GNN 维度不兼容 | P1/P2 不加载 GFM；P4 单独设计 |
| 增加模型成本却不提升下游 | 保留廉价 Cosine/BM25/RRF baseline，按照 Pareto 优势 Go/No-go |

## 下一步唯一任务（对实验执行者）

完成 P0 的冻结清单与误差标签可用性报告：数据目录/版本 hash、图边类型与复合 FK 统计、gold label 覆盖、Hard Role Set 的严格定义、编码器范数健康检查以及比较协议。**没有 P0 审计报告，不得开始 P1 “挑最优维度”。**

## 执行状态补充：P2d.2 失败归因后的有界 SQL Pilot（2026-11-05）

本文件前文是 2026-10-14 制定的历史路线图；以下只记录后续实际执行指导，不回写旧实验门槛。

- P2d.2 对已封存的28条不可执行预测做了静态/只读归因：10条解析/结构错误、13条限定符或作用域错配、4条不存在标识符、1条误用可见字段；旧样本里没有“失败字段不在 prompt”的案例。
- 因此，不追加旧30题上的检索打包扫描。P2d.3 已按方案完成：66题 Full、5题独立 Smoke，均与旧 P2d 准备样本不重叠；同一初始 SQL 比较 A0 无修复、A1 完整 R0 Schema 一次修复、A2 只见 V00 检索上下文并由 SQLite authorizer 拒绝未检索表列。
- 最终 Set EX 为 A0 18/66（27.27%）、A1 20/66（30.30%）、A2 17/66（25.76%）。A2−A0 为−1.52pp，未达到 +5pp 成功门；A2 阻止了8个越界字段提案，0个越界读取被接受。实验判为 `NO_GO_OR_INCONCLUSIVE`，不换 seed、不扩样。完整数据与边界见[P2d.3 报告](reports/p2d3_context_bounded_repair_20261105_01/README.md)。
- 此 Pilot 检验本地 pipeline 效用与信息范围，不作为通用修复算法的新颖性主张；近期 Post-SQLFix、DSR-SQL、SCOPE-SQL 等已覆盖相近方法类别。本分支停止新增 SQL 修复实验。
- P2d.3不评真实FK Role、JOIN Path角色或Jev；可信双人Role标签仍为0，相关准确率和训练实验继续等候人工审阅门。
- 2026-11-06 对 P2d.3 被拒候选的只读反事实审计发现 8 个修复候选中 2 个完整 Schema 下可执行且正确，但不改变 66 题系统分数；按新近 Post-SQLFix / DSR-SQL 近邻和本项目既定停止规则，不新增通用 SQL 修复实验。下一项唯一 GFM 方法试验仍是冻结 checkpoint 的 FK 映射排序 Pilot，必须先通过两位真实审阅者的标签与样本门。当前标签数为 0，未启动模型运行；详见[2026-11-06 路线更新](plans/p0_fk_mapping_rank_literature_update_20261106.md#6-p2d3-反事实审计后的路线更新-2026-11-06)。
- 2026-11-06 前沿复核另核对了 Rethinking Schema Linking、REaR、ARCS 与 FLINT：一般双向检索和 joinable 表扩展已有直接近邻；ARCS 多解释标注不能直接替代 BIRD 的 FK mapping 双人接受标签。未发现可绕开现有人工门且能回答同一科学问题的新分支，故唯一保留项仍是受限的冻结 G-reasoner Accepted@1 Pilot；实验尚未运行。详见[前沿复核](plans/p0_fk_mapping_rank_frontier_check_20261106.md)。

### 2026-11-06 后续执行状态：映射级盲审材料已准备

候选容量审计从 1,127 个可解析的 JOIN-ON 问题中找到 176 个多 mapping 问题×表对，涉及 4 个数据库。独立 pair-level 材料准备已通过 Smoke（5题）和 Full（60个问题×表对、135个 mapping 候选）；A/B 候选集合一致，展示顺序已打乱。材料只用于人工判断，不产生 Role 标签或模型成绩，题目和回复表留在本地私有目录。详情见[容量审计报告](reports/p0_fk_mapping_candidate_capacity_20261106_01/README.md)、[盲审材料报告](reports/p0_fk_mapping_pair_level_blind_review_20261106_01/README.md)。

**下一项模型实验仍是同一项受限迁移/证伪 Pilot**：在两位审阅者一致接受的 mapping 集合上，比较冻结 G-reasoner 与 Dense Cosine 的 Accepted@1；BM25 和 query-independent 结构排序只作次级控制。由于表对来自参考 JOIN，这只测给定表对后的 FK mapping 排序，不测端到端 JOIN 发现、SQL EX 或跨库泛化。启动前必须满足：两位审阅者的决定与接受 mapping 集合完全一致、双方置信度均至少为 2；排除问题级 Smoke 后，至少 30 个可裁定单元、20 个结构可区分单元、覆盖至少 3 个数据库。若样本门通过，成功筛选门为 Accepted@1 比 Dense 高至少 5 个百分点、净救回至少 4 个单元，且至少两个各自有不少于 5 个可区分单元的数据库净救回方向为正；满足后仅升级为独立复现候选。未通过标签或模型门则停止该方向。当前可信标签仍为 0，故不运行模型、SQL 或 GPU，也不让模型代标。正式执行仍须另行注册并完成当轮资源预检。

### 2026-11-06 新增用户选择的模型审阅代理轨道

用户明确选择本地模型代替人类提供初始审阅。独立 `exploratory` 实验 `p0_fk_mapping_model_review_proxy_20261106_01` 已完成：Smoke_001 未通过（Qwen2.5-Coder 5/5，Qwen3-4B 3/5）；一次非空候选提示澄清后，Smoke_002 两模型均 5/5。Full 有 28 个双方高置信、决定和接受集合完全一致的可裁定单元，低于 30 个先决门；23 个可区分单元覆盖4库。结论为 `STOP_INSUFFICIENT_MODEL_PROXY_LABELS`，不跑排序、不扩样。模型标签不覆盖人工 CSV、不构成可信人工标签，也不解锁原 Accepted@1 主 Pilot。详见[模型审阅代理实验计划](plans/p0_fk_mapping_model_review_proxy_20261106.md)与[报告](reports/p0_fk_mapping_model_review_proxy_20261106_01/README.md)。

### 2026-11-06 第三模型审阅结果与独立探索排序诊断

用户明确选择由模型进行审阅后，按已单独预注册方案运行 Gemma 4 E4B-it。vLLM GPU 初始化受 PyTorch CUDA 13 / 驱动 CUDA 12.4 不兼容阻断；没有生成 token，也没有修改驱动或依赖。CPU 恢复 Smoke 5/5、Full 60/60。三模型高置信精确多数为56个，其中41个可区分、覆盖4库。按稳定问题哈希选出5题 Smoke 并把其问题级样本全部排除后，Full 保留51个可裁定、38个可区分、覆盖4库，通过独立 exploratory 排序诊断的模型代理数据门。该结果仅许可另行预注册一次模型代理 Accepted@1 诊断；原双人真实审阅门与可信人工 Role 标签仍为0，不得把代理多数描述成金标准。见[GPU失败记录](reports/p0_fk_mapping_model_review_third_proxy_gpu_20261106_01/README.md)、[CPU恢复与聚合报告](reports/p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/README.md)。

### 2026-11-06 模型代理映射排序诊断已预注册

单独的 exploratory 分支 `research/p0-model-proxy-rank-pilot-20261106` 已完成一次冻结 G-reasoner FK mapping 排序诊断。唯一主比较为共用 Qwen3 Query/mapping vectors 的 G-reasoner 对 Dense Cosine；BM25 和稳定 mapping-ID 顺序是次级控制。5题 Smoke 通过；排除 Smoke 后，Full 为55对、51个可裁定、38个可区分、4个匿名数据库。首次 Smoke_001 在模型加载前发现一条 `<br>`/换行序列化差异并停止；Smoke_002 与 Full_002 在预注册的唯一规范化修正后完成。主 Accepted@1 为 G-reasoner 7/38（18.42%），Dense 27/38（71.05%），差−52.63 pp；净救回−20，4库均为负，排除异常项后的差值−54.05 pp。所有正向门失败，按停止条件标记 `NO-GO`，不追加同一代理标签的图变体或调参。模型代理标签不是人类真值，可信人工 Role 标签仍为0。见[预注册方案](plans/p0_fk_mapping_model_proxy_rank_pilot_20261106.md)、[完整报告](reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/README.md)和[匿名聚合结果](reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/aggregate_summary.json)。

### 2026-11-06 Mini-Dev 2026 reviewed Schema 检索迁移筛查

首次登记 `_01` 在读取问题和 schema 文件哈希时停止：question 哈希匹配，SQLite schema 的配置摘要误录；同时发现 `conda run -n ... python3` 解析到 Python 3.9.20。SQL 解析、标签、向量和模型都未启动。原始记录见[报告 `_01`](reports/gfm_minidev_schema_retrieval_transfer_20261106_01/README.md)。

Amendment 001 注册了独立 `_02`，修正观察到的 schema 哈希并分开 CPU/GPU 环境。CPU 审计解析 SQL 500/500、表标签500/500，但 Full 列合格340/495，低于450门槛；因此 Qwen、G-reasoner、GPU Smoke 与 Full 均未运行。按停止规则，本注册不修改解析器、不启动模型，也不追加 `_003`。完整结果见[报告 `_02`](reports/gfm_minidev_schema_retrieval_transfer_20261106_02/README.md)和[匿名聚合](reports/gfm_minidev_schema_retrieval_transfer_20261106_02/aggregate_summary.json)。Amendment 与配置见[plan](plans/gfm_minidev_schema_retrieval_transfer_20261106_amendment_001.md)和[config](../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106_02.json)。

模型代理 FK 排序已完成且为 NO-GO；同一代理标签上的调参、增加审阅模型或图结构扫描均停止。原 BIRD-dev 全 Schema 检索尝试在模型加载前停止，没有科学结果；其恢复额度已用完。本项使用 BIRD Mini-Dev 2026 reviewed release 的新问题集合，回答一个不同于已知表对内 FK 排序的筛选问题：冻结 G-reasoner 是否改善整库表/列召回。由于数据库仍是原有 11 库，本项只算 query-set transfer，不能写成跨库独立复现或算法新颖性结果。

近期相关工作已覆盖通用 Schema linking 和图结构扩展（Rethinking Schema Linking、Graph-Link、REaR、DSR-SQL、MDB-Link），通用静态错误诊断与 SQL 修复也由 Post-SQLFix 和 SCOPE-SQL 研究；本实验只验证 checkpoint transfer。比较 D0 Dense、G1 Top-1 graph anchors、G3 Top-3 graph anchors；Gold 由参考 SQL 静态解析，`evidence` 与 SQL 不进入模型特征。CPU 标签门先于任何 GPU/模型载入；随后 5 题/5 库 Smoke，成功才运行剩余 495 题一次 Full。G3 需要同时达到 Column R@10 +2pp、数据库簇 bootstrap CI 下界 >0、相对 G1 +1pp，且 Table R@10 下降不超过1pp；失败即停止。

预注册方案：[gfm_minidev_schema_retrieval_transfer_20261106.md](plans/gfm_minidev_schema_retrieval_transfer_20261106.md)；配置：[JSON](../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106.json)。
## 2026-11-06 G3：起点敏感性机制诊断（预注册）

模型代理 Accepted@1 Pilot 已按原计划完成并为 NO-GO；同一标签上不得继续调参或挑图结构。当前只保留一个不同问题的有限机制核查：在完全相同的 55 个 Full 问题×表对和 FK mapping 候选上，比较两个端点同时为 query seed、仅第一个端点为 seed、仅第二个端点为 seed。审阅标签和 Gold SQL 不读取，指标仅为 seed 条件间的 Top-1 变化率与候选对顺序反转率。

这是基于现有报告提出的探索性机制诊断，不是 Role Accuracy、方法改进或论文主线结果；无论排序变化与否，都不能判定正确性。计划：[G3 方案](plans/g3_fk_seed_direction_sensitivity_20261106.md)，配置：[G3 冻结配置](../../../configs/text2sql/g3_fk_seed_direction_sensitivity_20261106.yaml)。执行规则为 5 对 Smoke 通过后运行一次 55 对 Full；之后停止该支线，真实准确率仍需可信标签。

### 2026-11-06 G3 执行结果与路线决定

Smoke_002 通过；Full 完成55个问题×表对、123个mapping候选。A1 对 A0 改变 Top-1 4/55（7.27%）、反转6/81个候选对（7.41%）；A2 改变6/55（10.91%）、反转7/81（8.64%）。A0 确定性重复误差为0。结果没有满足机制信号门，也没有达到无实质影响门，故为 `INCONCLUSIVE`。本支线按计划停止，不继续调整seed、模型或图结构；不读取审阅标签的设计不能判断哪一组排序更正确。Smoke_001 的 Python 3.9 环境错配仅造成一次模型加载前失败，随后在同一冻结环境用 Python 3.12 重跑通过。详见[G3报告](reports/g3_fk_seed_direction_sensitivity_20261106_01/README.md)和[聚合结果](reports/g3_fk_seed_direction_sensitivity_20261106_01/aggregate_summary.json)。可信人工 Role 标签仍为0；如果研究问题仍是 FK Role 准确率，仍需独立可信标签，模型代理结果不可替代。

## 2026-11-06 P0 代理排序错误归因完成

冻结结果的只读分层没有发现 G-reasoner 的正向子组：38个可区分单元中 G-reasoner Accepted@1 为7/38，Dense为27/38，配对净差−20。2候选与3候选分层、无列重叠与单端点重叠分层均未出现 G-reasoner 正向净差；没有复合FK或多接受 mapping 样本可供评估。按预注册规则停止该代理标签排序方向，不进行同数据调参或结构扫描。结果不代表人工 FK Role 准确率，也不证明因果机制。报告：[错误归因说明](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/README.md)、[匿名聚合](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/aggregate_summary.json)。

## 2026-11-06 下一阶段决策

模型代理审阅及其唯一探索排序已完成；排序为 G-reasoner 7/38、Dense 27/38，错误分层没有发现已观察到的正向子群；G3 起点诊断为 INCONCLUSIVE。结合 P2c-R 的离线 Schema 覆盖收益尚无 SQL EX 支持、P2d.2 错误主要集中在 SQL 结构与作用域、P2d.3 受限修复未达到效用门，当前 BIRD-dev 排序/通用修复分支停止扩展，转入错误模式综合和新核心问题筛选。不得把模型代理多数当作人工标签。候选筛选和重启条件见[下一阶段决策记录](plans/next_step_evidence_synthesis_20261106.md)。

## 2026-11-06 新版 BIRD Mini-Dev Gold-SQL mapping 迁移诊断（单次、有界）

本项不是重开旧 BIRD-dev 代理标签排序，也不是宣称拿到了人类 FK Role 标签。官方 2026 reviewed Mini-Dev 给出新的人工复核参考 SQL；标签被严格定义为“在参考 SQL 显式 `JOIN ... ON` 中出现的已声明 FK mapping”。它只验证已知端点后的 mapping 排序，11 个数据库与既有 BIRD 资源相同，不能支持跨数据库泛化或 QuadGraph 整体性能主张。

先在 CPU-only 环境解析 5 题 Smoke，再完成其余题的单次 SQL 覆盖审计。只有 SQL parse ≥98%、限定 JOIN 等式的列解析 ≥95%、排除 Smoke 后至少 30 个可评分问题×表对且覆盖至少 3 个数据库，才运行冻结 G-reasoner 与 Dense 的一次 Smoke/Full 排序比较。质量门失败即归档停止；无同一数据上的调参、图结构扫描或扩样。成功筛选门是 G-reasoner Mapping@1 至少 +5pp、净救回 ≥4，且至少两个各 n≥5 的数据库净救回为正。完整预算、字段边界、环境、版本与复现步骤见[预注册方案](plans/p0_minidev_sql_fk_mapping_rank_20261106.md)及[配置](../../../configs/text2sql/p0_minidev_sql_fk_mapping_rank_20261106.json)。

执行修订：`cpu_smoke_001` 在 SQL 解析前因旧 `dev_tables.json` 与 2026 官方 DDL 表数量不同而停止；未读取标签。旧表列清单对官方 DDL 中对应表/列均一致，官方 DDL 额外包含一张表。已在 amendment 001 登记以官方 DDL 为权威并保留旧清单子集检查，唯一工程恢复为 5 题 `cpu_smoke_002`；不再重试。

最终结果：Smoke 5/5 parse、7/7 JOIN 等式解析；Full 495 题完成。完整 500 题 parse 为 500/500，限定 JOIN 等式解析率 523/663=78.88%，低于 95% 质量门。48 个可评分题×表对、4 个数据库的数量门通过，作用域错误为 0；最终 `STOP_LABEL_GATE_FAILED`。未运行 G-reasoner/Dense/BM25，也未调用模型/API。此次停止针对标签解析覆盖，不代表排序器性能负面结果。报告和匿名聚合见[实验报告](reports/p0_minidev_sql_fk_mapping_rank_20261106_01/README.md)与[聚合](reports/p0_minidev_sql_fk_mapping_rank_20261106_01/aggregate_summary.json)。不自动重试或扩展该排序实验；如后续研究 140 个无法解析的限定等式，须另立有界 parser error taxonomy 预注册。

## 2026-11-06：G-reasoner 原始表/列检索迁移诊断（停止；无科学结果）

已停止的 FK mapping Pilot 回答“已知表对内哪条 FK mapping 得分更高”，不能代表 P1.6 的完整表/列检索任务。P1.6 测得 Dense Column R@10 为 68.00%，但没有运行 G-reasoner。为区分“FK mapping 任务适配失败”和“G-reasoner 在 Schema 检索上无增量”，单独预注册一次冻结 checkpoint 的表/列检索诊断。它仍使用反复开发的 BIRD dev，只作 exploratory transfer screen。

三条件共享同一 Qwen3 query/node vectors：D0 为 Dense Cosine；G1 为每类节点一个 Dense anchor；G3 为每类节点三个 Dense anchors。Query 使用 G-reasoner checkpoint 指令并重新编码，避免复用指令不同的 P1.6 cache；Schema 文本使用冻结的 value-free R1 视图，避免让公开方法声称不含 Values 却实际输入 Values。图只含双向 table/column membership 边，不含 FK、Gold SQL、Gold 派生边、Values 或业务角色。主指标 Column R@10；迁移门、预算、Smoke/Full 和停止规则见[预注册方案](plans/gfm_schema_retrieval_transfer_20261106.md)与[冻结配置](../../../configs/text2sql/gfm_schema_retrieval_transfer_20261106.json)。

首次 `smoke_001` 的 `conda run ... python3` 解析到了 `/root/miniconda3/envs/python39/bin/python3`，在 PyG 导入时停止。Amendment 1 显式指定目标环境解释器后，唯一恢复 Smoke `_002` 又在 G-reasoner `config.json` SHA-256 核验处停止：注册值 `75d14b97d6a077ebc17b09a21170a3d9272251db59f7ac8cc853165efb2efd5`；实际文件值 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`，注册值少一个 `a`。两次均无 Qwen/G-reasoner 模型加载、embedding、前向、token 或 API 请求；`_002` 有 0/5 有效打分。原日志和失败收据保留；没有覆盖数据、模型或旧结果。

REaR、Graph-Link、Rethinking Schema Linking、JoinGR 已覆盖多类图式/结构式 Schema retrieval，因此本项只作冻结 G-reasoner checkpoint-transfer 证伪诊断，不宣称新算法。Amendment 1 的恢复额度已耗尽；按预注册停止规则，不启动第三次 Smoke 或 Full。没有科学指标，核心假设未被支持或否定。完整记录见[失败报告](reports/gfm_schema_retrieval_transfer_20261106_01/README.md)及[匿名汇总](reports/gfm_schema_retrieval_transfer_20261106_01/aggregate_summary.json)。
# 2026-11-07：冻结 FK 排序对参考 SQL 映射的配对复核（已预注册）

前一轮在三模型代理标签上的 G-reasoner/Dense Mapping@1 为 7/38 对 27/38。为判断该负向诊断是否只由代理标签定义造成，本登记在完全相同的 55 个非 Smoke 问题×表对和冻结排名上，另用原 BIRD dev 参考 SQL 中明确使用的 FK mapping 作为评价标签。模型分数、候选集、数据库和问题均不变；SQL 只进入离线评价，绝不进入 Query 特征、候选生成、分数或排名。

该复核是一次 exploratory label-target audit，而非新增方法或重复模型实验。Primary 为 set-valued SQL-used Mapping@1；Secondary 为 Mapping@3、MRR 与模型代理接受集合对 SQL-used mapping 的覆盖。若参考 SQL 使用多个匹配映射，全部作为正例；若解析后候选集中没有 SQL-used mapping，该行计入候选覆盖损失并从排序分母排除，不能作为排序错误。`SQL-used` 不等于唯一业务正确 Role。

预注册门：5 个非 Full 的 Smoke 样本需全部解析、无 scope error、所有 qualified JOIN-ON 等式均可解析，且至少 4 个匹配候选；Full 至少 54/55 SQL 可解析、scope error 为 0，至少 30 个“该题全部 qualified JOIN-ON 等式均可解析且候选中含 SQL-used mapping”的样本覆盖至少 3 个匿名库。该题级完整解析门可能因不相关 JOIN 丢弃样本，但避免把部分提取映射集当成完整目标。主信号沿用既有筛选门：G-reasoner 比 Dense 至少 +5pp、净救回≥4，且至少两个各 `n≥5` 的匿名库净救回为正。任一覆盖门失败或信号门未达，均停止，不补样、不调分、不重新调用模型。

Amendment 001 在任何 SQL 解析前把评测资格收紧为“该问题所有 qualified JOIN-ON 等式均已解析”，因为当前复用 helper 只提供 query-level resolution counters；这会牺牲覆盖率以避免不完整 SQL mapping 集进入主指标。

设备检查显示 4 张 RTX 4090 当前约 80–82% 使用；本实验限定 CPU、不加载模型、无需 GPU。代码与报告使用独立 run IDs 和目录。预注册提交地址、输入哈希、实现 commit、环境和命令均归档在[实验方案](plans/p0_fk_sql_used_proxy_alignment_20261107.md)与[配置](../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107.json)。

### 2026-11-07 执行结果：SQL-used FK 映射复核在 Smoke 预检停止

运行准备提前创建了 `smoke_001/` 输出目录，触发运行器的 `OUTPUT_DIRECTORY_ALREADY_EXISTS` 保护；运行器在输入读取前停止，未解析 SQL、未计算任何排名指标，Full 未运行。按冻结规则不重试该注册，核心假设未检验。完整记录见[执行报告](reports/p0_fk_sql_used_mapping_alignment_20261107_01/README.md)和[匿名汇总](reports/p0_fk_sql_used_mapping_alignment_20261107_01/aggregate_summary.json)。

### 2026-11-07 独立注册 02：冻结排名的 SQL-used 标签复核

旧注册 `_01` 不重试。其 Smoke 在输入读取前因运行准备提前创建受保护的结果目录而停止，旧报告明确：若未来仍要回答该问题，必须使用新注册。另建 `_02`，使用新的 runner、config、Smoke/Full run IDs、结果根和日志根；冻结数据、样本、排名与 SQL-used 标签规则不变。该复核可判断旧的 7/38 对 27/38 模型代理排序是否依赖标签目标，但参考 SQL-used 仍不是唯一语义真值，也不构成新方法主张。

Qwen A/B 与 Gemma C 的模型审阅已经完成；新增模型票不会建立人工金标准，所以本轮不做模型推理，只用现有代理集合做次要描述指标。正式执行前推送并核对本预注册；Smoke 全部通过后才运行唯一一次 CPU Full，否则停止。详细边界、门槛和预算见[注册方案](plans/p0_fk_sql_used_proxy_alignment_20261107_02.md)、[冻结配置](../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107_02.json)及[独立报告](reports/p0_fk_sql_used_mapping_alignment_20261107_02/README.md)。

执行结果：Smoke 5/5 SQL parse、8/8 限定 JOIN 等式解析、0 scope error；但 SQL-used mapping 与冻结候选命中 0/5，低于预注册 4/5 门槛。状态 `STOP_SMOKE_GATE`，不启动 Full，不计算 G-reasoner/Dense 排名指标。当前聚合不能区分候选确实缺少参考 SQL 使用的 FK mapping 与候选/映射身份对齐问题；该结果不支持模型效果结论。依停止规则，不重试本注册。见[执行报告](reports/p0_fk_sql_used_mapping_alignment_20261107_02/README.md)及[匿名汇总](reports/p0_fk_sql_used_mapping_alignment_20261107_02/aggregate_summary.json)。
