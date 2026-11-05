# P0-BIRD-FK Hop Profile：高跳数结构可行性审计

**状态：预注册，CPU-only exploratory 结构审计；不使用模型，也不产生 Role / JOIN 方法准确率。** 该审计只回答：本地 BIRD dev 的声明 FK 图中是否有足够多、跨数据库分布的高跳数问题，适合将来作为路径检索实验的难度分层？

## 痛点与依据

- G0-02 的合成关系排序为 GFM 2/4、Dense cosine 4/4；G2 只证实关系输入会改变分数，干预后的 top-1 没变。因此尚未证明 GFM 会选对真实关系或长路径。
- BIRD dev 的 P2a.5 审计记录 1,428 个 `JOIN ON`，其中 204 个未匹配声明 FK；结构原因不代表 JOIN 语义错误，也说明只依据声明 FK 的路径覆盖可能有限。
- 最新公开工作将高跳数路径错误作为独立痛点。SchemaScope 报告 JHD 含 410 个由人工验证、按 1–6 跳分层的问题；其失败分析中错误 JOIN 路径占高跳数样本错误的 38%，漏表占 24%。论文报告 BIRD dev 中约 22% 问题达到 3 跳，但该工作页面/PDF没有给出可直接复用的 benchmark 仓库链接；截至本计划日期，JHD 数据与代码是否公开仍未核实。[SchemaScope (SURGeLLM 2026)](https://aclanthology.org/2026.surgellm-1.17/)
- 新颖性边界：SchemaGraphSQL 已用 FK 表图与 pathfinding 生成 JOIN 路径；Graph-Link 已将 schema linking 写为受结构约束的子图诱导。因此“用图找路径/连通子图”本身不作为创新主张。[SchemaGraphSQL (EACL 2026)](https://aclanthology.org/2026.findings-eacl.134/)、[Graph-Link (ICML 2026)](https://proceedings.mlr.press/v306/zhong26s.html)

这次只检查 BIRD 是否能支撑后续的难度分层，不能替代待完成的人工标签门，也不据结构路径推断正确业务语义。

## 研究问题与可证伪判据

**问题：** 在 BIRD dev 的 SQL 所引用表集合上，声明 FK 无向表图的精确最小 Steiner 树边数分布是什么？其中是否有至少 30 道可解析、FK 图连通且 hop≥3 的问题，且分布在至少 3 个数据库？

**筛选判据：** 只有当完整数据中同时有至少 30 道 `h≥3` 连通题、覆盖至少 3 个数据库时，才将 BIRD 视作可供一个小型高跳数结构检索 pilot 继续评估的候选数据源。该数字是实验资源筛选线，不是统计功效或方法有效性门槛。若未达到，则不在 BIRD dev 上提出高跳数方法实验；改为寻找有可审计数据许可与标签的公开评测资源。

**完整性门：** 1,534 道题与 11 个 schema 均须对齐；每题必须归入且只归入一个状态。SQL 表引用抽取成功率低于 95% 时，结果标记为 `INCOMPLETE`，不据以判断数据集是否支持高跳数实验。

## 定义与执行边界

- 输入只用本地 BIRD `dev.json`、`dev_tables.json`；哈希已冻结在 `configs/p0_bird_fk_hop_profile_20261105.yaml`。
- 对每条 SQL 用 SQLGlot 解析所有查询范围中的基础表引用；CTE 名称不算数据库基础表。不会把问题文本、Gold SQL 内容或逐题/数据库标识写入报告与聚合产物。
- 每个 schema 构成无向、无权、表级声明 FK 图；BIRD `foreign_keys` 里的列映射对先投影到表对，同一对表的多个 FK 映射在此结构统计中合并成一条表边。
- hop 定义为连接 SQL 涉及全部不同基础表的**精确最小 Steiner 树边数**，在 FK 图上用 Dreyfus–Wagner 子集动态规划计算；最多支持 12 个终端表。该定义与语义正确路径不同；图不连通、表名无法映射、SQL 解析失败、终端数超限分别记录。
- 只报告全局匿名聚合：状态计数、h 分布、h≥3/4 题量、覆盖数据库数与单库最大题数。不得导出题目 ID、数据库 ID、问题文本、SQL、逐题 hop 或输入数据。
- 只读 CPU 运行；最多 4 线程；不调用 GPU、模型、外部 API、SQL 执行或训练；不安装依赖、不下载/复制数据、不改模型/数据。

## 与本地既有方法的关系

本地 Text-to-SQL 知识库中的 EXP-129/130/131/132/136/137/138/139/140/142 已测试过显式 role-map oracle、词面/类型对齐、Qwen 角色生成、确定性图修补、采样候选 lattice 与动态 SQL gate；EXP-138/139/142 也显示 fresh synthetic split 上生成/修补路线弱于冻结 lexical planner。此次不是再生成 role map 或 SQL，而是用公开预训练 G-reasoner 给固定 FK mapping nodes 打分并做结构难度画像。问题相邻，**不主张新算法**；实验价值仅是检查 BIRD 数据难度覆盖，并在标签门通过后评估该 checkpoint 的排序迁移是否值得继续。

## 资源、预算与命令

- 使用现有 `think2sql_20260909` 环境的 Python 3.12.14 解释器与 SQLGlot 28.0.0（通过该环境的显式 prefix 调用，避免 shell 默认环境解析偏差）。
- 资源上限：4 CPU 线程；预期内存低于 4 GiB；单次最多 10 分钟；不使用 GPU。正式启动前重新检查 `nvidia-smi`、`free -h`、`nproc`、磁盘与输入哈希。
- 先 5 题 Smoke；5/5 均须能解析 SQL 并映射所有表引用，且分母/输出门通过后，执行一次完整 1,534 题审计。Full 至少 95% 解析成功才算完整画像；Smoke 与 Full 使用不同空结果目录和同一冻结配置，不覆盖旧文件。

```bash
conda run -p /root/miniconda3/envs/think2sql_20260909 python3.12 \
  scripts/text2sql/audit_bird_fk_hop_profile.py \
  --mode smoke --run-id p0_bird_fk_hop_profile_smoke_20261105_01 \
  --config configs/p0_bird_fk_hop_profile_20261105.yaml \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_01/smoke
```

Full 命令除 `--mode full`、`--run-id p0_bird_fk_hop_profile_full_20261105_01` 和 `/full` 结果目录外相同。

## 预期结论范围与停止条件

此审计最多决定“BIRD 的结构 hop 分层是否适合作为后续 pilot 的一项描述性切片”。它不评估 GFM、Dense、BM25 或 SQL EX，不解除两位审阅者标签门，不会仅凭 h≥3 数量启动新的 JOIN 方法实验。Full 完成后停止该审计，不追着分布重复切片或改阈值。

后续真实 FK 映射排序仍以双人独立审核及共识标签为前置。标签完成前不得计算 Role Accuracy、用 Gold 监督排序、比较预测 JOIN 或调方法参数。若筛选通过且标签门以后通过，最多在事先冻结的全体结果中补充按结构 hop 的探索性分层；不能据此宣称跨库泛化。

## 指导与来源

- 仓库指导：[`README.md`](../README.md)、[`experiment-roadmap.md`](../experiment-roadmap.md)、[`reproducibility-contract.md`](../reproducibility-contract.md)。
- 本地依据：[`G0-02`](../reports/g0_fk_instance_node_20261024_02/README.md)、[`G2`](../reports/g2_asymmetric_relation_20261024_01/README.md)、[`P2a.5`](../reports/p2a_5_error_audit_20261018_01/README.md)、[`P0 双人盲审报告`](../reports/p0_fk_disagreement_blind_review_20261105_01/README.md)。
