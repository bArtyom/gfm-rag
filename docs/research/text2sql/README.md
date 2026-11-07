# Text2SQL × QuadGraph / G-reasoner：研究工作台

> **模型代理审阅进度（2026-11-07，Full 尚未启动）**：Amendment 001 已准备好 138 个问题×表对单元、369 个完整 FK constraint 候选，A/B packet-only preflight 通过。模型 Smoke/Full 尚未运行：06:16 UTC 最近检查时 GPU1/GPU2 分别只有 3,853/3,039 MiB 可用且利用率98%/99%，未加载模型。GPU3 也只有 1,041 MiB 可用、利用率77%；此前曾短暂空闲，但未用于本实验。模型仍按冻结协议分配到 GPU1/GPU2。中间报告与状态见[审阅报告](reports/p0_bird_train_fk_model_proxy_review_20261107_01/README.md)、[Amendment 001](plans/amendments/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.md)。

> **2026-11-07 模型审阅准备状态更新**：首个本地 packet-preparation run 在冻结输入哈希通过后因配置字段路径错误停止；未生成 packet、未加载模型，也无 token 消耗。Amendment 001 只修复读取路径并使用新的准备 run ID；Smoke/Full 模型 run 尚未启动。见[Amendment 001](plans/amendments/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.md)和[修订配置](../../../configs/text2sql/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.json)。

> **2026-11-07 BIRD train FK constraint identity Full 完成：容量门通过**。Amendment 001 recovery Smoke/Full 后，379/379 个表对列集合与 SQLite PRAGMA 精确一致；138 个问题×表对有至少2种不同的完整 FK 约束，覆盖8个匿名数据库，超过预设60/4门。首次 Full 的 Smoke 收据比较错误已保留；恢复只修预检并使用新 run ID。无模型、GPU、SQL执行或 API 调用。用户选择以本地模型作审阅代理，已为这138个单元另行预注册模型代理审阅；尚未启动模型或 G-reasoner 排序。见[完整报告](reports/p0_bird_train_fk_constraint_identity_20261107_01/README.md)、[匿名Full汇总](reports/p0_bird_train_fk_constraint_identity_20261107_01/aggregate_summary.json)、[Amendment 001](plans/amendments/p0_bird_train_fk_constraint_identity_20261107_amendment_001.md)及[模型审阅注册](plans/p0_bird_train_fk_model_proxy_review_20261107_01.md)。

> **2026-11-07 FK mapping 证据综合完成**：BIRD-dev SQL-used rank 中 G-reasoner 43/108、Dense 63/108（−18.52 pp）；Bag 接受集重评分缩小差距但未反转；Spider 官方 test 只有52个合格单元，低于冻结60门。BIRD train 列对容量审计得到384个上界单元/12库，不是384个独立 FK constraint。现已预注册只读 PRAGMA constraint identity 核验；用户选定的模型审阅只有在该门通过后才作为代理标签运行，不当作人工共识。见[证据综合](synthesis/fk_mapping_evidence_synthesis_20261107.md)、[容量报告](reports/p0_bird_train_fk_mapping_capacity_20261107_01/README.md)和[constraint identity 预注册](plans/p0_bird_train_fk_constraint_identity_20261107.md)。

> **BIRD train 列对容量阶段记录**：train/dev schema 库 ID 交集0；Full解析9,423/9,423、scope错误0，得到384个列对上界单元/12库。后续独立约束身份 Full 在379个非Smoke单元上精确对齐，筛出138个多约束单元/8库；两阶段分母不同，384仍不是独立约束数。容量审计原报告见[执行报告](reports/p0_bird_train_fk_mapping_capacity_20261107_01/README.md)和[匿名汇总](reports/p0_bird_train_fk_mapping_capacity_20261107_01/aggregate_summary.json)。

> **2026-11-07 Spider 独立迁移容量审计停止**：按预注册完成只读 Full，2,142题 SQL 解析率100%、scope错误0，但仅有52个多FK问题×表对单元，覆盖4个匿名库，低于60单元门槛。未运行本地模型审阅或G-reasoner/Dense排序，也没有GPU或token消耗；不事后降低门槛。该结果只说明本次固定Spider切片容量不足，不是方法负结果。见[执行报告](reports/p0_spider_fk_mapping_candidate_capacity_20261107_01/README.md)、[匿名聚合](reports/p0_spider_fk_mapping_candidate_capacity_20261107_01/aggregate_summary.json)、[预注册](plans/p0_spider_fk_mapping_candidate_capacity_20261107.md)和[Amendment 001](plans/amendments/p0_spider_fk_mapping_candidate_capacity_amendment_001.md)。

> **2026-11-07 SQL-used mapping 目标敏感性重评分完成**：在89个共同完整单元上，按 SQL-used 单目标计分时 G-reasoner/Dense 为33/89对55/89；允许当前 SQLite 实例上 Bag 相同的替代 FK mapping 后为63/89对80/89。相对差距缩小5.62pp，达到预设评价敏感性门，但 G-reasoner 仍低19.10pp，方法排序没有反转。该口径只表示同一静态实例的结果 Bag 相同，不是SQL语义等价、人工Role或跨实例证据；停止本批候选的调参和图变体，转错误证据综合。详见[完整报告](reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/README.md)、[匿名 Full 汇总](reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/aggregate_summary.json)、[注册方案](plans/p0_fk_mapping_output_equivalence_rescore_20261107.md)和[Amendment 001](plans/amendments/p0_fk_mapping_output_equivalence_rescore_amendment_001.md)。

> **2026-11-07 SQL-used FK mapping ranker 已完成，正向筛选失败并停止**：Amendment 002 的 GPU Smoke 5/5、Full 108/108；G-reasoner Mapping@1 为 43/108（39.81%），Dense 为 63/108（58.33%），差 −18.52pp，配对净救回 −20。未达到预注册门，不继续同一 BIRD-dev 数据上的调参或图变体。Amendment 004 的唯一 CPU Smoke 为 0/5，在 RSPMM 报 `No CUDA GPUs are available`，CPU 恢复线关闭。用户选择的 Qwen A/B 结果是模型代理审阅（高置信精确一致 2/5），不是人工 Role 标签；主排序标签由 SQL 派生。见 [GPU Full 报告](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/README.md)、[GPU 匿名聚合](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/aggregate_summary.json)、[CPU 失败报告](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/README.md)及[CPU 匿名摘要](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/aggregate_summary.json)。

> **2026-11-07 FK-domain 原生核验完成**：Smoke 5/5，Full 32/32 候选对与 SQLite PRAGMA 一致；两阶段都只有同一匿名库的2个唯一FK声明，其中1个声明49行违规，另1个为0。没有PRAGMA错误，数据库哈希未变。该结果核验的是旧筛选器语义，不是图传播或排序收益；原shuffle支线按门槛关闭。详见[完整报告](reports/p0_fk_domain_violation_crosscheck_20261107_01/README.md)、[匿名聚合](reports/p0_fk_domain_violation_crosscheck_20261107_01/aggregate_summary.json)、[预注册方案](plans/p0_fk_domain_violation_crosscheck_20261107.md)。

> **2026-11-07 多 FK 映射实例级可区分性审计完成：正向实例不可区分信号**。Full_002 的94个完整非空单元中，54个至少有一个合法替代 FK mapping 在当前 SQLite 实例上与 Gold SQL 的 Bag 相同（57.45%，Wilson 95%区间47.35%–66.96%），覆盖4个匿名数据库。信号集中于DB-B/DB-D；不能解释为通用 SQL 等价、业务 Role 正确或 GFM 排名收益。旧 Full_001 启动环境错误与 runner 结构中止均保留，Recovery 的唯一 amendment 未改样本、候选、SQL变换、只读 evaluator 或阈值。见[报告](reports/p0_fk_mapping_instance_equivalence_20261107_01/README.md)、[匿名汇总](reports/p0_fk_mapping_instance_equivalence_20261107_01/aggregate_summary.json)、[方案](plans/p0_fk_mapping_instance_equivalence_20261107.md)和[Amendment 001](plans/amendments/p0_fk_mapping_instance_equivalence_amendment_001.md)。

