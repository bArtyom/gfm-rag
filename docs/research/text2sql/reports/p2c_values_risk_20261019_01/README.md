# P2c Values 词面信息暴露风险审计

状态：计分前登记，尚未运行。前提是 P2c-R H1/H2 已通过；本轮回答移除 Values 是否产生参考谓词常量不可见线索，不能评价SQL准确率或证明这些常量语义必需。

按 [协议](../../plans/p2c_values_risk_audit_20261019.md)冻结一次5题Smoke和一次全量扫描，使用同一P2c-R结果/原数据/1024预算，不重新评分或装包。匹配规则、排除项、1460题主分母、解析质量和人工复核边界都在运行前登记。

预算：每次300 process CPU秒、8线程、4GiB RSS；模型前向/GPU/API/SQL执行=0。复用现有环境与数据入口，不安装或下载依赖。代码 `scripts/text2sql/audit_p2c_values_risk.py`，配置见 [experiment_config.json](experiment_config.json)。
