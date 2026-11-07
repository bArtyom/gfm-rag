# Amendment 004：SQL-used FK mapping ranker CPU 恢复 Smoke

**状态：`FAILED / CPU_BACKEND_UNSUPPORTED`。** 唯一登记的 5-unit CPU Smoke 得到 0/5 个排序结果；RSPMM 阶段报 `No CUDA GPUs are available`。按预注册停止条件，CPU 恢复线关闭，108-unit Full 未运行。这不是排序科学结果，也不改变后续 GPU 运行的标签或配置。

## 研究问题、假设与停止条件

本 amendment 只验证冻结的 G-reasoner 排序能否在 GPU 不可见的 CPU-only 环境完成 5 个单元的 Smoke。若全部候选都有有限分数，且按实际耗时外推后 Full 在预算内，才允许运行一次固定的 108-unit Full。任一运行错误即关闭 CPU 恢复线；不再重试。

主科学比较继承基础方案：BIRD-dev 参考 SQL 显式 `JOIN ON` 使用的 FK mapping 上，G-reasoner 是否优于相同 Qwen3 embedding 的 Dense cosine。标签由 SQL 派生，不依赖审阅者标签。用户选择的 Qwen A/B 审阅仅作次要模型代理；已有 Smoke 高置信精确一致为 2/5，低于 4/5 门，且不代表人工 Role 真值。

## 仓库、方案与执行版本

- 项目仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 运行源提交：[`7801d46206a0aeeaaacad05f80e71961297ee475`](https://github.com/bArtyom/gfm-rag/commit/7801d46206a0aeeaaacad05f80e71961297ee475)。
- 上游参考：`RManLuo/gfm-rag`，固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；实验报告和结果仅归档在用户维护仓库。
- 注册方案：[Amendment 004](../../plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.md)；[冻结配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.json)。配置 SHA-256：`5ad73a6f00f7f45659540cbbe7a211fd0ae362ef3f2d4b6a297b8e71d376a59d`。
- 运行输入：固定 BIRD-dev 样本，Smoke=5、Full=108、4 个匿名数据库；准备 manifest SHA-256 `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0`，来源提交 `566b8e2d9bb244d8868372ae39c887de02f703e9`。CPU 聚合摘要 SHA-256 `b1376e075a4d22afa62b578a0d9fac70d242c8e3a7d482c0a4a64d204f9ac737`。

## 环境、资源与命令

- 环境：`gfmrag_greasoner_20261022`；Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。未安装或升级依赖；模型和 Transformers 处于离线模式。
- 模型：本地冻结 G-reasoner-34M 与 Qwen3-Embedding-0.6B。`CUDA_VISIBLE_DEVICES=""` 隐藏 GPU，CPU 线程上限 8。启动前记录的资源快照（2026-11-07 02:14 UTC）：192 个 CPU、约 436 GiB 可用内存、`/mnt/liansp3` 约 112 TiB 可用磁盘；四张 RTX 4090 中 GPU1 当时较空闲，但本次按已登记方案不使用 GPU。
- Run ID：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery_smoke_001`。未启动 Full。

~~~bash
GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES="" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_sql_used_mapping_rank_20261107_03.py --mode smoke --run-id p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery_smoke_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.json --cpu-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/aggregate_summary.json --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cpu --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/ranker_cpu_smoke
~~~

## 结果与错误

运行器通过数据准备和配置入口后，在 CPU 图评分的 RSPMM 阶段失败，错误为 `RuntimeError: No CUDA GPUs are available`。执行回执记录 `partial_prediction_count=0`，私有 predictions 文件为空，故没有 Mapping@1、Mapping@3、MRR 或候选分数；Smoke 的 5 个单元均未完成排序。Full 未运行，不能把该失败称为负向方法结果。

在失败前，本地 Qwen3 Embedding 已完成 3 次调用，实际记录 1,174 输入、0 输出 token。没有外部 API 调用；公开 API 费用为 CNY 0。账本没有为本地推理套用外部 API 单价，也没有把本地 GPU/CPU 资源折算成账单。运行未记录可用于报告的完整 wall、CPU、RSS 指标。

| 指标 | 结果 |
|---|---:|
| Smoke 目标单元 | 5 |
| 已完成排序单元 | 0 |
| 完整候选映射分数 | 0 |
| G-reasoner 前向 | 0 个有效排名前向 |
| 异常 | `No CUDA GPUs are available` |
| Full | 未运行 |

该结果只说明这套冻结 RSPMM 图评分路径在当前无 GPU 环境下不可用；CPU 导入诊断曾成功加载扩展和模型，但不能证明 CPU 前向可执行。Amendment 004 到此关闭，不用新 run ID 再试 CPU。

## 产物与隐私

- [匿名失败摘要](aggregate_summary.json)
- 私有输出：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/ranker_cpu_smoke/`
- 日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/smoke.log`
- 公开摘要不含样本 ID、SQL、题目、schema、mapping ID 或预测内容；这些数据仅保留在本地私有目录。
