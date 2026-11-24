# RAMP-SL 创新性定位与结构感知 V2 研究路线（决策记录）

> **2026-11-24｜IDEA / RESEARCH POSITIONING / NOT RUN**。本文保存研究判断，**不是已执行的实验协议，不修改 RAMP-SL V1 的方法、超参、数据分库或 GO/STOP 门槛**。V2 属于条件性研究候选：先完成 V1 强基线对照，再决定是否立项。当前分支为 research/ramp-sl-v1-active-encoding-20261124，不修改 main 与 G2 主线。
>
> 证据入口：[RAMP-SL 2026-11-23 离线上限实验](../reports/ramp_sl_encoding_budget_gate_20261123_001/README.md)；[RAMP-SL V1 执行指导](ramp_sl_v1_budget_feasible_active_encoding_20261124.md)；[原始 Idea](ramp_sl_progressive_schema_encoding_idea_20261123.md)；[BoundaryMORPH 独立报告（跨分支固定版本）](https://github.com/bArtyom/gfm-rag/blob/d9cca989dbe38f2b8d717860e86ad2665a9305fc/docs/research/text2sql/reports/boundarymorph_grast_bird_20261123_001/README.md)。

## 1. 回答核心问题：研究的是模型还是方法？

**目标是提出一个新的 Text2SQL Schema Linking / 预算化主动编码方法，不是训练新的 GRAST 精排器。** 使用官方 GRAST-SQL 0.6B BIRD Reranker 作为**冻结的高成本 query–column 打分后端**是合理的；模型本身不是我们的论文创新。方法研究的是“有限计算预算下，如何主动选择哪些字段应获取高成本查询感知评分，以及这些评分如何改善整题必要 Schema 的完整恢复”。

| 组成 | 来源 | 当前创新地位 |
|---|---|---|
| 低成本 Qwen3 Embedding 排序 | 已有模型及 P1.6 缓存 | 非创新 |
| GRAST 0.6B 官方精排器 P(yes) | 官方发布权重；本项目只运行 scalar reranking | 非创新；**未完成官方 GNN / Steiner / SQL** |
| 固定 Top-M 再调用昂贵模型 | 常规粗排—精排基线 | 非创新 |
| GP 后验、边界不确定性主动采样 | BoundaryMORPH 等相关工作已有 | 单独不足以建立新颖性 |
| 固定真实高成本输入 token 预算下的主动选列 | RAMP-SL V1 的待验证系统问题 | 值得做，但两轮调度或 cost normalization 本身不足 |
| **在高成本评分前利用可验证 Schema 结构与字段组互补性，优化完整可用 Schema 集合的预期收益** | V2 候选核心 | 可能形成独立方法贡献，**仍需严格机制消融和先行工作核查** |

预算必须区分：M 是**实际调用昂贵模型的输入 token**（不能只计最终被选字段的预计 token）；K 是如采用的最终字段数量约束；B 是序列化 Schema 和未来若加入的连接闭包输出 token 成本。

## 2. 当前为什么还不能说有足够论文创新？

**GRAST** 已经提出问题感知 Schema 编码、图重排序及 Steiner 连接补齐；复用这些模块或简单搬到前端不能充当新方法。**BoundaryMORPH** 已研究 cheap prior、vMF/GP 后验和在昂贵评分预算下的边界主动采样。本仓库 2026-11-23 的 BoundaryMORPH pilot 用 **Jina 代理、固定16评分调用、Top30** 获得探索性收益，不能直接等同于本轮官方 GRAST token-budget 方法，更不能宣布 GP 主动选择由我们首次提出。

KaSLA 已有受预算约束的 Schema 集合选择；AttnLink 已研究集合覆盖相关的学习目标；EviLink 已研究根据不确定性获得额外字段证据。将“GP、字段必需概率、除以 token 成本、两轮选择”直接拼装，可能只是这些已有思想的任务迁移。具体差异仍需要完整论文/源码核查，不得仅凭命名宣称独创。

**V1 的集合函数存在退化风险：** log Q(T)=Σ(对未入选字段 c 的 log(1−p_c)) 假设各字段需求独立，缺少 JOIN/字段组条件依赖；在 B 较宽裕时，可能近似退化为单列 p(c)/cost 排序。2026-11-23 旧实验在已执行样本中，Static/Offline Oracle 的最大输出为 1560/1439 tokens，均低于 B=2048。若 V1 无法通过与 Calibrated-2R、BoundaryMORPH、单列 p/t 的消融区分，就不能把“集合级”当作创新结论。

**历史 headroom 不是方法增益。** RAMP-SL 上限实验：pilot 110题/11DB，Static 73、Offline Oracle 100（+24.545pp）；full 在输入 token 上限处停于1046题/8DB，Static603、Oracle915（+29.828pp）。Oracle 在筛选前已经对全部字段进行昂贵评分，实际推理超过 M，它是参考上限而非可部署方案。上述数字不属于 V1/V2 的真实预算效果，也不代表 SQL EX。

**当前判断：** RAMP-SL 的科学问题成立、V1 具有强基线实验价值；但其现有机制靠近已有主动精排，**创新性目前未证实**。不要提前宣称“不可能创新”或“足够 A 会”，应通过可证伪对照识别新增机制。

## 3. 候选创新：Structure-aware Budgeted Active Schema Encoding

### 3.1 真正区别于普通文档精排的难点

Text2SQL 经常需要**成组**召回列。例如“每个客户最近一次付款的金额”，可能需要 customers.id、payments.customer_id、payments.amount、payments.date。找到金额列但漏时间列、关联键，仍可能无法正确生成 SQL。普通边界采样重点判断“哪个单列排名不确定”；目标方法要判断“**获取某个字段/结构组的昂贵评分，能否降低整个可用 Schema 集合不完整的风险？**”

此论断是研究假设，不代表 GRAST 没有结构建模。要将贡献锁定在 **决定谁获得昂贵编码时使用结构**，而不是再发明图消息传播或精排后的 Steiner 补路径。

### 3.2 条件性 V2 机制草案（不是冻结协议）

1. **冻结线上可见输入：** query、cheap 全列相似度与向量、已执行高成本评分集合 S、剩余真实 M、输出 B，以及来自可信来源的 Schema 关系 G。可用的安全关系包括 table–column ownership、可核验主键；FK 必须先通过具体 constraint ID、复合 FK 列对、角色及来源质量审计。对未经检验的预测边不能假装是可信 FK。
2. **用 V1 两轮框架保留因果边界：** 第一轮只评分预算内候选，训练库内拟合的代理预测未评分列的高成本分数及不确定性；测试时禁止直接查看全列 scorer 缓存/Gold。第二轮规划完成前不得看第二轮真实评分。
3. **把字段独立重要性升级为结构约束下的候选组合效用：** 用可验证 ownership、列组、连接路径的**互补性**和严格的 B/闭包成本定义一个“完整可用 Schema”质量代理。该代理不能简单把多个独立 p(c) 相乘就宣称实现了结构建模，也不能强行把参考 SQL Gold 当作唯一合法 SQL 的需求。
4. **反事实模拟评分的边际收益：** 对一个未评分字段或合法字段组，积分其可能的 GRAST 输出，预测最终 B 内的列集合及可靠连接路径怎样改变；以“结构代理损失的预期下降 / 实际 GRAST 输入 token”选择下一批。在联合选择时应处理多字段组的重叠贡献，每个实际评分字段精确记账一次，整个 query 不超过 M。
5. **实证重点：** 与同一 Qwen 初始池、同一 GRAST、同一 M/B 的 Static、Stratified、BoundaryMORPH、V1 GP、V1 p/t 比较，另必须对比**完全相同前端选择后才运行同一个 FK/Steiner closure** 的控制组，分离“提前用结构指导昂贵编码”与“只靠后处理补列”的作用。

以上是 V2 可能的**结构调度机制**，不是现有实现，尚无结果。不要把它和 GNN 替代、关系预测、摘要图、训练全新编码器同时塞到同一新方法里；保持最小可解释机制。

### 3.3 必要消融矩阵与证伪条件

| 对照 | 要证伪什么 |
|---|---|
| V2 vs V1、BoundaryMORPH、Calibrated-2R，全部真实 M/B 相等 | 增益是不是已有主动采样或便宜重排即可解释 |
| V2 去除结构因子，其余特征/评分预算完全一致 | 结构信息是否真正驱动 acquisition 改进 |
| ownership-only vs trusted-FK-aware | 是表内字段组合，还是连接语义贡献 |
| trusted-FK 移除/打乱（负控只用于诊断） | 是否错误依赖无关或带噪边 |
| 相同最终 FK/Steiner closure 但前端不结构化选择 | 是否只是后处理补字段的功劳 |
| 有/无集合互补收益、有/无成本项，但强制相同 M | 复杂模块是否必要 |
| B=512、1024、2048 及 B 实际绑定比例 | 集合/闭包约束是否真实发生 |
| DB 隔离、非饱和问题、复杂 JOIN、真实 GPU 时延、最终 paired SQL EX | 质量是否可泛化，调度开销是否抵消收益，SQL 是否真的改进 |

这里不能只看 Column Recall 总数字，还应报告完整参考列覆盖、可信 join-instance/连接可行性（标签通过质量 gate 后才使用）、DB-cluster bootstrap、配对 rescue/damage、SQL 多解风险、真实 token/时延、独立数据库与未来外部数据复现。

## 4. 下一步决策树（不得事后修改 V1 门槛）

- **A｜V1 不超过 Static、Calibrated-2R 或 BoundaryMORPH：** 优先做预算/候选饱和、GP 校准、B 不紧、低成本排序与多列漏失归因；禁止在同一测试集反复调参。只有结构错误确实占较大份额且有可信结构证据时才单独预注册 V2，不能把 V1 失败自动包装成 V2 新颖性。
- **B｜V1 超过 Static，但不超过 p/t 或 BoundaryMORPH：** 保留 V1 为基线平台，承认收益可能由已有机制或监督重排解释；优先验证结构型失败是否足以支持 V2 研究问题。
- **C｜V1 稳定超过公平预算强基线：** 继续完成 GP、成本、集合函数消融与外部数据库复现；再根据真正的结构型误差决定是否需要 V2。必要时可直接以 V1 的明确可证机制为论文候选，但不能因分数好就宣布 novelty。
- **FK / Role Gold Gate 仍 NO-GO：** V2 的真实 JOIN/FK 主张 **HOLD**。可以仅用可核验 ownership/表内字段组进行独立探索，但不能由 ownership-only 实验推出 join-aware 有效。真实 FK role 训练/评测必须先完成标签来源与质量治理。
- **主线关系：** 本支线不更改 G2 非对称 relation-channel identifiability 的既定优先级。

## 5. 推荐论文定位与禁止的说法

**可能的论文定位（条件式）：** “A schema-structure-aware acquisition policy that decides where to spend expensive query-aware column-scoring tokens to maximize complete usable Text2SQL schema recovery, while holding real inference cost and final output budget fixed.”

**不可声称：** 重新设计了 GRAST 精排器；首次使用 GP/图/JOIN/集合目标；Offline Oracle +29.83pp 是我们算法结果；Embedding Top-M 与全评分 Oracle 同计算成本；本轮运行了官方 GRAST GNN/Steiner/SQL；字段召回提升等于端到端 SQL EX 提升；结构机制已经证明有效。

**如果结构消融失败：** 坦诚归档为强基线与预算可行性/失败归因的负或中性结果，不通过换名或堆模块制造创新。

## 6. 执行安排与引用

1. **先执行 [RAMP-SL V1](ramp_sl_v1_budget_feasible_active_encoding_20261124.md)** 的缓存完备性预检、严格预算 replay、训练数据库 smoke、sealed held-out test。此文只提供研究定位，不覆盖既定 M/M0/B、对照、指标、拆分、Go/Stop。
2. 对 V1 测试归因分类：cheap 候选漏列、精排误判、互补字段缺失、跨表连接键遗漏、真实 token/B 瓶颈、Schema 结构约束失效、参考 SQL 多解。GitHub 仅上传匿名汇总。
3. 若结构型错误在质量可信范围内成立，再独立创建 V2 预注册协议、固定训练/验证/测试数据并评估强对照；不能拿已经使用过的 V1 测试集进行无约束迭代。
4. V2-FK 先过 FK/Role 数据质量 gate，再考虑官方 GRAST 图/GNN/Steiner 接入和固定生成器下的 paired SQL EX；不能在没有 Gold Join 可信度时宣称连接正确率。

相关先行工作入口：[GRAST-SQL](https://arxiv.org/abs/2512.16083)；[BoundaryMORPH](https://arxiv.org/abs/2609.27213)；[KaSLA](https://github.com/DEEP-PolyU/KaSLA)；[AttnLink](https://arxiv.org/abs/2608.00693)；[EviLink](https://arxiv.org/abs/2605.29670)；[AEGT](https://arxiv.org/abs/2611.20979)；[本仓库预算修复负结果](../reports/budget_repair_attention_bird_20261121_01/README.md)。

> **Novelty caution：** 以上是基于已有项目证据与近邻工作的阶段性定位，不是穷尽文献检索；投稿前必须再做最新相关论文与开源实现的系统性查重。**本次只写入指导文档，V1 与 V2 都没有新增实验结果。**
