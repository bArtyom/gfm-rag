# P2d.3：受检索上下文约束的 SQL 修复

**状态：`PREPARED_NOT_RUN`。** 预注册、固定配置和匿名样本登记已发布到项目仓库；私有 Full 66 题与独立 Smoke 5 题已冻结在本地 `prepare_002`。尚未启动模型或产生 SQL 实验结果。

本地准备过程保留了两个失败现场。第一次在打开私有输入前，因程序误要求预先登记的空结果根不存在而以 `FileExistsError` 停止。第二次通过冻结输入哈希检查后，发现 P2c-R 将 1,460 个可评样本的 V00 完整性标记存成整数 `0/1`（633/827），而非 JSON boolean；因此在抽取样本和打开 SQLite 数据库前停止。修订只兼容已冻结的 `0/1` 表示，并支持预先登记的空结果根，不改变抽样算法或实验定义；两个失败回执及日志均保留。

随后使用公开代码提交 `4005fb138899cd3fdb6692287f8da57889291192` 完成私有样本准备，结果写入新的 `prepare_002`：Full 66 题、Smoke 5 题，排除全部 33 个旧 P2d 准备样本，按匿名数据库 × 完整/不完整分层。公开登记文件只含匿名计数、种子及输入哈希，不含题目、Gold SQL 或私有路径。样本准备已完成；当前本地推理服务已启动，尚未发送模型请求。

模型服务首次启动命令按 `--model` 传入模型，但本机 vLLM 0.8.5 的 `serve` 接口要求模型路径作为位置参数；这次失败发生在模型加载前，未占用 GPU 或发出推理请求。修正命令后，服务已在 GPU 1 上启动。第一次 smoke 预检又发现服务身份核验器只识别 `--model`，不能识别 vLLM 0.8.5 的位置参数形式；检查在建立运行目录和发送请求前停止。运行器现同时识别 `--model <path>` 和 `serve <path>`，只改变服务身份读取兼容性，不改变实验处理、prompt、样本、指标或判据。两次服务/预检失败日志均保留在本地权限受限日志目录；新的 smoke 尚未发出模型请求。

本轮从 P2d.2 的失败归因提出一个探索性问题：对同一条初始 SQL，最多修复一次时，只允许查看检索得到的 V00 Schema，上下文受限修复能否接近完整 Schema 修复的效果，并提高不修复基线的 Set EX。通用 SQL 校验/修复已有近期工作，本实验不主张该机制新颖。

P2c-R 的候选排序和节点选择保持冻结；准备器使用 Qwen3-Embedding tokenizer 重建 R0/R1 Schema 文本，生成 prompt 的计数、初始 SQL 和修复请求则使用 Qwen2.5-Coder-7B tokenizer/模型。两套模型资源分开登记、分开校验。

比较的三组共享同一条初始 SQL：A0 不修复；A1 在初始 SQL 无法解析/完整 Schema 编译时允许一次完整 R0 Schema 修复；A2 只给原 V00 检索上下文，并对初始 SQL 与修复候选都用 SQLite authorizer 拒绝上下文外表列，拒绝后至多修复一次。模型只收到标准化失败类别，不收到 SQLite 原始报错、Gold SQL 或查询结果。

- 预注册方案：[p2d3_context_bounded_repair_20261105.md](../../plans/p2d3_context_bounded_repair_20261105.md)
- 冻结运行配置：[experiment_config.json](experiment_config.json)
- 准备器与阶段运行器：[p2d3_prepare_inputs.py](../../../../../scripts/text2sql/p2d3_prepare_inputs.py)、[p2d3_context_bounded_repair.py](../../../../../scripts/text2sql/p2d3_context_bounded_repair.py)
- 直接前序证据：[P2d.2 失败归因](../p2d2_frozen_failure_attribution_20261105_02/README.md)

Full 样本从 P2c-R 可评的 1,460 题中抽取，与旧 P2d 全部准备样例不重叠；按匿名数据库与 V00 Complete Schema@1024 完整/不完整分层。另有 5 题 Smoke，独立于 Full 与历史样本。运行仍须在核对远端公开登记和启动前资源后进行；BIRD dev 仅作探索性开发证据。
