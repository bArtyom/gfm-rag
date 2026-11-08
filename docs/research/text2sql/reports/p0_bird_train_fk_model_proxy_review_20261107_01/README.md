# BIRD train FK constraint-level local model-proxy review

**Status: packet preparation passed; Smoke 001 is a protocol deviation and excluded; valid Smoke 002 and Full 002 are pending.**
**Experiment ID:** p0_bird_train_fk_model_proxy_review_20261107_01  
**Evidence class:** exploratory local-model proxy review feasibility; no human Role labels and no ranking result.

## Research question and hypothesis

For BIRD-train question/table-pair units with at least two distinct complete FK constraints verified against SQLite, can two local Qwen models produce enough exact, medium-or-higher-confidence agreement to justify a separately registered exploratory mapping-ranking diagnostic?

The frozen hypothesis requires at least 30 adjudicable exact agreements, at least 20 distinguishable accepted sets, and coverage of at least three anonymous databases on Full. Model agreement is not correctness. The two reviewers share the Qwen family, and Qwen3-4B is Think2SQL fine-tuned; their errors may be correlated.

## Protocol and scope

- Layer: exploratory annotation-feasibility gate before any ranking experiment.
- Source: public BIRD train, previously used in other local work. Treat results as exploratory, not as independent hidden-test evidence.
- Fixed candidate set: all 138 exact-aligned question × table-pair units with at least two distinct complete SQLite FK constraint signatures, selected from the prior identity audit's 379 non-Smoke units. Eight anonymous databases.
- Five Smoke units are selected across five anonymous databases. On success, each reviewer reruns all 138 units for Full; Smoke outputs are excluded from Full metrics.
- The table pair was selected using reference-SQL-derived joins in the earlier capacity stage. Reviewers see the natural-language question, the two table names, and complete candidate FK constraints. They do not see SQL, database IDs, ranks, scores, or the other reviewer's output. This is a known-pair task, not end-to-end Gold-free evaluation.
- Composite FK columns remain together and in PRAGMA sequence order. Identical complete signatures are deduplicated in the candidate universe.
- A later G-reasoner/Dense comparison is out of scope and requires its own pre-registration.

The fixed eligible-unit counts by anonymous database are db_01 30, db_02 27, db_03 6, db_04 34, db_05 13, db_06 7, db_07 14, and db_09 7. Smoke selects one unit from each of db_01 through db_05; Full reruns all 138.

Full protocol: ../../plans/p0_bird_train_fk_model_proxy_review_20261107_01.md.  
Base config: ../../../../../configs/text2sql/p0_bird_train_fk_model_proxy_review_20261107_01.json.  
Recovery amendment: ../../plans/amendments/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.md.

## Frozen inputs, code, and models

| Item | Frozen value |
|---|---|
| User-owned project repository | https://github.com/bArtyom/gfm-rag |
| Branch | research/p0-sql-used-proxy-alignment-20261107 |
| Base protocol/config/code commit | c71bdef1f7822f07c336dda83020b7f9f880019e |
| Preparation amendment commit | 23c3570c8d90982b7b2ff450c9c73cb4a2a9701d |
| BIRD train JSON SHA-256 | abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520 |
| Train schema SHA-256 | 85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b |
| SQLite identity-audit evidence SHA-256 | ff3d379743824eff85f9eec55bffdbf8679e8980ab1f47abbbdc70b86fb01ebf |
| Existing A model | Qwen2.5-Coder-7B-Instruct, local alias /mnt/liansp3/sources/models/qwen25-coder-7b |
| Existing B model | Qwen3-4B-Think2SQL, local alias /mnt/liansp3/sources/models/qwen3-4b-think2sql |
| Model artifact checksum manifest | docs/research/text2sql/reports/p0_fk_mapping_model_review_proxy_20261106_01/model_artifact_checksums.txt, SHA-256 ac3ddf5fb9e30f6f4a77258c0963bff0d1d4419b123af0711ebc8ab29d15a809 |
| Environment | think2sql_train_20260909; Python 3.10.21; Torch 2.6.0+cu124; Transformers 4.57.1; CUDA runtime 12.4.127 |
| Frozen reviewer runner | scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py, SHA-256 45cadb60ffda61caa762094166f6aa247c1a7c39422cfc8fc8793285346b0f5f |
| Frozen A/B local calls | 5 Smoke and 138 Full per reviewer; greedy generation, max_new_tokens=384; no retries |

The model checksums must match the existing checksum manifest before model loading. No model file was downloaded, copied, or changed.

## Preparation run history and current evidence

1. The first preparation attempt passed all frozen input-hash checks, loaded the private identity evidence and BIRD train JSON, then stopped with KeyError 'audit'. The code used the wrong config nesting; the correct capacity census is inputs.identity_audit. Its private failure receipt and log are preserved. It made no packet, SQL parse, SQLite access, model load, or model/API call.
2. Amendment 001 changed only that field lookup and added a fresh preparation run ID. It did not change the sample, question/table-pair selection, candidate signatures, prompt, models, generation settings, thresholds, or resource limits.
3. Recovery preparation run p0_bird_train_fk_model_proxy_review_20261107_01_packet_prep_002 passed. It created 138 units and 369 mapping candidates across eight anonymous databases. Five Smoke units span five anonymous databases. The packet receipt records sql_copied_to_packet=false, database_opened=false, and model_calls=0.
4. The existing reviewer runner's packet-only preflight passed: 138 units and 369 candidates; A/B pair and mapping sets agree. Packet SHA-256: A 10142c485ec0d934591fca7c90c85f9b818f1e1c26bb814756632af69a388682; B c371cdf7292af4d45927e0a95d85ed39c39dce8941694e496065672ca2fb3628.

