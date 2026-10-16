# P1.5：列检索错误、预算饱和与 FK 实例诊断

- **实验日期：** 2026-10-16
- **实验 ID：** `p1_5_diagnosis_20261016`
- **最终运行：** `p1_5_diag_full_20261016_03`
- **状态：** 诊断运行完成；严格逐题复现门未通过；P2a 未运行。
- **证据范围：** BIRD dev 开发集，只作 exploratory 诊断，不是独立泛化或端到端 Text2SQL 证据。

## 研究问题与预注册门槛

本轮按 [P1.5 执行指导](../../plans/p1_5_diagnostics_and_p2a_20261016.md) 检查：历史列检索错误是否出现在非饱和候选集、Gold 排名与 token 预算如何共同影响覆盖，以及 SQLite/BIRD 外键实例是否足以支持之后的 Join Role/Path 实验。

- **核心假设：** 固定 1,024 维编码、候选文本和数据后，可以复核历史排名结果，并量化各库的候选饱和、Gold rank、预算可行性与 FK 质量。
- **实验层级：** 主线之外的离线诊断；不训练模型，不执行生成 SQL。
- **预算：** 1 次 CPU 输入/FK 预检、5 题 smoke、1 次全量 1,534 题的 1,024 维前向；同一前向的 512 前缀用于配对诊断。GPU wall 上限 900 秒、CPU 1,800 秒、最多 8 线程、RSS 16 GiB。
- **成功判据：** 固定输入及代码哈希通过，smoke 输出有效，且历史 512/1,024 维逐题 hit 数与 2,048 token 完整覆盖标记完全相同；同时输出逐库饱和、预算、rank、错误特征和 FK 汇总。
- **停止条件：** 任一冻结哈希不符、资源越界、smoke 失败或历史逐题指标不一致。最后一项触发严格复现门失败，因此没有启动 P2a。

## 仓库指南、来源与实现

