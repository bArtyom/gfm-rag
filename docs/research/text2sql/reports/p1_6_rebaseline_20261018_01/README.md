# P1.6 1024 维冻结基线重建（2026-10-18）

> **状态：全量完成，P1.6 Full Gate = PASS。** 本轮重新冻结了同一 BIRD dev 输入下的 1024 维 Qwen3 表/列检索基线。它验证了当前缓存与 scorer 的可重复性，不改变历史 P1/P1.5 的严格复现 FAIL，也不代表新检索方法优于旧方法。

## 研究问题、假设与停止规则

- **研究问题：** 在固定的 Query、Schema 文本、标签、1024 维 Embedding 和候选顺序下，余弦 scorer 是否能在可追溯输入上稳定重建，并给 P2a 提供新的同运行 Dense 基线？
- **核心假设：** 一次固定编码的 float32 向量缓存可无损回读；同一缓存上重复 scorer 会产生逐题完全一致的 Top-K、预算选集和聚合值。
- **层级：** P1.6 基线复建，不是方法增益实验。
- **资源预算：** GPU 编码 ≤900 秒、CPU ≤1,800 秒、RSS ≤16 GiB、最多 8 个 CPU 线程。
- **成功判据：** Smoke 5 题/1 库成功；输入、节点顺序和模型清单 hash 匹配；Full 为 1,534 题/11 库/873 节点，表分母 1,534、列分母 1,460；float32 cache 压缩回读逐位相同；同缓存两次 scorer 的逐题记录及 score digest 完全相同。
- **停止条件：** Smoke、输入/标签 hash、完整分母、资源预算或 Full 重放门任一失败即停止，不进入 P2a。

## 来源与执行指导

