# G-reasoner 表/列检索迁移诊断：启动失败记录

**状态：`STOP_NO_SCIENTIFIC_RESULT`。** 两次 5 题 Smoke 均在模型推理前失败，且 amendment 1 的一次恢复预算已经用完。Full 未启动；没有 Column/Table Recall、bootstrap 区间或可用于判断核心假设的科学结果。

## 研究问题与预注册假设

本诊断要检验：在 BIRD-dev 同一组 Schema 候选与 Qwen3 向量上，冻结 G-reasoner 从 Dense 选出的 Top-3 表锚点和 Top-3 列锚点沿 table/column membership 图传播后，能否提高 Column Recall@10；并优于每类一个锚点的 G1 条件，同时不明显损伤 Table Recall@10。

本实验属于 `exploratory checkpoint-transfer diagnostic`。BIRD-dev 已用于项目开发，结果不代表独立泛化。成功门、数据隔离、条件、预算和停止规则以预注册方案为准。FK mapping 排序的既有 `NO-GO` 结论不因这次无推理运行而改变。

## 仓库、指南与版本

- 自有项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/gfm-schema-retrieval-transfer-20261106`。
- 预注册提交：[`cd70d8e`](https://github.com/bArtyom/gfm-rag/commit/cd70d8e975701722681e864adb8822152dabecbc)。运行脚本提交：[`452675a`](https://github.com/bArtyom/gfm-rag/commit/452675a8fa533a69411ad4be88bc27409574ded8)。解释器入口 Amendment 1：[`4f2bb33`](https://github.com/bArtyom/gfm-rag/commit/4f2bb334e874869bc7d9f8578d714eec0fa4eef7)。
- 方案：[`gfm_schema_retrieval_transfer_20261106.md`](../../plans/gfm_schema_retrieval_transfer_20261106.md)；启动修订：[`Amendment 1`](../../plans/gfm_schema_retrieval_transfer_20261106_amendment1.md)。冻结配置和修订配置分别为 [`base config`](../../../../../configs/text2sql/gfm_schema_retrieval_transfer_20261106.json) 与 [`amendment config`](../../../../../configs/text2sql/gfm_schema_retrieval_transfer_20261106_amendment1.json)。运行代码：[`run_gfm_schema_retrieval_transfer.py`](../../../../../scripts/text2sql/run_gfm_schema_retrieval_transfer.py)。
- 启动前依仓库流程核对了根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 和 `/mnt/liansp3/sources.md`。运行以用户指定的 `bArtyom/gfm-rag` 为项目仓库；论文代码参考是 [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0。本实验没有向上游仓库写入内容。

## 方案与冻结输入

- 数据：BIRD dev，1,534 题、11 个数据库、75 张表、798 个列；列指标原定分母为 1,460 题。统一入口为 `/mnt/liansp3/sources/datasets/bird/dev`。问题、Schema、P0 审计、Gold 派生标签和 Qwen 文件清单哈希均与配置一致。
- 向量模型：本地 Qwen3-Embedding-0.6B，1024 维，统一入口 `/mnt/liansp3/sources/models/qwen3-embedding-0.6b`。查询文本使用 G-reasoner checkpoint 登记的 Query instruction；Dense、G1、G3 应共用重编码后的 query 和 value-free R1 schema 向量。
- 推理模型：冻结 G-reasoner-34M，34,640,897 参数，统一入口 `/mnt/liansp3/sources/models/g-reasoner-34m`。图预注册为仅含双向 table/column membership 边，不含 FK、Gold、数据库行、Values 或业务角色。
- 条件：D0 Dense cosine；G1 每类一个 Dense Top-1 起点；G3 每类三个 Dense Top-3 起点。主指标为 query-macro Column Recall@10。成功门要求 G3-D0 至少 +2.0pp、按数据库聚类的 95% CI 下界大于 0、G3-G1 至少 +1.0pp，且 Table Recall@10 损失不超过 1.0pp。
- 目标环境：`gfmrag_greasoner_20261022`，Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1；没有安装或升级依赖。
- 运行预算：一次 5 题 Smoke；只在 Smoke 通过后运行一次 1,534 题 Full；单张 RTX 4090、8 CPU 线程、GPU allocated ≤8 GiB、RSS ≤8 GiB、CPU ≤900 秒、wall ≤1,200 秒。amendment 1 仅容许一次新的 Smoke 启动。

## 实现改动、样本规则与随机种子

项目仓库新增了独立的运行脚本和冻结配置，以便按同一套问题、Schema 和向量输入比较 D0、G1、G3；脚本包含数据与 checkpoint 哈希守卫。运行脚本版本为 `452675a8fa533a69411ad4be88bc27409574ded8`。Amendment 1（`4f2bb334e874869bc7d9f8578d714eec0fa4eef7`）只修正启动器，改为显式使用目标环境的 Python 3.12.15；没有改变模型、数据、特征、指标或阈值。两次尝试都没有进入检索打分。预注册的 G-reasoner `config.json` SHA-256 错写少一个 `a`，导致 `_002` 在哈希守卫处停止。

Smoke 按固定规则选择排序后第一个数据库中的前 5 条源顺序问题，不随机抽样，因此没有 Smoke 抽样种子。预注册的数据库聚类 bootstrap 种子为 `20261106`，但没有运行 bootstrap，也没有产生置信区间。

## 硬件预检

启动前检查了 `nvidia-smi`、`free -h`、`nproc` 和磁盘。机器有 4 张 RTX 4090（每张 24,564 MiB）；检查时各卡只用 14 MiB、GPU 利用率 0%。内存总量 503 GiB、可用约 448 GiB，系统 CPU 192 核，磁盘可用约 112 TiB。任务将 CPU 线程限制在 8。两次失败期间 GPU 仍空闲；没有模型推理资源消耗。

## 执行记录

### `smoke_001`：错误解释器，停止于 PyG 导入

实际启动命令通过 `conda run -n gfmrag_greasoner_20261022` 运行 `python3`，但记录到的解释器是 `/root/miniconda3/envs/python39/bin/python3`，版本为 Python 3.9.20。目标环境本身另有 Python 3.12.15 和正确依赖；未安装、修改或重建环境。

程序在导入 `torch_geometric` 时以 `ModuleNotFoundError` 退出。这发生在实验数据读取、Qwen/G-reasoner 加载、向量编码及任何模型前向之前。退出前没有 Qwen 账本请求。墙钟 1.242 秒、进程 CPU 1.823 秒。

### `smoke_002`：修正解释器后，checkpoint 配置哈希门失败

Amendment 1 将唯一恢复 Smoke 改为明确调用 `/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12`，目标环境版本和包清单核验通过。此时脚本完成了冻结输入哈希检查，并在本地内存中读取问题/Schema 与构造基础 Schema 记录；没有把这些记录送入编码器或模型，也没有读取/评测 Gold 标签内容（Gold 文件只在冻结输入检查中做了 SHA-256 校验）。

接着权重文件哈希通过，但 checkpoint `config.json` 哈希核验停止：

| 项 | SHA-256 |
| --- | --- |
| 预注册配置与 runner 中记录的值 | `75d14b97d6a077ebc17b09a21170a3d9272251db59f7ac8cc853165efb2efd5` |
| 本地冻结 checkpoint `config.json` 的实际值 | `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5` |
| 本地 `model.pth` 实际值（与注册值一致） | `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d` |

配置哈希的预注册值少了一个字符。G-reasoner 参数没有加载；Qwen 快照校验、R1 构造、任何 embedding、任何 G-reasoner 前向均未发生。进程没有占用 GPU；墙钟 8.363 秒、进程 CPU 9.577 秒。程序记录了 5 题 Smoke 样本，但有效打分为 **0/5**。

| 尝试 | 执行代码 commit | 配置 SHA-256 | 实际解释器 |
| --- | --- | --- | --- |
| `smoke_001` | `452675a8fa533a69411ad4be88bc27409574ded8` | `f1dfc0d68a147de698dc1a0e3c08131e4f2a2e0e64c8342d859c9441001605dd` | `/root/miniconda3/envs/python39/bin/python3`，3.9.20 |
| `smoke_002` | `4f2bb334e874869bc7d9f8578d714eec0fa4eef7` | `c944d6372e1797cd82f9503b572ccc898d617069f3daad1d8c6aca1015a290dd` | `/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12`，3.12.15 |

## 指标、成本与停止决定

| 项目 | 结果 |
| --- | ---: |
| 成功完成的 Smoke 问题 | 0/5 |
| Full 问题 | 0/1,534；未启动 |
| Dense / G1 / G3 排序与指标 | 未产生 |
| Column/Table Recall@K、bootstrap CI | 不可计算 |
| G-reasoner 前向 | 0 |
| Qwen 本地 embedding 请求 | 0；输入/输出/总 token = 0/0/0 |
| 外部 API 请求与费用 | 0；无供应商调用或账单费用 |
| GPU 推理时间 | 0 秒 |
| 两次失败进程累计 CPU 时间 | 11.400 秒；本地 CPU 成本未折算为货币 |

amendment 1 明确规定 `_002` 若失败即停止，不再启动第三次 Smoke。故本诊断以 `STOP_NO_SCIENTIFIC_RESULT` 结束；不是核心假设的正向或负向检验。配置哈希 typo 是工程门失败，修复它需要新的正式注册，不能在本报告中补跑或改写历史尝试。

## 产物与复现

- 私有结果与失败收据：`/mnt/liansp3/sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_001/` 和 `/mnt/liansp3/sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_002/`；对应日志为 `/mnt/liansp3/logs/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_001.log` 和 `/mnt/liansp3/logs/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_002.log`。目录独立、权限受限，均未覆盖。
- 汇总文件 [`aggregate_summary.json`](aggregate_summary.json) 只含去标识化的运行状态和计数，不含问题、数据库名、SQL、逐题预测、原始日志或模型文件。
- `_001` 实际使用了未解析到目标环境的 `python3` 入口：

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
conda run --no-capture-output -n gfmrag_greasoner_20261022 python3 \
scripts/text2sql/run_gfm_schema_retrieval_transfer.py \
--mode smoke --run-id gfm_schema_retrieval_transfer_20261106_smoke_001 \
--expected-commit 452675a8fa533a69411ad4be88bc27409574ded8 \
--config configs/text2sql/gfm_schema_retrieval_transfer_20261106.json \
--legacy-root /mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014 \
--dataset-root /mnt/liansp3/sources/datasets/bird/dev \
--embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
--checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --device cuda:0 \
--output-dir /mnt/liansp3/sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_001
```

- `_002` 使用的显式解释器入口为：

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
conda run --no-capture-output -n gfmrag_greasoner_20261022 \
/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 \
scripts/text2sql/run_gfm_schema_retrieval_transfer.py \
--mode smoke --run-id gfm_schema_retrieval_transfer_20261106_smoke_002 \
--expected-commit 4f2bb334e874869bc7d9f8578d714eec0fa4eef7 \
--config configs/text2sql/gfm_schema_retrieval_transfer_20261106_amendment1.json \
--legacy-root /mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014 \
--dataset-root /mnt/liansp3/sources/datasets/bird/dev \
--embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
--checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --device cuda:0 \
--output-dir /mnt/liansp3/sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_002
```

该命令是失败运行的记录，不应在已存在的结果目录上重放。后续若继续同一研究问题，必须先提交新的方案、正确的 checkpoint 哈希和新的 run ID；本报告不授权重试。
