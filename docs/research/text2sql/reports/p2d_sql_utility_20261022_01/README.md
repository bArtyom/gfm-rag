# P2d：冻结本地7B的三臂SQL效用Pilot

**状态：已完成实际生成与只读SQL评测；exploratory诊断Pilot，不是1534题全量或论文确认性实验。** 2026-10-22 10:50:32–10:52:42（UTC+8）完成正式30题×3臂；此前合成Gate及互斥Smoke均通过。102次真实本地模型请求全部入账，无重试、无付费API、无配置修改后重跑。

## 结论与主要指标

本轮没有显示V01带来SQL正确率提升。V01继续作为离线候选，**不默认替换V00**；一次有界Pilot后停止扩展。人工审核0，semantic_review_status=unverified、必要性分母0；不能由AST标签或本轮SQL结果推断Values语义必要性。

| 正式30题 | E0：V00节点/R0全文 | E1：V01节点/R1短文 | E2：V00节点/R1短文 |
|---|---:|---:|---:|
| 确认Set正确 / 全选样本 | 8/30（26.67%） | 7/30（23.33%） | 8/30（26.67%） |
| 确认Bag正确 / 全选样本 | 8/30（26.67%） | 7/30（23.33%） | 8/30（26.67%） |
| 生成SQL可执行 | 19/30 | 18/30 | 20/30 |
| 参考SQL可执行 | 26/30 | 26/30 | 26/30 |
| 比较未知（保留30分母） | 11 | 12 | 10 |
| 双方可执行但确认不正确 | 11 | 11 | 12 |
| 完整生成Prompt输入token | 35,074 | 35,591 | 24,458 |
| 生成输出token | 1,801 | 1,843 | 1,872 |

主表比例是**已确认正确/N的保守计数**，未知不算正确，也不宣称已知错误；不是忽略失败后算出的准确率，更不是官方榜单分数。E1相对E0确认正确比例−3.33pp，但共同可判样本上各有1题独有正确，故不能把−1题解释为已证实的净语义退化。E2输入较E0少10,616 token（30.27%），确认正确数相同，但存在不同题的得失和未知，不能据此宣称无损压缩。

完整指标见[正式汇总](full_summary.json)、[失败与未知审计](failure_analysis.json)、[产物验证](verification_summary.json)。

## 问题、预注册与来源

唯一问题：冻结一个普通本地Generator时，删除Values是否改变谓词值和SQL执行正确性？本轮为`exploratory_minimal_paired_SQL_pilot`，不作为主线确认性证据、不新增模型/embedding/参数扫描。预算102调用、输入≤1M/输出≤104448 token、从Gate A起≤5400秒、并发1；单请求120秒、零自动重试。成功判据为合成Gate全部正确、Smoke≥6/9可执行且每臂≥1、正式90预测先封存后评分；**没有预设“必须出现正收益”的门槛**。任何输入/代码/服务漂移、usage缺失或覆盖风险即停止；一次正式Pilot结束即停止扩展，已遵守。

