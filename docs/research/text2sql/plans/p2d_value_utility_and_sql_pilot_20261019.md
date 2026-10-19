# P2d 下一轮实验预注册：Values 语义必要性 + 冻结 SQL 生成配对 Pilot

> **制定：2026-10-19。状态：计划/未执行。** 这是承接 [P2c-R 全量 H1/H2 PASS](../reports/p2c_r_recovery_20261019_01/README.md)、[Values 词面审计](../reports/p2c_values_risk_20261019_01/README.md) 及 [19 题直接绑定](../reports/p2c_value_binding_20261019_01/README.md) 的**新问题**。参见 [最新决策与数据边界](../reports/p2c_r_latest_review_20261019/README.md)。不得把本文写成 P2d 已完成或 P2c-R 已测 SQL EX。

## 0. 决策和目标

**唯一主问题**：在富语义 Retrieval View 保留 Values、短 Schema Context 省略 Values 后，Schema 召回虽更完整，但是否损害问题中的谓词值映射或最终 SQL 执行正确率？

**不做的事**：不重试已完成的 19 题列值绑定扫描、不继续扩充词面匹配规则、不根据 Gold 补 Schema Context、不搜索 Embedding 维度、RRF 超参、不训练 GNN、不立即称 V01 为新默认方案。

设计分两阶段：

1. **Gate A（必须先完成）**：冻结19题语义必要性人工复核和评测环境准备，包括固定已有 SQL Generator / Selector / BIRD SQLite evaluator 的可用性和接口契约；新 Generator 不可只因这一实验而偷偷升级、换 Prompt 或更换模型尺寸。
2. **Gate B（仅 Gate A 合格才执行）**：一次有界、同题配对的 SQL 生成和执行 Pilot，比较同一问题在不同 Schema Context 下的 SQL 质量。Pilot 为**诊断**而非足以证明总体 EX 提升的最终检验。

## 1. 样本（在看任何 Pilot 结果前冻结）

- **原19题：全部保留**，不得只挑9个 supported；分类为 `binding_supported=9`、`binding_mismatch=8`、`binding_unresolved=2`，并保留其原始 `rescued=6 / unchanged=13` 分层。这19题来自 `1460` Column-eligible 中的“常量只在 Values 命中、且问题/evidence 不可见”的二次筛选，**不能被当作随机总体代表**。
- **额外控制组：目标19题**，从其余 Column-eligible 且不在19优先集合的题中，以数据库、谓词类型、Gold Schema 大小和原 V00 Schema 节点覆盖情况做固定分层随机选择；在冻结方案时登记唯一 ID 的私有有序 SHA、随机 seed=`20261021`、实际每库配额和不足情形。**不能根据生成器/SQL EX 正确与否选择对照样本**，无法匹配时记录缺口而不放宽隐私/标注标准。
- 19+至多19样本只用来检验 SQL 语义变化风险和任务可行性。结果按原19 supported/mismatch/unknown、对照、原覆盖 rescued/unchanged、DB 分层报告。最终 EX 泛化必须独立数据库测试或冻结全量可评集合，不能以 `9/19` 推导全体错误率。
- 源 BIRD dev 1534/11 DB、Column-eligible 1460、固定非饱和 706 分母不变；74 道 Gold Column 不全题保持不可评但不称它们“无 Value 风险”。

## 2. Gate A1：语义必要性与风险审核

### 2.1 审核输入与盲法

- 仅在私有机器读取19题对应的问题、既有 evidence、参考 SQL/谓词绑定、R0/R1 文本和 V00/V01@1024 选集；**只用于离线评测与人工理解**，不得把参考 SQL/Gold 常量填回 V01 的 Prompt/检索文本。
- 两名相互独立审核者先只看问题、Evidence、非 Gold Schema 和 R0/R1 差异判断 SQL 值映射是否需要 Values；第二阶段才揭示参考 SQL 和 AST 绑定证据校核。审核者不得看到 E0/E1/E2 的生成输出，也不得以目标方法名称影响判定。
- 单条记录使用 `necessary | replaceable_from_question_evidence | unnecessary | unknown`，并记录 `direct_column_binding_correct`、`code_to_literal_mapping`、`predicate_filter_value`、`implicit_domain_enumeration`、`parser_limit` 及自由简短原因（私有）。
- 两人有分歧先独立记录再共同裁定，汇总原始一致率与 Cohen kappa（若类别过稀，明确 kappa 的不稳定性）。不能把模型裁定自动称作“人工 Gold”。已有本地 32B 语言模型若可用，只能用来辅助预审且必须盲化、记录模型 revision/费用；**最终语义必要性需要独立人工审查或明确标记为未验证**。
- 如果没有独立审核资源，允许交付 `semantic_review_status=unverified` 并继续准备工程入口，但不得宣称 Values 信息“语义安全”或“语义受损”。

