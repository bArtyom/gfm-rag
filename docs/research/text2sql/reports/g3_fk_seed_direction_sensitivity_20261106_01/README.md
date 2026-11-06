# G3：FK mapping 候选排序的起点敏感性诊断

**结果：INCONCLUSIVE；按预注册规则停止本支线。** 单端 seed 会改变一部分候选排序，但没有任何单端条件同时达到“Top-1 改变至少 20%、候选对反转至少 10%”的机制信号门；同时也没有达到“两项变化都不高于 5%”的无实质影响门。本实验不含正确标签，不能判断变化是否让排序变好。

## 研究问题与预注册边界

问题是：在同一组已知表对和 FK mapping 候选图上，将两个表端点都作为 query seed，或只将其中一个端点作为 seed，会不会实质改变 mapping 候选的相对顺序？核心假设是 seed 选择可能影响排序。本轮属于一次有界、探索性的机制诊断；不报告 Role Accuracy、Accepted@1、SQL EX 或方法收益。

本实验与此前代理标签上的排序 NO-GO 不冲突：这里不读取 A/B/C 模型审阅回复、共识标签、Gold SQL 或 SQL 执行结果，只计算不同 seed mask 下的分数和名次。表对仍来自参考 JOIN，因此问题是“给定端点对后的候选区分”，不是端到端 JOIN 发现，也不是无泄漏泛化评测。

冻结的三种条件如下：

| 条件 | Query seed | 与 A0 相比的变化 |
|---|---|---|
| A0 | 按字典序排列的两个表端点 | P0 适配的双端 seed 基线 |
| A1 | 字典序第一个端点 | 只改 `start_nodes_mask` |
| A2 | 字典序第二个端点 | 只改 `start_nodes_mask` |

A0 另重复一次，用于检查确定性。三种 seed 条件共用相同的 Query、表与 mapping 文本、归一化 1024 维 Qwen3 embedding、mapping 节点、四类有向端点边、关系向量、冻结 G-reasoner checkpoint 与排序 tie-break；不训练模型，也不修改消息传播代码。相对于 QuadGraph 原始实体检索流程，本轮使用的是已知表对上的任务适配诊断，不能据此声称复现了原始端到端查询检索。

## 预注册判据与样本

- Smoke：5 个冻结问题×表对、12 个 mapping 候选；通过条件为输入与图结构有效、四次/图分数有限、输出不含私有逐题字段。Smoke 不进入 Full 指标。
- Full：55 个问题×表对、123 个 mapping 候选，覆盖4个匿名数据库。候选图规模为42个双候选图、13个三候选图，合计81个候选对比较。
- 主要指标：A1/A2 相对 A0 的 Top-1 变化率；候选对严格顺序反转率。若 A0 或比较条件中的某候选对恰好打平，该对不进入反转率分母；本次排除数为0。Top-1 用稳定 mapping ID 做确定性 tie-break，另报告最高分并列。
- 机制信号门：至少一个单端条件 Top-1 改变率 ≥20%，且候选对反转率 ≥10%。无实质排序影响门：A1 与 A2 两项指标均 ≤5%。其余为 INCONCLUSIVE。这些是操作阈值，不是显著性检验或准确率门。
- 停止条件：只跑一轮 Smoke 和一轮 Full；Full 完成后无论结果如何停止，不追加 seed、图结构、模型或参数扫描。

## 来源、代码与配置

