# Steiner 子 schema：本地7B下游 SQL pilot

2026-11-10 UTC+8，exploratory，运行 `steiner_sql_pilot_bird_20261110_01`。**已完成100题主pilot和37题差异诊断。加权子schema减少30.67%逻辑输入token，但确认Set正确为39/100，完整schema为42/100；未过预注册扩量门，不运行1534题全量。**

## 问题与预注册

唯一假设是：冻结种子/图/子schema后，输入压缩能否在基本保持下游SQL正确率的同时降低输入token。只比较full、unit-Mehlhorn、question-weighted-Mehlhorn三臂；这次从此前图覆盖代理指标前进到实际生成和SQLite执行，不是重新测试五个求解器，也不是完整DeepEye复现。旧方法和结果不改。

[执行前协议](../../plans/steiner_sql_pilot_20261110.md)与[独立配置](../../../../../configs/text2sql/steiner_sql_pilot_bird_20261110.json)先提交后推理。主pilot100题以固定hash、seed20261110按11库轮转抽取，不读取gold决定样本；5题工程smoke属于100题，真实响应缓存复用。37题诊断取冻结unit/weighted选表不同的全部题，只涉及3库，和主pilot重叠4题，总共133个不同问题。不能相加为137题独立样本，诊断也不控制扩量。

扩量只看主pilot：weighted确认Set正确数至少full-1，且输入节省至少15%，否则完成诊断后停止。本轮39<41，故停止。服务预算4小时/8 reserved GPUh，最多5000请求、20M输入/5M输出；无参数搜索、SQL修复或候选选择，未启动其它模型/数据集。数据已多次探索，结果不能作为独立泛化证据。

## 已冻结输入与实现

- 项目仅归档自有 `bArtyom/gfm-rag`，分支 `research/steiner-sql-pilot-20261110`。本地base5350b83对应公开parent377e7ec；真实推理执行source `0b592aa36e64dc7ce724110a65b122c739e7455f`。准备sourcea26afd8，正式推理前的变更仅为执行/资源/标签身份保护；不改准备的prompt/cohort/参数。
- 已读根README、text2sql README、experiment-roadmap、reproducibility-contract及此前Steiner报告。沿用GRAST-SQL公开代码commit4c698cae31da8299deb5c809101d172d5b2ddeb3的项目衍生实现，原第三方仓库保持只读。新代码不写上游结果。
- BIRD-dev1534题/11库的相同aligned SQLite快照；问题、schema、11DB、历史选择、9个模型文件和额外tokenizer支持文件均核验SHA。历史top3种子和两种Mehlhorn表集合直接读取封存结果，无新embedding/选表/加权。完整hash见配置及[manifest](reproduction_manifest.json)。
- 图结构仅依schema；问句仅影响已冻结的边cost。三臂统一序列化：full保留全表，另外两臂保留选中表的全部列及表间合法外键。模型输入均含同一个问题和BIRD提供的evidence；历史检索仍为question-only，不暗改检索输入。无gold SQL/表字段进入模型。
- 本地Qwen2.5-Coder-7B-Instruct，已有模型alias `sources/models/qwen25-coder-7b`；temperature0/top_p1/n1/seed20261110/max_tokens1024，不截prompt。全部1534×3输入预tokenize，最大2497token，context16384。
- 复用独立vLLM0.8.5/Python3.10/torch2.6.0服务环境，无安装下载。GPU1、2，TP2/BF16，每卡显存预算.45，maxseq4/batch4096、V0/eager/chunked-prefill/prefix-cache。仅本机服务，无外部API。CPU准备/评测环境think2sql_20260909，Python3.12.14/numpy2.2.6/transformers4.57.1/sqlglot28.0.0。

## 主pilot结果

| 输入schema | 确认Set正确 | 确认Bag正确 | Set未确认 | 预测可执行 | 逻辑输入token |
|---|---:|---:|---:|---:|---:|
| full | 42/100 | 38/100 | 23 | 81 | 89,785 |
| unit | 39/100 | 37/100 | 26 | 78 | 62,219 |
| weighted | 39/100 | 37/100 | 26 | 78 | 62,247 |

这里的分母固定100，未确认仍保留在分母中。Set不计重复行，Bag计重复行；列位置固定，使用既有浮点容差。这是**受执行/比较限制的确认匹配率，不是官方BIRD EX**。相对于full，weighted净少3个确认正确，输入节省30.6710%；unit节省30.7022%。weighted与unit均39，但逐题有1个确认救回和1个损失，不能称生成输出完全一致。

将未确认按“非确认正确”作二元配对时，weighted相对full救回4/损坏7，净-3；双方可判断的配对子集则救回3/损坏4、31对至少一端未确认，两种口径不混写。按库重采样10000次的描述性95%区间约[-10.00,+2.02]个百分点，仅说明小样本不确定性，不证明退化显著或非劣。

主pilot参考SQL有7题被既有评测器的保守语法/函数规则阻止。预测full有13error+6blocked，unit/weighted各17error+5blocked；另有大结果非精确比较无法判定的情况。因此Set未确认为23/26/26，不应全部解释成SQL语义错误。没有执行超时、模型截断、HTTP或usage失败。所有状态计数见[独立核验](independent_verification.json)。