- 目标仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支main；上位指导commit [`d262043`](https://github.com/bArtyom/gfm-rag/commit/d262043fbec5723d7bed7433d87bc556a753bc83)。
- **实际执行源commit**：[`33c6a216a5a3b70d61b52badb529ba9f86ebcad7`](https://github.com/bArtyom/gfm-rag/commit/33c6a216a5a3b70d61b52badb529ba9f86ebcad7)，tree `cbafd0549255fb0d4e23b3c407c3c1f380ee4529`。代码/配置先发布并逐文件远端回读，再启动模型调用；三阶段源码/配置一致。
- 已读根README、研究README、[路线图](../../experiment-roadmap.md)、[复现规范](../../reproducibility-contract.md)、[P2c-R最新复核](../p2c_r_latest_review_20261019/README.md)、[P2d上位指导](../../plans/p2d_value_utility_and_sql_pilot_20261019.md)。具体冻结选择见[2026-10-22执行登记](../../plans/p2d_sql_execution_20261022.md)。
- 本仓库沿用GFM-RAG公开代码及根目录Apache-2.0许可证，本轮未重新克隆或修改第三方上游。复用P2c-R冻结节点/序列化与既有Values审计模块，新增输入准备、三臂执行器和只读评测模块；不改变原排序、1024预算或上游结果。
- 原始冻结配置保存在[frozen_execution_config.json](frozen_execution_config.json)，SHA256 `6ae873a216932a6f34ad6b24748fb8230ce7e2dadb6cdb7818676908afb9a0e1`；[experiment_config.json](experiment_config.json)仅增加完成状态和结果指针。sample_registration中的prepared_not_run及冻结配置中的preregistered_not_run是原始登记时点，刻意保留不改写；当前状态以本报告和completed回执为准。源文件/依赖hash、实际命令及UTC时刻见三个receipt。

偏离及限制：依上位协议允许的独立工程/SQL路径，未做19题独立人工必要性审核（reviewers=[]，一致率/kappa=null），也未运行32B语义辅助审阅。selector=none，本地7B为首个普通LLM基线，**不是Jev结果**。原节点文本只有表列归属，FK Gate未过，没有额外补PK/FK约束；不混入新的数据库信息。评测器为明确口径的BIRD-compatible实现，非官方评测器完整复刻。

## 数据、模型与资源

源集仍为BIRD dev 1534题/11DB、既有可评1460题；本轮正式仅30题/5DB。原19题全部保留（AST直接绑定9支持/8不一致/2未知）。严格按DB、谓词类型集合、(Gold表数,Gold列数)、旧V00@1024 Complete相同分层，seed20261021、无放回匹配11对照；8题无匹配，未放宽条件。另3题Smoke seed20261022与正式样本互斥，不计正式指标。匿名DB配额15/3/5/2/5；样本清单SHA、输入文本及模型权重全量SHA见[sample_registration.json](sample_registration.json)。这不是随机总体抽样，30题也不是19个完整配对。

模型统一使用资源索引`/mnt/liansp3/sources/models/qwen25-coder-7b`对应的Qwen2.5-Coder-7B-Instruct，已有共享vLLM0.8.5服务，32768上下文；没有新增服务或GPU。冻结temp0、top_p1、top_k−1、repetition_penalty1、seed20261021、max_tokens1024。每题每臂单次生成，无SQL修复。问题/evidence/system模板相同；E0/E2节点ID和顺序完全一致。Prompt未裁切，完整本地tokenizer计数与99个BIRD真实请求usage逐项相同。参考SQL只用于预定样本分层和随后评测，不进入模型消息；正式90预测及SHA封存完成后才打开该阶段参考SQL执行。

环境复用`think2sql_20260909`：Python3.12.14、SqlGlot28.0.0、transformers4.57.1、tokenizers0.22.1；未装新依赖/升级环境。主机192CPU、503GiB RAM、4×RTX4090；运行前检查GPU/内存/CPU，已有服务占用GPU1约21.8GiB。客户端`CUDA_VISIBLE_DEVICES=''`，CPU线程上限8，模型请求并发1，未干扰其他GPU任务。完成后可用内存约427GiB，无OOM/资源超限。

统一私有结果入口：`/mnt/liansp3/sources/results/gfmrag_p2d_sql_utility_20261022_01`（软链有效），真实目录`/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p2d_sql_utility_20261022_01`。`prepare_01`分离保存输入/参考、模型与DB SHA、服务身份；`gate_a_01`、`smoke_3q_01`、`full_01`各有独立请求/响应、预测封存、执行结果和receipt。日志在`/mnt/liansp3/logs/gfmrag_p2d_20261022_01/`。不公开原题、SQL、DB名、节点ID、逐题结果/响应或原日志。

## 执行、验证与计时

Prepare耗时62.60秒，无模型调用。合成Gate3/3 Set及Bag正确；互斥Smoke9次请求成功，可执行2/3、3/3、2/3，共7/9通过门槛，Set正确0/1/0，**仅为Smoke，不计30题结果**。没有根据Smoke调模型、参数、匹配或提示。

| 阶段 | 请求数 | CPU秒（父进程） | 阶段wall秒 |
|---|---:|---:|---:|
| 合成Gate | 3 | 8.689 | 17.428 |
| 私有3题Smoke | 9 | 7.365 | 20.830 |
| 正式30题Full | 90 | 10.593 | 130.405 |

三阶段实际receipt：[Gate](gate_a_receipt.json)、[Smoke](smoke_receipt.json)、[Full](full_receipt.json)。阶段wall包括生成及SQL/hash检查；全轮请求wall累计126.692秒，不能当作独占GPU计算时间。准备与阶段CPU计时不包括共享服务或SQL子进程全部CPU。

在项目根目录执行，原始配置/输入必须从上述执行源commit复现；**请用新的结果目录和run ID，不覆盖已归档运行**。私有端点/PID通过环境设置，且须核验本地服务身份；不从仓库复制个人服务地址。公开准备器支持`P2D_RESULT_ROOT`、`P2D_REPORT_ROOT`设置新的输出位置，准备器命令为相同环境下运行`scripts/text2sql/p2d_prepare_inputs.py`；保留其生成的独立冻结配置。实际执行命令（三次依次使用gate-a、smoke、full）如下，机器环境完整前缀及路径已保留：

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
OPENBLAS_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3 \
  scripts/text2sql/p2d_sql_context_eval.py \
  --stage full \
  --expected-commit 33c6a216a5a3b70d61b52badb529ba9f86ebcad7 \
  --result-root /mnt/liansp3/sources/results/gfmrag_p2d_sql_utility_20261022_01
```

数据由已有合法本地BIRD/P2c-R资源提供，不随仓库上传。新机器还需先按仓库规范准备源缓存及19题私有绑定产物；输入/权重/DB哈希不符时执行器会停止。执行器要求远端main仍指向所登记源commit；报告归档后main已前进，**上面是原始运行记录而非可直接覆盖重跑的命令**。独立复现须在新的已发布执行登记中指定当时commit、run ID和输出目录，保留同一科学配置。

真实调用前按协议完成223项定向测试（含91项只读SQLite合成测试），全部通过4.92秒。正式后没有修改评测规则或重算冻结主指标。另从保存的结果行重算计数/三对臂配对表，并核对102条真实响应usage与共享账本、99条冻结消息、预测封存SHA、源码/输入/DB SHA；均一致，DB前后未变。见[验证结果](verification_summary.json)及[重核脚本](audit_saved_artifacts.py)，重核脚本不调用模型或重执行SQL，需私有原产物，使用同一冻结比较器，**不等于独立官方评测器验证**。

## 指标定义、配对差异与分层

只读SQLite采用mode=ro&immutable、query_only、AST+authorizer检查，隔离worker硬超时10秒，单结果50000行/64MiB，SQLite硬堆256MiB；不是针对恶意DB的OS沙箱，Python对象/解析内存不属于SQLite堆上限。Set忽略行序及重复，Bag保留重复，列投影顺序固定；空结果也要求列数相同。整数及任一侧为整数时严格相等，浮点对浮点rel1e-6/abs1e-8；非精确匹配超过500行比较记未知。NULL/字符串精确。

| 配对Set结果 | 双方正确 | 左独有正确 | 右独有正确 | 双方确认错误 | 至少一侧未知 |
|---|---:|---:|---:|---:|---:|
| E0 vs E1 | 6 | 1 | 1 | 9 | 13 |
| E0 vs E2 | 7 | 1 | 1 | 10 | 11 |
| E1 vs E2 | 7 | 0 | 0 | 11 | 12 |

E0→E2只变文本内容，E2→E1再变节点装包。E0/E2相同8正确并非逐题一致：共同可判19题有1救回/1损坏，其余11未知。E1/E2共同可判18题无独有正确，其余12未知；E2总确认数多1来自未知配对，不是可判对中的已证实救回。不能从这些数推出值信息一定有益/可删。

| 分层 | N | E0确认Set | E1确认Set | E2确认Set | 未知 E0/E1/E2 |
|---|---:|---:|---:|---:|---|
| 原19优先题 | 19 | 5 | 4 | 5 | 10/10/9 |
| 严格匹配对照 | 11 | 3 | 3 | 3 | 1/2/1 |
| 绑定支持 | 9 | 3 | 2 | 3 | 4/4/3 |
| 绑定不一致 | 8 | 1 | 1 | 1 | 5/5/5 |
| 绑定未解析 | 2 | 1 | 1 | 1 | 1/1/1 |
| 覆盖rescue | 6 | 0 | 0 | 0 | 4/4/4 |
| 覆盖unchanged | 24 | 8 | 7 | 8 | 7/8/6 |

匿名DB的确认Set计数：db_01(N15)=3/3/3，db_06(N3)=0/0/0，db_02(N5)=2/2/2，db_05(N2)=1/1/1，db_10(N5)=2/1/2；其余分母/未知详见完整汇总。优先组执行/比较可用性更低、未知更多，且含4题参考策略拦截；不能由本轮指标单独判断题目难度差异，也不能外推总体风险。覆盖rescue6题无确认正确，4题未知，不能说覆盖收益必然无效。

AST诊断：direct Literal集合相同 E0=10/26、E1=10/28、E2=10/26；direct Column/Literal pair相同5/16、5/15、5/17；谓词类型集合相同22/30、23/30、21/30。原19题Literal集合相同1/15、0/17、0/15，Column/Literal pair均0（分母8/8/9）。Literal/pair分母取各自可解析/可绑定项；谓词类型按全部30题报告确认相同数，未解析不计相同。这些不是统一语义正确率；SQL执行可正确而AST常量/谓词表达不同，因此不能把集合不同直接称值错误。

## 失败案例类型与未知审计

| 生成执行失败类型 | E0 | E1 | E2 |
|---|---:|---:|---:|
| SqlGlot解析失败 | 4 | 2 | 4 |
| SQLite执行错误（未留原错误文本） | 5 | 7 | 3 |
| 保守AST策略拦截 unsafe_sql | 2 | 3 | 3 |

4题参考SQL均因**时间函数带非字面量参数**（如列表达式）被冻结安全策略拦截；这是评测覆盖不足，不能称参考SQL错误或恶意SQL。原策略仅接受显式时间字面量以避免now/时区不确定性，限制过严；对应预测在各臂同样不可执行，均保留未知。其余未知分别为预测不可执行且参考可执行7/8/6。没有超时/行数/字节/内存或浮点匹配上限导致未知，没有运输/计量失败。

可执行仍不正确为11/11/12题，说明通过工程门不代表正确生成。当前错误回执仅保留通用错误类型，不能据此断言具体“缺列/表名/连接错误”；不为补解释偷偷修SQL、重跑或覆盖错误。公开失败分析提供类型和分母，不发布题目或SQL。进一步题例分析需基于私有封存预测，人工判定与AST判断分开记录。

## Token、费用与可复现边界

全轮（3合成+9Smoke+90Full）**输入103,762 / 输出6,193 / 合计109,955 token，102请求，未知0**。Full输入95,123/输出5,516；9次Smoke输入8,302/输出643；合成输入337/输出34。全部来自真实usage并逐请求入账，无估计token冒充真实值。

[账本快照](usage_snapshot.json)：跨项目已登记确认输入150,438,723/输出23,737,372/总174,176,095，未知45请求。并行任务会继续增加累计；这是报告快照，不冒称供应商账户全部消费。跨项目已知usage按公开价格估算**CNY23.6301330**，277条有价、32,934条确认usage未定价，实扣未核实，未知usage/折扣不计入确认估价。

本轮**外部API费用CNY0.00**；本地共享GPU计算货币成本未定价，GPU compute秒无法分摊，不声明总资源成本为零。此次没有使用外部报价模型，因此无新付费价格快照。实际请求wall126.692秒，不能直接换算GPU秒或费用。跨项目费用也不包括所有本地硬件成本。

## 保留/停止与下一份指导

保留冻结模型、输入、所有正确/失败/未知产物及P2c-R离线覆盖结论；**不升级为V01默认方案**，不以本轮8/7/8证明Values安全或必要。无holdout、无独立种子/服务运行复现、无完整PK/FK，30题人为风险筛选、11对照不完整配对；单次共享服务seed也不保证跨运行比特一致。

本轮已达到一次Pilot停止条件，不自动扩到1534题或增加模型/调提示。下一份研究指导应先决定：是否把时间函数评测覆盖作为独立工程修订并基于已封存预测另登记评测，以及如何补19题独立人工必要性审核。修订必须另有版本和结果，不能回改本轮主指标。G0未运行，FK/Role Gate仍NO-GO，未产生新GNN或Jev性能结论。
