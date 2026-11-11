# QAFD: feasible diffusion with context-cost capacities

2026-11-11 UTC+8, new user-authorized QAFD-based discovery, exploratory only.
Owned repository bArtyom/gfm-rag, branchresearch/qafd-context-capacity-20261111,
localbaseb9ebcb1c94b614afef0db992219ecd1dfbf1f01c, publicparent092b843d32dda596637c3d9296be1630d78177c2.
Read rootREADME,text2sql hub/roadmap/contract, previous experiment reports. Old
stopped protocols/results remain frozen; this is a new bounded investigation.

Official upstream https://github.com/Tarzanagh/QAFD-RAG cloned read-only at commit
2a3a42c8ea4e9c416de0a7fe53c04fab50b756ef; no LICENSE file found, no vendoring.
Original run: python benchmarks/run.py --task text2sql --dataset spider2-lite
--questions10; default stack requires OpenAI and incompatible additional deps.
Reuse existing numpy/networkx/transformers/scipy CPU environment, no installs,
downloads or paid APIs. Import original core/base files in an isolated package
with a standard-library logger shim; do not load package services/LLM modules.

One core hypothesis: degree-based sink capacities allocate diffusion support in
units unrelated to serialized schema cost; charging actual context cost in sink
capacities can preserve more necessary schema under the same prompt budget.

Stage0 engineering/audit, not accuracy evidence: execute unchanged upstream core
on three tiny graphs and five fixed BIRD graphs at READMEalpha1.5/confidence.7,
500iterations; measure source mass, accessible capacity, final excess/mass loss,
not just returned scores. Check paper/source differences: capacity normalized10,
confidence source scaling, warm-start, structural accumulation vs query routing.
Verify mathematical necessary condition sum injected<=reachablecapacity for
mass-conserving convergence. Do not generalize a code/config issue into a paper
theorem failure, and do not use an infeasible truncated core as the main baseline.

Stage1 method trial, three arms only, cached query/table vectors and same top3
seeds/query-aware edge formula. Positive graph weights from unchanged upstream
get_edge_weight(multiply), baseweight=(cos(table_u,table_v)+1)/2. Graph only actual
FK topology (original composite/parallel constraints preserved in serializer).
This is a controlled BIRD/table-only adaptation, not the full official KG/LLM
Text-to-SQL pipeline or reproduction of published scores.

- Dense: semantic ordering under the exact schema-token cap.
- Feasible degree-QAFD: paper dual/push semantics, zero warmstart, exact mass
  conservation and structural-degree capacities rescaled to sum(cost capacities).
- Context-cost QAFD: same solver/source/weights/packing, capacities c_v computed
  as max_S [C(S+v)-C(S)] over table subsets, floored1, with C the exact frozen
  Qwen-tokenized schema serializer (all selected-table columns and internal FKs).
  Exhaustive tiny-schema preprocessing n<=13; not a scalable algorithm claim.

By telescoping C(S)<=sum_{v in S}c_v (C(empty)=0). From zero x, each positive-x
vertex has mass>=capacity; conservation bounds sum c_v on support by injected
mass. Thus context-cost support has a checkable schema-budget certificate before
packing, even at finite iterations. This is a surrogate/context certificate,
not a semantic correctness or retrieval-recovery guarantee.

BudgetB per question is the previous weighted-Mehlhorn Qwen schema token count.
Run independently from each of3seeds with common mass=min(B/3,.9*min(reachable
degreecapacity,reachablecostcapacity)); sum sources<=B. Same M in both diffusion
arms. Exact deterministic largest-excess push, stop when total excess<=1e-7,
max100000updates/seed; fail on real nonconvergence/negative mass/hash drift.
Normalize x per source and sum. Common packer: descending flow, then dense score,
then tableID; dense-only arm flow0. Add table only if exact C(S+v)<=B, otherwise
continue. Zero-flow items are dense fallback, explicitly counted. No forced seed
retention/Steiner closure in any arm. Shared packer/metadata; no larger budget.

Small-graph tests and stage0 before5 engineering smoke then100pilot. Pilot hash
seed20261111/saltqafd-context-v1,DB-roundrobin, excludes priorSQL133 AND priorroute
100=233questions. Still exposed BIRD-dev, not independent test. Seal all scores/
selections before reference coverage; all denominators preserved, parsefailure
stops. Report complete table coverage, perDB rescue/damage, tokens, support cost,
capacity/KKT/convergence and fallback counts. CPU8threads/1800s perstage/RSS4GiB,
subsetcostpreprocessing<=16384subsets perDB, no GPU/new model calls.

Pilot gate: context complete>=degree+2 AND>=dense+2, no budget violation; else
STOP candidate/no tuning/full/SQL. If pass, one unchanged CPU1534 run; full gate
>=2pp over both and netpositive in>=2DBs, then separately register bounded local
SQL followup. At most one capacity hypothesis this turn; no parameter sweep.
Reports/code/config/hashes/anonymous aggregates only in owned project; private
cases/scores/cache/SQL remain local. Record actual compute and sharedledger totals.
