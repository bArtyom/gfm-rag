# P0 FK mapping 模型代理排序诊断

**结论：NO-GO。停止本轮代理标签排序方向，不追加同一数据上的调参或图结构变体。** 在三模型高置信一致的 38 个可区分 Full 样本上，冻结 G-reasoner 的 Accepted@1 为 7/38（18.42%）；同向量 Dense Cosine 为 27/38（71.05%）。G-reasoner 低 52.63 个百分点，配对净损失 20 个样本。该结论只说明当前适配下的排序与三模型代理标签不一致得更多；它不是人类真值、SQL 准确率或 QuadGraph 论文整体效果结论。

## 研究问题与预注册门

问题：给定自然语言问题、由参考 JOIN 得到的表对，以及该表对中已声明的 FK mapping 候选，冻结的 G-reasoner 是否比共用 Qwen3 向量的 Dense Cosine 更能把三模型高置信多数接受的 mapping 排在第一位？

核心假设是：把每个 FK mapping 显式表示为图节点，并通过表节点进行 query-conditioned message passing，可能提高代理标签上的 Accepted@1。该实验是 BIRD dev 上的 exploratory 迁移/证伪诊断，数据曾暴露于开发过程；它不验证端到端 JOIN 发现、SQL 执行或跨库泛化。

预先登记的正向筛选门为：G-reasoner 相对 Dense 的 Accepted@1 至少提高 5 个百分点、净救回至少 4 个样本，并且至少两个各有不少于 5 个可区分样本的匿名数据库净救回为正。三项均未通过。它是筛选门，不是显著性检验。

## 上游方法与本轮适配

