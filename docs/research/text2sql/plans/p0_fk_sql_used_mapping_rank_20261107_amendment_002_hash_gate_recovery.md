# Amendment 002：一次独立的输入哈希门恢复

**登记日期：2026-11-07。状态：预注册，尚未运行恢复。** 此补充只处理 CPU 首轮的输入指纹停止，不改变样本定义、标签、抽样、指标、模型、资源上限或成功门。

## 触发原因与证据

Run `p0_fk_sql_used_mapping_rank_20261107_cpu_001` 在解析任何数据前停止，回执原因为 `INPUT_HASH_MISMATCH_EXCLUSION_MANIFEST`。这个回执没有保存失败瞬间的实际哈希，因此无法确定当时的两个比较值。之后用独立 `sha256sum` 对同一路径复算，得到 `14d3e65e53bbc29c03d312fb32227c47b568242502d30bc3c4d4656b97521ed7`，与原预注册值相同；文件未修改，mtime 早于本实验。此次 CPU 首轮只读取了各冻结输入做 SHA-256，没有解析 JSON、读取问题/SQL 字段、生成样本、审阅包或模型输入。

## 唯一恢复规则

- 只允许一个新运行 ID：`p0_fk_sql_used_mapping_rank_20261107_cpu_002`，只写入新的 `cpu_002/` 目录；`cpu_001/` 失败回执和日志保留，不覆盖、不重跑。
- 恢复前先在本地独立确认原始 BIRD、schema、FK artifact、crosswalk、canonical Full 和 60-unit exclusion manifest 的 SHA-256 全部等于主配置原值；本次额外修订的 runner 在预解析阶段记录 expected/actual，并仅当全部相等时才开始读取数据。
- 恢复仍执行原来唯一的一次 CPU 全量 SQL/候选解析和同一个 30 Full 单元、至少 3 库容量门。Smoke/Full 拆分、SQLGlot 定义、目标生成、模型审阅和排名方案均不变。
- 任一 SHA 再次不一致、SQL 解析门失败或数据容量门不足，立即停止。此 amendment 不授权第二次恢复、换输入、重置 alias、改哈希、补样或加载任何模型。
- 若 CPU 容量门通过，才按原主计划及 Amendment 001 进入两个本地 reviewer 的 5-unit Smoke/Full 与 G-reasoner/Dense Smoke/Full。Model-proxy 仍是次要标签，不是人工真值；SQL-used 仍是主要目标。

## 记录与归档

- 原始失败：私有 `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_001/`；日志 `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_001.log`。
- 唯一恢复目标：私有 `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/cpu_002/`；独立日志 `.../cpu_002.log`。
- 运行前将本补充、配置及带 actual/expected 哈希回执的 runner 推送到用户拥有的 `bArtyom/gfm-rag` 分支，并读回验证；执行 commit/hash 记录在 CPU 回执。
- 本轮恢复仍不上传问题、SQL、schema 行、逐题身份、mapping ID、模型原文或本地运行日志。

## 2026-11-07 执行记录与更正

唯一恢复 `p0_fk_sql_used_mapping_rank_20261107_cpu_002` 已运行并按本 amendment 停止。CPU runner 在反序列化任何 JSON、读取问题/SQL 字段或构造样本之前，报告 exclusion manifest 哈希不匹配：冻结 expected 为 `14d3e65e53bbc29c03d312fb32227c47b568242502d30bc3c4d4656b97521ed7`，observed 为 `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`。独立 `sha256sum` 与失败回执的 observed 值相同。Recovery allowance 已用完；不再试运行、不更改输入或登记哈希，也不运行后续模型审阅与 GPU 排序。

**登记勘误：**本补充开头“独立 SHA-256 检查与原登记值相同”的记录，以及 Amendment 002 JSON `independent_check.observed_sha256`，错误地复写了 expected 值；它们不是正确的独立实测值。保留冻结配置以避免静默改写预注册，按 CPU_002 回执和本段公开更正解释。匿名执行结果见[报告](../reports/p0_fk_sql_used_mapping_rank_20261107_01/README.md)。
