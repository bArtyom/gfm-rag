# P0 FK 候选定义对账

**状态：已预注册；尚未读取本轮 BIRD 问题/Gold SQL 或私有逐题产物，尚未运行 Smoke/Full。**

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
- 历史 P0 v3 的 956/174 只在存在可复核源码和逐题标签时归因；若只有聚合 artifact，将标为 aggregate-only、unreproducible。
- 停止条件：hash/分母不符、5 题 Smoke 失败、源码不匹配、逐题集合差异无法完整解释、隐私或资源门失败。失败 run ID 不重试；不生成 blind-review packet。

## 运行与结果

待运行。结果、异常、私有产物位置和最终结论将在本目录追加；原始题目、SQL、数据库标识、逐题标签和日志不公开。
