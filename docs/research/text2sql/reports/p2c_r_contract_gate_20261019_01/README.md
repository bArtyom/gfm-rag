# P2c-R Gate 0: full archive-to-summary contract

Status: **Gate 0 PASSED**. The archive-only engineering run completed at published source commit `34f843ce0ea4014f152e4b53ab2b32ea93bfce12`. This record follows the P2c-R protocol at guidance commit `629bfe0`. The original P2c report and its stopped status remain unchanged.

The root cause was a full schema boundary mismatch: P2b stores flat Column recall and budget dictionaries, while P2c stores recall under K and budget metrics inside each budget. The repair compares all 48 required metrics explicitly at `rtol=0, atol=1e-14`, checks four eligible-question denominators, and reports full metric paths for missing, malformed, non-finite, or unequal values.

Tests use the actual public P2b archive, perturb each metric independently, exercise six synthetic questions on two databases through aggregation, bootstrap, anonymization, JSON roundtrip and SHA checking, and reproduce the greedy-packing counterexample in which a shortened early non-Gold candidate displaces later Gold. Before repair, 65 of 66 contract tests failed on the old mapping. After repair, runner guards and review fixes, 93 relevant tests passed; raw test logs remain local in `ai_temp_code/`.

The Gate 0 run read only archived R0/R1 rows. V01 duplicated R0 and V10 duplicated R1; Table metrics were synthetic zero placeholders because P2b did not archive Table Top-K. All 48 archive metrics, four eligible denominators, and aggregate JSON write/read/SHA checks passed across 1,534 historical questions. The local artifact is engineering-only and suppresses any scientific decision. No new V01/V10 scoring occurred. Gate 0 artifacts remain outside formal result directories.

The original registration stays closed. Shared input validation now accepts an explicit independent registration path and experiment ID, with the old defaults retained; the new runner has separate contract/smoke/full IDs and unique output paths. A subsequent smoke and Full require a passing Gate 0 receipt, unchanged code and input hashes, and one source commit for both scientific stages.

Independent review found two integrity gaps before execution: configured input hashes were not enforced, and only two runner sources were frozen. Both are fixed and covered by failing-then-passing regression tests: all four registered input hashes are checked, and a seven-file execution-source map including dynamic helpers is frozen. Persisted predecessor identity/state and aggregate SHA are also checked before Full. No review finding remains open.

Validation command: `conda run --no-capture-output -n think2sql_20260909 pytest -q tests/test_p2c_r_contract.py tests/test_p2c_r_runner.py tests/test_p2c_dual_view_factorial.py tests/test_p1_6_input_manifest.py` (93 passed).

Configuration: [experiment_config.json](experiment_config.json). Runner: `scripts/text2sql/run_p2c_r_recovery.py`. References: [P2c-R protocol](../../plans/p2c_r_replay_contract_recovery_20261018.md), [old failure analysis](../p2c_execution_review_20261018/README.md).

Budget: at most 1,800 process CPU seconds, eight threads, 16 GiB RSS; GPU/API/model forwards/SQL = 0. Existing `think2sql_20260909` environment and canonical source symlinks are reused. No dependencies or model weights are installed.

Actual use: 12.381695 process CPU seconds / 12.647481 wall seconds / 0.882500 GiB peak RSS. Machine-readable checks, complete command, dependency versions, source/input hashes and receipt hash are in [gate0_checks.json](gate0_checks.json). The next step is the separately registered [P2c-R smoke/Full](../p2c_r_recovery_20261019_01/README.md), limited to one run each with the same execution code and inputs.
