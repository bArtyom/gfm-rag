# Amendment 001：新增本地模型代理审阅（次要分析）

**登记时间：2026-11-07。状态：预注册、尚未读取新样本。** 本补充由用户明确要求“用模型来审阅”触发。它只增加独立的本地模型审阅及次要描述分析，不改变原方案的 SQL-used 主要标签、抽样、排名输入、主要指标、成功筛选门或停止条件。

## 问题与边界

在新 SQL-derived 候选样本上，两种本地模型是否能对问题给定的 FK mapping 候选形成可复核的一致代理判断？这些代理判断与参考 SQL 显式 `JOIN ON` 实际使用的完整 FK mapping 有何一致或分歧？若代理共识覆盖足够，冻结 G-reasoner 与共享向量 Dense 对该代理集合的排序表现如何？

模型审阅不是人工真值，不替代双人审阅，也不产生可信人工 Role 标签。SQL-used Mapping@1 仍是唯一主要排名指标；模型代理标签仅用于审阅一致率、与 SQL-used 的集合一致性及一个明确标记为 exploratory 的次要排序切片。模型提示、问题、候选列名及模型原始输出只留在权限受限的本地文件中。

## 审阅者与盲审材料

- Reviewer A：本地 `Qwen2.5-Coder-7B-Instruct`，统一入口 `/mnt/liansp3/sources/models/qwen25-coder-7b`；config SHA-256 `c0242402ad6a13b331ea320feea8c7e3776ffb7a4eff0757b9cd667e116d9a28`，四个权重分片 SHA-256 见冻结配置。
- Reviewer B：本地 `Qwen3-4B-Think2SQL`，统一入口 `/mnt/liansp3/sources/models/qwen3-4b-think2sql`，真实目录 `/mnt/liansp3/资源模型/Think2SQL/Qwen3-4B-1cfa9a7`；config SHA-256 `8ba006f74fecfaaeb392872a60f4a480e7ec9860153d2e1b769ec81f9a147f8a`，三个权重分片 SHA-256 见冻结配置。
- 两个 checkpoint 在彼此隔离的进程中审阅同一 question × 已给定 table pair × 全部有效 FK 候选。两份私有包使用相同候选 ID、不同的稳定候选顺序；模型只看到自然语言问题、表对和 FK 列映射，不看到 Gold SQL、SQL-used 目标、排名、图模型分数或另一个 reviewer 的输出。
- 使用已归档的固定 JSON 标签结构与提示代码 `scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py`；Reviewer B 关闭 thinking。贪心解码，最多生成 384 tokens；不改提示、不重试、不人工修补格式错误。
- A、B 的 decision 和 accepted mapping ID 集合完全相同、且双方 confidence 都至少为 2，才形成一个 **model-proxy consensus**。`cannot_determine`、格式错误或低置信度不形成可裁定标签。接受所有候选的共识不纳入可区分代理排序子集。

## 执行次序、预算与停止规则

1. CPU 准备阶段在模型审阅前创建 Smoke 5 题和 Full 余集；确认输入哈希、候选完整性、目标与候选身份分离、旧 60 题排除及 Full 数据门。两份模型包与 SQL 标签的私有交叉表权限为 0600。
2. 两位本地 reviewer 各运行一次 5 题 Smoke。每位均须得到 5/5 格式有效 JSON，且至少 4/5 在 decision 和 accepted-ID 集合上完全一致、双方 confidence≥2；否则停止该 reviewer 的 Full 审阅，不重试。
3. Smoke 通过后，每位 reviewer 对不含 Smoke 的 Full 余集各运行一次。Full 的输出覆盖不足或无效行保留为不可裁定，不替换题目、不补跑。
4. SQL-used 主排序照原计划执行，不依赖模型标签门。模型代理 Full 子集若不足 20 个可区分单位或少于 3 个数据库，只报告审阅覆盖/一致性，不对模型代理排序作方向性比较；满足时仍只作 exploratory 描述，不触发新实验。
5. 物理 GPU 固定为 0（A）和 1（B），串行执行，避免显存争抢；每个模型启动前记录 `nvidia-smi`、`free -h`、`nproc` 与磁盘余量。A/B 单次阶段上限分别为 GPU allocation 20/14 GiB、RSS 24 GiB、wall 1,800 s；每请求最多 384 输出 tokens。模型仅从本地加载，不下载、不安装依赖、不调用外部 API。
6. 实际 prompt/completion token 按每个请求写入 `/mnt/liansp3/.config/api-usage/usage.sqlite3`，provider 标为本地推理；本地 GPU 秒单列。外部 API 费用应为 USD/CNY 0；没有供应商账单时只报告“无外部 API 请求”，本地 GPU 时间不折算为零成本。

## 预先规定的报告字段

匿名公开报告仅写：两 reviewer 有效输出数、双方有效数、decision+映射集合精确一致数、双方置信度≥2 的共识数、共识中与 SQL-used target 完全集合/有交集/无交集数量、可区分代理单位数、匿名数据库覆盖、G-reasoner 与 Dense 的模型代理 Accepted@1/MRR（若容量足够）、token/GPU/墙钟成本，以及模型标签不等于人工真值的限制。不得上传逐题 ID、问题、库/表/列名、SQL、映射 ID、rank/score、模型原始输出或审阅理由。

## 产物与配置

- 冻结配置：[Amendment 001 JSON](../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_amendment_001_model_review.json)。
- 代码在任何新样本读取前与配置/本补充一起推送至用户拥有的 `bArtyom/gfm-rag` 分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 本地 packets、model outputs、交叉表、逐题排名与日志只写 `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/` 及 `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_01/`。
- 不覆盖原计划、原模型审阅结果或旧实验目录；每阶段使用独立 run ID 和输出子目录。
