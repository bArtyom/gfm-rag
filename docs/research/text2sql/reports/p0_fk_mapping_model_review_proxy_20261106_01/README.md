# P0 FK mapping 双本地模型审阅代理实验

**状态：Full 完成；模型代理标签数量门未通过，停止后续排序。** 实验 ID：`p0_fk_mapping_model_review_proxy_20261106_01`。

本报告登记用户选择“用模型来审阅”后的独立探索轨道。它不修改原双人盲审 CSV，不将模型判定称为人工标签或可信 Role 标签；原人类审阅门仍为 0。详细冻结方案见[实验计划](../../plans/p0_fk_mapping_model_review_proxy_20261106.md)。

## 运行前已冻结

- 输入：本地私有 pair-level A/B 审阅包；60 个问题×表对、135 个 FK mapping、4 个匿名数据库。
- 审阅器：Reviewer A 使用本地 Qwen2.5-Coder-7B-Instruct；Reviewer B 使用本地 Qwen3-4B-Think2SQL。两个模型独立运行，互不查看对方结果。
- 先 5 单元 Smoke；通过后独立重跑 60 单元 Full。仅 Full 进入模型间一致性汇总。
- 本轮只评估模型输出有效率和模型共识代理标签数量；任何 G-reasoner 排序需另建 run ID。
- 私有问题、候选映射、逐题模型标签/原始输出、CSV 与日志不进入 GitHub。

