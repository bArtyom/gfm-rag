# G-reasoner 表/列 Schema 检索迁移诊断

**状态：`smoke_001` 和 Amendment 1 的唯一恢复 `smoke_002` 均在模型推理前失败；按停止规则结束，Full 未运行。** 无有效指标，核心假设未检验。详见[Amendment 1](gfm_schema_retrieval_transfer_20261106_amendment1.md)和[运行报告](../reports/gfm_schema_retrieval_transfer_20261106_01/README.md)。实验 ID：`gfm_schema_retrieval_transfer_20261106_01`。这是一次 BIRD-dev 上的探索性 checkpoint-transfer 诊断，不是新算法主张、独立测试、FK Role 准确率或 SQL EX 实验。

## 痛点与研究问题

- P1.6 测得 Dense Column Recall@10 为 68.00%，Table Recall@10 为 99.91%；它没有运行 G-reasoner。
- G-reasoner 在已知表对内的 FK mapping 代理排序为 7/38，Dense 为 27/38。该任务只排序固定表对里的 mapping，不能说明模型在原始表/列检索任务上的表现。
- 旧的[多锚点候选方案](gfm_schema_anchor_probe_20261106.md)曾暂停，且把 P1.6 Query 向量视为可复用输入。后续[指令兼容性审计](p0_gfm_embedding_instruction_compatibility_audit_20261106.md)确认两者 Query 指令不同；P1.6 节点文本还包含 Values，而旧方案声明图中不含 Values。本注册为新 run ID，修正这两项输入不一致，并保留旧暂停记录。

**研究问题：** 在相同 BIRD 问题、相同 Schema 候选、相同 Qwen3 向量与相同 Dense 锚点下，冻结 G-reasoner 沿 table/column membership 图传播，能否找回 Dense 排名靠后的 Gold 列？

**核心假设：** 每题以 Dense Table Top-3 与 Column Top-3 作为 G-reasoner 的二值起点时，G-reasoner Column Recall@10 会高于同向量 Dense Cosine，并高于每类仅一个起点的 G-reasoner 条件；Table Recall@10 不会出现明显下降。

这项问题可能改变本项目对“冻结 G-reasoner 是否能在 Text2SQL 原始 Schema 检索任务上提供增量”的判断。它不重开已停止的 FK mapping 排序，也不把图传播变化表述成准确率提升以外的机制证明。

## 与近期方法的关系

