# FK 映射排序 Pilot：输入语义与起点规则审计

**状态：实现边界澄清；不是正式实验注册，也未运行模型。** 本文只补足现有 Pilot 候选中未冻结的起点语义。真实运行仍必须等待两位审阅者独立回复并通过标签门。

## 为什么需要澄清

现有候选任务是在给定一个由参考 JOIN 得出的表对及其声明 FK 候选时，评价模型能否排出审阅者接受的映射。它是条件式映射排序，不能代表端到端表发现或 JOIN 推断。

官方 `GFMRetriever.prepare_input_for_graph_retriever` 从 NER/EL 结果构造 `start_nodes_mask`；`GraphReasoner.forward` 将该 mask 与 Query 表示共同送入图网络。现有 G0 合成探针则固定从 FK 的 source table 起步。真实表对没有一个对所有 FK 候选都通用的 source 方向：若每个候选各用自己的 source table 作起点，候选之间的模型输入就会不同，分数差异会混入起点变化。

## 起点方案及选择

1. **每个 FK 候选从自身 source table 起步：不采用。** 这会让候选的初始节点随候选改变，不能隔离映射节点的排序效果。
2. **按稳定表名顺序只选一个端点起步：不采用。** 输入虽固定，但任意方向会对反向 FK 带来额外偏差。
3. **表对两端同时作为起点：冻结为候选 Pilot 方案。** 每个问题×表对只建一张 pair graph；其两个端点 table node 在二值 `start_nodes_mask` 中均设为 1，所有候选映射共享同一个 mask。该设置直接对应“给定表对后排序映射”的条件任务，也避免使用审阅标签选择起点。

这是对本地映射排序任务的输入定义，不等同于官方 GFM-RAG 的 NER/EL 在线流程。报告必须把两者区分开；不把结果称为端到端 GFM-RAG，也不外推为自然问题到 JOIN 的全链路效果。

## 候选图与评分输入

- 每个问题×表对的图只含该表对的两个 table node、该表对全部有效声明 FK mapping node，以及对应的四类有向端点关系。每个 mapping node 的方向仍按实际 FK child/parent 记录；两端同时起点不会抹掉关系方向。
- mapping node 使用稳定的完整有序列映射 ID。复合 FK 作为一个完整候选；相同的重复声明按唯一 mapping identity 合并，重数只作审计元数据，不复制为额外排名候选。
- Query embedding、table/mapping 文本、1024 维输入和官方冻结 checkpoint 沿用现有 G0/Pilot 配置。Gold 或人工接受集合只供评价器读取，不生成节点、边、文本、seed 或模型输入。
- 主比较为 reified G-reasoner 对同 Query、同映射文本、同候选集合的 Dense Cosine。BM25 和 query-independent 结构排序作为次级控制。所有方法按同一问题×表对单独排序；不跨图比较未经校准的原始分数。
- Smoke 按问题级固定抽取；被抽中的问题所含全部表对都从 Full 排除。Smoke 不计入正式指标。

## 解释边界与执行门

- 表对来自参考 JOIN，因此试验给定了参考 JOIN 的端点。它只检验已给定端点下的 FK mapping discrimination，不检验表对发现、缺失 FK 推断、无 FK JOIN、SQL 执行或跨数据库泛化。
- 两个 binary seeds 与官方 `start_nodes_mask` 的张量接口兼容；本轮没有运行该真实数据 forward。其分布不完全等同于某次真实 NER/EL 输出，这是此条件式 Pilot 的明示输入，不声称是 checkpoint 原始推理流程的逐步复现。
- 现有 G0 探针把 start index 固定为 0，只适用于原合成 fixture。未来 Pilot runner 必须按表对建立共享 seed mask；不可直接复用该固定索引并声称完成真实映射评测。G0 历史代码和结果保持不变。
- G0-02 的 GFM 2/4、Dense 4/4 是该合成 fixture 的动机证据；由于图、样本和 seed 设定不同，不与真实 Pilot 的分数或准确率直接合并比较。
- 两位真实审阅者的决定、映射集合和置信度必须先独立完成并达成冻结共识。排除 Smoke 问题后，至少需要 30 个可裁定问题×表对、20 个可区分映射对、覆盖至少 3 个数据库，才可另行正式注册并运行。未达到时只报告标签覆盖，不启动模型。
- 正式运行时重新检查数据/模型 hash、环境、GPU、内存、CPU、磁盘与输出目录。Conda 环境必须使用已验证的 Python 3.12 绝对路径；普通 `conda run ... python3` 曾解析到 Python 3.9，不能照搬旧失败命令。
- 原设计审计的比较、指标和停止门保持不变：主指标为可区分集合上的 Accepted@1；至少比 Dense 高 5 个百分点、净救回至少 4 个问题×表对，并在至少两个各自有不少于 5 个可区分样本的数据库中净救回方向为正，才升级为独立复现候选。此门只作小样本筛查，不作确认性显著性结论。

## 依据

- 上游 `RManLuo/gfm-rag`：commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；`gfmrag/gfmrag_retriever.py` 中 `prepare_input_for_graph_retriever` 使用 NER/EL 结果构造 seed mask；`gfmrag/models/gfm_reasoner/model.py` 的 `GraphReasoner.forward` 消费 `start_nodes_mask` 与 `question_embeddings`。
- 本仓库 G0-02：`scripts/text2sql/g0_fk_instance_node_probe.py` 中 `run_forward(..., start, ...)` 为合成查询固定传入单个起点；报告显示 GFM 2/4、Dense Cosine 4/4。该结果不作为真实 Role 表现。
- 主候选与成功门：[FK 映射 Pilot 候选](p0_fk_mapping_rank_pilot_candidate_20261105.md)、[设计审计](p0_fk_mapping_rank_pilot_design_audit_20261106.md)。

## 当前状态

本次仅做代码/协议核对和输入语义冻结，没有读取审阅回复内容，没有运行模型、SQL、GPU 或 API，也没有创建正式运行目录。回复文件元数据仍是材料生成时的状态，可信双人标签为 0。下一项可运行工作仍取决于两位真实审阅者提交独立标签。
