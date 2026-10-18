# P2b R0/R1 Values 文本消融

> **状态：Full 完成；预注册主成功门 NO-GO，停止 Values 扩展。** BIRD dev 是探索集，本结果不支持跨库泛化结论。

## 摘要

在同一 Qwen3-Embedding-0.6B、同一批 query 向量、同一 873-node 候选池和同一 Cosine scorer 下，对比原始列 Schema 文本 R0 与移除 `value_description` 的 R1。全体 1,460 个可评列问题上，R1 的 Column R@10 下降 **0.96 pp**，DB-cluster bootstrap 95% CI 为 **[−2.06, +0.08] pp**。因此没有达到预注册的“至少 +1.0 pp 且区间下界 >0”主成功标准；预注册 NO-GO。固定非饱和集的 Column R@10 护栏通过，Complete@1024 全体与固定子集均提升。结果显示删除 Values 让预算内完整 Schema 更容易放入，但本实验没有证据支持因此删除 Values 字段。

- 完整公开匿名聚合：[aggregate_summary.json](aggregate_summary.json)
- 预注册计划：[p2b_values_ablation_20261018.md](../../plans/p2b_values_ablation_20261018.md)
- 项目运行脚本：[run_p2b_values_ablation.py](../../../../../scripts/text2sql/run_p2b_values_ablation.py)

## 研究问题、假设与判据

- **问题：** 在其他字段、候选集、query、维度、Cosine scorer 和预算保持固定时，列文本的 Values 描述是否提高列召回，或主要增加 Schema 文本长度、降低完整 Schema 的预算内选择？
- **核心假设：** R1−R0 全体 Column R@10 至少 +1.0 pp，DB-cluster bootstrap 95% CI 下界 >0；固定非饱和 Column R@10、全体 Complete@1024 和固定子集 Complete@1024 均不低于 −1.0 pp。
- **实验层级：** 最小消融。最多一组 R0/R1，加同文本 R0-repeat 数值控制；一次初始 smoke、因纯实现错误登记的一次恢复 smoke、一次 Full。恢复 smoke 再失败即停止；Full 完成后进入分析/写作，不自动排新实验。
- **结果性质：** BIRD dev 已用于多轮开发，只作为 exploratory 证据。

## 仓库指导与版本

