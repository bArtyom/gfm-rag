# P2d.3 authorizer 候选结果反事实审计

**状态：Full 完成；在封存候选中发现 authorizer 拒绝了可执行且正确的 SQL。** 这是对 P2d.3 的只读错误归因，不是新生成方法，不改写 P2d.3 原始 A0/A1/A2 指标。

## 研究问题与范围

P2d.3 的 A2 在 66 题中 Set EX 为 17/66。该臂只向模型提供 V00 检索上下文，并用 SQLite authorizer 拒绝读取上下文外的表列。Full 记录了 6 个初始 SQL 上下文拒绝和 8 个被拒修复候选。原聚合无法判断安全边界挡住的是正确候选，还是只挡住错误候选。

本审计只回答：**对这 14 条已经封存的 SQL，移除 V00 标识符 allowlist 后，有哪些能在完整数据库 Schema 下通过同一只读评测并匹配参考结果？** 不重生成、不修补 SQL、不改变原 A2 处理，也不据此估计新的系统级 EX。

- **H1：** 至少一个被拒修复候选在完整 Schema 下只读可执行且 Set EX 正确。
- **对立假设：** 被拒候选都不正确或无法执行。
- **实验层级：** P2d.3 的 exploratory error attribution，CPU-only；不是主实验、消融或独立复现。
- **预算：** 最多回放 6 条初始 SQL 与 8 条被拒修复候选；Smoke 最多 3 条且不进 Full 指标。执行器设 300 秒 wall 上限、最多 8 CPU 线程、4 GiB RSS 预算。GPU、模型、外部 API、训练、依赖安装与下载均为 0。
- **成功判据：** 来源 seal、预测与 DB 哈希一致；Smoke 覆盖两种候选；Full 完成 6+8 条回放。这里的“成功”只表示审计完整，不表示方法有效。

## 方案、来源和相对原方法的改动

