# RAMP-SL 编码预算上限试验

**Run ID：** `ramp_sl_encoding_budget_gate_20261123_001`

**状态：** smoke 与 pilot 完成；pilot 达到预注册扩展门；全量阶段因预注册输入 token 上限停止，完成 1,046/1,460 题。BIRD-dev exploratory，不是完整 GRAST-SQL 复现，也不构成方法有效性或泛化结论。

**匿名汇总：** [aggregate.public.json](aggregate.public.json)。原始逐题分数、问题/字段 ID、Gold 映射及日志仅保存在本地结果目录。

## 研究问题与预注册判据

固定每题昂贵编码预算 `M=4,096` 与最终 Schema 输出预算 `B=2,048`，比较静态低成本 Top-M 候选排序与离线 GRAST-SQL reranker 排序。唯一主指标为完整 Gold-column coverage@B。pilot 至少 80 题、至少 8 个数据库，且离线 oracle 相对静态方法提升至少 3.0 个百分点，才进入 1,460 题扩展。全量扩展上限为 16,000,000 个本地 reranker 输入 token 或 3,600 GPU 秒；不训练效用模型、不生成或执行 SQL。

## 数据、代码与模型

- 数据：BIRD-dev 的 1,534 题中有 1,460 题具备冻结列标签。问题与 Schema SHA-256 分别为 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`、`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。75 份数据库描述 CSV 已校验。P1.6 embedding cache SHA-256 `c7bb9ed942aa793e34e1253a5d1d8f8d8d871c95bdfdc33718dde7396d345250`；rank 文件 `6b28af7400cb70e0ab88a00b56654235571a074022fd8ea52b3f9744a844c4e9`；node manifest `81ccc51c442c9d4771a16f600340c37f2673887fc0672d8179ecc20d39296754`。
- 低成本排序复用冻结的 Qwen3-Embedding-0.6B 1024 维 P1.6 cache，本轮没有重新调用 Qwen。两臂使用相同的 P1.6 字段文本，其中包含可用的列描述、格式和值描述。没有 GRAST 图缓存，因此 `sample_values`、`has_null` 和额外图侧 meaning 元数据未使用。
- 昂贵模型：Hugging Face `griffith-bigdata/GRAST-SQL-0.6B-BIRD-Reranker`，revision `50b224a1e8557ad6629c7dafddeba7b73c603acb`，BF16；权重 SHA-256 `545b970a33ac183ae1746a732f455f5b0a94822be1329526c41aef891ba84fdd`。只对列对打分，用下一 token 的 `yes/no` logits 计算 reranker 分数，不做生成。模型卡标示 Apache-2.0：[模型卡](https://huggingface.co/griffith-bigdata/GRAST-SQL-0.6B-BIRD-Reranker)。
- 上游参考实现：[`thanhdath/grast-sql`](https://github.com/thanhdath/grast-sql)，commit `4c698cae31da8299deb5c809101d172d5b2ddeb3`。已核对 README、`reproduce.sh`、`evaluate_on_the_fly.py`、`modules/column_encoder/init_embeddings.py` 与 `modules/embedding/coarse_retriever.py`；该 checkout 未发现 LICENSE。本实验仅按接口和 prompt 规格自行实现评分，没有复制上游代码或运行其完整流程。
- 自有项目分支：`research/ramp-sl-progressive-encoding-20261123`。运行前代码 commit `6008197b8e6b2cfa7a24db78a80ef14eecf2c9ae`；runner SHA-256 `0539041e22656a9bc9f1a1820b30e02791f5601548efba73aa6af2eb991ad537`；配置 SHA-256 `7788ad9585b63cda03c6f34cbcb4d64cddb020e54afd21726c515d3e7b101200`。

## 执行环境与命令

- 环境：`think2sql_20260909`，Python 3.12.14、PyTorch 2.8.0+cu128、Transformers 4.57.1、NumPy 2.2.6、CUDA 12.8。仅使用物理 GPU1：RTX 4090 24,564 MiB；启动时空闲 24,161 MiB。运行时峰值 PyTorch allocated 1,290,757,120 bytes，reserved 1,413,489,448 bytes。
- 批大小 8，最大单条输入 4,096 token。Smoke 固定为 5 个数据库各 1 题；pilot 每库最多 10 题，最终 110 题、11 个数据库。全量按冻结数据顺序遍历 1,460 题，使用已完成阶段的逐题分数缓存复用。

```bash
cd /mnt/liansp3/研究项目/Text2SQL/Seed-Steiner-20261108/project
CUDA_VISIBLE_DEVICES=1 /root/miniconda3/envs/think2sql_20260909/bin/python3.12 scripts/text2sql/ramp_sl_encoding_budget_gate.py --mode smoke --output-dir results/ramp_sl_encoding_budget_gate_20261123_001/smoke_001
CUDA_VISIBLE_DEVICES=1 /root/miniconda3/envs/think2sql_20260909/bin/python3.12 scripts/text2sql/ramp_sl_encoding_budget_gate.py --mode pilot --output-dir results/ramp_sl_encoding_budget_gate_20261123_001/pilot_001 --reuse-private-scores results/ramp_sl_encoding_budget_gate_20261123_001/smoke_001/private_model_scores.jsonl
CUDA_VISIBLE_DEVICES=1 /root/miniconda3/envs/think2sql_20260909/bin/python3.12 scripts/text2sql/ramp_sl_encoding_budget_gate.py --mode full --output-dir results/ramp_sl_encoding_budget_gate_20261123_001/full_001 --reuse-private-scores results/ramp_sl_encoding_budget_gate_20261123_001/pilot_001/private_model_scores.jsonl
```

## 结果

| 阶段 | 题数 / 数据库数 | 静态完整覆盖 | 离线 oracle 完整覆盖 | 差值 | 状态 |
|---|---:|---:|---:|---:|---|
| 工程 smoke | 5 / 5 | 不作科学判断 | 不作科学判断 | — | 通过；预算与输出结构检查通过 |
| Pilot | 110 / 11 | 73/110（66.36%） | 100/110（90.91%） | +24.545 pp | `EXPAND_FULL` |
| Full 扩展 | 1,046/1,460 / 8 | 603/1,046（57.65%） | 915/1,046（87.48%） | +29.828 pp | `stopped_input_token_cap` |

Full 阶段的完整覆盖差异与 pilot 同方向，但由于 token 上限仅完成 1,046 题、覆盖 8 个数据库，不应把它称为 BIRD-dev 全量结果或用作总体效果估计。该阶段按冻结数据顺序截断，数据库覆盖并不均匀。

逐题输出独立复核与聚合一致：Full 共 1,046 题、8 个数据库、没有 Gold 数为零的题；两臂候选输入最大均为 4,096 token，静态/Oracle 输出最大分别为 1,560/1,439 token，均不超过 `B=2,048`。完整覆盖计数与聚合文件一致。

## Token、资源与费用

- 全阶段实际 GRAST 本地推理：smoke 88,794、pilot 新评分 1,475,074、full 新评分 14,770,428 个输入 token，合计 **16,334,296 输入 token、0 输出 token**；三阶段 GPU scoring time 合计 **475.402 秒**。pilot/full 复用的缓存分数不是新推理，不重复计入实际调用 token。
- Full 扩展的预注册预算记账包含复用分数：**15,968,847/16,000,000 token**，剩余 31,153 token；下一题会超过上限，因此程序正常以 `stopped_input_token_cap` 结束。3,600 秒 GPU 时间上限未触发。这里的 16M 限额适用于全量扩展阶段，smoke 与 pilot 是预先安排的独立门控阶段。
- 本轮外部模型 API 调用 0 次，外部 API 输入/输出/总 token 均为 0，费用估算 CNY 0；没有供应商账单。所有模型评分均为本地 GPU 计算，不能据此认为计算没有资源成本。

## 异常与边界

- 运行期间共享 GPU1 出现另一进程，占用约 20,762 MiB，观测到的可用显存最低约 1,227 MiB。Full 结果在准备中断时已自行按输入 token 上限正常结束；没有强制杀进程、OOM 或数据损坏。运行自身 PyTorch 峰值 allocated 约 1.20 GiB。
- 日志只有 `torch_dtype` 弃用提示与 tokenizer 性能提示，没有影响结果的异常。逐题原始分数与日志留在本地。
- Oracle 在全部字段上离线评分，不能在线部署；低成本与昂贵排序器是不同模型，不是同模型公平对照。BIRD-dev 已用于模型训练/开发，仍有数据暴露风险。
- 输入缺少 GRAST 图缓存中的样例值、空值和额外 meaning；最终 Schema 不做 FK/Steiner 闭包；没有训练、SQL 生成或 SQL 执行。因此结果只验证“昂贵 encoder 排序可能在固定预算下留下有用选择余量”，不验证渐进预算策略、在线效用预测、端到端 SQL 增益或跨数据集泛化。

## 结论与后续

按预注册规则，pilot 足以触发扩展；full 扩展已达到唯一预算停止条件。保留该信号作为 BIRD-dev 探索证据，不追加本轮 GPU 预算，也不继续在该开发集调参。若要推进 RAMP-SL，下一项应先在数据库隔离数据上设计并验证可部署的预算调度器及其强基线；该工作属于新实验，需要单独预注册。

## 本地私有产物

- 结果根目录：`results/ramp_sl_encoding_budget_gate_20261123_001/`；阶段目录为 `smoke_001/`、`pilot_001/`、`full_001/`。
- 日志根目录：`logs/ramp_sl_encoding_budget_gate_20261123_001/`。
- 本地资源索引入口：`/mnt/liansp3/sources/results/ramp_sl_encoding_budget_gate_20261123_001`。
- 问题文本、逐题分数、Gold 映射、权重和运行日志没有上传到 GitHub。