Schema 图扩展和受约束检索已被多项近期工作研究，包括 [REaR](https://aclanthology.org/2026.acl-long.1826/)、[Graph-Link](https://proceedings.mlr.press/v306/zhong26s.html)、[Rethinking Schema Linking](https://aclanthology.org/2026.findings-eacl.236/) 和 [JoinGR](https://arxiv.org/abs/2610.01064)。因此本实验只回答冻结官方 G-reasoner checkpoint 的受限迁移问题，不宣称提出新的 Schema Linking 算法，也不以这次 BIRD-dev 结果支持新颖性或跨库泛化主张。

## 实验层级、预算与停止条件

- 层级：一次 `exploratory` 方法迁移/证伪 Pilot；不训练、不微调、不做超参数搜索。
- 数据固定为 BIRD dev 全部 1,534 题、11 个数据库、873 个节点（75 tables、798 columns）；列指标只在预先冻结的 1,460 个 column-eligible 问题上计算。BIRD dev 已用于项目开发，不作独立测试解释。
- Smoke：按稳定数据库/问题顺序选一个数据库的 5 题，只检查输入隔离、图结构、有限分数、tie-break、资源和输出契约；Smoke 不进入 Full 指标。
- Full：仅当 Smoke 完全通过时，对冻结的 1,534 题运行一次。Smoke 与 Full 不改输入、阈值、prompt、关系文本或模型。
- 资源上限：单张 RTX 4090；8 CPU 线程；进程 RSS ≤8 GiB；GPU 已分配显存 ≤8 GiB；每阶段 CPU ≤900 秒、墙钟 ≤1,200 秒。不启服务、不下载或安装依赖、不调用外部 API。
- 任一输入/模型哈希、指令、节点数、标签分母、图构造或 finite-score 检查失败，或超过资源上限，立即保留现场并停止。Full 后不追加 K、关系文本、边、checkpoint 或 query instruction 变体。

## 冻结输入与防泄漏

- 数据：P1.6 同一 BIRD-dev 问题、`dev_tables.json`、P0 审计和 Gold 派生表/列标签。数据 SHA-256 分别为 question `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`、schema `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`、P0 audit `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`、Gold labels `1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525`。
- Gold 表/列标签只由评测器在得分和排序固定后读取。查询编码、Dense 排名、起点 mask、图节点、边、关系特征和 G-reasoner 前向都不能读取 Gold、SQL、数据库行或执行结果。
- Schema 节点文本固定使用 P2b/P2c-R 已审计的 R1 视图：保留 Table、Column、type、description 和 format，删除 `value_description`。有序文本 SHA-256 为 `73c59126b931fb72b7c09ba06de76327057e32832e2aeef0c8175b8956ed3e3c`；278 个 Values 字段已按历史审计规则移除。不得将 R1 结果与 P1.6 原始 R0 得分直接相减。
- Query 使用 G-reasoner checkpoint 登记的完整指令：`Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: `。Dense、G1 和 G3 共用同一批 Query 与 passage 向量；不复用 P1.6/P2c 的 Query cache。
- 图每个数据库单独构造，节点仅为冻结候选表与列；边仅为双向 table/column membership。关系文本固定为 `Relation: table contains column.`、`Relation: column belongs to table.`，使用 passage 编码。无 FK、Gold、Values、业务角色或问答生成边。
- 模型保持冻结：Qwen3-Embedding-0.6B 1024 维；G-reasoner-34M 原 checkpoint、6 层、参数/配置不变。Qwen3 文件清单采用 P1.6 冻结 manifest，SHA-256 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`；G-reasoner `model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`，`config.json` SHA-256 `75d14b97d6a077ebc17b09a21170a3d9272251db59f7ac8cc853165efb2efd5`。

## 比较条件

| 条件 | 排序/推理 | 起点 |
|---|---|---|
| D0 | Qwen3 Dense cosine，分表和列各自排序 | 不调用 G-reasoner |
| G1 | 冻结 G-reasoner 输出分数，分表和列各自排序 | 同一数据库的 Dense Table Top-1 与 Column Top-1 |
| G3 | 冻结 G-reasoner 输出分数，分表和列各自排序 | 同一数据库的 Dense Table Top-3 与 Column Top-3 |

每个条件使用完全相同的 Query/节点向量、候选集、图与稳定 node-ID tie-break。起点仅由 query text、Schema text、Dense 分数决定。评测器分开计算 table 与 column 排名，不跨类型比较未经校准的 G-reasoner 分数。

## 指标与 Go/No-go

- **唯一主指标：** Column Recall@10（query macro，n=1,460）。
- 预先冻结的迁移信号门须同时满足：
  1. G3 相对 D0 的 Column Recall@10 至少 +2.0 个百分点；
  2. 按数据库聚类的配对 bootstrap 95% CI 下界 >0（10,000 次，seed `20261106`）；
  3. G3 相对 G1 至少 +1.0 个百分点；
  4. G3 Table Recall@10 相对 D0 下降不超过 1.0 个百分点。
- 辅助报告 Table R@5/@10、Column R@5/@10/@20 与 Precision@10、每题/每库 rescue-damage、Dense anchor Gold 命中率、打分有限性及每库方向。11 个数据库簇的区间只作探索性摘要。
- 任一信号门不满足即 `NO_GO`，停止该 checkpoint/输入设定，不补 K=2/4/5，不调整关系文本，不用同一 BIRD dev 继续找最优结构。全部通过只授权另行设计独立数据复现，不等同于 SQL EX、JOIN Role、路径准确率或论文主实验通过。

## 软件、运行与归档

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)；本次分支 `research/gfm-schema-retrieval-transfer-20261106`。官方代码来源 `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0；不修改上游模型或权重。
- 环境复用 `gfmrag_greasoner_20261022`：Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。无依赖安装或升级。
- 每个 Qwen 本地 embedding batch 以唯一 call ID 记入 `/mnt/liansp3/.config/api-usage/usage.sqlite3`；真实输入 token 数按实际 tokenizer 记录，输出 token 为 0。G-reasoner forward 次数、GPU/CPU 时间、显存、RSS 分别记录；本地推理不记为零资源成本。
- 结果运行 ID：`gfm_schema_retrieval_transfer_20261106_smoke_001`、`gfm_schema_retrieval_transfer_20261106_full_001`。私有运行/逐题分数/日志置于唯一的 `sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/` 和 `logs/gfmrag_gfm_schema_retrieval_transfer_20261106_01/`。
- 公开预注册和运行代码必须先推送到本仓库并回读核验，再启动 Smoke。结果报告、匿名聚合与复现配置归档到 `docs/research/text2sql/reports/gfm_schema_retrieval_transfer_20261106_01/`；不上传问题、Gold SQL、逐题预测、节点明细、模型权重或原始日志。
