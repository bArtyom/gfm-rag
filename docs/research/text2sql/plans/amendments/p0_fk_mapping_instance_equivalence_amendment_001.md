# Amendment 001：恢复多目标 SQL-used mapping 的 Full 单元处理

**状态：Recovery Smoke_002 与 Full_002 已完成。** Amendment 从原注册提交 2a8523c599d8846ec452281de8ddc970afd32e4a 派生；旧失败记录保留，完整恢复结果见[实验报告](../../reports/p0_fk_mapping_instance_equivalence_20261107_01/README.md)。恢复未重用 smoke_001 或 full_001。

## 触发原因

原 Smoke_001 在5个固定单元上全部完成。Full_001 的第一次启动因 conda run 使用 python3 时实际解析到 Python 3.9、导致 SQLGlot 版本不符，在输入读取前停止。第二次明确调用环境内 python3.12 后，runner 在进度 40/108、累计 36 个完整单元时以 SQL_USED_TARGET_NOT_SINGLETON 停止。

原协议已把多个或零个 SQL-used mapping 目标列为 unsupported case，应作为不可替换单元记录。原 runner 却在 run_unit 中将目标 ID 数量不等于1设为致命异常，因此中断整批 Full；此外，Full 覆盖门在聚合文件写出前硬停止，与“覆盖不足时报告并停止”的注册约定不符。失败目录仅有 failure.json，没有单元级或聚合指标。

## 允许的最小修正

1. sql_used_mapping_ids 不是长度恰为1的列表时，立即返回匿名状态 not_substitutable 和原因 SQL_USED_TARGET_NOT_SINGLETON；该单元不执行 Gold SQL 或候选 SQL，也不计入完整样本分母。
2. Full 仍按原门槛判断：至少80/108个完整单元并覆盖至少3个匿名数据库。低于门槛时写出匿名覆盖汇总并将状态设为 INCONCLUSIVE_FULL_COVERAGE 或 INCONCLUSIVE_DATABASE_COVERAGE，不得解释正负假设。
3. 不改变其他 run-level 校验。遇到本 amendment 未覆盖的错误即停止，不做第三次尝试。

## 冻结项

核心假设、固定 Smoke 5题/Full 108题、输入 manifest SHA-256 cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0、候选映射集合、SQL AST 变换、SQLite 只读 evaluator、每查询及总资源预算、10%正向门、5%弱信号门和解释限制全部不变。原 full_001 进度不与 Recovery 合并；Recovery 必须从108个固定 Full 单元重新开始。

Recovery 配置为 configs/text2sql/p0_fk_mapping_instance_equivalence_20261107_01_amendment_001.json。新 run IDs 为：

- Smoke：p0_fk_mapping_instance_equivalence_20261107_01_smoke_002，独立输出 smoke_002/。
- Full：p0_fk_mapping_instance_equivalence_20261107_01_full_002，仅在 Smoke_002 达到原定5/5门槛后运行，独立输出 full_002/。

运行固定使用 Conda 环境 think2sql_20260909 的 python3.12 可执行入口；已观察到该 shell 的 python3 可能被外层 Python 3.9 路径优先解析。Smoke 失败即停止。Recovery 再遇其他 run-level error 即停止，不再追加运行。
