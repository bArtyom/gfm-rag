# P0：冻结 FK 排序对参考 SQL 映射的配对复核（注册 02）

**最终状态：`STOP_SMOKE_GATE`。** Smoke 的 SQL 解析门通过，但 5 个问题×表对里没有一个能将参考 SQL-used FK 映射对齐到冻结候选，低于预注册的 4/5 门槛。按规则未启动 Full；本报告没有排序效果指标。

## 研究问题与方法

此前在三模型代理审阅集合上，冻结 G-reasoner Mapping@1 为 7/38，Dense Cosine 为 27/38。本次原定在相同 55 个非 Smoke 问题×表对、候选和排名上，以原 BIRD dev 参考 SQL 中显式 `JOIN ... ON` 实际使用的已声明 FK mapping 作为评价目标，检查负向诊断是否依赖模型代理标签。

唯一拟改变的量是评价标签；模型分数、候选集合、样本与排序保持冻结。SQL-used 只代表参考 SQL 实际选用的 mapping，不等于唯一语义真值、人工 Role 标签或所有等价关系。Qwen A/B 与 Gemma C 的模型审阅在本次之前已完成；本轮未追加模型审阅，也未把代理多数作为主评价标签。

## 注册和仓库依据

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 独立方案：[预注册计划](../../plans/p0_fk_sql_used_proxy_alignment_20261107_02.md)；[冻结配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107_02.json)。
- 预注册提交：`5f2dcbfdc5d79c0b769914478b549905b7bf3a0f`。执行代码与配置在此提交中冻结。
- Runner：`scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment_20261107_02.py`；SHA-256 `1c1b2230ed3cb5531b612d1b0a69513f21bdac6cc85704d687852ad940da42cd`。
- 本次为独立注册 `_02`。前一注册 `_01` 在输入读取前因 Smoke 输出目录已存在而停止；其报告保留。本次使用新的实验 ID、runner、run IDs 和结果/日志根。两轮均没有覆盖既有数据或实验结果。
- 启动前依照实验室 `AGENTS.md` 阅读项目 `README.md`、Text2SQL `README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 和资源索引。公开仓库仅存方案、代码及匿名汇总；私有 SQL、问题、表名、mapping IDs 和逐题结果不上传。

## 数据、配置与运行环境

- 数据：本地原版 BIRD dev snapshot（1,534 题）；Smoke 使用冻结 split 中 5 个问题×表对，原计划 Full 55 个，Smoke/Full 不重叠。不抽新样本，无新随机种子。
- 固定输入 SHA-256：`dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；pair manifest `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`；frozen rankings `d06f07b2b1000e40dbc0614e9bdbe224a79130010011721b97eccaf3dd9b2484`；split `40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0`。三个已有模型审阅文件的 SHA 见冻结配置；Smoke 对所有输入文件计算哈希，但不解析审阅回复或排名预测。
- Parser：SQLGlot 28.0.0，SQLite dialect。只识别同一显式 JOIN-ON 和 alias pair 内的限定跨表列等式；复合 FK 必须完整匹配全部有序列对。
- 环境：既有 Conda `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；未安装或升级依赖。
- 启动前资源：4×RTX 4090；可用内存约 451 GiB；192 CPU 逻辑核；磁盘可用约 112 TiB。此任务关闭 GPU，限 8 CPU 线程，未加载模型。
- 预算：一次 5 对 CPU Smoke；全部 Smoke 门通过才运行一次 55 对 Full。无 retry、补样、调参、模型调用、API 调用或 GPU。

## 启动命令

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment_20261107_02.py \
--mode smoke \
--run-id p0_fk_sql_used_mapping_alignment_20261107_02_smoke_001 \
--expected-commit 5f2dcbfdc5d79c0b769914478b549905b7bf3a0f \
--repo-root . \
--config configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107_02.json \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_02/smoke_001
```

## Smoke 结果

| 指标 | 结果 | 预注册门 | 状态 |
|---|---:|---:|---|
| SQL parse | 5/5 | 5/5 | 通过 |
| Scope analysis error | 0 | 0 | 通过 |
| 限定 JOIN 等式解析 | 8/8 | 全部 Smoke 等式 | 通过 |
| 完整解析且匹配候选 | 0/5 | 至少 4/5 | **失败** |

运行状态为 `STOP_SMOKE_GATE`。因此 Full 未启动，Mapping@1、Mapping@3、MRR、配对救回/损坏和数据库级排名指标均未计算。结果说明这 5 个 smoke 对没有可用于评分的 SQL-used mapping 与冻结候选交集；仅凭聚合回执无法区分“参考 SQL 所用映射确实不在候选集中”与“映射身份/表对对齐存在问题”，不据此归因 parser 或模型性能。

资源回执：wall 0.043952 秒、CPU 0.026850 秒、峰值 RSS 0.631207 GiB。模型调用 0、外部 API 0、GPU 0；已确认模型 token 输入/输出/合计均为 0，API 估价 CNY 0.00（无 API 请求）。

## 结果文件、异常与结论

- 私有 Smoke 产物：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_02/smoke_001/`。
- 私有日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_02/smoke_001.log`。
- 公开匿名汇总：[aggregate_summary.json](aggregate_summary.json)。公开文件不包含题目、SQL、表名、数据库名、候选身份、逐题行或审阅原文。
- 结论：核心排序假设**未检验**。0/5 候选覆盖触发预注册停止门；不得把本次记录说成 G-reasoner/Dense 的负面排名结果。旧注册 `_01` 和本次 `_02` 都没有产生科学排名结果。
- 下一步：不重试本注册、不扩样、不修改 parser 后复跑。若要继续，需先把问题改成一个有界的候选—SQL mapping identity 对齐审计，并独立预注册；在未解决 label coverage 前，不声称 G-reasoner 的 SQL-used 排序能力。
