# P2d：冻结本地7B的三臂SQL效用Pilot

状态：准备完成，模型生成与真实SQL EX尚未运行。原19题及11题严格匹配对照已冻结，8题无匹配不放宽条件；另有3题不计正式结果的私有Smoke。先3个合成Generator/SQLite检查，再9次私有Smoke生成，通过后正式30题×3臂一次生成。

语义审核status=unverified，人工审核0，语义必要性分母0；按上位协议允许的独立工程/SQL Pilot路径执行。配置见[experiment_config.json](experiment_config.json)，样本与权重SHA见[sample_registration.json](sample_registration.json)，执行协议见[登记](../../plans/p2d_sql_execution_20261022.md)。本轮不运行G0，不新增GPU/服务/付费API，不修改旧结果。
