# Closure cost timing pilot (exploratory, 2026-11-12 UTC+8)

Owned bArtyom/gfm-rag; local basee798085, equivalent publicparent2149fac7da6b160d738b4fef5dded9c6803cb2c8.
Read rootREADME/text2sql README/roadmap/contract, QAFD cost report and frozen cache/serializer/loader code.
QAFD unchanged upstream2a3a42c8ea4e9c416de0a7fe53c04fab50b756ef;
GRAST unchanged loader identity4c698cae31da8299deb5c809101d172d5b2ddeb3.
Neither full official pipeline is reproduced. No upstream vendoring.

Outer-loop decision: previous whole-table worst-cost capacities failed74/74/72.
Do not tune that stopped candidate. New single hypothesis: postponing connector
cost until after semantic column selection discards useful columns under a hard
budget; considering exact closure cost during column admission can preserve
reference SQL expressibility. Column selection/Steiner/keys are known GRAST/
Graph-Link mechanisms; no novelty is claimed for this intervention.
Primary closest sources: https://arxiv.org/html/2512.16083v1 and
https://proceedings.mlr.press/v306/zhong26s.html ; QAFD paper
https://arxiv.org/html/2605.18775v1 . This is not full literature novelty clearance.

Three arms, same question-only cached vectors, Qwen tokenizer, exact per-question
old weighted-Mehlhorn schema capB:
1 whole_dense: all columns of semantically ranked tables, append only if exact
serialized full-table schema fitsB; same prior QAFD dense control.
2 late_closure: semantic columns descending cached cosine/table-independent;
append while the partial schema without FKs/bridges fitsB. Compute deterministic
FK closure; while it exceedsB remove lowest-ranked retained semantic column and
recompute. No refill. Report rejection/repair costs; custom baseline, not official
GRAST or strongest possible repair algorithm.
3 early_closure: same semantic column ordering. For each column propose union with
selected semantic columns, compute the SAME deterministic FK closure, accept only
if exact serialized context fitsB. Skip rejected columns and continue.

Closure joins terminal tables independently within each actual FK component.
Start from smallest terminal in each component; repeatedly attach nearest
remaining terminal to tree via lexicographically deterministic unweighted
shortest path (distance,target,path tie breaks); this is greedy closure, not exact
Steiner. Selected tables include bridge tables. Retain ALL actual FK constraints
among closure tables, including parallel/composite identities, and all their keys.
Never invent joins across disconnected components. Do not force old three seeds;
column candidates are retractable. Full PK declared only when all its columns are
present. Each arm uses identical partial serializer when given the same columns;
whole-table serialization must match old frozen serializer byte-for-byte.
Memoize closure by terminal-table mask; no gold/reference enters predictions.

5 engineering smoke then100 new DB-roundrobin hash pilot; exclude233 old cases
plus previous QAFD100=333. Salt closure-cost-v1:20261112. Smoke subset primary.
Seal all predictions before reference evaluation. No model/API/GPU calls or
installations. Existing think2sql Python3.12/numpy/networkx/transformers/sqlglot.
CPU8threads,1800s each stage, targetRSS4GiB. No full1534/SQL generation this turn.
At most one independent second100 only if primary gate passes, fresh hash/same
config/excluded prior pilot; no tuning. Otherwise stop new candidate.

Primary: reference SQL can be prepared by SQLite EXPLAIN QUERY PLAN on empty
in-memory physical-schema stubs using retained columns. No query execution/data
reads; no EX claim. Original full schema must prepare first. Reject projection
stars(except COUNT(*)), NATURAL/USING joins, qualified catalog names and any
unqualified double-quoted column as unknown (avoid semantic false positives).
Record unknown in full denominator, never count it correct. Full schema failure
also unknown. Shared evaluator across arms. Table coverage is diagnostic only.
Synthetic tests exercise aliases/nesting, missing columns, star/quoted traps,
FK composite integrity, disconnected closure and exact budget boundary.

Gate: early confirmed-compatible>=late+3 AND>=whole_dense, zero budget violation.
Need>=90/100 evaluable or stop for measurement issue. Success permits only one
unchanged100 confirmation requiring same gate; no automated GPU/SQL expansion.
Report paired rescue/damage, table coverage, tokens, semantic/connector columns,
late repair incidence, perDB counts, failures and exact config/source/input seals.
This is exposed BIRD-dev and only syntactic reference expressibility, not semantic
sufficiency or correct SQL generation. Any positive result remains exploratory.
