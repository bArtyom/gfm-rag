# 2026-10-23 新实验复核：P2d.1 SQL评测审计 + G0官方GraphReasoner接口

> **类型：跨研究分支的已运行报告复核；并非新实验。** 主仓库 `bArtyom/gfm-rag`，main在审阅起点 `c49cde5184543e104d358810b0f3af1fdefb874c`，**最新科学/工程产物仅存在研究分支，尚未合并main**：
>
> - SQL分支 `research/p2d1-eval-v2-20261022`，tip `aa2d21ac710edfe098ac752970571c084ad84731`：[恢复02全量报告](https://github.com/bArtyom/gfm-rag/blob/research/p2d1-eval-v2-20261022/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02/README.md)、[aggregate](https://github.com/bArtyom/gfm-rag/blob/research/p2d1-eval-v2-20261022/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02/aggregate.json)、[taxonomy](https://github.com/bArtyom/gfm-rag/blob/research/p2d1-eval-v2-20261022/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02/failure_taxonomy.json)。
> - G0图分支 `research/g0-synthetic-compat-20261023`，tip `7152ab2a75e1bada1bc4d8280728878cbaf73726`：[attempt03完成报告](https://github.com/bArtyom/gfm-rag/blob/research/g0-synthetic-compat-20261023/docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_03/README.md)、[result](https://github.com/bArtyom/gfm-rag/blob/research/g0-synthetic-compat-20261023/docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_03/result.json)。
>
> 主分支上此前的[2026-10-22 P2d诊断](../p2d_latest_review_20261022/README.md)和[下一轮P2d.1协议](../../plans/p2d_1_frozen_prediction_eval_audit_20261022.md)是历史来源；此处尊重不同分支各自独立提交的run/失败回执，不将其误写为已合并main。

## 一、P2d.1：工程和评测覆盖Gate成功，模型EX增益仍无证据

冻结原BIRD dev 30题/5库（19条高度筛选风险题+11条严格匹配对照，非随机独立测试），既有90条预测、Qwen2.5-Coder-7B-Instruct/selector=none；**新增模型调用=0**。

- Gate 1：合成安全测试 **137 PASS/0失败**；**26条旧可执行Gold +57条旧可执行预测 =83条**新旧回放完全一致。输入/DB SHA验证。
- Gate 2：以前被阻止的4条reference均安全可比；30题×3臂，v2共120 SQL评测使用83已有核验结果+37新执行。
- **确认正确数不变**：E0/E1/E2 **8/7/8（固定30分母）**；unknown从11/12/10缩为**10/10/8**，新增可判分别**1/2/2**，全是wrong。v2对应wrong **12/13/14**。不能称“准确率提高”。
- E0 vs E1 v2配对：**6 both correct、1 E0-only、1 E1-only、10 both wrong、12 unknown**；v2仍无有力方法优势。
- **28/90预测不可执行**，明确为**10 sql_parse_error +18 sqlite_missing_column**；E0为4+6，E1为2+8，E2为4+4。别拿v1通用SQLite error来猜具体类型。
- 可执行但不正确的集合，table-set exact **10/12、10/13、9/14**，join-signature exact **6/12、4/13、3/14**，直接列值pair exact **3/12、4/13、4/14**（后者未解析分母存在）。都是**错误样本内部的代理诊断**，并非SQL错误因果或全体Join Path Accuracy。
- 原P2d真实输入tokens E0/E1/E2 **35074/35591/24458**，离线再次核对。E1“覆盖更多Gold Schema节点”不等于“Generator prompt更短”或“SQL成功”。E2虽然确认正确同8题，但不是完全相同的8题。
- P2d.1 attempt01的seals校验缺陷及recovery02记录保持；不改写原P2d 8/7/8主口径。人类Values必要性审核=0；不能将19题中AST binding-supported9题当作人工语义标签。

**方法决定**：P2d.1审计目标已经完成；**在同一30题上不继续调prompt/packing/参数来“追正确率”**。若要验证SQL有效性新方法，应冻结新数据库/新问题集合并修好generator-validation机制；但这不是本轮首选创新方向。

## 二、G0：官方checkpoint接通，FK实例原始元数据不在有效推理通道内

固定 `rmanluo/G-reasoner-34M`（34,640,897参数，1024D）运行5节点/8有向边/6关系类型的合成PyG图，含两个parallel role边、复合FK两组件、正反向边。第三次attempt成功：

| Gate | 实测 | 解释 |
|---|---|---|
| G0-A | 模型输出`[1,5]`且全部finite | 合成graph前向可用；未测排名/SQL |
| G0-B | 并行role、component index/count、FK实例ID、inverse pairing在设备转移中保真 | 元数据留在PyG图对象中 |
| **G0-C** | 仅扰动`edge_attr`与`edge_fk_instance_id`/component等，输出max abs delta=**0.0**，exact equality | **这些被测试字段未进入当前checkpoint的计算通道** |

源码/runner表明：模型侧用 `graph.x`、`graph.rel_attr`；传播主要依赖 `edge_index` 和 `edge_type`；attempt03**没有扰动`edge_type`或`rel_attr`**。因此**只证实“给edge_attr/自定义字段加FK角色没有效果”，不能说checkpoint完全无法利用关系类型、也不能证明当前对SQL FK语义具备或缺乏准确率**。

G0原attempt01的Ninja/PATH JIT加载失败和attempt02不存在的script路径失败已单独记录；attempt03本地result与stdout完成，但shell broker没有持久保留exit code，报告如实披露。用单seed/单合成图不能外推质量。

### 研究含义：真正的下一个falsifiable mechanism

**FK身份必须进入实际被模型读取的路径，或者扩展模型明确消费逐边属性。** 目前尚未验证“改变`edge_type`或`rel_attr`究竟会改变分数、是否具备关系编码不变性和Query条件性”。先做一个低成本、能停机的G1关系通道机理消融比直接训练edge gate更合理。

- 若原模型对有语义影响的`edge_type/rel_attr`改变敏感，并满足一致的关系ID重命名不变性，才可研究将FK Role/Instance映射到有限关系类型/关系向量的**工程baseline**；单纯关系类型编码不是论文级新贡献。
- 若对这些通道无足够敏感，先查GraphReasoner forward的输入契约/起点mask/关系传播，而非在未使用的`edge_attr`上训练无效参数。
- 若关系通道有效，但`edge_type`粒度不足以唯一表示多FK/复合FK的身份，应另立**edge-feature aware gate / instance-node**架构，对照原模型和relation-typing baseline，**新功能必须消费实例属性且有可靠标注**。

## 三、下一轮决策和证据限制

**唯一主实验推荐：G1 relation-channel sensitivity & FK instance preservation Gate**，已规划在 [G1独立预注册](../../plans/g1_relation_channel_and_fk_instance_gate_20261023.md)：使用原fixed checkpoint、synthetic fixture和多组因果控制，读取已经被证明在模型计算通道的`edge_type/rel_attr`，检查负控与等价重标记；并完成真实FK实例ID/复合键的**CPU-only数据契约审计**。**G1目前NOT RUN**。

并行但**不新启动LLM/GPU SQL EX**的工作是对v2的18个missing-column和10个parse failure做匿名根因补证，并补19题Values语义必要性人审。如无人审则标UNVERIFIED，不能捏造。

**FK/Role Gold Gate仍NO-GO**：P1.5/P2a.5已有103个raw SQLite FK（100有效、3无效）、1428 JOIN ON（1199唯一FK匹配、204未决/非FK、25歧义）、197题同表多FK候选。它们是候选标签数据质量信息，**不是可用于Query-aware Edge Gate监督或JOIN准确率的可信Golden Role样本**。因此G1实验只评价通道敏感性和结构完整性，不能报F1、Join Accuracy、BIRD SQL EX或GraphReasoner增益。

P2c-R离线Complete@1024 +10.96pp的成功与P2d 7B Pilot 8/7/8/P2d.1不变均保留；不要将二者混为一个方法端到端成绩。

**学术排序**：G1是可证伪的模型适配基础；在标签/评估契约完成后，“Query-conditioned FK Instance Gate + 合法JOIN约束子图”才是潜在的研究新方法，需对比原G-reasoner、无GNN Dense、typed-relation baseline，以及既有SchemaLink/Graph-Link方法。
