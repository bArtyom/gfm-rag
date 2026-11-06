# P0 FK mapping 双本地模型审阅代理实验

**状态：Full 完成；模型代理标签数量门未通过，停止后续排序。** 实验 ID：`p0_fk_mapping_model_review_proxy_20261106_01`。本计划是用户明确选择模型审阅后新增的独立探索轨道，不修改原双人盲审方案、CSV 或其“可信人工标签为 0”的结论。

## 研究问题与假设

**问题：** 两个独立运行的本地模型，能否在固定 BIRD 问题×表对与全部已声明 FK mapping 上，产出足够一致且可区分的接受集合？

**核心假设：** 若两个模型对接受集合与决定类型给出完全一致的答案，并各自给出至少中等置信度，则这 60 个单元中会有足够的“模型共识代理标签”支持一次仅供探索的后续排序诊断。此结果只反映两模型一致性，不能证明标签正确、不能代替两位人工审阅者，也不能解除论文主实验的人类标签门。

## 所属层级、预算和成功 / 停止条件

- 层级：主实验前的 `exploratory` 模型标注可行性门；不是 G-reasoner 主方法实验。
- 数据预算：同一冻结盲审 Full 包的 60 个问题×表对、135 个完整 mapping 候选、4 个匿名数据库。先跑 5 单元 Smoke，Smoke 通过后单独重跑 60 单元 Full；Smoke 不计入 Full 指标。
- 模型预算：两种本地模型各 5 次 Smoke 请求和 60 次 Full 请求；不联网、不使用付费 API、不自动重试格式错误。
- 主指标：Full 上两模型决定类型与接受 mapping ID 集合的精确一致率；通过冻结置信度规则的模型共识可裁定数、其中至少拒绝一个候选的可区分数及匿名数据库覆盖数。
- 探索性后续门：只有 Full 中至少 30 个精确共识、双模型置信度均≥2的可裁定单元，其中至少 20 个接受集合未覆盖全部候选，且覆盖至少 3 个匿名数据库，才可另行启动**独立登记**的模型代理标签排序实验。此门只决定能否做诊断，不赋予模型标签金标准地位。
- 最终 Smoke 停止：输入解析或候选 ID 校验失败、任一模型无法本地加载、5 个案例中通过 JSON 与语义校验的输出少于 4 个/每模型、或出现数据串行/提示泄漏时，停止 Full，保留现场并报告。只允许下方登记的一次范围有限的提示澄清；若修订 Smoke 仍未达门槛，不再改提示或替换模型。
- Full 停止：环境/模型异常连续失败、可用显存低于安全边界、运行超出每模型 90 分钟、输出覆盖风险或任一输入 hash 改变时停止；不换模型、不改提示、不追加样本。

## 冻结输入与盲法

- 输入只来自本地私有审阅包 `sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_{A,B}_packet.md`。A、B 的案例与候选显示顺序各自冻结；Reviewer A 用模型一，Reviewer B 用模型二。两个进程互不读取对方输出。
- 表对由参考 SQL 的 JOIN 派生；模型不见 SQL，但该设置只评价已知表对条件下的 mapping 审阅，不是端到端 Gold-free 任务。
- 两模型只见自然语言问题、表对名称和完整 FK mapping 表达式及匿名 mapping ID；不提供 Gold SQL、参考 JOIN/ON、数据库 ID、模型排名或原方法结果。
- 提示要求逐个 mapping 判定、允许多映射接受集、返回决定类别/ID 集/自评置信度/理由码的 JSON。温度关闭，单案例独立上下文，每案例单次请求；无输出重试、无人工修订。
- Smoke 使用 Full A 包前 5 个冻结案例，并在 Smoke 与 Full 中分目录重跑。两次运行各自计入本地 token 用量；Smoke 输出不混入 Full 统计。

## 模型、实现和资源

| 角色 | 本地模型 | 模型入口 | 环境 / GPU |
|---|---|---|---|
| A | Qwen2.5-Coder-7B-Instruct | `sources/models/qwen25-coder-7b` | `think2sql_20260909`，物理 GPU 1 |
| B | Qwen3-4B-Think2SQL | `sources/models/qwen3-4b-think2sql` | `think2sql_20260909`，物理 GPU 2 |

预检时 GPU 1 与 GPU 2 各有约 24 GiB 空闲显存；GPU 0 与 3 有其他进程占用，不使用。RAM 可用约 446 GiB，CPU 192 核。模型文件已在本地，不下载权重、不安装或升级依赖。执行前后记录 torch 峰值显存、进程耗时与 GPU 状态；不声称本地推理没有资源成本。

