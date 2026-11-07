# P0：冻结 SQL-used GFM 排名的实例输出等价重评分

**状态：预注册，尚未读取逐单元排名或等价结果。** 实验 ID：`p0_fk_mapping_output_equivalence_rescore_20261107_01`。这是对两份已冻结结果的探索性只读重评分，不训练、调用模型、执行 SQL 或调整排序方法。

## 研究问题与痛点

已完成的 SQL-used FK mapping 排序把参考 SQL 实际使用的 mapping 作为唯一正确候选。另一份独立的静态实例审计显示，一些不同 mapping 在同一冻结 SQLite 数据库上也会产生与参考 SQL 相同的结果 Bag。问题是：**在共同可评估样本上，把这些同实例 Bag 相同的候选列为次级可接受项，会不会实质改变冻结 G-reasoner 相对 Dense Cosine 的负向差距？**

用户已选择使用本地模型做审阅；两位 Qwen 与一位 Gemma 的 60 单元盲审、56 个高置信模型多数标签，以及模型代理排序诊断均已在先前报告中完成。本轮不重复模型审阅。此重评分回答的是静态执行结果是否使 SQL-used 唯一目标对排名解释过严，不判断人工业务 Role。

## 预注册假设、层级与预算

- **核心假设：** 在符合实例审计完整性条件的共同样本中，允许 Bag 相同的替代 mapping 后，G-reasoner 与 Dense 的 Mapping@1 差距会相对“仅 SQL-used mapping 为正确”的定义改变至少 5 个百分点。
- **实验层级：** 主实验之外的 exploratory 评价构念诊断；不是方法效果实验，也不改变既有主指标。
- **唯一主要对比：** 同一共同样本上的 G-reasoner 与 Dense Cosine；BM25 和稳定顺序仅作为描述性次级结果。
- **结果成功判据：** 实例输出等价标签下的配对差值 `(G-reasoner − Dense)@1` 相对 SQL-used 单目标标签的差值变化至少 +5 pp，记为“本地评价对目标定义敏感”。这不等于 G-reasoner 获胜。低于 +5 pp 且差值仍为负，记为“本次有限重评分未改变负向结论”。
- **停止条件：** 输入 SHA、来源提交、108 个 pair 的一对一映射、候选集合/哈希或目标候选校验任一失败时停止；不修复输入、不补齐样本、不重跑上游实验。只报告 5 题 smoke 的检查结果，不把 smoke 与 Full 合并。
- **预算：** CPU，最多 4 线程；Smoke 5 个可评估单元，Full 排除 smoke 后预计最多 89 个单元；墙钟 2 分钟、峰值 RSS 2 GiB；模型/API/GPU/SQL 调用均为 0。无扩样、调参或第二轮。

## 冻结输入、版本和口径

- 项目仓库：`https://github.com/bArtyom/gfm-rag`，分支 `research/p0-sql-used-proxy-alignment-20261107`。启动前读取该仓库 README、Text2SQL README、路线图和复现契约；不写入上游 `RManLuo/gfm-rag`。
- 参考排名：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_002` 的 GPU Full，108 个 pair。冻结预测文件 SHA-256：`553556a4de85efa48d0b639b899d07b39fa8a35955e6757de0e7a6020308e659`；运行源 commit：`7801d46206a0aeeaaacad05f80e71961297ee475`。
- 共同清单：`prepared_manifest_private.json`，SHA-256：`cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0`；完整映射使用 `unit_id → review_pair_id` 和候选 `mapping_id`，不公开其值。
- 静态结果：`p0_fk_mapping_instance_equivalence_20261107_01` 的 Full_002，逐单元文件 SHA-256：`f996213f2d6e657f518c5440843eaa7f61e6f91fd57e5d0393d8022d6d5a4337`；执行源 commit：`e0d3e0d0d617cbedc02ef317f3578057b36b28ee`。
- 目标集合：纳入静态审计状态 `complete` 且 Gold 返回非空结果的单元。精确 SQL-used 单目标结果以唯一 `is_target=true` 候选计分。次级实例输出等价集合为该目标加上静态比较 `status=ok` 且 `bag_equal=true` 的候选。只使用 Bag 相等；Set 相等不用于标签。
- 共同样本分母由静态审计完整单元、排名输出和候选映射三者的严格一对一交集决定。所有可评估候选须在冻结排名候选集合中；任何映射缺失、哈希碰撞、重复 pair 或目标不唯一都停止。
- Smoke 由可评估单元按 `SHA256("p0-output-equivalence-smoke-v1:" + unit_hash)` 排序取前 5 个；Full 排除这 5 个。所有指标以单元为分母，按匿名数据库报告描述性结果，不做显著性检验或因果解释。

## 解释边界与近邻工作

本实验使用一个冻结数据库实例上的实际结果 Bag 相等，仅检查评价敏感性。它不证明 SQL 在其他数据库内容上等价，不代表 SQL 意图、业务角色、用户需求或人类审阅共识，也不能把同实例执行正确性归因于 GFM。通用 SQL test-suite / 合成数据库 / 等价验证已有既有研究，本轮不主张这些机制为新方法；重评分只服务于解释本仓库现有负结果。

## 归档与报告要求

执行脚本、配置和本计划在 Smoke 前提交。输出写入新目录 `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/`，不覆盖原实验。最终报告放入 `docs/research/text2sql/reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/`，只上传匿名聚合、环境/命令/哈希和报告；不上传问题、Gold SQL、数据库名、mapping ID、逐单元标签或私有预测。完成后推送并从 GitHub 读回核验。
