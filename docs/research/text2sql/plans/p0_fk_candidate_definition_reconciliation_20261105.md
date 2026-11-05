# P0 FK 候选定义对账计划（2026-11-05）

## 研究问题与核心假设

同一份 BIRD dev `dev.json` / `dev_tables.json`（历史 SHA-256 固定）产生过三套不同的 JOIN/FK 汇总：历史 P0 v3 为 956 个 FK 匹配题 / 174 个多 FK 候选题；P1.5/P2a.5 为 970 个唯一 FK JOIN 题 / 197 个多 FK 候选题；2026-10-25 P0 packet 为 1,043 / 176。假设这些差异至少部分来自解析器版本和“FK 命中”/“候选 JOIN”定义不同；不预设差异已解释，不调整算法去凑历史计数。

## 层级、主线关系与预算

- 层级：只读 exploratory 定义/实现审计；不属于方法效果主实验。
- 核心假设：在固定输入下，运行时/SQLGlot 版本差异和判定口径可分别量化；现存 P1.5 与 P0 packet 脚本的逐题差异可归因到可检查的 AST/候选规则。
- 主线证据：否。此工作只决定能否构造可信 FK/Join-Role 标签，不测检索、GNN、SQL 生成、SQL EX 或论文方法收益。
- 预算：CPU-only，每个正式进程 wall/CPU 上限 600 秒、RSS 4 GiB、线程最多 8；GPU、模型、API、SQL 执行、下载、依赖安装与人工审阅均为 0。固定环境分别为 `t2sql_code_audit_20261005`（Python 3.10.22 / SQLGlot 26.33.0）及 `think2sql_20260909`（Python 3.12.14 / SQLGlot 28.0.0），运行时使用对应环境的绝对 Python 路径。
- 成功判据：输入 SHA 与登记一致；每个 runner 的样本分母为 1,534、成功解析 1,534、含 `JOIN ... ON` 的题数为 1,140；P0 packet 定义在其冻结环境复现 1,043/176，P1.5 精确实现复现 970/197；在 SQLGlot 28 的同一环境中比较两套规则，以仅含不可逆题目哈希和布尔/计数类别的私有 crosswalk 完整分解匹配集合差异；分别报告 packet 规则从 SQLGlot 26 到 28 的变化。任一分母或输入 hash 不符、标签集合差异无法穷尽、资源上限超出，则停止且不进入盲审。
- 历史 P0 v3 的 956/174：只有在私有历史产物中找到可审计逐题标签和版本化源代码时才纳入集合对照；若只有聚合数，则标为 aggregate-only / unreproducible，不将其强行解释为以上两套规则之一。
- 停止条件：任一输入 hash 不符；冻结源码 SHA 不符；Smoke 5 题无效；分母偏离；内存、CPU 或 wall 超预算；隐私控制失败；或全量跨方法 set delta 未完全解释。失败的 run ID 不重试，修订另立登记。

## 冻结来源与定义差异

- 项目仓库：`https://github.com/bArtyom/gfm-rag`，研究基线 `research/p0-role-review-packet-20261025` / commit `f0d9ceeed8dc5b19a5bfddc83bdfabc6ee6e3e4e`；本试验分支从该 commit 派生。
- Packet runner：`scripts/text2sql/prepare_p0_role_review_packet.py`，SHA-256 `5c84af91edc6dd39cd1fba39105dfc74b804be17912d91edab5eba2ff180eebc`。它在整条 parsed query 上建立别名表，递归扫描 `JOIN ON` 后代 `EQ`，只要任一等式命中 `dev_tables.json` 的任一 JSON FK 列对就记题级命中；多 FK 候选按等式两端表对关联的 JSON FK 映射数计算，不要求命中的列对恰好属于该候选映射。
- P1.5 runner：`scripts/text2sql/run_p1_5_diagnostics.py`，SHA-256 `af59d01d22a6b5d5538231b38c2bf52e0355a9193a5773f40b14d29470ec40cf`。复用其 `golden_join_audit`：SQLGlot scope/local alias 处理、直接 Column=Column 条件、对比 SQLite 完整 FK 实例的全部有序列对；唯一完整实例、部分匹配、多重匹配与无匹配分别计数。
- P2a.5 runner：`scripts/text2sql/run_p2a_5_error_audit.py`，SHA-256 `e046595df72d3b684062a54d2fffc2c8df13cae419b056625b8981c20b805085`；仅用于核对其诊断标签是否来自同一 scope-aware 完整实例规则。
- 输入历史 SHA-256：`dev.json`=`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json`=`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 私有参照：历史 P0 `/mnt/liansp3/sources/results/quadrag_p0_20261014/full_audit_v3.json`；P1.5 `/mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json`，已知 SHA-256 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。文件存在性/哈希/结构将在本登记推送后核验；私有内容不得进入公开产物。

## 执行顺序与输出

1. 提交并推送本登记后，才检查题目/Gold SQL 与私有逐题 artifact；先保存环境、资源与输入 hash 回执。
2. 分别用两套冻结环境对五条固定 Smoke 输入运行 packet 规则，写入独立私有目录；不得创建 reviewer packet。
3. 两个 Smoke 均通过后，在新 runner 中复用冻结函数，对 1,534 题运行 packet@26、packet@28 与 P1.5@28。SQLite 只读读取 schema 元数据；不得执行参考或预测 SQL。
4. 若历史 P1.5 artifact 含逐题结果，按哈希题键与重新计算标签对齐；只存题键哈希及各规则标签，不保存文本/ID/SQL。若 artifact 只有聚合，注明无法做历史逐题对照。
5. 输出匿名聚合：解析/Join 分母、各定义计数、交集、各方向差集、规则分类原因、环境版本贡献及历史 P0 v3 可复现性状态。私有逐题 crosswalk 与原始日志不上传。
6. 只有所有 Gate 通过，才允许另外登记一轮盲审包生成；本轮不生成盲审材料。

## 公开复现边界

公开报告仅含公开源码哈希、数据文件哈希、匿名分母/计数和差异类别计数；不包含数据库名称、原题、Gold SQL、逐题输出、原始 artifact 内容、服务地址或密钥。实验运行后不因结果修改阈值/标签定义，也不重写旧报告中的 956/174、970/197 或 1,043/176。
