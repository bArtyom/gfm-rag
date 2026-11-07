# P0：SQL-used FK mapping ranker — Amendment 002 GPU execution

**状态：`FULL_COMPLETE / POSITIVE_SCREEN_FAIL`。** Smoke 5/5、Full 108/108 均完成。冻结 G-reasoner 的 SQL-used Mapping@1 为 43/108（39.81%），共享向量 Dense cosine 为 63/108（58.33%），相差 **−18.52 个百分点**。配对净救回为 −20，4 个匿名数据库中只有 1 个净救回为正；预注册的正向筛选未通过。此结果是重复使用 BIRD-dev 上的 exploratory 排序比较，不是语义 Role 真值或跨库泛化结论。

## 研究问题、假设和实验层级

痛点是先前 60 个模型审阅问题×表对与同一问题的参考 SQL 显式 `JOIN ON` 不对齐，无法衡量 SQL 实际使用的 mapping 是否排在前面。本实验冻结 SQLGlot 派生的 SQL-used FK mapping 为标签，检验同一 embedding 向量下 G-reasoner 是否比 Dense cosine 更好地把该 mapping 排在首位。

**核心假设与判据：** G-reasoner 的 set-valued Mapping@1 相对 Dense 至少提升 5pp、配对净救回至少 4 个单元，并且至少 2 个各有 `n≥5` 单元的匿名数据库净救回为正。Full 未通过；该分支不继续同一 BIRD-dev 数据上的调参、图变体或模型代理扩展。

该标签只表示参考 SQL 显式 JOIN 实际使用的完整 FK mapping。它不等同于业务语义 Role、唯一合法 JOIN、端到端 JOIN 发现或 SQL 执行准确率。SQL 和 SQL-derived 标签只用于 CPU 标签构造及最终离线评估，不进入模型输入。用户选择的 Qwen A/B 审阅是次要模型代理；它们的高置信精确一致为 2/5，低于审阅 Full 门槛，人工 Role 真值仍为 0。主排序不依赖审阅标签。

## 仓库、指导、版本和代码改动

