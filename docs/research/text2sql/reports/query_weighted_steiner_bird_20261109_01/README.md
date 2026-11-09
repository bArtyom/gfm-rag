# 固定 schema 图上的问句加权 Steiner：初步实验

2026-11-09（UTC+8）；运行 ID `query_weighted_steiner_bird_20261109_01`；exploratory。**完成全部 1,534 题，问句加权完整表覆盖率80.70%，不带权80.57%，净增2题；未达到预设至少1个百分点的升级目标，停止扩展。** 未运行 SQL 生成、训练、GPU、付费 API 或更多参数扫描。

## 研究问题与预先冻结的协议

同样的三个语义种子表和同一 FK 图，问题相关的连接代价能否改善参考 SQL 所需表的完整覆盖？图结构离线只由 schema 定义；在线仅改变边权。主实验三组，最小消融仅在全量升级门通过后运行，独立数据/SQL复现也仅在有足够信号后另行安排。

计划见 [执行方案](../../plans/query_weighted_steiner_20261109.md)。固定 k=3、lambda=1、Mehlhorn、question-only 输入，不引入 BIRD evidence。r=(1+cos(q,e))/2，cost=1+(1-r)。描述模板只串联真实 FK 的有序完整列对：`Foreign key relationship: <qualified column equalities>.`，不生成业务含义。表级图共75表、105个完整约束、74条非自环无向表对边；并行FK单独保存，复合FK不拆散。求解时以最低(cost, constraintID)代表并行边，输出保留具体ID；schema context仍携带所选表间所有合法外键，不强迫下游只使用树边。

预算8CPU线程、RSS目标<12GiB、30wall分钟、新输入token<=100000、无GPU。升级流程：五条关系/五问题向量兼容性检查→五题检索smoke→按图结构分层100题；100题weighted-minus-unit>0且weighted-minus-dense>=0才扩大1534。最终升级目标>=1pp vs unit且优于matched dense。预算、输入漂移、不可恢复/连续失败停止；不得因小幅正向结果自动追加实验。

## 数据、模型与版本

- 项目仓库 `https://github.com/bArtyom/gfm-rag`，新分支 `research/query-weighted-steiner-20261109`。沿用独立项目checkout，本地基线83a25249758f81f68a7a61ee1649fdbde73d8073；对应已公开树的parent为20a83a308913a9e2d78db362d1f4dd3057e27a19。
- 阅读根README、text2sql README、experiment-roadmap、reproducibility-contract、此前两份Steiner报告和运行入口。旧维度/监督角色/GFM Gate保持不变；本轮为用户明确授权的独立无监督FK评分探索，不是完整GRAST或GFM复现。
- BIRD开发集1534题/11库，既有archive-aligned SQLite快照，十一DB与题目/schema/cache哈希固定在[配置](../../../../../configs/text2sql/query_weighted_steiner_bird_20261109.json)。复用旧Qwen问题及表向量，旧结果均未覆盖。
- 本地 Qwen3-Embedding-0.6B，权重SHA `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`；新HF CPU FP32 last-token pooling/L2/1024D关系向量。五问题与历史vLLM缓存余弦最小0.99984276；只证明该五点的数值兼容检查通过，不声称全量逐位一致。
- 编码执行commit2593c3f，检索执行commit `9084970790a8fed408f1dc2c1238d6adf97a6662`；最终归档额外包含独立核验脚本与报告。Python3.12.14；torch2.8.0/numpy2.2.6/networkx3.6rc0/transformers4.57.1/sqlglot28.0.0。无新依赖安装、模型/数据下载。

## 实测结果

| 方法 | 完整覆盖题数 | 完整表覆盖率 | 平均表数 | 平均schema token* |
|---|---:|---:|---:|---:|
| 不带权 Steiner | 1236/1534 | 80.57% | 3.2810 | 515.00 |
| 问句加权 Steiner | 1238/1534 | 80.70% | 3.2777 | 515.21 |
| 同选表数量语义扩展 | 1219/1534 | 79.47% | 3.2777 | 495.22 |

*同一Qwen embedding tokenizer测量序列化schema，仅为上下文长度代理，不是SQL生成输入用量。匹配的是逐题表数；加权组token比语义扩展多约4%，不能称同token预算。

相对不带权：修复8题、退化6题、1520题覆盖状态不变，净增2/1534（+0.13pp）。DB聚类描述性95%区间[-0.175, 0.642]pp，跨0，不能声称稳定提升。相对同表数语义扩展：修复28、退化9、净增19（+1.24pp），描述性区间[-0.234, 3.187]pp也跨0。加权组参考表平均召回略增，未测SQL执行准确率或已裁定JOIN角色准确率。

100题pilot为unit82/weighted83/dense81，50题有备选路径、50题唯一连接；只是结构分层样本，不能代表总体。满足预设扩样条件后原参数跑全量，提升缩小，未按pilot调参。5题smoke为工程检查，不计入独立论文证据。

全量有备选路径738题、唯一连接796题；全部14次覆盖变化来自前者。选表集合改变37题（2.41%）；连接约束集合改变261题，不能把后者全部视为表覆盖改善。表数增加1的6题、减少1的11题，其余1517题表数相同，净少5个逐题表出现。森林情况252题保留在分母；参考表解析失败0。唯一连接796题均未改变覆盖。

