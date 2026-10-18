# P2c 预注册执行方案：Retrieval / Context 双视图 2×2 因子实验

> **计划制定于 2026-10-18；执行状态：STOPPED，注册的 Full 恢复也因实现错误失败，未产生科学结果。** 本文件为新的独立研究问题，不是 P2b 已失败 Values 消融的扩展参数搜索；如果未验证私有向量缓存与完整输入，停止并报告缺口。
>
> 依据：[P2b 最新分析](../reports/p2b_review_20261018/README.md)、[P2b 正式结果](../reports/p2b_values_ablation_20261018_01/README.md)、[P2a.5 错误/FK 审计](../reports/p2a_5_error_audit_20261018_01/README.md)。

## RQ、假设和因果隔离

**RQ：** 在保持 Schema 检索语义的前提下，是否可以让进入 Embedding 的文本包含 Values，而最终检索返回的 Schema Context 省略 Values，从而降低 Token Budget 的浪费并保持 Column 排序质量？

- H1（结构不变量）：V01 与 V00 的 Column / Table Top-K **逐题、逐元素完全一致**，因为候选向量、query 向量、Cosine 分数没有改变；只替换后续 Context 的文本及 token_count。
- H2（新主探索目标）：固定原 Schema 长度定义的 5 DB / 706 题非饱和集，V01−V00 的 **Complete@1024 至少 +3.0 pp**，且全体 1460 题 **Complete@1024 至少 +5.0 pp**，数据库聚类 95% CI 下界 >0；至少 3/5 非饱和 DB 为正或零且至少 2 DB 严格为正（避免仅依赖单库）。
- H3（诊断，不作为第二套挑赢家门槛）：V01 与 V11 的不同，揭示“保留 Values 参与排序”对短文本预算覆盖的影响；任何收益必须区分排名/内容长度与两者交互。

上面 H2 阈值**是计划目标，不是结果**；若不满足，只记录 NO-GO，不进行事后参数扫描。BIRD dev 已被反复分析，H2 只是进一步独立 DB 实验资格筛查，不是泛化证明。

## 四臂设计：所有条件共用同一批 CPU 缓存

| Run | 1024-D Dense 打分向量 | 预算内 Schema Context 文本 | 作用 |
|---|---|---|---|
| V00 | P2b R0，带 Values | P2b R0，带 Values | 旧 R0 对照 |
| **V01** | **P2b R0，带 Values** | **P2b R1，不带 Values** | 主要假设——检索/呈现解耦 |
| V10 | P2b R1，不带 Values | P2b R0，带 Values | 固定输出长度测排名变化 |
| V11 | P2b R1，不带 Values | P2b R1，不带 Values | 旧 R1 对照 |

注意：Context View 的删除是“候选字段文本在 SQL Prompt 中如何呈现”的模拟，不删除 DB 列、不更改 SQL JOIN 结构，也不把 Gold 用于排序。V01/V10 是**此前未运行**的新组合，不应预填测量值。

### 全量固定输入

- 数据 BIRD dev 1534 题 / 11 DB / 873 Schema 节点（75 tables，798 columns），Column eligible **1460** / 6523 Gold Column；另保留 74 不可评题计数。
- 固定困难子集：**5 DB / 706 列可评题**，由 P2b 的原始 R0 schema token >2048 判定；不得因为 R1 缩短 Schema 而变更子集。
- 读取 P2b Full 私有产物 `embedding_cache_cpu_private.npz`，已登记其 keys 为 `query_vectors, r0_node_vectors, r0_repeat_node_vectors, r1_node_vectors`；输入哈希、model manifest、P1.6 baseline、P2b 公共 aggregate checksum 必须核验。**先做实际存在性与 shape check**，不可把用户未上传的本机文件视为已经可供分析助手读取。
- R0/R1 节点 ID、顺序和文本分别按 P2b 已冻结的序列化规则重建，核对有序 manifest hash、文本 hash、token count 与 P2b。R1 仅删除 Column 的 `value_description`，共 278 列有 Values。
- 使用**P2b 同一 CPU backend 的 R0/R1 node vectors 和 CPU query vectors**，禁止把 P1.6 的 GPU/vLLM 1024 缓存混入 2×2 因子主对照；P1.6 只作单独 parity 参考。
- Scorer 固定 Cosine（归一化后内积），stable node ID 破精确同分；用既有 P2a/P2b evaluator 的稳定版本。Context View 的 tokens 必须由真正将呈现的文本调用同一 tokenizer 获得；不能仅凭假定字节长度分配预算。
- 所有操作只读取已有数据/缓存，**GPU=0、模型 forward=0、API=0、SQL execution=0、不训练、不下载模型、不安装依赖**。

