# P0 FK mapping 双本地模型审阅代理实验

**状态：预注册，尚未运行。** Run ID：`p0_fk_mapping_model_review_proxy_20261106_01`。

本报告登记用户选择“用模型来审阅”后的独立探索轨道。它不修改原双人盲审 CSV，不将模型判定称为人工标签或可信 Role 标签；原人类审阅门仍为 0。详细冻结方案见[实验计划](../../plans/p0_fk_mapping_model_review_proxy_20261106.md)。

## 运行前已冻结

- 输入：本地私有 pair-level A/B 审阅包；60 个问题×表对、135 个 FK mapping、4 个匿名数据库。
- 审阅器：Reviewer A 使用本地 Qwen2.5-Coder-7B-Instruct；Reviewer B 使用本地 Qwen3-4B-Think2SQL。两个模型独立运行，互不查看对方结果。
- 先 5 单元 Smoke；通过后独立重跑 60 单元 Full。仅 Full 进入模型间一致性汇总。
- 本轮只评估模型输出有效率和模型共识代理标签数量；任何 G-reasoner 排序需另建 run ID。
- 私有问题、候选映射、逐题模型标签/原始输出、CSV 与日志不进入 GitHub。

## 执行结果

待运行。
