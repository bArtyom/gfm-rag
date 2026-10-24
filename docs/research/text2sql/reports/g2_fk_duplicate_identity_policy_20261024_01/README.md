# FK完全重复约束身份策略探索

> **状态：EXPLORATORY_COMPLETE；原FK Instance Gate仍为NO_GO。** 本工作包来自[G2 FK Instance结构Gate的NO_GO](../g2_fk_instance_quality_20261024_01/README.md)，比较唯一Join映射与保留声明重数的两种表示。它没有改写原Gate，也没有进入Relation-typed G0。

## 研究问题与核心假设

两个不同SQLite FK约束组可能具有完全相同的规范化数据库/源表/目标表/有序列对。排除PRAGMA组号能保持顺序与重编号不变性，却无法把这样的重复声明分成两个基于内容的身份。本探索回答：映射级去重能否保留所有不同的Join映射并单独记录声明重数；出现序号能否保留每个声明并产生稳定的ID集合，以及该序号是否能稳定绑定到具体PRAGMA组。

比较两个预登记策略：

- **Mapping identity**：完全相同的有效结构共用一个mapping ID，每个唯一映射输出一对正反向边，原声明数作为重数另行报告。
- **Declaration multiset identity**：保留每个有效声明，以结构键加重复出现序号生成唯一ID和对应边。重排/重编号后要求ID多重集合稳定；同时报告组号到序号的关联变化，不声称它是可稳定追踪的单个声明ID。

## 预注册范围与门槛

- 只读BIRD dev SQLite schema；Smoke处理1库并运行合成重复/近似映射/复合FK fixture；通过后Full扫描11库。
- 复现原Gate的103个FK声明、100有效、3无效，以及1组完全重复有效映射；数据快照与schema manifest必须匹配原Gate。
- Mapping策略必须仅合并结构完全相同的映射，保留声明重数，且不同列映射仍有不同ID；唯一映射各生成2条反向配对边。
- Declaration multiset策略必须为100个有效声明提供唯一ID，各ID都有一对边，ID集合对FK行顺序和PRAGMA组号重编号不变；完全重复声明的组号—序号关联变化作为限制明确报告。
- 预算：单线程CPU≤300秒、RSS≤2 GiB；GPU/API/模型/SQL/人工审核/依赖安装均为0。Smoke失败、历史分母或输入hash变化、schema错误、超预算即停止。
- 该实验只比较表示属性，不自动选择生产策略；不运行G0模型或SQL评测。

## 运行前注册信息

方案见[独立实验计划](../../plans/g2_fk_duplicate_identity_policy_20261024.md)，固定配置与命令见本目录`experiment_config.json`。代码为`../../../../../scripts/text2sql/fk_duplicate_identity_policy_audit.py`。所有逐库摘要、数据库名称和原始日志只保留本地私有目录。

## 结果

### Smoke `g2_fk_duplicate_identity_policy_20261024_01_smoke_001` — `SMOKE_PASS`

Python 3.10.21标准库，CPU只读1个BIRD dev SQLite schema；原始2个、有效2个FK声明，输入hash匹配预注册。真实单库没有完全重复映射，因此只作为路径与输出smoke。内存合成fixture有4个有效声明：mapping策略将完全重复的一对合成一个映射（3个唯一映射、6条方向边、重数1）；声明multiset策略保留4个唯一ID并生成8条方向边。两策略的ID集合均通过行顺序与组号重编号不变性检查；重复声明fixture在multiset策略下有2个组号到出现序号关联随重编号变化。复合FK fixture保持为一个实例，反转组件顺序会改变身份。进程wall 0.00313秒、CPU 0.00267秒、峰值RSS 0.0190 GiB；GPU/API/模型/SQL/依赖安装均为0。

私有结果：`/mnt/liansp3/logs/g2_fk_duplicate_identity_policy_20261024_01/smoke_001/result.json`；日志：`/mnt/liansp3/logs/g2_fk_duplicate_identity_policy_20261024_01/smoke_001.log`。Full扫描11库并复现预注册hash/分母后，才判断BIRD重复约束上的两种策略表现。

### Full `g2_fk_duplicate_identity_policy_20261024_01_full_001` — `EXPLORATORY_COMPLETE`

按冻结配置扫描11个SQLite schema。复现原Gate全部结构输入：103个原始FK声明、100有效、3无效；`dev_tables.json` SHA-256为`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`，与预注册一致；schema manifest SHA-256与原Gate完全一致（`89765355de0a75d03a547afa5bf04eed21857f28d393aeb4e94c20e18212c74e`）。只读取`sqlite_master`、`PRAGMA table_info`和`PRAGMA foreign_key_list`，未读取问题、Gold SQL或业务表行。Full wall 0.02564秒、CPU 0.02118秒、峰值RSS 0.0190 GiB；单线程CPU，GPU/API/模型/SQL/人工审核/依赖安装均为0。

