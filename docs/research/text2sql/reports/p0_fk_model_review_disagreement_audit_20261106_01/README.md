# P0 双模型 FK 审阅分歧归因审计

**状态：已完成；只读描述性分析。** 实验 ID：`p0_fk_model_review_disagreement_audit_20261106_01`。

本审计分析两份已经冻结的模型审阅结果，定位不一致集中在哪里。它不新增标签，不判断哪个模型正确，也不运行 G-reasoner 排序。

## 研究问题与边界

问题是：两模型的 29 个不一致单元，是否集中在候选数量、候选展示顺序、决定类型或自报理由上？

- 层级：探索性错误归因，不是新方法效果实验。
- 单位：60 个问题×表对；共 135 个 FK mapping，来自 4 个匿名数据库。
- 只读取匿名 A/B 审阅包及两份模型输出。没有读取 Gold SQL、人类回复 CSV、数据库内容或数据库映射清单。
- 只报告描述性计数，不做显著性检验或因果解释。自报置信度和理由不视为正确性证据。

## 版本、来源和执行

- 项目仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-model-review-disagreement-audit-20261106`。
- 分析代码与计划冻结于提交 [`fc06c87131f71cb575a316b9bac697b6c778d119`](https://github.com/bArtyom/gfm-rag/commit/fc06c87131f71cb575a316b9bac697b6c778d119)。
- 输入来自[双本地模型审阅报告](../p0_fk_mapping_model_review_proxy_20261106_01/README.md)。输入包与模型输出 SHA-256 见本目录的匿名[`aggregate_summary.json`](aggregate_summary.json)。
- 命令：`conda run -n think2sql_20260909 python3 scripts/text2sql/audit_p0_fk_model_review_disagreement.py --packet-a <private-A-packet> --packet-b <private-B-packet> --output-a <private-A-output> --output-b <private-B-output> --output-dir <private-output-dir> --run-id p0_fk_model_review_disagreement_20261106_full_001 --expected-commit fc06c87131f71cb575a316b9bac697b6c778d119`。
- 环境：`think2sql_20260909`，Python 3.12.14；仅 Python 标准库；CPU-only，最多 4 个线程，墙钟上限 60 秒。运行时间 0.011932 秒。进程峰值 RSS 未采集。
- 资源检查快照：4×RTX 4090；GPU 1/2 各约 24 GiB 空闲，GPU 0/3 有占用；RAM 可用约 444 GiB，192 个 CPU 核。分析没有使用 GPU、模型、API、网络或 SQL。
- 私有输出：`/mnt/liansp3/sources/results/gfmrag_p0_fk_model_proxy_disagreement_20261106_01/full_001/aggregate_summary.json`；日志：`/mnt/liansp3/logs/gfmrag_p0_fk_model_proxy_disagreement_20261106_01/full_001.log`。

## 结果

两模型各自有效输出为 59/60 与 58/60；双方均有效的 57 个单元中，精确决定和接受集合一致 28 个，即 49.12%。其余 29 个不一致里，23 个连“单映射/多映射”决定都不同，6 个决定相同但接受集合不同。

| 分组 | 单元数 | 双方有效 | 精确一致 | 一致率 |
|---|---:|---:|---:|---:|
| 2 个候选 | 45 | 44 | 17 | 38.64% |
| 3 个候选 | 15 | 13 | 11 | 84.62% |
| 候选顺序不同 | 31 | 29 | 15 | 51.72% |
| 候选顺序相同 | 29 | 28 | 13 | 46.43% |

三候选组只有 13 个双方有效单元，比例不稳定，只作描述。候选顺序相同与不同两组的一致率接近；本审计没有发现明显的展示顺序关联模式，也不能据此作因果判断。

审阅者 A 将 9 个单元判为多映射，B 判为 26 个。20 个单元是 A 判单映射、B 判多映射；反向只有 3 个。可观测的主要分歧因此是“一个还是多个 FK 映射可以接受”的判定口径。双方 57 个有效单元都给出至少 2 的自报置信度，仍只有 28 个精确一致；置信度没有筛除分歧。两模型都属于 Qwen 家族，且自报置信度未经校准，不能据此推断准确率。

## 结论和下一步

这次归因支持一个有限结论：当前两模型代理标签的不稳定主要表现为可接受映射集合的**基数判断**不同，而不是候选显示顺序造成的明显差异。它不能指出哪一方正确。

按原双模型预注册门槛，28 个可裁定单元低于 30 个，排序门仍未通过。本报告不会把这一门槛改写成通过，也不会把模型标签当成人工金标准。用户已选择继续用模型审阅；可另行预注册一次不同模型家族的盲审，检查三方多数代理标签是否达到探索性排序所需的样本门。即使达到，也只能做独立登记的探索性排序诊断，不能支持真实 Role 准确率主张。
