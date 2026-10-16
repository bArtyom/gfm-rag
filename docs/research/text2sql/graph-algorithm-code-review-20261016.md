# G-reasoner / QuadGraph 图算法源码精读与 Text2SQL 改进候选（2026-10-16）

> **状态：已完成源码静态核对与实验优先级分析；本文是研究建议，不包含任何新训练/检索/SQL 运行成绩。**
>
> 审阅的 canonical fork: [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag), commit `fef24f94a008e4aa167df41229c8a62bd53021fc`（开始审阅时）；代码基线与官方上游保持一致，后续仓库中新增的文件属于研究文档。最新已测 P1：见 [P1 复核](reports/p1_review_20261016/README.md)。**P1 是 embedding-only，不可借其结果宣称 GNN 已有效/无效。**

## 核心判断

**现阶段最值得研究的机制是「Query-aware Edge / Join-instance Scoring + Constrained Subgraph Retrieval」，而不是仅加深 GNN 或继续试 Embedding 维度。**

一张图可以正确表达某列为何属于一张表、哪些 FK 可 JOIN，却不一定包含足够信息确定「在这个用户问题下应该走哪条 FK、怎么连接」。G-reasoner 的主干输出是**节点得分**，Text2SQL 的最终输出需要具有关系类型/实例身份、完整 FK 列对、连通性及语义角色的子图。这是可检验的结构性缺口。

但需要明确：Graph-Link、SchemaGraphSQL、GRAST-SL 已研究连通子图、外键补全或图重排序。不能把「引入 schema 图、Steiner Tree、RRF」本身宣称新颖；增量贡献应该落在**实例级 JOIN 角色建模、查询条件下可解释边权、文本/结构证据的联合监督及受约束输出**。

## 1. 源码中的可核对事实

| 模块 | 位置 | 当前行为 | 与 Text2SQL 的关系 |
|---|---|---|---|
| 构图默认实例 | [`kg_constructor.py`](../../../gfmrag/graph_index_construction/graph_constructors/kg_constructor.py) `build_kg` 约 L390、`augment_graph` L456–506 | OpenIE 三元组在构图中存为 `graph[(head,tail)] = relation`；图增强把高相似实体加 `equivalent` 边，门槛默认 0.8、上限邻居 100 | 相同有向实体对的不同关系会在**该字典**中覆盖；若把这条构图路径用于多角色 FK，关系身份可能丢失。我们应绕开 OpenIE 生成 DB 图，用确定性 Schema 数据建多重关系 |
| 相似图增强 | [`dpr_el_model.py`](../../../gfmrag/graph_index_construction/entity_linking_model/dpr_el_model.py) L122–168；[`kg_constructor.yaml`](../../../gfmrag/workflow/config/graph_constructor/kg_constructor.yaml) | DPR 检索相似度；`norm_score = raw_score / max_score`，增强规则用 `norm_score` 而非绝对校准相似度 | 该相对分值不等于同义的概率。数据库里 shipping/billing 这类近义但非等价关系不能随便连 `equivalent`，需单独的消融与误边审计 |
| 输入/种子 | [`gfmrag_retriever.py`](../../../gfmrag/gfmrag_retriever.py) L125–174 | 先做 NER，缺实体则退回整个 Query；每 mention 做 `EL(topk=1)`，生成二值 `start_nodes_mask` | 单点误链会影响整个后续图传播；多实体、同义列名/业务别名适合评估软锚点 `top-k + confidence` |
| 图加载 | [`graph_index_dataset.py`](../../../gfmrag/graph_index_datasets/graph_index_dataset.py) L346–540 | 构造 node_type、edge_index、edge_type；加 inverse edge；把关系、节点及（可选）逐边属性编码为 `rel_attr/x/edge_attr` | 格式能存异构节点和边属性，但是否被主干使用要看下游 |
| 图消息传播 | [`model.py`](../../../gfmrag/models/gfm_reasoner/model.py) L229–307；[`models.py`](../../../gfmrag/models/ultra/models.py) L195–210、L430–489；[`layers.py`](../../../gfmrag/models/ultra/layers.py) L77–110、L163–251 | 主干以 `rel_attr` 对关系**类型**投影；NBFNet 单进程路径的 `edge_weight` 默认为全 1；默认 `DistMult` 消息和 `sum` 聚合；当前 `GraphReasoner.forward` 未将 `graph.edge_attr` 传入 GNN，也未显式以 `graph.node_type` 控制类型专属消息 | **关系类型会影响消息**，不能说「完全不考虑边」。真正缺少的是**同一关系类型下，逐实例边的 Query-conditioned 权重及业务角色区分**；大度数/桥表处 Sum 聚合的尺度行为也值得受控消融 |
| 输出 | [`gfmrag_retriever.py`](../../../gfmrag/gfmrag_retriever.py) L72–124 | `pred` 是全部节点分数，按 `target_types` 独立 `torch.topk`；默认目标类型为 document | 节点 Top-K 并不自动保证 Column 属于已选 Table、所需桥表未漏、子图连通、JOIN 条件完整 |
| 训练监督 | [`sft_trainer.py`](../../../gfmrag/trainers/sft_trainer.py) L151–198；[`sft_training.yaml`](../../../gfmrag/workflow/config/gfm_reasoner/sft_training.yaml) | 监督任务选择 `document`，BCE/ListCE + 以 `question_embeddings @ target_node_emb.T` 作 MSE 蒸馏信号；可按类型配置不同目标 | Text2SQL 要的是 Table/Column/FK/Path，不能只依赖 document ranking；直接蒸馏文本内积可能复制纯 embedding 检索的偏差。需重新定义标签/负例及目标 |

