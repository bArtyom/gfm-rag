# P2d.2：封存 SQL 失败根因归因

**状态：已预注册，未运行。** 本轮承接 P2d.1 完成报告中的下一步建议，只分析 P2d 已封存的 90 条预测。它不重算 P2d 的 Set/Bag 指标，不更改 P2d.1 的评测结果，也不解开 FK Role 双人标签门。

## 痛点与研究问题

P2d.1 在固定分母下确认三臂均有不可执行预测：E0 为 4 条解析失败、6 条缺列；E1 为 2 条解析失败、8 条缺列；E2 为 4 条解析失败、4 条缺列。总计 28/90。现有报告只给出这两类错误计数，还不能判断缺列是否来自检索上下文未包含正确字段，还是生成器写出了错误标识、错误别名或作用域。

本轮问题：对 28 条失败做一次有界、只读的结构归因，能否在不看新题、不调用模型的前提下，区分“上下文未提供字段”与“生成 SQL 指向错误字段/别名”，并确认解析失败是包装格式还是语句结构问题？

因果链：失败类型归因 → 比较报错字段与冻结 Schema/各臂可见节点 → 观察错误是否可由上下文缺失解释 → 决定下一轮是测试可见性修复、生成有效性，还是暂停等待更好的证据。

## 方案比较与本轮选择

1. **直接在同 30 题调 prompt / packing：** 不采用；会把已查看结果的数据继续用于调参，且不能给出独立证据。
2. **启动新 SQL 生成或换模型：** 不采用；这会新增模型变量并混淆已有失败原因。
3. **只读检查封存输出：** 采用；静态解析 10 条语法失败，对 18 条旧评测已判为 `missing_column` 的查询，仅在可信数据库快照上做只读 SQLite `EXPLAIN` 编译，不读取查询结果、不执行 SELECT。将精确报错标识只在内存中映射到冻结 Schema 与 prompt 可见节点，公开结果只保留匿名计数。

## 预注册判据

- **固定分母：** 30 题 × E0/E1/E2 = 90 条；失败分析分母固定为 28，分别为 10 parse、18 missing-column。所有其他结果仍计入 90 条全体分母。
- **主指标：** 28 条失败中能被确定性规则高置信归类的比例；类别为 `schema_column_omitted_from_context`、`column_visible_but_reference_invalid`、`column_not_in_schema`、`qualifier_or_scope_mismatch`、`parse_format_issue`、`parse_structure_issue`、`unresolved`。
- **可见性配对诊断：** 对每条“Schema 中存在但本臂没有选入上下文”的缺列，统计另外两臂是否选入同一个字段节点；只报告匿名问题数和臂间计数，不把这项相关性当作因果收益。
- **成功判据：** 至少 23/28 条失败达到高置信分类；否则报告归因覆盖不足，不提出新的方法介入。
- **下一轮决策规则：** 若至少 9/18 缺列失败属于上下文缺失，且至少 4 个不同问题的同一字段在另一臂可见，则只登记“字段可见性保护”候选，后续必须在新的冻结样本验证。若至少 9/18 属于字段幻觉、可见字段误用或别名/作用域错误，则优先考虑生成有效性诊断，不调整检索。均未达到或未知过多则停止，不在原 30 题上继续扩试。
- **停止条件：** 任一输入/数据库/预测封存哈希不匹配、P2d.1 失败类别与冻结聚合不一致、只读授权失败、EXPLAIN 无法复现旧 `missing_column` 错误、资源超限或输出可能暴露私有内容时，保留现场并停止；不重试、不更新旧结果。

## 数据、实现与资源

- 输入固定为 P2d 的准备包、90 条封存预测、P2d.1 Gate 2 90 条匿名内部状态及其对应 BIRD dev 数据库快照；不读参考 SQL 来构造方法特征，不查看问题级表现后增删案例。
- 执行器：`scripts/text2sql/diagnose_p2d2_failures.py`。输出仅含整体/按臂匿名计数、哈希和运行资源回执；不写出题目 ID、数据库/表/列名、SQL、SQLite 原始错误文本、路径或 prompt。
- 资源预算：CPU-only，最多 4 线程、300 process CPU 秒、4 GiB RSS；对最多 18 条 SQL 各做一次只读 EXPLAIN 编译，单条硬限 2 秒；没有查询结果、LLM/API/GPU/训练/下载/依赖安装。
- 环境：复用 `think2sql_20260909`，固定 Python 3.12.14、SQLGlot 28.0.0 与系统 SQLite 版本；先跑不含私有数据的合成 smoke，再检查资源和封存哈希，然后运行一次 Full。
- 私有输出使用资源索引别名 `sources/results/gfmrag_p2d2_frozen_failure_attribution_20261105_01/`；日志使用 `logs/gfmrag_p2d2_frozen_failure_attribution_20261105_01/`。目录须新建且权限 0700；不得覆盖。
- GitHub 归档：本报告、配置与匿名聚合只提交到 `bArtyom/gfm-rag` 的本实验分支；不得上传 SQL、问题、Schema、逐题结果或本地日志。

## 执行前固定输入指纹

- P2d predictions payload SHA-256：`e88bf42f22a73b6b56af96a5d3ea88d69252c33509bb72da5b8cfde2f7474ea5`
- P2d prediction seal file SHA-256：`f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3`
- P2d prepared seal SHA-256：`334e388af338c7f20575aa81a86ff7184e526716b251cd1b48955b4134172aaa`
- P2d.1 private Gate 2 outcomes SHA-256：`9b7fec27ee0d23cddf76b4bf842ddde530a2f1bbb001fa449218d3b049b3711d`
- `dev_tables.json` SHA-256：`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`

冻结结果与文献指导分别见 [P2d.1 完整审计报告](../reports/p2d_1_eval_audit_20261022_02/README.md) 和当前项目 [README](../README.md)、[实验路线图](../experiment-roadmap.md)、[复现规范](../reproducibility-contract.md)。
