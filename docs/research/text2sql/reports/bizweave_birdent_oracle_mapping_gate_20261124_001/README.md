# BizWeave：BIRD-Ent 文档到 Schema 映射可行性 Gate

- **Run ID：** `bizweave_birdent_oracle_mapping_gate_20261124_001`
- **日期：** 2026-11-24 UTC
- **状态：** 探索性 Gate 通过；允许进入下一阶段的小规模人工标注 pilot。
- **结论边界：** 本实验验证数据和 Oracle 上界是否值得继续研究，不验证自动构图能力、跨数据集泛化、论文新颖性或 Text-to-SQL 执行收益。

## 核心结果

- 5/5 个不同数据资产的样本，都能从业务知识文档中找到至少一条带原文跨度、可落到已有 Schema 列的直接映射。盲审记录 30 条 MappingAssertion：23 条直接支持，7 条冲突、拟议新增或未决；合计形成 26 条 Claim→Column 边。
- SQL 派生标签共得到 15 个唯一 Gold 列，15 个均可解析并映射到当前数据库 Schema；没有列标签被静默剔除。
- 在相同的任务数据库列候选全集、相同 K=10 下，FlatDocBM25 的宏平均 Column Recall@10 为 **0.6600**，OracleBizWeave 为 **0.7467**，绝对差 **+0.0867**；Oracle 在 **2/5** 个样本提升、2/5 持平、1/5 下降，刚好达到预注册成功线。
- Macro MRR 为 **0.5500 → 1.0000**。Table Recall@5 两臂均为 **1.0000**，在本次小型数据库上已饱和，不能作为有效区分证据。

**判断：GO，但只进入 30–50 条的独立探索性人工审核 pilot。** 这轮 Gate 只说明有字段级证据，且理想映射有机会改变列排序。映射是 AI 助手人工式审阅结果，不是独立人类标签；Oracle 直接使用人工核验映射，属于有利于 BizWeave 的上界，不能据此声称自动构图有效。

## 研究问题和预注册假设

问题：BIRD-Ent 的业务知识文档是否包含可引用到物理表列的业务断言；如果把正确的 Claim→Column 映射作为 Oracle 图，能否在同一问题、同一文档来源、同一 Schema 候选全集与 K 下，比文档增强的扁平检索找回更多 Gold 列？

主假设是：有原文证据支持的 Business–Schema 映射边可能帮助召回必要列。Oracle 映射由审阅者提供，实验不估计模型能否自动抽取这些映射。预注册门槛为 5 个样本中至少 3 个存在非平凡字段级映射；通过后运行检索对照；Oracle Recall@10 至少在 2/5 个样本提升才进入下一轮。

预注册与修订文件：

- [实验计划](../../plans/bizweave_birdent_oracle_mapping_gate_20261124_001.md)
- [Gold 列标签修订](../../plans/bizweave_birdent_oracle_mapping_gate_20261124_001_amendment_001.md)
- [冻结配置](../../../../../configs/text2sql/bizweave_birdent_oracle_mapping_gate_20261124_001.json)
- [评测修订配置](../../../../../configs/text2sql/bizweave_birdent_oracle_mapping_gate_20261124_001_amendment_001.json)

## 数据、采样与证据边界

