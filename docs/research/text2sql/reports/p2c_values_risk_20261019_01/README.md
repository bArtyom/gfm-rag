# P2c-R 后续：Values 词面信息暴露风险审计

**一次5题Smoke及一次1534题Full均完成；冻结规则发现407/1460题有Values词面线索，其中19题至少一个相关常量也未出现在问题/evidence中。V01保留为离线候选，进入语义复核准备。** 本轮为exploratory风险诊断，未测SQL准确率，也未认定任何Values字段为语义必需。

## 研究问题、依据与停止决定

唯一问题是：参考SQL中的直接数据谓词常量，是否只出现在V00已返回节点的Values字段中，并在V01实际返回的短文本中消失？此前[P2c-R全量实验](../p2c_r_recovery_20261019_01/README.md)在1024预算下Complete覆盖提高10.96pp，但这不能回答下游值信息是否保留。本审计依照其H2成功分支，补充这一关键风险的词面证据。

指导提交`3a72c13b3054951f13dfc6a7fc56422e225365c1`；运行前阅读项目README、研究README、experiment-roadmap、reproducibility-contract、P2c-R协议与结果。协议为[计分前登记](../../plans/p2c_values_risk_audit_20261019.md)，执行源为`9f1ac0e71b8b5bc1fe9fda8381b0281dcdd72222`，分支main。上游来源RManLuo/gfm-rag，项目使用现有公开代码及本地增量；原实现与历史结果未覆盖。

层级：最小信息风险诊断，非新增方法主实验。预算固定为一次前5题Smoke+一次1534题Full，无重试；每阶段300 process CPU秒、8线程、4GiB RSS；模型前向/API/GPU/SQL执行均0。工程成功要求输入/源码哈希、顺序、落盘和分母一致，Smoke解析5/5、Full解析至少95%。任一工程错误或超限立即停止，完成一次Full也停止；不根据观察结果调整规则或扩大扫描。

**本轮决定：保留离线覆盖结果，停止实验扩展。** 全量已完成，准备了19条本地优先人工复核模板，人工复核=0、语义必要性判断分母=0；下一步需复核业务值绑定并确定固定Generator、Selector及独立数据库验证方案，再考虑SQL EX实验。没有新增LLM/GPU任务排队。

## 数据、规则与环境

沿用BIRD dev同1534题/11库、873候选节点（75表/798列）和P2c-R Full逐题输出。主要暴露分母1460题；74道Column不可评题只用于解析质量检查，不代表无风险；固定非饱和子集706题。只审计1024预算的V00与V01，不重新编码、评分或装包，不改变原排名或H1/H2。没有随机抽样、训练或解码，本轮seed不适用，Smoke固定前5题。

