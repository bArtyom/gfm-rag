# Seed-to-Steiner pilot: frozen exploratory protocol and implementation plan

User approval: the chat approved semantic table/column seeds -> schema graph -> Steiner connection and explicitly requested cloning related code, adapting it, and running experiments. No changes to frozen GFM/QES experiments or stopped G-reasoner ranking lines.

## Contract

One hypothesis: starting from the same semantic table seeds, Steiner completion recovers reference-used bridge tables better than adding the same number of tables by semantic rank. This is an exploratory development-set experiment, not a novelty claim or independent benchmark.

Owned archive: bArtyom/gfm-rag; branch research/seed-steiner-pilot-20261108; base cb6fe5f4f32a011861d9cf91c0497fb3483450ff. Read README, research hub, experiment-roadmap and reproducibility-contract. Existing historical gates remain unchanged; this user-authorized pilot is a separate protocol.

Upstream: https://github.com/thanhdath/grast-sql, commit 4c698cae31da8299deb5c809101d172d5b2ddeb3. Read README, environment.yaml, modules/steiner_tree_spanner/{__init__,steiner}.py. No LICENSE file or declared redistribution license was found. Keep checkout unchanged outside this repository; dynamically import the public helper locally. Publish only independently authored adapter/runner/config/tests. This is a component adaptation using frozen local embeddings, NOT a full GRAST-SQL reproduction or its trained reranker/GNN.

## Design

- Reuse the frozen P1.6 Qwen3-Embedding-0.6B 1024-D cache. Verify source question/schema/cache/node-manifest hashes and row identity; do not infer against reference SQL. Default seeds: top two TABLE embeddings by cosine, stable table-ID ties. Column-seed mode is an API capability only, not another experimental branch.
- Build FK column graph from SQLite PRAGMA metadata, using synthetic IDs to preserve names with dots. Call upstream get_steiner_subgraph without its final Top-K truncation. Recover bridge table IDs from returned column nodes. Keep disconnected seed components explicit; do not invent join edges.
- Serialize every column of selected tables, retaining original names/types/PKs and all complete actual FK constraints among selected tables, including parallel relationships, composite keys and self references. This first pilot selects tables; it does not claim fine-grained column pruning or unique join-role resolution.
- Three arms only: seed_only; dense_size_matched (top N semantic tables, N = Steiner output table count); seed_steiner. Same seed scores, question/evidence, schema source and generator. Table COUNT is matched for the latter two; prompt tokens are measured, NOT claimed equal. Independent fallback to full schema is forbidden.
- Seal predictions before loading reference SQL for evaluation. Reference-used tables are a proxy; equivalent SQL can use different tables. SQL EX is a separate single-instance result metric, not semantic equivalence.

## Experiment budget and decisions

Main layer, exploratory: 5-question smoke, followed by one cached CPU retrieval pass on BIRD dev 1,534 questions / 11 databases. No tuning, training or new embedding inference. CPU <=16 threads, RAM target <8 GiB. Hash-selected smoke: first five global (SHA256 of seed|db_id|question_id); SQL pilot: next four per database excluding smoke (44 questions). Selection never inspects labels or method outcomes.

Metrics: reference-table complete coverage (primary structural proxy), macro table recall/precision, mean selected tables/columns, token counts, graph-disconnected cases, paired rescues/damage, per-database aggregates. Report bridge-expansion slice and whole sample separately; no filtering failures out of denominators. Predeclared positive structural signal: at least one net complete-coverage rescue over dense_size_matched AND seed_only on expandable cases. If no signal, stop expansion and report negative retrieval result; do not spend GPU on SQL. Smoke success concerns engineering, not efficacy.

If structural signal exists and resources permit: 5-question SQL smoke (15 generations), then the fixed 44-question pilot (132 generations). Same local Qwen3-4B checkpoint for all arms; greedy, thinking disabled, 768 max new tokens, 8,192 max input tokens, one generation/arm, seed 20261108. No paid API fallback. Fixed GPU 0 requires >=12 GiB free immediately before load; batch=1; <=1 GPU-hour. Resource failure leaves CPU results valid and SQL pending. Prompt overflow/truncation and SQL extraction failures are reported as failures, not dropped. No repair loops.

Reuse the repository's read-only bounded SQLite evaluator (Set EX primary, Bag secondary); timeout 10 seconds, row/byte/memory caps unchanged. Unsupported gold/execution cases remain unknown and are separately counted. Report 44-question pilot separately from five smoke examples. No official BIRD leaderboard claim, independent replication, ablation sweep or new model/dataset expansion in this run. End with retain/upgrade/downgrade/stop.

## Implementation tasks

Task 1 — adapter and scientific checks. Files: scripts/text2sql/seed_steiner.py; tests/test_seed_steiner.py. Interfaces: connect_schema(schema, constraints, seeds, upstream_path) -> selected tables, complete constraints, disconnected status; rank_seed_tables(schema, nodes, scores, seed_count, source). Test-first checks: bridge recovery using actual upstream helper, all seed retention, disconnected graph, full composite FK and parallel-role retention, names with dots, empty/one seed, finite score validation, physical-table extraction with CTE shadowing. Expected: targeted tests pass without any model/API call.

Task 2 — frozen runner. File: scripts/text2sql/run_seed_steiner.py; config: configs/text2sql/seed_steiner_bird_20261108.json. Verify hashes/versions/cache alignment before any score; create mode-specific new output directories exclusively; write private JSONL predictions then score labels, aggregate without question/SQL text. Run smoke, then full retrieval once; preserve logs and checksums. Tests cover cache row mapping, deterministic label-blind split and no silent overwrite.

Task 3 — conditional SQL and report. File: scripts/text2sql/run_seed_steiner_sql.py. Test output extraction and metric accounting before GPU use; record every local generation attempt in shared usage ledger with stable IDs, actual token lengths and separate GPU time. Freeze prediction file before evaluation. Save sanitized report/aggregate/config/commands under docs/research/text2sql/reports/seed_steiner_bird_20261108_01. Review changes, commit/push independent branch, verify GitHub contents. Do not upload upstream code, data rows, prompts, SQL, logs or model files.

Review focus: disconnected terminals; ambiguous/parallel FKs; composite keys; labels leaking through cached result files; size-matched comparison being mislabeled token matched. Native worktree tool could not verify the remote path; an independent clone is used. Reuse existing think2sql_20260909 environment with its absolute Python executable inside conda run; install nothing. This avoids the known environment/Python mismatch.

## Amendment 001: verified existing database snapshot, before scientific scoring

Smoke_001 stopped during metadata loading, before any predictions, metrics or inference: the shared student_club file contains FKs to a missing internal table. This is a pre-existing documented schema migration, not caused by this run. The resource index already registers bird_dev_aligned_qes_20261012: ten databases are links to unchanged originals; student_club is a separate original-archive-aligned copy. Its SHA256 eb89bcfe97eefa386a27904ec5aa15159811a7eac894ec659a36e48fa9f76b77 also matches the registered official Mini-Dev package copy. Reuse that existing snapshot without copying or modifying any database/link. Freeze all eleven DB hashes in a NEW config seed_steiner_bird_aligned_20261108.json; preserve the first config/log. All subsequent runs use this config. Queries, cache, seed count, split, metrics and gates are unchanged. Smoke_002 is the one recovery attempt for this data-path issue. The manifest/schema/name hashes are verified before scoring; all complete FK constraints come from the aligned SQLite metadata. Original graph and cached embedding text versions remain separately identified.
