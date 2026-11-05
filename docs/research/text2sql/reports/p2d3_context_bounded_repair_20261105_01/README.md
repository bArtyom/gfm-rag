# P2d.3：受检索上下文约束的 SQL 修复

**状态：`COMPLETED_NO_GO_OR_INCONCLUSIVE`。** 预注册、固定配置、匿名样本登记、运行器和最终报告已归档到项目仓库；私有 Full 66 题与 Smoke 5 题保存在本地 `prepare_002`。第三组同源 Smoke/Full 已完成；最终结果与三臂对照见下方“最终执行结果”。

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

Full 样本从 P2c-R 可评的 1,460 题中抽取，与旧 P2d 全部准备样例不重叠；按匿名数据库与 V00 Complete Schema@1024 完整/不完整分层。另有 5 题 Smoke，独立于 Full 与历史样本。BIRD dev 仅作探索性开发证据。预注册停止条件已触发，不扩样。

## 最终执行结果（2026-11-06）

**状态：已完成，`NO_GO_OR_INCONCLUSIVE`。** 预注册判据、配置、样本和模型均未因结果而改动。最终 Smoke `p2d3_context_bounded_repair_smoke5_20261105_03` 与 Full `p2d3_context_bounded_repair_full66_20261105_03` 使用相同公开源码提交 `405535cd87b6c1b0ee6780c46f0e7461ea080c85`、相同冻结输入 seal 和同一服务身份。前两次 Full 预检 `full_001/002` 都在首个 Full 模型请求前停止，未生成预测；所有失败回执保留在本地。

### 本轮实际比较的处理方法

三组使用同一个一次生成器、同一初始 SQL、相同问题和证据。P2c-R `V00` 的节点排序与所选节点冻结；Full Schema 来自同一冻结数据库 Schema。修复诊断只传固定类别，不传 SQLite 原始错误、Gold SQL、结果行或具体缺失字段名称。

| 组 | 相对原先一次生成流程的改动 | Full 修复情况 |
|---|---|---|
| A0 | 保留一次生成，不做修复；作为不修复基线。 | 15题初始 SQL 无法解析或编译；没有修复请求。 |
| A1 | 新增至多一次的 repair 请求；失败时把完整 R0 数据库 Schema、原 SQL及标准化失败类别交给同一个本地模型。候选只有通过只读 parse/compile 安全检查才采用。 | 13次尝试，2个候选通过门并被采用。 |
| A2 | 与 A1 共用同一初始 SQL和单次修复上限，但模型只看 V00 原检索上下文。SQLite authorizer 同时检查初始 SQL与修复候选；读取未出现在 V00 中的表/列即拒绝，并可触发一次修复。 | 19次尝试，3个候选通过门并被采用；8个越界字段提案被拒绝，记录14次被拒 READ 事件及6次初始上下文拒绝；最终接受的越界读取为0。 |

修复提示要求模型仅返回只读查询、只使用提供的 Schema 与证据、保留问题意图，不得臆造表列。没有多轮重试、候选投票、人工挑选或基于 Gold 的反馈。A1/A2 只在本轮新加的修复分支改变模型输入；A0 一直是共享的原始一次生成输出。

### Full 指标与判据

Full 为预先抽样的 66 题、11 个匿名数据库；每库最多 6 题，并按 V00 Complete Schema@1024 完整/不完整分层。样本与旧 P2d 的 33 个准备样本排除重叠。种子为 Full `20261105`、Smoke `20261106`。Set/Bag EX 的分母均为 66；8 个参考 SQL 不可执行的案例另行记录，报告的聚合分数按冻结 evaluator 口径计算。

| 指标 | A0 不修复 | A1 完整 Schema 修复 | A2 V00 受限修复 |
|---|---:|---:|---:|
| Set EX | 18/66（27.27%） | 20/66（30.30%） | 17/66（25.76%） |
| Bag EX | 15/66（22.73%） | 16/66（24.24%） | 13/66（19.70%） |
| 最终 SQL 可执行数 | 51/66 | 53/66 | 48/66 |
| 修复请求数 | 0 | 13 | 19 |
| 通过安全/编译门的修复候选 | 0 | 2 | 3 |

配对 Set 结果：A1 相比 A0 有 2 题由错转对、0 题由对转错；A2 相比 A0 有 1 题由错转对、2 题由对转错；A2 相比 A1 有 0 题由错转对、3 题由对转错。A2−A0 为 **−1.52 个百分点**，没有达到预注册的至少 +5pp；A2−A1 为 **−4.55pp**，在与 A1 相差不超过5pp的容许线内。最低修复信号达到（A0 有15个初始解析/编译失败，门槛10）；A2 authorizer 门通过（0个越界读取被接受）。由于主要增益门失败，整体仍判 NO-GO；不追加样本、不改阈值、不继续本轮修复实验。

