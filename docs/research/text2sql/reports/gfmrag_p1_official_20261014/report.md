# QuadGraph P1：官方 GFM-RAG 编码器复跑

**实验日期：** 2026-10-14

**实验 ID：** `gfmrag_p1_official_20261014`

**正式运行 ID：** `gfmrag_official_full1534_20261014_01`

**状态：** 完成；结果为 BIRD dev exploratory；无维度通过表/列筛查门。

**归档性质：** 历史运行记录。实验于 2026-10-14 完成，早于当前研究工作台与复现规范迁入主仓库；本文不声称该运行满足当前 P0/P1 的完整验收要求。

**方案背景：** [实验路线图](../../experiment-roadmap.md)。本次实际运行的冻结参数见本目录的 `experiment_config.json`。

## 研究问题与结论

本实验检验 GFM-RAG 官方 Qwen3 embedding 编码器的较短向量前缀，能否在降低节点向量存储时保持 Text2SQL 表/列检索质量和预算内的完整 schema 覆盖。

五题 smoke 通过后，运行了 BIRD dev 的 1,534 题筛查。`{128, 256, 512, 768, 1024}` 中没有维度满足全部预设条件，因此按停止规则结束 P1，不追加搜索。

512 维将 float32 节点向量矩阵从 3,575,808 字节降至 1,787,904 字节，节省 50%；完整表列覆盖率为 78.84%，比 1,024 维低 0.82 个百分点。但 Table Recall@10 低 0.04 个百分点，Column Recall@5/@10 分别低 1.33/0.77 个百分点，未通过“不降低表/列召回”的门槛。其他维度也至少违反一项门槛。

本实验只调用官方 `Qwen3TextEmbModel` 编码器与本地 vLLM embedding 路径；没有运行 G-Reasoner 图模型、官方端到端 RAG 或 Text2SQL。由于 P0 外键质量门未通过，FK、Join Role 和路径指标未测试。本结果不支持完整 H1，也不能作为 SQL 执行或官方论文复现的证据。

## 实验方案

- **核心假设：** 官方 GFM-RAG Qwen3 embedding 后端能够执行预注册的 BIRD 表/列维度筛查；较低的 Matryoshka 前缀维度有机会减少 float32 节点向量存储而不损伤关键检索指标。
- **数据与范围：** BIRD dev，1,534 个问题、11 个数据库、873 个候选节点（75 个表、798 个列）；1,534 题可评表指标，1,460 题有完整列标签可评列指标，合计 6,523 个列标签。BIRD dev 已用于开发，因此只作 exploratory 证据。
- **候选文本：** 表节点使用表名和全部原始列名；列节点使用表/列名、BIRD 类型及非空的 description、format、values 描述。Gold SQL 不参与候选文本构造、编码或排序。
- **编码与排序：** 同一 1,024 维编码结果截取 `{128, 256, 512, 768, 1024}` 前缀；每个前缀单独做 L2 归一化；穷举精确 cosine，不用 ANN。Query 指令为 `Given a natural-language question about a database, retrieve the relevant tables and columns.`
- **指标：** Table 与 Column Recall@5/@10；将两类候选合并后，在 2,048 passage-token 预算中贪心纳入候选，计算所有必需表列都命中的问题比例；向量存储只计 `873 × d × 4` 字节，不含索引和元数据。
- **筛查门：** 相对 1,024 维，完整 schema 问题覆盖损失 ≤1.0 个百分点、float32 向量存储节省 ≥45%，并且 Table/Column Recall@5 和 @10 均不下降。三项必须同时满足。
- **试运行与预算：** 先跑 5 题 smoke，通过才跑 1,534 题全量。物理 GPU 1；GPU 上限 2,700 秒、CPU 上限 1,800 秒（最多 8 线程）、RAM 上限 16 GiB。无 API 调用、训练、SQL 执行、HTTP 服务、依赖安装或模型下载。

## 结果

Recall 与完整覆盖率按逐题宏平均报告；完整覆盖分母为 1,460 个列标签完整解析的问题。

| 维度 | Table R@5 | Table R@10 | Column R@5 | Column R@10 | 完整表列覆盖率@2048 | 相对 1024 覆盖损失 | 向量矩阵 | 存储节省 | 筛查门 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 128 | 93.65% | 99.74% | 45.88% | 61.23% | 76.92% | 2.74 pp | 446,976 B | 87.5% | 未通过 |
| 256 | 94.14% | 99.87% | 48.58% | 64.51% | 77.26% | 2.40 pp | 893,952 B | 75% | 未通过 |
| 512 | 94.80% | 99.88% | 51.51% | 67.24% | 78.84% | 0.82 pp | 1,787,904 B | 50% | 未通过：Recall 下降 |
| 768 | 94.85% | 99.90% | 52.51% | 67.52% | 79.38% | 0.27 pp | 2,681,856 B | 25% | 未通过：节省不足且 Recall 下降 |
| 1024 | 94.75% | 99.91% | 52.84% | 68.01% | 79.66% | — | 3,575,808 B | 0% | 参考维度 |