## 差异诊断及误差线索

37题诊断full确认17/37（45.95%），unit11/37（29.73%），weighted13/37（35.14%）；未确认分别6/15/10，Bag确认也是17/11/13。weighted相对unit净增2，但相对full仍少4，且这是特意富集差异的3库子集，不能外推全量收益。

参考SQL完整表覆盖在主pilot为full100、unit76、weighted75；诊断为37、17、19。主pilot中weighted损失的7个full确认题，有6个未完整保留参考表；这是事后关联，不证明唯一原因。即使没有覆盖参考表，也可能生成用其它表得到相同结果的SQL，本轮weighted有4个此类确认题；覆盖率不是生成正确率的充分必要条件。

当前证据支持保留“输入变短”的观察，不支持“问题加权Steiner已改善下游SQL”。先整理种子遗漏、SQL生成错误和评测未确认原因；不继续扫描求解器或追加全量推理。

## 验证、故障与资源成本

96项针对性pytest通过（5项新prompt/cohort/cache/reference-SHA/owned-process-cleanup测试，91项既有评测器测试），不宣称全仓库测试。执行前独立审阅发现进程清理/参考标签SHA检查两项问题：execution_001启动29.39秒后、模型请求前主动停止；0次请求，现场保留。修复后execution_002完成全部阶段。独立审阅无剩余阻塞项。

独立核验PASS：配置/数据/DB/历史选表/输入hash、100/5/37样本身份、预测seal、payload/响应/真实usage、284条共享账本逐条一致；重新执行358个不同(db,SQL)，所有原始评价与重放零差异。重放不挑最佳结果，不追加模型调用。核验没有重新生成SQL，也不宣称独立实现了另一套比较器。停止本实验拥有的完整service session及子进程，确认全部退出、端口关闭；其它任务未被停止。

实际物理模型请求284次，全部有真实usage：输入209008、输出15565、总224573token，未知0。不同臂/阶段的完全相同payload只请求一次；逻辑表格不当作实际累计调用成本。服务正常运行227.25秒，另启动中断29.39秒；两卡合计513.28 reserved GPU秒（约0.143 GPU小时），是分配时长而非实测GPU kernel时间。外部API费用0CNY，本地GPU/CPU费用未货币化，不称资源免费。

跨项目共享账本快照见[usage](usage_snapshot.json)：确认493,823,017token，未知108次；已定价CNY部分按公开价格估算24.0406214732928元，实际账单未核。模块不包含未登记调用/未定价本地成本或其它币种sidecar，不能当作账户全部花费。

## 复现命令与产物

先按项目资源索引提供数据、冻结选表和模型，设置LAB_ROOT，核对配置及依赖。以下均在项目根目录执行；每次用新的输出目录，不覆盖既有结果。

```bash
export LAB_ROOT=/path/to/your-resource-root
conda run -n think2sql_20260909 python -m pytest tests/test_steiner_sql.py tests/test_p2d_sql_evaluator.py -q
conda run -n think2sql_20260909 python scripts/text2sql/prepare_steiner_sql.py \
  --config configs/text2sql/steiner_sql_pilot_bird_20261110.json \
  --output results/steiner_sql_pilot_bird_20261110_01/prepared_001
conda run --no-capture-output -n think2sql_20260909 python scripts/text2sql/run_steiner_sql.py \
  --config configs/text2sql/steiner_sql_pilot_bird_20261110.json \
  --prepared results/steiner_sql_pilot_bird_20261110_01/prepared_001 \
  --output results/steiner_sql_pilot_bird_20261110_01/execution_002
conda run --no-capture-output -n think2sql_20260909 python scripts/text2sql/verify_steiner_sql.py \
  --config configs/text2sql/steiner_sql_pilot_bird_20261110.json \
  --prepared results/steiner_sql_pilot_bird_20261110_01/prepared_001 \
  --execution results/steiner_sql_pilot_bird_20261110_01/execution_002 \
  --output results/steiner_sql_pilot_bird_20261110_01/audit_001
```

实际启动还设置OMP/OPENBLAS/MKL线程8、TOKENIZERS_PARALLELISM=false和PYTHONHASHSEED=20261110；原命令、环境路径、服务GPU资源快照在私有run_start/service_start/logs中。核验脚本对本次保留的execution_001启动中断目录作记账；其它复现需保留相应启动记录并使用新的run_id以免账本call_id冲突。greedy GPU推理不保证跨硬件bitwise一致。

本地 `results/steiner_sql_pilot_bird_20261110_01/prepared_001`、`execution_001`、`execution_002`、`audit_001`，日志 `logs/steiner_sql_pilot_bird_20261110_01/`；统一资源alias `sources/results/steiner_sql_pilot_bird_20261110_01`。私有question/evidence/prompt/SQL/response/逐题评价仅本地保留，公开仓库只含代码、配置、hash及匿名聚合。归档commit及PR由提交后读回核验，再在交付消息和资源索引登记；本报告不声称已经合并main。
