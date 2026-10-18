# P2a.5 错误归因与 FK / Join-Instance Gate 审计（2026-10-18）

> **状态：完成。** 本报告记录冻结 P2a 的 CPU-only 回放与匿名误差分析，以及独立 FK / Join-Instance 数据质量审计。P2a 的相似度方法结论继续为 **NO-GO**；本轮没有新模型分数、SQL 执行、JOIN 角色准确率或 GNN 结果。BIRD dev 是反复使用过的开发诊断集，不代表独立泛化验证。

## 1. 研究问题与预注册边界

- **研究问题：** 冻结 P2a 中 BM25 / RRF 的列检索与完整 Schema 变化，能否由词面覆盖、BM25 同分、可见字段文本或预算选择解释？冻结的 JoinInstance 标识与 Gold JOIN 覆盖是否可按原始 P1.5 证据重建？
- **核心假设：** BM25 / RRF 的损失可能与词面零重叠、稳定 ID 同分、文本特征或上下文预算选择有关；FK 标签不确定性是另一条独立 Gate。该审计不预测任何新评分方法会提升结果。
- **实验层级：** P2a.5 只读诊断与 FK 数据质量 Gate；不重新训练、不改变 S0/S1/S2 排名，也不启动 P2b。
- **预算：** GPU 0 秒；CPU ≤1,800 秒；峰值 RSS ≤16 GiB；最多 8 线程；外部 API、模型前向、SQL 执行、依赖安装、模型下载均为 0。
- **成功判据：** 验证冻结 P2a / P1.6 输入与缓存；逐题行、聚合及 S0 parity 与归档完全一致；按稳定 node ID 输出 rank 转移；报告 1460 / 706 两个列可评分母的救回 / 损坏、BM25 overlap / tie、上下文选择和字段特征；重建 FK 与 JOIN 分母并为每条 unmatched ON 指定一个结构性原因；保持历史 P2a 与 Role Gate 决定不变。
- **停止条件：** 任一输入、缓存、digest、分母或归档 FK/JOIN 数不匹配；缺私有逐题排名或 FK artifact；CPU、RSS 或线程数超预算。最终运行没有触发数据完整性或资源停止条件。

## 2. 指导、代码和输入版本

