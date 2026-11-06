# P0：FK mapping pair-level 双人盲审材料准备

**状态：`REVIEW_PACKET_READY_PENDING_HUMANS`。** 5 题 Smoke 与 60 题 Full 均通过材料生成门。材料已保存在本地私有目录，尚无任何人类标签；本轮没有运行 G-reasoner、Dense 排序、模型推理或 SQL 执行。

## 研究问题与痛点

旧的 FK 定义分歧包有 49 道独立问题、51 个“问题×表对”审阅单元，其中只有 8 个单元含至少两个不同的有效 FK mapping。它适合检查候选定义分歧，但无法提供已登记映射排序 Pilot 所需的可区分候选数量。

冻结容量审计发现：1,140 个含 `JOIN ON` 的 BIRD dev 问题中，1,127 个可提取表对；共找到 176 个至少有两个不同有效 FK mapping 的“问题×表对”，涉及 175 道问题和 4 个数据库。另 13 道题因 `JOIN_PAIR_EXTRACTION_INCOMPLETE` 未解析。本轮仅从身份完整、可稳定映射的解析结果中抽样；未把 13 道未解析题作为负例或零候选样本。

本轮唯一问题是：**给定参考 JOIN 中已提取的表对时，两位独立审阅者能否对这对表的 FK mapping 接受集合给出足够一致的判断，以便后续评价冻结 G-reasoner 的 Accepted@1？**

这是“表对已知”的条件式映射判断。表对来自参考 SQL，因此评审不是完全 Gold-free 的在线任务；它不评估端到端表检索、无 FK JOIN、SQL 执行或跨数据库泛化。

## 预注册方案与实际处理

- 样本单位为“问题×表对”；每道题最多取一个含至少两个不同、完整、有效 mapping 的表对。
- 用固定 seed `20261106` 对 4 个匿名数据库分层抽样。每库目标 15 个；Smoke 5 题不进入 Full。最终 Full 为 60 个不同问题，各匿名数据库 15 个。
- FK 候选按数据库、子表、有序列对和父表形成稳定 mapping 身份。相同声明折叠为一个候选；复合 FK 若入样则作为完整有序列对呈现。本次 60 个单元没有抽到复合 FK，因此本轮不提供复合 FK 的人工审阅证据。
- A、B 两份材料都显示问题、表对名称及全部候选 FK 列映射。表名和列名必须可见，方便判断业务角色；数据库 ID、题目 ID、Gold SQL、`ON` 表达式、方法来源、模型分数和排名不显示。两份包的案例和候选顺序分别打乱，mapping ID 在两包之间保持一致。
- 审阅者需要给出 `single_mapping`、`multiple_mappings`、`cannot_determine`、`no_declared_fk` 或 `other`，填写接受 mapping 集合、置信度和理由类别。两名审阅者的决定与接受集合完全一致，且双方置信度均不低于 2，才算共识；模型不代标、不裁决。

本轮只新增独立材料准备执行器：[prepare_p0_fk_mapping_pair_level_review_packet.py](../../../../../scripts/text2sql/prepare_p0_fk_mapping_pair_level_review_packet.py)。没有改动 GFM-RAG 上游实现、G-reasoner 传播算法、模型权重、训练目标或已有盲审生成器。执行器复用已冻结的输入加载器、FK identity 和 SQLGlot 表对解析规则；没有读取旧 A/B 回复内容。

