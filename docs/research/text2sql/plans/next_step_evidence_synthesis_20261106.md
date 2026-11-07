# 下一阶段决策：停止当前 BIRD-dev GFM 排序支线，转入证据综合

**日期：2026-11-06。性质：路线决策与结果综合，不是新实验。** 本记录落实用户选择的本地模型审阅路线，并根据截至本日已归档结果判断下一步。此轮没有运行模型、SQL、GPU 或外部模型 API。

## 决策

当前 BIRD-dev FK mapping 排序支线停止扩展。暂不继续增加代理审阅模型、调整 seed/图结构、扫描参数或另跑相同标签上的排序实验。下一阶段先综合已经取得的结果，再从仍未解释的错误类别中寻找一个与现有方法和近期工作有明确区别的新核心假设。

原因是：模型代理标签上的 G-reasoner 排序明显落后于 Dense；错误分层没有找到 G-reasoner 占优的可见子群；seed 变化只改变部分排序，无法判定变化是否正确。继续在同一 BIRD-dev 子集上变体搜索不会补上独立标签、独立数据或下游效用证据，且触发实验守则 §14 的连续无结论变化停止规则。

## 用户选择模型审阅后的实际结果

- 两个本地 Qwen 审阅模型的高置信一致单元少于排序诊断所需门槛，因此首次代理审阅停止，没有进入排序。
- 后续按单独预注册方案增加 Gemma 4 E4B-it。GPU 初始化因 PyTorch/CUDA 版本不匹配失败；CPU 恢复完成 Smoke 5/5 与 Full 60/60。三模型高置信精确多数为 56 个；排除预先选定的 Smoke 问题后，保留 51 个可裁定、38 个可区分单元，覆盖 4 个匿名数据库。
- 唯一获准的探索性排序诊断已完成：G-reasoner Accepted@1 为 7/38（18.42%），Dense Cosine 为 27/38（71.05%），差 −52.63 个百分点；配对净救回为 −20，4 个数据库均没有 G-reasoner 正向净救回。
- 这条路线仍有 0 个可信人工 Role 标签。三模型多数只能叫“模型代理标签”，不能用于宣称人工 FK Role 准确率，也不能把原双人审核门改成已通过。

详细来源：[双模型分歧审计](../reports/p0_fk_model_review_disagreement_audit_20261106_01/README.md)、[第三模型 CPU 恢复报告](../reports/p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/README.md)、[代理排序报告](../reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/README.md)、[代理错误分层报告](../reports/p0_fk_mapping_proxy_error_analysis_20261106_01/README.md)。

## 痛点与证据

| 痛点 | 已做的对照或改动 | 结果 | 能说明什么 |
|---|---|---|---|
| Schema 在固定 token 预算下不完整 | P2c-R 保持候选排序，用较短的返回表示提高预算内覆盖 | Complete Schema@1024 从 56.64% 到 67.60% | 改善了离线覆盖；尚未证明 SQL EX 提高 |
| 检索内容是否限制 SQL 修复 | P2d.3 比较 A0 不修复、A1 可见完整 Schema 修复、A2 仅使用 V00 上下文并用 SQLite authorizer 拒绝越界字段 | Set EX 为 18/66、20/66、17/66；A2−A0 为 −1.52pp；A2 拒绝 8 个越界字段提案，未接受越界读取 | 当前一次上下文受限修复没有达到效用门；安全边界有效不等同于准确率提升 |
| 失败是否由缺少 Schema 字段造成 | P2d.2 对 28 个封存失败作静态归因 | 10 个解析/结构问题、13 个限定符/作用域问题、4 个不存在标识符、1 个误用可见字段；没有“失败字段不在提示上下文”案例 | 旧样本中的主要故障在 SQL 生成结构和名称/作用域使用，不是检索缺字段 |
| GFM 关系传播是否改善 FK mapping 排名 | 冻结 checkpoint、同一 Qwen3 Query/mapping 向量，对比 G-reasoner 与 Dense | 代理可区分集为 7/38 对 27/38；分层中没有已观察到的正向 GFM 子组 | 当前任务适配设定没有正向排序证据；不代表人工标签下的最终性能，也不证明 QuadGraph 原方法无效 |
| 起点选择会不会影响 GFM 分数排序 | G3 仅改 `start_nodes_mask`，比较双端与两个单端 seed | Top-1 改变 4/55 与 6/55，候选对反转 6/81 与 7/81；未达到机制信号门或无影响门 | 排序对 seed 有一定敏感性，但无标签时不能知道变动是变好还是变坏；按预注册停止 |

完整历史与分母见 [P2c-R 报告](../reports/p2c_r_recovery_20261019_01/README.md)、[P2d.2 失败归因](../reports/p2d2_frozen_failure_attribution_20261105_02/README.md)、[P2d.3 报告](../reports/p2d3_context_bounded_repair_20261105_01/README.md)、[G3 报告](../reports/g3_fk_seed_direction_sensitivity_20261106_01/README.md)。

## 候选实验筛选

