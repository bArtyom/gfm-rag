# Residual-semantic route selection: bounded exploratory pilot

Written after the registered terminal-envelope diagnosis, before route outcomes.
Initial >=50% outside-envelope criterion failed:126/296=42.57%,170/296 inside.
The first-stage decision therefore selects path-choice investigation; do not
silently promote terminal replacement. The diagnostic envelope1408/1534 is a
union over alternatives, not one feasible tree or a cost-matched oracle.

Core hypothesis: raw edge/query cosine repeats semantics already explained by
fixed seed tables; internal route nodes should instead explain the remaining
question semantics. Retain the same three seeds and graph. Enumerate all
inclusion-minimal terminal trees in each component (k<=3), then rerank only trees
with no more tables AND no more Qwen generator schema tokens than the frozen
weighted baseline. Graphs never gain edges; FK identities remain preserved.

Three arms, same candidate catalogue/information/budget:
1. Frozen query-weighted Mehlhorn baseline, replayed without modifying old files.
2. Raw-semantic bridge control: select highest max column/query cosine among
   nonterminal tables; tie by old weighted cost, then canonical edges/nodes.
3. Residual-semantic bridge: for each seed pick its most query-aligned column,
   orthogonally project query AND candidate columns off the span of those three
   witnesses (SVD tolerance1e-8). Score max remaining cosine on nonterminal tables;
   fall back to raw if query residual norm<=1e-8. Same ties. No learned parameters.

Both scores choose one strongest additional witness, not a complete demand
decomposition; likely failure: residuals amplify embedding noise or omit meaning
that overlaps anchor semantics. Original minimal tree remains an eligible candidate.
No-bridge tree score is0. More tables/tokens never buys a win. This is a concrete
mechanism probe, not a claim that orthogonal projection, graph enumeration, or
semantic reranking is novel by itself. Strong prior-art overlap remains to assess.

Reuse frozen query/column vectors, tokenizer and schema serializer; no new model
forward passes. Same question-only retrieval input. Online ranker takes no labels.
Small synthetic brute-force catalogue tests and five label-blind engineering
smoke cases first. Pilot100 DB-balanced hash seed20261111/saltresidual-route-v1,
excluding all133 distinct questions exposed by the prior SQLpilot/diagnostic.
This is still previously explored BIRD-dev, not independent test evidence.
All predictions sealed before evaluation. Report reference-table coverage,
rescue/damage, perDB, table/token counts, catalogue sizes and exact within-budget
reference-complete oracle (diagnostic only, never used by ranking).

Pilot upgrade gate: residual complete>=frozen baseline AND >=raw control+2,
all per-question table/token constraints valid. If it fails, STOP this candidate,
no parameter tuning/full/SQL. If it passes, one unchanged CPU1534 run, and require
>=2pp over BOTH controls plus positive net cases in at least2DBs before any local
7B SQL followup. Followup would be separately logged, <=3arms/100questions/500
actual calls/2GPUh; no paid API. At most one new method candidate this turn.

Resource budget1800seconds/stage,8CPUthreads,4GiBRSS target,catalogue<=100000trees
per distinct graph/terminal set. New results terminal_blindspot_bird_20261111_01/
route_pilot_001; debug smoke underai_temp_code, no overwrites. Source/config/inputs
committed before execution; no model calls, GPUtime or token charges in CPU stages.
