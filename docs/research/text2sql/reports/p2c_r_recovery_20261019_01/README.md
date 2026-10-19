# P2c-R 独立恢复实验

状态：Gate 0 通过后独立预注册，Smoke/Full 尚未运行。原 P2c 的两次 Full 失败及其停止结论保留；本记录遵循最新 P2c-R 指导，允许一次 Smoke 和一次 Full，工程失败不重跑。

唯一核心问题是检索向量保留 Values、最终 Schema Context 省略 Values，能否在保持 R0 排名时改善固定 token 预算覆盖。四臂、数据、缓存、tokenizer、指标、Bootstrap 10000 次及种子 20261020、H1/H2 成功门均沿用原预注册。H2 要求 V01−V00 Complete@1024 全体 1460 题至少 +5pp、固定 5 DB/706 题至少 +3pp、两组数据库簇 95% CI 下界都大于 0，且固定至少 3 库非负、2 库严格为正。

Gate 0 已完成真实 P2b 48 项指标、4 个分母回放及 JSON 写入/读取/SHA 校验；V01/V10 仅为历史行复制占位，没有新的交叉臂评分。93 项相关测试通过，独立代码审查的问题已修复。Gate 0 用时 12.381695 CPU 秒、12.647481 wall 秒，峰值 RSS 0.882500 GiB；模型/API/GPU/SQL 均为 0。见相邻工程报告和机器可读配置。

执行环境为现有 think2sql_20260909，Python 3.12.14、NumPy 2.2.6、Transformers 4.57.1、Tokenizers 0.22.1；Qwen3-Embedding-0.6B 仅使用本地 tokenizer 和既有 1024-D CPU 向量，不载权重、不推理。每次最多 8 CPU 线程、1800 process CPU 秒、16 GiB RSS。数据/模型入口沿用 /mnt/liansp3/sources/；不下载或安装依赖。

配置见 [experiment_config.json](experiment_config.json)；工程记录见 [Gate 0 报告](../p2c_r_contract_gate_20261019_01/README.md)；执行协议见 [P2c-R 指导](../../plans/p2c_r_replay_contract_recovery_20261018.md)。BIRD dev 仅为 exploratory 开发集；本实验不执行 SQL，不能将 Schema coverage 解释为 SQL EX。
