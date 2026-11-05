# GFM Schema 多锚点候选的路线复核与暂停决策

**日期：2026-11-06。性质：只读研究决策记录，不是实验报告。** 多锚点实验方案已于 commit 2d0a057 在研究分支登记；没有实现运行器，没有执行 Smoke/Full，没有加载模型或产生指标。本记录暂停该候选，不改写原始登记。

## 决策

不启动 GFM 真实 Schema 多锚点诊断。当前分支的最新实验路线只保留一项 GFM 方法 Pilot：在两位真实审阅者的共识标签上，比较冻结 G-reasoner、Dense Cosine、BM25 与不看 Query 的结构排序，主指标为 FK mapping Accepted@1。两份 A/B 审阅表当前仍是空白模板，可信 Role 标签数为 0。

多锚点候选与该路线回答不同的问题，且没有足够的独立方法差异来覆盖当前路线的单实验限制。原登记方案保持不变，状态解释为“未运行且暂停”；不把草案存在描述成已批准执行或实验结果。

- 原候选方案：[GFM Schema 多锚点迁移诊断](gfm_schema_anchor_probe_20261106.md)
- 当前路线：[实验路线图](../experiment-roadmap.md)
- 最近前沿复核：[FK mapping 排序候选前沿复核](p0_fk_mapping_rank_frontier_check_20261106.md)
- 人工标签状态依据：[FK mapping 文献与实验门更新](p0_fk_mapping_rank_literature_update_20261106.md)

## 本地问题与证据

1. P2c-R 的 V01 在相同排名下缩短返回文本，使 Complete Schema@1024 从 56.64% 提高到 67.60%，但没有证明 SQL EX 提升。
2. P2d 的 30 题生成 Pilot 中，E0/E1/E2 的确认 Set 正确数为 8/7/8，未知结果较多。
3. P2d.2 对 28 条已封存失败的归因中，没有发现“失败字段没被检索进上下文”的案例；主要问题是 SQL 解析、限定符与作用域、字段存在性。
4. P2d.3 受限修复 A2 为 17/66，低于不修复 A0 的 18/66；后续反事实审计发现少量被拒候选正确，但不支持追加一般 SQL 修复实验。
5. G0-02 合成映射任务中，G-reasoner 为 2/4，Dense 为 4/4。G2 证明关系输入能改变一张非对称合成图上的原始分数，但所有条件 top-1 都未变化。

因此，当前最重要的未决问题不是“关系输入是否影响分数”，而是“冻结 G-reasoner 是否能把人类认可的 FK mapping 排在正确位置”。这个问题需要可信 Role 标签，不能用 Gold SQL、模型伪标签或另一种合成题替代。

## 多锚点候选的近邻与边界

候选方案只改变 G-reasoner 的二值起点数：每题先由 Dense 分别选 Table/Column Top-1 或 Top-3，再在 table-column membership graph 上运行冻结模型。这能检验一个具体输入敏感性问题，但“增加语义锚点后沿 Schema 图传播”本身已有直接近邻：

