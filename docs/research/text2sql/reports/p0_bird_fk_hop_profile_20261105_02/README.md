# P0 BIRD FK Hop Profile v2：作用域感知解析复核（2026-11-05）

> **状态：Smoke 与 Full 完成；解析完整性门通过。** 本轮只审计数据结构，不比较检索/图方法，不计算 Role Accuracy，也不评估 SQL EX。v2 的匿名全局汇总与 v1 相同；但 BIRD `h≥3` 比例与 SchemaScope 报告仍相差约一个数量级。按预注册停止规则，不再追加解析器或 hop 阈值扫描；定义差异保持未解决。

## 研究问题、假设与停止条件

- **问题：** SQL 中涉及的基础表，在 BIRD dev 声明 FK 无向表图上的精确最小 Steiner 边数分布是什么？是否至少有 30 道连通且 `h≥3` 的题，且分布在至少 3 个数据库？
- **核心假设：** 作用域感知 SQL 解析能在不改变既定数据、FK 图或 hop 定义的条件下，排除 v1 全局 CTE 别名过滤的跨作用域误删风险，并给出完整匿名结构画像。
- **实验层级：** exploratory 数据资源审计，不是主方法实验或消融。
- **预设门槛：** Smoke 5/5 题通过；Full 解析率至少 95%；资源筛选线为连通 `h≥3` 至少 30 题且覆盖至少 3 个库。高跳数门槛只用于判断是否值得进一步评估数据，不是统计功效或方法有效性门槛。
- **预算与停止：** 每轮 CPU-only、最多 4 线程、600 秒；不调用模型/API、不用 GPU、不执行 SQL、不训练。若 Smoke 失败，不启动 Full；若 Full 与文献定义仍有明显差异，不继续做更多切片或阈值扫描，停止 BIRD 高跳数方法扩展。

## 与 v1 的方法差异

v1 对整条 SQL AST 收集表名，再从全局 CTE 别名集合中排除同名项。由于 CTE 名称只在自己的查询作用域内有效，v1 有可能把其他作用域中的真实同名基础表也排除。v2 将表引用抽取改为 SQLGlot `traverse_scope(parsed)` 的 `scope.selected_sources`：只计入当前作用域被解析为 `exp.Table` 的基础表，CTE 和派生表由其作用域来源处理。

除此之外，v2 不改变 SQL 方言、输入数据、FK 图、图边合并、Steiner 算法、最多 12 个终端表限制、完整性门、资源筛选线或资源预算。v1 的报告和结果原样保留，状态为 `SUPERSEDED_PENDING_SCOPE_CORRECTION`；v2 与 v1 的聚合相同并不证明逐题分布完全一致，因为本轮没有生成逐题公开 crosswalk。

## 指导、来源与版本

- **项目仓库：** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/p0-fk-disagreement-review-20261105`。
- **预注册/代码归档：** [2026-11-05 作用域修正提交 `2ba870c`](https://github.com/bArtyom/gfm-rag/commit/2ba870c95b82b124e1d20cf919d81c0e87d46586)。该提交包括 v1 报告、v2 配置、v2 方案和修正后的 runner；远端文件逐个回读 SHA 均匹配。实际运行工作树提交为 `e13c30241fcadcb53e1cace493f586fdc64f0b1b`，其 tree `b689ef5b22db5a17d84fbd361c569e0043c64f31` 与该远端提交完全一致。
- **执行文件：** [`audit_bird_fk_hop_profile.py`](../../../../../scripts/text2sql/audit_bird_fk_hop_profile.py)，SHA-256 `6fc32cb3dcfb6f8f2815c84f4667d8c3c2f0988d5094e361d1464867ba69e6f7`。
- **冻结配置：** [`p0_bird_fk_hop_profile_v2_20261105.yaml`](../../../../../configs/p0_bird_fk_hop_profile_v2_20261105.yaml)，SHA-256 `9be6139b3c3fd16ad74aaa7f86a01d83ea939b7780266dd2880f5b0f3e022465`。
- **方案：** [v2 CTE 作用域更正计划](../../plans/p0_bird_fk_hop_profile_v2_correction_20261105.md)。
- **仓库指导：** 执行前阅读仓库根 README、Text2SQL README、实验路线图与复现规范。计划中登记的 BIRD 输入 SHA 与运行时完全匹配。

## 数据、图定义与环境

| 项目 | 冻结/实测信息 |
|---|---|
| 数据 | BIRD dev，1,534 个问题、11 个 schema；本地多轮开发集，仅作诊断 |
| 输入 SHA-256 | `dev.json`: `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06`；`dev_tables.json`: `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |
| FK 图 | 102 个声明 FK 列对，投影并折叠后 72 条无向表边；无效端点 0 |
| hop 定义 | 对 SQL 涉及的不同基础表，在无权、无向声明 FK 表图中求精确最小 Steiner 树边数；使用 Dreyfus–Wagner 子集 DP，最多 12 个终端表 |
| 软件 | `think2sql_20260909`；Python 3.12.14、SQLGlot 28.0.0、PyYAML 6.0.3；未安装或升级依赖 |
| 随机性 | 确定性算法；无随机抽样、无随机种子 |
| 计算资源 | 4×RTX 4090 主机，但本轮 GPU 秒为 0；运行前 GPU 0/3 有显存占用，未干扰或使用；内存可用 438 GiB、CPU 192 线程、磁盘可用 112 TB；程序线程上限 4 |

