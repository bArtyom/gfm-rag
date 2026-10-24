# FK完全重复约束的身份策略探索（2026-10-24）

> **状态：已预注册 / NOT RUN；类别：exploratory CPU representation audit。** 来源是[G2 FK Instance稳定编码Gate的NO_GO结果](../reports/g2_fk_instance_quality_20261024_01/README.md)：11库计数103/100/3符合历史值，但两个有效约束声明规范化后具有相同的完整FK结构键。本探索不改写原Gate、不撤销NO_GO，也不启动Relation-typed G0。

## 问题、假设与范围

**研究问题：** 当两个不同SQLite FK声明具有完全相同的数据库、源表、目标表和有序列对时，结构编码能否支持两种不同而可复现的语义：

1. **Mapping identity：** 相同结构是同一个可连接映射；将完全重复声明合为一个映射ID，另存声明重数，每个唯一映射生成一对正反向边。
2. **Declaration multiset identity：** 保留每个声明；对相同结构使用出现序号生成不同ID，保留每个声明的边重数。ID集合可保持稳定，但需测量出现序号是否能稳定绑定到具体PRAGMA约束组。

**核心假设：** 两种策略都可在FK行枚举顺序和PRAGMA组号重编号下得到稳定的映射/ID集合；mapping策略会将相同映射作为一个边实例并保留重数，multiset策略会产生唯一的声明ID，但对结构完全相同的声明无法保证“哪个原组号对应哪个序号”在重编号后稳定。这个区别可能决定FK实例如何进入G0图，因此结果能改变原Gate后续工程决策。

本轮只评估身份/边表示。不得将任何策略描述为业务角色真值；不读取问题、Gold SQL或业务表行；不做人工标签、不执行SQL、不加载模型、不调用外部模型API。

## 数据与方法

- 输入固定为`/mnt/liansp3/sources/datasets/bird/dev/dev_databases`的只读SQLite schema；使用`sqlite_master`、`PRAGMA table_info`、`PRAGMA foreign_key_list`。以原Gate冻结的`dev_tables.json` hash和11库结构计数检查输入连续性。
- 首先跑一个数据库smoke，并用内存合成fixture覆盖：两条完全重复FK、同端点但列映射不同的FK、以及一个复合FK。通过后才扫描全部11库。
- 对每个数据库分别构造mapping ID和声明multiset ID。检验FK行反序、数据库列表反序、PRAGMA约束组号反向重编号；对完全相同约束，同时记录ID集合稳定性与组号到序号绑定稳定性。
- mapping策略必须合并且仅合并结构完全相同的有效映射；保留原始声明数/重复重数；不同列映射仍分开；每个唯一映射一对反向边。
- multiset策略必须为每个有效声明分配唯一ID；不同ID分别配成正反向边；重复映射的ID多重集合对重排/重编号稳定。不得把不稳定的重复组号关联宣称为可稳定追踪的物理声明身份。

## 成功判据、预算和停止条件

**技术完成判据：**（a）复现11库、103原始/100有效/3无效；（b）真实完全重复有效映射数与原Gate确认的1组一致；（c）两策略分别通过其预期结构/顺序/边配对检查；（d）明确报告声明序号与PRAGMA组的关联是否在重编号后变化。任何结构分母改变则记`INCONCLUSIVE`，不调门槛。

预算：CPU最多300秒、进程RSS最多2 GiB、单线程；GPU/API/模型/SQL/人工审核/依赖安装均为0。使用既有`precisiongate_bird` Python 3.10.21标准库。

**停止条件：** smoke任一断言失败；11库计数或历史FK分母不符；只读schema读取失败；超预算。结果只回答表示策略性质，不自动选定哪种语义，也不直接开放G0。

## 预注册实现与产物

- 运行器：`scripts/text2sql/fk_duplicate_identity_policy_audit.py`；策略与合成fixture检查在smoke内执行。
- Smoke：`g2_fk_duplicate_identity_policy_20261024_01_smoke_001`；Full：`g2_fk_duplicate_identity_policy_20261024_01_full_001`。命令/路径见同目录`experiment_config.json`。
- 私有结果：`/mnt/liansp3/sources/results/gfmrag_g2_fk_duplicate_identity_policy_20261024_01/`；私有日志：`/mnt/liansp3/logs/g2_fk_duplicate_identity_policy_20261024_01/`。
- 公开报告：`docs/research/text2sql/reports/g2_fk_duplicate_identity_policy_20261024_01/README.md`。不公开数据库名称、DDL、逐实例ID、运行日志或任何查询内容。
- 在第一次Smoke之前，协议、配置、运行器和更新后的研究决策必须提交到`bArtyom/gfm-rag`并逐文件回读确认。
