# BIRD Gold SQL 标签稳健性审计：Smoke 门停止报告

**实验 ID：** `p0_bird_gold_label_robustness_20261106_01`
**状态：** `STOP_SMOKE_GATE`，未进入 Full
**性质：** exploratory 测量有效性审计；本次没有产生检索质量或方法效果结论。

## 研究问题与预注册假设

本审计原计划固定 BIRD 问题、evidence、数据库 Schema、P1.6 候选节点和排序，只把 Gold SQL 标签来源从 BIRD 原 SQL 换为 Arcwise-Plat-SQL 修正版，观察 Table、Column 与 Complete Schema 指标是否变化。主假设是标签来源变化可能改变 Gold 表/列集合，进而改变冻结排序下的检索指标。

预注册要求修正版 498 条记录与本地 BIRD 记录按 `question_id`、`db_id`、`question`、`evidence` 全量一对一精确匹配。不得用模糊文本匹配补配；匹配门失败时停止，不运行 Full。实验计划和 Smoke 前的解析器兼容修订见 [`plans/bird_gold_label_robustness_20261106.md`](../../plans/bird_gold_label_robustness_20261106.md)。

## 参考仓库与指南

- 用户项目：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，实验分支 `research/bird-gold-label-robustness-20261106`。
- 本地执行代码版本：`6c2183ad66974aaae5e147413930c25ae97f29b7`；代码文件 SHA-256：`01816feeb09032090de80470c4b3a93ecf1426f6bcf14a7eebb33681592015bf`。
- corrected SQL 数据源：[`uiuc-kang-lab/text_to_sql_benchmarks`](https://github.com/uiuc-kang-lab/text_to_sql_benchmarks)，固定 commit `fe766045c55b6875a43b30e9ac7683df5582f8cf`，文件 `data/arcwise_plat_sql_only_with_diff.json`，SHA-256 `e7bf76408f99266506ea558d84982c69422e5db3dfecab5f08a3a8d3900e8395`，498 条、11 个数据库，许可证为 CC BY-SA 4.0。
- 固定 commit 的上游 README 将 Arcwise-Plat-SQL 描述为只修正 SQL 标注并保留问题和 evidence 中原有歧义。[上游 README](https://github.com/uiuc-kang-lab/text_to_sql_benchmarks/blob/fe766045c55b6875a43b30e9ac7683df5582f8cf/README.md)
- 依照项目要求，执行前复核了 `bArtyom/gfm-rag` 的项目 README、Text2SQL 研究 README、roadmap 与 reproducibility contract。项目工作区的具体数据及结果入口登记在本地 `/mnt/liansp3/sources.md`。

## 环境、资源与可复现输入

- 环境：现有 `qes_rear_refine`；Python 3.10.22；SQLGlot 30.12.0。用环境内绝对解释器启动，因为 `conda run ... python3` 在该机器解析到 Python 3.9。未安装或升级依赖。
- 设备：CPU-only，线程上限 4。启动前检查到 4 张 RTX 4090 空闲但未使用、可用内存约 450 GiB、逻辑 CPU 192、工作盘可用约 112 TiB；swap 已满 2 GiB。任务没有申请 GPU。
- 原 BIRD `dev.json` SHA-256：`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`。
- Schema `dev_tables.json` SHA-256：`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 冻结原标签 SHA-256：`1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525`。
- P1.6 逐题结果、节点清单和聚合结果 SHA-256 分别为 `6b28af7400cb70e0ab88a00b56654235571a074022fd8ea52b3f9744a844c4e9`、`81ccc51c442c9d4771a16f600340c37f2673887fc0672d8179ecc20d39296754`、`925a7116835080b78f0752b3915f9bdf056e173434bd5b176111f7830c91c504`。
- 可复现配置：[`configs/text2sql/p0_bird_gold_label_robustness_20261106.json`](../../../../../configs/text2sql/p0_bird_gold_label_robustness_20261106.json)。
- 执行代码：[`scripts/text2sql/audit_bird_gold_label_robustness.py`](../../../../../scripts/text2sql/audit_bird_gold_label_robustness.py)。

计划 Smoke 为按 SHA-256(`db_id/question_id`) 稳定选择的 5 条。正式标签提取、Top-K 命中计算与预算覆盖复算均以精确匹配门为先决条件。该门未通过，因此脚本没有调用 SQLGlot 提取标签，也没有读取逐题 P1.6 指标来进行比较。

## 运行记录与结果

| 运行 | 状态 | 结果 |
|---|---|---|
| `smoke_001` | `STOP_OUTPUT_EXISTS` | 启动器预先创建了 runner 要自行创建的结果目录。数据检查未开始；失败回执保留在本地。 |
| `smoke_002` | `STOP_MATCH_GATE` | 读取元数据后，498 条记录未能全部按预注册字段精确匹配；脚本在样本选择和 SQL 标签解析之前停止。 |

对 `smoke_002` 的只计数诊断结果如下，不含问题文本、SQL 或逐题编号：

- 修正版共 498 条；498 个 `question_id` 都能在本地 BIRD 中找到；两侧没有重复或无法解析的问题编号。
- `db_id` 精确相等：498/498。
- `question` 精确相等：414/498。
- `evidence` 精确相等：407/498；仅对字符串去除首尾空白后为 423/498。
- `question`、`evidence`、`db_id` 三项同时精确相等：351/498。另有 147 条至少一项不等。

因此预注册的“全部 498 条精确匹配”门失败。虽然上游说明其 SQL-only 版本旨在保留问题/evidence 的原有歧义，但它与当前本地 BIRD 快照在大量字符串上不精确相同。本次无法区分这是基准快照、序列化或字段内容差异，也不能证明唯一变化是 Gold SQL。为保持原实验的因果解释，未改成模糊匹配，也未事后筛出 351 条继续计算。

**主要检索指标：未计算。** Table/Column Recall@K、Complete@1024、标签集合变化率、配对差值和 bootstrap 区间全部记为未观测；不能据此声称标签稳健或敏感。Full（493 条）未运行。

## 启动命令

Smoke 使用以下实际命令；输入文件的 SHA-256 也记录在仅本地保存的 `start_manifest.json` 中：

```bash
env CUDA_VISIBLE_DEVICES='' \
  OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4 \
  PYTHONHASHSEED=0 timeout --kill-after=5s 600s \
  conda run --no-capture-output -n qes_rear_refine \
  /root/miniconda3/envs/qes_rear_refine/bin/python \
  scripts/text2sql/audit_bird_gold_label_robustness.py \
  --repo-root . \
  --expected-commit 6c2183ad66974aaae5e147413930c25ae97f29b7 \
  --config configs/text2sql/p0_bird_gold_label_robustness_20261106.json \
  --run-id p0_bird_gold_label_robustness_20261106_01_smoke_002 \
  --stage smoke \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_gold_label_robustness_20261106_01/smoke_002 \
  --original-json /mnt/liansp3/研究项目/Text2SQL/Alpha-SQL_idea1/data/bird/dev/dev.json \
  --schema-json /mnt/liansp3/研究项目/Text2SQL/Alpha-SQL_idea1/data/bird/dev/dev_tables.json \
  --corrected-json /mnt/liansp3/sources/datasets/bird_arcwise_plat_sql_only_20261106/arcwise_plat_sql_only_with_diff.json \
  --archived-labels /mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014/results/p1/full_1534_final_20261014/per_question_private.jsonl \
  --p1-rows /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/per_question_private.jsonl \
  --node-manifest /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/ordered_node_manifest.json \
  --p1-aggregate /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/aggregate_summary.json
```

## 结论、偏离与下一步

- **结论：** 这是数据对齐门的有效停止，不是方法负结果。当前本地 BIRD 快照与 corrected SQL 发布记录不能形成预注册要求的 498 条严格配对。
- **偏离：** 无实验设计偏离。两次 Smoke 尝试及其失败原因均留痕；修复第一次启动器目录冲突后，第二次在精确匹配门停止。未放宽任何匹配条件。
- **停止条件：** 已触发；不运行 Full，不根据部分精确匹配子集发布检索分数。
- **后续工作：** 若未来要重启，必须先独立确认与上游修正数据相对应的原始 BIRD 快照，并在新预注册中冻结该映射。用户已选择后续 G-reasoner A/B 判断采用模型审阅；该任务需独立记录模型、提示/判定规则与预算，模型判断须与人工共识区分。本次标签审计未调用模型。
- **调用与成本：** 本次没有模型、API、SQL 执行、GPU 或依赖变更。API token、外部费用和本地 GPU 时间均为 0；本次使用本地 CPU。

## 本地结果与日志

- 结果与失败回执：`/mnt/liansp3/sources/results/gfmrag_p0_bird_gold_label_robustness_20261106_01/smoke_001/`、`.../smoke_002/`。
- 日志、启动 manifest 和仅计数诊断：`/mnt/liansp3/logs/gfmrag_p0_bird_gold_label_robustness_20261106_01/smoke_001/`、`.../smoke_002/`。
- 未产生可公开的逐题输出；报告与聚合 JSON 仅含汇总元数据。