**证据限定：**上述是源码静态分析而非运行时 bug 定性。构图的多关系覆盖问题只适用于当前 `KGConstructor.build_kg` 用字典构图路径；**Path B：用户自带 `nodes.csv/relations.csv/edges.csv` 不会自动触发这个 OpenIE 字典覆盖**。训练主干的 `edge_weight` 在路径可视化时可用于梯度归因，这不等于正常推理已有可学习逐边概率。

## 2. 候选创新按优先级排序

### T0 — 图保真度和标签质量：前置 Gate，而非新颖性主张

1. 确定性解析 BIRD 的 Table/Column/PK/FK，保留一个完整 Join Instance 的**约束 ID + 所有有序列对**；两条指向同表的不同 FK 不可归并，复合键不能任意拆开。
2. 构建一个**最小、可直接加载 GFM-RAG 的 Schema Graph**：table、column、可选 join-instance 类型；`has_column`、`fk_endpoint`、`fk_to` 等关系。只使用运行时可见注释/DDL 生成 role 文本；gold SQL 只作评价。
3. 校验 `nodes.csv` / `relations.csv` / `edges.csv`、inverse edge、关系类型和关系实例在 `graph.pt` 的无损映射；单测 billing/shipping、多条平行关系、复合键和无 FK JOIN。
4. 审计 `equivalent` 增强边：Schema 下默认禁用，不因相似度高就创造结构性 FK；如研究同义词边，单列为软语义边，不能当作可执行 JOIN。

**现在做什么：**继续历史 P1.5 的 FK Gate + 标签审计，不额外训练，不把这项算作创新成绩。

### T1 — Query grounding / soft multi-anchor：最先可做的图推理机制消融

**源头：**`GFMRetriever.prepare_input_for_graph_retriever` 固定 `EL(topk=1)`，并构造二值 mask；`GraphReasoner.forward` 已支持非二值的 `start_nodes_mask` 与查询向量结合。

