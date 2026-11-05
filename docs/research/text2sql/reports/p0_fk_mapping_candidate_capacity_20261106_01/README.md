# P0 FK mapping 候选容量审计

**状态：完成；已解析子集通过结构容量必要门，完整总体计数含 13 个解析缺口。** 本轮只评估是否有足够的 BIRD dev 问题×表对供后续双人审阅；没有运行 G-reasoner、Dense 排序、SQL 生成或执行。

## 研究问题与预注册门

现有盲审包有 49 道问题、51 个问题×表对，其中只有 8 对含至少两个不同有效 FK mapping。冻结的映射排序 Pilot 在排除 5 个问题级 Smoke 后要求至少 30 个有 FK 候选的问题×表对、其中至少 20 个结构上可区分的多映射对，并覆盖至少 3 个数据库。本审计检查完整冻结 BIRD dev 候选池能否在不降低这些门槛的情况下支持一份全新的 pair-level 双人审阅包。

结构上“至少两个 mapping”只表示有可排序的候选，不表示哪一个 mapping 正确或可由人类裁定。最终可裁定分母仍需两名审阅者独立标注后按既有共识规则确定。

## 数据、代码与执行

- **工作仓库：** `https://github.com/bArtyom/gfm-rag`，分支 `research/gfm-schema-anchor-probe-20261106`。
- **方案：** [`容量审计计划`](../../plans/p0_fk_mapping_candidate_capacity_audit_20261106.md)。执行前读取项目 `README.md`、研究工作台 `README.md`、`experiment-roadmap.md`、`reproducibility-contract.md`、盲审报告和 Pilot 设计审计；研究仓库的资源、安全、隐私和归档规则均遵守。
- **执行代码：** [`audit_p0_fk_mapping_candidate_capacity.py`](../../../../../scripts/text2sql/audit_p0_fk_mapping_candidate_capacity.py)，代码提交 `de481ac62d1b278c9b21c5b2f805548a52c2bb59`，脚本 SHA-256 `273bcc382d4316e4d41d67cf68b0c6175fd337264fd65ea011bff1d0a7498bbb`。脚本复用既有冻结输入加载器、FK identity 规则和 SQLGlot 表对解析器，没有改动旧审阅包或解析器。
- **冻结输入：** BIRD dev `dev.json`、`dev_tables.json`，P1.5 有效 FK artifact，canonical P1.5 Full 与 question crosswalk。五个 SHA-256 均保存在随报告归档的匿名 `aggregate_summary.json` 中；运行器逐项匹配已登记哈希后才开始扫描。
- 参考 Gold SQL 只在内存中交给 SQLGlot 解析 `JOIN ON` 的端点表对；没有把 SQL 写到结果、日志、stdout 或公开仓库，也没有执行 SQL 或读取数据库业务行。
- **环境：** `think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0。资源检查时 `python3` 名称落到了系统 Python 3.9，因此实际使用环境内明确的 `python3.12`；模型、服务、依赖和配置没有改变。
- **硬件与资源：** CPU-only，最多 8 线程、300 CPU 秒、600 秒 wall、4 GiB RSS。启动前主机有 447 GiB 可用内存和 192 个 CPU 线程，磁盘可用 112 TiB；未占用 GPU。Full 实际 wall 0.848946 秒、CPU 0.844948 秒、峰值 RSS 0.032227 GiB，均低于预算。
- **运行 ID：** `p0_fk_mapping_candidate_capacity_20261106_01`。运行命令：

  ```bash
  conda run -n think2sql_20260909 python3.12 \
    scripts/text2sql/audit_p0_fk_mapping_candidate_capacity.py \
    --run-id p0_fk_mapping_candidate_capacity_20261106_01 \
    --expected-commit de481ac62d1b278c9b21c5b2f805548a52c2bb59 \
    --repo-root <该分支工作树> \
    --dev-json /mnt/liansp3/sources/datasets/bird/dev/dev.json \
    --tables-json /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
    --fk-artifact /mnt/liansp3/sources/results/gfmrag_p1_5_diagnosis_20261016/full_03/fk_gate_private.json \
    --crosswalk-private /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/crosswalk/crosswalk_private.json \
    --canonical-full /mnt/liansp3/sources/results/gfmrag_p0_fk_canonical_crosswalk_20261105_01/full/p0fk_canonical_p15_full_py312_sqlg28_20261105_01.json \
    --output-dir /mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_candidate_capacity_20261106_01
  ```

## 结果

冻结输入中有 1,140 个 `JOIN ON` 问题。1,127 个问题可以由既有解析器提取表对；13 个问题因 `JOIN_PAIR_EXTRACTION_INCOMPLETE` 未能提取。对成功解析的部分共得到 1,391 个问题×表对：

| 匿名聚合指标 | 数量 |
|---|---:|
| 有至少一个有效 FK mapping 的问题×表对 | 1,208 |
| 有至少两个不同有效 FK mapping 的问题×表对 | 176 |
| 含多映射候选的数据库数 | 4 |
| 含 FK 候选的问题数 | 989 |
| 含多映射候选的问题数 | 175 |

容量必要门为 30 个 FK-bearing 对、20 个多映射对、3 个数据库。即使从已解析集合中排除对容量影响最大的 5 个问题，已观察到的保守剩余下界仍是 **1,189 个 FK-bearing 对、170 个多映射对、4 个数据库**。因此，已解析子集本身足以支持准备一份新的 pair-level 盲审包，且余量很大。

13 个未解析问题没有被当作零容量纳入结果；它们使完整 BIRD 候选池的精确总数和精确 Smoke 范围仍不完整。这个缺口不抹去已解析子集已经超过必要门的事实。后续 packet 只能从身份完整、可稳定映射的已解析候选中抽样，不能把 13 个未解析案例当成已标注或可排序样本。

候选映射数直方图也只作匿名容量统计：0 个映射 183 对、1 个映射 1,032 对、2 个映射 141 对、3 个映射 28 对、22 个映射 7 对。没有写出具体问题、数据库、表、列或映射身份。

## 偏离、异常与隐私

- 没有改变固定输入、FK identity、参考 SQL 表对提取规则、容量阈值或旧审阅材料。
- `JOIN_PAIR_EXTRACTION_INCOMPLETE` 的 13 个异常仅按原因码计数；没有把 SQL 或异常文本写入日志。它们不在容量计数中。
- 没有读取 A/B 审阅回复文件或旧 packet 内容，没有生成新的审阅材料，没有读取业务表行，也没有执行 SQLite 查询。
- 输出只包含匿名聚合、已登记输入哈希、代码版本、资源用量和隐私标记；逐题键、SQL、数据库/表列名、mapping ID、审阅材料和回复均未写入或上传。
- 本轮 GPU、模型和 API 调用均为 0；已确认模型 token 为 0/0/0，外部 API 费用 CNY 0.00。CPU 时间未折算货币。

## 结论与下一步

**保留同一个核心假设，不新增模型假设。** 容量审计说明现有盲审包抽样不适合映射排序 Pilot，但完整、可解析的冻结候选子集有足够结构容量。下一步是单独登记一版新的 pair-level 双人盲审材料方案，使用新 seed、新 run ID 和新本地目录；旧 49 题材料及 A/B 回复原样保留，不替换、不合并，也不联系审阅者。

人类标签仍为 0。新材料即使准备成功，也不能直接启动模型 Pilot。只有两位真实审阅者在同一候选集合上给出符合共识规则的决定、映射集合与置信度，并且排除 5 题 Smoke 后达到 30 个可裁定对、其中 20 个结构可区分对、至少 3 个数据库，才可另行正式注册 G-reasoner 与 Dense 的 Accepted@1 Pilot。

## 归档

- 匿名聚合：[aggregate_summary.json](aggregate_summary.json)，SHA-256 `93eecfef431796ad20d623da3f0b0cb86e9a389a100ae2eab57ba566a7ffaad1`。
- 私有运行记录入口：`/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_candidate_capacity_20261106_01/`；权限为目录 `0700`、文件 `0600`。
- 公开归档只包含 runner、方案、本文和匿名聚合；不包含原始数据、Gold SQL、问题 ID、逐题结果、审阅回复或本地日志。
