# P0：SQL-used FK mapping 排序独立注册 03

**状态：`STOPPED_BEFORE_RANKING`。** CPU 数据门通过；两名本地模型的 Smoke 均有效，但高置信精确共识为 2/5，低于预注册的 4/5，因此停止模型审阅 Full。随后 G-reasoner 排序 Smoke 在模型导入前因运行器与 CPU manifest 字段不匹配而停止。没有 G-reasoner/Embedding 前向、没有排序分数，也没有科学结果。按实验室规则保留现场，不重用失败的 Smoke run ID。

## 研究问题与实验边界

问题是：在 BIRD dev 参考 SQL 中明确出现的、具有多个声明 FK mapping 候选的表对上，冻结 G-reasoner 是否比共享向量 Dense cosine 更常把 SQL 实际使用的完整 mapping 排在第一位？这是重复开发集上的 exploratory 筛查，不是独立测试或跨库泛化结果。

目标是 SQLGlot 从显式 `JOIN ... ON` 等式中提取出的 SQL-used FK mapping。它不代表唯一正确的业务语义 Role，也不等价于端到端 JOIN 路径发现或 SQL 执行准确率。SQL 和 SQL-derived 目标只用于 CPU 标签构造及离线评价，不进入模型特征或模型审阅提示。

本轮改变的是**样本来源与标签目标**：先前 60 个模型审阅问题×表对与参考 SQL 的显式 JOIN 对不齐；本注册从已解析的 JOIN 表对重新选择样本，并用 SQL-used mapping 作评价目标。排序算法、G-reasoner checkpoint、Embedding checkpoint、图结构和 Dense 基线均保持冻结，没有提出或测试新的 GFM 算法。用户选择两名本地 Qwen 模型作次要盲审代理；它们不构成人工金标准。

## 预注册和停止规则