- G0：原 NER + Top-1 EL + binary seed，按现有 checkpoint 建立实际 GFM 基线。
- G1：相同 NER/EL 模型的 Top-3/Top-5 + 二值多点 seed。
- G2：相同候选和预算的 Top-3/Top-5 + **归一化软权重 seed**（基于校准的候选分值，不能直接把相对 `norm_score` 当概率）。
- G3：同输入 Text2SQL 的 table/column mentions、列名别名与描述锚点，固定同等信息量；单独归因新 NER/alias 映射的作用。

关键风险：预训练 GFM 的 seed 分布与训练时 Top-1 二值输入不同，零微调效果可能退化。**先做不训练的可兼容测试，若失败不要直接断言 soft seed 无效**。评价 node Recall、锚点覆盖、最终完整 Schema 与成本。

创新性：中等偏低——seed 扩展是合理工程改进，但与图检索社区已有工作相近；可作为后续方法组成，不宜单独成论文。

### T2 — Query-conditioned Edge Gate：更贴近核心图算法创新

**源头：**每条边在加载后有 `edge_index`、`edge_type`，可选 `edge_attr`，而 `QueryNBFNet.bellmanford` 正常单进程边权初始化为全 1；当前未把边自身特征用于主干。

保持 FK 原子结构的前提下，新增一个轻量打分器：

\[
g_e(q)=\sigma(\mathrm{MLP}([h_q;h_{r(e)};h_{\mathrm{edge}(e)};h_u;h_v]))
\]

并把它用于消息：

\[
m_{u\to v}^{(\ell)} = g_e(q)\,\big(h_u^{(\ell-1)}\odot r_e^{(\ell)}\big)
\]

其中 `h_edge` 可包括 Join Instance 的业务角色描述或规范化属性；`r_e` 初期仍使用现有关系类型 embedding。**这不是现有论文公式，是计划中的待验证扩展。**

必须区分两类边：
- **硬结构事实**（FK/PK/has_column）：事实存在性永远不能被模型改写；检索权重可以调低，但形成的候选 SQL 子图必须满足硬连接条件。避免将 `g_e < threshold` 直接视为结构无效。
- **软语义关联**（别名/文档提及/假设性连接）：可以按可信度打分及过滤，但不能把它变为一个凭空存在的 FK。

**最小消融**：E0 原全 1；E1 原关系类型投影 + Query/Relation Cosine 的静态边先验；E2 加原始边文本 embedding 的 gate；E3 Query+Edge 的轻量可训练 gate；E4 去 role hint、E5 去 query、E6 去 edge_attr。保持图、初始锚点、GFM 主干和预算不变，训练变体需同规模同算力/标签。对比桥表漏检、同表多 FK、无关语义边进入 Top-K 的错误。

实现建议：在 `GraphReasoner` 预计算每查询的 `edge_gate[B,E]`，在 `QueryNBFNet` / `GeneralizedRelationalConv` 中改为应用权重。当前边权接口传入的是 `edge_weight`，需确认 **batch 维与 fused rspmm CUDA 路径对 [B,E] 是否兼容**；优先验证 batch=1 或非 fused reference 路径，再决定高性能实现。不能无测试地假定现有 CUDA kernel 支持 Query-conditioned per-sample edge weight。

创新性：潜力中高，但「Query-aware 边打分」本身并不新；要突出 **SQL JOIN 实例身份、role grounding + 可执行结构约束**。

### T3 — 多粒度异构消息与 degree-aware aggregation

**源头：**`graph.node_type` 用于类型标记、`nodes_by_type` 用于监督/输出，`GraphReasoner.forward` 里没有类型专属路由；默认 `sum` 聚合在高度数 Table/Column/Document 节点可能放大邻域规模效应。

逐级测试：
- H0：现有 `sum`（6 层）；H1：`mean`，H2：`pna`，**需重训/适配受影响的层，不可直接带相同 checkpoint 当纯推理开关**。
- H3：把 Table–Column、Column–Join Instance、Document–Column、Community–Table 分为可审计的关系族，基于现有 `edge_type` 做族分组归一化/门控。
- H4：只有 H3 有证据时，再做跨类型路由、relation-family attention 或 residual；固定图输入且逐项拆分新增参数量。