- [REaR](https://aclanthology.org/2026.acl-long.1826/) 先检索相关表，再依据预计算列向量扩展结构上可连接的表，最后剪除噪声候选。
- [JoinGR](https://arxiv.org/abs/2610.01064) 从语义 anchor 出发，在 join graph 上做 query-conditioned traversal，并学习轻量边评分。
- [Graph-Link](https://proceedings.mlr.press/v306/zhong26s.html) 把 Schema Linking 表述为带连通约束的子图诱导。
- [Rethinking Schema Linking](https://aclanthology.org/2026.findings-eacl.236/) 已研究 table-first 与 column-first 的双向 Schema 检索。

我们的候选与这些工作仍有实现差异：使用冻结的官方 G-reasoner、不训练边评分器，只在 BIRD table-column membership graph 上比较起点 K。但这更适合作为受限的 checkpoint-transfer 诊断，不能当作新的图检索算法；而当前路线明确优先完成 FK mapping Accepted@1 Pilot。因此不在本轮启动它。

上述近邻论文来自正式会议论文集或 arXiv 原文；它们支持“相关机制已有覆盖”的判断，不等于证明不同任务、数据和评价完全相同。

## 三种研究镜头下的候选池

| 研究镜头 | 候选假设 | 处置与理由 |
|---|---|---|
| 边界探测 | Dense Top-1 换成 Top-3 起点，冻结 G-reasoner 能否救回靠后的 Gold 列？ | 暂停。诊断问题清楚，但与当前唯一 GFM Pilot 冲突，且多锚点图检索已有近邻。 |
| 边界探测 | 在更大 Schema、更高干扰率或高跳数条件下，GFM 图传播是否比 Dense 更有用？ | 不启动。BIRD-dev 已多轮使用；JoinGR、REaR、Graph-Link 已覆盖广义结构扩展；本项目高跳数审计已按规则停止。 |
| 结构类比 | 把 FK 当成带完整列端点契约的映射对象，而非普通表间边，能否避免同表对多映射混淆？ | G0 已测试合成 reified mapping 节点，但 Dense 4/4、GFM 2/4；接下来需在人类接受的真实映射上检验，仍受双审标签门控制。 |
| 结构类比 | 从表对两端共同出发，以 mapping node 输出单个候选映射分数是否比表节点分数更可辨识？ | 保留在同一个 Accepted@1 Pilot 内，不另开实验；候选、Query 与映射文本须对所有打分方法一致。 |
| 矛盾反转 | 关系通道分数会变，是否意味着关系选择正确？ | 作为当前 Pilot 的核心问题。G2 的分数敏感与 G0 的排序表现并不等价，必须由 Accepted@1 检验。 |
| 方法迁移 | 用双向检索、joinability 扩展或连通子图修复 Column Recall？ | 不作为新主张。Rethinking Schema Linking、REaR、Graph-Link 已有直接方法覆盖；若要复现，应作为文献基线而非改名新方法。 |
| 下游效用 | 继续调 Values、上下文约束或 SQL 修复来提高 EX？ | 停止。P2c-R、P2d、P2d.3 已显示覆盖增益未转成已确认 SQL 增益；DSR-SQL 和 Post-SQLFix 等也覆盖相邻方法。 |
| 唯一保留的 Pilot | 在双人共识接受集合上，冻结 G-reasoner 是否优于同候选上的 Dense/BM25？ | 等待人工门。人工回复后先检查至少 30 个可裁定问题×表对、20 个可区分映射对、3 个数据库，再决定是否能运行。 |

## 唯一下一步及停止规则

1. 不运行多锚点 Smoke/Full；不实现其运行器，不做 K 扫描或调关系文本。
2. 等待两名真实审阅者分别完成已有 A/B 表单。不得读取表单来推断答案，不通过消息工具联系审阅者，除非用户明确授权。
3. 收到真实回复后，按既有共识规则检查独立完成、映射集合一致、置信度与样本门。若任一门未通过，只归档审阅覆盖和分歧，不启动模型。
4. 若样本门通过，再对冻结模型作一次有界 Accepted@1 Pilot；相同候选和输入对比 G-reasoner、Dense Cosine、BM25 与不看 Query 的结构排序。预设筛选门为 G-reasoner 比最强预先指定基线高至少 5 个百分点、净救回至少 4 个可区分样本，且收益不只来自一个数据库。通过也只成为独立复现候选；失败则停止在当前 BIRD-dev 方法线。
5. 若两份人工回复没有新增，本轮不追加模型、SQL 或 GPU 实验。后续新方向必须证明它改变核心研究结论，并由仓库最新路线单独登记。

## 执行状态审计

- 研究分支 research/gfm-schema-anchor-probe-20261106 当前包含原预注册文件；本次审计时本地 HEAD 与远端分支头均为 2d0a05743cdf2215d0ca6106df1c17a00b655b54。
- 原方案所列运行器 scripts/text2sql/gfm_schema_anchor_probe.py 未纳入 Git；对应报告目录不存在。
- 本地结果索引未发现 gfm_schema_anchor_probe_20261106_01 结果目录。
- 双人 A/B 回复文件仍各为 1,121 字节，时间戳仍为 2026-11-05 20:56:11；此检查只读取文件元数据，没有打开回复内容。
- 本次复核未调用模型 API、未运行本地模型、未使用 GPU、未执行 SQL，未修改既有实验结果。

## 用量

本轮没有模型 API 请求，确认输入/输出/总 token 为 0/0/0，未知请求数为 0，API 费用为 CNY ¥0.00。本地研究与 GitHub 文档核对没有模型推理开销。
