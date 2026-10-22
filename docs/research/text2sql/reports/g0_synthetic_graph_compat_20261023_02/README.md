# G0 synthetic graph compatibility — recovery attempt 02

**Status: preregistered; execution pending.** This is one bounded recovery run after attempt 01 failed before message passing.

The [recovery protocol](../../plans/g0_synthetic_graph_compatibility_recovery_20261023_02.md) keeps the checkpoint, synthetic fixture, seed, gates, and compute budget fixed. It changes only the launch method to activate the existing Conda environment, where Ninja is already installed. No dependencies are changed.

## Frozen scope

- Five synthetic nodes and eight directed edges with parallel FK-role relations and one two-component composite FK.
- Official G-reasoner-34M checkpoint at 1024 feature dimensions.
- One GPU, seed 20261023, one baseline forward and one metadata-perturbed paired forward.
- No BIRD, Gold labels, SQL, training, model API, tuning, or retries.

## Results

Pending the single preregistered recovery run. No measurements are reported yet.

## Interpretation boundary

Only input compatibility, tensor shape/finiteness, metadata round-trip, and metadata sensitivity are measured. A successful forward pass does not establish FK-role reasoning, JOIN accuracy, or downstream SQL improvement.

Attempt 01 and its launch failure are reported separately at [attempt 01](../g0_synthetic_graph_compat_20261023_01/README.md).