- 项目仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 预注册提交：[`566b8e2d9bb244d8868372ae39c887de02f703e9`](https://github.com/bArtyom/gfm-rag/commit/566b8e2d9bb244d8868372ae39c887de02f703e9)。执行时本地 HEAD 与该提交相同。
- 参考上游实现：[`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，固定 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`；报告和实验结果只进入用户维护的 `bArtyom/gfm-rag`。
- 注册方案：[plan](../../plans/p0_fk_sql_used_mapping_rank_20261107_03.md)；[主配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json)；[模型审阅配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_model_review.json)。
- 实验前阅读了仓库根 README、Text2SQL README、`experiment-roadmap.md`、`reproducibility-contract.md` 和 `/mnt/liansp3/sources.md`。项目实验报告只写入用户维护的 `bArtyom/gfm-rag`，没有写入第三方上游。
- 主要筛选门：G-reasoner−Dense 的 Mapping@1 至少 +5 个百分点、净救回至少 4 个单元，并且至少两个各有 `n≥5` 的匿名数据库净救回为正。CPU 门要求 5 个 Smoke 全部完整解析且目标 mapping 覆盖候选，并在排除 Smoke 后至少 30 个 Full 单元、覆盖至少 3 库。
- 模型审阅门：A/B 各自 Smoke 5/5 有效，且至少 4/5 高置信精确一致，方可运行模型审阅 Full。排序器只有一次 5 题 Smoke；本轮失败后不复用该 run ID。
- 偏离项：没有改变数据、模型、阈值或方法。两个预设质量门按原规则停止相应阶段。

## 数据与 CPU 标签门

数据使用冻结的 BIRD dev（1,534 题、11 个数据库）；数据 SHA-256 与冻结 FK、crosswalk 和 exclusion manifest 见主配置。SQLGlot 为 28.0.0，SQLite 方言，并使用 scope-aware JOIN 等式解析。候选来自按端点表对建立的 canonical FK mapping，不用 Gold 列对筛选候选；复合 FK 要在同一 `JOIN ON` 和 alias pair 中完整匹配。`WHERE` 与 `USING` 不属于本标签。

| CPU 检查 | 结果 |
|---|---:|
| 含显式 JOIN 的题目 | 1,140 |
| SQL parse 成功 | 1,140/1,140 |
| 完整解析的题目 | 1,128 |
| 限定 JOIN 等式解析 | 1,417/1,431；未解析 14 |
| Scope analysis error | 0 |
| 多 FK SQL JOIN 候选覆盖 | 174/176（98.86%） |
| 选出的样本 | 113 个问题×表对：Smoke 5，Full 108 |
| Full 覆盖 | 4 个匿名数据库；每个单元至少有两个候选，且目标在候选集中 |
| CPU 资源 | 2.01 CPU 秒、2.05 wall 秒、峰值 RSS 0.62 GiB；无 GPU、模型、API 或 SQL 执行 |

CPU 数据门状态为 `CPU_DATA_GATE_PASS`。Smoke 与 Full 不重叠；所有样本及 SQL-derived 目标只保存在权限受限的本地 manifest 和审阅包中。

## 本地模型审阅 Smoke

两位审阅者只看到问题、无序表对和全部候选 mapping；看不到 SQL、SQL-used 标签、排名、分数、数据库/问题 ID 或另一位审阅者的输出。使用本地模型、贪心解码，不调用外部 API。

| Reviewer | 本地模型 | 有效输出 | 输入 token | 输出 token | 峰值显存 | 生成区间 / 整段运行 wall |
|---|---|---:|---:|---:|---:|---:|
| A | Qwen2.5-Coder-7B-Instruct | 5/5 | 2,216 | 249 | 14.34 GiB | 6.59 / 7.14 秒 |
| B | Qwen3-4B-Think2SQL | 5/5 | 2,236 | 542 | 7.70 GiB | 19.81 / 20.41 秒 |
| 合计 | 两个本地模型 | 10/10 | 4,452 | 791 | — | 生成区间 26.41 秒、运行 wall 27.55 秒；模型加载另计 10.17 秒 |

这里记录的是进程 wall 与生成计时区间；没有独立的 GPU kernel-active-time 计数。

两位模型仅 2/5 达到预注册的高置信精确一致门（要求至少 4/5）。状态为 `MODEL_REVIEW_SMOKE_STOP`；未运行模型审阅 Full，也未将模型共识解释成人工标签。人工 Role 金标准仍为 0。

## G-reasoner 排序 Smoke：运行器错误

运行 `p0_fk_sql_used_mapping_rank_20261107_03_smoke_001` 时，程序读取了 CPU 汇总和私有 manifest，随后报 `SELECTED_UNIT_COUNT_MISMATCH`。CPU manifest 保存 `smoke_unit_ids` 和 `full_unit_ids`，但没有 `smoke_unit_count` / `full_unit_count` 字段；排序运行器却用缺失的计数键校验所选样本数。因此它在 `adapt_private`、PyTorch/Transformers 导入、模型加载、Embedding 编码和 G-reasoner 前向之前停止。

该错误是实现契约不一致，不是模型错误，也不提供方法正负证据。没有生成排名输出目录，没有打分单元、指标或 ranker token。按本轮“一次 Smoke”预算和连续工程错误暂停规则，不修补后重放同一 run ID，也不自动新开 `_04` 注册。若未来要继续，须先单独修正并审阅 manifest/count 契约，另行决定新的预算和 run ID。

## 方法、代码与复现记录

- Primary：冻结 G-reasoner-34M 排序；Dense cosine 复用同一 Qwen3-Embedding-0.6B query/mapping vectors。图包含两个端点表节点、每个唯一 canonical mapping 一个节点、每个 mapping 四条有向关系边，两个端点表作为二值 seed。Tie-break 固定为 mapping ID 升序。BM25 只作描述控制。
- Smoke/Full 样本由本实验 ID 与 question-key SHA-256 确定；排序器设 `torch.manual_seed(20261107)`，模型审阅使用 greedy、temperature 0。
- 本轮只新增 `_03` 专属 CPU 准备器、ranker wrapper、模型审阅聚合器和冻结配置；复用仓库既有 SQL resolver、ranker 底层和本地 review runner。没有训练、微调、调参、SQL 执行、下载或依赖升级。
- G-reasoner 与 Qwen3 Embedding 的权重/config/tokenizer 指纹均与登记值一致；Reviewer A/B 的 config 和所有分片指纹也与登记值一致。
- CPU 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0。
- 模型环境：`gfmrag_greasoner_20261022`，Python 3.12.15、PyTorch 2.8.0、PyG 2.6.1、Transformers 4.56.1、Sentence-Transformers 5.1.1。
- 硬件：4×RTX 4090；启动检查时 4 卡空闲，内存可用约 451 GiB、192 CPU 线程、磁盘可用 112 TiB。Reviewer A/B 分别用 GPU0/1 串行执行；ranker 预定 GPU3，但失败发生在 GPU 初始化前。没有安装或升级依赖。
- Reviewer 实际命令、日志及私有输出在 `/mnt/liansp3/logs/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/` 与 `/mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/`。所有私有文件权限为 0600；GitHub 仅公开匿名汇总，不公开问题、SQL、schema、mapping ID、逐单元输出或模型原文。

下列为本地实际启动命令（模型均离线加载；输出路径仅在本机）。

```bash
OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 conda run --no-capture-output -n think2sql_20260909 /root/miniconda3/envs/think2sql_20260909/bin/python3.12 scripts/text2sql/prepare_p0_fk_sql_used_mapping_rank_20261107_03.py --run-id p0_fk_sql_used_mapping_rank_20261107_03_cpu_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001

GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_A_smoke_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_B_smoke_packet.md --reviewer A --mode smoke --model /mnt/liansp3/sources/models/qwen25-coder-7b --model-name Qwen2.5-Coder-7B-Instruct --run-id p0_fk_sql_used_mapping_rank_20261107_03_review_smoke_001 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/review_smoke_A

GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_A_smoke_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_B_smoke_packet.md --reviewer B --mode smoke --model /mnt/liansp3/sources/models/qwen3-4b-think2sql --model-name Qwen3-4B-Think2SQL --run-id p0_fk_sql_used_mapping_rank_20261107_03_review_smoke_001 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/review_smoke_B --disable-thinking

conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/aggregate_p0_fk_sql_used_model_review_20261107_03.py --mode smoke --run-id p0_fk_sql_used_mapping_rank_20261107_03_review_smoke_001 --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --packet-a /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_A_smoke_packet.md --packet-b /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/reviewer_B_smoke_packet.md --reviewer-a /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/review_smoke_A/reviewer_A.jsonl --reviewer-b /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/review_smoke_B/reviewer_B.jsonl --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/review_smoke_aggregate

GFM_SHARED_CODE_ROOT=/mnt/liansp3/sources/code CUDA_VISIBLE_DEVICES=3 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false timeout --signal=INT 1800s conda run --no-capture-output -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 scripts/text2sql/run_p0_fk_sql_used_mapping_rank_20261107_03.py --mode smoke --run-id p0_fk_sql_used_mapping_rank_20261107_03_smoke_001 --repo-root /mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom/.worktrees/bird-gold-label-robustness-20261106 --config configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json --cpu-summary /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/aggregate_summary.json --prepared-manifest /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/cpu_001/prepared_manifest_private.json --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cuda:0 --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_sql_used_mapping_rank_20261107_03/ranker_smoke
```

模型审阅 Full 未启动；排序 Smoke 的完整命令与失败日志保存在私有 `ranker_smoke_command.txt` / `ranker_smoke.log`。

## Token、费用、结果和解释

- 本轮 ledger 记录 10 个本地 reviewer 请求：输入 4,452、输出 791、总计 5,243 token；没有缺失 usage 的本轮请求。G-reasoner ranker 尚未调用 Embedding，ranker tokens 为 0。
- 外部 API 请求为 0，外部 API 费用为 CNY 0；本地 GPU 时间单独记录，不折算为账单金额。供应商实扣状态不适用于本地推理。
- 本轮没有 Ranking@1/3、MRR、救回/损坏或逐库排序指标。因而不能据此说 G-reasoner 优于或劣于 Dense。
- 结论仅为：SQL-used 目标下的样本和 CPU 标签门可构造；这两个模型在此批审阅任务上的高置信一致性未过门；ranker 尚未被实际评估。此结果不改变对 QuadGraph/G-reasoner 整体效能的判断。

共享 token ledger 当前累计：73,757 请求；已报告输入 329,493,201、输出 55,162,566、总计 384,655,767 token；usage 缺失请求 106。可核价请求的累计公开价估算为 CNY 23.9626091190912，实际账单未核实；另有 72,493 个有 usage 的请求未进入公开价估算。Ledger 只覆盖已登记请求，不代表供应商账户全部消费。

## 产物

- [匿名聚合结果](aggregate_summary.json)
- [预注册方案](../../plans/p0_fk_sql_used_mapping_rank_20261107_03.md)
- [冻结主配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03.json)
- [模型审阅配置](../../../../../configs/text2sql/p0_fk_sql_used_mapping_rank_20261107_03_model_review.json)
