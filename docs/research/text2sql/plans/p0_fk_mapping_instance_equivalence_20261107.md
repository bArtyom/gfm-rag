# P0：多 FK 映射的实例级可区分性审计

**状态：预注册；未运行。** 这是一次 CPU-only exploratory diagnostic，不是新的 GFM 排序方法实验。

## 痛点与研究问题

最新 SQL-used 排序注册 `_03` 的两名本地 Qwen 审阅者各自 5/5 输出有效，但只有 2/5 达到高置信精确一致，低于原登记的 4/5 门槛。不能把该门槛事后改成通过，也不能用更多模型投票冒充人工 Role 金标准。与此同时，SQLGlot 在当前 BIRD dev 子集中解析出 174/176 个多 FK JOIN 目标映射候选覆盖；因此可以直接问一个更窄的问题：参考 SQL 使用的 FK 映射，是否能在当前 SQLite 数据实例上与同表对的其他 FK 候选区分？

**研究问题：** 对固定 Gold SQL，只替换一个显式 JOIN-ON alias pair 的 FK 列等式，其他 SQL 结构保持不变；其他有效 FK 候选中有多少会在当前 BIRD 数据库上返回与 Gold SQL 相同的 Set/Bag 结果？

**核心假设：** 在可安全替换且 Gold 输出非空的 Full 单元中，至少 10% 存在一个非 SQL-used FK 候选，使替换后的 SQL 与 Gold SQL 在当前数据库上 Bag 相等。≤5% 弱化该假设；5%–10% 记为 inconclusive。

这个审计只测“单个固定数据库实例上的结果不可区分性”。相同输出不能证明一般 SQL 语义等价，也不能证明候选符合用户意图或业务 Role。

## 证据与近邻工作

