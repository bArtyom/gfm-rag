# 五种 Steiner 求解方法：固定图与问句权重下的配对实验

2026-11-09（UTC+8），exploratory，运行ID `steiner_five_solvers_bird_20261109_01`。**全部五种方法、两种权重设置均完成1534题；DP和MILP达到相同最优连接代价，但没有提高参考表完整覆盖。问句加权组Kou与Mehlhorn均1238题，DP/MILP均1236题。**

## 问题、授权和停止边界

用户明确追加要求比较最短路径贪心、Kou/KMB、Mehlhorn、Dreyfus–Wagner和整数规划。唯一问题是：同种子/图/权重下，求解器是否改变连接代价和选表覆盖？两者分别报告。此前问句权重公式升级失败的结论不变；本轮是新授权的有限算法诊断，不继续调公式/种子/模型。

主层两组：所有边权1，以及冻结上一轮cost=1+(1-cos)/2的问句权重。每组五种指定算法，top3种子和图完全一致。先每组5道label-blind smoke（25solver calls），只以工程正确性允许全量，不用5题覆盖率择优；随后两组各1534题/7670次真实求解，共15340次全量调用，另50次smoke。没有求解器缓存或跳过重复种子组合。执行顺序按问题轮换。

预算每组1800wall秒、CPU<=4线程、HiGHS1线程、RSS目标<4GiB、每MILP组件10秒；失败/哈希漂移/未证最优即保留现场并停止，不自动替换DP。成功判据：严格降低图代价为算法信号，参考完整覆盖净救回为任务代理信号。无论正负，两组完成后停止，不追加SQL/GPU/训练/数据集/参数搜索。

## 输入、仓库与实际实现

- 归档只进入用户仓库 `https://github.com/bArtyom/gfm-rag`，分支 `research/steiner-five-solvers-20261109`。本地base24f7b8d0519676f9b95a963a6c67df15f072f040，对应公开parent4030164e73203dda83fdd48dbdd022de746f2eef。执行source `99cfc79d4469f2e75ce60b0e86ebadda5c6be293`；最终归档额外包含核验与报告。
- 已读根README、text2sql README、experiment-roadmap、reproducibility-contract、前两求解器和问句加权报告与入口。旧维度/GFM/监督角色Gate不重开；不是完整GRAST/GFM复现。
- 数据BIRD-dev1534题/11库、同一archive-aligned SQLite，题/schema/十一DB哈希和缓存身份锁在[独立配置](../../../../../configs/text2sql/steiner_five_solvers_bird_20261109.json)。该开发集已多次探索，不能称独立测试或泛化证据。
- 复用旧Qwen3-Embedding0.6B query/table向量及上一轮105条FK向量，未运行新模型。相同question-only输入，不新增evidence/生成业务角色。表图75节点/74非自环表对边，完整105外键约束保真；并行关系取min(cost,ID)用于求解，复合FK列对不拆。按真实连通分量返回森林，全部分母保留。
- 每组Mehlhorn逐题种子/表/边/约束ID/代价完整回放上一轮结果，一致1534/1534。不修改原始图、数据、缓存或旧结果。
- 五种实现位于 `scripts/text2sql/extended_steiner_solvers.py`。贪心从最小种子ID开始，multisource Dijkstra最近接入，之后MST剪枝；Kou、Mehlhorn分别显式使用NetworkX对应method；DP复用已有子集递推。
- MILP以无向边二元变量x和双向连续流f建模：最小种子发k-1单位，其余种子各收1，非种子守恒，f<=（k-1）x；目标sum(weight*x)。SciPy自带HiGHS，presolve、mip_rel_gap=0、time_limit10s、threads1。仅status0、零gap、有限对偶界且原始可行性/整数性/重建代价一致才记最优。所有证明为求解器数值容差内证书，并由k<=3距离/汇合点最优值交叉核对。
- 环境think2sql_20260909，Python3.12.14/scipy1.16.3/networkx3.6rc0/numpy2.2.6/sqlglot28.0.0。未安装或升级依赖；highspy/pulp/ortools/Gurobi不需要。HiGHS threads选项经SciPy passthrough，只过滤该已知转发warning。

## 覆盖率结果

