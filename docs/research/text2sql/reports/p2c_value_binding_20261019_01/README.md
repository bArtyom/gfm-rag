# P2c-R Values：直接列值绑定审计

状态：计分前登记，尚未运行。只核验已冻结19题/21个输入不可见常量的直接源列绑定，unknown不计负例，不评价语义必要性或SQL EX。

一次前5题Smoke通过后，一次19题Full，无重试；各阶段CPU300秒/8线程/4GiB RSS，API/模型/GPU/SQL执行均0。规则见[协议](../../plans/p2c_value_binding_20261019.md)，配置见[experiment_config.json](experiment_config.json)。原人工模板和历史结果保持不变。
