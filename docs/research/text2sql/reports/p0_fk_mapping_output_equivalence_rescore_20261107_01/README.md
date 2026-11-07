# P0：冻结 SQL-used GFM 排名的同实例输出等价重评分

**状态：完成；评价敏感性达到预设门，但 G-reasoner 仍落后 Dense。** 实验 ID：`p0_fk_mapping_output_equivalence_rescore_20261107_01`。这是对已冻结排序与 SQLite 对比结果的探索性只读重评分；不训练、不调用模型、不执行 SQL、不改排序分数。

## 研究问题、动机与假设

原 SQL-used Mapping@1 把参考 SQL 实际使用的 FK mapping 作为唯一正确候选。独立的实例审计发现，部分其他 mapping 在当前数据库内容上也产生与参考 SQL 完全相同的结果 Bag。本实验问：**在有完整结果的共同样本上，将这些 Bag 相同候选纳入次级接受集合，是否会明显改变冻结 G-reasoner 相对 Dense Cosine 的差距？**

预设假设为差值 `(G-reasoner − Dense)@1` 在扩展接受集合后至少提高 5 个百分点。达到该门只表示评价对目标定义敏感，不代表 G-reasoner 获胜。实验是 `exploratory` 的结果解释诊断，不是新方法主实验；没有显著性检验。

这不是用户选择的模型审阅路线。两位 Qwen 与一位 Gemma 对 60 个盲审单元的审阅、56 个高置信模型多数以及代理排序已在先前报告完成；本实验不重跑模型，不把模型输出作为本次标签。用户选择的模型审阅和本次 SQL-used 结果标签是两条不同证据线。

## 仓库指南、版本与变更

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 启动前读取项目根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`，以及相关 SQL-used 排序/实例等价方案和报告。采用仓库要求的独立 run ID、Smoke 与 Full 分离、匿名归档和停止规则；本轮没有偏离结果口径。
- 初始方案与执行器已在 GitHub 提交 [`853294f`](https://github.com/bArtyom/gfm-rag/commit/853294f37b40cc1c826dd1966d62361580dfc1b9)。首次 Smoke 发现预测文件的 `pair_id` 实际保存完整 `unit_id`，而盲审展示 ID 是 `review_pair_id`。源代码核对后，Amendment 001 只修正这个确定性的 join key；未改输入、样本、标签、阈值或预算。Amendment 已在 Smoke 重跑前提交 [`9f0f39d`](https://github.com/bArtyom/gfm-rag/commit/9f0f39d316d1ff96c58850a42102ccebbcd73b4f)，文件在 GitHub 已逐项读回一致。
- 本轮唯一新增执行器为[`rescore_p0_fk_mapping_output_equivalence.py`](../../../../../scripts/text2sql/rescore_p0_fk_mapping_output_equivalence.py)，SHA-256 `e25e34bb514901ae28a279b314a32cb265d85ff91ab27bfaa43c056bd08bb283`；配置 SHA-256 `508e007f0049c883a35c14a686b44ce9b3ae89e4ea7a8eed4479d96ef6aad998`。执行来源提交为 `9f0f39d316d1ff96c58850a42102ccebbcd73b4f`。
- 本轮没有修改或替代 QuadGraph 上游算法、G-reasoner 权重、Dense 向量、BM25 参数、候选集或任何排序；只新增一层标签重评分。

## 输入、数据与评估口径

- 排名输入：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_002` GPU Full 的冻结 108 行预测，SHA-256 `553556a4de85efa48d0b639b899d07b39fa8a35955e6757de0e7a6020308e659`，源提交 `7801d46206a0aeeaaacad05f80e71961297ee475`。
- 身份清单：`prepared_manifest_private.json`，SHA-256 `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0`。与静态等价审计使用同一冻结清单。
- 实例对比：`p0_fk_mapping_instance_equivalence_20261107_01` Full_002 的私有逐单元文件，SHA-256 `f996213f2d6e657f518c5440843eaa7f61e6f91fd57e5d0393d8022d6d5a4337`；源提交 `e0d3e0d0d617cbedc02ef317f3578057b36b28ee`。
- 静态结果审计在 108 个单元中确认 94 个完整且 Gold 输出非空；其余 14 个为 7 `not_substitutable`、4 `gold_execution_unknown`、3 `candidate_execution_incomplete`，不进入本次分数。
- SQL-used 单目标标签为唯一 `is_target=true` 候选。次级实例输出等价标签包括该目标及所有满足 `status=ok`、`bag_equal=true` 的候选。不使用 Set-equality 标签。
- **Bag 定义澄清：** 注册 JSON 中的 `bag_semantics` 描述曾写“ordered rows”，这句不准确；实际冻结比较器 `p2d_sql_evaluator.compare_rows` 忽略结果行顺序、保持列顺序、保留重复行的多重性；float/float 使用 `rel_tol=1e-6`、`abs_tol=1e-8`，integer-involving 比较要求相等。运行器只消费静态审计已生成的 `bag_equal` 标记。该配置描述没有进入代码路径、候选标签或结果，不改变本次数字；这里保留记录，避免误称行顺序参与比较。
- Smoke 由固定 SHA-256 排序选择 5 个可评估单元；这 5 个从 Full 中排除。Full 为剩下 89 个，覆盖 4 个匿名数据库。没有随机种子、扩样或逐题调参。
- 每个 unit、pair 和候选 ID 都通过冻结身份哈希进行严格 join；108/108 预测与清单一对一匹配。所有入选单元候选集合一致，且 SQL-used 目标唯一。

