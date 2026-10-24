# G2 FK Instance稳定编码质量Gate

> **状态：FULL NO_GO。** 计数匹配历史参照，但发现1组有效FK身份碰撞，反向边配对门槛失败；Relation-typed G0暂不运行。协议见[实验方案](../../plans/g2_fk_instance_quality_gate_20261024.md)。

## 研究问题与边界

验证BIRD dev只读SQLite schema能否生成确定性的FK Join-Instance身份，保留复合外键有序列对、同实例双向边以及同端点不同FK映射。该实验只检验结构序列化，不评估业务角色语义、JOIN选择、路径准确率、SQL EX或G-reasoner效果。BIRD dev是反复使用的开发诊断集，不是独立测试集。

## 预注册门槛

- Full覆盖11个SQLite schema，历史结构计数参照为103原始FK、100有效、3无效。
- 有效实例ID唯一；数据库/FK行枚举顺序和PRAGMA group id重编号不改变ID；复合列顺序变化会改变ID；每个有效FK有同ID的正向/逆向边。
- 先1数据库CPU smoke，通过后再扫描全量；预算CPU 1,800秒、RSS 16 GiB、线程数8、GPU/API/模型/SQL/依赖安装均为0。
- 任何历史分母差异记为INCONCLUSIVE，保留现场，不更改门槛；没有人工审阅，因此`human_review=0, trusted_role_label_n=0`。

## 结果

协议已在GitHub commit `b3c60a2`预注册。启动前检查发现runner最初只查SQLite目录顶层；递归路径测试在任何BIRD数据读取前复现该问题，修正提交为`b2129583`，修正后9/9合约测试通过。代码及测试内容在首次数据读取前已按GitHub commit `f1398935`回读校验。

### Smoke `g2_fk_instance_quality_20261024_01_smoke_001` — 启动失败

宿主缺少`/usr/bin/time`，shell退出127；runner未启动、未读取BIRD文件，也未生成结果。失败日志保留在`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/smoke_001.log`。这是启动错误，不是科学结果；修复后采用新run ID。

### Smoke `g2_fk_instance_quality_20261024_01_smoke_002` — 通过

使用Python 3.10.21及标准库，在CPU上只读1个BIRD dev SQLite schema。结果为`SMOKE_PASS`：原始FK实例2，有效2，无效0；双向有向边4，ID碰撞0，复合FK 0，同端点多FK表对0。输入顺序不变、PRAGMA组号重编号不变、反向边配对检查均通过。Smoke进程wall 0.00139秒、CPU 0.00123秒、峰值RSS 0.0190 GiB。GPU/API/模型/SQL执行/依赖安装均为0。

私有JSON结果：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/smoke_002/result.json`；原始日志：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/smoke_002.log`。JSON内逐数据库摘要与日志留在本地，不公开上传。

### Full `g2_fk_instance_quality_20261024_01_full_001` — `NO_GO`

按预注册命令扫描全部11个SQLite schema，读范围严格限于`sqlite_master`、`PRAGMA table_info`和`PRAGMA foreign_key_list`。历史分母完全复现：原始103、有效100、无效3；3个无效实例均为`target_table_missing`。因此数据计数门槛通过。其余聚合结果：有向边200；同端点多FK表对9；按表端点去重会丢失30个有效映射；有效身份碰撞1；反向边配对失败。全量wall 0.01943秒、CPU 0.01478秒、峰值RSS 0.0190 GiB。数据schema清单聚合SHA-256为`89765355de0a75d03a547afa5bf04eed21857f28d393aeb4e94c20e18212c74e`，`dev_tables.json`哈希与预注册相同。没有读取问题、Gold SQL或业务表行。

### 失败原因与结论

本地只读诊断确认碰撞来自两个**不同PRAGMA约束组**，但它们规范化后的数据库/源表/目标表/有序列对完全相同。当前身份键有意排除PRAGMA组号，因此把这两个声明编码成同一ID；随之产生的4条边不能拆成两组各自唯一的正反向边，配对检查失败。这不是SHA-256随机碰撞，而是身份定义无法区分完全相同的约束声明。失败条件是真实数据反例，不能靠重跑或调整阈值消除。

全量没有复合FK（`composite_instance_count=0`），因此程序显示的复合顺序敏感检查为真是空集合上的真值，不构成BIRD实证。原先9项合约测试通过，但没有覆盖这种完全重复的真实约束。

**结论：**预注册的唯一实例ID/双向边门槛未通过，核心假设被精确重复声明反例否定；本Gate为`NO_GO`。后续Relation-typed G0模型前向不启动，以免把不唯一边身份传入模型。需要先决定重复约束应作为一个语义映射去重，还是保留声明重数并另定义稳定的重复项编号，再独立预注册和验证；本报告没有采用任何新规则。BIRD dev为重复使用的开发诊断集，结果不代表独立泛化。

私有全量JSON结果：`/mnt/liansp3/sources/results/gfmrag_g2_fk_instance_quality_20261024_01/full_001/result.json`；原始日志：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/full_001.log`。逐数据库哈希、SQLite名称和schema细节不公开。