- **项目仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `main`，运行代码 commit `d948d462f9407a18f4a48c85a76380d54f865cb2`，tree `db25ea92cffe4042e799b5c5fefd021bf20f23b2`，运行时工作树干净。
- **上游编码器：** [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0；实验只读选择性使用官方 `Qwen3TextEmbModel`。
- **实验前阅读：** 项目根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、P1.6 恢复计划、P1.6 Smoke 审查和已归档 P1.6 进度报告。
- **偏离项：** 无输入、模型、候选集或评分协议变更。Smoke 的重复编码出现非零数值差异，已单独报告；Full Gate 只依据冻结缓存完整性及 scorer 重放通过，不把一次 Smoke 的重新编码等同于跨运行 bit-exact。

## 数据、模型与环境

| 项目 | 冻结设置 |
|---|---|
| 数据 | 本地 BIRD dev；1,534 问题、11 DB；输入 SHA256：questions `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`，schema `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`，P0 audit `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`，gold labels `1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525` |
| 候选 | 873 个 Schema 节点：75 tables、798 columns；type-first 有序节点文本内容 hash `4e930d3b906d46d77381edbfee8bfb57ab04fc09d47b9e90fc6272986cceaa5a` |
| 标签分母 | Table 1,534 题；Column 1,460 题、6,523 个 gold column elements |
| 模型 | 本地 Qwen3-Embedding-0.6B，输出 1,024 维，batch size 32；模型文件清单 SHA256 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68` |
| 编码 | Query 指令沿用 P1.5；float32；L2 归一化；精确 Cosine；仅在分数完全相等时按 stable node ID 字典序破同分 |
| 软件 | Python 3.12.14、NumPy 2.2.6、PyTorch 2.8.0、vLLM 0.10.2、Transformers 4.57.1、sqlglot 28.0.0；复用 `think2sql_20260909`，未安装依赖、下载模型或升级环境 |
| 随机性 | 无随机抽样/随机种子；Smoke 使用冻结顺序的前 5 题，Full 使用全部输入 |

## 运行记录

Smoke：`p1_6_smoke5_20261018_01`，2026-10-18，固定 5 题/1 DB。命令：

```bash
CUDA_VISIBLE_DEVICES=1 LOCAL_RANK=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3 scripts/text2sql/run_p1_6_rebaseline.py \
  --mode smoke --run-id p1_6_smoke5_20261018_01 \
  --expected-commit d948d462f9407a18f4a48c85a76380d54f865cb2 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/smoke_5q_20261018_01 \
  --legacy-root /mnt/liansp3/sources/projects/quadrag \
  --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
  --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
  --previous-run-dir /mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01 \
  --p1-5-run-dir /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03 \
  --gpu-id 1
```

Smoke wall 38.51 秒，编码器 load+encode 25.84 秒，CPU 18.23 秒，峰值 RSS 0.97 GiB。输出状态 `smoke_passed`，分母为 Table 5 / Column 5，节点 92。回执 input manifest SHA256 `693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`，摘要 SHA256 `c1048fac0f8a88131e0d1f93bb444e11782737896695af53ab99aaf2a0f8b74b`。

Full：`p1_6_full1534_20261018_01`，同一代码、输入、模型及 GPU1 RTX 4090；在完整 smoke receipt 上启动。命令：

```bash
CUDA_VISIBLE_DEVICES=1 LOCAL_RANK=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3 scripts/text2sql/run_p1_6_rebaseline.py \
  --mode full --run-id p1_6_full1534_20261018_01 \
  --expected-commit d948d462f9407a18f4a48c85a76380d54f865cb2 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01 \
  --legacy-root /mnt/liansp3/sources/projects/quadrag \
  --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
  --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
  --previous-run-dir /mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01 \
  --p1-5-run-dir /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03 \
  --smoke-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/smoke_5q_20261018_01 \
  --gpu-id 1
```

Full wall 43.98 秒，模型 load+encode 29.35 秒，CPU 21.52 秒，峰值 RSS 0.98 GiB。开始资源快照：4× RTX 4090；所选 GPU1 空闲约 24,113 MiB、利用率 0%；主机可用内存 447 GiB、192 CPU、数据盘剩余 116 TiB。未训练、未运行 SQL、未调用外部模型 API。

## 结果

### 主要检索指标

| 指标 | 结果 |
|---|---:|
| Table Recall@5 / @10（query macro，n=1,534） | 94.75% / 99.91% |
| Column Recall@5 / @10 / @20（query macro，n=1,460） | 52.84% / 68.00% / 79.08% |
| Column MRR / MAP（query macro） | 82.71% / 55.25% |
| Gold column rank（6,523 个元素） | p50=6，p90=52，max=198 |
| 512-token budget：Gold-element recall / precision / complete schema | 70.41% / 25.85% / 35.55% |
| 1,024-token budget：Gold-element recall / precision / complete schema | 82.34% / 18.20% / 56.16% |
| 2,048-token budget：Gold-element recall / precision / complete schema | 92.09% / 13.21% / 79.66% |

指标定义均按 query macro；budget 分母为 1,460 个 column-eligible 问题。2,048-token 非饱和子集覆盖 5 DB、746 道总问题，其中 706 道 column-eligible 问题；非饱和子集仅作为后续 P2a 的预先指定分析层，本轮不据此挑选方法。

### 完整性与数值稳定性

- **Full Gate：PASS。** 压缩 float32 cache 回读 bit-exact；同一缓存两遍 scorer 的矩阵 digest 均为 `08b33648f25a5da09e2e5651207b83732bbc4b06eea2a2529ea1c1e290c53625`，逐题行 digest 均为 `73f44cc435b29e8a118b4b5719acb1cf5f3c418d3d8b7c8cf6f7e07e9b732631`。
- 完整输入 manifest SHA256 `693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`；有序节点清单文件 SHA256 `81ccc51c442c9d4771a16f600340c37f2673887fc0672d8179ecc20d39296754`；其规范化内容 SHA256 `4e930d3b906d46d77381edbfee8bfb57ab04fc09d47b9e90fc6272986cceaa5a`。
- Query 与 node 原始向量范数最小值均为 0.99999988，中位数与 p95 均为 1.0；L2 归一化后范数最大绝对误差均为 `1.19e-7`。
- 全量 score 有 1 个问题出现 1 组精确同分（多出的同分候选 1 个）。Column R@5/@10/@20 边界精确零间隔均为 0；最小分差分别为 `5.84e-6`、`1.31e-6`、`2.32e-6`。
- **Smoke 重新编码有可见浮点/排序变化：** Query 向量 max abs diff `0.002555`，node 向量 `0.003764`；非 bit-exact，5/5 问题的指标行发生变化。两个编码 pass 的 Column R@20 最小 Top-K 边界 gap 分别为 `4.01e-5` 和 `2.97e-4`，均无精确同分边界。故本报告只确认冻结 cache 下 scorer 确定，不宣称编码器在不同前向间 bit-exact。

### 与历史结果的关系

- P1.5 1024 维逐题比较为 7,448 项检查中 7,405 项相同、43 项不同（99.4227% 匹配）；其中 Column@5 命中差异 20 项、Column@10 18 项、2,048-token complete 3 项、Table@5 1 项、Table@10 1 项。旧向量/分数未留存，浮点与 tie 原因仍未完全定因。
- 历史 P1/P1.5 严格复现结论仍为 **FAIL**；本轮新基线不能覆盖或更改旧 Gate。

## 异常、结果位置与结论

- vLLM 进程退出时日志出现 `destroy_process_group() was not called before program exit` 警告；Smoke 与 Full 退出码均为 0，所需摘要、回执与缓存完整，未观察到结果损坏。
- 私有运行目录：`/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/`。Smoke 与 Full 分目录保存；逐题记录、完整输入清单、向量缓存和日志不进入 GitHub。
- 公开匿名聚合：本目录的 [`aggregate_summary.json`](aggregate_summary.json)，SHA256 `925a7116835080b78f0752b3915f9bdf056e173434bd5b176111f7830c91c504`；完整运行配置见 [`experiment_config.json`](experiment_config.json)。
- **结论：** P1.6 冻结的新 1024-D Dense 基线可用于同一冻结输入下的 P2a 对照。P1.6 没有证明历史复现问题已解决，也没有证明检索质量提升。根据仓库指导，下一步只做同候选文本/同标签/同预算的 S0 Cosine、S1 BM25、S2 RRF(k0=60)；FK/Role/Path、GNN、P3 SQL EX 与 P4 均不在本轮启动。

## 可复现产物

- P1.6 代码：`scripts/text2sql/run_p1_6_rebaseline.py`，commit `d948d462f9407a18f4a48c85a76380d54f865cb2`。
- 配置与聚合文件：本报告目录中的 `experiment_config.json`、`aggregate_summary.json`。
- 本地数据入口：`/mnt/liansp3/sources/datasets/bird/dev`；模型入口：`/mnt/liansp3/sources/models/qwen3-embedding-0.6b`。
- 本轮没有 API 请求，因此按调用账本记录的费用为 ¥0；模型是在本地运行。
