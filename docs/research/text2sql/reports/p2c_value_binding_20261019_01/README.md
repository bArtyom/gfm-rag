# P2c-R Values：冻结19题的直接列值绑定审计

**一次5题Smoke和一次19题Full完成，无失败/重试。19题中9题存在与被移除Values匹配列相同的直接谓词绑定、8题直接绑定不一致、2题保留unknown；21个Literal标记分别为10/9/2。** 这将上一轮词面线索细化为源列关联证据，不证明语义必要性或SQL损害。

## 问题、依据与实验边界

项目仓库为[自有bArtyom/gfm-rag](https://github.com/bArtyom/gfm-rag)，指导基点main `99e4db00837d420cba18de76175f18f910a903bf`。用户再次请求继续实验后，按上一轮“先核对Literal与SQL列绑定”的未决项独立登记[协议](../../plans/p2c_value_binding_20261019.md)。旧词面审计的扫描额度已结束，本轮没有扩展到其余题目或修改匹配规则。

核心假设沿用双视图：保留检索端Values、缩短返回Context；本轮只核验其信息保留叙事的一个风险条件，不提出新方法。层级为exploratory误差分析，不作为主效能、独立数据库复现或SQL EX证据。

运行前阅读根README、研究README、experiment-roadmap、reproducibility-contract、P2c-R成功分支及上一轮报告；远端没有新增指导提交。上游代码来源RManLuo/gfm-rag，项目许可证Apache-2.0。增量代码只新增`predicate_value_binding.py`、`run_p2c_value_binding.py`及合成测试，没有修改旧执行器、历史结果、数据或人工模板。复用原有实现与缓存，不重建环境。

工程成功要求SHA、案例身份、旧词面标记重放、类别分区与聚合写盘一致；unknown保留完整分母。存在supported只决定优先审查价值，不能解释为方法通过语义安全门。预算固定为1次前5题Smoke+1次19题Full，0重试；每阶段CPU≤300 process秒、8线程、RSS≤4GiB；GPU/模型/API/SQL执行/下载/安装均0。输入/实现/资源失败即停止；完成一次Full也停止，不根据观察结果补充解析规则。

## 数据与实现

只使用[上一轮词面审计](../p2c_values_risk_20261019_01/README.md)冻结的19题、21个问题与evidence均未出现的常量标记，原顺序不变，来自5个数据库。它们是经过筛选的局部集合，**9/19不能当作1460题的总体风险率**。原BIRD dev1534题/11库、Column分母1460、固定706及P2c-R覆盖成绩均不重新评测。

使用参考SQL、完整`dev_tables.json`、已冻结R0/R1节点和P2c-R V00/V01@1024选择，仅在事后分析模块读取Gold。重放所选题旧词面标记必须逐字段相同；不重新编码、打分或装包。query/schema、P2c-R两份产物、旧词面两份产物、19条空白模板共7项SHA，以及P2b/cache/manifest均见[配置](experiment_config.json)和[回执](run_receipt.json)。源数据和模型版本仍为P2c-R冻结manifest；只加载既有tokenizer验证文本，不加载模型权重。

SqlGlot28.0.0按SQLite解析、依完整Schema限定列名。合格Literal提取保持旧规则：直接数据谓词，排除函数参数/模式通配符/常量对常量/分页值；保持原规范化和符号。限定前给原Literal打元数据标签，限定后只处理标签保留且hash未变的原出现，不把别名展开生成的常量当新证据。

二元比较、IN列表、BETWEEN界限关联对应的直接Column；表别名、唯一可限定列、合法相关外层引用、唯一直接列投影的CTE/子查询可追溯到基表节点ID。函数/算术/聚合等变换、UNION、歧义/缺失/递归来源均unknown，不求值或推断业务编码。解析当前FROM/JOIN只用`selected_sources`，避免未使用的同名CTE干扰相关外层别名。

每个Literal收集其所有原出现的已知源列及未知原因：与旧Values匹配列有交集→supported；无交集且所有出现均解析→mismatch；其余unknown。若supported同时含其他未知出现另列，本轮该数为0。题级采用“有supported优先，其次unknown，其余mismatch”的互斥分组。

## 结果与解释

| 分类 | 题数（分母19） | Literal标记数（分母21） | 含义 |
|---|---:|---:|---|
| binding_supported | 9 | 10 | 至少一个常量与被移除Values的同一源列有直接谓词关联 |
| binding_mismatch | 8 | 9 | 直接约束的是其他源列；不能排除间接说明用途 |
| binding_unresolved | 2 | 2 | 变换型/未支持谓词目标，保持未知 |

19条SQL均解析并通过名称限定；2个unknown属于预登记的不支持目标类别，不是SQL解析失败或工程错误。supported的10个标记没有同时含其他未知出现；其余不确定性仍包括业务编码、映射是否必要、函数/SQL等价语义、描述可替代性等。

| 匿名库 | 题数 | supported题 | mismatch题 | unknown题 |
|---|---:|---:|---:|---:|
| db_01 | 8 | 4 | 4 | 0 |
| db_06 | 2 | 2 | 0 | 0 |
| db_02 | 3 | 1 | 1 | 1 |
| db_05 | 1 | 0 | 0 | 1 |
| db_10 | 5 | 2 | 3 | 0 |

| 原P2c-R覆盖分层 | 题数 | supported题 | mismatch题 | unknown题 |
|---|---:|---:|---:|---:|
| rescued | 6 | 3 | 3 | 0 |
| unchanged | 13 | 6 | 5 | 2 |

supported涉及4库。覆盖被救回的6个优先案例中，3题有同一源列绑定；这说明覆盖改善与值文本移除可以共现，不能据此推断SQL损害。此前“10题同一标记命中Gold Schema列”是更弱的Schema成员关系，本轮“9题/10标记源列直接绑定”是不同判断，不能混用题级与标记级分母或改写旧统计。

## 运行、环境与验证

执行源main `0f0bf08a611600423948f416542db26952bea934`，Smoke/Full同提交、10份项目源码SHA、输入、依赖版本和抽查的`qualify.py`/`scope.py`哈希一致。只对这两个SqlGlot源文件做额外hash检查；没有声称冻结整个依赖源码闭包。环境think2sql_20260909，Python3.12.14、NumPy2.2.6、Transformers4.57.1、Tokenizers0.22.1、SqlGlot28.0.0。无随机抽样/训练/解码，seed不适用。

主机192CPU线程、503GiB RAM，启动前445–446GiB可用内存、约115TiB可用磁盘；4张RTX4090忙碌，未分配GPU。未发现本容器内已有模型推理监听；本任务不需要模型，未恢复服务或回退付费API。所有数据、模型、结果统一入口均用既有软链接，未改目标。

| 阶段 | 题数 | Literal标记 | CPU秒 | Wall秒 | 峰值RSS GiB |
|---|---:|---:|---:|---:|---:|
| Smoke | 5 | 5 | 10.991322 | 11.302871 | 0.864391 |
| Full | 19 | 21 | 11.031841 | 11.336785 | 0.861462 |

合计CPU22.023163秒、Wall22.639656秒。Smoke不是独立验证集合，也没有额外扩大候选集合。准确启动命令、禁用GPU/8线程变量、源码和输入SHA均见[Full回执](run_receipt.json)、[Smoke回执](smoke_receipt.json)。进程UTC时间保留原始记录；北京时间为UTC+8。

预运行124项定向测试通过。静态复核发现同名未使用CTE可能误遮蔽外层别名，先用合成反例复现错误，再修复到`selected_sources`和合法相关作用域；修复发生在读取真实19题之前，正式运行中没有修补或重试。两个运行均无失败，2个unknown按预注册保留，不再追加解析规则。

[产物验证](verification_summary.json)独立重计19条trace、21个标记的三类分区及匿名库/覆盖分层，重核原案例与Literal集合、匹配节点、交集、原有产物与项目源码hash，全部一致。公开隐私扫描通过。[验证器](verify_artifacts.py)验证持久化类别与契约，未独立证明业务语义或完整lineage正确性。

Full聚合SHA=`5b5c7ad4dd20dee4645c6febcf9ecb215e08822de1d97cd202b4cd6ea73d3bb2`；私有traceSHA=`9af35480aa5804edba6ea8d772431fc90af96aa91e9771e479ad18f2ec5ffae1`。本地Full目录`/mnt/liansp3/sources/results/gfmrag_p2c_value_binding_20261019/full_19q_20261019_01`、Smoke目录`/mnt/liansp3/sources/results/gfmrag_p2c_value_binding_20261019/smoke_5q_20261019_01`，原始日志`/mnt/liansp3/logs/gfmrag_p2c_value_binding_full19_20261019_01.log`。新私有`binding_review_queue_private.json`含19条机器分类和空白人工字段；旧19条人工模板的SHA保持不变。公开[匿名聚合](aggregate_summary.json)、配置、协议、回执和验证器，不公开SQL、Literal原文、数据库名、逐题/节点ID、trace或日志。

## 外循环结论与停止

**保留P2c-R的离线覆盖成功，将9题/10个同源列标记列为更具体的Values信息风险候选，保留2题unknown；结束本轮扫描。** 8题mismatch只削弱“直接约束同一列”的解释，不能宣称不存在间接用途。没有扩展到407题或其余预算，没有新模型、提示词、Values拼接、GPU或SQL生成任务。

这两轮诊断将研究叙事从“覆盖提高”细化到“存在值文本变化、部分与SQL源列直接关联”。它们仍没有证明哪些说明不可缺少。人工语义复核=0、语义必要性分母=0，模型语义审阅也未运行；不把静态绑定代替这些证据。下一关键问题应是固定Generator/Selector下是否改变谓词值生成与SQL EX，并采用预先定义的数据库级独立验证；在该契约和语义证据完成前，V01只保留离线候选，不全局删除Values。

本轮输入/输出/总token=0/0/0，未知请求0，API费用CNY0.00，模型/GPU/SQL执行均0；CPU资源有成本但未定价。[共享账本快照](api_usage_snapshot.json)的跨项目累计已确认输入4,762,889/输出217,761/总4,980,650token，未知请求14；已定价部分按公开价估算CNY17.4014610，另42个已知用量请求缺价待核实，实际扣费未核验。其他项目并行调用不归到本实验；账本仅覆盖已登记调用。
