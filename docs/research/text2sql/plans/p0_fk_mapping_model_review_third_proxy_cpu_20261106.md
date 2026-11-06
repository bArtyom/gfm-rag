# P0 FK mapping 第三模型 CPU 恢复实验

**状态：GPU 版未产生任何模型回复；CPU 恢复版 Full 前预注册。** 独立实验 ID：`p0_fk_mapping_model_review_third_proxy_cpu_20261106_01`。该恢复沿用用户选择的“用模型来审阅”，不改数据、模型、提示、标注规则或此前结果，只改本地执行后端。

## 恢复依据

前一份 GPU 预注册为 `p0_fk_mapping_model_review_third_proxy_20261106_01`。第一次启动时，`conda run -n vllm ... python3` 实际解析到 Python 3.9 的 `python3`，在导入 vLLM 前失败；随后改用 `/root/miniconda3/envs/vllm/bin/python3.12`，vLLM 0.21.0 成功识别 Gemma 4，但在 GPU 初始化时因 PyTorch 构建使用 CUDA 13、系统驱动仅支持 CUDA 12.4 而失败。失败发生在任何模型生成前；没有模型输入/输出 token、没有模型标签，也没有使用 GPU 显存。两份启动日志分别保留；失败输出目录保持为空。

已核对本机 CPU 为 Intel Xeon Platinum 8360H，支持 AVX512 BF16；可用 RAM 约 443 GiB。现有 `vllm` Conda 环境安装了 Transformers 5.9.0 与 PyTorch 2.11.0，Transformer 源码包含 Gemma4 模型实现。恢复版直接使用同一环境中的 Transformers 和 CPU，不安装、不升级或混用环境依赖，也不调用 CUDA。

## 研究问题、层级与预算

- **问题：** 采用不同家族 Gemma 4 E4B-it 独立盲审，是否能与两位既有 Qwen 审阅者形成足量的高置信精确多数标签，达到独立探索性 G-reasoner 映射排序诊断门？
- 层级：`exploratory` 模型代理标注可行性；不检验标签准确性、G-reasoner 效果或真实 Role 准确率。
- 冻结数据：60 个问题×表对、135 个 FK mappings、4 个匿名数据库；不抽样、不扩样。原 A/B 包与 A/B 模型输出只读。
- 先 5 条 Smoke；有效 JSON 与候选语义校验至少 4/5 才跑独立的 60 条 Full。每条最多一次生成、不重试、不改 prompt、不人工修订。Smoke 不计入 Full。
- 单次 Full 最高 60 次生成；单一 CPU 进程、最多 64 线程、峰值 RSS 预算 64 GiB、墙钟预算 90 分钟。任何约束失败则停止，保留输出与日志。

## 冻结标签规则与停止门

- 每单位至少两位审阅者必须在**决定类别和接受 mapping ID 集合**上精确一致；其中至少两位对该精确标签自评置信度≥2。仅 `single_mapping`/`multiple_mappings` 且接受集合非空进入可裁定集。
- 排序登记门：至少 30 个可裁定多数标签、至少 20 个接受集合未覆盖全部候选的可区分标签，并覆盖至少 3 个匿名数据库。
- 门未通过：停止，不补样、不换模型、不重写提示。门通过：仅允许另行登记 `exploratory` Accepted@1 诊断；不回填人工 CSV，不解除可信人工 Role 标签门。
- Smoke 若 Transformers 本地加载或 JSON/候选校验失败、有效输出少于 4/5、RSS 超过预算、网络回退、数据泄漏或已有输出将被覆盖，停止 Full。Full 若遇到生成异常、OOM、运行超过 90 分钟或输出覆盖风险，保留现场并停止。

## 盲审与资源配置

- 模型：Google Gemma 4 E4B-it，revision `c53e9d33178b12afbad4a48334d21e19b8c29761`；本地单 safetensors 15,992,595,884 bytes；SHA-256 `cfbd3d2f1cd71bd471c37fe2bf8546d5028d41e5736f64e1ca6c6b8893125503`；Apache-2.0。
- 环境：`/root/miniconda3/envs/vllm` 的 Python 3.12.13、Transformers 5.9.0、PyTorch 2.11.0。使用该环境绝对 Python 路径，避开已查明的 `conda run` PATH 次序异常。
- 权重与 tokenizer 仅从本地读取；设置 `CUDA_VISIBLE_DEVICES=`、`HF_HUB_OFFLINE=1` 与 `TRANSFORMERS_OFFLINE=1`。BF16、greedy decoding、每条独立上下文、最多 384 个生成 token。
- 线程上限 64。模型输入和原始输出留在权限 0700/0600 的本地目录；公开只提交匿名聚合和复现代码。
- 每次真实生成均使用稳定 call ID 记录实际输入/输出 token。这里没有第三方 API 单价或 API 调用；CPU 时间单独报告。

## 实施与解释边界

- 项目：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)；分支从 `research/p0-fk-model-review-third-proxy-20261106` 的 `6a5fa74f9d22e6dfaa58b761ca4c841ab60d4165` 开始。
- 参考：仓库 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、双模型代理报告及分歧归因报告。
- C 只看到问题、表对名称和映射候选；候选顺序以固定 seed `20261106` 加 pair ID 独立打乱。C 不读取 A/B 输出、Gold SQL、参考 JOIN/ON、数据库名或 G-reasoner 分数。
- 三方聚合器只读取匿名 A/B/C 判断和私有 manifest 中 pair→匿名数据库归属；输出不含逐题 ID、数据库名、候选 ID、问题、Gold 或模型原文。
- GPU Smoke 失败不与 CPU 恢复结果混合；新的 run ID、独立输出目录和本报告保证结果可区分。

