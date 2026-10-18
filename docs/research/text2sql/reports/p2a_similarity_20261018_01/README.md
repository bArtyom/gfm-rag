# P2a：1024-D Cosine、BM25 与 RRF 全量对照（2026-10-18）

> **结果状态：全量完成，数据完整性门通过，预注册方法成功门未通过（NO-GO）。** 本报告记录一次 5 题 smoke 和一轮 1,534 题主实验。Smoke 仅验证流程，不纳入正式指标。最终决定是停止本轮评分方法扩展，不启动 Role/Path、GNN、P3 SQL EX 或 P4。

## 研究问题、假设与停止规则

- **研究问题：** 在固定 BIRD dev Query、Schema 文本、Gold 标签、1024-D 向量和候选集合上，BM25 或 Cosine+BM25 的 RRF 是否能提升列检索或同预算的完整 Schema 覆盖？
- **核心假设：** 在预先指定的 706 道列可评、2,048-token 非饱和问题上，BM25 或 RRF 相对 S0 至少提升 Column Recall@10 2.0 个百分点，或 Complete Schema@2048 提升 1.0 个百分点；对应指标在 5 个数据库中至少 3 个方向为正；全体 Table Recall@10 下降不超过 1.0 个百分点。
- **层级：** P2a 主线评分对照，比较 S0 Cosine、S1 BM25、S2 RRF（k0=60）。无训练、无新模型、无图拓扑修改、无 FK/Role/Path 排序、无 SQL 生成或执行。
- **资源预算：** GPU 0 秒；CPU ≤1,800 秒；进程峰值 RSS ≤16 GiB；最多 8 个 CPU 线程。仅复用 P1.6 的本地 float32 缓存。
- **Smoke 成功判据：** 固定顺序前 5 题、单数据库；输入和缓存 hash 与 P1.6 相同；S0 排名和预算选择完全一致；三种方法输出有限且结构有效。Smoke 不计入主结果。
- **停止条件：** 输入/缓存 hash、分母、Smoke、S0 对照、资源预算或输出目录任一检查失败即停止；不覆盖既有运行目录。
- **停止决定：** 全体 Table Recall@10 保护门通过，但 S1/S2 均未达到预注册成功门，因此停止本轮评分方法扩展。该决定只适用于本次 BIRD dev 开发诊断数据。

## 指导、代码与偏离记录

- **工作仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 main。预注册方案与执行器初版先在 commit 8874c208dd632931dd42d9e8b7283efdd42d097c 提交；本轮实际运行使用修复版 commit 689b7f681651f312a1db8850d86b8b7dc4f69fd2，tree 97774d1ca2c7d1bec7346713fd3ce562ec6d1dbf，运行时工作树干净。
- **执行文件：** scripts/text2sql/run_p2a_similarity.py。修复版只调整决策摘要中 Column/Table 与 budget 指标的键访问，不改变候选、分数、排序、指标或阈值。
- **实验前阅读：** 项目根 README、docs/research/text2sql/README.md、experiment-roadmap.md、reproducibility-contract.md、[P2a 预注册协议](../../plans/p2a_similarity_20261018.md)及 P1.6 冻结基线报告。
- **遵循的仓库要求：** 固定输入和候选全集；Top-K 与预算分别按预注册方法计算；报告 Query macro、数据库配对损益和数据库聚类 bootstrap；公开匿名聚合，不公开逐题预测、输入清单、Gold SQL、向量缓存或日志。
- **偏离项：** 方法、输入、候选、K、预算、RRF 常数和成功门均未改变。第一次全量执行在结果汇总阶段因执行器访问字段名错误退出，详见“失败与异常”；修复后以新 run ID 完整重跑。失败运行保留且不作为有效结果。

## 数据、模型、环境与命令

