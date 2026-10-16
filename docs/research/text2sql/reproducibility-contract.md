# 复现、实验数据契约与交付规范

> 本文为 2026-10-14 制订并于 2026-10-16 迁入主仓库的实验实施说明；**计划中的 Text2SQL 专用代码尚未在迁移过程中实现，未核实任何实验已运行**。所有示例路径为建议，不能据此声称脚本已经存在。

## 1. 版本与目录建议

~~~text
docs/research/text2sql/
  paper-and-code-audit.md
  experiment-roadmap.md
  reproducibility-contract.md
configs/
  p0_manifest.example.yaml         # 待实现：版本、数据、冻结超参
  retrieval_sweep.example.yaml     # 待实现：维度/评分实验清单
src/
  schema_graph_builder.py          # 待实现：确定性 Table/Column/FK 图
  schema_texts.py                  # 待实现：可追溯序列化
  encode_embeddings.py             # 待实现：同模型多维编码
  rank_candidates.py               # 待实现：Cosine/BM25/RRF/RolePath
  gold_schema_extract.py           # 待实现：AST解析及人工歧义接口
scripts/
  audit_p0.py                      # 待实现
  run_dimension_sweep.py           # 待实现
  run_similarity_sweep.py          # 待实现
  evaluate_retrieval.py            # 待实现
tests/
  test_no_leakage.py               # 待实现
  test_dim_and_norm.py             # 待实现
  test_fk_identity.py              # 待实现
reports/
  p0/README.md
  p1-dimension/README.md
  p2-similarity/README.md
  p3-end2end/README.md
~~~

以上是**规划文件清单**，不是现有代码。

## 2. 固定输入契约

每条 Query 样本应保留以下字段（私有本地数据）：

~~~json
{
  "question_id": "dataset/db/question_key",
  "db_id": "db_identifier",
  "question": "...",
  "source_dataset_version": "...",
  "schema_hash": "sha256...",
  "schema_text_template_version": "v1",
  "eligible_element_ids": ["table:...", "column:...", "fk:..."],
  "query_instruction_version": "v1",
  "evidence_source_ids": ["ddl:...", "comment:..."],
  "gold_tables": ["..."],
  "gold_columns": ["..."],
  "gold_join_instances": ["..."],
  "gold_label_status": "resolved | multiple_valid | unresolved",
  "strata": ["multi_fk_role", "composite_fk"]
}
~~~

- eligible_element_ids 和 evidence_source_ids 是运行时可见信息；gold_* 只进入评价模块，**不能参与描述生成、候选生成或评分**。
- 每个 FK ID 必须绑定到明确的有序列对/constraint ID；复合 FK 必须一次性保留。
- 需同时保存两个 Schema 信息设定的版本：基本 DDL 信息和允许的真实业务说明信息。任何比较必须固定一个设定。
- 对无 FK 但 SQL 合法的连接，记录为“无法由 FK-only 检索覆盖”并单独分层；不强行判成相似度错误。

## 3. Embedding 缓存与向量健检

建议 cache key：

~~~text
sha256(model_id + model_revision + tokenizer_revision +
       backend_version + prompt_version + schema_text_version +
       dimension + normalization_mode + ordered_texts_hash)
~~~

不可仅用文本内容 hash 复用不同维度/模型/归一化缓存。禁止将机密 Query、数据记录、执行结果或 API key 推送到 GitHub；如仓库私有也应避免意外泄露。

对每种维度记录：
- 模型及 commit revision、vLLM 版本、GPU/CPU、precision、batch、seed；
- query/node/relation 的 output shape / norm min median p95 / 非有限值；
- L2 显式归一化前后范数；
- 单样本重复编码一致性；
- float32/float16 实际 bytes、索引附加元数据内存及检索 wall-clock；
- 所有检索固定准确穷举 Top-K（ANN 留到独立优化实验）。

## 4. 评分数据契约

建议存储统一排序文件（仅本地逐题，仓库可提供匿名聚合）：

~~~json
{
  "run_id": "P2_S3_d512_...",
  "question_id": "dataset/db/question_key",
  "method": "relation_cosine",
  "dimension": 512,
  "candidate_universe_hash": "...",
  "schema_snapshot_hash": "...",
  "scores": [
    {"element_id": "fk:...", "raw_score": 0.0, "rank": 1}
  ],
  "topk": 10,
  "schema_token_budget": 2048,
  "encoder_output_norm_checked": true
}
~~~

