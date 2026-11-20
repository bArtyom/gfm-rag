# Budget-feasible repair supervision: trained pilot, overall no-go

2026-11-21 UTC+8. Exploratory run `budget_repair_attention_bird_20261121_01`.
Owned repository bArtyom/gfm-rag; branch research/budget-repair-attention-20261121.
**Three real small vector-model training runs completed.** Full reference-read
binding retention independent/global/repair/whole-dense=52/50/64/79 out of100.
Repair helps the two learned comparators but fails the overall registered gate.
A posthoc untrained starting-score control gives68/100. Stop this version; no
loss/seed/model sweeps, full1534, SQL generation or follow-up training launched.
No innovation or overall retrieval/SQL advantage established.

## Question, insight and proposed mechanism

Prior experiments showed table coverage can improve while fields required by
reference SQL are lost. Ordinary global attention is already covered by prior
work. The single new hypothesis here: supervise attention with an **actual
budget-feasible schema repair**, rather than only independent relevance labels.
For a training query, obtain the current budgeted field selection. Find an
omitted reference-read field, propose adding it, and greedily remove selected
non-reference semantic candidates until exact FK closure+serialized token cost
fits the same budget. Protect every reference-read field and table currently
retained. A nontrivial successful exchange is a training certificate, not a
minimum repair, an optimal solver or a deployable semantic correctness proof.

The attention model learns to rank the added field above the mean removed-field
score via a softplus margin term, in addition to the common balanced BCE.
The loss primitive, hard-example mining and global attention are not claimed
new; possible differentiation is the supervision defined by exact feasible
schema exchanges. This pilot does not establish its novelty or isolate its
value from ordinary extra hard-positive weighting.

## Protocol, guides and prior art

Read owned rootREADME/text2sql README/experiment-roadmap/reproducibility-contract,
resource index, QAFD/closure reports, frozen loaders/serializer/SQLite-binding
helper and local environment before execution. [Protocol](../../plans/budget_repair_attention_20261121.md)
and [config](../../../../../configs/text2sql/budget_repair_attention_bird_20261121.json)
were locally committed before smoke. All6 frozen code/config/protocol files
were publicly archived and fetched back exactly before formal GPU training:
first663ddb0a0355aa87649d4db71f49f21d33e9e247, then identity-guard correction
8912100aadae1e76e601a12c2315ee58a7bc8df0, tree324a587964c91011d3ff02e4f84866c4ef5221b5
matching local0b330c7. Starting publicparent124fd30/local0376a89.