- 项目仓库为 [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，运行分支 `research/p2d3-authorizer-counterfactual-audit-20261106`。
- 执行源码 commit：[`e8fe43d`](https://github.com/bArtyom/gfm-rag/commit/e8fe43dc211152812e342dcfacac429d1b4a194f)；对应运行代码树与 GitHub 归档树一致。
- 执行前读取项目 README、Text-to-SQL README、`experiment-roadmap.md`、`reproducibility-contract.md`、P2d.3 报告及本轮预注册。预注册与执行修订见[计划](../../plans/p2d3_authorizer_counterfactual_audit_20261106.md)。
- 复用 P2d.3 已封存的 `full_003`、`prepare_002`、原始 A0/A2 输出与 SQLite 快照。准备 seal SHA-256：`8e9d1947c34756a86e5ab19c4a58c34e5df5d862a8ae3d0f547cdd4d193a4976`；预测文件 SHA-256：`5f4956fb4b0fadd3cff3a92a5e77dc5170352f631d46919ac23887bce22b6817`。
- 唯一反事实变化是**离线回放时拿掉 V00 表列 allowlist**。仍使用 P2d.3 的 SQLGlot 只读检查、SQLite `mode=ro&immutable=1`、`query_only`、SQLite authorizer、超时、行数/字节/SQLite heap 上限以及同一 Set/Bag 比较规则。没有放开写操作、函数安全规则或数据库访问边界。
- 6 条初始拒绝 SQL 来自 A2 与 A0 共用的同次初始生成；8 条修复 SQL 来自 A2 已保存的修复响应。参考 SQL 只用于封存后的结果比较。完整 Schema 编译失败保留为不可判定，不记作 SQL 错误。

## 执行环境和运行记录

- 环境：既有 `think2sql_20260909`；Python 3.12.14、SQLGlot 28.0.0；无依赖变更。
- 资源预检：4×RTX 4090；本轮不使用 GPU。启动时可用 RAM 约 439 GiB，192 CPU，数据盘可用约 112 TiB；CUDA 对本任务关闭，CPU 线程上限 8。
- 随机性：无抽样与随机种子；完整复用固定候选。Smoke 是从冻结候选顺序中选 1 条初始拒绝和 2 条修复拒绝，不计入 Full。
- 公开运行命令（数据结果仍需通过个人资源索引中的私有输入入口提供）：

```bash
timeout --kill-after=5s 300s env CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 PYTHONHASHSEED=0 \
conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
  scripts/text2sql/p2d3_authorizer_counterfactual_audit.py \
  --stage full \
  --expected-source-commit e8fe43dc211152812e342dcfacac429d1b4a194f \
  --expected-preparation-seal 8e9d1947c34756a86e5ab19c4a58c34e5df5d862a8ae3d0f547cdd4d193a4976 \
  --expected-predictions-sha 5f4956fb4b0fadd3cff3a92a5e77dc5170352f631d46919ac23887bce22b6817 \
  --expected-registration-sha 4f54425c059995036d6a27d387004069351c20a20d9e49d8ba54daffced56ec4 \
  --source-result-root /mnt/liansp3/sources/results/gfmrag_p2d3_context_bounded_repair_20261105_01 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p2d3_authorizer_counterfactual_audit_20261106_01/run_002 \
  --sql-config docs/research/text2sql/reports/p2d3_context_bounded_repair_20261105_01/experiment_config.json
```

首次使用 `/usr/bin/time` 的启动包装因该可执行文件未安装而在 runner 启动前停止；随后用 Bash 内建计时器和 300 秒 wall timeout 运行。第一次 Smoke 尝试在 `run_001` 中遇到配置对象层级错误，在调用 SQL 执行器前停止，未执行 SQL、未写 Smoke 结果。该问题已在执行前修复并公开记录，后续以新目录 `run_002` 重登记相同 14 个候选、通过 Smoke 并完成 Full。没有改假设、样本、指标、SQL 或安全规则。Full 8.619 秒 wall、约 8.565 秒进程 CPU；Smoke 8.702 秒 wall、约 8.670 秒进程 CPU。由于环境缺少 `/usr/bin/time`，**本轮未测量单进程峰值 RSS**，不声称 RSS 预算已被直接测量验证。

## 结果

### 初始 SQL 上下文拒绝：6 条

| 检查 | 结果 |
|---|---:|
| 完整 Schema 下只读编译并执行 | 6/6 |
| Set EX 正确 | 2/6 |
| Bag EX 正确 | 2/6 |
| 冻结 A0 的 Set / Bag 正确数 | 2 / 2 |
| 同题冻结 A2 最终 Set / Bag 正确数 | 0 / 0 |

6 条 SQL 在完整 Schema 下的回放与冻结 A0 的 Set/Bag 结果逐题一致。6 个案例里 A0 有 2 个正确、A2 最终输出有 0 个正确；配对结果为 A0-only 2、A2-only 0。这里的 A0/A2 数字只针对这 6 个被拒案例，不代表全体 66 题。

### 被拒修复候选：8 条

| 检查 | 结果 |
|---|---:|
| 参考 SQL 可执行 | 8/8 |
| 候选完整 Schema 编译并只读执行 | 6/8 |
| 完整 Schema 编译阶段失败 | 2/8 |
| 可比较候选中的 Set EX 正确 | 2/6 |
| 可比较候选中的 Bag EX 正确 | 2/6 |

因此，H1 在这批封存候选中得到支持：authorizer 拒绝的 8 个修复候选里，**至少 2 个在完整 Schema 下可执行且 Set/Bag 都正确**。另外 4 个可执行候选不正确；2 个无法通过完整 Schema 编译，保留为不可比较。不可将后两类合并成“全部错误”。

## 结论与局限

这次审计证明 P2d.3 的上下文边界在少数封存例子中挡住了正确 SQL；它不只是拒绝错误修复。6 个初始拒绝中也有 2 条 A0 SQL 在完整 Schema 下正确，但 A2 的最终结果在这 6 题中没有正确案例。

这仍是**候选级、定向、样本很小**的反事实结果。它不能直接推断如果取消 allowlist，A2 的整体 Set EX 会提高多少，也不能代替一条新处理臂的前瞻性评测。P2d.3 原始 66 题 A0/A1/A2 的 18/20/17 Set EX 不变，原 `NO_GO_OR_INCONCLUSIVE` 决定不改；不据此宣称新的 SQL 修复方法，也不外推到 BIRD 测试集、JOIN Role 或图推理。

## 失败、产物和费用

- 失败现场：`/usr/bin/time` 缺失；`run_001` 中的 Smoke 尝试因配置读取层级错误停止。修复与新 run ID 已登记；原始目录与日志保留。
- 匿名汇总 SHA-256：`80f84c887f754a8809b375b7a3fa13b8bc3f9278be4584db69b56af183c7c46c`。
- 本地结果入口：`local:results/gfmrag_p2d3_authorizer_counterfactual_audit_20261106_01/`；有效运行是 `run_002`。日志入口：`local:logs/p2d3_authorizer_counterfactual_audit_20261106_01/`。
- 本文和 [`aggregate_summary.json`](aggregate_summary.json) 仅包含匿名聚合、哈希和执行信息；不公开题目、SQL、数据库真实名称/路径、逐题结果或查询结果行。
- 本轮模型/API 调用 0，确认输入/输出/总 token 0/0/0，未知用量请求 0；外部 API 费用 CNY ¥0.00。没有本地模型前向；本地 CPU 时间如上单独记录，不估算机器折旧或货币成本。