Raw question packets, table names, private manifest, mapping identities, and logs remain local at /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_model_proxy_review_20261107_01/ and /mnt/liansp3/logs/gfmrag_p0_bird_train_fk_model_proxy_review_20261107_01/. They are mode 0600 under a 0700 directory.

## Model resource gate

At the initial packet-preflight snapshot, GPU1 had 2,149 MiB free and GPU2 1,293 MiB free, both at 100% utilization. At 06:16 UTC, GPU1 had 3,853 MiB free / 98% utilization, GPU2 had 3,039 MiB free / 99%, and GPU3 had 1,041 MiB free / 77%; available RAM was 436 GiB, with 192 CPU threads. GPU3 briefly showed idle but was occupied at subsequent checks. The frozen launch gate requires GPU1 free memory ≥18,432 MiB and utilization ≤10%, GPU2 free memory ≥10,240 MiB and utilization ≤10%, and available RAM ≥32 GiB. At 07:11 UTC, GPU1 had 16,381 MiB free / 0% utilization and GPU2 13,985 MiB / 0%; GPU1 still failed its free-memory gate, so no valid Smoke 002 was launched. At the latest check (15:26 UTC), `nvidia-smi` showed 7,835 MiB in use on GPU1 and 15,509 MiB in use on GPU2, corresponding to 16,729 MiB and 9,055 MiB free, respectively; both were at 0% utilization and below their frozen free-memory thresholds. Available RAM was 438 GiB, with 192 CPU threads. No valid model inference was started, and other GPU work was left untouched.

Smoke 001 did run before the environment resolution issue was discovered. Both reviewers returned five syntactically valid outputs, but `conda run` selected `/root/miniconda3/envs/python39/bin/python` (Python 3.9.20, Torch 2.5.1+cu118, Transformers 4.57.6), rather than the frozen `think2sql_train_20260909` runtime (Python 3.10.21, Torch 2.6.0+cu124, Transformers 4.57.1). It is excluded from all review gates and metrics. Amendment 002 pins the absolute target-environment executable and new Smoke 002 / Full 002 run IDs.

## Results, current decision, and limits

**Latest resource recheck (2026-11-08 16:41 UTC):** GPU1 had 3,615 MiB free and GPU2 had 2,341 MiB free; both were at 100% utilization. Available RAM was 434 GiB. The frozen GPU gate remains closed, so Smoke 002 and Full 002 have not run.

The packet-construction and format gates passed. Smoke 001 had 5/5 valid outputs for A and B and the private aggregator returned `SMOKE_PASS`, but that result is invalidated by the runtime deviation and cannot authorize Full. It has no scientific validity, agreement, confidence, or adjudicability metrics. The active run IDs are p0_bird_train_fk_model_proxy_review_20261107_01_smoke_002 and p0_bird_train_fk_model_proxy_review_20261107_01_full_002; both remain pending because the latest GPU memory and utilization gates failed.

Protocol-deviation Smoke 001 used 10 local model calls: Reviewer A recorded 1,794 input / 230 output tokens; Reviewer B recorded 1,814 input / 301 output tokens; combined 3,608 input / 531 output / 4,139 total tokens. All ten usage records are known. Aggregate GPU generation time was 15.107 seconds. External API requests and API spend were zero. These calls remain in the ledger but are excluded from experimental metrics. Any subsequent local GPU time will be reported separately, without converting it to a provider bill.

The model outputs, if run, remain proxy labels. BIRD train is public training data with prior local use, the table pair is SQL-derived, and both models come from the Qwen family. None of these labels can be described as human consensus, ground truth, or an independent test result.

## Reproducibility

The committed config and scripts freeze input hashes, sample rules, run IDs, prompt runner, model IDs, environment versions, token ledger, GPU gates, and stop rules. Amendment 002 is active: after GPU1/GPU2 and RAM gates pass, run Smoke 002 using the absolute Python executable for `think2sql_train_20260909`. If each reviewer returns at least four valid outputs out of five, run Full 002 once. Otherwise stop and retain all files. If Full finishes, append anonymous metrics and resource/token accounting to this report and update the local resource index. The superseded Smoke 001 outputs remain private and are not included.

The recovery packet-preparation command was:

    CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 PYTHONHASHSEED=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 timeout --signal=INT 600s conda run --no-capture-output -n think2sql_train_20260909 \
      /root/miniconda3/envs/think2sql_train_20260909/bin/python \
      scripts/text2sql/prepare_p0_bird_train_fk_model_proxy_review.py \
      --config configs/text2sql/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.json \
      --expected-config-sha256 ea64b20e0594593a155b98a6869b96bad16505c19fa97e6120f90373f6a0fa42 \
      --run-id p0_bird_train_fk_model_proxy_review_20261107_01_packet_prep_002 \
      --repo-root . --expected-commit 23c3570c8d90982b7b2ff450c9c73cb4a2a9701d \
      --train-json /mnt/liansp3/sources/datasets/bird/train/train.json \
      --train-tables /mnt/liansp3/sources/datasets/bird/train/train_tables.json \
      --dev-tables /mnt/liansp3/sources/datasets/bird/dev/dev_tables.json \
      --audit-evidence /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/amendment_001_full_001/candidate_evidence_private.json \
      --audit-summary /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_constraint_identity_20261107_01/amendment_001_full_001/aggregate_summary.json \
      --output-dir /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_model_proxy_review_20261107_01/packet_002

The packet-only preflight used scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py with --preflight-only, the two private packet paths, reviewer A, Smoke mode, the frozen Smoke run ID, and the local Qwen2.5-Coder-7B-Instruct alias. It returned PASS for 138 review units and 369 candidates. It did not load the model or initialize GPU inference.
