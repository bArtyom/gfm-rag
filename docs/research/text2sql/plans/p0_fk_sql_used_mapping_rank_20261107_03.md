# P0：SQL-derived FK mapping 排序独立注册 03

**状态：预注册，未运行。** 本注册为新的实验 ID 与输出目录，承接上一注册的“输入哈希门前停止”这一工程事实，但不重用旧运行 ID、结果目录或样本指纹。上一注册没有解析数据、建立样本、生成审阅包或运行模型。新注册修正已独立核验的 exclusion-manifest SHA，并使用不同的实验 ID 重新确定 Smoke/Full；这是可审计的新注册，不改写旧失败记录。

## 痛点、问题与核心假设

旧 60 个模型审阅问题×表对与配对 SQL 的显式 `JOIN ON` 目标不对齐，不能回答模型是否把 SQL 实际使用的 FK mapping 排在前面。之后的 SQL-used 排序注册又在解析数据前因排除清单的哈希登记值不符而停止，因此目前没有这项主比较的结果。

**研究问题：** 对 BIRD dev 参考 SQL 中明确使用的表对，且该表对具有至少两个不同、有效的 FK mapping 候选时，冻结 G-reasoner 是否比共享相同 embedding 的 Dense cosine 更常把 SQL-used mapping 排在首位？

**核心筛选假设：** G-reasoner 相对 Dense 的 set-valued Mapping@1 至少提高 5 个百分点、净救回至少 4 个问题×表对，并且至少两个各含 `n≥5` 单元的匿名数据库净救回为正。正向筛选仅升级为独立留出评估候选，不构成论文主张。

该目标是“参考 SQL 的显式 `JOIN ON` 实际用了完整 FK mapping”，不是人工语义 Role 真值、唯一合法 JOIN、端到端路径发现、SQL 执行准确率或独立数据集泛化。SQL 和其派生目标不进入模型特征或审阅提示。

## 数据、样本和标签

- 数据：同一冻结 BIRD dev 快照（1,534 题、11 库，已用于开发）；本结果只作 exploratory。
- 目标由 SQLGlot 28.0.0、SQLite 方言的 scope-aware 分析抽取：只纳入同一个显式 `JOIN ON`、同一 alias pair 中完整出现的跨表列等式。复合 FK 必须完整匹配。`WHERE` 与 `USING` 不参与目标标签。若 SQL 中任一 qualified `JOIN ON` 等式无法解析，该题不进入完整分母。
- 候选先从已冻结 canonical FK identity 按端点表对独立构造，不能用 Gold 列对筛选候选。候选至少两个，且 SQL-used 完整 mapping 必须在候选集中，否则记为候选覆盖失败。
- 排除先前 60 单元审阅包中的所有 question keys。每题最多保留一个合格表对，选择规则只依赖本实验 ID、question-key hash 与无序表对 hash。随后按本实验 ID 与 question-key hash 选 5 个 Smoke；Smoke 全部排除在 Full 之外。
- SQL/候选 CPU 门：Smoke 必须 5/5 SQL 解析成功、所有 qualified join 等式完整解析、且 5/5 SQL-used mapping 命中候选全集；排除 Smoke 后 Full 至少 30 个可评分单元、覆盖至少 3 个匿名数据库；全部 Full 单元至少有两个候选和至少一个 SQL-used 候选。任一门失败则停止，不加载模型。

## 模型审阅与排序

用户选择由模型审阅。两名本地 reviewer 对新样本分别盲审所有 mapping 候选，问题、表对和候选列映射可见；Gold SQL、SQL-used target、排名、分数、数据库/题目 ID 和另一 reviewer 输出不可见。Reviewer A 为 Qwen2.5-Coder-7B-Instruct，Reviewer B 为 Qwen3-4B-Think2SQL；各自固定本地快照、贪心解码和已归档输出格式。双方的 decision 与 accepted mapping ID 集合完全一致且置信度均≥2，才计入高置信代理共识。代理标签不代表人工真值。

每位 reviewer 各执行一次 5 题 Smoke；只有各自 5/5 有效且至少 4/5 双方高置信精确一致，才各自运行一次 Full。不补跑、不换题、不修复格式。模型代理只作次要审阅一致性/SQL-used 集合对齐描述；若可区分代理共识少于 20 个或覆盖少于 3 库，不报告代理排序方向。

