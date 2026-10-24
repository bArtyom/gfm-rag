# BIRD-dev 双人盲审候选包准备协议

> **状态：已预注册，尚未运行。实验 ID：p0_role_blind_review_packet_20261025_01。** 这是CPU-only的人工审阅材料准备工作，不是模型实验，不产出角色标签。P0 Role Gate仍为NO-GO。

## 问题、假设与结论边界

**问题：** 能否从已冻结的174条BIRD-dev多FK候选中，按映射级身份策略构造20条可由两位审阅者独立、盲态判断的本地材料，并确认材料没有Gold SQL、模型输出或公开数据泄漏？

**假设：** 固定BIRD-dev输入、唯一FK映射身份和确定性分层抽样，可以得到可复现的20条审阅包；两份包仅在样本顺序和候选显示顺序上分别随机化。

**可推翻结果：** 输入hash、SQLGlot解析/历史计数、映射身份、样本选择或泄漏检查任一不符合冻结条件时停止，不生成正式审阅包。历史候选总数无法精确复现时不改筛选规则追数。

本工作只准备评审材料。即使包生成成功，也不代表有人已审阅、没有Role Gold、不能启动角色准确率、query-conditioned Role监督或真实SQL实验。完成标签必须由两位独立的人类审阅者产生。

## 输入、映射身份与抽样

- 数据：只读 /mnt/liansp3/sources/datasets/bird/dev/dev.json 和 dev_tables.json；固定SHA-256分别为630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06和35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97。**不读取SQLite业务表行，不执行SQL。**
- 使用已有 t2sql_code_audit_20261005 环境（Python 3.10.22、SQLGlot 26.33.0）作SQLite方言解析；不安装或升级依赖。执行器需重算历史汇总门：1,534题解析成功、1,140题带JOIN ON、956题至少匹配一个schema JSON FK映射、174题至少有一个同表对包含两个或更多不同FK映射。任一计数不符即停止。
- dev_tables.json 的FK关系按唯一有序映射 (db_id, source_table, ordered source columns, target_table, ordered target columns) 归一。完全相同映射折叠成一个候选；声明重复数仅作本地元数据，不增加候选或图边。此策略依据重复身份探索报告的映射级候选建议；原SQLite Instance Gate仍为NO-GO。
- 候选全集锁定为通过上列历史计数门的174个query。按数据库分层循环抽取20个不同query；每个数据库内使用固定seed 20261024 对 (db_id, question_id) 的SHA-256排序，数据库轮转顺序按db_id排序。若合格候选不足20则停止并报告实际数，不放宽定义。
- 为每条case生成私有伪名ID；不在公开材料中写query ID、数据库名、问题、SQL或逐例标签。两份盲审包包含相同20条case，但case顺序分别用A/B固定seed打乱；每组FK候选的显示顺序也分别打乱，映射ID保持可选但无业务含义。

## 审阅表单与标注规则

每条case只呈现自然语言问题、相关表名、各个唯一FK映射的有序列对及匿名映射ID。隐藏Gold SQL、Gold join条件、模型输出/排名和数据库ID。两位审阅者不得相互讨论后再提交。

每个同表对独立选择以下一种状态：

- single_mapping：选择一个映射ID；
- multiple_mappings：选择所有可接受的映射ID；
- cannot_determine：问题文字不足以唯一或多金标判定；
- no_declared_fk：所需连接不在列出的声明FK中；
- other：并说明理由。

同时记录置信度（1低、2中、3高）和固定理由类别（问题明确、上下文支持、指代/角色歧义、schema冲突、其他）。只在两人选择完全一致的映射集合或状态，且两人置信度均不低于2时，标为候选可信共识；任何冲突、弃答或低置信度均保留为未决，不由模型自动裁决。该规则只定义审阅后如何整理，不改变当前零标签状态。

## 成功门、预算与停止条件

**材料准备成功门：** 两个输入hash完全匹配；四项历史计数精确匹配；抽出20个不同case；两份包各含全部case、问题及候选映射；不含Gold SQL、答案、预测或模型排名；所有私有包可以逐文件hash复核。

预算上限：CPU 600秒、峰值RSS 4 GiB、GPU 0、外部/本地模型调用0、SQL执行0、训练/下载/安装0。只读两份数据JSON；不读取dev.sql、SQLite或其他未登记文件。执行命令使用 /root/miniconda3/envs/t2sql_code_audit_20261005/bin/python，工作目录为项目根目录。

Smoke仅处理最多5条样本并检查字段、ID、两份随机顺序和无Gold字段契约；Smoke通过后方可扫描全部1,534条。出现hash漂移、解析计数不符、FK候选数不符、少于20条可用样本、越预算、输出覆盖风险或任何Gold泄漏时停止并保留失败现场。

## 产物、复现和隐私

- 运行器：scripts/text2sql/prepare_p0_role_review_packet.py。
- Smoke结果及调试日志：/mnt/liansp3/logs/p0_role_blind_review_packet_20261025_01/。
- 私有Full产物：/mnt/liansp3/sources/results/gfmrag_p0_role_blind_review_packet_20261025_01/；包含两份reviewer packet、空白response表、本地manifest及SHA-256。目录不进入Git。
- 公开归档：docs/research/text2sql/reports/p0_role_blind_review_packet_20261025_01/；只记录聚合计数、输入/代码hash、环境、资源与隐私检查，不记录样本文本、ID、SQL、逐例映射或标签。
- sources.md只记录私有材料路径、数据版本、状态和公开报告链接。
- 运行前必须把本协议、配置、执行器、报告占位文件及研究索引改动提交到 bArtyom/gfm-rag。包生成后再追加独立结果报告提交。不得向第三方上游或历史bArtyom/quadrag提交。

## 指南与停止后的下一步

执行基点为 bArtyom/gfm-rag@9d2c23483506f40f62aee91bd276f0368170cc9f。已阅读根README.md、docs/research/text2sql/README.md、experiment-roadmap.md、reproducibility-contract.md及最新P0报告。与指南冲突处没有；本轮把P0报告要求的“双人盲审”落实为受控本地材料准备。

本运行结束后停止，等待两位真实审阅者独立提交表单。之后的标签整理、共识率/分歧报告及是否解锁新实验必须另行登记。BIRD-dev仍为开发集，不作独立测试集。
