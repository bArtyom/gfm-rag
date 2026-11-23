# RAMP-SL 编码预算上限试验：预注册

**Run ID:** `ramp_sl_encoding_budget_gate_20261123_001`

**状态:** preregistered，尚未读取本轮结果

**层级:** 主假设的最小可行性 gate；exploratory，不作为论文主结果

**方向:** 验证固定低成本候选排序之外，昂贵问题—字段编码是否存在值得学习的选择余量。

## 研究问题与核心假设

在每题固定高成本编码输入预算 `M=4,096` tokenizer tokens、固定最终字段序列化预算 `B=2,048` tokens 时，按低成本 Qwen3-Embedding 相似度固定取候选，与一个离线昂贵编码 oracle 相比，完整参考字段覆盖是否至少相差 3 个百分点？

**唯一假设 H1：** 在相同候选编码预算 `M` 和输出预算 `B` 下，离线 oracle 相对固定低成本排序的完整 Gold-column coverage@B 至少高 `3.0 pp`。这只是可学习余量的必要条件；通过不代表 RAMP-SL 方法有效。低于门槛则停止当前方向，不开发效用头或调度器。

## 范围与两组对照

数据为本地 BIRD-dev 的列标签可评题，来自 1,534 题/11 库的已冻结 P1.6 输入；每库按固定哈希种子抽取最多 10 题，预期最多 110 题。抽样只使用数据库 ID、问题 ID 和列标签可评状态，不使用具体 Gold 字段、SQL 或本轮模型分数。此数据已在本仓库多轮使用，结论仅为 exploratory。

1. **Static-TopM：** 用已有 Qwen3-Embedding-0.6B 全量缓存按精确余弦分数排序；按此顺序扫描字段，在 `M` 预算内加入可容纳项，跳过超出剩余预算项并继续扫描。只对入选字段运行 GRAST-SQL BIRD 微调 0.6B reranker，取得 `P(yes)`；再按该分数排序，在 `B` 内输出字段。
2. **Offline-Oracle：** 对该题全部字段运行同一个 GRAST-SQL reranker，按 `P(yes)` 排序，在相同 `M` 下选字段，再在相同 `B` 下输出。它是不可部署的离线上限；虽最终入选字段的输入 token 不超过 `M`，计算上已对全候选编码，实际消耗必须另报，不能称为同等实际计算量。

不运行 GNN、Steiner 闭包、SQL 生成/执行或训练。此 gate 检验“昂贵编码应分配给哪些字段”的上限，不声称是完整 GRAST-SQL 复现，也不评价 GNN 或端到端 Text-to-SQL。

## 冻结输入和实现边界

