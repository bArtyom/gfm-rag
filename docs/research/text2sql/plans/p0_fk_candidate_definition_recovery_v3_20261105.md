# P0 FK 候选定义恢复 v3：更正冻结指纹后的三臂复核（2026-11-05）

## 触发原因与上轮证据

v2 的两组 packet Smoke 均通过；P1.5 Smoke 在解析输入前因冻结 FK artifact SHA 不匹配而停止。失败回执及独立复核显示：同一文件字节缓冲区摘要、旧分块 helper 和 `sha256sum` 相同，文件身份稳定；实际文件摘要为 `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`，而 v1/v2 共同登记的摘要为 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。因此 v1/v2 的 P1.5 Smoke 不是对目标文件的有效重现，且不能在原 run ID 内修正冻结指纹。

本 v3 是新的、有独立 run ID 的纠错复核。它只把 P1.5 artifact 的预期 SHA 更新为 v2 对同一文件通过三种读取路径确认的值；数据、packet/P1.5 解析代码、FK 匹配定义、样本顺序、分母、计数门槛、环境和停止规则保持不变。旧实验、结果和配置均保留。

## 核心假设与问题

- **核心假设：** v1/v2 的 P1.5 Smoke 失败由预注册错误指纹导致；在新实验中冻结经独立确认的实际文件摘要后，同一文件句柄的摘要与解析可通过完整性门，三个定义可通过五题 Smoke。
- **可证伪条件：** 运行时摘要不等于新冻结值、文件身份变化、JSON 结构/解析失败、任一 Smoke 失败或输入/源码版本不符。
- **研究问题：** 纠正预注册指纹后，三套既定 FK 候选定义能否在各自固定环境中通过 smoke，并在全量只读扫描中复现其自身计数？
- **范围：** CPU-only 实现与标签定义审计，不是 QuadGraph/GFM 方法增益实验；不创建 Role 标签、不做 SQL 执行、不调用模型/API。

## 数据、版本与实现

- 项目仓库：[bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)。本轮从 v2 结果 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e` 建立新分支 `research/p0-fk-definition-recovery-v3-20261105`。
- 预注册前已读取该项目 commit 上的根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md` 和 `reproducibility-contract.md`。对应 blob SHA：`ba967338e1c257af24b683102aebca9c87b62a3e`、`9992c42ed5a87b1bd31ce9b0fc5f144d57f6e650`、`0c9eb1f5f0906f287b2b53edf8b701c156361d41`、`d31e8bc078a02695e1cef96efd61171d4329ebc0`。
- 数据仍是已反复用于开发/诊断的 BIRD dev，不是独立测试集。`dev.json` SHA-256 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` SHA-256 `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- P1.5 artifact 的本轮冻结 SHA-256：`5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。预注册代码会对同一有界字节缓冲区做摘要与 JSON 解析，并独立计算旧分块路径摘要；记录文件身份稳定性。失败回执只保留状态、hash/计数和安全代码位置，不记录 SQL、问题、数据库名或异常原文。
- 解析/定义代码与环境维持冻结：packet/Python 3.10.22/SQLGlot 26.33.0；packet/Python 3.12.14/SQLGlot 28.0.0；P1.5 `golden_join_audit`/Python 3.12.14/SQLGlot 28.0.0。
- 两个本轮执行脚本及 SHA-256、原始 P0/P1.5 源码 SHA、所有输入摘要和确切命令写入同目录 `reports/p0_fk_candidate_definition_recovery_v3_20261105_01/experiment_config.json`。

## 实验层级、预算与成功判据

- **层级：** P0 输入完整性与定义可复核性；exploratory，不是主线收益证据。
- **预算：** 最多 6 个 runner 进程；每进程 wall/CPU ≤600 秒、RSS ≤4 GiB、最多 8 线程；累计 CPU ≤3,600 秒。GPU/model/API/SQL/download/install 均为 0。
- **Smoke：** 三臂各按冻结顺序处理前 5 题。三个 Smoke 必须全部通过输入/代码/artifact 摘要、稳定身份、输出结构、分母、资源与隐私门，才启动任何 Full。
- **Full：** 仅在三 Smoke 全过时执行。每臂 1,534 题，预期 1,534 parse 成功、1,140 JOIN-ON；packet 两个版本均需复现 1,043 个 FK 匹配题和 176 个多 FK 候选题；P1.5 需复现 970/197。
- **crosswalk：** 仅在三 Full 都过且题目哈希集合一致时运行；只报告匿名实现定义差异，不当作语义正确率。
- **停止：** 任一摘要/身份/解析/计数/资源/隐私门失败即停止剩余运行；不在同一 run ID 重试，不修改冻结数据、定义、分母或指标。v3 失败则保留 P0 Role Gate NO-GO，下一步先分析证据，不自动再开同类轮次。

## 运行与归档位置

- 私有结果根：`local:results/gfmrag_p0_fk_candidate_definition_recovery_v3_20261105_01/`
- 私有日志根：`local:logs/p0_fk_candidate_definition_recovery_v3_20261105_01/`
- 运行前提交并回读注册材料后，才可重读本轮输入并启动三个 smoke。
- 结果报告位于 `docs/research/text2sql/reports/p0_fk_candidate_definition_recovery_v3_20261105_01/README.md`；每个 run 单独归档，不覆盖旧报告。

## 结果状态

预注册完成；截至注册时尚未重读本轮输入，也未运行 v3 Smoke/Full。v2 的结果仅作为更正指纹的依据，不混入 v3 的样本或成绩。
