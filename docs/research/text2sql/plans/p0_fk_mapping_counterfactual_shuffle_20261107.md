# P0 FK mapping counterfactual-shuffle diagnostic

**Experiment ID:** `p0_fk_mapping_counterfactual_shuffle_20261107_01`
**Status:** preregistration
**Layer:** one bounded exploratory mechanism diagnostic; not a GFM ranking or method-effectiveness experiment
**Project branch:** `research/p0-sql-used-proxy-alignment-20261107`

## Pain point and research question

The completed static-instance audit found 55 alternative candidate comparisons with the same Bag result as the SQL-used mapping, across 54 of 94 complete nonempty units. The positive cases were concentrated in two of four anonymous databases. A single stored SQLite instance therefore sometimes cannot distinguish candidate mappings, but the audit did not test whether this result survives a changed FK assignment.

**Question:** Among those 55 fixed candidate comparisons, how often does a controlled change to the row-level assignments of the competing declared single-column FKs make the two SQL variants return different Bags?

**Hypothesis:** At least 50% of eligible candidate comparisons that matched on the original instance will produce a Bag difference on at least one of 20 pre-seeded, referentially valid counterfactual views. This would show that their original match is sensitive to the observed row associations. It would not show that either mapping is semantically or business-correct.

## Approaches considered

1. Add more model votes to the existing FK Role proxy and rerun G-reasoner ranking. Rejected: the repo has already closed that proxy line after a negative result and explicitly says additional votes do not establish human labels.
2. Treat model judgments as correctness labels. Rejected: models can review a protocol, but their votes are not human gold and do not resolve the registered label limitation.
3. Apply controlled FK-value permutations to the fixed same-instance matches. Selected: it directly probes the remaining data-instance sensitivity question without changing the query generator, GFM, or ranking target.

## Frozen inputs and sample

- Dataset: the existing local BIRD dev snapshot; it remains a development diagnostic, not an independent test set.
- Source question/FK manifest: `p0_fk_sql_used_mapping_rank_20261107_03`, fixed by the manifest and input hashes in the completed instance-equivalence report.
- Source result: `p0_fk_mapping_instance_equivalence_20261107_01`, Full_002; 94 complete units, 55 Bag-equal alternative candidate comparisons, four anonymous databases.
- Sample: exactly those 55 candidate comparisons. No resampling, added questions, or changed SQL targets. The runner must reconstruct the same 55 pairs from the frozen local artifacts and verify the source hashes before opening SQL or database files.
- Smoke: the first five eligible pairs sorted by `SHA256(experiment_id || private_pair_identity)`. Full: all eligible pairs among the fixed 55, including the Smoke pairs in a separate run directory.

## Intervention and validity checks

For each eligible pair, keep both SQL ASTs and all non-FK data fixed. In a SQLite connection whose main database is opened read-only, create temporary views that overlay a seeded bijection of existing values across rows for each competing child FK column. Do not write, copy, or alter the source databases. Each perturbation preserves the child column's value multiset and NULL count; replacement values must remain within every referenced parent-key domain.

Only single-column FK constraints are eligible. Exclude a pair if a changed column participates in a composite FK, overlaps another changed FK column, cannot be tied to a stable row key, or would violate a declared unique constraint under permutation. Validate the view's row counts, per-column multisets, NULL counts, FK-domain support, and applicable uniqueness constraints before executing either SQL. If fewer than 40 of the fixed 55 pairs remain eligible, or fewer than three anonymous databases remain represented, stop after reporting coverage; do not widen eligibility.

For each eligible candidate pair, run 20 deterministic, non-identity permutations with seeds `20261107` through `20261126`. Both SQL variants run on the exact same view for each seed. Record both-empty outputs separately; they are non-informative and do not count as evidence of persistent equivalence. All query execution is read-only and uses the existing row, output-size, and timeout limits.

## Metrics and decision rules

- **Primary:** candidate-pair `EverBagDiverged@20`: number of eligible pairs with at least one valid perturbation where the SQL-used and alternate SQL Bags differ, divided by eligible fixed pairs.
- **Secondary:** per-seed Bag/Set divergence; per-pair divergent fraction; both-empty and one-empty rates; invalid/excluded perturbation counts; anonymous-database slices; and difference from the original static-instance result.
- Report exact counts and database strata. Four database clusters are too few for a strong population-level confidence claim; do not use unit-level Wilson intervals as if observations were independent.
- **Positive sensitivity signal:** at least 50% `EverBagDiverged@20` and at least three represented databases.
- **Weak sensitivity signal:** at most 25%. Values in `(25%, 50%)`, insufficient coverage, or unreliable perturbation validity are inconclusive.
- Regardless of outcome, stop after this one Full run. No G-reasoner ranking, model-vote expansion, parameter search, or new sample follows from this registration.

## Model protocol review

Before Smoke, two existing local models (Qwen2.5-Coder-7B-Instruct and Qwen3-4B-Think2SQL) independently critique this protocol for validity, confounds, and implementation risks. They see only this protocol, not questions, SQL, candidate IDs, database names, or outputs. Their judgments are process feedback only; they are not pooled into labels or metrics. Any unresolved fatal concern must be addressed in a dated amendment before Smoke. Local input/output tokens and GPU time are recorded per request in the private ledger/results.

## Resources, code, and reproducibility

- Experiment execution: CPU only, at most 8 threads, 1,800 seconds CPU, 3,600 seconds wall, and 4 GiB RSS. No dependency installation, training, external API, or GPU use for the SQL diagnostic.
- Model protocol review: reuse the two indexed local Qwen snapshots and existing compatible environment; assign one idle GPU to each model and run independently. No external API or model download.
- Main experiment environment: `think2sql_20260909`'s explicit Python 3.12.14 interpreter and SQLGlot 28.0.0, subject to a preflight that verifies the actual interpreter and imported package versions. Do not rely on an inherited `python3` that resolves to Python 3.9.
- Reference repository: this user-owned `bArtyom/gfm-rag` branch at source commit `3efabf6318c67a34d9893233ccc700c2e727d0b8`; upstream reference code is not copied. The public `TestSuiteEval` implementation has no declared license, so this experiment does not reuse or modify it. The published test-suite method is cited as related evaluation work, not claimed as our method.
- Private results: `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/`; logs: `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_counterfactual_shuffle_20261107_01/`.
- Public report and anonymous aggregate: `docs/research/text2sql/reports/p0_fk_mapping_counterfactual_shuffle_20261107_01/`.

## Interpretation limits

These views preserve selected declared-key constraints and empirical FK-value marginals, but they do not preserve business processes, temporal dependencies, or every undocumented invariant. This is a controlled sensitivity diagnostic, not official Test Suite Accuracy, semantic equivalence proof, a business Role annotation, or evidence that G-reasoner works or fails. A no-divergence result after 20 permutations is not proof of equivalence.

## References

- Zhong, Yu, and Klein (EMNLP 2020), [Semantic Evaluation for Text-to-SQL with Distilled Test Suites](https://aclanthology.org/2020.emnlp-main.29/). Their method generates and distills database test suites; the present bounded FK permutation diagnostic is not a reproduction of it.
- Prior local evidence: [static instance-equivalence report](../reports/p0_fk_mapping_instance_equivalence_20261107_01/README.md) and [anonymous aggregate](../reports/p0_fk_mapping_instance_equivalence_20261107_01/aggregate_summary.json).