按 11 个数据库聚类、10,000 次 bootstrap（seed `20261014`），512 维相对 1,024 维的 Column Recall 差异为：R@5 −1.10 pp（95% CI −1.96 至 −0.28 pp），R@10 −0.88 pp（95% CI −1.56 至 −0.21 pp）。

5 题 smoke 使用 1 个数据库、92 个节点；五个维度都产出有效结果，GPU 加载与编码耗时 21.79 秒。全量 GPU 加载与编码耗时 23.89 秒；总 wall time 30.25 秒、CPU time 36.18 秒、峰值 RSS 1,011,796 KiB，均在登记预算内。

## 代码、数据与环境

- **后续工作仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，公开 fork。实验代码基线及本次运行记录的官方代码 commit 均为 `b3e43219c49929da505244df4f0ba54c0947e4c4`；该代码版本采用 Apache-2.0。报告现归档在此仓库的 Text2SQL 研究工作台。
- **运行时实际代码来源：** [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，commit `b3e43219c49929da505244df4f0ba54c0947e4c4`。实际类为 `gfmrag.text_emb_models.qwen3_model.Qwen3TextEmbModel`；该 commit 的源码未修改。
- **仓库指南核对：** 目标仓库 README 声明 Python 3.12、CUDA 12+；`docs/experiment/overview.md` 与 `docs/experiment/gfm_rag.md` 描述的是论文官方复现流程（索引、训练、QA）。本报告是独立的 BIRD 表/列维度筛查，没有执行这些端到端复现阶段，故不标称论文复现。该 GitHub fork 用作后续工作基准；本报告记录的历史运行仍按其真实执行来源和 commit 描述。
- **编码器与模型：** 本地 `Qwen3-Embedding-0.6B`，BF16 权重，vLLM `LLM(task="embed")`；checkpoint pooling 配置 `normalize=True`，runner 对各维度前缀再次显式 L2 归一化。按精确 cosine 排序。
- **执行环境：** `think2sql_20260909`；Python 3.12.14、PyTorch 2.8.0+cu128、vLLM 0.10.2、Transformers 4.57.1、NumPy 2.2.6；NVIDIA GeForce RTX 4090，物理 GPU 1。未安装依赖、下载模型、启动服务、训练、执行 SQL 或调用 API。
- **数据校验：** `dev.json` SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；P0 审计 SHA-256 `0f3f104638e1a37c579db81c453aa514188e0a40341938b92964db833410ebcf`；模型清单 SHA-256 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`。75 份 description CSV 均通过冻结哈希检查；71 份以 `utf-8-sig` 读取，4 份 UTF-8 解码失败后回退 `cp1252`，源文件未改写。
- **指纹限制：** Query 文本 SHA-256 为 `a33e140e6ae5a362b5480a437bc77431b8c878f000e3ea03dadba38108b25634`；本轮确定性 type-first schema 文本 SHA-256 为 `b5b6ca9714195f733aaeb379aabbcb64c403e107444b8ed95679d798d924ab5a`。旧 full 记录的 schema 指纹为 `2089cf5c7d10aa4056c98a19edca44a3fa0bfa17e2c1f0593848f7c935d4f226`，但没有保存节点排序及哈希序列化规则，不能证明全量候选文本逐字相同；本轮单独保留指纹，不声称直接匹配。

## 归档产物

- [运行配置](experiment_config.json)，SHA-256 `cce5e7b3f75aa2a102d40554fe6fba14ea65a6a84b45f4602e659663e1c9794b`。
- [聚合结果 JSON](aggregate_summary.json)，SHA-256 `33aed3af07201515aa59d3d4bd03894befec597ea3853c07e815db8db2dda97a`。
- [运行脚本](scripts/run_gfmrag_p1.py)，SHA-256 `824cbfbd0e18b2ecadada6738b447300c8725515d7867cac4cb1467ff1d2bd4f`；公共输入处理模块 [scripts/gfmrag_p1_common.py](scripts/gfmrag_p1_common.py)，SHA-256 `54fadef342ba6eb5e19d16f2121d9e078b258de909a1c9ed1a52b32a1b2c26de`。同目录还归档输入审计与环境预检脚本。
- 逐题 JSONL、原始数据集、模型权重及运行日志未上传；它们不属于此公开报告归档。聚合结果 JSON 和本文记录了主要结果、输入哈希及运行信息。

## 局限与偏离

1. BIRD dev 是已反复使用的开发集，所有发现均为探索性，不作为独立测试集证据。
2. P0 的 FK 元数据问题排除了 FK、Join Role 和路径指标；完整 H1 未检验。
3. 旧全量 schema 文本指纹缺少序列化规则，无法做逐字输入等价性确认；数据文件哈希和节点数仍通过冻结审计。
4. 常规包级导入因环境缺少未使用的 `torch_geometric` 失败。本轮采用选择性导入 shim，只加载上游编码器和基类；官方源文件保持未修改。
5. 运行配置保留当时实验环境的 `/mnt/liansp3/sources/` 数据与模型入口。其他机器复跑前需映射到等价的本地资源入口；仓库不含数据和模型。
6. 本轮是旧版表/列维度筛查，不包含当前复现规范要求的 Join-Instance/Hard Role 审计，不能用于宣称当前研究路线的 P0 闸门已通过或完整 P1 已完成。
