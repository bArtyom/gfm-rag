# 2026-10-24 Text2SQL × G-reasoner 当前实验全局复核与 G2 研究决策

> **性质：已有仓库结果审计 + 后续决策；不是新实验。** 初始核对时间：2026-10-24，随后追加G2及FK Instance结构Gate结果，见本文件第5、6节。权威仓库 `bArtyom/gfm-rag`；相关结果在 `research/g2-asymmetric-relation-20261024`，尚未合并`main`。不要把研究分支产物冒充已合并`main`。
>
> 原始证据：[P2b](../p2b_values_ablation_20261018_01/README.md)、[P2c-R](../p2c_r_recovery_20261019_01/README.md)、[P2d Pilot](../p2d_sql_utility_20261022_01/README.md)、[P2d.1分支recovery02](https://github.com/bArtyom/gfm-rag/blob/research/p2d1-eval-v2-20261022/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02/README.md)、[G0分支attempt03](https://github.com/bArtyom/gfm-rag/blob/research/g0-synthetic-compat-20261023/docs/research/text2sql/reports/g0_synthetic_graph_compat_20261023_03/README.md)、[G1分支run002](https://github.com/bArtyom/gfm-rag/blob/research/g1-relation-channel-20261023/docs/research/text2sql/reports/g1_relation_channel_20261023_02/README.md) / [数值JSON](https://github.com/bArtyom/gfm-rag/blob/research/g1-relation-channel-20261023/docs/research/text2sql/reports/g1_relation_channel_20261023_02/result.json)。

## 1. 目前到底验证了什么？

| 层级 | 历史实测 | 准确可下的结论 |
|---|---|---|
| Qwen3维度（P1/P1.6） | 1024D固定检索基线；老P1/P1.5严格逐题复现未通过，P1.6冻结缓存与评分通过 | 是新的可复用Dense基线；不再无意义扫维度 |
| P2a BM25/RRF | 相对Cosine主门NO-GO | 没证据支持泛化的排序提升 |
| P2b Values R0/R1 | Column R@10 67.99→67.03%，主门NO-GO；Complete@1024 56.64→65.96% | 删Values缩短文本但影响语义检索；混合了排序与装包因素 |
| P2c-R 2×2 Dual View | V01固定富Values检索排名但返回短文本；Complete@1024 56.64→67.60%，+10.96pp，困难706题+8.22pp，主门PASS | **离线Schema节点覆盖有效**，并非SQL EX |
| P2d Qwen2.5-Coder-7B SQL Pilot | 在人为选取30题，E0/E1/E2已确认Set/Bag正确 8/7/8，原unknown11/12/10 | **没有证据显示V01改善最终SQL**；样本小且有偏，不能称总体差异 |
| P2d.1 evaluator-v2 | 137合成安全测试PASS，83/83旧可执行SQL replay PASS；4条旧blocked参考可评；E0/E1/E2正确仍8/7/8，unknown10/10/8；90条预测中10 parse+18 missing-column | v2改善测量覆盖，但新增可判全wrong，不是生成方法变好；19题人类Values必要性标签仍0 |
| G0官方GraphReasoner-34M | 1024D、5节点/8有向边，前向输出[1,5]有限；扰动edge_attr/custom FK属性delta=0 | 工程接口成功；**自定义逐边元数据没有被当前forward消费** |
| G1 GraphReasoner关系通道 | Run001设备转移错误，Run002修复后8次forward成功；C1/C2/C3/C4 delta=0，C5=30.9753，C6=8.3077（C6 top1改变） | **按原预注册G1-A NO-GO**，但C2/C3零差异是对称聚合下未辨识干预，并不证实模型忽略`edge_type/rel_attr` |
| G2 非对称关系通道（后续实测） | 官方34M、1024D、5节点/8边；1次加载、8/8前向；A2/A3分数delta 0.75878/3.78130，A1/A4=0，epsilon=1e-6 | **G2-A PASS**：非对称合成图上的关系通道分数敏感性；无top-1变化，不支持业务FK角色或SQL效果 |

补充资源/可靠性：G1 Run002 9/9聚焦结构测试，固定官方checkpoint，seed20261023，8次forward约1.7147秒（含模型载入）；无训练、无BIRD/Gold/SQL/API。G0原前两次工程失败保留。原实验结果及缺陷都已独立登记，不在新阶段改写。

## 2. G1关键发现应如何解释？

根据研究分支真实`scripts/text2sql/g1_relation_channel_probe.py`和`gfmrag/models/ultra/layers.py`，G1合成图`edge_index`中两种角色的正向边**同源0→目标1**，对应逆向边**同源1→目标0**；C2交换它们的关系`edge_type`；C3交换关系特征`rel_attr`对应两行，保持边不变；C4同时置换label和feature，固定每条边实际取到的关系向量。

**问题：** C2/C3的操作均可使同一目标的关系消息多重集合完全相同。QueryNBFNet聚合本身是置换不变的sum/mean/max等，因而即使真消费`edge_type/rel_attr`，输出也可能严格相同。C2/C3的`0.0`**不能推出“官方checkpoint无关系类型能力”**；只能严谨写成：G1主门未过、当前对称fixture无法识别这一能力。

G1 C5 anchor和C6 query都有变化，只表示在单个合成图上模型路径分别响应起点和Query；**不代表模型准确判断业务JOIN角色**。G0的`edge_attr`静默不意味着`rel_attr/edge_type`静默，两者是不同计算接口。

**图表示设计风险：** 如果把两个FK实例仅用同一对表节点之间的平行边表示，而下游只输出每个表节点分数，即便relation channel敏感，也可能无法从置换不变的聚合中恢复“billing_fk vs shipping_fk”的单独实例身份。需要单独的Edge/Instance输出或reified instance node方案（后续研究，不在G2做架构改动）。

## 3. 下一轮唯一优先方法：G2打破关系聚合对称性

参见 [G2可执行预注册](../../plans/g2_asymmetric_relation_channel_identifiability_20261024.md)。选择新**合成**拓扑：保留5节点/8边/6种关系和旧复合FK，但把两条`0→1`并行角色分别改为`0→1`与`0→4`，逆边相应改为`1→0`与`4→0`。这是只改变合成设计的**新固定测试fixture**，不用与G1旧输出的差异推断关系因果；所有主比较均须在**同一新拓扑**内成对单因素进行。

- 首先**CPU Gate**按目标节点的`(source node, rel_attr[edge_type])`消息多重集合计算hash，要求被测试关系扰动实质改变至少一个相关目标的多重集合；负控/一致重标记保持完全一致。
- **G2 GPU Gate**仍用冻结官方34M、1024D、固定同Query/start，重复前向估噪、逐边关系类型交换、仅指定角色向量改变、原始metadata负控、一致关系编号/向量置换对照和Query/anchor指纹。
- 主成功条件：负控/一致置换 `delta≤epsilon`，且**单因素关系类型或关系向量干预至少一种`delta>epsilon`**。如果CPU证明多重集合改变而GPU仍不变，才是真正值得用中间层激活继续定位的结果；若预检多重集合未变化则 STOP，不浪费GPU。
- 结果只能称“关系输入消费/敏感性机理”，没有真实关系检索效果、无Role F1、无SQL EX。
- 与之并行的CPU-only FK Instance Gate必须保留复合列对顺序、双向边实例身份和同一对表多FK；准备最多20复杂例的双审核流程，未有人类审核则trusted Role标签数量仍0。

## 4. Go/No-go 以后如何走？

1. **G2 relation sensitivity PASS** → 先复现 relation-typed G0工程baseline及真实FK Instance的可用、稳定编码；仍需可信Role标签；不能直接说Typed GNN实现了Query-aware JOIN选择。
2. **G2消息输入变化且模型输出不变** → 检查relation MLP、QueryNBFNet前几层的关系嵌入/消息激活和可达性，暂停盲目多seed、超参数扫面或EdgeGate训练。
3. **G2 negative control/语义重标记不变性FAIL** → 先修fixture/模型调用或识别ID依赖性，科学结果不可用于正面结论。
4. **FK Role human label=0** → 只做synthetic和数据结构工程，不上真实query-conditioned edge supervision、不报Role Accuracy/Join Path Accuracy。

**论文创新主张边界**：G2是判别G-reasoner接口的科学测量前置；真正新意可能是**Query-conditioned FK Instance scorer + typed/reified relation graph + constrained JOIN subgraph decoding**。等可信Gold和独立SQL集后，至少与Dense、relation-typed G0、简单FK path heuristic和官方G-reasoner对照，固定生成器与token预算。

**决策：** 暂停继续在旧30题上调Prompt/SQL，优先执行G2合成机制Gate+可信FK Instance结构审计，条件满足再进入Graph Relation编码与真实角色检索。

## 5. G2 实测补充与后续决策（2026-10-24）

G2使用预注册fixture和成功门，CPU Gate `_012` 14/14硬门通过，定向合约测试23/23通过。首次运行在CUDA context初始化前调用峰值显存重置而停止；模型未加载、前向0。显式初始化CUDA context并固定当前设备后，新run `g2_asymmetric_relation_20261024_01_amended_01` 完成：checkpoint加载1次、前向8/8、耗时6.3151秒。重复噪声为0；A2 relation-ID成对交换max abs delta=`0.758783`，A3 relation-row坐标变换=`3.781296`，A1 metadata-only与A4同步语义重标均为0；故冻结门槛下判为`G2_A_PASS`。所有输出finite `[1,5]`，各条件top-1均相同。

结果仅表明**这个非对称合成fixture上的关系输入能影响节点原始分数**。G0 attempt03仍只证明官方路径忽略测试的`edge_attr`和自定义FK metadata；G1原`NO-GO`仍是对称拓扑下不可辨识的结果。三者不互相覆盖，亦不支持真实JOIN角色准确率、Query-aware EdgeGate或SQL EX。完整参数、错误现场、GPU资源与匿名聚合结果见[G2报告](../g2_asymmetric_relation_20261024_01/README.md)，已提交至G2研究分支。

按G2预注册后续路线，先做独立的[CPU FK Instance稳定编码质量Gate](../g2_fk_instance_quality_20261024_01/README.md)，再视结构Gate结果单独登记**Relation-typed G0工程基线**。CPU Gate只检查BIRD dev SQLite schema的有序复合列对、FK实例主键、双向边同ID配对、同表对多FK区分和顺序稳定性；不读取题目/Gold SQL，也不报Role/Join Path准确率。G0模型前向阶段须使用匿名结构、冻结关系文本/向量生成方式，并和简单FK path及无关系baseline比较；不训练、不把自动匹配称为Role Gold。G2的8次前向预算已用完，不追加同一合成实验扫描。可信人工Role标签仍为0，因此不开始Query-conditioned Role监督或报告SQL EX。

## 6. FK Instance Gate结果与下一步（2026-10-24）

[FK Instance全量结构Gate](../g2_fk_instance_quality_20261024_01/README.md)已完成，结果为`NO_GO`：11个SQLite schema、103原始/100有效/3无效约束与历史参照一致；一个有效身份碰撞使双向边按唯一实例配对的门槛失败。只读诊断确认碰撞是两个不同PRAGMA组的约束声明具有完全相同的规范化FK结构，而非哈希随机冲突。全量中复合FK数为0，所以复合组件顺序敏感性没有BIRD实证。**Relation-typed G0暂缓**，不能将结构审计包装成模型或JOIN准确率证据。

为回答“相同结构是一个Join映射还是两个声明实例”这一会改变G0输入语义的问题，已完成[重复FK身份策略CPU探索](../g2_fk_duplicate_identity_policy_20261024_01/README.md)。11库的103/100/3分母和schema hash与原Gate一致。Mapping策略得到99个不同有效映射和198条方向边，并保留1个重复声明重数；声明multiset策略得到100个ID和200条边，ID集合对重排/组号重编号稳定，但2个重复项的组号—序号绑定发生变化。合成fixture验证了重复映射、同端点不同映射及复合FK的边界。

该结果说明结构字段能稳定标识唯一Join映射，却不能在不借助额外来源信息时稳定追踪完全相同的单个声明。候选建议是G0使用映射级ID并将声明重数作为独立元数据；这是建议，不代表原Gate改为PASS或G0已获准。Relation-typed G0仍需独立协议明确映射语义、边去重、对照和停止门槛后再运行。
