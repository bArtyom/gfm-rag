# BIRD-dev 双人盲审候选包准备

**实验 ID：** p0_role_blind_review_packet_20261025_01

**Full Run ID：** p0_role_blind_review_packet_20261025_01_packet_001

**状态：** PREPARATION_GATE_STOP。Smoke通过；Full因历史计数门不匹配而停止，未生成评审包。

**运行日期：** 2026-10-25 UTC

## 研究问题与边界

本轮要从P0报告记录的174个多FK候选中确定性抽取20例，生成两份不含Gold SQL或模型结果的本地双人盲审材料。核心门槛是先按冻结的SQLGlot/Schema JSON规则复现四项历史计数；计数不一致即停止，不能改筛选定义追数。

这只是人工审阅材料准备，不是模型/SQL实验。即使包生成也不会自动成为角色标签；本轮实际没有生成包或标签，trusted_role_label_n仍为0。

## 指导、预注册与实现

- 项目仓库：bArtyom/gfm-rag，分支 research/p0-role-review-packet-20261025。
- 预注册 commit：f880de25f93f2f80980ab0d5e2f6226c1e747b85。运行器与预注册文件在执行前已逐文件回读确认。
- 遵循仓库README、Text2SQL研究README、experiment-roadmap、reproducibility-contract及最新P0证据报告。P0报告要求在Role实验前取得双人盲审标签。
- 运行器只读BIRD dev的dev.json和dev_tables.json，以schema JSON中的有序FK映射构造候选。它在本地内存中读取dev.json的问题与Gold SQL并用SQLGlot解析以计算汇总计数；Gold SQL没有写入审阅包、日志或GitHub。没有读取dev.sql或SQLite业务行。代码SHA-256：5c84af91edc6dd39cd1fba39105dfc74b804be17912d91edab5eba2ff180eebc。
- Smoke与Full预算均为CPU 600秒、RSS 4 GiB、GPU/API/本地模型/SQL执行/训练/下载/依赖改动均为0。没有模型配置或模型成本。

## 数据、环境与资源

固定输入哈希与预注册值一致：

| 输入 | SHA-256 |
|---|---|
| dev.json | 630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06 |
| dev_tables.json | 35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97 |

- 环境：t2sql_code_audit_20261005；Python 3.10.22；SQLGlot 26.33.0。沿用已有环境，未安装或升级依赖。
- 启动前资源快照：192逻辑CPU，内存503 GiB总量/414 GiB可用；GPU仅监测、不使用。
- 本地数据统一入口最终指向Alpha-SQL目录中的BIRD dev公开数据；未复制数据集。
- BIRD dev为开发/诊断集，不是独立测试集。

## 执行与结果

Smoke对5条样本完成解析和盲审模板渲染，结果SMOKE_PASS；输入hash通过，未写出问题文本或Gold SQL。Smoke耗时1.87秒外层wall；进程内wall 0.033625秒、CPU 0.025906秒、峰值RSS 0.021973 GiB。

Full解析1,534条记录后命中预注册停止门：

| 指标 | 预期历史值 | 本次实现值 | 差异 |
|---|---:|---:|---:|
| 题目/解析成功 | 1,534 / 1,534 | 1,534 / 1,534 | 0 |
| 含JOIN ON题数 | 1,140 | 1,140 | 0 |
| 至少匹配一个声明FK的题数 | 956 | 1,043 | +87 |
| 多FK同表对候选题数 | 174 | 176 | +2 |

Full命令以退出码2停止；外层命令wall约2.667秒。进程CPU时间和峰值RSS未测量。由于计数门失败，写包步骤没有启动；检查确认预期的packet_001输出目录不存在。无Gold泄漏、无模型调用、无SQL执行、无GPU使用，外部API与本地模型token均为0，费用0 CNY。

## 解释、失败记录与下一步

数据hash、解析题数和JOIN ON题数匹配，但FK匹配数与多FK候选数不匹配。该结果表明本轮实现对历史提取规则的复现不足；它不是数据变化，也不是角色方法的科学结果。历史公开材料只有聚合数，没有逐题候选清单，因此当前无法确认差异来自FK来源、JOIN条件匹配定义还是其他历史归一规则。按预注册规则没有调整计数定义或重跑。

- 私有Smoke结果与日志：/mnt/liansp3/logs/p0_role_blind_review_packet_20261025_01/smoke_001/。
- 私有Full失败日志：/mnt/liansp3/logs/p0_role_blind_review_packet_20261025_01/full_001.log。
- 机器可读失败记录：/mnt/liansp3/logs/p0_role_blind_review_packet_20261025_01/full_001_failure_summary.json。
- 盲审包：未生成。
- 公开匿名汇总：本目录的result_summary.json；不含问题、SQL、数据库名、逐题ID或逐例候选。
- 预注册协议与命令：../../plans/p0_role_blind_review_packet_20261025.md及本目录experiment_config.json。

下一步应先找回或重建历史P0的精确FK匹配/候选定义，并用独立预注册的只读schema审计验证。当前不启动Role准确率、监督训练、维度扫描或新的SQL实验；两位人工审阅者仍是Role Gate的必要条件。
