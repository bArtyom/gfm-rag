# P2b R0/R1 Values 文本消融

> **状态：首个 smoke 遇到结果汇总代码错误；唯一一次修复 smoke 已在远端预注册，尚未重跑。** 本文是本次实验的唯一正式记录；recovery smoke 通过前不启动 Full。BIRD dev 为探索集。

## 预注册摘要

- **研究问题：** 在固定 Qwen3 1024-D、Cosine、候选池和查询后，移除列文本中的 Values 是否提高列召回，且不损害预算内完整 Schema 选择？
- **核心假设：** R1−R0 的全体 Column R@10 至少 +1.0 pp，数据库聚类 bootstrap 95% CI 下界 >0；固定非饱和子集 Column R@10 与 Complete@1024 均不劣于 −1.0 pp。
- **层级/预算：** 最小消融；最多一次初始 5 题 CPU smoke、一次实现错误恢复 smoke、一次 Full、R0 同文本重编码控制；实验累计 CPU 7200 s / wall 3600 s / RSS 16 GiB / 8 线程。初次失败资源计入总预算，超限停止。
- **运行策略：** 优先本地 CPU；四张 4090 预检时忙碌。无外部 API、GPU、SQL、训练、下载或依赖安装。
- **详细协议：** [P2b 预注册计划](../../plans/p2b_values_ablation_20261018.md)。

## 首次 Smoke 与恢复登记

首次 Smoke `p2b_values_smoke5_20261018_01` 于 2026-10-18 执行 5 题 / 1 DB。冻结输入、R0/R1 序列化审计、CPU 编码、向量检查和 Cosine 打分均完成；在写聚合结果时因代码从 prepared question 读取不存在的 `column_eligible` 字段而中止，该标记实际位于 scorer rows。此错误使 smoke 未通过，且没有 aggregate 或逐题结果文件写出。失败现场留在本机结果目录 `/mnt/liansp3/sources/results/gfmrag_p2b_values_ablation_20261018/smoke_5q_20261018_01`，日志为 `/mnt/liansp3/logs/gfmrag_p2b_values_smoke5_20261018_01.log`。本次消耗 49.808 秒 wall、313.046 秒 CPU、峰值 RSS 2.703 GiB；实际本地模型输入 12,238 tokens，生成 0。未调用 API、GPU 或 SQL。

已登记唯一一次恢复 Smoke `p2b_values_smoke5_20261018_02`，使用全新的结果目录和日志；修复只改 eligible-question 分母读取来源，不改假设、数据、样本、编码器、条件、指标、门槛或资源预算。首次失败的 CPU/wall 用量与本轮恢复和 Full 共用累计 7,200 CPU 秒 / 3,600 wall 秒预算。若恢复 Smoke 再失败则停止，不启动 Full。

恢复 Smoke 与 Full 目前都未启动。只有恢复 smoke 通过冻结输入、R0 text parity、R1 唯一 Values 差异、输出格式和本地资源门后，才会运行一次 Full。Smoke 数字不会混作正式 Full 结果。

## API 与费用

- 本实验预期无模型 API 请求；本地 Qwen3 CPU 输入 token 数在运行报告中记录，生成 token 为 0。
- API 账本请求、确认 token 与按公开价估算费用在实验完成后按账本核对；本地 CPU 资源时间单独报告，不冒称为 API 费用。
