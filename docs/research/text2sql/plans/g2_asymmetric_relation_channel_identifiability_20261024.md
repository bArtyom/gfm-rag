# G2 预注册实验：非对称FK关系通道可辨识性与Instance图结构Gate（2026-10-24）

> **状态：PLANNED / NOT RUN**；本文已提交的只是方案，不是 G2 执行或性能结果。依据 [2026-10-24全局复核](../reports/current_results_review_20261024/README.md)。实验唯一主仓库 `bArtyom/gfm-rag`；原 G1 完成证据：[run002 report](https://github.com/bArtyom/gfm-rag/blob/research/g1-relation-channel-20261023/docs/research/text2sql/reports/g1_relation_channel_20261023_02/README.md)；代码基点 `research/g1-relation-channel-20261023@8353892d68de152f0c1500ac49d9f6c7c6585ab2`；官方模型和checkpoint均与G1一致，不修改模型权重。**代码与实验产物仍在G1分支；执行前必须先建独立G2分支/PR或pin G1 blob，明确复制和diff，禁止把G1分支未合并的文件视作main已存在。**

## 1. 问题、主要假设和防止错误结论

**RQ：** 在完全固定模型、Query和起始节点条件下，如果关系干预经CPU证明使**同一目标节点收到的关系消息多重集合改变**，官方G-reasoner-34M输出是否会表现出超出数值重复误差的变化？

G1 C2/C3 zero-delta源于同端点平行边上的标签/向量交换；输入`edge_index`有两条`0→1`、对应逆边`1→0`，目标端消息多重集合可保持不变，原G1预注册G1-A **NO-GO** 不可改写成PASS。G1 C5/C6只证明单合成图对起点/Query敏感；G0仅证明自定义`edge_attr`字段没有作用。

**本次可证伪原假设：** 当两种角色指向不同的非对称目标，且操作实际改变目标`(source x, relation feature)`消息多重集合时，C2/C3-style修改应引发`>epsilon`节点输出变化；负控和语义等价全双射重命名仍不引发变化。

**重要范围：** G2的不同端点是为了检验**关系输入被模型消费**，**不是**实际“一个源表到同一目标表的billing/shipping多FK实例身份”已经可辨识；同端点多实例识别需要以后单独研究instance-node/edge-aware readout等架构，不能把不同端点测试的正结果冒充同端点业务角色分类能力。没有JOIN Role Gold，此实验不报Role F1、Join Path Accuracy或SQL EX。

## 2. 预检Gate 0：使用CPU构造真正非对称、可区分的合成fixture

沿用G1/G0 **5节点、8条有向边、6种关系ID、1024-D node/relation features**、原固定种子`20261023`、官方34M checkpoint。保留4条forward及4条inverse，复合FK两列对同属一个instance：

```text
G1 old forward: 0 -(type0, FKinstance0)-> 1
                0 -(type1, FKinstance1)-> 1    // 同端点，关系交换对称
                2 -(type2, FKinstance2,component0)-> 3
                2 -(type2, FKinstance2,component1)-> 3

G2 new forward: 0 -(type0, FKinstance0)-> 1
                0 -(type1, FKinstance1)-> 4    // 与instance0不同目标，打破端点对称性
                2 -(type2, FKinstance2,component0)-> 3
                2 -(type2, FKinstance2,component1)-> 3

G2 reverse:     1 -(type3, FKinstance0)-> 0
                4 -(type4, FKinstance1)-> 0
                3 -(type5, FKinstance2,component0)-> 2
                3 -(type5, FKinstance2,component1)-> 2
```

将G1的第二条正向边目标`1→4`，将对应第二条反向边起点`1→4`（两处都只是端点值的修改，不能改变列对方向），保证类型0↔3、1↔4、2↔5的reverse pairing。G1原节点x、关系向量rel_attr、Query、mask保留完全相同；新fixture单独赋SHA256、与G1原fixture SHA明确区分。node4由孤立变为reachable，因此**禁止直接把G1旧输出和新G2基线差异归因于关系类型**；主因果对比全部在这个固定G2拓扑内部做。

### 2.1 CPU合约测试和消息签名（硬门槛）

- 合成图对象/边数、`num_relations=6`、`edge_type`范围、`rel_attr`shape和finite、`x`shape、双向实例ID一致、复合列对排序`[0,1]`、共用一个constraint identity。copy和PyG CPU/GPU device clone不得改变输入；**严禁重演G1 run001中mutating`Data.cpu()`误把前向图移回CPU**。
- 针对每个`target`计算排序不变的**入边消息输入多重集合**（建议按每条边的`(source node ID, source x的hash, rel_attr[edge_type]的逐字节hash)`构成，序列排序再hash；不得只计`edge_type`直方图），以检验图/关系干预是否在消息入口有可辨识差异。该签名是必要条件，**不是已测网络内部message tensor**。
- 原G1对称fixture可用**纯CPU**重现`C2/C3`多重集合不变作为负控；新G2 A2/A3必须至少使一个**从anchor可达**的目标入边集合不等价；关系ID+行向量同步重标A4必须对**所有节点**相等；原metadata-only A1必须保持模型消费的`x,edge_index,edge_type,rel_attr`完全相同。
- A2 只允许对`edge_type`做成对交换 0↔1和对应逆向3↔4，保持全部rel_attr行/节点x/edge_index不变；A3 在保持edge_type与全部端点不变情况下，**只改变一种关系及其逆向关系的rel_attr行**（0与3），用事先冻结的确定性坐标置换/正交变换保持单行L2 norm且改变行值，不允许改变其他角色；A4对0↔1、3↔4作`edge_type`与`rel_attr`行全双射一致重标，逐边读取`rel_attr[edge_type]`必须精确相同。
- 对A2/A3先做`input_multiset_changed=true`断言；A1/A4`input_multiset_unchanged=true`，否则**STOP before GPU**。要求包括未变动的Query/start、逆边和复合FK instance identity；测试失败则只提交工程失败，不进行forward。冻结实际实验fixture seed/hash、测试通过数量以及new branch source SHA。

### 2.2 前向对照（一个checkpoint load，**8次forward**）

| 条件 | 与固定G2基线相比改动 | 角色 | 预期CPU输入多重集合 |
|---|---|---|---|
| **A0** | 新非对称fixture与固定Query/start | 主对照 | 原始 |
| **A0_repeat** | 完全重复 | 估数值误差 | 相同 |
| **A1** | 仅`edge_attr`和自定义instance metadata的有效重标 | 负控 | 相同 |
| **A2** | 两条不同终点FK角色的`edge_type`及逆类型交换；`rel_attr`行不变 | 关系类型敏感性 | **改变** |
| **A3** | 仅role0+对应逆role3的`rel_attr`行做冻结等范数变换 | 关系向量敏感性 | **改变** |
| **A4** | 所有相关relation ID和`rel_attr`行一致全双射重标 | 不变性负控 | 相同 |
| **A5** | 仅更改起始mask至冻结的另一个合法节点 | 起点敏感性辅助 | 不涉及关系改变 |
| **A6** | 仅替换固定的第二个归一化Query向量 | Query敏感性辅助 | 不涉及关系改变 |

必须记录`[1,5]`各节点全部数值finite、max_abs、mean_abs、Top-1变化、重复基线误差以及elapsed和资源，不挑seed/节点/最大有利变化重复做实验。A5/A6为辅助机制fingerprint，不作为主成功的必要条件。

## 3. 原预注册Gate和分析口径

**数值噪声门：** `epsilon = max(1e-6, 10 * max_abs(A0-A0_repeat))`，固定FP/模型eval/inference_mode; 这是事前Gate，不是根据结果再调。

**G2-A PASS** 当且仅当全部以下条件满足：
1. Gate0结构、输入SHA、关系入边消息多重集合负/正控全部PASS；
2. A0/A0_repeat都finite、输出[1,5]，全部8 forward成功；
3. `max_abs(A1-A0) <= epsilon` 且 `max_abs(A4-A0) <= epsilon`；
4. `max_abs(A2-A0)>epsilon` **或** `max_abs(A3-A0)>epsilon`。

**G2-A NO-GO**：Gate0全部PASS、负控与重标不变性PASS、但A2和A3均`<=epsilon`。此时建议在另一个新版本进行**局部关系表示/第一层message/聚合激活探针**，分别区分`rel_mlp`改变、relation-message改变、readout被掩蔽，而不是继续随机换拓扑/seed。

**STOP-INVALID**：Gate0预检没证明干预改变入边消息集合、A4不变性失败、模型参数/fixture hash漂移、环境失配、CUDA执行失败、输出NaN/Inf、资源超限。**失败不算模型机制结论**；原run ID停止，恢复须独立登记。C2/C3换终点后可能同时影响各层传播；不要把输出非零直接称为“理解FK Role”或“业务JOIN正确”。

**优先可选的机制检查**：如G2-A NO-GO且所有输入门通过，仅保存静态CPU源码追踪和中间层拟探针方案，不在同一个实验下额外加forward或临时插hook提升成功概率。

## 4. 环境、资源与执行安全

- **前向模型**：沿用G0/G1 `rmanluo/G-reasoner-34M` revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`，官方 `RManLuo/gfm-rag` upstream commit `b3e43219c49929da505244df4f0ba54c0947e4c4`，已归档权重/model/config sha；1024输入维，不重训练、不下载新模型、不装依赖。GPU型号和实际资源以**启动前**现场预检为准，不假设某张4090必定可用。
- **Conda** `gfmrag_greasoner_20261022`（G1已验证），启用官方 `conda run` 且清理错误继承环境变量，路径和CLI脚本实际存在。提议新G2 runner `scripts/text2sql/g2_asymmetric_relation_probe.py`、unit tests `tests/test_g2_asymmetric_relation_probe.py`；新实验代码必须先提交并回读，再调用GPU。
- **预算**：至多一次checkpoint load、**8 model forwards**，训练0 epoch，一张已有授权空闲GPU，最长wall15min（含编译/加载），CPU预检≤8线程，batch仅synthetic，无BIRD/DB/API/LLM/收费服务；不可在同run ID重试。真实GPU分摊与峰值RSS无实测时写unknown，不得宣称资源成本0。
- **输出**：建议新研究分支 `research/g2-asymmetric-relation-20261024`；冻结 `docs/research/text2sql/reports/g2_asymmetric_relation_20261024_01/experiment_config.json`、clean commit、checkpoint/blob/fixture/test SHA、8case输出和Gate+资源回执；公开仅合成张量/匿名统计，原有数据库文件、BIRD原文和Gold SQL不要上传。

## 5. 平行但不混入模型效果的 CPU FK Instance Quality Gate

该Gate**不是G2模型检验的前置科学门**，可以在另一工作包并行做；不能将自动结构匹配数当Role Gold。

1. 复核P2a.5的**103 raw FK（100 valid/3 invalid）**，BIRD Gold JOIN ON 的**1428**条件归为**1199唯一declared FK匹配、25歧义、204 unmatched/非FK**；另197道问题有同表多FK候选。对`student_club`元数据缺口特别说明，不能默认Gold JOIN坏或Gold业务角色已人工核对。
2. 设计实例主键如`(DB alias, FK constraint来源+稳定hash, source table, ordered source→target column pairs, target table)`；确保完整复合FK原子性、别名/双向边引用同一个实例、同一对表多个FK不被折叠；合成billing/shipping和双列复合FK做单测。
3. 固定最多20个多FK/复合/桥表候选作**私有本地**人工role核查队列，冻结匿名分层与样本ID SHA；两名盲审核者独立判断gold role与结构类型，再汇总分歧、一致率和`trusted_role_label_n`；没有人力时明确`human_review=0, trusted_role_label_n=0`，不可造标签。
4. 独立产出 `docs/research/text2sql/reports/g2_fk_instance_quality_YYYYMMDD/` 匿名数量/结构失败/人工审核状态。此工作与G2 synthetic forward的模型结果分开报告，**不能把结构完整性自动推成查询相关EdgeGate效果**。

## 6. G2结果之后的学术路线

- **若G2-A PASS**：说明特定非对称合成图上至少一个已消费relation channel能改变模型分数，优先**Relation-typed G0 baseline**，但面对同端点多FK instance仍需可辨识设计（instance-node、edge-level scoring或instance-indexed propagation）；之后在可信Role labels形成、冻结独立DB时再注册Query-conditioned instance gate+合法JOIN path对照。
- **若G2-A NO-GO**：下轮定位关系张量在`rel_mlp → NBFNet message → aggregation → score`何处被消去，并检验是否有特定anchor可达性/输出目标阻断，不允许直接解读为全模型关系能力失效。
- **若Gate0/A4 FAIL**：优先修CPU输入合约/实例配对或copy逻辑；不是“方法无效”。
- 真实论文主结果必须与Dense Cosine、Relation-typed G0、简单FK graph/path baseline、公平信息/预算下的G-reasoner及新Edge Gate比；报告Query-conditioned Role/Join Path和最终SQL Set EX，不能只靠synthetic`delta>0`。

**最终执行指令：新建独立版本G2，先跑CPU消息多重集合强预检，再按8前向限额运行，冻结成功门；FK Role 标签治理并行。当前文件不含任何G2实测成绩。**
