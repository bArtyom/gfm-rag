# P0 Mini-Dev：唯一作用域列绑定恢复诊断

**状态：`STOP_LOGIC_FIXTURE_FAILED`。** 唯一允许的恢复 Smoke 在执行样本级 SQL 分析前失败；Full 未启动。本轮没有检验核心假设，也没有产生 SQL 映射覆盖结果。

## 研究问题、假设与实验层级

冻结的 BIRD Mini-Dev 2026 SQLite Gold-SQL audit 在 663 个跨表 `JOIN ... ON` 列等式中解析出 523 项；前一轮 direct-projection resolver 新增 46 项，达到 569/663。仍未解析的 94 项中，一部分含未限定的直接投影列。研究假设是：仅当未限定列在当前 SQL scope 中恰好属于一个来源时恢复绑定，并经 SQLite 编译期 READ 集核验，可在零回归、零歧义接受下新增至少 61 项，将覆盖率提高到至少 630/663（95%）。

本实验属于一次 bounded、CPU-only 的 exploratory 数据/标签可用性诊断，不是 FK Role 方法效果实验。成功判据为至少 61 个新增唯一作用域绑定、既有解析零回归、scope error 与 authorizer mismatch 均为零。Smoke 预选 5 题；至少 3/5 题有保守恢复且无交叉核验不一致，才允许唯一一次 Full。Smoke 逻辑夹具、冻结输入哈希或资源门任一失败即停止；amendment 只允许一次新的 Smoke attempt。

## 仓库、指导与代码

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/gfm-minidev-scope-binding-20261106`。
- 最新实验前指导提交：`61b6b9ef02cd8283fe69d9b9df48675675e9d76f`。已读取根 README、Text2SQL 研究 README、`experiment-roadmap.md`、`reproducibility-contract.md`、Mini-Dev 标签覆盖报告及本方案。没有偏离原有停止门；哈希转录错误只通过已归档 amendment 更正。
- amendment 与冻结配置、执行器、方案在提交 [`b854153d02a747befd4a758c16a7d5196e02cde1`](https://github.com/bArtyom/gfm-rag/commit/b854153d02a747befd4a758c16a7d5196e02cde1) 归档并完成 GitHub 文件读回核对。
- 唯一新增代码为 `scripts/text2sql/diagnose_minidev_unique_scope_binding.py`；无上游 GFM-RAG、G-reasoner、模型、训练目标或评测实现改动。

## 输入、环境与资源

- BIRD Mini-Dev reviewed 数据 revision：`38818fcbc46038129592680c51b2c8b597aac27c`；JSONL SHA-256：`926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`（500 行）。
- SQLite schema SHA-256：`5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`。前一轮 scope taxonomy 私有摘要 SHA-256：`c7116459bbc5d0262378136c0304cfb8b459e94b4d284b81730aeb8110d03475`。
- 环境：conda `think2sql_20260909`、Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2；CPU-only，最多 8 线程、4 GiB RSS、每次运行 1,200 秒。不安装依赖，不调用模型/API，不执行原始 SQL。
- 运行前资源检查：4×RTX 4090 无任务占用；RAM available 451 GiB；192 个逻辑 CPU；2 GiB swap 已用尽。该 run 隐藏 GPU，不申请 GPU。

## 执行与结果

| Attempt | 结果 | 数据读取 | 样本 SQL 分析 | 结果产物 |
|---|---|---|---|---|
| `smoke_001` | 输入哈希检查失败：配置中的 schema SHA 有一处转录错误 | 未读取 | 未开始 | 只保存启动日志；无输出目录 |
| `smoke_002` | 输入哈希检查通过；正向逻辑夹具 `unique_unqualified_direct_projection` 未通过 | 冻结 JSONL 已读入内存并完成预定样本选择 | 0/5；失败发生在 `analyze_question()` 之前 | 无输出目录、manifest、逐题结果或 aggregate |
| `full_002` | 未启动 | — | — | 无 |

Smoke_002 的 resolver 对预期可从单一来源绑定的直接投影返回 `None`，触发夹具断言。由于唯一允许的恢复 attempt 已失败，按预注册规则停止，不修补后重跑该注册。此实现问题意味着主假设未被测量；不能从本次结果判断绑定规则能恢复多少真实等式，也不能将该失败计作科学上的假设反证。

本次命令：

```bash
CUDA_VISIBLE_DEVICES=-1 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
  conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/diagnose_minidev_unique_scope_binding.py \
  --config configs/text2sql/p0_minidev_unique_scope_binding_20261106.json \
  --mode smoke --attempt 2 \
  --expected-commit b854153d02a747befd4a758c16a7d5196e02cde1 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_minidev_scope_binding_recovery_20261106_01/smoke_002
```

实际日志在本地 `/mnt/liansp3/logs/gfmrag_p0_minidev_scope_binding_recovery_20261106_01/smoke_001.log` 和 `smoke_002.log`。日志不上传。无模型/API请求，本轮确认 token 输入/输出/总计均为 0，API费用 CNY 0；无 GPU 推理成本。

## 结论与后续

本轮没有 SQL 级指标，核心假设状态为 **未检验**。保留两次 Smoke 日志、停止状态和公开方案；不继续同一 parser variant，不运行 G-reasoner 排序。用户提出改用模型审阅时，仓库已有独立的 Qwen/Qwen/Gemma 三模型审阅和一次探索性排序结果：三模型高置信精确多数 56/60、其中 41 个可区分；该排序为 G-reasoner 7/38、Dense 27/38。它们是模型代理标签，不是人工共识金标；项目决策记录已停止对同一数据和标签继续加模型或重复排序。本 Smoke 失败不会改变上述既有结果。

下一步按项目现有路线进入错误模式与新问题综合。若未来重新研究未限定 scope binding，必须先作为新的独立假设/实现注册，并说明与本次失败实现的差异及资源停止门；不得把本次失败补写成成功结果。
