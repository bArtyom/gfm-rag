# G0 FK instance-node scoring probe (pre-registration)

**Status: registered, not run.** Experiment ID: `g0_fk_instance_node_20261024_01`. Category: bounded exploratory synthetic engineering probe. This is a new protocol after G2-A PASS, the original FK Instance Gate NO-GO, and the duplicate-identity policy audit. It does not change either earlier result.

## Question and hypothesis

**Question.** When two distinct FK mappings connect the same pair of tables, can the frozen G-reasoner emit one stable score per mapping if each unique Join mapping is represented as a node? Does this small synthetic fixture produce a query-conditioned signal beyond dense cosine, while the direct table graph exposes only table-node scores?

**Core hypothesis.** Mapping-level identity (one node per distinct ordered Join mapping; exact duplicate declarations stored as multiplicity metadata) preserves stable candidate IDs. Reifying each mapping as a node creates an instance-level scoring target for the official node scorer. The frozen model may or may not rank a controlled synthetic billing/shipping mapping correctly; this toy ranking is a kill gate only, not evidence of real business-role accuracy.

## Claim and evidence contract

| Claim | Evidence | Pass rule | Boundary |
|---|---|---|---|
| Mapping identity preserves unique Join candidates | CPU fixture with two distinct mappings and one exact duplicate declaration | 3 declarations become 2 mapping IDs with multiplicities `{billing_map: 2, shipping_map: 1}`; reified graph has 2 mapping nodes and 8 directed endpoint edges | Synthetic structure only |
| Reification exposes one model score per Join mapping | Frozen G-reasoner forward on direct and reified layouts | Direct layout output `[1,2]`; reified layout output `[1,4]`; all finite | Engineering/readout feasibility, not model accuracy |
| Scores follow stable mapping IDs | Reorder reified nodes and all edge rows, remap output to frozen IDs | max absolute score delta `<= 1e-5` and top-1 unchanged | One synthetic graph/query; no statistical inference |
| Small query-conditioned signal exists | Four fixed synthetic questions, with two billing and two shipping targets | GFM top-1 correct on at least 3/4; mean score margin is positive for billing queries and for shipping queries | Synthetic pilot only; no BIRD/real query claim |
| Baselines are comparable on this fixture | Same Qwen query/node vectors for cosine; direct typed-edge graph; FK-path heuristic | Report each exact score/rank; path-only baseline ties because both mappings share one endpoint path | No claim that a 4-item toy is a benchmark |

The experiment-level decision is `G0_SYNTHETIC_PASS` only when the interface, permutation, and synthetic-signal rules all pass. Otherwise record `G0_SYNTHETIC_NO_GO` or an implementation failure and stop. No threshold changes after observing outputs.

## Frozen fixture and methods

Synthetic schema: `orders(order_id, billing_customer_id, shipping_customer_id)` and `customers(customer_id, name)`. Two unique mappings share the same table endpoints:

- `orders.billing_customer_id -> customers.customer_id` (`billing_map`)
- `orders.shipping_customer_id -> customers.customer_id` (`shipping_map`)

The fixture contains three declarations: one billing mapping is repeated exactly. Under the selected mapping-identity policy the repeated declaration collapses to one `billing_map` node with multiplicity 2; it does not generate duplicate graph edges. The shipping mapping remains a distinct node with multiplicity 1. These are synthetic labels, not human-verified BIRD roles.

Four frozen query texts are in `scripts/text2sql/g0_fk_instance_node_probe.py`: two billing and two shipping requests. The model inputs use the G-reasoner checkpoint's existing Qwen query instruction from its config. Passage texts use fixed table, mapping, or relation descriptions for all relevant baselines.

1. **Dense cosine:** local Qwen3 query vectors against the two mapping-node vectors.
2. **Direct typed-edge reference:** two table nodes with two parallel relation instances and their inverses; read only the official per-node outputs. This graph cannot produce a distinct FK score because both mappings share the same endpoints.
3. **Reified relation-typed GFM:** two table nodes plus two mapping nodes; source/target typed incidence edges and inverse types; frozen official G-reasoner scores are read at the two mapping-node positions.
4. **Simple FK-path heuristic:** both unique mappings have the same single-hop endpoint path, so it ties and cannot resolve roles.

