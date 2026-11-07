# Amendment 002：SQL-used ranker 计数契约恢复

**状态：预注册，未运行。** 本 amendment 只恢复此前在导入 PyTorch、加载模型或计算分数之前因 SELECTED_UNIT_COUNT_MISMATCH 停止的主排序 Smoke。原失败运行 ID 不复用；模型审阅 Full 仍按原门停止。

## 为什么恢复

独立实验报告已确认：CPU 数据门通过，固定样本为 5 个 Smoke、108 个 Full、4 个匿名数据库；SQL-used 目标均来自参考 SQL 中显式 JOIN ON 的完整 mapping。排序 Smoke 中断的原因是 manifest 保存了 smoke_unit_ids 和 full_unit_ids，但不含运行器额外要求的计数字段。此次只在 count 字段缺失时按对应 ID 列表长度校验；拒绝重复 ID，并同时要求数量等于已报告的 5/108。

用户选择本地模型审阅后，A/B 两位本地 Qwen 各自 Smoke 输出 5/5 有效，但高置信精确一致仅 2/5，低于 4/5 门槛，因此审阅 Full 已停止。此代理审阅是次要分析；主排序的标签由预先冻结的 SQL-used 抽取规则产生，不依赖模型或人工审阅标签。SQL-derived 目标不进入模型输入。

## 保持冻结的内容

- 不重新抽样、不重新准备或更改问题×表对、候选、SQL-derived 标签、模型权重、Embedding、图结构、seed、指标、阈值或停止规则。
- 不执行 SQL，不训练、不调参、不安装依赖、不调用外部 API。
- 不重放原失败的 smoke_001。新的运行身份见 frozen config。
- Smoke 通过后才运行一次 Full；Smoke 失败则本 amendment 终止。
- 不运行模型审阅 Full，不将模型输出视作人工 Role 金标准。

## 验收和停机

Smoke 必须对 5 个预选单元的所有候选生成有限的 Dense 与 G-reasoner 分数，并保持候选完整。随后 Full 一次处理原冻结的 108 个单元。保留原主筛选条件：G-reasoner−Dense 的 SQL-used Mapping@1 至少 +5pp、配对净救回至少 4，且至少两个各有 n≥5 的匿名数据库净救回为正。该正向筛选仍只够进入独立留出评估，不构成论文主张。

两阶段沿用已有 GPU/RSS/wall/CPU 上限。启动前重新执行硬件、环境、模型指纹和输入哈希检查。所有输出进入 amendment 专属私有目录；结果只匿名汇总到用户维护的 bArtyom/gfm-rag。

## 版本及文件

- 基础实验：p0_fk_sql_used_mapping_rank_20261107_03。
- 基础配置 SHA-256：d965ee4f5250193f5fd3a53d82c59a55ca95c97c9bb0980008d4a907c27b9db4。
- CPU 样本的来源提交：566b8e2d9bb244d8868372ae39c887de02f703e9；运行时仍校验 CPU summary 中保存的 manifest SHA。
- 运行器仅增加对原配置和本 amendment 配置的识别、计数数组回退以及准备提交与评分提交分离校验；排序代码和评分实现不变。
- 冻结配置：configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002.json。
- 新报告目录：docs/research/text2sql/reports/p0_fk_sql_used_mapping_rank_20261107_03_amendment_002/。
