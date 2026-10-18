/root/.profile: line 9: true_PROXY: command not found
# P2b R0/R1 Values 文本消融：预注册方案

> 状态：**已预注册，尚未运行**。对应实验记录：[P2b 报告](../reports/p2b_values_ablation_20261018_01/README.md)。本计划只覆盖一组有限消融与重复编码控制，不扩展为表示参数搜索。

## 研究问题与核心假设

**研究问题：** 在其余 Schema 字段、候选集、查询、编码器维度和 Cosine scorer 固定时，列文本中的 `values` 描述是否帮助列召回，还是主要增加文本长度并影响预算内的完整 Schema 选择？

**核心假设 H1：** R1 移除 Values 后，BIRD dev 全体 column-eligible 问题的 Column R@10 相对 R0 提升至少 1.0 个百分点，且数据库聚类 bootstrap 的 95% 区间下界高于 0；同时固定非饱和子集的 Column R@10 与 Complete@1024 均不低于 R0 超过 1.0 个百分点。满足条件只表示值得做独立数据库验证，不改变 P2a 的 NO-GO，也不支持跨库结论。

**实验层级：** 最小消融；BIRD dev 是反复用于开发的探索集，结果不是独立测试证据。它可能改变对 Values 字段是否保留的选择，因此可影响后续 Schema 表示主张。

## 对照与固定项

| 条件 | 列 Schema 文本 | 用途 |
|---|---|---|
| R0 | Name + Type + Description + Format + Values（有字段才写） | 当前冻结文本基线 |
| R0-repeat | 与 R0 完全相同；同一 CPU encoder 再编码一次节点文本 | 测量同文本前向的数值及排序变化，不作为独立种子 |
| R1 | R0 移除 `values:` 字段；其他字段与次序不变 | 唯一消融因素 |

固定 1024 维 Qwen3-Embedding-0.6B、Cosine、节点候选全集、1534 个问题及冻结 Gold 标签、stable node-ID tie-break。三个新编码条件共用同一批本地 CPU 编码的查询向量；R0-repeat 只重复编码 Schema 节点。另以 P1.6 的冻结 vLLM/GPU R0 cache 做 scorer parity 与后端差异参考，**不把跨后端差异解释为 Values 效应**。R0 与 R1 的主要比较只使用同一 Transformers CPU 后端和相同查询向量。

## 来源、数据与版本

