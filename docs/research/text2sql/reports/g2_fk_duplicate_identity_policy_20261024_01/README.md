# FK完全重复约束身份策略探索

> **状态：已预注册 / NOT RUN；exploratory。** 本工作包来自[G2 FK Instance结构Gate的NO_GO](../g2_fk_instance_quality_20261024_01/README.md)，比较唯一Join映射与保留声明重数的两种表示。它不改变原Gate结果，不进入Relation-typed G0，也不声称真实查询语义收益。

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

尚未运行。Smoke与Full结果、失败案例、资源使用、局限和结论将在各自运行结束后补充；Smoke与Full使用不同run ID及独立输出目录。
