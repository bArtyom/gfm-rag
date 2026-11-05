# P0 BIRD FK Hop Profile v2：CTE 作用域解析修正

**状态：预注册；修正轮 exploratory 结构审计。** 父运行 `p0_bird_fk_hop_profile_20261105_01` 保留原报告与匿名输出，复核状态为 `SUPERSEDED_PENDING_SCOPE_CORRECTION`。本方案只修正 SQL 表引用解析器的作用域处理，不改研究问题、输入、图、hop 定义、筛选阈值或资源预算。

## 研究问题与修正原因

父运行先收集整个 SQL AST 中的全部表名，再把所有与任意 CTE 名称相同的名称全局过滤。CTE 名称只在其查询作用域内有效；若另一作用域引用了同名真实数据库表，父实现可能误删真实表引用。尚未逐题确认该情形实际影响了多少父运行记录，因此不回写或修正父运行数字。

本轮使用 SQLGlot `traverse_scope(parsed)` 的 `scope.selected_sources`，只收集当前作用域解析为 `exp.Table` 的基础表源。CTE 与派生表以各自作用域表示，不再用全局别名集合过滤名字。

## 冻结条件

- 数据仍为同一 BIRD dev `dev.json` 与 `dev_tables.json`；SHA-256 分别为 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`、`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 图仍为每库一张无向、无权、表级声明 FK 图；同表对多 FK 映射在结构审计中折叠为一条边。
- hop 仍为所有 SQL 基础表终端间的精确最小 Steiner 树边数，使用 Dreyfus–Wagner 子集 DP，最多 12 个终端。
- 完整性门仍要求每题恰好归入一个状态、Full 表引用解析率至少 95%；资源筛选线仍为连通 `h≥3` 至少 30 题且覆盖至少 3 库。后者仅为资源筛选，不是方法效果或统计功效门槛。
- 只运行 5 题 Smoke；5/5 必须解析并映射全部表引用后才可运行一次 1,534 题 Full。CPU-only、最多 4 线程、600 秒硬上限；模型/API/GPU/SQL 执行/训练均为 0。
- 新配置和输出路径使用独立 `_02` run，不覆盖 `_01`。结果按可复现文档汇总匿名全局计数，不记录题目、SQL、schema 名、逐题 hop 或数据库级稀疏分布。

## 决策与停止规则

Smoke 任一题解析或 schema 映射失败即停止，保留回执，不运行 Full。Full 若解析率不足 95% 则标记 `INCOMPLETE`；若完整，则只报告 v2 结构画像并与 v1 聚合及 SchemaScope 已发表的约 22% `h≥3` 报告作定义层面的谨慎比较。若两者差异仍大，不做更多解析器/阈值扫描，停止 BIRD 高跳数方法拓展并记录定义差异为未解决。

无论 v2 结果如何，均不计算 FK Role Accuracy、不评估 GFM/Dense/BM25 路径排序、不生成或执行 SQL，也不解除双人 Role 标签门。未来 FK mapping rank Pilot 仍需两名真实审阅者先完成独立标注与共识。

## 可复现配置

- 机器配置：[`p0_bird_fk_hop_profile_v2_20261105.yaml`](../../../../configs/p0_bird_fk_hop_profile_v2_20261105.yaml)。
- 执行器：[`audit_bird_fk_hop_profile.py`](../../../../scripts/text2sql/audit_bird_fk_hop_profile.py)，其 source commit 和 SHA 在启动回执及结果报告中登记。
- 独立输出：`/mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_02/{smoke,full}`。
- 日志：`/mnt/liansp3/logs/p0_bird_fk_hop_profile_20261105_02/`。
