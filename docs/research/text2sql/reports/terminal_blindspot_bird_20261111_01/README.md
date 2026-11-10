# 固定种子 Steiner 的可行域：底层诊断与残余语义原型

2026-11-11 UTC+8，exploratory。**完成BIRD1534题结构诊断和100题新原型试验。296个选表不完整案例中，126个缺表不可能靠固定种子重加权补回；新原型同预算覆盖78/100，与原方案和简单对照相同。严格可行域中的参考覆盖oracle也只有78/100，因此停止该原型，不追加全量/GPU/SQL。**

## 研究问题与分层记录

用户要求继续研究、有底层改进并做实验。核心研究问题是：失败究竟受路径评分限制，还是被固定种子及预算定义的可行域先行限制？这不是继续比较求解器精度。两层有限探索：第一层检查固定终端的结构支持范围；第二层只试一个残余语义选路候选，含三个公平对照臂。两份[结构诊断协议](../../plans/terminal_blindspot_20261111.md)、[原型协议](../../plans/residual_route_pilot_20261111.md)均在各自执行前提交。

结构层成功/分支判据是：若至少50%的不完整案例存在路径支持范围之外的必要表，优先改变种子；否则优先分析选路。实际42.57%未达阈值，按注册走选路分支。不能事后将126/296写成“大多数失败”。选路pilot要求残余法>=原方案且>=直接语义对照+2题，否则停止、不调参数。实际未通过。没有新的独立复现或下游SQL实验。

每阶段1800wall秒、8CPU线程、RSS目标4GiB；每个小图树目录上限100000。先5题工程smoke，通过数据/图不变量才扩大。两阶段都在约8秒内完成；没有资源错误、数据漂移、parse排除或模型调用。注册/修复/复核记录完整保留，不覆盖旧实验。

## 数据、代码与范围

自有项目bArtyom/gfm-rag，分支research/steiner-terminal-blindspot-20261111；本地basef103e2f对应公开parent712e874e24099d476cb3db218720f2589298abc5。已读根README及text2sql README、experiment-roadmap、reproducibility-contract和既有Steiner/SQL代码报告。原GRAST代码commit4c698cae仅作只读资源，无LICENSE，未复制或发布其源码。

数据沿用BIRD-dev1534/11库、75表节点/74非自环表对边，原始105条FK约束的复合键/平行关系身份保留；不是完整GRAST/GFM复现。题/schema、缓存、历史预测与11SQLite均有SHA核验；配置里的历史模型/服务字段仅作资源来源，不触发GPU或新推理。Qwen3-Embedding0.6B1024D query/column向量均复用旧缓存，未新编码；Qwen2.5-Coder7B tokenizer仅在CPU计数schema文本。数据已多轮探索，不能称独立测试集。

结构诊断source `adb6b68ec3e215ff46eb7a30b49e59a975e146ba`，选路执行source `7764afd0787a7630c98cb7d5fbc886b50e6b0616`；后续a3da3f8修复未执行的full模式门控并加审计，不修改预测或评分规则。最终归档代码使用stage_upgrade_gate，历史pilot用pilot_upgrade_gate；审计兼容两种字段。

## 第一层：固定终端的结构支持范围

定义H(T)为种子T自身，加上同一真实连通分量内任意两个种子之间所有简单路径的顶点并集。正边权下，经过非终端叶剪枝的Steiner森林不可能包含H(T)之外的表：树中任何非终端节点必须处于两个终端之间的路径上。此图论事实是已有知识，不作为新定理。

实现用双连通块/顶点关联森林，剪掉无终端支撑的叶，再展开活跃块。独立用all_simple_paths枚举真实173个不同(graph,seedset)组合，共3064条路径，逐一核对相同；另有40随机小图×4终端设置单元验证。森林图中路径唯一，无论怎么改正边权都不能改变最小终端连接结构。

| 结构观察 | 实际数量 |
|---|---:|
| 加权原方案完整表覆盖 | 1238/1534（80.70%） |
| 原方案不完整 | 296 |
| 不完整且必要表位于H(T)之外 | 126/296（42.57%） |
| 不完整、所有必要表仍在H(T)内 | 170/296（57.43%） |
| 路径并集与原方案表集合完全相同 | 799/1534（52.09%） |
| 问题所在数据库的表图为森林 | 636/1534 |
| H(T)完整覆盖参考表 | 1408/1534（91.79%） |

126类中118题有同种子连通分量的路径外缺表、8题有无种子分量缺表；原始缺表334次中145次在H(T)外。最后一行是**无预算、合并互斥路线的宽松支持上界**，不是某棵树可达到的覆盖，更不是SQL准确率。结构聚合字段名diagnostic_maximum_complete_rate按此上界解释。