### 代码和运行入口（待实现）

- 新增 `scripts/text2sql/run_p2c_dual_view_factorial.py`，只调用已有 `p2b` 输入校验/节点构造方法与 `p2a` 排序器，使用 `variant_prepared(prepared, context_nodes)` 将 Context View 文本/长度独立注入。
- 把每个 run 的 `score_view`、`context_view` 显式写入 run metadata；分离存储 `embedding_source_sha`、`context_text_sha`、`token_lengths_sha`，禁止缓存键仅按文本名复用错分数。
- **回归测试（CPU、无模型）**：
  1. 2×2 同库、同问题节点序一致；如果 score view 一致，两个 context view 的所有 Table/Column Top-K ID、分数 digest 必须完全一致。
  2. V00 的 Top-K、完整覆盖@512/1024/2048、逐题 digest 等于 P2b R0；V11 等于 P2b R1。若相同资料无法重放，立即 STOP。
  3. R0/R1 context 文本只在原 278 个有 Values 列变化；选择节点之后实际呈现的短文本与用于计数的 tokenized 文本一一对应。
  4. Gold SQL / Gold Column 只能用于离线 metrics，不能影响 score/context 生成或预算选择。
  5. 保留多个 JOIN 可达性错误和表列归属作为**诊断指标**，但不把 FK Gate 视为已通过。

### Smoke → Full

- **Smoke**：固定前 5 题/1 DB；四臂得分有限、输出大小和 schema text 合法；V00/V11 双重归档 parity 通过；V00/V01、V10/V11 的 Column@K 完全一致；不计入正式结果。
- **Full**：通过 smoke 后对全部 1534 题离线打分/排序/预算选择，每条件仅一次；产物保存新目录、不覆盖 P2b 或 P2a.5 原结果。各条件重新以固定 512/1024/2048 tokens 选择节点。
- **资源预算**：CPU process ≤1800s、RSS≤16 GiB、最多 8 CPU 线程、GPU=0、API=0；如果原缓存读取/重算因依赖版本产生数值不同，先暂停并只报告差异，不能悄悄继续。
- **失败处理**：只允许一个小规模预检 + 一个 Smoke + 一次 Full。因纯实现故障需要恢复时，须先记录失败阶段、提交最小补丁/增加回归测试，再声明并冻结新运行 ID；绝不在看到四臂收益后修改门槛或重复选择有利结果。

## 必报指标、统计和证据

| 类别 | 要求 |
|---|---|
| **主指标** | V01−V00 的 Complete Schema@1024（1460 全体 + 706 非饱和），分母不变，query macro |
| 排名不变量 | 所有四臂的 Table R@5/@10、Column R@5/@10/@20、Precision@10、Top-K 逐题 ID/hash；score view 相同必须完全一致 |
| Token 代价 | 真正返回文本的 token 数、返回表列数、平均列文本长度、完整 Schema@512/1024/2048 与 Gold-element recall、Gold-only oracle fit |
| 因子贡献 | 两个 score view × 两个 context view 的预算覆盖; `V10−V00` 和 `V01−V00` 与交互差值 |
| 配对及稳健性 | 全体/非饱和各自 rescue/damage，11 DB / 5 DB 分层; DB cluster bootstrap 10000、seed=20261020，95% CI |
| 信息移除风险 | 对保留/移除 Values 的列数与被选中的列数、因 Context View 丢失的 Values 数量与 token 数、SQL 可能需要业务常量/枚举值的案例只做匿名规则计数或后续离线人工审核。不能使用 Gold 反向补充 Prompt |
| 复现 | 源 commit、数据/缓存/model hash、baseline parity、失败日志/资源真实消耗、安全聚合文件和最终 Gate |

