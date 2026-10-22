# P2d.1 预注册下一轮：封存 SQL 的评测覆盖审计 + 失败归因

> **制定 2026-10-22；状态 NOT RUN。** 承接 [P2d 首轮真实 SQL Pilot](../reports/p2d_sql_utility_20261022_01/README.md) 与 [最新复核](../reports/p2d_latest_review_20261022/README.md)。P2d 已严格一次Pilot结束，**不得在旧 run ID 下重试模型、改旧主分数或覆盖封存预测**。本轮只做离线评测器/失败归因。研究目标不是让数字变高，而是理解 SQL 是否正确、何处失效、为什么相同 Schema Context 产生的 Set EX 与离线节点召回脱节。

## 0. 实验状态与不得改变的事实

冻结数据：BIRD dev 30固定题/5DB（19个 Values 风险优先案例 + 11严格匹配控制，8个优先题无匹配），每题3臂90条封存预测。E0=V00节点/R0全文，E1=V01节点/R1短文本，E2=V00节点/R1短文本。Qwen2.5-Coder-7B-Instruct、vLLM服务、temp0、同Prompt及其他解码参数；本轮**模型forward=0**。

归档P2d口径（永不覆盖）：
- 确认 Set/Bag 正确 E0/E1/E2 **8/7/8（均30分母）**；unknown **11/12/10**。
- 四个 Gold Reference 因时间函数的列/非字面量参数被当前保守策略拒绝。其余各有7/8/6预测不可执行而参考可执行。
- E0/E1 Prompt真实输入 **35074/35591** tokens（E1更长1.47%）；E2 **24458**（比E0短30.27%），不能靠 P2c 的 Schema Token 指标假定 SQL Prompt 更短。
- 原19题人工 semantic necessity=0、FK/Role Gold Gate NO-GO、原7B试验不是Jev且G0没有运行。

**唯一直接行动**：冻结预测并审计正确性/无法比较的具体源头，建设安全且可重复的 evaluator-v2 可行性测试；**只有 safe gate PASS 才允许用封存预测另算一个补充的v2指标**。

## 1. Gate 0：检查封存资产 / 版本，所有评测行为先于观察v2指标预注册

- 从本机私有 `gfmrag_p2d_sql_utility_20261022_01` 读取原已封存的 **90条预测SQL/30条参考SQL/原样本 ID和DB hash**，核验 `prediction_seal_sha256=f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3` 和 `full_aggregate_sha256=091b3b68b2a24a693c8e12a2783d9630d6f467c521616a0b366bc81c41fea1f2`；以真实资产回执上的原sha为准。
- 原三臂 8/7/8、11/12/10、E0/E1/E2逐题 paired outcome 和 DB/优先题分母必须可由持久化原结果复算。核验DB前后未变、最新代码工作树clean、无网络模型请求。**任何输入文件丢失、SHA不一致，停止，不伪造。
- 建立全新 `experiment_id` / `result_root` / `source_commit` / `protocol_sha`，新派生输出**不得覆写**旧 P2d 原报告/Gold/SQL记录。所有源码/测试先提交GitHub，再跑任何真实case评测。
- CPU-only，`max_new_llm_calls=0`、`gpu_seconds=0`、`paid_api_calls=0`，建议≤8线程、≤4GiB RSS、单阶段≤600 process CPU s，SQL每执行10 s/50000行/64MiB/256MiB SQLite内存。其他依赖沿用旧冻结环境。

## 2. Gate 1：时间函数「安全评测覆盖」规则修复的必要验证

**评测器的真实当前拒绝逻辑**（`scripts/text2sql/p2d_sql_evaluator.py::_validate_sql`）：时间函数的所有参数必须是 Literal（如 `date(column)` 被禁），以防 `date(column)` 的源值可能是 `now`；不能简单允许所有含列参数的 `date/time/strftime`，也不能将 blocked 当作 Gold 不正确。

