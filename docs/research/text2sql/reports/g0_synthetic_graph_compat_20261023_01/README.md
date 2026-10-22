# G0 synthetic graph compatibility — run 01

**Status: preregistered; execution pending.** This is a bounded engineering/interface smoke, not evidence of SQL quality, JOIN accuracy, or a method gain.

The frozen hypothesis, gates, resource budget, source revisions, fixture, and stop rule are recorded in [the experiment plan](../../plans/g0_synthetic_graph_compatibility_20261023.md) and [experiment_config.json](experiment_config.json). The protocol was committed before execution.

## Frozen scope

- One synthetic five-node graph with eight directed edges, including two parallel FK-role relations and one two-component composite FK with inverse edges.
- One pretrained official G-reasoner-34M checkpoint at 1024 feature dimensions.
- One forward pass and one paired pass that changes only edge metadata.
- One seed; no BIRD, Gold labels, SQL, training, API calls, tuning, or retries.

## Results

Pending the preregistered run. No measurements are reported yet.

## Interpretation boundary

Only checkpoint load, input/output interface, finite tensor shape, metadata round-trip, and metadata sensitivity are measured. Synthetic scores are not treated as ranked answers. A successful forward pass does not establish FK-role reasoning or JOIN accuracy.
