# Amendment 001 — Spider capacity audit runtime correction

**Registered before retry.** This amendment changes only the execution environment and the Smoke run ID. The dataset, split, sample rule, parser, candidate definition, resource caps, and decision gates remain frozen.

## Stopped attempt

`p0_spider_fk_mapping_candidate_capacity_20261107_01_smoke_001` was launched with the existing `gfmrag_greasoner_20261022` environment. It stopped at `ModuleNotFoundError: sqlglot` while importing the runner. The failure occurred before archive hashing, ZIP opening, question/SQL reads, or output-directory creation. Its private startup log is `/mnt/liansp3/logs/gfmrag_p0_spider_fk_mapping_candidate_capacity_20261107_01/smoke_001.log`. No model, API, GPU, or SQL execution was involved.

## Corrected execution

An environment inventory confirmed the existing `think2sql_20260909` environment already has Python 3.12.14 and SQLGlot 28.0.0. No package is installed or changed. Smoke 001 remains closed and is not reused. The new Smoke ID is `p0_spider_fk_mapping_candidate_capacity_20261107_01_smoke_002`; if it passes, the not-yet-attempted Full ID remains `p0_spider_fk_mapping_candidate_capacity_20261107_01_full_001`.

The runner now requires the amended IDs. No input, data version/hash, SQL parser behavior, sample, threshold, budget, or output policy has changed.