先只用**合成数据库 + SQL fixtures**测试两个类别：
1. 静态确定的日期列字符串、`date(col)`、`strftime('%Y',date_col)`、`julianday(date_col)`、相关日期函数的无时钟可复算情况，以及只读查询、与原SQLite结果语义一致；
2. 反例：列值 `now`、`localtime`、`utc`、`subsec`，动态拼接这些 modifier、嵌套函数、数据库view/trigger/UDF、空参数时间函数、`CURRENT_TIMESTAMP`、SQL注入、非 SELECT / PRAGMA/ATTACH/写路径；**所有可能获取真实机器时钟或执行非只读动作的路径必须拒绝或明确返回 unknown**。若 SQL 安全策略需要跑真实DB列数据才能认证，须冻结快照/溯源并评估与官方 SQL 评测语义一致，不能偷用Gold值来改模型。
3. 保留原AST+authorizer双层、只读immutable SQLite、子进程硬超时/行数/字节/heap约束。优先考虑**使用独立可信的BIRD官方或同口径离线评测器作交叉验证**（如果已在本机且许可/安全检查可用），而不是把自制安全策略去掉。
4. 必须先让 v2 对**原策略可判定的26/30参考SQL**及对应原已成功预测SQL至少保持执行结果一致（row hash / Set / Bag 及投影列数），再评估另外4道 blocked Reference 能否安全接纳。任何过去可判正确/错误出现无解释改变，即 Gate FAIL；不能强制指标向上。
5. 若四题任意不能在保证时钟独立/只读的策略下执行，则对应结论继续 unknown，**不要求全部4题从 unknown 变成可判**。评测器v2和旧评测器两套结果都输出。

**Gate 1**=安全合成/负例测试PASS，旧已可判样本回放一致，新代码/数据SHA冻结，不需要任何特定EX提升。**Gate失败时只交付工程诊断，不重算全样本评分。**

## 3. Gate 2：已封存预测的全30题 CPU 复核（Gate 1 PASS后）

只读取旧封存 `predicted_sql` 和 `reference_sql`，没有新LLM请求，没有prompt变化，没有再次采样：

- 先产生结构化的**评测可用性漏斗**：参考 SQL original 26ok/4blocked，预测 E0/E1/E2 original 19/18/20 executable；v2 是否变为可比较，对每题明确 `reference_unavailable | prediction_parse | prediction_sqlite | prediction_ast_policy | timeout | row/bytes/heap | compare_nonexact | comparable_correct | comparable_wrong`，主类互斥 + 可以多值的证据标记；
- 区分 **生成器真正的错误** vs **评测器有限覆盖**。具体错误归因需要读取私有原 SQL/Schema：对 `sqlite_error` 再分类 `missing_table | missing_column | ambiguous_column | datatype | unsupported_func | bad_join | other | unknown`，不得仅根据旧聚合中 generic `sqlite_error` 猜。记录所有隐私内容留本地；
- 同时统计成功 SQL 的**可判但错误**案例的本地 AST 结构证据、谓词列/值、JOIN 路径和Gold节点覆盖，人工标签不足则记 uncertain，别用完全相同Literal集合当唯一准确率；
- **保存 E0/E1/E2 逐题 paired contingency 的新旧版本并列**，特别是 `E1-only/E0-only`、`E0/E2` 的 1/1 配对损益是否有新的可判数据。保留全部30分母和原19/11分层，显式 8题无控制；
- 固定数据下对比例指标提供 conservative confirmed-correct/N 与 unknown-count，以及适当不确定性范围；**不能把 unknown 默认为 false SQL Gold**，也不能只在共同可判上报告总准确率；
- 独立输出 Token 结构分解：生成器固定 overhead / Question+Evidence / 返回的 Table+Column 文本 / Schema 元素数量，核对 **E0 35074、E1 35591、E2 24458** 是否全量来自实际冻结输入；列出只显示较短 Schema 但 Prompt 不短的原因，不能事后修改装包规则；
- 额外分析6个覆盖 rescued 题为何三个臂确认正确均为0、4题 unknown，**不作样本外泛化**。
- 严守单次离线 CPU full 验证额度，结束即停；检查所有原输入、原评分和sha未变。建议冻结一次 synthetic smoke+一次 saved-SQL full；如故障另立恢复记录。

