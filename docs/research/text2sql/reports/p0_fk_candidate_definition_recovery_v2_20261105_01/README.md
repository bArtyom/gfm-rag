# P0 FK 候选定义恢复 v2：哈希一致性与三臂复核

> **状态：预注册，尚未读取本轮输入、尚未运行。** 这是一项 CPU-only 数据完整性与标签定义审计，不是方法效果实验。

## 问题与假设

最近一轮恢复中，packet 的两个五题 Smoke 通过；P1.5 Smoke 在冻结 FK artifact SHA 闸门停止。外部 SHA-256 在运行前后均匹配冻结摘要，但失败回执没有运行时摘要。本轮将同一文件句柄读取的字节用于哈希和 JSON 解析，并记录文件身份是否稳定。

核心假设：先前失败来自文件定位/读取链路状态，而不是 SHA-256 定义。若同句柄摘要、旧分块路径 helper 与冻结摘要不一致，或文件身份变化，假设不成立并立即停止。

## 预注册条件

- **实验 ID：** `p0_fk_candidate_definition_recovery_v2_20261105_01`
- **层级：** exploratory CPU-only 实现/标签定义审计；不是主线方法证据。
- **冻结问题：** 1,534 BIRD dev 样本，显式 JOIN-ON 分母 1,140；三臂定义、解析器版本与期望计数见 [配置](experiment_config.json)。
- **来源仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，基线 commit `81521b33b48fe8f9e06a3b9d9c653e627dcbc79e`；本轮新分支 `research/p0-fk-definition-recovery-v2-20261105`。
- **运行层改动：** 新增可审计的 FK artifact 同句柄哈希/解析路径与安全摘要回执；冻结的 packet/P1.5 算法、Gold 匹配定义、数据、计数和停止门不变。旧 runner 和旧结果保留。运行脚本及哈希见 [配置](experiment_config.json)。
- **成功门：** 输入/源码与 artifact SHA 对齐、文件身份稳定；三个五题 Smoke 全部通过；之后三次 Full 均处理 1,534 题、解析 1,534 题、JOIN-ON 1,140 题并复现各自冻结 FK 计数；最后才能产出匿名 crosswalk。
- **停止门：** 任一 Smoke、完整性、结构、分母、资源或隐私检查失败即停，不启动后续 Full，不在同一 run ID 重试，不更改冻结值。
- **预算：** 每进程 CPU/wall ≤600 秒，RSS ≤4 GiB，最多 8 线程；最多 6 个 runner 进程、累计 CPU ≤3,600 秒。GPU/API/模型/训练/SQL/下载/安装均为 0。

## 数据、环境与资源

冻结输入 SHA-256：`dev.json` `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`；FK artifact `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。artifact 内容、问题文本、SQL 和逐题哈希只留本机权限受控目录。

Python 3.10.22 / SQLGlot 26.33.0 与 Python 3.12.14 / SQLGlot 28.0.0 均复用已有 Conda 环境。启动前检查 GPU、内存、CPU、磁盘和相关进程；此项任务只用 CPU，不安装或升级依赖。精确源码 commit、命令、资源快照和运行结果在注册文件与完成后的回执中追加。

## 结果

尚未运行。无全量计数、差异 crosswalk 或科学结论。

## 解释边界

即使本轮所有门槛通过，也只说明三套当前定义可被有界复核及其题级差异可描述。旧 P0 v3 的 956/174 没有逐题产物，仍为 `aggregate-only / unreproducible`。多 FK 候选不等于可信 Role 标签；本轮不会产生人工语义判断、Role Accuracy、Join-Path Accuracy 或 SQL EX 结果。
