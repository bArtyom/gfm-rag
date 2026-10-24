# G2 FK Instance稳定编码质量Gate

> **状态：SMOKE PASS / FULL PENDING。** Smoke结果已记录；全量结果尚未运行。协议见[实验方案](../../plans/g2_fk_instance_quality_gate_20261024.md)。

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

使用Python 3.10.21及标准库，在CPU上只读1个BIRD dev SQLite schema。结果为`SMOKE_PASS`：原始FK实例2，有效2，无效0；双向有向边4，ID碰撞0，复合FK 0，同端点多FK表对0。输入顺序不变、PRAGMA组号重编号不变、反向边配对检查均通过。该样本没有复合FK，故复合组件顺序敏感性仍由全量中实际出现的复合实例验证。Smoke进程wall 0.00139秒、CPU 0.00123秒、峰值RSS 0.0190 GiB。GPU/API/模型/SQL执行/依赖安装均为0。

私有JSON结果：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/smoke_002/result.json`；原始日志：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/smoke_002.log`。JSON内逐数据库摘要与日志留在本地，不公开上传。

### Full `g2_fk_instance_quality_20261024_01_full_001` — 待运行

Smoke通过后，按已登记命令扫描11个SQLite schema。预注册门槛仍为103原始/100有效/3无效；分母不符时记为`INCONCLUSIVE`并停止，不调整门槛。全量报告会补充聚合结果、资源使用、失败/异常和保守结论。
