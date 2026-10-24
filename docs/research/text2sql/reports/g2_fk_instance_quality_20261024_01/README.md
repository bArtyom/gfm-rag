# G2 FK Instance稳定编码质量Gate

> **状态：已预注册 / NOT RUN。** 不含实验结果。协议见[实验方案](../../plans/g2_fk_instance_quality_gate_20261024.md)。

## 研究问题与边界

验证BIRD dev只读SQLite schema能否生成确定性的FK Join-Instance身份，保留复合外键有序列对、同实例双向边以及同端点不同FK映射。该实验只检验结构序列化，不评估业务角色语义、JOIN选择、路径准确率、SQL EX或G-reasoner效果。BIRD dev是反复使用的开发诊断集，不是独立测试集。

## 预注册门槛

- Full覆盖11个SQLite schema，历史结构计数参照为103原始FK、100有效、3无效。
- 有效实例ID唯一；数据库/FK行枚举顺序和PRAGMA group id重编号不改变ID；复合列顺序变化会改变ID；每个有效FK有同ID的正向/逆向边。
- 先1数据库CPU smoke，通过后再扫描全量；预算CPU 1,800秒、RSS 16 GiB、线程数8、GPU/API/模型/SQL/依赖安装均为0。
- 任何历史分母差异记为INCONCLUSIVE，保留现场，不更改门槛；没有人工审阅，因此`human_review=0, trusted_role_label_n=0`。

## 结果

尚未完成BIRD数据Smoke/Full。协议已在GitHub commit `b3c60a2`预注册。启动前检查发现runner最初只查SQLite目录顶层；递归路径测试在任何BIRD数据读取前复现该问题，修正提交为`b2129583`，修正后9/9合约测试通过。首次Smoke命令`g2_fk_instance_quality_20261024_01_smoke_001`在shell层因宿主不存在`/usr/bin/time`退出127，runner未启动、无数据读取或结果文件；该失败保留独立日志。命令已修正，下一尝试使用新run ID `..._smoke_002`，完整预注册见配置。合约测试属于实现检查，不是BIRD实验结果。后续追加每个独立run状态、聚合指标、异常、哈希与结论。逐DB详情与运行日志留在本地私有目录。
