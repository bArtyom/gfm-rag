# P0：冻结 FK 排序对参考 SQL 映射的配对复核

**状态：`STOPPED_SMOKE_PREFLIGHT`。** Smoke 在读取数据前因输出目录已存在而停止；没有解析 SQL、计算指标或启动 Full。本报告记录的是执行门失败，不是方法效果结果。

## 研究问题与本轮方法变化

此前在三模型代理审阅集合上，冻结 G-reasoner 的 Mapping@1 为 7/38，Dense Cosine 为 27/38。本次预注册要在完全相同的 55 个非 Smoke 问题×表对和冻结分数上，将评价目标换成参考 SQL 的显式 `JOIN ... ON` 中实际使用的已声明 FK mapping，检查前一负向结论是否依赖代理标签定义。

候选集、模型分数和排序均沿用既有结果；唯一拟改变的是评价标签，从模型代理接受集合改为参考 SQL 使用的映射集合。它不是人类 Role 标签，也不表示参考 SQL 是唯一语义正确答案。本轮没有到达标签读取阶段，因此该对照没有产生数据结果。用户选择的本地模型审阅已在先前的 Qwen A/B 与 Gemma C 报告中完成；本次没有新增审阅或模型推理。

## 注册、代码与数据

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，执行分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 启动前依照实验室 `AGENTS.md` 阅读项目 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md` 与 `reproducibility-contract.md`；本方案按其归档位置、CPU smoke/full 门和隐私规则执行。
- 实验方案：[`p0_fk_sql_used_proxy_alignment_20261107.md`](../../plans/p0_fk_sql_used_proxy_alignment_20261107.md)；配置：[`p0_fk_sql_used_mapping_alignment_20261107.json`](../../../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107.json)。
- 预注册先提交于 `ae6bbef41b322bd92523eca498e32370903d61b8`，完整等式解析资格修订为 `a37a5d4058ab0927c0c74fb4fd5f171123a32f87`；执行代码提交为 `fd9bb12bbb480c6593e30a92ac00073a0e5d2908`。
- 执行代码：`scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment.py`，SHA-256 `a8b22d7733c5fcd6e3111cdcc42e9dd0ed1d365de2f72b677776a96bae057e53`。运行配置与预注册方案锁定同一 runner；本报告不包含任何脚本修改。
- 数据为本地原版 BIRD dev（1,534 题）及其 schema 清单。计划复用既有盲审与排名产物中的 60 对，并按冻结 split 分为 Smoke 5、Full 55。预期输入指纹记录在冻结配置内；本次运行未到达输入哈希检查，故不声称已在本轮重新验证。
- 运行器在检查输出目录时就停止了；Gold SQL、代理标签、排名预测、split 和数据文件均未读取。

## 环境、资源与命令

- 环境：既有 `think2sql_20260909`，执行前确认 Python 3.12.14；未安装或升级依赖。预注册使用 SQLGlot 28.0.0。因运行在输出目录门退出，SQLGlot 版本检查与数据处理没有执行。
- 执行前资源快照：4×RTX 4090，每卡约 11–14 MiB / 24,564 MiB 显存占用；内存可用 451 GiB；192 个逻辑 CPU。任务关闭 CUDA 并限制 CPU 线程为 8，没有分配 GPU。
- 计划预算：一次 5 对 CPU Smoke；仅当 Smoke 通过才进行一次 55 对 CPU Full。无模型调用、训练、外部 API、依赖改动或重试。Smoke 预设门为 5/5 SQL 可解析、0 scope error、5/5 全部限定 JOIN 等式完整解析、至少 4 个候选匹配。
- Full 预定运行 ID 为 `p0_fk_sql_used_mapping_alignment_20261107_full_001`，未启动。无新随机抽样或随机种子；样本次序沿用冻结 split（SHA-256 `40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0`），本次未读取该文件。
- 实际启动命令：

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment.py \
--mode smoke \
--run-id p0_fk_sql_used_mapping_alignment_20261107_smoke_001 \
--expected-commit fd9bb12bbb480c6593e30a92ac00073a0e5d2908 \
--repo-root . \
--config configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107.json \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_01/smoke_001
```

## 执行结果与失败原因

运行器要求 Smoke 输出目录在启动前不存在，并由运行器自行创建。执行准备时提前创建了 `smoke_001/` 空目录；运行器随即返回 `OUTPUT_DIRECTORY_ALREADY_EXISTS`，并明确要求保留现场且不重试。这是本轮启动准备错误，不是数据、依赖或 SQL 解析失败。

| 阶段 | 结果 |
|---|---|
| Smoke 样本读取 / SQL 解析 | 0 / 5；未开始 |
| scope / 等式覆盖 | 未测量 |
| Mapping@1、Mapping@3、MRR | 未测量 |
| Full 55 | 未运行 |
| 本地模型 / 外部 API / GPU | 0 / 0 / 0 |
| 本轮确认模型 token | 输入 0、输出 0、合计 0 |
| API 费用 | CNY 0.00；没有 API 请求 |

日志保留在 `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_01/smoke_001.log`。Smoke 与 Full 结果目录均保留为空；没有结果表、逐题输出或聚合指标。没有读取 SQL 或私有题目内容，也没有写入或覆盖既有实验产物。

## 结论与停止决定

本轮没有验证或否定核心假设，不能据此比较 G-reasoner 与 Dense，也不能将其记成 SQL-used 对照的负结果。按照冻结运行器的停止规则，不重试此注册，Full 不启动。若之后仍要回答同一问题，需另立运行注册，并让运行器创建新的、不存在的输出目录；任何后续结果必须单独记录。

本次无模型/API 调用，故无供应商价格快照或实际账单条目；报告中的 CNY 0.00 指本次无 API 消费，不代表查询供应商账户账单。
