# BizWeave BIRD-Ent Codex Evidence-Review Pilot

**Run ID:** `bizweave_birdent_codex_review_pilot_20261124_001`  
**Status:** preregistered; case selection and review not yet run.  
**Level:** bounded exploratory annotation pilot; not a main experiment or benchmark result.

## Research question and falsifiable claim

Do BIRD-Ent business documents contain source-supported claims that can be linked to physical schema columns, including a useful number of claims whose meaning depends on multiple columns together?

The pilot tests annotation yield and evidence traceability. It does not test whether a model can independently construct a graph, retrieve the right document, improve SQL generation, or establish research novelty.

## Unit, data, and sample

- Dataset: `jjjycaptain/BIRD-Spider-Ent`, revision `cde16ccf0eb606585642d6b06209760d73fd28dc`, dataset-card license `CC-BY-SA-4.0`.
- Unit: one unique knowledge document paired with one BIRD-Ent evaluation database schema, for 30 cases.
- Candidate documents are those referenced by at least one task's `gold_knowledge_ids`. Those IDs are used only to find a document and its associated data-asset/schema context. This is an oracle-selected document pool; it cannot support a claim about document retrieval.
- The case packet contains only a document and its physical table/column schema. It excludes questions, SQL, gold table/column labels, table-name mappings, and task identifiers.
- Sampling is frozen in `configs/text2sql/bizweave_birdent_codex_review_pilot_20261124_001.json` and `scripts/research/bizweave_birdent_codex_review_pilot_20261124_001/select_review_cases.py`: 18 hash-selected cases balanced across the seven data-asset domains, 6 lowest document-to-schema lexical-overlap cases, and 6 cases with predeclared multi-component language cues. The strata are reported separately and are not treated as a representative prevalence estimate.
- The earlier data-shape smoke exposed document ID `0`, evaluation database `california_schools`, and the schema table `xelion11_bkpub_ttl_metadata_drop`. All such cases are excluded from this run. No question text, SQL, or evaluation labels were inspected for that smoke.
- If a stratum cannot supply its registered count, stop before review, record the shortfall, and amend the protocol before selecting replacements.

## Review procedure and label definitions

The current Codex assistant is the sole AI reviewer. It reads the frozen document/schema packet without questions or SQL and records each candidate business assertion with an exact evidence span and zero or more physical column targets.

Each assertion receives one status:

- `direct_supported`: the document span directly supports the stated mapping to an existing physical column;
- `inferred`: the mapping requires unstated semantic inference;
- `ambiguous`: more than one schema target remains plausible;
- `conflict`: the document contains incompatible statements;
- `proposed_schema`: the document implies a field absent from the supplied schema;
- `unsupported`: no defensible column mapping is present.

Only `direct_supported` mappings count as positive Claim→Column edges. A multi-column dependency is counted only when one evidence-backed business assertion states a relation, formula, rule, or component dependency that requires at least two columns jointly; merely listing columns does not qualify. Every positive edge must carry an exact verbatim source substring and an existing table/column target.

This is a single AI review, not an independent human annotation, double annotation, or expert adjudication. A second internal consistency pass and deterministic checks for exact evidence spans and schema membership are quality controls, not independent agreement evidence.

## Outcomes and decision rules

Primary descriptive outcomes:

1. Number of cases with at least one directly supported Claim→Column edge, overall and by registered stratum.
2. Number of directly supported assertions and edges, plus inferred, ambiguous, conflicting, proposed, and unsupported assertions.
3. Number of cases with an explicit multi-column dependency, and number of distinct data-asset domains represented.
4. Exact-span and schema-target validation rates.

Continue to a separately registered method-versus-baseline experiment only if all of the following hold:

- at least 18/30 cases have one or more directly supported Claim→Column edges;
- at least 3/6 low-overlap cases have a directly supported mapping;
- at least 6/30 cases contain an explicit multi-column dependency, spanning at least 3 data-asset domains;
- 100% of counted positive edges pass exact-span and schema-membership validation.

If a threshold fails, stop this annotation expansion and report which part of the proposed mechanism lacks support in this sample. These thresholds are exploratory continuation gates, not statistical evidence of prevalence or effectiveness. Do not run SQL or inspect gold labels in this pilot.

## Resources, privacy, and stop conditions

- CPU-only metadata preparation and deterministic validation; no GPU, model server, Qwen, external model API, SQL execution, or dependency installation.
- The only semantic reviewer is the current Codex app interaction. Exact token usage and app cost are unavailable and must be recorded as unknown; do not invent a model name, token count, or price.
- Private results: `/mnt/liansp3/sources/results/bizweave_birdent_codex_review_pilot_20261124_001/`; logs: `/mnt/liansp3/logs/bizweave_birdent_codex_review_pilot_20261124_001/`.
- Keep document text, IDs, schema packets, annotations, exact spans, and case-level outputs local. Publicly archive only protocol/code, anonymized aggregate counts, hashes, limitations, and the conclusion.
- Stop before annotation if the selected packet contains a question, SQL, gold label, unmatched schema, or missing document. Stop and preserve the run if a file would be overwritten or validation cannot establish exact evidence/span integrity.

## Repository and provenance

- Project repository: `https://github.com/bArtyom/gfm-rag`.
- Branch: `research/bizweave-human-review-pilot-20261124_001`.
- Base commit: `7a143b2fe8420f65f4ffed58d96e1e65d0a5cc4a` (the verified GitHub head of `research/bizweave-event-constraints-20261117` before this pilot).
- Read before execution: repository `README.md`, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, and `reproducibility-contract.md`.
- The protocol, configuration, and case-selection/validation scripts must be committed and pushed before case content is opened for review. Report and anonymized aggregate are separate files under `docs/research/text2sql/reports/bizweave_birdent_codex_review_pilot_20261124_001/`.