## 环境、资源和运行命令

- 环境：Conda `think2sql_20260909`，Python 3.12.14；仅 Python 标准库。CPU-only，4 线程上限；没有安装依赖。
- 运行前可用 RAM 约 432 GiB、192 逻辑 CPU、磁盘余量约 112 TiB。GPU 未使用。Full 墙钟约 0.017 秒，峰值 RSS 约 0.021 GiB；CPU 秒未单独采集。GPU 时间 0 秒。
- Smoke run：`p0_fk_mapping_output_equivalence_rescore_20261107_smoke_001` 因错误假设的 pair key 触发 `PREDICTION_PAIR_COVERAGE_MISMATCH` 停止；没有计算指标、没有结果目录。旧 run ID 保留且关闭。日志：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/smoke_001.log`。
- Amendment 001 Smoke：`p0_fk_mapping_output_equivalence_rescore_20261107_amendment_001_smoke_001`，5/5 通过配对、候选集、目标唯一性和 Bag 重放标签完整性校验。它是执行检查，不并入 Full 指标。日志在 `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/amendment_001_smoke_001.log`。
- Full run：`p0_fk_mapping_output_equivalence_rescore_20261107_amendment_001_full_001`，89/89 完成。日志在 `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/amendment_001_full_001.log`。
- Full 命令（从仓库根目录执行）：

```bash
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4 \
  conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/rescore_p0_fk_mapping_output_equivalence.py \
  --mode full \
  --run-id p0_fk_mapping_output_equivalence_rescore_20261107_amendment_001_full_001 \
  --expected-commit 9f0f39d316d1ff96c58850a42102ccebbcd73b4f \
  --repo-root . \
  --config configs/text2sql/p0_fk_mapping_output_equivalence_rescore_20261107.json \
  --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json \
  --private-predictions /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/ranker_gpu_full/private_predictions.jsonl \
  --instance-equivalence /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/full_002/private_unit_metrics.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/amendment_001/full_001
