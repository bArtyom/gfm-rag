# Closure cost timing: negative pilot and field-level bottleneck

2026-11-12 UTC+8. Exploratory run `closure_budget_order_bird_20261112_01`.
Owned repository bArtyom/gfm-rag, branch research/closure-budget-order-20261112.
**Stopped:** reference SQL preparability whole_dense/late_closure/early_closure
85/76/77 out of100. Full-reference table coverage87/94/94. No new inference,
training, GPU, paidAPI or SQL data-result execution. No independent confirmation.

## Pain point, hypothesis and preregistration

Previous QAFD context-capacity trial74/74/72 showed worst-context whole-table
costs can exclude necessary wide tables. That candidate remains stopped.
Outer-loop decision: test column granularity and the timing of connector-cost
accounting before inventing another diffusion score or tuning capacities.
Single hypothesis: delaying FK closure until after semantic column selection
forces avoidable removal of useful columns under a hard context budget.
[Protocol](../../plans/closure_budget_order_20261112.md) and frozen
[config](../../../../../configs/text2sql/closure_budget_order_bird_20261112.json)
were committed locally before running5 smoke and100 pilot. Layer exploratory
main experiment;8CPU threads,1800wallseconds/stage,RSS target4GiB. Upgrade only
if early preparability>=late+3 AND>=whole, at least90/100 evaluable, zero budget
violations. Only one unchanged fresh100 confirmation would be allowed on pass.
Gate failed; no confirmation, full1534, new model or SQL-generation runs.

## Sources, implementation and comparators

Read owned rootREADME, text2sql README, experiment-roadmap, reproducibility-contract,
previous QAFD/Steiner reports, serializers/cache loader and relevant upstream code.
QAFD read-only upstream https://github.com/Tarzanagh/QAFD-RAG at
2a3a42c8ea4e9c416de0a7fe53c04fab50b756ef; prior audit/noLICENSE-found recorded
in previous report. Official original run is python benchmarks/run.py --task
text2sql --dataset spider2-lite --questions10. This turn does not invoke that
full pipeline. GRAST read-only resource identity4c698cae31da8299deb5c809101d172d5b2ddeb3
remains checked by inherited loader; no upstream source vendored or modified.
No original paper end-to-end scores are reproduced or compared numerically.