## 启动命令与运行记录

先运行 5 题 Smoke，通过后才运行一次 1,534 题 Full。两次使用独立输出目录；命令均从项目根目录执行：

```bash
timeout 600s conda run --no-capture-output \
  -p /root/miniconda3/envs/think2sql_20260909 python3.12 \
  scripts/text2sql/audit_bird_fk_hop_profile.py \
  --mode smoke \
  --run-id p0_bird_fk_hop_profile_v2_smoke_20261105_01 \
  --config configs/p0_bird_fk_hop_profile_v2_20261105.yaml \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_02/smoke

timeout 600s conda run --no-capture-output \
  -p /root/miniconda3/envs/think2sql_20260909 python3.12 \
  scripts/text2sql/audit_bird_fk_hop_profile.py \
  --mode full \
  --run-id p0_bird_fk_hop_profile_v2_full_20261105_01 \
  --config configs/p0_bird_fk_hop_profile_v2_20261105.yaml \
  --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
  --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_02/full
```

| Stage | Questions | Status | Runner elapsed |
|---|---:|---|---:|
| Smoke | 5 | `SMOKE_PASS`; 5/5 references parsed and mapped | 0.133 s |
| Full | 1,534 | `FULL_COMPLETED`; 1,534/1,534 references mapped, status counts exhaustive | 1.134 s |

Runner elapsed time is not a full host resource accounting; process CPU time and peak RSS were not measured. No model/API request, SQL execution, training, download or dependency installation occurred. External model API usage and cost for this run: 0 tokens and CNY 0.00; local CPU time is a separate, unpriced resource.

## 结果

| 指标 | Full |
|---|---:|
| 已处理问题 / schema | 1,534 / 11 |
| 已解析基础表引用 | 2,978 |
| 所有基础表引用均映射到 schema | 1,534 / 1,534（100%） |
| FK 图连通 / 不连通 | 1,457 / 77 |
| 连通题 hop 直方图 `h=0/1/2/3/4` | 363 / 849 / 209 / 35 / 1 |
| 连通 `h≥3` | 36 / 1,534（2.35%），覆盖 5 个数据库 |
| 单个数据库最多 `h≥3` | 18 / 36 |
| 连通 `h≥4` | 1 / 1,534（0.07%） |
| 预注册结构筛选门 | 通过：36≥30，且 5≥3 |

v1 与 v2 的上述匿名聚合计数相同：102 个 FK 列对、72 条表边、1,457 连通、77 不连通、hop 直方图相同，`h≥3` 为 36 题。由于没有跨版本逐题 ID 文件，这只能称为**聚合相同**，不能声称每道题的解析结果相同。

## 文献差异、失败与结论

SchemaScope 报告 BIRD dev 约 22% 的问题达到 `h≥3`；本轮在声明 FK 表图上的定义得到 2.35%。来源定义可能在 schema 图构造、基础表终端抽取、连接路径与 hop 计算上不同，目前没有足够证据归因。v2 修正了解析器的作用域风险，但差异仍在；因此按预注册规则停止后续 BIRD hop-depth 切片或重复解析器扫描。此比例不推翻 SchemaScope，也不能外推到真实 JOIN 正确性。

本轮没有运行时错误或输入哈希偏差。77 道题在声明 FK 图上不连通，不代表 SQL 错误；可能涉及未声明/不一致连接，也可能是当前结构定义无法覆盖。Hop 只描述声明 FK 图结构，不表示业务角色正确。

**决策：** 本地 BIRD dev 在本定义下刚好通过内部高跳数资源筛选线，但 `h≥3` 样本偏少、半数集中于一个数据库，`h≥4` 仅 1 题，且与论文比例差异尚未解释。停止在本数据集上继续开展高跳数方法拓展。当前双人可信 Role 标签仍为 0；不能运行/报告 Role Accuracy、真实 FK mapping 排序或监督式 GFM 方法。

## 结果与日志位置

- Smoke 私有摘要：`/mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_02/smoke/aggregate_summary.json`，SHA-256 `0cfc25af2379a051fbffbdf0d7fd593752c118a6acba21576d9c7453ed94d36a`。
- Full 私有摘要：`/mnt/liansp3/sources/results/gfmrag_p0_bird_fk_hop_profile_20261105_02/full/aggregate_summary.json`，SHA-256 `d98e9681b4ed32a77850ce7c30980528af5a5beba111463fcdfa71f59fead442`。
- 公共匿名 Full 汇总：[`aggregate_summary.json`](aggregate_summary.json)，只含全局匿名统计。
- 本地日志与资源快照：`/mnt/liansp3/logs/p0_bird_fk_hop_profile_20261105_02/`。
- 未上传 BIRD SQL、问题、题目/数据库 ID、逐题 hop、原始 schema 或私有日志。
