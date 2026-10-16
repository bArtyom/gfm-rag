# 下一轮唯一执行指导：P1.5 错误/预算审计 → 条件式 P2a 混合检索

> **制定：2026-10-16。协议与门槛已冻结；P1.5 于 2026-10-16 执行完成，严格历史逐题复现门未通过；P2a 未运行。** 结果见 [P1.5 报告](../reports/p1_5_diagnosis_20261016/README.md)。本次只更新执行状态，不改实验条件或历史 P1 判定。
>
> 最新依据：[P1 复核](../reports/p1_review_20261016/README.md)；[原始结果](../reports/gfmrag_p1_official_20261014/report.md)。**不要修改 P1 已冻结配置或历史 NO-GO。**

## 总决策

当前没有理由继续尝试更多 Embedding 截断维度，也不应马上训练新的 Query-aware GNN。**下一次实际开跑的实验编号定为 P1.5，先处理 1024 基线错误来源、Top-K / token 预算饱和、FK metadata Gate。**

P1.5 先使用本地既有只读工件（CSV、DDL、参考标签、曾保存的 1024/512 向量或排序）。如果向量/排序确实未保留，只允许在完成成本、资源和数据版本冻结后重新编码**既有 1024 一组**用于诊断；不新增模型、维度或 SQL/API 调用。**P2a 必须等待 P1.5 Gate 结果，不与 P1.5 混跑。**

## A. P1.5 操作清单

### A0：确认可复现输入及审计源

- 绑定代码 commit `b3e43219c49929da505244df4f0ba54c0947e4c4` 与此次 runner 的 SHA：`824cbfbd0e18b2ecadada6738b447300c8725515d7867cac4cb1467ff1d2bd4f`。
- BIRD dev 1,534 问题、11 DB；Table gold 全部；Column gold 可用 1,460（另 74 要记录不能参与的理由与分库）。只读取获许可的本地输入，保留输入 hash。
- 固定候选文本原样：Table(name + 全部原始列名)；Column(table/column、type、description/format/values)。冻结 DB 内节点排序、文本 hash、query instruction、归一化、tie-break。
- 检查本地是否保存逐题向量/排序、Schema token counts；若未保存，先**只输出缺失清单**，不要将聚合 JSON 虚构为可恢复的逐题得分。
- 不执行新的 SQL，不访问 Jev，不改生成器、selector、GNN。

### A1：检查 Top-K 及 token 预算的测评有效性

形成每个 db 的以下统计（不要只给全局 1534 汇总）：

1. `#tables / #columns / #questions`，Table/Column gold 个数分布，gold 个数大于 K 时的“天然不可达到完整召回”比例。
2. Table R@5/@10 饱和率：例如候选 Table 数≤K 时，R@K 不检验排序能力；分析中拆开“平凡满召回”与真正需要排序的题。
3. Corpus 节点文本长度 p50/p95、所有节点文本 token 总量、预算/总量比例。
4. 计算 *Gold-only oracle-fit*（在当前文本表示下，完整 Gold 的总 token 数≤给定预算则理论上可装入）、完整 Schema 直接塞入是否可行；后者非线上检索策略，只是诊断上界。
5. 仅在本地可用完整排序向量时，固定 512/1024/2048 三档 token budget 对 1024 baseline 做预算曲线；用**相同排序**和文本，不要再编码。必要时另记录 256 作敏感性分析，但不得事后挑预算宣布成功。
6. 输出 Precision@K、Recall@K、Gold rank p50/p90、MAP/MRR（须注明多金标口径）、完整表列覆盖@budget、检索返回总元素数与 Token Efficiency。Table/Column 的 type-specific Top-K 与 combined budget 必须分开报告。
7. 对 1024 维按库聚合，找低列召回库/高饱和库，并区分“列排序错误”和“预算太紧/描述过长”。

### A2：配对失误归因

- 用现有冻结的 512 vs 1024 维逐题结果（**只有本地可核对时**）建立救回/损坏表，先对完成度变化的 **9 救回/21 损坏**查来源；不可仅从聚合统计臆造题目。
- 同时采样所有 Column@10 未命中的题，而不是只调查 512 损坏题。分类建议：Lexical 直匹配失败、Column 描述空/噪声、同名多表、类型/值信息干扰、Query 改写或同义词、正确列排名过低、候选列表太短、长文压预算、Gold 标注歧义。
- 对每个类型记录数量、分库、代表性的匿名 ID 或 hash 与可验证来源；如果需人工标签，先盲审再揭示方法。
- 严格分离“利用 Gold 诊断错误”与“把 Gold 用作候选文本/检索特征”，禁止泄漏。

### A3：P0-FK Gate 修复性诊断（并行，但不能越过）

- 核对为什么 2026-10-14 P0 判定 FK 不合格：约束缺失、BIRD Schema FK、实际 DDL FK、Gold 非 FK join、复合 FK、多条 FK 角色、表列 ID 映射，分别计数。
- 用真实 DB 结构生成**稳定 Join-Instance ID**（`db_id + constraint_id + ordered_column_pairs`），复合 FK 原子化；不生成语义上不存在的新边。
- 先统计连接覆盖、Gold JOIN 适配率、不可唯一裁定路径、可比较的同表多关系候选数；无法核实等价路径时标记 `ambiguous`。
- 这一步的目的是判定能否研究 Join/Role，不是运行业务角色分类；**FK Gate 不过就不做 Role/Path 准确率实验**。

