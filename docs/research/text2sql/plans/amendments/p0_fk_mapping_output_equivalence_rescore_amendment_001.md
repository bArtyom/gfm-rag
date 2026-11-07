# Amendment 001：修正冻结排名与实例审计的 join key

**状态：首次 Smoke 已停止；Amendment 001 已登记，尚未重跑。** 对应主计划：[P0 输出等价重评分](../p0_fk_mapping_output_equivalence_rescore_20261107.md)。

## 触发原因与根因证据

初始 Smoke `p0_fk_mapping_output_equivalence_rescore_20261107_smoke_001` 在一对一配对门停止，错误为 `PREDICTION_PAIR_COVERAGE_MISMATCH`。运行器先校验配对，再计算指标；此次没有产生或保存任何命中统计，且没有创建 Smoke 输出目录。失败日志保存在本机：`/mnt/liansp3/logs/gfmrag_p0_fk_mapping_output_equivalence_rescore_20261107_01/smoke_001.log`。

代码追踪确认了唯一根因：`run_p0_fk_sql_used_mapping_rank_20261107_03.py` 将 `base.score_pair(unit_id, ...)` 的返回值直接写入 `private_predictions.jsonl`；`base.score_pair` 的 `pair_id` 字段就是传入的完整 `unit_id`。`review_pair_id` 只用于人类盲审包显示。初始 runner 错将二者视为相同键。

两个结果使用相同 SHA-256 为 `cc6dd6263f4b3a50c444c4f8ea82d9923f8b2dea5eac46d2ade5201a62550ad0` 的冻结清单，因此本 amendment 规定以排名输出的 `pair_id == prepared_manifest.units` 字典键 `unit_id` 连接。实例审计仍按其冻结函数计算 `unit_hash = SHA256(JSON(unit_id))[:20]`；mapping 候选仍按源审计函数计算 `candidate_hash = SHA256(JSON(mapping_id))[:20]`。三个键之间均做完整集合、唯一性与候选集合校验；不使用问题文本或模糊匹配。

## 变更范围

- 只将预测行与准备清单的连接键从错误假设的 `review_pair_id` 改为代码实际输出的 `unit_id`。
- 不改数据文件、输入哈希、候选 mapping、目标标签、比较器、Bag 口径、Smoke 选择、样本门、阈值、资源预算或停止规则。
- 首次失败 run ID 关闭并保留；新 Smoke 使用 `p0_fk_mapping_output_equivalence_rescore_20261107_amendment_001_smoke_001`，输出写至 `.../amendment_001/smoke_001/`。通过后 Full 另用 `p0_fk_mapping_output_equivalence_rescore_20261107_amendment_001_full_001`，并排除同一 5 个 Smoke 单元。
- 如果 Amendment 001 的 Smoke 再次失败，关闭本注册，不再修改 join-key、数据或标签。

## 运行前确认

提交后确认本文件、修订后的 runner 与配置已在 `bArtyom/gfm-rag` 目标分支可读，再运行新 Smoke。只运行 CPU 解析；无模型、API、GPU 或 SQL 执行。结果仍为同实例静态输出一致性诊断，不作语义等价、人工 Role 或 GFM 效果主张。
