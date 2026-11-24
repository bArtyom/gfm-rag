# BizWeave BIRD-Ent 30-Case Codex Evidence-Review Pilot

**Run ID:** `bizweave_birdent_codex_review_pilot_20261124_001`
**Status:** completed; exploratory continuation gate passed.
**Level:** bounded pilot. This is not a benchmark result or a main-method comparison.

## Research question

Do benchmark business documents contain source-supported links to physical schema columns, including explicit business rules that jointly depend on multiple columns? This pilot measured annotation yield and evidence traceability. It did not test automatic graph induction, document retrieval, schema linking performance, SQL generation, or research novelty.

## Preregistered protocol

The preregistered protocol, configuration, selector, and validator are in this repository:

- [Protocol](../../plans/bizweave_birdent_codex_review_pilot_20261124_001.md)
- [Configuration](../../../../../configs/text2sql/bizweave_birdent_codex_review_pilot_20261124_001.json)
- [Case selector](../../../../../scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/select_review_cases.py)
- [Annotation validator](../../../../../scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/validate_annotations.py)

The research repository was `https://github.com/bArtyom/gfm-rag`, branch `research/bizweave-human-review-pilot-20261124_001`. The protocol and scripts were archived before opening the selected document/schema cases. The pre-registration branch head was `ca4862fc0cceac08d41535da7747d360ec0d688a`, based on `7a143b2fe8420f65f4ffed58d96e1e65d0a5cc4a`.

## Data and sample

- Dataset: [BIRD-Ent](https://huggingface.co/datasets/jjjycaptain/BIRD-Spider-Ent/tree/cde16ccf0eb606585642d6b06209760d73fd28dc), revision `cde16ccf0eb606585642d6b06209760d73fd28dc`; dataset-card license `CC-BY-SA-4.0`.
- Unit: one unique business document paired with one associated evaluation database schema.
- Sample: 30 cases, consisting of 18 balanced hash-selected cases, 6 cases with the lowest document/schema token Jaccard overlap, and 6 cases selected by predeclared multi-component language cues. These strata are diagnostic and must not be interpreted as representative prevalence.
- Candidate documents were identified through task `gold_knowledge_ids` only to pair documents with their associated schemas. This is an oracle-selected document pool. It cannot support a claim about retrieval quality.
- The review packet excluded question text, SQL, Gold table/column labels, and task IDs. No SQL was executed.

## Review procedure

The current Codex app assistant was the sole reviewer. This was an AI-only review, not an independent human review, double annotation, or expert adjudication. The underlying Codex model/version and app token usage were not exposed. The reviewer was blind to questions, SQL, Gold schema labels, and task identifiers.

Each candidate assertion received one of these labels: `direct_supported`, `inferred`, `ambiguous`, `conflict`, `proposed_schema`, or `unsupported`. Positive edges required an exact source substring and a target column present in the paired schema. A multi-column dependency counted only when one supported assertion expressed a relation, formula, rule, or component dependency over two or more physical columns; co-mention alone did not count.

## Environment and execution

- Environment: Conda `qes_rear_refine`, Python 3.9.20.
- Selector and validator: CPU only, standard-library code. No GPU, local Qwen, external model API, SQL execution, or dependency installation.
- Pre-run resource snapshot: 192 CPU cores, approximately 421 GiB available memory, approximately 108 TiB available filesystem space; four GPUs were present but unused. GPU 0 and 1 were occupied at the snapshot.
- Selection command:

  ```bash
  conda run -n qes_rear_refine python3 scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/select_review_cases.py \
    --dataset-root /path/to/BIRD-Ent \
    --output-dir /path/to/private-results
  ```

- Validation command:

  ```bash
  conda run -n qes_rear_refine python3 scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/validate_annotations.py \
    --packet /path/to/private-results/review_packet.private.jsonl \
    --annotations /path/to/private-results/annotations.private.jsonl \
    --output /path/to/private-results/validated_annotations.private.json
  ```

- No method code was changed during the review. Only the preregistered selector and deterministic validator were used; labels were entered by the current Codex assistant.

## Results

| Stratum | Cases | Cases with a direct mapping | Direct assertions | Claim-to-column edges |
|---|---:|---:|---:|---:|
| Balanced hash sample | 18 | 18 | 70 | 80 |
| Lowest lexical overlap | 6 | 6 | 13 | 15 |
| Multi-component language cue | 6 | 6 | 21 | 27 |
| **Total** | **30** | **30** | **104** | **122** |

Across all assertions, the reviewer recorded 104 directly supported, 5 inferred, 9 ambiguous, 3 conflicting, 25 proposed-schema, and 4 unsupported assertions. Twelve of 30 cases contained an explicit multi-column dependency, spanning all 7 data-asset domains represented in the dataset.

The deterministic validator confirmed exact source-substring matches for all 104 directly supported assertions and schema membership for all 122 positive edges (100% for both checks). Initial review entries with non-exact quotations were corrected against the frozen packet; the validation rule was not relaxed.

## Continuation decision

All preregistered exploratory thresholds passed:

- At least 18/30 cases with direct mappings: **30/30**.
- At least 3/6 direct mappings in the low-overlap stratum: **6/6**.
- At least 6/30 explicit multi-column cases spanning at least 3 domains: **12/30 across 7 domains**.
- Exact evidence and schema-target validation: **100%**.

**Decision:** proceed to prepare a separately preregistered, bounded method-versus-baseline experiment. It should hold documents, schema candidates, input information, and retrieval budget constant, and compare BizWeave against dual-path retrieval and a schema-description graph without explicit business relations. This pilot alone does not establish that BizWeave improves retrieval or Text-to-SQL.

## Interpretation and limitations

The result supports a narrow feasibility claim: within this oracle-selected sample, documents contained directly linkable field meanings and multiple explicit cross-column rules. It does not estimate how common these properties are in the full dataset or in real enterprise repositories. Because candidate documents came from task Gold knowledge associations, this pilot does not evaluate finding the right document. The BIRD-Ent documents are benchmark-created artifacts, not validated enterprise policy manuals. The sole reviewer was an AI assistant, so these labels do not establish annotation accuracy, human agreement, or gold-label quality.

Review cases also exposed duplicated field names across tables, document/schema version mismatches, missing numerical thresholds, and proposed fields absent from the schema. These cases are why the graph representation should retain uncertainty and conflict states instead of converting every text mention into a definite edge. They do not establish that an automated system can detect these states reliably.

The study did not implement graph construction, compare retrieval methods, execute SQL, or verify novelty. A separate method comparison is required before making a utility claim. Any paper claim about mapping precision or recall will require independent review of the mapping labels.

## Resources and accounting

No external model API or local model service was called. The Codex app interaction was the only semantic review mechanism. Its exact input/output token count, underlying model version, and app cost were unavailable; one unknown-usage event was recorded in the local usage ledger. This repository report does not claim a known Codex token count or cost.

## Privacy and artifacts

Only the preregistration code, protocol, anonymized aggregate, and this report are public. The documents, case identifiers, schemas, exact spans, case-level annotations, questions, and SQL remain in private local storage. Public provenance hashes are listed in [the aggregate file](aggregate.public.json).

## Reproduction artifacts

- [Anonymous aggregate](aggregate.public.json)
- [Frozen protocol](../../plans/bizweave_birdent_codex_review_pilot_20261124_001.md)
- [Config](../../../../../configs/text2sql/bizweave_birdent_codex_review_pilot_20261124_001.json)
- [Selector](../../../../../scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/select_review_cases.py)
- [Validator](../../../../../scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/validate_annotations.py)
