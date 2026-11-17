# BizWeave business-event and constraint pilot

**Status:** preregistered; no results inspected for this run.
**Run ID:** `bizweave_business_semantic_pilot_20261117_001`
**Layer:** exploratory feasibility / mechanism gate.
**Project:** `bArtyom/gfm-rag`; branch `research/bizweave-event-constraints-20261117`; starting commit `cb6fe5f4f32a011861d9cf91c0497fb3483450ff`.

## Research question and hypothesis

When several physical implementations are joinable, can a typed business mapping containing event, status, time basis, grain, evidence references, and verification state select the implementation matching the query, while abstaining when evidence or intent is unresolved?

**H1 (mechanism only):** On a fixed synthetic schema, the structured selector will correctly resolve all eight prewritten minimal-pair queries, switch paths/constraints for all four pairs, and abstain on both unresolved controls. It will exceed the best unstructured baseline by at least two of the eight resolved cases.

This fixture is hand-authored from the supplied order-domain example. Passing it establishes only that the implementation can represent and enforce its stated rules. It is not independent evidence that real queries contain those signals or that automatic intent/evidence extraction works.

## Causal chain and measures

`typed event/state/time/grain mapping + evidence state → hard constraint filtering → correct implementation selection / safe abstention`.

- **Unit:** one fixed synthetic query case; four paired contrasts (purchase/browse, payment completed/attempted, refund completed/requested, order count/line-item count) plus two unresolved controls.
- **Independent variable:** selector: shortest physical path; schema-token overlap; flat mapping-description token overlap; BizWeave structured constraints with verified evidence; structured constraints with evidence-state check removed.
- **Primary outcome:** exact implementation ID accuracy on the eight resolved cases.
- **Secondary outcomes:** pair-switch accuracy (4 pairs), correct abstention on the two unresolved controls, coverage, and the case-level error table. No confidence interval or significance test is meaningful for a hand-authored fixture.
- **Fairness controls:** identical candidate mappings per case; deterministic tie-break by mapping ID; fixed lexicons and descriptions; no learned weights or model calls.

## BIRD readiness audit

Read BIRD train/dev question-SQL JSON and schema JSON in place through `/mnt/liansp3/sources/datasets/bird`; do not copy or publish question text, SQL, database rows, or per-query outputs. Freeze the four source hashes in `config.json`.

Use SQLGlot SQLite parsing to count only aggregate candidate-supply signals: query has a state/status cue and a Gold-SQL state predicate; query has a temporal cue and Gold-SQL predicate on a date/time-like field; query has a count/grain cue and Gold SQL count/grouping; and intersections with multi-table SQL. Count distinct databases for each split and train/dev database overlap. Lexicons and field-name patterns are frozen in the runner before the full audit.

These counts are silver candidate supply, not verified business labels, relation/path accuracy, or evidence-calibration results. Gold SQL is read only for the audit counters; it never enters the synthetic selector's features. BIRD-dev remains previously exposed development data.

**Readiness threshold for proposing a later annotated real-data pilot:** at least 100 strict candidate queries across 10 train databases and 50 across 3 dev databases in a condition category. Passing this count does not authorize a correctness claim: a separate, blinded manual review must establish ambiguity, valid alternatives, and labels before real-data scoring. This run ends at that review gate.

## Success, falsification, and stop rules

- **Synthetic mechanism pass:** structured selector gets 8/8 resolved cases, 4/4 pair switches, 2/2 correct abstentions, and beats the best unstructured baseline by ≥2/8 resolved cases.
- **Falsifier for the fixture claim:** any resolved case is missed, any pair does not switch, either unresolved case is selected, or the structured method fails to exceed the best unstructured baseline by the threshold. Report the exact failure; do not alter the fixture after results.
- **BIRD readiness:** report counts and whether the predeclared sample-count threshold is met. Even if met, stop before real-data model scoring because no blinded business-label review is available in this run.
- Stop on source-hash mismatch, SQL parser/runtime failure, result-path collision, privacy leak, or resource cap. No repair of thresholds or lexicons after seeing the full counts.

## Data and versions

Read-only source root: `/mnt/liansp3/sources/datasets/bird` → `/mnt/liansp3/研究项目/Text2SQL/Alpha-SQL_idea1/data/bird`.

| Split/file | Rows | SHA-256 |
|---|---:|---|
| train/train.json | 9,428 | `abf17d3def22f56f41b3e139b94bba3fa4a986280abcbf6df2d7f30150695520` |
| train/train_tables.json | 69 | `85300c745b263db88a5e0cdf083e8b2427d90272e954bc8c5f92aa1dc66c836b` |
| dev/dev.json | 1,534 | `630272f2b1c44d8cef2c3b246f623355cf0bbc1e832c81061df895530dfc2f06` |
| dev/dev_tables.json | 11 | `35e7f73f2bc3a3bc4def9466215f7617ff8b37e9b2837f03539a42c9e9c69d97` |

The project source tree is the public Apache-2.0 fork `bArtyom/gfm-rag`; no upstream GFM-RAG code is needed or modified in this pilot. Dataset files and database contents remain local.

## Resources and execution

- CPU only, one process; cap at 8 threads, 4 GiB RSS, and 30 minutes. Use no GPU because all four GPUs were occupied at preflight.
- Existing environment: `t2sql_code_audit_20261005`, explicit interpreter `/root/miniconda3/envs/t2sql_code_audit_20261005/bin/python3.10`, Python 3.10.22, SQLGlot 26.33.0. No dependency installation.
- No model/local service/API, embedding, SQL execution, training, downloads, or public-price lookup. Expected model/API tokens and fees are zero; local CPU wall time is recorded separately.
- Smoke: parse at most five examples per split and run the fixed synthetic fixture. Full: all BIRD train/dev rows and the same fixture, only after smoke passes.
- Planned command (run from repository root):

```bash
conda run -n t2sql_code_audit_20261005 \
  /root/miniconda3/envs/t2sql_code_audit_20261005/bin/python3.10 \
  experiments/bizweave_business_semantic_pilot_20261117_001/run_pilot.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird \
  --output /mnt/liansp3/sources/results/bizweave_business_semantic_pilot_20261117_001/full_001.json
```

The smoke uses a unique `smoke_001.json` output path. The runner refuses to overwrite outputs. Local outputs/logs stay under the registered private result/log roots; the GitHub report contains only the synthetic case summary and BIRD aggregates.

## Result boundary

No claim about BIRD retrieval quality, business semantics, cross-database generalization, SQL execution accuracy, or novelty follows from this pilot. A positive result can justify only a separately preregistered, human-reviewed real-data labeling study. A negative synthetic result means revise or stop the implementation before spending on models or GPU experiments.
