# Amendment 003：固定 SQL-used ranker 的本地 CPU 执行

**状态：预注册，未运行。** GPU 版 Amendment 002 尚未启动。启动前复查发现四张 GPU 均处于高利用率，GPU 3 仅余 7,918 MiB，低于实验 8 GiB 显存上限。为避免和其他作业争抢显存，本 amendment 将同一冻结的 Smoke/Full 排序任务改为 CPU 执行。

## 实验问题和范围

核心问题、样本、目标标签、候选集、G-reasoner 和 Qwen3 Embedding 快照、图结构、seed、指标、+5pp/4 个净救回/两库正向阈值全部继承基础预注册。SQL-used mapping 仍由冻结 SQLGlot 规则提取，Gold SQL 与派生目标不进入模型输入。用户选择的本地 Qwen A/B 审阅仍以 2/5 高置信精确一致停止，不运行 reviewer Full。

唯一执行变更是把排序模型和 Embedding 移至 CPU，隐藏 CUDA 设备并限制最多 8 个线程。CPU Smoke 固定使用原 5 个预选单元；只有 Smoke 全部成功，才运行一次原定 108 单元 Full。Full 保留 1,800 秒 wall、900 秒 CPU、8 GiB RSS 上限；任何越限或非有限/缺失分数都停止。不重新准备样本，不更改依赖或模型，不调用外部 API，也不执行 SQL。

## 代码与资源记录

- 资源快照：4 张 RTX 4090 的 GPU 利用率为 78–80%；GPU 3 空闲显存为 7,918 MiB，低于注册的 8 GiB；系统可用内存约 446 GiB、192 个 CPU 核。CPU 执行限制为 8 线程。
- 环境：复用 gfmrag_greasoner_20261022，显式 Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。
- 基础配置 SHA-256：d965ee4f5250193f5fd3a53d82c59a55ca95c97c9bb0980008d4a907c27b9db4。
- GPU Amendment 002 配置 SHA-256：ccef27daaf32df29b0344c9a0315d73583b2e06572caf1253177a1004fc54360；未运行。
- CPU 清单来源提交：566b8e2d9bb244d8868372ae39c887de02f703e9。运行前运行器会核验 CPU summary 与私有 manifest 的 SHA、来源提交、ID 唯一性和预设 5/108 单元数。
- 使用新的 CPU-only run ID 和独立私有输出、日志目录；原失败及未运行的旧 run ID 均不复用。
- Smoke run ID：p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu_smoke_001。
- Full run ID：p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu_full_001；仅在 Smoke 全部通过后运行。
- 私有输出：/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/；日志：/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/。

## 结果解释

此为冻结排序方法的 CPU 执行恢复，不是新模型、训练或算法对比。若通过原正向筛选，只进入独立留出评估候选；BIRD dev 结果不能作为独立泛化或论文主张。