- **唯一项目仓库：** [bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，分支 `main`。本轮最终运行代码版本为 commit `210c2d2ba635a47881c6694f2754b3a407990f6d`，runner SHA-256 `e046595df72d3b684062a54d2fffc2c8df13cae419b056625b8981c20b805085`。
- **实验前阅读：** 仓库根 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、P2a.5 计划、P2a 结果与复核、P1.6 报告 / 配置、P1.5 诊断报告和 runner。
- **指导范围：** 执行 `p2a_5_diagnostic_and_schema_representation_20261018.md` 的 A（冻结排名错误归因）和 C（FK / Join-Instance 数据质量审计）。按计划只公开匿名聚合、代码、配置和 hash；逐题记录、Gold SQL、数据库、embedding cache 与日志均留在本地。
- **P2a 源运行：** `p2a_similarity_full1534_20261018_02`，源码 commit `689b7f681651f312a1db8850d86b8b7dc4f69fd2`；逐题文件 SHA-256 `1016892314903ab98f1be0864c044217d2656ab8e4f44646bef5525a65443f28`；归档聚合 SHA-256 `0b5b3ddff8abfd4f330e5a0417b92403de1a01d0b01d8702b96cc87c4e2f0eec`。
- **P1.6 缓存：** `p1_6_full1534_20261018_01`，源码 commit `d948d462f9407a18f4a48c85a76380d54f865cb2`；Qwen3-Embedding-0.6B，1024 维 float32、L2 归一化；模型清单 SHA-256 `b89ec1366231e37e92c64eaff3f98edce0f0c6af15cc8c7991ed900520143c68`；缓存 SHA-256 `c7bb9ed942aa793e34e1253a5d1d8f8d8d871c95bdfdc33718dde7396d345250`；S0 digest `08b33648f25a5da09e2e5651207b83732bbc4b06eea2a2529ea1c1e290c53625`。
- **输入：** BIRD dev，本地统一入口 `/mnt/liansp3/sources/datasets/bird/dev`；manifest SHA-256 `693d6e1d8a1c4dcddadc7becd130c8d379e5d7378b96af99897acbae3f792c1a`；有序节点文本 SHA-256 `4e930d3b906d46d77381edbfee8bfb57ab04fc09d47b9e90fc6272986cceaa5a`。P1.5 FK artifact 为本地 `full_03/fk_gate_private.json`，不公开原始内容。
- **最终聚合：** `aggregate_summary.json` SHA-256 `813f43c3952a97dbabe011de5869ce50c419f7432b0dc6bb586f56051ee1d58a`。最终 run metadata SHA-256 `eb1e2bc7a41aa397da2043620495c54213431be82e67f0c15c77bebcaa51de9f`，只在本地保存。

## 3. 数据、环境与运行

| 项目 | 设置 / 结果 |
|---|---|
| 数据范围 | 1534 题、11 DB、873 个节点（75 tables、798 columns）；1460 题 / 6523 个 Gold column elements 可评，74 题列标签不完整而排除 |
| 非饱和子集 | Schema 文本 >2048 tokens 的 5 DB、746 题；其中 706 题可评、3156 个 Gold columns。另有 6 个 DB 的完整 Schema 不超过 2048 tokens |
| 环境 | Conda `think2sql_20260909`；Python 3.12.14、NumPy 2.2.6、sqlglot 28.0.0；`rank-bm25` 未安装，沿用仓库冻结的内部实现 |
| 硬件 | 4×RTX 4090；开跑前 GPU 利用率约 72–97%，本轮 GPU 使用为 0。内存约 441 GiB 可用、192 CPU 线程、磁盘约 116 TiB 可用 |
| Full 资源 | wall 22.737 秒、进程 CPU 22.777 秒、峰值 RSS 0.837 GiB；脚本线程上限 8 |
| 随机性 | 固定输入顺序，无随机采样、随机种子或 bootstrap；Smoke 固定 5 题 / 1 DB，Full 为全部 1534 题 |
| 其他资源 | 无 API 请求、模型前向、模型下载、训练、SQL 执行或依赖安装；因此本轮模型 API token 与 API 成本均为 0 |

本轮不重新编码。Qwen3-Embedding-0.6B 模型路径只用于复用原实验输入验证，不产生新向量或推理结果。

**Smoke** `p2a5_smoke5_20261018_02`：5/5 逐题输出匹配、输入和 cache hash 匹配、S0 parity PASS，FK artifact 核对为 103 instances / 11 DB；wall 11.515 秒、RSS 0.816 GiB。

**最终 Full** `p2a5_full1534_20261018_04`：1534 行重放与归档逐行相同；聚合指标完全相同；S0 parity PASS；所有 FK ID / JOIN 分母校验通过。命令：

```bash
set -o pipefail
conda run -n think2sql_20260909 \
  /root/miniconda3/envs/think2sql_20260909/bin/python3 \
  scripts/text2sql/run_p2a_5_error_audit.py \
  --mode full \
  --run-id p2a5_full1534_20261018_04 \
  --output-dir /mnt/liansp3/sources/results/gfmrag_p2a_5_error_audit_20261018/full_004 \
  --p2a-run-dir /mnt/liansp3/sources/results/gfmrag_p2a_similarity_20261018/full_1534_02 \
  --p1-6-run-dir /mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01 \
  --p1-5-run-dir /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03 \
  --legacy-root /mnt/liansp3/sources/projects/quadrag \
  --dataset-root /mnt/liansp3/sources/datasets/bird/dev \
  --model-path /mnt/liansp3/sources/models/qwen3-embedding-0.6b \
  --previous-run-dir /mnt/liansp3/sources/results/quadrag_p1_dimension_20261014/gfmrag_official_full1534_20261014_01 \
  --smoke-dir /mnt/liansp3/logs/gfmrag_p2a5_smoke5_20261018_02 \
  2>&1 | tee /mnt/liansp3/logs/gfmrag_p2a5_full_20261018_04.log
```

本地正式产物位于 `/mnt/liansp3/sources/results/gfmrag_p2a_5_error_audit_20261018/full_004/`；本地日志为 `/mnt/liansp3/logs/gfmrag_p2a5_full_20261018_04.log`。公开仓库没有上传逐题数据、run metadata 或日志。

## 4. 冻结 P2a：排名变化与救回 / 损坏

以下为之前 P2a Full 的已归档指标，本轮逐行重放和 aggregate replay 均与其完全一致；这些不是本轮新评分结果。Recall / Complete 均为 query macro。

| 分母 | 方法 | Column R@10 | Column R@20 | Complete@2048 |
|---|---|---:|---:|---:|
| 全体 1460 | S0 Cosine | 68.00% | 79.08% | 79.66% |
| 全体 1460 | S1 BM25 | 55.91% | 72.02% | 62.67% |
| 全体 1460 | S2 RRF | 66.90% | 80.32% | 77.05% |
| 非饱和 706 | S0 Cosine | 58.20% | 69.12% | 57.93% |
| 非饱和 706 | S1 BM25 | 47.70% | 61.79% | 22.80% |
| 非饱和 706 | S2 RRF | 58.29% | 71.06% | 52.55% |

| 方法 / 分母 | Column R@10 救回 / 损坏题 | Gold column 命中数净变化 | Complete@2048 救回 / 损坏题 |
|---|---:|---:|---:|
| BM25 / 全体 | 215 / 660 | −734 | 17 / 265 |
| RRF / 全体 | 273 / 319 | −48 | 27 / 65 |
| BM25 / 非饱和 | 142 / 310 | −282 | 17 / 265 |
| RRF / 非饱和 | 170 / 159 | +25 | 27 / 65 |

Complete 变化在其他预算下同样没有稳定方向：

| 方法 / 分母 | @512 救回 / 损坏 | @1024 救回 / 损坏 | @2048 救回 / 损坏 |
|---|---:|---:|---:|
| BM25 / 全体 | 30 / 235 | 29 / 369 | 17 / 265 |
| RRF / 全体 | 43 / 134 | 43 / 188 | 27 / 65 |
| BM25 / 非饱和 | 11 / 112 | 11 / 183 | 17 / 265 |
| RRF / 非饱和 | 18 / 65 | 21 / 97 | 27 / 65 |

完整的 5×5 rank-transition 矩阵（1–5、6–10、11–20、21–50、>50）在聚合 JSON 中提供，分别按 1460 全体、706 非饱和及数据库分层；节点以稳定 ID 对齐。P2a 原先登记的两方法增益门不通过，保持 `no_go_stop_method_expansion`，不能以 RRF 的 R@20 单项增加改写结论。

## 5. 词面、并列与字段文本诊断

### BM25 overlap 与 ties

- 6523 个 Gold column elements 中，5624 个（86.2%）与 Query 至少有一个 BM25 token overlap。
- Gold column 在 BM25 排名 >10 的元素中，830 个没有词面 overlap，2322 个有 overlap；有 overlap 但仍低于 cutoff 的原因在本审计中不作语义归因。
- 相对 S0 的 1313 个 Gold top-10 损坏元素中，分类为 200 个无词面 overlap、984 个有 overlap 但排名低于 10 且原因未识别、129 个落在 BM25 tie 类别。三类之和为 1313；不能据此将其余损失归因为特定语义错误。
- BM25 列候选平均每题有 23.7 个零分候选（中位数 13，P90 53）。1534 题中有 1530 题出现列候选同分；在 Column@10 边界有同分的题为 400，涉及 tie group 内 4992 个候选，stable-ID 规则分配了 1146 个 cutoff slots。全局有 tie 不等于每题的 Top-K 一定受影响。
- 同一 P2a 候选池是每个 DB 内 table + column 混合池；Top-K 列指标再按 column 类型切分。平均每题全池 82.6 个节点、列候选 75.6 个。

### Gold / 非 Gold Top-10 字段特征

特征均来自运行时可见的 schema text 和 Query 表面形式。Gold 只用于离线分层；Top-10 中“不在 Gold 列集合”按参考标签定义，**不等于人工确认无关**。字段 token 长度使用冻结 P2a BM25 tokenizer；`node.token_count` 长度是既有上下文预算记账值。Uppercase abbreviation 是 2–4 字母全大写 token 的表面代理；ID-like 是精确命中 `id / uid / uuid / key / no / num`。

| 统计 | S0 Cosine | S1 BM25 | S2 RRF |
|---|---:|---:|---:|
| 全体 Column@10 参考标签非匹配节点 / 14600 slots | 10495 / 71.9% | 11229 / 76.9% | 10543 / 72.2% |
| 这些节点 `node.token_count` 中位数 / P90 | 24 / 54 | 32 / 84 | 28 / 63 |
| 非 Gold top-10 中有 Values 字段 | 36.5% | 49.2% | 44.3% |
| 非 Gold Values 字段 BM25 token 数 P90 | 15 | 40 | 24 |
| 非 Gold 完整文本 BM25 token 数 P90 | 33 | 59 | 42.6 |
| 非 Gold top-10 中有 Description / Format | 95.2% / 97.0% | 98.4% / 98.6% | 98.0% / 98.4% |

在 Gold elements 中，Description 出现于 6316/6523（96.8%），Format 出现于 6461/6523（99.0%），Values 出现于 1677/6523（25.7%）。Gold 完整文本 BM25 token 长度中位数 / P90 为 14 / 27；Values 长度中位数为 0、P90 为 12。Description / Format 几乎没有缺失对照；Values 的变化更充分。

Gold 有 Values vs 无 Values 的 Column R@10 hit rate 分别为：S0 78.8% vs 57.4%，S1 75.3% vs 43.5%，S2 81.2% vs 55.6%。这与非 Gold top-10 中较长 Values 字段同时出现的事实并存。两者是分层关联，可能受到字段和标签选择影响；它既不能证明 Values 是噪声，也不能证明它因果改善检索。

### 预算与上下文选择

`Gold-only fit` 表示按冻结 token 计数把该题所有 Gold table/column 文本相加后，理论总长不超过预算；它**不是一个替代 packer 的实际结果**。Gold-only 可行但现有贪心选择仍不完整，可能同时包含排序召回不足与预算选择损失，不能把全部差额称为纯 packing 因果损失。

| 分母 | 预算 | Gold-only fit | S0 Complete | S1 Complete | S2 Complete |
|---|---:|---:|---:|---:|---:|
| 全体 1460 | 512 | 1399/1460 (95.8%) | 519 (35.5%) | 314 (21.5%) | 428 (29.3%) |
| 全体 1460 | 1024 | 1460/1460 (100%) | 820 (56.2%) | 480 (32.9%) | 675 (46.2%) |
| 全体 1460 | 2048 | 1460/1460 (100%) | 1163 (79.7%) | 915 (62.7%) | 1125 (77.1%) |
| 非饱和 706 | 512 | 645/706 (91.4%) | 141 (20.0%) | 40 (5.7%) | 94 (13.3%) |
| 非饱和 706 | 1024 | 706/706 (100%) | 265 (37.5%) | 93 (13.2%) | 189 (26.8%) |
| 非饱和 706 | 2048 | 706/706 (100%) | 409 (57.9%) | 161 (22.8%) | 371 (52.5%) |

对 2048 预算，Gold-only fit 覆盖 1460/1460 题，但 S0 仍有 297 题、S1 545 题、S2 335 题未完整选中 Gold；非饱和子集对应相同数量。这说明只提升预算上限并不能保证完整覆盖，也说明 BM25 / RRF 排名与贪心选择的组合值得单独验证。本轮没有替换 packer 或比较新策略。

## 6. FK / Join-Instance Gate

| 检查 | 结果 |
|---|---:|
| SQLite FK JoinInstance 原始实例 / 唯一稳定 ID | 103 / 103 |
| 端点有效 / 无效 | 100 / 3 |
| JSON FK pairs 仅 JSON 有 / SQLite 有效但 JSON 缺失 | 5 / 2 |
| Gold 显式 JOIN ON 总数 / SQL parse failure | 1428 / 0 |
| 唯一 FK 实例结构匹配 / 多个有效匹配 / unmatched | 1199 / 25 / 204 |
| 有 JOIN ON 的 Query / 多 FK table-pair 候选 Query | 1140 / 197 |

204 个 unmatched ON 的互斥结构性原因如下：99 个 `non_fk_relation_unverified`，90 个 `metadata_incomplete`（来自 student_club 的端点不完整实例），7 个 `unresolved_alias`，4 个无跨表 equality，4 个列对不匹配声明 FK。它们和 204 的分母一致。

`non_fk_relation_unverified` 只表示参考 SQL 的 join 列对未匹配已声明 FK；本轮没有执行 SQL，因此没有判定这些连接是否合法。197 个查询存在多 FK 表对候选、207 条 `role_candidate_joins` 也都不是可直接使用的语义角色标签。唯一结构匹配不等于业务角色正确。没有人工盲审，语义角色准确率分母为 0；**Role Gate 继续 NO-GO**。

## 7. 异常、偏离与有效结果

所有尝试均使用独立 run ID / 输出目录，没有覆盖既有结果。

| Run | 状态 | 说明 |
|---|---|---|
| `p2a5_smoke5_20261018_01` | 通过 | 5 题 smoke 通过；最初日志包装器因 `/mnt/liansp3/logs` 尚不存在而无法 tee，已保留捕获的输出并创建日志目录补记，不影响 runner 结果 |
| `p2a5_full1534_20261018_01` | 失败，保留 | P1.5 冻结字段名与新汇总字段映射不一致，`KeyError`；尚未产出分析 aggregate。之后显式映射字段名 |
| `p2a5_full1534_20261018_02` | 失败，保留 | 文本特征 accumulator 初始化结构与读取方式不一致，`KeyError`；P2a replay / FK 校验此前通过，未产出 aggregate。修复为统一计数器结构 |
| `p2a5_full1534_20261018_03` | 中间结果，保留 | 回放和核心诊断完整，但最终按计划 A2 核对发现没有输出非 Gold Top-10 特征与字段 token 长度；不作为最终公开 aggregate |
| `p2a5_smoke5_20261018_02` | 通过 | 扩展统计 runner 的 5 题 smoke 通过 |
| `p2a5_full1534_20261018_04` | 最终有效结果 | 扩展聚合完整；重放、cache、S0、分母与 FK Gate 全部通过；本报告与公开 JSON 使用此 run |

这些是审计实现和交付完整性问题，不是 P2a 算法失败，也没有对排名分数做变更。初始与修正 runner/config 的 Git 提交均保留在 `main` 历史中。

## 8. 结论与下一步决策

1. **保持 P2a NO-GO。** BM25 在全体和非饱和子集均落后于 Cosine；RRF 全体 Column R@10 净少 48 个 Gold elements，Complete@2048 救回 27 题、损坏 65 题。非饱和 Column R@10 仅 +0.09 pp，Complete@2048 −5.38 pp；不继续调 RRF/BM25 参数。
2. **可注册一个窄范围的 P2b R0/R1 Values 消融，但本轮没有启动。** Values 字段的 Gold 分层与非 Gold 候选长度都显示足够样本的关联信号；R0 保持原文本，R1 仅移除 Values。预注册时应固定 1024-D Qwen3 + Cosine、问题/候选/预算和 token 序列化，并加入同文本重复编码控制，以区分字段效应与编码数值差异。该结果只会检验 Values 的因果作用，不能把本审计中的相关性当成收益。
3. 这轮数据没有支持更复杂图推理、JOIN 角色监督或 Path Gate；FK 实例身份虽可复核，但 204 unmatched 与 25 ambiguous 仍需独立标签修复 / 人工审查。不得把 197 个多 FK 候选查询写成 197 个角色金标。
4. 本轮报告只提供 BIRD dev 诊断证据；没有独立数据库留出、人工角色审查或端到端 SQL EX 结论。

## 9. API token 与费用账本

- 本实验 API 请求：0；确认输入 / 输出 / 总 token：0 / 0 / 0；未知用量请求：0；本轮模型 API 费用：CNY ¥0.00。没有模型 API 调用，因此本轮没有新增价格报价或费用记录。
- 2026-10-18 账本跨项目累计（只覆盖已登记调用）：已报告输入 4,028,809、输出 198,188、总计 4,226,997 tokens；另有 14 个请求 usage 未知（10 个认证拒绝、4 个其他无 usage 请求）。已报告用量按不可变的未缓存公开价估算为 **CNY ¥8.5232850**，不是供应商实扣；账本无实扣账单核验。未知用量不计入上述 token 和估价总和。
- 该账本不是供应商账户全量消费声明。API 账本费用与本地 CPU/GPU 物理资源费用分开；本轮未计算本地机器租用或折旧费用。