| 候选 | 决定 | 依据 |
|---|---|---|
| 在同一代理标签上继续调 GFM、换 seed 或加图结构 | 停止 | 排序主比较明显负向；可见结构分层无正向子组；G3 已执行一次且为 inconclusive |
| 再增加一个模型审阅者以“确认”代理标签 | 停止 | 三模型已足以通过一次探索排序的数据门，但结果仍只能代表代理共识；更多模型票不能建立人工真值 |
| 继续调 Schema packing、检索方向或 context repair | 不登记 | 本项目已有覆盖/效用对照；广义预算与双向 Schema retrieval、双 Schema 生成及执行反馈已有近期近邻 |
| 继续做通用 SQL 修复或静态校验 | 不登记 | 本项目修复增益未过门；Post-SQLFix、SCOPE-SQL 等已研究相邻的静态诊断、作用域和修复机制 |
| 为新问题另开研究线 | 暂缓实验，先做文献与失败案例综合 | P2d.2 的结构/作用域错误是可核验痛点，但需先证明拟议干预与现有诊断修复方法有明确差异，再制定独立数据和评价方案 |

近期近邻用于限制新颖性主张，而非声称任务完全相同：[BudgetSchemaBench](https://arxiv.org/abs/2610.00092)、[DSR-SQL](https://aclanthology.org/2026.emnlp-main.1688/)、[Rethinking Schema Linking](https://aclanthology.org/2026.findings-eacl.236/)、[Post-SQLFix](https://arxiv.org/abs/2610.41472)、[SCOPE-SQL](https://aclanthology.org/2026.findings-emnlp.951/)。

## 下一步与重新开启条件

1. 当前线进入错误模式综合与方法整理，不再启动本方向的 GPU 或模型实验。
2. 如果目标仍是声称“正确 FK Role”，只有独立、可信的标签流程才能解锁新准确率实验；模型代理结果不替代人工真值。原双人审阅门与模型代理结果分开保存。
3. 如果要提出新的 Text2SQL 方法，先围绕一个可改变论文主结论的失败机制提出假设，再做近邻文献核验与最小证伪设计。不能把通用 Schema 变体、更多代理投票或通用 SQL 修复重新命名为新方法。
4. 新提案至少明确：受影响失败类别、相对最强基线的机制差异、独立评价数据、配对指标、成功门、资源预算及停止条件；满足后再单独预注册并执行 Smoke。

当前决定是“停止本支线并综合”，不是“研究目标已完成”。

## 2026-11-07 补充：SQL-used 评测样本对齐诊断

针对 11 月 7 日 `_02` 的 0/5 Smoke，仅新增一次预注册的 CPU-only 候选—SQL 身份对齐诊断。它复用原 60 个问题×表对，不改变 G-reasoner、Dense、BM25、模型代理审阅或排名；独立抽取参考 SQL 的限定显式 JOIN 等式并与候选 FK 身份/旧 matcher 比对。Full 结果为 60/60 目标表对都没有出现在对应 SQL 的显式 `JOIN ON` 等式中；76/76 个限定等式解析成功，独立身份匹配与旧 matcher 在60/60一致，均无匹配 ID。WHERE/USING 不属于已登记标签规则，因此结论限定为“该样本与显式 SQL-used 目标不对齐”，不推断所有 SQL 表达中均不存在该表对，也不涉及模型排名效果。

该诊断解释了 `_02` 为什么没有可评分映射，但不改变代理标签排名 7/38 对 27/38、人工 Role 标签数为0、G3 inconclusive 或 P2d.3 NO-GO。按实验守则结束这批样本的 SQL-used 排名扩展，继续进入方法/错误模式综合。若未来重启条件式 FK 排序，必须重新从可解析的 SQL JOIN 目标构造并冻结样本、复核候选身份覆盖，另立预注册；仍需把它称为已知 SQL 表对条件下的 mapping 排序，不可冒充端到端 JOIN 发现或真实业务 Role 准确率。

完整数据边界和下一轮候选见[SQL-used 对齐诊断报告](../reports/p0_fk_candidate_sql_identity_alignment_20261107_01/README.md)。

## 2026-11-07 补充：冻结 SQL-used 排名的同实例输出等价重评分

针对“SQL-used 单 mapping 是否把结果标签定得过窄”这一未决解释，单独预注册只读重评分；没有重跑排名器、模型、SQL 或 GPU。静态实例审计的94个完整非空单元中，5个固定 Smoke 排除后，Full 为89个。SQL-used 单目标口径的 G-reasoner/Dense Mapping@1 为33/89对55/89；允许 Bag 相同替代 mapping 后为63/89对80/89。两者差距由−24.72pp缩小至−19.10pp，变化+5.62pp，通过登记的评价敏感性门，但 G-reasoner 仍落后 Dense，方向没有反转。

这说明目标唯一性影响负结果的**幅度**，不足以把它解释成 GFM 收益或语义等价。实例 Bag 相等仅描述冻结数据内容；替代项高度集中在部分匿名数据库。通用 test-suite / 合成数据库 / 等价验证已是相邻研究主题，本结果不支持提出通用静态实例等价方法。经此重评分，当前 BIRD-dev GFM 排序支线仍停止调参和结构变体，转入错误证据综合；任何后续要改变论文结论的 FK mapping 工作，需要独立数据库内容证据或可信人工 Role 标签。详见[重评分执行报告](../reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/README.md)及[匿名 Full 汇总](../reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/aggregate_summary.json)。
