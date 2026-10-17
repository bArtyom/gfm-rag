# P1.6 最新实验状态与源码审计（2026-10-17）

> **状态：只读检查已提交 GitHub 文件与脚本；未访问实验主机/私有运行目录，未运行新的 Smoke、Full 或 P2a。**
>
> 开始审阅时主仓库 `main` 最新提交：`efd6af442321f00aeb16b40f259685ed68cbe1b5`（2026-10-16T15:00:17Z）。主要证据：[P1.6 进度报告](../p1_6_rebaseline_20261016/README.md)、[`run_p1_6_rebaseline.py`](../../../../../scripts/text2sql/run_p1_6_rebaseline.py)、[历史执行协议](../../plans/p1_6_rebaseline_then_p2a_20261016.md)。

## 核心结论

**P1.6 正在执行，但未完成。** 已过预检，先后两次 5 题 Smoke 都在 scorer/聚合阶段失败；仓库已有针对两处报错的代码修复，但截至本次审阅未归档修复后成功的 Smoke 报告。没有全量 1,534 题新基线，没有 P2a BM25/RRF，也没有 GNN、JOIN Role/Path、SQL Execution 或 Jev 的新结果。

既有 P1/P1.5 结论不变：旧逐题 14,896 项检查中 91 项不一致，历史严格复现 FAIL；FK/Role Gate FAIL。**不能因本轮预检或两处修复便宣布 P1.6 PASS。**

## 已发生的两次真实 Smoke 尝试

| 实验事件 | 失败位置 | 当前代码状态 | 推论边界 |
|---|---|---|---|
| `p1_6_smoke5_20261016_01` | per-question `column_hits` 初始为 `None`，无法赋列命中值 | Commit `a04f6dc5` 修复为可写字典 | 已改代码，但没证明端到端 Smoke 成功 |
| `p1_6_smoke5_20261016_02` | 汇总 schema token 数时把节点下标当节点对象访问 | Commit `efd6af44` 已按数组索引读 `token_count` | 已改代码，需重新跑 5 题 Smoke |

预检确认冻结 BIRD dev **1,534 题、11 DB、873 节点（75 table/798 column）、1,460 column-eligible**；输入/model hash 检查通过，旧差异原因依然 unresolved。以上为工具链进展而非检索质量增益。

## 新发现：下一次 Full 前必须修复的 Manifest 哈希不一致（源码静态证据）

阅读 `scripts/text2sql/run_p1_6_rebaseline.py` 的当前代码可见：

1. `validate_inputs()` 构建的 `input_record` **包含** `ordered_node_manifest` 键（约 L268–294）。
2. Full 路径先做 `current_input_json = json.dumps(input_record,...)`，对整个对象哈希，再与 Smoke 的 `input_manifest_private.json` 文件哈希比较（约 L990–998）。
3. 但 Smoke 和 Full 落盘之前，`node_manifest = input_record.pop("ordered_node_manifest")`，**将该字段拆分到另一个文件**，再写入 `input_manifest_private.json`（约 L1000–1002）。
4. 因此 Full 在内存中哈希的是「有节点清单」的对象，Smoke receipt 引用的磁盘 manifest 是「无节点清单」的对象。相同输入也会比较不一致，在实际 Full 编码之前抛出 `Full input manifest differs from the smoke input manifest`。

**判定：确定存在的代码逻辑缺陷，尚未见到真实 Full 失败日志。**

推荐修复（行为不改变模型/向量）：

- 由唯一纯函数 `canonicalize_input_record(record)` 返回 `(node_manifest, manifest_without_nodes)`，按统一 `json.dumps(... ensure_ascii=False, indent=2, allow_nan=False) + "\n"` 输出；
- Smoke 保存和 Full 验证对**同一个** `manifest_without_nodes` 字节串哈希；节点清单 hash 另外比较 `ordered_node_manifest_sha256`，并检查原始 list 本身稳定；
- 更简单的局部修复是让 Full 在哈希前先对 `dict(input_record)` 做 `pop("ordered_node_manifest")`，再执行完全一致的序列化，但建议抽象单函数并写回归测试。

**最低回归测试（无需 GPU）**：用一份相同的冻结 `input_record` 做 Smoke 文件保存、Full 对象哈希，断言匹配；故意修改一个 node/text hash，断言立即失败；交换候选 node 顺序，断言另行保存的 ordered manifest digest 变化。不能仅测试已有文件 digest 自等。

另检查 `assert_committed_source(expected_commit)` 要求 `origin/main`、`HEAD` tree、clean worktree 与注册的 commit 一致。**修复脚本并提交后，重跑 Smoke 时需同步新 commit，并把该 commit 作为后续 Full 的冻结版本；旧 smoke receipt 不适用于新的代码版本。** 不推荐绕过 git dirty / 哈希检查来让实验通过。

## 尚需验证的其他协议边界

- 新代码的 Smoke 会编码同一 5 题两次并报告向量最大绝对差和逐题输出变化，但 `smoke_passed` 的基本条件主要检查题数/分母/有限值；如出现排序明显变化，必须报告并依据已冻结的数值稳定协议处理，不能把 `status=smoke_passed` 当作「两次编码逐题完全相同」。
- Full 在缓存向量上对 scorer 连续执行两次，要求逐题行、score digest 完全一致；这只能证明**冻结缓存下的确定性**，不是重新编码的跨机器 bit-exact 证据，也不等于历史旧 P1 复现 PASS。
- 原 P1.5 的 Column@10≈68.06%、2048 Token 完整率≈79.59% 仍是最近已完成的纯 Embedding 诊断；P1.6 没有能替代它的正式新性能结果。
- FK/Join Instance 信息质量仍不足；不把后续密集/词面列检索实验混成图推理实验。

## 研究决策

**当前行动：先用 CPU 最小测试修复 manifest 签名不一致，重新执行 5 题 Smoke，之后才执行 P1.6 Full；Full Gate PASS 后另行冻结并开展 P2a。**

详见 [下一轮恢复执行计划](../../plans/p1_6_smoke_recovery_then_p2a_20261017.md)。

## 评价 P1.6 是否值得继续

可以继续：冻结源、数据和模型已校验，两个先前 smoke 失败都是确定的 Python scorer 汇总错误，改动后不应要求重新训练。短期 CPU 单测和 5 题 smoke 的代价低于反复全面重跑。

不可继续无界调试：如果同一类别再次失败，先追加可复现回归测试、定位堆栈并限制尝试次数；如果真实模型编码不稳定或输入不一致，则停留 P1.6，不启动 P2a。到目前**没有算法性能结论发生变化**。
