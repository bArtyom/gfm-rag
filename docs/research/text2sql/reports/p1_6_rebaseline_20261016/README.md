# P1.6：历史差异审计与新 1024 基线冻结

> **状态：输入预检通过；前两次 smoke 失败已保留。运行器修复及 CPU 回归测试已提交，5/5 通过；尚无修复后的 GPU smoke。** 2026-10-17 10:44 UTC 资源检查时四张 GPU 均未达到预注册的 8 GiB 空闲显存门槛，因此没有启动模型任务。已重新核对用户仓库 `main` commit `bf3a1d28186b86815c4ff7873fff8368d761a027` 的实验指导；模型运行仍须待 GPU 资源门通过后再开始。旧 P1/P1.5 历史逐题复现 FAIL 与 FK/Role Gate FAIL 均保持。

## 研究问题与假设

- **问题：** 在旧运行未留存 embedding/rank cache、历史差异无法从原始分数回放的情况下，能否用固定的 BIRD dev 输入、官方 Qwen3 encoder 与有序候选 manifest 建立一份可复核的 1024 基线？
- **核心假设：** 当前固定输入的一次 1024 编码缓存可以在同一 CPU scorer 上重复排序；相同候选、标签、token budget 与确定性 tie-break 下，逐题 Top-K、budget selection、Recall 与完整覆盖将完全一致。
- **层级：** P1.6 复现诊断与新基线 Gate；BIRD dev 仅为 exploratory。不是 P2a、训练、JOIN/Role、GNN、SQL 生成或端到端 EX 实验。

## 预注册预算、成功判据与停止条件

- 先运行 5 题、1 个数据库的 smoke；重复编码同一 smoke 输入以报告最大浮点差、Top-K 边界间隔与是否有名次变化。
- Smoke 通过后，对全量 1,534 题、11 个数据库和 873 个 schema nodes 做一次固定参数 1024 前向。旧缓存不存在，因此新 query/node 向量只保存在本地私有结果目录。
- 对同一 float32 向量缓存连续运行两次完全相同的 scorer。排序按分数降序；**仅对完全相等的 float32 分数**用 stable node ID 字典序破同分。记录 5/10/20 Top-K、512/1024/2048 token budget、完整覆盖及分数哈希。
- 资源预算：GPU wall ≤900 秒、CPU process time ≤1,800 秒、峰值 RSS ≤16 GiB、最多 8 个 CPU 线程。复用既有 `think2sql_20260909` 环境、GPU 1 和本地模型；不安装/升级依赖、不下载模型、不调用 API、不训练、不执行 SQL。
- **P1.6 Gate 通过：** 固定输入和有序 node-ID/text-hash manifest 可重建；smoke 数据/向量/输出有效；全量两个 scorer pass 的逐题 Top-K、budget selection、Recall、完整覆盖与 score digest 完全相同；Table 分母为 1,534、Column/budget 分母为 1,460；tie 与边界数值已记录。
- 任一冻结 hash 不符、输入/标签/分母错误、smoke 失败、资源超限或结果可能覆盖时停止并保留现场；smoke 未通过不跑 full；P1.6 Gate 未通过不跑 P2a。历史 91 项差异原因若无法从留存证据确定，限定审计后标为 unresolved，不试新维度或改写旧 Gate。