实际cost范围1.1545–1.4815，中位1.3334。观察到权重改变了部分路径/关系，但简单列对语义评分的任务收益很小；不能据此推断所有问句加权方式无效。

## 工程异常与验证

首个100题attempt `pilot_001` 在schema token序列化遇到BIRD嵌套复合主键格式而退出，未写预测或指标；保留原日志。增加失败回归测试后，仅修复serializer的PK索引展开，未改变输入/权重/选表。`pilot_002`恢复完成，无重编码或额外模型请求。另一次旧单测入口缺少GRAST_SOURCE，补齐既有公开上游路径后35项通过；单独2项新runner测试通过，共37项与既有20个brute-force子案例。没有声称全仓库测试通过（此前全仓库collection有缺失依赖，未安装或重跑）。

独立代码审阅无阻塞项。核验脚本不调用模型或求解器，重新计算原始缓存排名、边权、FK代表身份、图/种子连通性、逐题表数匹配、schema token和覆盖配对数；全部1534行/4602组输出PASS，检查全量身份、完整预测seal和升级门。该核验复用固定输入loader、参考SQL解析器和serializer，不独立证明这些公共函数的语义，也不证明Mehlhorn最优。

预测SHA `232d5ff471f9f06181929aa1148c853e42c8172c28f6fdda373c0434dc959e3b`；核验见[independent_verification.json](independent_verification.json)。输入SQLite及缓存哈希不变。所有预测先封存，之后评价模块才提取参考表；没有将gold、SQL或人工角色标签用于种子/权重/采样。

## 运行方式与产物

配置使用环境变量LAB_ROOT统一资源入口。使用既有think2sql_20260909环境，并明确使用该环境Python（若conda中的裸python解析到其他环境，改用目标环境解释器绝对路径）。

```bash
export LAB_ROOT=/path/to/lab-root
export CUDA_VISIBLE_DEVICES=''
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
conda run -n think2sql_20260909 python scripts/text2sql/prepare_query_weighted_cache.py \
  --config configs/text2sql/query_weighted_steiner_bird_20261109.json \
  --output results/query_weighted_steiner_bird_20261109_01/relation_cache_001
conda run -n think2sql_20260909 python scripts/text2sql/run_query_weighted_steiner.py \
  --config configs/text2sql/query_weighted_steiner_bird_20261109.json \
  --relation-cache results/query_weighted_steiner_bird_20261109_01/relation_cache_001 \
  --mode smoke --output ai_temp_code/query_weighted_steiner_smoke_001
conda run -n think2sql_20260909 python scripts/text2sql/run_query_weighted_steiner.py \
  --config configs/text2sql/query_weighted_steiner_bird_20261109.json \
  --relation-cache results/query_weighted_steiner_bird_20261109_01/relation_cache_001 \
  --mode pilot --output results/query_weighted_steiner_bird_20261109_01/pilot_002
# Only after positive pilot receipt, run --mode full with new output full_001.
conda run -n think2sql_20260909 python scripts/text2sql/verify_query_weighted_outputs.py \
  --config configs/text2sql/query_weighted_steiner_bird_20261109.json \
  --relation-cache results/query_weighted_steiner_bird_20261109_01/relation_cache_001 \
  --output results/query_weighted_steiner_bird_20261109_01/full_001 \
  --report-name independent_verification_complete.json
```

All output directories are exclusive; reproductions must choose fresh directories instead of overwriting existing results. Full CLI trusts operator to enforce prior pilot gate; actual expansion satisfied it. Actual commands/interpreter/environment/hardware/source version are retained privately in each run_start.json and logs.

私有产物 `results/query_weighted_steiner_bird_20261109_01/relation_cache_001`, `pilot_001`失败现场、`pilot_002`, `full_001`；smoke在`ai_temp_code/query_weighted_steiner_smoke_001`，日志在`logs/query_weighted_steiner_bird_20261109_01`。仅提交代码、协议、配置、匿名聚合与哈希，不提交原题、Gold SQL、逐题选择/分数、关系描述或模型权重。

编码wall 23.05s / processCPU 50.17s / peakRSS 4.08GiB；全量检索wall 15.10s / processCPU 15.65s / peakRSS 0.76GiB。检索wall包含加载/验证/token统计，不是纯求解器延迟。全部阶段均在预算内。

本轮15次本地embedding前向，真实输入1700/输出0/总1700token，无未知请求；外部API费用0CNY、GPU0秒，本地CPU未折金额，不能称无计算成本。详见[用量快照](usage_snapshot.json)；累计费用仅已定价部分的公开价估算，实际账单未核实。

## 结论和停止决定

固定图、问题赋权的流程已验证可执行；比不带权仅多完整覆盖2题，升级门未通过。保留实现和负/弱信号结果，停止该冻结版本的扩样、权重调参、shuffle消融及SQL/GPU实验。后续如继续，应先分析37道选表变化和8修复/6回退，判断关系文本或种子错误是否限制效果；不自动启动新方向。本开发集已多次使用，任何更强主张仍需独立数据库验证。

GitHub归档状态以本报告所在分支及最终提交为准；本地执行commit与连接器创建的同树归档commit分开记录。此前实验和上游仓库均未更改。
