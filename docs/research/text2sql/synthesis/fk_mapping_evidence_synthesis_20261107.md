# FK mapping 证据综合与下一步边界

日期：2026-11-07
仓库基线：`14525e6b90c673a744db38f69019b67fdb2a53a7`
性质：研究证据综合；不是新方法结果或独立复现。

## 当前核心问题

当前核心假设是：对自然语言问题给定一对表和多个声明式外键映射时，G-reasoner 的图传播排序能否比共享向量 Dense cosine 更准确地选出有用映射。已运行证据均限定在显式 JOIN-ON、可解析候选及当前数据/实例；它们不能直接代表完整 Text-to-SQL JOIN 发现或唯一业务语义。

## 证据综合

| 证据 | 观测 | 能说明什么 | 不能说明什么 |
|---|---|---|---|
| BIRD-dev SQL-used Mapping@1 Full（108 单元、4 库） | G-reasoner 43/108（39.81%）；Dense 63/108（58.33%）；差 −18.52 pp；配对净救回 −20；仅 1/4 库净救回为正 | 在冻结的 SQL-used 标签与候选定义下，G-reasoner 没有超过 Dense；预注册正向门失败 | 不是人工 Role 准确率，也不是完整 Text-to-SQL 结果 |
| 同实例 Bag 接受集敏感性重评分（89 个共同完整单元） | 单目标口径 33/89 对 55/89；Bag 相同替代映射口径 63/89 对 80/89；差距由 −24.72 pp 缩至 −19.10 pp | 指标对接受集合有敏感性，放入当前实例上可产生相同结果 Bag 的映射会缓解负差 | 排序未反转；实例 Bag 相同不等于 SQL 语义等价、业务 Role 正确或跨实例成立 |
| 当前实例映射可区分性审计（94 个完整非空单元、4 库） | 54/94（57.45%）至少有一个替代 FK 映射产生与 Gold 相同的结果 Bag；信号集中在 DB-B/DB-D | 当前数据库实例经常无法区分多个映射，存在目标可识别性问题 | 不是 57.45% 的 SQL 等价率，也不能外推到其他数据库 |
| Spider 1.0 官方 test 容量门 | 2,142 个 Full 问题 SQL 解析率 100%、scope 错误 0；仅 52 个合格问题×表对单元/4 库，低于冻结的 60 门 | 该固定切片不足以支持已登记的模型审阅复制；按门槛停止 | 没有运行审阅或排名，因此不是 Spider 上的正/负方法结果 |
| 本地模型审阅可靠性 | BIRD-dev rank Smoke 的 A/B 两模型仅 2/5 高置信精确一致；旧三模型包在其自身固定任务上的高置信多数集合不可与本轮 A/B Smoke 混作同一统计量 | 用户可选择模型审阅作为代理标签来源，但应先过独立的一致性/可区分性门 | 模型投票不是人工共识，不可替代金标准，也不能补救样本容量门失败 |

上表的主排名及重评分结果来自 [SQL-used rank 报告](../reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/README.md)、[Bag 接受集重评分报告](../reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/README.md)、[实例可区分性报告](../reports/p0_fk_mapping_instance_equivalence_20261107_01/README.md)及[Spider 容量报告](../reports/p0_spider_fk_mapping_candidate_capacity_20261107_01/README.md)。

## 结论与范围

现有证据支持一个窄结论：在当前 BIRD-dev 的冻结多 FK 映射任务和 SQL-derived/实例 Bag 评价口径下，没有观察到 G-reasoner 相对 Dense 的排序优势；改变接受目标可缩小差距，但没有翻转排序。与此同时，SQL-used mapping 不是唯一业务 Role 金标准，模型代理审阅也尚未显示足够稳定，因此不能把该负结果升级成“图传播对 JOIN 角色普遍无效”。

同一 BIRD-dev 样本上的调参、图变体、补充投票和降低 Spider 的 60 单元门均关闭。按项目路线，下一步先综合错误与目标标签边界；若继续做迁移，只能是新的、明确标为 exploratory 的数据库迁移检查，并在看新样本 SQL 前完成注册。

## 模型审阅选择

用户已选择“用模型来审阅”。后续模型输出按模型代理标签记录：逐模型保存配置、版本、输入/输出 token、拒答/不确定状态、接受集合和一致性；报告不得称作人工审阅或人类共识。模型审阅需先满足预注册的一致性、可区分样本数和数据库覆盖门，失败时停止，不追加模型票来稀释分歧。

## 下一步候选（尚未执行）

一次 BIRD train 数据库迁移容量审计已经通过：train/dev schema `db_id` 交集为0；Full 解析9,423/9,423、scope错误0；得到384个列对层面候选容量单元、覆盖12个匿名库。由于 BIRD schema 没有 FK constraint ID，384只是上界，不能直接进入模型审阅。完整结果见[容量报告](../reports/p0_bird_train_fk_mapping_capacity_20261107_01/README.md)。

BIRD train 是公开训练数据，资源索引记录它曾被其他本地项目使用；因此后续结果仍只能称“数据库分离的 exploratory train-split transfer”，不能称隐藏测试、干净独立 benchmark 或正式复现。BIRD 官方资料将训练/开发数据列为公开数据，并强调隐藏 test databases 是为减轻预训练暴露风险，见[官方数据集说明](https://papers.nips.cc/paper/2023/file/83fc8fab1710363050bbd1d4b8cc0021-Paper-Datasets_and_Benchmarks.pdf)与[BIRD 官方页面](https://bird-bench.github.io/)。

下一步只考虑另行预注册 actual FK constraint / composite identity 核验。需在只读 SQLite PRAGMA 与 metadata 的对齐门后仍有至少60个真多约束单元、覆盖至少4个匿名数据库，才进入用户选择的本地模型代理审阅。该复核仍不预设 G-reasoner 会改善；模型标签不得表述为人工共识。