- BIRD-dev 问题与 schema：`/mnt/liansp3/sources/datasets/bird/dev/{dev.json,dev_tables.json}`；P1.6 清单中的问题/Schema SHA-256 分别为 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`、`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。启动时重新核验本地 SHA，不匹配即停止。
- Gold 字段 ID 从既有 P1.6 私有 `column_gold_ranks` 与冻结 query/node 向量重建；先在每题逐项核验重新计算的 Top-5/10/20 ID 与原缓存一致。任一不一致即停止，不能打开或解析 Gold SQL 来绕过该检查。
- 低成本分数：复用 `/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01/embedding_cache_private.npz`，不重新编码。缓存来自 Qwen3-Embedding-0.6B、1024 维；精确模型清单 hash 为 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`。
- 高成本模型：Hugging Face `griffith-bigdata/GRAST-SQL-0.6B-BIRD-Reranker`，冻结 revision `50b224a1e8557ad6629c7dafddeba7b73c603acb`，Apache-2.0。只下载模型 safetensors 与 tokenizer/config，不下载 GNN `.pt` 检查点。
- 问题—字段输入采用上游 GRAST-SQL commit `4c698cae31da8299deb5c809101d172d5b2ddeb3` 的问答指令、前缀/后缀和字段描述构造；当前本地 BIRD schema 没有 GRAST 图缓存，所以字段描述只含表名、列名和声明类型，meaning、sample-values、null/value 描述留空。实际 token 成本按冻结模型 tokenizer 对最终 prompt 计数。此输入信息缺失是重要限制，结果不等同于官方完整字段增强流程。
- reranker 分数按模型下一 token 的 `yes`/`no` logits 计算二类 softmax 概率；批内 padding token 不算入逻辑预算，但另报物理填充 token（若可取）。单条 prompt 超过 4,096 tokens、非有限分数或 tokenizer/model revision 不匹配均停止。
- 输出格式固定为每列一行 `table.column (declared_type)`，B 用同一 tokenizer 计算；不补表、不闭包、不额外加键。
- Tie-break 固定为字段 ID 字典序。无随机训练；抽样 seed `20261123`。

## 指标与成功/停止门

- **主要指标：** `complete Gold-column coverage@B`，即输出字段集合完整包含该题所有已解析 Gold columns 的题目比例。报告 Static-TopM 与 Offline-Oracle 逐题配对差。
- 次要指标：Gold-column Recall@M、字段 Recall/Precision@B、每题入选的昂贵编码 token、oracle 全候选真实编码 token、模型 wall time / GPU 时间、输入/输出 token 数、数据库分层结果。
- 5 题工程 smoke：来自 5 个不同数据库的确定性样本；只检验资源、数据映射、prompt、输出形状和日志，不作科学判断。
- smoke 通过后运行最多 110 题 gate。要求至少 80 个可评分问题且覆盖至少 8 个数据库；不满足则报告 HOLD。
- 若 Oracle−Static-TopM 的主要指标 `<3.0 pp`，停止 RAMP-SL 当前版本。若 `≥3.0 pp`，只表示存在值得验证的余量；再按此相同冻结规则扩展到全部 1,460 个列标签可评题，不调阈值、不换模型、不换预算。
- 全量扩展上限：最多 16,000,000 个本地 reranker 输入 tokens、GPU wall 3,600 秒、单卡 GPU1、日志/结果目录独立。任一预算先到、资源冲突或连续两次可恢复错误仍失败则暂停并保留现场。
- 无论 gate 结果如何，本轮不训练动态效用模型，不进行跨数据集泛化结论，不启动 SQL 生成/执行。

## 执行环境、资源与产物

- 参考代码：`https://github.com/thanhdath/grast-sql`，commit `4c698cae31da8299deb5c809101d172d5b2ddeb3`；已阅读根 README、`reproduce.sh`、`evaluate_on_the_fly.py`、`modules/column_encoder/init_embeddings.py`、`modules/embedding/coarse_retriever.py`。上游 checkout 未发现 LICENSE，本实验只引用接口/复用模型，不复制或再分发源代码。
- 自有项目：`https://github.com/bArtyom/gfm-rag`，本轮分支 `research/ramp-sl-progressive-encoding-20261123`；运行代码提交将写入最终报告。
- 环境：复用 `think2sql_20260909` 的 Python 3.12.14、PyTorch 2.8.0、Transformers 4.57.1；不安装依赖、不升级稳定环境。模型 BF16，批大小 8，最大单条输入 4,096 tokens。
- 资源：仅 GPU1 RTX 4090；启动前复查 `nvidia-smi`、`free -h`、`nproc`、磁盘和 GPU 进程。GPU1 空闲显存低于 20 GiB 或利用率超过 10% 时不启动。
- 本地结果：`results/ramp_sl_encoding_budget_gate_20261123_001/`；日志：`logs/ramp_sl_encoding_budget_gate_20261123_001/`；只向 GitHub 归档协议、代码、匿名聚合和报告。问题文本、逐题分数/字段、Gold 映射、权重和运行日志不上传。
- 外部模型 API/付费推理：0。所有 reranker 输入/输出 token 与 GPU 时间分开记录；本地计算不计作零资源成本。

## 结果解释边界

此实验只测一个使用公开 BIRD-dev 训练过的 reranker 直接给列对打分的 encoder-only 上限，不能证明动态策略可在线实现。低成本 embedding cache 与高成本 GRAST reranker 来自不同模型；字段描述缺少 GRAST 预处理的语义和值信息；BIRD-dev 是已暴露开发集；`B` 不含 FK/Steiner 闭包。任何通过结果都只支持下一步在数据库隔离数据上学习并验证预算调度器，不支持新颖性、全流程收益或泛化主张。
