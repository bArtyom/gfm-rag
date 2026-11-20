# 需求见证预算 pilot：CPU Smoke 结果

**状态：按预注册门槛停止；未运行 40 题 pilot。** 五题 recovery smoke 中，需求见证输出仍为 0/5 可解析 JSON。五题表覆盖和标量列闭包基线均保留 22/22 个参考读取列，且各自在 5/5 题完整；需求见证保留 0/22 列、0/5 题完整。该结果足以触发本版本的 smoke stop gate，但不能代表全量 BIRD-dev 或 BizWeave 整体效果。

## 研究问题和范围

在每题 2,048 token 的“在线推理 + 最终 schema”总预算内，显式需求见证能否比整表覆盖和标量列相似度闭包保留更多参考 SQL 读取列？需求见证臂要求模型为选择、过滤、聚合和比较需求给出精确问句源片段以及列/算子候选绑定，再做一对一预算分配。

这是 BizWeave 查询感知在线检索层的窄范围首测。它没有构建离线业务概念图或映射图，也没有从 SQL、数据或文档抽取业务规则；没有评估业务路径准确性、粒度安全或完整约束满足。实验使用重复暴露的 BIRD-dev 样本，结果为探索性 smoke，不是独立测试、SQL EX、业务语义结论或新颖性结论。

## 预注册设计和门槛

- **实验层级：** 五题 smoke；只在至少 4/5 输出可解析并通过需求/跨度校验、请求 usage 完整且无预算违规时，才继续 40 题 pilot。
- **三臂：** 整表 query-cosine 覆盖；全列 query-cosine + FK 闭包；本地 Qwen 需求见证 + 一对一绑定 + FK 闭包。
- **预算：** 每题新推理 token 与序列化 schema token 合计不超过 2,048；比较臂不使用新生成 token。
- **停止条件：** 首次 smoke 可做一次预先登记的恢复修改；恢复 smoke 再失败即停止此方法版本，不扩量。
- **样本：** BIRD-dev 五题、五个不同数据库；与拟定 40 题 pilot 不重叠。冻结全量有 1,534 题/11 库，433 个历史排除项已在预检核对。smoke 和 pilot 均为开发集抽样。
- **随机种子：** 20261121；样本由预注册的独立 smoke 盐确定。

完整设计见[预注册方案](../../plans/requirement_witness_budget_20261121.md)，执行配置及数据、缓存、模型文件 hash 见[CPU 配置](../../../../../configs/text2sql/requirement_witness_bird_cpu_20261121.json)。GPU 配置因启动前显存低于门槛而保持 HOLD，未启动 vLLM 或做 GPU 推理。

## 仓库、实现和运行环境

- **自有仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，实验分支 `research/requirement-witness-pilot-20261121`。
- **实验基线：** `research/closure-budget-order-20261112`，commit `124fd30b1548106f714d7218c9d6972dc82a4e52`。
- **恢复 smoke 源码：** commit `ced7a4ce013eb14d82b4cae373fe127f8768ad3b`；恢复配置 SHA-256 `71e878d4fe81f66be3d0546966d5908f07444c471c45008b3b9641fe789055d2`。
- **实现：** 新增受预算约束的需求见证执行器及独立 GPU/CPU 配置。一次恢复改动把物理列号仅写入私有预测，修复封存后列映射错误，并将 CPU 生成上限从 256 提至 640；单题总预算、采样、模型和科学门槛不变。
- **数据：** 复用冻结 BIRD-dev 问题、schema、对齐 SQLite、Qwen3 embedding cache 和节点清单；其 SHA-256 及模型各文件 hash 在配置文件中登记。预检通过 1,534 题/11 库、433 排除项、样本互斥和文件校验；本实验没有下载或复制数据。
- **模型：** 本地 Qwen2.5-Coder-7B-Instruct，Transformers CPU backend，bfloat16，greedy 解码，seed 20261121；无外部 API、无模型下载、无依赖安装。
- **环境：** 已有 `think2sql_20260909`，Python 3.12.14、PyTorch 2.8.0、Transformers 4.57.1、NumPy 2.2.6、NetworkX 3.6rc0、SQLGlot 28.0.0、Requests 2.32.5。CPU 使用 AVX-512 BF16/MKL/MKLDNN，32 intra-op / 16 inter-op 线程。无环境升级。
- **资源：** 启动时可用内存约 422 GiB（高于 49,152 MiB 门槛），`nproc` 为 32。四张 RTX 4090 均为 100% 利用率，GPU 0 仅余 9,173 MiB，低于 20,000 MiB 门槛；因此没有占用 GPU。
- **命令：** `conda run -n think2sql_20260909 python scripts/text2sql/run_requirement_witness.py --config configs/text2sql/requirement_witness_bird_cpu_20261121.json --mode smoke`（执行两次，分别使用原始和恢复版配置/输出目录）。

