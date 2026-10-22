# G0 synthetic graph compatibility — recovery attempt 02

**Status: failed launch; no model result.** Attempt 02 did not execute the preregistered runner.

The [recovery protocol](../../plans/g0_synthetic_graph_compatibility_recovery_20261023_02.md) keeps the checkpoint, synthetic fixture, seed, gates, and compute budget fixed. It changes only the launch method to activate the existing Conda environment, where Ninja is already installed. No dependencies are changed.

## Frozen scope

- Five synthetic nodes and eight directed edges with parallel FK-role relations and one two-component composite FK.
- Official G-reasoner-34M checkpoint at 1024 feature dimensions.
- One GPU, seed 20261023, one baseline forward and one metadata-perturbed paired forward.
- No BIRD, Gold labels, SQL, training, model API, tuning, or retries.

## Launch outcome

The process exited with code 2 in under one second because the actual command named the nonexistent temporary script gfmrag_greasoner_dummy.py instead of the preregistered gfmrag_g0_synthetic_graph_compat_20261023_02.py. The shell stopped before loading the runner, checkpoint, or synthetic fixture.

This is an operator command-path error. It is not evidence about the model or graph interface. No GPU computation, dependency change, model API request, training, or SQL execution occurred. The pre-registered command and the actual failed command are recorded separately in the local launch manifest and failure record.

No retry was made under attempt 02. A corrected execution requires a separately registered attempt 03, with its exact command reviewed before launch.

Attempt 01 and its independent RSPMM/Ninja activation failure are reported at [attempt 01](../g0_synthetic_graph_compat_20261023_01/README.md).
