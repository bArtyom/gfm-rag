# P2d.2：封存 SQL 失败根因归因

**状态：STOP；合成自检 10/10 通过；正式归因未运行。** 本运行因启动参数把 P2d.1 评测目录误作 P2d 准备包目录，在读取封存清单前收到 `FileNotFoundError`。没有读取私有样本内容，没有生成分析输出，也没有执行 SQL。失败回执见 [`attempt_001_status.json`](attempt_001_status.json)。路径修正后的单独登记运行见 [P2d.2 recovery `_02`](../p2d2_frozen_failure_attribution_20261105_02/README.md)。

## 研究问题

区分旧失败是“本臂 Schema 上下文缺少生成 SQL 所需字段”，还是“生成器引用了不存在/不可见字段、别名或作用域”；同时将 SQL parse failures 粗分为包装格式与语句结构问题。

## 预注册设计

- 只读静态检查 10 条 SQL parse failures。
- 对 18 条旧 `missing_column` 错误，在本地只读不可变 SQLite 快照上做一次 `EXPLAIN` 编译，不执行 SELECT、不读出查询结果。
- SQLite 原始错误中的字段名只在内存中使用，用于匹配 BIRD schema 与每臂已选节点；仅将匿名根因计数写盘。
- 成功标准、停止条件、匿名类别和下一步规则见同目录 `experiment_config.json` 与[预注册计划](../../plans/p2d2_frozen_failure_attribution_20261105.md)。上游已完成评测报告在 [P2d.1 commit `0f4a932`](https://github.com/bArtyom/gfm-rag/tree/0f4a932968f54b9c756e61f7b0ec910b93eefaac/docs/research/text2sql/reports/p2d_1_eval_audit_20261022_02)。

## 预运行结果

合成自检使用临时 SQLite fixture，验证解析错误粗分、标识符到 Schema 的映射、别名错误识别、危险表达式拦截与只读 `EXPLAIN` 缺列检测，共 10 项通过；没有读取私有输入，没有读取查询结果。该自检只确认运行器基本可用，不构成数据实验结果。正式启动尝试在定位准备清单时停止；其原因是传入的准备包目录不存在，准备包的本地资源别名归属于 P2d 结果，而 P2d.1 目录只存放评测结果。未更改科学假设、样本或失败分母。
