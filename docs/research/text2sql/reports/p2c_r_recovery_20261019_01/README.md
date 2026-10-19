# P2c-R：检索与 Context 双视图独立恢复实验

**结果：H1 排名不变量 PASS，预注册 H2 覆盖成功门 PASS；V01 冻结为进入 Values 信息风险审计的离线候选。** 这是 BIRD dev 的探索性 Schema 节点覆盖结果，SQL Set/Bag EX、谓词值效用和跨数据库泛化均未测。

## 研究问题、边界与原失败记录

核心问题：检索向量是否应保留 Values，而返回 Schema Context 采用省略 Values 的短文本？四臂为 V00=R0 排名/R0 Context、V01=R0/R1、V10=R1/R0、V11=R1/R1。R1 只移除原有列节点的 `value_description`，不删除数据库列或改变候选宇宙。

原 P2c 的两次 Full 在聚合报告契约处失败，原注册已停止且没有科学结果。本实验依照 [最新 P2c-R 协议](../../plans/p2c_r_replay_contract_recovery_20261018.md)，先完成 [Gate 0](../p2c_r_contract_gate_20261019_01/README.md)，再于提交 `7f5893ac9840ada957680bce7bce183a756ed6ab` 独立注册并执行一次 Smoke、一次 Full，未改变原 H1/H2、数据、阈值、缓存或随机性，也未在看到结果后修复重跑。

本轮为最小因子诊断层。成功判据在正式评分前冻结：全体 Complete@1024 的 V01−V00 ≥+5pp；固定困难集 ≥+3pp；两组数据库簇 95% CI 下界都 >0；固定至少 3/5 库非负且 2/5 库严格为正。任何输入/版本/排名回放错误、工程失败或资源超限均停止，无重试。每次限 1800 process CPU 秒、8 线程、16 GiB RSS；GPU/API/模型前向/SQL=0。

## 数据、环境与复现

BIRD dev 共 1534 题、11 DB、873 节点（75 表/798 列）。Column/Complete 指标仅使用 1460 列可评题，74 题保持不可评；固定 R0 非饱和子集为 5 DB、746 表可评题/706 列可评题。子集由原 R0 Schema token >2048 定义，不随短文本调整。所有比较均为 query macro。

沿用既有 1024-D Qwen3-Embedding-0.6B CPU Query/R0/R1 向量、L2+Cosine、稳定 ID tie-break、512/1024/2048 token first-fit 装包。只加载本地 tokenizer 校验文本长度，模型权重未加载。Bootstrap 采用数据库簇、10000 次、固定 seed=20261020。

环境：think2sql_20260909；Python 3.12.14、NumPy 2.2.6、Transformers 4.57.1、Tokenizers 0.22.1。主机 192 CPU 线程、503 GiB RAM；Full 前可用约444 GiB RAM/115 TiB磁盘，四张 RTX4090 均未用于本轮。复用 /mnt/liansp3/sources/ 中的数据、模型与项目入口，没有新下载/安装。

执行源提交：`7f5893ac9840ada957680bce7bce183a756ed6ab`。Gate 0 到正式运行冻结七个执行源文件及依赖版本；Smoke/Full 使用同一提交、输入和源码哈希。P2b CPU cache SHA-256=`63f0accdd1dee9d3e7ca2f0c93004f3c5a4201cac573d2a748a9d3f3bf613ba8`；输入 manifest=`693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`。模型 manifest、其他缓存/文本 SHA 和完整注册见 [配置](experiment_config.json)，准确命令、环境变量、各依赖/源码 SHA 见 [Full 回执](run_receipt.json) 与 [Smoke 回执](smoke_receipt.json)。

命名使用工作区日期 2026-10-19；进程实际 UTC 启止时间以回执为准。原始逐题、Gold/SQL、向量和日志保留本地，GitHub 仅发布安全汇总。

## 四臂主要结果

表内召回与 Complete 为百分比；mean returned tokens/elements 均按1460列可评题统计。

| 条件 | 排名/Context | 全体 Column R@10 % | 全体 Complete@1024 % | 固定困难集 Complete@1024 % | 平均返回 token | 平均返回元素 |
|---|---|---:|---:|---:|---:|---:|
| V00 | R0/R0 | 67.99 | 56.64 | 37.96 | 949.59 | 30.36 |
| V01 | R0/R1 | 67.99 | 67.60 | 46.18 | 915.23 | 38.88 |
| V10 | R1/R0 | 67.03 | 53.77 | 34.14 | 949.95 | 29.67 |
| V11 | R1/R1 | 67.03 | 65.96 | 43.48 | 915.27 | 38.84 |

四臂 Table R@5/R@10 均为 94.75%/99.93%。V00/V01、V10/V11 的 Table/Column Top-K 逐题逐元素及同视图 score digest 完全一致；V00/V11 精确重放 P2b 已归档的 Column Top-K 与所有预算行，48 个聚合字段在 atol=1e-14、rtol=0 下匹配。历史 P2b 没有逐题 Table Top-K 存档，所以历史 Table 只报告新一轮配对不变量，不冒称历史 Table 逐题回放。