## 数据、代码与环境

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，实验分支：`research/p0-fk-mapping-review-packet-20261106`。
- 预注册方案及容量审计来自父提交 `8082da5bdb5dc7e5047ef6e10c6cfd9c7ce13880`；正式执行代码提交为 [`0077db570a5c1f68dbb74598777593a75b3d1d27`](https://github.com/bArtyom/gfm-rag/commit/0077db570a5c1f68dbb74598777593a75b3d1d27)。执行器 SHA-256：`83be039b8cb2a377974cebff065786d45fbef96f38a89d90f341d051b8c5110c`。
- 输入为本地冻结的 BIRD dev 问题和 schema、有效 FK artifact、canonical crosswalk 与 P1.5 full 结果。五份输入 SHA-256 见 [`aggregate_summary.json`](aggregate_summary.json)。问题、Gold SQL、数据库名、表对键、mapping identity 和逐题 manifest 未提交到 GitHub。
- 已阅读仓库根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、本轮预注册方案和容量审计报告。仓库根目录没有 `AGENTS.md`；实验同时遵循本任务提供的实验室守则。
- 环境：conda `think2sql_20260909`、Python 3.12.14、SQLGlot 28.0.0。CPU-only；Full 峰值 RSS 0.033691 GiB，墙钟 0.855841 秒、CPU 0.845503 秒。运行前记录 447 GiB 可用内存、192 CPU、磁盘余量 112 TB。主机有 4 张 RTX 4090；`nvidia-smi` 显示 GPU 0 使用 21,965 MiB、GPU 1/2 各 11 MiB、GPU 3 使用 3,665 MiB，任务没有申请或干扰 GPU。
- 外部 API token：输入 0、输出 0、合计 0；费用 CNY 0.00。没有本地模型请求、训练、SQL 执行、依赖安装或资源下载。

## 运行命令

在本仓库根目录、提交 `0077db570a5c1f68dbb74598777593a75b3d1d27` 下运行。Smoke 与 Full 使用独立输出目录；重跑必须使用新的目录，不能覆盖本轮产物。

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
  conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/prepare_p0_fk_mapping_pair_level_review_packet.py \
  --mode smoke \
  --run-id p0_fk_mapping_pair_level_blind_review_20261106_01 \
  --expected-commit 0077db570a5c1f68dbb74598777593a75b3d1d27 \
  --repo-root . \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
  --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
  --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/smoke_001
```

Full 使用同一输入与 commit，另加通过的 Smoke 收据：

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
  conda run --no-capture-output -n think2sql_20260909 python3.12 \
  scripts/text2sql/prepare_p0_fk_mapping_pair_level_review_packet.py \
  --mode full \
  --run-id p0_fk_mapping_pair_level_blind_review_20261106_01 \
  --expected-commit 0077db570a5c1f68dbb74598777593a75b3d1d27 \
  --repo-root . \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
  --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
  --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
  --smoke-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/smoke_001/smoke_summary.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001
```

## 结果与验证

| 检查项 | Smoke | Full |
|---|---:|---:|
| 状态 | `SMOKE_PASS` | `REVIEW_PACKET_READY_PENDING_HUMANS` |
| 样本 | 5 个问题，覆盖 4 个匿名数据库 | 60 个不同问题×表对，4 个匿名数据库各 15 个 |
| Full 与 Smoke 重叠 | — | 0 个问题 |
| 可解析候选总体 | 1,127 / 1,140 个 JOIN-ON 问题 | 与 Smoke 输入一致 |
| 多 mapping 候选总体 | 176 个问题×表对、175 道问题、4 个数据库 | 与 Smoke 输入一致 |
| 入选 mapping 数 | — | 45 个表对有 2 个候选，15 个有 3 个，共 135 个候选 |
| A/B 案例及候选集合 | 一致 | 一致 |
| A/B 展示顺序 | 案例顺序不同 | 案例顺序不同；31/60 个案例的 mapping 展示顺序不同 |
| 标签 / 模型结果 | 0 | 0 |

A、B 两份包各有 60 个案例和 60 个表对；回复 CSV 各有 60 条空白记录。`sha256sums.txt` 列出的所有 Full 产物均校验通过。实验目录权限为 `0700`，包、manifest、收据和日志权限为 `0600`。Full 包本地私有入口：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_pair_level_blind_review_20261106_01/full_001/`；Smoke 收据：`.../smoke_001/smoke_summary.json`。GitHub 仅包含本报告、匿名聚合、Smoke 汇总、配置和验证摘要，不含审阅包、空白 CSV、原始 SQL、题目、数据库或逐题 manifest。

## 结论与下一步

**材料准备门通过，人工标签门仍未通过。** 这轮只证明 60 个盲审单元能按预定规则抽取、完整呈现并在 A/B 间一致；它没有判断哪个 FK mapping 正确，也没有产生 G-reasoner、Dense 或 SQL 的效果指标。

下一步必须由两位真实审阅者独立填写 A/B 回复表。只有审阅决定、接受 mapping 集合完全一致且双方置信度至少为 2，才计入共识。之后另行检查既有 Pilot 门：排除 Pilot 自己的 5 个问题级 Smoke 后，至少 30 个可裁定单元、其中至少 20 个结构可区分单元、覆盖至少 3 个数据库；接受集合还需同时有被接受和被拒绝候选。通过后才能另行冻结 G-reasoner 与 Dense cosine 的 Accepted@1 Pilot。**当前可信人工标签仍为 0，因此本轮不运行模型 Pilot。**

## 归档文件

- 预注册方案：[p0_fk_mapping_pair_level_blind_review_20261106.md](../../plans/p0_fk_mapping_pair_level_blind_review_20261106.md)
- 匿名 Full 汇总：[aggregate_summary.json](aggregate_summary.json)
- 匿名 Smoke 汇总：[smoke_summary.json](smoke_summary.json)
- 冻结配置：[experiment_config.json](experiment_config.json)
- 产物验证：[verification_summary.json](verification_summary.json)
