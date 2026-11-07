# P0：FK-domain 排除项的 SQLite 原生核验

**实验 ID：** p0_fk_domain_violation_crosscheck_20261107_01
**状态：** 完成；预注册结论 **PREDICATE_EQUIVALENCE_CONFIRMED_ON_FIXED_SET**
**实验层级：** 有界 exploratory 数据/校验器审计，不是 GFM 排名或方法效果实验
**项目仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)
**预注册分支：** research/p0-sql-used-proxy-alignment-20261107
**预注册提交：** [9f7978a63c31c41553d70de4a63b0d8bb423af78](https://github.com/bArtyom/gfm-rag/commit/9f7978a63c31c41553d70de4a63b0d8bb423af78)
**执行代码树：** 739cd0a54b01316d6ed9c29e3a85a7f33de24468；本地执行 HEAD 为 85e926f8cf49c66864bab6c88335b9deaa108c00，与预注册提交具有相同 Git tree。
**预注册方案：** [plan](../../plans/p0_fk_domain_violation_crosscheck_20261107.md)；[冻结配置](../../../../../configs/text2sql/p0_fk_domain_violation_crosscheck_20261107_01.json)；[运行器](../../../../../scripts/text2sql/audit_p0_fk_domain_violation_crosscheck_20261107.py)。

## 研究问题与假设

前一项反事实 shuffle 诊断固定了 55 个候选 mapping 对，因预注册资格门仅有 14 对、覆盖 2 个匿名数据库而停止；其中 32 对被自定义检查标记为 original_fk_domain_violation，另有 9 对因修改列为主键而排除。没有运行反事实 SQL 比较或 G-reasoner 排名。

本审计只核验那 32 个既有排除项：原有的非 NULL anti-join 检查，是否与 SQLite 对相同声明外键执行的 PRAGMA foreign_key_check 一致。核心假设是二者对冻结候选外键声明给出相同的布尔判定。审计没有扩样，也没有重试先前已停止的 run ID。

SQLite 文档说明，外键比较会使用父键的 affinity 和 collation，子键为 NULL 时满足约束；foreign_key_check 输出的 FK 编号与 foreign_key_list 对应。本实验直接对照实际声明，检查原校验逻辑是否遵守 SQLite 的本地语义：[SQLite 外键语义](https://www.sqlite.org/foreignkeys.html)、[SQLite PRAGMA 参考](https://sqlite.org/pragma.html)。

## 原方法与本次改动

**原有方法：** 对每个候选 mapping，检查子表中是否存在非 NULL 的 child 值，在 parent key 中找不到相等值。若 target 或 alternate 任一声明有此类值，旧流程把整个候选对标为 original_fk_domain_violation，不允许进入随机扰动资格集。

**本次实际改动：** 不改 G-reasoner、图结构、embedding、候选排序、SQL 变换或旧 eligibility gate。新增只读审计运行器，重建原先冻结的 32 对，并将相同的 target/alternate 单列外键声明分别交给 SQLite 原生 foreign_key_check。运行器按 foreign_key_list.fkid 将原生检查结果对应到声明级别，另报告候选对级别的一致性。每个相关子表只扫描一次，读取结果不输出行 ID 或值。

因此，这次改动是**校验器实现的语义对账**，不是新的 Text2SQL 方法，也不代表 QuadGraph 论文的图关系传播或检索改进。

## 预注册范围与停止条件

- 固定人群：旧进度文件里恰好 32 个 original_fk_domain_violation 对；不加新题、mapping、数据库或样本。
- Smoke：按固定哈希顺序取 5 对；Full 独立重查完整 32 对，Smoke 与 Full 不合并。
- 随机种子：不适用；样本按固定 pair hash 与 experiment ID 的 SHA-256 确定性排序。
- 主要指标：target 与 alternate 两个声明“至少一个违规”的 pair-level 布尔判定是否一致。
- 次要指标：唯一外键声明级一致性、两边的违规组合、SQLite 错误数、匿名数据库切片以及违规行数分布。
- 通过结论要求 32 对和每个唯一声明均可解析，且无任何分歧；有 SQLite 错误或资源超限则判为 inconclusive。
- 停止规则明确禁止降低旧 40 对/3 数据库门槛、重跑旧实验、生成 SQL、扰动数据库、跑排名、增加模型审阅票数或做超参数扫描。
- 结果仅是针对旧排除项的定向核验，不是 BIRD-wide 外键违规率，也不是语义 Role 标签。

## 数据、代码与运行环境

- 数据：BIRD dev，统一入口 /mnt/liansp3/sources/datasets/bird/dev/；dev.json SHA-256 为 630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06，dev_tables.json SHA-256 为 35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97。
- 数据库快照：复用注册配置中的 4 个匿名 BIRD SQLite 文件及其 SHA-256；全量结束后哈希复核通过，文件未改变。
- 前序样本来源：SQL-used mapping 独立注册 03 的本地 manifest，以及 instance-equivalence Full_002 和旧 shuffle coverage-stop 产物。各输入 hash 在冻结配置中逐一登记；私有 manifest、逐对散列、数据库对象名和比较明细留在本地。
- 原始代码参考：用户维护仓库 bArtyom/gfm-rag；上游实现仅按方案记录为 RManLuo/gfm-rag commit b3e43219c49929da505244df4f0ba54c0947e4c4，本实验未修改或向上游写入。复用的旧 eligibility/anti-join helper 文件 SHA-256 为 4959dce11f28be60146542a6da2c72c565f1c299b69fa0a2d73a32dea350c824。
- 环境：conda 环境 think2sql_20260909，显式解释器 /root/miniconda3/envs/think2sql_20260909/bin/python3.12，Python 3.12.14，SQLite 3.53.2。注意：裸 conda run -n think2sql_20260909 python3 在该机器解析成 Python 3.9.20；因此本实验按注册要求显式调用环境内的 python3.12，没有改动环境或依赖。
- 硬件：192 个 CPU 逻辑核、503 GiB 内存（Full 启动时约 446 GiB 可用）、磁盘可用 112 TiB；4 张 RTX 4090 均有其他任务运行，本实验不占 GPU。
- 预算上限：8 线程、900 CPU 秒、1,800 墙钟秒、4 GiB RSS；每张表的 native check 最多 120 秒。未调用模型或外部 API，无新依赖。

## 启动命令

以下为 Full 实际命令。Smoke 使用相同参数和输入，将 --mode full、Full run ID、输出目录 full_001 改成 --mode smoke、Smoke run ID、输出目录 smoke_001，且不传 --smoke-receipt。Full 额外传入 Smoke 回执。

    OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 conda run --no-capture-output -n think2sql_20260909 /root/miniconda3/envs/think2sql_20260909/bin/python3.12 scripts/text2sql/audit_p0_fk_domain_violation_crosscheck_20261107.py --mode full --run-id p0_fk_domain_violation_crosscheck_20261107_01_full_001 --config configs/text2sql/p0_fk_domain_violation_crosscheck_20261107_01.json --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json --source-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --prior-full-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_instance_equivalence_20261107_01/full_002 --prior-stop-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/smoke_005_20261107_04 --prior-protocol-config configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_amendment_002.json --prior-execution-config configs/text2sql/p0_fk_mapping_counterfactual_shuffle_20261107_01_execution_001.json --smoke-receipt /mnt/liansp3/sources/results/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/smoke_001/run_receipt.json --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/full_001

运行 ID：

- Smoke：p0_fk_domain_violation_crosscheck_20261107_01_smoke_001
- Full：p0_fk_domain_violation_crosscheck_20261107_01_full_001

## 结果

| 阶段 | 候选对 | 唯一 FK 声明 | Pair-level 一致 | 声明级一致 | SQLite 错误 | 耗时 / 峰值 RSS |
|---|---:|---:|---:|---:|---:|---|
| Smoke | 5 | 2 | 5/5 | 2/2 | 0 | 5.99 秒 / 0.63 GiB |
| Full | 32 | 2 | 32/32 | 2/2 | 0 | 11.24 秒 / 0.63 GiB |

Smoke 与 Full 均只覆盖匿名 DB-B。Full 的两个唯一声明中，一个在自定义 anti-join 和 SQLite 检查下都报出 49 行违规；另一个在两者下都为 0 行。所有 32 对都由同一组两个声明组合构成，因此 32/32 不能解读为 32 个独立数据库证据。聚合结果另存于 [aggregate_summary.json](aggregate_summary.json)。

## 结论、下一步与边界

结果支持**现有 anti-join 与 SQLite 原生 checker 在这组固定声明上一致**。因此旧 32 项排除不是已观察到的比较器差异；它们确实包含一个被声明为 FK、但其现有 child values 不符合 parent-key 域的映射。旧 shuffle 试验仍应停止：它要求在资格样本上比较受控扰动，不能把这个已存在的约束违规当作可控扰动效应，也没有理由降低原覆盖门。

这次只核验了同一数据库中的 2 个唯一 FK 声明，且都来自先前筛出的排除项。不能据此估计其他 BIRD 数据库的外键状态，也不能推断哪一种业务 JOIN Role 才正确。该结果没有打开或执行 Gold SQL，没有生成新的模型标签，没有 G-reasoner/Dense 前向，没有 SQL 执行准确率。

旧 counterfactual-shuffle 分支到此关闭，不追加该分支的参数、数据库或样本扩展。原 14/55 eligibility、40 对/3 库停止门和旧输出均保持不变。下一步回到研究主线的结果综合：模型代理审阅的高置信一致率为 2/5，仍低于原注册 4/5 门；不能用这次 SQLite 审计替代语义共识或启动排名实验。只有取得门槛要求的标签依据后，再独立注册真实 mapping 排序实验。

本实验 API 用量为 0 输入 / 0 输出 / 0 总 token，无未知用量请求，外部 API 费用为 0 CNY。没有模型调用或供应商计费请求。Full 的本地 CPU 时间为 11.14 秒、墙钟时间为 11.24 秒；这是本地资源使用，不折算为 API 费用。跨项目账本累计值在会话最终答复中单独列出。

## 产物与隐私

- 公开预注册：配置、计划和脚本见上方链接；分支提交为 9f7978a63c31c41553d70de4a63b0d8bb423af78。
- 公开本次报告与匿名聚合：本目录的 README 和 aggregate summary；预注册与结果均按仓库流程提交，并进行远端内容回读校验。
- 本地完整结果：/mnt/liansp3/sources/results/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/{smoke_001,full_001}/。
- 本地日志：/mnt/liansp3/logs/gfmrag_p0_fk_domain_violation_crosscheck_20261107_01/{smoke_001,full_001}.log。
- 私有比较细节、逐对 hash 和 input preflight 均为 0600；没有上传问题文本、SQL、schema 名称、表/列名、FK id、row id、数据库值或私有 manifest。