## 第二层：残余语义选路原型

直觉是：三个种子已经解释了问句的某些内容，中间表应补充尚未解释的内容，而不是重复整体问句的主题。对每个种子选query最相关的列，构成小维数span；query和候选列均正交投影掉该span，再计算剩余余弦。query剩余范数<=1e-8才回退原始余弦。该投影/余弦不是新数学方法，也不保证得到真实语义需求。

固定原三个种子和FK图，精确枚举k<=3的所有无非终端叶森林：对每个分量取最小ID种子为根，枚举到其它种子的简单路径组合，只保留无环并集。任意最小终端树都能分解为这些根路径，因此包含全部相关候选。每题硬限制：表数<=原加权Mehlhorn，Qwen序列化schema token<=原加权Mehlhorn。三臂候选/信息/预算相同：

- frozen：旧加权Mehlhorn封存结果。
- raw：中间表最强列与原始query余弦最大，作为简单语义重排对照。
- residual：中间表最强列的残余余弦最大。

后两者都按旧加权cost、规范化边/节点稳定打破tie；无中间表评分0。原方案本身始终在候选集中。真实业务模型不新增关系、不读gold、不调参数。

100题以seed20261111/固定salt按11库轮转hash抽样，排除前次SQL实验133个不同问题；5题工程smoke是这100题子集。排除旧题不使其成为独立数据集，因BIRD-dev此前已广泛暴露。预测先seal，再读参考SQL评价完整表覆盖，解析失败0。

| 方法 | 完整表覆盖 | 选表总数 | schema token总数 | 相对frozen换表题数 |
|---|---:|---:|---:|---:|
| frozen | 78/100 | 329 | 52557 | 0 |
| raw | 78/100 | 329 | 52554 | 1 |
| residual | 78/100 | 329 | 52557 | 0 |

没有新的SQL执行准确率；表格不与前次SQL42/39/39混用。残余法对两个对照救回0/损坏0；完整性状态100题均不变。平均完整树目录5.13个，但同预算只有1.07个；只有1题存在不止一种可行表集合。因候选可行域几乎退化，本轮**不能据此证明残余语义表示本身无效**，只能否定此固定种子/预算原型的实际收益。无需显著性检验来包装零变化。

## 事后可行域分析：不是再扫评分函数

独立审计原始100题后，使用gold仅计算以下上界，未用于选路或重新发布方法结果：

| 参考表可完整容纳的条件 | 题数/100 |
|---|---:|
| 固定种子、最小终端树、原表数及token双预算 | 78 |
| 同上，仅取消表数上限 | 78 |
| 同上，仅取消token上限 | 78 |
| 固定种子最小终端树，取消两个预算 | 91 |
| 直接取参考表集合，检查原双预算是否装得下 | 93 |

22个原方案不完整案例中，13个在无限预算的最小终端树中可补全；15个参考表集合本身就装得进原双预算。最后一行同时移除固定种子和连接要求，不能把差异单独归因于其中某一个因素；也不是可部署oracle或另一种SQL语义真值。

这把研究问题推进了一步：**硬性保留种子并把整体schema限制为其最小连接树，会消耗可用预算；仅在这个可行域里提升评分精度，可能根本没有任务收益空间。** 原来的Steiner最优代价、参考表覆盖与SQL正确率是三个不同目标。

## 相关工作与下一步想法的边界

