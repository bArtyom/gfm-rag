# P2d 独立工程与SQL Pilot执行登记（2026-10-22）

依据main `d262043fbec5723d7bed7433d87bc556a753bc83`的[P2d上位协议](p2d_value_utility_and_sql_pilot_20261019.md)，以及用户再次明确“继续做实验”。已读根README、研究README、experiment-roadmap、reproducibility-contract、最新复核与P2d协议。沿用其唯一问题和E0/E1/E2定义，不重跑Embedding/规则网格。本轮为exploratory小样本诊断，非总体效能/独立泛化证明。

## 1. 人工标签边界与生成器

19题均登记semantic_review_status=unverified，人工审核0、必要性分母0、一致率/kappa不计算。依上位协议允许的例外**单独注册工程/SQL Pilot**；不以AST或模型标签冒充人工Gold。未运行32B辅助语义审阅。本仓库此前没有Text2SQL Generator运行记录，本轮显式建立首个固定普通LLM基线适配器，不冒称历史生成成绩或Jev结果。

核验既有本地共享vLLM服务的模型ID、权重路径、进程命令身份及32768窗口；使用已有Qwen2.5-Coder-7B-Instruct和同目录tokenizer，完整权重/配置SHA冻结。selector=none；temp0/top_p1/top_k-1/repetition_penalty1/seed20261021/maxnew1024，每题每臂一次。服务端点与PID仅私有.env/回执，不提交地址；不修改或停止服务所有者任务，不配置新服务/GPU，不回退外部API。各阶段开始及每个请求前核验服务身份。

## 2. 已冻结样本和输入

原19题全部保留（9绑定支持/8不一致/2未知），按原顺序。以DB、SQL Predicate类型集合、(Gold表数,Gold列数)、V00@1024 Complete进行**严格相同分层**，seed20261021固定无放回随机抽取匹配控制；未使用Generator或SQL EX结果。得到11对照、8题无严格匹配，不放宽匹配条件；正式N=30。另从剩余可评题中seed20261022冻结3题私有Smoke，与正式30题互斥。实际匿名配额、有序ID SHA及完整权重SHA见[sample_registration.json](../reports/p2d_sql_utility_20261022_01/sample_registration.json)。

完全复用P2c-R V00/V01@1024已落盘节点ID及顺序：E0=V00/R0；E1=V01/R1；E2=V00/R1。E0/E2节点序列相同，Question/Evidence/System模板各臂相同。只序列化原节点文本，自带表列归属，不引入Gold、样本值、额外FK或修复提示。原节点没有可信完整PK/FK约束且FK Gate仍未过，因此**不额外补DB约束**；该限制明确保留，避免混入新的信息因子。原embedding tokenizer1024预算保持，另外用Generator tokenizer计完整Prompt长度；不得把总Prompt或E2预算误当重新装包后的1024。

Prepare对原P1.6输入manifest、BIRD原文/Schema、P2c-R聚合/逐题、19题绑定产物、DB前置SHA、R0/R1文本序列和7B权重均验明身份。输入/参考SQL分别存储，生成消息只由Question/Evidence/Context固定函数构造；正式预测全部封存后才执行该阶段参考SQL。参考SQL可在样本分层中用于Gold大小/谓词类型，但不进入任何模型消息。

## 3. 顺序、预算与工程判据

1. Gate A2：3个预定的简单合成题（COUNT/SUM/WHERE），一次生成并在新建合成SQLite上对照预定参考；三题Set/Bag均正确才通过。无BIRD题目或正式EX。
2. 私有Smoke：3题×3臂=9个请求，按题循环平衡臂顺序；成功计量且≥6/9 SQL可执行、每臂至少1个可执行才继续。不以EX正确率为门槛，不根据结果修改参数、Prompt、样本或规则。
3. Full：30题×3臂=90次请求；题内循环旋转E0/E1/E2顺序，全部预测/请求hash封存后才评测。单次Full后停止，不扩到1534或继续修Prompt。运输/usage缺失失败立即保留现场停止，0自动重试，比最早资源登记的“连续3错”更保守。

最多102模型调用（3合成+9Smoke+90Full）、真实输入≤1M、输出≤104448token、从Gate A开始≤5400秒；请求120秒、并发1。任何预算/源码/输入/服务身份漂移、覆盖风险或安全错误停止，无付费API fallback。每个实际请求用稳定call_id记录共享账本真实usage，含失败/未知，缓存明细不重复计费；不将本地估算token写成确认usage。

SQL执行在现有环境的隔离worker中，SQLite immutable+mode=ro、query_only、只允许单SELECT/WITH查询、AST/authorizer双检查，禁危险写操作/函数和非确定性时钟表达；硬wall10秒、每结果≤50000行/64MiB、SQLite硬堆≤256MiB，超限保留独立状态。原数据不复制，不覆盖；DB作为已哈希的静态只读快照访问，启动和完成后验证SHA不变，适用可信静态本地DB而非恶意文件OS沙箱。

复用既有think2sql_20260909、Python3.12.14/SqlGlot28，无依赖变动。主机初查192CPU/503GiB RAM、388GiB可用；后续每阶段重新检查。共享服务用GPU，但无法精确分摊GPU compute秒；报告本轮请求wall、共享GPU时间未知及GPU货币成本未定价，不声称本地推理免费或计算量0。外部API费用CNY0，未分配新GPU。

## 4. 指标与边界

主Set EX、辅Bag EX均按无序行、固定投影列顺序计算；整数及任一侧为int的混合数值严格比较，float-float仅rel1e-6/abs1e-8容差，NULL/字符串精确。>500行且无法精确匹配的容差比较记unknown，空结果比较仍要求列数相同。所有样本保留分母，生成/执行失败、参考不可执行和比较unknown分别报告；主表为“已确认正确/N”的保守比例，不把unknown称作已知错误。它是明确口径的BIRD-compatible比较器，不冒称完全复制官方所有实现细节。

记录direct Literal集合、direct Column/Literal pair与predicate类型集合的AST诊断和可评分母；这些是冻结规则内近似，不等于完整语义谓词正确率。按优先/对照、9/8/2、coverage rescue/unchanged、匿名DB分层，给三对臂的only/both/unknown配对计数、tokens/请求wall与错误类型；不作论文级显著性或独立DB泛化主张。

## 5. 交付与停止

独立报告`docs/research/text2sql/reports/p2d_sql_utility_20261022_01/`，结果统一入口`gfmrag_p2d_sql_utility_20261022_01`。代码/配置/协议先提交并远端核对，再允许模型调用；三阶段同发布代码和配置，完成后另提交匿名指标、回执、失败汇总与验证。原问题/SQL/响应/结果行、样本定位与原日志只在本机。G0本轮不启动。出现退化保留V01候选并分析；没有退化也不能证明安全。结束一次Pilot后做外循环总结，不自动启动新分支。
