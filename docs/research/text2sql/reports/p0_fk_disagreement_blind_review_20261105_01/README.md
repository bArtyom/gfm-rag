# P0 FK 定义分歧双人盲审材料准备

**状态：Smoke 与 Full 材料生成通过；等待两位真实审阅者独立标注。** 本轮没有产生 Role 标签、Role Accuracy、SQL EX 或方法效果证据。

## 1. 研究问题与实验边界

**问题：** packet-28 与 canonical P1.5 对 FK 候选的定义存在逐题分歧。给定由参考 JOIN 得出的表对，能否用冻结的 crosswalk、P1.5 诊断和有效 SQLite 外键实例，稳定抽出分歧与控制样本，并生成不暴露方法来源的双份人工审阅包？

**假设：** 固定输入和哈希后，分层抽样、复合 FK 完整映射、A/B 随机顺序及本地权限门可以重复通过；两位审阅者看到相同问题和候选映射，但看不到题目/数据库 ID、Gold SQL、具体 JOIN 列、分层标签和方法来源。

这是 P0 标签定义与审阅准备阶段的 exploratory 运行，不是方法对照。审阅单元是“问题 × 已给定表对”，表对由参考 JOIN 结构推导，因此本轮只准备条件式映射判断；它不是端到端、Gold-free 的在线评测。BIRD dev 已被多次用于开发诊断，不是独立测试集。

预算最多 54 个分层抽样名额，去重后至少 30 个独立问题；成功条件包括 1,534 个问题键完整对齐、五层配额吻合、完整候选映射、A/B 映射集合一致、顺序打乱和私有权限检查。失败即停止，不以其他题目替换。

## 2. 仓库、指导与代码变更

- 研究仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-disagreement-review-20261105`。
- 预注册基线：`7a65c5564f7be68e506adffcf4b66c213ee5a8bd`；登记后的执行器与配置提交：[`41dcaf5`](https://github.com/bArtyom/gfm-rag/commit/41dcaf54e55ab20035788b06aad7a6a95497a987)。本地执行提交：`b35ccf44ceede9e8b730371b3687ad03646ae1a0`。报告归档提交另见本报告所在分支的最新提交。
- 启动前阅读仓库 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、旧盲审计划以及 canonical crosswalk 报告；执行依照仓库的 P0、隐私和结果归档要求。
- 新增独立执行器 `scripts/text2sql/prepare_p0_fk_disagreement_review_packet.py`；没有修改 QuadGraph/GFM-RAG 的检索、图构建、G-reasoner、SQL 生成或模型权重。
- 启动前静态复核发现初版 launch 清单里的 run ID 与配置不一致；当时尚未调用执行器，也未读取输入。随后更正执行器检查逻辑、冻结新代码哈希并先推送到实验分支，再运行 Smoke。初版 launch 清单保留在本地日志中，并附有更正回执。

## 3. 数据、环境与可复现设置

- 数据：BIRD dev，1,534 题；`dev.json` SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`，`dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- FK 输入：原始 103 个实例、有效 100、无效 3、不同有效映射 99；1 个完全重复声明按冻结规则合并并记录重数。输入哈希见 `experiment_config.json`。
- Crosswalk 和 canonical P1.5 全量结果各覆盖 1,534 个问题键；两个输入文件哈希分别为 `7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e` 与 `746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed`。
- 环境：conda `think2sql_20260909`、Python 3.12.14、SQLGlot 28.0.0；CPU-only，线程上限 8。运行时未调用 GPU、模型、API、SQL 执行或训练；未安装依赖、未下载资源。
- 执行器 SHA-256：`5ef881594e99cd0a4ebed02a04dc130ebf3ef787bf62cb09f5a95a308dc87db0`。种子 `20261105`。每进程上限 600 秒、登记 RSS 上限 4 GiB。
- Full 启动前资源检查：可用内存 446 GiB、磁盘剩余 112 TB、192 个 CPU；GPU 1/2 各占用约 11 MiB，本任务仍指定 CPU-only。Full 实际墙钟 0.082388 秒、CPU 0.080409 秒、峰值 RSS 0.032227 GiB。

Smoke 与 Full 命令均使用以下入口；`{mode}`、`{run_id}` 和输出目录分别取配置中的冻结值：

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
  timeout 600s conda run --no-capture-output -n think2sql_20260909 \
  python3.12 scripts/text2sql/prepare_p0_fk_disagreement_review_packet.py \
  --mode {smoke|full} --run-id {registered_run_id} \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
  --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
  --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_disagreement_blind_review_20261105_01/{smoke|full}/{run_id}
```