### 分析原则

- **仅 1,460 道 Column eligible 题计 Complete 与 Column 统计**；不评 74 题不完整 Gold，也不更改这些题的状态。
- 预算完整覆盖只衡量“Gold Table/Column 是否出现”，不衡量候选 SQL 执行、业务谓词值是否有用或选对 FK。即使 H2 PASS，也仅能说 **Schema-node coverage under fixed budget** 改善，不能称提升 Text2SQL EX。
- 如 H2 失败：停止这一组双视图探索、保留 R0 作为默认检索与呈现策略，转向 FK/role 数据与真正 GFM 基线准备；不打开 Value truncation 搜索空间。
- 如 H2 通过：冻结 V01 为候选离线策略；**下一轮独立**进行 value-critical SQL 风险审计，预先登记安全保留/回补规则，再用**固定 SQL Generator/Selector、相同预算和数据库级独立集**检验 Set EX。未获此证据，不默认全局删 Values。
- 独立数据库留出必须在条件选择后冻结，不能继续在同一 11 DB 上调策略并宣称跨 DB 泛化。

## 并行的 T0-FK 研究基础设施（不影响 P2c Gate）

不额外训练 GNN；独立修复 / 审计：
1. `student_club` 的 90 个 `metadata_incomplete` JOIN 条件与 3 invalid SQLite FK 实例；分类 source DDL 缺陷/合法 non-FK JOIN/alias parser error/无法裁定。报告筛选分母和数据出处，不自动造 FK。
2. 重新对照 SQLite/JSON 的 5 JSON-only、2 SQLite-only 差异；保存稳定 FK instance ID（constraint + ordered column pairs），对同表不同关系、复合键创建 synthetic unit tests。
3. 25 ambiguous ON 与 197 题同表多 FK 候选：建立 `uniquely-resolvable | multiple-valid | unresolved` 的标注协议，**先抽样双人复核**并报告一致性；没有人工审核，就如实报告 `semantic_role_label_eligible=0`。
4. 真实 Gold Role/Path Gate 之前，禁止宣称 Query-aware Edge Gate 的 Text2SQL 性能、禁止训练 SQL-aware Path Loss。GNN 的输入/张量 compatibility smoke 可另立纯工程任务，但不代表角色模型效果。

## 本轮交付

- `docs/research/text2sql/reports/p2c_dual_view_YYYYMMDD/README.md`：实测四臂、全体/困难分母、配对 delta/CI、预算、异常及 Gate；
- `aggregate_summary.json`、`experiment_config.json`、代码/缓存/输入 hash 与最小回归测试；
- `docs/research/text2sql/reports/t0_fk_gate_YYYYMMDD/README.md`（如独立审计完成），但不能把 P2c 质量门和 Role Gate 混为一个；
- 本机保留完整 query、Gold、SQL、embedding cache、逐题排名、日志。GitHub 只公开安全的聚合/计划/代码。

**下一轮执行者应先提交完整 P2c Full 及 Gate，再由研究分析决定是否需要额外的 SQL 级验证；本次只是计划提交，任何 V01/V10 的数值都尚未测得。**

## 执行前实施澄清（2026-10-18，首次计分前登记）

