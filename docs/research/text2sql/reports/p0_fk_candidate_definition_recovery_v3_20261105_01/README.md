# P0 FK 候选定义恢复 v3：更正冻结指纹后的三臂复核

> **状态：`CROSSWALK_COMPUTED_REVIEW_REQUIRED`（2026-11-05）。** 三臂 Smoke、三臂 Full 和匿名 crosswalk 已运行完成。运行后代码复核发现 P1.5 wrapper 使用了未过滤的 FK instance 列表；因此本 crosswalk 的 970/197 是该 wrapper 的实际输出，不能直接当作 canonical P1.5 有效实例口径。详见“运行后发现的适配差异”。本轮是 CPU-only 审计，不是 QuadGraph/GFM 方法增益实验。

## 研究问题与假设

v1/v2 两次 P1.5 Smoke 使用了同一个错误冻结摘要并在解析前停止。v2 中同一字节缓冲区、分块 helper 与独立 `sha256sum` 对目标文件计算出相同摘要，文件身份稳定。v3 仅把此摘要更正到经独立确认的文件指纹，重跑三臂的 smoke 门，并在三臂全部通过时按既定门槛运行 Full。

核心假设：失败原因是先前登记的输入指纹与指定 artifact 不匹配；纠正后，P1.5 同字节摘要/JSON 解析门及三臂 smoke 均通过。任一完整性、解析、环境、计数或资源门失败即可证伪并停止。

## 预注册

