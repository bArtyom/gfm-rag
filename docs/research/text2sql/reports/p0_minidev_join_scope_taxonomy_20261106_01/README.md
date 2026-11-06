# P0 Mini-Dev JOIN 作用域与直接投影覆盖诊断

**状态：`EXPLORATORY_COMPLETE; 95% COVERAGE GATE FAILED; STOP`**。本实验只诊断 SQL 解析器对 JOIN 列等式的覆盖，不比较检索排序器，也不产生 FK Role 人工标签。

## 问题与冻结假设

前一轮对固定的 500 条 BIRD Mini-Dev reviewed SQL 解析出 663 个两端都有限定列名的 `JOIN ON` 等式；旧解析器将 523 个映射到官方 DDL 列（78.88%），另有 140 个未解析。其 95% 标签覆盖门要求至少 630/663 个可解析等式。

本次检验：**至少 107/140 个未解析等式能否沿唯一的 CTE 或派生表直接列投影，回溯到官方 SQLite DDL 中的物理表列？** 成功判据为 ≥630/663；任一回归、作用域错误、分类不守恒或样本覆盖异常均停止。预算为 5 题 Smoke + 不重叠的 495 题 Full、一个固定逻辑夹具组，不做参数扫描或自动追加实验。

## 参考仓库、指南与版本

