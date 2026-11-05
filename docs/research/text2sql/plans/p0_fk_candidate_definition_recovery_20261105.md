# P0 FK 候选定义对账恢复计划（2026-11-05）

## 为什么开恢复轮

原 `p0_fk_candidate_definition_reconciliation_20261105_01` 的两组 P0 packet Smoke 通过，P1.5 五题 Smoke 在约 1.08 秒后以通用 `RuntimeError` 停止。原 runner 按隐私保护省略异常位置，因此该失败不能定位，也不能据此判断标签定义。原 run、报告及产物全部保留；本计划用新实验 ID 和新结果目录，只补安全诊断回执，不改任何 FK 定义、解析器版本、计分规则、阈值或输入。

## 研究问题与范围

- **研究问题：** 上次 P1.5 Smoke 的 `RuntimeError` 出在哪个阶段/调用点？在安全诊断下，三个冻结 runner 是否都能对同一五题 Smoke 产生有效结果？若通过，三套历史计数中可复现的两种定义差异能否在全量题目级交叉表中分解？
- **痛点依据：** 同一 BIRD dev 输入 hash 下存在 956/174、970/197、1,043/176 三组“FK 命中题 / 多 FK 候选题”计数。可信人工 Role 标签为 0，因而 Role 准确率、Role 监督和真实 SQL 扩样仍无法解释。
- **假设：** 安全回执会定位先前实现失败；若恢复后的三个 Smoke 和 Full 都过冻结门，SQLGlot 26→28 的 packet 规则变化及 packet@28→P1.5@28 的规则变化可由题级匿名布尔标签和冻结的 P1.5 逐 JOIN 计数分层描述。
- **层级：** 只读 exploratory 标签定义/实现审计；不是方法效果主实验，不是 Role 评测。
- **不纳入的历史计数：** P0 v3 的 956/174 只有聚合值，没有可复核的逐题标签/版本化代码。本轮不猜测其归属，也不将它与其它逐题集合硬配；报告仍标 `aggregate-only / unreproducible`。

## 唯一改动与隐私边界

恢复 runner 是原冻结协调器的副本。唯一科学无关改动是新增私有 failure receipt：仅写 `error_type`、异常模块、调用栈的文件模块名/函数名/行号、实验阶段、题目键 SHA-256 和已处理计数。**不写**异常消息、源码行、局部变量、问题/SQL、数据库名或原始 ID。外层终端输出仍仅写异常类型和 receipt 是否创建。正常结果 schema/三个计数定义与原协调器相同。

另用恢复版 comparator 产出原 comparator 的全部配对布尔计数，并预先增加受限分层：packet@26 对 packet@28 按版本间标签方向统计；packet@28 对 P1.5@28 对 `fk_match` 差异按 P1.5 的 parse / ON / exact / ambiguous / partial / unmatched 计数状态分层；`multi_fk_candidate` 差异按方向及 P1.5 候选 JOIN 数是否为零分层。公开聚合只含类别计数，不含题目键；匿名题目交叉表和 hashed key 只写私有目录。分层描述定义差异，不把 SQLGlot 版本解释为唯一因果因素。

## 冻结输入、环境与科学条件