- 主仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `main`。
- 预注册起点 `8d00c66532d0110ea09e02d220ff3dbb45b50b22`；正式 smoke recovery 与 Full 使用已发布 commit [`7cb681000f4da87aeeb71098ff383aaae6b45660`](https://github.com/bArtyom/gfm-rag/commit/7cb681000f4da87aeeb71098ff383aaae6b45660)。该提交包含恢复 smoke 修复及故障/恢复记录；运行前远端 main、checkout commit 和 clean tree 一致。
- 执行前读取项目 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、P2a.5 专项计划与结果。旧 roadmap 仍写“P0 是唯一立即执行任务”，较新的研究首页与 P2a.5 专项计划则在诊断后允许另行预注册 P2b；本轮采用较新且更具体的专项指导，并在计划中记录冲突。P2a NO-GO 与 FK/Role Gate NO-GO 保持不变。
- 没有修改上游实现；仅增加本实验 runner、计划和记录。P2a evaluator 及冻结输入用于相同 scorer、cache parity 与指标计算。

## 对照和执行方法

| 条件 | Schema 列节点文本 | 作用 |
|---|---|---|
| R0 | Name + Type + Description + Format + Values（有值才序列化） | 当前文本基线 |
| R0-repeat | 与 R0 完全相同的文本，同一 CPU encoder 再编码一次 | 数值/排序稳定性控制 |
| R1 | R0 只移除 `value_description` | 唯一消融因素 |

固定 Qwen3-Embedding-0.6B、1024 维、batch 32、max sequence length 8192、Cosine、node-ID 稳定 tie-break、query 指令、全部候选节点、同一组 query 向量和 512/1024/2048 token budgets。R1 从冻结 Schema metadata 重建；完整 R0 text hash 与 P1.6 冻结值一致，并逐节点验证 R1 只删除列 Values。共 873 节点（75 tables、798 columns），其中 278 列含非空 Values 描述。

P1.6 的冻结 vLLM cache 用于重放 S0 scorer parity 和后端参考。因四张 RTX 4090 在预检和运行时持续繁忙（GPU 利用率约 69–100%），R0、R0-repeat、R1 与 query 全在本地 CPU Transformers `AutoModel` 上完成；没有把 vLLM/CPU 后端变化归因于 Values 消融。R0/R1 主对照使用同一 CPU encoder 和 query vectors。编码采用 Qwen3 模型卡的 left-padding、last-token pooling、BF16 权重/前向及 float32 L2-normalized 输出。

## 数据、模型与环境

- BIRD dev 冻结输入：1,534 questions、11 databases、1,460 column-eligible questions、6,523 Gold columns；均为探索集样本。
- P1.6 input manifest SHA-256：`693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`。
- Qwen3 模型 manifest SHA-256：`b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`，由本地 `/mnt/liansp3/sources/models/qwen3-embedding-0.6b` 统一入口加载；模型未下载或复制。
- 环境 `think2sql_20260909`：Python 3.12.14、PyTorch 2.8.0、Transformers 4.57.1、NumPy 2.2.6、tokenizers 0.22.1；CPU Intel Xeon Platinum 8360H，最多 8 线程。预检时内存可用 438–440 GiB、磁盘可用 116 TiB。
- 本轮没有外部模型 API、GPU、SQL、训练、依赖安装或数据/模型下载。API 请求 0、API 输入/输出 tokens 0/0、API 费用 CNY 0.00（无外部计费请求）；本地 CPU 运行时间单独记录。

## Smoke 记录与偏差

1. 初始 smoke `p2b_values_smoke5_20261018_01` 保留在本机 `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/smoke_5q_20261018_01`，日志 `/mnt/liansp3/logs/gfmrag_p2b_values_smoke5_20261018_01.log`。5 题编码与 scorer 计算完成后，聚合器错误地从 prepared question 取 `column_eligible`，引发 `KeyError`。未写出 aggregate、逐题行或向量缓存。该实现错误与唯一恢复额度在再次运行前已登记并提交；没有改变科学假设、数据、条件、指标或阈值。用量：49.808 s wall、313.046 s CPU、2.703 GiB RSS、12,238 本地输入 tokens。
2. 恢复 smoke `p2b_values_smoke5_20261018_02` 通过，运行 5 题/1 DB、活动候选节点 92 个；核验全体 873 节点 R0 hash、278 个 Values 字段删除、P1.6 scorer parity 和向量有效性。Smoke-only Column R@10 delta −5.0 pp，仅用于流程检查，不作为结果证据。用量：44.843 s wall、273.809 s CPU、3.512 GiB RSS、12,238 本地输入 tokens。
3. Full 仅在 recovery smoke 通过后启动。所有尝试的累计预算为 7200 CPU s / 3600 wall s；无尝试重用既有输出目录。

## Full 结果

主对照是 `R1_local_cpu_without_values − R0_local_cpu_pass_1`；所有点估计以 query macro 报告，区间按数据库簇 bootstrap 10,000 次、seed `20261019` 计算。固定非饱和子集按冻结 R0/P1.6 schema-token totals 预先确定，为 5 DB / 706 列可评题。

| 指标 | R0 | R1 | R1 − R0 |
|---|---:|---:|---:|
| Column R@5，全体 | 52.82% | 51.77% | −1.05 pp |
| **Column R@10，全体（主指标）** | **67.99%** | **67.03%** | **−0.96 pp** |
| Column R@20，全体 | 79.21% | 78.67% | −0.55 pp |
| Complete@512，全体 | 35.34% | 38.90% | +3.56 pp |
| **Complete@1024，全体（护栏）** | **56.64%** | **65.96%** | **+9.32 pp** |
| Complete@2048，全体 | 79.52% | 85.82% | +6.30 pp |
| Gold-column budget recall@512，全体 | 70.47% | 74.20% | +3.73 pp |
| Gold-column budget recall@1024，全体 | 82.52% | 86.39% | +3.87 pp |
| Gold-column budget recall@2048，全体 | 92.10% | 95.24% | +3.14 pp |

预注册判据及结果：

- 全体 Column R@10 Δ **−0.9555 pp**；DB-cluster 95% CI **[−2.0564, +0.0829] pp**，11 clusters / 1,460 questions。既未达到 +1.0 pp，也没有正的区间下界；**主成功门失败**。
- 固定非饱和 Column R@10 Δ **−0.6666 pp**，满足不低于 −1.0 pp 的护栏；其 95% CI 为 [−2.0586, +0.8659] pp。
- Complete@1024 全体 Δ **+9.3151 pp**，固定非饱和子集 Δ **+5.5241 pp**，两个护栏通过。
- 因主成功门失败，预注册综合判定为 **`no_go_stop_values_ablation`**。护栏通过不改变主判定，也不授权新增实验。

## 文本、预算与稳定性诊断

- R0/R1 的 873 节点文本 token 总数从 27,506 降至 20,071（−7,435，−27.0%）；列节点 token 总数从 24,448 降至 17,013（−30.4%）。R0/R1 列文本 token 中位数 23→21，P90 53→29。
- R0 中 5 个 DB 的 Schema 文本总量超过 2048 tokens；R1 中为 4 个。固定非饱和集合仍按 R0 确定，不随 R1 改变。
- 全体平均实际选择 tokens：budget 1024 下 949.59→915.27；budget 2048 下 1709.27→1498.26。与 Complete@1024 的改善方向一致。
- R0-repeat 与 R0 首遍向量 **bit-exact**（873×1024，最大绝对差 0）；R@5/@10/@20 的 Top-K 集合和顺序均无变化。这次 CPU 重编码未见数值波动。
- P1.6 冻结 cache S0 逐题重放 parity 精确通过，1,534 题全部核对。冻结 GPU/vLLM cache 的 Column R@10 为 68.0044%，本轮本地 CPU R0 为 67.9886%（−0.0158 pp）；该后端参考不是 Values 主对照。

## 运行时间与复现命令

Full `p2b_values_full1534_20261018_01` 使用 commit `7cb681000f4da87aeeb71098ff383aaae6b45660`，本地结果目录 `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/full_1534_20261018_01`，日志 `/mnt/liansp3/logs/gfmrag_p2b_values_full1534_20261018_01.log`。Full 用时 292.863 s wall / 2168.755 s CPU / 峰值 RSS 5.700 GiB；本地 encoder 实际输入 141,327 tokens，生成 0。三次尝试累计 387.514 s wall / 2755.610 s CPU / 峰值 RSS 5.700 GiB / 本地输入 165,803 tokens。

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 python3 scripts/text2sql/run_p2b_values_ablation.py \
  --mode full \
  --run-id p2b_values_full1534_20261018_01 \
  --expected-commit 7cb681000f4da87aeeb71098ff383aaae6b45660 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/full_1534_20261018_01 \
  --smoke-dir /mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/smoke_5q_20261018_02 \
  --p1-6-run-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01 \
  --legacy-root /mnt/liansp3/sources/projects/quadrag \
  --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
  --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
  --previous-run-dir /mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01 \
  --p1-5-run-dir /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03
```

Full 日志仅含 Transformers 的 `torch_dtype` 弃用提示；运行完成，输出向量和分数有限，没有其他异常。结果 receipt、逐题行、embedding cache、日志均留在本机独立结果目录，不上传。

## 结论与局限

在这组 BIRD dev 上，移除 Values 明显缩短 Schema 文本并改善预算内 Complete，但 Column R@10 点估计略降，且区间跨过 0。该结果不满足预注册主门，不能据此将 Values 从列检索文本中移除，也不能断言 Values 对所有数据集都有帮助或伤害。对当前 pipeline 的选择是保留 Values 作为列检索字段，并停止继续扩展这组 Values 消融；若论文需要解释预算收益，先做已有结果的错误分析与叙事整理，不自动启动新 GPU 实验。

## 可公开产物与隐私

`aggregate_summary.json` 只包含匿名 DB 聚合、计数、指标和 hash；不含 question IDs、问题文本、Gold SQL、逐题预测、模型向量或数据库内容。逐题 JSONL、向量 cache、manifest 原件、运行 receipt 和日志只保存在本地结果目录。
