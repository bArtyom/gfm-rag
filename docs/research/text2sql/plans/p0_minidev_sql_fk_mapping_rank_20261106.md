# P0：新版 BIRD Mini-Dev Gold-SQL FK 映射排序检验

**状态：** 已修订预注册；首次 Smoke 在解析 SQL 前因 schema inventory 版本校验停止，唯一一次工程恢复 Smoke `002` 待运行。标签覆盖不足即停止，不启动模型排序。
**实验 ID：** `p0_minidev_sql_fk_mapping_rank_20261106_01`
**层级：** 一次独立任务集迁移诊断；不是主结果，也不是新算法主张。

## 痛点和可证伪假设

截至 2026-11-06，当前 BIRD-dev FK 映射排序线已在三模型代理标签上完成一次 G-reasoner 与 Dense 比较，结果为 7/38 对 27/38，之后按停止规则不再用同一批代理标签调参。可信人工 FK-role 标签仍为 0。新版官方 BIRD Mini-Dev 提供经过人工复核的 SQLite Gold SQL，可定义一个更窄且可复核的目标：**在 Gold SQL 的显式 JOIN 条件实际采用了哪条已声明 FK mapping**。

**核心假设：** 在冻结的候选 table-pair 和 FK mapping 集合中，官方冻结 G-reasoner 对 Gold-SQL-used mapping 的 Top-1 命中率，比相同 Query/mapping 向量上的 Dense Cosine 至少高 5 个百分点，且至少净救回 4 个问题×表对。若未达门，停止该排序方向，不改 seed、图结构、编码器或阈值。

这个标签表示“参考 SQL 选择的映射”，不表示它是唯一语义正确的连接，也不等同于人类 FK Role 标注。评价只覆盖已知两个端点后的映射辨别；不测端到端表发现、缺失 FK、SQL 执行准确率或跨数据库泛化。

## 数据、模型和冻结输入

