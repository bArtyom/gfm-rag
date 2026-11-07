# P0 BIRD train FK constraint-level local model-proxy review

**Status: base protocol; protocol-conforming inference has not started.** Smoke 001 produced 5/5 syntactically valid outputs per reviewer under an unintended Python 3.9 runtime; this is recorded as a protocol deviation and excluded. Amendment 002 is the active execution plan. Experiment ID: p0_bird_train_fk_model_proxy_review_20261107_01. This is an exploratory model-review feasibility stage. It creates model-proxy labels only; it does not create human consensus, trusted FK Role labels, or ranking results.

## Research question and hypothesis

For question/table-pair units with at least two distinct, complete FK constraints that were independently verified against SQLite, can two local Qwen models produce enough exact, medium-or-higher-confidence agreement to justify a separately registered exploratory ranking diagnostic?

The hypothesis is that a larger, eight-database candidate pool than the earlier 60-unit BIRD-dev review may yield at least 30 high-confidence, adjudicable exact agreements and at least 20 distinguishable agreements. Agreement is not correctness. The two models share the Qwen family, and Qwen3-4B is fine-tuned for Think2SQL, so correlated errors remain likely.

## Scope, layer, and limits

- Layer: pre-main-experiment exploratory annotation-feasibility gate.
- The source is BIRD train. It is public training data and has prior use in other local work, so results are exploratory and are not an independent benchmark result.
- The input universe is the 138 exact-aligned units with at least two distinct complete SQLite FK constraint signatures in the identity audit's 379 non-Smoke units. Coverage is eight anonymous databases. Use every eligible unit; no label-based or model-based subsampling.
- The known table pair was selected from reference-SQL joins in the prior capacity stage. Reviewers see the question, the two table names, and every complete candidate FK constraint. They do not see SQL, reference JOIN/ON text, database IDs, rankings, scores, or the other reviewer's output. This is not an end-to-end Gold-free evaluation.
- Composite FK components stay together and in SQLite sequence order. The identity audit's candidate universe deduplicates identical complete signatures; the model review therefore compares distinct signatures, not duplicate declaration multiplicity.
- No SQLite is opened and no SQL is executed by this review stage. Existing private audit evidence is the fixed source of candidate signatures.

## Budget and frozen sample

- Smoke: five eligible units, chosen one each from anonymous databases db_01 through db_05, using the minimum SHA-256 order under seed 20261107. This is a resource and response-format gate only.
- Full: one run of all 138 eligible units, including a fresh inference pass on the five Smoke units. Smoke outputs are not included in Full metrics.
- Two reviewers: A is local Qwen2.5-Coder-7B-Instruct and B is local Qwen3-4B-Think2SQL. The same prompt and candidate set are used; case and mapping display order are independently shuffled by deterministic hashes. B runs with thinking disabled.
- Each reviewer has five Smoke calls and 138 Full calls. do_sample=false, max_new_tokens=384, one generation per unit, and no retries or post-hoc prompt edits.
- Per model and stage wall-time cap: 90 minutes. No checkpoint, weight download, package installation, package upgrade, or external API use.
- Environment is the existing think2sql_train_20260909 environment, invoked via /root/miniconda3/envs/think2sql_train_20260909/bin/python. Frozen package versions: Python 3.10.21, PyTorch 2.6.0+cu124, Transformers 4.57.1. No environment changes are allowed.

## Resource gate

Run A only on physical GPU 1 and B only on physical GPU 2, with one model per GPU. Immediately before each paired Smoke or Full launch, inspect nvidia-smi, free -h, and nproc. Require GPU 1 free memory of at least 18,432 MiB and utilization at or below 10%; require GPU 2 free memory of at least 10,240 MiB and utilization at or below 10%. Available RAM must be at least 32 GiB. If a gate is not met, wait and check again; do not terminate, pause, or displace other work. If the GPUs remain unavailable, leave this registration pending and report the blocker.

## Decision and stop rules

