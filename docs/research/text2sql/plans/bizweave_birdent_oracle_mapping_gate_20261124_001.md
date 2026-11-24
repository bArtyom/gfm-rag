# BizWeave BIRD-Ent Oracle Mapping 可行性 Gate

**Run ID:** `bizweave_birdent_oracle_mapping_gate_20261124_001`
**状态:** 预注册；数据与样本尚未读取。
**实验层级:** 有界探索性 pilot，不是主实验或基准结论。

## 研究问题与核心假设

检查 BIRD-Ent 的业务知识文档是否确实包含可以绑定到物理表列的、可引用原文证据的业务 Claim；若存在，带正确 `Claim → Column` 映射的 Business–Schema 图，在问题、Schema、文档、候选全集和 K 相同的条件下，是否能比文档增强的扁平 Schema 检索找回更多 gold-required 字段。

这是有利于图方法的 **oracle mapping 上界**：映射由调查者在查看文档与 Schema 后核验，不代表模型可以自动生成这些映射，也不评估端到端知识文档召回。正向结果仅作为是否值得进入更大标注 pilot 的证据。

## 数据、抽样与盲审

- 来源固定为 `jjjycaptain/BIRD-Spider-Ent`，revision `cde16ccf0eb606585642d6b06209760d73fd28dc`，数据卡标注 CC-BY-SA-4.0；只用数据卡、BIRD-Ent task、data asset、knowledge document 与许可/NOTICE 文件，不取数据库内容。
- 从 task 文件原始顺序扫描；最多取 5 条具有至少一个 `gold_knowledge_id` 的任务，并优先让每条来自不同 data asset。若字段名/结构与此描述不符，在查看任何题目内容前记录 amendment 并冻结等价规则。
- 在映射阶段，调查者仅查看对应 Schema/字段说明和关联业务文档，不看用户问题、Gold SQL、`gold_table_ids` 或其他评测答案。`gold_knowledge_ids` 仅用于确定条件式 oracle 文档集。逐条保留文档 ID、证据跨度偏移、映射列 ID、支持状态（直接/推断/歧义/不支持）和判断理由；该审阅由 AI 助手完成，不能称为独立人类标签，也不计算标注者一致性。
- 有效映射须落到明确表列，并有精确文档跨度支持。仅主题相关、仅表级泛化、字段名猜测、或不支持的映射不计入有效映射。Gold SQL/答案只在盲审映射冻结后用于评估。

## 对照协议（仅在审计门通过时）

审计门：5 个样本中至少 3 个存在至少一个非平凡、字段级且有原文支持的映射；否则停止，不计算检索收益指标。

- **FlatDocBM25:** 将同一任务的问题与其 `gold_knowledge_ids` 对应的完整文档拼接为查询文本，对同一 Schema 列候选全集按 BM25 排序。
- **OracleBizWeave:** 用冻结的 Claim→Column 映射边，将同一问题对文档 Claim 的 BM25 分数传播到已映射列；未映射候选按相同 Schema-only BM25 补足排序。采用同一列全集与 K。
- BM25 固定为小写字母/数字 token，拆分 snake_case 与 CamelCase；`k1=1.5, b=0.75`；稳定 tie-break 为列 ID 字典序。主指标为 gold required column Recall@10；次指标为 gold table Recall@5、MRR。若发布数据没有可直接用的 column label，则在映射盲审封存后用已有 SQLGlot 解析 Gold SQL 得到引用列，并单独记录解析失败；不执行 SQL。Gold SQL 解析结果仅用于 scoring。
- 所有 5 例逐题结果只在本地保存；公开报告只给匿名聚合。`gold_knowledge_ids` 造成的 oracle 条件必须在所有结果中显式标记。

## 预算、成功与停止条件

- CPU-only；最多 5 个 task、关联文档、15 分钟、4 CPU 线程、4 GiB RSS；不启动 GPU，不调用任何模型或外部 API，不安装依赖，不执行 SQL。
- 进入下一轮 30–50 例人工标注探索 pilot 的成功条件：审计门通过，且 OracleBizWeave 在至少 2/5 例提升 gold required column Recall@10；映射边须有支持证据。该门槛只判断是否值得继续，不能据此声称显著效果、自动构图能力或新颖性。
- 若样本结构无法稳定关联文档与 Schema、5 例中不足 3 例存在有效字段映射、Oracle 不满足成功条件，或运行超预算，即停止并记录 `NO-GO` / `HOLD` 原因，不扩大数据规模。

## 版本与复现

- 项目仓库：`https://github.com/bArtyom/gfm-rag`；分支：`research/bizweave-event-constraints-20261117`。运行前本地 HEAD 为 `63c2787d849b359ad1a71818b8286f46669a0728`；协议、配置与必要脚本须在读取样本前提交并推送。
- 参照并遵循仓库 `README.md`、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`；本次使用后者的 gold-label 隔离和公开数据边界约定。
- 本地结果与日志分别登记到 `/mnt/liansp3/sources/results/bizweave_birdent_oracle_mapping_gate_20261124_001/` 与 `/mnt/liansp3/logs/bizweave_birdent_oracle_mapping_gate_20261124_001/`。原始任务、问题、SQL、文档全文、逐样本映射和日志不进入 Git。
