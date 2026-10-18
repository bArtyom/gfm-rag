# P2a 1024-D Cosine / BM25 / RRF 对照预注册（2026-10-18）

> 本文件及执行代码须先提交到 `bArtyom/gfm-rag`，再开始查看 P2a smoke/full 结果。若任何输入、Smoke、S0 对照或资源门失败，停止 P2a 并只归档失败诊断。

## 核心问题与假设

- **问题：** 同一组 BIRD dev 的 Query 与 Schema 候选文本上，BM25 的词法信息是否能为固定 1024-D Cosine 增加列检索信号？
- **核心假设：** 在 2,048-token 无法完整容纳全库 Schema 的预先指定子集上，BM25 或其 RRF 融合相较 S0 提升 Column R@10 或同预算 complete schema 覆盖。
- **实验层：** P2a 主线评分基线；仅含 S0/S1/S2 三组，无新模型、训练、图拓扑、FK/Role、SQL 生成/执行或 Jev。
- **预算：** GPU 0 秒（完全复用本地 P1.6 float32 cache）；CPU ≤1,800 秒、RSS ≤16 GiB、最多 8 CPU 线程；S0/S1/S2 各只完整计算一次，不在 dev 上调参。
- **Smoke：** 固定顺序前 5 题/1 DB，只验证流程、有限值、S0 与 P1.6 一致和输出结构；不计入任何正式指标。Smoke 全部通过后才运行完整 1,534 题。
- **成功判据：** BM25 或 RRF 在 706 个非饱和、可评列问题上的 Column R@10 至少比 S0 高 2.0 个百分点，或同一子集 Complete Schema@2048 至少高 1.0 个百分点；对应差值在 5 个非饱和 DB 中至少 3 个方向为正；全体 Table R@10 相对 S0 下降不超过 1.0 个百分点。所有阈值在运行前冻结。通过只意味着继续做独立 DB 验证，不是泛化或论文结论。
- **停止条件：** 输入/cache/hash 不匹配、Smoke 失败、S0 与已冻结 P1.6 结果不一致、分母不符、资源门超限或输出可能覆盖，立即停止并保留现场。

## 冻结数据与来源

- 项目仓库 `https://github.com/bArtyom/gfm-rag`，从 P1.6 报告 commit `3b3e880244e256e8ae282ee77b017ea4e915b624` 出发；本协议与执行代码的提交 SHA 记录在 run metadata 中，实验启动时要求本地 `main`、`origin/main`、代码树完全一致且 clean。
- P1.6 基线 run：`p1_6_full1534_20261018_01`；其 Full Gate 必须为 PASS，源代码 commit `d948d462f9407a18f4a48c85a76380d54f865cb2`。Smoke 输入/输出与完整摘要见 [`P1.6 报告`](../reports/p1_6_rebaseline_20261018_01/README.md)。
- 数据固定为 BIRD dev 1,534 题/11 DB，873 节点（75 table/798 column），Table 分母 1,534、Column 分母 1,460、Gold columns 6,523；问题、schema、P0 audit、gold labels 的 hash 必须与 P1.6 run manifest 完全相同。
- 模型固定为本地 Qwen3-Embedding-0.6B 1024-D。复用原 run 的私有 query/node float32 cache，不重新编码、不改提示、Schema 文本、候选集合、标签或 token lengths。
- 重点子集固定为 schema token 总量 **大于 2,048** 的 5 DB：共 746 道问题，其中 706 道 column-eligible。它仅用于预注册分层，不用于排除其他题或挑选赢家。

## 方法定义与公平约束

### S0：Dense Cosine

复用 P1.6 原实现：缓存向量转 float32，显式 L2 归一化，精确内积，分数降序；只有完全相等的 float32 分数按 stable node ID 字典序破同分。S0 的 cache hash、score matrix digest、逐题 digest 与 P1.6 必须一致，否则停止。

### S1：BM25

