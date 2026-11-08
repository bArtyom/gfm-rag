# 两种 Steiner 求解器：Mehlhorn 与 Dreyfus–Wagner

**已完成：5题 smoke 与1,534题正式配对诊断。精确算法小幅降低连接代价，参考表完整覆盖未改变。** 本轮为用户明确要求的 exploratory 求解器比较；2026-11-09（UTC+8），运行ID保留20261108。旧两种子方法试验保持原结果与停止状态。

## 核心问题、预算和预设判断

唯一问题：固定相同种子和图，精确求解能否改善近似解的连接代价及找表覆盖？连接边权之和是主优化目标，参考 SQL 所用表的完整覆盖是次要任务代理；二者不可混为一谈。

只比较两个方法：NetworkX `method=mehlhorn` 与独立实现的 Dreyfus–Wagner 子集动态规划。两个实验组：top3语义表种子为主组；top2为最短路退化核对。两方法在各组接收逐题完全相同的种子、表图和单位边权。主层 exploratory，CPU<=8线程、RAM目标<2GiB、总wall预算300秒、每次求解事后检测5秒上限；不训练、不请求新模型、不运行SQL、不下载权重、不扩展第三个求解器。

预设：任一真实样本 exactcost<approxcost 即算算法层信号；参考表净救回>0才算任务层信号。工程失败、输入哈希变化、精确解不优于近似解、代价独立核验失败则停止。两个信号均不自动触发GPU或其他方法扫描。

## 实测结果

**三个种子主组，全部1,534题：**

| 方法 | 参考表完整覆盖 | 完整覆盖率 | 每题平均选表数 | 逐题连接边数之和 |
|---|---:|---:|---:|---:|
| Mehlhorn近似 | 1236/1534 | 80.57% | 3.2810 | 3220 |
| Dreyfus–Wagner精确 | 1236/1534 | 80.57% | 3.2725 | 3207 |

精确求解在13题（0.85%）上每题少一条连接边和一张中间表；其余1521题代价相同。13题只对应**一个数据库的六种不同种子组合**，不能视为13个独立结构例子。173种不同图+种子组合中六种有改进。被移除的13个逐题中间表出现均不在对应参考SQL表集合内，但完整覆盖没有任何题发生变化：救回0、损害0、不变1534。没有同代价但表集合不同的两算法输出。总连接代价减少13/3220=0.404%；这不是SQL准确率提升。

252题的种子跨FK图连通分量，输出明确森林；包括这些题在内，所有分母完整保留。全部1534题的参考物理表解析成功。

**两个种子核对组：** 两算法都是963/1534（62.78%），逐题连接总代价均1795、平均表数2.2901，所有1534题代价和表集合一致。184题为森林；132种不同图+种子组合。结果符合非负边权下双终端Steiner退化为最短路。此处的同分不提供新的跨数据库等价性结论。

本轮top2结果不能用来改写前次报告的949/1534。新比较对两方法统一使用规范化的数值表ID、排序后的种子/图插入顺序；旧GRAST包装器使用合成字符串ID和集合迭代顺序。等长最短路径可能选到不同中间表。两轮不是逐节点回放，也没有改变旧预测。跨轮的top2差异不构成求解质量提升；本轮的公平比较是同一组内两算法配对。

参考表覆盖的数据库聚类bootstrap区间为[0,0]，因为本样本每一题的覆盖状态都相同；不能据此证明其他数据库上的方法等价。top3相对top2覆盖较高同时增加了种子/表预算，不属于两求解器性能差异，也未做同token预算比较。

## 实际求解方法

Mehlhorn：在每个包含种子的真实FK连通分量上调用NetworkX近似算法，显式指定method；不吞掉求解异常。

Dreyfus–Wagner：状态D[mask,v]表示连接指定种子子集与v的最小代价。单种子状态初始化为最短距离；先在同一顶点合并两个子集，再沿最短路径松弛。存储子集分割和合并顶点，回溯恢复原图边，去环并剪掉非种子叶子，检查恢复代价等于DP最优值。本实现最多允许每个连通分量12个种子，本次实际<=3。

图为无向简单表图，只有声明式SQLite FK提供的边，边权全为1；自引用不用于连接不同表。平行/复合FK完整身份仍保留在共同元数据中；求解器比较不选择唯一业务关系角色。上下文定义沿用选中表的全部列和合法完整FK，边代价单列，不把序列化中所有FK条数当树的优化代价。

