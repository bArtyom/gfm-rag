# P0 Mini-Dev JOIN scope taxonomy：预读取哈希更正 A1

**登记时间：2026-11-06；状态：唯一工程恢复，Full 尚未启动。** 原预注册保留不改：[方案](p0_minidev_join_scope_taxonomy_20261106.md)。

## 触发原因

第一次 Smoke `p0_minidev_join_scope_taxonomy_20261106_cpu_smoke_001` 在验证输入哈希时停止。独立 `sha256sum` 与旧审计报告均确认本地 Mini-Dev JSONL 仍为 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`，schema JSON 仍为 `5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`。差异来自新配置中 schema hash 的字符转置：注册值为 `...c310dceaa9f13e1a413...`，实际及既有冻结记录为 `...c310dceaa9f13a1e413...`。

执行 traceback 停在 `input_hashes == expected_hashes` 检查。程序先运行了 7 个逻辑 fixture，并在读取 JSONL 或解析任何 Gold SQL 前失败；没有生成 Smoke 输出目录，也没有改数据或旧结果。该日志保留在 `/mnt/liansp3/logs/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/smoke_001.log`。

## 唯一恢复规则

- 只新建 `configs/text2sql/p0_minidev_join_scope_taxonomy_20261106_amendment1.json`，以正确冻结 hash 替代错误配置；原注册配置原样保留。
- 在 runner 中显式记录 Smoke 尝试号。使用新 Run ID `p0_minidev_join_scope_taxonomy_20261106_cpu_smoke_002` 重跑同一确定性 5 题 Smoke；Full 仍只有一次，Run ID `p0_minidev_join_scope_taxonomy_20261106_cpu_full_001`。
- 数据、schema、SQLGlot 版本、7 个逻辑 fixture、直接投影规则、指标、95% 成功门、样本拆分和资源上限全部冻结不变。
- Smoke_002 任一输入哈希、fixture、baseline 或分类守恒检查再失败，则结束本项目，不作第三次尝试。通过后才允许 Full 495 题。
- Smoke_001 计作失败尝试，不进入任何指标。Smoke_002 的结果亦不与 Full 混合；报告单列。

本更正不改变科学假设，不降低任何门槛，也不授权 G-reasoner/Dense 排序或模型审阅。
