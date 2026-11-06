# Gemma 4 第三模型审阅：CPU 恢复与三模型代理聚合

**状态：完成；排序登记门通过，仅限 MODEL-PROXY exploratory。** Gemma 4 CPU Smoke 与 Full 均通过。三模型共识池达到另行注册排序诊断的样本门，但没有产生人工标签，也没有解除主路线的真实双人审阅门。

## 研究问题、假设与停止条件

- 研究问题：不同家族 Gemma 4 E4B-it 是否能提供有效且足量的第三方模型判断，使冻结 FK mapping 盲审样本形成足量的高置信精确多数？
- 核心假设：将一个独立模型家族加入两位 Qwen 审阅者后，可能得到至少30个可裁定共识单元、20个可区分单元，覆盖至少3个匿名数据库。
- 层级：exploratory 的模型代理标签可行性实验；不是人工标签准确率实验，不测试 G-reasoner。
- 预算：5条独立 Smoke；通过后对冻结60条运行一次 Full。每条最多一次生成，不重试、不改提示、不人工修订。Full 最多60次生成，64线程，峰值 RSS 上限64 GiB，墙钟上限90分钟。
- 成功门：精确决策与接受 mapping 集合多数一致，且至少两位多数支持者自报置信度≥2；汇总后至少30可裁定、20可区分、覆盖3库。门通过只允许另开探索性排序实验。
- 停止门：有效 Smoke 少于4/5、资源/格式/隔离失败、需要改动冻结输入或可能覆盖结果时停止。原 GPU 路径失败后，本轮单独登记 CPU 恢复，没有更改模型、提示、数据、标签门或旧结果。

## 项目、代码、数据与指导

- 项目：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-model-review-third-proxy-cpu-20261106`；执行提交 `27986d12fc01be7cb10a77abe783def01f47f577`。
- 指导：仓库根 README、Text2SQL README、实验路线图、复现契约，以及第三模型 CPU 恢复预注册。预注册偏离仅为后端从 GPU 改为本机 CPU；原 GPU 失败单独保留。
- 冻结数据：60个问题×表对、135个候选 mapping、4个匿名数据库；不抽样、不扩样。A/B packet SHA-256：`0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2`、`a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb`。
- C 模型只看到盲审题目、表对和 mapping 候选；候选展示顺序由固定 seed `20261106` 加 pair ID 打乱。没有读取 A/B 输出、Gold SQL、参考 JOIN、数据库名或 G-reasoner 分数。
- 模型：Google Gemma 4 E4B-it，revision `c53e9d33178b12afbad4a48334d21e19b8c29761`；权重 SHA-256 `cfbd3d2f1cd71bd471c37fe2bf8546d5028d41e5736f64e1ca6c6b8893125503`；Apache-2.0。

## 运行配置和命令

- 环境：`/root/miniconda3/envs/vllm/bin/python3.12`，Python 3.12.13、PyTorch 2.11.0、Transformers 5.9.0；CPU BF16、greedy decoding、每条最多384个新 token。`CUDA_VISIBLE_DEVICES` 为空，HF/Transformers 离线；64 CPU线程，进程 RSS 上限64 GiB。没有安装或升级依赖。
- 硬件：Intel Xeon Platinum 8360H，主机192逻辑CPU；运行限64线程。Smoke 峰值 RSS 9.64 GiB；Full 10.18 GiB。Full 进程墙钟726.43秒，生成720.50秒；未使用 GPU。
- Smoke run ID：`p0_fk_mapping_model_review_third_proxy_cpu_20261106_smoke_001`；Full run ID：`p0_fk_mapping_model_review_third_proxy_cpu_20261106_full_001`。
- 命令模板（Smoke/Full 分别替换 `--mode`、`--run-id`、`--output-dir`）：

  `CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=64 MKL_NUM_THREADS=64 GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code /root/miniconda3/envs/vllm/bin/python3.12 scripts/text2sql/run_p0_fk_mapping_model_review_third_proxy_cpu.py --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_A_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_B_packet.md --mode full --model /mnt/liansp3/sources/models/gemma-4-e4b-it --expected-commit 27986d12fc01be7cb10a77abe783def01f47f577 --run-id p0_fk_mapping_model_review_third_proxy_cpu_20261106_full_001 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/full_001/reviewer_C`。

## 结果

| 项目 | Smoke | Full |
|---|---:|---:|
| 有效输出 | 5/5 | 60/60 |
| 输入 token | 1,848 | 22,654 |
| 输出 token | 218 | 2,863 |
| 总 token | 2,066 | 25,517 |
| 生成耗时 | 55.67秒 | 720.50秒 |
| 进程墙钟 | 59.28秒 | 726.43秒 |
| 峰值 RSS | 9.64 GiB | 10.18 GiB |

三方只按“决策类别 + 接受 mapping ID 集合”精确匹配；多数支持者中至少两位置信度≥2，才纳入模型代理共识。

| 审阅者组合 | 共同有效单元 | 精确一致 | 一致率 |
|---|---:|---:|---:|
| A/B（两位 Qwen） | 57 | 28 | 49.12% |
| A/C（Qwen/Gemma） | 59 | 40 | 67.80% |
| B/C（Qwen/Gemma） | 58 | 34 | 58.62% |

三位都有效的单元中，23个三方一致、31个为二比一、3个三方各异。最终有56个高置信精确多数：16个 `multiple_mappings`、40个 `single_mapping`。其中56个可裁定；41个接受集合未覆盖所有候选，属于可区分集合；覆盖4个匿名数据库。未使用 Gold SQL 或人工标签，可信人工 Role 标签仍为0。

## Smoke/Full 分离后的排序样本门

在排序实验单独注册前，固定 seed `20261106`，按私有 question-key SHA-256 的稳定哈希排序选择5个问题作为 Smoke；所有属于这些问题的 pair 都从 Full 排除。选择过程不读取模型分数。结果：5个 Smoke 问题/5个 pair；Full 留下55个 pair，其中51个可裁定、38个可区分、覆盖4库；四库的可区分单元数按匿名顺序为5、10、10、13。因此独立探索排序的30/20/3数据门通过；4库均达到后续方向性筛选要求中的每库≥5样本，但这不代表主实验通过。

Smoke 的样本划分清单和逐题数据只在本地私有路径保存：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/preflight/split_manifest_private.json`。

## 产物、成本与结论

- 私有 C 回复与逐题数据：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_model_review_third_proxy_cpu_20261106_01/`。
- 匿名聚合 JSON：本报告目录的 `aggregate_summary.json`；SHA-256 `87fb10ac43015b3226d736becc0c0af6f8f000abe72f5cd950e3426924ece7c9`。上游 A/B 回复、C 原文、问题文本和数据库标识没有上传。
- 本轮本地模型确认 token：输入24,502、输出3,081、合计27,583；外部 API调用0。没有供应商 API 费用；CPU/GPU时间按本机资源记录，不折算成电费。
- 结论：异家族 Gemma4 提高了可用高置信精确多数的数量，模型代理排序诊断的样本门现在可过。模型间总体一致率仍有限；这不能证明多数标签正确。下一步只可注册一次模型代理探索性 G-reasoner 排序诊断，不可称作真实 Role 准确率、论文主实验或人工金标准。
