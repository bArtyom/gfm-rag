# P2d.3：受检索上下文约束的 SQL 修复

**状态：`SMOKE_RECOVERY_PENDING`。** 预注册、固定配置和匿名样本登记已发布到项目仓库；私有 Full 66 题与 Smoke 5 题已冻结在本地 `prepare_002`。首次 Smoke 运行门通过，但后续 Full 预检要求 Smoke/Full 使用相同代码提交，故将用新 run ID 重做同一组 Smoke，再运行 Full。

本地准备过程保留了两个失败现场。第一次在打开私有输入前，因程序误要求预先登记的空结果根不存在而以 `FileExistsError` 停止。第二次通过冻结输入哈希检查后，发现 P2c-R 将 1,460 个可评样本的 V00 完整性标记存成整数 `0/1`（633/827），而非 JSON boolean；因此在抽取样本和打开 SQLite 数据库前停止。修订只兼容已冻结的 `0/1` 表示，并支持预先登记的空结果根，不改变抽样算法或实验定义；两个失败回执及日志均保留。

随后使用公开代码提交 `4005fb138899cd3fdb6692287f8da57889291192` 完成私有样本准备，结果写入新的 `prepare_002`：Full 66 题、Smoke 5 题，排除全部 33 个旧 P2d 准备样本，按匿名数据库 × 完整/不完整分层。公开登记文件只含匿名计数、种子及输入哈希，不含题目、Gold SQL 或私有路径。

模型服务首次启动命令按 `--model` 传入模型，但本机 vLLM 0.8.5 的 `serve` 接口要求模型路径作为位置参数；这次失败发生在模型加载前，未占用 GPU 或发出推理请求。修正命令后，服务已在 GPU 1 上启动。第一次 smoke 预检又发现服务身份核验器只识别 `--model`，不能识别 vLLM 0.8.5 的位置参数形式；检查在建立运行目录和发送请求前停止。运行器现同时识别 `--model <path>` 和 `serve <path>`，只改变服务身份读取兼容性，不改变实验处理、prompt、样本、指标或判据。两次服务/预检失败日志均保留在本地权限受限日志目录。

兼容性修正后，Smoke `smoke_001` 在代码提交 `e62ed2180d7d72c723a42366a4d40216e14ff02f` 上完成并通过运行门：5题参考与预测均可执行；A0、A1、A2 均为 3/5 Set EX、2/5 Bag EX；5题都没有触发修复，所以这组结果不能检验修复方法是否有效。共发送5次本地初始 SQL 请求，usage 为4,732输入、236输出、4,968总 tokens；无外部 API 费用。

之后，Full `full_001` 预检在代码提交 `f9f15613c0e1e55b1d8accaf4db77de23609301a` 上发现它与 `smoke_001` 的来源提交不同，按冻结的同源门在第一次模型请求前停止；只写入运行开始信息和停止回执，没有生成 Full SQL。两个 run 均保留。为避免覆盖并满足同源要求，补充[来源一致性修订](amendment_smoke_source_recovery.md)：不改问题、模型、处理臂或判据；用新的 `smoke_002` 和 `full_002` 目录重跑同一份冻结 Smoke/Full 样本。剩余请求、token 与 wall-clock 上限分别扣除 `smoke_001` 已确认的5次请求、4,732输入 tokens、236输出 tokens和17.087820秒，确保原始总预算不增加。新的 Smoke 与 Full 将在同一提交上运行。

本轮从 P2d.2 的失败归因提出一个探索性问题：对同一条初始 SQL，最多修复一次时，只允许查看检索得到的 V00 Schema，上下文受限修复能否接近完整 Schema 修复的效果，并提高不修复基线的 Set EX。通用 SQL 校验/修复已有近期工作，本实验不主张该机制新颖。

P2c-R 的候选排序和节点选择保持冻结；准备器使用 Qwen3-Embedding tokenizer 重建 R0/R1 Schema 文本，生成 prompt 的计数、初始 SQL 和修复请求则使用 Qwen2.5-Coder-7B tokenizer/模型。两套模型资源分开登记、分开校验。

比较的三组共享同一条初始 SQL：A0 不修复；A1 在初始 SQL 无法解析/完整 Schema 编译时允许一次完整 R0 Schema 修复；A2 只给原 V00 检索上下文，并对初始 SQL 与修复候选都用 SQLite authorizer 拒绝上下文外表列，拒绝后至多修复一次。模型只收到标准化失败类别，不收到 SQLite 原始报错、Gold SQL 或查询结果。

- 预注册方案：[p2d3_context_bounded_repair_20261105.md](../../plans/p2d3_context_bounded_repair_20261105.md)
- 冻结运行配置：[experiment_config.json](experiment_config.json)
- 准备器与阶段运行器：[p2d3_prepare_inputs.py](../../../../../scripts/text2sql/p2d3_prepare_inputs.py)、[p2d3_context_bounded_repair.py](../../../../../scripts/text2sql/p2d3_context_bounded_repair.py)
- 直接前序证据：[P2d.2 失败归因](../p2d2_frozen_failure_attribution_20261105_02/README.md)
- 执行修订：[Smoke/Full 来源一致性 amendment](amendment_smoke_source_recovery.md)

Full 样本从 P2c-R 可评的 1,460 题中抽取，与旧 P2d 全部准备样例不重叠；按匿名数据库与 V00 Complete Schema@1024 完整/不完整分层。另有 5 题 Smoke，独立于 Full 与历史样本。运行仍须在核对远端公开登记和启动前资源后进行；BIRD dev 仅作探索性开发证据。