- 项目及报告仓库：[`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag)，分支 `research/minidev-sql-fk-use-rank-20261106`。
- 论文代码参考：[`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag)，冻结 commit `b3e43219c49929da505244df4f0ba54c0947e4c4`。本实验没有修改或向第三方上游写入任何内容。
- 本项目预注册：`835884078aef25bdec0cc30220857679ba493c47`；初版 runner：`cb0ea76dbefbe8d2c76d120361190b5e86c674a0`；哈希更正方案与配置：`e6a86ee5ccb4dfe06dcb8b83c7118c0af164b8e7`；最终执行 runner：`36deb5c0f520d0db88833d0eed53a9a9ecfa3718`。
- 已按项目流程阅读仓库根 README、`docs/research/text2sql/README.md`、`experiment-roadmap.md`、`reproducibility-contract.md` 及 `/mnt/liansp3/sources.md`。实验遵守其中的匿名公开、冻结配置、Smoke/Full 隔离及停止门。报告和聚合是本轮新产物；原预注册、原始配置、失败 Smoke 日志均未覆盖。
- 代码：[`diagnose_minidev_join_scope_taxonomy.py`](https://github.com/bArtyom/gfm-rag/blob/36deb5c0f520d0db88833d0eed53a9a9ecfa3718/scripts/text2sql/diagnose_minidev_join_scope_taxonomy.py)。配置：`configs/text2sql/p0_minidev_join_scope_taxonomy_20261106_amendment1.json`，SHA-256 `cfe1087513687490e6e2e3ff9f377cb597a15dc0b283c1ff55405c18afbc8516`。

## 方法：旧解析器与本次改动

旧实现对 JOIN 两端列引用使用当前 SQL 作用域里的 alias 和物理 schema 列名直接匹配。若 JOIN 写的是 CTE/派生表输出别名，旧逻辑无法把输出列继续追溯到源表列，因此会记为 unresolved。

本次保留旧逻辑作为逐项 baseline，并在独立审计脚本中增加 `trace_direct_column`：

1. 通过 SQLGlot scope 找到当前 alias 的唯一来源。
2. 若来源是物理表，只接受官方 DDL 中存在的表和列。
3. 若来源是 CTE/派生 SELECT，只接受列名唯一、表达式本身为直接列引用的投影；然后递归向内追踪，直到物理表列。
4. 拒绝表达式/函数推断、`UNION`、星号展开、重复或歧义 alias、未限定中间列、缺失输出列、模糊列名匹配及模型判断。
5. 对旧解析器未解决项使用互斥主类别计数，并另记 operand 原因；旧解析器已解决而新逻辑失败则计作回归并触发停止。

7 个固定夹具覆盖直接 CTE、直接派生表、嵌套直接投影的恢复，以及表达式、缺失输出、物理列缺失、重复 alias 的拒绝。7/7 通过。该追踪只确认 AST 列引用能够映射至 DDL 列，不证明 SQL 的连接语义正确，也不判断某条 FK 是否为唯一正确答案。

## 数据、环境与执行

- 数据：BIRD Mini-Dev 2026 reviewed，固定 revision `38818fcbc46038129592680c51b2c8b597aac27c`，500 条；JSONL SHA-256 `926af2a0d1b47e5d0d15a7aa8a34d4721007f4550a881555b6a89496b54a2606`。
- 官方 SQLite DDL SHA-256：`5176e324a72e80a8a37a12285596d123e0ba6c310dceaa9f13a1e413ee88ff5b`。两项数据均从 `/mnt/liansp3/sources/` 统一入口读取；未复制或改动源文件。
- Smoke/Full 按升序 `SHA256(experiment_id + db_id + question_id)` 确定，分别为 5 与 495 条，不重叠；随机种子不适用。
- 环境：`think2sql_20260909`，Python 3.12.14、SQLGlot 28.0.0、SQLite 3.53.2；未安装或升级依赖。CPU-only，无模型加载、外部 API 请求或 GPU 计算。
- 运行前资源：4 张 RTX 4090 均空闲；192 个逻辑 CPU；449 GiB 可用 RAM；112 TiB 可用磁盘。Swap 当时 2 GiB 已用；本轮进程峰值 RSS 仅 34.5 MiB。
- Smoke Run ID：`p0_minidev_join_scope_taxonomy_20261106_01_cpu_smoke_002`；5 条、0.054 秒 wall、7/7 夹具通过、0 作用域错误、0 回归。Smoke 有 6 个限定等式（5 resolved、1 unresolved、0 rescue）。
- Full Run ID：`p0_minidev_join_scope_taxonomy_20261106_01_cpu_full_001`；495 条、1.526 秒 wall、1.509 秒进程 CPU、峰值 RSS 34.5 MiB。Full 单独有 657 个等式（518 resolved、139 unresolved），新逻辑 rescue 46，0 回归、0 作用域错误。

### 唯一工程恢复记录

`smoke_001` 使用的首版配置把 schema SHA-256 中两个字符转置了。运行在输入哈希校验处停止，未读取 JSONL、未解析 SQL，且没有创建结果目录。独立复核确认数据文件未变。原始计划、配置和失败日志均保留；更正写入单独的 Amendment 1 计划/配置，成功重试使用新 ID `smoke_002`。本次没有改变样本、指标、resolver 规则或 95% 成功门。失败日志仅保存在本机，不公开上传。

## 结果

Smoke 与 Full 合并后覆盖全部 500 条，结果与冻结 baseline 精确一致：

| 指标 | 结果 | 预注册门槛 | 判断 |
| --- | ---: | ---: | --- |
| SQL 解析成功 | 500/500（100%） | 500 条全覆盖 | 通过 |
| 限定 `JOIN ON` 等式 | 663 | 固定分母 | 一致 |
| 旧逻辑已解析 | 523/663（78.88%） | 与冻结 baseline 一致 | 通过 |
| 旧逻辑未解析 | 140/663 | — | 分类分母 |
| 唯一直接投影新增恢复 | 46/140（32.86%） | 至少 107 | **失败** |
| 新逻辑回归 | 0 | 0 | 通过 |
| SQL scope 错误 | 0 | 0 | 通过 |
| 新逻辑总解析 | 569/663（85.82%） | 至少 630/663（95%） | **失败，少 61 项** |

140 个旧 unresolved 等式的互斥分类：46 个可由唯一直接投影恢复；74 个属于 alias 未找到或相关引用；19 个涉及表达式或 `UNION`；1 个派生输出列缺失。四类合计 140。当前规则没有尝试修补剩余 94 个 unresolved 项。

匿名数据库级等式统计如下。`resolved after` 是旧逻辑已解析数加本次新增恢复数；这些是固定数据集上的分层计数，不是独立外部验证集。

| 匿名库 | 等式数 | 旧解析数 | 新增恢复 | 新解析率 |
| --- | ---: | ---: | ---: | ---: |
| db_01 | 85 | 81 | 2 | 97.65% |
| db_02 | 123 | 75 | 31 | 86.18% |
| db_03 | 60 | 58 | 0 | 96.67% |
| db_04 | 44 | 22 | 2 | 54.55% |
| db_05 | 24 | 17 | 1 | 75.00% |
| db_06 | 101 | 87 | 5 | 91.09% |
| db_07 | 59 | 51 | 1 | 88.14% |
| db_08 | 58 | 45 | 2 | 81.03% |
| db_09 | 44 | 39 | 0 | 88.64% |
| db_10 | 55 | 42 | 2 | 80.00% |
| db_11 | 10 | 6 | 0 | 60.00% |
| **总计** | **663** | **523** | **46** | **85.82%** |

匿名机器可读聚合见 [`aggregate_summary.json`](aggregate_summary.json)。它不包含原题、Gold SQL、question ID、数据库/表/列名或逐题预测。问题级摘要、日志和资源快照留在本地受控目录。

## 复现命令

工作目录为仓库根目录；代码版本为 commit `36deb5c0f520d0db88833d0eed53a9a9ecfa3718`：

```bash
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
scripts/text2sql/diagnose_minidev_join_scope_taxonomy.py \
--config configs/text2sql/p0_minidev_join_scope_taxonomy_20261106_amendment1.json \
--mode smoke --attempt 2 \
--expected-commit 36deb5c0f520d0db88833d0eed53a9a9ecfa3718 \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/smoke_002
```

```bash
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 \
conda run --no-capture-output -n think2sql_20260909 \
/root/miniconda3/envs/think2sql_20260909/bin/python3.12 \
scripts/text2sql/diagnose_minidev_join_scope_taxonomy.py \
--config configs/text2sql/p0_minidev_join_scope_taxonomy_20261106_amendment1.json \
--mode full --attempt 1 --smoke-attempt 2 \
--expected-commit 36deb5c0f520d0db88833d0eed53a9a9ecfa3718 \
--smoke-private /mnt/liansp3/sources/results/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/smoke_002/private_summary.json \
--output-dir /mnt/liansp3/sources/results/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/full_001
```

本地结果：`/mnt/liansp3/sources/results/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/{smoke_002,full_001}/`；专属日志和资源记录：`/mnt/liansp3/logs/gfmrag_p0_minidev_join_scope_taxonomy_20261106_01/`。失败的 `smoke_001.log` 也在该日志目录中，没有上传。

## 结论、停止决定与边界

唯一直接列投影追踪确实修复了 46 个解析缺口，但只到 85.82%，未达到 95% 标签覆盖门。故核心假设被该预注册判据否定；**本次诊断停止，不启动 G-reasoner、Dense、BM25、模型审阅或新的 SQL 生成/执行实验。** 这不改变此前 G-reasoner 模型代理排序 NO-GO，也不把模型多数改称人工标签。新逻辑没有训练模型、构造 FK Role 标签或执行生成 SQL。

本报告仅说明在固定 Mini-Dev SQL 与 DDL 上的句法列追踪覆盖。它不证明 SQL 执行正确、join 语义正确、FK mapping 排序效果、Text-to-SQL 准确率或跨库泛化。数据覆盖是固定 500 条全量；没有对更广总体作抽样推断，因此不报告置信区间。

本轮无模型/API 请求：确认 token 输入/输出/总量为 `0/0/0`，未知用量请求数 0，模型/API 估算费用 `0 CNY`，供应商实扣不适用；CPU 时间另行记录如上。
