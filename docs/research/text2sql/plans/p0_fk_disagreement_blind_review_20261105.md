# P0 FK 定义分歧双人盲审材料准备协议

> 状态：预注册，尚未运行。实验 ID：p0_fk_disagreement_blind_review_20261105_01。只准备本地盲审材料；不产生人类标签、模型结果或 SQL EX。

## 研究问题与痛点

2026-11-05 canonical crosswalk 在相同 1,534 道 BIRD dev 题上确认：packet-28 与 canonical P1.5 对 FK-match / multi-FK candidate 的定义仍不同。双方在 88 道题上只有 packet-28 标为 FK-match，15 道题只有 canonical P1.5 标为 FK-match；另有 21 道题只有 canonical P1.5 标记 multi-FK candidate。FK-match 和 multi-FK 都不是 Gold business Role 标签。

本轮问题是：能否从这些定义分歧中抽出一组可复查案例，让两名独立审阅者在不知道方法来源、Gold SQL 和模型排序的情况下，判断给定表对的关系映射是否由问题明确指定、存在多个可接受映射，或无法确定？

研究层级为 P0 标签定义与审阅准备，属于 exploratory。审阅单位是“问题 × 给定表对”。表对由 SQLGlot 从参考 JOIN ON 结构中提取，用于把任务限定为“已知两个端点时判断 FK 映射”；审阅者看不到 Gold SQL、ON 条件或该表对是否来自 Gold。这个条件式任务不能代表端到端表召回或部署时可见信息评测。

## 核心假设与边界

冻结的逐题 crosswalk、canonical SQL 诊断和有效 SQLite FK 实例可以支持可重复抽样及不泄漏方法来源的双人材料。材料准备成功只说明数据和审阅流程可运行，不表示两位审阅者已经完成标注，也不解锁 Role Accuracy、监督训练、GNN 角色排序或真实 SQL 扩样。

BIRD dev 已被重复用于开发和诊断，不是独立测试集。所有审阅者必须是人类且独立完成；Qwen 或其他模型不能替代审阅者或充当可信 Gold。

## 输入与冻结版本

只读取以下已登记输入，不读取 SQLite 业务表行、不执行 SQL、不调用模型：

| 输入 | 统一入口 | SHA-256 |
|---|---|---|
| BIRD dev questions | local:datasets/bird/dev/dev.json | 630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06 |
| BIRD dev schemas | local:datasets/bird/dev/dev_tables.json | 35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97 |
| P1.5 FK artifact | local:results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json | 5bc60f6d64429215fa92d3c3a42f1a4881dc77c09839729153fb55a119555060 |
| canonical crosswalk private rows | local:results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json | 7acdbecca557d8ce49283adca174e1caacd9dc77929e1f6ad819b75299a9938e |
| canonical P1.5 full output | local:results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json | 746e6366831b5924fedd309af4c96f71ab49d6f3462ad2d054cfd427fb2f33ed |

SQLite FK 候选只使用 artifact 中 valid_endpoints 严格为 true 的实例。实例身份为数据库、child table、有序 child/parent column pairs、parent table；结构完全相同的声明折叠为一个映射，重复次数只记在私有 manifest 中。复合 FK 必须整组展示，不能拆成独立候选。

## 分层抽样

先按哈希问题键连接 crosswalk、canonical P1.5 行和 BIRD dev 输入，再使用固定 seed 20261105 按每个分层的 SHA-256 排序抽样。类别配额如下：

| 分层 | 冻结总体数 | 配额 | 选择规则 |
|---|---:|---:|---|
| packet-only FK-match；canonical P1.5 有 ambiguous 证据 | 22 | 6 | 确定性抽样 |
| packet-only FK-match；canonical P1.5 有 unmatched 证据 | 66 | 6 | 确定性抽样 |
| canonical-only FK-match | 15 | 15 | 全部纳入 |
| canonical-only multi-FK candidate | 21 | 21 | 全部纳入 |
| 两套定义都同时标记 FK-match 与 multi-FK 的正向控制 | 173 | 6 | 确定性抽样 |

各分层先独立满足配额，再按问题键去重并合并分层标签；同一道题不得重复出现。预期抽样赋值共 54 次，实际唯一问题数和表对数在运行后报告。若任一冻结总体数或配额不足、去重后唯一问题少于 30，立即停止，不跨层替补。

## 审阅材料与盲态

每位审阅者看到自然语言问题、待判断的表对，以及该表对在冻结 SQLite schema 中全部有效、去重后的 FK mapping。若没有有效声明映射，明确显示无候选。映射用匿名 ID 展示，A/B 两份包的案例和映射显示顺序分别打乱；ID 在两份包之间保持一致，便于之后计算逐项一致性。

审阅者看不到数据库 ID、题目 ID、Gold SQL、Gold ON 列、P1.5/packet 标签、分层类别、模型分数、排名或方法来源。由于表对是从参考 JOIN 结构抽取的，审阅任务明确限定为条件式角色判断，不称为完全无 Gold 派生信息的在线评估。

每个表对填写以下决策之一：single_mapping、multiple_mappings、cannot_determine、no_declared_fk、other；同时填写所选 mapping ID、置信度 1–3、理由类别和可选说明。只有两人对状态和映射集合完全一致，且双方置信度均至少为 2，才记为候选共识。否则保留为未决，不用模型裁决。

## 成功判据、预算与停止条件

材料准备成功须满足：所有冻结输入哈希匹配；1,534 个问题键完整连接；五个分层总体数准确；每个配额准确且去重后至少 30 道题；每题至少有一个可解析表对；候选映射完整保留复合列对；A/B 包的案例和候选集合一致、显示顺序按 seed 打乱；包中不包含 Gold SQL、方法来源、私有 ID 或逐题 crosswalk 标签；私有 manifest 与每个产物均可校验哈希。

预算：一次最多 5 题 Smoke，通过后一次 Full；失败不重试同一 run ID。CPU 上限 600 秒、RSS 4 GiB、最多 8 线程；GPU、模型、API、SQL 执行、训练、下载和安装均为 0。Smoke 只在内存中渲染材料并写匿名回执；Full 才写权限受限的本地审阅包。

任何输入/hash/环境漂移、分层数不符、目标题不可解析、复合 FK 不完整、隐私检查失败、资源超限或目录已存在时停止并保留现场。不得放宽门槛后替换样本。

## 产物与复现

- 执行器：scripts/text2sql/prepare_p0_fk_disagreement_review_packet.py。
- 计划与公开匿名报告：docs/research/text2sql/plans/ 与 docs/research/text2sql/reports/p0_fk_disagreement_blind_review_20261105_01/。
- 私有材料：local:results/gfmrag_p0_fk_disagreement_blind_review_20261105_01/。
- 日志：local:logs/p0_fk_disagreement_blind_review_20261105_01/。
- 公开仓库只保存协议、代码、匿名统计和报告；问题文本、数据库标识、SQL、逐题类别、mapping crosswalk、审阅包和原始回复均不上传。
- 完成材料准备后停止，等待两名真实审阅者独立提交表单。审阅结果分析必须另有明确登记，不能把准备阶段记为标签实验已完成。