| 项目 | 冻结设置 |
|---|---|
| 数据 | BIRD dev，1,534 题 / 11 DB；完整实验输入 manifest SHA256 693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a |
| 资源入口 | 数据 /mnt/liansp3/sources/datasets/bird/dev；BIRD 预处理任务由统一资源索引指向的 bird_dev_tasks.pkl 提供；Schema 数据库使用同一索引的 bird_dev_databases |
| 候选与标签 | 873 节点：75 tables、798 columns；Table 分母 1,534，Column 分母 1,460、Gold columns 6,523；有序节点内容 hash 4e930d3b906d46d77381edbfee8bfb57ab04fc09d47b9e90fc6272986cceaa5a |
| 预先指定子集 | Schema token 总量 >2,048 的 5 DB，共 746 题，其中 706 题可评列；子集 Gold columns 3,156 |
| 模型与缓存 | Qwen3-Embedding-0.6B，1,024 维；本轮不重新编码或加载模型，复用 P1.6 float32 Query/Node cache。模型文件清单 SHA256 b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68，向量缓存 SHA256 c7bb9ed942aa793e34e1253a5d1d8f8d8d871c95bdfdc33718dde7396d345250 |
| 软件 | Conda 环境 think2sql_20260909；Python 3.12.14、NumPy 2.2.6。未安装 rank-bm25，BM25 按预注册公式用执行器内实现；未安装/升级依赖 |
| 随机性 | Smoke 使用固定顺序前 5 题；Full 使用全部 1,534 题。DB bootstrap 10,000 次，seed=20261018 |
| 资源 | 启动快照：4×RTX 4090，GPU 利用率 67–72%，显存已用 447 / 447 / 6,335 / 451 MiB；本实验不使用 GPU。主机内存 503 GiB、可用 447 GiB；192 CPU 线程；磁盘可用 116 TiB。Full wall 13.315 秒、进程 CPU 12.858 秒、峰值 RSS 0.762 GiB；不调用 API、不训练、不执行 SQL、不下载模型 |

实际使用修复版主仓库 commit 689b7f681651f312a1db8850d86b8b7dc4f69fd2。完整参数数组、输入 hash、环境和日志路径见同目录 experiment_config.json。

- Smoke：run ID p2a_similarity_smoke5_20261018_02；结果目录 /mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/smoke_5q_02；日志 /mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/smoke_5q_02.log。
- Full：run ID p2a_similarity_full1534_20261018_02；结果目录 /mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/full_1534_02；日志 /mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/full_1534_02.log。
- 两次命令均由 conda run -n think2sql_20260909 /root/miniconda3/envs/think2sql_20260909/bin/python3 scripts/text2sql/run_p2a_similarity.py 启动。Smoke 使用 --mode smoke；Full 使用 --mode full 并通过 --smoke-dir 指向上述 smoke 结果。每次实际参数均保存在 experiment_config.json。

Smoke 共 5 题 / 1 DB / 92 个节点，列分母 5，状态 smoke_passed；输入 manifest 与 P1.6 相同，S0 parity PASS，三种方法输出均为有限值。Smoke wall 10.730 秒、CPU 10.340 秒、RSS 0.743 GiB。

Full 的输入 manifest、P1.6 cache、S0 score digest 与冻结基线匹配；数据分母为 1,534 题 / 11 DB / 873 节点、Table 1,534 / Column 1,460，完整性门 PASS。

## 评价方法

- **S0 Cosine：** 复用冻结 float32 向量，显式 L2 归一化后精确内积；同分按 stable node ID。
- **S1 BM25：** Query 原文；每个 DB 的 table+column 节点共同构成文档集合；分词先 casefold、将下划线改为空格，正则 [A-Za-z0-9]+，去除长度 1 的 token；不做停用词过滤、词干化或扩展。使用 k1=1.5、b=0.75、idf=ln(1+(N-df+0.5)/(df+0.5))，同分按 stable node ID。
- **S2 RRF：** k0=60；Top-K 指标分别在同类型候选内排名，token budget 在该 DB 的完整 table+column 候选全集排名；两路排名取倒数融合。预算按节点 token 数贪心选择，超预算节点跳过。
- **指标：** Top-K 的 Table / Column Recall、Column Precision、MRR、MAP；512/1,024/2,048 token 下的 Gold-element recall、precision、Complete Schema；报告均为 Query macro，另按 DB 配对和 cluster bootstrap。

## 全体结果：1,460 个列可评问题