- 项目仓库：用户指定的 `https://github.com/bArtyom/gfm-rag`；执行分支 `research/minidev-sql-fk-use-rank-20261106`。登记基线为 BIRD audit 分支远端 commit `b73df4669d7ddb20e29226f8b0a9d0d8fa8bc704`。
- 主数据：BIRD 官方 HF `birdsql/bird_mini_dev`，固定 revision `38818fcbc46038129592680c51b2c8b597aac27c`，`data/mini_dev_sqlite.jsonl`，500 条，SHA-256 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`，CC BY-SA 4.0。
- 官方 SQLite schema：同一 revision 的 `baseline_inference/schemas/sqlite.json`，SHA-256 `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`。BIRD `dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；FK mapping 定义复用 P1.5 artifact `fk_gate_private.json`，SHA-256 `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。
- 本地数据路径：`/mnt/liansp3/sources/datasets/bird_mini_dev_2026_reviewed/mini_dev_sqlite.jsonl`、`.../sqlite_schema.json`、`/mnt/liansp3/sources/datasets/bird/dev/dev_tables.json`。
- 旧版 2025 Mini-Dev 只用于版本来源审计，不混入分母。新版与旧版 question IDs 不可直接配对；按 `(db_id, question)` 精确匹配仅 13/500。
- G-reasoner-34M 和 Qwen3-Embedding-0.6B 使用本地已校验快照；不训练、不下载、不换权重。映射文本、四类有向关系、双端 table seed、Qwen3 query instruction、stable mapping-ID tie-break 与已完成的 2026-11-06 代理 Pilot 完全一致。Query 只用 Mini-Dev `question`，不使用 `evidence`、Gold SQL 或预测标签。SQL 只供隔离的解析/标签步骤。

## 标签和分析单位

1. 用 SQLGlot 28.0.0、`read="sqlite"` 解析 Gold SQL；只收集显式 `JOIN ... ON` 中跨表列等式。`WHERE` 隐式连接、`USING`、无法唯一解析别名、未知列/表和解析失败均按独立原因计数，不推断补全。
2. 将等式映射到固定 FK artifact 中完整的有序 mapping identity。比较时表名和列名大小写不敏感；重复身份按 `(child_table, parent_table, ordered_column_pairs)` 合并，保留字典序最小的 mapping ID。左右操作数可反转；复合 FK 的有序列对必须全部出现在**同一 JOIN ON 且同一别名对**中，不跨 JOIN 或 SQL 子查询作用域拼接。若同一 join 对上多个不同完整 mapping 被 SQL 同时使用，保留为多正例接受集合；没有匹配 mapping 的 join 不纳入排名。
3. 只有 table pair 去重后至少含两个不同 FK mapping、且 Gold SQL 明确匹配至少一个候选时，该问题×表对才进入排序分母。候选集由该 pair 的全部有效、身份唯一的已声明 FK mappings 构成。
4. 在读取 SQL 标签前，按 `SHA256(experiment_id + db_id + question_id)` 稳定选 5 个问题作为 Smoke；这些问题的全部 join pairs 从 Full 排除。公开结果不得包含题目、SQL、问题 ID、数据库名、表列名、mapping ID 或逐题排名。

## 指标、门槛、预算和停止规则

- 主比较：Gold-SQL-Mapping@1（G-reasoner 对 Dense Cosine）；辅助：@3、MRR、配对净救回、BM25 与稳定 ID 次序。若所有方法 @3 饱和，注明其无区分力。
- 启动 Full 的标签门：SQLGlot parse success 至少 98%，带限定符且两端均为 column 的 `JOIN ON` 等式解析覆盖至少 95%；Smoke 排除后至少 30 个可评分问题×表对，覆盖至少 3 个数据库。所有 500 SQL 的 parse/alias/column/FK 映射状态都计入聚合，不能静默丢弃。
- Full 启动前重新校验 Smoke 私有结果的运行 ID、数据哈希、5 个唯一题目键与 5 条审计记录；Full 与 Smoke 必须不重叠，并恰好覆盖 500 条唯一题目。重复别名的等式计入限定 JOIN 等式分母，但不能用于正例标签。
- CPU 标签审计复用已有 `think2sql_20260909` 环境（Python 3.12.14、SQLGlot 28.0.0、SQLite 标准库），不安装或修改依赖；官方 SQLite DDL 用内存 SQLite 读取列清单，并与 BIRD `dev_tables.json` 交叉核验。排序模型仍使用下方冻结的 GFM 环境。
- 正向筛选门：G-reasoner 相对 Dense @1 至少 `+5 pp`、净救回至少 `+4`，且至少两个各有 `n≥5` 的数据库净救回为正。它是筛选门，不是显著性检验。
- 先 5 题 Smoke，Smoke 通过后只跑一次剩余 Full。一次尝试的预算：1 张空闲 RTX 4090、GPU allocated ≤8 GiB、RSS ≤16 GiB、wall ≤20 分钟；单任务资源检查须在运行前刷新。固定本地 conda 环境 `gfmrag_greasoner_20261022`，Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence Transformers 5.1.1；不安装或升级依赖。
- 任一输入哈希/Schema/候选身份门失败、解析代码不能保持列和作用域一致、覆盖门不足、Smoke 非有限输出或资源超限：保留现场并停止，不用同一 run ID 重试；只有先登记新 attempt 和纯工程原因，才允许另行恢复。
- **2026-11-06 amendment 001（运行时 schema 版本兼容修正）：** `cpu_smoke_001` 在读取/解析 Gold SQL 前停止，原因是预检错误要求官方 2026 Mini-Dev SQLite DDL 与旧版 BIRD full-dev `dev_tables.json` 表集合完全相等。只读差异审计显示：11 个数据库中 10 个完全相同；其余 1 个在 Mini-Dev 官方 DDL 中新增 1 张表，已有表的列集合一致。没有读取或统计任何 SQL 标签。固定 HF revision 的官方 SQLite DDL 是本实验已登记的列名权威来源；旧版 `dev_tables.json` 只作为兼容性交叉检查。因此修正为：旧清单中的每张表/列都必须存在于官方 DDL，允许官方 DDL 有新增表/列，并在聚合中只记录新增数量。其余输入、标签、分割、模型、阈值和假设不变。保留 `smoke_001` 失败现场；登记 `smoke_002` 为唯一一次工程恢复，Full 至多一次；`smoke_002` 若再遇到输入/Schema/候选身份错误则停止，不再重试。
- 本地 Qwen embedding 每批真实输入 token 使用共享 `api_usage_ledger.record_request` 记账，输出 token 为 0；无外部 API 请求。GPU forward 时间、token 和外部 API 费用分开汇报。

## 近邻与新颖性边界

- `SchemaGraphSQL` 已用 FK 图和路径搜索进行 schema linking，并在 BIRD Mini-Dev 报告 schema-linking 结果；`JoinGR` 已把 join graph 用于查询条件化 table retrieval；`Rethinking Schema Linking`、`LitE-SQL` 和 `DSR-SQL` 覆盖双向检索、向量 schema retrieval 与完整/裁剪 schema 的互补路径。
- 因此本轮不是新方法主张；它只回答冻结 G-reasoner 的 FK 映射节点排序能否迁移到新版人工复核 SQL 的实际 join mapping。观察结果不能证明语义 Role 准确率、QuadGraph 原论文整体效果或端到端收益。

## 预期产物

- 预注册与配置：本文件和 `configs/text2sql/p0_minidev_sql_fk_mapping_rank_20261106.json`。
- 执行代码：`scripts/text2sql/audit_minidev_sql_fk_labels.py` 与 `scripts/text2sql/run_minidev_sql_fk_mapping_rank.py`。
- 私有输入、Smoke/Full 原始逐题输出、manifest 和日志留在 `/mnt/liansp3/sources/results/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/` 与 `/mnt/liansp3/logs/gfmrag_p0_minidev_sql_fk_mapping_rank_20261106_01/`，每个 attempt 使用独立目录。公开报告与匿名聚合归档到 `docs/research/text2sql/reports/p0_minidev_sql_fk_mapping_rank_20261106_01/`，提交并推送到该项目分支后必须回读核验。