- 上游代码：[`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，冻结 commit [`b3e4321`](https://github.com/RManLuo/gfm-rag/commit/b3e43219c49929da505244df4f0ba54c0947e4c4)。项目内实验代码和报告只写入用户指定的 [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，没有改写上游仓库。
- G-reasoner 权重、内部传播实现和参数都未训练或修改。本轮改动在任务适配层：把一个候选 FK mapping 作为 mapping node，保留 child→parent 方向和完整有序复合列对；每个候选图含两个 table node，并按 G0 探针连四条端点边：child table→mapping、parent table→mapping、mapping→child table、mapping→parent table。两个 table node 均设为起始 query seeds，最后按 G-reasoner 返回的 mapping-node 分数排序。
- **Dense Cosine** 使用相同的 query 向量、mapping 文本向量、候选集和稳定 mapping-ID tie-break；它没有图传播。
- **BM25 Okapi** 和 **稳定 mapping-ID 顺序**是次级控制；BM25 参数为 k1=1.5、b=0.75。它们不参与正向主门。
- Query 使用 checkpoint 的固定 instruction：`Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: `。mapping、table、relation passage 不加 instruction。Dense 与 G-reasoner 共用归一化的 1024 维 Qwen3 embedding。

## 代理标签、数据与输入边界

- 三个独立本地模型审阅者为 Qwen2.5-Coder-7B、Qwen3-4B-Think2SQL 和 Gemma 4 E4B-it。仅当至少两个置信度不低于 2 的审阅者对 decision 和 accepted mapping-ID 集合完全一致时，才生成可裁定代理标签。模型标签只供 evaluator 在排序结束后评分；question、标签、理由、Gold SQL 和参考 JOIN 都没有进入图特征或排序输入。
- 冻结盲审材料为 60 个问题×表对、135 个候选。按固定种子 20261106 和问题哈希选出 5 个 Smoke 问题；这些问题的所有表对均从 Full 排除。Smoke 为 5 个表对、12 个候选；Full 为 55 个表对、123 个候选，其中 51 个可裁定、38 个接受集合严格小于候选集合，覆盖 4 个匿名数据库。可区分样本数按匿名数据库为 10、10、13、5。
- 人工审阅仍未完成：可信人工 Role 标签数为 0。模型多数绝不等同于人工 gold，也不替代原双人审阅门。

## 运行、环境与资源

项目分支为 `research/p0-model-proxy-rank-pilot-20261106`。排序代码冻结于项目 commit [`f39292e`](https://github.com/bArtyom/gfm-rag/commit/f39292ec035963c55a4370622bb8881c1bc2b291)；配置 SHA-256 为 `93ad60fbe32c6b26aea39fe2ddea5845b640a65362dd30efdf314a7d3beab1bb`。

- G-reasoner：`/mnt/liansp3/sources/models/g-reasoner-34m`，revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`；`model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`。
- Embedding：`/mnt/liansp3/sources/models/qwen3-embedding-0.6b`（Qwen/Qwen3-Embedding-0.6B）；模型权重 SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`。完整模型文件哈希保存在本地私有 run manifest。
- Conda 环境 `gfmrag_greasoner_20261022`，Python 3.12.15、PyTorch 2.8.0+cu128、PyG 2.6.1、Transformers 4.56.1、Sentence Transformers 5.1.1。未安装依赖、未下载权重、未调用外部 API。
- 四张 RTX 4090 在启动前空闲；本轮固定物理 GPU 1（进程内 `cuda:0`）。启动快照显示 GPU 1 空闲显存约 24,553 MiB、主机可用内存 447 GiB、192 CPU、磁盘剩余 112 TiB。Smoke 峰值 GPU 分配 2,531,396,608 bytes、RSS 4,720,988,160 bytes；Full 峰值 GPU 分配 2,979,721,216 bytes、RSS 4,716,544,000 bytes，均低于预注册 8 GiB GPU、16 GiB RSS 上限。
- 本地结果保存在 `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`，日志在 `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`。逐题预测、输入清单和运行清单权限为 0600，仅保存在本机，没有上传。

### 运行编号与异常

1. `..._smoke_001` 在加载模型前停止。原因是一条盲审包问题把换行序列化为字面 `<br>`，而私有清单保留真实换行；其余 59 条逐字相同。精确替换该 `<br>` 为换行后与规范文本一致。没有加载模型、嵌入或 G-reasoner forward，也没有产生推理 token。失败日志及本地 `preflight_failure.json` 保留。
2. `..._smoke_002` 通过：5/5 图完成有限分数计算，12 个候选各计分一次，5 次 G-reasoner forward；Smoke 指标不进入 Full 结果。Qwen 本地嵌入输入 528 token，输出 0 token；墙钟 19.04 秒。
3. `..._full_002` 完成：55 个表对、123 个候选、55 次 G-reasoner forward；墙钟 9.33 秒，forward 合计 0.98 秒。Qwen 本地嵌入输入 2,695 token，输出 0 token。资源预算未超限。

协议 v3 在重跑前固定了唯一允许的 `<br>`→换行校验，并预先登记排除该条样本的敏感性分析。排序输入和 BM25 使用私有清单中的规范问题文本；旧审阅输出仍按原盲审包保留，不重新挑选标签。异常样本位于 Full 可区分集合内，排除后主分母为 37。

## Full 结果

主指标在 38 个模型代理可区分 Full 表对上计算。Accepted@k 表示前 k 个候选中至少一个属于模型代理接受集合；MRR 是首个被接受 mapping 的倒数排名均值。

| 方法 | Accepted@1 | Accepted@3 | MRR |
|---|---:|---:|---:|
| G-reasoner | 7/38（18.42%） | 38/38（100%） | 0.5746 |
| Dense Cosine | 27/38（71.05%） | 38/38（100%） | 0.8553 |
| BM25 Okapi | 22/38（57.89%） | 38/38（100%） | 0.7675 |
| 稳定 mapping-ID 顺序 | 22/38（57.89%） | 38/38（100%） | 0.7675 |

G-reasoner 比 Dense 低 **52.63 个百分点**。配对结果为：两者均正确 6、均错误 10、仅 G-reasoner 正确 1、仅 Dense 正确 21，净救回 `1−21=−20`。四个匿名数据库的 G-reasoner/Dense Accepted@1 与净救回均为负：

| 匿名数据库 | n | G-reasoner | Dense | G-reasoner-only / Dense-only | 净救回 |
|---|---:|---:|---:|---:|---:|
| db_01 | 10 | 1/10 | 5/10 | 0 / 4 | -4 |
| db_02 | 10 | 1/10 | 4/10 | 1 / 4 | -3 |
| db_03 | 13 | 2/13 | 13/13 | 0 / 11 | -11 |
| db_04 | 5 | 3/5 | 5/5 | 0 / 2 | -2 |

在全部 51 个可裁定样本上，G-reasoner 为 20/51（39.22%），Dense 为 40/51（78.43%）。所有方法 Accepted@3 都是 100%，因为每题最多只有 3 个候选；因此本数据上的 @3 已到上限，区分力有限。

**序列化异常敏感性分析**：排除那 1 个异常样本后，Dense 为 27/37（72.97%），G-reasoner 为 7/37（18.92%），差值为 -54.05 个百分点，净救回仍为 -20。异常不改变方向或停止决定。

没有做显著性检验或超参数搜索。所有正向筛选门均失败：Accepted@1 增益门 false、至少 4 个净救回门 false、两个数据库正向门 false（实际 0 个）。结果状态为 `NO_GO_OR_INCONCLUSIVE`，并按预注册规则停止。

## 复现命令

下列命令从项目根目录执行。路径指向本机权限受限的输入与模型；这些文件本身不在 GitHub 上。Smoke 与 Full 共用输入参数，区别仅为 `--mode`、`--run-id` 和 `--output-dir`。

```bash
PACKET_ROOT=/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001
REVIEW_A_B_ROOT=/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_review_proxy_20261106_01/full_001
REVIEW_C_ROOT=/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/full_001
SPLIT=/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/preflight/split_manifest_private.json
COMMON_ARGS=(
  --config configs/text2sql/p0_fk_mapping_model_proxy_rank_pilot_20261106.yaml
  --packet-a "$PACKET_ROOT/reviewer_A_packet.md"
  --packet-b "$PACKET_ROOT/reviewer_B_packet.md"
  --private-manifest "$PACKET_ROOT/private_manifest.json"
  --reviewer-a "$REVIEW_A_B_ROOT/reviewer_A/reviewer_A.jsonl"
  --reviewer-b "$REVIEW_A_B_ROOT/reviewer_B/reviewer_B.jsonl"
  --reviewer-c "$REVIEW_C_ROOT/reviewer_C/reviewer_C.jsonl"
  --split-manifest "$SPLIT"
  --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m
  --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b
  --device cuda:0
)

CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code \
conda run --no-capture-output -n gfmrag_greasoner_20261022 \
/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 \
scripts/text2sql/run_p0_fk_mapping_model_proxy_rank_pilot.py \
--mode full --run-id p0_fk_mapping_model_proxy_rank_pilot_20261106_full_002 \
--expected-commit f39292ec035963c55a4370622bb8881c1bc2b291 \
"${COMMON_ARGS[@]}" \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/full_002
```

Smoke 使用同一命令，将 `--mode full`、Full run ID、`--output-dir .../full_002` 分别替换为 `--mode smoke`、`p0_fk_mapping_model_proxy_rank_pilot_20261106_smoke_002` 和 `.../smoke_002`。完整参数向量、环境变量、输入哈希、模型哈希、依赖版本和输出哈希保存在相应本地 `attempt_manifest.json` 与 `run_manifest.json`；未将这些包含本机私有路径的 manifest 上传。

## 结论与范围

当前冻结 reified G-reasoner 适配没有比 Dense Cosine 更好地恢复三模型代理接受项，且在四个匿名库都没有正向净救回。至少在这组固定候选和表示下，图传播分数不应被当作 Dense 的改进。一个可能解释是共享表节点与双端起始 seed 让不同候选的区分信号被传播削弱；本实验没有消融来证实这一解释，不能把它写成已证实原因。

继续研究前应先取得人类审阅标签，或另行预注册一个能直接检验传播机制的有限诊断。不得在同一代理标签上持续挑图结构或阈值。本报告不能支持人类 Role 正确率、SQL EX 提升、隐藏 FK 发现、端到端 Text2SQL 收益、跨数据集泛化或算法新颖性主张。

## 产物

- 本报告：`docs/research/text2sql/reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/README.md`
- 聚合结果：`docs/research/text2sql/reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/aggregate_summary.json`
- 预注册方案：[`plans/p0_fk_mapping_model_proxy_rank_pilot_20261106.md`](../../plans/p0_fk_mapping_model_proxy_rank_pilot_20261106.md)
- 本地 Smoke 与 Full 原始运行记录、日志和逐题预测：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`，`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`；均未上传。
