# G1 预注册：GraphReasoner 关系通道敏感性 × FK Instance 保真门

> **制定：2026-10-23；状态：NOT RUN。** [最新跨分支结果复核](../reports/p2d1_g0_cross_branch_review_20261023/README.md)。本方案不是新GNN方法训练，也没有任何已经发生的G1收益。**唯一主目标：在不重训练官方G-reasoner-34M的前提下验证真正可消费的关系通道能否承载FK角色差异，并做可信的FK instance数据Gate。**

## 0. 上游结果和分支处理

- 主仓库 `bArtyom/gfm-rag`，审阅基线main旧提交 `c49cde5184543e104d358810b0f3af1fdefb874c`，最新结果分别只存在两条未合并研究分支。
- **G0 source**：`research/g0-synthetic-compat-20261023` tip `7152ab2a75e1bada1bc4d8280728878cbaf73726`；[G0第三次结果](https://github.com/bArtyom/gfm-rag/blob/research/g0-synthetic-compat-20261023/docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_03/README.md)；原模型34,640,897参数，1024D，5 nodes/8 directed edges/6 relation types，官方CKPT `rmanluo/G-reasoner-34M` revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`；元数据-only扰动差值**0**。
- **P2d.1 source**：`research/p2d1-eval-v2-20261022` tip `aa2d21ac710edfe098ac752970571c084ad84731`；[P2d.1恢复02](https://github.com/bArtyom/gfm-rag/blob/research/p2d1-eval-v2-20261022/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02/README.md)；v2 EX仍8/7/8，28不可执行SQL（10 parse+18 missing-column）。
- 在新G1运行之前，必须通过可审查的PR/明确pin的commit导入G0 synthetic runner和已完成的匿名报告或在新分支按**内容和SHA**引用；不得暗自以main缺少G0文件为由重新下载其他checkpoint或替换fixture。G1建议新分支 `research/g1-relation-channel-20261023`，隔离来源、测试与配置。
- 不修改或覆盖G0 attempts 01/02/03或P2d/P2d.1任何原始结果。

## 1. 核心研究问题

**RQ1（消费机制）：** G0在`edge_attr`/自定义FK字段扰动时逐位不变；那么**改变模型真正读取的`edge_type`或`rel_attr`** 是否对节点输出有可复现、超出浮点噪声的影响？

**RQ2（表示合同）：** 如果将两种同表FK角色编码为**独立但成对的正反向`edge_type`和关联的`rel_attr`**，能否保持“两个边角色、复合FK整体标识、逆边成对”的Schema图语义，而非仅依赖不消费的`edge_fk_instance_id`字段？

**RQ3（未来Go/No-go）：** 当前checkpoint只敏感于relation type还是足以作为以后Query-conditioned FK Role/Path的工程基线？此轮**没有人工Gold/SQL**，只能回答输入敏感性和编码保真，不能测Role Accuracy或方法创新。

## 2. 仅Synthetic Model Gate（先写测试，再前向）

### 2.1 严格冻结输入与变体

复用G0 `make_fixture`：5节点/8有向边（4正向+4逆向）、6种relation id、两组并行角色0/1、2组件构成复合FK；固定`node x`、`edge_index`、原`rel_attr`、1024D，start mask为node0，查询向量原seed+1。所有关系类型变体必须**保证索引合法和inverse-role pair互斥且匹配**；设计对照前完成CPU事务式结构校验，并生成fixture/branch source/model SHA。

| Run | 变更变量 | 可证伪预期/角色 |
|---|---|---|
| **C0 baseline×2** | 固定图、查询、model.eval()，重复前向 | 测量真实数值噪声/稳定性，冻结容差 |
| **C1 negative** | 只改变`edge_attr`+FK custom fields，保持所有有效输入不变 | 对G0结论做负控；预计输出不变 |
| **C2 role-edge-type** | 同表两平行FK角色的`edge_type`作成对切换，inverse type同步维护；`rel_attr`矩阵保持不变 | 检验模型是否读取`edge_type` |
| **C3 relation-feature** | 只交换/扰动并行角色的`rel_attr`行，`edge_type`不变，relation数量不变 | 检验模型是否读取`rel_attr` |
| **C4 consistent ID re-label** | 对关联`edge_type` ID、逆边 ID和对应`rel_attr`行**作一致双向置换**，其余完全一致 | **关系ID重命名不变性**；否则baseline定义可能受ID/索引副作用影响 |
| **C5 anchor condition** | 图不变，只更改合法start_nodes_mask，保持原查询embedding | 检查start anchor是否影响输出 |
| **C6 query condition** | 图及start mask不变，换冻结的第二个归一化query embedding | 检查输出是否query-conditioned |

**禁止误操作**：C2/C3不得修改`x`或`edge_index`；C4必须使用同一全双射置换，不能通过改变关系内容代替重命名；C1不能修改`rel_attr`或`edge_type`；复合FK的2个组件在所有臂必须保留同一实例ID/逆边配对（只是当前模型不读取metadata）。

用冻结`torch.inference_mode`、`model.eval()`和相同精度，输出每臂`[1,5]`全部有限值。**不强制解释某一测试为“SQL语义更正确”**；输出是否改变只是mechanism fingerprint。

### 2.2 CPU合成/输入合同单测

- 同表2平行role的端点相同但`edge_type`不同，交换role仅影响预定边；正反边对应类型成对、不能将inverse edge错误地写成正向类型。
- 复合FK两组件共用实例ID/tuple group、保留有序column-pair，不得拆为两个独立FK实例；对组件乱序必须触发结构合同FAIL。
- 图复制与PyG device transfer前后`x, edge_index, edge_type, rel_attr`和额外FK字段shapes、ID hashes、没有泄漏Gold。
- C4双向重标记后，边标注与关系向量的**语义配对**保持不变。模型输出可有极小浮点噪声，必须以C0重复前向误差校正，并输出最大/平均差异、top-1排序是否变化。
- 任何fixture重排、丢边、角色合并、wrong checkpoint加载、nan/inf、错误输入维度，STOP。

### 2.3 前向限额、阈值和决策

建议同一个checkpoint load，**8次前向**（C0两次、C1–C6各一次），1个既有可用的RTX4090，1次执行，seed20261023，15min wall，模型参数全部frozen，**训练epoch=0、无BIRD/Gold、无SQL、无API、无新模型下载/安装**。环境沿用`gfmrag_greasoner_20261022`、已确认的`conda run`入口和RSPMM/Ninja PATH；先通过`--help`/runner路径/输出目录/preflight确认，吸取G0 attempts01/02路径错误。

- 定义数值噪声 `ε=max(1e-6, 10 × C0两次max_abs_diff)`（此值为事前阈值，不是观测）；报告原始float差异与`ε`。
- **G1-A 消费性成功：** C1 `delta≤ε`，C4 `delta≤ε`；且 C2 或 C3 有 `delta>ε`，证明至少一个有效relation channel对固定合成图有因果敏感性。两者都`≤ε`则G1-A NO-GO，先查forward路径/配置/可达性和局部对称性，不开发GNN Gate。
- **G1-Q 另行报告（非Gate主成功）：** C5、C6各自`delta>ε`与否。若无变化，不能称模型query-conditioned；若有变化，只证明合成条件敏感，不是SQL Query-aware Edge Gate成功。
- **保真不可省：** 若C4关系重命名导致高于`ε`的变化，STOP，先修映射或确认模型是否有index dependence；不能把C2变化直接当Role Encoding有效。
- 任何Gate失败、源码/数据hash漂移、显存超限、资源不足、执行错误，按固定运行停止并归档失败；禁止本run ID下重试或挑选最有利seed。新恢复需要另立理由与独立登记。

**科学结论限制**：C2/C3 non-zero仍只有输入机制，不能称GFM学会了FK Instance identity，不能证明实际SQL JOIN path准确率。反向结果同理，是特定合成图、固定查询的受限negative，不代表所有G-reasoner模型。

## 3. 同轮可并行的CPU-only FK Instance Label Gate（与GPU结果独立）

G0已有FK metadata传输保真，却没有真实BIRD可靠Role gold。这个Gate可**独立于G1输出**开始数据质量工作，但不能用Gold调G1合成输入：

- 实例标识单元：`(database, constraint identity or stable source, source_table, ordered_column_pairs, target_table)`；同表多个FK不可塌缩；复合键必须一个constraint内有序多列对，逆边指向同一`instance_key`。
- 重放P2a.5事实：103 raw SQLite FK、100有效、3无效；1428 Gold JOIN ON中1199 unique FK match、204 unmatched/non-FK、25 ambiguous；多FK候选题197。每项注明源JSON/SQLite/alias解析，不把metadata`unmatched`全当数据错误。
- 重点选择最多**20条**真实FK复杂案例作为**仅本机人工审核队列**（至少包含多个同表FK/复合/桥表/别名），按来源冻结抽样规则/ID私有hash；如果需要Gold SQL，Gold只能用在事后裁定，不得进入模型输入。
- 使用匿名聚合报告 `unambiguous_structure | multiple_candidates | non_fk | metadata_gap | unresolved`，而**Role Gold人工审核是否完成**单独记录。若没有两人复核，则`human_review=0`且`trusted_role_label_n=0`，不得启动正式Edge Gate模型训练/报告Role F1。
- FK实例图中 `edge_type` 是有限关系类别，不能靠对每个instance随意新增one-hot relation ID伪造可泛化实例模型；真实角色embedding方案必须另外研究跨数据库泛化与 relation vocab 增长。

## 4. Go/No-go 与下一阶段分岔

| Gate情况 | 下一步 | 明确不能宣称 |
|---|---|---|
| G1-A PASS、FK label still 0 | 进入**relation-typed G0 baseline设计**（只做输入编码与可重复排名，合成+受限真实匿名结构；不训练/不报Role F1），并完善Role审核 | 原G-reasoner已理解业务FK role |
| G1-A PASS、FK人工Gold可信 | 下一独立实验可预注册 **query-conditioned FK instance Gate** 对照：Dense/typed relation/G0+edge gate/instance-node（控制输入信息、预算和模型参数） | G1本身证明SQL EX提升 |
| G1-A NO-GO | 报告无敏感性，先定位`edge_type/rel_attr`及起始mask和query路径；暂停所有G1后续训练 | FK role特征有效 |
| C4 invariance FAIL / input parity FAIL | STOP并修runner/映射的工程合同；必要时另立恢复 | 将非等价图当语义角色消融 |
| 标注不足/SQL生成器错误仍大量存在 | 不扩大BIRD dev SQL EX; 完成trusted FK-Gold与生成器错误分类 | 对照可直接推广至论文主表 |

## 5. 输出、隐私、资源和学术价值

- 建议新代码路径 `scripts/text2sql/g1_relation_channel_probe.py` 与合成fixtures单测 `tests/test_g1_relation_channel_probe.py`，新研究分支独立commit，公共报告 `docs/research/text2sql/reports/g1_relation_channel_YYYYMMDD/README.md, result.json, experiment_config.json`。**此次只是预注册方案，未实现/运行这些文件**。
- GPU运行前实际检查checkpoint/model/RSPMM源码/本机环境/执行脚本 SHA、硬件/显存/使用权；成功/失败全部保存真实资源消耗和回执。不能宣称CPU-only或训练/SQL已做。
- BIRD raw DB、问题/GoldSQL、private per-question排名、数据库名/元数据内容、人工审阅逐项、模型文件、日志、服务路径及敏感环境变量**禁止提交公共GitHub**；只提交synthetic固定fixture、源码、匿名汇总、hash和研究协议。
- 本G1只是有必要性的**工程适配与机制验证**，绝不是新的论文SOTA结果。真正可能有科研贡献的是“可转移的FK Instance表示+Query-conditioned Edge Gate+JOIN合法路径约束”，必须配备可信标签、强对照、跨数据库与下游SQL Set EX。

**执行原则：先G1角色通道消费与保真测试，再根据Gate结果决定是否进行instance-aware graph adaptation；P2d.1已经结束，不在旧30题上继续调得分。**
