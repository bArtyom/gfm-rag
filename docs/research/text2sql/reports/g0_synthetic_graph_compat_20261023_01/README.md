# G0 synthetic graph compatibility — attempt 01

**Status: failed launch; no model-forward result.** This attempt did not measure retrieval, JOIN accuracy, SQL execution, or method quality.

## Frozen scope

The preregistered five-node, eight-directed-edge synthetic fixture, official G-reasoner-34M checkpoint, 1024-dimensional features, seed 20261023, and one-GPU budget are recorded in the [protocol](../../plans/g0_synthetic_graph_compatibility_20261023.md) and [frozen configuration](experiment_config.json). Preregistration was published before execution at commit fd7a4d58bf09c082c5ad1691cbb091e3f1bd5fbc.

## What completed

- The pinned checkpoint loaded: 34,640,897 parameters; model and entity input dimensions were both 1024.
- The synthetic fixture assertions passed: five nodes, eight directed edges, two distinct relation types over the same endpoint pair, two ordered components for one composite FK, and consistent inverse-edge pairing.
- PyG device transfer preserved edge indices, relation IDs, edge features, FK-instance IDs, composite component indices/counts, and inverse flags.
- No score tensor was produced. The model forward stopped while PyTorch attempted to load the upstream RSPMM C++/CUDA extension.

## Failure and root cause

The process exited with code 1 after about five seconds. PyTorch reported that Ninja was required for JIT extension loading. Ninja 1.11.1.4 was already installed in the dedicated Conda environment at its bin/ninja path, but the launch invoked that environment's Python executable directly without activating the environment. As a result, the environment's bin directory was absent from PATH.

The root cause was confirmed after the attempt: conda run exposes the installed Ninja executable and reports version 1.11.1.git.kitware.jobserver-1. No package was installed or upgraded. The original failed logs remain local under the registered log directory.

## Gate status and limits

| Gate | Outcome |
|---|---|
| Checkpoint load and 1024-d configuration | Pass |
| Synthetic graph and FK metadata integrity | Pass |
| G0-A finite [1,5] model output | Not reached |
| G0-C metadata perturbation comparison | Not reached |

This is a launcher/environment failure, not a negative model result. It does not count as G0 completion. No retry was made under attempt 01.

## Recovery

A separate attempt 02 was preregistered with the same model, fixture, seed, and gates. Its only execution change is activating the existing environment through conda run. See the [recovery plan](../../plans/g0_synthetic_graph_compatibility_recovery_20261023_02.md) and [attempt 02 report](../g0_synthetic_graph_compat_20261023_02/README.md).

## Provenance

- Official source: RManLuo/gfm-rag commit b3e43219c49929da505244df4f0ba54c0947e4c4, Apache-2.0.
- Checkpoint: rmanluo/G-reasoner-34M revision a3a4ed2c62281e1c3e0551bd42f2072d9204674f, Apache-2.0.
- Runner: scripts/text2sql/g0_synthetic_graph_compat_20261023.py; SHA-256 ab9e21065f59c0be91b4474bf03989e193ddbb154fde77371b82ca2091fd2984.
- Seed 20261023; GPU2 RTX 4090; Python 3.12.15; PyTorch 2.8.0; PyG 2.6.1.
- BIRD/Gold/SQL/API/training: none.
