# 阶段实验方案：Dimension → Similarity → Role/Path → Text2SQL

> **研究指导 v1（2026-10-14 制订；2026-10-16 迁入主仓库，尚未核实任何实验已运行）**。任务是找出“表示维度 vs 评分方法 vs 业务 JOIN 角色”各自可归因的影响；先使用最小可复现检索实验，再决定是否接入 GFM/GNN。

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
