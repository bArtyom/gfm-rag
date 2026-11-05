# GFM 真实 Schema 多锚点迁移诊断

**状态：预注册协议；尚未运行 Smoke 或 Full。** 本轮只检验冻结的 G-reasoner 在 BIRD 表/列 Schema 图上的排序迁移，不评估 FK 角色、JOIN 路径、SQL 生成或跨库泛化。

## 为什么开这一项

已有 BIRD 检索结果显示 Column Recall@10 为 68.00%，而 Table Recall@10 接近饱和（99.91%）。P1/P2 测的是 Qwen embedding 与评分，不是 G-reasoner 在真实 Schema 上的检索效果。G0-02 只测了 4 条合成 FK 映射题，结果 G-reasoner 2/4、Dense 4/4；G2 只证明非对称合成图上分数会响应关系输入。它们均未回答真实表列检索中的图传播是否有用。

源码中的默认 GFM-RAG 输入由 NER/EL 产生二值 `start_nodes_mask`；当前 EL 对每个 mention 使用 `topk=1`。多锚点是一个可检验的输入假设。相近工作已覆盖图式 Schema Linking、Join-aware 检索和层级结构推理，因此本实验不是新算法主张，而是决定是否继续投入冻结 G-reasoner 的真实 Schema 迁移诊断。若不优于强 Dense 基线，则停止在 BIRD 上追加 GFM 表列检索改动；若有信号，也只进入独立数据复现设计，不升级成 SQL 或 FK 角色结论。

## 实验契约

- **核心假设：** 对同一问题、同一 Schema 候选及相同 Qwen3 特征，给冻结 G-reasoner 每类节点 3 个 Dense 锚点，比每类 1 个锚点能提升 Column Recall@10；提升应同时优于 Dense 排名，且不明显损害 Table Recall@10。
- **机制链：** 更多高相关表/列作为 GFM 边界种子 → G-reasoner 经 `has_column` / `belongs_to_table` 关系传播 Query 状态 → 找回初始 Dense 排名靠后的所需列。
- **可证伪预测：** 若 GFM-Top3 未达到下述效用门，或提升只出现在一个数据库、或 Table Recall 明显下降，则多锚点迁移不作为后续 GFM 方向。
- **层级：** 一次 exploratory 可行性/迁移 Pilot；无训练、无超参搜索，不作为确认性主实验。
- **主线意义：** 结果可能决定 GFM 是否有真实 Schema 表列检索信号，还是当前投资应停止在传统 Dense 检索和待审 FK 映射诊断。

## 数据与信息边界

- 数据：已有本地 BIRD dev，1,534 题、11 个数据库；表指标分母 1,534，列指标分母 1,460。74 题无完整列标签，保留为不可评列题，不从分母静默删除。
- BIRD dev 已多次用于开发，所有结果明确标记为 exploratory；不能表述成独立测试或跨数据库泛化。
- 节点及 Query 文本、1024 维 Qwen3 特征沿用 P1.6 冻结输入/缓存与哈希。只将 SQL 解析得到的表列 Gold 放入离线评价器。
- 每个 DB 独立构造 `table`、`column` 节点及双向 `has_column` / `belongs_to_table` 边。**不输入 FK、Gold SQL、Gold JOIN、数据库行、Values、业务角色说明或任何由 Gold 推出的图边。** 两条 FK 的身份冲突因此不进入本实验。
- 关系文本固定为 `Relation: table contains column.` 与 `Relation: column belongs to table.`，由本地 Qwen3-Embedding 以 passage 模式编码。关系文本不得根据结果修改。

## 比较条件

候选、Query/节点/关系向量和模型权重完全相同；只改变 GFM 的起始锚点个数。

| 条件 | 排序方式 | `start_nodes_mask` |
|---|---|---|
| D0 | Qwen3 Dense cosine | 不运行 GFM；记录原始稠密排名 |
| G1 | 冻结 G-reasoner | 同 DB 的 Dense Table Top-1 与 Column Top-1，各一个二值锚点 |
| G3 | 冻结 G-reasoner | 同 DB 的 Dense Table Top-3 与 Column Top-3，各三个二值锚点；不足 K 时取全集 |

