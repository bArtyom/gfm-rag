# P0：冻结 FK 排序对参考 SQL 映射的配对复核（独立注册 02）

**状态：Full 前预注册。** 实验 ID：`p0_fk_sql_used_mapping_alignment_20261107_02`。这是旧注册在输入读取前停止后的独立新注册，不是重试。

## 为什么另立注册

注册 `..._01` 的 Smoke 因运行准备提前创建受保护的 `smoke_001/` 结果目录，在读取输入前停止。旧报告确认本轮没有读 SQL、模型审阅、排名预测或标签，没有科学指标。旧注册不重跑；若仍需回答同一问题，旧报告要求建立不同注册。本方案使用新的实验 ID、run IDs、runner 文件、配置、结果根和日志根，并在运行前先推送预注册提交。

## 研究问题与核心假设

此前在三模型代理审阅集合上，冻结 G-reasoner 的 Mapping@1 为 7/38，Dense Cosine 为 27/38。该负向结果可能受代理标签与参考 SQL 选用关系不一致影响。本实验在**相同 55 个非 Smoke 问题×表对、候选集与冻结排名**上，改用原 BIRD dev 参考 SQL 显式 `JOIN ... ON` 实际使用的已声明 FK mapping 作为评价目标。

**核心假设：** 在 SQL 映射可完整解析的样本上，G-reasoner Mapping@1 比 Dense Cosine 至少高 5 个百分点、净救回至少 4 个单元，且至少两个各有不少于 5 个有效单元的匿名数据库净救回为正。

此标签只表示参考 SQL 明确使用的 mapping，不是人工 Role 真值，也不排除其他业务上等价或正确的 mapping。任务仍是在已知表对和冻结候选中的条件式排序，不是端到端 JOIN 发现、SQL EX 或跨库独立复现。

## 层级、预算、成功判据与停止条件

- 层级：单次 `exploratory_label_target_audit`，用于检查旧模型代理排序结论是否依赖标签目标。
- 预算：CPU Smoke 5 对；全部 Smoke 门通过后，运行一次 CPU Full 55 对。每阶段只运行一次，不重试、不补样、不改 parser、不调排名或扩展模型。
- Smoke 门：5/5 SQL 可解析；0 scope error；每题全部限定显式 JOIN-ON 等式可解析；至少 4/5 样本有完整映射且匹配冻结候选。
- Full 质量门：SQL parse 至少 54/55、0 scope error；至少 30 个题级完整解析且候选命中的样本，覆盖至少 3 个匿名数据库。质量门失败则归档停止，不计算排序分数。
- Primary：set-valued SQL-used Mapping@1。Secondary：Mapping@3、首个 SQL-used mapping 的 MRR、模型代理集合包含率和精确集合相等率；代理集合只作描述，不作为真值。
- 信号门：G-reasoner 至少 +5 pp、净救回至少 4，并且至少两个 `n≥5` 匿名库净救回为正；信号门未过即停止，不做新变体。
- 资源：CPU-only、最多 8 线程、600 秒 wall / 300 秒 process CPU / 4 GiB RSS；不加载模型、不调用 API、不用 GPU、不安装依赖。
- 运行前再次检查 `nvidia-smi`、`free -h`、`nproc`；输出目录叶子必须不存在，由 runner 创建。任何输入哈希、版本、候选对齐或资源门失败即停止并保留现场。

## 数据、方法与实现冻结

- 项目：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`；预注册源代码基线为本次预注册提交，运行使用随后固定的实现提交。
- 数据版本、样本、Smoke/Full split、候选映射、排名和审阅输出与 `_01` 相同；所有逐题输入 hash 继续由配置冻结。样本不能因审阅结果或排名变化而替换。
- Parser：SQLGlot 28.0.0，SQLite dialect；只取同一显式 JOIN-ON 内、同 alias pair 的限定跨表列等式。复合 FK 必须所有有序列对都出现。忽略 WHERE、USING 及未解析列/alias。
- 不在 Smoke 里读 reviewer 原文或排名；Full 只将三模型代理集合用于描述性 SQL inclusion / exact-set 指标，主排序比较使用参考 SQL-used mapping。
- Runner：`scripts/text2sql/audit_p0_fk_sql_used_mapping_alignment_20261107_02.py`。相对 `_01` 仅增加独立 ID、唯一输出 run IDs 和 runner/config 路径；解析与统计定义冻结不变。
- 配置：`configs/text2sql/p0_fk_sql_used_mapping_alignment_20261107_02.json`。
- 私有结果：`/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_02/`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_alignment_20261107_02/`。公开只保留匿名聚合，不提交 SQL、问题、表名、逐题预测或模型输出。

## 复现与指导依据

实验前复核了目标仓库 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md` 和 `reproducibility-contract.md`，并检查实验室 `/mnt/liansp3/AGENTS.md` 与 `/mnt/liansp3/sources.md`。遵循仓库的 CPU Smoke/Full、独立报告目录、数据隐私和匿名聚合要求。与原 `_01` 的差异仅为新的完整注册以回答尚无科学结果的问题；旧失败和旧输出不覆盖。

## 结果

运行记录待 Smoke 完成后追加到该实验的独立报告目录；本计划在运行前登记并单独保留。