代码：`scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py`。Torch/Transformers 版本取运行环境已安装版本；`local_files_only=True` 禁止从外网取模型。每次生成请求在私有共享用量账本中记录模型名、run ID、输入/输出 token；本地 GPU 时间单独报告，不折算 API 费用。

## 分析与解释边界

1. JSON 必须通过决定、理由码、mapping ID 子集和集合基数校验，否则计为无效；不重试。
2. 两模型仅当决定类型与接受 ID 集合完全相同，且双方置信度都≥2，才形成模型共识标签。精确一致率的分母同时报告双方均有效的单元；无效输出另报。
3. 排序后续门只接受 `single_mapping` 或 `multiple_mappings` 的非空共识接受集，且集合不等于全部候选。`cannot_determine`、`no_declared_fk`、`other` 不进入排序可裁定集。
4. 即使满足数目门，也只能称为**模型共识代理标签上的探索性结果**。模型共享 Qwen 家族偏差，且 Qwen3-4B 为 Think2SQL 微调模型；模型间一致既非独立人工共识，也不是准确率证据。
5. 所有逐题问题、候选身份、原始模型输出、CSV、清单及日志留在本地私有目录。GitHub 只公开代码、协议、匿名汇总和可复现资源说明。

## 依据与偏离

本实验沿用项目 [`README`](../README.md)、[`experiment-roadmap`](../experiment-roadmap.md) 与 [`reproducibility-contract`](../reproducibility-contract.md) 对私有输入、独立 run ID、Smoke、匿名公开汇总和结果报告的要求。它**有意偏离**原计划“必须有两位真实审阅者后才能启动 GFM Accepted@1 Pilot”的门控：用户选择模型代审，因此本轮只进行模型审阅并产出单独的模型代理标签；人工金标准门与原 Pilot 定义维持不变。若启动任何模型代理标签上的 G-reasoner 排序，必须另建实验 ID、计划和报告，不与本轮合并。

## 结果归档

- 私有输入：`sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/`。
- 新私有输出根：`sources/results/gfmrag_p0_fk_mapping_model_review_proxy_20261106_01/`；运行日志位于 `logs/gfmrag_p0_fk_mapping_model_review_proxy_20261106_01/`。
- 公开报告：`docs/research/text2sql/reports/p0_fk_mapping_model_review_proxy_20261106_01/README.md` 与匿名 `aggregate_summary.json`。
- 源数据、模型文本输出、逐题标签和 Gold 相关内容不得提交。

## 执行时修订 A1（2026-11-06；发生在任何 Full 运行之前）

原始 `smoke_001` 中 Qwen2.5-Coder 为 5/5 通过；Qwen3-4B 有 2/5 个输出选择 `no_declared_fk`，但这些审阅单元均展示了至少两个已声明 mapping，故按既定语义校验拒收，只有 3/5 通过。Full 未启动，Smoke 输出不作为标签使用。

修订原因是提示没有明确声明当前 60 个冻结单元均为非空 FK 候选集。A1 仅补充一句约束：本包每个单元都列出至少两个 mapping，因此 `no_declared_fk` 不适用。模型、样本、候选次序、决策规则、置信度门、采样设置均不变。修订 Smoke 使用新 run ID `p0_fk_mapping_model_review_proxy_20261106_smoke_002`，仍只跑原冻结的 5 个 Smoke 单元；不读取旧 A/B 回复，不复用 `smoke_001` 输出。通过后才可跑独立 Full；Smoke_002 是最后一次提示调整。

Smoke_002 已通过：两模型各 5/5 输出均通过 JSON 与候选语义校验。Full 使用相同 A1 提示、完整冻结的 60 个单元与独立 `full_001` 输出目录；不混用 Smoke 标签。

## Full_001 执行后结果

- Qwen2.5-Coder-7B-Instruct 有效 59/60；Qwen3-4B-Think2SQL 有效 58/60。双方均有效 57 个单元，其中决定与接受集合精确一致 28 个；28 个均达到双方置信度≥2。
- 28 个模型共识单元可裁定；23 个至少拒绝一个 mapping，覆盖 4 个匿名数据库。预注册排序先决门要求≥30 个可裁定、≥20 个可区分、≥3 库。本次 23/20 与 4/3 两项通过，28/30 可裁定数量门失败。
- 预注册结论：`STOP_INSUFFICIENT_MODEL_PROXY_LABELS`。不运行 G-reasoner/Dense 排序、不补样、不再调整提示。该门仅针对模型代理标签的独立探索路线，原真人双审门仍未满足。
- Full 资源和 token 统计见[完整报告](../reports/p0_fk_mapping_model_review_proxy_20261106_01/README.md)及匿名[聚合结果](../reports/p0_fk_mapping_model_review_proxy_20261106_01/aggregate_summary.json)。
