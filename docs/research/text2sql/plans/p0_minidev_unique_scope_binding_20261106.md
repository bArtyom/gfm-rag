# P0 Mini-Dev：唯一作用域列绑定恢复诊断

**状态：`smoke_002` 在样本 SQL 分析前因正向逻辑夹具失败而停止；依 amendment 不再重试，Full 未运行。** 实验 ID：`p0_minidev_scope_binding_recovery_20261106_01`。本实验是一次有界的 CPU-only 标签可用性诊断，不是 FK Role 方法实验，也不自动解锁模型排序。失败记录见[报告](../reports/p0_minidev_scope_binding_recovery_20261106_01/README.md)；唯一一次恢复方案见 `plans/amendments/p0_minidev_scope_binding_recovery_amendment_001.md`。

## 痛点与核心假设

冻结 Mini-Dev 2026 SQLite Gold-SQL audit 在 663 个限定 `JOIN ... ON` 跨表列等式中解析出 523 个（78.88%）。随后唯一直接列投影追踪恢复 46 个，达到 569/663（85.82%）；仍有 94 个未恢复等式，其中 74 个归于 `alias_not_found_or_correlated`，19 个涉及表达式或 `UNION`，1 个派生输出缺失。当前 resolver 对派生查询中的未限定直接列一律停止，因此这一失败类别中可能存在可由局部 Schema 唯一确定的名称绑定。

**核心假设：** 在不猜测名称、不做表达式展开、不跟踪相关子查询的前提下，为直接投影中的未限定列加入“当前查询作用域内唯一来源”绑定，并用 SQLite 编译期读取事件做保守交叉检查，可以在零回归、零歧义接受的情况下从余下 94 个等式中新增解析至少 61 个，使总覆盖达到预注册的 630/663（95%）。

该假设若失败，就停止 Mini-Dev SQL→FK mapping 标签恢复方向；不再换 parser、放宽规则或另选样本。即使通过，也只代表 SQL 结构标签准备达到覆盖门，不代表 SQL 所用 FK mapping 是唯一语义正确答案，不代表模型有效，也不自动运行 G-reasoner。

## 外循环判断与相邻工作

这是此前两次 Mini-Dev 标签质量实验之后的第三个、也是最后一个有界解析覆盖实验：原始标签 audit 为 523/663；scope taxonomy 的直接投影 resolver 恢复 46/140，但未达到 95%。本轮只针对明确剩余的“局部作用域里唯一的未限定直接列”失败机制；表达式、`UNION`、多个匹配来源、缺失列及相关引用仍拒绝。预算耗尽或覆盖门失败后进入结果综合，不继续同一数据上的 parser variant。

