# P1.6：历史差异审计与新 1024 基线冻结

> **状态：预注册和输入预检通过；5 题 smoke 正在修复运行器错误，尚未通过。** 本轮遵循仓库 commit `ec7ebe697b0350ac9b4b137c68e79a52a97255a3` 的 [P1.6 → P2a 执行指导](../../plans/p1_6_rebaseline_then_p2a_20261016.md)。旧 P1/P1.5 历史逐题复现 FAIL 与 FK/Role Gate FAIL 均保持。Smoke 未通过前不运行全量。

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

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，预注册 commit `ec7ebe697b0350ac9b4b137c68e79a52a97255a`；仓库内已阅读根 README、Text2SQL README、roadmap、reproducibility contract、P1.5 review 与当前 P1.6 指导。
- Encoder 来源：GFM-RAG 官方 `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，Apache-2.0；选择性导入原 encoder 源文件，不修改上游实现。
- 数据：本地冻结 BIRD dev；1,534 questions / 11 DBs / 873 candidate nodes；Table labels 1,534，Column labels 1,460；Gold 只用于离线计分。
- 模型：`/mnt/liansp3/sources/models/qwen3-embedding-0.6b`，1024 维，query instruction 沿用 P1.5，batch size 32；继续验证 P1.5 的数据、模型 manifest、query prompt 与 schema-text 哈希。
- 实现入口：[`run_p1_6_rebaseline.py`](../../../../../scripts/text2sql/run_p1_6_rebaseline.py)。
- 本地结果：`/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p1_6_rebaseline_20261016/`。逐题记录和向量缓存不上传；GitHub 仅保存匿名聚合、公开可重建配置、代码与候选 ID/text hash manifest。

## 当前进度与已处理异常

- 输入预检通过：1,534 questions、11 DB、873 nodes（75 tables、798 columns）、1,460 column-eligible questions；冻结 schema/query/node manifest hash 与协议一致。历史 P1/P1.5 指标对比为 14,896 项检查、14,805 项相同、91 项不同；旧 vectors/scores/rank lists 不存在，差异原因保持 unresolved。
- Smoke 尝试 `p1_6_smoke5_20261016_01` 在模型编码后因 per-question `column_hits` 被初始化为 `None` 而无法写列命中指标；修正在公开运行器中已提交。
- Smoke 尝试 `p1_6_smoke5_20261016_02` 的模型加载与编码完成，但 scorer 汇总 schema token 数时把数据库节点索引当作节点对象访问，因而失败。该指标现按索引从当前有序节点数组取回 token count。两次失败均保留在本地私有输出，不上传含逐题信息的日志或记录。
- 当前仍处于 smoke 门禁阶段。修复后需重新执行 5 题 smoke；只有成功且满足浮点有限、分母正确等冻结判据，才运行全量。

最终报告将补入每次实际命令、环境与资源快照、输入和模型哈希、smoke 与 full 结果、91 项差异分类、P1.6 Gate、异常及结论。P2a 仅在本轮 Gate 通过后另建独立报告。