Table Recall 的分母为 1,534；Column 的分母为 1,460。以下值均为百分比，Top-K、MRR、MAP 和预算指标均为 Query macro。

| 方法 | Table R@5 / R@10 | Column R@5 / P@5 | Column R@10 / P@10 | Column R@20 / P@20 | MRR / MAP |
|---|---:|---:|---:|---:|---:|
| S0 Cosine | 94.75 / 99.91 | 52.84 / 42.34 | 68.00 / 28.12 | 79.08 / 18.24 | 82.71 / 55.25 |
| S1 BM25 | 86.52 / 99.67 | 41.32 / 33.12 | 55.91 / 23.09 | 72.02 / 16.76 | 71.67 / 44.43 |
| S2 RRF | 94.58 / 99.61 | 50.80 / 41.04 | 66.90 / 27.79 | 80.32 / 18.56 | 82.14 / 54.53 |

| 方法 | 512-token Gold recall / precision / complete | 1,024-token Gold recall / precision / complete | 2,048-token Gold recall / precision / complete |
|---|---:|---:|---:|
| S0 Cosine | 70.41 / 25.85 / 35.55 | 82.34 / 18.20 / 56.16 | 92.09 / 13.21 / 79.66 |
| S1 BM25 | 56.01 / 22.74 / 21.51 | 70.47 / 16.62 / 32.88 | 86.22 / 12.73 / 62.67 |
| S2 RRF | 66.36 / 25.71 / 29.32 | 78.88 / 18.15 / 46.23 | 91.53 / 13.40 / 77.05 |

## 非饱和子集：706 个列可评问题 / 5 DB

| 方法 | Column R@5 | Column R@10 | Column R@20 | MRR | MAP |
|---|---:|---:|---:|---:|---:|
| S0 Cosine | 44.91 | 58.20 | 69.12 | 79.07 | 46.60 |
| S1 BM25 | 34.99 | 47.70 | 61.79 | 69.10 | 38.30 |
| S2 RRF | 43.93 | 58.29 | 71.06 | 79.43 | 47.48 |

| 方法 | 512-token recall / precision / complete | 1,024-token recall / precision / complete | 2,048-token recall / precision / complete |
|---|---:|---:|---:|
| S0 Cosine | 58.43 / 23.13 / 19.97 | 71.27 / 14.72 / 37.54 | 83.64 / 8.80 / 57.93 |
| S1 BM25 | 42.45 / 18.60 / 5.67 | 56.24 / 12.76 / 13.17 | 71.49 / 7.81 / 22.80 |
| S2 RRF | 54.00 / 22.00 / 13.31 | 66.33 / 14.51 / 26.77 | 82.49 / 9.18 / 52.55 |

### 配对变化、数据库差异与不确定性

| 方法 vs S0 | 非饱和 Column R@10 差值 | 该指标正向 DB | 非饱和 Complete@2048 差值 | 该指标正向 DB | 全体 Table R@10 差值 |
|---|---:|---:|---:|---:|---:|
| S1 BM25 | −10.50 pp | 0 / 5 | −35.13 pp | 0 / 5 | −0.24 pp |
| S2 RRF | +0.09 pp | 2 / 5 | −5.38 pp | 1 / 5 | −0.30 pp |

| 方法 vs S0 | Column R@10 救回 / 损坏题（全体） | Gold 列命中净变化（全体） | Complete@2048 救回 / 损坏题（全体） | Column R@10 救回 / 损坏题（非饱和） | Gold 列命中净变化（非饱和） | Complete@2048 救回 / 损坏题（非饱和） |
|---|---:|---:|---:|---:|---:|---:|
| S1 BM25 | 215 / 660 | −734 | 17 / 265 | 142 / 310 | −282 | 17 / 265 |
| S2 RRF | 273 / 319 | −48 | 27 / 65 | 170 / 159 | +25 | 27 / 65 |

按数据库聚类 bootstrap 10,000 次、seed 20261018，百分点差的 95% 百分位区间如下。数据库数少，区间只作探索性摘要。

