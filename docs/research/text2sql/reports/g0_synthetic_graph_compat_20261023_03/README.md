# G0 synthetic graph compatibility — attempt 03

**Status: preregistered; execution pending.** This is one final bounded attempt to run the fixed synthetic interface gate after two separately documented launcher failures.

The [protocol](../../plans/g0_synthetic_graph_compatibility_attempt_20261023_03.md) holds the checkpoint, fixture, seed, gates, and resource budget fixed. The launch command explicitly points to the attempt 03 runner and result file and activates the existing Conda environment through conda run.

## Frozen scope

- Five synthetic nodes, eight directed edges, two parallel relation roles, and a two-component composite FK.
- Official G-reasoner-34M at 1024 feature dimensions.
- One GPU, seed 20261023, one baseline forward plus one metadata-perturbed forward.
- No BIRD, Gold labels, SQL, training, API calls, dependency changes, tuning, or further retries.

## Results

Pending the single preregistered attempt. No measurements are reported yet.

## Interpretation boundary

Only model loading, input/output interface, finite output, metadata preservation, and metadata sensitivity are measured. A successful forward does not establish FK-role reasoning, JOIN accuracy, or SQL improvement.

Earlier failures are archived separately: [attempt 01](../g0_synthetic_graph_compat_20261023_01/README.md) and [attempt 02](../g0_synthetic_graph_compat_20261023_02/README.md).
