# Budget-feasible repair supervision for global schema attention

2026-11-21 UTC+8. Exploratory, user-authorized. Owned bArtyom/gfm-rag,
branch research/budget-repair-attention-20261121. Localbase0376a89; equivalent
publicparent124fd30b1548106f714d7218c9d6972dc82a4e52.
Read rootREADME/text2sql README/roadmap/contract, resource index, old QAFD/
closure reports and code. Keep old stopped candidates stopped. No upstream edits.

Core hypothesis: training global attention on a budget-feasible repair certificate
(add an omitted reference-read field, remove selected non-reference distractors,
retain all currently covered reference reads/tables, fit the same exact schema
budget) improves complete read-binding coverage over independent scores and
ordinary global attention. Not a claim that attention, hard-positive mining,
ranking loss or executable supervision alone is novel.

Closest inspected primary papers: QAFD https://arxiv.org/html/2605.18775v1,
AttnLink https://arxiv.org/html/2608.00693v1 (attention ranking and setmass/floor),
JOLT-SQL https://arxiv.org/html/2505.14305v1 (noisy schema/bidirectional attention),
RAT-SQL https://aclanthology.org/2020.acl-main.677/ and old GRAST-SQL
https://arxiv.org/html/2512.16083v1 . Potential differentiation is exact
closure/token-feasible repair supervision, not new attention architecture/loss.
Novelty remains unestablished; first test a measurable signal.

Data: frozen BIRD-dev1534/11DB, cached question/schema1024D Qwen embeddings;
no new LLM/embedding inference, no paidAPI or installs. Preselect3 whole testDBs
by SHA256('repair-db-v1:20261121:'+db), before any new reference labels.
Remaining8DBs training. Select320 train cases DB-roundrobin hash; no reference
filtering during selection, unsupported labels are recorded/skipped, need>=280
supported to train. Test100 new cases from3DBs, exclude all prior433 cases
(SQL133+route100+QAFD100+closure100). Need100 available, else stop, don't change
split or replace cases. Dev already exposed: DB-heldout within this run only,
not an independent benchmark or external confirmation.

Training labels: only selected training cases' reference SQL is compiled on
empty full TEXT-schema stubs via SQLite authorizer, with the prior conservative
prepare guards. Targets are physical read table/column identities, not unique
semantic requirements. COUNT(*) can provide a table target without column
positives. Gold test SQL values are not accessed until all predictions sealed;
source JSON is shared with the existing loader but reference fields aren't
available in prediction examples. No SQL data-result execution.

Three models, same embeddings/query/metadata/budgets/train cases/order/epochs:
- independent pointwise residual scorer, balanced BCE table+column labels;
- one-layer global self-attention scorer, balanced BCE;
- same global scorer initialized identically, BCE+repair margin supervision.
No position embeddings. Hidden96/heads4/dropout0, query/node/product/owner-table
features. Fixed3epochs, AdamWlr.001/weightdecay.01, seed20261121, no tuning,
validation checkpoint selection or test-driven early stopping. BCE balanced
positive/negative means separately for table and column node types. Final field
rank=columnlogit+.25ownertablelogit, same all trained arms.

All selections use the previous deterministic greedy FK closure, atomic/all
internal FK identities and exact frozen Qwen partial-DDL token count. B perquery
is prior weighted-Mehlhorn full-table schema cost. Direct whole-table dense
is an extra no-training control so gains cannot hide a weak learned baseline.
Repair candidate: lowest-score omitted reference column; remove non-reference
semantic candidates from low to high score only if currently retained reference
columns AND tables stay retained. Stop at first fit; this is a greedy feasible
certificate, not minimum repair or optimal structured inference. Train on
softplus(mean_removed_score-added_score+.1) times.25 if a nonempty removal
certificate exists. No heldout labels in loss/packing. Require>=30 certified
training events spanning>=2trainDBs or mark mechanism unsupported, don't expand.

Engineering:5 training forwards/backwards perarm,5test forwards perarm, then
throw away smoke weights. Synthetic unit tests before smoke. CPU8threads,
CUDA_VISIBLE_DEVICES=2 after fresh resource check, need>=4GiB free, targetGPU
allocation<=2GiB. Each stage1800wallseconds, total3600, forwards<=5000,
no LLM tokens. Log every actual graph forward/node count/GPUevent time, training
steps, checksums and model versions. Graph inputs are vectors, not language
input tokens; do not fabricate tokenizer/model usage or API ledger calls.
ExternalAPI0CNY; local GPU/CPU measured separately and unpriced.

Seal checkpoints and all100 model scores/selections before reference evaluation.
Primary: all original physical read table/column bindings retained, unknown
kept in100 denominator; supporting preparability and table coverage. Same
conservative unsupported-reference guards. Report paired rescue/damage, perDB,
exact tokens, repair counts/cost/protected-binding verification, parameter counts,
compute/node units. Gate: repair>=global+3 AND>=independent+3 AND>=whole_dense,
>=90/100 evaluable, positive versus both trained baselines in>=2/3DBs, zero
budget violations and adequate certificate support. If fail STOP this version,
no seed/loss/model sweep, GPU/SQL/full expansion. If pass, only a separately
registered bounded reproducibility check is allowed, not automatic new SQL.

Report code/config/protocol/anonymous aggregates and hashes in owned repository;
private cases/readsets/scores/checkpoints stay local. Publish via connector if
shell credentials absent; compare archive tree and remote files exactly. No
merges or uploads of raw data/weights. Final usage ledger totals and known
cost scope must be reported even though this run has zero new language tokens.
