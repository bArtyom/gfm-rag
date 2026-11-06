# P0 多 FK 映射实例级可区分性审计

**最终状态：POSITIVE_INSTANCE_EQUIVALENCE_SIGNAL。** 固定 BIRD dev Full 样本中，94 个完整且 Gold 输出非空的单元里，有 54 个至少存在一个替代 FK mapping，在对应 SQLite 实例上返回与参考 SQL 完全相同的结果 Bag：54/94 = **57.45%**（Wilson 95% 区间 47.35%–66.96%）。这超过预注册的 10% 正向信号门。

这只证明“在当前固定数据库实例上输出相同”，不证明一般 SQL 语义等价、业务 Role 正确、用户意图相同，也不是 G-reasoner 排序或 Text-to-SQL EX 结果。数据库间差异明显，见分层指标。

## 研究问题与预注册

研究问题：固定 Gold SQL，只替换一个显式 JOIN-ON alias pair 的 FK 等式 bundle，其他 SQL AST 和谓词保持不变；当前 BIRD SQLite 实例上有多少非 SQL-used mapping 会给出与 Gold SQL 相同的结果？

核心假设：在可安全替换且 Gold 输出非空的 Full 单元中，至少 10% 有一个替代 FK mapping 与 Gold SQL 的结果 Bag 相同。≤5% 为弱信号；5%–10% 为 inconclusive。Smoke 只检验执行链，不用于接受或拒绝该假设。

这是 exploratory diagnostic，不是新的 GFM 方法实验。预注册明确禁止根据结果重排 GFM、补模型投票、修改样本或候选集合、改 SQL evaluator 或移动阈值。

