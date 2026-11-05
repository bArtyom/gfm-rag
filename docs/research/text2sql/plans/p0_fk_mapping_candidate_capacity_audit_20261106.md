# FK 映射 Pilot：候选样本容量审计

**状态：已登记，尚未运行。** 这是同一 FK 映射排序核心假设的样本可行性前置审计，不新增模型假设，不读取审阅回复，不生成新盲审材料。

## 动机

现有盲审包包含 49 个问题、51 个问题×表对。只按私有 manifest 中的候选身份数量做匿名计数，51 对中只有 8 对包含至少两个不同的有效 FK 映射，分布在 4 个数据库；候选 pilot 的 Full 门要求排除 5 个问题级 Smoke 后至少有 20 个可区分映射对。因此现有包即使标签全部达成共识，也不可能满足 20 对门槛。A/B 回复文件未变化；此前和本审计均不读取回复内容。

这个审计检查完整冻结 BIRD dev FK/Join 候选总体中是否有足够的**表对级**歧义样本。它解决盲审材料的抽样覆盖问题，不降低原 Pilot 的标签一致性、20 个可区分映射、30 个可裁定问题×表对、3 个数据库或模型效果阈值。

## 研究问题与预设判据

- **问题：** 在现有 1,534 题 BIRD dev 和冻结有效 FK 映射中，按参考 JOIN 提取的问题×表对候选池，是否存在足够多的表对，使其具有至少两个不同的有效 FK mapping，可供双人判断后检验 Accepted@1？
- **结构可区分映射对：** 同一问题×表对有至少两个不同、完整且身份稳定的有效 FK mapping。这个定义只说明模型有可排序的备选项，不代表其中哪个 mapping 正确。
- **容量必要条件：** 全体候选池至少包含 30 个有 FK mapping 的问题×表对、至少 20 个结构可区分映射对，并覆盖至少 3 个数据库。它是继续准备盲审包的必要条件，不是标签门或 Full 启动许可。
- 如果全体上限低于任一必要条件，停止当前 BIRD dev mapping Pilot，不降低阈值、不追加模型实验。如果达到必要条件，只说明可继续设计一个新的、独立版本的盲审包；仍须在真实双人回复后重新检查共识，以及排除 Smoke 后的 30/20/3 样本门。
- 同一问题可含多个表对；计算按问题聚类保留其关联，不把各表对假设为独立问题。

## 输入与计算

- 数据固定为已登记 BIRD dev、SQLite FK artifact、canonical P1.5 全量 SQL 解析记录及其 question crosswalk；预期 SHA-256 沿用已发布盲审包配置，执行时由现有冻结加载器逐项验证。
- 复用盲审材料生成器中的 `load_frozen_inputs`、`parse_target_pairs` 和有效 FK identity 规则。对所有冻结的 JOIN-on 问题提取参考 SQL 所涉及的表对，再统计该表对在 SQLite 中的不同有效 FK mapping 数。
- 汇总题数、问题×表对数、候选数直方图、至少一个 mapping 的对数、至少两个 mapping 的对数、涉及的问题数和匿名数据库覆盖。报告 5 个问题级 Smoke 移除后候选容量的范围；不选 Smoke 样本、不依标签筛选、不生成预测。
- 只写匿名聚合、输入哈希、代码版本和资源用量。禁止输出问题/数据库 ID、SQL、表列名、mapping ID、逐题行或审阅包内容。A/B 回复表及盲审 packet 内容均不读取。

## 环境、预算与停止规则

- CPU-only，复用 `think2sql_20260909`（Python 3.12.14、SQLGlot 28.0.0）；最多 8 线程、300 CPU 秒、600 秒 wall、4 GiB RSS。
- 不调用 GPU、模型、API，不执行 SQLite 查询、不训练、不安装依赖、不下载资源。
- 输入 SHA 或数量不符、解析器运行异常、资源超限或匿名输出约束不满足时立即停止；不在本运行内修补后重跑。
- 独立运行 ID：`p0_fk_mapping_candidate_capacity_20261106_01`；本地私有聚合写入新的专用 results 目录和日志，不覆盖现有 blind-review 或历史 P0 结果。

## 结果解释边界与后续

此审计只回答样本容量是否足以准备盲审，不回答人类接受集合、G-reasoner 排序能力、JOIN 语义正确率或跨库泛化。即使容量充足，仍需两名审阅者独立完成标签、映射集合和置信度后，才可按既有规则裁定可用分母。

如果容量不足，记录为 BIRD dev 结构样本限制并停止该 pilot。若容量充足，下一步是预注册新的 pair-level blind-review packet 版本；保留当前 packet 与回复文件原样，不替换、不覆盖，也不联系审阅者。

## 关联记录

- [FK 映射 Pilot 设计审计](p0_fk_mapping_rank_pilot_design_audit_20261106.md)
- [FK 映射 Pilot 输入语义审计](p0_fk_mapping_rank_pilot_input_semantics_audit_20261106.md)
- [原双人盲审报告](../reports/p0_fk_disagreement_blind_review_20261105_01/README.md)
- [原盲审材料执行器](../../../../scripts/text2sql/prepare_p0_fk_disagreement_review_packet.py)