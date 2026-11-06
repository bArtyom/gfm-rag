# Model-proxy FK mapping ranking pilot (G-reasoner)

**Status: completed exploratory diagnostic; NO-GO.** The first Smoke attempt failed before model loading; corrected Smoke and Full completed. The three-model labels remain proxies only. This branch does not replace the original two-human-reviewer gate and cannot support a claim about human Role accuracy.

## Research question and core hypothesis

Given a natural-language question, the pair of tables extracted from its reference JOIN, and the pair's declared FK mapping candidates, does the frozen G-reasoner-34M rank a three-model high-confidence majority mapping above the shared Qwen3 dense-cosine baseline?

The hypothesis is intentionally narrow: query-conditioned message passing over reified FK mapping nodes may improve Accepted@1 on the model-proxy-distinguishable subset. The test is exploratory, on previously exposed BIRD dev data, and cannot establish algorithm novelty, end-to-end JOIN discovery, SQL execution accuracy, or correct human labels.

## Experiment layer, budget, and gates

- Layer: one exploratory transfer/contradiction diagnostic, not a main result.
- Budget: one five-question Smoke and one Full over the remaining 55 question-pairs; one frozen G-reasoner checkpoint; one local Qwen3-Embedding-0.6B snapshot; no training, tuning, prompt search, extra seeds, or added questions.
- Smoke: choose five unique question keys from the frozen 60 by sorting `SHA256("20261106:" + question_key_sha256)` and taking the first five. Selection reads no model score or label. Every pair from a selected question is held out from Full. Smoke checks embeddings, candidate coverage, graph structure, finite model scores, and output shape only; no Smoke score enters metrics.
- Full data gate after Smoke exclusion: at least 30 model-proxy-adjudicable pairs, at least 20 distinguishable pairs, and at least three anonymous databases. The frozen split currently yields 51 adjudicable and 38 distinguishable pairs across four databases (5, 10, 10, 13 distinguishable pairs in anonymous order). If code recomputation disagrees, stop before model inference.
- Smoke pass: all five graphs produce finite per-candidate scores; query/node/relation vectors have dimension 1024 and are finite; every frozen candidate is scored exactly once; both endpoint seeds are set for each graph; no label value enters model input.
- Full screen: report GFM and Dense Accepted@1 on the 38 distinguishable pairs. A positive screen requires GFM minus Dense ≥5 percentage points, at least four net rescues (GFM-only correct minus Dense-only correct), and positive within-database net rescue in at least two databases that each have at least five distinguishable pairs. This is a screening rule, not a significance test. If positive, stop and request a separately approved human-labeled validation plan; do not auto-launch another experiment. Otherwise stop this BIRD-dev proxy ranking direction.
- Stop immediately on hash mismatch, missing candidate, label leakage into scoring inputs, non-finite output, resource limit, unexpected output overwrite, or unrecoverable runtime error. Preserve the failed run and do not switch model, seed, or graph design under the same run ID.

**Protocol revision v2, before any ranking inference:** the initial 1 GiB GPU-memory budget was too low for the local Qwen embedding encoder plus G-reasoner. It is raised to an 8 GiB GPU peak budget and 16 GiB process RSS limit. Dataset, model, graph, methods, labels, metrics, success gates, run IDs, and stop rules are unchanged. This correction follows the frozen local model footprint and avoids an avoidable allocation failure; it does not authorize exceeding the new limits.

**Smoke attempt `..._smoke_001` (2026-11-06):** input loading stopped before model initialization because one packet question serialized a line break as the literal `<br>` while the private manifest retained a newline. Diagnostic checks found 59 exact text matches and one such serialization-only difference; replacing that exact `<br>` with a newline matches the canonical private text. The affected pair is in Full and in the model-proxy-distinguishable subset. No model was loaded, no embeddings or G-reasoner forwards ran, and no inference tokens were consumed. The failed launch log is retained locally. No data, labels, split, candidate set, model, graph, metric, or threshold changed.

**Protocol revision v3, before retry:** validate the one frozen `<br>`→newline serialization exception explicitly and reject any additional or different mismatch. Query embeddings and BM25 use the canonical private-manifest question text; the prior model-review labels remain tied to the immutable blind packet as reviewed. The Full report will include a predeclared sensitivity result excluding this one distinguishable pair (denominator 37) alongside the primary 38-pair metric. Run IDs advance to `..._smoke_002` and `..._full_002`; the failed `smoke_001` is never reused. The source text anomaly and label provenance will be disclosed; no labels are promoted to human truth.