近期数据质量工作显示 BIRD Mini-Dev 的 Gold 标注错误会改变 Text-to-SQL 评估，官方 2026 Mini-Dev 更新也说明对选定标注进行了人工参与的修正。因此建立可复核 SQL 结构标签有价值，但不能把 SQL 解析覆盖包装成算法创新。[Jin et al., 2026](https://arxiv.org/abs/2601.08778)；[BIRD Mini-Dev release](https://github.com/bird-bench/mini_dev)。

SQLite authorizer 在语句编译期间收到 `SQLITE_READ(table, column)` 事件；官方说明 callback 在 `sqlite3_prepare()` 阶段调用，`EXPLAIN` 会返回原语句的虚拟机指令而不执行原查询。[SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html)；[SQLite EXPLAIN](https://www.sqlite.org/lang_explain.html)。此 callback 仅提供物理表列读取，不提供每个 alias occurrence 或谓词边，因此它只能核验物理列引用是否出现在编译后的语句里，不能单独证明某个等式两端的 alias 绑定正确。编译期可能报告 `SQLITE_FUNCTION`/递归 SELECT 控制事件；执行器只放行 `READ`、`SELECT`、`FUNCTION` 和递归查询控制事件，并拒绝其他动作。该边界写入实现和报告。

## 实验层级、预算与判据

- **层级：** `exploratory` 数据/标签可用性诊断；不属于主方法效果证据。
- **单一变量：** 只新增当前作用域内唯一的未限定直接投影列绑定。保留上一轮 resolver 作为 frozen baseline；不改 Gold SQL、FK identity、候选、SQLGlot 版本或覆盖阈值。
- **固定分母：** 500 条 reviewed Mini-Dev 问题；663 个原限定跨表 JOIN 等式。基线必须逐项复现 523 resolved / 140 unresolved，再加上上一轮 46 项 direct-projection rescue，合计 569/663；任何已解析项回归即停止。
- **成功门：** 新增至少 61 个唯一作用域解析；既有 569 项零回归；SQL scope error 为 0；所有新增物理列绑定均能在对应整条语句的 SQLite `EXPLAIN` authorizer 读取集中找到；不得把多来源、缺列或仅凭列名模糊匹配的项计入成功。
- **Smoke：** 从上一轮私有 `full_001/private_summary.json` 中选出含未限定列 operand 的问题（该文件 SHA-256：`c7116459bbc5d0262378136c0304cfb8b459e94b4d284b81730aeb8110d03475`），按 `SHA256(experiment_id + question_key_digest)` 升序取前 5 个。该摘要仅保存匿名 question-key digest 和计数；Smoke 原始 SQL 从冻结 JSONL 按 digest 在运行时读取。Smoke 与其余 495 题 Full 不重叠。另运行内置正负逻辑夹具：唯一来源恢复；当前作用域多来源歧义拒绝；无物理列拒绝；上一轮可解析直接投影保持不变。Smoke 至少 3/5 有一项保守恢复且 authorizer 核验零不一致，才运行唯一一次 Full。
- **停止门：** 输入或 baseline hash 不符；逻辑夹具失败；任何 baseline 回归、scope error、SQLite/解析器物理列不一致；Smoke 恢复少于 3/5；超过 1,200 秒或 4 GiB RSS；停止后保留现场，不用同一 run ID 重试。
- **预算：** 现有 CPU 环境，最多 8 线程、4 GiB RSS、1,200 秒；无 GPU、训练、模型推理、外部 API、依赖安装、下载或 SQL 数据查询。只准备内存中的空 SQLite 表结构；原始 SQL 只加 `EXPLAIN` 前缀，authorizer 仅允许 SELECT/READ 编译动作，不执行原始 SQL。
- **后续门：** 解析覆盖达到 95% 也不启动排序。另行核验至少 30 个排除 Smoke 后的可评分问题×表对、覆盖至少 3 个库，并为 SQL-used mapping 任务单独注册一次冻结 checkpoint 比较；该结果仍只称为 Mini-Dev mapping-transfer diagnostic，不叫人类 Role accuracy 或跨数据库泛化。

## 冻结输入、代码与资源

- 项目仓库：用户指定的 `https://github.com/bArtyom/gfm-rag`；以本分支当前最新研究指导 commit `61b6b9ef02cd8283fe69d9b9df48675675e9d76f` 为基线。实验代码、报告只进入该用户仓库，不写入 `RManLuo/gfm-rag`。
- Mini-Dev：revision `38818fcbc46038129592680c51b2c8b597aac27c`；JSONL SHA-256 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`。
- 官方 SQLite DDL SHA-256 `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13e1a413ee88ff5b`。
- Smoke selection source: previous scope-taxonomy private aggregate `.../p0_minidev_join_scope_taxonomy_20261106_01/full_001/private_summary.json`; only aggregate metrics and anonymous key digests are used for the deterministic Smoke split.
- 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2；仅使用既有依赖。
- 资源：本轮开始前 GPU 4×RTX 4090 空闲；192 逻辑 CPU；450 GiB RAM available；112 TiB 磁盘 available；Swap 2 GiB 已用。任务 CPU-only，最多 8 线程、4 GiB RSS。
- `smoke_001` 仅留启动日志 `/mnt/liansp3/logs/gfmrag_p0_minidev_scope_binding_recovery_20261106_01/smoke_001.log`，在输入哈希断言处退出；无 JSONL 读取、无输出目录、无 manifest。修正哈希后的 `smoke_002` 读取了冻结 JSONL 并做确定性样本选择，但在 `unique_unqualified_direct_projection` 正向夹具未通过时停止，未进入任何样本 SQL 分析；输出目录与 manifest 未创建，日志为 `smoke_002.log`。按 amendment，Full 不运行且不再重试。
- 公开材料只含方案、脚本、配置、匿名聚合和报告；不得上传问题、Gold SQL、问题键、数据库/表/列名、逐题标签、manifest 或日志。

## 预期产物

- 本方案：`docs/research/text2sql/plans/p0_minidev_unique_scope_binding_20261106.md`。
- 新执行器：`scripts/text2sql/diagnose_minidev_unique_scope_binding.py`。
- 配置：`configs/text2sql/p0_minidev_unique_scope_binding_20261106.json`。
- 若 Smoke 通过：完整匿名报告归档到 `docs/research/text2sql/reports/p0_minidev_scope_binding_recovery_20261106_01/`，并同步更新项目研究状态和 `/mnt/liansp3/sources.md`。

## 终止记录

`smoke_002` 的冻结输入哈希均通过，但 `run_logic_fixtures()` 在第一个正向夹具 `unique_unqualified_direct_projection` 处抛出 `ValueError`（预期 resolver 给出唯一物理绑定，实际为 `None`）。该检查发生在 `analyze_question()` 和输出目录创建之前；没有生成逐题结果、聚合指标或 attempt manifest。由于 amendment 只允许这一个恢复 Smoke，状态改为 `STOP_LOGIC_FIXTURE_FAILED`，不修补后复跑本注册，不运行 Full。具体环境、命令、分母和证据边界见实验报告。
