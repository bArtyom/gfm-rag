# P0 BIRD FK 图 Hop Profile — 初次完整运行

**运行器状态：`FULL_COMPLETED`。复核状态：`SUPERSEDED_PENDING_SCOPE_CORRECTION`。** Smoke 与 Full 均完成，但事后代码检查发现 SQL 表抽取使用全查询 CTE 名称集合过滤表名，可能误删其他作用域中的同名真实表。本报告保留原始运行及指标；在 scope-aware 修正复跑前，不把该画像作为最终 BIRD hop 分布。

## 研究问题与边界

本审计询问：BIRD dev 的 SQL 涉及表集合，在声明式 FK 无向表图上的精确最小 Steiner 边数分布是什么？它只用于判断 BIRD dev 是否值得进一步作为高 hop 结构分层的候选数据源。

本轮不使用人工 Role 标签，不评估 GFM、Dense、BM25、JOIN 候选或 SQL EX，不训练、不调用模型/API、不执行 SQL。BIRD dev 是已反复使用的开发诊断集，不是独立测试集。预注册判据为：至少 30 道连通且 `h≥3` 的题，分布于至少 3 个数据库；该阈值只是资源筛选线，不是统计功效或方法效果门槛。

## 仓库指导与代码

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-disagreement-review-20261105`。
- 启动前遵循仓库 `README.md`、Text2SQL README、实验路线图及复现规范；初次预注册、配置和 runner 见 commit [`b9d6d00`](https://github.com/bArtyom/gfm-rag/commit/b9d6d0013b2acae8d25b512b90fe3d24eb886725)。
- 原始 runner：`scripts/text2sql/audit_bird_fk_hop_profile.py`，SHA-256 `c4905341a9dbd427934109e1f70a22d5ad56dfe8ab9359683f306964fa3e7e5a`。
- 配置：`configs/p0_bird_fk_hop_profile_20261105.yaml`，SHA-256 `0c42e7305a8e96f97f3ae084a7a739e9400b100099ed2a88ce1b35212ab3ed40`。

**复核发现：** 初次 runner 收集整个 SQL AST 的所有 table 名，再从全查询 CTE 别名集中排除同名名称。CTE 别名是作用域内的；如果某个作用域引用与另一作用域 CTE 同名的真实数据库表，v1 会误删该基础表。当前没有逐题核验该情况是否实际发生，因此不将其描述成已确认的逐题错误；但 v1 的 100% 表映射门不能排除这种漏计。已另行登记 scope-aware parser 修正，不改写本次文件或结果，见 [v2 修正计划](../../plans/p0_bird_fk_hop_profile_v2_correction_20261105.md)。

## 数据、配置与运行环境

- BIRD dev：1,534 题、11 个 schema；`dev.json` SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`，`dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- Hop 定义：声明 FK 列映射投影到无向表对图；重复端点映射折叠为一条图边。对 SQL 中不同表终端，以 Dreyfus–Wagner 子集 DP 求精确无权最小 Steiner 边数，最多 12 个终端。
- Python 3.12.14、SQLGlot 28.0.0、PyYAML 6.0.3；使用本地 `think2sql_20260909` 环境的显式 Python 3.12 解释器。CPU-only，runner 线程上限 4。
- 启动前 Full 资源快照：内存可用 439 GiB，CPU 192 线程，磁盘可用 112 TB。GPU 0/3 当时有其他任务占用；本轮未使用 GPU。无模型/API token、GPU 小时、SQL 执行或依赖安装。
- 随机种子：无；计算确定性。完整运行命令：

```bash
timeout 600s conda run --no-capture-output \
  -p /root/miniconda3/envs/think2sql_20260909 python3.12 \
  scripts/text2sql/audit_bird_fk_hop_profile.py \
  --mode full --run-id p0_bird_fk_hop_profile_full_20261105_01 \
  --config configs/p0_bird_fk_hop_profile_20261105.yaml \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_01/full
```

## Smoke 与 Full 结果

Smoke 处理 5 题，全部解析且表名映射完整，状态 `SMOKE_PASS`。Full 处理 1,534/1,534 题，runner 返回 `FULL_COMPLETED`；每题归入一个状态，全部表名在 schema 中可映射。

| 指标 | v1 结果 |
|---|---:|
| 声明 FK 列对 / 唯一无向表边 | 102 / 72 |
| FK endpoint 无效 | 0 |
| FK 图连通题 | 1,457 / 1,534 |
| 声明 FK 图不连通题 | 77 / 1,534 (5.02%) |
| `h=0 / 1 / 2 / 3 / 4`（仅连通题） | 363 / 849 / 209 / 35 / 1 |
| 连通 `h≥3` | 36 / 1,534 (2.35%)，覆盖 5 个数据库 |
| 单库最高 `h≥3` 题量 | 18 / 36 |
| 连通 `h≥4` | 1 / 1,534 (0.07%) |

按最初资源筛选门，v1 的 `h≥3` 数量与数据库数均达到阈值。但题量偏少、半数集中在一个数据库，`h≥4` 仅 1 题；这不足以支持高 hop 方法结论。

## 外部对照与解释

SchemaScope 论文在 BIRD dev 上报告约 22% 的问题属于 `h≥3`。本次 v1 得到 2.35%，相差约一个数量级。[SchemaScope (SURGeLLM 2026)](https://aclanthology.org/2026.surgellm-1.17/) 论文与本轮均声称使用 BIRD dev，但我尚不能确认 schema 图构建、表终端抽取和 hop 操作细节是否完全一致。加上上述 CTE 作用域风险，本结果不能据此声称推翻论文数字；差异仍需在修正解析器后复核。

另外，77 道题在声明 FK 表图上断开。`h` 只表示该 FK 图上的结构距离；它不说明 SQL 是否业务正确，也不说明缺失连接应如何补齐。连接不上的题没有被硬塞进 hop histogram。

## 产物、异常与下一步

- 本地 Smoke 汇总：`local:results/gfmrag_p0_bird_fk_hop_profile_20261105_01/smoke/aggregate_summary.json`，SHA-256 `da2420f617834c2c451a45328da957654a54dd5d3b5d7449034309ddd0d1fc13`。
- 本地 Full 匿名汇总：`local:results/gfmrag_p0_bird_fk_hop_profile_20261105_01/full/aggregate_summary.json`，SHA-256 `5fdd7c442e196ac2593bad7d6c7e8eb17dd109fe4abdb5b9bf214d31211d3e3a`。本报告附同一聚合 JSON；没有导出题目、数据库 ID、问题文本、Gold SQL 或逐题 hop。
- 本地运行日志：`local:logs/p0_bird_fk_hop_profile_20261105_01/`。
- 运行过程中没有运行失败或数据损坏；运行后复核发现解析实现风险。因此保留原始产物并做版本化修正，不能用 v1 指标直接挑选下一方法实验。
- v2 只修正 SQL 表引用的作用域解析，以新配置、新 run ID、新 smoke/full 目录运行一次。若 v2 与 SchemaScope 仍有大差异，停止该 BIRD hop 方向的拓展，把定义差异记为未决；无论结果如何，双人 Role 标签仍是 FK 映射排序实验的前置条件。
