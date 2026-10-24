# G2 非对称关系通道可辨识性实验

**实验 ID：** `g2_asymmetric_relation_20261024_01`
**当前状态：** 首次 GPU 启动因 CUDA 上下文未初始化而 `STOP-INVALID`（未加载模型、未执行前向）；修复已通过 CPU Gate 和 23 项合约测试。修订运行 `g2_asymmetric_relation_20261024_01_amended_01` 待启动，本报告不包含 G2 模型结果。

**归档仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)
**执行分支：** `research/g2-asymmetric-relation-20261024`
**原运行代码冻结 commit：** `0729aa5f3b29e5bf44f3d93d2b1d41cf4bab79ba`；**CUDA 初始化修订 commit：** `7a9cba0b4ebc473ebba753627e6bcfa9e65b52c9`
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
- Gate `_012` 的 14 项硬门全部通过：A2 的变化目标为 `{0, 1, 4}`，A3 为 `{0, 1}`，A4 不改变目标消息多重集合；旧 G1 C2/C3 对称性审计仍通过。固定 fixture SHA-256、复合 FK 顺序、逆边配对和条件隔离保持有效。
- 23 项定向 CPU 合约测试通过；CPU Gate 将 PyTorch 线程数限制为 8；checkpoint 与 fixture SHA-256 均在模型加载前强校验。Gate `_012` 未加载模型、未执行模型前向。
- 运行 ID 在模型加载前以独占 reservation 固定；逐次记录 checkpoint 加载尝试、前向尝试及完成条件。worker 结果与监督进程回执分开保存且均不覆盖；监督回执只有在 worker 正常退出且结果为 PASS/NO-GO 时才标记 `COMPLETED`，超时或异常退出一律标记 `STOP-INVALID`。

当前有效的正式 Gate 0 回执及完整匿名签名见 [`cpu_preflight_bounded_012.json`](cpu_preflight_bounded_012.json)（SHA-256：`5e4acd94c807b839261f2b53ae363e83c83dbe08cafb30f9d44600de014725d8`）；冻结参数和完整启动命令见 [`experiment_config.json`](experiment_config.json)。`_005` 至 `_011` 和早期初步回执均保留为历史记录；`_011` 早于 CUDA 上下文修复，不作为修订运行依据。CPU 多重集合 hash 是图输入层面的必要性审计，不代表模型内部 message activation。

## 首次启动故障与修订

首次运行使用 run ID `g2_asymmetric_relation_20261024_01`，状态为 `STOP-INVALID`，阶段 `MODEL_IMPORT`。调用 `torch.cuda.reset_peak_memory_stats(cuda:0)` 时，PyTorch 返回 `RuntimeError: Invalid device argument`。监督回执确认异常退出；worker 结果记录 `model_load_attempted=false`、`model_loaded=false`、`forward_attempted_count=0`、`successful_output_count=0`。因此首次启动没有消耗冻结的一次 checkpoint 加载或 8 次前向额度。

只读诊断确认进程可见 1 张 GPU；在显式建立 CUDA context 前重置峰值内存统计会失败，而 `torch.cuda.current_device()` 或 `torch.cuda.init()` 初始化 context 后，同一设备的重置通过。导入 GFM 工具模块不是触发条件。修订仅在统计重置前调用 `torch.cuda.init()` 与 `torch.cuda.set_device(device)`，并新增测试固定 `init → set_device → reset_peak_memory_stats` 顺序。没有修改模型、实验假设、fixture、依赖或检查点。

首次结果与监督回执的 SHA-256 分别为 `f3ba2921843e8f2dfc4499841f7d1427275cdf0332fdb72018ad427fecc4fc45` 和 `333fe4740ee4ba2800d79fdff6b85c5660c34b18b934dab2cd191013263bc5cc`；本地运行日志 SHA-256 为 `2b9ac62eb7883cc3ecf6f11887072d1b9322d09a337f8908f622c4dac74701c4`。原始运行日志与 CUDA 诊断日志按仓库安全约定留在本地，不上传 GitHub。此故障不会覆盖，修订运行使用全新 run ID 和独立产物路径。

## 运行前结果

| 项目 | 结果 |
|---|---|
| 最新 CPU Gate 0（`_012`） | PASS，14/14 硬门 |
| 定向合约测试 | 23/23 PASS |
| 首次启动 | `STOP-INVALID`；0 次 checkpoint 加载，0 次前向 |
| 修订运行 | 待启动；冻结额度最多 1 次加载、8 次前向、900 秒 |
| 训练 / API / 数据集 / SQL | 0 / 0 / 未使用 / 未执行 |
| 修订启动前资源复核 | 2026-10-24 11:13:17 UTC：GPU 2 RTX 4090，21,146 MiB free、0% 利用率且进程表为空；GPU 1 正在运行其他任务（88%），未选择/中断；RAM 可用 421 GiB，192 CPU，磁盘可用 114 TB；checkpoint 和 config hash 与冻结值一致 |

修订运行命令、模型/数据版本、环境、资源限制、结果路径和当前 CPU Gate 均记录在 [`experiment_config.json`](experiment_config.json)。GPU 运行结束后追加实际指标、异常、结果哈希、结论和边界；不会覆盖首次停止现场或历史 G1 报告/结果。
