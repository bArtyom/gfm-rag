# P0 Mini-Dev JOIN 等式未解析原因审计

**状态：预注册，尚未运行。** 实验 ID：`p0_minidev_join_scope_taxonomy_20261106_01`。这是对上一轮标签质量门失败的有界 CPU 诊断；不恢复或重跑 G-reasoner 排序。

## 痛点与研究问题

上一轮对冻结的 500 条 BIRD Mini-Dev reviewed 样本解析成功 500/500，但 663 个限定 `JOIN ON` 列等式中仅 523 个映射到官方 schema 列；140 个未解析，覆盖率 78.88%，低于 95% 标签门。旧报告没有将这 140 项按作用域、派生表或列名原因分类。

**研究问题：** 这些未解析等式中，有多少只是 SQLGlot 当前适配未追踪的 CTE/派生表直接列投影别名？保守地追踪直接投影后，能否把可解析覆盖率提高到 95%？

**核心假设：** 至少 107/140 个未解析等式可沿唯一的直接列投影逐层映射到官方 SQLite DDL 中的物理表列。107 是达到 630/663（95.02%）所需的最小新增等式数。表达式投影、歧义投影、未限定列、重复别名和不支持的查询结构不做猜测，继续标为未解析。

## 实验层级、预算和停止条件

- 层级：`exploratory` 数据/解析器错误分类；不是方法效果实验，不输出 FK Role 准确率。
- 预算：固定 500 题；5 题 Smoke，随后独立处理其余 495 题 Full；按新 experiment ID 做确定性问题级拆分，不重叠。
- 主指标：直接投影追踪后 `JOIN ON` 限定列等式的覆盖数/比例；最低成功筛选门为 ≥630/663（≥95%）。
- 诊断指标：140 项 unresolved equality 的互斥错误分类；unresolved operand 原因计数；新旧解析器 scope error；已解析项的回归数；数据库匿名宏计数。
- 运行前逻辑自检：使用人工构造的 SQLite/SQLGlot fixture 检查直接 CTE 投影、直接派生表投影、嵌套投影可恢复；算术表达式、缺失输出列、物理列不存在、重复 alias 不得恢复。
- Smoke 通过条件：5/5 SQL parse；原解析器计数与冻结实现一致；分类分母守恒；逻辑自检全部通过；无 scope error、输入哈希变化或输出覆盖。
- Full 停止条件：输入/配置 hash 不符、Smoke/Full 键重叠或覆盖不全、原解析器基线偏离 523/663、分类不守恒、任一逻辑 fixture 失败、scope error 非零、输出目录已存在。
- `Full` 达到 ≥630/663 仅说明解析覆盖门可能满足；仍不自动启动 G-reasoner、Dense、BM25 或模型审阅。未达到则停止 FK mapping 数据线，并报告错误类型。

## 解析策略冻结

1. 只分析 SQLGlot `JOIN ... ON` 中左右两侧均为限定列引用的等式，分母与前一轮完全相同。
2. 原始解析器实现作为 baseline 原样调用；不改写旧 runner 或旧输出。
3. 新增 resolver 仅允许沿唯一、直接投影列逐层回溯至已冻结官方 SQLite DDL 中的表/列。每层都必须能一对一解析到投影表达式和源 alias。
4. 对函数/算术表达式、`UNION`、星号展开、非直接投影、重复/歧义别名、未限定中间列、缺失输出列及其他不支持结构一律不解析，不进行模糊匹配或模型判断。
5. 每条原未解析 equality 只进入一个预先定义的主类别：`direct_projection_recoverable`、`duplicate_or_ambiguous_alias`、`derived_expression_or_union`、`derived_output_missing`、`physical_column_missing`、`alias_not_found_or_correlated`、`unsupported_or_other`。左右 operand 原因另行聚合，不与 equality 分母混淆。
6. 新 resolver 已解析、旧 resolver 未解析的项记为 recoveries；旧 resolver 已解析但新 resolver 不能解析的项记为 regression 并触发停止。只公开匿名聚合，逐题键和原因留本地私有目录。

## 输入、环境与复现边界

- 上游论文实现仓库仍为 `https://github.com/RManLuo/gfm-rag`，固定源码 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；本审计只复用其已固定 FK artifact，不修改上游代码。
- 项目仓库：`https://github.com/bArtyom/gfm-rag`，分支 `research/minidev-sql-fk-use-rank-20261106`。仓库根 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 与 `/mnt/liansp3/sources.md` 已核对。
- Mini-Dev 2026 reviewed revision `38818fcbc46038129592680c51b2c8b597aac27c`，500 行；JSONL SHA-256 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`。
- 官方 SQLite DDL SHA-256 `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b`。
- 复用环境 `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2；CPU only，不安装或升级依赖。
- 不加载模型、不调用外部 API、不运行 SQL 查询数据库、不访问 Gold SQL 以外字段；只读 Gold SQL AST 结构及 DDL 列名。Gold SQL 不作为检索/模型特征。
- Smoke/Full 私有目录分别位于 `/mnt/liansp3/sources/results/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/` 下；日志在对应 `/mnt/liansp3/logs/` 路径；新目录不得覆盖。
- 公开产物为本目录下完整报告及匿名 `aggregate_summary.json`；不公开题目、SQL、问题键、表列名、逐题标签或模型数据。

## 结果解释

通过门槛不等于 SQL 语义正确、不等于 JOIN role 真值，也不解除人工 Role 标签要求。实验不会因解析覆盖提升而重算或改写此前 `p0_minidev_sql_fk_mapping_rank_20261106_01` 的结果。任何后续排序必须另行审阅最新仓库指导、独立预注册，并且仍受当前 GFM 排序支线停止决定约束。
