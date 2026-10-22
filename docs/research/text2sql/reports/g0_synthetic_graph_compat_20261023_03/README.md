# G0 synthetic graph compatibility — attempt 03

**Status: completed; interface feasibility passed, tested FK-instance metadata was ignored.** This is a bounded synthetic engineering result, not a Text-to-SQL accuracy experiment.

## Research question and preregistered hypothesis

Can the pinned official G-reasoner-34M checkpoint execute the fixed five-node, eight-directed-edge synthetic PyG graph at 1024 feature dimensions and return finite per-node outputs? The companion mechanism check asks whether perturbing only `edge_attr` and custom FK-instance fields changes the output. Source inspection predicted that this model path ignores these fields.

- Layer: synthetic/interface feasibility.
- Budget: one model load, two forwards, one RTX 4090, seed `20261023`, and a 15-minute ceiling.
- Success criteria: G0-A checkpoint/shape/finite-output pass; G0-B graph and metadata survive device transfer; G0-C exact output difference is recorded, with `<= 1e-6` treated as unchanged.
- Stop rule: one run, no retry under this ID. This run completed within the budget; no further G0 launch was started.

## Provenance and reproduction

- Owned report repository: [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/g0-synthetic-compat-20261023`.
- Protocol and experiment-guide revision: [`aa2d21a`](https://github.com/bArtyom/gfm-rag/commit/aa2d21ac710edfe098ac752970571c084ad84731); run-specific preregistration was published before launch.
- Pre-run repository guidance read at that revision: the project `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, `reproducibility-contract.md`, and the run-specific attempt plan. The local `AGENTS.md` experiment/resource rules were also followed.
- Official code: [`RManLuo/gfm-rag`](https://github.com/RManLuo/gfm-rag), commit `b3e43219c49929da505244df4f0ba54c0947e4c4` (Apache-2.0).
- Checkpoint: `rmanluo/G-reasoner-34M`, revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f` (Apache-2.0), 34,640,897 parameters. Model and config SHA-256 values are in [`experiment_config.json`](experiment_config.json) and [`result.json`](result.json).
- Public runner: [`g0_synthetic_graph_compat_20261023_03.py`](../../../../../scripts/text2sql/g0_synthetic_graph_compat_20261023_03.py); local execution copy SHA-256 `2e70a4bf97a762d1a386a26cd28c12260455c572a3297eaf1e0d7808e5f44f0d`.
- Environment: isolated `gfmrag_greasoner_20261022`; Python 3.12.15, PyTorch 2.8.0+cu128 (runtime CUDA 12.8), PyG 2.6.1, CUDA Toolkit 12.6.3, Ninja 1.11.1.4. Existing packages only; no dependency changes.
- Synthetic fixture: five nodes, eight directed edges (four direct edges plus inverse edges), six relation IDs, 1024-dimensional node/relation/edge features, two parallel relation roles and two ordered components for a composite FK. Seed `20261023`; fixture bundle SHA-256 is recorded in `result.json`.
- No BIRD data, Gold labels, business data, SQL, database, training, or model API were used.

Run from `/mnt/liansp3` with physical GPU 2 selected (process-visible `cuda:0`):

```bash
CUDA_VISIBLE_DEVICES=2 /root/miniconda3/bin/conda run -n gfmrag_greasoner_20261022 --no-capture-output python /mnt/liansp3/ai_temp_code/gfmrag_g0_synthetic_graph_compat_20261023_03.py --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --output /mnt/liansp3/sources/results/gfmrag_g0_synthetic_graph_compat_20261023_03/g0_result.json --device cuda
```

The model forward loaded/compiled the upstream RSPMM CUDA extension and completed in **56.3941 seconds**. The run result was written at 2026-10-23 00:24:13.826 CST. The run-session broker did not retain the final shell return code after it closed; stdout contains the complete result JSON and no traceback, and the result artifact is present. No rerun was made to recover that status. The only stderr entry was a non-fatal warning that `TORCH_CUDA_ARCH_LIST` was unset.

## Results

| Gate | Observed result | Outcome |
|---|---|---|
| G0-A checkpoint and forward | 1024 input/features; 34,640,897 parameters; output shape `[1, 5]`; all finite | Pass |
| G0-B metadata round trip | 5 nodes, 8 directed edges, parallel relation types 0/1, composite FK components `[0,1]` with counts `[2,2]`, inverse-edge pairing intact after device transfer | Pass |
| G0-C metadata perturbation | Maximum absolute output difference `0.0`; tensors exactly equal; threshold `1e-6` | **Metadata ignored** |

The full sanitized result is [`result.json`](result.json). Its SHA-256 is `0c608813b2cf2ce6630d662b96e1404c9158f72109dd75034818bfb5186380ae`. Local stdout/stderr and the complete machine manifest remain under `/mnt/liansp3/logs/gfmrag_g0_synthetic_graph_compat_20261023_03/` and were not uploaded.

## Interpretation and decision

The checkpoint accepts this synthetic graph and returns a finite per-node tensor, so the narrow interface-feasibility hypothesis passed. Changing only `edge_attr` and the custom FK-instance metadata did not change the scores at all. This matches the upstream source path: GraphReasoner uses `graph.x` and `graph.rel_attr`, while message passing uses `edge_index` and `edge_type`; the tested edge attributes and custom FK-instance fields are not consumed.

**Decision: retain this as partial engineering feasibility; stop claims or follow-up runs that assume instance-aware FK-role/path reasoning from the unmodified checkpoint.** Any future mechanism experiment needs a separately preregistered input/model change and a new falsifiable question. The FK/Role Gold Gate remains **NO-GO**.

This fixture has no labeled ranking target and only one fixed seed/checkpoint. It therefore measures no JOIN accuracy, retrieval quality, SQL execution accuracy, or method improvement. The first two launch failures remain separately reported in [attempt 01](../g0_synthetic_graph_compat_20261023_01/README.md) and [attempt 02](../g0_synthetic_graph_compat_20261023_02/README.md); they are not folded into this successful model run.
