# P0 FK 候选定义恢复 v2：哈希一致性与三臂复核

> **状态：`STOP_INVALID_SMOKE`（2026-11-05）。** 两组 packet Smoke 通过；P1.5 Smoke 在冻结 FK artifact 摘要门停止。按预注册规则未启动任何 Full，也未生成 crosswalk。这是 CPU-only 数据完整性与标签定义审计，不是方法效果实验。

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

## 执行记录与结果

- **注册/执行源码 commit：** `516ff3fafc83f2bbff848dfed825db9951b65fdf`；远端分支 `research/p0-fk-definition-recovery-v2-20261105`，注册文件在运行前已逐文件 SHA 回读核对。
- **输入版本：** `dev.json` 与 `dev_tables.json` 的运行时 SHA-256 分别为 `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`、`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`，均匹配预注册值。
- **packet / Python 3.10.22 / SQLGlot 26.33.0 Smoke：** 5/5 解析成功，3 题有 JOIN-ON、3 题有 FK 匹配、0 题有多 FK 候选；wall 0.0633 秒、CPU 0.0608 秒、峰值 RSS 0.0264 GiB。
- **packet / Python 3.12.14 / SQLGlot 28.0.0 Smoke：** 同样 5/5 解析成功，3/3/0；wall 0.6061 秒、CPU 0.0984 秒、峰值 RSS 0.0278 GiB。
- **P1.5 / Python 3.12.14 / SQLGlot 28.0.0 Smoke：** 在处理问题前停止，状态 `STOP_INVALID`。冻结配置摘要为 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`；同一受控字节缓冲区的计算摘要、旧分块 helper 与独立 `sha256sum` 均为 `5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060`。文件大小 76,177 字节，身份在打开前后与路径复核期间稳定，非符号链接且 `O_NOFOLLOW` 可用。因摘要与冻结值不符，JSON 解析及五题分析都没有进行。
- **停止决定：** 三个 Smoke 未全部通过；没有任何 Full 运行，没有题级 crosswalk，没有可信 Role 标签，也没有新的 JOIN 或 SQL 效果结果。旧文件没有覆盖。
- **私有产物：** packet Smoke 结果与 P1.5 失败回执位于 `/mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_definition_recovery_v2_20261105_01/smoke/`；三份日志位于 `/mnt/liansp3/logs/p0_fk_candidate_definition_recovery_v2_20261105_01/`。结果/失败回执权限为 `0600`。
- **调用与资源：** GPU、模型、API、SQL 执行均为 0；无依赖安装。失败臂在完整性门退出，未记录到该臂解析资源指标。

## 结论与后续

当前证据定位到预注册中的 FK artifact 摘要与被指定文件内容不一致；同一字节缓冲区、分块 helper、路径身份检查与独立外部计算彼此一致。因此本轮没有证据支持“文件在读取链路中被替换”这一假设，失败更直接地指向冻结摘要与目标文件指纹不匹配。v1 与 v2 使用了同一个冻结摘要，所以 v2 不构成独立的 P1.5 Smoke 复现。

后续若继续，只能在新的实验 ID 和预注册 commit 中修正该输入指纹，并重新跑三臂 Smoke；不得在本轮替换摘要、复用 run ID 或启动 Full。只有新的三臂 Smoke 全部通过，才可按冻结条件考虑 Full。即使三套定义通过计数复现，也仍不能恢复只有聚合数字的历史 P0 v3 逐题标签，不能把“多 FK 候选”当成 Gold Role，也不能据此主张 QuadGraph/GFM 方法收益。

## 解释边界

即使本轮所有门槛通过，也只说明三套当前定义可被有界复核及其题级差异可描述。旧 P0 v3 的 956/174 没有逐题产物，仍为 `aggregate-only / unreproducible`。多 FK 候选不等于可信 Role 标签；本轮不会产生人工语义判断、Role Accuracy、Join-Path Accuracy 或 SQL EX 结果。
