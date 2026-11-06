# P0：新 SQL-derived 样本上的 FK 映射排序诊断

**状态：预注册。CPU_001 在 exclusion-manifest SHA 门停止；尚未解析问题或 SQL、生成样本或调用模型。** 唯一恢复须依照[Amendment 002](p0_fk_sql_used_mapping_rank_20261107_amendment_002_hash_gate_recovery.md)使用新 run ID `cpu_002`；失败的 `cpu_001` 不重跑。主假设、样本与标签条件不根据数据改动。实验 ID：`p0_fk_sql_used_mapping_rank_20261107_01`。该实验沿着 2026-11-07 身份对齐诊断指出的缺口，另建一批由参考 SQL 显式 `JOIN ... ON` 目标派生的样本；不是重跑旧 60 对。用户随后要求使用模型审阅，补充协议见[Amendment 001](p0_fk_sql_used_mapping_rank_20261107_amendment_001_model_review.md)：两种本地模型标签只作次要代理审阅与描述性评估，不改变主要 SQL-used 标签、主要指标或成功门，也不称为人工共识。

## 痛点、研究问题与因果链

**已核实痛点：** 旧 60 个审阅问题×表对全部没有出现在配对参考 SQL 的显式 `JOIN ON` 等式里。那批数据无法回答“G-reasoner 是否排对 SQL 实际使用的 FK mapping”。与此同时，G-reasoner 在模型代理标签上的排序明显低于 Dense（7/38 对 27/38），不能只因目标错位就推翻这个负结果。

**研究问题：** 对一个参考 SQL 明确连接的表对，当 schema 中存在至少两个不同的有效 FK mapping 候选，冻结 G-reasoner 是否比共享相同向量的 Dense cosine 更常把该 SQL 使用的 mapping 排在第一？

**核心假设（筛选，不是论文主张）：** 在新 SQL-derived、目标 mapping 与完整候选集身份完全对齐的样本上，G-reasoner 的 set-valued SQL-used Mapping@1 至少比 Dense 高 5 个百分点，净救回至少 4 个样本，并在至少两个各有 `n≥5` 样本的数据库上净救回为正。

因果链：`旧样本目标不对齐 → 旧排名不能检验 SQL-used mapping → 用真实 JOIN 对生成新评测单位并冻结原模型评分方法 → 比较 G-reasoner 与 Dense 的 SQL-used Mapping@1 → 若未过筛选门则停止此 GFM 映射排序方向`。

**标签边界：** 目标仅表示参考 SQL 的显式 `JOIN ON` 实际用了该完整、已声明 FK mapping；它不等于唯一业务语义真值，也不评估端到端表/路径发现、SQL EX、人工 Role Accuracy 或跨数据库泛化。SQL 和派生标签不能进入 Query/节点文本、候选排序特征、模型审阅或候选筛选之外的模型输入。

## 备选路线与取舍

| 路线 | 作用与代价 | 决定 |
|---|---|---|
| 在旧 60 对上继续换标签、加模型审阅者或改图 | 重用已证明与显式 SQL target 错位的样本；同一代理标签排序已 NO-GO | 不做，违反停止规则 |
| 继续调 P2d 修复或通用 schema packing | 既有修复未过效用门，且近邻工作已覆盖一般修复和双向 schema 检索 | 不做，不回答 FK 排序痛点 |
| 从已解析 SQL JOIN 对重新构造映射候选排序集 | 绕开旧 pair-target 错位；仍能用同一冻结 GFM 对 Dense 进行成对比较；增加一次 Qwen embedding 与 GFM 本地推理 | **采用**；这是区分“旧评测样本错位”与“GFM 在目标对齐后仍无排序优势”的最小试验 |

此选择是有限测量/迁移诊断，不是新算法。近邻 JoinGR 已把 schema FK join graph 用于 query-conditioned table retrieval；因此本试验不把 GFM、FK mapping nodes 或 join graph retrieval 宣称为新颖。该试验只回答本地冻结 checkpoint 在精确定义的目标上是否值得继续研究。

## 数据、样本和标签冻结

