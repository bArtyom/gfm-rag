# 种子检索 → Steiner 子 schema：首轮实验报告

**状态：完成 CPU 主对照；STOP_NO_STRUCTURAL_SIGNAL；SQL/GPU 阶段按预设条件未启动。** 这是用户授权的新探索协议，不改变旧 GFM/QES 负结果或冻结配置。日期：2026-11-09（UTC+8；运行 ID 沿用 20261108）。

## 问题与结果

核心假设：相同语义种子下，通过 FK 图补齐 Steiner 中间表，比按相似度补到相同表数，更能覆盖参考 SQL 使用的全部表。只检验此一个假设；本轮属于主实验层的 exploratory 验证。

BIRD dev 全部 1,534 题、11 库；每题固定两个语义表种子。三个实验臂使用同一份 Qwen3-Embedding-0.6B 1024 维缓存。完整表覆盖为“参考 SQL 物理表集合是检索集合的子集”；不是 SQL EX，也不意味着参考路径唯一正确。

| 方法 | 完整表覆盖 | 覆盖率 | 每题平均表数 | 每题平均列数 |
|---|---:|---:|---:|---:|
| 仅两个语义种子 | 826/1534 | 53.85% | 2.000 | 32.88 |
| 按相似度补至 Steiner 相同表数 | 973/1534 | 63.43% | 2.290 | 37.51 |
| 两个语义种子 + Steiner 连接 | 949/1534 | 61.86% | 2.290 | 37.28 |

Steiner 相对种子净增加完整覆盖 123 题（+8.02pp），但相对同表数语义补充少 24 题（−1.56pp）。369 题实际加入了中间表；其中相对同表数对照救回 32 题、损害 56 题、其余 281 题完整覆盖状态不变。184 题的两个种子属于不同 FK 连通分量，保留为森林，不伪造连接。全部参考 SQL 的物理表解析成功，无标签解析排除。

按数据库聚类、固定 seed=20261108 的 10,000 次 percentile bootstrap，Steiner−同表数对照的完整覆盖差 95% 探索性区间为 [−5.28pp, +1.23pp]。点估计未胜出；不能宣称统计上确定劣于对照。11 个数据库和复用开发集限制了泛化解释。

**预设信号要求：**在加入中间表的题目上，相对两个对照均有至少一个净完整覆盖救回。第二个对照净 −24，未达到条件；按协议停止，不启动条件式 5 题 SQL smoke 或 44 题 SQL pilot，不追加种子数/阈值/求解器扫描。没有 SQL 预测、Set EX、Bag EX、训练或独立复现成绩。

## 实现与复用