验证：S0/S3/S4 比较时**候选元素宇宙相同、可见文本来源相同、Top-K/预算相同**。RRF 对未出现在某路召回列表中的元素如何处理必须明确，避免缺失排名影响可重复性。

## 5. 结果记录模板（每轮必填）

### 5.1 配置信息

| 项 | 记录 |
|---|---|
| 数据库/问题数量、拆分方式 | 待填 |
| 数据版本与 DDL/schema hash | 待填 |
| Git commit、模型 revision、依赖锁定 | 待填 |
| 维度、文本模板、归一化方式 | 待填 |
| 方法/超参、Top-K 与 token budget | 待填 |
| 实际运算资源、执行时间、费用 | 待填 |
| 验证/测试划分及参数冻结时间 | 待填 |

### 5.2 主要指标

| Run ID | N / db数 | Table R@K | Column R@K | JoinInstance R@K | Full Schema Coverage | Hard Role Accuracy | Index MB | Retrieval p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P1-E1024 | — | — | — | — | — | — | — | — |
| P1-E512 | — | — | — | — | — | — | — | — |

同时记录平均、数据库宏平均与数据库聚类 95% CI（数据量不足时仅报告探索性区间）。对于 Hard Role Accuracy 必须标明**可唯一裁定、存在可用候选**的分母，并将候选缺失单独记为错误或 coverage gate，不允许静默过滤困难题。

### 5.3 配对错误与下游 SQL

| 对比 | baseline错→新方法对 | baseline对→新方法错 | 不变 | 数据库聚类不确定性 |
|---|---:|---:|---:|---|
| 待填 | — | — | — | — |

P3 单列 Set EX (primary)、Bag EX (secondary)、原生 SQL 候选池 Oracle (if changed)、token/美元与延迟；不可把 Schema 改变候选 SQL 分布后的提升归因于 SQL Selector。

## 6. 最低限度的回归测试

1. 1024、768、512、256、128 的输出实际维度正确；同一模型同一输入可重复。
2. 显式单位化后 Dot≈Cosine；二者排序一致，避免假阳性算法结果。
3. 更改 dimension/模板/normalization 必须更改缓存 key。
4. 同一对表两条 FK（billing/shipping）不可因 Table-level dedup 合并。
5. 复合 FK 的列对不可拆散，也不可由不相关列拼接新 JOIN。
6. Gold 表/列/路径标签和参考答案不会被文本模板、role hint、检索特征引用。
7. RRF、BM25、Cosine、Role Path 使用相同 candidate universe 和信息预算。
8. 可追溯的未解决歧义不能进入“唯一角色准确率”的分母；且总数量显式报告。
9. 在固定模型与配置时，查询顺序变化不应改变每题检索结果（若存在浮点 tie，则规定稳定 tie-break）。
10. 预训练 GFM 1024 输入与低维不兼容时明确报错，不能静默零填充。

## 7. 仓库提交与数据边界

- 优先提交**实现代码、配置模板、实验协议、聚合结果、版本与 hash**。
- 默认**不要提交** BIRD/其他数据集原始题目、Gold SQL、逐题预测/评分、候选 SQL、数据库内容、API 密钥、缓存和日志；遵循许可，逐题文件保留本地受控路径。
- 新的数字必须说明“实际实验结果 vs 预计目标”，明确 denominator、拆分、置信区间和失败数量。
- 重要协议修改采用版本号（v1→v2）并解释与旧版不可直接比较的原因。

## 8. 第一份交付的验收（P0）

合格的 P0 应同时交付：

- [ ] 版本冻结 manifest 与来源 hash，数据库级拆分；
- [ ] 同一候选图以及稳定的 FK/Join Instance ID，复合 FK 检查；
- [ ] Gold label/多金标/不可裁定统计，明确 Hard Role Set；
- [ ] Qwen3 Text Embedding 的输出维度、范数检查及运行后端说明；
- [ ] P1 预注册 Top-K、token budget、预设非劣界/资源目标；
- [ ] 误差归因的匿名样本分类和 Go/No-go 决定；
- [ ] 对缓存泄漏、基准信息量和下游 Jev 不变的审计。

**P0 通过前不开展 P1 大规模 sweep；P1 结束前不开展 P2 新评分方法搜索。**
