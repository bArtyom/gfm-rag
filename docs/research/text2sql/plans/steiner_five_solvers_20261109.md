# Five Steiner solvers implementation and experiment plan

Status: completed 2026-11-09; exploratory. Two settings x1534questions x5methods
executed,15340 full solver calls plus50smoke. See
../reports/steiner_five_solvers_bird_20261109_01/README.md. Conclude, no extension.
Goal: compare greedy shortest-path attachment, Kou/KMB, Mehlhorn, exact
Dreyfus-Wagner and a certified MILP under identical frozen seeds/schema/weights.
Spec: user explicitly requested all five methods, combined with current experiments.
This is a bounded new solver diagnostic, not a reopening of the stopped weight
formula/embedding/SQL experiments. One question: does changing the solver improve
graph cost or reference-table coverage? Those objectives are reported separately.

Architecture: new extended solver module reuses existing canonical graph/pruning
and DP; new paired runner reuses pinned question/table/FK-vector caches. k=3,
fixed same three table seeds; TWO graph settings only: unit and question-weighted
cost1+(1-cos)/2 with lambda1. Five explicitly requested solvers per setting are
algorithm comparisons, not five independent hypotheses. No added semantic dense
arm, k/weight sweeps, training, GPU, new embeddings, paid API, SQL, or downloads.
Tech: existing think2sql_20260909 Python3.12, scipy1.16.3 bundled HiGHS MILP,
networkx3.6rc0/numpy2.2.6/sqlglot28.0.0. No package changes.

## Frozen data and source

- Owned bArtyom/gfm-rag, existing independent checkout, NEW branch
  research/steiner-five-solvers-20261109, localbase24f7b8d0519676f9b95a963a6c67df15f072f040,
  equal-tree publicparent4030164e73203dda83fdd48dbdd022de746f2eef.
- Read root README, text2sql hub/roadmap/reproducibility-contract, current weighted
  and two-solver reports, runners/core solvers. Legacy dimension/GFM/supervised-role
  gates unchanged; this explicit unsupervised solver study needs no role labels.
- Same BIRD1534/11DB aligned SQLite snapshot and eleven pinned hashes; same old
  Qwen table/query ranking vectors and105 FK vectors from relation_cache_001.
  Validate cache receipts/identities; preserve every parallel/composite FK.
- Unit and weighted graph topology identical. Parallel constraint representative
  minimum(cost,ID) per pair, true disconnected components yield forests. Schema
  retains all selected-table columns/FKs, not a mandatory SQL join plan.
- Already repeatedly explored BIRD-dev; no held-out/generalization/novelty claim.

## Algorithms, numerical proof, and fairness

- Greedy: start smallest terminal ID, attach closest unconnected terminal to the
  current tree by multisource Dijkstra, stable terminal tie; MST+leaf pruning.
- Kou/KMB: NetworkX method='kou', terminal metric closure MST expanded/pruned.
- Mehlhorn: unchanged NetworkX method='mehlhorn', same canonical graph/pruning.
- DP: unchanged Dreyfus-Wagner subset recurrence/reconstruction, <=12 terminal cap.
- MILP: binary x_e for undirected selected edges; directed continuous flows on
  both arcs, each <=(k-1)*x_e. Smallest terminal sends k-1 units, every other
  terminal consumes1, nonterminals conserve flow. Minimize sum(weight*x).
  SciPy milp/HiGHS presolve, mip_rel_gap=0, per-component limit10s, threads1
  (SciPy passes this HiGHS option through with a known warning). Only status0,
  finite zero gap/dual consistency and feasible primal qualify as certified.
  Preserve status/gap/dual/nodecount; never label a timeout incumbent optimal.
  Trivial one-terminal components are exact by construction without MILP calls.
- Independently verify real k<=3 optimum by distance/meeting-node identity;
  DP and certified MILP must match. Approximate cost cannot be below that oracle.
  Equal-cost different schemas are tie sensitivity, not optimization improvement.
- No solver memoization: every question/settings/method is actually solved.
  Rotate five method execution order by question ordinal to reduce timing bias.
  Timing includes wrapper/canonicalization/certification, not a general speed claim.

