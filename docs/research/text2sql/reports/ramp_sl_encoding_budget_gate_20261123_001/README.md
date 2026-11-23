# RAMP-SL 编码预算上限试验

**状态：预注册；尚未运行。**

**Run ID：** `ramp_sl_encoding_budget_gate_20261123_001`

**层级：** 最小可行性 gate；BIRD-dev exploratory。

本轮只检验：固定昂贵编码输入预算 `M=4,096` 与字段输出预算 `B=2,048` 时，昂贵编码离线上限相对静态低成本候选排序，是否至少提高 `3.0 pp` 的完整 Gold-column coverage@B。该 gate 的完整协议、模型/数据版本、样本、预算和停止规则见[预注册方案](../../plans/ramp_sl_encoding_budget_gate_20261123.md)。

比较 Static-TopM 与 Offline-Oracle 两组。Smoke 最多 5 题，仅做工程核验；若通过，先运行每库最多 10 题的 pilot。只有预设上限差达到 3.0 pp 且达到分母/数据库数门槛，才按同一协议扩展全部 1,460 个列标签可评题。

结果、代码提交、硬件状态、精确 token 计数和异常：运行后填写。此处不代表已经运行或已有实验成绩。