## 指南、代码与恢复修订

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 初始注册提交：[2a8523c](https://github.com/bArtyom/gfm-rag/commit/2a8523c599d8846ec452281de8ddc970afd32e4a)。原始实验方案见[plan](../../plans/p0_fk_mapping_instance_equivalence_20261107.md)。
- 执行前查阅该仓库 README、Text2SQL README、experiment-roadmap 与 reproducibility-contract；参考上游为 [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`。本诊断复用项目已有 SQLite 只读 evaluator，不改上游模型或算法。
- Full_001 暴露 runner 契约缺口：零个或多个 SQL-used mapping 已在原方案列为 unsupported case，但旧 runner 把这种单元当成整轮致命错误；它也没有在覆盖门失败时先写出匿名覆盖汇总。
- 仅在保留 Full_001 失败记录后，登记一次 [Amendment 001](../../plans/amendments/p0_fk_mapping_instance_equivalence_amendment_001.md)，提交为 [e0d3e0d](https://github.com/bArtyom/gfm-rag/commit/e0d3e0d0d617cbedc02ef317f3578057b36b28ee)。runner 对目标数非 1 的单元改为记作 `not_substitutable`，并在 Full 覆盖不足时输出匿名汇总。恢复没有更改研究问题、固定样本、候选、SQL 变换、只读 evaluator、资源限额或判定阈值。
- 恢复 runner：[audit script](../../../../../scripts/text2sql/audit_p0_fk_mapping_instance_equivalence_20261107.py)，SHA-256 `99245f972de3f8827c812ec0fc5f89e3d269ea9b80bfb5a1c1bad03ce81adc3c`；[恢复配置](../../../../../configs/text2sql/p0_fk_mapping_instance_equivalence_20261107_01_amendment_001.json)，SHA-256 `7be0192548346e1d3bb7e554b779c459bda7334f4cb97d83cca5d021f5bd502b`。

## 数据、样本与执行方法

- 数据：BIRD dev。`dev.json` SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 冻结的 SQL-used candidate manifest SHA-256：`cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0`。固定 Smoke 5 单元、Full 108 单元、4 个匿名数据库、全体候选映射行359（Smoke 31，Full 328）。无随机抽样；没有随机种子。
- 干预：SQLGlot 解析 SQLite SQL；只改同一显式 JOIN-ON alias pair 的直接限定列等式，复合 FK 作为整体替换。保留其余 JOIN 条件和查询结构。不可唯一定位或不能安全改写的单元记为不可替换；候选执行失败不纳入完整指标。
- 结果比较：使用既有只读 SQLite evaluator。数据库以 `mode=ro&immutable=1` 打开，并启用 query-only 与只读 authorizer；每条 SQL 最多10秒、50,000行、64 MiB结果、256 MiB SQLite heap。Full 至少80个完整单元且覆盖至少3个匿名数据库才可解释预设假设；低于覆盖门只报告描述性结果。
- 硬件/环境：CPU-only，最多8个 CPU 线程；启动时192个逻辑 CPU、503 GiB RAM（约452 GiB可用）、磁盘剩余112 TiB；四张 RTX 4090 均空闲但本实验没有使用 GPU。Conda 环境 `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2。没有安装或升级依赖。

## 执行记录

| 阶段 | 运行情况 | 结果 |
|---|---|---|
| Smoke_001 | 原注册 commit 2a8523c，5/5 单元完整；26 个替代 mapping 比较 | `SMOKE_PASS`；1/5 单元有 Bag 相同的替代 mapping。仅为 pilot。 |
| Full_001 启动尝试 | `conda run ... python3` 被外层 PATH 解析到 Python 3.9 / SQLGlot 30.12.0 | `SQLGLOT_VERSION_MISMATCH`，输入未读取，未创建结果目录。日志私有保留。 |
| Full_001 执行尝试 | 明确调用 Python 3.12.14 后，执行进度到40/108、其中36个完整 | `SQL_USED_TARGET_NOT_SINGLETON` 导致旧 runner 整轮停止；只写了失败回执，没有 Full 聚合指标。该部分运行不并入 Recovery。 |
| Smoke_002 | Amendment 001 提交 e0d3e0d，5/5 单元完整；26 个替代 mapping 比较 | `SMOKE_PASS`；与 Smoke_001 相同，1/5 单元出现 Bag 相同替代 mapping。 |
| Full_002 | 从冻结的108单元重新开始 | 108/108已处理，94个完整，4库；达到预注册覆盖门，状态 `POSITIVE_INSTANCE_EQUIVALENCE_SIGNAL`。 |

启动错误与 Full_001 结构停止均保留在本地独立日志和失败回执中。唯一恢复使用新 run IDs `_smoke_002` / `_full_002`，先重新通过 Smoke；没有第三次尝试。

Full_002 复现命令：

```bash
conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/audit_p0_fk_mapping_instance_equivalence_20261107.py \
  --mode full \
  --run-id p0_fk_mapping_instance_equivalence_20261107_01_full_002 \
  --repo-root "/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106" \
  --config configs/text2sql/p0_fk_mapping_instance_equivalence_20261107_01_amendment_001.json \
  --manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --database-root /mnt/liansp3/sources/datasets/bird/dev/dev_databases \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/full_002
```

Recovery Smoke 使用相同参数和输入，仅将 `--mode`、run ID 和输出目录分别改为 `smoke`、`p0_fk_mapping_instance_equivalence_20261107_01_smoke_002`、`smoke_002`。

## Full 指标

| 指标 | 结果 |
|---|---:|
| 固定 Full 单元 | 108 |
| 完整且可评分 | 94/108（87.04%） |
| 覆盖匿名数据库 | 4 |
| 完整单元中的空 Gold 输出 | 0 |
| 完整单元中至少一个替代 mapping 的结果 Bag 与 Gold 相同 | **54/94（57.45%）** |
| 同一主指标的 Wilson 95% 区间 | 47.35%–66.96% |
| 替代 candidate 对照中 Bag 相同 | 55/144 |
| 完整单元中至少一个替代 mapping 的 Set 与 Gold 相同 | 54/94 |
| 替代 candidate 对照中 Set 相同 | 55/144 |

分层结果：

| 匿名数据库 | 完整且非空单元 | 至少一个 Bag 相同替代 mapping | 比例 |
|---|---:|---:|---:|
| DB-A | 21 | 0 | 0% |
| DB-B | 54 | 44 | 81.48% |
| DB-C | 10 | 1 | 10.00% |
| DB-D | 9 | 9 | 100% |

分层差异很大：54个正向单元中53个来自 DB-B 与 DB-D；DB-A 为0/21。总体 Wilson 区间按单元计算，没有校正数据库内相关性。因此 57.45% 是该冻结样本的实例级结果，不能外推为每个数据库或一般 BIRD 查询的概率。

Full 未完整的14个单元：7个 `not_substitutable`（4个多 JOIN target group、3个 SQL-used target 数非1），4个 Gold 执行结果未知，3个候选执行不完整。它们不进入94个完整单元的主分母。任何异常 SQL、逐题信息、映射身份、数据库名称与结果行均留在本地。

## 资源、模型调用与费用

- Smoke_002：wall 3.14秒；父进程 CPU 0.63秒、含子进程 CPU 17.49秒；峰值 RSS 约0.63 GiB。
- Full_002：wall 35.88秒；父进程 CPU 6.15秒、含子进程 CPU 46.75秒；峰值 RSS：父进程0.63 GiB、最大子进程0.64 GiB。
- GPU 时间0秒。模型/API 请求0次；本轮模型输入/输出/总 token 为0/0/0。外部 API 费用 CNY 0.00。CPU 时间保留为资源成本，不折算电费。
- 第一次 Full_001 的运行器异常退出，没有形成最终资源 metadata，因此不把它与 Full_002 的精确资源统计混加。

## 结论、限制与下一步

该固定 BIRD dev 子集中，静态 SQLite 实例经常不能区分参考 SQL 使用的 mapping 与其他合法 FK 候选：54/94完整非空单元至少有一个替代 mapping 返回相同 Set 与 Bag。结果达到预注册正向信号门，支持在后续**实例级** FK mapping 评测中记录多个输出相同候选，而不是把这些输出相同直接说成语义等价。

结果集中在两个匿名数据库，其他数据库的频率明显更低。静态输出相同可能来自数据值、空连接或当前记录分布；本实验没有构造第二数据库实例、生成 test suite、审阅业务意图或获得人工 Role 标签。故不改变 G-reasoner 7/38 对 Dense 27/38 的既有 NO-GO，不验证模型排名，也不证明 SQL Gold 错误。

本注册到此停止，不追加模型审阅、GFM 排序或同数据调参。适合的下一研究问题是单独预注册跨实例/受控数据扰动复核，判断这些相同输出中哪些只是当前数据巧合；这需要独立生成约束一致的数据实例，不能由本轮结果替代。

## 产物与复现边界

- 项目仓库中的匿名结果：[aggregate_summary.json](aggregate_summary.json)。
- 本地结果目录：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/`。Full_001 失败回执、两个 Smoke 和 Full_002 私有指标分目录保存。
- 公开文件不含题目、Gold SQL、mapping identity、逐题样本、原始执行结果或私有日志。精确样本 manifest 只在本地保留，因此独立复现者需按其公开 hash 和冻结筛选代码重建该样本；本报告不声称发布了逐题复现包。