Top-K 种子通过稳定 node ID 破同分。每个问题的 Dense Top-K 候选只用问题、Schema 文本和 Dense 分数确定，Gold 信息不会影响候选或 mask。G1/G3 对每个问题使用完全相同的 Query 和图；G-reasoner 的参数、checkpoint、层数、关系向量及精度均冻结。

## 指标与决策门

- **唯一主指标：** Column Recall@10（query macro，n=1,460）。主比较为 G3−D0；G3−G1 用于判断锚点数机制是否带来额外改善。
- **护栏：** Table Recall@10 相对 D0 不得下降超过 1.0 个百分点。
- **辅助指标：** Table Recall@5/@10、Column Recall@5/@10/@20、按数据库的配对救回/损坏、起始锚点命中 Gold 比例、每个 DB 的 G1/G3/D0 方向。
- 以数据库为簇做 10,000 次配对 bootstrap，seed=`20261106`。11 个簇下区间只作探索性不确定性摘要，不解释为稳健跨域显著性。
- **迁移信号门：** G3 的 Column R@10 相对 D0 至少 +2.0pp，数据库簇 95% CI 下界 >0；相对 G1 至少 +1.0pp；Table R@10 满足上述 −1.0pp 护栏。三项同时满足才保留为独立复现候选。
- 任一条件失败，则 `NO_GO`，停止此多锚点方向；不扫描 K=2/4/5、不调文本或 checkpoint、不换 BIRD 样本。
- 该门通过也不表示 GFM 优于所有 Schema Linking 方法，更不说明 SQL EX、FK Role 或 JOIN Path 准确率改善。

## 执行与停止条件

1. 先核对运行仓库 commit、P1.6 输入/缓存 manifest、Qwen 与 G-reasoner 权重 hash、环境版本及新资源状态。
2. 新建私有结果和日志目录；选择一张空闲 RTX 4090，不使用已被其他作业占用的 GPU。预算上限：单卡、CPU 8 线程、RSS 8 GiB、墙钟 20 分钟；不启动模型服务。
3. 先以固定 hash 顺序的 5 题 Smoke 运行 D0/G1/G3；验证输入形状、finite scores、可复现 tie-break、图边和节点映射。Smoke 不进入主指标。若任一门失败，保留现场并停止，不启动 Full。
4. Smoke 通过后，在同一提交、同一输入及同一缓存上运行一次 1,534 题 Full；GFM 前向分批处理，每题各跑 G1 与 G3。无重试、无参数修改、无增量扩样。
5. 记录真实本地 Query/节点/关系编码输入 token 数、GPU 时间、CPU 时间、峰值 RSS、checkpoint hash、代码 commit、命令、数据 manifest、异常与结果文件 hash。无外部模型/API 请求；本地 GPU 时间作为资源消耗单列。

## 代码与报告产物

- 运行器：`scripts/text2sql/gfm_schema_anchor_probe.py`。
- 预注册：本文件；预注册 commit 必须先推送并完成远端回读后，才能启动模型前向。
- 报告：`docs/research/text2sql/reports/gfm_schema_anchor_probe_20261106_01/README.md`，附匿名聚合、配置、Smoke/Full 回执及代码/输入 hash。
- 私有题目、Gold SQL、逐题排名、图节点明细、日志和原始缓存留在 `/mnt/liansp3/sources/results/` 与 `/mnt/liansp3/logs/`，不提交 GitHub。
- 源码基线：用户仓库 `bArtyom/gfm-rag` 当前研究分支 `research/gfm-schema-anchor-probe-20261106`，预注册前 HEAD `c046ee1e314502b507104ede019aaadc46b378cf`；官方运行实现来源沿用仓库冻结的 GFM-RAG commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0。原方法不修改；新增 runner 作为独立实验实现。

## 主要风险

- Checkpoint 训练时的二值文档/实体种子分布与 BIRD Schema 图不同；负结果只能否定当前零微调迁移设定。
- 表列标签来自开发集 Gold SQL 且反复被本项目使用，容易过度代表熟悉数据；任何正结果都需要新数据库/新 benchmark 复现。
- 多锚点扩散可能使相关表下的同义/无关列一起升分；必须同时看 Column precision/救回与损坏，不将召回单项改善写成 SQL 价值。
- GFM 输出在 Table 与 Column 间可能未校准，因此主指标按列内排序计算；不在本试验中混合两类型分数做 token-budget SQL 结论。