- 成功门的数据库簇 bootstrap 95% CI 下界 >0 同时应用于全体 1,460 个可评题和固定 706 题子集；不满足任一组即 NO-GO。
- P2b 已归档的逐题私有行包含 Column Top-K 与 512/1024/2048 budget 选择，但没有逐题 Table Top-K ID。因此 V00/V11 将对所有已归档 Column Top-K 与预算字段做逐题精确重放，并对聚合指标做数值精确复核；新实验的 Table Top-K 将通过各自 context-only 配对臂的逐题排名与原始 score-matrix digest 完全一致性检查。这个归档字段缺口不改变实验假设、门槛或数据分母。
- 新增执行器 `scripts/text2sql/run_p2c_dual_view_factorial.py` 只读同一缓存，不载入模型权重；仅加载本地 tokenizer 以按计划计算 R1 Context token 数。冻结配置最多允许一个 preflight 实现恢复、一个 5 题 smoke 和一个 Full 实现恢复；恢复仍失败即停止，不进行第三次 Full。
- P2c 成功门会要求全体及固定子集的 Complete@1024 CI 下界均 >0，并要求固定 5 个数据库中至少 3 个 delta 非负、至少 2 个严格为正。这是对原文未指定 CI 所属分组的保守解释，计分前冻结。
- 归档目录固定为 `docs/research/text2sql/reports/p2c_dual_view_20261018_01/`，含 `README.md`、`experiment_config.json` 与匿名 `aggregate_summary.json`。完整逐题输出、run receipt 与日志仅留本地。

## 实现恢复登记（2026-10-18；Full 聚合尚未完成）

- 首次 preflight `p2c_dual_view_preflight_20261018_01` 在验证 P2b 聚合 checksum 时因 runner 从 P2c config 读取 `final_result` 而出现 `KeyError`。用时 10.548 s wall / 10.306 CPU s / 0.749 GiB RSS；发生于四臂评分前，模型 forward=0，未产生实验分数。原目录与日志保留。
- 最小修复：分别读取 P2c 注册状态与 P2b 已完成配置，并只从 P2b 配置读取其 aggregate SHA；新增配置来源回归检查。新一次且唯一恢复 preflight 固定为 `p2c_dual_view_preflight_20261018_02`，同一数据、阈值和资源预算；恢复再失败即停止，不运行 Smoke/Full。
- 5 题 smoke `p2c_dual_view_smoke5_20261018_01` 已通过：V00/V01 与 V10/V11 的 score/context 排名不变量通过，V00/V11 的 P2b Column Top-K 和预算行逐题精确重放。用时 11.217 s wall / 11.152 CPU s / 0.865 GiB RSS；不是正式证据。
- 首次 Full `p2c_dual_view_full1534_20261018_01` 已完成四臂评测和逐题 replay，但在聚合构建时错误地用私有行键 `R0_local_cpu_pass1` 查找公共聚合键；真正 key 是 `R0_local_cpu_pass_1`。进程在写 aggregate/per-question 前失败，20.579 s wall / 20.685 CPU s / 0.969 GiB RSS；模型/API/SQL 均为 0。保留独立目录与日志。
- 唯一 Full 恢复 `p2c_dual_view_full1534_20261018_02` 仅修正公共聚合键映射，并允许已登记的 2026-10-18 preflight/smoke commit `91fc6fef002edce8f68d78ca4050c4f62688107c` 作为同一代码链中的前置证据；打分和数据路径无改动。新增聚合键及前置提交回归检查。该恢复已完成四臂及逐题行 replay，但 aggregate replay 因本地 Column recall 字段名不一致再次触发 `KeyError: 'column_r5_query_macro'`。没有生成 Full aggregate 或 per-question 文件；恢复次数耗尽，停止，不进行第三次 Full。
- 两个 preflight、一个 smoke 和两次 Full 合计 73.965210294 CPU 秒 / 73.943058270 wall 秒，最大峰值 RSS 0.979721 GiB；GPU/API/model forward/SQL 均为 0。Full 两次失败目录和日志保留在 `/mnt/liansp3/sources/results/gfmrag_p2c_dual_view_20261018/` 与 `/mnt/liansp3/logs/`。
- 本轮是执行器聚合回放故障，**不是 H1/H2 通过或失败**；未产生可用于科学比较的 Full 指标。不得把 smoke 或进程内未落盘评分当作正式结果。只有另行修复并补充本地 summary-to-archive 字段契约后，才可考虑新的实验登记和运行预算。
