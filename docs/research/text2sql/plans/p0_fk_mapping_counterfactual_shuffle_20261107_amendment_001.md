# Amendment 001: operational definitions for FK counterfactual views

**Experiment:** `p0_fk_mapping_counterfactual_shuffle_20261107_01`
**Timing:** registered after the two protocol-only model critiques and before opening the fixed SQL/sample
**Status:** preregistered clarification; no sample, SQL, database connection, or row result has been read for this experiment

## Reason for amendment

Two local models independently reviewed the public protocol. Qwen2.5-Coder-7B recommended proceeding and asked for source-hash and view-construction checks. Qwen3-4B-Think2SQL recommended revision because “referentially valid” and unique-constraint handling should be operational. Its separate concern that the protocol did not define the below-threshold stop was already covered by the original stop rule. The model critiques are process feedback, not correctness labels.

## Frozen clarifications

1. **Input integrity.** Before parsing SQL or opening a SQLite connection, stream-hash the two BIRD JSON files, the exact frozen source manifest, the prior Full_002 private metrics, and each of the four SQLite files. The JSON and source-manifest hashes must match the prior public report/config. Record SQLite hashes in a private input manifest and verify they are unchanged at run end. Hashing bytes is not SQL parsing or query execution.
2. **Eligible FK columns.** Both alternative predicates must be the already-frozen single-column declared FK mappings for that pair. Each changed child column must be a non-PK field, appear in exactly one single-column FK constraint, have a stable SQLite `rowid`, and have every non-NULL value in its referenced parent-key domain. Exclude a pair if its changed fields overlap, belong to any composite FK, or occur in a table with a declared `CHECK` constraint or generated column.
3. **Unique constraints.** Inspect `PRAGMA index_list` / `PRAGMA index_info` and table metadata. A changed field may participate in a single-column unique index (its exact value multiset is preserved); exclude it if it participates in a multi-column unique index. For each generated view, verify row count, exact value multiset, NULL count, parent-key membership, and every applicable unique index before SQL execution. A failed check invalidates that perturbation; it is never silently counted.
4. **View construction.** Open each main SQLite file using `mode=ro&immutable=1`. Store rowid-to-permuted-value assignments only in connection-local TEMP tables. TEMP views shadow only the source table(s) with explicit column projections; every unaffected source column is passed through unchanged. Close the connection after the two SQL variants are compared. No main-schema write or source-file copy is permitted.
5. **Permutation set.** For each pair, construct exactly 20 distinct combined assignments from base seeds 20261107–20261126 using deterministic rejection sampling (advance a per-seed attempt counter when a draw is identity, duplicates an earlier assignment, or fails a registered invariant). Stop after 100 attempts for a seed; if 20 valid distinct assignments cannot be built, mark the pair ineligible and report the reason. No adaptive sampling based on SQL outputs.
6. **Primary denominator.** A perturbation is informative when at least one of the two query Bags is nonempty. A fixed pair enters the `EverBagDiverged@20` denominator only if at least one of its 20 valid perturbations is informative. If all 20 are both-empty, report it as `all_perturbations_empty` and exclude it from the primary denominator. A pair is divergent if any informative perturbation has different Bags. The minimum coverage gate of 40 pairs across at least three anonymous databases applies to this informative denominator; if it fails, stop without widening eligibility.

## What does not change

The fixed 55 original-instance Bag-equal candidate comparisons, query variants, twenty-per-pair budget, seed range, positive/weak thresholds (50% / 25%), 40-pair and three-database minimums, CPU-only SQL execution, and stop-after-one-Full rule remain unchanged. No G-reasoner ranking or additional model vote is authorized by this amendment.
