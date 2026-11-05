# P0 FK 候选定义恢复 v3：更正冻结指纹后的三臂复核

> **状态：预注册，尚未读取本轮输入、尚未运行。** v2 定位到冻结摘要与目标文件不一致；本轮为新的纠错复核，不复用旧 run ID。

## 研究问题与假设

v1/v2 两次 P1.5 Smoke 使用了同一个错误冻结摘要并在解析前停止。v2 中同一字节缓冲区、分块 helper 与独立 `sha256sum` 对目标文件计算出相同摘要，文件身份稳定。v3 仅把此摘要更正到经独立确认的文件指纹，重跑三臂的 smoke 门，并在三臂全部通过时按既定门槛运行 Full。

核心假设：失败原因是先前登记的输入指纹与指定 artifact 不匹配；纠正后，P1.5 同字节摘要/JSON 解析门及三臂 smoke 均通过。任一完整性、解析、环境、计数或资源门失败即可证伪并停止。

## 预注册

- **实验 ID：** `p0_fk_candidate_definition_recovery_v3_20261105_01`
- **层级：** exploratory CPU-only 输入完整性与 FK 标签定义审计；不属于方法效果证据。
- **核心假设、预算、成功与停止门：** 见 [实验计划](../../plans/p0_fk_candidate_definition_recovery_v3_20261105.md) 和 [机器可读配置](experiment_config.json)。
- **项目仓库/基线：** `bArtyom/gfm-rag`，v2 结果 commit `8f5d60f919786f967dd9bfafecc12b2000ec0a9e`；新分支 `research/p0-fk-definition-recovery-v3-20261105`。
- **执行源码：** `scripts/text2sql/reconcile_p0_fk_candidate_definitions_v3.py` 与 `scripts/text2sql/compare_p0_fk_candidate_definitions_v3.py`；哈希见配置。只更新 runner 的 run ID 和 FK artifact 冻结摘要，不改 packet/P1.5 算法及计数定义。
- **数据：** 固定 BIRD dev 1,534 题，只用于开发/诊断。输入 SHA 与 artifact 正确冻结值见配置；SQL、问题文本、逐题哈希和私有 artifact 内容不上传。
- **环境：** Python 3.10.22/SQLGlot 26.33.0 与 Python 3.12.14/SQLGlot 28.0.0，复用已存在 Conda 环境。
- **执行命令、run ID、资源预算、硬件快照、输出路径：** 见配置、运行日志和最终回执。

## 执行状态与结果

尚未运行。所有结果与结论待 smoke 门完成后填写；Smoke 未全部通过时不会启动 Full 或 crosswalk。

## 解释边界

即使所有门通过，本轮也只验证输入完整性、三套 parser/标签定义的运行复现及匿名计数差异。它不能说明哪套 FK 定义在语义上正确，不能恢复没有逐题记录的历史 P0 v3 的 956/174 计数，也不会产生可信 Gold Role 标签或 QuadGraph/GFM 方法收益结论。
