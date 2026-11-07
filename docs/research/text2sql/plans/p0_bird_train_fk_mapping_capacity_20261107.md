# BIRD train FK mapping 数据容量审计（预注册）

实验 ID：`p0_bird_train_fk_mapping_capacity_20261107_01`
状态：待执行；本文件和运行器须先提交到 `bArtyom/gfm-rag`，再读取任何训练样本 SQL。
层级：exploratory database-disjoint transfer feasibility；不属于正式隐藏测试或论文主结果。

预注册口径更正见 [Amendment 001](amendments/p0_bird_train_fk_mapping_capacity_amendment_001.md)：它只把 schema FK column-pair 数明确为容量上界，并规定隔离检查先于 train SQL 读取；所有样本量门、预算和停止条件保持不变。

## 研究问题与核心假设

问题：在排除已测 BIRD-dev 数据库后，公开 BIRD train split 是否提供足够多的、由显式 `JOIN ... ON` 与多个已声明 FK mapping 构成的 question×table-pair 单元，以支持一次有界的模型代理审阅迁移检查？

候选假设：train/dev 数据库元数据无交集，且冻结规则可筛出至少 60 个合格单元，覆盖至少 4 个匿名数据库。此阶段只检验数据容量和解析完整性，不检验 G-reasoner/Dense 的排名效果。

## 证据范围与暴露限制

- 参考仓库：`https://github.com/bArtyom/gfm-rag`；执行前记录实际分支与 commit，并阅读项目 README、研究 README、路线图和复现契约。
- 数据：`/mnt/liansp3/sources/datasets/bird/train/train.json`、`train_tables.json`；仅读取对应 schema 元数据。禁止打开 `train_databases/` 下的 SQLite 文件或执行任何 Gold/候选 SQL。
- 数据库隔离：先只读 `train_tables.json` 与 `dev_tables.json` 的 `db_id` 元数据并核对交集为 0；若交集非 0，停止且不打开 `train.json`。仅确认隔离后才读取 train 问题与 SQL。
- 暴露：BIRD train 是公开训练拆分；统一资源索引记录该拆分曾被其他本地项目使用。因此任何后续结果只称 exploratory database-disjoint train-split transfer，不称隐藏测试、benchmark 独立复现或无暴露泛化。
- BIRD 官方 Datasheet 将 train/dev 列为公开数据、test 数据库列为隐藏并说明其设计用于缓解预训练数据暴露：[官方 Datasheet](https://papers.nips.cc/paper/2023/file/83fc8fab1710363050bbd1d4b8cc0021-Paper-Datasets_and_Benchmarks.pdf)。

## 冻结筛选与指标

1. 输入文件哈希、样本行数、schema 数量和解析环境在读取 SQL 前记录。
2. 按 `db_id/question_id` 的 SHA-256 确定 5 条容量 Smoke；Smoke 与 Full 严格分离。
3. 用 SQLGlot SQLite dialect 解析参考 SQL；通过 scope-aware source 解析定位显式 `JOIN ON` 中限定的跨表列等式。
4. 只保留能够解析物理表对、且 schema 的 `foreign_keys` 列对列表对该表对声明至少 2 个不同列对候选的单元。该数据格式不保证暴露 FK constraint ID；因此此处只计作**候选容量上界**，不宣称是两个独立 FK constraint。若容量门通过，另行核验复合 FK / constraint identity 后，才可登记模型审阅。
5. 每个问题最多保留一个合格问题×表对单元，按冻结 SHA 排序选择；Full 不包含 Smoke。
6. 匿名数据库名只在本地聚合中映射为稳定 `db_01...` 标签；逐题问题文本、SQL、候选映射身份不得写入 GitHub。

| 门/指标 | 通过条件 | 失败处理 |
|---|---:|---|
| train/dev `db_id` 交集 | 0 | 输入完整性停止；不解析 train SQL |
| Smoke SQL parse | 5/5；scope error 0 | 停止，不自动重试 |
| Full SQL parse | ≥98% | 记录失败数并停止 |
| Full scope-analysis errors | 0 | 停止 |
| 合格候选容量单元（以不同声明 FK 列对计数） | ≥60 | `STOP_INSUFFICIENT_CAPACITY`，不运行模型/排序 |
| 匿名数据库覆盖 | ≥4 | 同上 |

这些是样本容量门，不是效果阈值。沿用 Spider 的 60 单元门，避免看到新的候选数后降低要求。通过容量门也不自动启动模型：先要单独核验实际 FK constraint / composite identities；之后模型审阅的模型版本/提示、token 预算、盲审包哈希、至少 30 个高置信可裁定单元/20 个可区分接受集/3 库门，以及任何 G-reasoner/Dense 排名阶段，都须另行提交预注册和资源记录。

## 资源、预算与停止条件

- 阶段 A 为 CPU-only、最多 8 线程；不调用本地/外部模型、API、GPU、SQLite 或 G-reasoner。阶段 A 通过只提供 schema 列对层面的容量上界。
- 预计最多扫描 9,428 条 train SQL 与 schema 元数据；不复制数据，不安装/升级依赖。
- Smoke 最多一次，Full 最多一次。启动错误按新 run ID 和 amendment 流程处理；不复用失败 run ID，不覆盖结果。
- 输入损坏、解析环境不符、哈希变更或数据库隔离门失败时立即停止并保留失败收据。
- 通过后仅允许提出独立的本地模型审阅注册；未通过即关闭该候选。无论结果如何都不改变 BIRD-dev 的排名或门槛。

## 公开与私有产物

- 公开：本预注册、实现脚本、输入哈希/来源、匿名聚合、完整执行报告、命令/环境/资源、结论与限制。
- 私有本地：逐题 ID、问题文本、Gold SQL、解析片段、FK 身份、逐题产物和日志。
- 结果目录：`docs/research/text2sql/reports/p0_bird_train_fk_mapping_capacity_20261107_01/`。
- 运行 ID：`..._smoke_001` 与 `..._full_001`；若任一运行在读取输入前因环境错误停止，按研究契约登记 amendment 和新 ID，不覆盖旧记录。

## 预期解释

容量门通过只说明存在一个可继续评估的 exploratory 样本池，不说明任何模型效果；门失败只说明冻结抽取规则下该公开训练拆分容量不足。模型判断只能作为代理标签，不能表述为人工 Role 或业务金标准。
