# P0 canonical P1.5 FK crosswalk 复核计划（2026-11-05）

## 研究问题与假设

**问题：** P0 v3 wrapper 把 SQLite FK artifact 的原始 `instances_private` 全集传给 P1.5 `golden_join_audit`。canonical P1.5 汇总入口使用的却是 `valid_instances_private`。排除 `valid_endpoints=false` 的记录后，P1.5 与同环境 packet 实现的题级 FK-match 和 multi-FK-candidate 差异是否仍存在？

**假设：** 使用每个数据库中 `valid_endpoints=true` 的实例，能够复现 P1.5 的 canonical 输入集合；与 v3 未过滤 wrapper 的题级结果相比，变化只来自无效 FK 记录的排除。相对 packet 的差异若仍存在，应归因于两套实现定义的差异，不能视为 Role 准确率。

**层级与主张边界：** P0 输入/标签定义复核，exploratory CPU-only。不是检索、图推理、SQL生成方法实验，不创建人工 Role 标签，也不恢复缺失源码的历史 956/174 结果。

## 依据与冲突处理

- 用户提供的实验守则要求实验前阅读目标仓库指导、使用独立 run ID、先 Smoke、全程留痕并归档结果。
- 目标仓库为 `bArtyom/gfm-rag`。实验前核对根 `README.md`、研究 `README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`，并阅读 v3 P0 分支的计划和报告。
- GitHub `main` 的研究首页/路线图停留在较旧状态，与 v3 分支后续 FK 对账报告不一致。本次采用更具体且更新的 v3 FK 对账报告作为直接指导，并在结果中记录该冲突。
- v3 代码审计确认 `run_p1_5_diagnostics.py` 的 canonical 汇总路径传入 `valid_instances_private`；每条实例的有效性定义为布尔字段 `valid_endpoints`。本轮只修正 wrapper 过滤，不改变 `golden_join_audit`、packet parser、SQLGlot 或定义规则。

## 冻结数据和比较臂

- 数据为 BIRD dev 1,534 题、11 个数据库；`dev.json` 和 `dev_tables.json` 的 SHA-256 分别固定为 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` 和 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- FK artifact 固定 SHA-256 `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。读取时先对同一字节缓冲区做摘要校验再解析 JSON；要求 11 个数据库、103 条原始实例、100 条有效实例、3 条无效实例，且 `valid_endpoints` 均为布尔值。
- 新实验臂：Python 3.12 / SQLGlot 28，冻结 P1.5 `golden_join_audit`，过滤后有效实例，5 题 Smoke、条件式 1,534 题 Full。
- 冻结参考臂 A：v3 的 packet / Python 3.12 / SQLGlot 28 Full，结果 SHA-256 `13401f39e6744a4c47e3a5f36b59be468335f79f04594db27c3e662ce9ba75f3`。
- 冻结参考臂 B：v3 的 P1.5 原始实例 wrapper Full，结果 SHA-256 `4736e320aff6da6bdc56f0ddd56c7887a85014cf9577c6dd568b7f738df0f883`。它用于测量过滤改变了哪些标签，不作为 canonical P1.5。
- 三臂题目顺序及题目键集合必须一致；比较过程只保留题目键 SHA 和匿名标签，不公开问题、Gold SQL、数据库名、原始 artifact 或逐题结论。

## 运行门、预算与停止条件

1. 运行前登记代码、配置、结果目录别名、输入摘要、参考结果摘要、命令和环境，并推送到项目研究分支。
2. 在 `think2sql_20260909`（Python 3.12.14 / SQLGlot 28.0.0）运行 5 题 Smoke。Smoke 必须完成 5/5 解析、5/5 预期 JOIN-ON 计数路径、过滤集合结构检查；失败即停止，不在同一 run ID 重试。
3. Smoke 全部通过后运行 1,534 题 Full。硬数据门为 1,534/1,534 解析成功、1,140 道含 JOIN-ON 问题、11 个数据库/103/100/3 FK 实例计数，以及三臂完整一致的题目 SHA 集合。FK-match 和 multi-FK-candidate 数是结果，不作停止门；canonical 历史参照 970/197 只作对照，不强制通过。
4. 只有 Full 数据门通过后生成匿名 crosswalk：比较“v3 未过滤 P1.5 → canonical 过滤 P1.5”以及“packet-28 → canonical 过滤 P1.5”，分别报告 parse、JOIN-ON、FK match 和 multi-FK candidate 的逐题一致/不一致计数及 P1.5 证据类别分层。
5. 资源上限：每个进程 wall/CPU ≤600 秒，RSS ≤4 GiB，最多 8 线程，顺序执行；累计 CPU 上限 1,800 秒。CPU-only，GPU、模型、API、SQL执行、训练、下载和依赖安装均为 0。
6. 输入/代码/参考摘要不匹配、有效性字段不合约、分母异常、题目键集合不一致、隐私输出违规或资源超限时停止。任何失败都保留现场，不覆盖历史记录，不继续 Role accuracy 或 SQL EX。

## 可复现产物

- 新实验 ID：`p0_fk_canonical_crosswalk_20261105_01`
- Smoke run ID：`p0fk_canonical_p15_smoke_py312_sqlg28_20261105_01`
- Full run ID：`p0fk_canonical_p15_full_py312_sqlg28_20261105_01`
- 执行器：`scripts/text2sql/reconcile_p0_fk_candidate_definitions_canonical.py`
- crosswalk 汇总器：`scripts/text2sql/compare_p0_fk_candidate_definitions_canonical.py`
- 结果与逐题匿名 SHA crosswalk 按[报告目录](../reports/p0_fk_canonical_crosswalk_20261105_01/README.md)的隐私边界保存。
