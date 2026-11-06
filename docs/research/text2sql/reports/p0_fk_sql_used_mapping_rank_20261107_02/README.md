# SQL-used FK mapping 独立注册 02：启动停止报告

**状态：`STOP_SOURCE_COMMIT_MISMATCH`，停止于数据读取前。** 新运行没有检查输入文件哈希、反序列化题目或 SQL、构造样本、生成 A/B 模型审阅包或运行任何模型。没有科学指标，本报告不代表 G-reasoner 的正面或负面结果。

## 研究问题与预注册判据

研究问题：在 BIRD dev 参考 SQL 的显式 `JOIN ON` 确实使用一个完整 FK mapping，且端点表对至少有两个有效候选的前提下，冻结 G-reasoner 是否比共享 Qwen embedding 的 Dense cosine 更常把 SQL-used mapping 排在第一？这属于同一开发数据上的探索性目标对齐诊断，不测人工语义 Role 准确率、端到端 JOIN 发现或 SQL 执行。

预注册的 CPU 门要求 5 个 Smoke 单元均完整解析且 SQL-used mapping 在候选集合中；排除 Smoke 后，Full 至少 30 个候选覆盖单元并覆盖至少 3 个匿名数据库。通过后才会调用两名本地模型做次要盲审并运行一次 G-reasoner Smoke/Full。主要正向筛选门是 Mapping@1 至少比 Dense 高 5 个百分点、净救回至少 4 个单元、并在至少两个各有 `n≥5` 的匿名数据库净救回为正。此门只决定是否考虑未来独立留出实验，不等于确认性结论。

完整预注册见[方案](../../plans/p0_fk_sql_used_mapping_rank_20261107_02.md)、[主配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_02.json)及[模型审阅配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_02_model_review.json)。

## 仓库、指导和代码版本

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 预注册 commit：[`de1b8a7`](https://github.com/bArtyom/gfm-rag/commit/de1b8a7ed69c175cf08ddc2eecc947a2cb16dc1f)。远端文件逐一读回，与本地预注册文件内容一致。其代码树也与本地运行工作树提交 `ca73a0afd92c72373b9a12858b508fe9dbf53c2f` 完全一致；本地提交的 SHA 元数据不同。
- 执行前已阅读仓库根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 及 `/mnt/liansp3/sources.md`。代码参考为 Apache-2.0 上游 `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；没有向上游写入。
- 新增独立的 prepare、G-reasoner ranking 和模型审阅聚合入口。实验 ID、样本 hash 和输出路径均为 `_02`，旧 `_01` 运行及产物未改动。预注册和实现提交前未读取 BIRD 问题或 SQL 内容。
- 主配置 SHA-256：`21479bf95a303c0b23f2ccf8f6935dd44648ce6b25505608aee9b8dd42a0066c`；模型审阅配置 SHA-256：`f873152cf1df8f451230584c735c6b000c9f0a15d04c6f7fb167125ce1513195`。

## 数据、模型和环境

- 计划数据为本地冻结 BIRD dev、canonical FK/crosswalk/P1.5 Full，以及既有 60 单元排除 manifest。各路径和登记 SHA 见公开主配置。排除 manifest 当前独立 SHA 为 `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`；它在本次运行中没有被读取或哈希核验。
- 计划主模型为本地冻结 G-reasoner-34M 与 Qwen3-Embedding-0.6B。按用户选择，次要审阅为本地 Qwen2.5-Coder-7B 与 Qwen3-4B-Think2SQL；审阅者不会看到 Gold SQL、SQL-used mapping、模型分数或另一审阅者的输出。**所有模型均未加载或调用。**
- CPU 目标环境为 `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0；显式调用目标环境解释器。运行前资源快照：4 张 RTX 4090 均空闲；可用内存约 450 GiB，磁盘可用约 112 TiB，192 个逻辑 CPU。该 CPU 阶段不需要 GPU。
- 未安装、升级或重建依赖；未下载模型或数据；未运行 SQL。

## 执行与停止原因

唯一运行 ID：`p0_fk_sql_used_mapping_rank_20261107_02_cpu_001`。启动命令传入了错误的 `--expected-commit`：

```text
ca73a0a4a894d1960362fcf514725c5fe567fe08
```

实际本地 HEAD 是：

```text
ca73a0afd92c72373b9a12858b508fe9dbf53c2f
```

脚本在当前分支检查后立即因 `SOURCE_COMMIT_MISMATCH` 退出，尚未进入输入哈希检查。错误在本轮启动参数的人工抄录，不是数据文件或模型配置损坏。失败收据保存在权限受限目录，日志保留完整命令。该 run ID 已关闭，不再重放；本报告归档后，本任务因连续启动完整性失败暂停实验执行。

复现失败记录的命令如下；它只用于解释已停止运行，不应重放：

```bash
conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/prepare_p0_fk_sql_used_mapping_rank_20261107_02.py \
  --run-id p0_fk_sql_used_mapping_rank_20261107_02_cpu_001 \
  --expected-commit ca73a0a4a894d1960362fcf514725c5fe567fe08 \
  --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 \
  --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_02.json \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
  --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
  --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_02/cpu_001
```

## 结果、资源与成本

| 项目 | 结果 |
|---|---:|
| 数据输入 hash 检查 / SQL 解析 | 未开始 / 未开始 |
| 样本、Smoke、Full | 0 / 0 / 0 |
| A/B 模型审阅包或输出 | 未生成 / 未运行 |
| G-reasoner、Dense、Qwen embedding | 未运行 |
| Mapping@1、Mapping@3、MRR、配对救回 | 未测量 |
| 本轮模型调用 / 已确认 token | 0 / `0 input + 0 output = 0 total` |
| 未知用量请求 | 0 |
| 外部 API 费用 / 账单 | CNY 0.00 / 无外部请求、无账单 |
| GPU 推理时间 | 0 秒 |
| 命令总耗时 | 执行器约 6 秒（含 conda 启动）；失败发生在实验计时器开始前 |

私有失败回执：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_02/cpu_001/failure.json`；私有日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_02/cpu_001.log`。未产生题目、SQL、schema、review packet、mapping ID 或逐题分数。

## 结论与边界

这次运行只说明启动时的来源提交守门生效，**不检验核心假设**。按预注册与实验室守则，保留失败现场并停止本注册；本轮不改 run ID、不补跑、不加载模型。今后若重新研究该问题，须另立注册，并直接从目标 worktree 查询完整 HEAD SHA 注入命令或由运行脚本自动比较，避免人工抄写。该建议不改变本次停止状态。
