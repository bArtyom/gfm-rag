# P0 FK mapping 第三模型审阅代理实验

**状态：Full 前预注册；只检验模型代理审阅门。** 实验 ID：`p0_fk_mapping_model_review_third_proxy_20261106_01`。本计划遵循用户“用模型来审阅”的选择；不修改原人类盲审 CSV，也不将模型标签称为人工真值。

## 研究问题与核心假设

- **问题：** 一个不同模型家族的独立盲审者，能否与已有两位 Qwen 审阅者形成足量的高置信精确多数标签，达到一次单独登记的探索性 G-reasoner 映射排序诊断门？
- **核心假设：** 在固定的 60 个问题×表对上，Gemma 4 E4B 与两位 Qwen 审阅者组成的三方代理审阅，可能产生至少 30 个高置信、精确决定和接受 mapping 集合的多数标签，其中至少 20 个可区分、覆盖至少 3 个匿名数据库。
- **边界：** 该实验检验代理标签的数量和跨模型一致性，不检验标签正确性、G-reasoner 效果或真实 Role 准确率。模型多数不是人工共识，也不解除原主实验的人类标签门。

## 层级、预算与停止规则

- 层级：`exploratory` 模型审阅可行性门；属于主实验前的标签代理诊断，不属于方法主实验、消融或独立复现。
- 数据固定为 60 个问题×表对、135 个完整 FK mappings、4 个匿名数据库；不抽样、不扩样。A/B 包和既有 A/B 输出保持冻结。
- 新模型预算：先 5 单元 Smoke；只有 Smoke 结构校验至少 4/5 有效才运行独立的 60 单元 Full。Smoke 不进入 Full 指标。每个单元最多一次生成，不重试、不改提示、不人工修订。
- 最高预算：65 次 Gemma 本地生成；vLLM 单进程、单 GPU、最多 90 分钟，不下载权重、不安装或升级依赖、不调用外部 API。
- 三方代理标签：决定类型与排序无关的接受 mapping ID 集合必须精确相同；同一精确标签中至少两位审阅者各自置信度≥2。标签只适用于 `single_mapping` 或 `multiple_mappings` 且接受集合非空。至少 30 个此类标签、其中至少 20 个不接受全部候选、并覆盖至少 3 个匿名数据库，才通过探索性排序登记门。
- **不通过时：** 停止该代理排序方向；不补样、不换模型、不改 prompt。
- **通过时：** 只允许另行预注册一个 exploratory Accepted@1 诊断；不得把本轮多数结果回填为人工标签或可信 Role truth。
- Smoke 若模型无法加载、候选/输入哈希不符、输出有效少于 4/5、GPU 显存/系统资源越过安全边界或出现泄漏，立即停止 Full。Full 若连续运行错误、OOM、运行超 90 分钟或输出覆盖风险，保留现场并停止。

## 审阅设计与防泄漏

- Reviewer A/B 已由 Qwen2.5-Coder-7B-Instruct 与 Qwen3-4B-Think2SQL 完成；本轮 C 使用另一个模型家族 Gemma 4 E4B-it。家族不同只能降低同源偏差风险，不能证明审阅判断独立或正确。
- C 只读冻结 A/B 审阅包中的问题、表对名和完整候选 mapping；不得读取 A/B 模型答案、Gold SQL、参考 JOIN/ON、数据库身份或 G-reasoner 分数。
- C 使用与 A/B 相同的审阅指令和 JSON 校验；每个问题独立上下文、`temperature=0`。候选顺序按固定种子 `20261106` 和 pair ID 逐题独立打乱，减少沿用 A/B 展示顺序的偏差。
- Smoke 使用 A 包前 5 个冻结单元；Full 重跑全部 60 单元。Smoke 和 Full 输出完全分开。
- 聚合器只从私有 manifest 读取 pair 到匿名数据库的归属，用于匿名数据库覆盖数；不会输出 pair ID、数据库名、问题、mapping ID、原始输出或逐题标签。

## 模型、资源与复现

| 项 | 冻结值 |
|---|---|
| 模型 | Google Gemma 4 E4B-it，来自不同于 Qwen 的模型家族 |
| 模型 revision | `c53e9d33178b12afbad4a48334d21e19b8c29761` |
| 本地 safetensors | 15,992,595,884 bytes；SHA-256 `cfbd3d2f1cd71bd471c37fe2bf8546d5028d41e5736f64e1ca6c6b8893125503` |
| License | Apache-2.0（模型卡） |
| 环境 | 已有 `vllm`；Python 3.12、vLLM 0.21.0、Transformers 5.9.0；不得升级 |
| 推理 | vLLM 离线引擎，BF16，GPU 1，单序列，`max_model_len=4096`，`gpu_memory_utilization=0.82`，`enforce_eager=True` |
| 资源快照 | 预检 GPU 1 空闲约 24 GiB；4×RTX 4090；RAM 可用约 444 GiB；192 CPU 核。运行前重新检查 `nvidia-smi`、`free -h`、`nproc` |
| 代码 | `scripts/text2sql/run_p0_fk_mapping_model_review_third_proxy.py` 与 `scripts/text2sql/aggregate_p0_fk_mapping_model_review_three_proxy.py` |

所有模型输出和逐题资料留在权限受控的本地目录。每次实际本地生成按稳定 call ID 写入共享 token ledger；记录真实 prompt/completion token。没有外部 API 费用；GPU 时间单独报告，不冒称没有资源成本。模型加载/生成期间禁止联网回退。

## 参考依据与变化

- 项目：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，从模型分歧审计分支最新提交继续。
- 已读 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 与最新模型审阅/分歧报告。
- 本实验沿用冻结 A/B 数据和判定字段；新增一位 Gemma 模型审阅者、独立候选打乱顺序及三方多数代理聚合。这是预注册的新 exploratory run，不修改前两轮结果。
- 先前双 Qwen Full 有 28 个精确高置信一致单元，低于原双人/双模型 30 个排序先决门；本轮通过与否只决定能否再登记一个模型代理排序诊断，不修改原门槛。

