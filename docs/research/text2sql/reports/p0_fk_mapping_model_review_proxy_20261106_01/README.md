# P0 FK mapping 双本地模型审阅代理实验

**状态：Smoke_001 未通过；已公开登记一次提示澄清，等待 Smoke_002。** 实验 ID：`p0_fk_mapping_model_review_proxy_20261106_01`。

本报告登记用户选择“用模型来审阅”后的独立探索轨道。它不修改原双人盲审 CSV，不将模型判定称为人工标签或可信 Role 标签；原人类审阅门仍为 0。详细冻结方案见[实验计划](../../plans/p0_fk_mapping_model_review_proxy_20261106.md)。

## 运行前已冻结

- 输入：本地私有 pair-level A/B 审阅包；60 个问题×表对、135 个 FK mapping、4 个匿名数据库。
- 审阅器：Reviewer A 使用本地 Qwen2.5-Coder-7B-Instruct；Reviewer B 使用本地 Qwen3-4B-Think2SQL。两个模型独立运行，互不查看对方结果。
- 先 5 单元 Smoke；通过后独立重跑 60 单元 Full。仅 Full 进入模型间一致性汇总。
- 本轮只评估模型输出有效率和模型共识代理标签数量；任何 G-reasoner 排序需另建 run ID。
- 私有问题、候选映射、逐题模型标签/原始输出、CSV 与日志不进入 GitHub。

## Smoke_001：未通过，不运行 Full

- Run ID：`p0_fk_mapping_model_review_proxy_20261106_smoke_001`；输入 A/B 包 SHA-256 分别为 `0b6102f3…d826cfa2` / `a30230c9…944dfdb`；每个模型独立处理同一组 5 个冻结单元，分别按 A/B 的不同显示顺序。
- Qwen2.5-Coder-7B-Instruct（GPU 1）：5/5 通过输出和候选语义校验；输入 1,524、输出 225、总计 1,749 tokens；峰值已分配显存 15.31 GB；模型加载 8.01 秒，生成 5.64 秒。
- Qwen3-4B-Think2SQL（GPU 2）：3/5 通过；2 个 JSON 输出选择 `no_declared_fk`，但每个单元均有已展示候选，因此按预注册响应契约判为无效；输入 1,544、输出 228、总计 1,772 tokens；峰值已分配显存 8.13 GB；模型加载 4.61 秒，生成 7.40 秒。
- 两者合计本地输入 3,068、输出 453、总计 3,521 tokens。此为本地推理，不发生外部 API 费用；本地 GPU 时间单独计量，不估算电费。
- **结论：** Smoke_001 失败门触发，未运行 60 单元 Full，未计算或使用任何共识标签，也未运行 G-reasoner、SQL 或外部 API。

## 修订与下一步

修订 A1 只在提示中明确：该审阅包的每个单元都列有至少两个声明 mapping，因此 `no_declared_fk` 不适用。该修订已在 Full 启动前单独登记，Run ID 为 `p0_fk_mapping_model_review_proxy_20261106_smoke_002`；模型、样本、候选顺序和校验规则均不变。若任一模型仍少于 4/5 通过，就停止此模型审阅路线，不再改提示或换模型。详见[修订记录](../../plans/p0_fk_mapping_model_review_proxy_20261106.md#执行时修订-a1-2026-11-06发生在任何-full-运行之前)。