评价：每类节点的 Recall 与 precision、bridge table coverage、高度数节点扰动、运行时/显存。若性能变化仅来自增加节点类型和更大参数量，不可归因于异构消息本身。

创新性：已有 Heterogeneous GNN/R-GCN/HGT 相关基础，独立新颖性有限；若用于解决 SQL 角色与复合 FK 的明确失效则有价值。

### T4 — 从 Node Ranking 到合法 Subgraph/Join Path Retrieval（最终系统目标）

**源头：**`GFMRetriever.retrieve` 当前输出按类型独立 Top-K，缺乏表/列依赖及强约束。

给定检索打分和候选连接图，在固定预算下构造：

\[
P^*(q)=\arg\max_{P\subseteq G}\{\mathrm{Rel}(P,q)-\lambda\mathrm{Cost}(P)\}
\]
\[
\text{s.t. }P\text{ 引用的字段均属于已选表，JOIN 使用真实且完整的约束，所需表连通，输出遵守 token 预算。}
\]

初版无需端到端训练，可比较：
- R0：现有 node Top-K；
- R1：node Top-K + 确定性 FK closure（保证结构连通但可能增加噪声）；
- R2：同候选/同预算 shortest path / Steiner Tree baseline；
- R3：Query-aware Role/Edge 评分 + constrained path rerank；
- R4：联合训练可选，只有 R3 同信息增益可靠后才做。

对最短路径偏好进行保护：短路可能选错 billing/shipping、无 FK join 可能合法，不能把长度当业务正确性。路径应允许**多个等价合法候选**或 abstain，并独立记录不可被 FK-only 图覆盖的题目。