Closest primary sources already cover query-column ranking plus key/Steiner
closure: [GRAST-SQL](https://arxiv.org/html/2512.16083v1),
[Graph-Link](https://proceedings.mlr.press/v306/zhong26s.html), and
[QAFD](https://arxiv.org/html/2605.18775v1). Column pruning, graph connectivity,
flow, budget and subquery decomposition are not claimed as new. This is a bounded
mechanism probe, not completed novelty clearance or a new SOTA method.

All arms reuse question-only cached1024D Qwen3Embedding0.6B vectors. Evidence
is available in inputs but not encoded into this frozen retrieval score.
B per question is exact Qwen2.5-Coder7B tokenizer cost of prior frozen weighted
Mehlhorn schema, all its columns and internal FK constraints. Same ceiling for
all arms; actual spending is allowed to differ. Tokenization is not inference.

- whole_dense: rank tables by cached query cosine, append full table schema only
  if exact serialized context fitsB. Same control as previous QAFD adaptation.
- late_closure: rank physical columns by cached query cosine, append if partial
  schema without FKs/bridges fitsB. Add FK closure; while overB remove the
  lowest-ranked retained semantic candidate and recompute. No refill. This is a
  custom pipeline comparator, not an official GRAST reproduction or strongest
  possible deferred-repair algorithm.
- early_closure: same column ranking, graph and closure; for each candidate first
  compute complete closure and exact context cost, accept only if it fitsB.
  Continue after rejection. No training, parameter search or fixed old seeds.

Closure is deterministic nearest-terminal greedy in each real FK-connected
component, shortest-path ties fixed lexicographically. Bridge tables and ALL
legitimate FK constraints between retained tables are retained; composite/parallel
constraint identities and their key columns stay intact. No invented edges
between disconnected components. Actual schema serialization is partial DDL,
PK only if all its fields present. All-fields serialization is verified bytewise
against the old serializer. Keys/bridge nodes carry only retained columns.
This greedy closure is not exact Steiner and does not select a unique join role.

## Data, sample, evaluation and limitations

BIRD-dev1534/11DB, existing aligned database copies, question/table/column caches,
model/tokenizer hashes and previous predictions are all verified by frozen config.
Exclude prior SQL133+route100+QAFD100=333 cases. Sample100 by DB-roundrobin
SHA256 salt closure-cost-v1:20261112;5 engineering smoke are a subset. No labels
used in sampling/selection; all300 selections sealed before reference evaluation.
This exposed development set is not an independent held-out benchmark.

Primary metric: SQLite EXPLAIN QUERY PLAN of unchanged reference SQL on empty
in-memory schema stubs with retained physical column names. Full schema must
prepare first. Reject projection stars except COUNT(*), NATURAL/USING joins,
catalog-qualified tables and unqualified double-quoted columns as unknown.
Unknown stays in denominator. This is **syntactic preparability**, not semantic
sufficiency, required-column recall or Set/Bag execution accuracy. Stubs use TEXT
columns and omit original constraints/indexes; no database records are read or
SQL query results executed. SQLite itself may resolve nested unqualified fields
differently after pruning, even when preparation succeeds.

Reviewer identified that last risk after the pilot. Preserve original counts
and failed gate. A separately documented [posthoc addendum](../../plans/closure_budget_order_binding_addendum_20261112.md)
compiles reference SQL on full empty stubs using SQLite authorizer to capture
original physical table/column read bindings. Verify retention of those bindings
in sealed selections. A synthetic correlated-rebinding counterexample is caught;
no such discrepancy was observed in the100 real cases. This diagnostic remains
posthoc and is not a replacement success criterion or semantic correctness label.

## Actual results

| Arm | Preparable reference SQL /100 | Full reference tables /100 | Mean selected tables | Mean selected columns | Mean actual schema tokens |
|---|---:|---:|---:|---:|---:|
| Whole-table dense |85|87|3.32|52.38|514.41|
| Columns then closure |76|94|4.27|47.93|514.48|
| Closure-aware admission |77|94|4.33|48.96|523.57|

98/100 evaluable;2 unknown unqualified quoted-column cases preserved throughout.
Early vs late rescue1/damage0/unchanged97/unknown2; early vs whole rescue3/
damage11/unchanged84/unknown2. Zero budget violations. Late needed repair in81
cases, removing851 accepted semantic candidates in total. Despite frequent
repair, early only rescues1 case, below registered+3 and below whole baseline.
Final connector-only count early0 does NOT mean closure was free: keys admitted
structurally earlier can later also enter the semantic-candidate list at zero
extra cost. Reported semantic-candidate designation is procedural, not true
semantic necessity; don't use it as key-overhead savings.

All11 whole-to-early loss cases retain every reference table, but omit12 original
read-binding fields in total. Their owning tables have only2--14columns;
4 missing fields have the same name as a retained field elsewhere. Thus wide
tables are not the sole failure regime. Same-name occurrence is an association,
not proof that the retriever selected the wrong role or that alias ambiguity
caused the errors.

Binding diagnostic: whole/late/early preserve original reads85/76/77 among98
supported cases. Early retains all reference tables but cannot prepare SQL in15
cases. All98 have a reference-binding-guided closure that fits their same B;
early misses original bindings in21 despite such a feasible witness. This is an
oracle construction from reference labels, NOT a deployable selector, optimal
oracle, proof of semantic correctness, or a causal isolation of scorer failure.
It shows that irreducible budget infeasibility is not the observed barrier for
these witnesses. Anonymous per-loss features are in posthoc_binding_diagnosis.json.

Pilot wall19.499sec, processCPU23.266sec, peakRSS.7368GiB; smoke wall21.114sec;
verification wall15.719sec. Timing excludes full research/packaging overhead.
Existing think2sql_20260909 environment, explicit interpreterPython3.12.14;
SQLite/dependencies in reproduction_manifest.json.192logical CPUs/~445GiB
available memory checked; four4090GPUs inspected but unused. No installations,
new embeddings, model forwards or API calls. Inherited unused GPU/SQL config
fields are retained for provenance and do not launch their services.

## Verification, failures and final decision

Five pre-run synthetic checks passed, then two targeted tests added for closure
repair/refill behavior and the posthoc binding trap:7 passed. Independent audit
re-tokenizes300 final selections, replays200 column admissions, checks FK closure
connectivity/keys, sample exclusion, predictions seal, all primary counts and
failed gate. It shares tokenizer/serializer/closure/reference parser and primary
prepare evaluator, so is not wholly independent. Separate full-stub authorizer
supports the binding diagnostic. No scientific run failed; no overwritten outputs
or post-hoc rescore. Expected initial test collection failure before module
implementation is preserved as RED log.

Source for actual smoke/pilote9866a5 (see full SHA in reproduction manifest);
posthoc auditd242893. Private prediction seal
11c77853ace1f4d27843fff9d1e1e6c4737e5b942415f4b21f136fc35d8b4443;
config1b347cc99d9b4386bd2af1b71032f86a7a8d58d96e1cdd57b114d00ebccd7c1b.
Archive squashes this turn onto publicparent2149fac7; final tree equivalence
and remote file readback must be recorded before claiming GitHub completion.

Stop this closure-timing candidate. It does not establish a useful innovation.
The scientifically useful change is the bottleneck diagnosis: improving table
coverage94vs87 does not ensure retaining the columns needed by original SQL.
The tested early-admission rule improves preparability by only1 case over late
repair. Ranking and need allocation warrant investigation alongside cost
accounting; other timing/repair rules remain untested.

## Next method hypothesis (not implemented or run)

Move from scalar whole-question relevance to explicit requirement witnesses.
Inputs remain question+evidence+schema. Represent each selection/filter/aggregation/
comparison requirement with source-span provenance and alternative candidate
column/operator bindings. A field counts toward coverage only when a compatible
binding witnesses that requirement; repeated similar columns do not satisfy an
uncovered requirement. Select bindings jointly with shared connector/serialization
cost, and allow earlier seed proposals to be withdrawn. Keep alternatives for
ambiguous requirements rather than forcing the first guess.

The key unresolved issue is whether requirement/witness inference is accurate,
not whether another graph solver is faster. Before any new large run: freeze a
small faithful requirement assessment and compare against existing Coverage and
GRAST-style column baselines under equal total inference+context budget. QAFD
already decomposes subqueries and our old Query-aware Coverage already tried
requirements, so decomposition plus coverage alone is NOT sufficient novelty.
A defensible contribution would need a distinct verifiable witness mechanism
and an empirical gain over those neighbors. Neither has been established here.

## Reproduction and artifact scope

Use LAB_ROOT aliases and hashes from config; set SQL_ENV_PREFIX to the existing
think2sql_20260909 environment prefix. Explicit interpreter avoids host PATH
shadowing. At project root set OMP_NUM_THREADS/OPENBLAS_NUM_THREADS/MKL_NUM_THREADS
all8 and TOKENIZERS_PARALLELISM=false. Fresh output names are required:

```bash
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" -m pytest tests/test_closure_budget_order.py -q
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_closure_budget_order.py --config configs/text2sql/closure_budget_order_bird_20261112.json --mode smoke --output ai_temp_code/closure_smoke_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/run_closure_budget_order.py --config configs/text2sql/closure_budget_order_bird_20261112.json --mode pilot --output ai_temp_code/closure_pilot_replay
conda run -n think2sql_20260909 "${SQL_ENV_PREFIX}/bin/python" scripts/text2sql/verify_closure_budget_order.py --config configs/text2sql/closure_budget_order_bird_20261112.json --execution ai_temp_code/closure_pilot_replay --output ai_temp_code/closure_verify_replay
```

Local artifacts: results/closure_budget_order_bird_20261112_01/{pilot_001,
verification_001}, logs/closure_budget_order_bird_20261112_01 and smoke under
ai_temp_code/closure_budget_order_smoke_001. Public artifacts: code/tests/configs,
protocol/addendum, aggregates, anonymous diagnoses and usage. Question/SQL/IDs/
column selections/read bindings/tokenizer/model/vector caches remain local.
Public reproduction requires separately provisioning exact hashed resources.

Usage: this run model input/output/total0/0/0, unknown0, externalAPI0CNY,
GPU0seconds. CPU not monetized. Shared ledger snapshot in usage_snapshot.json
covers registered calls only, not complete account spending; cumulative CNY
estimation is only its priced portion, not verified billed cost and not all
currencies/local compute. No old cache usage charged again.