**Outcome:** Smoke_002 passed. Full_002 scored 55 pairs, including 38 distinguishable proxy-labeled pairs. G-reasoner Accepted@1 was 7/38 versus Dense Cosine 27/38 (−52.63 pp), with paired net rescue −20 and zero anonymous databases having positive net rescue. Excluding the one serialization-anomaly pair gives 7/37 versus 27/37 (−54.05 pp), same direction. All registered positive-screen gates failed. Per the stop rule, no GFM ablation, parameter search, or additional run was launched. Full report and sanitized aggregate are archived at [the experiment report](../reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/README.md) and [aggregate summary](../reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/aggregate_summary.json).

## Frozen source and inputs

- Project repository: `https://github.com/bArtyom/gfm-rag`, branch `research/p0-model-proxy-rank-pilot-20261106`; project HEAD before this registration: `2a399931c87e4cc10acedd9ea09497a186fee7ca`.
- Upstream method code: `https://github.com/RManLuo/gfm-rag`, commit `b3e43219c49929da505244df4f0ba54c0947e4c4`. The user-owned project repo contains the experiment adaptations; no report or change is written to upstream.
- Read before registration: root README, `docs/research/text2sql/README.md`, `experiment-roadmap.md`, `reproducibility-contract.md`, the G0-02 report/code, the three-model proxy report, the GFM input-semantics audit, and the checkpoint/Query-instruction compatibility audit.
- Blind-review input: 60 question-pairs and 135 mapping candidates. Public-safe hashes: A packet `0b6102f38c9a60afa9434091ce3b9c94e35460c47e105de804cfd119d826cfa2`; B packet `a30230c9562f95e00c0af88e7cd0277d6d27e9f26eca2863ca968540b944dfdb`; third-model response `88c5b79785af76896055378ece4776b523bdb036588304cd63305db51a10d333`; private manifest `14d3e65e53bbc29c03d312fb32227c47b568242502e30bc3c4d4656b97521ed7`.
- Three-model label rule: exact agreement on decision and accepted mapping-ID set, with at least two agreeing model reviewers at confidence ≥2. Only single-/multiple-mapping decisions with a nonempty accepted set are adjudicable. A pair is distinguishable only when the accepted set is a strict subset of the frozen candidate set. All labels are read by the evaluator after scores are fixed; labels, answer rationales, A/B/C raw outputs, Gold SQL, and reference JOIN are never features or embeddings.
- Data and model outputs remain in local permission-restricted folders. Public artifacts contain aggregate counts and metrics only; do not commit questions, table/database names, mapping IDs, per-case labels, raw outputs, per-case rankings, database IDs, SQL, or local manifests.

## Frozen methods and representation

1. **Reified G-reasoner (primary method).** Use the released 34M checkpoint with 1024-dimensional node, relation, and query vectors. Each graph has two table nodes and every frozen FK mapping as one node. Nodes are ordered by stable table name and mapping ID. Each mapping retains its full ordered composite column pairs and child→parent direction. The graph contains the four G0 endpoint relations: child table→mapping, parent table→mapping, mapping→child table, mapping→parent table. Add inverse edges exactly as the G0 reified probe does. Set a shared binary start mask on both table nodes for every candidate graph; keep the actual child/parent edge direction unchanged. Rank mapping nodes by returned G-reasoner node score.
2. **Dense Cosine (single primary baseline).** Use the exact same query vector, exact same mapping text vectors, candidate universe, normalized 1024-dimensional Qwen3 embeddings, and stable tie-break as G-reasoner.
3. **BM25 (secondary control).** Tokenize raw question and the same candidate mapping text with lowercase Unicode word tokens; Okapi parameters k1=1.5 and b=0.75. Candidate ties break by mapping ID.
4. **Query-independent order (secondary control).** Give every candidate the same score and sort by stable mapping ID. This is the fixed structural-order control; it makes no semantic claim.

Query text is the canonical private-manifest question text. The packet parser's only accepted serialization repair is the frozen literal `<br>`→newline conversion described above. Query instruction is exactly `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: `, matching the G-reasoner checkpoint config. Mapping, table, and relation passages receive no query instruction, matching the checkpoint's null passage instruction. The query and mapping vectors are shared between the Dense baseline and G-reasoner. Table-node text is `Table: <table>. Declared FK columns appearing in this candidate set: <sorted unique columns>.` Mapping-node text serializes the full ordered child/parent column pairs. Relation text uses the fixed four strings in `g0_fk_instance_node_probe.py`.

