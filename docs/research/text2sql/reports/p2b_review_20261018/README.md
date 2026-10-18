# P2a.5 / P2b 结果复核与 P2c 研究决策（2026-10-18）

> **性质：已归档结果的静态复核 + 新研究决策；不是新实验。** 审阅起点主仓库 `4afe4fcd55eee151271fbb45d7c975bb3762303f`。所有实验只在反复开发的 BIRD dev，未经独立数据库验证。本研究线仓库唯一入口：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)。

## 1. 当前完成状态

- [P2a.5 冻结排名错误审计 / FK Gate](../p2a_5_error_audit_20261018_01/README.md)：Full/缓存/逐题重放、S0 parity PASS，错误特征与结构原因分类完成；**P2a 的方法增益 NO-GO、FK/Role 标签 Gate NO-GO 都没有改变**。
- [P2b Values R0/R1 实验](../p2b_values_ablation_20261018_01/README.md)，[聚合 JSON](../p2b_values_ablation_20261018_01/aggregate_summary.json)：1534 题/11 DB、1460 Column-eligible；R0 原始文本 vs R1 只移除 `value_description`，1024-D Qwen3、同 CPU backend、query vectors、Cosine 和节点池。**Full 数据完整性 PASS，预注册主成功门 NO-GO**。
- 官方 G-reasoner GNN 及 Text2SQL SQL EX：**尚无本研究线实验结果**。BIRD dev 已多轮查看，所有观察均为探索性。

## 2. P2b 主指标及其统计边界

| 指标（query macro） | R0 保留 Values | R1 删除 Values | R1−R0 |
|---|---:|---:|---:|
| Column R@5 | 52.82% | 51.77% | −1.05 pp |
| **Column R@10** | **67.99%** | 67.03% | **−0.96 pp** |
| Column R@20 | 79.21% | 78.67% | −0.55 pp |
| Complete Schema@512 | 35.34% | **38.90%** | +3.56 pp |
| **Complete Schema@1024** | 56.64% | **65.96%** | **+9.32 pp** |
| Complete Schema@2048 | 79.52% | **85.82%** | +6.30 pp |

- 全体 Column R@10 delta 的 11-DB cluster bootstrap 95% CI **[−2.06,+0.08] pp**，跨 0；不能称 R1 已确定性损失 0.96 pp，也不能说 R1 表示更好。原预注册目标为 ≥+1 pp 且 CI 下界>0，**失败**。
- 预先按 R0 冻结的非饱和 5 DB/706 题：Column R@10 **−0.67 pp**；Complete@1024 **+5.52 pp**（cluster bootstrap CI [+2.73,+8.25] pp，5 DB 区间有限）。
- R0/R1 873 节点的全部 Schema 文本从 **27,506→20,071 tokens（−7,435；−27.0%）**；有 Values 的列 **278/798**。R0/R1 均包含相同 75 表、798 列，改变的是 node.text 与长度，不是候选数量。
- 1024-budget 下平均实际选取 tokens 949.59→915.27；Schema 整体变短，预算内能够容纳更多不同元素，是覆盖上升的合理机制；**但本轮同时改变排序与文本长度，尚不能归因出两者各贡献多少**。
- CPU R0 与 R0-repeat 节点向量 **bit-exact（873×1024，max diff=0）**；所有 Column Top-K 集合与次序不变。P1.6 冻结 vLLM/GPU cache 对照另行记录，与本次 CPU 组对照分离。

## 3. P2a.5 支持哪些新的因果实验？

- [P2a.5 匿名聚合](../p2a_5_error_audit_20261018_01/aggregate_summary.json) 中，BM25 在 1530/1534 题产生并列分数；其中 **400 题在 Column Top-10 截断边界上有同分**，不能把所有并列都等同 Top-10 边界影响。
- S0 Cosine 的 1024-budget：**1460/1460 题在 Gold-only oracle 下均可放入 Gold Table+Column 文本**，但实际只对 **820/1460 题完整覆盖**，说明当前损失来自候选排序和分配，而不只是 Gold 本身过长。
- P2a RRF 在全体 Column@10 救回 273 题、损坏 319 题，Complete@2048 救回 27、损坏 65；无需继续盲调融合参数。
- 278 列含 Values，且 P2a.5 中“Gold 列是否有 Values”与检索命中存在相关性，**不能从相关性直接推断 Values 本身增加语义准确性**；P2b 的 R0/R1 则提供了同模型消融证据，但分配效应混杂。

## 4. 本轮真正值得保留的研究问题：Dual-View Schema Retrieval

**当前最小可检验新假设**：用于检索向量的富语义文本，未必必须原样进入后续 SQL Schema Context。把 **Retrieval View**（保留 Values，用于向量打分）与 **Prompt/Context View**（仅用于预算和呈现的紧凑文本）分离，有可能同时保留 R0 的 Column R@10 和提升预算内完整 Schema 覆盖。

