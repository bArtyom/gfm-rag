# G3：真实 FK mapping 图的起点敏感性诊断

**状态：预注册，待实现与执行。日期：2026-11-06。**

## 研究问题

P0 冻结 G-reasoner 在模型代理可区分样本上明显落后于 Dense。当前适配把一对表的两个端点都设为 query seeds。G2 已证明关系输入能改变一个合成非对称图的原始分数，但没有证明这种关系信号能改变真实候选 mapping 的相对排序。

本诊断只回答：在固定的 BIRD FK mapping 候选图上，把两个表都设为起点、或分别只设其中一端，是否会实质改变候选 mapping 的相对排序？

## 假设、实验层级与边界

- **核心假设：** 双端 seed 与单端 seed 会对候选 mapping 排序产生实质影响。若排序几乎不变，则“双端 seed 抹平候选差异”不再是值得继续追的解释；若排序改变，只能说明起点选择影响分数，不能说明哪个排序正确。
- **层级：** 一次有限的机制诊断，属于 exploratory。它不评估 Role Accuracy、Accepted@1、SQL EX，也不训练或修改 G-reasoner。
- **与既有 NO-GO 的关系：** P0 排序 NO-GO 禁止继续在同一模型代理标签上调分数或挑图结构。本实验完全不读取人工或模型审阅回复、accepted mapping 集合、Gold SQL 或排名标签；唯一主要结果是无标签的排序敏感度。它是对 P0 报告中“双端 seed 可能削弱候选差异”这一未验证解释的机制核查，不是性能补救或新方法主张。该边界是本轮相对旧路线的明确偏离。
- **输入边界：** 沿用已冻结的 60 单元盲审 packet 和对应私有映射清单；问题×表对源自已知参考 JOIN，因此只测“已知端点表对条件下”的候选区分。5 个既有 Smoke 问题继续排除于 Full。

## 冻结条件

| 条件 | 起点掩码 |
|---|---|
| A0 | 两个端点表均为 seed，复现 P0 基线 |
| A1 | 只把按稳定字典序排列的第一个端点表设为 seed |
| A2 | 只把第二个端点表设为 seed |

除 seed mask 外，三个条件共用同一问题向量、表和 mapping 文本向量、1024 维 Qwen3 embedding、FK mapping 节点、四类有向边、关系向量、G-reasoner-34M checkpoint、参数与排序 tie-break。A1/A2 的锚点按表名稳定排序，不按参考 SQL 的 source/target 方向选择，也不查看问题答案。重复 A0 一次用于估计确定性噪声。

**禁止读取：** A/B/C 审阅回复、任何 reviewer 输出、模型共识标签、Gold SQL、执行结果。不得根据任何条件挑选后续配置。

## 样本、指标与判据

- Smoke：冻结 split 中 5 个问题×表对；只验证输入、三种 mask、有限分数与输出结构。Smoke 不进入 Full。
- Full：余下 55 个问题×表对、123 个候选 mapping；所有具有至少两个候选的表对参与相对排序分析，单候选项只报告数量。
- 主要指标：A0 对 A1/A2 的候选 Top-1 变化比例，以及所有候选对的相对顺序反转比例。辅助指标：每个条件的分数范围、并列数和 A0 重复的最大分数误差。
- **机制敏感性信号：** 至少一个单端 seed 条件在不低于 20% 的多候选表对上改变 Top-1，且其候选对顺序反转率不低于 10%。
- **无实质排序影响：** A1 与 A2 的 Top-1 变化率均不高于 5%，且候选对顺序反转率均不高于 5%。
- 其余结果为 inconclusive。上述阈值是本轮预先设定的实用敏感度界限，不是显著性检验或角色准确率门。

无论机制判据如何，结果都不能说明某个 seed 条件更准确。出现敏感性信号后停止；之后若要评估准确率，仍需独立可信标签。

## 资源、运行与停止

- 运行前检查 GPU、内存、CPU、磁盘、checkpoint/config、Qwen snapshot、数据 hash 与 conda 环境。
- 环境沿用 gfmrag_greasoner_20261022；仅使用一张空闲 RTX 4090；离线加载本地模型；不安装依赖、不下载权重、不调用外部 API、不执行 SQL。
- 单轮预算：GPU allocated ≤8 GiB、RSS ≤8 GiB、CPU ≤900 秒、wall ≤1,200 秒；最多 5 个 Smoke 图及 55 个 Full 图各运行 A0/A1/A2，另对 A0 重复一次。
- 每个 run 使用独立 ID、目录和日志。Smoke 未通过、hash/版本不符、非有限分数、资源超限或输出含私有字段时停止；不在同一 run 目录重试。
- Full 完成后按机制判据判定，并停止本支线，不再追加 seed、图结构或模型扫描。

## 代码与归档

- 项目仓库：bArtyom/gfm-rag。
- 起始项目 commit：b7d64ecde544e5bfcb20d311a0316b6d8bebeff5；上游 GFM-RAG 源码和 checkpoint 保持只读。
- 计划配置：configs/text2sql/g3_fk_seed_direction_sensitivity_20261106.yaml。
- 独立 runner：scripts/text2sql/run_g3_fk_seed_direction_sensitivity.py。
- 结果报告：docs/research/text2sql/reports/g3_fk_seed_direction_sensitivity_20261106_01/。
- 私有逐题分数、输入清单和日志只保留在本机受限结果目录；GitHub 只提交匿名聚合、计划、配置和复现代码。

## 主要局限

该实验对照的是起点初始化造成的相对排序变化，不含正确答案。BIRD dev 已被反复用于开发；表对由参考 JOIN 派生，不能据此宣称端到端检索或泛化能力。即使排序发生变化，也需要可信标签才能判定变化是否有益。