> **2026-11-07 SQL-used FK mapping 独立注册 03：执行停止，主排序无指标**。CPU 数据门通过，生成5题 Smoke和108题 Full（4库）；Qwen A/B 各有5/5有效输出，但高置信精确一致为2/5，未达到4/5，模型 Full 按规则停止。G-reasoner Smoke 因 CPU manifest 缺少运行器校验的样本计数字段，在模型导入前停止；无Embedding/G-reasoner前向或排名指标。失败 run ID 不重用。详见[完整报告](reports/p0_fk_sql_used_mapping_rank_20261107_03/README.md)和[匿名聚合](reports/p0_fk_sql_used_mapping_rank_20261107_03/aggregate_summary.json)、[预注册方案](plans/p0_fk_sql_used_mapping_rank_20261107_03.md)、[主配置](../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json)及[模型审阅配置](../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_model_review.json)。
> **Amendment 004 CPU 恢复已关闭**：唯一 5-unit Smoke 在 RSPMM 阶段以 `No CUDA GPUs are available` 失败，0/5 排序完成，Full 未运行。离线导入和模型加载诊断不等于 CPU 前向可行；不再重试本 CPU 线。用户选择的 Qwen A/B 仍是次要模型代理，2/5 高置信精确一致未达原门；主标签来自 SQL。见[Amendment 004 计划](plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.md)、[配置](../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.json)、[失败报告](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/README.md)和[匿名摘要](reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/aggregate_summary.json)。

> **2026-11-07 独立注册 02 已停止（来源提交门失败）**：CPU_001 的启动参数把本地 HEAD SHA 抄错，运行器在任何输入哈希或 SQL 读取前以 `SOURCE_COMMIT_MISMATCH` 停止。没有样本、模型审阅或排名结果；按停止规则不重放该 run ID。完整报告见[执行报告](reports/p0_fk_sql_used_mapping_rank_20261107_02/README.md)和[匿名聚合](reports/p0_fk_sql_used_mapping_rank_20261107_02/aggregate_summary.json)。用户选择的 Qwen A/B 次要代理审阅已写入预注册，但未运行。

> **2026-11-07 新实验状态：输入门终止**。CPU_001 与 Amendment 002 唯一恢复 CPU_002 均在解析数据前因 exclusion-manifest 哈希不匹配停止。CPU_002 的登记值与文件实测值一位不同；Amendment 002 中“独立哈希匹配”的字段是登记抄录错误。没有样本、模型审阅或排名结果，且不再重试。详细结果见[匿名执行报告](reports/p0_fk_sql_used_mapping_rank_20261107_01/README.md)与[聚合结果](reports/p0_fk_sql_used_mapping_rank_20261107_01/aggregate_summary.json)。方案与错误更正见[主方案](plans/p0_fk_sql_used_mapping_rank_20261107.md)、[Amendment 001](plans/p0_fk_sql_used_mapping_rank_20261107_amendment_001_model_review.md)和[Amendment 002](plans/p0_fk_sql_used_mapping_rank_20261107_amendment_002_hash_gate_recovery.md)。
> **最新决策（2026-11-06）**：用户选择的本地模型审阅代理路线、一次 G-reasoner 排序诊断、起点敏感性诊断及错误分层均已完成。代理排序为 7/38 对 27/38，错误分层未发现正向子群；G3 为 inconclusive。按停止规则，当前 BIRD-dev GFM 排序支线不再扩展，进入错误模式综合和新问题筛选。模型标签仍不是人工 Role 真值。见[下一阶段决策记录](plans/next_step_evidence_synthesis_20261106.md)。
> **2026-11-07 有界复核注册 01 已停止**：针对同一代理排序结果，原计划用原 BIRD dev 参考 SQL 显式 `JOIN ON` 映射复核 55 对冻结排名，但 Smoke 在任何输入读取前因输出目录预检失败而停止。无 SQL 解析或排名指标；旧注册不重跑。见[方案](plans/p0_fk_sql_used_proxy_alignment_20261107.md)、[配置](../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107.json)及[执行报告](reports/p0_fk_sql_used_mapping_alignment_20261107_01/README.md)。
> **2026-11-07 独立注册 02 执行结果**：CPU Smoke 5/5 SQL 解析成功、8/8 限定 JOIN 等式解析成功且无 scope error，但冻结候选映射命中 0/5，未达到 4/5 门槛；Full 未运行，没有排序指标。按预注册停止，不重试。见[计划](plans/p0_fk_sql_used_proxy_alignment_20261107_02.md)、[匿名汇总](reports/p0_fk_sql_used_mapping_alignment_20261107_02/aggregate_summary.json)和[完整报告](reports/p0_fk_sql_used_mapping_alignment_20261107_02/README.md)。
> **2026-11-07 候选—SQL 对齐诊断完成**：60/60 个冻结问题×表对都没有出现在对应参考 SQL 的显式 `JOIN ON` 等式中；76/76 个 SQL 限定 JOIN 等式解析成功。直接 FK 身份匹配与旧 matcher 在60/60一致，均未找到候选映射 ID。结果说明旧 SQL-used 评价目标与这批审阅问题×表对不对齐，不是 G-reasoner 排名结论。WHERE 等式和 USING 不在本轮标签定义中。详见[报告](reports/p0_fk_candidate_sql_identity_alignment_20261107_01/README.md)和[匿名汇总](reports/p0_fk_candidate_sql_identity_alignment_20261107_01/aggregate_summary.json)。Amendment 001 在 Full 前补上预注册的完整解析门，记录见同一报告。
> **随后的一次有界迁移筛查（2026-11-06）**：原注册 `_01` 在 CPU 输入哈希门停止；尚未解析 SQL、生成标签或加载模型。失败原因为 schema SHA-256 预注册值误录，且环境命令解析到了 Python 3.9。Recovery `_02` 使用独立 run IDs 和正确环境后解析 500/500 SQL，但 Full 列标签只有 340/495，低于450门槛；Qwen/G-reasoner、GPU Smoke 和 Full 均未运行。报告：[运行 `_01`](reports/gfm_minidev_schema_retrieval_transfer_20261106_01/README.md)、[Recovery `_02`](reports/gfm_minidev_schema_retrieval_transfer_20261106_02/README.md)及[聚合结果](reports/gfm_minidev_schema_retrieval_transfer_20261106_02/aggregate_summary.json)。环境和独立注册见[基础方案](plans/gfm_minidev_schema_retrieval_transfer_20261106.md)、[Amendment 001](plans/gfm_minidev_schema_retrieval_transfer_20261106_amendment_001.md)和[Recovery 配置](../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106_02.json)。

> **2026-11-06 后续迁移诊断已停止，无科学结果**：原始 Smoke `_001` 误用了 Python 3.9；唯一恢复 Smoke `_002` 用上正确环境后，在 checkpoint 配置哈希核验处发现预注册 SHA 少一个字符并停止。两次都没有载入 Qwen/G-reasoner、没有 token、没有 GPU 前向；Full 未运行，主假设未检验。按 Amendment 1 停止规则不再重试。见[完整失败报告](reports/gfm_schema_retrieval_transfer_20261106_01/README.md)、[匿名汇总](reports/gfm_schema_retrieval_transfer_20261106_01/aggregate_summary.json)、[方案](plans/gfm_schema_retrieval_transfer_20261106.md)和[Amendment 1](plans/gfm_schema_retrieval_transfer_20261106_amendment1.md)。