创新边界：连通子图/Steiner 已被 [Graph-Link (ICML 2026)](https://proceedings.mlr.press/v306/zhong26s.html) 和 [SchemaGraphSQL (EACL 2026)](https://aclanthology.org/2026.findings-eacl.134/) 研究过，必须有 **JOIN-role 可证实的额外贡献**，不能仅照搬优化器。

### T5 — SQL-aware 监督而不是纯文档蒸馏（最后考虑，训练成本较高）

**源头：**`SFTTrainer.train_step` 的教师分数 `q @ node.T`，默认 `target_node_type=document`。即使采用 GNN，蒸馏项仍可能鼓励复制纯文本相似度。

对 Text2SQL 的可选监督：
- Table/Column multi-label BCE / Listwise ranking；
- **同表多 FK Hard Negatives**：结构合法但与用户问题业务角色不匹配的 JOIN；
- Path-level contrastive/ranking：要求正确或等价 Join Path 在同候选下高于错误角色/冗余路径；对业务语义无法唯一裁定的题不施加强制负例；
- 训练前先证明 Gold FK/path 标签可信、不泄漏 SQL 到推理特征；
- 仅有 BIRD dev 的 11 个数据库时，对数据库独立 hold-out 的统计不确定性须充分标明。

训练组须配对：纯文本 scorer vs GFM 原始 SFT vs 新 edge/path loss；同训练预算与 checkpoint，禁止将新增信息、更多负例与新 loss 混在一次实验里而不消融。

## 3. 优先级 / 研究投入

| 顺位 | 课题 | 改动代码 | 首轮成本 | 可解释性 | 独立创新性判断 |
|---|---|---|---|---|---|
| **0** | 数据图保真 + FK/Role Gate | Schema builder / tests / loader validation | CPU、低 | 很高 | 必要前置，不单独新颖 |
| **1** | 1024 GFM 真正推理基线 + soft multi-anchor | `gfmrag_retriever.py` | 低至中，取决于 checkpoint/GPU 环境 | 高 | 中低 |
| **2** | Query-aware edge/role gate | `gfm_reasoner/model.py`、`ultra/models.py`、`ultra/layers.py` | 中，需要小规模训练与 kernel 检查 | 高 | **最值得研究** |
| **3** | 实例感知关系子图约束解码 | retriever + SQL Schema serializer | CPU/中 | 高 | 与 Graph-Link 等强重合，需联合角色创新 |
| 4 | Heterogeneous/degree-aware message | `ultra/layers.py` | 中高，需对照重训 | 中 | 单独新颖性有限 |
| 5 | SQL-aware path loss / hard negatives | SFT dataset/trainer/loss | 高，标签要求高 | 中高 | 与 2/3 联合后有潜力 |

**说明：**「研究潜力」是基于缺口与已有基线的判断，不是有实证增益的排名。

## 4. 下一轮决策：不覆盖已冻结的 P1.5 主线

当前已冻结的执行指导仍为：[P1.5 离线列检索错误与预算审计 → 条件式 P2a Cosine/BM25/RRF](plans/p1_5_diagnostics_and_p2a_20261016.md)，**新算法实验不提前运行**。

可以并行开展**仅 CPU 的 T0 图保真度审计与微型合成库测试**，但这不算 P1.5 Gate 通过：

1. 在 `orders(billing_address_id,shipping_address_id)→addresses(id)`、复合 FK、2 跳桥表、无声明 FK 但合法连接的最小 Schema 上构造单测，保证从 `edges.csv` 到 `graph.pt` 的 Join Instance 无损映射。
2. 确认 `GraphReasoner` 的 `edge_attr` 未被用于预测，确认 `topk=1` / 二值 seed 的具体错链路径；如果引用默认构图 `graph[(h,t)]=r` 覆盖，限定其适用范围并提出回归用例。
3. 等 P1.5 报告到达后，如果列错误主要是 lexical retrieval 且 P2a 能明显纠正，先把融合检索用于 seeds；如果错误主要是路径/角色，T2+T4 才正式进入注册实验。
4. 若 FK Gate 仍未通过，则不声称「Join Role 实验」已开始；可以保留独立的 node retrieval 基线，不编造 JOIN。

**下一轮交付物**：一份 `P1.5` 真实数据诊断（分库、可评分母、Top-K 饱和、512/1024 配对错因、FK 不合格原因），并提供上述 T0 的合成单测结果；所有“是否改进”的判断在实际消融后记录。

## 5. 必须报告的指标

- 召回：Table / Column / Join Instance Recall@K，区别已召回端点表下的条件列召回；
- 结构：FK instance coverage、Bridge-Table Path Recall、Composite-FK Integrity、Connected Required Subgraph@Budget、多路径/歧义计数；
- 精度：Precision@K 与 Schema tokens per correct element；按复合键、同表多关系、缺失 FK、数据库大小分层；
- 可靠性：多 seed 的错误传播、同表不同 role hard negatives、无 FK 的 abstention / fallback；
- 端到端：**Set EX 主指标、Bag EX 辅助**、Token/USD/Latency，固定 SQL Generator、候选池与 Selector；
- 统计：数据库宏平均、同题 rescue/damage、按数据库聚类的置信区间、真正的独立数据库验证；
- 全部真实计算资源和更改的模型参数/训练量；*不能把 P1 的 50% 向量大小节省写成 GFM 全链路省 50%*。

## 6. 不应立即进行的操作

- 直接把 GNN 层数 6→8、隐藏维 1024→512，未适配 checkpoint 就对比“原模型”；
- 默认用 `equivalent` 把同名/高 Cosine 的 FK 合并；
- 只替换 `sum→mean/pna` 而不训练兼容权重；
- 没有完备 Join Role 标签就用 Gold SQL 自动生成负例并宣称角色识别；
- 仅在 BIRD dev 多次搜索边权系数并汇报最优 SQL EX；
- 在当前图尚未保真时将更多 Attribute/Document/Community 节点堆入图；
- 对读取到的代码做未经测试的线上改动；本文件仅提出研究方案。