使用 Hugging Face `jjjycaptain/BIRD-Spider-Ent` 固定 revision `cde16ccf0eb606585642d6b06209760d73fd28dc`，数据集许可标注为 CC-BY-SA-4.0。只取 task、Schema/data asset、knowledge document、NOTICE、license 和评测名称映射；未下载数据库，也不执行 SQL。数据集包含 1,534 道 BIRD-Ent 问题、7 个 data-asset 域和 1,412 份约 150 万 tokens 的知识文档。数据卡说明 BIRD-Ent 的知识文档由其知识解耦和文档生成流程构造，因此这些结果不能当作真实企业内部文档上的验证。[数据集卡与固定版本](https://huggingface.co/datasets/jjjycaptain/BIRD-Spider-Ent/tree/cde16ccf0eb606585642d6b06209760d73fd28dc)，[正式论文](https://aclanthology.org/2026.findings-emnlp.1971/)。

按预注册顺序，从含非空 `gold_knowledge_ids` 的任务中选取每个 data asset 的第一条样本，最多 5 条。本次为 5 个不同资产、5 个任务、9 份关联文档。评分候选范围按任务对应的 `eval_db` 限制为该数据库的 3–8 张表、12–124 个物理列，而不是整个 data-asset 目录。

映射审阅时只看相关知识文档与 Schema/列说明，不看问题文本、Gold SQL、Gold table ID 或其他答案。映射 JSON 在审阅完成后冻结，SHA-256 为 `ffd47bdebf172c4ed460c16f7a68f733ed70e5785c2fca63c0c6af9f9afb8934`。之后才公开评分阶段使用 `gold_table_ids`、Gold SQL 和固定版本的 table/column name mappings。名称映射仅用于把 SQL 引用列转成 Ent Schema 列标签，不进入候选特征或图构建。

**标注限制：**映射由当前 AI 助手依据明确文本跨度审阅。它们是可供人复核的候选标注，不是独立人类金标；本轮没有双人一致性、专家裁决或业务组织验证。逐样本映射、问题、Gold SQL、文档全文和日志仅保存在本地受控目录，未公开。

## 对照方法

共同设置：每个任务使用同一数据库的全部物理列、同一 K、稳定的列 ID 字典序 tie-break。列候选文本只包含企业版表名、列名和 SQL 类型；排除 DDL 示例值。BM25 固定 `k1=1.5, b=0.75`，查询词取去重后的 lowercase alphanumeric tokens，并拆分 snake_case/CamelCase。

1. **FlatDocBM25：**将问题与 `gold_knowledge_ids` 对应的完整文档拼成查询，对 Schema 列候选做 BM25。
2. **OracleBizWeave：**将冻结的 Claim 摘要和对应原文跨度作为 Claim 节点，只用问题对 Claim 做 BM25。得分大于零的 Claim 才把分数传播到直接映射列；没有问题词项匹配的边不获得检索加分。其余候选按问题到 Schema 列的 BM25 补位。多个 Claim 命中同一列时取最高得分。

两臂使用同一来源的信息，但 Oracle 拥有由审阅者提供的结构化 Claim 和正确映射，属于上界。另一个重要条件是两臂均拿到 Gold 关联文档；这是 `gold_knowledge_ids` 条件式 Oracle 文档检索，**不测文档检索器能否找对文档**。

Table Recall@5 的预注册没有单独定义列分数如何聚合成表分数；本次按每张表最早出现的列排名生成表排名，表 ID 用字典序打破平局。该次级指标两臂均饱和且不参与成功门判断。

SQLGlot `30.12.0` 仅解析 Gold SQL 产生列标签，不执行 SQL。对未限定列及单表查询中的未知别名，只有在任务 SQL 唯一源表规则能确定映射时才采用该表；否则标签列入未决分母。本次 15/15 个唯一 Gold 列都可解析、映射，未决为 0。评分前校验冻结映射 SHA-256。

## 聚合结果

| 指标（5 个任务宏平均） | FlatDocBM25 | OracleBizWeave | 差值 |
|---|---:|---:|---:|
| Column Recall@10 | 0.6600 | 0.7467 | +0.0867 |
| MRR（首个 Gold 列） | 0.5500 | 1.0000 | +0.4500 |
| Table Recall@5 | 1.0000 | 1.0000 | 0.0000 |

Column Recall@10 的配对方向为 Oracle 更好 2 题、相同 2 题、更差 1 题。样本只有 5 个，没有做显著性检验或置信区间；宏平均差值是方向筛选信号，不是稳定收益估计。Table Recall@5 两臂都为 100%，且每库表数最多 8，指标有明显饱和。

匿名聚合也保存在 [aggregate.public.json](aggregate.public.json)。

## 资源、环境与复现

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/bizweave-event-constraints-20261117`。预注册和评测 amendment 已在读取 Gold 标签前归档到该自有仓库。
- 运行起始本地代码版本：`0d9ecd98493f0740e6037292766dbd66a60f2fa9`。数据 revision 与上述 SHA 固定；盲审文件 SHA 如上。
- 环境：conda `qes_rear_refine`，Python 3.9.20，SQLGlot 30.12.0；没有安装或升级依赖。
- CPU-only 单进程，线程环境变量设为 1；运行器约 0.112 秒，最大 RSS 47,960 KiB。没有使用 GPU、Qwen、模型 API 或 SQL 执行。实验运行器的 token/API 费用为 CNY 0；CPU 资源未折算费用。
- 计分脚本 SHA-256：`3e5d6fb80c56060dfe18c8212bd15a2f292abdd729d52e07913a7c6dc1dcf87c`。选样脚本：`e78c5f7092197f287ac8653e9c6493e311f09690c798c577da933042f0712c89`；标签准备脚本：`137f25524db3e8a4e6f63298752e3b1d1cc6a5927cb94f1ac83c7281b61e7c95`。脚本位于 [`scripts/research/bizweave_birdent_oracle_mapping_gate_20261124_001/`](../../../../../scripts/research/bizweave_birdent_oracle_mapping_gate_20261124_001/)。

```bash
conda run -n qes_rear_refine python3 scripts/research/bizweave_birdent_oracle_mapping_gate_20261124_001/select_samples.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird_ent_public_20261124_001/BIRD-Ent \
  --output /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/selected_samples.private.json
```

映射审阅完成后，先用 `prepare_scoring_metadata.py` 校验盲审文件 SHA 并准备本地私有标签元数据，再运行冻结评分器：

```bash
conda run -n qes_rear_refine python3 scripts/research/bizweave_birdent_oracle_mapping_gate_20261124_001/prepare_scoring_metadata.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird_ent_public_20261124_001/BIRD-Ent \
  --selection-manifest /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/selected_samples.private.json \
  --frozen-mapping /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/oracle_mappings.private.json \
  --expected-mapping-sha256 ffd47bdebf172c4ed460c16f7a68f733ed70e5785c2fca63c0c6af9f9afb8934 \
  --output /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/selected_scoring_metadata.private.json

timeout 900s env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  conda run -n qes_rear_refine python3 scripts/research/bizweave_birdent_oracle_mapping_gate_20261124_001/score_gate.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird_ent_public_20261124_001/BIRD-Ent \
  --result-root /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001 \
  --output /mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/retrieval_scores.private.json \
  --expected-mapping-sha256 ffd47bdebf172c4ed460c16f7a68f733ed70e5785c2fca63c0c6af9f9afb8934
```

精确数值需要本地冻结的逐样本映射和评分元数据。它们依照预注册隐私边界未上传；公开仓库提供协议、代码和匿名聚合，不会泄露这些逐样本材料。重复运行时使用新的独立结果目录和新输出名；脚本采用独占创建，避免覆盖旧产物。

### 运行异常记录

前期三次评分启动分别遇到系统缺少 `/usr/bin/time`、文档文件实际为 ID→文本字典而非记录数组、以及数据资产中个别无关 DDL 不能由 SQLGlot 解析。上述尝试均在评分结果写入前停止且单独保留日志。最终运行器以标准库逐行读取 Schema 列声明，Gold SQL 仍使用 SQLGlot；最终评分文件由版本化脚本执行并通过冻结映射 SHA 校验。曾保留一份临时排序结果；复核发现零 BM25 匹配的已映射列被错误放在候选前面，未作为最终结果。最终结果只采用“问题检索到 Claim 后才传播映射分数”的修正版，结果文件 `retrieval_scores_005.private.json`。

## 结论与下一步

这组样本支持两个有限判断：

1. BIRD-Ent 文档里确实能找到可引用到物理列的字段级说明，因此可用来试验 Business–Schema 映射；
2. 在正确映射的 Oracle 条件下，Column Recall@10 达到预注册的继续门槛，但结果有提升、持平和损害案例。

因此可登记下一步 30–50 条探索性人工标注 pilot，优先让独立标注者复核跨度、列目标、冲突/未决状态，并加入低词面重合和多字段依赖样本。之后再测试模型自动提取和图结构是否优于同文档的扁平检索与描述增强 Schema baseline。当前结果没有确认论文新颖性；也没有证明模型能自动建图或改善端到端 SQL。相关工作边界及 idea 定义见 [BizWeave idea](../../ideas/bizweave.md)。