| 方法 | 不带权完整表覆盖 | 问句加权完整表覆盖 |
|---|---:|---:|
| 最短路径贪心 | 1236/1534（80.57%） | 1235/1534（80.51%） |
| Kou / KMB | 1238/1534（80.70%） | 1238/1534（80.70%） |
| Mehlhorn | 1236/1534（80.57%） | 1238/1534（80.70%） |
| Dreyfus–Wagner DP | 1236/1534（80.57%） | 1236/1534（80.57%） |
| MILP / HiGHS | 1230/1534（80.18%） | 1236/1534（80.57%） |

这是参考SQL所需表完整覆盖，不是SQL执行准确率或JOIN角色正确率。各算法输出表数略有不同；本轮固定的是问题/种子/图/代价，未匹配表数或token预算，不能把覆盖差异解释为同预算生成收益。

## 连接代价、最优率与时间

不带权：

| 方法 | 全量连接总代价 | 达到独立最优值的题数 | 平均表数 | median ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| 最短路径贪心 | 3209.000000 | 1532/1534 | 3.2738 | 0.274 | 0.446 |
| Kou / KMB | 3221.000000 | 1520/1534 | 3.2816 | 0.402 | 0.581 |
| Mehlhorn | 3220.000000 | 1521/1534 | 3.2810 | 0.406 | 0.596 |
| Dreyfus–Wagner DP | 3207.000000 | 1534/1534 | 3.2725 | 0.389 | 0.735 |
| MILP / HiGHS | 3207.000000 | 1534/1534 | 3.2725 | 1.606 | 2.294 |

问句加权：

| 方法 | 全量连接总代价 | 达到独立最优值的题数 | 平均表数 | median ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| 最短路径贪心 | 4204.653878 | 1530/1534 | 3.2731 | 0.280 | 0.446 |
| Kou / KMB | 4213.510360 | 1525/1534 | 3.2777 | 0.413 | 0.591 |
| Mehlhorn | 4213.510360 | 1525/1534 | 3.2777 | 0.411 | 0.597 |
| Dreyfus–Wagner DP | 4203.314485 | 1534/1534 | 3.2725 | 0.397 | 0.742 |
| MILP / HiGHS | 4203.314485 | 1534/1534 | 3.2725 | 1.613 | 2.361 |

代价只在同一权重设置内比较，不能直接跨两表比较数值。两精确算法全部1534题均等于独立oracle；每组1507次非平凡MILP组件调用全部status0/零gap，无超时，27题的种子彼此孤立无需MILP调用，按构造得到零代价森林。每组252题森林保留在覆盖分母。

时间是本机小图/k3上的单次wrapper耗时，包含规范化、剪枝和证书检查，不代表一般大图性能。HiGHS约1.6ms中位，DP约0.4ms；不能据此推断MILP在所有问题上更慢或DP可扩展到很多种子。

## 配对差异与机制解释

- 问句加权时Kou与Mehlhorn逐题节点/约束/代价完全一致。DP和MILP也逐题选表一致，均在9题比Mehlhorn更便宜，但修复1题、退化3题，净-2（-0.13pp）；描述性DB聚类95%区间约[-0.571,+0.185]pp。图目标优化成功不等于必要表覆盖改善。
- 不带权DP与MILP逐题代价相同，但34题选择了不同的同代价最优表集合。MILP相对Mehlhorn的8修复/14退化都来自同代价选择；它不是没求到最优。DP较Mehlhorn便宜的13题没有覆盖变化。
- 不带权Kou比Mehlhorn净多覆盖2题，3修复/1退化均来自等代价的路径选择；它还在另一题多花1条边而不改变覆盖。因此不能把这2题解释为更好的目标优化。
- 贪心在不带权1532/1534达到最优值，在加权1530/1534达到最优值；覆盖没有稳定优势。由于图小、种子少，简单方法已很接近精确代价。以上是本样本观察，不是对任意图的最优保证。

详见[配对/代价分层分析](mechanism_analysis.json)，所有方法的按库统计与描述性区间在[完整聚合](aggregate_summary.json)。当前证据支持把后续分析重点放在代价目标与必要表覆盖的对应关系及等价路径选择，不能仅以“算法更精确”预期SQL更好；本轮不自动启动新方法。

