# Gemma 4 第三模型审阅：GPU 启动失败记录

**状态：STOPPED_BEFORE_GENERATION。** 本报告记录独立预注册实验 `p0_fk_mapping_model_review_third_proxy_20261106_01` 的 GPU Smoke 启动失败。模型没有生成任何回复，因而没有模型标签或研究指标。CPU 恢复运行另有独立实验 ID 和报告，见 [CPU 恢复报告](../p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/README.md)。

## 研究问题与预注册边界

- 问题：不同模型家族 Gemma 4 E4B-it 能否对冻结的 FK mapping 盲审包给出有效、可与两位 Qwen 审阅结果独立聚合的标签？这一步只检测模型代理审阅可行性，不评估 G-reasoner 排序，也不生成可信人工 Role 标签。
- 层级：exploratory 模型代理审阅。
- 冻结预算：60 个问题×表对、135 个候选 mapping；先运行 5 单元 Smoke，有效 JSON 与候选语义校验达到预注册条件后再考虑 Full。
- 预注册门：三个模型的精确标签多数且至少两个多数支持者置信度≥2；只有另行满足不少于30个可裁定单元、20个可区分单元、覆盖3个数据库时，才允许注册独立的探索性排序诊断。
- 停止条件：模型加载失败、CUDA初始化失败、无输出、覆盖风险或资源超限时停止当前后端并保留现场；不升级驱动或核心依赖。

## 版本、数据与指南

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-model-review-third-proxy-20261106`，GPU 运行源码提交 `6a5fa74f9d22e6dfaa58b761ca4c841ab60d4165`。
- 本仓库指南：根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`，以及本实验 CPU/GPU 预注册方案。按盲审隔离要求，模型没有读取另一模型输出、Gold SQL 或参考 JOIN。
- 数据：冻结 A/B packet，各60单元、合计135个候选；packet SHA-256 分别为 `0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2` 和 `a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb`。没有改变数据或标签规则。
- 模型：Google Gemma 4 E4B-it，revision `c53e9d33178b12afbad4a48334d21e19b8c29761`，权重 SHA-256 `cfbd3d2f1cd71bd471c37fe2bf8546d5028d41e5736f64e1ca6c6b8893125503`，Apache-2.0。

## 环境、资源和启动方式

- 运行环境：`vllm` Conda 环境，Python 3.12.13、vLLM 0.21.0、PyTorch 2.11.0；此 PyTorch 构建使用 CUDA 13。
- 硬件：RTX 4090；系统 NVIDIA Driver 550.40.07 / CUDA 12.4。预定使用 GPU 1。模型没有进入 CUDA 推理阶段。
- 失败 Smoke run ID：`p0_fk_mapping_model_review_third_proxy_20261106_smoke_001`。
- 第二次启动命令：`conda run /root/miniconda3/envs/vllm/bin/python3.12 scripts/text2sql/run_p0_fk_mapping_model_review_third_proxy.py --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_A_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_B_packet.md --mode smoke --model /mnt/liansp3/sources/models/gemma-4-e4b-it --expected-commit 6a5fa74f9d22e6dfaa58b761ca4c841ab60d4165 --run-id p0_fk_mapping_model_review_third_proxy_20261106_smoke_001 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_review_third_proxy_20261106_01/smoke_001/reviewer_C`。

## 失败原因与结果

第一次调用使用了环境内 `python3` 名称；该机器的 PATH 次序解析到 Python 3.9，vLLM 未导入成功。之后改用 Python 3.12 的绝对路径，vLLM 已初始化模型引擎，但 PyTorch 在设置 CUDA 设备时拒绝当前驱动，报错为 driver too old（检测到 CUDA driver API `12040`）。两次失败均发生在 tokenization/generation 之前。

- 有效回复：0；输入/输出 token：0/0；外部 API：0；GPU 模型前向：0。
- Smoke 输出目录没有回复文件。启动堆栈留在本地日志：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_model_review_third_proxy_20261106_01/smoke_001_launch_recovery.log`。
- 未修改 GPU 驱动、PyTorch、vLLM 或任何共享环境。根据本机 CPU 与可用内存，转为单独预注册的 CPU 恢复路径；不在 GPU 后端复用此 run ID。

## 结论与限制

这次运行只证明当前 vLLM/PyTorch/CUDA 组合不能在该驱动上启动 Gemma 4 GPU 推理。它没有产生关于 Gemma 判断质量、模型间一致性或 FK mapping 的科学结果。CPU 恢复实验的标签仍只是模型代理；原可信人工 Role 标签数为0。
