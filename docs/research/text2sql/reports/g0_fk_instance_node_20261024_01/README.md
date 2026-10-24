# G0 FK instance-node scoring probe

**Status: launcher attempt 001 failed before model initialization; smoke_002 passed the operational gate.** Full is eligible under the frozen protocol, but no full scientific result exists yet.

## Experiment question

After choosing mapping-level FK identity with repeated declaration counts stored separately, can the frozen G-reasoner return one stable node score per Join mapping when same-endpoint mappings are represented as explicit instance nodes? Does a four-query synthetic billing/shipping probe show an initial query-conditioned signal relative to dense cosine and a simple FK path baseline?

## Pre-registered design

- **Layer:** exploratory synthetic engineering and identifiability probe; no real-role or SQL claim.
- **Fixture:** two tables, two distinct mappings sharing endpoints, and three declarations (one exact duplicate). Mapping identity yields two unique Join nodes with multiplicities 2 and 1.
- **Comparisons:** local Qwen3 dense cosine; direct typed parallel-edge table graph; reified relation-typed G-reasoner graph; simple FK path tie baseline.
- **Queries:** four fixed synthetic prompts, two with billing targets and two with shipping targets.
- **Pass criteria:** direct output `[1,2]`, reified output `[1,4]`, finite scores; stable mapping IDs derive from ordered table/column tuples; mapping scores remain stable under node/edge permutation (max delta ≤ `1e-5`, same mapping top-1 set); GFM top-1 correct on ≥3/4, strictly exceeds dense cosine accuracy, and has positive mean score margins for billing and shipping queries. All criteria must pass for `G0_SYNTHETIC_PASS`.
- **Budget:** smoke 1 forward then, only if it passes, full 6 forwards; total max 7 forwards and 2 loads per model, one GPU, 20 minutes/run with a hard launcher timeout, 300 CPU seconds and 8 GiB peak RSS per run, no training, API, BIRD/Gold, SQL, installs, or downloads.
- **Environment/resources:** frozen `gfmrag_greasoner_20261022`; details and hashes are in the [pre-registration](../../plans/g0_fk_instance_node_20261024.md) and [configuration](experiment_config.json).

## Execution and results

### `smoke_001` — launcher failure before model initialization

- **Outcome:** `FAILED_PRE_MODEL_STARTUP`, exit code 1 at 2026-10-24 12:39:37 UTC. The command used `conda run -n gfmrag_greasoner_20261022 ... python3`, but the wrapper selected `/root/miniconda3/envs/python39/bin/python3` (Python 3.9.20), which raised `ModuleNotFoundError: No module named 'sentence_transformers'`.
- **Root cause:** the wrapper's `python3` resolved outside the registered target environment. The target environment is intact: its absolute Python executable is Python 3.12.15, and a no-GPU preflight successfully imported Sentence-Transformers 5.1.1, PyTorch 2.8.0+cu128, PyG 2.6.1, and Transformers 4.56.1.
- **Work not performed:** no Qwen encoder or G-reasoner checkpoint loaded; zero G-reasoner forwards; no data/model download or API call; no scientific metric was produced. Qwen input tokens: 0 for this attempt.
- **Preserved artifacts:** `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_01/smoke_001/result.json.attempt.json` and `result.json.failure.json`; log `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/smoke_001.log`.
- **Resource note:** the immediate post-failure snapshot showed GPU 3 at 17,817 MiB used and 100% utilization while `nvidia-smi` listed no process. A later fresh snapshot returned to 8,665/24,564 MiB and 0% utilization. The failed process did not initialize CUDA; the transient GPU use is not attributed to this experiment.

### `smoke_002` — operational gate passed; no signal claim

- **Outcome:** `SMOKE_PASS`, completed at 2026-10-24 12:46:14 UTC. The CPU identity contract passed: 3 declarations became 2 ordered-mapping IDs with multiplicities 2 and 1, and IDs/counts survived declaration reordering. The local Qwen model hashes matched; output was normalized 1024-D. The frozen G-reasoner checkpoint hash and 34,640,897 parameter count matched; the reified output was finite with the expected `[1,4]` shape.
- **One smoke query:** `q_billing_1`. GFM scored billing `-14.220245` and shipping `-14.047931`, so its top-1 was the wrong shipping mapping. Dense cosine scored billing `0.459858` and shipping `0.405354`, so its top-1 was billing. The FK-path baseline ties both candidates at `1.0`. This single-query observation is the operational smoke only; it does not determine the frozen 4-query signal criterion.
- **Resource use:** physical GPU 2 (RTX 4090; visible as `cuda:0`), wall 8.657 s, GFM forward 0.646 s, Qwen load 1.733 s, GFM load 0.334 s, peak allocated GPU memory 2,477,169,152 bytes, peak process RSS 4.137 GiB, process CPU 34.031 s. All are within registered limits.
- **Local embedding usage:** 13 input sequences / 242 tokens (query 28; passages 214); embedding output is vectors, not generated text tokens. External API requests: 0; external API cost: 0 CNY. Model output is local inference, with GPU time reported separately.
- **Artifacts:** result `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_01/smoke_002/result.json`, SHA-256 `60aa0005e27a422bdd9bb7d942bcda75258b83d453e9c5db34c045f56ca6cbda`; attempt marker is adjacent. Log `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/smoke_002.log`; launch manifest `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/smoke_002_launch.json`.

### Corrected launch registered before retry

The corrected attempt used the target environment's absolute Python executable inside `conda run`. All scientific inputs and criteria remain frozen. Smoke_002 passed, so the single registered Full run may proceed; any Full failure or timeout stops the experiment. Its output uses a separate immutable path under `/mnt/liansp3/sources/results/gfmrag_g0_fk_instance_node_20261024_01/`, with logs under `/mnt/liansp3/logs/g0_fk_instance_node_20261024_01/`. Public artifacts will be limited to synthetic aggregate scores and reproduction metadata.

- **GPU selection:** at the 2026-10-24 12:44 UTC pre-launch check, GPU 3 had 12,805/24,564 MiB used and 100% utilization; GPU 2 had 5,211/24,564 MiB used and 0% utilization. The corrected run selects physical GPU 2 (`CUDA_VISIBLE_DEVICES=2`, visible as `cuda:0`) with one GPU only.
