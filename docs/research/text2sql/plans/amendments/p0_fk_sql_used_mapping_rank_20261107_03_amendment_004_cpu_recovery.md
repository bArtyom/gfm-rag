# Amendment 004：SQL-used ranker 的一次 CPU 运行时恢复

**状态：预注册，未运行。** 本 amendment 只回答一个未决工程问题：冻结的 5-unit G-reasoner 排序 Smoke 能否在当前 CPU-only 环境完成。Amendment 003 的失败 run ID 保留并关闭，本 amendment 使用独立 run IDs、日志和结果目录。

## 研究问题、假设和层级

核心科学假设继承基础注册：在 BIRD-dev 参考 SQL 显式 `JOIN ON` 使用、且至少有两个有效 FK mapping 候选的表对上，冻结 G-reasoner 相比同一 Qwen3 embedding 的 Dense cosine 是否提高 SQL-used set-valued Mapping@1。

本次层级为一次 exploratory 主排序可行性 Smoke，成功后最多一次固定 Full。其工程触发证据是：Amendment 003 在 RSPMM 扩展加载期间报 `No CUDA GPUs are available`；之后，在相同 Conda 环境、隐藏 CUDA、关闭在线下载的诊断中，仓库内 CPU RSPMM 扩展成功导入，冻结 G-reasoner 的 34,640,897 个参数成功加载并置于 CPU。诊断没有读取题目、SQL 或标签，也没有执行模型前向。因此这只能支持再做一次受控 Smoke，不能当成实验结果。

## 不变项与停止条件

- 不改变原 Smoke/Full 单元、SQL-derived 标签、候选集、模型权重、图构造、评分、seed、指标或正向门；不运行训练、SQL 或外部 API。
- 用户选择的模型 A/B 审阅作为次要代理分析保留。此前 Smoke 的高置信精确一致为 2/5，低于 4/5，故不补跑、不扩到 reviewer Full；它不构成主排序的标签门，主标签完全由冻结 SQL 派生。
- Smoke 固定 5 个单元。须对每个候选产生有限分数且覆盖完整。任何错误即关闭此 CPU 恢复，不再重复 CPU 尝试。
- 只有 Smoke 完整通过，且按 Smoke 的实际 CPU/wall 时间外推后 Full 可在 900 CPU 秒、1,800 wall 秒、8 GiB RSS 内完成，才运行一次固定的 108-unit Full。否则停止并保留 Smoke 结果。
- Full 正向筛选沿用原门：G-reasoner−Dense Mapping@1 ≥ +5pp、配对净救回 ≥4，且至少两个各有 `n≥5` 单元的匿名数据库净救回为正。若通过，只升级为独立留出评估候选。

## 版本、资源和数据

- 项目仓库：`https://github.com/bArtyom/gfm-rag`；分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 本文、配置和最小运行器变更须在任何 Smoke 前推送到项目分支；运行器记录正式执行 HEAD。参考上游保持 `RManLuo/gfm-rag` 固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，不向上游写入。
- 基础配置 SHA-256：`d965ee4f5250193f5fd3a53d82c59a55ca95c97c9bb0980008d4a907c27b9db4`。
- 前序 Amendment 003 SHA-256：`ade0769d6b18ae58f28a29694f5d7cbc6fe8b8ac3d800869d5d8e36b903ad929`。
- 数据准备来源 commit：`566b8e2d9bb244d8868372ae39c887de02f703e9`；复用其既有 Smoke=5、Full=108 的私有 manifest 与摘要，不重采样、不复制数据。
- 环境：`gfmrag_greasoner_20261022`，Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1；最多 8 CPU 线程，GPU 完全隐藏，HF/Transformers 离线。不安装或升级依赖。
- 开工资源检查必须重跑 `nvidia-smi`、`free -h`、`nproc` 和磁盘检查。近期快照：四张 RTX 4090 均约 76–78% 利用率，各有约 7.7–8.0 GiB 空闲；系统约 440 GiB 可用 RAM、192 CPU 核。故本次 CPU-only，不启动新的 GPU 负载。
- 私有结果：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery/`。新目录必须不存在；旧运行结果不覆盖。
- Run IDs：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery_smoke_001`；通过预算门时才用 `p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery_full_001`。

## 结果解释边界

Smoke 只能证明（或否定）当前执行环境下排序前向可运行。只有 Full 产出全部冻结指标后才能判断这一重复 BIRD-dev 子集上的相对排序；本结果不是真实业务 Role 准确率、不代表独立泛化，也不能推翻另一个模型代理标签实验的 NO-GO。失败则报告无科学排名结论，并结束此 CPU 恢复线。
