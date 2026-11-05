# P0 FK 候选定义恢复 v2：文件哈希与三臂复核（2026-11-05）

## 研究问题与痛点

相同 BIRD dev 输入哈希下，历史 P0 v3、P1.5/P2a.5 与 P0 packet 分别记录 956/174、970/197、1,043/176 个 FK 匹配题/多 FK 候选题。最近恢复轮的两个 packet 五题 Smoke 通过；P1.5 臂在 FK artifact SHA-256 闸门以 `RuntimeError` 停止。外部校验在运行前后均得到登记摘要，但失败回执没有保存运行时计算摘要。

本轮只回答两个问题：

1. 对同一个冻结 FK artifact，目标 Python 解释器中的 runner、独立文件句柄读取及路径重开是否得到同一 SHA-256；从已校验的字节解析出的 JSON 是否就是被校验的那份文件？
2. 若完整性门通过，三个冻结的 parser/label 定义能否在新 run ID 下通过五题 Smoke，并在一次全量只读运行中分别复现其已登记计数？

这是一项 CPU-only exploratory 实现与标签定义审计，不是方法效果实验。历史 v3 的 956/174 仅有聚合值，无可复核的逐题标签与代码，因此本轮不会推测这组计数的来源，也不能把它纳入题级 crosswalk。

## 核心假设、实验层级与结论边界

- **核心假设：** 上次失败发生在文件定位/文件状态或读取链路，而非 SHA-256 算法本身；将摘要和 JSON 解析绑定到同一受控文件句柄后，可以得到可审计的完整性证据。此假设可被观察到的摘要不一致、文件身份变化或解析失败推翻。
- **层级：** P0 数据/标签定义审计；不属于主线方法增益证据。
- **主线证据：** 否。无模型、图前向、训练、SQL 执行或人工角色审阅。
- **冻结定义：** packet / Python 3.10.22 / SQLGlot 26.33.0；packet / Python 3.12.14 / SQLGlot 28.0.0；P1.5 `golden_join_audit` / Python 3.12.14 / SQLGlot 28.0.0。除哈希诊断与失败回执外，不改解析、FK 匹配、候选定义、分母、预期计数或排序。

## 预注册的完整性诊断

P1.5 FK artifact 的预期 SHA-256 固定为 `5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。诊断器只处理 artifact 字节，不打印或公开其 JSON 内容。按以下顺序执行：

1. 检查文件为普通文件且不是末端符号链接；记录本地私有回执中的 `device/inode/size/mtime_ns/ctime_ns`，并记录公开汇总允许发布的文件大小和摘要。
2. 打开一次只读文件句柄，读取字节一次；在这批内存字节上计算 SHA-256，再用同一批字节解码/解析 JSON。解析前不得重新按路径读取。
3. 对同一路径执行旧版分块 `sha256_file` 读取，再比较摘要；打开前后及两个路径读取阶段的文件身份必须一致。输入上限为 2 MiB，超出即停止。
4. 将预期摘要、单句柄摘要、旧分块 helper 摘要及文件身份稳定标记写入本地私有结果/失败回执；异常回执不含异常消息、源码行、局部变量、SQL、问题文本、数据库名或 JSON 内容。
5. 只有摘要都匹配、身份稳定且 JSON 结构检查通过时，才继续该臂的五题解析。

## 冻结数据与版本

- 项目仓库：`https://github.com/bArtyom/gfm-rag`。
- 本轮基线：远端分支 `research/p0-fk-candidate-definition-recovery-20261105`，commit `81521b33b48fe8f9e06a3b9d9c653e627dcbc79e`；本轮使用新分支 `research/p0-fk-definition-recovery-v2-20261105`，从该 commit 建立独立工作分支。
- 当前公开指导读取自 `main`：根 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`。对应 GitHub blob SHA 分别为 `ba967338e1c257af24b683102aebca9c87b62a3e`、`cb88d3d9b296e1ce9f18c02446795c00cb586087`、`0c9eb1f5f0906f287b2b53edf8b701c156361d41`、`d31e8bc078a02695e1cef96efd61171d4329ebc0`。
- `dev.json` SHA-256：`630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`。
- `dev_tables.json` SHA-256：`35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- FK artifact SHA-256：`5bc60f6d64429215fa92c3d3a42f1a4881dc77c09839729153fb55a119555060`。
- 三套 runner 与定义 hash 沿用恢复轮配置；本轮新增 recovery runner/comparator 的 hash 在公开 config 中冻结。
- 本轮执行器：`scripts/text2sql/reconcile_p0_fk_candidate_definitions_v2.py`；匿名比较器：`scripts/text2sql/compare_p0_fk_candidate_definitions_v2.py`。二者的 SHA-256 在 `experiment_config.json` 冻结。

