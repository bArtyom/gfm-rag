# BIRD Gold SQL 标签稳健性审计（预注册）

**实验 ID：** `p0_bird_gold_label_robustness_20261106_01`

**登记日期：** 2026-11-06

**代码/指导基线：** 用户项目 `bArtyom/gfm-rag`，分支 `research/p0-fk-rank-error-analysis-20261106`，commit `64c7d2ba629828256bd8eb85cbfdc8cbd9e150a5`。本方案在独立分支上预注册。
**性质：** exploratory 的测量稳健性审计；不是新检索方法，不调用 GFM 或 SQL 生成器，不用于声称独立测试集泛化。

## 痛点与研究问题

P1.6/P2c-R 的 Table、Column 与 Complete Schema 指标由 BIRD 原 Gold SQL 推导标签。若 SQL 标注错误，固定排序器可能被错误标签误判。UIUC-Kang Lab 发布的 Arcwise-Plat-SQL 只改正 SQL 标注，保留原问题和 evidence 的歧义；这提供了一个比重跑编码更干净的标签扰动来源。来源论文为 [Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards](https://arxiv.org/abs/2601.08778)，数据仓库为 [uiuc-kang-lab/text_to_sql_benchmarks](https://github.com/uiuc-kang-lab/text_to_sql_benchmarks)。源仓库当前固定到 main commit `fe766045c55b6875a43b30e9ac7683df5582f8cf`，`LICENSE` 声明 CC BY-SA 4.0。

**核心问题：** 对题目、evidence、数据库 Schema、候选集及 P1.6 排名全部固定，只将原 Gold SQL 换成官方 SQL-only corrected SQL，Gold 表/列标签和 Dense 检索指标改变多少？

**可证伪预测：**

- 若旧指标稳健，原/修正版 Gold table/column 集合高度一致，且同一冻结排名下的主要检索指标差异很小。
- 若标签错误实质影响评价，部分问题的标签集合会改变，并导致 Recall@K 或预算内完整 Schema 覆盖出现可见配对变化。
- 此审计不能说明哪个 SQL 才符合原问题的所有可能解释；SQL-only 文件保留原问题与 evidence 中的歧义。

## 对照、变量与指标

- **唯一干预：** 标签来源由本地 BIRD 原 SQL 切换为 Arcwise-Plat-SQL corrected SQL。
- **固定项：** 原问题、evidence、db_id、Schema snapshot、873 个 P1.6 候选节点、Qwen3-Embedding-0.6B 冻结向量、1024 维 cosine、stable node-ID tie-break、tokenizer 和 1,024-token budget。不得重新编码或训练。
- **对照组：** 相同问题的原 SQL 标签与 corrected SQL 标签，使用相同排名和候选顺序配对计算。
- **单位：** 问题。首先报告 table/column label set 的精确一致率、变更数和 Jaccard；其次报告 Table Recall@5/@10、Column Recall@5/@10、Complete Schema@1024 的配对差值，以及完整覆盖由对变错/由错变对的数量。
- **统计：** 报告 question-macro 与可计算的 database-macro；以数据库聚类 bootstrap 95% 区间作探索性不确定度摘要，数据库数量不足以支持稳定区间时只报告点估计和簇数。

## 数据与纳入规则

- 数据入口先登记于个人资源索引：`/mnt/liansp3/sources/datasets/bird_arcwise_plat_sql_only_20261106/arcwise_plat_sql_only_with_diff.json`。数据不得提交到项目仓库。
- 冻结本地原始 BIRD dev `dev.json`、`dev_tables.json` 与 P1.6 产物 `full_1534_20261018_01`；记录下载字节数、SHA-256、Git commit/blob、输入文件哈希和产物哈希。
- 只有当公开记录与本地记录在 `db_id`、原始 `question`、`evidence` 和问题标识上一对一精确匹配时，才纳入 SQL-only 对照。不得用模糊文本匹配补配；匹配失败或重复立即停止完整审计并报告 gate。
- Gold SQL 只由隔离的标签提取步骤读取，不参与文本序列化、向量缓存、排序或候选生成。沿用 P1.6 的 SQLite SQLGlot 标注提取约定；保存原/修正版解析覆盖和无法解析项，不静默剔除。
- Smoke：按 SHA-256(`db_id/question_id`) 稳定排序取 5 题，独立检查字段、精确匹配、标签提取、Top-K 与 budget scorer parity。Smoke 题从主 Full 分母排除。
- Smoke 通过后，Full 使用其余匹配题（若发布集为 498 题且全匹配，则 Full 为 493 题）；未达到精确匹配或标签解析 gate 时停止，不扩大到其他 BIRD 数据。

## 成功判据、解释门与停止条件

本审计的成功是“能够在不改变排名的情况下可靠重算标签敏感性”，不是任何方法取得正收益。

- **运行有效性门：** Smoke 5/5 字段、匹配与解析流程成功；针对 Smoke 原 SQL，冻结排名的 Table/Column Top-K 和 1,024-token 选集与 P1.6 原始输出一致；正式匹配需一对一且精确。原/修正版标签解析率均须至少 98%，否则不解读检索分数。
- **实质标签敏感门：** Full 中至少 5% 问题的 gold table 或 gold column 集合改变，或任一主检索指标绝对变化至少 2.0 个百分点。
- **稳健门：** 标签集合变更问题不超过 1%，且三项关键覆盖指标（Table R@10、Column R@10、Complete Schema@1024）绝对变化均小于 1.0 个百分点。
- **其他结果：** `INCONCLUSIVE / MIXED`；不继续改 parser、改标签定义或扩展样本来追逐门槛。
- 任意输入哈希不符、匹配歧义、原始标签/冻结排名复算不一致、资源或文件完整性异常时停止并保留失败现场；Full 最多运行一次。

## 资源、运行方式与隐私

- CPU-only，单进程最多 4 线程，墙钟预算 10 分钟、RSS 预算 8 GiB；不加载模型、不调用 API、不使用 GPU、不执行 SQL、不安装依赖。
- 运行前重查 `nvidia-smi`、`free -h`、`nproc` 和磁盘；输出、日志、下载数据均使用此 ID 的新目录，不覆盖已有结果。
- 代码从项目根目录在 `think2sql_20260909` 环境执行；复用已安装 SQLGlot/NumPy。记录 Python、SQLGlot、NumPy、Git commit、命令、开始/结束时间及资源摘要。
- 私有输出在 `/mnt/liansp3/sources/results/gfmrag_p0_bird_gold_label_robustness_20261106_01/`；日志在 `/mnt/liansp3/logs/gfmrag_p0_bird_gold_label_robustness_20261106_01/`。公开仓库只保存本协议、匿名聚合与完整报告，不保存原始问题、SQL、逐题标签、逐题排名或原始数据。

## 决策用途与限制

- 若达到实质标签敏感门，先修订对 P1.6/P2c-R 检索质量的表述，并将原 Gold 与 corrected Gold 的指标并列；不自动重跑检索器或生成器。
- 若达到稳健门，结论限于这 493 个未用于主 Full smoke 的 matched mini-dev 问题和三项阈值；保留 BIRD dev 的 exploratory 属性。
- 若 mixed/inconclusive，停止该标签支线并回到错误分析；不把标签审计改名成方法贡献。
- 不验证 SQL 执行准确率、歧义消解、JOIN Role、GFM 传播、模型输出质量或独立数据库泛化。原始 Gold 与 corrected SQL 的差异只作评价标签来源的对照。

## 预期归档

- 运行代码：`scripts/text2sql/audit_bird_gold_label_robustness.py`。
- Smoke/Full 独立配置与本地日志、结果 manifest、失败回执和聚合 JSON 保存在相应私有目录。
- GitHub 报告：`docs/research/text2sql/reports/p0_bird_gold_label_robustness_20261106_01/README.md` 与匿名 `aggregate_summary.json`；原始问题、SQL 和逐题输出不上传。

## 执行前修订 A1：历史标签解析器兼容门与环境（2026-11-06，Smoke 前）

### 修订原因

- 复核发现，旧 P0 全量审计只归档了摘要与代码哈希；它记录 `SQLGlot read=sqlite`、Python 3.10.21、SQLGlot 30.12.0、1,534/1,534 SQL 可解析、1,460 题列引用完整。产生该审计的 `run_p0_audit.py` 当前未保留。
- P1/P1.6 runner 直接读取历史 `per_question_private.jsonl` 中已冻结的表/列标签，不从 SQL 重新提取标签。因而当前不能声称能够逐字节复用原标签解析实现。
- 原协议预设的 `think2sql_20260909` 安装 SQLGlot 28.0.0，与旧 P0 记录的 SQLGlot 30.12.0 不同。继续使用该环境会把解析器版本变化混入唯一干预。

### 冻结修订

- 解析使用本机现有 `qes_rear_refine` 环境中的 Python 3.10.22 与 SQLGlot 30.12.0；不安装或升级依赖。`conda run -n qes_rear_refine python3` 在本机解析到 Python 3.9，因此命令须通过该环境的绝对 `python` 解释器启动，并记录此运行入口偏差。
- 新增历史兼容门：对每个精确匹配的原始 SQL 重新提取表/列标签，并与 P1 冻结逐题标签对照。Smoke 的 5 题必须全部逐项一致；498 个匹配原始 SQL 的逐题集合一致率须至少 98%，原始 SQL 与 corrected SQL 的解析率、非空表标签率和列标签完整率也须分别至少 98%。任一门未过，停止指标比较并把差异作为解析兼容问题报告，不调整解析器追逐结果。
- 指标对照始终使用同一 SQLGlot 30.12 解析器分别处理原 SQL 与 corrected SQL。若原始标签的逐题兼容率未达到上述门槛，不把重解析的结果称为 P1.6 指标复算。
- Smoke 的原 Gold 标签重新计算出的 Table/Column Top-K 命中和 Complete@1024 必须与 P1.6 封存逐题结果一致。Full 不包含 Smoke 的 5 题。
- Full 同时报告各标签源自身的列资格分母，以及两边均列资格问题上的配对指标；列资格变化单独计数，不静默排除。
- 数据、模型/向量、排序、主要敏感性门槛、停止条件、CPU-only 预算和隐私边界不变。Bootstrap 固定为数据库簇、10,000 次、seed `20261106`；不足 5 个有效数据库簇时不报告 bootstrap 区间。

### 审计结论边界

本修订使用归档的 P0 摘要和逐题冻结标签作为兼容证据。由于原始标签提取源码缺失，即使兼容门通过，也只称“逐题标签兼容重建”，不声称恢复了原始脚本或其全部解析行为。原/修正 SQL 标签比较仍是本实验唯一科学干预。
