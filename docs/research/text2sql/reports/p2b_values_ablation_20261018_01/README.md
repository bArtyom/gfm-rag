/root/.profile: line 9: true_PROXY: command not found
# P2b R0/R1 Values 文本消融

> **状态：已预注册，尚未运行。** 本文是本次运行的唯一正式记录；按 smoke → Full 顺序更新结果。BIRD dev 为探索集。

## 预注册摘要

- **研究问题：** 在固定 Qwen3 1024-D、Cosine、候选池和查询后，移除列文本中的 Values 是否提高列召回，且不损害预算内完整 Schema 选择？
- **核心假设：** R1−R0 的全体 Column R@10 至少 +1.0 pp，数据库聚类 bootstrap 95% CI 下界 >0；固定非饱和子集 Column R@10 与 Complete@1024 均不劣于 −1.0 pp。
- **层级/预算：** 最小消融；一次 5 题 CPU smoke、一次 Full、R0 同文本重编码控制；CPU 7200 s / wall 3600 s / RSS 16 GiB / 8 线程。超限停止。
- **运行策略：** 优先本地 CPU；四张 4090 预检时忙碌。无外部 API、GPU、SQL、训练、下载或依赖安装。
- **详细协议：** [P2b 预注册计划](../../plans/p2b_values_ablation_20261018.md)。

## 执行状态

Smoke 与 Full 尚未启动。正式结果、失败/异常、实际环境、指标、结论和匿名 aggregate 链接将在运行后写入此报告；不得把 smoke 数字作为 Full 结果。

## API 与费用

- 本实验预期无模型 API 请求；本地 Qwen3 CPU 输入 token 数在运行报告中记录，生成 token 为 0。
- API 账本请求、确认 token 与按公开价估算费用在实验完成后按账本核对；本地 CPU 资源时间单独报告，不冒称为 API 费用。