- Smoke passes only if each model has at least four of five outputs passing the frozen JSON and candidate-ID semantic validator. Any model-load failure, prompt leakage, input mismatch, or lower validity stops Full; no retry or prompt revision is allowed.
- Full completes only if both reviewers return one output for all 138 units before the time cap. A runtime error, output-coverage mismatch, OOM, hash mismatch, or time-cap breach stops this registration; preserve all partial outputs and do not rerun under the same ID.
- The exploratory follow-up gate passes only when Full has at least 30 exact decision-and-accepted-set agreements with both self-reported confidence values at least 2; among them at least 20 are adjudicable and reject one or more candidates; distinguishable agreements cover at least three anonymous databases.
- If the follow-up gate fails, stop the model-proxy ranking path. If it passes, it only permits a separate preregistration of G-reasoner versus Dense ranking on these proxy labels; it does not authorize a human-accuracy claim or change the human-label gate.
- No additional model, sample extension, label adjudication, parameter sweep, or graph variant is permitted within this registration.

## Models and prompt contract

The runner is the existing scripts/text2sql/run_p0_fk_mapping_model_review_proxy.py, whose complete source hash is pinned in the config. It accepts only single_mapping, multiple_mappings, cannot_determine, no_declared_fk, or other, plus accepted mapping IDs, confidence 1–3, and a rationale code. All current units display at least two declared mappings; selecting no_declared_fk is invalid. For a single mapping exactly one ID is required; for multiple mappings at least two IDs are required; undetermined decisions require an empty ID set.

Each request is isolated. The prompt states that input text is data and not instructions, that the table pair is already supplied, that no Gold SQL or hidden database facts are available, and that multiple mappings may be acceptable. It requires one JSON object and disallows prose or Markdown. Raw generations stay private.

## Frozen inputs and versions

- User-owned project repository: https://github.com/bArtyom/gfm-rag, branch research/p0-sql-used-proxy-alignment-20261107; base commit dd27ec44e485cee9344cf3b23a53625409f0bc98.
- Read before registration: root README.md, docs/research/text2sql/README.md, experiment-roadmap.md, reproducibility-contract.md, and /mnt/liansp3/sources.md.
- Train JSON SHA-256: abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520.
- Train schema SHA-256: 85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b.
- Dev schema SHA-256: 35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97.
- Fixed private identity-audit manifest SHA-256: ff3d379743824eff85f9eec55bffdbf8679e8980ab1f47abbbdc70b86fb01ebf.
- Fixed private identity-audit summary SHA-256: b2bd43b28133fd424005d3e3d4e7b5d21cfc0b43dc9f306c291a6e5bee8bac8c.
- The audit reported 379/379 exact metadata-to-PRAGMA alignment and 138 eligible units across eight anonymous databases. Input hashes and code hashes are frozen in the JSON config.
- Local model paths: /mnt/liansp3/sources/models/qwen25-coder-7b and /mnt/liansp3/sources/models/qwen3-4b-think2sql. Model weights are not copied or published. Existing artifact checksums are recorded in the prior model-review report; current checksums must match before loading.

## Commands, accounting, and artifacts

The frozen config records source paths, hashes, run IDs, model parameters, resource gates, expected counts, script hashes, and private destinations. After this plan/config/code commit is verified on GitHub, the packet preparer creates private A/B packets and a 0600 provenance manifest under /mnt/liansp3/sources/results/gfmrag_p0_bird_train_fk_model_proxy_review_20261107_01/. The existing model runner records each actual local generation attempt through the shared ledger at /mnt/liansp3/.config/api-usage/usage.sqlite3, with stable IDs; unknown usage remains unknown. External API spend is zero. GPU-active time is reported separately and is not treated as cost-free.

Logs go under /mnt/liansp3/logs/gfmrag_p0_bird_train_fk_model_proxy_review_20261107_01/. The sanitized public report and aggregate, if produced, go under docs/research/text2sql/reports/p0_bird_train_fk_model_proxy_review_20261107_01/. Do not publish question text, table names, candidate identities, per-item labels, raw generations, prompts, SQL, databases, model weights, or logs.

## Guide deviations

The repository's historical route required two real reviewers before FK Role ranking. The user explicitly chose model review. This registration therefore uses two local models solely as a labeled proxy feasibility stage; it does not redefine the historical human-label requirement. It also uses BIRD train rather than dev because the independent PRAGMA audit established capacity. The source is public training data with prior local use, so conclusions remain exploratory. Any G-reasoner/Dense comparison requires a new registered plan and a separate report.