| 方法 vs S0 | 全体 Column R@10 差值及 95% CI | 非饱和 Column R@10 差值及 95% CI | 非饱和 Complete@2048 差值及 95% CI |
|---|---:|---:|---:|
| S1 BM25 | −12.09 [−16.39, −7.77] pp | −10.50 [−17.42, −4.17] pp | −35.13 [−48.69, −20.57] pp |
| S2 RRF | −1.11 [−3.28, +1.39] pp | +0.09 [−4.15, +4.52] pp | −5.38 [−9.99, −0.14] pp |

S1 的非饱和 Column R@10 在 5 个数据库都下降；S2 仅在 2/5 个数据库上升，增幅也远低于预注册的 +2.0 pp。S2 的 2,048-token 完整覆盖在 5 个数据库中仅 1 个上升；数据库聚类区间整体落在 0 以下。两种方法的全体 Table R@10 下降均小于 1.0 pp，保护门通过，但不足以抵消主指标未达标。

BM25 的 Column 排名在 1,534 题中的 1,530 题出现并列分数；RRF 在 777 题出现并列。执行器按预注册规则使用 stable node ID 破同分。这种大量并列是词面方法结果的重要解释限制，尤其可能使零分候选的尾部排序受确定性 ID 顺序影响。

## 失败与异常

- 初次 smoke p2a_similarity_smoke5_20261018_01（commit 8874c208...）通过，但它仅为流程检查，不作正式结果。
- 初次 Full p2a_similarity_full1534_20261018_01 在决策摘要访问不存在的 recall 键时以 KeyError: 'recall' 退出。错误发生在评分与统计完成后的结果汇总路径；该目录只有失败 metadata，没有有效 aggregate，故整次运行不纳入结果。原目录及日志保留。
- 对执行器键访问做最小修复并提交 commit 689b7f681651f312a1db8850d86b8b7dc4f69fd2 后，以新 run ID 重跑 smoke 和 Full。修复版本 smoke 通过，Full 全部完整性检查通过。原失败目录没有被复用或覆盖。
- 没有 API 请求、依赖安装、模型下载、训练或 SQL 执行；无费用产生。

## 结论与后续

1. 冻结 P1.6 Cosine 基线的重算与 S0 parity 通过，证明三组分数在同一批冻结输入上比较；不改变 P1.6 以外的历史 Gate。
2. **BM25 单独排序明显落后**：非饱和 Column R@10 为 −10.50 pp、Complete@2048 为 −35.13 pp，5 个数据库均没有正向变化。
3. **RRF 没有达到预注册收益门**：非饱和 Column R@10 仅 +0.09 pp，数据库方向为 2/5；Complete@2048 为 −5.38 pp。尽管 RRF 的 Top-K Column R@20 较高，预算完整覆盖仍低于 Cosine。
4. **决策：NO-GO，停止本轮相似度方法扩展。** 不据此声称 BM25/RRF 普遍无效；结果来自已反复用于开发诊断的 BIRD dev，且 DB 数量少、BM25 并列多。没有独立数据库验证，也没有 JOIN Role、Path 或端到端 SQL EX 证据。
5. 根据当前研究守则，后续先做错误模式分析与研究叙事整理；本报告不自动排入额外 GPU 实验。FK/Role Gate 仍未通过，因此 Role/Path、GNN、P3、P4 继续 NO-GO。

## 产物与可复现性

- 在线报告：[P2a 全量报告](https://github.com/bArtyom/gfm-rag/blob/main/docs/research/text2sql/reports/p2a_similarity_20261018_01/README.md)。
- 匿名聚合：同目录 aggregate_summary.json，SHA256 0b5b3ddff8abfd4f330e5a0417b92403de1a01d0b01d8702b96cc87c4e2f0eec。
- 完整配置、命令、资源快照及本地日志/结果位置：同目录 experiment_config.json。
- 私有本地运行根目录：/mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/。逐题预测、完整输入 manifest、排序缓存和运行日志仅留在本地，不提交到 GitHub。
- 本轮代码 commit：689b7f681651f312a1db8850d86b8b7dc4f69fd2；预注册协议首次提交：8874c208dd632931dd42d9e8b7283efdd42d097c。
- 本实验没有 API 调用，当前轮确认 token 用量为 0，估算费用 ¥0。