Closest inspected primary sources:
- [AttnLink](https://arxiv.org/html/2608.00693v1): attention-derived schema ranking
  and set-mass/adaptive-floor supervision already address multiple necessary items.
- [JOLT-SQL](https://arxiv.org/html/2505.14305v1): bidirectional attention and
  confusion-aware noisy-schema training are prior mechanisms.
- [RAT-SQL](https://aclanthology.org/2020.acl-main.677/): relation-aware schema attention.
- [GRAST-SQL](https://arxiv.org/html/2512.16083v1): learned column ranking and key closure.
- [QAFD](https://arxiv.org/html/2605.18775v1): query-aware diffusion/learned-edge future
  direction motivated this exploration; this new owned prototype does NOT run
  the original QAFD or reproduce its paper scores/theoretical guarantees.

Original QAFD upstream remains separate/read-only at2a3a42c8ea4e9c416de0a7fe53c04fab50b756ef
(no LICENSE found in prior audit). Original pipeline command is python
benchmarks/run.py --task text2sql --dataset spider2-lite --questions10; not invoked.
Inherited GRAST resource identity4c698cae31da8299deb5c809101d172d5b2ddeb3 is checked
by the loader, not a full GRAST reranker reproduction. No upstream code vendored
or modified. No claim of outperforming these official systems.

## Data and supervision contract

Frozen BIRD-dev1534/11DB, aligned SQLite metadata, cached Qwen3Embedding0.6B
1024D question/schema vectors. Question-only vectors; evidence is not newly
encoded. All data/cache/database/tokenizer hashes and aliases are in config.
No new Qwen/LLM/embedding forwards or model downloads. Graph rankers consume
vectors directly: their forward inputs are graph nodes/features, not text tokens.

Before reference labels, select3 testDBs by SHA256(repair-db-v1:20261121:db),
leave8 trainingDBs, sample320 training cases DB-roundrobin hash.317 have supported
full-stub physical read labels,3 unqualified quoted-column cases unknown and
excluded from training with counts retained. Same317 cases/order for all arms.
Test100 cases from the3DBs exclude all433 prior SQL/route/QAFD/closure cases;
5 smoke test cases are a subset. No replacement or test-driven split changes.
This is DB-heldout for this run, but BIRD-dev/embeddings have prior exposure;
NOT an independent external benchmark or unseen-data scientific replication.

Training reference SQL is compiled on empty full TEXT-schema stubs using SQLite
authorizer, recording physical table/column reads. COUNT(*) can give table targets
without column positives. These are reference-binding targets, not unique
semantic necessities. Test reference SQL values are not used until checkpoint,
score and final selection seals exist for ALL models. Mixed source JSON contains
reference fields, but only selected train keys access SQL during preparation.
The loader strips reference fields from online question features.

## Models, loss and exact budget

Independent468385parameters; global and repair468577each. Input per node is
[node vector,query vector,elementwise product,owner-table vector],4096features,
plus table/column type. Hidden96, heads4, no positions/dropout. Independent uses
a pointwise FF block; global uses one self-attention block over all schema
nodes plus FF. Parameter counts nearly match; architectures differ as recorded.
No relation-aware attention bias: actual FK structure is used by packing and
certificate construction. These are small models trained from scratch atop
frozen vectors, not tuned Qwen or pretrained attention-probing AttnLink.

Common raw score is cached cosine plus a learned residual head, initialized to0.
Global/repair initial tensors are exactly equal. Common balanced BCE uses
positive/negative means within table and column types. AdamWlr.001/wd.01,
3epochs, seed20261121, gradient clip1, no validation/best-checkpoint selection.
Same shuffle every epoch across arms. Final field rank=fieldscore+.25owner-table
score. Repair adds.25*softplus(mean_removed_score-added_score+.1), only when
an actual nonempty feasible exchange exists.237 certificate events span7trainDBs
(72/79/86 across epochs), not237 necessarily distinct queries or requirements.
One lowest-score omitted reference column is considered per query update; greedy
removals are not minimum and certificates do not cover every failure.

All fields are considered without gold-based candidate filtering. The same prior
deterministic nearest-terminal FK closure runs within actual connected components,
retains all internal parallel/composite FK identities and all their key fields.
No fabricated edges or forced old seeds. Exact Qwen2.5-Coder7B tokenizer partial
DDL cost, PK only when all fields retained, same per-query old weighted-Mehlhorn
full-table budget B. Admit ranked columns only if whole closure fits; skip and
continue. Whole-dense no-training control packs complete semantically ranked
tables under the same ceiling. Actual spending differs; all budgets verified.
No token-cost capacity heuristic from the stopped QAFD experiment reused.

## Results and stopping decision

| Method | Complete original reads /100 | Actual schema tokens total | Fields total | Tables total |
|---|---:|---:|---:|---:|
| Independent BCE |52|44780|4139|437|
| Global attention BCE |50|44791|4200|420|
| Global attention + feasible repair |64|44781|4293|404|
| Whole-table dense, no training |79|44869|4642|316|
| Initial algebraic score, posthoc |68|44788|4309|405|

99 supported test references,1 unknown quoted-column case retained in100.
Primary is all original physical read table/column bindings retained, with
syntactic preparability as secondary (counts happen to agree here). Neither
is SQL semantic correctness or execution accuracy. No SQL data-result execution
or generator was run. Empty stub types/constraints differ from original catalog;
reference bindings are not necessarily the only valid answer implementation.

Repair versus independent rescues14/damages2; versus global rescues14/damages0;
versus whole-dense rescues5/damages20. Unknown1 in each pair. PerDB counts:
DB01 independent/global/repair/dense35/35/35/35 (36cases,1unknown);
DB02 10/10/20/22; DB03 7/5/9/22 (32cases each). Improvement versus both learning
baselines is positive in2DBs, but the strong baseline wins overall by15cases.
The fully retained/saturated firstDB does not distinguish methods.

Registered gate:>=90evaluable,>=30certificates spanning>=2trainDBs, repair at
least+3 over BOTH learning baselines AND>=whole-dense, positive over both in>=2/3
DBs, zero budget violations. All components pass EXCEPT matching whole-dense;
overall gateFALSE. STOP_THIS_VERSION, no seed/loss sweep or large expansion.

After observing primary counts, [a separately recorded posthoc diagnostic](../../plans/budget_repair_initial_score_audit_20261121.md)
checks the zero-head starting score using cached dot products and the identical
packer; no network forwards, new training or parameter changes. It retains68,
versus repair64; repair rescues7/damages11. This was not a preregistered primary
comparator, does not replace the gate and supports the narrower interpretation:
repair offsets part of small-data learning degradation, not a demonstrated gain
over the pretrained semantic starting score or whole-table control.

## Verification and actual compute

Five meaningful synthetic tests pass: global permutation equivariance,
pointwise/global context behavior, preserved read bindings, COUNT-table protection,
and closure-cost-aware multi-field repair. Expected RED collection failure before
implementation retained. Read-only review identified missing tokenizer/reference
identity guards; these were fixed and republished before formal GPU training.
prepared002 split/targets exactly equal001; second smoke after identity fix has
identical scores/seals/checkpoints to first. Both smoke runs are charged in compute
and all smoke weights are discarded. No scientific configuration changed.

Audit PASS:300 final-checkpoint CPU forward replays, maximum GPU/CPU score
difference8.95e-7;400 exact selection budgets;237 nontrivial repair certificates;
317 training targets recompiled;3153 formal graph forward records, all counts,
split/seals/checkpoints/primary gate verified. Model parameters changed in all
three training runs. Shares serializer/closure/reference helpers; optimization
gradients are not independently replayed. Posthoc algebraic baseline has100 more
packing checks and no model forward. No silent score correction.

Formal each model951optimizer steps (317x3), total2853, plus300test forwards=
3153GPUforwards,255039node units. Two smoke runs add60GPUforwards; CPU audit300,
so this turn3513graph-model forwards,283923input node units. These are NOT
language tokens. No API-ledger rows fabricated for vector operations.
Formal GPU forward2.607sec/backward+optimizer13.692sec; including both smokes,
CUDAevent intervals17.784sec. Intervals are not exclusive GPU-busy accounting.
Formal model+packing wall89.189sec/processCPU92.875sec, including smokes total
model-stage wall108.649sec, excluding preparation/audit/research overhead.
Peak formal PyTorch GPU allocation83761152bytes (~79.9MiB), not total driver
VRAM. GPU2 exited and freed; other workloads untouched. CPU8threads,192logical
CPUs/~445GiB RAM available at preflight. Existing Python3.12.14/torch2.8.0
CUDA12.8/numpy2.2.6/networkx3.6rc0/transformers4.57.1/sqlglot28.0.0; no installs.
GPU>=4GiB free,<=2GiB PyTorch allocation,<=5000forward and1800s/stage budgets met.

## Artifacts, reproduction and limits

Actual training source local0b330c7 (public equivalent8912100a...); auditd9dd1eb,
posthoc68be023. Full hashes/dependencies/parameter checkpoint seals in manifest.
Formal prediction SHA495268febca47c7b81bf04da10ed5cb119b4373f7fbf1fdfed8b9945d6887ad0.
Configff68e45c963c916ec4882ecb815c4bc3c781ddd34a6e83fb9afe16b283108365;
split4cae8b9af1b84e5cef61c555d8bbacede32debb6e0e7beae452b3e4733f6f363;
train targets d7c192df54f42c8872b9521c4c638527975f31491d1d4f0f1c102ad4b3faca05.
All code/config/protocol hashes, aggregates and anonymous compute are public;
private questions/SQL/IDs/readsets/embeddings/scores/repair events/checkpoints stay
local under results/budget_repair_attention_bird_20261121_01. Three exploratory
weights in pilot_001/{independent,global,repair}_final.pt are not defaults and
are not uploaded. Logs under logs/same-run; engineering outputs under ai_temp_code.

At project root set LAB_ROOT to resource root and SQL_ENV_PREFIX to the existing
think2sql environment. Set OMP/OPENBLAS/MKL threads8, TOKENIZERS_PARALLELISM=false.
GPU training needs CUDA_VISIBLE_DEVICES=2 and CUBLAS_WORKSPACE_CONFIG=:4096:8.
Use fresh directories (never overwrite). Exact input aliases/hashes required:

```bash
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" -m pytest tests/test_budget_repair_attention.py -q
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/prepare_budget_repair_attention.py --config configs/text2sql/budget_repair_attention_bird_20261121.json --output ai_temp_code/repair_prepare_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_budget_repair_attention.py --config configs/text2sql/budget_repair_attention_bird_20261121.json --prepared ai_temp_code/repair_prepare_replay --mode smoke --output ai_temp_code/repair_smoke_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_budget_repair_attention.py --config configs/text2sql/budget_repair_attention_bird_20261121.json --prepared ai_temp_code/repair_prepare_replay --mode pilot --output ai_temp_code/repair_pilot_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/verify_budget_repair_attention.py --config configs/text2sql/budget_repair_attention_bird_20261121.json --prepared ai_temp_code/repair_prepare_replay --execution ai_temp_code/repair_pilot_replay --output ai_temp_code/repair_verify_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/audit_budget_repair_initial_scores.py --config configs/text2sql/budget_repair_attention_bird_20261121.json --execution ai_temp_code/repair_pilot_replay --output ai_temp_code/repair_initial_replay
```

CPU verifier is read-only checkpoint inference; set CUDA_VISIBLE_DEVICES='' for
CPU replay. Existing resources and input hashes required for reproduction;
public archive alone does not contain private benchmark caches.

Decision: retain the local supervision signal as exploratory evidence; stop the
current globally reranking configuration. Whether exact feasible certificates
outperform ordinary hard-example weighting is unresolved. Any future mechanism
should preserve a strong initial selector and learn a small number of proposed
schema exchanges with a no-op option, rather than assume a learned global rerank
is superior. That action-policy variant is NOT implemented, trained, or claimed
novel/safe/effective here. No more GPU work this turn.

Experiment language-token input/output/total0/0/0, unknown0, externalAPI0CNY;
localGPU/CPU unpriced, not free. Usage snapshot includes the shared ledger's
confirmed cumulative tokens/unknown requests and priced-CNY portion, not complete
supplier-account spending or verified billing. Vector units/GPU work are reported
separately and old embedding usage is not charged again.