> **唯一主仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)。生效日期：2026-10-16。**
>
> 此目录管理该研究线的**想法、论文核对、实验方案、实现决策、结果分析及下一轮指导**。之前的 [`bArtyom/quadrag`](https://github.com/bArtyom/quadrag) 仅作历史来源，不再向其提交新的研究方案或结果。保留旧仓库历史，不强制删除。
>
> **最新决策（2026-10-24，P0证据复核后）**：P0只读复核的88/88输入指纹、3/3历史产物/模型配置指纹及聚合计数均通过；结果支持在重复使用的BIRD dev上复现表/列清单。Role Gate仍为**NO-GO**：174个多FK候选未盲审，可信双人标签为0；FK schema来源差异和身份碰撞仍需保留。G0-02仍为**G0_SYNTHETIC_NO_GO**（GFM 2/4、dense 4/4），G2-A PASS仅说明非对称合成fixture上关系输入能改变分数。不得启动P1角色准确率/维度扫描或SQL扩样。下一步需要先建立受控的双人盲审标签；任何后续G0都须基于明确的FK身份策略另行预注册。见[P0复核报告](reports/p0_bird_dev_evidence_reconciliation_20261024_01/README.md)、[G0-02最终报告](reports/g0_fk_instance_node_20261024_02/README.md)和[实验路线图](experiment-roadmap.md)。

> **2026-11-05 状态补充**：相同 BIRD dev 输入哈希下，历史 P0 v3、P1.5/P2a.5 与 P0 packet 报告的 JOIN/FK 汇总分别为 **956/174、970/197、1043/176**（FK 匹配题/多 FK 候选题）。定义对账中两种环境的 P0 packet 五题 Smoke 通过；P1.5 五题 Smoke 出现 `RuntimeError`，按预注册停止，未启动 Full、未生成 crosswalk 或审阅包，可信角色标签仍为0。详见[FK候选定义对账报告](reports/p0_fk_candidate_definition_reconciliation_20261105_01/README.md)。

> **2026-11-05 恢复轮预注册**：新增安全异常位置回执和独立 run ID，重过三个冻结定义的 5 题 Smoke；只有三臂全过才运行 Full。旧报告和数据定义不改。见[恢复计划](plans/p0_fk_candidate_definition_recovery_20261105.md)与[恢复报告](reports/p0_fk_candidate_definition_recovery_20261105_01/README.md)。

> **2026-11-05 哈希诊断恢复结果**：两组 packet Smoke 通过；P1.5 Smoke 因冻结 artifact SHA 与同一字节缓冲区、分块 helper 及独立 SHA-256 的结果不符而 `STOP_INVALID`。文件身份稳定，JSON 未解析，未启动 Full。见[计划](plans/p0_fk_candidate_definition_recovery_v2_20261105.md)和[结果报告](reports/p0_fk_candidate_definition_recovery_v2_20261105_01/README.md)。

> **2026-11-05 哈希指纹更正 v3 结果（运行后复核修订）**：三组 Smoke、三组 Full 与匿名 crosswalk 已运行；packet 两环境均为 1,043/176，本轮 P1.5 wrapper 输出 970/197。后续代码复核发现 wrapper 传入原始 `instances_private`，canonical P1.5 汇总使用过滤后的 `valid_instances_private`。当时的待办已由下方 canonical crosswalk 新 run ID 完成：过滤后仍为 970/197，逐题标签与未过滤适配器一致；packet/P1.5 差异仍在。可信 Role 标签仍为0。见[v3报告](reports/p0_fk_candidate_definition_recovery_v3_20261105_01/README.md)及[canonical crosswalk报告](reports/p0_fk_canonical_crosswalk_20261105_01/README.md)。

> **2026-11-05 canonical FK crosswalk 复核（完成）**：5题 Smoke、1,534题 Full 与逐题 crosswalk 全部通过。valid-only 过滤没有改变 P1.5 的任何逐题标签或 970/197 汇总；packet-28 的 1043/176 差异仍在，且可分解为实现定义差异，不是 Role 准确率。见[计划](plans/p0_fk_canonical_crosswalk_20261105.md)和[报告](reports/p0_fk_canonical_crosswalk_20261105_01/README.md)。

> **2026-11-05 FK分歧盲审材料生成完成**：Smoke 与 Full 通过，54个分层名额去重为49题、51个问题×表对，五层配额和1,534个问题键对齐均通过。包只在本地私有保存，等待两位真实审阅者独立填写；可信Role标签仍为0，因此不启动Role Accuracy、监督训练或真实JOIN方法实验。该审阅以参考JOIN派生的表对为条件，不是端到端Gold-free评测。见[预注册计划](plans/p0_fk_disagreement_blind_review_20261105.md)及[完整实验报告](reports/p0_fk_disagreement_blind_review_20261105_01/README.md)。

> **2026-11-05 高跳数结构审计状态**：v1 全量后发现 CTE 全局别名过滤的作用域风险；v2 改用 SQLGlot scope-aware parser，Smoke/Full 均通过，匿名聚合与 v1 相同：36/1,534 题 `h≥3`、覆盖5库，77题声明FK图不连通。与 SchemaScope 报告的 BIRD 约22% `h≥3` 差距仍未解释；按预注册停止规则，不追加切片或解析器扫描。此项仅为 CPU-only 数据审计，不是JOIN方法结果，也不解除双人Role标签门。见[v1报告](reports/p0_bird_fk_hop_profile_20261105_01/README.md)、[v2修正方案](plans/p0_bird_fk_hop_profile_v2_correction_20261105.md)和[v2完整报告](reports/p0_bird_fk_hop_profile_20261105_02/README.md)。

> **P2d.3 检索上下文约束 SQL 修复（2026-11-06，完成）**：在与旧 P2d 样本不重叠的66题 Full 上，A0无修复 Set EX 为18/66（27.27%），完整 Schema 一次修复 A1 为20/66（30.30%），V00 上下文约束修复 A2 为17/66（25.76%）。A2 的 8 个越界字段提案均被拒绝，实际接受的越界读取为0；但 A2−A0 为−1.52pp，未达到预注册的 +5pp 提升门，因此本轮 `NO_GO_OR_INCONCLUSIVE`，不扩样。实验只支持这条本地 repair pipeline 的 utility/safety 结论，不代表 QuadGraph/G-reasoner 图传播效果，也不解除可信双人 Role 标签门。见[P2d.2 失败归因](reports/p2d2_frozen_failure_attribution_20261105_02/README.md)、[P2d.3 完整报告](reports/p2d3_context_bounded_repair_20261105_01/README.md)和[匿名聚合结果](reports/p2d3_context_bounded_repair_20261105_01/aggregate_summary.json)。

> **方法变更台账**：为避免把检索、上下文打包、SQL评测和图传播探针混为“QuadGraph方法改进”，逐项列出原方法、实际改动、结果及证据边界，见[方法变更台账](method-change-ledger-20261105.md)。

> **2026-11-06 文献与下一步门更新**：新近的 JoinGR 已覆盖 join-graph 遍历及可选边级监督，MDB-Link 已覆盖分层表/列选择与预算 Schema 构造；当前 FK mapping pilot 只保留为冻结 G-reasoner 的小样本迁移/证伪测试，不主张新算法。旧盲审包的回复元数据仍停留在材料生成时间；另一个面向多 mapping 对的独立 60 单元盲审包已准备完成，尚无审阅标签，模型实验仍停止。见[文献更新与候选门](plans/p0_fk_mapping_rank_literature_update_20261106.md)和[新盲审包报告](reports/p0_fk_mapping_pair_level_blind_review_20261106_01/README.md)。

> **2026-11-06 Pilot 设计审计**：新核对的 Post-SQLFix、CORE-T、DBCC、BASS 与 PASCAL 进一步覆盖通用修复、相干表检索、上下文压缩、预算搜索及交互式证据获取；不新增相邻 SQL 修复或普通 Schema packing 实验。FK 映射 Pilot 的主对照、可区分标签分母、Smoke/Full 不重叠和数据库级成功门已明确；仍须等待两位真实审阅者，未注册、未运行。见[设计审计](plans/p0_fk_mapping_rank_pilot_design_audit_20261106.md)。

> **2026-11-06 Pilot 输入语义澄清**：代码核对发现 G0 合成探针固定从 FK source table 起步，而真实表对的候选 FK 方向可能不同。为避免候选得到不同起点，条件式映射排序 Pilot 暂定将表对两个端点作为所有候选共享的 binary seeds；这不是官方端到端 NER/EL 流程，也未解除人工标签门。见[输入语义审计](plans/p0_fk_mapping_rank_pilot_input_semantics_audit_20261106.md)。

> **2026-11-06 模型审阅代理实验完成**：用户选择由本地 Qwen2.5-Coder-7B 与 Qwen3-4B 分别审阅 A/B 包。Full 有 28 个双方高置信、决定与接受集合完全一致的可裁定单元，低于独立探索排序所需的 30 个；23 个可区分单元、覆盖4库。按预注册规则停止，不运行 G-reasoner 排序、不扩样；这不是人工标签，原可信人工 Role 标签仍为0。见[完整报告](reports/p0_fk_mapping_model_review_proxy_20261106_01/README.md)。

> **2026-11-06 P2d.3 authorizer 候选归因（完成）**：只读回放 6 个初始上下文拒绝与 8 个被拒修复候选；6/6 初始 SQL 在完整 Schema 下可执行、2 条正确；8 个修复候选中 6 条可执行，其中 2 条 Set/Bag 正确，2 条在完整 Schema 编译失败。支持“安全边界拒绝了少量正确候选”这一候选级判断，但不更新 P2d.3 的 A0/A1/A2 系统分数，也不证明取消边界会提升总体 EX。无模型/GPU调用。见[预注册与最终报告](reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md)及[匿名聚合](reports/p2d3_authorizer_counterfactual_audit_20261106_01/aggregate_summary.json)。

> **2026-11-06 Query 指令兼容性审计**：G-reasoner-34M checkpoint/G0 使用的 Query 指令与 P1.6 表列检索指令不同。后续 FK 映射 Pilot 的 G-reasoner 与 Dense 主比较须共享 checkpoint 兼容的 Query 向量和相同映射候选文本；不得直接复用 P1.6 Query cache。本审计不修改 P1.6 历史结果；双人标签仍为0，Pilot 未运行。见[兼容性审计](plans/p0_gfm_embedding_instruction_compatibility_audit_20261106.md)。

> **2026-11-06 FK mapping 样本容量与盲审材料准备完成**：已解析 1,127/1,140 个 JOIN-ON 问题，176 个多映射表对涉及 175 道问题和 4 个数据库。新的 pair-level 盲审包 Smoke 5 题、Full 60 题均通过；Full 为每个匿名数据库 15 题、共 135 个完整 mapping 候选，A/B 候选集合一致且展示顺序打乱。旧包保持原样。材料本地私有，尚无人工标签；G-reasoner Pilot 仍未启动。见[容量审计报告](reports/p0_fk_mapping_candidate_capacity_20261106_01/README.md)、[预注册方案](plans/p0_fk_mapping_pair_level_blind_review_20261106.md)和[材料准备报告](reports/p0_fk_mapping_pair_level_blind_review_20261106_01/README.md)。
> **2026-11-06 后续迁移诊断**：Mini-Dev `_01` 因输入哈希门失败而封存；Recovery `_02` 的 CPU 标签门也未通过（Full列合格340/495，低于450），因此没有启动任何模型排序。该诊断只测试 query-set transfer，未提供方法效果证据。见[运行 `_01` 报告](reports/gfm_minidev_schema_retrieval_transfer_20261106_01/README.md)、[Recovery `_02` 报告](reports/gfm_minidev_schema_retrieval_transfer_20261106_02/README.md)、[Recovery Amendment](plans/gfm_minidev_schema_retrieval_transfer_20261106_amendment_001.md)和[Recovery 配置](../../../configs/text2sql/gfm_minidev_schema_retrieval_transfer_20261106_02.json)。

## 现有研究文档

| 文档 | 作用 | 状态 |
|---|---|---|
| [下一阶段决策：证据综合与路线停止](plans/next_step_evidence_synthesis_20261106.md) | 综合模型代理审阅、GFM 排序、seed 诊断、Schema 覆盖与 SQL 修复结果；筛选下一研究问题 | 2026-11-06；不新增实验；当前 BIRD-dev GFM 排序线停止扩展 |
| [方法变更台账（当前）](method-change-ledger-20261105.md) | 逐项区分 QuadGraph 原方法、Text2SQL 检索/上下文改动、SQL评测变化及 G0/G1/G2 图探针 | 2026-11-06 更新，含 P2d.3 authorizer 候选归因；不把候选级结果写成系统收益 |
| [P0 FK mapping pair-level 盲审材料报告](reports/p0_fk_mapping_pair_level_blind_review_20261106_01/README.md) | 60 个多 mapping 问题×表对的 A/B 双人审阅材料准备；不含人工标签或模型结果 | Smoke/Full 通过；等待两位真实审阅者；Role Pilot 仍未启动 |
| [模型代理 FK mapping 排序预注册](plans/p0_fk_mapping_model_proxy_rank_pilot_20261106.md) 与[完整报告](reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/README.md) | 三模型高置信多数代理标签上的 G-reasoner vs Dense 排序诊断 | 已完成，NO-GO：7/38 vs 27/38（−52.63 pp）；停止同一代理标签方向，人工 Role 标签仍为0 |
| [论文与代码审计](paper-and-code-audit.md) | QuadGraph 四层图、Qwen3 Embedding 输出维度、GraphReasoner 投影约束、相似度归一化 | 讨论版，待按当前 fork commit 复核 |
| [实验路线图](experiment-roadmap.md) | P0 数据审计 → P1 维度消融 → P2 评分消融 → P3 Text2SQL EX → P4 可选 GFM 适配 | 研究指导 v1，尚未按本路线图执行 |
| [数据与复现规范](reproducibility-contract.md) | Gold 约束、FK 实例标识、反泄漏、缓存版本、评测模板与 Go/No-go | 待实现/执行 |
| [历史 P1 官方编码器报告](reports/gfmrag_p1_official_20261014/report.md) | BIRD dev 表/列维度筛查结果、配置、代码快照及聚合指标 | 2026-10-14 已运行；exploratory；不满足当前 P0/P1 完整验收范围 |
| [P1 结果复核与决策（最新）](reports/p1_review_20261016/README.md) | 核对 512/1024 配对损益、显著性、预算饱和及实验局限 | 2026-10-16 完成**归档再分析**，不是新实验 |
| [P1.5 诊断报告](reports/p1_5_diagnosis_20261016/README.md) | 列检索、Top-K/预算饱和、复现核对及 FK 实例质量 | 2026-10-16 已运行；严格逐题复现 Gate 未通过；exploratory |
| [P1.5 最新复核与决策](reports/p1_5_review_20261016/README.md) | 汇总预算/列 rank、历史 91 项差异、FK/Role Gate、继续实验的逻辑 | 2026-10-16 静态分析；非新实验 |
| [P1.6 → P2a 旧执行协议（历史）](plans/p1_6_rebaseline_then_p2a_20261016.md) | 冻结新基线、同数据 Cosine/BM25/RRF 与 Go/No-go | P1.6 已完成；P2a 为下一步 |
| [P1.6 全量冻结基线（已通过）](reports/p1_6_rebaseline_20261018_01/README.md) | 1024-D cache/scorer replay，smoke 编码不稳定性记录 | 2026-10-18 PASS，新基线 |
| [P2a Cosine/BM25/RRF 全量实验](reports/p2a_similarity_20261018_01/README.md) | 全体/非饱和 DB 的三种方法对比，NO-GO | 2026-10-18 已运行 |
| [P2a 最新结果复核（当前）](reports/p2a_review_20261018/README.md) | 失败机制、RRF rescue/damage、排序/预算冲突和未来研究边界 | 2026-10-18 只读复核 |
| [P2a.5 错误归因与 FK Gate 报告](reports/p2a_5_error_audit_20261018_01/README.md) | 冻结排名错误归因、预算 / 字段特征、FK / JOIN 覆盖与下一步决策 | 2026-10-18 完成；原 P2a NO-GO 与 Role Gate NO-GO 均保留 |
| [P2a.5 执行计划与后续消融指导](plans/p2a_5_diagnostic_and_schema_representation_20261018.md) | P2a.5 已执行范围、复现约束、条件式 P2b / packing 选择 | P2a.5 A/C 已完成；R0/R1 已按专项计划另行预注册 |
| [P2b R0/R1 Values 文本消融预注册](plans/p2b_values_ablation_20261018.md) | 固定 1024-D Cosine 下只移除列 Values 文本，含 CPU 编码控制、成功门与停止条件 | Full 完成；预注册成功门 NO-GO，停止 Values 扩展 |
| [P2b R0/R1 Values 消融记录](reports/p2b_values_ablation_20261018_01/README.md) | 预注册、运行状态、匿名结果及下一步决策 | 2026-10-18 完成，匿名聚合已归档 |
| [P2c 双视图 2×2 实验报告](reports/p2c_dual_view_20261018_01/README.md) | 预注册、smoke 与两次 Full 执行故障、停止决定 | 执行器恢复额度耗尽；未产生 Full 科学结果 |
| [P2c 最新执行分析（2026-10-18）](reports/p2c_execution_review_20261018/README.md) | Full 两次聚合失败、逐字段源码映射审计、科学结论边界 | **最新复核；无新实验成绩** |
| [P2c-R 聚合契约恢复协议](plans/p2c_r_replay_contract_recovery_20261018.md) | 48 项源归档字段映射测试、全流程合成/归档回归、新恢复试验 Gate | Gate 0 与一次正式恢复已完成 |
| [P2c-R Gate 0 工程记录](reports/p2c_r_contract_gate_20261019_01/README.md) | 完整字段适配、缺失/非有限值与分母验证、占位臂聚合写盘 | 93 项测试、真实归档 48 指标/4 分母和 JSON 写盘 Gate PASS |
| [P2c-R 独立恢复全量结果](reports/p2c_r_recovery_20261019_01/README.md) | Gate 0 后同四臂、同阈值恢复及独立产物复核 | H1/H2 PASS；V01为Values风险审计候选，无SQL EX结论 |
| [Values 词面信息风险审计](reports/p2c_values_risk_20261019_01/README.md) | 冻结1024预算下的参考谓词常量可见性，CPU一次有界扫描 | 完成；407/1460题有线索，19题优先复核；非语义安全门 |
| [Values 直接列值绑定核验](reports/p2c_value_binding_20261019_01/README.md) | 冻结19题/21个输入不可见常量的AST源列绑定 | 完成；9题绑定支持/8题不一致/2题未知，仍无语义必要性结论 |
| [P2c-R + Values 最新实验复核（当前）](reports/p2c_r_latest_review_20261019/README.md) | 四臂 PASS、407题风险线索、19题绑定结果和局限 | 2026-10-19 分析，非新实验 |
| [P2d 语义必要性与 SQL EX 配对 Pilot（上位指导）](plans/p2d_value_utility_and_sql_pilot_20261019.md) | 原19题和匹配对照，固定 Generator/Selector/SQL evaluator，E0/E1/E2 与 Go/No-go | 工程/SQL Pilot已按2026-10-22独立登记完成；人工审核未完成 |
| [P2d 2026-10-22 SQL实验报告](reports/p2d_sql_utility_20261022_01/README.md) | 固定本地7B、19优先+11严格对照、三臂一次生成与只读SQLite评测 | Gate A/Smoke/30题Full完成；8/7/8确认正确，语义标签unverified |
| [P2d 最新SQL Pilot复核（当前）](reports/p2d_latest_review_20261022/README.md) | 30题三臂可判/不可判、Token机制、时间函数策略与研究主线 | **2026-10-22分析；非新实验** |
| [P2d.1 评测覆盖和失败归因](plans/p2d_1_frozen_prediction_eval_audit_20261022.md) | 封存SQL复核、safe temporal evaluator v2测试、19题语义审核与Go/No-go | 已完成于独立分支；完整报告在 [GitHub commit `0f4a932`](https://github.com/bArtyom/gfm-rag/tree/0f4a932968f54b9c756e61f7b0ec910b93eefaac/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02) |
| [P2d.2 封存 SQL 失败归因计划](plans/p2d2_frozen_failure_attribution_20261105.md) | 对 28 条旧不可执行输出做只读根因归因；不重新生成、不重算原分数 | `_01` 启动前检查因路径错误停止；科学分析未运行 |
| [P2d.2 `_01` 启动记录](reports/p2d2_frozen_failure_attribution_20261105_01/README.md) | 预注册代码 10/10 合成自检；未读取样本 | **STOP：准备包路径误填；保留失败回执** |
| [P2d.2 `_02` recovery 报告](reports/p2d2_frozen_failure_attribution_20261105_02/README.md) | 固定 90 条封存预测的失败归因 | **Full 完成；28/28 可分类；未发现上下文缺字段，生成引用错误候选待新样本验证** |
| [P2d.3 检索上下文约束修复（最终报告）](reports/p2d3_context_bounded_repair_20261105_01/README.md) | 66题 Full 比较不修复、完整 Schema 修复和 V00 上下文约束修复；匿名聚合随报告归档 | **已完成；A0/A1/A2 Set EX=27.27%/30.30%/25.76%；NO_GO_OR_INCONCLUSIVE，不扩样** |
| [P2d.3 authorizer 候选归因](reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md) | 对冻结的6个初始拒绝与8个修复拒绝候选做完整 Schema 只读回放 | **Full 完成；发现2个可执行且正确的修复候选；候选级归因，不修改原系统准确率** |
| [P0 FK候选定义对账报告](reports/p0_fk_candidate_definition_reconciliation_20261105_01/README.md) | 对账 956/174、970/197、1043/176 三组不一致计数 | **STOP_INVALID_SMOKE；未启动 Full** |
| [P0 FK候选定义对账恢复](reports/p0_fk_candidate_definition_recovery_20261105_01/README.md) | 对上次 Smoke 增加不含 SQL 内容的异常位置回执，并重过三臂小样本门 | **已预注册；Smoke/Full 尚未运行** |
| [P0 FK候选定义哈希诊断恢复计划](plans/p0_fk_candidate_definition_recovery_v2_20261105.md) | 记录同一受控文件句柄的摘要、文件身份和解析字节；新 run ID 重跑三臂 Smoke | **已预注册；尚未读取实验输入** |
| [P0 FK候选定义哈希诊断恢复报告](reports/p0_fk_candidate_definition_recovery_v2_20261105_01/README.md) | 同句柄/旧 helper 摘要一致，但与冻结摘要不同；记录 smoke 停止门 | **STOP_INVALID_SMOKE；未运行 Full** |
| [P0 FK候选定义哈希更正 v3 计划](plans/p0_fk_candidate_definition_recovery_v3_20261105.md) | 新实验 ID 冻结经独立确认的 FK artifact 摘要，重跑 smoke / 条件式 full | **2026-11-05 已执行；结果见报告** |
| [P0 FK候选定义哈希更正 v3 执行报告](reports/p0_fk_candidate_definition_recovery_v3_20261105_01/README.md) | v3 注册、Smoke/Full 与 crosswalk 运行结果；追加适配层代码复核 | 已完成；原始 FK 适配差异由后续 canonical crosswalk 复核，语义 Role 标签仍缺 |
| [P0 canonical P1.5 FK crosswalk 报告](reports/p0_fk_canonical_crosswalk_20261105_01/README.md) | valid-only FK adapter 与 packet-28 / v3 P1.5 的匿名逐题对账 | **完成；过滤无标签影响；实现定义差异仍在，Role Gate NO-GO** |
| [P0 FK 分歧双人盲审材料准备计划](plans/p0_fk_disagreement_blind_review_20261105.md) | 对 packet-only ambiguous/unmatched、canonical-only FK/multi-FK 与正向控制分层抽样，准备匿名本地 A/B 包 | **已按计划执行；Full 通过，等待人工审阅** |
| [P0 FK 分歧双人盲审材料准备报告](reports/p0_fk_disagreement_blind_review_20261105_01/README.md) | 材料生成、映射完整性和隐私门；不产出人类标签 | **49题/51表对；等待两位审阅者；Role 标签仍为0** |
| [P0 BIRD FK 图 hop-depth 结构审计](plans/p0_bird_fk_hop_profile_20261105.md) | 检查 BIRD dev 声明 FK 表图上的精确最小 Steiner hop 分布及高跳数样本覆盖 | **已预注册；CPU-only；不涉及 Role/JOIN 方法准确率** |
| [P0 BIRD FK hop v1 报告](reports/p0_bird_fk_hop_profile_20261105_01/README.md) | 初次 Smoke/Full 匿名画像及 CTE 作用域解析风险 | v1 保留；`SUPERSEDED_PENDING_SCOPE_CORRECTION` |
| [P0 BIRD FK hop v2 修正方案](plans/p0_bird_fk_hop_profile_v2_correction_20261105.md) | 只将 CTE 过滤改为 SQLGlot 作用域感知基础表解析，其他定义冻结 | Smoke/Full 已按计划完成 |
| [P0 BIRD FK hop v2 完整报告](reports/p0_bird_fk_hop_profile_20261105_02/README.md) | v2匿名结构画像、v1聚合对照、SchemaScope比例差异及停止决定 | **FULL_COMPLETED；不再扩展高跳数方法** |
| [双人标签后 FK 映射排序 Pilot 候选](plans/p0_fk_mapping_rank_pilot_candidate_20261105.md) | 在固定表对/映射候选上比较冻结 GFM 与 Dense、BM25、结构顺序；报告接受集合排序与错误交集 | **仅候选；方法新颖性未知；必须先通过真实双人标签门，不得提前运行** |
| [FK 映射排序文献更新](plans/p0_fk_mapping_rank_literature_update_20261106.md) | 将 JoinGR、MDB-Link 等近邻纳入 novelty audit，明确候选只作 G-reasoner 迁移/证伪测试 | **盲审回复未更新；按路线图等待，不启动模型实验** |
| [FK 映射排序前沿复核](plans/p0_fk_mapping_rank_frontier_check_20261106.md) | 核对双向检索、joinable-table扩展和多解释歧义评测等新近邻，说明为何保留同一映射级 Pilot | **未发现可替代盲审门的独立实验；A/B可信标签仍为0** |
| [FK 映射 Pilot 设计审计](plans/p0_fk_mapping_rank_pilot_design_audit_20261106.md) | 纳入近期修复/检索/压缩文献，冻结主基线、可区分标签分母、Smoke/Full 隔离和小样本成功门 | **设计收敛；仍待双人标签；未注册、未运行** |
| [FK mapping 候选容量审计计划](plans/p0_fk_mapping_candidate_capacity_audit_20261106.md) | 检查冻结 BIRD dev 的表对级有效 FK 候选容量 | **已执行；解析子集超过必要容量门，完整总体有 13 个解析缺口** |
| [FK mapping 候选容量审计报告](reports/p0_fk_mapping_candidate_capacity_20261106_01/README.md) | 匿名统计表对级 FK mapping 候选、Smoke 后结构容量范围 | **完成；1,208 个 FK-bearing 对、176 个多映射对、4 个数据库；未运行模型** |
| [FK mapping pair-level 双人盲审方案](plans/p0_fk_mapping_pair_level_blind_review_20261106.md) | 用新的独立样本包补足映射级双审候选，保留旧包和阈值 | **材料已生成：60 个问题×表对、135 个 mapping；等待独立审阅，可信标签仍为 0** |
| [G-reasoner Query 指令兼容性审计](plans/p0_gfm_embedding_instruction_compatibility_audit_20261106.md) | 对照 checkpoint、G0 与 P1.6 的 Query 指令，冻结 FK mapping Pilot 的向量兼容要求 | **只读审计；不推翻历史结果；仍待双人标签，未运行模型** |
| [FK 映射 Pilot 输入语义审计](plans/p0_fk_mapping_rank_pilot_input_semantics_audit_20261106.md) | 基于官方 seed-mask 接口与 G0 代码，冻结条件式表对任务的共享起点语义 | **设计澄清；仍待双人标签；未注册、未运行** |
| [2026-10-23 P2d.1 + G0 跨分支复核（当前）](reports/p2d1_g0_cross_branch_review_20261023/README.md) | 读取分支的真实结果，区分 evaluator v2、元数据未被模型读取及方法结论边界 | 已完成静态分析；非新实验 |
| [G1关系通道×FK Instance保真](plans/g1_relation_channel_and_fk_instance_gate_20261023.md) | 8次合成前向/多种edge_type/rel_attr对照、同义重标记不变性、FK Role Label Gate及Go/No-go | 2026-10-23完成；按原门槛 G1-A NO-GO，见G1报告 |
| [2026-10-24全局实验复核与G1结构对称性分析](reports/current_results_review_20261024/README.md) | 从P1/P2到G1/G2及FK Instance Gate结果、失败机制和下一步 | **静态复核附Gate结果更新** |
| [G2非对称关系通道识别实验](plans/g2_asymmetric_relation_channel_identifiability_20261024.md) | 新synthetic fixture、CPU多重集合强Gate、8次前向、FK Instance质量工作包 | **2026-10-24完成；G2-A PASS；报告在研究分支** |
| [G2非对称关系通道实验报告](reports/g2_asymmetric_relation_20261024_01/README.md) | 预注册、CUDA首次启动故障与修复、CPU Gate、8条件结果与结论边界 | **G2-A PASS；branch commit `d234507`** |
| [G2 FK Instance稳定编码质量Gate](reports/g2_fk_instance_quality_20261024_01/README.md) | BIRD dev SQLite schema的FK实例标识、复合列与双向边结构复核；不含Gold语义判断 | **2026-10-24 Full NO_GO；同结构重复FK导致身份冲突** |
| [FK重复声明身份策略计划](plans/g2_fk_duplicate_identity_policy_20261024.md) | 比较唯一Join映射和保留声明重数的两种CPU结构表示 | **已独立预注册；exploratory，尚未运行** |
| [FK重复声明身份策略报告](reports/g2_fk_duplicate_identity_policy_20261024_01/README.md) | smoke/full结果、ID集合与组号关联不变性、重复边处理风险 | **EXPLORATORY_COMPLETE；G0-01实现失败，G0-02恢复版已独立预注册** |
| [G0 FK实例节点预注册](plans/g0_fk_instance_node_20261024.md) | 两个同端点FK映射的重化节点表示、冻结G-reasoner、Qwen稠密基线和合成查询翻转门 | **已运行；Full因图重排设备错误按协议停止** |
| [G0 FK实例节点实验](reports/g0_fk_instance_node_20261024_01/README.md) | 合成同端点多FK图中实例级输出与映射身份稳定性 | **实现失败；无全量科学结论，待独立恢复版预注册** |
| [G0-02图设备迁移恢复预注册](plans/g0_fk_instance_node_recovery_20261024.md) | 仅修复 PyG `Data.to()` 原地改变图对象的问题，重复冻结的同一合成查询与评分门 | **已执行；科学门 NO_GO** |
| [G0-02恢复实验报告](reports/g0_fk_instance_node_20261024_02/README.md) | G0-01 Full 图重排实现失败后的独立、有界恢复执行 | **G0_SYNTHETIC_NO_GO；GFM 2/4，dense 4/4** |
| [P0 BIRD-dev证据复核预注册](plans/p0_bird_dev_evidence_reconciliation_20261024.md) | 只读复核既有P0 v3输入指纹、FK/Role标签覆盖与Qwen健康证据，不重跑模型或SQL | **2026-10-24完成；冻结方案保留** |
| [P0 BIRD-dev证据复核报告](reports/p0_bird_dev_evidence_reconciliation_20261024_01/README.md) | 对照当前路线图归档历史P0证据并划定可支持的结论范围 | **88/88输入及3/3产物指纹通过；表/列证据可复现；Role Gate NO-GO** |
| [P0双人盲审候选包准备协议](plans/p0_role_blind_review_packet_20261025.md) | 从冻结的174个多FK候选中分层抽样20题，准备无Gold/模型输出的本地双审材料 | **已预注册并运行；历史FK计数门未通过，可信Role标签仍为0** |
| [P0双人盲审候选包准备记录](reports/p0_role_blind_review_packet_20261025_01/README.md) | 数据/计数门、映射身份、隐私与材料生成记录 | **PREPARATION_GATE_STOP；未生成审阅包** |
| [P1.6 最新 Smoke/代码审计](reports/p1_6_smoke_review_20261017/README.md) | 两次 Smoke 失败、manifest 校验问题与源代码检查 | 2026-10-17 静态审计；后续修复和测试见 P1.6 阶段报告 |
| [P1.6 Smoke 恢复 → P2a 历史执行方案](plans/p1_6_smoke_recovery_then_p2a_20261017.md) | CPU manifest 回归、Smoke/Full Gate、后续 Cosine/BM25/RRF | Smoke 与 Full 已按此计划完成；见 2026-10-18 报告 |
| [P1.6 冻结基线重建报告](reports/p1_6_rebaseline_20261018_01/README.md) | 修复后 Smoke 与 1,534 题 Full；新 1024-D Dense 基线及 Gate | 2026-10-18 完成；Full Gate PASS，encoder 跨前向浮点差异已披露 |
| [P2a Cosine/BM25/RRF 全量对照](reports/p2a_similarity_20261018_01/README.md) | 固定缓存、候选全集和预算的评分方法对照及数据库级不确定性 | 2026-10-18 完成；S0 parity / integrity PASS，预注册收益门未通过，停止方法扩展 |
| [P2a 相似度对照预注册](plans/p2a_similarity_20261018.md) | 1024-D Cosine / BM25 / RRF 的冻结分词、候选集、指标、门槛与资源 | 修复版 Smoke 与 Full 已完成；预注册方法成功门未通过，见 P2a 全量报告 |
| [P1.5 → P2a 执行指导](plans/p1_5_diagnostics_and_p2a_20261016.md) | 离线诊断、FK Gate、条件式 BM25/RRF 检索实验及 Go/No-go | P1.5 与 P2a 已运行；结果及停止决定见各自报告；原指导保留 |
| [G-reasoner 图算法源码精读（新）](graph-algorithm-code-review-20261016.md) | 分析 NER/Top-1 锚点、关系类型与逐边属性、NBFNet 消息传播、SQL 子图结构约束、创新性排序 | 2026-10-16 静态审查与研究建议；未跑新实验 |

论文与代码审计、实验路线图、复现规范从旧仓库**迁移**，部分路径/迁移日期调整；迁移本身不产生新实验结论。上表的 P1 报告记录了 2026-10-14 实际运行，但其范围仅为表/列筛查，FK/角色未测；不得视作当前路线图下 P0 通过或完整 P1 完成。

> **2026-11-06 路线更新**：P2d.3 authorizer 只读反事实审计在 8 个被拒修复候选中发现 2 个完整 Schema 下可执行且正确，但不改变原 A2 的 17/66 系统分数。通用 SQL 修复和双 Schema 路线已有近期工作覆盖，本分支不继续追加此类实验。FK 映射 Pilot 仍必须等两位真实审阅者；针对多 mapping 候选的新 60 单元 A/B 包已准备完成，但目前可信标签仍为 0，所以不运行模型 Smoke/Full，也不让模型代标。见[审计报告](reports/p2d3_authorizer_counterfactual_audit_20261106_01/README.md)、[新盲审材料报告](reports/p0_fk_mapping_pair_level_blind_review_20261106_01/README.md)、[映射排序文献更新](plans/p0_fk_mapping_rank_literature_update_20261106.md)和[设计审计](plans/p0_fk_mapping_rank_pilot_design_audit_20261106.md)。

> **2026-11-06 前沿复核补充**：Rethinking Schema Linking 已覆盖 table-first/column-first 检索，REaR 已覆盖检索后按列向量扩展 joinable 表；ARCS 的人工多解释标签并非 BIRD FK mapping 业务角色标签。未发现能在不重复已有工作、也不替代双人审阅的可执行新实验，因此保留同一 Accepted@1 映射级证伪 Pilot，不另开支线。详见[前沿复核](plans/p0_fk_mapping_rank_frontier_check_20261106.md)。

## 当前研究命题

**固定 Schema Graph 下研究 Query/Node/Join-Instance Embedding 维度与检索评分方式如何影响表列召回、关系角色、合法 JOIN 路径及最终 Set EX。**

1. 同一 Qwen3-Embedding-0.6B 比较 **128、256、512、768、1024** 维；固定输入模板、数据库/Graph、L2+Cosine、候选预算。
2. 在固定维度及同候选宇宙对比 Cosine、BM25、RRF、Relation-description Cosine、Role-aware Path Score。
3. 关注**同表不同 FK 角色、复合 FK、桥表**；不能仅用 Table Recall 替代 JOIN 正确性。
4. 最终用固定 SQL generator / selector 评价 **Set EX（主）/ Bag EX（辅）**，独立报告 token、延迟与实际费用。
5. 发布的 1024 维 G-reasoner checkpoint **不能直接输入 512 维向量**；如需 GFM 侧对照，另建适配器实验并记录训练变量。
6. 本研究中涉及 Jev 时，需要和向量检索模块分开对照归因，不将单纯候选数或下游 SQL 更换归因于 Jev。

## GFM 源码拓展方向（研究储备，不改变当前 Gate）

在 [2026-10-16 的代码级分析](graph-algorithm-code-review-20261016.md) 中，重点确定了 **Top-1 起始锚点、关系实例/逐边属性未纳入默认消息权重、节点 Top-K 非连通、SQL-aware 监督未落地**等可验证机制。最有潜力的后续方向是 **Query-aware JOIN Edge Gate + 实例感知约束子图解码**；但必须先过 FK/Join 标签 Gate，并与 Graph-Link、GRAST-SL、SchemaGraphSQL 同信息比较。**这不是已有实证收益**。

## 最新行动结果与下一步（2026-10-24，P0证据复核后）

### 当前执行项

已根据以下P0结论登记受控候选包准备协议：可信双审标签为0，真实Role准确率、监督训练和新SQL实验保持停止；先重现历史候选计数，再生成20条本地盲审材料。2026-10-25 Smoke通过，但Full统计为FK匹配1043题、多FK候选176题，与冻结历史956/174不一致，按协议停止且未生成审阅包；详细结果见[执行报告](reports/p0_role_blind_review_packet_20261025_01/README.md)。该差异需先用独立协议复核历史FK匹配定义，不属于角色方法结果。

**分支与证据**：G2、FK Instance Gate及重复声明身份策略结果在`research/g2-asymmetric-relation-20261024`；G0-01 `IMPLEMENTATION_FAILURE`与G0-02 `G0_SYNTHETIC_NO_GO`在`research/g0-fk-instance-node-20261024`。G0-02最终报告记录了Smoke和Full结果、代码/模型/环境版本、资源、token和限制。研究分支结果尚未合并`main`。

**G1实测**：8次官方G-reasoner-34M 1024D合成图前向PASS，负控及关系交换C1/C2/C3/C4 max abs delta均0，起点C5=30.9753、Query C6=8.3077。原预注册`G1-A NO-GO`保持。经代码核对，C2/C3交换的两条relation边同起点/终点，交换后节点的消息多重集合不变；所以这个zero delta不证明模型全局忽略relation type/embedding。这是一项**实验设计可辨识性不足**，不是模型没有使用关系的因果结论；原G0只证明非模型消费的自定义FK字段不影响推理。

**G2实测**：Gate `_012` 14/14硬门、23/23定向合约测试通过。首次GPU启动在`MODEL_IMPORT`因CUDA context未初始化而停止，未加载checkpoint、未前向；增加显式CUDA初始化后使用新run ID完成1次加载和8/8前向。固定官方34M checkpoint hash一致；A0重复噪声0、epsilon=1e-6；A1/A4 max abs=0；A2=0.758783、A3=3.781296，按冻结条件判为`G2_A_PASS`。所有输出finite `[1,5]`、所有条件top-1相同；总加载+前向6.3151秒。结论限于**该5节点非对称合成fixture的关系通道分数敏感性**，不代表同端点多FK角色能力、SQL EX或真实Schema收益。

**其他重要结果**：P2c-R在1460可评题上Schema Complete@1024从56.64%至67.60%（+10.96pp），只是离线结构节点覆盖；P2d的有偏30题7B Pilot E0/E1/E2确认SQL Set/Bag正确数仍8/7/8，P2d.1 v2已通过137合成安全测试和83/83历史SQL replay，仍8/7/8，28条预测不可执行（10 parse+18 missing-column）。不要用Schema覆盖代替SQL EX，不用该30题调Prompt来追分。

**FK Instance Gate：NO_GO**。Full在11库复现103原始/100有效/3无效；两个有效声明规范化为同一个结构键，且没有复合FK。精确失败机理与局限见Gate报告。G0-01独立实现失败；G0-02结构与映射置换门通过，但GFM 2/4、dense cosine 4/4，按预注册门槛为`G0_SYNTHETIC_NO_GO`。该结果不改变无真实角色标签的事实。

**后续探索结论**：mapping identity保留所有99个不同有效映射，并将1个完全重复声明作为重数元数据；multiset identity保留100个声明ID，但无法在PRAGMA重编号后稳定绑定到重复组。候选建议为映射级唯一ID，且将声明重数作为元数据；原Gate仍是`NO_GO`，新方案须先独立预注册。人类Role标签仍为0，故不开始query-conditioned Role监督；不在旧30题继续SQL调参、换模型或自动扩样。

**2026-11-06 P0 代理排序错误归因完成**：只读分析冻结的38个可区分单元，G-reasoner Accepted@1 为7/38，Dense为27/38，净差−20。2/3候选数和已公开的列重叠分层都没有 G-reasoner 正向子组；38个单元均为单一接受 mapping 且不含复合FK。停止在同一模型代理标签上的调参/结构扫描。该结果仍不是人工FK Role准确率。见[错误归因报告](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/README.md)和[聚合结果](reports/p0_fk_mapping_proxy_error_analysis_20261106_01/aggregate_summary.json)。

G2、FK Gate、身份策略、G0及P0复核均各自保留运行ID与结果，不覆盖历史产物，也不把研究分支结果说成已合并`main`。本轮P0审计的91项输入/产物指纹检查均通过，但没有可信Role标签；因此P0结果仅支持表/列证据，整体Role Gate仍为NO-GO。下一步需先取得受控双人盲审标签并明确FK身份策略；在此之前，不启动P1角色准确率、维度扫描、query-conditioned Role监督或新的真实SQL实验。后续G0如仍有清晰问题，必须另行冻结身份表示、对照、成功门、预算和停止条件后再登记。


## 从今往后的提交规范

- **文档：**研究思路/文献核对进入 `docs/research/text2sql/`；每轮计划以明确版本文件记录，前一版保留以供追溯。
- **实现：**沿用本仓库的 `gfmrag/`、`scripts/`、`tests/` 项目约定；先检视现有模块再新增代码，不擅自覆盖上游实现。
- **结果：**新建 `docs/research/text2sql/reports/<experiment-id>/` 保存匿名聚合指标、失败模式、数据/代码 hash、变更前后对照、明确的下一轮 Go/No-go。
- **变更区分：**研究设想、实验计划、已运行证据、未执行行动必须显式区分。统计说明数据集、分母、数据库级拆分、Set/Bag、计算预算以及不确定性。
- **GitHub 权威性：**以后本研究的最新判断以**该仓库真实已提交的版本**为准。分析新结果之前先读取本仓库最新报告与提交；不能拿历史会话里的数字冒充新报告。
- **安全：**不上传数据库内容、原题/Gold SQL、逐题预测、API 密钥、日志或无法公开的数据；公开代码和协议、必要的匿名统计与 hash。
- **代码合并：**原则上研究文档可直接独立提交；涉及主干模型/评测代码的改动，应优先独立分支及 PR，并明确测试与回退方式。

## 历史来源与技术依据

- 历史研究仓库（仅供追溯）：[bArtyom/quadrag](https://github.com/bArtyom/quadrag)。
- 本代码库上游：[RManLuo/gfm-rag](https://github.com/RManLuo/gfm-rag)。
- G-reasoner 论文：[arXiv:2509.24276](https://arxiv.org/abs/2509.24276)。

**下一次接到“看最新报告、分析下一轮、保存到 GitHub”时：先看本仓库，再给出可归因分析，并提交新版本指导。**

### 2026-11-06：新版 BIRD Mini-Dev SQL 映射迁移诊断（已停止）

旧 BIRD-dev 模型代理映射排序已按 NO-GO 停止；本次使用官方 2026 reviewed Mini-Dev 与冻结 FK 候选，标签定义为 Gold SQL 显式 `JOIN ON` 中出现的 mapping。`cpu_smoke_001` 在解析 SQL 前发现旧版 `dev_tables.json` 与官方 DDL 的版本差异，未读取标签；登记唯一工程恢复 `cpu_smoke_002` 后，通过 Smoke 并完成 500 题 CPU 标签审计。SQL 解析率 100%，但限定 JOIN 等式解析覆盖为 78.88%，低于 95% 门槛；48 个可评分问题×表对和 4 个数据库达到数量门。按预注册停止，未启动模型排序。此标签不是真实人类 Role 标签，也不支持跨库泛化。见[实验报告](reports/p0_minidev_sql_fk_mapping_rank_20261106_01/README.md)、[匿名聚合](reports/p0_minidev_sql_fk_mapping_rank_20261106_01/aggregate_summary.json)、[预注册方案](plans/p0_minidev_sql_fk_mapping_rank_20261106.md)和[冻结配置](../../../configs/text2sql/p0_minidev_sql_fk_mapping_rank_20261106.json)。


> **2026-11-06 双模型审阅分歧归因**：只读审计 60 个匿名问题×表对，双方有效 57 个，精确决定与接受集合一致 28 个；23 个分歧来自“单映射/多映射”决定不同，候选顺序分组一致率接近。两模型自报置信度高并未解决分歧。排序门仍未通过，模型输出不是人工金标准。用户选择继续用模型审阅；下一步候选为单独预注册一个不同模型家族的盲审，并预先冻结三方代理共识规则，是否进入探索性排序仍需看新门槛。见[分歧归因报告](reports/p0_fk_model_review_disagreement_audit_20261106_01/README.md)及[匿名聚合](reports/p0_fk_model_review_disagreement_audit_20261106_01/aggregate_summary.json)。


> **2026-11-06 第三模型审阅代理已单独预注册**：用户选择继续用模型审阅后，为检验双 Qwen 审阅口径分歧是否能由不同家族的独立意见减少，新增 Gemma 4 E4B-it 盲审方案。三方代理标签使用精确决定与接受 mapping 集合多数、且至少两票置信度≥2；仅当 ≥30 可裁定、≥20 可区分、覆盖 ≥3 匿名数据库时，才允许另行登记探索性排序。当前仅计划已提交，Smoke/Full 尚未运行。仍不能将模型多数称为人工标签。见[预注册方案](plans/p0_fk_mapping_model_review_third_proxy_20261106.md)。


> **2026-11-06 第三模型审阅 GPU 失败与 CPU 恢复（完成）**：GPU 预注册运行在生成前失败，原因是 vLLM 环境的 PyTorch CUDA 13 与系统 CUDA 12.4 驱动不兼容；第一次 conda run 还曾解析到 Python 3.9，未产生任何模型 token。没有升级驱动或依赖。独立 CPU 恢复使用同一 Gemma4 checkpoint、冻结样本与标签门，Smoke 5/5、Full 60/60。三方高置信精确多数56个、可区分41个，覆盖4库；仍为模型代理标签，可信人工 Role 标签为0。排除固定问题级 Smoke 后，模型代理排序门剩51个可裁定、38个可区分、覆盖4库，允许另行注册一次探索性排序诊断。见[GPU失败记录](reports/p0_fk_mapping_model_review_third_proxy_gpu_20261106_01/README.md)、[CPU恢复报告](reports/p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/README.md)和[恢复预注册](plans/p0_fk_mapping_model_review_third_proxy_cpu_20261106.md)。
> **2026-11-06 G3 起点敏感性诊断完成**：Smoke_002 通过；Full 55 对、123 个 mapping 候选。相对双端 seed，第一端单 seed 改变 Top-1 4/55、候选对反转6/81；第二端改变6/55、反转7/81。A0 重复误差0。两条件都未达到预设机制信号门，结果为 `INCONCLUSIVE`；按协议停止，不把排序变化解释为正确性或方法收益。Smoke_001 的 Python 3.9 环境入口失败已保留，未加载模型或产生 token；Smoke_002 使用环境内 Python 3.12 完成。可信人工 Role 标签仍为0。见 [G3 方案与执行记录](plans/g3_fk_seed_direction_sensitivity_20261106.md)、[完整报告](reports/g3_fk_seed_direction_sensitivity_20261106_01/README.md)和[匿名聚合](reports/g3_fk_seed_direction_sensitivity_20261106_01/aggregate_summary.json)。

### 2026-11-06：Mini-Dev JOIN 直接投影覆盖诊断（已完成，未过门槛）

针对上一轮 SQL 解析覆盖 523/663 的 140 个缺口，单独注册并完成唯一直接投影 lineage 诊断。Smoke 5/5、Full 495/495，7/7 逻辑夹具通过；500/500 SQL 可解析。新增直接 CTE/派生表列投影追踪恢复 46 项、0 回归，合计 569/663（85.82%），低于预设 630/663（95%）门槛；剩余 94 项主要是 alias/相关引用以及表达式/UNION。按预注册停止，不启动模型排序或新 SQL 生成/执行；此结果不改变已停止的 G-reasoner 代理排序结论。首个 `smoke_001` 因配置中 schema hash 转置而在数据读取前失败，原日志保留；更正配置后 `smoke_002` 成功。详情见[完整报告](reports/p0_minidev_join_scope_taxonomy_20261106_01/README.md)、[匿名聚合](reports/p0_minidev_join_scope_taxonomy_20261106_01/aggregate_summary.json)和[预注册计划](plans/p0_minidev_join_scope_taxonomy_20261106.md)。

### 2026-11-07：SQL-used FK 映射对照执行状态

用户选择使用模型审阅；Qwen A/B 与 Gemma C 的审阅和模型代理排序已在此前独立报告中完成。本轮计划只复用冻结排名，将标签目标改为原 BIRD dev 参考 SQL 显式 `JOIN ON` 使用的 FK mapping，不再调用模型。Smoke 在读取任何数据前因启动准备提前创建输出目录而触发 `OUTPUT_DIRECTORY_ALREADY_EXISTS`；按运行器冻结规则停止，不重试，Full 未运行。该次无指标，不能解释为支持或反对核心假设。详见[执行报告](reports/p0_fk_sql_used_mapping_alignment_20261107_01/README.md)、[匿名状态汇总](reports/p0_fk_sql_used_mapping_alignment_20261107_01/aggregate_summary.json)、[预注册方案](plans/p0_fk_sql_used_proxy_alignment_20261107.md)。

### 2026-11-07：唯一作用域列绑定恢复诊断（Smoke 实现门失败，停止）

为上一轮剩余的 94 个未解析 JOIN 等式，登记了“只恢复当前 scope 中恰有一个来源的未限定直接投影列”诊断。`smoke_001` 因配置 schema SHA 转录错误在输入哈希门停止；唯一 amendment 修正哈希后，`smoke_002` 通过输入校验，但第一个正向逻辑夹具 `unique_unqualified_direct_projection` 返回空绑定，未进入 5 题 SQL 分析。按恢复协议停止；Full 未启动，核心假设未检验，禁止本注册再重试。详见[报告](reports/p0_minidev_scope_binding_recovery_20261106_01/README.md)、[匿名状态汇总](reports/p0_minidev_scope_binding_recovery_20261106_01/aggregate_summary.json)、[方案](plans/p0_minidev_unique_scope_binding_20261106.md)及[Amendment 001](plans/amendments/p0_minidev_scope_binding_recovery_amendment_001.md)。
