# P2d.3：受检索上下文约束的 SQL 修复

**状态：`SMOKE_RECOVERY_PENDING`。** 预注册、固定配置和匿名样本登记已发布到项目仓库；私有 Full 66 题与 Smoke 5 题已冻结在本地 `prepare_002`。两次 Smoke 均通过运行门，但对应的 Full 预检分别因来源提交差异和服务身份 JSON 类型比较错误而停止；正在保留既有产物并准备第三组同源运行。

本地准备过程保留了两个失败现场。第一次在打开私有输入前，因程序误要求预先登记的空结果根不存在而以 `FileExistsError` 停止。第二次通过冻结输入哈希检查后，发现 P2c-R 将 1,460 个可评样本的 V00 完整性标记存成整数 `0/1`（633/827），而非 JSON boolean；因此在抽取样本和打开 SQLite 数据库前停止。修订只兼容已冻结的 `0/1` 表示，并支持预先登记的空结果根，不改变抽样算法或实验定义；两个失败回执及日志均保留。

随后使用公开代码提交 `4005fb138899cd3fdb6692287f8da57889291192` 完成私有样本准备，结果写入新的 `prepare_002`：Full 66 题、Smoke 5 题，排除全部 33 个旧 P2d 准备样本，按匿名数据库 × 完整/不完整分层。公开登记文件只含匿名计数、种子及输入哈希，不含题目、Gold SQL 或私有路径。

模型服务首次启动命令按 `--model` 传入模型，但本机 vLLM 0.8.5 的 `serve` 接口要求模型路径作为位置参数；这次失败发生在模型加载前，未占用 GPU 或发出推理请求。修正命令后，服务已在 GPU 1 上启动。第一次 smoke 预检又发现服务身份核验器只识别 `--model`，不能识别 vLLM 0.8.5 的位置参数形式；检查在建立运行目录和发送请求前停止。运行器现同时识别 `--model <path>` 和 `serve <path>`，只改变服务身份读取兼容性，不改变实验处理、prompt、样本、指标或判据。两次服务/预检失败日志均保留在本地权限受限日志目录。

兼容性修正后，Smoke `smoke_001` 在代码提交 `e62ed2180d7d72c723a42366a4d40216e14ff02f` 上完成并通过运行门：5题参考与预测均可执行；A0、A1、A2 均为 3/5 Set EX、2/5 Bag EX；5题都没有触发修复，所以这组结果不能检验修复方法是否有效。共发送5次本地初始 SQL 请求，usage 为4,732输入、236输出、4,968总 tokens；无外部 API 费用。

之后，Full `full_001` 在来源提交与 Smoke 不同时，于第一次请求前停止。改用新目录后，Smoke `smoke_002` 在提交 `764020a8eda7680745b6c3fd1f1c62f72a05ad76` 上再次通过运行门（仍是3/5 Set EX、2/5 Bag EX、无修复）；再启动的 `full_002` 也在任何 Full 请求前停止。逐字段核对发现，实时服务身份中的 `models` 是 tuple 列表，写入 `run_start.json` 并读回后变成 list 列表，Python 直接比较因此错误地判定身份不一致。运行器现统一使用 JSON list 表示。`smoke_001`、`full_001`、`smoke_002`、`full_002` 的目录和日志全部保留，没有 Full 预测。

为避免覆盖并满足同源要求，第二份[恢复修订](amendment_service_identity_json_stability.md)注册新目录 `smoke_003` / `full_003`，重跑同一冻结 Smoke/Full 样本，不改模型、处理臂、prompt、指标或判据。剩余请求、token 和阶段 wall-clock 上限已从原始预算中扣除两次 Smoke 的已确认用量及两次 Full 预检 wall time：203 次请求、6,990,536 输入 tokens、199,531 输出 tokens、14,364.887822 秒。新 Smoke 与 Full 将使用同一公开提交和同一服务身份。

本轮从 P2d.2 的失败归因提出一个探索性问题：对同一条初始 SQL，最多修复一次时，只允许查看检索得到的 V00 Schema，上下文受限修复能否接近完整 Schema 修复的效果，并提高不修复基线的 Set EX。通用 SQL 校验/修复已有近期工作，本实验不主张该机制新颖。

P2c-R 的候选排序和节点选择保持冻结；准备器使用 Qwen3-Embedding tokenizer 重建 R0/R1 Schema 文本，生成 prompt 的计数、初始 SQL 和修复请求则使用 Qwen2.5-Coder-7B tokenizer/模型。两套模型资源分开登记、分开校验。

比较的三组共享同一条初始 SQL：A0 不修复；A1 在初始 SQL 无法解析/完整 Schema 编译时允许一次完整 R0 Schema 修复；A2 只给原 V00 检索上下文，并对初始 SQL 与修复候选都用 SQLite authorizer 拒绝上下文外表列，拒绝后至多修复一次。模型只收到标准化失败类别，不收到 SQLite 原始报错、Gold SQL 或查询结果。

- 预注册方案：[p2d3_context_bounded_repair_20261105.md](../../plans/p2d3_context_bounded_repair_20261105.md)
- 冻结运行配置：[experiment_config.json](experiment_config.json)
- 准备器与阶段运行器：[p2d3_prepare_inputs.py](../../../../../scripts/text2sql/p2d3_prepare_inputs.py)、[p2d3_context_bounded_repair.py](../../../../../scripts/text2sql/p2d3_context_bounded_repair.py)
- 直接前序证据：[P2d.2 失败归因](../p2d2_frozen_failure_attribution_20261105_02/README.md)
- 执行修订：[Smoke/Full 来源一致性 amendment](amendment_smoke_source_recovery.md)
- 执行修订：[服务身份 JSON 稳定性 amendment](amendment_service_identity_json_stability.md)

Full 样本从 P2c-R 可评的 1,460 题中抽取，与旧 P2d 全部准备样例不重叠；按匿名数据库与 V00 Complete Schema@1024 完整/不完整分层。另有 5 题 Smoke，独立于 Full 与历史样本。运行仍须在核对远端公开登记和启动前资源后进行；BIRD dev 仅作探索性开发证据。