Candidate ordering is score descending, then stable mapping ID ascending. This deterministic tie-break applies to every method. Do not compare raw scores across graphs. Duplicate declarations collapse by the frozen full mapping identity; multiplicity is metadata only.

## Metrics and analysis

- Primary: Accepted@1, evaluated only on the 38 distinguishable Full pairs.
- Sensitivity: repeat the primary metrics after excluding the single Full pair with the documented packet serialization anomaly; report its denominator and paired rescue/damage counts. This is a fixed input-quality sensitivity check, not another run or parameter comparison.
- Secondary: Accepted@3, reciprocal rank of the first accepted candidate, Accepted@1 over all adjudicable pairs, paired rescue/damage counts, and anonymous-database macro metrics.
- Report per-database denominators, Accepted@1, and net rescue. Report paired bootstrap by question only as exploratory uncertainty if computed; no confirmatory p-value. The frozen cohort has one pair per question.
- Report candidate coverage, excluded/undecidable counts, exact tie counts, vector norms/shapes, graph sizes/edges, and runtime/resource measurements.
- Error analysis uses only anonymous categories such as model-proxy decision type and score/rank pattern. Per-case details remain local.

## Resource and execution contract

- Reuse `/mnt/liansp3/sources/models/g-reasoner-34m`, Qwen3 embedding model, and the verified `gfmrag_greasoner_20261022` environment; no downloads, package installs, driver changes, or paid APIs.
- The verified environment command is `conda run -n gfmrag_greasoner_20261022 /root/miniconda3/envs/gfmrag_greasoner_20261022/bin/python3.12 ...`. A pre-inference environment probe found that unqualified `python3` under `conda run` resolves to the unrelated Python 3.9 environment because of PATH ordering. No model was loaded during that probe; the absolute interpreter selected the already-installed frozen environment and matched all expected versions. No environment changes were made.
- Before each launch, record `nvidia-smi`, `free -h`, `nproc`, and disk availability. Assign only a currently free GPU and pin it with `CUDA_VISIBLE_DEVICES`. Reservation: one RTX 4090; at most 8 GiB GPU memory, 16 GiB process RSS, 20-minute wall limit; stop rather than contend with another active job.
- Run IDs: failed pre-inference Smoke `p0_fk_mapping_model_proxy_rank_pilot_20261106_smoke_001` (preserved); retry Smoke `p0_fk_mapping_model_proxy_rank_pilot_20261106_smoke_002`; Full `p0_fk_mapping_model_proxy_rank_pilot_20261106_full_002`. Private results live under `/mnt/liansp3/sources/results/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`; logs under `/mnt/liansp3/logs/gfmrag_p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`. Refuse any existing run directory.
- Run from the project root with the explicit GFM environment and offline local model loading. Record code commit, config hash, checkpoint and embedding hashes, exact command, dependency versions, CUDA device, input hashes, and output hashes in each run manifest.
- Qwen embedding request batches are local model calls: count actual tokenizer input tokens including the query prefix, record each batch with a stable call ID in the shared usage ledger and output tokens 0. G-reasoner consumes vectors/graph structures, not text tokens; report forward count and GPU time separately. No external API or billing cost is expected; report as no API charge, not zero resource cost.

## Expected deliverables

- Plan and YAML config in this repository before inference.
- Runner and sanitized public aggregation code in `scripts/text2sql/` before inference.
- Separate Smoke/Full logs, manifests, private per-pair predictions, and sanitized aggregate under the reserved local result tree; never upload private data.
- Final report and sanitized aggregate are archived under `docs/research/text2sql/reports/p0_fk_mapping_model_proxy_rank_pilot_20261106_01/`, with separate run IDs, assumptions, code/config hashes, exact results, anomalies, interpretation, limitations, and GitHub commit/link.

## Interpretation boundary

The table pairs are derived from reference JOINs. The experiment conditions on those endpoints and tests only mapping discrimination by a frozen G-reasoner against a shared dense baseline, using model-generated proxy labels on a previously exposed development set. A positive screen means only that G-reasoner agrees better with this proxy consensus under this setup. It is not evidence of human truth, end-to-end JOIN generation, missing-FK discovery, SQL execution improvement, cross-database generalization, or a new QuadGraph algorithm.