| 策略 | 有效身份数 | 有向边 | 对行/组号重排的ID集合 | 重复约束的组号绑定 |
|---|---:|---:|---|---|
| Mapping identity | 99个唯一映射；保留1个重复声明的重数 | 198 | 稳定 | 同一映射共用ID，不把重复声明伪称为两个可区分映射 |
| Declaration multiset | 100个声明ID | 200 | 稳定 | 2个重复约束组的出现序号绑定随PRAGMA组号重编号而变化 |

两种策略都保留了非相同的列映射身份并通过正反向边配对检查。合成fixture也通过：mapping策略将一对重复项表示为一个映射和重数，multiset策略将其表示为两个ID；同端点不同列映射保持分开；复合FK作为单一实例且组件顺序变化会改变身份。BIRD全量实际有0个复合FK，因此复合顺序证据仅来自合成fixture。

### 结论与决策边界

探索回答了原Gate反例的表示取舍，但**不会自动将原Gate翻为PASS**。结构内容可以稳定标识唯一Join映射；若保留两个完全相同的声明，则出现序号生成的ID集合稳定，但无法稳定指回某个具体PRAGMA组。结构本身没有信息区分这两个声明。

对后续G0的候选建议是将身份定义为**唯一Join映射**，并把原始声明重数作为单独元数据；相同映射只生成一对边。这样保留99个不同有效映射及所有不同列对，也避免重复边额外改变消息聚合。此为表示建议，不是已执行的G0结果。需要先在下一份G0预注册中明确采纳该语义和对应门槛；Relation-typed G0本轮没有运行。

局限：BIRD dev是重复使用的开发诊断数据，不是独立测试集；没有查询条件、Gold角色标签、人工审阅或SQL EX。结果只支持结构编码与稳定性判断。

## 复现信息与产物

- 方案和固定命令见[计划](../../plans/g2_fk_duplicate_identity_policy_20261024.md)及`experiment_config.json`。Smoke在分支预运行commit `a90cfef`后启动；Full在Smoke报告commit `3c5720f`后启动。公开运行器为`fk_duplicate_identity_policy_audit.py`，SHA-256 `23f96e1db5bec304bb1b6deeddd9efd1638801ad03cb7c24bfe50f36f89d632d`；基础FK扫描器SHA-256 `a2ff6a331bad4c74fd4cffd7bd5df0295e15f2ba1ab87d5f1e4d641489f5b5`。
- 实验前在基点`79f2bba7d1065a75c2bf4baf1d905d056ceb3473`读取仓库根`README.md`、研究工作台`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、G2预注册计划和父级FK Gate报告；该仓库基点无`AGENTS.md`，同时遵守用户提供的`/mnt/liansp3/AGENTS.md`。
- 环境：`precisiongate_bird`、Python 3.10.21、标准库；机器192 CPU逻辑核、503 GiB RAM（启动检查时约422 GiB可用）、114 TB磁盘可用；实验只用1个CPU线程，不请求GPU。
- Smoke命令：`/usr/bin/timeout 300s conda run -n precisiongate_bird /root/miniconda3/envs/precisiongate_bird/bin/python3.10 scripts/text2sql/fk_duplicate_identity_policy_audit.py --dataset-root /mnt/liansp3/sources/datasets/bird/dev/dev_databases --mode smoke --run-id g2_fk_duplicate_identity_policy_20261024_01_smoke_001 --output /mnt/liansp3/logs/g2_fk_duplicate_identity_policy_20261024_01/smoke_001/result.json`
- Full命令：`/usr/bin/timeout 300s conda run -n precisiongate_bird /root/miniconda3/envs/precisiongate_bird/bin/python3.10 scripts/text2sql/fk_duplicate_identity_policy_audit.py --dataset-root /mnt/liansp3/sources/datasets/bird/dev/dev_databases --mode full --run-id g2_fk_duplicate_identity_policy_20261024_01_full_001 --output /mnt/liansp3/sources/results/gfmrag_g2_fk_duplicate_identity_policy_20261024_01/full_001/result.json`
- 私有JSON：`/mnt/liansp3/sources/results/gfmrag_g2_fk_duplicate_identity_policy_20261024_01/full_001/result.json`；私有日志：`/mnt/liansp3/logs/g2_fk_duplicate_identity_policy_20261024_01/`。逐库hash、名称和原始日志不公开。