### 预注册主门

| 分组 | V01−V00 Complete@1024 | 数据库簇95%CI（pp） | 预设最小增益 |
|---|---:|---:|---:|
| 全体1460题/11库 | +10.9589 pp | [+5.3669, +18.6988] | +5.0 pp |
| 固定706题/5库 | +8.2153 pp | [+4.1116, +13.1195] | +3.0 pp |

固定五库全部严格正向：

| 匿名库 | Complete@1024 delta pp |
|---|---:|
| db_01 | +6.90 |
| db_02 | +4.57 |
| db_05 | +2.46 |
| db_07 | +8.59 |
| db_10 | +16.98 |

全体 V01 相对 V00 救回162题、损坏2题、1296题不变，净增160题；困难集救回60题、损坏2题、644题不变，净增58题。平均改善不意味着逐题单调改善；两个损坏案例已保留在私有逐题文件，未在本轮做人类语义裁定。

### 固定预算辅助结果

| Budget | V00 Complete % | V01 Complete % | V10 Complete % | V11 Complete % |
|---|---:|---:|---:|---:|
| 512 | 35.34 | 39.32 | 35.00 | 38.90 |
| 1024 | 56.64 | 67.60 | 53.77 | 65.96 |
| 2048 | 79.52 | 86.37 | 78.84 | 85.82 |

Complete@1024 的全体因子分解：固定 R0 排名只缩短 Context 为 +10.9589pp；固定 R0 Context 改用 R1 排名为 −2.8767pp；交互项 +1.2329pp。Column R@10 的 Context 效应为0，而移除检索端 Values 的排名效应为 −0.9555pp。这支持继续区分检索语义与返回文本长度；不支持将删除检索端 Values 本身解释为更好的语义检索。

## Token 与 Values 信息风险

全部候选 Schema 文本由27506缩到20071 tokens，减少7435（27.03%）；这不是完整 SQL prompt 的实测降幅。1024预算下 V01 平均返回 tokens 从949.59降到915.23（约3.62%），返回元素从30.36增到38.88。困难集平均已用token约1019.77→1020.12，缩短文本主要增加预算内元素数。

278个候选列带有被移除的 Values 描述。V01 在1024预算下平均选中12.84个这样的列，跨题累计18741次；其 Values 内容不再呈现在 Context 中。这只是信息移除暴露计数，尚未判断 SQL 是否依赖这些业务常量/枚举值。后续需要独立 Values-critical 风险审计，再考虑固定 Generator/Selector 的数据库级 SQL EX 对照。V01当前仅为离线候选。

## 验证、异常与真实资源

93项相关测试通过，包含真实归档成功路径、48项单独扰动、缺键/None/NaN/空集合、分母检查、完整合成聚合写盘、Source/Input冻结、前置产物完整性、缩短早位非Gold候选挤掉后位Gold的反例。独立代码审查的两个输入/执行源冻结问题及前置文件完整性建议均已修复。

另以持久化私有逐题文件独立复核：9204项配对排名/分数不变量、3068项历史行回放、120项指标、48项旧聚合指标、两组Bootstrap CI和主门重算均通过；公开产物的数据库名和私有字段扫描通过。见 [verification_summary.json](verification_summary.json)；[独立校验脚本](verify_artifacts.py)使用 atol=1e-12 处理独立求和顺序，实验内回放仍为原1e-14。

| 阶段 | process CPU秒 | wall秒 | peak RSS GiB |
|---|---:|---:|---:|
| Gate 0 | 12.381695 | 12.647481 | 0.882500 |
| Smoke（5题，非正式证据） | 11.264175 | 11.158932 | 0.860424 |
| Full（1534题） | 21.618961 | 21.962420 | 0.977512 |
| 本轮合计 | 45.264831 | 45.768833 | 0.977512 |

本轮无新的运行失败；原P2c所有失败仍归档，计入整个恢复链后总process CPU=119.230041秒。API请求、确认输入/输出tokens、未知用量和外部API费用均为0（CNY0.00）；本地模型前向为0，CPU耗用如表，不将本地计算称为没有资源成本。

本地 Full目录：`/mnt/liansp3/sources/results/gfmrag_p2c_r_recovery_20261019/full_1534_20261019_01`；日志：`/mnt/liansp3/logs/gfmrag_p2c_r_full1534_20261019_01.log`。公开聚合 SHA-256=`7e4ce4b2a92df5e17160bb2429402b66ab7caec521c6e4da9ec90abd108e8fdc`；私有逐题SHA=`99935116001811bef790bf2e916d34f4f40ffecc70322f7b71e28f885d9425ff`。

## 决策与局限

保留V01为离线候选并结束本次登记的一轮Full，不追加Values拼接/截断参数搜索。P2b原NO-GO、原P2c无科学结果和FK/Role Gate NO-GO均保留。当前结论限于反复开发的BIRD dev、固定CPU缓存和同一装包规则；它不能证明SQL EX提升、谓词值安全、JOIN Role正确或独立数据库泛化。下一项关键未决问题是省略Values的SQL信息风险。