## 环境与冻结输入

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-model-review-proxy-20261106`。启动前同步到最新指导提交 `9c480d2b1b2638e4d028a6b501b19d87786bd75d`；预注册和 A1 修订在 Full 启动前提交 `df88472eb5a0409110780e0b31610955d280aa3f`。没有运行第三方 `RManLuo/gfm-rag` 代码。
- 输入包来自 `p0_fk_mapping_pair_level_blind_review_20261106_01`，生成器提交 `0077db570a5c1f68dbb74598777593a75b3d1d27`。冻结包为 60 个问题×表对、135 个 FK mapping、4 个匿名数据库；A/B 包哈希详见匿名[`aggregate_summary.json`](aggregate_summary.json)。表对由参考 SQL 的 JOIN 派生，因此这是**已知表对条件下**的 mapping 审阅，不是端到端 Gold-free 评测。
- 环境为 `think2sql_20260909`、Python 3.9.20、Torch 2.5.1+cu118、Transformers 4.57.6。模型使用 BF16、`do_sample=False`、每题独立上下文、`max_new_tokens=384`、`local_files_only=True`。A 是本地 Qwen2.5-Coder-7B-Instruct（GPU 1）；B 是本地 Qwen3-4B-Think2SQL（GPU 2，关闭 thinking）。两个模型都属于 Qwen 家族，输出一致可能受共享偏差影响。
- Full 使用预注册提交中的 runner；Full 后仅将共享 token ledger 的模块目录改为通过 `GFM_SHARED_CODE_ROOT` 环境变量提供，生成逻辑和本报告结果未变。复跑时须把该变量设为本机共享代码目录。
- 模型资源入口为 `sources/models/qwen25-coder-7b` 与 `sources/models/qwen3-4b-think2sql`。逐分片 SHA-256 见[模型文件校验清单](model_artifact_checksums.txt)；未上传权重。
- 模型只看到问题、表对名称和候选 mapping。没有 Gold SQL、参考 JOIN/ON、数据库 ID、GFM 分数或对方模型输出。原人类回复 CSV 未读取、未修改。

## Smoke_001：未通过，不运行 Full

- Run ID：`p0_fk_mapping_model_review_proxy_20261106_smoke_001`；输入 A/B 包 SHA-256 分别为 `0b6102f3…d826cfa2` / `a30230c9…944dfdb`；每个模型独立处理同一组 5 个冻结单元，分别按 A/B 的不同显示顺序。
- Qwen2.5-Coder-7B-Instruct（GPU 1）：5/5 通过输出和候选语义校验；输入 1,524、输出 225、总计 1,749 tokens；峰值已分配显存 15.31 GB；权重加载 8.01 秒，生成 5.64 秒。
- Qwen3-4B-Think2SQL（GPU 2）：3/5 通过；2 个 JSON 输出选择 `no_declared_fk`，但每个单元均有已展示候选，因此按预注册响应契约判为无效；输入 1,544、输出 228、总计 1,772 tokens；峰值已分配显存 8.13 GB；权重加载 4.61 秒，生成 7.40 秒。
- 两者合计本地输入 3,068、输出 453、总计 3,521 tokens。此为本地推理，不发生外部 API 费用；本地 GPU 时间单独计量，不估算电费。
- **结论：** Smoke_001 失败门触发，未运行 60 单元 Full，未计算或使用任何共识标签，也未运行 G-reasoner、SQL 或外部 API。

## 修订与下一步

修订 A1 只在提示中明确：该审阅包的每个单元都列有至少两个声明 mapping，因此 `no_declared_fk` 不适用。该修订已在 Full 启动前单独登记，Run ID 为 `p0_fk_mapping_model_review_proxy_20261106_smoke_002`；模型、样本、候选顺序和校验规则均不变。若任一模型仍少于 4/5 通过，就停止此模型审阅路线，不再改提示或换模型。详见[修订记录](../../plans/p0_fk_mapping_model_review_proxy_20261106.md#执行时修订-a1-2026-11-06发生在任何-full-运行之前)。

## Smoke_002：通过

- Run ID：`p0_fk_mapping_model_review_proxy_20261106_smoke_002`；与 Smoke_001 使用相同冻结的 5 个单元和 A/B 包 hash，按 A/B 各自候选显示顺序分别运行。
- Qwen2.5-Coder-7B-Instruct（GPU 1）：5/5 通过；输入 1,674、输出 238、总计 1,912 tokens；峰值已分配显存 15.31 GB；权重加载 6.41 秒，生成 7.06 秒。
- Qwen3-4B-Think2SQL（GPU 2）：5/5 通过；输入 1,694、输出 260、总计 1,954 tokens；峰值已分配显存 8.14 GB；权重加载 4.63 秒，生成 8.19 秒。
- 合计输入 3,368、输出 498、总计 3,866 个本地 token。模型间标签一致性不作为 Smoke 门，也未在此阶段用于排序。
- 两个 Transformers 进程均提示模型 generation config 中存在 temperature/top-p/top-k 旗标但当前 `do_sample=False` 不使用这些采样旗标；所有结构和语义检查通过。

**结论：** 最终 Smoke 门通过；随后已按冻结设置完成一次 Full（两模型各 60 单元）。Smoke 标签没有混入 Full 汇总。

## Full_001：完成

- Full 前资源：4×RTX 4090；GPU 1/2 各有 24,199 MiB 空闲，未使用 GPU 0/3；可用 RAM 442 GiB、192 CPU 核、工作盘可用 112 TiB。Full 期间未见 OOM 或 GPU 异常。

- Run ID：`p0_fk_mapping_model_review_proxy_20261106_full_001`；两模型各跑完 60 个单元，共 120 次本地生成请求；没有 API 请求、SQL 执行、训练或重试。
- Qwen2.5-Coder-7B-Instruct：60/60 有响应，59 条通过决定、理由码、mapping ID 和集合基数校验；1 条在有候选时输出 `no_declared_fk`，按规则判无效。输入 20,557、输出 2,910、总计 23,467 tokens；权重加载 6.68 秒、生成 80.55 秒；峰值已分配显存 15.32 GB。
- Qwen3-4B-Think2SQL：60/60 有响应，58 条通过同一校验；1 条 `multiple_mappings` 只列 1 个 ID，1 条引用未知 mapping ID。输入 20,797、输出 3,117、总计 23,914 tokens；权重加载 4.37 秒、生成 94.00 秒；峰值已分配显存 8.14 GB。
- Full 合计输入 41,354、输出 6,027、总计 47,381 个本地 tokens。加上两次 Smoke，本实验共输入 47,790、输出 6,978、总计 54,768 个本地 tokens。Full 两进程生成时间合计约 174.55 秒；外部 API 花费为 0，电费不估算。
- 两模型均有效的单元为 57/60。决定类别和接受 mapping 集合精确一致 28 个：28/57（49.12%），按全部 60 个计为 46.67%。这 28 个单元双方自报置信度都至少为 2，其中 22 个为单映射、6 个为多映射。
- 28 个共识集合都可裁定；其中 23 个拒绝至少一个候选，覆盖 4 个匿名数据库。聚合器给出：30 个可裁定样本门 **未通过**（少 2 个），20 个可区分样本门通过，3 库覆盖门通过。
- 全部匿名计数及输入/输出哈希在[`aggregate_summary.json`](aggregate_summary.json)。它只读私有 manifest 的 pair—数据库归属用于计算匿名覆盖数；不读 SQL 或逐题真值。

## 结论与停止决定

本轮得到 28 个高置信模型共识可裁定单元，低于预注册的 30 个门槛。23 个可区分单元和 4 库覆盖达到各自门槛，但不能补偿可裁定样本数不足。因此不启动 G-reasoner/Dense Accepted@1 排序、不扩样，也不再改提示。结果状态为 `STOP_INSUFFICIENT_MODEL_PROXY_LABELS`。两模型不一致不告诉我们哪一个模型正确。

相对原方法，本轮只替换了标签来源：原方案要求两位真人各自盲审、决定类型和 mapping 集合完全一致且置信度至少为 2；本轮按用户选择，分别用本地 7B 与 4B 模型审阅，标签改为**模型共识代理标签**。问题、候选和盲审呈现沿用；模型标签不是人工金标准，不能支持 G-reasoner 真实 Role 准确率结论。原人工可信标签仍为 0。

## 结果归档

- 私有数据与模型原始输出：`sources/results/gfmrag_p0_fk_mapping_model_review_proxy_20261106_01/`；完整日志：`logs/gfmrag_p0_fk_mapping_model_review_proxy_20261106_01/`。目录权限 0700，文件权限 0600。
- 公开材料：本报告、匿名 `aggregate_summary.json`、`model_artifact_checksums.txt` 与复现脚本 `scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py` / `scripts/text2sql/aggregate_p0_fk_mapping_model_review_proxy.py`。
- 问题文本、候选身份、CSV、人类回复、逐题输出、Gold SQL、数据库和模型权重均未上传。