### 2.2 Gate A2：固定生成/执行管线预检

1. 读取主仓库已有可用的 SQL Generator / Selector 接口和运行机器上的本地模型清单；**目前研究报告没有任何可复核的 Text2SQL Generator 模型运行记录**，不能假设 Qwen-32B 或 Jev 已在本仓库运行。模型若不可用，先写明 BLOCKED 和资源条件，不自行下载或切付费 API。
2. 冻结 Generator 模型标识、权重/服务 revision、Prompt 模板、Schema 序列化器、temperature（首选0）、seed（如支持）、解码上限、最大上下文与推理资源（优先用户本地现有模型，费用审批另行请求）。固定 SQL Selector（若使用）或明确 `selector=none`；不按结果切换模型/模板。
3. 将 V00/V01 的 **实际 Context 内容**输入同一 SQL Generator（包括 Table/Column 归属及 DB 约束），Prompt 中 Question、Evidence、系统说明一字不差，**除实验指定 Schema Context 外输入必须一致**。统一采用真实生成器 tokenizer 衡量完整 prompt tokens，Schema Context 仍按 P2c-R 的相同 1024 budget 截取；记录两个 tokenizer 的预算口径差异。
4. 必须在本地 SQLite/BIRD 官方或兼容 evaluator 中只读运行生成的 `SELECT` / `WITH` SQL；执行前解析和审查阻止 DDL、DML、ATTACH 和危险函数；使用只读快照、有限 wall timeout、行数及资源上限，保留原始预测和参考结果在本地，不传到公开 GitHub。
5. 提供离线合成测试：无需 DB 内容的 Prompt parity、同节点集合序列化、SQL 只读拦截、行数/超时/空结果处理、Set 与 Bag EX 区别、非确定性和失败聚合。成功后固定三臂的代码和输入哈希。
6. Gate A2 必须实际通过 **1～3 条不计正式 Pilot 的合成 SQL smoke**，不接触真题的 Pilot EX。验证器接收原数据，不泄漏 Gold 到生成器。没有 Generator 或 evaluator 就 `BLOCKED`，不得直接填 SQL 指标。

**Gate A** 通过标准：所有19题审核状态有记录且未知保持、Reviewer 资格明确（若仅自动审核则不能称人工已验），样本与对照 IDs/hash 冻结、Generator/Selector/SQLite 只读 EX harness 固定且合成 smoke PASS、真实运行成本预算和隐私审计记录。若人工审核暂缺，允许单独注册工程/SQL Pilot，但必须显式写清“语义 Gold 不可用”，不得作价值必要性的因果断言。

## 3. Gate B：一次冻结的同题三臂 SQL EX Pilot

| Arm | 选取的 Table/Column 节点 | 注入 Generator 的字段文本 | 定位 |
|---|---|---|---|
| **E0** | V00@1024 | R0 完整 Values Context | 原始基线 |
| **E1** | V01@1024 | R1 无 Values Context | 已通过覆盖 Gate 的新候选 |
| **E2** | **V00@1024 同一节点 ID** | **相同节点的 R1 短文本** | 只移除 Values 内容，隔离语义删除效应 |

