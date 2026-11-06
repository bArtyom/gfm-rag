# P0 FK Mapping 代理排序负结果归因

**状态：已预注册，待执行。** 这是对冻结 P0 proxy-ranking pilot 的只读错误分析，不是新的模型实验，也不产生真实 Join Role 标签。

## 问题与目的

冻结的 mapping-node G-reasoner 在 38 个模型代理可区分 Full 单元上的 Accepted@1 为 7/38，Dense Cosine 为 27/38。本分析检查两者差距是否集中在候选数、代理接受集合大小、复合 FK 或候选列重叠等已定义结构类型中，以决定是否存在值得另行研究的机制假设。

本分析只对已有结果作描述性分层。不得据此在同一批模型代理标签上调参、挑图结构或声称因果机制；无论结果如何，都不自动重开已判 NO-GO 的排序分支。

## 冻结输入与范围

- 排序输入来自 `p0_fk_mapping_model_proxy_rank_pilot_20261106_01/full_002/private_predictions.jsonl`。
- 候选结构来自原 pair-level 私有 manifest；标签由已封存的 A/B Qwen 与 C Gemma 审阅输出按原高置信精确多数规则重建。
- 仅分析 Full 中 38 个模型代理接受集合严格小于候选集合的单元；5 个 Smoke、13 个可裁定但接受全部候选的单元，以及 4 个不可裁定单元不进入主分母。
- 核验 G-reasoner、Dense Cosine、BM25 Okapi、stable mapping-ID 顺序的冻结排名与原始 pilot 聚合完全一致。
- 不读取 Gold SQL、参考 JOIN、SQL 执行结果；不重新编码、不调用生成模型、不训练、不做 GPU 推理。

先用原排序 Pilot 的 5 个专用 Smoke 单元核验解析和匿名聚合流程；Smoke 只作运行契约检查，不计算研究指标。通过后再对独立 Full 文件做 38 单元分层分析。

## 预设分层与指标

分层变量仅从候选数、匿名代理接受标签和有序 FK identity 计算：

1. 候选 mapping 数：2 与 3。
2. 代理接受集合大小：单个与多个 mapping。
3. 候选中是否含复合 FK（一个 mapping 含多组有序列对）。
4. 不同候选是否共享 source 端列、target 端列、两端列，或没有共享列。

每个分层报告 n、四种方法的 Accepted@1、G-reasoner 相对 Dense 的救回/损坏/净差；另报告两者首个代理接受候选的 rank。候选 score margin 仅作描述，不跨方法比较原始分数尺度。

任何公开分层单元少于 5 个时并入 `small_n`，不公开可反推出 case 或数据库的细分。不给出显著性或因果结论。

## 判定与停止

- 如果性能差距没有在预设结构分层中形成可重复、跨多个匿名数据库的清晰模式，停止该 G-reasoner mapping 方向并进入综合整理。
- 如果出现集中模式，只把它登记为待验证假设；后续实验必须使用新的数据/独立可信标签，并重新预注册。不得在本批 proxy labels 上追加图变体。
- 本分析不改变原 Pilot 的 `NO-GO`、模型 proxy 身份或人工 Role 标签数（仍为 0）。

## 执行与归档

- CPU-only，目标环境沿用 `think2sql_20260909` 的 Python 3.12；上限 4 线程、4 GiB RSS、300 CPU 秒。
- 运行前资源检查已在 2026-11-06 完成：4 张 RTX 4090 空闲，主机可用内存约 451 GiB，192 CPU，数据盘可用 112 TiB。分析本身不申请 GPU。
- 独立运行目录：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_proxy_error_analysis_20261106_01/{smoke_001,full_001}/`；公开仓库只保存无 case ID 的匿名聚合、脚本和解释报告。
- 原始预测、审阅回复、manifest、问题、数据库名、mapping ID、逐题排名/分数与日志均不得进入 GitHub。
- 实际输入文件 SHA、代码 commit、命令、资源、匿名结果与隐私检查记录写入报告；运行完成后检查目标仓库 GitHub 回读内容。