算法依据：[Dreyfus–Wagner原论文](https://doi.org/10.1002/net.3230010302)、[NetworkX文档](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.approximation.steinertree.steiner_tree.html)。已有GRAST checkout保持不变；本轮直接比较两个求解器，不调用其Steiner包装器。无第三方源码复制或新依赖安装。

## 验证与证据边界

先写测试观察失败，再实现求解器。带权合成反例：Mehlhorn=10，精确=9；另用20个小图的边子集穷举验证四终端DP，覆盖重建、零权、空/单种子、断开森林、顺序稳定、非法权重和输入图不变等。带权反例是算法正确性测试，不计入真实BIRD改进。

5题smoke包含每题两个组×两个方法，共20次求解，全部连接/独立代价检查通过；两个组内各方法完整覆盖分别3/5和2/5。smoke只用于工程验证，未加入正式全量计数。

全量为3068个配对实例、6136次求解。每题精确代价用独立恒等式再次核验：两个终端取最短路；三个终端取所有候选汇合点到三种子的距离和最小值。断开时逐分量计算，不伪造跨分量路径。独立读回封存输出，再次验证6136个解的真实边、种子、无环性、连通性、代价及全部DB哈希，全部通过。封存SHA256：`3c57c6a40f1d2f9c199208fb9dcbaf122890738465e706ed65b2e7cdab793b43`。

相关测试119项、20个穷举子测试通过。独立代码审阅未发现阻断问题。全仓pytest仍在收集阶段因已有环境缺少torch_geometric和omegaconf而失败，分别为tests/test_gfmrag_retriever.py和tests/test_pretrained_dataset_config.py；未修改稳定环境或声称全仓通过。

## 版本、数据、资源与命令

项目归档：bArtyom/gfm-rag，独立分支research/steiner-two-solvers-20261108，基于前次公开commit78992d461c1e37264b8e626ed08291350bb03c9a。已阅读仓库README、研究入口、experiment-roadmap、reproducibility-contract、前次报告及配置/调用链。实现与全量执行源为本地commit090aa03；远端归档若由连接器创建等内容提交，其SHA与本地源分开记录。

复用冻结P1.6 Qwen3-Embedding-0.6B 1024维缓存，未重新编码。缓存、问题、schema、节点清单哈希与前次相同；本轮额外强制校验缓存源回执与身份清单哈希。数据库复用既有bird_dev_aligned_qes_20261012副本，含全部11库冻结哈希；没有覆盖共享源或此前异常student_club文件。所有配置见configs/text2sql/steiner_two_solvers_bird_20261108.json。

环境：现有think2sql_20260909，Python3.12.14、NetworkX3.6rc0、NumPy2.2.6、SQLGlot28.0.0，未升级任何依赖。启动检查192逻辑CPU、约440GiB可用RAM、4×RTX4090均有其他模型占用；本轮CPU-only。固定PYTHONHASHSEED=0，OMP/BLAS/MKL=8；两算法调用顺序按题号和种子数平衡。没有单侧缓存，相同种子重复出现也分别求解。

正式wall12.523秒、进程CPU12.912秒、峰值RSS0.0791GiB（不含外部资源检查子进程）；GPU0秒。新模型输入/输出/总token0/0/0、外部API费CNY0.00；本地CPU成本未折算金额。

三个种子时，Mehlhorn/精确的逐次包装器中位耗时0.417/0.404ms，p95为0.605/0.749ms；两个种子中位0.350/0.324ms。包装器包含规范化、DP/近似求解和局部校验；不同图太小，这些亚毫秒测量不能支持一般速度优劣或大图扩展性结论。超时检测发生在调用返回后，不能打断卡死求解器；本次所有调用正常结束，没有触及预算。

设置LAB_ROOT和已有环境的绝对PYTHON_EXECUTABLE后，在项目根执行，输出目录必须不存在：

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 \\
conda run --no-capture-output -n think2sql_20260909 "$PYTHON_EXECUTABLE" \\
  scripts/text2sql/run_steiner_two_solvers.py \\
  --config configs/text2sql/steiner_two_solvers_bird_20261108.json \\
  --mode smoke --output ai_temp_code/two_solver_smoke_REPLAY

PYTHONHASHSEED=0 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 \\
conda run --no-capture-output -n think2sql_20260909 "$PYTHON_EXECUTABLE" \\
  scripts/text2sql/run_steiner_two_solvers.py \\
  --config configs/text2sql/steiner_two_solvers_bird_20261108.json \\
  --mode full --output results/two_solver_full_REPLAY
```

本地私有正式产物：统一结果入口steiner_two_solvers_bird_20261108_01/full_001，包含run_start、private_predictions、prediction_seal、private_input_receipt和聚合；日志在项目logs/steiner_two_solvers_bird_20261108_01；smoke在ai_temp_code。完整绝对入口由个人资源索引管理，不公开原题、SQL、逐题表/边、缓存、数据库或日志。

## 决策

保留两个求解器及精确校验实现。此次“精确求解减少少量中间表”有真实算法信号，但集中于一个库六种结构；没有参考表完整覆盖收益，没有SQL EX、生成token或最终业务正确性结论。按固定预算完成并进入分析，不自动追加求解器、种子数、模型或GPU实验。