- 项目仓库：`https://github.com/bArtyom/gfm-rag`，`main`；预注册基线 commit `8d00c66532d0110ea09e02d220ff3dbb45b50b22`。实际运行 commit 记录在 `run_start.json` 与最终报告。
- 参考实验：P2a.5 计划与报告；其发现 Values 字段的分层相关性，但明确没有因果证据。
- 数据：冻结 BIRD dev，1534 题、11 DB、873 Schema 节点；列指标分母为 1460 题 / 6523 Gold columns。沿用 P1.6 输入 manifest、查询顺序和 Gold-free Schema 构造；标签只用于离线评价。
- 冻结 P1.6 输入/cache SHA、节点及模型 manifest 必须由 runner 校验；不读取 Gold SQL 来构造 R1 或打分。
- 模型从 `/mnt/liansp3/sources/models/qwen3-embedding-0.6b` 本地入口读取；该软链接已解析到个人模型目录，模型文件 manifest SHA256 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`。

## 编码与实现

- 使用本地 `think2sql_20260909` 环境（Python 3.12.14、PyTorch 2.8.0、Transformers 4.57.1、NumPy 2.2.6），模型离线加载；不调用 API、不下载模型、不安装或升级依赖。
- 四张 RTX 4090 在预检时均处于高利用率，故本轮选择 CPU；CPU 为 Xeon Platinum 8360H，支持 AVX512-BF16。官方项目 `Qwen3TextEmbModel` 使用本地 vLLM，而此环境没有可用空闲 GPU；本轮使用同一个本地 Transformers `AutoModel` 后端编码 R0/R0-repeat/R1，按 Qwen3 模型卡的 left-padding last-token pooling、1024 维输出、float32 L2 normalization 执行。该后端差异在报告中单列，不与原 vLLM cache 混作同后端结果。
- batch size 32，max sequence length 8192；固定 P1.5 query instruction 已包含在冻结 prompt 中。相同 query 向量用于全部三个 CPU 条件。
- R1 从原始 Schema description metadata 重新序列化，只跳过 `value_description`；先要求 R0 的 node ID、顺序和 text hash 与 P1.6 完全一致，再检查 R1 唯一差异为列节点 Values 字段。
- budget 重新使用同一 tokenizer 计数；顺序排序由相同 P1.6 scorer 处理。保持训练、SQL 执行、GFM、JOIN 角色模型均为关闭。

## 指标与分析

1. **唯一主指标：** R1−R0 的 Column R@10 query-macro，覆盖全体 1460 个 column-eligible 问题；报告百分点差及按数据库簇重采样 10000 次、seed `20261019` 的 percentile 95% CI。
2. **固定护栏：** 非饱和子集使用 P1.6/R0 原始全 Schema token 总量固定数据库成员（5 DB / 706 题），不随 R1 文本长度变化改分母；报告 Column R@5/@10/@20 与 Complete@512/@1024/@2048。R1 在该子集 Column R@10、以及全体与固定子集 Complete@1024 均不得下降超过 1.0 pp。
3. **解释性指标：** R0/R1 列文本长度 token 中位数/P90、Values 字段覆盖率、三种预算 Gold-only fit、Complete@预算、query/database macro、数据库级匿名结果；报告每个版本的 2048-token 饱和数据库集合。
4. **数值控制：** R0 与 R0-repeat 向量最大绝对差、cosine 相似度分位数、Column Top-K set/rank 变化和指标 delta；同时报告 CPU R0 相对冻结 P1.6 R0 cache 的 backend/device 对照，避免把数值变动归因给 Values。
5. 报告样本数、缺失值、全部失败和异常。仅上传匿名 aggregate、配置、代码和报告；逐题记录、向量、输入清单、原始 Schema/Gold 与运行日志留在本机。

## 预算、成功判据与停止条件

- 资源上限：CPU process time 7200 s、wall 3600 s、RSS 16 GiB、最多 8 个 CPU 线程；只运行一次 5 题 smoke 和一次 1534 题 Full。Full 内含 query 1 pass、R0 node 2 passes、R1 node 1 pass；不再加 seed 或重复直到有利。
- 先跑前 5 题/1 DB smoke，检查冻结输入、R0 完全相同、R1 只删 Values、向量 shape/有限值/范数、输出格式与本地 CPU 可行性；smoke 不进入正式结果。
- Full 成功门：全部 1534 题 / 11 DB 及 1460 列分母完整；P1.6 冻结 cache 的 Cosine scorer parity 精确；所有输入、模型和代码 hash 校验通过；资源预算内完成。
- H1 成功门：全体 Column R@10 提升至少 1.0 pp 且数据库 bootstrap 95% CI 下界 > 0，两个护栏均通过。通过只将 Values-removal 作为候选送去独立数据库验证，不覆盖 P2a NO-GO。
- 任一 hash/分母/R0 text parity 错误、缺少模型/数据、非有限向量、smoke 失败、预算越界或输出有私有逐题数据风险即停止；不要启动第二组消融。若 H1 不通过，P2b 本轮结论为 NO-GO，并停止 Values 参数扩展。

## 执行记录

- Smoke：`p2b_values_smoke5_20261018_01`，独立本地结果目录 `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/smoke_5q_20261018_01`，日志 `/mnt/liansp3/logs/gfmrag_p2b_values_smoke5_20261018_01.log`。
- Full：`p2b_values_full1534_20261018_01`，仅在 smoke 成功后启动；独立本地结果目录 `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/full_1534_20261018_01`，日志 `/mnt/liansp3/logs/gfmrag_p2b_values_full1534_20261018_01.log`。
- 完整启动命令、环境快照和实际时间由 runner 写入本地 `run_start.json`；公开报告只保留可复现命令模板及安全聚合。

## 指导冲突

仓库旧版 `experiment-roadmap.md` 仍写着“P0 是唯一立即执行任务”，而当前研究首页、已完成的 P1.6/P2a 状态及 P2a.5 专项计划允许在其诊断通过后单独注册 R0/R1。采用较新且更具体的 P2a.5 专项计划，不回溯修改旧路线图；本轮仍明确标记 BIRD dev 为 exploratory，不能声称独立泛化。
