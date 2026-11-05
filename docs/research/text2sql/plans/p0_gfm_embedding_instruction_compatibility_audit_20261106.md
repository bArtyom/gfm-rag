# G-reasoner Query 指令兼容性审计：FK 映射 Pilot

**状态：只读代码与模型配置审计；不是新实验注册，也未运行模型。** 本审计冻结下一项 FK 映射排序 Pilot 的 Query 编码要求。可信双人 Role 标签仍为 0，因此不启动 Smoke、Full 或模型加载。

## 结论

G-reasoner-34M checkpoint 配置登记的 Query 指令，与 P1.6 表列检索使用的 Query 指令不同。G0 探针实际使用 checkpoint 登记的指令。后续 G-reasoner FK 映射 Pilot 可以沿用 G0 的输入格式；不得把 P1.6 的 Query 向量缓存直接作为该 Pilot 的 G-reasoner Query 输入。

若 Dense Cosine 与 G-reasoner 要在同一 Pilot 中比较，二者必须共享同一 Query 文本、同一 checkpoint 兼容的 Query 向量、同一映射候选文本和同一候选集合。否则得分差异会同时包含编码指令差异，无法归因于图推理。

这项发现不推翻 P1.6 的内部结果：P1.6 的所有条件都在其已冻结的自然语言数据库检索指令下比较。本审计只限制跨配置复用缓存，不修改历史 P1.6、P2 或 G0 结果。

## 代码与配置证据

| 位置 | 冻结内容 |
|---|---|
| G-reasoner-34M checkpoint 配置 | Qwen/Qwen3-Embedding-0.6B；1024 维；query_instruct 为下列 checkpoint 指令；passage_instruct 为 null。配置文件 SHA-256：75d14b97d6a077ebc17b09a21170a3d9272251db59f7ac8cc853165efb2efd5。 |
| scripts/text2sql/g0_fk_instance_node_probe.py | Query 编码使用与 checkpoint 配置相同的指令；候选节点编码不加 Query 指令。 |
| scripts/text2sql/run_p1_6_rebaseline.py | P1.6 使用另一条面向数据库表列召回的自然语言指令，并将其显式加在 Query 前缀中。 |

checkpoint 与 G0 使用的 Query 指令：

> Instruct: Given a web search query, retrieve relevant passages that answer the query  
> Query:

P1.6 使用的 Query 指令：

> Instruct: Given a natural-language question about a database, retrieve the relevant tables and columns.  
> Query:

## 对下一项 Pilot 的输入要求

在双人标签门通过、正式注册之前，将以下约束写入独立运行配置：

1. Query 向量使用 G-reasoner checkpoint 登记的完整 Query 指令；不从 P1.6 cache 读取 Query 向量。
2. checkpoint 的 passage_instruct 为 null；映射节点文本按 passage 侧编码，不额外套用 Query 指令。
3. Dense Cosine 与 Reified G-reasoner 使用完全相同的 Query embedding、映射文本 embedding、问题×表对候选集及文本字段。BM25 和 query-independent 结构排序也必须使用相同原始 Query、映射文本与候选集。
4. 保存模型与配置哈希、Query/映射文本序列化、指令全文、向量缓存哈希和运行配置；将输入兼容性检查放在 5 题 Smoke 的启动门内。
5. P1.6 的 Query/schema cache 继续用于原有 Dense rebaseline，不改写旧缓存或历史报告。

该 Pilot 仍只回答：在给定表对和声明 FK 候选时，冻结 G-reasoner 是否能把双人共识接受的映射排在 Dense Cosine 前面。它不测端到端表发现、缺失 FK 推断、SQL EX 或跨库泛化；不训练、不微调 checkpoint。

## 当前执行门

当前可信双人 Role 标签数为 0。收到两位审阅者独立回复并通过原有共识与样本门之前，不运行模型、不创建正式结果目录。满足标签门后，先按以上指令和共享输入约束生成独立预注册配置，再执行不重叠的 Smoke 与 Full。

## 关联资料

- [FK 映射 Pilot 设计审计](p0_fk_mapping_rank_pilot_design_audit_20261106.md)
- [FK 映射 Pilot 输入语义审计](p0_fk_mapping_rank_pilot_input_semantics_audit_20261106.md)
- [P1.6 冻结基线报告](../reports/p1_6_rebaseline_20261018_01/README.md)
- [G0-02 合成映射探针报告](../reports/g0_fk_instance_node_20261024_02/README.md)