## 样本、指标、门槛与停止条件

- 固定样本顺序：每臂前 5 题 Smoke；只有三个 Smoke 全部通过才允许三个 Full，每个 Full 为 1,534 题。Smoke 只作输入/执行闸门，不进入 Full 指标。
- Smoke 指标：处理题数、SQL parse 成功数、JOIN-ON 题数、FK 匹配题数、多 FK 候选题数、输入/源/artifact SHA、文件身份稳定性及资源用量。
- Full 分母冻结为 1,534 题、1,534 parse 成功、1,140 个 JOIN-ON 题。预期计数：两个 packet 定义各为 1,043/176；P1.5 定义为 970/197。
- 只有三个 Full 都复现各自冻结计数、问题哈希集合相同、所有定义差异落入预登记分类后，才运行匿名 crosswalk。该结果只描述实现/定义差异，不证明任何 JOIN 角色语义正确。
- 任一输入/代码/环境 hash 错误、摘要或文件身份不一致、JSON 结构错误、Smoke 失败、Full 计数不符、crosswalk 分母不一、资源或隐私门失败，立即停止；失败产物保留，不在此 run ID 下重试，不修改冻结摘要/解析规则/计数以求通过。
- 任一 Smoke 失败即不启动任何 Full；三臂全量通过后也不自动生成审阅包。需要人工标签时，必须另行依照双人盲审协议登记。

## 预算、环境与执行命令

- CPU-only；最多 8 个线程；每个进程 wall/CPU 不超过 600 秒、RSS 不超过 4 GiB；Smoke/Full 总计最多 6 个 runner 进程及 3,600 CPU 秒。
- Python 3.10 packet 环境：`/root/miniconda3/envs/t2sql_code_audit_20261005/bin/python`，SQLGlot 26.33.0。
- Python 3.12 环境：`/root/miniconda3/envs/think2sql_20260909/bin/python3.12`，SQLGlot 28.0.0。
- 运行前必须检查 `nvidia-smi`、`free -h`、`nproc`、磁盘与相关进程；本实验不分配 GPU，不安装/升级依赖。
- GitHub 源码、config、计划和报告预登记并验证回读后才访问数据/artifact。实际运行命令在远端执行 commit 冻结时写入 `experiment_config.json`；Shell 只重定向到权限 0600 的本地日志。
- 独立结果根：`/mnt/liansp3/sources/results/gfmrag_p0_fk_candidate_definition_recovery_v2_20261105_01/`；独立日志根：`/mnt/liansp3/logs/p0_fk_candidate_definition_recovery_v2_20261105_01/`。旧结果不覆盖。

## 后续判断

若 hash/Smoke/Full Gate 通过，可把 packet@26、packet@28、P1.5@28 的题级差异按冻结规则做匿名描述；仍不能恢复历史 P0 v3 956/174，也不能直接把多 FK 候选变成 Gold Role。若 Gate 失败，继续保留 Role Gate NO-GO，下一步只针对失败证据做独立修复登记，不开展 Role 预测或 SQL 增益实验。