- **实验 ID：** `p0_fk_candidate_definition_recovery_v3_20261105_01`
- **层级：** exploratory CPU-only 输入完整性与 FK 标签定义审计；不属于方法效果证据。
- **核心假设、预算、成功与停止门：** 见 [实验计划](../../plans/p0_fk_candidate_definition_recovery_v3_20261105.md) 和 [机器可读配置](experiment_config.json)。
- **项目仓库/基线：** `bArtyom/gfm-rag`，v2 结果 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e`；新分支 `research/p0-fk-definition-recovery-v3-20261105`。
- **执行源码：** `scripts/text2sql/reconcile_p0_fk_candidate_definitions_v3.py` 与 `scripts/text2sql/compare_p0_fk_candidate_definitions_v3.py`；哈希见配置。只更新 runner 的 run ID 和 FK artifact 冻结摘要，不改 packet/P1.5 算法及计数定义。
- **数据：** 固定 BIRD dev 1,534 题，只用于开发/诊断。输入 SHA 与 artifact 正确冻结值见配置；SQL、问题文本、逐题哈希和私有 artifact 内容不上传。
- **环境：** Python 3.10.22/SQLGlot 26.33.0 与 Python 3.12.14/SQLGlot 28.0.0，复用已存在 Conda 环境。
- **执行命令、run ID、资源预算、硬件快照、输出路径：** 见配置、运行日志和最终回执。

## 执行记录与结果

### 注册、实现与输入

- **项目仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-definition-recovery-v3-20261105`。预注册 commit 为 [`1514a20`](https://github.com/bArtyom/gfm-rag/commit/1514a2017afa245439d6e7a3bd28bbd47d949a0a)；注册代码、配置和报告已在运行前逐项做 GitHub blob SHA 回读。
- **本轮实现差异：** v3 runner 只更改实验 ID 和 P1.5 artifact 的冻结 SHA；crosswalk runner 只更改实验 ID。packet/P1.5 解析与候选定义、题序、分母、预期 Full 计数和停止门均沿用 v2。运行器及比较器 SHA-256 见 [配置](experiment_config.json)。
- **指导版本：** 运行前已阅读远端基线 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e` 的根 README、研究 README、路线图及复现规范；文件 blob SHA 见配置。
- **数据：** BIRD dev 1,534 题，11 个数据库；这是重复使用过的开发/诊断数据，不是独立测试集。运行时 `dev.json` 和 `dev_tables.json` SHA 分别匹配 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` 和 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- **纠正后的 FK artifact SHA：** `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。Smoke 和 Full 的同字节缓冲区 SHA、旧分块 helper SHA 与冻结值一致；文件大小 76,177 字节，身份稳定，JSON 从已校验字节解析。
- **环境：** packet/SQLGlot 26 使用 Python 3.10.22；packet 与 P1.5/SQLGlot 28 使用 Python 3.12.14；沿用 `t2sql_code_audit_20261005` 和 `think2sql_20260909`，没有安装或升级依赖。
- **硬件/预算：** CPU-only，最多 8 线程；每进程 wall/CPU ≤600 秒、RSS ≤4 GiB；三组 Smoke、三组 Full、一次比较器运行，累计 runner CPU 约 5.52 秒；峰值 RSS 0.0454 GiB。运行前可用内存约 443 GiB、磁盘约 112 TiB；GPU 未分配。外部 API、模型推理、GPU 任务、SQL 执行、训练均为 0。

### Smoke 与 Full

| 定义 | Smoke | Full 解析 / JOIN-ON | FK 匹配题 | 多 FK 候选题 | Full wall / CPU / 峰值 RSS |
|---|---:|---:|---:|---:|---|
| packet / Python 3.10 / SQLGlot 26 | 5/5 parse | 1,534 / 1,140 | 1,043 | 176 | 1.675 / 1.674 秒 / 0.0264 GiB |
| packet / Python 3.12 / SQLGlot 28 | 5/5 parse | 1,534 / 1,140 | 1,043 | 176 | 1.159 / 1.155 秒 / 0.0308 GiB |
| P1.5 `golden_join_audit` / Python 3.12 / SQLGlot 28 | 5/5 parse | 1,534 / 1,140 | 970 | 197 | 1.235 / 1.856 秒 / 0.0454 GiB |

所有 Smoke 均为 5 题解析成功。P1.5 的 Smoke 同时确认实际摘要、旧 helper 摘要与冻结摘要一致，文件身份稳定，JSON 解析通过。三个 Full 都达到 1,534 题、1,534 parse 成功、1,140 个 JOIN-ON 分母及各自预登记 FK 计数。

### 匿名 crosswalk

三份 Full 结果的题目 SHA 集合一致（1,534/1,534）。两个 packet 环境的题级 FK-match 与 multi-FK 标签完全一致。packet-28 与本轮 P1.5 wrapper 在相同 Python 3.12/SQLGlot 28 环境下的原始 crosswalk 为：

- **FK 匹配：** 两者都匹配 955 题；packet-only 88 题；P1.5-only 15 题；两者都不匹配 476 题。差异总数 103，与 1,043 对 970 的汇总差一致。
- **多 FK 候选：** 两者都有 176 题；P1.5-only 21 题；packet-only 0 题；两者都无候选 1,337 题。差异总数 21，与 176 对 197 的汇总差一致。
- **按 P1.5 证据类分层：** packet-only FK match 中 22 题被 P1.5 标为 ambiguous、66 题标为 unmatched；P1.5-only 中 14 题为 exact、1 题同时含 exact 与 unmatched 证据。多 FK 候选新增的 21 题在 P1.5 结果中均有非零 role-candidate joins。
- 所有定义的 parse 与 JOIN-ON 标签一致。完整匿名聚合见 [crosswalk_aggregate.json](crosswalk_aggregate.json)；逐题哈希和交叉表只保存在权限 `0600` 的本地私有结果中。

### 运行后发现的适配差异

只读对照执行器和原 P1.5 汇总入口使用的 FK instance 集合不同。`run_p1_5_diagnostics.py` 同时构造 `instances_private`（原始实例，包含 `valid_endpoints` 字段）和 `valid_instances_private`（过滤后的有效实例）；原 `analyze_gold_joins` 把 `valid_instances_private` 传给 `golden_join_audit`。而本轮写出的 `fk_gate_private.json` 只保存 `instances_private`，P0 对账 wrapper 读取该字段后直接调用 `golden_join_audit`，没有按 `valid_endpoints` 过滤。`golden_join_audit` 本身也不执行此过滤。

因此，当前 P1.5 arm 的候选实例全集可能包含原 P1.5 正式汇总排除的无效端点记录。现有 970/197 及 103/21 交叉差异可作为“本轮 wrapper 实际输出”保留，但尚不能归因于 packet 与 canonical P1.5 的 FK 语义差异。需要在新 run ID 和新预注册中修正输入过滤后，才可作同口径比较；旧产物不覆盖。

### 历史 P0 v3 来源核对（只读）

| 主张 | 核对证据 | 判断 |
|---|---|---|
| 历史结果记有 1,534 题、1,140 个 JOIN-ON、956 个 FK 匹配题和 174 个多 FK 候选题 | 旧 `full_audit_v3.json` 的 `dataset` 与 `gold_label_audit` 聚合字段；旧 `full_audit_v3.log` 也打印 956 | **作为历史聚合值有支持** |
| 历史输入与本轮 v3 是同一份 dev JSON/schema | 旧结果两份 SHA 与本轮运行 SHA 一致 | **有支持** |
| 956/174 可以由原执行器复算 | 旧 `commands.md` 指向 `ai_temp_code/run_p0_audit.py`，该源文件当前缺失；结果记有代码 SHA `457fd370…e1c3847`，但在旧工作区 `ai_temp_code/` 和上游 checkout 中找不到匹配的 Python 源文件 | **无法复算** |
| 956/174 可以与当前两个实现做逐题 crosswalk | 旧 `full_audit_v3.json` 只含聚合计数，没有逐题 FK 标签/问题键列表 | **没有所需证据** |
| 历史结果报告了 Gold Role 准确率 | 旧结果字段 `role_accuracy_claimed` 为 `false` | **没有该主张** |

旧证据位置在原始工作区别名 `local:QuadGraph-Text2SQL-20261014/` 下：`results/p0/full_audit_v3.json`、`logs/p0/full_audit_v3.log`、`logs/p0/commands.md`、`configs/p0_20261014.json`。上游 QuadGraph checkout 本身只包含 README/研究文档，没有该自定义 P0 runner。故历史 956/174 与当前 1,043/176、970/197 的差异原因仍未知；不能用当前实现推断旧标签定义。

### 两套可执行定义的具体差别

这里的“FK match”与“multi-FK candidate”是两套计数规则，不是 Gold Role 准确率，也不是 QuadGraph 检索/关系传播方法的改动。

| 项目 | packet 定义 | P1.5 `golden_join_audit` 定义（本轮 wrapper 的实际传入） |
|---|---|---|
| FK 来源 | BIRD `dev_tables.json` 的 `foreign_keys` 列索引；转换为表名/列名，按不区分大小写的列端点匹配 | 冻结 P1.5 私有 artifact 的 `instances_private` 原始 SQLite FK instance；候选保留约束的有序列对。本轮未过滤 `valid_endpoints=false` |
| SQL 条件 | SQLGlot SQLite AST 中每个 `JOIN ... ON` 下的直接列等式；允许列外包括号/Cast/TryCast，要求可由别名解析出两个不同表 | SQLGlot scope 中每个 `JOIN ... ON` 下左右均为直接 Column 的等式；按 scope 的别名映射到物理表 |
| FK match | 任一 ON 等式的两个表列，正向或反向等于 schema 声明的一条 FK 列对，就把整题标记为 match | 对一个 JOIN 的等式集合检查完整 FK instance：唯一一个 instance 的全部列对都出现为 `matched`；多个完整 instance 为 `ambiguous`；只有部分列重叠为 `partial`；没有完整/部分重叠为 `unmatched`。整题只要有一个 `matched` JOIN 即标记为 match |
| multi-FK candidate | JOIN 涉及的无序表对，在 schema 中有至少两种不同的列映射就计候选；它不要求 ON 条件已经选出其中一个 | 某个 JOIN 涉及的表对，在 artifact 中有多个 FK instance 就增加 `role_candidate_joins`；整题只要该计数非零就标记候选。它也不证明角色选对 |
| 复合 FK / 角色判定 | 列对逐项处理；候选以表对分组，因此不是完整约束级复合 FK 判定，也不输出唯一角色 | 完整 instance 的有序列对需整体覆盖才是 exact；但 `role_candidate_joins` 只数同表对的多个 instance，不判断业务问题要求哪一个 |

packet 对“有没有某条声明式 FK 列对被 ON 命中”较宽；P1.5 的函数对“一个 FK instance 的全部列对是否被完整覆盖”较严，同时另行记录歧义、部分匹配与候选数。但本轮实际传给 P1.5 函数的 instance 集合与原 P1.5 汇总入口不同，所以当前 103/21 差异混有候选实例过滤差异。没有人工/Gold 语义裁决，也没有完成修正过滤后的对照，不能宣布哪套 canonical 定义正确或将差异归因于算法本身。

### 相对原实验究竟改了什么

- **相对 v2：** 没有改 packet 或 P1.5 的算法、计数口径、数据、分母或成功/停止门。v2 的预注册 SHA 字符串与目标 artifact 实际 SHA 不同；v3 只将冻结 SHA 改为从同一字节计算并独立复核的正确值，换用新实验/run ID，再重新执行 Smoke 和条件式 Full。
- **相对原 P1.5 运行入口：** 本轮适配层实际传入了 `instances_private`，而原汇总入口传入 `valid_instances_private`。这是输入过滤口径差异，不是论文算法修改；它使本轮 P1.5 数字暂不能视为 canonical P1.5 的复现。发现后没有修改旧 run 或补跑，需另行预注册修正版。
- **相对更早的历史 P0 v3：** 目前只能确认历史报告的 956/174 聚合计数和输入摘要，无法确认它使用了上表哪一种算法。历史 runner `ai_temp_code/run_p0_audit.py` 和与记录 SHA 对应的源码都缺失，也没有逐题标签。因此不能严谨地把 packet 或 P1.5 说成“对历史算法的修正版”，也不能把计数变化归因到某个具体旧代码改动。
- **相对 QuadGraph/GFM-RAG 论文方法：** 本轮没有改图构建、节点/边表示、检索排序、图消息传播、SQL 生成器或训练方法；只做 FK/Join 标签定义和输入完整性审计。它不构成论文方法改进或效果证据。

## 结论与下一步

1. v1/v2 的 P1.5 Smoke 失败可归因于错误冻结摘要：v3 在更正后完整通过了同字节哈希与解析门。这不是数据变化，也不是 SHA-256/文件读取故障。
2. packet 的题级结果不受 Python 3.10/SQLGlot 26 与 Python 3.12/SQLGlot 28 变化影响。packet-28 与本轮 P1.5 wrapper 的原始 crosswalk 有 103/21 标签差异，但 wrapper 传入了原始 FK instance 列表；这些差异不能解释为单纯的算法/语义差异。
3. 历史 P0 v3 的 956/174 只有聚合计数，没有逐题标签和可复算 runner；可信双人 Role 标签仍为 0。不能用这些数字替代 Gold Role，也不能把它们解释为检索、GraphReasoner 或 SQL EX 收益。
4. **研究决策：** 保留本轮结果，但把 canonical P1.5 crosswalk 标记为待修正适配层后再比较。下一步若继续，只需新预注册一个过滤到 `valid_instances_private` 的修正对照；不启动 GPU/模型实验，也不扫描其他计数。Role Accuracy 及其主张仍为 NO-GO。

## 产物与调用

- 配置、命令模板、所有 run ID 和哈希：[`experiment_config.json`](experiment_config.json)。
- 安全聚合：[`crosswalk_aggregate.json`](crosswalk_aggregate.json)，SHA-256 `8751fa1930434b2ed1af49c8ec63cd4ff2ddb37d6364513beb752aa409c0e55d`。
- 私有 Smoke/Full 逐题结果：`local:results/gfmrag_p0_fk_candidate_definition_recovery_v3_20261105_01/`；私有 crosswalk 在同一目录 `crosswalk_private.json`。日志和启动快照：`local:logs/p0_fk_candidate_definition_recovery_v3_20261105_01/`。
- **模型 API usage：** 0 请求，0 输入/输出/总 tokens，0.00 CNY；无外部费用。CPU 时间未货币化。

## 解释边界

即使所有门通过，本轮也只验证输入完整性、三套 parser/标签定义的运行复现及匿名计数差异。它不能说明哪套 FK 定义在语义上正确，不能恢复没有逐题记录的历史 P0 v3 的 956/174 计数，也不会产生可信 Gold Role 标签或 QuadGraph/GFM 方法收益结论。