主排名对比冻结 G-reasoner-34M 与共享 Qwen3-Embedding-0.6B query/mapping vectors 的 Dense cosine。主指标为 set-valued SQL-used Mapping@1；辅以 Mapping@3、首个目标 MRR、配对救回/损坏、候选覆盖和匿名逐库结果。BM25 仅作描述控制，不参与成功门。无训练、微调、参数扫描、SQL 执行或新依赖。

## 版本、资源与运行预算

- 项目仓库：`https://github.com/bArtyom/gfm-rag`，分支 `research/p0-sql-used-proxy-alignment-20261107`。实验前已核对根 README、Text2SQL README、实验路线图、可复现契约和 `/mnt/liansp3/sources.md`。参考上游 `RManLuo/gfm-rag` 固定在 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；不向上游写入。
- 预注册提交：提交到项目分支后记录 GitHub commit；运行器在正式执行时自动从干净 worktree 读取并记录完整 HEAD SHA，不接受手工输入提交号。执行前重新确认分支与 worktree 干净，CPU manifest 与 GPU run 必须使用同一 SHA。
- CPU 环境：复用 `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；显式使用 `/root/miniconda3/envs/think2sql_20260909/bin/python3.12`。每次正式阶段前复核依赖，不安装或升级。
- GFM 环境：复用 `gfmrag_greasoner_20261022`，显式 Python 3.12.15；PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。固定已校验的 G-reasoner-34M 与 Qwen3-Embedding-0.6B 快照，离线加载。
- 资源快照：每个阶段开工前检查 `nvidia-smi`、`free -h`、`nproc` 与磁盘。历史预检为 4×RTX 4090；GPU2 正在使用，其余 GPU0/1/3 空闲；总内存可用约449 GiB、磁盘可用112 TiB。CPU 最多8线程。新注册将 GFM ranker 固定在物理 GPU3（进程内 `cuda:0`），Reviewer A/B 分别固定 GPU0/GPU1、串行执行；启动前必须刷新资源状态。
- 预算：一次 CPU Full 准备（≤8线程、600秒 wall、300秒 CPU、4 GiB RSS）；通过数据门后，每位 reviewer 各一次 5 题 Smoke 和最多一次 Full；一次 GFM 5 题 Smoke 和最多一次 Full。GFM ranker GPU allocation≤8 GiB、RSS≤8 GiB、wall≤1,800秒、CPU≤900秒；Reviewer A/B 显存上限分别≤20/14 GiB、RSS≤24 GiB、每阶段最多1,800秒，串行监控，超过任一预算立即停止。
- 本地模型实际输入/输出 token 按请求计入共享 usage ledger；本地 GPU 秒单独报告。外部 API 为0，费用 CNY 0.00（不表示本地资源没有成本）。
- Smoke/Full 私有样本、SQL-derived 标签、A/B packets/outputs、逐题排名和日志只保存在权限受限的新目录。GitHub 只提交匿名计数、配置和报告，不含问题、SQL、schema 内容、原始模型回答、mapping ID 或私有 ID。

## 输入指纹

| 输入 | SHA-256 |
|---|---|
| BIRD dev `dev.json` | `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` |
| BIRD dev `dev_tables.json` | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| canonical FK artifact | `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060` |
| canonical crosswalk | `7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e` |
| canonical P1.5 Full | `746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed` |
| prior 60-unit exclusion manifest | `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7` |

全部 hash 在读取任何题目或 SQL 内容前重新核验。任何差异立即停止本注册，不修正源文件、不换输入、不启动 reviewer 或 ranker。

## 新运行身份、判据和产物

- Experiment ID：`p0_fk_sql_used_mapping_rank_20261107_03`。
- Run IDs：`p0_fk_sql_used_mapping_rank_20261107_03_cpu_001`、`..._03_review_smoke_001`、`..._03_review_full_001`、`..._03_smoke_001`、`..._03_full_001`。
- 主筛选：G-reasoner−Dense Mapping@1≥+5pp，配对净救回≥4，且至少两个 `n≥5` 匿名数据库净救回>0。未达门则停止该 SQL-used GFM 排序方向，不调参、不重抽样。
- 私有结果：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/`；私有日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/`。
- 项目报告：`docs/research/text2sql/reports/p0_fk_sql_used_mapping_rank_20261107_03/README.md` 及匿名 `aggregate_summary.json`。

**解释边界：** 通过仅代表在重复使用的 BIRD dev 上有继续做独立留出评估的理由；不通过或容量门失败也不证明原始 GFM-RAG 方法无效。模型审阅一致不等于人类一致或真实业务 Role 正确。