输入为已冻结R0/R1文本、旧选择及原BIRD dev参考SQL/question/evidence。Gold只用于事后风险分析，不进入检索或Context构造。原query JSON SHA=`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；P2c-R aggregate SHA=`7e4ce4b2a92df5e17160bb2429402b66ab7caec521c6e4da9ec90abd108e8fdc`、private rows SHA=`99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff`。其他输入及P2b向量缓存/manifest哈希见[配置](experiment_config.json)和[回执](run_receipt.json)；已有模型与tokenizer版本沿用P2c-R冻结manifest。仅本地tokenizer校验需要读取模型目录，未加载权重。

SqlGlot按SQLite解析，只保留含列引用的直接谓词Literal，沿途仅允许负号、括号、Tuple。排除LIMIT/OFFSET、常量对常量谓词、函数参数/计算表达式、空串和带通配符的LIKE模式；不推断编码映射、同义词或函数语义。文本用NFKC/casefold/空白归一和边界匹配，数值符号保持一致，不跨节点拼接。

标记要求同一Literal命中V00已选节点被移除的Values字段，且既不命中V00这些节点保留的非Values文本，也不命中V01任何已选短文本。问题/evidence可见性另列；命中Gold Column只表示该Schema列参与SQL，不代表该Literal绑定到此列。

环境think2sql_20260909：Python3.12.14、NumPy2.2.6、Transformers4.57.1、Tokenizers0.22.1、SqlGlot28.0.0。复用既有数据/模型/环境，没有下载或安装。主机192 CPU线程、503GiB RAM，启动前可用445GiB RAM/约115TiB磁盘；4张RTX4090未用于审计。完整命令和8线程/禁用GPU环境变量见[Full回执](run_receipt.json)与[Smoke回执](smoke_receipt.json)。公开脚本为`scripts/text2sql/audit_p2c_values_risk.py`。

命名沿用工作区日期2026-10-19；本轮Full实际UTC为2026-10-19 01:23:22至01:23:35，以进程回执为准。此前P2c-R回执有其独立UTC时间，不改写历史记录。

## 结果

1534/1534参考SQL解析成功（100%），无解析失败；1374题提取到至少一个注册规则内常量，其中Column可评1314题。总共提取2334个按题去重的直接谓词常量。工程门全部通过。

| 范围 | 题数/主分母 | 有词面线索题 | Literal线索数 | 至少一个线索也不在问题/evidence中 |
|---|---:|---:|---:|---:|
| 主分母：Column可评题 | 1460 | 407 (27.88%) | 548 | 19 (1.30%) |
| 固定非饱和子集 | 706 | 223 (31.59%) | 314 | 17 (2.41%) |

407题中388题的所有已标记常量仍能在问题/evidence中找到；其余19题涉及21个未找到的常量，优先安排人工复核。19题全部至少有一个对应Schema节点仍被V01选择，因而需检查Values内容移除而非仅节点缺失；其中10题的同一未见常量命中了Gold Schema列的Values字段。**这10题仍不是已经确认的SQL列值绑定或语义损害**；其余9题也不能凭此排除风险。

全部407题中375题至少一个标记命中Gold Schema列；407题均至少有一个匹配节点仍被V01选择。以上是题级“至少一个”计数，不能解释为全部548个标记的逐条性质。

| 原P2c-R覆盖分层 | 题数 | 有词面线索题 | 至少一常量也不在问题/evidence |
|---|---:|---:|---:|
| rescued | 162 | 62 | 6 |
| damaged | 2 | 1 | 0 |
| unchanged | 1296 | 344 | 13 |

覆盖被救回的162题中有62题伴随词面线索，6题也有输入不可见常量。这表明节点覆盖增益与值信息变化可以同时存在；不能从该共现推断因果或SQL准确率方向。匿名11库汇总见[完整聚合](aggregate_summary.json)，不把不同库的总题数误当作Column风险分母。

## 运行、验证与异常

| 阶段 | 样本数 | CPU秒 | Wall秒 | 峰值RSS GiB | 状态 |
|---|---:|---:|---:|---:|---|
| Smoke | 5 | 10.875585 | 11.030989 | 0.864250 | PASS，仅工程检查 |
| Full | 1534 | 12.322502 | 12.485752 | 0.861168 | PASS，词面审计 |

两阶段同一发布提交、8份源码哈希和输入/依赖版本；合计CPU23.198087秒、Wall23.516741秒。两个运行均无失败/重试。运行前108项定向测试通过；静态复核发现的函数参数和数值正负号边界已用先失败后通过的合成回归修复，均发生在读取本轮样本之前。不存在观察Full结果后的匹配规则修改。

独立[产物验证](verification_summary.json)从1534条已持久化私有trace重计548个Literal标记；全体/1460/706、11匿名库及rescue/damage/unchanged分层完全一致，聚合/逐题hash与8份执行源hash匹配，原P2c-R两份产物hash未变。公开内容隐私扫描通过。验证器[verify_artifacts.py](verify_artifacts.py)只重计标记和检查契约，不独立认定匹配语义正确。

Full aggregate SHA=`e81a1d7fca13209a0aafa33d612e4a6f05290678f49e8d78fdf7a01c9e3efcb4`；私有trace SHA=`66b38471056efc084c0af80d0dca99aaff5dca47df51aba985ddce52ea8ea7a9`。本地结果：`/mnt/liansp3/sources/results/gfmrag_p2c_values_risk_20261019/full_1534_20261019_01`；优先队列`human_review_priority_private.json`只保存定位和空白复核字段。日志位于`/mnt/liansp3/logs/gfmrag_p2c_values_risk_full1534_20261019_01.log`。Smoke目录`/mnt/liansp3/sources/results/gfmrag_p2c_values_risk_20261019/smoke_5q_20261019_01`。公开材料只含代码、规则、匿名汇总及回执，不上传参考SQL、Literal原文、逐题ID、数据库名、节点ID或原始日志。

## 结论与局限

P2c-R的Schema覆盖成功保持成立。本轮发现冻结规则可见的Values信息移除线索，不能把缩短Context描述为已证实的下游信息无损。V01仍是离线候选；19条输入不可见线索可提高人工复核的信息量，407题不等于407题SQL受损。

词面归一可能合并大小写/Unicode等差异，通用数字也可能巧合命中无关列；未做Literal到SQL列的绑定，未推断业务编码。被排除的计算、模式、函数、隐式类型和语义等价关系未覆盖；零标记题不代表安全。输入中能看到常量也不保证映射关系足够。BIRD dev是已观察的探索集，没有独立数据库泛化证据或SQL EX，人工语义复核尚未进行。

本轮API输入/输出/总token=0/0/0，未知用量请求=0，外部API费用CNY0.00；本地模型前向/GPU/SQL执行=0，不将CPU资源费用计作供应商账单。[共享账本快照](api_usage_snapshot.json)累计已确认输入4,081,634/输出198,230/总4,279,864 token，未知用量请求14；已有单价用量按公开价估算CNY8.5232850，42个已知用量但缺价请求费用待核实，未核对实际扣费。账本仅覆盖已登记调用，其他项目并行调用不归到本实验。旧P2c故障记录、P2a/P2b原NO-GO、FK/Role门及历史复现边界均保持。