## 4. 结果

| 检查项 | Smoke | Full |
|---|---:|---:|
| 状态 | `SMOKE_PASS` | `REVIEW_PACKET_READY_PENDING_HUMANS` |
| 处理问题 | 5 | 49 个唯一问题 |
| 问题 × 表对 | 5 | 51 |
| 数据库数 | 2（仅私有摘要） | 6（仅私有摘要） |
| 问题键对齐 | 1,534 / 1,534 | 1,534 / 1,534 |
| 墙钟 / CPU 秒 | 0.039016 / 0.036406 | 0.082388 / 0.080409 |
| 峰值 RSS | 0.032227 GiB | 0.032227 GiB |

Full 的 54 个分层名额按种子去重后为 49 题；有 2 道题跨表对，因此审阅行共 51。冻结总体与名额如下：

| 分层 | 总体数 | 名额 |
|---|---:|---:|
| packet-only，canonical ambiguous | 22 | 6 |
| packet-only，canonical unmatched | 66 | 6 |
| canonical-only FK match | 15 | 15（全取） |
| canonical-only multi-FK | 21 | 21（全取） |
| 双方均命中且多候选的正向控制 | 173 | 6 |

抽样后独立题数超过 30 的最低门槛。A/B 两份包的题目顺序不同，候选显示顺序在 4 个案例中不同；两份包的候选映射 ID 集合一致。历史 FK 输入的 103/100/3 与 99 个不同有效映射计数复现。所有运行门通过。

这轮没有人工标注，因此可信 Role 标签仍为 0，Role Accuracy 和 SQL EX 不适用。结果只说明冻结的材料准备流程可执行，不能据此判断 packet-28 或 canonical P1.5 哪种 FK 定义更正确，也不能声称方法有提升。

## 5. 产物与隐私

私有结果与日志只保存在本地，未提交到 GitHub：

- Smoke 摘要：`/mnt/liansp3/sources/results/gfmrag_p0_fk_disagreement_blind_review_20261105_01/smoke/p0_fk_disagreement_blind_review_smoke_20261105_01/smoke_summary.json`；SHA-256 `b6764f56b51cfc60e689958180a3a783343ecf82db257e9436239ee212a44f37`。
- Full 匿名聚合：`/mnt/liansp3/sources/results/gfmrag_p0_fk_disagreement_blind_review_20261105_01/full/p0_fk_disagreement_blind_review_full_20261105_01/private_aggregate.json`；SHA-256 `17dd5d0ae813ee71e4ba5dfc6d31c9fe25f9d16c6bb1ebd549341201b2c74cfb`。
- 人工审阅包、两份回复 CSV 和逐题 manifest 位于同一 Full 目录，文件权限 `0600`、目录权限 `0700`；完整私有文件清单在其中的 `sha256sums.txt`。
- 启动收据和 stdout 日志：`/mnt/liansp3/logs/p0_fk_disagreement_blind_review_20261105_01/`，目录权限 `0700`。
- GitHub 仅归档本报告、匿名配置/汇总、计划与执行器。题目文本、Gold SQL、题目/数据库 ID、逐题分层标签、审阅包和回复均未公开。

## 6. 结论与下一步

本轮实现了可重复的双人盲审材料生成，满足预注册的 Smoke、Full、抽样数量和权限门。实验核心未决问题仍是**实际人类审阅者如何判定 FK 映射**；在两位审阅者分别提交决定、映射集合、置信度和简短理由之前，不产生共识标签，不启动 Role Accuracy、query-conditioned Role 训练、P1 角色维度扫描或真实 JOIN 方法实验。

下一步由两位真实审阅者独立填写本地 A/B 回复表。随后仅汇总逐题一致性与分歧类型，按预注册规则形成共识；若无法裁定或候选不完备，应保留为不可判定，不让模型代标。该流程仍受 BIRD dev 的开发集局限约束。