公开相关实现：[thanhdath/grast-sql](https://github.com/thanhdath/grast-sql)，冻结 commit `4c698cae31da8299deb5c809101d172d5b2ddeb3`。已阅读 README、environment.yaml 和 Steiner 模块；原始使用方式需专用训练 reranker/GNN 与作者数据，README 自建数据库流程还使用外部模型生成描述。本轮不执行那些阶段。

实际运行时直接加载未修改的 `modules/steiner_tree_spanner/steiner.py::get_steiner_subgraph`。独立适配层采用合成表/列 ID 建图，避免表名中的点号被误拆；不使用上游最后的固定 Top-K 截断；保留全部种子、补入表的所有列及选中表之间的完整 SQLite FK 约束。并行 FK 和复合 FK 不压成一个猜测角色。输出是 SQL 生成上下文，不是指定的唯一 JOIN 计划。列级种子 API 已实现并测试，但本轮只运行表级种子配置。

没有发现上游 LICENSE 文件或明确再分发许可。上游 checkout 保持在项目之外，不发布其源文件；公开内容仅为独立编写的适配器、运行器、配置、合成测试和聚合。本轮是**组件复用后的改造实验**，不是完整 GRAST-SQL 复现或其论文指标。

参考论文：[GRAST-SQL](https://arxiv.org/abs/2512.16083)、[SchemaGraphSQL](https://aclanthology.org/2026.findings-eacl.134/)。检索 + 图路径/Steiner 不是本报告主张的新颖性。

## 数据、版本和失败记录

只读复用统一资源入口，不复制模型或大数据：

- BIRD questions SHA256：`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`。
- Schema SHA256：`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 冻结 P1.6 向量缓存 SHA256：`c7bb9ed942aa793e34e1253a5d1d8f8d8d871c95bdfdc33718dde7396d345250`；query [1534,1024]、node [873,1024]，float32，显式 L2+cosine。
- 节点清单 SHA256：`81ccc51c442c9d4771a16f600340c37f2673887fc0672d8179ecc20d39296754`。
- 缓存输入回执 SHA256：`693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`；身份清单文件 SHA256：`6b28af7400cb70e0ab88a00b56654235571a074022fd8ea52b3f9744a844c4e9`。运行器只取其中 question_id/db_id 验证顺序，不取历史标签/命中数/排名特征。当前代码未强制锁定这两个辅助回执哈希；向量、问题、schema 和节点清单已强制锁定，原始 P1.6 源码另有完整 canonical-order 检查。
- 实际数据库使用已登记的 `sources/datasets/bird_dev_aligned_qes_20261012/dev_databases`；11 个逐库哈希全部写在 aligned 配置中。原始缓存的文本版本与本轮 FK 图的数据库版本分开记录，不声称二者来自同一数据库文件快照。

首次 Smoke_001 在加载元数据时停止：共享 student_club 三个 FK 指向不存在的内部 shadow 表。个人资源索引已有该历史迁移记录。未修复或覆盖共享文件，改用现成归档对齐副本，新增 aligned 配置和协议 Amendment 001，保留原配置/日志/失败目录。student_club SHA256 `eb89bcfe97eefa386a27904ec5aa15159811a7eac894ec659a36e48fa9f76b77` 与已登记官方 Mini-Dev 包副本逐字节一致；其余十个 DB 不变。

Smoke_002（5 题）工程通过：参考表解析 5/5、输出 5/5；完整覆盖三个方法均 2/5。该 smoke 用于接口验证，不能与 1,534 题成绩相加，也不是独立效能试验。

正式预测先封存再重新打开参考 SQL 评价，预测 SHA256：`e1d9b0792735e2a750008ac90958626fefa53961f5b1921a37ad72494f0424e8`。原始问题、SQL、逐题预测、身份清单、数据库、日志均保留本地，不上传。

## 环境、预算与实际资源

已有 `think2sql_20260909` 环境，使用环境 Python 的绝对入口通过 conda run 启动：Python3.12.14、NumPy2.2.6、NetworkX3.6rc0、SQLGlot28.0.0。未安装/升级依赖。预算 CPU<=16 threads、RAM目标<8GiB；实际固定 OMP/BLAS/MKL 8 threads，主对照 wall=6.496秒、进程CPU=7.038秒、峰值RSS=0.0644GiB（不含外部资源检查子进程）。

启动检查：4×RTX4090，三张忙、一张约15GiB余量；主机192逻辑CPU、约431GiB可用RAM，磁盘充足。全过程 CPU-only，未占用新 GPU；新模型输入/输出/总 token=0/0/0，外部API费用 CNY0.00，本地CPU资源不折算货币。历史缓存的编码成本不是本轮新增费用，也不能解释为本地推理无成本。

## 可复现命令

先设置个人资源索引根 `LAB_ROOT`、现有环境绝对 Python 入口 `PYTHON_EXECUTABLE`，并将上游 checkout 定位至配置路径的冻结 commit。记录的本次 `PYTHONHASHSEED=0` 很重要：上游含 set 迭代，跨 hash seed 的等价路径选择没有验证。目标输出必须不存在。

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 \\
conda run --no-capture-output -n think2sql_20260909 "$PYTHON_EXECUTABLE" \\
  scripts/text2sql/run_seed_steiner.py \\
  --config configs/text2sql/seed_steiner_bird_aligned_20261108.json \\
  --mode smoke --output ai_temp_code/seed_steiner_smoke_REPLAY

PYTHONHASHSEED=0 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 \\
conda run --no-capture-output -n think2sql_20260909 "$PYTHON_EXECUTABLE" \\
  scripts/text2sql/run_seed_steiner.py \\
  --config configs/text2sql/seed_steiner_bird_aligned_20261108.json \\
  --mode retrieval --output results/seed_steiner_bird_REPLAY
```

原始私有产物位于独立 checkout 的 `results/seed_steiner_bird_20261108_01/retrieval_001/`；统一入口后缀同名。包括 run_start、封存预测、输入回执、划分及结果。日志位于 `logs/seed_steiner_bird_20261108_01/`；调试在 ai_temp_code，未写入正式结果目录。

## 验证与代码审阅

执行源 commit：`f95f520`；此后仅增加防止上游静默失败的连接后置检查和验证脚本，原预测和数字未修改。独立代码审阅发现上游会吞掉部分求解异常；新增测试先观察到失败，再实现对每个可连接种子分量的结果连通性检查。对封存结果逐条验证 **1534/1534**：种子保留、可连接分量连通、表数匹配、预测哈希、11 DB哈希均通过。见 postcondition_verification.json。

适配器/运行器及仓库已有只读评测/输入回归合计 **107项通过**。全仓库 pytest 在收集阶段被已有环境缺少 `torch_geometric`、`omegaconf` 阻止：tests/test_gfmrag_retriever.py、tests/test_pretrained_dataset_config.py；未称全仓测试通过，也未为此修改稳定环境。

独立统计重算 826/973/949，与原汇总完全一致。完整表覆盖、均值和逐库匿名计数见 aggregate_summary.json；聚类不确定性与误差计数见 postrun_analysis.json。

## 结论与边界

当前实现能把语义种子变为包含中间表与 FK 元数据的子 schema；但这一次固定两个表种子的 Steiner 补全，没有超过相同表数的简单语义扩充。仅对比种子会把“多给了表”的效果误当作结构收益。

708题的两个种子未覆盖全部参考表；369个实际扩展题中302题起初缺表，Steiner后仍有179题缺表。这是输入种子与桥路径能覆盖哪些表的诊断，不能推导换某个求解器必然改善，也不能推导连接最短就是业务语义正确。相同表数不等于相同提示 token；本轮没有生成器 token 或 SQL EX 比较，不得声称端到端收益。

决策：保留可复用代码，停止扩展这版固定种子的无权 Steiner 方案；如未来要研究种子歧义或问句条件路径，须先形成单独可证伪协议，不从本次负结果自动展开新实验。