- 用户维护仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 本次执行代码 commit：[`7801d46206a0aeeaaacad05f80e71961297ee475`](https://github.com/bArtyom/gfm-rag/commit/7801d46206a0aeeaaacad05f80e71961297ee475)。
- 官方上游：[RManLuo/gfm-rag](https://github.com/RManLuo/gfm-rag)，固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`。报告和结果仅归档到用户维护仓库。
- 执行前检查了仓库根 README、Text2SQL README、`experiment-roadmap.md`、`reproducibility-contract.md` 和 `/mnt/liansp3/sources.md`。
- [基础预注册](../../plans/p0_fk_sql_used_mapping_rank_20261107_03.md)；[Amendment 002](../../plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.md)；[冻结配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.json)。
- Amendment 002 修复 manifest 计数契约：缺少重复的 `*_unit_count` 字段时，以冻结 ID 数组长度校验 5/108 数量并拒绝重复 ID。除此之外不改数据、候选、SQL 标签、模型、评分、seed、阈值或停止规则；GFM 排序和 Dense 评分算法没有改变。

## 数据、模型和运行配置

- 数据：冻结 BIRD dev（1,534 题、11 库）。完整 Full 为 108 个问题×表对，覆盖 4 个匿名数据库，共评分 328 个 FK mapping 候选。
- 目标抽取：SQLGlot 28.0.0、SQLite 方言、scope-aware JOIN 等式解析；只把同一显式 `JOIN ON` / alias pair 中完整出现的 mapping 作为目标，复合 FK 要完整匹配。`WHERE` 和 `USING` 不属于本标签。
- 数据与清单指纹：`dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；准备清单 SHA-256 `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0`，来源提交 `566b8e2d9bb244d8868372ae39c887de02f703e9`。
- 其他冻结输入 hash：canonical FK `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`；crosswalk `7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e`；canonical P1.5 Full `746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed`；排除清单 `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`。
- 模型：G-reasoner-34M，34,640,897 个参数；`model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`，`config.json` SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`。Dense 与 G-reasoner 共享本地 Qwen3-Embedding-0.6B 向量；其 `model.safetensors` SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`。模型指纹由 runner 启动时核验。
- 环境：`gfmrag_greasoner_20261022`；Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1；离线加载，无依赖变更。
- 硬件：GPU3 RTX 4090；Smoke 前空闲显存 18,842 MiB，CUDA_VISIBLE_DEVICES=`3`；最多 8 CPU 线程。GPU allocation、RSS 上限各 8 GiB，wall 1,800 秒，CPU 900 秒。
- 随机种子：`20261107`。无训练、微调、SQL 执行、外部 API 调用或新数据下载。

## 执行命令

Smoke run ID：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_smoke_001`；Full run ID：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_full_001`。两次使用同一冻结配置和清单，输出目录互不覆盖。

~~~bash
GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES=3 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_sql_used_mapping_rank_20261107_03.py --mode smoke --run-id p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_smoke_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.json --cpu-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/aggregate_summary.json --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cuda:0 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/ranker_gpu_smoke

GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES=3 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_sql_used_mapping_rank_20261107_03.py --mode full --run-id p0_fk_sql_used_mapping_rank_20261107_03_amendment_002_full_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.json --cpu-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/aggregate_summary.json --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cuda:0 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/ranker_gpu_full
~~

## 结果

### Smoke

5/5 预选单元全部评分，31/31 候选 mapping 均有完整有限分数。Smoke 只作为运行门，不纳入 Full 指标。

### Full

| 方法 | Mapping@1 | Mapping@3 | 首个目标 MRR |
|---|---:|---:|---:|
| Dense cosine | 63/108 (58.33%) | 103/108 (95.37%) | 0.7733 |
| G-reasoner | 43/108 (39.81%) | 104/108 (96.30%) | 0.6792 |
| G-reasoner − Dense | **−20/108 (−18.52pp)** | +1/108 (+0.93pp) | −0.0941 |

配对比较：两者都正确 30、都错 32、Dense 单独正确 33、G-reasoner 单独正确 13，净救回 −20。正向门要求 Mapping@1 至少 +5pp、净救回≥4、至少2个 `n≥5` 的匿名库净救回为正；实际分别为 −18.52pp、−20 和 1 个库，**三项筛选条件未通过**。

| 匿名数据库 | 单元 | Dense Mapping@1 | G-reasoner Mapping@1 | 配对净救回 |
|---|---:|---:|---:|---:|
| db_01 | 24 | 17/24 (70.83%) | 7/24 (29.17%) | −10 |
| db_02 | 10 | 10/10 (100%) | 5/10 (50.00%) | −5 |
| db_03 | 62 | 24/62 (38.71%) | 27/62 (43.55%) | +3 |
| db_04 | 12 | 12/12 (100%) | 4/12 (33.33%) | −8 |

只有 `db_03` 的净救回为正（+3）；四库规模和 BIRD-dev 复用限制了外推，不能据此宣称存在可泛化的正向子群。Full 共 108 个表对、328 个候选 mapping；候选数为 2/3/22 的单元分别为 91/12/5。

BM25 与稳定 mapping-ID 顺序在 108/108 单元有并列最高分，其 Mapping@1 取决于既定 tie-break；不把其 Mapping@1 当作有效语义比较。作为描述项，BM25 Mapping@3 为 105/108、首个目标 MRR 为 0.6175。

## 资源与 token

| 阶段 | 单元 | wall | CPU | 峰值 GPU allocation | 峰值 RSS | G-reasoner 前向时间 |
|---|---:|---:|---:|---:|---:|---:|
| Smoke | 5 | 33.252 秒 | 13.283 秒 | 3.56 GiB | 4.40 GiB | 23.337 秒 |
| Full | 108 | 12.086 秒 | 12.397 秒 | 3.31 GiB | 4.41 GiB | 1.263 秒 |

本地 Qwen3 Embedding 共记录 6,888 输入、0 输出 token（Smoke 1,174；Full 5,714），共 9 个本地调用记录；无 usage 缺失。原实验中两位 Qwen reviewer 另有 4,452 输入、791 输出 token。两者都是本地推理，无外部 API 调用；账本未给本地调用套用外部 API 报价，实际 API 费用为 CNY 0，GPU 时间另列，不折算为账单金额。

## 结论与下一步

对这 108 个固定 SQL-used mapping 单元，G-reasoner 的 Mapping@1 低于相同 embedding 的 Dense cosine，且未通过预注册正向门。G-reasoner 的 Mapping@3 仅高 1 个单元、MRR 更低，不能抵消主指标负结果。该结果支持停止当前重复 BIRD-dev 的 SQL-used GFM 排序支线；不进行同一数据上的图变体、参数调整或新增模型票。它不证明 QuadGraph/G-reasoner 在其他任务、标签或数据集上整体无效。

## 产物和隐私

- [匿名聚合结果](aggregate_summary.json)
- [主注册报告](../p0_fk_sql_used_mapping_rank_20261107_03/README.md)
- [Amendment 002 计划](../../plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.md)
- 本地私有输出：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/`。
- 私有预测、manifest、模型回答、原始题目、SQL、schema、mapping ID 未上传。公开 aggregate 只包含匿名总体与数据库级计数。
