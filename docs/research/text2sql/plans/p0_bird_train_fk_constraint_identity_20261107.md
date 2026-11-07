# BIRD train FK constraint identity audit（预注册）

实验 ID：`p0_bird_train_fk_constraint_identity_20261107_01`
状态：待执行；本方案、配置与 runner 必须先推到 `bArtyom/gfm-rag`，再重读 train SQL 或打开 SQLite。
层级：exploratory 数据有效性门；不是模型效果实验。

**核心假设：**384个列对层面的上界单元中，至少60个问题×表对在 SQLite 完整约束身份下仍有两个以上可区分 FK 约束，并覆盖至少4个数据库。它只决定是否值得单独注册模型代理审阅，不是当前论文主线的效果假设或主线证据。预算为一次5单元 Smoke 与一次剩余 Full；成功标准、停止条件与资源上限见下文。低于样本门立即停止。

## 研究问题与成功判据

容量审计在 BIRD train 中发现384个候选单元，但它只根据 schema 中 FK column-pair 行数计数，可能把一个 composite FK 的组成列对算作多个候选。本审计回答：将这些列对按实际 SQLite FK constraint ID/列序重新分组后，是否仍有至少60个**真实可区分的多约束**问题×表对单元，且覆盖至少4个匿名数据库？

只有同时满足以下条件，才允许另行预注册用户选择的本地模型代理审阅：

- metadata 与 SQLite PRAGMA 的 FK column-pair 集合在纳入单元中完全一致；
- 每个纳入单元的 table pair 至少对应2个不同的完整 FK constraint signature（相同列对的重复 constraint 仍只计一个可区分 signature）；
- Full 至少60个合格单元，覆盖至少4个匿名数据库；
- SQL 重建与 scope 分析无错误，相关 SQLite 文件前后 SHA-256 不变。

低于样本门即停止，不运行模型或 G-reasoner/Dense。此实验不重新评估 BIRD-dev 结果。

## 输入冻结与样本重建

- 项目仓库：`https://github.com/bArtyom/gfm-rag`，分支 `research/p0-sql-used-proxy-alignment-20261107`。
- 上一阶段报告 commit：`fce893c1ac2b52f30dfab1bf24099bdf3c1bf20f`。
- 固定 BIRD train 输入哈希：`train.json` `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520`；`train_tables.json` `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b`；`dev_tables.json` `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97`。
- 固定上阶段匿名 Full 汇总 SHA-256：`fb7f8498f8fdfefe3f220ed06eaa04aa46d2f91ad7acc7018b9d49bdfcb54a66`；上阶段容量 runner SHA-256：`c98422fa518b0fa5c929ed77c27585f363f075fa3546b707cfd2d52dc9288871`。
- 执行时先只读 train/dev schema 的 `db_id` 并要求交集为0；确认后才打开 train JSON。先按上阶段相同 SQL parser、候选筛选和**上阶段五题 Smoke 排除规则**重建 Full 的384单元；必须与冻结的匿名分库计数完全相同，否则在打开 SQLite 前停止。
- 本阶段再从384个固定单元中按新实验 ID 的 SHA-256 选5个 Smoke，优先保证来自5个不同数据库；其余为 Full。Smoke/Full 使用不同 run ID，Smoke 通过后才运行 Full。
- 仅打开候选涉及的数据库文件；容量索引记录 BIRD train 数据库目录共69个 SQLite 文件、约31 GB。具体打开文件由固定候选重建确定，不复制数据库。
- 执行环境固定为 Conda `think2sql_20260909` 中的 `/root/miniconda3/envs/think2sql_20260909/bin/python3.12`（Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2）。须使用该解释器的绝对路径；当前 `conda run -n ... python3` 的命令解析曾落到 Python 3.9，因此不得省略绝对解释器路径。
- Runner：`scripts/text2sql/audit_p0_bird_train_fk_constraint_identity_20261107.py`，SHA-256 `c480d87633317cb5ad93784cc440f1627c18b7048b27b0e1cd1317f2db1baf33`。容量 runner 与匿名聚合的 SHA-256 分别固定为 `c98422fa518b0fa5c929ed77c27585f363f075fa3546b707cfd2d52dc9288871`、`fb7f8498f8fdfefe3f220ed06eaa04aa46d2f91ad7acc7018b9d49bdfcb54a66`。

## SQLite 只读核验

- SQLite 以 `mode=ro&immutable=1` 打开；先启用 `query_only`，再安装 authorizer，仅允许对本轮所需表名执行 `PRAGMA foreign_key_list`。
- 不执行 Gold SQL、候选 SQL、`SELECT`、DML、DDL、`foreign_key_check` 或任何业务数据读取；只读取 schema constraint 元数据。
- 按 SQLite 的 child table、parent table、constraint `id` 和 `seq` 把列对分组成完整约束。对每个 table pair，将 schema FK 列对集合与 PRAGMA 中实际列对集合比较；只有集合完全一致才可参与“真实多约束”计数。
- `constraint signature` 为一个 FK constraint 内全部有序列对的规范化集合。Composite FK 的所有列对合并成一个 signature；相同 signature 不重复计为多个候选。
- 相关数据库在读取前后各计算 SHA-256。任何哈希变化、PRAGMA 异常、路径超出 train database root 或只读 authorizer 拒绝/放行不符合契约，均停止且不重试本 run ID。

## 门槛与运行限额

| 阶段/指标 | 通过条件 | 失败处理 |
|---|---:|---|
| 输入哈希、train/dev DB 隔离、384候选重建 | 与冻结收据完全一致；交集0 | 不打开 SQLite，停止 |
| Smoke | 5个候选均可只读 PRAGMA；至少1个返回可分组约束行；DB 哈希不变 | 停止，不跑 Full |
| Full SQL/scope | 解析错误0，scope错误0 | 停止 |
| metadata/PRAGMA 对齐 | 计数并公开 exact / mismatch，不放宽相等规则 | 纳入项只接受 exact |
| 可区分候选容量 | ≥60 个 exact 且≥2 distinct constraint signatures 的单元 | 不调用模型，停止 |
| 数据库覆盖 | ≥4 个匿名数据库 | 不调用模型，停止 |

- CPU-only，最多8线程；最多30分钟墙钟、20分钟 CPU、4 GiB RSS。GPU/API/模型调用均为0。
- Smoke 最多一次；Full 只在 Smoke 通过后运行一次。任何失败保留现场；新尝试须独立 Amendment 和新 run ID。
- 用户已授权模型审阅，但这不是模型审阅注册。若门通过，模型版本/量化、盲审 prompt、token 上限、usage 账本、置信度与一致性判据必须另行预注册。

运行顺序：将方案、冻结配置、runner 与路线状态先提交并在 GitHub 逐文件读回核验；之后运行 Smoke，且仅在 Smoke 收据通过时运行 Full。命令使用 `/root/miniconda3/envs/think2sql_20260909/bin/python3.12`，`CUDA_VISIBLE_DEVICES=""`，分别使用独立 run ID 和私有输出目录。任何失败均保留现场；不重跑本注册。

## 公开和私有产物

- 公开报告目录：`docs/research/text2sql/reports/p0_bird_train_fk_constraint_identity_20261107_01/`；仅写匿名 aggregate、输入 hash、命令、资源和限制。
- 私有本地结果：`/mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/`；包括逐题候选清单、数据库/表/列标识和实际 constraint grouping，权限限定为当前用户。
- 私有日志：`/mnt/liansp3/logs/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/`。
- BIRD train 是公开且已有其他本地项目使用的训练数据；结论限 exploratory database-disjoint train-split transfer。