- 查询文本：原始自然语言 question，不含仅供 Embedding 使用的 `Instruct:` 前缀。
- 候选文档：每个节点**完全相同的冻结 `node.text`**，table/column 混合在同一 DB 候选池，不使用标签或 Gold 特征。
- Tokenizer：先 `casefold`；`_` 视为空格；正则 `[A-Za-z0-9]+`；过滤长度为 1 的 token；不做 stemming、stopword removal、query expansion 或字符 n-gram。该规则与 P1.5 词面诊断保持一致；本实验数据为英文 BIRD dev。
- 依赖：环境没有 `rank-bm25`，不安装新包；执行代码直接实现并在报告披露公式。
- 公式：`k1=1.5, b=0.75`；每 DB 的全体 table+column 节点组成 BM25 文档集。令 `df(t)` 为出现 t 的文档数、`N` 为节点数、`dl` 为文档 token 数、`avgdl` 为该 DB 平均文档长度：

  `idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))`

  `score(q,d) = Σ_(t in q) idf(t) × tf(t,d) × (k1+1) / (tf(t,d) + k1 × (1-b+b×dl/avgdl))`

  Query 中重复 token 按出现次数重复计分；OOV token 贡献 0。分数以 float64 排序，同分按 stable node ID。

### S2：Dense + BM25 RRF

- `k0=60`，不调参。
- 对 Top-K 表/列指标，Dense 和 BM25 分别在同一个对应 type 候选集合内全排序后计算 `Σ 1/(60+rank)`；rank 从 1 开始。
- 对 schema-token budget，Dense 和 BM25 分别在同一 DB 的 table+column 全候选集合内全排序后做相同 RRF，再按融合顺序贪心选择完整节点；超预算节点跳过并继续尝试后续节点。完全相同的 RRF float64 分数按 stable node ID。
- S0、S1、S2 使用同一 `node.text`、node 集合、gold labels、K 与 512/1024/2048-token budget；所有节点参与穷举，无 ANN / Top-M 截断。

## 评价与统计

1. 全部 1,460 道可评列问题：Column Recall@5/10/20、Precision@5/10/20、MRR、MAP；同时报告 query macro、DB macro、element micro。Table Recall@5/10 为保护指标。
2. 706 道非饱和子集：同样报告 Column 指标；对 512/1024/2048 budget 报告 Gold-element recall、precision、complete schema、Gold elements/1,000 实际使用 tokens。
3. 所有 1,460 列可评题也完整报告 budget 指标，不以子集替代全体结果。
4. S1/S2 对 S0：逐 DB Column R@10 与 Complete@2048 的 paired delta；按 query 统计 gold-element rescue/damage 数、净命中变化和 complete-schema rescue/damage 数。
5. 不确定性：按 DB 聚类 bootstrap 10,000 次，种子 `20261018`；分别对 11-DB 全体和 5-DB 非饱和层的配对 query-macro 差值报告百分位 95% 区间。DB 数少，区间只作探索性摘要，不宣称独立验证。
6. 公开报告提供匿名聚合、分母、代码/data/cache hash 和资源；逐题记录、Query、Gold SQL、BM25 查询向量、日志、完整 manifest 与 embedding cache 只保留本地。

## 运行与交付

- 执行器：`scripts/text2sql/run_p2a_similarity.py`；在当前 `think2sql_20260909` 环境 CPU-only 执行，不安装或升级依赖、不下载模型、不调用外部 API。
- 输出使用新的唯一路径 `/mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/{smoke_5q_01,full_1534_01}`，启动前确认均不存在；独立日志与 run metadata 记录命令、commit、输入 hash、资源快照、版本、时长与产物 hash。
- Full 成功后将本报告的执行状态及结果写入新的 `docs/research/text2sql/reports/p2a_similarity_20261018_01/`，并更新 Text2SQL 工作台、`/mnt/liansp3/sources.md`。每个公开文件检查无私有题目、Gold、cache、日志或密钥，再提交推送并核验 GitHub 链接。
