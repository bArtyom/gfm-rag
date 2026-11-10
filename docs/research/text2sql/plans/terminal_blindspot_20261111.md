# Fixed-terminal structural blindspot investigation

2026-11-11 UTC+8, explicitly user-authorized research/experiments; exploratory.
One core hypothesis: with fixed terminals, missing reference tables outside the
union of terminal-to-terminal simple paths are unreachable by any inclusion-minimal
Steiner forest, so changing edge costs cannot repair the dominant omission mode.
This is an application of a classical graph fact, not a novel graph theorem.

Owned repo bArtyom/gfm-rag; new branch research/steiner-terminal-blindspot-20261111,
local parent f103e2f5d63fa99e5ad09d19a252c5e0356dd8ae, equal-tree public parent
712e874e24099d476cb3db218720f2589298abc5. Read README, text2sql hub/roadmap/
contract and frozen Steiner/SQL code and reports. Upstream GRAST checkout remains
unchanged at4c698cae; no LICENSE exists, no upstream code vendored or published.
User requests autonomous method discovery and trials; no extra approval gate for
reversible bounded experiments, consistent with laboratory instructions.

Stage1: CPU-only mechanism diagnosis on the existing1534 BIRD-dev questions,
frozen k3 terminals and prior unit/weighted selections. No new model, scoring,
selection tuning, SQL generation or raw-data changes. Preserve original results.
Compute exact path-union envelopes using a block/vertex incidence forest pruned
to terminal support; independently check by all-simple-path enumeration on tiny
random graphs and all distinct real(graph,terminal) combinations where bounded.
Envelopes contain alternatives, not a single executable tree, and their gold
coverage is a diagnostic upper bound, not a deployable model result.

Record: forest/cycle structure by DB, envelope=baseline frequency, observed misses
outside/inside envelope, same-component vs unseeded-component omissions; maximal
possible full reference coverage under any positive edge costs; previous SQL-loss
case association. Gold is used only after envelope outputs have been sealed.
Budget1800wallsec,8CPUthreads,4GiBRSS target; five-case smoke then all1534 if
invariants pass. Failure/hash drift stops. No model/GPU/paid API in this stage.

Decision: if >=50% of baseline incomplete cases contain a required table outside
the envelope, prioritize terminal-set intervention instead of edge/solver tuning.
Otherwise investigate path choice; no automatic hyperparameter search. Subsequent
intervention, if warranted, must be documented before execution, with <=3 groups,
fixed sample/budget and no reused tuning labels. At most one method pilot in this
turn, then synthesis; no indefinite branches. Claimed innovation requires prior-art
positioning and causal mechanism evidence, not a new acronym.

Prior-art checked2026-11-11: GRAST-SQL(arXiv2512.16083), Graph-Link(PMLR306/zhong26s),
RoSL(EMNLP2025industry122), bidirectional schema linking(arXiv2510.14296v2),
EviLink(arXiv2605.29670v1). Graph connectivity, question decomposition, optional
terminals/prizes, multi-path uncertainty and table/column union are prior ideas;
none will be claimed as new alone. Public report will preserve source links,
actual data/versions/commands/config/hardware/hashes/unknowns and negative results.