- 本地证据：`p0_fk_sql_used_mapping_rank_20261107_03` 通过 CPU 标签门，形成 5 个 Smoke 与 108 个 Full 单元、4 个匿名数据库；候选映射总行数 359。该运行的模型审阅一致性门失败，G-reasoner 排序 Smoke 也因 manifest/runner 字段契约不匹配停止，未产生排名结果。
- Text-to-SQL 基准可能包含问题歧义或多种有效 SQL 解释；EMNLP 2023 对跨域 Text-to-SQL 基准做人工复核和等价 SQL 改写，指出单一参考查询会低估或改变模型相对表现：[论文](https://aclanthology.org/2023.emnlp-main.99/)。
- Test-suite accuracy 通过多个合成数据库近似语义正确性，正是为了缓解单一数据库执行结果的假等价：[论文](https://aclanthology.org/2020.emnlp-main.29/)。
- EquiTrace 从查询改写规则构造可回放的 SQL 等价证明：[论文](https://arxiv.org/abs/2610.30100)。本轮只在单个现有 SQLite 实例上做输出反事实，既不是证明系统，也不替代多实例测试。
- 近期 CIDR 2026 对 BIRD 与 Spider 2.0-Snow 的标注错误及问题歧义作了审计：[论文](https://www.vldb.org/cidrdb/2026/text-to-sql-benchmarks-are-broken-an-in-depth-analysis-of-annotation-errors.html)。
- 因此，本审计不声称提出新的 SQL 等价评测方法；它只量化当前 FK mapping 评价样本在静态 BIRD 数据上的可区分性，并判断单映射标签是否需要保留成集合或标记为实例级不可判。

## 候选假设筛选

| 生成视角 | 候选假设 / 可证伪预测 | 最近工作与判断 |
|---|---|---|
| 边界探测 | 对同一表对仅替换一条有效 FK mapping；若映射标签可由当前数据区分，Gold 与所有替代候选的执行结果应不同 | 直接测本地 SQL-used 样本；保留为本轮假设 |
| 结构类比 | 把 FK 等式替换视为编译器 mutation test：保持 SQL AST 其余部分不变，用执行结果看该关系边是否可观测 | 是局部诊断，不是语义等价证明；能把“结构上不同”与“静态实例结果相同”分开 |
| 矛盾反转 | 双 Qwen 高置信一致只有 2/5；模型分歧可能来自参考 SQL 单映射标签，而非单纯提示质量 | EMNLP 2023 基准复核已指出问题歧义和多种 SQL 解释；不再加模型票，改用当前 DB 的反事实输出作独立观测 |
| 预算/效用矛盾 | P2c-R 的完整 Schema 覆盖提高，但 P2d 30 题 Set EX 为 8/8/7，短文本没有正向信号 | [BudgetSchemaBench](https://arxiv.org/abs/2610.00092) 与 [DSR-SQL](https://aclanthology.org/2026.emnlp-main.1688/) 已覆盖 schema budget/双视图相邻问题；不追加通用 packing 对照 |
| 值绑定边界 | P2c 风险审计有 19 题含问题文本不可见的 SQL 常量，其中 9 题可绑定到被删 Values 的同一列；选择性值检索或可恢复性能 | [VLD-Bench](https://doi.org/10.1145/3802029) 直接研究词面/语义 value linking；先不另开重复方向 |
| 修复机制 | P2d.2 的 13 个限定符/作用域类失败可通过 AST 最小编辑修复 | [Post-SQLFix](https://arxiv.org/abs/2610.41472) 与 [SCOPE-SQL](https://aclanthology.org/2026.findings-emnlp.951/) 已覆盖结构诊断、属性约束和模块化修复；本项目 P2d.3 也未过增益门，暂不做通用 SQL repair |
| GFM 机制 | G-reasoner 的收益只出现在某种 seed 或候选拓扑 | 代理排序 7/38 对 27/38、分层未见正向子群，G3 又无正确性标签；当前停止该图变体搜索 |

选中的问题若结果 ≥10%，会改变后续 Mapping@1 的标签解释；≤5% 则削弱“单实例替代映射普遍不可区分”的理由。两种结果都不会建立人类语义标签。

## 实验协议

- **来源/数据：** 复用 `_03` 已冻结并排除旧 60 个审阅问题的私有 manifest；BIRD dev `dev.json` 与 `dev_tables.json` 哈希固定在配置中。原始题目、Gold SQL、映射 ID、数据库名、SQL 变体及执行结果行只留本地。
- **样本：** 5 个既定 Smoke 与 108 个既定 Full；每题至多一个问题×表对，Full 覆盖 4 个匿名数据库。候选共 359 行；样本不扩充、不重抽。
- **干预：** 用 SQLGlot 解析 SQLite SQL。只处理一个唯一、明确的 JOIN alias pair；目标 mapping 的每个列等式必须是顶层 `AND` 中直接限定列之间的等式。把这些等式作为一个 bundle 替换为某一有效候选映射的全部列对，保留原查询其他谓词、SELECT、WHERE、GROUP/ORDER、CTE 等结构。复合 FK 整体替换，不能拆成单列。
- **排除/不可替换：** 多个 SQL-used mapping、重复或缺失等式、多个匹配 alias group、`OR` 内目标等式、列表达式/未限定列、别名或作用域歧义、不能通过只读 SQL 执行的候选。记录数量和原因，不臆造替换。
- **基线：** 原 Gold SQL 的只读执行结果；再把 SQL-used mapping 作为替换候选重放一次，必须与原 Gold 的列名、Set 与 Bag 结果一致。
- **指标：** Full 中完整可执行的单位里，Gold 输出非空的单位比例：是否存在至少一个非目标候选与 Gold Bag 相等（主指标）；同时报告 Set 相等、候选级相等计数、空 Gold 输出数量、不可替换/执行未知数量、4 个匿名数据库分层结果和 Wilson 95% 区间。
- **Smoke 门：** 5/5 都必须有唯一且可安全改写的目标 JOIN；所有 Gold 与候选 SQL 都必须只读执行成功；目标 mapping 重放须 5/5 与原 Gold Set/Bag 相等且输出列相同。任一失败即停止，不改脚本后重用该 run ID。
- **Full 门：** 至少 80/108 个 Full 单元完整执行、至少覆盖 3 个匿名数据库。低于该门仅报告覆盖不足，不解释假设。
- **资源与停止：** `think2sql_20260909` / Python 3.12.14 / SQLGlot 28.0.0；最多 8 CPU 线程、600 秒 wall、300 秒 CPU、4 GiB parent RSS。SQLite 每查询最多 10 秒、50,000 行、64 MiB 输出和 256 MiB SQLite heap；`mode=ro&immutable=1`、`query_only`、只读 authorizer。GPU/模型/外部 API/新依赖/训练均为 0。

## 路线决定

- ≥10% 的非空答案 Full 单元存在 Bag 相等替代映射：静态实例不足以把单映射排序错误直接解释成真实 Role 错误；后续结果需报告实例级等价候选集合，但仍不能声称语义等价。
- ≤5%：没有证据支持静态实例歧义普遍影响此样本的 FK mapping 指标；不代表业务 Role 金标准已建立。
- 5%–10% 或 Full 门失败：`INCONCLUSIVE`。不扩大样本、不继续追加模型审阅。
- 该审计无论结果如何都不启动 G-reasoner 排序，也不改变 `_03` 的已停止状态。

## 仓库与实现

- 用户项目仓库：`https://github.com/bArtyom/gfm-rag`，分支 `research/p0-sql-used-proxy-alignment-20261107`。只在该仓库归档。
- 参考上游：`https://github.com/RManLuo/gfm-rag`，固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；项目仓库许可证 Apache-2.0。该诊断复用项目既有 SQLite 只读 evaluator，不改上游文件或模型。
- 代码：`scripts/text2sql/audit_p0_fk_mapping_instance_equivalence_20261107.py`。
- 配置：`configs/text2sql/p0_fk_mapping_instance_equivalence_20261107_01.json`。
- 私有结果根：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/`；日志根：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/`。
- 报告目录：`docs/research/text2sql/reports/p0_fk_mapping_instance_equivalence_20261107_01/`。
