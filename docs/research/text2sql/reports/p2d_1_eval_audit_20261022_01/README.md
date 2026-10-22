# P2d.1 冻结预测评测覆盖审计与失败归因

> **预注册状态：NOT RUN。** 基于项目 `main` 最新指导 [`854cfea`](https://github.com/bArtyom/gfm-rag/commit/854cfea553359f20ceaa597ed57f096a82d20bbf)，执行协议 [P2d.1](../../plans/p2d_1_frozen_prediction_eval_audit_20261022.md) SHA256 `9e5b0b8c01a39b2b77afc8596ec7e25fed234e2e`。此登记在Gate 1/2观察前建立。

## 问题与边界

核心假设：对 SQLite 时间函数增加运行时实参审查，可以安全接纳某些静态日期列表达式，同时拒绝可能依赖真实时钟/时区的取值；对于旧评测器已经执行的参考SQL和预测SQL，v2保留同样的投影、Set/Bag结果。通过后才在旧P2d封存的30题90条SQL上产生独立补充评分。

本轮属于 `exploratory_evaluator_coverage_and_failure_audit`，不是生成方法或新模型效果检验；模型forward、API/GPU调用预算均为0。数据集固定为P2d原BIRD dev 30题、5个匿名DB、19优先/11严格对照、8个无匹配优先题；只读既有封存输入。不得改写原P2d报告的8/7/8、11/12/10。

## 成功与停止判据

- Gate 0：验证P2d原30样本/90预测、预测封存SHA `f6ae031ec83e12da36bb27f55f1f8461298b340ef251a51cb1d280a43f2ddde3`、Full汇总SHA `091b3b68b2a24a693c8e12a2783d9630d6f467c521616a0b366bc81c41fea1f2`、原始数据库SHA、旧评分/配对均可复算；新源码工作树clean；确认未产生网络模型请求。
- Gate 1：先用合成DB与fixture测试安全时间函数包装；拒绝now、localtime/utc、subsec、运行时危险字符串、嵌套传播、view/trigger/UDF、非SELECT、PRAGMA、ATTACH和写语句。旧可执行的26条参考SQL及57条原可执行预测必须保持相同输出列和行多重集哈希，Set/Bag比较一致。任何安全失败或无法解释的差异即停止在Gate 1，不做全样本v2评分。
- Gate 2仅在Gate 1通过时运行一次：读取封存SQL，对30个参考及90个预测复评，形成互斥可评漏斗、失败根因与匿名聚合；报告v1/v2配对，不挑可评题作为新分母。旧结果、源数据及hash运行后不变。
- 预算：新LLM/API调用0、GPU秒0、付费API调用0；CPU线程≤8、RSS≤4GiB、process CPU≤600秒；SQLite单SQL10秒、50000行、64MiB返回、256MiB SQLite heap。超预算/DB SHA漂移/预测seal不匹配立即停止并保存现场。Gate S人工审核仅当确有两名独立审核者时做；当前没有审核资源登记，状态UNVERIFIED，不调用LLM冒充人工Gold。

比较的运行时行为必须拒绝获取wall clock或时区的全部路径；不能通过放宽过滤规则增加准确数。当前v1仍是唯一已报告主Pilot口径。v2结果永远单独列为补充评测。

## 依赖、来源与成本

- 固定来源repo `bArtyom/gfm-rag` main初始commit `854cfea553359f20ceaa597ed57f096a82d20bbf`，上位复核commit `a97496a`，P2d.1协议SHA如上。实现代码/测试必须先在GitHub可读后再打开真实SQL/DB输入。
- 环境复用 `think2sql_20260909`；CPU-only、≤8线程。SQLite行为核对采用[SQLite官方日期/时间函数文档](https://www.sqlite.org/lang_datefunc.html)及[确定性函数说明](https://www.sqlite.org/deterministic.html)。若无安全、许可兼容的独立BIRD evaluator可用，明示没有独立评测器交叉验证。
- 新结果根路径 `/mnt/liansp3/sources/results/gfmrag_p2d_1_eval_audit_20261022_01`，对应独立目录 `/mnt/liansp3/研究工作区/03_实验中/gfm-rag-bartyom-local-results/p2d_1_eval_audit_20261022_01`；不得使用P2d旧目录。日志 `/mnt/liansp3/logs/gfmrag_p2d_1_20261022_01/`。私有逐题/SQL/DB/错误文本不上传GitHub。
- 本轮模型token与API费用预注册为0；本地CPU/GPU费用采用账本规则，CPU运行货币成本未定价。无新模型价格来源需求。真实CPU时间/峰值RSS结果运行后填写。

## 结果

尚未运行。Gate 0/1/2逐阶段回执、匿名聚合、失败根因、source/data hash与最终Go/No-go待本轮完成后追加；预注册文件本身保留为审计证据。