No model training, BIRD questions, Gold SQL, business table rows, SQL execution, human review, external model API, new download, or dependency installation.

## Model, data, versions, and environment

- Project repository: `https://github.com/bArtyom/gfm-rag`, branch `research/g0-fk-instance-node-20261024`, based on current G2 head `0bf7dc357bdcfdb86895d8e3c83518542a634ebf`.
- Official implementation: `https://github.com/RManLuo/gfm-rag`, commit `b3e43219c49929da505244df4f0ba54c0947e4c4`, Apache-2.0. Use the unchanged installed API and pinned checkpoint only.
- G-reasoner checkpoint: `rmanluo/G-reasoner-34M`, revision `a3a4ed2c62281e1c3e0551bd42f2072d9204674f`; input/feature dimension 1024; 34,640,897 parameters; local `model.pth` SHA-256 `2f2a1a2d2f5725133428941b785f3898255666b06041b58420f75e60599d387d`; `config.json` SHA-256 `75d14b97d6a077ebc17b09a21170a3ad9272251db59f7ac8cc853165efb2efd5`.
- Local encoder: `Qwen/Qwen3-Embedding-0.6B`, Apache-2.0, normalized 1024-D; local weight SHA-256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`; config SHA-256 `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`; tokenizer SHA-256 `def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a`. Snapshot revision is represented by verified file hashes because the resource index does not record its upstream commit.
- Conda environment: `gfmrag_greasoner_20261022`; Python 3.12.15, PyTorch 2.8.0, PyG 2.6.1, Transformers 4.56.1, Sentence-Transformers 5.1.1. Reuse as-is; no dependency change.
- Hardware: one RTX 4090 selected only after launch-time `nvidia-smi`, `free -h`, and `nproc`; no parallel GPU experiment. Record physical GPU, free VRAM, peak allocated VRAM, wall time, and local embedding input-token count. Local embedding output is vectors, not generated text tokens; no external API cost. Local GPU time is a resource cost and will be reported separately.
- Data: only the synthetic fixture in the script; dataset revision is this committed code. No external dataset or private text is loaded.

## Budget, smoke, and stopping

- Total maximum across both phases: two Qwen encoder loads, two G-reasoner checkpoint loads, seven G-reasoner forward passes (smoke 1 + full 6), one GPU, 20 minutes wall time per run, 300 CPU seconds per run, 2 GiB process RSS, zero training epochs.
- Smoke: one predeclared billing query, reified graph only. Require exact fixture counts, local-only 1024-D finite Qwen vectors, checkpoint hashes/parameter count, output `[1,4]`, finite scores, and no overwrite. Failure stops the experiment; no retry with the same run ID.
- Full starts only after smoke passes. It runs four reified queries, one direct-edge graph reference, and one reified node/edge-order permutation control.
- Stop immediately for any CPU fixture failure, offline model load failure, hash/config mismatch, non-finite or wrong-shaped output, GPU/RAM budget overrun, or attempted data/API/dependency access outside this protocol. Preserve failure output. No fallback to a paid API or different checkpoint.
- Successful engineering or synthetic signal does **not** authorize Role supervision, real BIRD accuracy reporting, SQL EX, or an unregistered follow-up.

## Reproducibility and artifacts

The runner, plan, fixed config, report stub, and index update are committed and pushed before the smoke run. Smoke and full each have unique immutable output paths under `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_01/`; logs are under `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/`. The public report and aggregate JSON live in `docs/research/text2sql/reports/g0_fk_instance_node_20261024_01/`. No vectors, weights, private datasets, or API secrets are published.

## Repository guidance read before this registration

At base commit `0bf7dc357bdcfdb86895d8e3c83518542a634ebf`, read root `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, `reproducibility-contract.md`, the G2 plan, G2 report, original FK Instance Gate report, and duplicate-identity policy plan/report. The fork has no root `AGENTS.md`; `/mnt/liansp3/AGENTS.md` governs local execution. The G2 decision explicitly requires a separately registered G0 semantic choice; this plan adopts unique mapping identity plus multiplicity metadata. Roadmap P0 remains required before any large-scale dimension sweep; this bounded G0 synthetic gate does not claim to complete P0.
