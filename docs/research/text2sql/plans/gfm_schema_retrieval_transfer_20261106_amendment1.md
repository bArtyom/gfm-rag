# Amendment 1：修正环境解释器入口

**状态：已登记；新的 Smoke 尚未运行。** 本 amendment 只修正启动器所用的 Python 路径，不改实验问题、假设、数据、模型、输入、图、锚点、指标、阈值、资源上限或停止门。

## 保留的失败尝试

- 原 Smoke ID：`gfm_schema_retrieval_transfer_20261106_smoke_001`。
- 日志：`/mnt/liansp3/logs/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_001.log`；私有失败与启动记录：`/mnt/liansp3/sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_001/`。
- `attempt_manifest.json` 记录的解释器是 `/root/miniconda3/envs/python39/bin/python3`。因此 `conda run -n gfmrag_greasoner_20261022 python3 ...` 受到现有 PATH 污染，没有调用目标环境的解释器；程序在导入 `torch_geometric` 时停止。
- 失败发生在读取实验数据、载入 Qwen、载入 G-reasoner 及任何前向计算之前。没有模型请求、账本 token、外部 API 请求或 GPU 推理；空的私有预测文件和失败收据保留，不删除、不复用。

## 核实与修正

目标环境目录 `/root/miniconda3/envs/gfmrag_greasoner_20261022` 的 `bin/python3.12` 确认为 Python 3.12.15，且已有 PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。没有安装、升级或重建依赖。

新的启动命令通过 `conda run -n gfmrag_greasoner_20261022` 激活同一环境，并显式调用 `/root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12`，以确保实际解释器和包都来自冻结环境。

## 唯一恢复预算

- 新 Smoke：`gfm_schema_retrieval_transfer_20261106_smoke_002`，结果目录 `sources/results/gfmrag_gfm_schema_retrieval_transfer_20261106_01/smoke_002/`，日志为专属日志根目录下的 `smoke_002.log`。
- 新的 amendment 配置是 `configs/text2sql/gfm_schema_retrieval_transfer_20261106_amendment1.json`。原预注册配置保持不变。若新 Smoke 通过，则仍只运行原定 Full ID `gfm_schema_retrieval_transfer_20261106_full_001`，并使用同一 amendment 配置与原定 Full 结果目录。
- 若 `smoke_002` 失败，停止本诊断，不再启动第三次 Smoke。所有输入哈希、条件、5 题样本规则、1,534 题 Full 规模、成功门和资源限制保持原预注册值。

## 依据

- 原方案：[G-reasoner 表/列检索迁移诊断](gfm_schema_retrieval_transfer_20261106.md)。
- 原冻结配置：`configs/text2sql/gfm_schema_retrieval_transfer_20261106.json`。
- Amendment 配置：`configs/text2sql/gfm_schema_retrieval_transfer_20261106_amendment1.json`。
- 已发布运行代码：`scripts/text2sql/run_gfm_schema_retrieval_transfer.py`。
