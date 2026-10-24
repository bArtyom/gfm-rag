# G2 FK Instance稳定编码质量Gate（2026-10-24）

> **状态：已预注册 / NOT RUN。** 依据 [G2非对称关系通道实验第6节](g2_asymmetric_relation_channel_identifiability_20261024.md)的CPU FK Instance质量Gate。项目归档仓库唯一指定为 [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，当前基点 `research/g2-asymmetric-relation-20261024@d234507c9c5678943e2c31fd22a6f3be86a2973f`。本Gate与G2模型前向分开，不改写G1/G2结论。

## 1. 研究问题与实验边界

**RQ：** 能否仅从BIRD dev冻结SQLite schema构造确定性的FK Join-Instance表示，并且保留复合列顺序、同一实例的双向边身份，以及同表对之间不同FK实例？

**核心假设：** 以`(dataset/database identity, source table, target table, ordered source→target column pairs)`为FK实例身份输入，按规范化JSON计算版本化SHA-256，可不依赖SQLite PRAGMA约束枚举ID、FK组枚举顺序或数据库文件枚举顺序；每个有效FK生成一对反向边并共用同一`instance_id`。不同列映射的同端点FK必须保持不同ID。

**可证伪条件：** 置换输入数据库/FK行顺序或只改变PRAGMA group id后产生不同ID；复合FK列被拆成独立实例或重排后仍产生相同ID；逆向边的实例ID不一致；不同列映射但同端点的FK发生ID冲突；完整数据扫描不能复现冻结的103/100/3结构计数。

**范围限制：** 本实验只验证结构序列化和身份稳定性。它不评估自然语言角色、JOIN选择、路径正确率、SQL EX或G-reasoner效果。BIRD dev曾被用于多轮开发实验，不能据此声称独立泛化。问题文本、Gold SQL、表数据与逐DB详情不得进入公开仓库。

## 2. 数据与冻结输入

- 数据集：本机统一入口`/mnt/liansp3/sources/datasets/bird/dev/dev_databases/`下的SQLite文件；只读连接，只查询`sqlite_master`、`PRAGMA table_info`和`PRAGMA foreign_key_list`，不扫描业务表行。
- 预期覆盖：11个dev数据库；历史P2a.5报告的SQLite FK结构计数为103个实例、100个端点/列结构有效、3个无效。该历史值仅作为精确复现参照；若与当前文件不匹配，报告INCONCLUSIVE并停止，不改门槛。
- 不读取`dev.json`、`dev.sql`、用户问题、Gold SQL、模型缓存或训练标签。
- 数据快照记录：schema-only摘要SHA-256、`dev_tables.json` SHA-256及数据库文件计数。公开报告仅留聚合hash，不上传DB路径、名称、DDL或逐实例ID。

## 3. 指标、基线与成功判据

**主要指标**：发现DB数；原始FK实例数；有效/无效实例数；复合FK实例数与组件数；同端点多FK表对数；稳定ID冲突数；双向边配对率；输入顺序/PRAGMA group id置换不变率；组件顺序敏感性。

**简单结构基线**：按source/target table对去重的朴素边数。它不是语义模型，而是展示朴素端点去重会丢失多少不同列映射实例。报告只写聚合差值，不使用查询标签。

**Gate PASS**需同时满足：

1. 覆盖11个SQLite数据库且复现103原始、100有效、3无效FK；否则INCONCLUSIVE并保留现场。
2. 所有有效实例均有非空、确定性ID；有效实例之间ID唯一；无不同结构被合并。
3. 规范化输出对数据库文件/FK行顺序及仅PRAGMA group id重编号不变；对复合FK组件顺序变化敏感。
4. 每个有效FK的有向边及逆向边数量为2，且共享同一个FK `instance_id`；反向列对在保留组件序号的条件下正确交换。
5. 复合约束作为一个实例保留所有有序列对；同端点不同列映射仍为不同实例ID。

成功只代表**结构编码Gate通过**，不代表角色标签可信或模型性能提升。

## 4. Smoke、预算与停止条件

- Smoke：固定文件名排序后的第一个SQLite数据库；验证只读schema扫描、输出格式、ID唯一性和边配对率。Smoke必须通过才运行全量。
- Full：固定扫描全部11个SQLite文件；单进程/单线程CPU，最多1,800 CPU秒、16 GiB RSS、8 CPU线程；GPU=0秒、外部API=0、模型加载/前向=0、SQL执行=0、依赖安装=0。
- 环境：复用已有`precisiongate_bird` conda环境中的Python 3.10标准库；使用该环境显式`python3.10`二进制，避免当前环境激活脚本将`python`错误解析到系统Python 3.9。不得修改/重建环境。
- 失败/停止：输入文件不足11个、只读连接失败、核心字段缺失、资源超预算、Smoke Gate失败或历史分母不匹配。失败产物单独留存；修正后使用新run ID及新目录。

## 5. 运行、代码与归档

- 实验ID：`g2_fk_instance_quality_20261024_01`；首次Smoke命令`..._smoke_001`在进入runner前因宿主缺少`/usr/bin/time`停止（0个BIRD文件被runner读取，未创建结果）；修正命令后新Smoke为`..._smoke_002`；Full为`..._full_001`。每个尝试保留独立run ID。
- 代码：`scripts/text2sql/fk_instance_quality_audit.py`；契约回归：`tests/test_fk_instance_quality_audit.py`。代码及协议须在首次Smoke之前提交到本仓库分支并通过GitHub内容回读。
- 私有结果根：`/mnt/liansp3/sources/results/gfmrag_g2_fk_instance_quality_20261024_01/`；日志：`/mnt/liansp3/logs/g2_fk_instance_quality_20261024_01/`。先确认目标不存在并创建独立目录。
- 固定命令以报告配置`run_commands`为准；runner自身采集wall/CPU/peak-RSS。宿主没有`/usr/bin/time`，故执行包装使用已存在的`/usr/bin/timeout`和`conda run`，不安装工具。
- 公开目录：`docs/research/text2sql/reports/g2_fk_instance_quality_20261024_01/`；只上传README、配置、脚本/测试和匿名聚合。任何DB名称、DDL、逐FK ID、表名、查询/Gold SQL、日志不公开。
- 本计划仅预注册，不含实测结果；实验结束后新增结果commit并校验GitHub分支、报告链接及文件内容。
