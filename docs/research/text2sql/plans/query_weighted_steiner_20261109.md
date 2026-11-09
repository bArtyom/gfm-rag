# Query-weighted Steiner implementation and experiment plan

Status: completed 2026-11-09; exploratory. Full1534 unit1236/weighted1238/dense1219;
upgrade gate failed. Report: ../reports/query_weighted_steiner_bird_20261109_01/README.md.

Goal: test whether question-conditioned FK costs improve complete reference-table
coverage over unit-cost connection and size-matched semantic retrieval.
Spec: the user-approved scheme in this conversation: fixed schema graph, three
frozen semantic table seeds, Mehlhorn solver, r=(1+cos)/2, cost=1+(1-r).
Architecture: retain FK constraint IDs and ordered composite column pairs;
collapse parallel edges only for solving by minimum (cost, constraint ID), keeping
the chosen identity. Serialize every legitimate FK among selected tables as schema
context, not a mandatory join plan. Keep self-FKs in metadata but exclude loops
from tree solving. No invented relation semantics or additional evidence input.
Tech: existing think2sql_20260909, Python 3.12, numpy/networkx/sqlglot,
Transformers Qwen3-Embedding-0.6B CPU FP32 last-token pooling, 1024 dimensions.

## Constraints and rulings

- Existing independent checkout, new branch research/query-weighted-steiner-20261109;
  base 83a25249758f81f68a7a61ee1649fdbde73d8073. No main-model changes.
- Read root README, text2sql README, experiment-roadmap and reproducibility-contract.
  Earlier dimension/supervised-role gates remain closed: this is an explicitly
  authorized unsupervised connection experiment, not a dimension sweep, learned
  edge gate, GFM experiment, or role-accuracy claim.
- Reuse prior BIRD aligned DBs / eleven pinned hashes / cache receipts. Questions
  already used for exploration; no held-out or significance claim.
- Qwen local weights hash must match prior 0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd.
  Question vectors reused from frozen vLLM cache. Relation vectors newly encoded
  with HF CPU; verify five re-encoded query cosine >=0.995 before accepting cache
  compatibility. This is backend compatibility checking, not bitwise equivalence.
- Question-only scoring, no BIRD evidence added. No gold in ranking/descriptions.
  Prediction JSONL sealed before evaluation opens SQL labels.
- Frozen lambda=1, k=3, solver=Mehlhorn; no parameter sweep or paid API fallback.
- Budget: <=8 CPU threads, target RSS <12 GiB, <=30 wall minutes, <=100k new
  embedding input tokens, <=5000 unique relation texts, no GPU / SQL generation.
  Every local forward attempt counted in shared ledger; external API CNY0,
  local CPU time recorded, not priced as free computation.

## Tasks

- [x] 1. Write failing semantic-path / parallel-FK / composite / invalid-vector /
  fixed-topology tests; implement pure query_weighted_steiner module; verify green.
- [x] 2. Add standalone relation cache preparation and paired runner; five-text
  encoding smoke before larger batches; five-question retrieval smoke before pilot.
  Preserve raw relation IDs, descriptors, scores, selected edges, seeds, input hashes.
- [x] 3. Run deterministic topology-stratified 100-question pilot. Main arms:
  unit-cost Steiner, query-weighted Steiner, semantic top-N matched per question
  to weighted output count. Evaluate all arms with identical schema serializer and
  embedding-model tokenizer (schema-token proxy, not generator usage).
- [x] 4. Expand to 1534 only if pilot weighted-minus-unit complete count >0 AND
  weighted-minus-dense >=0. No second tuning round. If gate fails, stop this
  frozen variant and report exploratory pilot; no full run or SQL generation.
  Final upgrade target: >=1pp net coverage vs unit and positive vs matched dense,
  with table/token costs explicitly reported; DB-cluster intervals descriptive.
- [x] 5. Conditional only; NOT RUN because full gate failed. Only after full positive gate: one minimal question-weight-shuffle control,
  fixed within-database cyclic permutation, no extra model encoding. Independent
  dataset replication / SQL EX deferred until real positive evidence.
- [x] 6. Independently reread sealed predictions, validate original topology,
  preserved seeds/connectivity, score/cost consistency, per-question matched size,
  FK identities/composites, input immutability and coverage counts; targeted tests.
  Archive code/config/protocol/aggregate report in owned bArtyom/gfm-rag, verify
  remote content. Do not publish questions, SQL, descriptors, weights or predictions.

## Mechanism and reporting

Record changed table sets vs changed relationship identities separately, disconnected
forests, and whether a selected unit-tree edge has an alternative route (edge not a
bridge of the full graph). Route-ambiguous and unique-route strata determined from
graph/seeds before labels. Pilot sampling balances these strata by deterministic
hash and is not representative random evaluation. Unknown label parses retained.
Paired rescue/damage and table/token sizes primary; no semantic join correctness
claim without adjudicated relation labels. Stop after negative pilot, budget or
continuous failures; retain all failure logs. No invented results.

## Execution ledger

- Initial preflight: clean checkout; CPU192 / available memory436GiB; GPUs busy
  with other processes, CPU-only selected. Existing model/data aliases valid.
- User has approved the method and execution; no repeated design approval needed.
- Native implementation used; any separate final reviewer only as required by
  review skill. No per-task agent delegation.
- Task1 complete2593c3f: seven tests RED missing module -> GREEN; two prediction
  tests RED missing predict -> GREEN. Task2 complete678e3c5: runner tests RED
  absent module; structural sampler test exposed51/49 imbalance, changed to
  two-level structural/DB round-robin -> GREEN. No labels inspected for sampling.
- Encoding2593c3f completed105FKtexts+fivequeryprobes,15localforwards,1700tokens;
  min probe cosine0.99984276. New CPU FP32 backend retained, no old cache changes.
- First100pilot failed before sealing due nested PK list in shared serializer;
  failing composite-PK regression reproduced root cause, minimal flattening fix
 9084970 passed. Pilot002 unit82/weighted83/dense81; gate passed, source/parameters
  frozen and full1534 ran. This is an engineering recovery, not a new hypothesis.
- Full1534 unit1236/weighted1238/dense1219, repair8/regress6 vs unit. Final gate
  failed. No shuffle, SQL, GPU, parameter sweep or independent-dataset extension.
- Final review no blockers; one operational caveat: full CLI gate is manual, and
  actual positive pilot receipt was checked before expansion. Independent audit
 1534rows/4602arms PASS, including full identities/gate/recount after review.
- Verification37 targeted tests plus20 brute-force subcases pass. An initial
  legacy-test invocation lacked GRAST_SOURCE; corrected invocation passed.
- Public archive being finalized; actual remote confirmation recorded separately.