## 4. 平行Gate S：原19题双审阅者语义必要性（若确有审核资源）

- 原9 supported、8 mismatch、2 unknown 不增删。把原 Query/Evidence、R0 Values、R1短文本、原参考SQL隔离展示：**先在Gold/生成结果盲化情况下独立判断是否需要原Values实现正确值编码，再揭示Gold进行核验**。
- 两名独立人工审阅者各自按 `necessary | recoverable_from_query_evidence | unnecessary | unknown` 标注来源列、常量映射和理由类型，记录原始一致率和分歧，裁定时另存，不将自动LLM审阅冒充人工 Gold。保留19题完整分母，unknown不删；记录kappa及类别稀疏风险。
- 若没有审核者：将 Gate S 标为 `UNVERIFIED`，工程审计可继续，**不把“9题同一源列绑定”升级为值语义必要性证据**。

## 5. Go/No-go 和下一轮研究切换

| 结果 | 决策 | 界限 |
|---|---|---|
| **Gate 0/1无法通过** | STOP P2d.1 的重新评分；完成静态错误归因，优先图研究的 FK/JoinInstance 与 G0工程基线 | 原8/7/8仍唯一可复核的主Pilot；不能修改安全门迁就参考SQL |
| Gate 1 PASS、补充的v2评测仍有大量不可判 | 不启动大规模新模型/Prompt；先处理生成器格式、SQL可执行性和评测分母 | 不能靠另选可判题美化EX |
| Gate 1 PASS、预测错误结构明晰；E1仍无稳健效果优势 | 保留 **E0作为原始 SQL基线**、E2作为压缩候选；后续方法若做只能预注册 `E3` 的 Generator-token-aware Budget Packing，严控公平tokens | 不从30题得出“压缩无损”或“新方法无效” |
| Gate 1 PASS、新旧对照显出特定可修复缺口 | 独立预注册很小规模的 **P2e**，冻结旧样本以外且未提前查看的DB/cases，用新方法+E0/E2对照并真实EX验证 | 不因本轮纠偏后的v2指标直接宣称泛化增益 |

**不要在 P2d.1 引入E3实际分数或更大的7B/32B/Jev模型。** 若P2d.1末尾仅产出原生成器失败原因，也属有价值的明确诊断结果。

## 6. 图方向并行但单独报告

论文主线仍需 **G-reasoner/GFM在 Schema Graph 上的真实G0 baseline**：先完成可信的 FK实例ID、多外键关系、复合键元数据合成fixture和 graph-index输入格式检查，记录 checkpoint 1024维兼容性，原始GFM消息传递/向量排名是否可复现。此阶段 G0 仅接口与张量的无Gold/synthetic smoke，不得直接宣称 SQL JOIN role/path 准确率；Role Gate仍NO-GO，训练 Query-aware Edge Gate 前须获得经人工/规范验证的JOIN Gold分母。
不要把双视图 Schema Context 工程收益和 GraphReasoner 消融混到同一次P2d.1比较。

## 7. 公开/私有交付

- 公共代码/fixtures/test：`scripts/text2sql/` 和 `tests/`，如更改评测器优先独立PR，明确版本命名 `p2d_eval_v2`；不要在原 `p2d_sql_evaluator.py` 中无版本修改历史规则。
- 公共匿名聚合：`docs/research/text2sql/reports/p2d_1_eval_audit_YYYYMMDD/` 的README/config/aggregate/verification/failure taxonomy与hash，必须列 **旧8/7/8原始口径 + v2重新评测的新口径，不能混为一个**。
- 私有：30问题/Gold SQL/预测SQL、DB/Values内容、人工复核原文、逐题ID、日志及模型服务地址，不上传GitHub。
- 全部新生成数字必须有真实CPU运行记录；本文件没有运行新实验或申请新模型费用。

**下一次希望得到的报告**：v1 vs v2 在30题上可比题的 exact parity、4个 reference blocked 的安全判定、7/8/6预测失败的具体根因矩阵、原19人工复核状态、Prompt token 的组成及研究人员可据此决定的下一轮G0/P2e优先级。
