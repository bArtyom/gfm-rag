# 当前执行指导：P1.6 Smoke 恢复 → Full Gate → P2a（2026-10-17）

> **最新状态：已形成执行指导，全部以下行动待实验执行者完成；不代表 Smoke、Full 或 P2a 已运行。**
> 证据：[P1.6 最新复核](../reports/p1_6_smoke_review_20261017/README.md)；[P1.6 已归档报告](../reports/p1_6_rebaseline_20261016/README.md)；[原始 P1.6/P2a 协议](p1_6_rebaseline_then_p2a_20261016.md)。**原历史复现 FAIL、FK/Role FAIL 不得改写。**

## 优先级 0：修复确定的 Manifest 比较缺陷（先 CPU）

文件：`scripts/text2sql/run_p1_6_rebaseline.py`。

**已确认的错配：** Full 的 `current_input_json` 计算发生在 `ordered_node_manifest` 从 `input_record` 移除之前（当前约 L990–998），而 Smoke 存盘及 receipt 哈希引用的是移除该字段后的 manifest（当前约 L1000–1002）。这会让后续 Full 收到错误的 hash mismatch。

执行建议：

1. 将输入清单规范化为一个纯函数，明确输出 `manifest_without_nodes` 和 `ordered_node_manifest`；所有模式使用**完全同一序列化**（UTF-8、key 顺序、indent、ensure_ascii=False、末尾换行）生成 hash。
2. 同时校验候选节点清单的有序 digest，不能为了让 hash 相同而删掉有用验证；保持 `node ID + text hash + token count + order` 的可追溯性。
3. 新增无 GPU 回归测试至少覆盖：（a）同输入 Smoke 保存→Full 复算哈希相同；（b）改变一个字段会触发不一致；（c）变更 node 顺序会改变其 digest。
4. 源码修复单独提交，记录代码 commit / tree SHA，不修改 Embedding 模型、Gold、候选模板、冻结标签或之前实验结果。

**Gate 0**：上述单测通过，重新检查 `--expected-commit` 参数与 `origin/main`、工作树 clean 条件匹配。失败就停止；不要使用禁用 hash/Git 检查的临时开关。

## 优先级 1：重跑 5 题 Smoke（先成功，再考虑 Full）

使用新源码、新目录、新 run ID。复用同一个本地 Qwen3-Embedding-0.6B、官方版本、同样 1,534 题/11 库的冻结数据，只对 5 题/1 DB 做编码。核验：

- Smoke 执行实际成功，`smoke_summary.json`、`smoke_receipt.json` 与 `run_start.json state=completed` 同时存在；
- 有限输出、向量形状/范数、至少一个 column-eligible 问题，`table_question_denominator=5`；
- 两次编码的向量 max-abs-diff、逐题排序变化、Top-K 临界分差明确报告；不只依赖 `status=smoke_passed` 字段；
- 哈希回归单测可被独立复现，且 smoke receipt 指向**修复后版本的正确 Manifest**；
- 真实占用 GPU wall/CPU/RSS 在 P1.6 冻结预算内。

旧两次 Smoke 是运行器失败，不能并入本轮新 Smoke 结果假装成功。

**Smoke Gate：** 满足以上检查且没有新运行器异常。否则修复确定的错误，再仅重跑 smoke，不直接扩大到 1,534 题；记录每次尝试以免调参史丢失。

## 优先级 2：全量 P1.6 冻结基线

仅以已通过的新 Smoke receipt + 相同代码 commit 和输入 hash 执行 Full：

- 1,534 问题 / 11 DB，873 节点（75 table、798 column），Column 分母 1,460，模型只做一次固定 1024 前向。
- 冻结输入 Schema / Query 文本及其有序 ID/text SHA manifest；向量缓存只存本地私有目录，公开只保存 hash/版本/匿名统计。
- 在**同一个已缓存 float32 向量**上重复两次 scorer，要求逐题 Top-K、512/1024/2048 token 预算下选中元素、Recall/Complete、score digest 完全一致；若无稳定性，不进入 P2a。
- 与 P1.5 的 1024 维逐题差异应报告真实数量及候选排位/浮点风险，不要求把旧 P1/P1.5 FAIL 事后判为 PASS。
- 重算 Column R@5/10/20、MRR/MAP、每库非饱和率、预算 Precision/Complete；若 P1.6 与 P1.5 数值变化，说明基线差异而非挑最佳数字。
- 输出 `reports/p1_6_rebaseline_<run_date>/` 中的 summary、配置、commit、哈希及 Gate 判定；保留失败追踪与后续建议。

**Full Gate：** 冻结缓存 round-trip bit exact + 两遍 scorer 得分 digest 和每题指标一致 + 数据/标签分母匹配 + 资源/输入完整性通过。否则仅提交失败诊断。

## 优先级 3：条件式 P2a Cosine / BM25 / RRF

Full Gate PASS 之后**另外预注册并启动** P2a；不修改历史数据，不调 GNN、无 SQL 生成及 Jev。

| ID | 方法 | 目的 |
|---|---|---|
| S0 | 1024 维 Qwen3，L2+精确 Cosine | 当前冻结 Dense 基线 |
| S1 | BM25，完全同一候选文本 + 已冻结 tokenization | 检验词法证据 |
| S2 | S0 + S1 的全排序 RRF，预设 k0=60 | 检验词法/语义是否互补 |

评测：
- 主要：Column R@5/10/20、Precision/MRR/MAP，**同一 1,460 道列可评题**；
- 重点：**706 题、5 DB 的 2048-token 非饱和子集**，并且同时报告 1,460 全体，不使用子集选择获胜者；
- Budget：512、1024、2048 tokens 下 Complete Schema、Precision、有效 Gold elements/1k tokens；
- 每库配对救回/损坏、DB cluster CI（只有 11 DB，谨慎解释）、真实时间和 CPU 资源；
- Go/No-go 延续之前登记的探索阈值：非饱和子集 Column R@10 ≥ S0 +2 pp **或**同预算 Complete ≥ S0 +1 pp，且全体指标无不可接受回归、分库方向稳定；结果能支持继续探索，但 BIRD dev 已反复使用，**绝不等于独立泛化证明**。
- 不将 RRF/BM25 本身视为新研究创新。若 P2a 无法提升，则先研究列描述/字段文本序列化；若有效可尝试将 lexical+dense 用于 GraphReasoner 的 Query Grounding。
- **FK/Role Gate 仍独立 NO-GO**；未通过前不运行业务 JOIN 角色、Query-aware Edge Gate、SQL-aware Path Loss 或端到端 SQL EX。

## 交付顺序

1. 向仓库提交 manifest 校验补丁及 CPU 回归测试结果；
2. 提交通过的 smoke receipt 匿名摘要、代码 hash 和资源使用；
3. 提交全量 P1.6 新冻结基线的公开聚合报告及 Gate；
4. Gate PASS 才另建 P2a 实验结果和下一轮决策。

整个过程不需重新搜索 Embedding 维度，不需下载/升级模型，不涉及数据库内容或 Gold SQL 的 GitHub 上传。
