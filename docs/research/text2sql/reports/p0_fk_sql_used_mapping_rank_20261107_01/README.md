# P0 SQL-used FK mapping rank：执行报告

**状态：`STOPPED_BEFORE_PARSE`。** 本报告记录预注册实验在输入完整性门失败后的结果，不是 G-reasoner 排序结果。冻结文件只被读取以计算 SHA-256；未反序列化数据集、未读取题目或 SQL 字段、未解析 SQL/schema，也没有建立样本或运行模型审阅与排名。

## 研究问题与预注册判据

研究问题：在参考 SQL 明确使用某个 FK mapping，且该表对至少有两个有效候选 mapping 的新样本上，冻结 G-reasoner 是否比共享同一 Qwen embedding 的 Dense cosine 更常把 SQL-used mapping 排在第一？目标是 SQL-used mapping 排序，不能解释为人工语义 Role 正确率或端到端 JOIN 发现能力。

预注册成功筛选门为 G-reasoner 相对 Dense 的 Mapping@1 至少提高 5 个百分点、净救回至少 4 个单元，并且至少两个样本数 `n≥5` 的匿名数据库各自净救回为正。CPU 数据容量门要求 Smoke 之外至少 30 个完整且候选覆盖的单元、覆盖至少 3 个匿名数据库；未通过前禁止模型运行。另按用户要求登记了两个独立本地模型审阅者，但审阅标签只作次要代理分析，不能替代人工真值或进入主排序输入。

## 执行结论

CPU 首轮 `_001` 曾在 exclusion-manifest 哈希检查处停止，回执没有保存实测值。按 Amendment 002 预注册的唯一一次新 ID 恢复 `_002` 也在同一检查处停止。恢复回执记录：

| 项目 | SHA-256 |
|---|---|
| 冻结登记值（expected） | `14d3e65e53bbc29c03d312fb32227c47b568242502d30bc3c4d4656b97521ed7` |
| 执行时实测值（observed） | `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7` |

两值不同。独立 `sha256sum` 对同一路径所得值与 `_002` 回执中的 observed 值相同。Amendment 002 配置中的 `independent_check.observed_sha256` 错误地复制了 expected 值；更正记录已追加在 Amendment 002 方案末尾，冻结配置本身保留不改。一次恢复额度已用完，按停止规则不再尝试、不改登记哈希、不替换输入。

**因此本实验没有主指标、代理标签指标或效果结论。** 这是输入校验停止，不能视为支持或反驳 G-reasoner 假设。Reviewer A/B 均未启动，GPU 排序也未启动。

## 数据与代码版本

- 项目仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 执行脚本、一次性恢复方案及配置的 GitHub 来源提交：[`3329dc0`](https://github.com/bArtyom/gfm-rag/commit/3329dc0cb029c1047147720616baebd707637613)。该提交先于 `_002` 运行；报告提交随后归档。
- 实验指南：仓库根 `README.md`、`docs/research/text2sql/README.md`、`docs/research/text2sql/experiment-roadmap.md`、`docs/research/text2sql/reproducibility-contract.md`、主实验计划及 Amendments 001/002。计划与资源/隐私规则无冲突；本次因注册 SHA 与输入字节不同而按哈希门停止。
- 主配置：`configs/text2sql/p0_fk_sql_used_mapping_rank_20261107.json`，SHA-256 `258249f042638fef36e20a2afe0877096364e259de5000414a546d1df4dd79cd`。
- 恢复配置：`configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_amendment_002_hash_gate_recovery.json`；它保留了 above-mentioned expected/observed 抄录错误，方案附录和本报告给出可审计更正。
- 被校验输入包括 BIRD dev `dev.json`（`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`）、`dev_tables.json`（`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`）、FK artifact（`5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`）、canonical crosswalk（`7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e`）、canonical Full（`746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed`）和 60-unit exclusion manifest。前五项匹配冻结哈希；exclusion manifest observed 值与上表一致，未通过门。
- 代码只增加了对唯一恢复 ID/config 的显式校验，并使停止原因打印 expected 与 observed 哈希；数据定义和成功判据没有更改。

## 环境、资源及命令

- CPU 环境：Conda `think2sql_20260909`，Python 3.12.14，SQLGlot 28.0.0；没有安装或升级依赖。
- 运行前资源：192 CPU 核；内存 503 GiB 总量、449 GiB 可用；数据盘可用 112 TiB。`nvidia-smi` 显示 GPU2 在用（14,355/24,564 MiB、61% 利用率），其他卡基本空闲。本阶段为 CPU 校验，不使用 GPU。
- 实际运行 ID：`p0_fk_sql_used_mapping_rank_20261107_cpu_002`。Shell 命令耗时约 5.17 秒（含 conda 启动）；脚本因哈希差异立即停止，未保存峰值 RSS 或进程 CPU 时间。
- 复现命令：

```bash
conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/prepare_p0_fk_sql_used_mapping_rank_20261107.py \
  --run-id p0_fk_sql_used_mapping_rank_20261107_cpu_002 \
  --expected-commit 3329dc0cb029c1047147720616baebd707637613 \
  --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 \
  --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107.json \
  --amendment-config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_amendment_002_hash_gate_recovery.json \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
  --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
  --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_002
```

## 样本、指标与产物

- 解析样本：0；候选 mapping：0；Smoke/Full：均未生成；随机种子：不适用（采样阶段未开始）。
- SQL-used Mapping@1、Mapping@3、MRR、候选覆盖率、G-reasoner/Dense 救回与损坏：均未测量。
- 模型版本（计划但未运行）：Qwen2.5-Coder-7B-Instruct 与 Qwen3-4B-Think2SQL；无输入/输出 token。G-reasoner-34M 和 Qwen3-Embedding-0.6B 未加载。
- 本轮外部模型 API 请求数与费用：0，CNY 0.00；本地 GPU 推理时间：0。
- 私有失败回执：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_002/failure.json`；私有日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_002.log`。二者权限分别为 0600，保留在本机，不上传。
- 本报告目录：`docs/research/text2sql/reports/p0_fk_sql_used_mapping_rank_20261107_01/`。聚合状态见同目录 `aggregate_summary.json`。
- 未上传问题文本、SQL、schema 内容、逐题身份、候选/排名、审阅包或模型原始输出。

## 解释与后续边界

结果是一次透明记录的完整性门失败，而不是模型比较结果。Amendment 002 的唯一恢复额度已耗尽；本实验不再有 CPU 重跑、哈希修正或模型运行。任何新的研究运行都必须作为独立注册先解决输入版本与 SHA 来源问题，并不能复用本次停止记录冒充结果。
