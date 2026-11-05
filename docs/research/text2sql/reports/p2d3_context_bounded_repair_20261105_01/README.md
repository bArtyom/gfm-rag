# P2d.3：受检索上下文约束的 SQL 修复

**状态：`PREREGISTERED_NOT_RUN`。** 本目录当前只有预注册方案和固定配置，尚未读取本轮样本、启动模型或产生实验结果。

本地准备 attempt 001 在打开私有输入前因程序误要求预先登记的空结果根不存在而停止（`FileExistsError`）。attempt 002 通过冻结输入哈希检查后，发现 P2c-R 将 1,460 个可评样本的 V00 完整性标记存成整数 `0/1`（633/827），而非 JSON boolean；因此在题目包生成前停止。两次失败回执均保留在本地私有日志中。attempt 002 已读取冻结的 BIRD dev 题目文件（其中包含 Gold 字段）与 P2c-R 分层行，但尚未抽出新样本、生成题目包、打开 SQLite 数据库或发出模型请求。修订后的准备器接受权限为 `0700` 且只包含保留的 `prepare_*` 目录的实验根，并只将冻结的 `0/1` 表示规范化为两层标签，不改变抽样逻辑或实验定义。正式样本将另写入 `prepare_002`，保留 `prepare_001` 失败现场。

本轮从 P2d.2 的失败归因提出一个探索性问题：对同一条初始 SQL，最多修复一次时，只允许查看检索得到的 V00 Schema，上下文受限修复能否接近完整 Schema 修复的效果，并提高不修复基线的 Set EX。通用 SQL 校验/修复已有近期工作，本实验不主张该机制新颖。

P2c-R 的候选排序和节点选择保持冻结；准备器使用 Qwen3-Embedding tokenizer 重建 R0/R1 Schema 文本，生成 prompt 的计数、初始 SQL 和修复请求则使用 Qwen2.5-Coder-7B tokenizer/模型。两套模型资源分开登记、分开校验。

比较的三组共享同一条初始 SQL：A0 不修复；A1 在初始 SQL 无法解析/完整 Schema 编译时允许一次完整 R0 Schema 修复；A2 只给原 V00 检索上下文，并对初始 SQL 与修复候选都用 SQLite authorizer 拒绝上下文外表列，拒绝后至多修复一次。模型只收到标准化失败类别，不收到 SQLite 原始报错、Gold SQL 或查询结果。

- 预注册方案：[p2d3_context_bounded_repair_20261105.md](../../plans/p2d3_context_bounded_repair_20261105.md)
- 冻结运行配置：[experiment_config.json](experiment_config.json)
- 准备器与阶段运行器：[p2d3_prepare_inputs.py](../../../../../scripts/text2sql/p2d3_prepare_inputs.py)、[p2d3_context_bounded_repair.py](../../../../../scripts/text2sql/p2d3_context_bounded_repair.py)
- 直接前序证据：[P2d.2 失败归因](../p2d2_frozen_failure_attribution_20261105_02/README.md)

Full 计划样本为 P2c-R 可评的 1,460 题中，与旧 P2d 全部准备样例不重叠的 66 题；按匿名数据库与 V00 Complete Schema@1024 完整/不完整分层。另抽 5 题 smoke，独立于 Full 与历史样本。只有公开预注册和运行器先推送到 `bArtyom/gfm-rag` 并核对远端后，才会准备私有样本和发起本地模型请求。BIRD dev 仅作探索性开发证据。
