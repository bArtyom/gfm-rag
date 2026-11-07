# Amendment 004 CPU recovery：SQL-used FK mapping ranker

**状态：预注册，未运行。** 本报告记录一次有界 CPU 恢复尝试。Amendment 003 的失败结果和 run ID 保留，不重用。

## 研究问题与判据

测试冻结的 G-reasoner 是否能在 CPU-only 环境完成原 SQL-used mapping ranker 的 5-unit Smoke。Smoke 要求所有候选均有有限分数且完整覆盖；只有通过且按实际耗时外推未超过预算，才运行固定 108-unit Full。Full 正向筛选为 Mapping@1 至少高于 Dense 5pp、净救回不少于4，并且至少两个 `n≥5` 的匿名数据库净救回为正。失败后不再重复 CPU 尝试。

## 方案、版本和复现信息

- 项目：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 执行代码 commit：待预注册推送后填写；Run ID：`p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery_smoke_001`。
- 参考上游：`RManLuo/gfm-rag`，commit `b3e43219c49929da505244df4f0ba54c0947e4c4`。
- 注册方案：[Amendment 004](../../plans/amendments/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.md)；配置：`configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_004_cpu_recovery.json`。
- 输入：沿用已冻结 BIRD-dev SQL-derived manifest（Smoke 5，Full 108，4个匿名库）；不重采样、不修改 SQL-used 标签。
- 模型：本地 G-reasoner-34M 与 Qwen3-Embedding-0.6B 冻结快照；无外部 API、训练或 SQL 执行。
- 环境：`gfmrag_greasoner_20261022`，Python 3.12.15，PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1；CPU≤8线程、GPU 隐藏，离线模式。
- 资源：正式运行前刷新 `nvidia-smi`、`free -h`、`nproc` 和磁盘空间。上次检查四张 RTX 4090 均较忙；可用 RAM 约440 GiB，192 CPU 核。
- 运行命令、精确硬件、时长、token、评价结果和错误：待执行后填写。

此前离线诊断仅导入了 RSPMM CPU 扩展、加载了冻结 G-reasoner 并把模型放置在 CPU；它未读取实验样本，也未做排序前向，不能视为本实验 Smoke 的通过。

## 结果

待运行。无排名指标或科学结论。
