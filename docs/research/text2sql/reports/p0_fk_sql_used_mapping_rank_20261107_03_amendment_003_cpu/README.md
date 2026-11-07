# Amendment 003 CPU Smoke：SQL-used FK mapping ranker

**状态：STOPPED_DURING_MODEL_IMPORT；无排名结果。** 该次 5 题 Smoke 在导入 G-reasoner/RSPMM 依赖时因当前包要求 CUDA 而停止。5 题中评分 0 题；Embedding 和 G-reasoner 均未前向，因此没有 Mapping@1、Mapping@3、MRR 或配对救回指标。此结果不支持或否定 G-reasoner 相对 Dense 的假设。

## 研究问题、层级和停止规则

继承 p0_fk_sql_used_mapping_rank_20261107_03 的 exploratory SQL-used FK mapping 主排序：在参考 SQL 明确使用、且有多个有效 FK mapping 候选的固定 BIRD-dev 表对中，比较冻结 G-reasoner 与共享 Qwen3 向量的 Dense cosine。目标是 SQLGlot 从显式 JOIN ON 派生的 mapping，不是人工业务 Role 真值，也不是端到端 JOIN 检测或 SQL Execution。

基础注册要求 Smoke=5/5 候选完整且分数有限，之后才可对固定 Full=108 运行一次。Full 的正向筛选仍为 Mapping@1 至少 +5pp、净救回至少 4，且至少两个各有 n≥5 的匿名数据库净救回为正。成功也只进入独立留出评估候选。

用户要求使用模型审阅。前一阶段已由两位本地 Qwen 分别审阅 5 题，各自有效输出 5/5，但高置信精确一致仅 2/5，低于冻结的 4/5 门槛；模型审阅 Full 已停止。该门是次要代理分析，不约束 SQL-derived 主排序标签。

## 为什么改为 CPU，以及执行版本

GPU Amendment 002 预注册后、启动前的资源检查显示四张 RTX 4090 的利用率为 78–80%；指定 GPU3 空闲显存 7,918 MiB，低于 8 GiB 上限。系统可用内存约 446 GiB、192 个 CPU 核。为避免占用忙碌显卡，Amendment 003 改为 CPU-only、最多 8 线程，保留同一输入、模型、图、指标和阈值。

- 用户维护仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)
- 分支：research/p0-sql-used-proxy-alignment-20261107
- 执行代码 commit：[27d4bb39ad4fcbcade4ae3fb88198f82723d88a4](https://github.com/bArtyom/gfm-rag/commit/27d4bb39ad4fcbcade4ae3fb88198f82723d88a4)
- CPU 执行预注册：[Amendment 003](../../plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu.md)；基础方案：[注册 03](../../plans/p0_fk_sql_used_mapping_rank_20261107_03.md)
- CPU 配置 SHA-256：ade0769d6b18ae58f28a29694f5d7cbc6fe8b8ac3d800869d5d8e36b903ad929
- 基础配置 SHA-256：d965ee4f5250193f5fd3a53d82c59a55ca95c97c9bb0980008d4a907c27b9db4
- 数据准备来源 commit：566b8e2d9bb244d8868372ae39c887de02f703e9
- 私有 prepared manifest SHA-256：cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0
- Run ID：p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu_smoke_001；该停止运行不重用。

输入仍是同一冻结 BIRD-dev 样本：Smoke 5、Full 108、覆盖 4 个匿名数据库。候选、SQL-used 标签和清单均未重新生成。准备清单哈希和来源提交匹配。G-reasoner checkpoint 的 model/config SHA-256 在启动前与配置一致；Qwen3 Embedding 的运行时指纹检查尚未到达。

环境为 gfmrag_greasoner_20261022，显式 Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。GPU 隐藏，CPU 限 8 线程。无依赖安装、下载、SQL 执行、训练或外部 API。

## 执行命令

~~~bash
GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES="" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_sql_used_mapping_rank_20261107_03.py --mode smoke --run-id p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu_smoke_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu.json --cpu-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/aggregate_summary.json --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cpu --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/ranker_cpu_smoke > /mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/smoke.log 2>&1
~~~

## 执行结果和异常

| 检查项 | 结果 |
|---|---|
| run status | FAILED / STOPPED_DURING_MODEL_IMPORT |
| 错误 | RuntimeError: No CUDA GPUs are available |
| 运行日志 | Load rspmm extension. This may take a while... 后报错 |
| 选中 Smoke 单元 | 5 |
| 已评分单元 | 0 |
| Embedding 前向 | 未开始 |
| G-reasoner checkpoint 加载 / 前向 | 未开始 |
| 排名指标 | 未产生 |
| 私有预测文件 | 0 bytes |
| 外部 API / token | 0 请求 / 0 输入 / 0 输出 |
| GPU 推理时间 | 0 秒 |

失败发生在加载 G-reasoner/RSPMM 运行依赖时，早于版本检查、Qwen3 编码和 G-reasoner checkpoint 加载。当前环境中的该 import 路径尝试初始化 CUDA，因此不能通过隐藏 CUDA 设备来运行 CPU Smoke。若要支持纯 CPU，需改变或重建 G-reasoner/RSPMM 运行路径；这会超出本次冻结实验的最小执行恢复，不能将本次失败通过修改模型核心实现来修复。

该 run 的私有诊断文件位于 /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/ranker_cpu_smoke/，日志位于 /mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_003_cpu/smoke.log。报告与匿名汇总不包含问题文本、SQL、schema、逐题 ID、mapping ID 或模型回答。

## 结论与下一步

CPU 回退路径在当前 G-reasoner 环境不可用。唯一有效的下一步仍是等指定 GPU 有足够空闲显存后，按 GPU 预注册执行未启动的 GPU Smoke；启动前重新检查硬件并保留安全余量。此次没有排名证据，不能据此判断方法优劣。不得继续追加 CPU 重试或改动 G-reasoner 内核来规避该失败。