项目工作仓库是 [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，运行前同步到 `main` 的基线 commit `1d3a05773cd4305fdd591e6bd729a03e22326e8c`，许可证为 Apache-2.0。执行前阅读了仓库根 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 和本轮 P1.5 指导。README 中的原始流程面向完整 GFM-RAG 训练/QA，要求 Python 3.12、CUDA 12+ 及项目依赖；本轮按 P1.5 指导仅调用官方文本编码器，复用已有环境，不运行完整训练/QA，也不安装整套依赖。普通包导入所需的 `torch_geometric` 在环境中缺失，因此运行器用选择性导入加载未修改的官方 encoder/base 文件。实际编码器来自上游 `RManLuo/gfm-rag` commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；官方 `Qwen3TextEmbModel` 与基类文件哈希分别为 `4515c5d6c586ad8ef63dc00b7ba6e70eac4496ce47e0a71c3988b81899c704a0` 和 `bdf97e695add03d00978eaedc64dcd76647b8e3cf5d662b7491ddb65ec404328`。官方源文件未修改，未把实验报告写入第三方上游仓库。

新增诊断入口为 [`scripts/text2sql/run_p1_5_diagnostics.py`](../../../../../scripts/text2sql/run_p1_5_diagnostics.py)，SHA-256：`af59d01d22a6b5d5538231b38c2bf52e0355a9193a5773f40b14d29470ec40cf`。脚本复用已归档的 P1 输入/候选文本构造逻辑，记录稳定的 type-first 候选文本哈希；只编码 1,024 维，再对 512/1,024 前缀分别 L2 归一化，以精确 cosine 和稳定降序排序。Gold 标签只用于计分；Gold SQL 仅用于离线解析显式 JOIN 条件与 FK 的覆盖关系，不进入候选文本或检索排序。

## 数据、模型与执行环境

- **数据：** BIRD dev，1,534 题、11 个数据库；873 个节点（75 表、798 列）。所有题有表标签；1,460 题有可评列标签，6,523 个 Gold 列元素。其余 74 题不参与列指标。
- **74 题排除原因：** 冻结的 P0 列引用审计在 74 题中记录到 145 个未解析引用：`missing_column` 21、`unknown_qualifier` 40、`ambiguous_unqualified` 84。1,534 题均至少有一个可解析 Gold 列；这 74 题另含未解析引用，因此整题不进入列指标分母。逐库排除数见下方“每库候选、饱和与 1024 维结果”表。
- **冻结哈希：** `dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；P0 审计 `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`；Gold 标签 `1b501810f0247999de1210fc807f3c39e60c2fab498cd104f8eb60f815269525`；模型文件清单 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`。86 个输入文件、约 1.493 GB 逐文件校验通过；75 个描述 CSV 中 71 个按 `utf-8-sig`、4 个按 `cp1252` 读取，未改写源文件。
- **模型：** 本地 `Qwen3-Embedding-0.6B`，1024 维输出；模型权重 SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`。查询指令为 “Given a natural-language question about a database, retrieve the relevant tables and columns.”
- **候选文本：** 75 表、798 列；表节点包含表名及原始列名，列节点包含表/列名、类型及非空的 description/format/values。全量 type-first 序列化哈希为 `b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a`。节点总长 27,506 tokenizer tokens；节点长度 p50=23、p95=71、最大 498。tokenizer 为 `Qwen2TokenizerFast`。
- **历史文本指纹限制：** 旧 P1 full-run 记录的 schema 文本哈希是 `2089cf5c7d10aa4056c98a19edca44a3fa0bfa17e2c1f0593848f7c935d4f226`，但未保存节点排序和哈希序列化规则，故不能证明与本轮 full text 逐字同序。本轮冻结数据哈希、节点数、候选定义和旧代码来源均已核对，并保留了本轮确定性文本哈希。
- **环境：** `think2sql_20260909`；Python 3.12.14、PyTorch 2.8.0、vLLM 0.10.2、Transformers 4.57.1、NumPy 2.2.6、SQLGlot 28.0.0。未安装依赖、下载模型或升级核心包。
- **资源：** 运行前 GPU 1 为 NVIDIA RTX 4090，641/24,564 MiB 已占用、利用率 0%；主机 192 CPU 线程，进程限 8 线程。全量 GPU wall（模型加载及编码）27.01 秒、总 elapsed wall 54.23 秒、CPU 21.44 秒、峰值 RSS 2.27 GiB，均未超预算。未使用 API、训练或 SQL 执行；没有随机采样，随机种子不适用。

最终全量运行记录的入口参数如下；`--output-dir` 指向独立本地目录，不覆盖既有 P1 结果：

```bash
/root/miniconda3/envs/think2sql_20260909/bin/python3 \
  scripts/text2sql/run_p1_5_diagnostics.py \
  --mode full \
  --run-id p1_5_diag_full_20261016_03 \
  --output-dir /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p1_5_diagnosis_20261016/full_03 \
  --legacy-root /mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014 \
  --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
  --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
  --previous-run-dir /mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014/results/p1/gfmrag_official_full1534_20261014_01
```

5 题/1 库 smoke 最终版本通过，向量有限且 rank/budget 输出有效；模型加载及编码 GPU wall 22.61 秒。实际因诊断代码错误重复了预检、smoke 和全量尝试；每次都使用独立输出目录并保留失败记录。`preflight_01` 的候选节点顺序检查错误、`preflight_02` 对 SQLite 隐式父键的判断错误、`smoke_01` 将未编码占位向量纳入范数检查、`full_01` 在 hit-map 的整数/字符串键转换处失败、`full_02` 未排除 74 道列标签不可评题。修正后 `smoke_02`、最终代码版本 `smoke_03` 均通过，`full_03` 完整结束。以上均是执行器/汇总代码错误，不是输入哈希或模型文件失败；没有覆盖历史结果，退出的 vLLM 进程已释放 GPU。

## 主要结果

以下 Recall/MRR/MAP 均为逐题宏平均；Table 分母 1,534，Column 和 combined token budget 分母 1,460。预算排序为 table/column 候选合并后的同一稳定 cosine 顺序，完整率要求全部 Gold 表列均被纳入。

| 前缀维度 | Table R@5 | Table R@10 | Column R@5 | Column R@10 | Column R@20 | Column MRR | Column MAP | 完整表列@2048 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 | 94.81% | 99.88% | 51.53% | 67.31% | 78.80% | 81.12% | 53.80% | 78.90% |
| 1024 | 94.77% | 99.93% | 52.93% | 68.06% | 79.16% | 82.78% | 55.28% | 79.59% |

### Token budget 曲线

| 前缀维度 | Token 预算 | Gold 元素 Recall | Precision | 完整表列问题率 | 平均返回节点 | 平均已用 tokens | Gold 元素/1,000 tokens |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 | 512 | 70.38% | 25.93% | 35.14% | 17.00 | 505.5 | 8.42 |
| 512 | 1024 | 82.20% | 18.09% | 56.03% | 30.62 | 949.5 | 5.37 |
| 512 | 2048 | 91.87% | 13.15% | 78.90% | 55.00 | 1709.5 | 3.41 |
| 1024 | 512 | 70.49% | 25.89% | 35.48% | 17.02 | 505.6 | 8.43 |
| 1024 | 1024 | 82.40% | 18.21% | 56.44% | 30.35 | 949.5 | 5.38 |
| 1024 | 2048 | 92.09% | 13.21% | 79.59% | 54.73 | 1709.4 | 3.41 |

预算 Precision 是检索到的 Gold 元素数除以总检索节点数；token efficiency 是所有可评问题中 Gold 命中总数除以实际使用 passage tokens 总数，再乘 1,000（micro 聚合）。

### Type-specific Precision@K

Precision@K 采用 runner 定义 `hits / K`；按题宏平均与按数据库宏平均均列出。对候选数小于 K 的库，未返回位置按未命中计入，因此应结合前述 Top-K 饱和结果解读。

| 前缀维度 | Table P@5（题宏/库宏） | Table P@10（题宏/库宏） | Column P@5（题宏/库宏） | Column P@10（题宏/库宏） | Column P@20（题宏/库宏） |
|---:|---:|---:|---:|---:|---:|
| 512 | 36.18% / 36.66% | 19.37% / 19.56% | 41.27% / 42.41% | 27.86% / 28.42% | 16.80% / 17.17% |
| 1024 | 36.15% / 36.63% | 19.39% / 19.57% | 42.42% / 43.36% | 28.13% / 28.71% | 16.87% / 17.24% |

1024 维的 Gold 列 rank（6,523 个 Gold 列元素）p50=6、p90=51.8、最大=198；按每题最靠前 Gold 列 rank 统计，p50=1、p90=3。列 R@10 下 4,107 个 Gold 列命中，2,416 个未命中。

### 每库候选、饱和与 1024 维结果

| 数据库 | 题数 / 列可评 / 不可评 | 表/列候选数 | 表 R@5 / R@10 | 列 R@5 / R@10 | 完整表列@2048 | Schema tokens / 全 schema 可装入 2048 |
|---|---:|---:|---:|---:|---:|---:|
| california_schools | 89 / 87 / 2 | 3 / 89 | 100.00% / 100.00% | 38.95% / 50.76% | 16.09% | 4,522 / 否 |
| card_games | 191 / 175 / 16 | 6 / 115 | 99.74% / 100.00% | 45.42% / 54.16% | 41.71% | 4,574 / 否 |
| codebase_community | 186 / 172 / 14 | 8 / 71 | 94.31% / 100.00% | 58.53% / 71.33% | 100.00% | 2,005 / 是 |
| debit_card_specializing | 64 / 61 / 3 | 5 / 21 | 100.00% / 100.00% | 65.73% / 83.02% | 100.00% | 497 / 是 |
| european_football_2 | 129 / 122 / 7 | 7 / 199 | 96.90% / 100.00% | 39.49% / 48.54% | 37.70% | 5,660 / 否 |
| financial | 106 / 102 / 4 | 8 / 55 | 87.99% / 100.00% | 50.80% / 68.43% | 100.00% | 1,653 / 是 |
| formula_1 | 174 / 163 / 11 | 13 / 94 | 80.32% / 99.43% | 38.72% / 52.08% | 75.46% | 2,760 / 否 |
| student_club | 158 / 158 / 0 | 8 / 48 | 96.89% / 100.00% | 54.62% / 73.48% | 100.00% | 1,727 / 是 |
| superhero | 129 / 129 / 0 | 10 / 31 | 89.73% / 100.00% | 57.35% / 70.70% | 100.00% | 1,340 / 是 |
| thrombosis_prediction | 163 / 159 / 4 | 3 / 64 | 100.00% / 100.00% | 58.07% / 81.14% | 95.60% | 2,281 / 否 |
| toxicology | 145 / 132 / 13 | 4 / 11 | 100.00% / 100.00% | 77.96% / 99.37% | 100.00% | 487 / 是 |

10/11 个数据库的表候选不超过 10 个，Table@10 在对应 1,360/1,534 题（88.66%）不检验排序；4/11 个库的表候选不超过 5 个，对应 461 题（30.05%）。Table Gold 数不超过 5，因此这些 K 下不存在 Gold 数大于 K 的天然不可达问题。每个库的列候选数都大于 10；但 317/1,460 题需要 6–10 个 Gold 列，故 Column@5 的完整召回对这些题天然不可达。

每个合格题的 Gold 节点总 token 数在 1,024 和 2,048 预算下均可装入；512 预算下为 1,399/1,460。另一方面，完整 schema 可装进 512/1,024 token 的仅 2 个库，2048 token 的有 6 个库、覆盖 754/1,460 个列可评问题（51.64%）。因此 2048 完整率不能脱离逐库全 schema 饱和单独解释；完整 schema 能装入的库在本轮自然达到 100%。

各库 `512 / 1,024 / 2,048 ÷ 全库 schema tokens` 比例依次为：`california_schools` 11.3/22.6/45.3%；`card_games` 11.2/22.4/44.8%；`codebase_community` 25.5/51.1/102.1%；`debit_card_specializing` 103.0/206.0/412.1%；`european_football_2` 9.0/18.1/36.2%；`financial` 31.0/61.9/123.9%；`formula_1` 18.6/37.1/74.2%；`student_club` 29.6/59.3/118.6%；`superhero` 38.2/76.4/152.8%；`thrombosis_prediction` 22.4/44.9/89.8%；`toxicology` 105.1/210.3/420.5%。

### 512 与 1024 的配对变化、列错误信号

| 指标（1,460 道列可评题） | 1024 改善 | 1024 变差 | 相同 |
|---|---:|---:|---:|
| Column R@10 命中数 | 154 | 117 | 1,189 |
| 完整表列@2048 | 18 | 8 | 1,434 |

对 Gold 列元素的自动、非互斥文本特征统计如下；分母是 Gold 列元素而非问题数。这是描述性关联，不是人工归因或因果结论。

| 特征 | R@10 命中 Gold 列 | R@10 未命中 Gold 列 |
|---|---:|---:|
| 问题与列/表名称有 token overlap | 56.46% (2,319/4,107) | 33.32% (805/2,416) |
| 有 values 描述 | 32.19% (1,322/4,107) | 14.69% (355/2,416) |
| 有 column description | 98.34% (4,039/4,107) | 94.25% (2,277/2,416) |
| 有任一描述字段 | 100.00% | 99.75% (2,410/2,416) |
| 有 format 描述 | 98.98% (4,065/4,107) | 99.17% (2,396/2,416) |

词面重合和 values 描述是可直接观察的运行时信号，但本轮没有对 2,416 个未命中 Gold 列逐条作人工语义分类；不能据此断言词面/描述是唯一错误来源，也不把它们当成 P2a 收益证据。

### FK / JOIN Gate

11 个库共核对 102 个 BIRD JSON FK pairs 与 103 个 SQLite 原始约束实例：100 个实例可解析为有效连接、99 个不同的关系签名、3 个无效约束；4 个 SQLite 外键省略父列并按父表主键解析，存在 1 个重复关系签名。另有 5 个 JSON FK pair 在 SQLite 中没有有效对应，2 个 SQLite FK pair 未出现在 JSON；差异集中在 `debit_card_specializing`、`european_football_2`、`student_club`，其余 8 库未见这些差异。

Gold SQL 解析失败 0；1,534 题中有 1,140 题含显式 JOIN ON，共 1,428 个 ON 条件。按直接列等值条件与 SQLite FK 实例核对：1,199 个唯一匹配、204 个未匹配、25 个有歧义；970 题至少有一个唯一 FK 匹配，只有 932/1,140 题的全部 ON 条件都唯一匹配。197 题存在同表对多 FK 候选。该解析只计显式 JOIN 条件，不等同于语义角色正确性；与旧 P0 的 query-level 956 匹配/174 多 FK 候选采用不同计数定义，不能直接作数值差异解释。**FK Gate 仍为 NO-GO；不开展 Role/Path 准确率实验。**

## 历史复现核对与最终 Gate

冻结文件、模型清单和执行器哈希通过；但旧 full-run 的完整候选文本排序/序列化规则未记录，且旧运行没有保存 embedding/rank 缓存。对留存的旧逐题指标，本轮 512/1,024 的 hit 数及 2,048 完整标记共 14,805/14,896 项一致，匹配率 99.389%；91 项不一致，主要在 Column R@5/R@10。各字段不一致数为：512 Table R@5 5、Table R@10 0、Column R@5 25、Column R@10 19、完整标记 1；1,024 分别为 1、1、20、16、3。没有证据可以将差异唯一归因于候选序列化、推理数值或排序边界。

1024 新旧聚合宏平均相差很小（Table R@5/R@10、Column R@5/R@10、完整@2048 依次约 +0.02、+0.02、+0.09、+0.05、−0.07 个百分点），但预注册要求逐题完全相同，故**严格历史复现 Gate 未通过**。本轮 P1.5 诊断产物已完成，P2a 按冻结停止条件未运行；需要在下一份仓库指导中先处理复现差异，再决定是否重新冻结评分比较。FK Gate 独立保持 NO-GO。

## 产物与隐私

- [预注册配置](experiment_config.json)，SHA-256 `9967c7fe57827a9f5ef36eb566c9fa14052948f90f8a39e7715298122d58f86b`。
- [安全聚合结果](aggregate_summary.json)，包含由本地逐题工件汇总的 type-specific Precision@K 与 token efficiency，SHA-256 `84afaaaf299c927244bcab240ab6697c3fd36892b3c0cddb8f31e3696579af54`。
- [公开输入与执行清单](input_manifest.json)，SHA-256 `ef67c6e0da15009191bba1f2a72d26b0beb2533178ee6a6319a60c75f5bd7021`。
- 逐题预测、question ID、Gold SQL、SQLite 约束明细和运行日志只留在本地 `/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p1_5_diagnosis_20261016/`；没有推送到 GitHub。公开聚合文件不含逐题行或 question hash。
- 本报告记录的是表/列检索诊断和 FK 覆盖，不是 GFM-RAG 端到端复现，也没有运行 SQL 生成/执行、GNN、Jev 或 Text2SQL EX。
