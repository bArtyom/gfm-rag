# P2d.2 recovery：封存 SQL 失败根因归因

**状态：`_02` Full 完成；`_01` 启动错误单独保留。** `_01` 因启动参数把 P2d.1 评测目录误作 P2d 准备包路径，在读取私有文件前停止；失败回执见 [`_01` 状态回执](../p2d2_frozen_failure_attribution_20261105_01/attempt_001_status.json)。新的 `_02` 只修正了准备包路径和运行编号，没有更换数据或预测。更正原因与边界见[执行路径更正计划](../../plans/p2d2_frozen_failure_attribution_amendment_20261105_01.md)。

## 研究问题与固定样本

仅对 P2d 封存的 90 条预测做错误结构归因。P2d.1 已固定 28 条不可执行输出：10 条 `sql_parse_error`，18 条 `missing_column`。E0/E1/E2 的失败数量分别为 E0 4+6、E1 2+8、E2 4+4。问题和方法与原预注册一致：判断缺列是否对应本臂 Schema 上下文未选入的字段、生成 SQL 的错误字段/限定符/作用域，或其他未决情况；把解析失败粗分为包装格式与语句结构。

本轮是已暴露 BIRD dev 子集上的探索性错误分析，不是独立测试。它不生成新 SQL、不改旧 Set/Bag 分数、不读取参考 SQL、不评估 FK Role Accuracy，也不执行查询获取结果行。

## `_01` 到 `_02` 的唯一变更

- `_01` 参数错误地把 P2d.1 评测结果目录当成 P2d 准备包目录，运行器在打开封存清单时停止；没有读取私有文件内容，没有写出分析结果。
- `_02` 使用已有登记资源别名 `sources/results/gfmrag_p2d_sql_utility_20261022_01/prepare_01/` 作为准备包来源；预测仍来自原 P2d Full，失败类型仍来自原 P2d.1 Gate 2。
- 为保证输出标注独立 run ID，runner 接收 `--experiment-id`；分析逻辑没有变化。
- `_01` 与 `_02` 使用不同结果和日志目录；不会覆盖或混用原有产物。

## 预注册方案与判断门

- 分母固定 30 题 × 3 臂 = 90；对 28 条已失败输出分析，其中 parse 10、missing-column 18。
- 10 条 parse 错误只做静态 SQLGlot 形状检查。
- 18 条缺列错误最多各做一次只读不可变 SQLite `EXPLAIN` 编译；SQLite authorizer 拒绝写操作和非白名单函数。查询结果行不会被读取。
- 精确失败标识仅在内存中关联冻结 schema、已选节点 ID 和上下文；落盘/公开仅保留匿名类别计数。
- 分类覆盖达到 23/28 才算高置信归因覆盖充分；少于该门槛则不提出方法干预。
- 上下文可见性候选门：至少 9/18 属于本臂上下文缺字段，且至少 4 个不同问题在另一臂选入同一字段节点。
- 生成有效性候选门：至少 9/18 属于可见字段误用、不存在字段或限定符/作用域错配。
- 两门均未达标或归因不充分时，停止在现有样本追加测试。任何哈希变化、只读门失败、预算超限或隐私风险均立即停止。

## 输入版本、环境和预算