## 固定来源与运行边界

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，预注册实验代码 commit `9fd0f192985d20a2a61b9d15de625d2c9ef1422d`；2026-10-17 10:44 UTC 复核时 `main` 为 `bf3a1d28186b86815c4ff7873fff8368d761a027`。仓库内已阅读根 README、Text2SQL README、roadmap、reproducibility contract 与当前 P1.6 指导。
- Encoder 来源：GFM-RAG 官方 `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0；选择性导入原 encoder 源文件，不修改上游实现。
- 数据：本地冻结 BIRD dev；1,534 questions / 11 DBs / 873 candidate nodes；Table labels 1,534，Column labels 1,460；Gold 只用于离线计分。
- 模型：`/mnt/liansp3/sources/models/qwen3-embedding-0.6b`，1024 维，query instruction 沿用 P1.5，batch size 32；继续验证 P1.5 的数据、模型 manifest、query prompt 与 schema-text 哈希。
- 实现入口：[`run_p1_6_rebaseline.py`](../../../../../scripts/text2sql/run_p1_6_rebaseline.py)。
- 本地结果：`/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p1_6_rebaseline_20261016/`。逐题记录和向量缓存不上传；GitHub 仅保存匿名聚合、公开可重建配置、代码与候选 ID/text hash manifest。

## 当前进度与已处理异常

- 输入预检通过：1,534 questions、11 DB、873 nodes（75 tables、798 columns）、1,460 column-eligible questions；冻结 schema/query/node manifest hash 与协议一致。历史 P1/P1.5 指标对比为 14,896 项检查、14,805 项相同、91 项不同；旧 vectors/scores/rank lists 不存在，差异原因保持 unresolved。
- Smoke 尝试 `p1_6_smoke5_20261016_01` 在模型编码后因 per-question `column_hits` 被初始化为 `None` 而无法写列命中指标；修正在公开运行器中已提交。
- Smoke 尝试 `p1_6_smoke5_20261016_02` 的模型加载与编码完成，但 scorer 汇总 schema token 数时把数据库节点索引当作节点对象访问，因而失败。该指标现按索引从当前有序节点数组取回 token count。两次失败均保留在本地私有输出，不上传含逐题信息的日志或记录。
- 最新静态审计还发现两处 Full 门禁缺陷：Full 在哈希时包含了 Smoke 落盘前拆出的 `ordered_node_manifest`，且从 `smoke_summary.json` 读取实际只存于 `smoke_receipt.json` 的输入清单哈希。现由共享 `canonicalize_input_record()` 生成唯一 manifest 字节串；Full 以 Smoke receipt 校验该哈希，并核对已完成的 Smoke `run_start`、项目 commit、summary hash、节点清单文件及其独立有序摘要。
- 上述代码和 CPU 回归测试作为独立源码提交推送：commit `9fd0f192985d20a2a61b9d15de625d2c9ef1422d`，tree `7fb6864abf1e50c9a07443ec49000ee33d2725a8`。测试覆盖 Smoke 保存后 Full 重算哈希一致、修改输入字段导致 hash 改变、改变节点顺序导致独立 node digest 改变，以及 Full 读取完成的 Smoke receipt 并拒绝不同代码 commit。
- CPU 回归命令：`/root/miniconda3/envs/think2sql_20260909/bin/python3 -m pytest -q tests/test_p1_6_input_manifest.py`；环境 Python 3.12.14 / pytest 9.0.1；结果 **5 passed**（0.15 s）。
- 新代码下 CPU 预检 `p1_6_preflight_20261017_03` 通过，source commit `9fd0f192985d20a2a61b9d15de625d2c9ef1422d`：1,534 questions、11 DB、873 nodes（75 tables、798 columns）、1,460 column-eligible questions；schema hash `b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a`，query prompt hash `a33e140e6ae5a362b5480a437bc77431b8c878f000e3ea03dadba38108b25634`，ordered node manifest content hash `4e930d3b906d46d77381edbfee8bfb57ab04fc09d47b9e90fc6272986cceaa5a`。
- CPU 预检完整命令：

  ```bash
  /root/miniconda3/envs/think2sql_20260909/bin/python3 scripts/text2sql/run_p1_6_rebaseline.py \
    --mode preflight --run-id p1_6_preflight_20261017_03 \
    --expected-commit 9fd0f192985d20a2a61b9d15de625d2c9ef1422d \
    --output-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/preflight_03 \
    --legacy-root /mnt/liansp3/sources/projects/quadrag \
    --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
    --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
    --previous-run-dir /mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01 \
    --p1-5-run-dir /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03 \
    --gpu-id 1
  ```

- GPU 资源快照（2026-10-17 10:44:23 UTC）：GPU 0/1/2/3 空闲显存分别为 7,038 / 1,248 / 0 / 5,618 MiB，利用率为 25% / 32% / 24% / 21%；均低于所需 8,192 MiB 空闲显存门槛。因此未启动新的 Smoke 或 Full，也未改变模型、batch 或资源门槛。首次通过资源门后使用全新 run ID/目录跑 5 题 Smoke；满足浮点、分母、manifest、预算和输出条件后才启动 Full。

最终报告将在后续实验完成时补入实际 Smoke/Full 命令、环境与资源、向量/排序结果、91 项差异分类、P1.6 Gate、异常及结论。P2a 仅在本轮 Full Gate 通过后另建独立报告。
