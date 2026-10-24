# G2 非对称关系通道可辨识性实验

**实验 ID：** `g2_asymmetric_relation_20261024_01`
**当前状态：** 已预注册；最终运行门槛复核后 CPU Gate 0 通过；GPU 前向待启动。本文目前不包含模型结果。

**归档仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)
**执行分支：** `research/g2-asymmetric-relation-20261024`
**运行代码冻结 commit：** `0729aa5f3b29e5bf44f3d93d2b1d41cf4bab79ba`
**所依据的最新指导：** `main` commit `cb6fe5f4f32a011861d9cf91c0497fb3483450ff`，预注册方案位于 [`g2_asymmetric_relation_channel_identifiability_20261024.md`](../../plans/g2_asymmetric_relation_channel_identifiability_20261024.md)。

## 研究问题与假设

固定官方 G-reasoner-34M checkpoint、1024 维节点/关系特征、Query、起点和 G2 图拓扑。检验关系干预在 CPU 上确实改变某个起点可达目标节点的入边消息输入多重集合后，模型节点分数是否变化超过重复前向噪声；metadata-only 负控与关系 ID/向量一致重标应保持不变。

实验分层为**合成机制可辨识性 Gate**，属于探索性机制证据，不是主线 SQL 效果证据。即使通过，也不代表模型能辨识同端点多 FK 的业务角色；本实验不报告 Role F1、Join Path Accuracy 或 SQL EX。

## 设计与判定

G2 沿用固定 seed `20261023` 的 5 节点、8 条有向边、6 个关系 ID 和 1024 维特征。相较 G1，将两个 forward 角色改为 `0→1` 与 `0→4`，并保持各自逆边、3 个 FK instance identity、复合 FK 的两个有序 component 及其逆边成对关系。所有主比较均在 G2 新拓扑内部完成；不把 G1 旧图与新图的分数差解释为关系效果。

八种前向条件为：A0 固定基线、A0_repeat 噪声估计、A1 仅修改未被模型消费的 metadata、A2 成对交换关系类型、A3 对关系特征行 0 与 3 做等范数坐标置换、A4 同步双射重标 relation ID 与特征行、A5 起点辅助对照、A6 Query 辅助对照。最多加载 checkpoint 一次、运行 8 次前向、使用一张 GPU、总时限 15 分钟；不训练、不调用外部 API、不读取 BIRD 或执行 SQL、不下载模型、不安装依赖，同一 run ID 不重试。

判定阈值冻结为 `epsilon = max(1e-6, 10 × max_abs(A0 − A0_repeat))`。只有 Gate 0 全部通过、8 个输出均为 finite `[1,5]`、A1 与 A4 在 epsilon 内、并且 A2 或 A3 至少一个超过 epsilon，才判为 `G2_A_PASS`。正负控有效但 A2/A3 均未超过 epsilon 则为 `G2_A_NO_GO`；无效输入、负控失败、输出异常或资源超限均记 `STOP-INVALID`。

## CPU 预检

在加载 checkpoint 或调用 GPU 前，已执行独立 CPU Gate：

- G2 fixture 张量 SHA-256：`3a36bd4656bed2ddeaa803a2fac5ea0bae6fb2635cdb2fa3a72b3f63b99f02f8`。
- 新 G2 A2 使目标 `{0, 1, 4}` 的输入多重集合改变；A3 使 `{0, 1}` 改变；这些目标均从 anchor 0 可达。
- A4 的所有目标输入多重集合保持一致；A1 的模型消费字段保持一致。
- 对旧 G1 对称拓扑纯 CPU 重算，C2 与 C3 的输入多重集合均不变，与 G1 零差异的结构性问题一致。
- 复合 FK component 顺序、关系逆配对、有限值、张量形状、复制及设备往返契约通过。
- Gate 会强制匹配预注册 fixture SHA-256，并校验条件名称、每个干预允许改变的图字段、Query/起点隔离、one-hot 起点和 A3 指定行置换；任一条件混杂均停止。
- 新增的 22 项定向 CPU 合约测试通过；CPU Gate 将 PyTorch 线程数限制为 8；checkpoint 与 fixture SHA-256 均在模型加载前强校验；未加载模型、未执行模型前向。
- 运行 ID 在模型加载前以独占 reservation 固定；逐次记录 checkpoint 加载尝试、前向尝试及完成条件。worker 结果与监督进程回执分开保存且均不覆盖；监督回执只有在 worker 正常退出且结果为 PASS/NO-GO 时才标记 `COMPLETED`，超时或异常退出一律标记 `STOP-INVALID`。

当前有效的正式 Gate 0 回执及完整匿名签名见 [`cpu_preflight_bounded_011.json`](cpu_preflight_bounded_011.json)（SHA-256：`e685eb540a60cc616eeda5562c8d47d7287cac380bd730900db59f2e4c6427a3`）；冻结参数和完整启动命令见 [`experiment_config.json`](experiment_config.json)。`cpu_preflight_bounded_005.json` 至 `_010.json` 与 `cpu_preflight.json` 均保留为历史记录，不作为本次 GPU 启动依据；早期正式回执所对应的实现已在后续审阅中继续加固。CPU 多重集合 hash 是图输入层面的必要性审计，不代表模型内部 message activation。

## 运行前结果

| 项目 | 结果 |
|---|---|
| CPU Gate 0 | PASS |
| 定向测试 | 22/22 PASS |
| checkpoint 加载 | 0（待运行） |
| GPU 前向 | 0（待运行） |
| 训练 / API / 数据集 / SQL | 0 / 0 / 未使用 / 未执行 |
| 资源快照 | 2026-10-24 11:01:16 UTC：GPU 2 RTX 4090，0% 利用率，报告空进程表；memory.free 查询 21,146 MiB；RAM 可用 421 GiB；192 CPU；磁盘可用 114 TB |

此报告与可复现配置已先于任何 G2 模型前向提交。后续完成后将在此文件内补充 GPU 结果、差异、异常与结论；不会覆盖历史 G1 报告或结果。
