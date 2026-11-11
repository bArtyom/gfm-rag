# QAFD context-cost capacity: stopped exploratory pilot

2026-11-11 UTC+8. Run `qafd_context_capacity_bird_20261111_01`.
Owned repository: https://github.com/bArtyom/gfm-rag, branch
`research/qafd-context-capacity-20261111`. Negative result; no SQL accuracy measured.

## Question and preregistration

Can replacing structural-degree sink capacity with actual schema-context cost
improve necessary-table coverage at the same per-question token cap?
[Protocol](../../plans/qafd_context_capacity_20261111.md) and
[configuration](../../../../../configs/text2sql/qafd_context_capacity_bird_20261111.json)
were frozen before pilot labels. Exploratory main pilot: 5 engineering smoke
cases followed by 100 primary cases, at most three arms; 8 CPU threads,
1800 seconds/stage, target RSS below4GiB. Success requires context coverage at
least2/100 above BOTH baselines with zero budget violations. Failure stops the
candidate without tuning, full1534, GPU or SQL. This gate failed.

## Sources, implementation and departures

Official source: https://github.com/Tarzanagh/QAFD-RAG at
`2a3a42c8ea4e9c416de0a7fe53c04fab50b756ef`; paper
https://arxiv.org/html/2605.18775v1. Read upstream README, requirements,
base/flow diffusion, answering cluster and schema builder, plus owned root
README, text2sql README, experiment-roadmap and reproducibility-contract.
No upstream AGENTS or LICENSE file found. Unchanged upstream checkout is kept
separate; no third-party code vendored or modified. Original command:
`python benchmarks/run.py --task text2sql --dataset spider2-lite --questions 10`.
Its full OpenAI/service/dependency pipeline was NOT run. Existing local CPU
environment was reused without installations; it differs from upstream pins.
Original core/base are loaded through an isolated package and stdlib logger shim.

Native audit uses original initialize/run code on3 toy+5 BIRD graphs:
alpha1.5, confidence.7 gives injected mass25.5 against total sink capacity10.
All8 successful audit cases fail the necessary reachable-capacity condition and
retain approximately15.5 excess after500 iterations. This is a bounded code/config
finding, NOT a refutation of paper theory or published end-to-end results.
The README alpha and caller confidence were composed for this audit; defaults
and other configurations must not be generalized from it.

Main comparison is a controlled BIRD table/FK adaptation, NOT official QAFD
reproduction. It uses cached Qwen3Embedding0.6B query/table vectors and frozen
three seeds. Topology is schema-only. Original multiply query edge factors are
used unchanged. Base affinity is shifted/clipped dot product of cached nearly
unit-normalized float32 table vectors; upstream query factors recompute cosine
in Python float64. This numerical detail is frozen and checked.

New feasible solver starts x=0 and conserves mass under paper-dual coordinate
pushes: weighted-degree update, deterministic largest excess, tolerance1e-7,
max100000 updates/source. Each source injects the SAME mass in both arms:
min(B/3,.9 times the smaller reachable capacity total of the two arms).
Degree capacities sum to the same total as cost capacities.

C(S) is exact frozen Qwen2.5-Coder7B tokenizer cost of all columns and internal
FK constraints of selected tables. c_v=max(1,max_S[C(S+v)-C(S)]).
All10240 subsets across11 databases, each<=13tables, were enumerated.
Telescoping gives C(S)<=sum c_v. Positive-x nodes have absorbed their capacities;
conservation bounds support capacity by injected mass, including finite
iterations. Unioning three supports therefore fits B. This certifies context
cost only; it says nothing about semantic recovery. Exponential preprocessing
is a tiny-schema prototype and not a scalable method claim.

All arms share the exact packer: sort by flow score, then cached dense score,
then tableID; append only if exact C(S+v)<=B. Zero-flow nodes are explicitly
counted dense fallback. Dense arm has zero flow. No forced seed retention or
Steiner closure. B is the prior frozen weighted-Mehlhorn schema token count.
Original composite/parallel FK identities remain in serialization; routing graph
is simple undirected table adjacency. Unused inherited SQL/GPU configuration
fields are not read by this CPU runner and did not start services or inference.

## Data, sample and versions

BIRD-dev1534/11 aligned databases and inherited validated caches; paths and
SHA256 hashes of questions, schemas, databases, embeddings, model/tokenizer,
previous predictions and exclusions are in the frozen configuration.
Sampling uses salt qafd-context-v1:20261111 and DB-roundrobin hash ordering.
Exclude prior SQL133 plus prior route100=233 cases. Engineering5 are a subset
of primary100. This is exposed development data, not independent held-out data.
Seal all predictions BEFORE reference SQL table-label extraction; labels are
used only for coverage recount. Reference parser is shared with prior work.

Local pilot implementation commit `dc043d4d6f702a731e3273eca04426d924f33ad9`;
cost-cache code `02a74d3abbed368e08b68b14c0881e774c8746f4`;
native audit code `f29f8364d384a529e968f799dc7bbb17a18b4871`.
Owned local base b9ebcb1c94b614afef0db992219ecd1dfbf1f01c; equivalent public
parent092b843d32dda596637c3d9296be1630d78177c2. Public archive squashes this
turn onto that parent, preserving the final tree. Inherited GRAST loader
checkout4c698cae31da8299deb5c809101d172d5b2ddeb3 is only a frozen resource
identity check, not a full GRAST reproduction.

## Results