```

- 本轮模型/API/SQL 调用均为 0；输入/输出 token 均为 0；外部 API 费用 CNY 0.00。CPU 使用不折算成电费。

## Full 结果

| 排名方法 | SQL-used 单目标 @1 | 同实例 Bag 等价 @1 | 新增接受的 Top-1 |
|---|---:|---:|---:|
| G-reasoner | 33/89（37.08%） | 63/89（70.79%） | 30 |
| Dense Cosine | 55/89（61.80%） | 80/89（89.89%） | 25 |
| BM25 Okapi | 22/89（24.72%） | 59/89（66.29%） | 37 |
| 稳定 mapping-ID 顺序 | 22/89（24.72%） | 59/89（66.29%） | 37 |

G-reasoner 与 Dense 的配对差值如下：

| 标签口径 | 两者都对 | 仅 G-reasoner 对 | 仅 Dense 对 | 两者都错 | G-reasoner 净差 |
|---|---:|---:|---:|---:|---:|
| SQL-used 单目标 | 24 | 9 | 31 | 25 | −22 |
| 同实例 Bag 等价 | 60 | 3 | 20 | 6 | −17 |

在 SQL-used 单目标口径下，G-reasoner−Dense 为 **−24.72 pp**；同实例 Bag 等价口径下为 **−19.10 pp**，差距缩小 **5.62 pp**。达到预设的 +5 pp 评价敏感性门。按匿名库看，扩展接受集合的信号主要来自 DB-B 与 DB-D；DB-A 没有新增接受项。分库值见匿名[`aggregate_summary.json`](aggregate_summary.json)。

## 结论、局限与下一步

同实例等价候选改变了 G-reasoner 的分数，但**没有扭转方法排序**：在 89 个 Full 单元上，它仍比 Dense 低 17 个配对净命中、低 19.10 个百分点。可以得出的有限结论是：原 SQL-used 唯一目标会夸大 G-reasoner 相对 Dense 的差距约 5.62 pp；校正这一评价敏感性后，G-reasoner 仍落后。

该结果不等于语义等价、业务 FK Role 正确、用户意图正确或独立泛化。所有替代候选只在**一个冻结数据库实例**上与 Gold 结果 Bag 相同；结果又集中在 DB-B/DB-D，分库样本较小。Test Suite Accuracy、SynSQL、ParSEval、SpotIt 已涉及测试数据库、合成数据库或 SQL 等价检验，因此这里不主张“合成数据库测试”或“等价验证”为新方法；本轮只重解释旧结果。[Test Suite Accuracy](https://aclanthology.org/2020.emnlp-main.29/)、[SynSQL](https://arxiv.org/abs/2604.27261)、[ParSEval](https://www.vldb.org/pvldb/vol18/p4750-miao.pdf)、[SpotIt](https://arxiv.org/abs/2510.26840)。

**决策：保留 G-reasoner 相对 Dense 的负向结论并停止这批 BIRD-dev 候选上的方法调参和图变体。** 下一步进入错误证据综合；若要继续 FK mapping 研究，需要独立的跨实例/多数据库内容证据或人工业务 Role 标签。此前 55 对候选的受控 child-FK 值置换只找到 14 个可用单元、覆盖 2 库，未达到门槛，因此不能把它当成已验证的替代验证方案。

## 产物和归档

- 项目内报告：`docs/research/text2sql/reports/p0_fk_mapping_output_equivalence_rescore_20261107_01/README.md`。
- 匿名 Full 汇总：[`aggregate_summary.json`](aggregate_summary.json)，SHA-256 `40de5cf557f1776324ba43203a1e7134335c1471be25f816114154cf73084886`。
- Smoke 汇总：[`smoke_summary.json`](smoke_summary.json)，SHA-256 `9101be87a4e03d881ea2bd4e3a5520dafee7acf4d99b9e55f262ed0f71ff8d68`。
- 配置副本：[`experiment_config.json`](experiment_config.json)。校验摘要：[`verification_summary.json`](verification_summary.json)。
- 私有逐单元计分和 run metadata 保存在 `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/`，权限受限；未上传。原始输入和旧实验结果保持不变。
