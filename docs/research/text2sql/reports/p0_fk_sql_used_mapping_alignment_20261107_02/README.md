# P0：冻结 FK 排序对参考 SQL 映射的配对复核（注册 02）

**状态：预注册完成，尚未运行。** 本文件为独立运行报告；执行结果将在对应阶段后补入。它不会覆盖注册 `_01` 的输入前失败报告。

## 注册信息

- 实验 ID：`p0_fk_sql_used_mapping_alignment_20261107_02`
- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)
- 分支：`research/p0-sql-used-proxy-alignment-20261107`
- 预注册依据：[`计划`](../../plans/p0_fk_sql_used_proxy_alignment_20261107_02.md)与[`配置`](../../../../../configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107_02.json)
- 代码：`scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment_20261107_02.py`
- 数据/评价目标：原 BIRD dev 冻结样本上的参考 SQL 显式 JOIN-ON 实际使用 mapping。它不是人工 Role 金标准。

## 核心问题与预算

检查同一 55 个非 Smoke 问题×表对的冻结 G-reasoner/Dense 排名，在参考 SQL-used mapping 标签上是否出现 G-reasoner 的预设正向信号。层级为 `exploratory_label_target_audit`。只运行一次 5 对 CPU Smoke；若所有门通过，再运行一次 55 对 CPU Full。不重试、不扩样、不改 parser 或评分。

## 执行记录

尚未启动。预注册推送确认后，运行前会再次检查资源、输入/代码版本、输出路径与 CPU 环境。实验调用本地模型 0 次、外部 API 0 次、GPU 0 张；不会产生模型 token 或 API 费用。