- E0 vs E2 固定节点集合，专门检查 Values 移除对 SQL 表达式/谓词的影响；E1 vs E2 两者文本视图一致，比较新增节点/上下文组织带来的收益与噪声（但不把非线性交互强行解释为单一机制）。
- 所有 arm **同一已冻结 Query/Evidence/LLM Prompt/Generator/Selector/输出参数**；一次生成/题/臂，成对调度以减少环境漂移，记录执行次序。模型无法保证完全确定时须如实报告，不得重采样选最好的一条。
- 主报告用**Set Execution Accuracy（paired questions）**，Bag EX 辅、parse/exec success、`WHERE/IN/BETWEEN` literal correctness、源列/predicate correctness、回答对错类型、返回数目和端到端 token/latency/本地 GPU 时间/外部 API 成本。原19与控制组分层单独显示总数、准确数，另外汇总3臂的题级 `E0-only/E1-only/both-correct/both-wrong`；必要时报告近似/精确配对区间，但 Pilot 不进行论文级显著性主张。
- 准确性须用正确的 BIRD DB 和固定比较语义，处理顺序、NULL、浮点 tolerance、重复行（Set vs Bag）、运行时异常与超时；禁止仅以参考 SQL 字符串完全一致判定。
- 先一次 **3条私有 Pilot 题的 Smoke（仅工程，不加入正式结果）**，其选择预先固定且结果不可用于改变量；通过后一次 Full（19 + 最多19 题）；不允许临时扩大实验范围或因 EX 退化而修改 Prompt/模型/预算。
- 资源预算需执行前按实际本地模型指定 GPU/CPU 和 token ceiling，输出 `max_total_model_calls=3×N+3×smoke`，N 为冻结样本数；未得到用户明确授权不能自动启用付费 API。记录实际确认/未知 tokens 和货币成本，不能将模型费用估为0。BIRD 原文、私有 SQL、用户/数据引用不可推入公开库。
- 正式比较仅有单轮 Pilot 结果；如果整体或高风险组的 E1 有实质错误回归，停留在实验候选并归因；如果无明显回归，也**不能证明安全**，下一步仍需要数据库级独立留出和规模足够的 Set EX 检验。

## 4. 决策门（工程 / 科研区分）

- **No-Run Gate**：无固定生成器/只读 EX harness 或真实数据哈希不符合 → P2d 只提交 BLOCKED + 技术缺口，不调用新模型。
- **工程 PASS、语义标签 unknown**：可进行 SQL Pilot 以观察 EX，但不能按自动绑定标签宣称 Values 语义必要性或安全。
- **SQL Pilot 有明确 E1 退化**：冻结问题类型、统计 E0-only 错误与原19类案例，优先研究**仅运行时可见信号**触发的 Values 按需附加；不能利用 Gold Literal 才能“修好”Prompt；之后需另行预注册新方法。
- **SQL Pilot E1 同等或更好**：V01 留作候选进入真正独立数据库 Holdout / 冻结全量 BIRD dev Set EX，对同等预算、真实端到端费用与谓词 correctness 分层评估。Pilot 无论结果如何，不以 38 题宣称总体 EX 显著改善。
- **两种情况**：独立启动一个 `G0` 官方 GraphReasoner schema-graph baseline 可行性工作包，先保证 JoinInstance Graph 保真与 FK/Role 标签可信；不能将 GFM 工程 Smoke 当作图算法增益。

## 5. 预期文件与 GitHub 提交

- 实现：建议 `scripts/text2sql/p2d_sql_context_eval.py`、`tests/test_p2d_sql_context_eval.py`，尽量复用已冻结 P2c-R 的节点排序/Context 输出和私有缓存；必要时单独分支/PR，保证 upstream GFM 主干不变。
- 实际报告：`docs/research/text2sql/reports/p2d_sql_utility_YYYYMMDD/README.md`、`experiment_config.json`、匿名 `aggregate_summary.json`、输入/model/prompt/code SHA、真实执行账本、测试/重复性与 Gate 状态。**不是现在预填结果。**
- 人工审查 19 题可按机器已生成私有 `binding_review_queue_private.json` 进行，保存审核分歧和分母；敏感 Query/Gold/数据库内容/模型原始 SQL 仅留本机。
- 如果没运行也必须报告 `NOT_RUN` 或 `BLOCKED`，不得编造 SQL EX、审核完成数或 GFM 基线。

**给下一轮执行者的一句话：先锁定19+对照和 SQL 生成/评测全链路，完成有限语义复核，再做同题三臂 SQL Pilot；不是继续跑新的 Embedding 或 Values 规则扫描。**