- 数据：本地原版 BIRD dev（1,534 题，11 个库；此前已用于开发），SQLite schema 与冻结 canonical 有效 FK 清单。只允许报告同数据开发诊断，不作独立泛化证据。
- 样本母体：由 SQLGlot scope-aware 解析参考 SQL `JOIN ... ON` 条件得到、且同一表对至少有两个不同有效 FK mapping 候选的 question×unordered-table-pair。目标 mapping 取同一 `JOIN ON`、同一 alias pair 中完整出现的有序列对。支持 SQL 条件左右方向互换。复合 FK 必须全部列对在同一 alias pair 的同一 JOIN 中匹配；部分命中不是目标标签。
- **候选与目标分离：** 候选集合先按冻结的有效 FK identity artifact、端点表对生成，不能按 gold 列对过滤候选；目标 mapping 只用于事后评分。若显式 SQL mapping 不在候选集合中，该单位记为候选覆盖失败，不得计作模型排序错误。
- 完整性：若一个 SQL 内任何限定显式 JOIN-ON 跨表等式无法解析，涉及该 SQL 的单位不进入主排序分母；记录解析覆盖和排除原因。`WHERE`、`USING` 和非显式 join 等式不补作标签。
- 防重复：排除先前 60 个盲审 question×table-pair 包所覆盖的全部 question key（使用既有私有 manifest SHA-256 固定身份）；每道剩余问题最多保留一个合格表对，候选多个时按 `SHA256(experiment_id + question_key_hash + canonical_unordered_table_pair_hash)` 升序取首个。该规则不读取排名或审阅输出。再按 `SHA256(experiment_id + question_key_hash)` 取最小的 5 道问题作为 Smoke，其余进 Full；Smoke 不进入 Full 指标。
- 最低 Full 数据门：排除 Smoke 后至少 30 个完整、候选覆盖的多 mapping 单位，且覆盖至少 3 个匿名数据库。达不到就停止在 CPU 数据准备阶段，不载入模型。

## 方法、对照和评价

- 主比较：同一 Qwen3-Embedding-0.6B 1024D query/mapping vectors、同一 query instruction、同一 mapping 文本和同一候选集合下，冻结 G-reasoner-34M 对 Dense cosine。G-reasoner 输入是两个端点共享的 binary seed 和每个候选一个 reified mapping node，沿用已归档 G0 结构；不训练、不微调、不改消息传递或 checkpoint。
- 次级控制：固定文本上的 BM25 与稳定 mapping-ID 顺序，只作描述性参照，不参与成功门。
- 主指标：set-valued SQL-used Mapping@1；当 Top-1 落在 SQL 明确使用的任一有效完整 mapping 集合中时计命中。报告 G-reasoner、Dense、paired rescue/damage 和每个匿名数据库结果。
- 次级指标：Mapping@3、首个 SQL-used mapping 的 MRR、候选覆盖率、排除原因、映射候选数分层、并列数和资源成本。因只有 4 个数据库有多 mapping 候选，不做跨库置信区间或跨库显著性声称；可按 question 做探索性配对 bootstrap，但不据此追加实验。
- 成功筛选门：G-reasoner − Dense Mapping@1 `≥+5pp`、净救回 `≥4`，并且至少两个 `n≥5` 的匿名数据库净救回方向为正。满足只升级为独立留出评估候选；不自动启动下一轮。任何门失败则按负向或证据不足停止，不调参、不换 seed、不补样。

## 运行预算、停止条件与复现

