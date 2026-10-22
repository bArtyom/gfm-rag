# P2d 首次真实 SQL Pilot 复核与下一轮研究决策（2026-10-22）

> **性质：已归档实测的独立静态复核与研究指导，非新实验。** 主仓库 `bArtyom/gfm-rag`；审阅基点 `67cb9e0a2b0c9a0b900bb955f9e9821cd0772265`。使用 [原P2d报告](../p2d_sql_utility_20261022_01/README.md)、[Full指标](../p2d_sql_utility_20261022_01/full_summary.json)、[失败分布](../p2d_sql_utility_20261022_01/failure_analysis.json)、[验证](../p2d_sql_utility_20261022_01/verification_summary.json)、[执行预注册](../../plans/p2d_sql_execution_20261022.md) 和 [评测器源码](https://github.com/bArtyom/gfm-rag/blob/main/scripts/text2sql/p2d_sql_evaluator.py)。实验已执行；下文下一轮计划尚未执行。

## 一、P2d 的主要结果：离线 Schema 覆盖收益没有在诊断 SQL Pilot 中转化为已确认 SQL 提升

- BIRD dev 30题（**19条被筛出的Values高风险题 + 11条严格匹配对照，5 DB**；8条高风险没有严格对照），**不是均匀抽样**。固定已有 Qwen2.5-Coder-7B-Instruct / vLLM 0.8.5、temperature=0、seed20261021、selector=none、同 Query/Evidence/系统模板，三臂每题仅一次生成：
  - **E0**: V00 原节点 + R0 完整含 Values 文本。
  - **E1**: V01 新节点选集 + R1 短文本（检索仍用 R0 embedding）。
  - **E2**: **固定 E0 相同节点 ID/顺序** + R1 短文本（隔离 Values 内容变化）。
- 实际 3 合成/9 Smoke/90 Full = **102次本地请求**，usage 真实入账、模型/输入/输出/DB 源 SHA 校验 PASS，外部API付费0、共享GPU成本未估；完整生成成本不能等同零。
- **30固定分母确认 Set / Bag 正确**：E0 **8/30**，E1 **7/30**，E2 **8/30**（分别 26.67%、23.33%、26.67%）。这不是官方 leaderboard EX；评测器是明确语义的 BIRD-compatible 非官方实现，未测稳健重生成及独立 DB。
- 生成SQL可执行：E0 19/30、E1 18/30、E2 20/30；**未知** E0 11、E1 12、E2 10（未知一直计入30题分母，不能等同已证实错误）。参考 SQL **26/30** 可执行，剩余4题受保守 evaluator 规则拦截。
- E0/E1共同可判只有 **17题**：6两臂正确、1 E0-only、1 E1-only、9两臂错，其他13题至少一侧未知。E0/E2共同可判19题：7 both-right，1 each-only，10 both-wrong，11 unknown。E1/E2共同可判18题无各自独有正确，其他12 unknown。**这不能支持 E1 系统性退化/改善，也不能支持 Values 无损。**
- **原19优先题**：E0/E1/E2 5/4/5确认 Set 正确，各10/10/9未知；绑定支持9题中各3/2/3确认正确（E1少1不是一个经人工确认的价值语义伤害）。覆盖 rescue6题各臂零确认正确，其中4题未知，不得声称额外 Schema 无用。
- AST 直接 Literal/pair相等是有限句法诊断，**不是统一语义正确率**。人工必要性复核仍0，语义必要性分母0。

## 二、这次最重要的机制线索：更短的节点描述不等于更短的完整 Prompt

| 臂 | Full 总模型输入 tokens | 相对 E0 |
|---|---:|---:|
| E0 R0节点+R0全文 | **35,074** | 基线 |
| E1 V01更多节点+R1短文 | **35,591** | **+517（+1.47%）** |
| E2 原节点+R1短文 | **24,458** | **−10,616（−30.27%）** |

- **E1 vs E2 +11,133 tokens（+45.52%，按E2为分母）**：短文本装包腾出的空间几乎完全用于更多 Schema 元素和表列包装开销。P2c-R 的 schema-node Complete@1024 **+10.96pp** 仍真实存在，但在这里不代表 Generator prompt 更短，更不代表 EX 增益。
- E2 Token 节约清楚；E0/E2确认正确总数同为8，但**不是相同的8题**，共同可判对称1救回/1损坏。E2不能直接升级为安全默认设置。
- 下一轮的潜在方法方向是**联合决定“用于检索的富语义文本、最终呈现文本和 SQL Generator 真正token预算的表列打包”**，而非继续在固定 Schema tokenizer 1024 预算下求完整 Gold 节点。**当前还没有 E3 控制臂或新打包算法实测，不可宣称新颖性/增益**。

## 三、评测质量缺口比扩大样本更迫切

检查 `scripts/text2sql/p2d_sql_evaluator.py`：`_validate_sql()` 当前对 `date/time/datetime/julianday/unixepoch/strftime/timediff` 的**所有参数必须是显式 Literal**（当前约 L86–93），拒绝可能求值为 `now` 的表达式/列。原报告确认有 **4题参考SQL因非字面量时间函数参数被 unsafe_sql 拦截**；这并非参考SQL有恶意操作或语义错误，而是 evaluator 预先冻结的保守授权规则覆盖有限。

- 其余预测SQL不可执行且参考可执行有 **7/8/6** 题（E0/E1/E2），故未知问题**不仅**来自这4个参考限制；生成器本身存在输出解析/SQLite错误/安全拦截。
- 公开类型：SQLGlot parse error **4/2/4**、SQLite执行错误 **5/7/3**、预测 unsafe_sql **2/3/3**（每臂总计11/12/10个预测无法执行）。公开回执有通用错误类型，尚不能归因具体缺列、FK、谓词、类型或表达式；不能凭聚合猜根因。
- **不要为了“让EX变高”把时钟/文件/写操作过滤整体放开**。如果进行评测器 v2，应限允许经证明与运行时时钟无关的时间表达，继续双重 AST+SQLite authorizer、read-only DB、子进程超时/内存/行数/字节限制。可能存储字符串 `now` 的列须保守处理；要证明确切4例是否可安全评测，不能自动恢复所有。若无法安全通过，维持unknown。
- 原 P2d 8/7/8 和完整回执 **永久保留**。新的 re-evaluation 只读取旧已封存预测+Gold，无模型调用，**另立版本和规则、补齐合成反例后另算辅助指标**，不可把 v2 数字静默覆盖原预注册主结果。

## 四、当前结论和独立主线

**P2d 是有用的工程+探索性诊断，却没有给 V01 的 SQL EX 增益提供支持。** 此时优先开展**P2d.1 冻结预测评测覆盖与失败归因**，辅以 **19题独立语义审核**。工程 PASS后才视实际错误模式决定是否开展 P2e“Generator预算感知 Context 打包”对照；不立即改 7B Prompt/模型、扩全量BIRD dev、进行 Values 参数扫描。

另外必须从学术研究价值上区分：dual-view/紧凑上下文属于有明确证据支持的工程基础，但其本身未构成 G-reasoner 论文级图创新。FK/JoinInstance/Role Gate 仍 NO-GO，**官方 GraphReasoner→Schema graph G0 baseline从未真实运行**。允许独立并行做 G0输入/关系实例完整性合成兼容 smoke，不能把工程可行性写成 GNN检索改进或 SQL EX。

## 五、下一轮交付

[P2d.1 冻结预测审计与评测器 v2 Gate](../../plans/p2d_1_frozen_prediction_eval_audit_20261022.md) 将指定只读复算、独立新输出、新安全条件、全部30题的未知/错误分层、19题语义审核状态与Go/No-go，确保下一次结果能够区分“评测器不覆盖”与“Generator/Schema真的无法输出合法SQL”。

结论中禁止将单次30题 targeted pilot 的任何百分比称为全BIRD SQL EX；也禁止将P2c离线Complete提升写成实际SQL收益。