- 用户项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/g3-fk-dual-seed-sensitivity-20261106`。Full 实际执行时源码 commit 为 [`1d37a9f`](https://github.com/bArtyom/gfm-rag/commit/1d37a9fd7407ed31103f4e464c2e31d83b00c2bc)；runner 为 `scripts/text2sql/run_g3_fk_seed_direction_sensitivity.py`。
- 上游 QuadGraph/G-reasoner 代码：[`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，本研究沿用的冻结版本为 [`b3e4321`](https://github.com/RManLuo/gfm-rag/commit/b3e43219c49929da505244df4f0ba54c0947e4c4)，许可证 Apache-2.0。上游代码与 checkpoint 未修改。
- 实验前阅读了项目 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、P0 源码/输入语义审计与本实验预注册计划。按仓库要求使用独立结果目录、Smoke→Full 顺序和匿名 GitHub 归档。与计划的执行偏差只有一次环境入口故障，见下文；样本、指标、门槛和模型配置未变。
- 预注册计划：[`G3 方案`](../../plans/g3_fk_seed_direction_sensitivity_20261106.md)。冻结配置 SHA-256：`b5c4b4bc4ded01b2f442354bcac6b64f16669a46b180cf4a01be93158aea3652`。
- 数据：BIRD dev 的私有 pair-level packet；A/B packet 分别 SHA-256 `0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2`、`a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb`；私有 mapping manifest `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`；固定 split manifest `40234d6c3430b1cede8a1d5cdcdfce7c10a6834c136f38f31ff716cff98f14c0`。原题、表名、mapping 身份、SQL 和逐题分数未上传。
- G-reasoner checkpoint revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`；`model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`，`config.json` SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`。
- Embedding：本地 Qwen/Qwen3-Embedding-0.6B，1024 维；权重 SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`。完整 snapshot 指纹在本地 run manifest。仅本地加载，未发外部 API 请求。
- 固定 conda 环境 `gfmrag_greasoner_20261022`：Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence Transformers 5.1.1。随机 seed `20261106`；只用物理 GPU 1，进程内 `cuda:0`。
- 资源预检：4 张 RTX 4090 均空闲，GPU 1 可用显存约24,196–24,199 MiB；主机可用内存约444–446 GiB、192 CPU、磁盘剩余112 TiB。Swap 为2 GiB且已用满，但主机可用内存充足，运行期间没有资源错误。

## 运行记录和异常

1. `g3_fk_seed_direction_sensitivity_20261106_smoke_001` 在模型导入前停止：`conda run -n ... python3` 实际解析到 Python 3.9，因此找不到 Python 3.12 环境内已安装的 PyG。检查确认目标环境和 PyG 文件完整；没有安装或修改依赖。该失败没有加载 Qwen/G-reasoner、没有 GPU 推理，也没有模型 token。日志与失败清单留在本机。
2. `..._smoke_002` 改用目标环境内的 Python 3.12 绝对解释器后通过：5/5 图、12 个候选、20 次 forward 均产生有限分数；A0 重复最大绝对误差为0。峰值 GPU 分配 2,531,396,608 bytes，峰值 RSS 4,721,029,120 bytes；墙钟10.04秒、CPU 13.62秒。Qwen 编码输入528 token、输出0。
3. `..._full_001` 完成：55/55 图、123 个候选、220 次 forward；墙钟10.64秒、CPU14.96秒，峰值 GPU 分配2,979,721,216 bytes，峰值 RSS4,719,513,600 bytes。预算上限为 GPU/RSS各8 GiB、CPU900秒、wall1200秒，均未超限。Qwen 编码输入2,695 token、输出0。

实际 Full 命令如下；Smoke_002 参数相同，仅将模式、run ID 和输出目录换为 `smoke`、`g3_fk_seed_direction_sensitivity_20261106_smoke_002` 与 `.../smoke_002`。这些输入路径指向本机私有材料：

```bash
CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code conda run -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3 scripts/text2sql/run_g3_fk_seed_direction_sensitivity.py --mode full --run-id g3_fk_seed_direction_sensitivity_20261106_full_001 --expected-commit 1d37a9fd7407ed31103f4e464c2e31d83b00c2bc --config configs/text2sql/g3_fk_seed_direction_sensitivity_20261106.yaml --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_A_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/reviewer_B_packet.md --private-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/private_manifest.json --split-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/preflight/split_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cuda:0 --output-dir /mnt/liansp3/sources/results/gfmrag_g3_fk_seed_direction_sensitivity_20261106_01/full_001
```

Smoke 与 Full 的完整 argv、环境变量和输入指纹保存在本地 `attempt_manifest.json` / `run_manifest.json`。外部 API 与 SQL 执行均为0。

## Full 结果

| 相对 A0 | Top-1 改变 | Top-1 改变率 | 严格候选对反转 | 反转分母 | 候选对反转率 | 预注册判据 |
|---|---:|---:|---:|---:|---:|---|
| A1：第一端点 | 4/55 | 7.27% | 6 | 81 | 7.41% | 未到机制信号门；也未到无实质影响门 |
| A2：第二端点 | 6/55 | 10.91% | 7 | 81 | 8.64% | Top-1 超过5%，反转率低于10%；未到任一完整门 |

所有 Full 图均无最高分并列；A0 与重复 A0 的最大 mapping score 绝对误差为0。每图候选分数范围的均值：A0 为0.4742，A1 为0.4697，A2 为0.4714。范围变化只作描述，不表示正确性。

**结论：INCONCLUSIVE。** 起点条件确实改变部分排序，但变化幅度没有同时达到预设的机制信号门；也不能说排序对起点不敏感。A1 或 A2 哪个更正确无法判断，因为本实验不读取任何标签。按停止条件不再追加 seed 方向或图结构变体。

## Token、费用和本地结果

- 共享 token 账本记录本实验 5 次本地 Qwen 编码批次：Smoke 输入528、Full 输入2,695；合计输入3,223、输出0、总计3,223 token；无 usage 缺失请求。初次失败发生在模型调用前，不产生 token 请求。
- 本轮外部模型 API 请求数为0，API 费用 CNY 0。账本没有本地算力电价；本地 GPU 计算不折算货币。测得 Qwen 编码耗时约1.292秒，G-reasoner forward 耗时合计约2.836秒；这是模型操作计时，不是功耗或电费估算。
- 私有 Smoke/Full 分数、输入清单和日志只保存在本机受限目录 `sources/results/gfmrag_g3_fk_seed_direction_sensitivity_20261106_01/` 与 `logs/gfmrag_g3_fk_seed_direction_sensitivity_20261106_01/`。GitHub 只归档匿名报告和聚合 JSON。

## 限制与下一步

这是被反复用于开发的 BIRD dev 子集；表对由参考 JOIN 派生，只能讨论条件式 mapping 排序。仅有55个 Full 表对、4个匿名数据库，且没有人类真值。`INCONCLUSIVE` 既不证明双端 seed 导致失败，也不支持单端 seed 优于双端 seed。该诊断按预注册规则结束，不继续参数、方向或图结构搜索。若将来要提出真实 FK 角色准确率，需要独立可信的标签与单独预注册；模型代理标签不能替代人工真值。