- 预算：一次 CPU-only 全量 SQL/候选解析；通过容量门后，一次 5 单位 G-reasoner GPU Smoke，再通过后一次 Full（全部剩余合格单位）。无重试、无 SQL 执行、无新依赖安装或数据下载。双本地模型次要审阅严格按 Amendment 001 的额外 Smoke/Full 预算执行。
- 资源：指定物理 GPU2（本次预检空闲 RTX 4090）；峰值 CUDA allocation `≤8 GiB`，RSS `≤8 GiB`，wall `≤1,800s`，进程 CPU `≤900s`；CPU 解析最多 8 线程。每次 GPU 启动前重新记录 `nvidia-smi`、`free -h`、`nproc`、磁盘余量和环境版本。若 GPU2 不空闲，本次停止，不挪用正在运行任务、不临时换卡或重试。
- 环境：复用 `gfmrag_greasoner_20261022`，指定 `/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12`，Python 3.12.15、Torch 2.8.0、PyG 2.6.1、Transformers 4.56.1、sentence-transformers 5.1.1；模型本地离线加载。不升级环境、不自动转外部 API。
- 固定模型：G-reasoner revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`，`model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`，checkpoint config SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`；Qwen3-Embedding-0.6B weights SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`。使用 checkpoint 注册的 Query instruction：`Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: `；Dense 与 G-reasoner 共享向量。
- 本地 Qwen 输入 token 按 tokenizer 实数计并逐批写入共享 usage ledger，embedding 输出 token 记 0；G-reasoner 图前向次数/耗时、GPU 时间单列。外部 API 请求与费用应为 0（CNY 0.00）；这不表示本地 GPU 资源免费。
- 私有逐题文件只写入权限 0700 的结果目录，文件 0600；GitHub 只归档匿名聚合。不得上传 SQL、问题/数据库/表列名、mapping ID、逐题分数/排名、模型审阅原文或私有 manifests。
- 完成验证：独立核验输入 hash、样本/Smoke/Full 不重叠、匿名聚合计数与私有逐题结果一致、成功门复算、公共报告和聚合已推送并逐 blob 从 GitHub 读回一致。实验文件目录：`docs/research/text2sql/reports/p0_fk_sql_used_mapping_rank_20261107_01/`。

### 冻结输入指纹

| 输入 | SHA-256 |
|---|---|
| BIRD dev `dev.json` | `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` |
| BIRD dev `dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| canonical FK artifact | `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060` |
| canonical crosswalk | `7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e` |
| canonical P1.5 Full | `746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed` |
| old 60-unit exclusion manifest | `14d3e65e53bbc29c03d312fb32227c47b568242502d30bc3c4d4656b97521ed7` |

## Pre-registered artifacts and run IDs

- Owned project repository: `https://github.com/bArtyom/gfm-rag`; branch `research/p0-sql-used-proxy-alignment-20261107`; registration parent commit `50aa99c64bf0148ddb7f93ec2f1467cd237f6e61`.
- Plan: `docs/research/text2sql/plans/p0_fk_sql_used_mapping_rank_20261107.md`.
- Config: `configs/text2sql/p0_fk_sql_used_mapping_rank_20261107.json`.
- Runner will be committed and its SHA-256/commit added to the report before any private SQL-derived sample is read.
- Run IDs: `p0_fk_sql_used_mapping_rank_20261107_cpu_001`, `p0_fk_sql_used_mapping_rank_20261107_smoke_001`, `p0_fk_sql_used_mapping_rank_20261107_full_001`.
- Local results: `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/`; logs: `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/`.

## Nearest work and interpretation

| Work | Relation to this diagnostic | Difference / boundary |
|---|---|---|
| [G-reasoner (ICLR 2026)](https://openreview.net/pdf?id=zJm9nmoahk) | Frozen graph-reasoning checkpoint being transferred | Original work evaluates graph-structured retrieval/reasoning, not this conditional BIRD SQL-used FK mapping ranking task |
| [JoinGR (2026 preprint)](https://arxiv.org/abs/2610.01064) | Closest Text2SQL join-graph retrieval work | Learns query-conditioned graph traversal for table retrieval; this run neither reproduces nor competes with JoinGR, and introduces no new traversal method |
| [Rethinking Schema Linking (Findings EACL 2026)](https://aclanthology.org/2026.findings-eacl.236/) | Nearby schema retrieval work | Bidirectional table/column retrieval and question-side augmentation, not FK mapping identity ranking |
| [MDB-Link (2026 preprint)](https://arxiv.org/abs/2608.09588) | Nearby schema retrieval work | Multi-database localization and budgeted schema construction; not this within-known-table-pair mapping diagnostic |

Novelty status: `not_claimed`; scientific role: corrected, bounded evaluation of whether the existing checkpoint retains a signal on a better-aligned target. A positive result remains same-BIRD-dev exploratory evidence and requires a genuinely independent held-out evaluation before any method claim.

## Result

Pending. No sample rows, SQL labels, candidate rankings, model outputs, or per-case metrics were read or produced when this plan was registered.
