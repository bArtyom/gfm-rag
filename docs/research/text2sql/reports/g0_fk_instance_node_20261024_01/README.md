# G0 FK instance-node scoring probe

**Status: registered; not yet run.** No result is reported in this pre-run version.

## Experiment question

After choosing mapping-level FK identity with repeated declaration counts stored separately, can the frozen G-reasoner return one stable node score per Join mapping when same-endpoint mappings are represented as explicit instance nodes? Does a four-query synthetic billing/shipping probe show an initial query-conditioned signal relative to dense cosine and a simple FK path baseline?

## Pre-registered design

- **Layer:** exploratory synthetic engineering and identifiability probe; no real-role or SQL claim.
- **Fixture:** two tables, two distinct mappings sharing endpoints, and three declarations (one exact duplicate). Mapping identity yields two unique Join nodes with multiplicities 2 and 1.
- **Comparisons:** local Qwen3 dense cosine; direct typed parallel-edge table graph; reified relation-typed G-reasoner graph; simple FK path tie baseline.
- **Queries:** four fixed synthetic prompts, two with billing targets and two with shipping targets.
- **Pass criteria:** direct output `[1,2]`, reified output `[1,4]`, finite scores; mapping scores remain stable under node/edge permutation (max delta ≤ `1e-5`, same top-1); GFM top-1 correct on ≥3/4 and mean score margin is positive for billing and shipping queries. All criteria must pass for `G0_SYNTHETIC_PASS`.
- **Budget:** smoke 1 forward then, only if it passes, full 6 forwards; total max 7 forwards and 2 loads per model, one GPU, 20 minutes/run, no training, API, BIRD/Gold, SQL, installs, or downloads.
- **Environment/resources:** frozen `gfmrag_greasoner_20261022`; details and hashes are in the [pre-registration](../../plans/g0_fk_instance_node_20261024.md) and [configuration](experiment_config.json).

## Execution and results

Pending smoke. Full is not authorized by the protocol unless smoke passes. Run outputs will be saved under `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_01/`, with logs under `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/`. Public artifacts will be limited to synthetic aggregate scores and reproduction metadata.