### P1.5 交付

预期新建 `docs/research/text2sql/reports/p1_5_diagnosis_<date>/`：

- `README.md`：数据/分母、可用性、异常、真实执行状态、错误归因、Gate 决策；
- `aggregate_summary.json`：按维度、库、K、预算分层的匿名汇总；
- `input_manifest.json`：数据 hash、节点 ID 序、模板/工具版本、模型及 runner SHA；
- **实现脚本和单测（如需）**：建议放 `scripts/text2sql/` 与 `tests/`，不直接改动 upstream `gfmrag/` 训练模块。
- 逐题含原题/SQL、embedding 缓存、数据库内容本地保存，不推送到公开仓库。

## B. 决策门槛（P1.5 → P2a）

**通过条件：**
1. Gold 与候选源的覆盖/不确定性及旧序列化差异已明示；能复现至少 1024 的 baseline（同代码/数据/信息量）或者如实报告无法复现。
2. 有清晰的、可由运行时可见信号改善的 Column 检索错误类别和足够样本；错误不主要由“Gold 不可靠/全库预算已饱和”造成。
3. 多预算下不会仅因为 2048 可以装下所有 Schema 而假性提高；所有汇总按数据库与真实可评问题分母报告。
4. 如果提到 Role/Path，**单独**满足 FK Join-Instance 质量门；不通过不影响列检索 P2a。

**不通过：** P1.5 只交付诊断及可修复问题，不启动新算法 sweep；若列召回主要受 Gold 歧义或候选信息不足影响，优先修复数据和字段描述规范，而非扩大融合网格。

## C. 通过后唯一新评分实验：P2a（先 Column，1024 主基线）

固定 1024 Qwen3 embedding、同 1,460 可评 Column 题、同 DB 内原始候选节点及文本、相同 prompt、同一时间预算和候选预算。推荐无训练、先不做 FK：

| ID | Method | 意义 |
|---|---|---|
| S0 | 原 1024 L2+Cosine | 冻结主基线 |
| S1 | BM25（表列 tokenization 规则统一，大小写、snake_case 的处理单独冻结） | 词面基线 |
| S2 | Cosine 与 BM25 的 RRF（预设 k0，未召回候选的排名处理固定） | 仅测简单融合是否有效 |

- 只在训练/验证 DB 冻结 BM25 tokenizer、RRF k0（可先无调参常数）；同一测试 DB 不调参。
- 分两层汇报：**type-specific Column@5/@10/@20** 与**combined 表列@512/1024/2048 token**；附 Precision、MRR、完整覆盖与 gold oracle-fit。
- 报告每库宏平均/题宏平均、配对 rescue vs damage、数据库 cluster bootstrap 95%CI、索引/编码/计算成本。
- **512 维只作为可选的储存/精度 Pareto 参考**，不改变历史未过 Gate 的结论；如增加实验，明确当作新 P2a 资源因子。
- 如果 S2 的增益可由 BM25 单独解释，就不主张“混合算法有创新性”。**S0/S1/S2 均为成熟 baseline，不是论文新贡献。**
- 不直接重复跑归一化 Dot 与 Cosine（等价）；不引入新的 Qwen 模型，也不调整 SQL Generation。

### P2a → P2b 的预设 Go/No-go（需在执行前冻结）

建议的初版决策阈值（**计划目标，非实验成绩**）：在非饱和、有可靠 gold 的子集上，相对 S0 Column Recall@10 提升 ≥2.0 pp **或者**完整 Schema@预算提升 ≥1.0 pp；同时主报告全体可评样本不能出现不可接受的大幅回归（暂以 Table R@10 相对下降≤1 pp 为风险门），并具备分库方向一致的证据。冻结后不按结果修改门槛；独立数据库 holdout 才可作为泛化主证据。

若不通过：记录负结果，改进文本表示/列描述而非立刻训练 GNN。

若通过：P2b 才研究 Relation-description Cosine、Join Instance、Role/Path 评分；**必须额外满足 FK Gate**，并与同信息角色文本基线对照。最后 P3 才用固定下游 SQL Generator / Selector 测 Set EX 主指标、Bag EX 和费用。

## D. 禁止行为

1. 修改 2026-10-14 的 P1 筛查阈值，把 512/768 事后宣称通过。
2. 以 99.91% Table@10 证明“表语义链接几乎完全解决”，不分析 db 中候选表数。
3. 将 2048 预算的 79.66% 与独立 Column R@10 的 68.01% 当作相同候选预算直接比较。
4. 把 873 节点的 50% 向量存储节省宣称为显著端到端成本改进。
5. 用 FK 质量未通过的数据报告任何 Join Role / Path 排序收益。
6. 在 BIRD dev 上连续搜索多个维度/融合超参，把最优值报告成独立测试表现。
7. 未执行实验便写性能数字或提交原题、逐题 SQL、敏感日志。

## E. 下一次要求实验执行方回复的内容

**只需回传 P1.5 的已完成报告和 Gate 结果**：74 题不可评归因、每库 Top-K/2048 饱和、1024 Gold rank & 512 配对错误来源、FK Gate 原因、原始输入/源代码 hash、真实资源与测试情况。若仍缺私有数据则报告阻碍，不得制造指标。收到 P1.5 后再由本仓库更新 P2a 的最终冻结执行命令与参数。
