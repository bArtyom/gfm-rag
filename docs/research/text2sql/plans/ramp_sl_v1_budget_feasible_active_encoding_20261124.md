# RAMP-SL V1：真实预算约束下的两轮主动 Schema 编码实验指导

> **2026-11-24｜设计与待执行协议（NOT RUN）**。本文件是 RAMP-SL 下一轮实验的**执行指导**，不是结果报告，也不表示新方法已验证。参数在本文件固定；在首次读取新一轮配对结果前完成数据/代码可行性审计、记录 SHA 并冻结 protocol/config。若预检失败只能 HOLD 并另开 amendment，不允许看过 test 结果后改门槛。
>
> **工作分支：** research/ramp-sl-v1-active-encoding-20261124，基于 RAMP-SL 结果提交 c8c75d3c53e0cf73e80d56fe995a4e99a425c4d6；不改 main，不重开已停止的预算修复、Steiner 或 G2 主线。
>
> **先前证据：** [RAMP-SL 昂贵评分上限报告](../reports/ramp_sl_encoding_budget_gate_20261123_001/README.md)；[RAMP-SL idea](ramp_sl_progressive_schema_encoding_idea_20261123.md)；[BoundaryMORPH 独立报告](https://github.com/bArtyom/gfm-rag/blob/d9cca989dbe38f2b8d717860e86ad2665a9305fc/docs/research/text2sql/reports/boundarymorph_grast_bird_20261123_001/README.md)（注意它在另一个研究分支，当前基线未合并到本分支）。遵守 [复现契约](../reproducibility-contract.md)。

## 1. 已经证明了什么、还没证明什么

2026-11-23 BIRD-dev 离线上限实验使用冻结 Qwen3-Embedding-0.6B 1024D cache，以及正式发布的 GRAST-SQL 0.6B BIRD Reranker 的 yes/no logits。固定入选字段的昂贵评分输入预算 M=4,096 tokens、Schema 输出预算 B=2,048 tokens：

| 阶段 | 可评问题/数据库 | Static 完整 Gold 列覆盖 | 全字段预评分参考（Offline Oracle） | 差值 |
|---|---:|---:|---:|---:|
| Pilot | 110/11 | 73/110（66.36%） | 100/110（90.91%） | +24.545pp |
| Full 预算停止前 | 1,046/8 | 603/1,046（57.65%） | 915/1,046（87.48%） | +29.828pp |

**不能说“算法已经提升 29.83pp”**：Oracle 在挑选预算内字段前已调用昂贵模型评分所有列，真实输入 token 显著超出 M，因此不是可部署的同计算成本算法；Full 的 1,046 题还由冻结顺序/16M 总 token 上限截断，不是全量或随机样本。上次输出最大 token 为 Static 1,560、Oracle 1,439，均小于 B=2,048：**B 在该批样本上没有成为有效约束**，主要观察到的是“谁获得昂贵编码”的差异。

**本轮唯一主张：** 在真正只允许对总输入 token ≤M 的问题—列对运行 GRAST Scorer 时，按已有评分自适应选择第二批列，能否比固定 Top-M 和其他预算可行策略完整保留更多参考列？本轮不训练 GRAST 模型、不运行 GNN/Steiner/SQL、不声称 end-to-end EX、完整 GRAST-SQL 复现或新颖性已成立。

## 2. 核心算法：RAMP-SL V1（两轮；可执行而非空泛描述）

### 2.1 固定输入与三类预算

- **Candidate universe C(q)：** 该问题所属 DB 的**全部列**；稳定 node ID、原始表归属和冻结 P1.6 列文本与向量，不允许用 Gold 过滤候选。初始便宜排序为 Qwen3 余弦（并列时按 node ID 字典序）。
- **昂贵编码成本 t(q,c)：** 冻结的 GRAST prompt 使用实际 GRAST tokenizer 编码（单条最大 4,096 tokens）；计入 query/instruction/列描述的全部 non-padding 输入 token，含重复的 query 前缀。不得以列数、Embedding token、输出列 token 代替。**M=4,096 tokens/题，第一轮 M0=2,048，第二轮剩余 M−已花费的实数 token**。每轮若下个候选放不下，跳过并检查其余候选；不重复打分。
- **Schema 输出预算 B=2,048 tokens/题（主）**，次要敏感性分析预先固定 B∈{512,1024}，不据结果选 B。为保持同历史实验可比，主分析沿用**实际 runner 的 node.text 完整文本序列化**与同一个 pack_output；历史 protocol 写的是 table.column(type)，但实现实际用了 node.text。先登记该不一致，不能无声改版。无需 FK/Steiner 闭包；若未来添加，另起实验。

### 2.2 第一轮：固定低成本起点

1. 用便宜 cosine 在全库列排序；逐列装入 M0=2,048，按实测 GRAST prompt token 计费，跳过装不下的列，得到 S0。
2. 仅对 S0 进行昂贵 GRAST 0.6B Scorer 推理，取 P(yes)，保存实际评分与成本。
3. 对未评分列 C\S0，使用 **BoundaryMORPH 的冻结 GP 代理**结合廉价列向量、排名先验和 S0 观测来估计昂贵分数的均值 μ(c)、标准差 σ(c)。在单题所有候选列的 L2-normalized embedding 上构建 cosine 矩阵；median_distance = max(median(1−cosine_ij, i<j), 1e−6)，κ=ln(2)/median_distance，K_ij=exp(κ(cosine_ij−1))。N>1 时 prior_i=1−rank_index_i/(N−1)，N=1 时 prior=1；另加**问题向量作为 score=1、prior=1 的零成本 anchor**，anchor 的核使用同一 κ。对观测的 score−prior residual 做均值中心化及标准差缩放，标准差下限 0.05；GP 核对角 jitter=1e−6；用原 BoundaryMORPH 的后验均值、方差公式，所得 μ 在用于打包/预测时 clip 到 [0,1]，σ 保持非负。本轮 GP 直接拟合 GRAST P(yes)，**不额外做 logit 变换**，以控制变量。无 test 参数搜索。若 GP 奇异、样本不足或预测非有限，执行固定 fallback：训练集校准的 cheap-only 分数预测并记录数量；不能用未评分字段的真实昂贵分数初始化 GP。

### 2.3 训练库内拟合“需要这个字段”的轻量校准器

避免把“预测昂贵相关分数”当作“字段必需概率”。拟合一个**简单、固定的 L2 Logistic Regression**，用训练 DB 的已解析 Gold-column 标签为监督，输出 p(c)=P(参考 SQL 使用列 c | 当前可见证据)。

- 训练特征只来自在线允许信息：cheap cosine、cheap rank percentile、log(1+t)、表/列名与 query 的固定词面重合率、GP μ、GP σ。标准化均值/方差仅从训练库计算。若列已评分，则可用实际 GRAST 分数与 observed flag；未评分只能用 GP 预测均值及 missing flag。训练时必须模拟相同 M0 初始评分场景，不能用训练时“全评分”特征假装测试时已观测。
- 固定 solver=lbfgs、C=1.0、max_iter=200、无 class_weight、无 test 调参；只在训练库拟合。若缺少必要依赖，在任何新结果读取前做可重复的等价实现并记录依赖/差异，不可隐式安装或换模型。
- **训练可以使用训练 DB 的 Gold 和离线全字段分数；测试 DB 的 Gold 只在 sealed 输出后评测，未评分昂贵分数只能由收费的 replay oracle 单次读取。** 不把测试 Gold、Oracle 排名、SQL 或 oracle 与 Static 的输赢用于模型训练、特征、候选选择。

### 2.4 第二轮：预算成本感知的集合效用选择

定义当前已评分列集合 S（开始是 S0）。对所有列用训练后校准器预测必需概率 p(c)，为数值稳定截断到 [1e-4,1−1e-4]。用已知昂贵分数将 S 按历史 pack_output 在 B 下输出成 T(S)。

用“完整保留的代理概率”衡量集合质量：

    log Q(T) = Σ_{c∈C\T} log(1−p(c))

这是**假设字段必需性独立的代理目标，不是真实完整召回概率，也不代表已学会 JOIN 约束**。它使漏掉高必需概率列受到更强惩罚。V1 不对该独立假设额外增加图模块。

对于每个预算可行的未评分列 c：

1. 根据 GP μ、σ，用固定八分位正态分位点 (j−0.5)/8、j=1..8 模拟它的昂贵评分，映射回 P(yes)。
2. 把“当前评分列 + 假设已评分的 c”用**同一个 B packer**重排，得到 8 个反事实输出集合 T_j(S∪{c})。计算在**固定当前 p** 下的 Q 改进；不得通过假想观测后任意降低其他列 p 来制造提升。
3. 取 8 次改进的平均，除以 t(q,c) 得到效用 U(c)。负收益记为零。相同 U 先选更低成本，再按 node ID 稳定排序。
4. 在剩余 M−spent 下贪心规划第二轮**一个批次** S1；在规划时，已排入但尚未实际评分的列暂用 GP 均值参与 B packer，下一候选重新计算 U。**整个批次只在计划完成后评分一次**，不允许用同批先评分结果重新挑同批其他列。所得 S1 使用真实 GRAST 打分，最终只可从 S0∪S1 中按真实昂贵分数和同一 B 序列化输出。

当 B=2,048 不紧时，集合效用可能退化为近似 p(c)/token 的排序；这是**本方法需要证伪的退化风险**，不能在这种情况下宣称“集合级建模已被证明”。必须对比“校准概率/成本、无 GP”的强消融；在 B=512/1024 下再分析集合代理是否真的带来增益。最终 Gold 只用于计算指标。

### 2.5 可实现的伪代码

    cheap_order = frozen_cosine_sort(all_columns)
    S0 = budget_fill(cheap_order, M0=2048, cost=exact_grast_prompt_tokens)
    observed = replay_score_only(S0)   # 只有查询此函数才可见昂贵分数并记实际 token
    gp = fit_query_gp(cheap_features, observed)
    p = frozen_train_db_calibrator(cheap_features, gp)
    S1 = []
    while exists_unscored_column_fitting_remaining_M:
        c = argmax_cost_adjusted_expected_set_gain(
            S0, S1, observed, gp, p, B=2048, eight_fixed_quantiles
        )
        S1.append(c)  # 仅规划；gp/p 不读取同批真实分数
    score_all_in_one_batch(S1)
    output = shared_pack_output(S0 + S1, their_observed_grast_scores, B=2048)

若发生预算空间不足、空候选、GP fallback，应明确记录并正常终止。**禁止在测试时直接使用离线全评分数组排序候选。**

## 3. 数据、隔离与合法的 Replay

- 只复用既有私有缓存：冻结 BIRD-dev P1.6 向量/列 Gold、RAMP-SL smoke/pilot/full 每题全列 GRAST 评分与逐列 token 成本；去重键 (db_id,question_id)，校验模型 revision、权重和 prompt/text/token/hash、字段全集一致。Full 只有 1,046/1,460 题、8 DB；pilot 110/11 DB，不准把未评分问题补成伪分数或称完整全量。
- **数据可用性预检（不读取 Gold 结果）：** 对每个 DB 统计全评分完备的去重题数。先过滤至少 40 题的 DB；以 SHA256("ramp-v1-test-20261124|" + db_id) 升序取前 3 个**测试 DB**，其他全部为训练 DB。Test DB 不可进入校准器训练或任何按测试效果调整的超参。若合格 DB 不足 3、测试题少于 80 或训练库少于 3 个：结果为 HOLD_INSUFFICIENT_COVERAGE，停止主 Gate，不得按 test 结果改抽样/换库；仅允许提前登记新版独立协议。
- **内部训练验证：** 训练 DB 中用固定哈希按题键取最多 20 题/DB 做 smoke、单元和算法正确性审计，不触碰测试 Gold；所有 V1 特征、L2、初始预算和 8 个积分点已在本指导固定。完成实现及复现测试后记录 train/test ID 哈希、代码/config SHA、预检样本数，seal 配置，测试只跑一次。
- BIRD-dev/公开 GRAST BIRD 微调模型已在历史研究中反复暴露，**DB 隔离只隔离本轮轻量校准器**，不是新的外部测试集，也不证明官方模型零样本泛化。未来论文必须额外寻找完全未参与模型微调与策略开发的 DB/数据集复现。
- Replay 包装器对每题持有不可直接访问的全列私有分数 map；暴露唯一 API：score(q, column_ids)，先检查 ID 与剩余 token 再返回对应真实分数；同一个列不能重复计费/调用。每次调用留下按序的 ID 哈希、prompt tokens、分数可见时间点、batch 数以及预算剩余。**Full Oracle 只能在全部在线策略输出封存后用于参考分析**，不可被在线方法拿来规划。

## 4. 需要公平比较的策略（同一 C、cache、M、B、scorer）

| 方法 | 第一轮 | 第二轮 / 选择机制 | 目的 |
|---|---|---|---|
| Static-TopM | 无分轮，cheap 顺序取满 M | 无 | 原实验现实基线 |
| Stratified-2R | cheap Top-M0 | 按 cheap 排名分位桶轮询，跳过不合成本列；seed=20261124 | 强制探索非前排字段的简单基线 |
| Random-2R | cheap Top-M0 | 固定 SHA256(seed,q,id) 顺序取满剩余 M | 额外下界 |
| BoundaryMORPH-2R | cheap Top-M0 | 基于相同 GP 的 Top-K 边界不确定性，K 为在 B 下当前可输出列数；**第二轮逐个真实评分、逐个更新 GP**，总输入 token 仍≤M；若边界不可定义，使用固定 cheap fallback，并如实记录顺序调用的时延 | 既有主动采样方法的公平迁移；**需要新实现与验证，不能把旧 Jina 结果直接搬来** |
| Calibrated-2R | cheap Top-M0 | 只用训练库 p(c)/t(q,c)，**不使用第一轮 GRAST→GP 残差更新**；其余相同 | 检验是否只是有监督重排序 |
| **RAMP-SL V1** | cheap Top-M0 | GP + 8 点反事实集合质量提升 / t(q,c) 的第二轮批次 | 待验证的新策略 |
| Full-score Reference | 在全列上评分后再预算选择 | **实际评分成本通常超过 M** | 只给参考 headroom，不进公平排名/GO 判定 |

BoundaryMORPH 原实验使用 Jina、固定 16 次评分、输出 Top-30；本轮迁移至 GRAST、token 预算后需独立验证实现细节。记录每种方法可实际编码列数及 M 消耗，不能把分轮/打分次数不同误称同预算。

**消融（不在 test 上调参）：** (a) RAMP 去掉 GP（退回 Calibrated-2R）；(b) 将集合改进改为单列 p/t；(c) 不考虑 token 成本而按效用选列、仍不能超过 M；(d) 在 B=512/1024 做固定敏感性对照，明确哪些问题 B 真实绑定。消融与主实验使用相同分库与缓存。

## 5. 主次指标、门槛和错误归因

**唯一主指标：** 测试 DB 全部具备完整缓存的可评题上，Complete Gold-column Coverage@B，即“最终选中列包含该题全部冻结参考 Gold 列”的题比例；全部 DB/样本纳入分母，包括预算饱和、标签多义潜在问题（另报告解析状态）。没有 Gold 列可唯一裁定的题按旧 P1.6 eligibility 规则隔离，不偷删失败题。对所有方法计算同题配对 Rescue / Damage。

**硬约束：** 每题 sum(实际看见昂贵分数的 prompt tokens) ≤4,096；只在已显式评分字段上用其真实 GRAST 分数，0 次未授权 cache peek；单次输入长度 ≤4,096；全流程输出 ≤2,048 tokens。违反任一约束则 CONTRACT_FAIL，不得发布收益。

**必须同时报告：**
- 全体与非饱和子集：非饱和定义为“所有列的真实昂贵评分 token 合计 >4,096”，且静态 Top-M 未完整覆盖 Gold；两种切分分别公布分母，子集不可替换全体主指标。
- 微/宏 Gold-column Recall、Precision、实际评分字段个数和 M 实花/剩余 token、最终 B 输出 token 与 B 是否紧约束、每库指标。
- Static→各策略 Rescue / Damage、配对 95% DB-cluster bootstrap（10,000 固定 seed=20261124；仅 3 个 test DB 时如实标明区间不稳定）与逐库变化；不把 p<0.05 当唯一判断。
- Replay token=模拟真实编码账单，与实际新增 GPU 调用=0 明确分列；未来实测单题 cold/warm latency、评分批次数、CPU GP/calibrator 开销与 p50/p95，再评估是否在线可用。不得把缓存查询时间当成真实 reranker 延迟。
- 差异样本匿名归因：cheap 候选漏列、第二轮挽救、过度探索、模型误判、候选预算饱和、B 是否绑定、同名列/多表歧义、Gold 不唯一风险。

**设计时固定的 Stage Gates（本文件并非结果）：**

1. **PRECHECK/HOLD：** 至少 3 个 DB 满足 40 条全列完整缓存；按上文规则抽出的测试 3DB 有 ≥80 题且训练 ≥3DB。另报告非饱和题比例；若可辨别题过少，只允许作探索性分析，不声称否定算法本身。
2. **REPLAY_CONTRACT：** 独立匿名审计逐题预算/序列化、缓存访问策略、数据拆分与稳定性均 PASS；核对 Static-TopM 在相同去重题/预算/输出序列化上的历史逐题结果一致。5 题 CPU smoke、至少 30 题训练 DB replay 单元/回归通过，再 seal test。
3. **SCIENCE GO（只允许表述为“值得独立复现”）：** 在 test 全体主指标上，RAMP−Static ≥+3.0pp；RAMP−最强的**实际预算可行**对照（含 BoundaryMORPH 与 Calibrated-2R）≥+1.0pp；在至少 2/3 测试 DB 上对 Static 净 Rescue>Damage；无预算或泄漏违规。任何一项未过则 STOP_THIS_V1 / PIVOT，不在同一个 test 上改指标/模型/阈值。DB-cluster CI 若跨零必须明确结果不稳健，即使观察值过门也不能声称统计显著。
4. **SET-LEVEL 额外资格：** 若全体主分析的 B=2,048 不紧，SCIENCE GO **只能**支持“预算内主动编码选择”，不能声称集合级优化带来独立收益；仅当预注册 B=512/1024 的同预算实验中，RAMP 超过 p/t 消融且配对改善有明确证据，才将“集合级效用”列为待外部复现机制。若两个较小 B 的效果也无差异，应删减该模块，不继续堆叠复杂 GNN/图摘要。

本门槛不用于对已知 Oracle 提升的二次宣告。所有对照先运行并封存 outputs，随后才计算 Gold/Oracle，不能试过 test 再补充有利子集。

## 6. 代码与产物建议（均待创建，不能冒充已存在）

- 配置：configs/text2sql/ramp_sl_v1_active_encoding_20261124.json（M/M0/B、seed、hash、训练/测试分库、模型与缓存 SHA、门槛）。
- 实现：scripts/text2sql/ramp_sl_v1_active_encoding.py；把 replay score API 与模拟调度分开，禁止直接读取离线所有分数的普通 dict。
- 单测：tests/test_ramp_sl_v1_active_encoding.py；必须覆盖预算跳列/余量、batch 因果隔离、同列重复计费、测试 Gold/全评分访问禁令、可重复 tie-break、GP 退化 fallback、同一 packer B=512/1024/2048、无隐藏 SQL/Steiner、DB 数据隔离及无输出预算超额。
- 报告：docs/research/text2sql/reports/ramp_sl_v1_active_encoding_20261124_001/README.md 与 aggregate.public.json；训练/测试身份、逐题 Gold/分数、SQL、问题文本、向量、模型权重、日志留在本地私有目录，不上传。
- 执行顺序：**先完整性审计/Hash → 冻结 test 分库和指标 → 只用训练 DB 实现与 smoke → 运行封存一次的测试 Replay → 独立逐题聚合校验 → 标记 GO/STOP/HOLD → 另行决定是否真实 GPU 时延对照或 SQL 下游试验。** 本文件本身不执行任何计算实验，也没有申请新增 GPU 或 API 费用。

## 7. 科学边界与下轮决策

- 这是在 RAMP-SL 的官方 GRAST 评分缓存上验证**预算内可部署的查询时列选择策略**，不是复现官方 GRAST GNN/Steiner/SQL；若收益需要提前看到未选择字段真实分数，判作泄漏，不能算成功。
- 训练监督采用冻结参考 SQL 的 Gold-column 标签，只是“参考 SQL 使用的列”，可能有多种同义 SQL；不等价于唯一语义必需列。FK/Role Gold Gate 仍未过，不能加入未验证的连接监督。
- 如果 Calibrated-2R 和 RAMP 表现基本相同，说明“监督式廉价重排”或成本比值已经解释收益，不能为 GP、主动编码或集合模块申报新颖性。如果 BoundaryMORPH 更强，应该优先沿已有算法做有控制的结构改动或停止 V1。
- 如果在非饱和题、不同 DB 及实际评分延迟下都明确占优，再单独预注册真实 GPU 在线评分验证和 GRAST 图/Steiner 接入，最后才做固定 SQL 生成器下的 paired EX；不把本轮覆盖收益直接外推成 SQL EX。
- **这次 GitHub 提交仅保存下一轮指导；没有运行 RAMP-SL V1 实验，也没有产生它的实验结果。**