这和 P2b“删除 Values 是否提高向量检索质量”的失败假设**不同**。不要把本想法写成“P2b 成功”，也不要在旧预注册下追加额外 R1 参数组合；必须另开独立预注册协议，且先只做 CPU 缓存重放的二维因子归因。

四个离线条件（采用 P2b **同一 CPU 后端缓存、同一 query vectors**）：

| 实验 | 向量/排名来源 | Schema Context 文本/长度 | 用途 |
|---|---|---|---|
| V00 | R0 embedding（含 Values） | R0（含 Values） | 原 P2b R0 基线，冻结 parity |
| **V01** | **R0 embedding（含 Values）** | **R1（无 Values）** | **核心：语义检索与预算呈现解耦** |
| V10 | R1 embedding（无 Values） | R0（含 Values） | 单独评估删 Values 对向量排名的影响 |
| V11 | R1 embedding（无 Values） | R1（无 Values） | 原 P2b R1 基线，冻结 parity |

要求：V00、V11 对 P2b 的**同 CPU 组**逐题精确重放；V01 / V10 的 Column R@K 必须分别与 V00 / V11 **完全一致**，因为只改变输出文本，不改变分数。如果不同，说明 runner 评分与文本长度耦合存在错误，**立即停**。

期望分离：
1. **Ranking 效应**：V10−V00（同样的 R0 长度；不同向量）。
2. **Packing/Context 效应**：V01−V00（完全相同的 R0 排序；改变文本长度）。
3. **交互效应**：(V11−V10)−(V01−V00)，避免误称预算增益完全来自较短文本。
4. **最终 SQL 信息风险**：V01 Prompt 文本缺少 Values，虽然 Schema gold coverage 更高，SQL 可能需要谓词值/业务枚举。**没有固定 Generator 的 SQL EX，就只能报告离线 Schema 指标，不能叫最终 Text2SQL 性能提升**。保留/回补 Values 的预算开销需要另立实验。

**研究新颖性边界**：富检索表示与紧凑展示分离是常见检索工程思想，不能单独声称有论文级创新。其研究价值在于 P2b 已出现显著的排名–预算冲突，因子实验能提供可归因依据，并可作为未来 Graph Edge/Join subgraph 方法的基础。

## 5. 另一个重要阻碍：FK/Role Gate 并未变为 PASS

P2a.5 重新确认 **103 raw SQLite FK（100 有效、3 无效）**，有效 JoinInstance ID 可稳定追踪；Gold 显式 JOIN ON 共 **1428**：**1199 unique FK match、204 unresolved/non-FK、25 ambiguous**；存在多 FK 候选的 query **197**，但**可可靠用作语义角色准确率的分母目前是 0**（human review=0）。

定位改善优先级：`student_club` 有 **90** 个被标为 `metadata_incomplete` 的 unmatched JOIN；这并不意味着它们必定是非法或可以凭空补 FK。先核对源 DDL/表别名/parent table 解析、BIRD JSON 与 SQLite 缺失映射，逐类标记合法非 FK、真正 metadata gap 与不可裁定；再在高可信子集上设计 GFM/Edge 研究。

## 6. 决策与执行边界

**唯一优先执行的下一轮：P2c Frozen-Cache Dual-View 2×2 Retrieval/Context Factorial**，完全 CPU 离线，禁止重新编码、改向量、调融合权重、训练 GNN 或执行 SQL。必要的基础图数据治理允许与此并行，但仍是独立 Gate。

- 可复用 P2b Full 的本地 `embedding_cache_cpu_private.npz`（包含 `query_vectors`、`r0_node_vectors`、`r1_node_vectors`）以及构建 R0/R1 文本的固定逻辑；不允许基于汇总 JSON 猜测逐题结果。
- 先做 preflight/smoke，确保 P2b 行、R0/R1 文本/节点 ID、query vectors/embedding cache 哈希一致；再做全量 1460 有效列标签的预算检索比较，报告所有 1534 题表的指标。
- 保留全体与固定 706 非饱和子集、512/1024/2048 budget、Table/Column Recall、complete、实际 token、Gold-only fit 与配对 rescue/damage、数据库 cluster CI。
- 主要决策阈值必须在任何 P2c 得分出现前独立预注册；是否可开展后续 SQL 验证，还需 Value-critical SQL 风险审计和可靠独立 DB 检验。
- 不能把 P2b NO-GO 或 P1/P1.5 历史严格复现失败改写成 PASS。

执行方案：[P2c Dual-View 因子实验](../../plans/p2c_dual_view_retrieval_context_factorial_20261018.md)。
