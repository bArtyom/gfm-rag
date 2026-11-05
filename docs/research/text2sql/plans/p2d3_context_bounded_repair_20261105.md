# P2d.3 受检索上下文约束的 SQL 修复：预注册方案

**状态：** `preregistered_not_run`
**实验 ID：** `p2d3_context_bounded_repair_20261105_01`
**性质：** BIRD dev 上的探索性本地效用实验；不主张通用 SQL 修复的新颖性。
**项目基线：** `bArtyom/gfm-rag`，执行分支从 `research/p2d2-frozen-failure-attribution-20261105` 的归档结果继续，起始提交 `9c39bee45daf5d12382bcd7c183ed0cb44237460`。
**指导文件：** 项目根 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`；本轮以 P2d.2 `_02` 报告给出的新样本 SQL 修复候选作为直接指导。主仓库 `main` 的 Text2SQL 状态说明落后于 P2d.2 分支记录；差异和采用依据记入本方案。

## 痛点与研究问题

P2d.2 对 28 条不可执行 SQL 的冻结归因中，10 条是解析/结构错误，13 条是限定符或作用域错配，4 条引用数据库中不存在的标识符，1 条误用上下文可见字段。18 条缺列输出都通过只读 `EXPLAIN` 重现；旧样本中没有失败字段被判定为缺失于该臂 prompt。旧 30 题是开发诊断样本，不再用于新方法调参或阈值选择。

**核心问题：** 对一条已生成但无法解析或编译的 SQL，只允许一次修复时，修复器只看原检索上下文，能否获得有用的修复收益；这种受限修复与允许读取完整数据库 Schema 的通用修复相比，质量损失是否可接受？

**核心假设：** 在与 P2d 旧 30 题不重叠的新冻结样本上，检索上下文约束的一次修复（A2）能提高 Set Execution Accuracy，相比完整 Schema 一次修复（A1）不低超过 5 个百分点，并且 A2 不接受任何引入检索上下文未提供表/列的 SQL。

这是一项**部署范围与证据边界**检验，不是新的 SQL 修复算法主张。近期已有工作覆盖分层 Schema/作用域检查、有界验证式修复、双 Schema 生成与执行反馈；A1 是必要的已知方法类对照。若有正结果，只支持本地流程中的效用，不支持文献新颖性或跨基准泛化。

## 考虑过的路径与本轮选择

1. **继续增加 Schema 检索覆盖。** 不选作本轮主干：旧失败归因没有发现 prompt 缺少失败字段，单靠扩大检索未对应已观察到的主要错误机制。
2. **单独实现通用 SQL 校验与修复器。** 作为新方法不成立；Post-SQLFix 已有分层静态分析、有界修复和接受前验证；SCOPE-SQL、ReEx-SQL、VET 也分别研究结构化修复、执行反馈和候选 Schema 约束。本轮只把通用修复作为 A1 对照。
3. **比较完整 Schema 修复与检索上下文受限修复。** 选择。它直接检验当前 RAG 流程中的检索证据是否足够修复已观察到的结构错误，并量化扩大上下文是否带来值得的准确率收益和 token 成本。它属于项目流程诊断，不是直接新颖性主张。

## 对照组与执行方法

所有组共用同一条 A0 初始生成 SQL、问题、证据及 P2c-R `V00` 选中的 R0 Schema 上下文。先用固定 SQLGlot/只读 SQLite 检查判定 SQL 是否解析并可编译。只对解析或 Schema/作用域检查失败的初始输出触发修复；通过检查的 SQL 保持原样。

| 组 | 规则 | 修复输入 |
|---|---|---|
| A0 | 无修复 | 固定的一次初始生成 |
| A1 | 最多一次修复；候选通过同一只读安全/执行检查后采用 | 问题、证据、完整数据库 R0 Schema、初始 SQL、仅含错误类别的标准化诊断 |
| A2 | 对初始 SQL 与修复候选都应用 V00 的 SQLite 只读 authorizer；上下文外表/列读请求一律拒绝。初始 SQL 仅在被拒绝或完整 Schema 编译失败时触发最多一次修复 | 与 A1 相同的问题、证据、初始 SQL和标准化诊断；Schema 仅为原始 V00 检索上下文 |

初始 SQL 首先在完整 SQLite schema 上统一做语法/编译检查。A0 直接保留这条 SQL；A1 仅在该检查失败时修复。A2 还会把同一 SQL 在 V00 允许表列下编译一次：若完整 schema 可编译但 V00 authorizer 拒绝其字段读取，则只对 A2 触发一次 `schema_or_scope_compile_failure` 修复；未通过 V00 门的 A2 SQL 不计作已接受输出。这样所有 A2 最终 SQL（包括未修复输出）都必须满足检索范围。诊断不包含具体表名、列名或 SQLite 原始错误。

两种修复都最多一次模型请求，不做循环重试、候选投票、人工挑选或 SQL 专项 prompt 调优。标准化诊断只有固定错误类别（解析失败或 Schema/作用域编译失败），不含 SQLite 原始错误文本、期望字段名或查询结果。候选修复先由 SQLGlot 与只读 SQLite 编译/安全门检查；A2 再由 authorizer 限制可读表列。完整数据库 R0 Schema 从同一冻结节点全集按稳定顺序拼接。两个修复组的 prompt token 数会如实报告；由于 A1 可用的 Schema 更多，本实验比较的是信息可见范围的实际效用，不声称 token 严格匹配。

## 样本与选择

- 数据：本地缓存的 BIRD dev，沿用冻结的数据及 Schema 版本。BIRD dev 已反复用于开发，结果仅为 exploratory。
- 完整样本：66 题，覆盖 11 个数据库；候选限定为 P2c-R 中 `column_eligible=true` 且具有布尔型 V00 `Complete Schema@1024` 标签的问题，排除 P2d 旧 30 题及其 Smoke 题。先按数据库×V00 完整/不完整单元格各抽最多 3 题；若某单元格样本不足，再从同库剩余题补到每库 6 题，因此补足配额时另一单元格可能超过 3 题；仍有空缺时按数据库当前样本数从少到多轮询补到 66 题。该资格限定可确保所有样本都属于定义明确的两层，且不改 Gold SQL 的提示隔离。具体 ID、问题、参考 SQL、Schema 和数据库路径只保存在本地私有 manifest。
- Smoke：从同一冻结合格候选池另抽 5 题，与 Full 和所有旧 P2d 样本不重叠，只检查模型连接、usage 记账、输出解析、修复请求、只读 SQL 门、A2 字段权限门和报告格式。Smoke 不按 EX 正确率判定、不用于调提示/采样/参数，也不进入 66 题指标；五题均须完成预测封存和评价、无传输/usage/安全/评测基础设施错误，才可进入 Full。
- 选择 seed：Full=`20261105`、Smoke=`20261106`。先固定排除旧 P2d 全部准备样例后的 1,460 题合格候选池，再按各自 seed 的稳定 SHA-256 顺序抽取；Full 按每个数据库×完整性单元格先抽最多 3 题；每库不足 6 题时从该库剩余题补足；仍不足 66 题时按当前样本数从少到多轮询数据库，按 Full seed 的固定 hash 顺序补样，直到 66 题或无候选。Smoke 从 Full 剩余候选中独立抽取。
- Gold SQL 只供最终评测和分层标签生成，不进入初始或修复 prompt，不用于生成诊断或挑选修复候选。

## 指标、成功判据与停止条件

**主要指标：** 66 题上的 Set EX，报告 A2−A0、A1−A0、A2−A1 的配对差，以及各数据库方向；执行不可用的预测按 EX 错误计入 Full 分母，并单独报告不可用数。该样本为数据库×V00完整性平衡的 case-control pilot，不做 BIRD dev 总体率估计，也不把单一总体差异解释为独立测试集结论。

**辅助指标：** Bag EX；初始无法解析/编译数量；对初始失败 SQL 的修复后可执行率；错误 SQL 被修复为正确/仍错/损坏的题数；A2 被拒的超出上下文字段提案数；A1/A2 每次请求的本地输入/输出 token、修复请求数及单次 GPU 运行时间。公开材料仅保留匿名聚合，不公开逐题 SQL、Schema、问题、执行结果或行数据。

**进入结果分析的最低信号：** Full 初始 SQL 至少有 10 题解析/Schema 编译失败；不足 10 题则记录 `INSUFFICIENT_REPAIR_CASES`，不追加模型或样本扫描。

**探索性候选成功门：** A2 相对 A0 的 Set EX 提升至少 5 个百分点；A2 相对 A1 不低超过 5 个百分点；A2 没有接受任何超出 V00 上下文的表/列；所有数据库快照哈希和账本 usage 完整。成功门只决定是否值得另行设计确认实验，不改变本轮 exploratory 标签。

以下情况停止当前 run，不自动更换 seed 或模型：输入/模型/Schema 哈希不匹配、5 题 Smoke 失败、数据/SQLite 安全门失败、请求超时或 usage 缺失、输出目录冲突、GPU/RAM/墙钟/token 预算将超限、SQL 对只读作者izer 发起写操作、私有数据可能进入公开文件。Smoke 或 Full 失败现场保留，不覆盖重跑。

## 固定配置与资源预算

- 模型：本地 `Qwen2.5-Coder-7B-Instruct`；temperature `0`、top-p `1`、top-k `-1`、repetition penalty `1.0`、seed `20261105`；初始 SQL 最大 1024 tokens；每次修复最大 512 tokens；一次初始生成，修复组各最多一次。
- 服务：独立既有 `qbridge_vllm085_20260829` 环境，vLLM `0.8.5`；单机本地服务，指定一张 RTX 4090 和独立端口；不启动 Jev，不使用外部付费 API。
- 运行器：既有 `think2sql_20260909` Python 3.12.14 / SQLGlot 28 环境；不改依赖、不下载模型。启动前再次确认环境实际版本。
- 资源上限：单 GPU、峰值显存 22 GiB、最多 8 CPU 线程、进程 RSS 16 GiB、Full+Smoke 总墙钟 4 小时；最大 213 个模型请求（15 Smoke + 198 Full），输入 token 700 万、输出 token 20 万。达到任一上限即停止。
- 私有结果与日志使用新的本地 canonical aliases `gfmrag_p2d3_context_bounded_repair_20261105_01`；创建前先登记个人资源索引并确认物理目标和 alias 均不存在。机器绝对路径仅在本地来源索引和运行回执中保留，不进入 GitHub。
- 每个实际本地模型请求以稳定 call ID 写入统一 API usage ledger；记录真实 prompt/completion/total tokens。无外部 API 费用；本地 GPU 秒单独报告，不折算成货币。

## 先验研究与边界

- P2d.2 `_02` 报告是本轮痛点和候选实验的直接依据；其旧样本只用于提出问题，不进入本轮分母。
- Post-SQLFix 已研究分层静态 SQL 分析、Schema 感知诊断、verify-before-apply 和有限重试；因此 A1 不是创新基线。[论文](https://arxiv.org/abs/2610.41472)
- DSR-SQL 已比较裁剪 Schema 和完整 Schema 路径，并结合执行反馈；因此本轮也不将“完整/裁剪 Schema 双视图”本身主张为新颖。[论文](https://aclanthology.org/2026.emnlp-main.1688/)
- SCOPE-SQL 已研究按 SQL 结构模块分配交互修复信用；ReEx-SQL 研究解码过程中的执行反馈，VET 把推理限制在候选 Schema 并逐步执行；本轮不做强化学习、多步执行推理或跨轮训练。[SCOPE-SQL](https://aclanthology.org/2026.findings-emnlp.951/)、[ReEx-SQL](https://aclanthology.org/2026.acl-long.35/)、[VET](https://aclanthology.org/2026.findings-acl.1544/)
- EMNLP 2026 的 PASCAL 研究在生成前按成本获取任务所需证据；这提示“证据够不够”是更宽的近期问题。本轮只测试已有静态 Schema 检索结果下的修复，不研究跨源证据获取。[论文](https://aclanthology.org/2026.emnlp-main.465/)
- 若 A2 有信号，下一步先做文献和代码对照，再决定是否需要独立数据库测试；不得自动把本轮结果升级为主实验或持续扩样。

## 代码/报告交付

公开预注册提交必须先于私有样本准备及任何模型推理。公开归档：本方案、独立运行器、公开配置模板；本地私有归档：样本 manifest、prompt/SQL、执行结果、日志和逐请求回执。完成后在 `docs/research/text2sql/reports/p2d3_context_bounded_repair_20261105_01/` 写每次运行的完整报告，提交并推送到 `bArtyom/gfm-rag`，随后从 GitHub 回读核验。