- 项目指导基线：`bArtyom/gfm-rag@14892ee5de06a101c2b79187f044aa7e63a30371`；代码预登记及 `_02` amendment 见本分支 commit 和同目录 `experiment_config.json`。
- 固定输入 SHA-256：预测 `e88bf42f22a73b6b56af96a5d3ea88d69252c33509bb72da5b8cfde2f7474ea5`；预测封存文件 `f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3`；准备包封存 `334e388af338c7f20575aa81a86ff7184e526716b251cd1b48955b4134172aaa`；P2d.1 结果 `9b7fec27ee0d23cddf76b4bf842ddde530a2f1bbb001fa449218d3b049b3711d`；schema `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；复用现有环境，不安装或升级依赖。
- CPU-only；最多 4 线程、300 CPU 秒、4 GiB RSS；每次 EXPLAIN 墙钟硬限 2 秒；无模型/API/GPU、训练或下载。
- 执行命令、硬件快照和私有产物位置保存在本地权限受限的启动日志；不公开绝对私有路径。

## 执行状态与结果

### 启动信息

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p2d2-frozen-failure-attribution-20261105`。
- `_02` 运行器、配置与路径更正已在**私有输入打开前**归档至 commit [`4b8b70b`](https://github.com/bArtyom/gfm-rag/commit/4b8b70b2ac8386012925e85c7c653e8706663202)，tree `8f01aff973c57f1bd1163199ddab14cf179102fc`；运行时 source check 与提交、tree、clean worktree 全部匹配。
- 原始 P2d 准备包、P2d Full 预测与 P2d.1 Gate 2 状态使用已登记的本地资源入口；准备包指向 `sources/results/gfmrag_p2d_sql_utility_20261022_01/prepare_01/`。输入封存、预测、评测状态与 BIRD schema 哈希均按配置核验通过。
- 环境：`think2sql_20260909`、Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2；未安装或升级依赖。由于本机裸 `conda run -n ... python` 会解析到 Python 3.9，启动命令显式使用目标环境的 Python 3.12 解释器。
- 随机种子：无；使用既有固定 30 题与 90 条封存预测，不抽样。
- 实际执行耗时 3.177 秒，其中进程 CPU 3.172 秒，峰值 RSS 36,175,872 字节（约 34.5 MiB）。CPU-only；模型/API 请求 0，GPU 秒 0，SELECT 查询执行 0，SQLite 只读 `EXPLAIN` 编译 18 次。
- 输出只包含匿名聚合与运行回执。预测、问题、SQL、schema 标识符、SQLite 原始错误和逐题记录均未写入公开产物。

### 失败类别

固定分母为 28/90。28 条均获得预注册类别；三臂分类计数如下：

| 失败类别 | E0 | E1 | E2 | 合计 |
|---|---:|---:|---:|---:|
| SQL 解析/语句结构 | 4 | 2 | 4 | 10 |
| 限定符或作用域与查询来源不匹配 | 4 | 6 | 3 | 13 |
| 标识符不存在于该数据库 schema | 2 | 1 | 1 | 4 |
| 上下文可见字段仍被错误引用 | 0 | 1 | 0 | 1 |
| **合计** | **10** | **10** | **8** | **28** |

18 条 `missing_column` 都由只读 `EXPLAIN` 重现。失败标识中没有一条被归为“该字段未进入本臂上下文”；另一个臂可见同一失败字段的跨臂配对数也为 0。上下文缺失门未达到 9/18；生成有效性候选门达到 18/18（预设门槛为至少 9/18）。

### 结论与下一步

在这批已反复使用的 P2d 诊断样本上，证据不支持继续优先改检索或上下文打包。当前失败更集中在生成 SQL 对字段限定符、查询来源/作用域的引用不一致，以及 schema 中不存在的字段。这个结果是错误结构归因，不证明生成器错误是唯一原因，也不能代表未见问题上的失败率或因果效果。

按预注册规则，决定为 `GENERATION_VALIDITY_CANDIDATE_FOR_FRESH_FROZEN_SAMPLE`。下一轮候选应使用与这 30 题不同的预先冻结样本，比较原生成流程与一个 SQL 标识符解析/一次修复反馈流程；主要观察缺列错误是否减少，同时检查可执行性与参考 SQL 一致性是否受损。旧 30 题只用于提出这个候选，不得再用来调 prompt、修复规则或选阈值。BIRD dev 已被多轮使用，后续结果仍须标为 exploratory，不能称为独立测试。

### 结果文件

- 公开匿名汇总：[`aggregate.json`](aggregate.json)，SHA-256 `86e2e4d2f43f01bb65f85ca6ceef8a56478faf838ceaf683734b12589527bcc3`。
- 本地权限受限结果入口：`sources/results/gfmrag_p2d2_frozen_failure_attribution_20261105_02/full_001/`；本地日志与启动清单位于对应 `logs/gfmrag_p2d2_frozen_failure_attribution_20261105_02/`，均未上传。
- SQLite 快照运行前后哈希一致；运行回执记载 `input_hashes_verified=true`、`database_hashes_unchanged=true`、`private_rows_or_identifiers_written=false`。