- 仓库：`https://github.com/bArtyom/gfm-rag`；基线为 `research/p0-fk-candidate-definition-20261105` 远端 commit `6c1e29b13d5cd0034fb769d91ed79cc282537157`；本轮独立分支 `research/p0-fk-candidate-definition-recovery-20261105`。
- 数据 SHA-256：`dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 冻结 P1.5 FK artifact：`fk_gate_private.json` SHA-256 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。
- 冻结源：P0 packet runner SHA `5c84af91edc6dd39cd1fba39105dfc74b804be17912d91edab5eba2ff180eebc`；P1.5 runner SHA `af59d01d22a6b5d5538231b38c2bf52e0355a9193a5773f40b14d29470ec40cf`；P2a.5 runner SHA `e046595df72d3b684062a54d2fffc2c8df13cae419b056625b8981c20b805085`。新 recovery runner/comparator 的 SHA 记录在同目录 config。
- 三臂：packet / Python 3.10.22 / SQLGlot 26.33.0；packet / Python 3.12.14 / SQLGlot 28.0.0；P1.5 `golden_join_audit` / Python 3.12.14 / SQLGlot 28.0.0。每臂仍处理固定输入顺序的前 5 题 Smoke，Full 才处理 1,534 题。
- **解释器调用约束：** 预检发现此主机上 `conda run -n <env> python3` 实际返回 Python 3.9.20 / SQLGlot 30.12.0；各目标环境内的绝对解释器经核验分别返回登记的 Python 3.10.22 / SQLGlot 26.33.0 和 Python 3.12.14 / SQLGlot 28.0.0。因此所有恢复 run 使用 `conda run -n <env> <该环境绝对 python 路径>`，保持同一环境，避免误用 PATH 中的解释器；没有安装、升级或重建依赖。
- 预期 Full 分母：1,534 条、解析成功 1,534、含显式 `JOIN ... ON` 的 1,140 题。冻结 Full 计数：packet 两版各按原登记 1,043/176；P1.5 按原登记 970/197。只要计数不匹配就停止比较并保留观测 receipt，不为凑数修改定义。

## 执行顺序、预算和停止门

1. 本协议、恢复 runner/comparator、config 与初始报告先提交并推送到本仓库分支；之后才验证数据/私有 artifact 文件 hash 并启动 Smoke。实际实验代码必须从该远端 commit 运行。
2. 使用三个全新 run ID、独立结果文件和日志，同时或顺序运行三个 5 题 Smoke。每个任务 CPU-only、最多 8 线程、wall/CPU ≤600 秒、RSS ≤4 GiB；总共最多 6 个进程（3 Smoke + 3 Full），累计 wall/CPU 上限各 3,600 秒。每一臂只尝试一次；失败写安全 receipt，不复用 run ID。
3. 只有三个 Smoke 均输出 `SMOKE_PASS`、分母与 hash 正确、输出结构有效且资源门通过，才进入三个 Full。任一 Smoke 不通过就停止全部 Full。
4. Full 只读数据、Schema 与已冻结 FK artifact；不执行 Gold SQL，不加载模型、不训练、不调用 API/GPU、不安装依赖、不生成盲审包。三个 Full 均 `FULL_COMPLETE`、分母和冻结聚合计数匹配后，才运行恢复版 comparator。
5. 任一输入/hash、环境、源码、分母、资源或隐私门失败；任一差异不能由冻结定义状态完整分类；或一个 arm 失败，立即停止，不建立盲审包。需要进一步修复时再立新登记。

## 成功判据与下一步

- **Smoke Gate：** 三臂有效输出并通过数据/source hash、五题分母、资源与隐私校验。
- **Full Gate：** 三臂复现各自冻结计数和完整分母；题目 hash 集合完全一致；所有布尔标签差异可由预注册的版本/规则状态类别覆盖。仅表示审计可复现，不表示 Role 标签正确。
- **停止判据：** 如 Full Gate 通过，再由新登记的 P0 双人盲审包工作继续产生少量独立人工 Role 标签；只有盲审定义、映射身份和仲裁门通过后才设计 Role-aware/path 方法效果实验。若 Gate 不通过，先报告是哪一类实现/数据问题，Role Gate 继续 NO-GO。

## 公开产物

- 本计划与配置在 `docs/research/text2sql/plans/` 及本报告目录。
- GitHub 仅提交协议、代码、软件/输入 hash、匿名聚合类别、资源和结论；逐题 crosswalk、题目 hash、Gold SQL、原始结果与日志留在权限为 0600 的本机结果目录。
- 不覆盖原实验 `p0_fk_candidate_definition_reconciliation_20261105_01` 的报告、日志或结果。
