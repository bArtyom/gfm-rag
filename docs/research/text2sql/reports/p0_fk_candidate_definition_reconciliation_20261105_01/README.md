# P0 FK 候选定义对账

**状态：`STOP_INVALID_SMOKE`。** 两组 P0 packet Smoke 通过；P1.5 Smoke 以 `RuntimeError` 结束，未形成有效输出。按预注册停止规则，未启动 Full、未生成 crosswalk、未生成审阅包。

## 问题

同一数据文件哈希下，历史 P0 v3、P1.5/P2a.5 与 P0 packet 分别报告 **956/174、970/197、1,043/176** 个 FK 命中/多 FK 候选题。当前 P0 packet 因计数与历史冻结期望不一致已停止；本轮只对账代码定义、SQLGlot 版本和可审计逐题集合，不生成角色盲审包，也不新增角色准确率结论。

## 预注册

- 实验计划：[P0 FK 候选定义对账](../../plans/p0_fk_candidate_definition_reconciliation_20261105.md)
- 层级：CPU-only exploratory 实现/标签定义审计，非方法效果或论文主线证据。
- 输入哈希：`dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。运行前还要校验私有 P0/P1.5 artifact。
- 实现版本：P0 packet runner SHA `5c84af91edc6dd39cd1fba39105dfc74b804be17912d91edab5eba2ff180eebc`；P1.5 runner SHA `af59d01d22a6b5d5538231b38c2bf52e0355a9193a5773f40b14d29470ec40cf`；P2a.5 runner SHA `e046595df72d3b684062a54d2fffc2c8df13cae419b056625b8981c20b805085`。
- 环境：`t2sql_code_audit_20261005` Python 3.10.22 / SQLGlot 26.33.0；`think2sql_20260909` Python 3.12.14 / SQLGlot 28.0.0。
- 预算：CPU only；进程 wall/CPU ≤600 秒、RSS ≤4 GiB、≤8 CPU 线程；GPU/model/API/SQL execution/download/install = 0。
- 成功判据：1,534 题、解析 1,534、JOIN-ON 1,140；复现 P0 packet 1,043/176 与 P1.5 970/197；完整解释 SQLGlot 28 下的逐题集合差及 packet 跨版本差异。不能解释则保持 unresolved/NO-GO。
- 私有 artifact 检查确认历史 P0 v3 只保留 956/174 聚合计数，没有逐题标签；P1.5 保留 970/197 聚合与 SQLite FK 实例，但没有逐题 JOIN 标签。P0 v3 将保留为 aggregate-only / unreproducible；P1.5 会从冻结实例表按原规则重新计算，不改写历史产物。
- 冻结 runner：`scripts/text2sql/reconcile_p0_fk_candidate_definitions.py` SHA `9d4e2ec2fa7d44156ae170285951c9df7a617ebde6d23714185cefc5c0749855`；匿名差异汇总器 `scripts/text2sql/compare_p0_fk_candidate_definitions.py` SHA `d1c9123d195e40afaf8e15a02cef823525ac06a1d1c531dade8fac9c3c2d7e9e`。
- 历史 P0 v3 的 956/174 只在存在可复核源码和逐题标签时归因；若只有聚合 artifact，将标为 aggregate-only、unreproducible。
- 停止条件：hash/分母不符、5 题 Smoke 失败、源码不匹配、逐题集合差异无法完整解释、隐私或资源门失败。失败 run ID 不重试；不生成 blind-review packet。

## 运行与结果

### Smoke 结果

| 定义 / 环境 | 处理题数 | 解析成功 | JOIN-ON 题数 | FK匹配题数 | 多FK候选题数 | wall | 峰值RSS | 状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| P0 packet / Python 3.10.22 / SQLGlot 26.33.0 | 5 | 5 | 3 | 3 | 0 | 0.082 s | 0.025 GiB | `SMOKE_PASS` |
| P0 packet / Python 3.12.14 / SQLGlot 28.0.0 | 5 | 5 | 3 | 3 | 0 | 0.361 s | 0.029 GiB | `SMOKE_PASS` |
| P1.5 `golden_join_audit` / Python 3.12.14 / SQLGlot 28.0.0 | 5 | 未形成有效结果 | 未形成有效结果 | — | — | 约1.08 s | 未记下 | `STOP_INVALID` (`RuntimeError`) |

P0 两个 smoke 使用同一固定顺序的前五题，输入哈希均匹配；结果表只报告 smoke 计数。P1.5 smoke 的 runner 捕获异常时只留下通用错误类型，没有异常发生位置；其私有输出文件未生成。为保护预注册边界，不重试该 run ID、不启动全量，也不把该错误当成科学上的支持或反对证据。需要诊断时应另行登记并改进失败回执。

### 决策

- 当前结果不能回答 1,043/176 与 970/197 的逐题集合差，也不能分离 SQLGlot 版本贡献与实现定义贡献。
- 历史 P0 v3 的 956/174 artifact 只有聚合字段，没有逐题标签或可定位的旧版源代码，保持 `aggregate-only / unreproducible`。
- Role Gate 仍为 NO-GO；可信人工角色标签仍为 0。没有 SQL 执行、模型推理、训练、API 调用或 GPU 计算。
- 如需继续，先用独立 run ID 和公开登记改进异常定位（只记录异常类、模块、函数和代码行，不记录 SQL/问题文本），重新通过 P1.5 五题 Smoke 后再决定是否启动 Full。

私有 Smoke 结果与日志不公开；原始题目、Gold SQL、数据库标识和逐题标签均未写入本仓库。