## Tasks, checks and budget

- [x] 1. Write tests RED->GREEN for all five solvers: weighted9vs10 example,
  weighted path, tiny brute-force optimum, forests, ties/input permutation,
  invalid inputs, zero costs; MILP proof/bound/primal integrality.
  Add scripts/text2sql/extended_steiner_solvers.py, tests/test_extended_steiner_solvers.py.
- [x] 2. Add new pinned config and runner scripts/text2sql/run_steiner_five_solvers.py.
  Main settings unit and weighted (two groups), each five requested methods.
  Five label-blind hash-selected question smoke precedes full1534 for BOTH.
  Since this is an algorithm diagnostic, engineering correctness permits full
  regardless of smoke task-score improvement. Seal before label evaluation.
- [x] 3. Run settings in independent CPU sessions if practical, <=4 threads each,
  HiGHS1thread, peakRSS target<4GiB/process. Budget1800wall seconds/setting,
  10seconds/MILP component, no more than3 consecutive uncertified/failing cases.
  For timeouts preserve status and stop/reassess, never silently substitute DP.
- [x] 4. Independently audit all output identities, original edges, seeds,
  per-component connectivity, constraint IDs/costs, exact certificates/oracle,
  coverage/paired counts/means and original hashes. Reread prior weighted baseline
  to verify Mehlhorn replay on identical frozen setting. Targeted regressions.
- [x] 5. Final independent code review; report source/env/resources/config/command,
  run counts, coverage/graph cost/time/table size, strict/equal-cost differences,
  paired rescues/damages and descriptive DB-cluster intervals. Archive sanitized
  code/config/aggregate report under owned docs/research/text2sql/reports/
  steiner_five_solvers_bird_20261109_01; commit/push/readback. Keep raw privately.

Success criteria: any strictly lower exact objective is algorithm signal; positive
net coverage vs Mehlhorn is task proxy signal, not SQL EX. No automatic promotion,
extra solvers, extra model/data settings, weight tuning or SQL after this matrix.
Stop on failed invariants, pinned input drift, resource budget or repeated failure.
After the two settings complete, conclude and analyze results regardless of sign.

## Reproduction notes and ledger

Actual paths use LAB_ROOT alias config. New private results/logs/debug have distinct
steiner_five_solvers_bird_20261109_01 names. No overwrite of prior measurements.
Preflight host192logicalCPU/442GiBavailable, GPUs have other tasks, CPU-only selected.
Existing SciPy MILP is available, no highspy/pulp/ortools/Gurobi installed or needed.
First metadata-only check lacked LAB_ROOT, repeated with variable set before any
experiment/model call. No resource or model cost occurred in that config check.
No actual model calls planned: token0, externalAPI0CNY, localCPU time still recorded.

Execution ledger: initial tests RED absent extended module ->GREEN5tests/12new
brute-force subcases; runner RED absent module ->GREEN2 tests. Source99cfc79
committed before any real solve. Both five-question/25-call smokes passed; full
unit and weighted sessions ran concurrently, each1534/7670calls, zero timeouts.
Every Mehlhorn result replayed old sealed selections/costs,1534/1534 each setting.
Full independent audits15340outputs PASS. Targeted regression44unique tests with
32brute-force subcases PASS. Code and verifier review no blockers; generic future
zero-cost extraneous-MILP-component case explicitly out of scope (realcost>=1).
Unit coverage greedy1236/Kou1238/ME1236/DP1236/MILP1230; weighted1235/1238/1238/1236/1236.
DP/MILP objective identical,3014nontrivial MILP certificates status0/gap0. Unit
34same-cost exact table sets differ; weighted DP/MILP tables match. No new model,
GPU, SQL, parameter tuning, further method/data groups or automatic extension.
Reports/code/config committed to owned repo; remote archive confirmation recorded
after actual readback in resource index and final user report.

References (checked2026-11-09; actual installed versions pinned above):
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html
- https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.approximation.steinertree.steiner_tree.html