## 运行结果

第一次 smoke 的五次本地推理均返回 usage，但 0/5 输出为有效 JSON，生成均到达原 256 token 上限；单请求时延为 82.70–89.26 秒，均值 86.25 秒。预测封存后，评估器因私有候选记录缺少物理列号触发 `KeyError`。预测、日志与失败清单保留，没有试跑 pilot。

按唯一允许的预注册恢复修改，使用新输出目录和新的 ledger 请求 ID 重跑五题。单请求时延为 94.67–174.07 秒，均值 143.75 秒。评估流程本身通过预测封存完整性、样本数、预算、无泄漏顺序和聚合重算核验，但需求见证仍为 0/5 有效 JSON，未抽取出需求或精确跨度。原始模型响应未保存，因此不能确认具体格式错误原因。

| 指标（恢复 smoke，n=5） | 整表覆盖 | 标量列闭包 | 需求见证 |
|---|---:|---:|---:|
| 参考读取列保留 | 22/22 | 22/22 | 0/22 |
| 完整绑定题 | 5/5 | 5/5 | 0/5 |
| 读取列召回（micro） | 1.000 | 1.000 | 0.000 |
| schema token | 3,698 | 4,892 | 0 |
| 在线推理 token | 0 | 0 | 8,409 |
| 2,048 token/题违规 | 0 | 0 | 0 |

恢复见证请求共有 6,385 输入、2,024 输出、8,409 总 token；全部 5 次请求 usage 均可记录，推理平均 1,681.8 token/题。候选池 Top-32 覆盖 16/22 个参考列（0.727），仅作候选召回诊断。相对两个基线，完整绑定题的配对结果均为 rescue 0、damage 5。恢复运行 wall time 757.51 秒，进程 CPU time 22,989.38 秒（约 6.39 核小时），峰值 RSS 15.13 GiB。第一次失败运行的进程 CPU 总时长没有可靠记录。

参考读取列是通过封存预测后在空 schema stub 上编译未改动参考 SQL，并由 SQLite authorizer 提取的结构 proxy；没有执行数据查询。指标不是 SQL 执行准确率或语义正确率。

## token、费用和产物

本 run 两轮合计 10 次本地模型请求：输入 12,770、输出 3,304、总计 16,074 token，未知用量请求 0。它们使用本地 CPU 模型，不调用外部 API；因此本轮外部 API 费用为 CNY ¥0.00。该数只表示没有外部 API 请求，不代表本地 CPU 运算没有资源成本；本地计算成本未货币化，也没有可核实的供应商账单。

匿名聚合与本报告公开归档。原题、SQL、逐题绑定、提示词、模型输出及私有逐题产物只保存在本地 run-specific 目录，未上传。公开匿名聚合见 [`aggregate.public.json`](aggregate.public.json)。

## 结论与后续

**停止当前方法版本；不运行 40 题 pilot，不启动 GPU 推理。** 恢复后仍没有一条需求或跨度通过 JSON 解析，方法在预先规定的 smoke 门槛失败；此阶段不能判断失败究竟来自提示格式、截断还是模型指令遵循。基线表现仅用于证明该五题 smoke 可评估，不构成与全量方法的比较。

若未来重启，需要先登记新的问题与停止门槛，并独立诊断结构化输出机制；不能把第三次尝试算作原预注册的恢复，也不能据此扩展 BizWeave 主张。完整 BizWeave 仍待研究在线商业关系构建、历史业务规则证据、业务路径准确度、粒度安全及约束满足。
