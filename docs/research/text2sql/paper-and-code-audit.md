# G-reasoner / QuadGraph 论文与代码审计（面向 Text2SQL 实验）

> 原始审计日期：2026-10-14；迁入主仓库：2026-10-16。**论文事实、实现事实与我们的迁移假设严格分开**。此文档不是实验报告。

## 1. 论文中直接支持的机制

**研究对象**：[G-reasoner: Foundation Models for Unified Reasoning over Graph-structured Knowledge](https://arxiv.org/abs/2509.24276)，官方代码：[RManLuo/gfm-rag](https://github.com/RManLuo/gfm-rag)。

- Section 4.1 把不同图抽象为包含四类节点的异构图接口：**Entity / Knowledge Graph、Attribute、Document、Community**。层内/跨层均可连边，并不要求每张输入图都含四层。
- Appendix C.1 描述复用已有图构建器，例如 HippoRAG、LightRAG、Youtu-GraphRAG，通过统一表示输入 G-reasoner。**统一图接口不等于作者提供一套最优的 Text2SQL Schema 建图算法**。
- Section 4.2 使用查询、实体、关系的文本表征与 Query-dependent 图消息传递。最终检索分数不是“只计算两向量 Cosine”；GNN 节点打分、教师相似度和 Entity Linking 分属不同阶段。
- 论文使用 Qwen3-Embedding-0.6B 的 1024 维文本表示，并采用六层、1024 隐藏维配置进行 GFM 实验。**这不说明 1024 是 Text2SQL 的最优维度**。

**重要核查界限**：针对当前查阅的 G-reasoner 版本，不把我们的 Text2SQL 表/列/FK 迁移图写成作者已公开验证的 Text2SQL 实验。若以后发现包含 Text2SQL 的不同版本，必须记录论文版本、页码、实验任务、数据与指标，再修订这一边界。

## 2. 官方源码：可以直接操作什么？

### 2.1 可调文本维度

- [text_emb_model/qwen3.yaml](https://github.com/RManLuo/gfm-rag/blob/main/gfmrag/workflow/config/text_emb_model/qwen3.yaml)：模型 Qwen/Qwen3-Embedding-0.6B、normalize: True、truncate_dim: 1024，以及面向 Web 检索的 query instruction。
- [Qwen3TextEmbModel](https://github.com/RManLuo/gfm-rag/blob/main/gfmrag/text_emb_models/qwen3_model.py)：内部 vLLM embed 使用 PoolingParams(dimensions=truncate_dim)；vLLM API 调用也可以带 dimensions。

结论：可以用**同一基础模型**形成 128/256/512/768/1024 维向量；不必为维度比较先训练一组不同的 Embedding 模型。

限制：**这不意味着直接改一个配置就能无障碍复用 G-reasoner 34M 已发布权重**，详见 2.3。

### 2.2 归一化风险：必须做运行时范数审计

- 官方 qwen3.yaml 指定 normalize: True。
- 但当前 Qwen3TextEmbModel.encode / embed / _make_request 路径没有清晰的“返回前显式 L2 normalize”步骤；底层 vLLM 输出是否已归一化需要实测，不能只凭 YAML 推断。
- [BaseTextEmbModel](https://github.com/RManLuo/gfm-rag/blob/main/gfmrag/text_emb_models/base_model.py) 的 SentenceTransformer 路径传入 normalize_embeddings，但不能因此推断 Qwen3 路径行为相同。

实验必须记录每个维度、每种运行后端的向量 L2 范数 min/median/p95，并**在检索评分之前显式统一归一化**：

$$
\hat h = \frac{h}{\max(\lVert h\rVert_2,\epsilon)}
$$

单元检查：NaN/Inf 数量=0；输出形状为 (N,d)；归一化后非零向量的范数接近 1。固定相同的 query/passsage instruction，禁止为每个维度单独优化 prompt。

### 2.3 为什么不能直接换维度后照用 pretrained GFM？

- [GraphReasoner / QueryGNN](https://github.com/RManLuo/gfm-rag/blob/main/gfmrag/models/gfm_reasoner/model.py) 的 question_mlp、rel_mlp、ent_mlp 输入为 feat_dim；训练权重形状与输入维度有关。
- [GFM 训练配置](https://github.com/RManLuo/gfm-rag/blob/main/gfmrag/workflow/config/gfm_reasoner/kgc_trianing.yaml) 包含 feat_dim: 1024、input_dim: 1024 和 hidden_dims 六层 1024。
- 因此 512 维向量直接作为原输入会触发投影层形状不兼容；重建投影层后不再是原 checkpoint 的纯推理复现。
- 零填充到 1024 维只能是诊断，不可作为“公平 GFM 维度消融”核心结果。若要保持 GFM 侧不变，需训练映射回 1024 的适配器并增加同预算基线；也可以在重训约束一致下微调投影层。此工作放 P4。

### 2.4 相似度的严格定义

对于单位向量：

$$
\text{Dot}(\hat q,\hat v)=\text{Cosine}(q,v)
$$

Sigmoid(dot) 单调，因此作为**单独排序**不会带来不同排序。对归一化向量重复运行 Dot 与 Cosine 并声称两种创新属于无效消融；如要比较向量范数效应，可额外评测 *unnormalized dot*，并明确它同时改变了归一化条件。

独立层次：

1. 向量召回：Q ↔ 节点/关系文本，Cosine / Dense Retrieval。
2. Entity Linking：NER mention ↔ 实体表示，可能采用 DPR 内积或 Cosine。
3. GraphReasoner：Query-dependent GNN 对节点打分，不能简单等价为 Cosine。

## 3. 我们提出、尚未被论文验证的 Text2SQL 图表示

冻结首轮基础图：Table、Column、Column-belongs-to-Table、真实 FK。Join Instance 作为**有稳定 ID 的整体关系实例**，包含外键约束 ID、左右列序列、复合键原子分组、来源、可选业务角色说明。

示例：

~~~text
join:orders.billing_address_id->addresses.id
source_column: orders.billing_address_id
target_column: addresses.id
role_hint: billing address  # 仅在 schema/业务文档已存在时可填

join:orders.shipping_address_id->addresses.id
source_column: orders.shipping_address_id
target_column: addresses.id
role_hint: shipping address
~~~

非必要的 Document/Attribute/Community **先不新增节点**，避免让 P1 的“维度变化”夹杂“建图结构变化”。业务注释可以先作为现有节点/边的文本字段。以后做独立 Graph Ablation 才决定是否拆为独立节点。

**不能从 Gold SQL、评测答案或人工事后分析中构造运行时 role_hint。** 允许用 Gold SQL 建立离线评价标签，不允许用于生成候选特征和在线评分。

## 4. 必须避免的论文与方法表述错误

- **“换 Embedding 维度证明 G-reasoner 图推理变强”**：错误。P1 是无 GFM 的 Text2SQL 检索实验。
- **“L2 normalized Dot 比 Cosine 更优”**：两者理论同分同排名。
- **“所有参考 SQL JOIN 边是唯一合法金标路径”**：业务等价路径/多 SQL 写法需要歧义审计。
- **“多层图越多越好”**：未经结构消融，不能断言。
- **“Embedding+BM25+RRF 即论文创新”**：已有大量基线；真正的研究空间在角色约束、JOIN 实例判别、路径级查询感知评分以及公平下游收益。
- **“提升的 Set EX 来自 Jev”**：本仓库不修改 Jev；直到独立验证前不做这种归因。

## 5. 后续参考与查新

- Qwen3 Embedding：[模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)（Matryoshka 维度能力）。
- [GRAST-SL 开源](https://github.com/thanhdath/grast-sql)：已涉及 Schema Filtering、图相关性排序等。新算法需要在同信息条件下比较，不能泛称“首次将图结构用于 Schema Linking”。
- [CHESS 开源](https://github.com/ShayanTalaei/CHESS)：可作为下游 Text2SQL 基线候选。
- 此页只核对已查阅的论文和官方源码；后续版本更新需记录 commit SHA 并重做关键假设检查。
