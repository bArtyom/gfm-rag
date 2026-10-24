# G0-02 FK instance-node scoring recovery probe

**Status: pre-registered; not run.** Experiment ID: `g0_fk_instance_node_20261024_02`. This is a separately budgeted recovery after G0-01 ended as `IMPLEMENTATION_FAILURE`; it does not reuse G0-01 run IDs, result paths, or in-memory outputs.

## Why a new experiment

G0-01 smoke_002 passed its operational gate, but full_001 completed four reified-query forwards and one direct-graph forward before failing in the permutation control. PyG 2.6.1 `Data.to()` mutates the source `Data` object through `apply()`. The later permutation then indexed a CUDA `edge_index` using a CPU inverse-index tensor. No complete Full metrics were serialized, so the four-query scientific gate remains unevaluated.

G0-02 makes one execution-only code correction: `move_graph()` clones a `Data` object before transferring tensors to the device. Its `EXPERIMENT_ID` and output paths are new. The fixture, questions, seed, model/checkpoint, baselines, metrics, pass thresholds, budget, and stopping rules are unchanged from G0-01. This is a new registered run to complete the same unresolved synthetic engineering question, not a retrospective change to G0-01.

## Question and frozen hypothesis

**Question.** With two distinct ordered FK mappings sharing table endpoints, can the frozen G-reasoner emit a stable, query-conditioned score per mapping node when each mapping is explicitly reified?

**Core hypothesis.** Mapping-level identity (one stable node per distinct ordered Join mapping, with exact duplicate declarations represented as multiplicity metadata) provides separate, permutation-stable score targets. The model may or may not produce a synthetic query-conditioned signal beyond dense cosine; this probe cannot establish real FK-role accuracy or downstream SQL gain.

## Frozen fixture and comparisons

- Synthetic schema: `orders(order_id, billing_customer_id, shipping_customer_id)` and `customers(customer_id, name)`.
- Declarations: billing mapping twice and shipping mapping once. SHA-256 of the ordered `(source_table, source_column, target_table, target_column)` tuple yields two stable mapping IDs with multiplicities 2 and 1; reordering declarations must preserve IDs/counts.
- Four fixed queries from `scripts/text2sql/g0_fk_instance_node_probe.py`, two billing and two shipping. Seed `20261024`.
- Compare local Qwen3 dense cosine over the two mapping descriptions, direct typed-edge table graph (table-node outputs only), reified relation-typed G-reasoner mapping-node outputs, and the one-hop FK path tie baseline.
- No BIRD questions, Gold SQL, database rows, SQL execution, human labels, training, downloads, dependency changes, remote model/API calls, or paid services.

## Success criteria (carried over unchanged)

1. CPU identity contract: 3 declarations form 2 unique IDs, with multiplicities 2/1, invariant to declaration-order reversal.
2. Forward shapes: direct graph `[1,2]`; reified graph `[1,4]`; all outputs finite.
3. Permutation: after reordering mapping nodes and edge rows and mapping outputs back by stable ID, maximum score delta `<=1e-5` and the set of top-ranked mapping IDs is unchanged.
4. Synthetic signal: GFM top-1 correct on at least 3/4 queries, strictly more correct queries than dense cosine, and positive mean score margins for both billing and shipping groups.
5. `G0_SYNTHETIC_PASS` requires all four gates. Any criterion failure yields `G0_SYNTHETIC_NO_GO`; an execution/code/resource failure yields `IMPLEMENTATION_FAILURE`. Smoke does not contribute to the 4-query signal denominator.

No thresholds or query text may change after seeing G0-01 smoke output.

## Code change under this registration

The only inference behavior change is in `move_graph()`: `graph.clone().to(device)` prevents PyG 2.6.1's in-place `Data.to()` from moving the registered source graph. The previous G0-01 script remains available at its original Git commit and blob. G0-02 uses the same script path at the new registered commit and a new `EXPERIMENT_ID`; no other model or scoring changes are included.