- [GRAST-SQL](https://arxiv.org/abs/2512.16083)已有列编码/图重排/Steiner连通性过滤；“图+连接器”不是新贡献。
- [Graph-Link](https://proceedings.mlr.press/v306/zhong26s.html)已将schema linking表述为带结构约束的子图诱导，用层级图与Steiner优化；不能把相同大框架宣称首次。
- [RoSL](https://aclanthology.org/2025.emnlp-industry.122/)已用问句分解提升schema召回；[双向schema linking](https://arxiv.org/abs/2510.14296)已有表/列两路检索。只加需求提取或两路融合不够构成创新。
- [EviLink](https://arxiv.org/abs/2605.29670)已有多SQL假设、schema不确定性和按需证据获取；“多假设+补证据”也不能单独当作新点。此处依据公开论文定位，未复现这些整套系统，也不比较其论文成绩。

下一研究候选是**根据可行域诊断，联合决定语义锚点与上下文预算**：语义需求作为待满足目标，种子表作为可撤销的grounding假设；区分只能改终端、可以换路径、需要重分配预算的情况。候选列/表按需求成组，选择与FK闭包token成本联合优化，允许替换冗余种子而不只扩表。核心可证伪预测：同预算且不给更多模型信息，应优于简单topK替换、PCST/分组Steiner和需求分解union，且收益集中于本轮识别的不可行/预算冲突层。

这是**尚未执行的新候选**，不是已经有效或已经证明创新的算法。PCST、group Steiner、需求覆盖本身均为已知概念；可行域诊断驱动的动作选择是否足够新，需要更细的最近邻审查以及正向机制实验。不能将本轮负结果包装为创新成立。当前停止GPU/SQL、残余评分调参和大规模搜索，先归档此有限发现。

## 验证、资源和异常

8项针对性pytest通过，包含160个随机envelope设置、对15个图种子中满足连通条件的图做边子集穷举catalogue oracle、断连/单种子、正交旋转不变性/回退和分阶段门控。不是全仓库测试。独立代码审阅发现full模式错误复用pilot门控，已修复为相对两个对照>=2pp且至少2库净正向；该模式未运行，无预测被回写。审计兼容历史/新版gate字段，审阅无其它阻塞。

审计PASS：预测seal/输入SHA/排除旧题、300组预算/选择、覆盖配对及oracle重算；选择几何用Gram伪逆独立重算，生产代码用SVD。树目录复用同一枚举器并逐树检查森林/终端/叶/真实边不变量，穷尽性由小图边子集测试提供，不能称独立实现了全部目录算法。tokenizer/serializer/reference parser共享，局限明确。私有日志保留最初缺模块RED测试、工程smoke及正常执行，没有运行中断或推理错误。

结构full wall8.32s/processCPU8.88s/peakRSS0.078GiB；routepilot wall7.72s/processCPU11.34s/peakRSS0.732GiB。无安装下载、新模型forward或GPU任务。本轮模型请求/输入/输出/总token均0，未知0，外部API0CNY；本地CPU资源未货币化。共享账本快照确认494,211,636token，未知108次；已有CNY定价部分公开估价24.0406214732928元，不含未登记/未定价/其它币种sidecar，实扣未核。详见usage_snapshot.json。

## 复现与产物

在项目根目录，复用sources索引提供的BIRD/cache/旧结果/tokenizer，设置LAB_ROOT后运行；独立环境think2sql_20260909/Python3.12.14，依赖见manifest。OMP/OPENBLAS/MKL线程8，TOKENIZERS_PARALLELISM=false、PYTHONHASHSEED=0。每次使用新输出目录，原始正式输出不覆盖。

```bash
export LAB_ROOT=/path/to/your-resource-root
conda run -n think2sql_20260909 python -m pytest tests/test_terminal_envelope.py tests/test_residual_routes.py -q
conda run -n think2sql_20260909 python scripts/text2sql/run_terminal_blindspot.py \
  --config configs/text2sql/terminal_blindspot_bird_20261111.json --mode smoke \
  --output ai_temp_code/terminal_blindspot_smoke_001
conda run -n think2sql_20260909 python scripts/text2sql/run_terminal_blindspot.py \
  --config configs/text2sql/terminal_blindspot_bird_20261111.json --mode full \
  --output results/terminal_blindspot_bird_20261111_01/full_001
conda run -n think2sql_20260909 python scripts/text2sql/run_residual_route_pilot.py \
  --config configs/text2sql/residual_route_bird_20261111.json --mode smoke \
  --output ai_temp_code/residual_route_smoke_001
conda run -n think2sql_20260909 python scripts/text2sql/run_residual_route_pilot.py \
  --config configs/text2sql/residual_route_bird_20261111.json --mode pilot \
  --output results/terminal_blindspot_bird_20261111_01/route_pilot_001
conda run -n think2sql_20260909 python scripts/text2sql/analyze_route_feasibility.py \
  --config configs/text2sql/residual_route_bird_20261111.json \
  --predictions results/terminal_blindspot_bird_20261111_01/route_pilot_001/predictions_private.json \
  --output results/terminal_blindspot_bird_20261111_01/route_audit_001
```

私有结果results/terminal_blindspot_bird_20261111_01/，日志logs/terminal_blindspot_bird_20261111_01/；smoke/debug在ai_temp_code/。统一入口sources/results/terminal_blindspot_bird_20261111_01。公开仅代码/配置/hash/匿名聚合，原题/SQL/逐题选择/向量/数据库均不上传。代码/报告按自有研究分支归档，提交后逐文件GitHub读回，commit与PR在交付消息/资源索引登记；未合并main。
