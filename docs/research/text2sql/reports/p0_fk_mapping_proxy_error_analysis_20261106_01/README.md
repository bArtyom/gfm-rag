# P0 FK mapping 代理排序错误归因

**状态：完成；描述性、只读分析。** 本报告分析冻结的 G-reasoner FK mapping 排序 Pilot。它不改模型、不增加训练，也不产生人工 Join Role 标签。

## 问题

此前的冻结排序在模型代理标签上得到 G-reasoner Accepted@1 7/38，Dense Cosine 27/38。这里检查差距是否只出现在候选数量、候选列重叠或 FK 结构的某一类中。分析是描述性的，不能据此推断因果机制，也不能把代理标签当作真实正确性。

## 原方法与本轮实际改动

QuadGraph 原始 G-reasoner 是使用 Query、起点和关系图做 query-dependent 消息传播，并输出节点相关性分数的通用检索器。本研究前一轮把已知表对的 FK mapping 表示成候选节点，使用冻结 G-reasoner 给候选排序，并与共享 Query/mapping 表示的 Dense Cosine 比较。

**本轮没有改任何排序方法。** 仅对已保存的四种排名（G-reasoner、Dense Cosine、BM25 Okapi、稳定 mapping-ID 顺序）和冻结代理多数标签做 CPU 分层统计。未读取 Gold SQL、参考 JOIN 或执行结果；未编码、调用生成模型、训练或使用 GPU。

## 数据与协议

- 冻结排序 Full 共 55 个问题×表对；其中 51 个可裁定、38 个候选集合存在至少一个不接受项，进入主分析。排除独立 Smoke 5 个、接受全部候选 13 个和无法裁定 4 个。
- 代理标签来自两份 Qwen 与一份 Gemma 审阅输出的高置信精确多数规则；不代表人类标注。覆盖 4 个匿名数据库。
- 预设分层：候选数 2/3、接受集合大小、是否含复合 FK、候选 FK 的列重叠。公开小于 5 的单元合并或隐藏。
- 成功判据：只有预设结构分层出现清晰、可重复且跨库的 G-reasoner 正向模式，才登记新数据验证假设；否则停止同一代理标签方向，不追加调参或图变体。

## 结果

| 方法 | Accepted@1 | 比例 | MRR（首个接受候选） | 首个接受候选平均排名 |
|---|---:|---:|---:|---:|
| G-reasoner | 7/38 | 18.42% | 0.574561 | 1.921 |
| Dense Cosine | 27/38 | 71.05% | 0.855263 | 1.289 |
| BM25 Okapi | 22/38 | 57.89% | 0.767544 | 1.553 |
| 稳定 mapping-ID 顺序 | 22/38 | 57.89% | 0.767544 | 1.553 |

G-reasoner 相对 Dense 的配对结果为：双方都对 6、双方都错 10、只有 G-reasoner 对 1、只有 Dense 对 21；净差为 **−20** 个单元（差 **−52.63 个百分点**）。所有方法的 Accepted@3 都是 38/38，因为本分析的候选最多 3 个且标签集合非空；因此 Accepted@3 在这里没有区分力。BM25 与稳定顺序的 top-1 相同，且 BM25 分数在这些对比中并列，稳定 tie-break 起了决定作用。

| 预设分层 | n | G-reasoner Accepted@1 | Dense Accepted@1 | 配对净差（GFM 独有正确 − Dense 独有正确） |
|---|---:|---:|---:|---:|
| 2 个候选 | 25 | 5/25 | 14/25 | −9 |
| 3 个候选 | 13 | 2/13 | 13/13 | −11 |
| 候选列无重叠 | 10 | 1/10 | 5/10 | −4 |
| 仅一个端点列有重叠 | 28 | 6/28 | 22/28 | −16 |

38 个分析单元全都只有一个接受 mapping，且没有复合 FK。因此本数据不能比较单个/多个正确 mapping，也不能检验复合 FK 这一因素。双端列重叠的细分小于公开门槛，未单独报告。候选数与已公开的列重叠分层里都没有 G-reasoner 正向净差。

## 结论与边界

按预注册规则，未发现支持重开同一代理标签排序方向的结构子组；停止该排序分支，不做同数据调参或再挑图结构。观察到的是冻结模型在该代理标签集合上的排序差距，不是 G-reasoner 对真实 FK Role 的准确率估计，也不证明 Dense 在别的数据或 Gold SQL 上更好。真实人工 Role 标签仍为 0。

## 复现信息与产物

- 项目仓库：`https://github.com/bArtyom/gfm-rag`；分支：`research/p0-fk-rank-error-analysis-20261106`。
- 分析代码及预注册方案来自源提交 `374817b5ab40ce5503e6058b66b88960e634b5b7`（GitHub）/ `b3a1f892464947b20ce5af7b3d503c640a7406e4`（本地）。
- 数据：冻结排序运行 `p0_fk_mapping_model_proxy_rank_pilot_20261106_01`，输入模型审阅运行 `p0_fk_mapping_model_review_proxy_20261106_01` 和 `p0_fk_mapping_model_review_third_proxy_cpu_20261106_01`。逐题输入和审阅原文保留在本地私有目录，不提交到仓库。
- 环境：`think2sql_20260909`，Python 3.12.14；CPU-only，最多 4 线程；资源预检为 192 CPU、约 450 GiB 可用内存、112 TiB 可用磁盘。Full 分析墙钟 0.130 秒、峰值 RSS 19.5 MiB、CPU 0.021 秒。
- 执行：Smoke 5 对通过后，Full 38 单元分析完成；两个运行均无模型推理、无外部 API 请求，本分析 token 数为 0。
- 冻结 Full 排序 SHA256：`d06f07b2b1000e40dbc0614e9bdbe224a79130010011721b97eccaf3dd9b2484`。匿名结果 SHA256：`2c38768cfc26953859efdb3cd445b6a2fc47cad461dbde3edfa45c1bb2a0d66a`。
- 匿名聚合结果见同目录 [`aggregate_summary.json`](aggregate_summary.json)。该文件不含问题、数据库、mapping ID/身份、逐题模型输出或 Gold SQL。