Smoke 5题三臂 Set EX 均为3/5、Bag EX 均为2/5，全部可执行；没有任何修复触发。因此 Smoke 只验证服务、usage 记账、输出解析和 authorizer 路径，不能当作修复效果证据。

### 可复现信息、资源与异常

- 基础仓库：`https://github.com/bArtyom/gfm-rag`；执行分支：`research/p2d3-context-bounded-repair-20261105`；模型推理的源码提交：`405535cd87b6c1b0ee6780c46f0e7461ea080c85`。
- 指导材料：运行前核对项目 `AGENTS.md`、根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 及 P2d.2 `_02` 失败归因报告。实验处理、阈值和停止条件均按已冻结方案执行；偏离项只有首次 Full 的两个预检被安全停止，随后用新 run ID 在同一提交恢复，没有发出 Full 请求或覆盖产物。
- 数据：本地冻结的 BIRD dev 与 P2c-R `V00` 结果。dev JSON SHA-256=`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；tables JSON SHA-256=`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；P2c-R 聚合 SHA-256=`7e4ce4b2a92df5e17160bb2429402b66ab7caec521c6e4da9ec90abd108e8fdc`；P2c-R 逐题输入文件 SHA-256=`99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff`。Gold 只用于样本完整性分层和最终评测，不进入任何 prompt。
- 模型：本地 `Qwen2.5-Coder-7B-Instruct`，vLLM 0.8.5，bfloat16，temperature 0、top-p 1、seed 20261105；单条初始生成最多1024 tokens，修复最多512 tokens，最多一次。Qwen3-Embedding-0.6B tokenizer 仅重建冻结的 R0/R1 文本和 token 计数，未重新排名或计算 embedding。
- 执行环境：Python 3.12.14、SQLGlot 28.0.0、Transformers 4.57.1、tokenizers 0.22.1。运行器没有改依赖、下载权重或训练模型。
- 资源：GPU 1（RTX 4090）；显存峰值21,821 MiB（预设上限22 GiB）；当时主机可用内存约435 GiB、192 CPU线程。Smoke+Full 共发出113个本地模型请求，确认输入145,120、输出5,476、合计150,596 tokens；没有 usage 缺失。Full 请求 wall time 92.227秒，Smoke 4.068秒。约190个一秒 GPU 采样点中积分约89.54个满利用率等效秒；这是设备利用率近似值，不是进程级精确 GPU 计时。外部 API 费用 CNY 0；本地 GPU 成本未折算货币。
- 可复现命令模板：
  ```bash
  python scripts/text2sql/p2d3_context_bounded_repair.py \
    --stage <smoke|full> \
    --expected-commit 405535cd87b6c1b0ee6780c46f0e7461ea080c85 \
    --expected-seal-sha256 <private-local-seal> \
    --result-root <private-local-result-alias>
  ```
  样本、SQLite 路径、prompt、seal 和逐题 SQL 仅在本机私有回执中；不能只靠 GitHub 文件从零重建私有数据快照。
- 本次保留的执行修复只涉及读取 vLLM 0.8.5 的位置参数、固定服务身份 JSON 的 tuple/list 序列化比较，以及登记新的 Smoke/Full run ID 和剩余预算；没有改模型、实验臂、prompt 判据、数据或结果。
- 本报告附带的 `aggregate_summary.json` 只含总体计数、匿名 `db_01`–`db_11` 聚合和隐私标记；不含问题、SQL、数据库真实名称、路径、结果行或逐题预测。运行回执中的私有路径和哈希保持在本地。
- 私有结果登记别名：`sources/results/gfmrag_p2d3_context_bounded_repair_20261105_01/`；成功运行目录为 `smoke_003/` 与 `full_003/`。本地逐题预测、输入 manifest、数据库路径和运行日志不公开。

### 解释边界

这是一项 BIRD dev 开发集上的小样本、分层探索性 utility pilot，不估计标准 BIRD 测试集总体准确率。A1 只比基线多2个 Set 正确案例；A2 虽然实现了上下文权限约束，却没有提升准确率。结论是“本次固定设置下受限修复未达到继续扩展的门槛”，不是“所有 SQL 修复都无效”，也不是 QuadGraph 图推理的反证。实验没有运行 Jev，没有修改 G-reasoner 六层传播、DistMult、sum 聚合、关系 MLP、模型权重或训练目标。下一步进入错误分析/方法整理；除非出现能改变主结论的新证据，不在此分支继续扩样。

### 附件与前序记录

- 匿名 Full 聚合：[aggregate_summary.json](aggregate_summary.json)
- 冻结方案：[p2d3_context_bounded_repair_20261105.md](../../plans/p2d3_context_bounded_repair_20261105.md)
- 方法变更台账：[method-change-ledger-20261105.md](../../method-change-ledger-20261105.md)
- 直接前序失败归因：[P2d.2 报告](../p2d2_frozen_failure_attribution_20261105_02/README.md)