## 验证、异常与局限

44项去重针对性测试通过，包含32个小图穷举子案例（旧20+新12）；独立代码审阅无阻塞项。两组1534题/7670输出各自核验PASS，总15340输出，检查全量身份、缓存/DB哈希、独立dot评分/种子、FK代表、森林连通性、每个方法图代价、独立k<=3最优值、MILP记录证书、覆盖配对/表列数/时间聚合、旧Mehlhorn回放。核验复用固定loader和参考SQL parser，不重新求解，也不重建完整MILP流向量；求解时已对流原始解验证可行性与整数性。并未宣称完整仓库测试通过。

两组预测SHA见[复现manifest](reproduction_manifest.json)，预测先封存，后提取参考表评价；未用gold或SQL影响路径。原始输入未变。正式运行无失败/超时；最初metadata-only检查缺LAB_ROOT，补齐后成功，尚未运行模型/实验。测试先观察缺模块失败，再实现并通过。

审阅指出一个不影响本轮的通用边界：若将来允许零代价边，MILP可返回带无关零代价分量的最优解，当前重建会保守拒绝；本轮全部cost>=1，无此情况。保留为后续稳健性事项，没有为它改动已冻结实验或追加试验。

## 资源、命令、产物与费用

两组独立CPU会话并行，每组4线程、HiGHS1线程；初检192逻辑CPU、可用442GiB内存，4张4090均有其他负载，本实验GPU0秒。unit full wall14.55s/processCPU14.98s/peakRSS0.128GiB；weighted wall14.26s/processCPU14.92s/peakRSS0.123GiB，均远低预算。wall含数据校验、评价和报告聚合；不是求解器纯速度。

```bash
export LAB_ROOT=/path/to/lab-root
export CUDA_VISIBLE_DEVICES=''
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
# Use the actual Python executable from think2sql_20260909 if bare python resolves elsewhere.
conda run -n think2sql_20260909 python scripts/text2sql/run_steiner_five_solvers.py \
  --config configs/text2sql/steiner_five_solvers_bird_20261109.json \
  --setting unit --mode smoke --output ai_temp_code/five_solvers_unit_smoke_001
conda run -n think2sql_20260909 python scripts/text2sql/run_steiner_five_solvers.py \
  --config configs/text2sql/steiner_five_solvers_bird_20261109.json \
  --setting unit --mode full --output results/steiner_five_solvers_bird_20261109_01/unit_full_001
conda run -n think2sql_20260909 python scripts/text2sql/verify_five_solver_outputs.py \
  --config configs/text2sql/steiner_five_solvers_bird_20261109.json \
  --output results/steiner_five_solvers_bird_20261109_01/unit_full_001
# Repeat for --setting weighted and distinct weighted_smoke/full output directories.
```

所有输出目录独占创建，复现须使用新目录，不覆盖旧结果。每个run_start.json保存实际命令、解释器、代码版本、依赖、环境和硬件。原始私有输出在`results/steiner_five_solvers_bird_20261109_01/unit_full_001`和`weighted_full_001`；smoke在ai_temp_code，日志在`logs/steiner_five_solvers_bird_20261109_01`。不上传题目、SQL、逐题节点/约束选择、向量或日志；公开协议/实现/配置/聚合/哈希。

本轮模型请求0，输入/输出/总token0/0/0；外部API费用0CNY，本地CPU未折金额。累计共享账本只包括已登记请求，[快照](usage_snapshot.json)区分已定价估价、未定价和未知usage；实际账单未核实。上一轮1700embedding token属于历史成本，不在本轮重复计入。

## 完成决定与来源

用户指定的五方法均实际运行，精确结果已交叉核验。覆盖没有显示稳定算法优势，按协议conclude，不继续新增求解器、种子、权重、模型、SQL或GPU实验。报告在本分支提交后通过GitHub读回核对；本地执行commit与同树归档commit分别记录，不把本地文件冒称已上云。

接口依据（核验2026-11-09；运行依赖以固定版本为准）：[SciPy milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)、[NetworkX Kou/Mehlhorn](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.approximation.steinertree.steiner_tree.html)。MILP流模型及贪心实现为本项目独立代码；没有下载第三方求解器源码。