## Budget and stops

- One smoke forward, then only on smoke operational pass one Full with 4 reified query forwards, 1 direct graph forward, and 1 permutation-control forward.
- Maximum per G0-02: 2 Qwen loads, 2 G-reasoner loads, 7 G-reasoner forwards, one physical GPU, 20 minutes wall time per run, 300 CPU seconds per run, 8 GiB peak RSS, zero training.
- GNU `timeout --signal=TERM --kill-after=15s 1200s` wraps each run. Use local models in offline mode only; record actual Qwen input tokens, GPU time/use, CPU time, RSS, logs, code/data hashes, and exact command.
- If smoke fails, stop. If Full fails/times out or any frozen success gate fails, preserve artifacts and stop; no further retry under G0-02. G0-01 and G0-02 outputs remain separate and immutable.

## Frozen model and environment

- Project repository: `https://github.com/bArtyom/gfm-rag`, branch `research/g0-fk-instance-node-20261024`; parent is the archived G0-01 failure commit.
- Official model implementation: `https://github.com/RManLuo/gfm-rag`, commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0.
- Checkpoint: local `/mnt/liansp3/sources/models/g-reasoner-34m`, revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`; model SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`; config SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`; 34,640,897 parameters, 1024-D.
- Encoder: local `/mnt/liansp3/sources/models/qwen3-embedding-0.6b`, Qwen3-Embedding-0.6B, Apache-2.0; model SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`; config `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`; tokenizer `def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a`; `modules.json` `84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf`; Sentence-Transformers module `10667c72ddb772627bf1780cb7f86af8e2ae0032b8c243c731172064105c6961`; tokenizer config `253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0`; pooling config `37bf193fa101f19101bfad9c31d3eb0f786e247b7b1e5cb7f007d730eed1ddbd`.
- Conda environment `gfmrag_greasoner_20261022`: Python 3.12.15, PyTorch 2.8.0+cu128, PyG 2.6.1, Transformers 4.56.1, Sentence-Transformers 5.1.1. No installs/upgrades. Because the bare `conda run ... python3` previously selected Python 3.9.20, use the target environment's absolute Python executable inside `conda run`.
- Latest preregistration resource check: 2026-10-24 12:53:42 UTC. GPU 2 (RTX 4090) had 5,600/24,564 MiB used, 18,964 MiB free, 0% utilization; RAM available 423 GiB, 192 CPUs, disk available 114 TiB. Recheck before each launch; if allocation changes, amend the config and push it before running.

## Commands and artifact paths

```bash
env CUDA_VISIBLE_DEVICES=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 timeout --signal=TERM --kill-after=15s 1200s /root/miniconda3/bin/conda run -n gfmrag_greasoner_20261022 --no-capture-output /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3 scripts/text2sql/g0_fk_instance_node_probe.py --mode smoke --run-id g0_fk_instance_node_20261024_02_smoke_001 --checkpoint /mnt/liansp3/sources/models/g-reasoner-34m --embedding-model /mnt/liansp3/sources/models/qwen3-embedding-0.6b --device cuda:0 --output /mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/smoke_001/result.json
```

Full uses the same command with `--mode full --run-id g0_fk_instance_node_20261024_02_full_001 --output /mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/full_001/result.json`.

Private outputs: `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_02/`; logs and launch manifests: `/mnt/liansp3/logs/g0_fk_instance_node_20261024_02/`. Public report and aggregate summary: `docs/research/text2sql/reports/g0_fk_instance_node_20261024_02/`.

## Repository guidance checked

Before registration on branch head `737d22ff989bff5818f64f476abb788797fdcd7a`, re-read root `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, `reproducibility-contract.md`, and the G0-01 report. The roadmap's P0 requirement remains for any BIRD/full-scale retrieval work; this is a bounded synthetic engineering recovery and makes no claim to complete P0. G0-01 is closed without a science conclusion; G0-02 has a separate ID, code tree, budget, paths, report, and stopping condition.