| Arm | Complete reference-table coverage | Selected tables total / mean | Actual schema tokens total / mean | Dense fallback tables | Flow updates |
|---|---:|---:|---:|---:|---:|
| Dense |74/100|335 /3.35|49480 /494.80|335|0|
| Feasible degree diffusion |74/100|335 /3.35|49480 /494.80|166|1152|
| Context-cost diffusion |72/100|341 /3.41|48972 /489.72|197|779|

Same per-question ceilings, not exactly equal actual spending. Context versus
either baseline: rescue0, damage2, unchanged98; both losses in DB-05.
No budget violations or support truncation in any arm. Context uses dense
fallback for197/341 selected tables; do not attribute the whole result to flow.
No SQL generation/execution accuracy measured. Different samples/budget/seed
rules mean74/100 cannot be directly compared with old80.70% full-dev Steiner.

Pilot wall7.779sec, processCPU8.265sec, peakRSS.1085GiB; cache wall10.670sec;
verification wall11.244sec. These are stage/process measurements, not complete
end-to-end CPU accounting. Resource checks found192logical CPUs/~431GiB
available RAM; GPUs were inspected but not used. Python3.12.14, numpy2.2.6,
networkx3.6rc0, transformers4.57.1, sqlglot28.0.0 in existing
think2sql_20260909. No dependency installations, model forwards, GPU or API calls.

Four small-graph tests passed. Independent check re-tokenized10240 subset costs,
validated600 flow states and300 packings, and recounted labels, pairs and gate.
Maximum primal-dual error6.26e-13, conservation error2.28e-13. Verification shares
loader/tokenizer/serializer/reference parser, so is not wholly independent.
Prediction seal87b8f86bf2d6b775699b8df8eaeacd315a674472b1006d2064a6b76f28ff3a4f.
Config/cache/serializer hashes are in the public receipts.

## Failures and recovery

Native audit001 executed8 cases but failed exporting NumPy scalar counts;
explicit scalar conversion fixed export and identical002 reran8 (16 actual
core executions total,8 unique audited cases). Smoke001 failed prediction
serialization before seal/evaluation; int conversion fixed it and identical
smoke002 completed. No score from failed exports was used. Verification001
incorrectly renormalized the producer's base float32 affinity; corrected
verification002 matched producer weights and passed. Original failed directories
and logs are retained, no results overwritten. No scientific parameter tuning.

## Diagnosis, decision and possible next hypothesis

Both loss cases omit a required115-column table. Its worst-context capacity1434
exceeds the entire1105-token budget and each source mass368.33, so it cannot be
in positive-x support. Yet dense's actual three-table schema fits the same cap.
Context instead selects six tables. This establishes an overly conservative
surrogate and unavailable flow support for the missed table; it does not isolate
all causal contributions of the score ordering/dense fallback.

Decision: STOP this whole-table worst-case-cost capacity candidate. No full1534,
SQL, GPU, parameter sweep or second method was launched. Innovation and retrieval
gains are NOT established. Query weighting, flow, capacity and multi-source ideas
already exist in QAFD and must not be claimed new.

Untested next hypothesis: represent query requirements by alternative column
witnesses; treat seeds as retractable proposals; score marginal uncovered
requirements while charging the actual added columns, required FK keys and
serialization cost. Share witness/connector costs once. A further experiment
would first need a precise feasibility rule and same-budget dense/column baseline.
This note is not an approved positive result, new experiment, or novelty claim.

## Reproduce and artifact scope

Set LAB_ROOT to your lab resource root; provide the exact hashed data/cache/model
aliases from the configuration. Set SQL_ENV_PREFIX to the existing environment
prefix (the interpreter path must be explicit because this host PATH can shadow
conda-run python). Existing environment commands (run at project
root, with OMP/OPENBLAS/MKL threads8 and TOKENIZERS_PARALLELISM=false):

```bash
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" -m pytest tests/test_qafd_context_capacity.py -q
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/audit_native_qafd.py --config configs/text2sql/qafd_context_capacity_bird_20261111.json --output ai_temp_code/qafd_native_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/prepare_qafd_cost_cache.py --config configs/text2sql/qafd_context_capacity_bird_20261111.json --output ai_temp_code/qafd_cost_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_qafd_capacity.py --config configs/text2sql/qafd_context_capacity_bird_20261111.json --cost-cache ai_temp_code/qafd_cost_replay --mode smoke --output ai_temp_code/qafd_smoke_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_qafd_capacity.py --config configs/text2sql/qafd_context_capacity_bird_20261111.json --cost-cache ai_temp_code/qafd_cost_replay --mode pilot --output ai_temp_code/qafd_pilot_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/verify_qafd_capacity.py --config configs/text2sql/qafd_context_capacity_bird_20261111.json --cost-cache ai_temp_code/qafd_cost_replay --execution ai_temp_code/qafd_pilot_replay --output ai_temp_code/qafd_verify_replay
```

Use fresh output names: scripts reject existing directories. Local original
artifacts live under results/qafd_context_capacity_bird_20261111_01 and
logs/qafd_context_capacity_bird_20261111_01; engineering smoke under ai_temp_code.
Public: code, tests, frozen config/protocol, aggregate receipts, anonymous loss
features and usage snapshot. Private: question-level predictions, scores, flow
states, token subset arrays, SQL and vector caches. No private data uploaded.
Public reproducibility requires separately provisioned hashed input resources.

Usage snapshot is ledger scope only. This turn input/output/total0/0/0, unknown0,
externalAPI0CNY, GPU0seconds; local CPU time is not monetized. Cumulative cost is
known-usage public-price estimate, not verified billing, and excludes unpriced
calls and unknown usage. See usage_snapshot.json for dated totals.
