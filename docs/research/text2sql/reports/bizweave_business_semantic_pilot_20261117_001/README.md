# BizWeave Business-Event Pilot

**Status:** completed; synthetic mechanism gate passed; real-data semantic-label gate remains open.
**Run ID:** `bizweave_business_semantic_pilot_20261117_001`
**Evidence level:** exploratory feasibility only; no paper claim.

## Research question

With identical joinable candidate mappings, does explicitly matching query event, status, grain, and evidence state distinguish business implementations better than shortest-path and unstructured lexical selection, while abstaining when the evidence or time basis is unresolved?

The experiment followed the frozen [protocol](../../../../../experiments/bizweave_business_semantic_pilot_20261117_001/protocol.md). It narrowed the supplied BizWeave proposal to its recommended query-aware retrieval line. It did not attempt automatic multi-source graph construction, model training, GFM adaptation, or downstream SQL generation.

## Result

The hand-authored synthetic fixture passed its preregistered behavior gate:

| Selector | Exact mapping, resolved cases | Correct pair switches | Correct abstentions, unresolved controls |
|---|---:|---:|---:|
| Shortest physical path | 4/8 | 0/4 | 0/2 |
| Schema token overlap | 5/8 | 1/4 | 0/2 |
| Flat mapping-description overlap | 5/8 | 1/4 | 0/2 |
| BizWeave structured constraints + verified evidence | **8/8** | **4/4** | **2/2** |
| BizWeave without evidence gate | 8/8 | 4/4 | 1/2 |

The eight resolved cases covered purchase vs. browse, completed payment vs. payment attempt, completed refund vs. requested refund, and order vs. line-item grain. Two controls had either an unverified payment-state mapping or an unspecified purchase-time basis. Removing the evidence gate caused the selector to accept the unverified state mapping.

These are deterministic checks on manually authored queries, mappings, and labels. The intent parser and verified evidence were supplied by the fixture; the result does not show that a model can infer them from real data. No statistical inference is warranted for ten constructed cases.

## BIRD candidate-supply audit

The runner parsed every frozen question-SQL pair with SQLGlot and reported only aggregate counters. All files matched their registered hashes; all 9,428 train and 1,534 dev SQL statements parsed. Train/dev database overlap was 0.

| Fixed lexical/SQL proxy | Train | Dev |
|---|---:|---:|
| Question state cue + Gold-SQL status/state predicate | 15 / 4 DBs | 0 / 0 DBs |
| Question time cue + Gold-SQL date/time predicate | 365 / 50 DBs | 57 / 8 DBs |
| Question count/grain cue + Gold-SQL COUNT or GROUP BY | 2,393 / 69 DBs | 340 / 11 DBs |
| Multi-table join + any state/time/grain proxy | 1,877 / 69 DBs | 271 / 11 DBs |

The preregistered count threshold for collecting candidates for a later annotation study was met for time, grain, and the combined proxy. The state-specific signal was absent in dev. The combined proxy only says a question has one lexical cue and a multi-table Gold query; it does **not** identify a competing business path, prove the SQL is the only valid implementation, or establish a correct event label. Therefore, the real-data scoring stage did not start.

BIRD-dev has been used in prior project work and is not an independent test set. These counts are a data-readiness screen, not retrieval quality or evidence that BizWeave works on BIRD.

## Decision

**Keep the idea, but keep it exploratory.** The synthetic check confirms that a typed mapping can encode the distinctions in the proposal and that evidence status can prevent one false acceptance. The available BIRD data offers many time/grain candidates for review but no strict state examples in dev and no business-path labels. The full claim remains untested.

The next evidence-bearing step is a blinded, database-grouped review of candidate BIRD cases (or a domain dataset with trusted documentation/query logs) that labels valid alternative implementations, event roles, status meanings, time basis, grain, and unresolved cases. Only after that review should a real-data comparison run against same-candidate Schema lexical and structural baselines. Do not proceed to contrastive training or SQL-EX evaluation yet.

## Reproducibility

- **Project repository:** [`bArtyom/gfm-rag`](https://github.com/bArtyom/gfm-rag), branch `research/bizweave-event-constraints-20261117`.
- **Starting commit:** `cb6fe5f4f32a011861d9cf91c0497fb3483450ff` (`origin/main`). The local branch committed the frozen protocol and runner before execution at `b00945c9656ce94f2963a809c125b86ed6e28961`; it recorded launcher recovery at `ecc91c9` before the successful smoke. The local GitHub push lacked CLI credentials, so the same reviewed files are mirrored to the connected GitHub branch after the run; the public commit timestamps reflect archival, not the local preregistration time.
- **Input:** BIRD train/dev question-SQL JSON and schema JSON, read-only from `/mnt/liansp3/sources/datasets/bird`. SHA-256 values are in the [protocol](../../../../../../experiments/bizweave_business_semantic_pilot_20261117_001/protocol.md) and [anonymous aggregate](aggregate.public.json).
- **Environment:** Python 3.10.22, SQLGlot 26.33.0, existing `t2sql_code_audit_20261005` environment. No dependency installation.
- **Resources:** CPU only; full audit runner time 10.83 s (shell wall 12.05 s). All four GPUs were occupied at preflight and none was used. Peak RSS was not instrumented; the 4 GiB limit was the preregistered cap, not a measured peak.
- **Models and costs:** no local or external model calls, SQL execution, training, or downloads; confirmed model/API tokens 0, external API cost USD $0, GPU time 0.
- **Output:** local raw aggregate `/mnt/liansp3/sources/results/bizweave_business_semantic_pilot_20261117_001/full_001.json`; logs `/mnt/liansp3/研究工作区/03_实验中/QuadGraph-Text2SQL-20261014/logs/bizweave_business_semantic_pilot_20261117_001/`. Only anonymous counters and synthetic fixture outputs are in Git.
- **Launcher issue:** first smoke launch failed before the Python process started because `/usr/bin/time` was absent. The failure log is preserved; a pre-run amendment changed only the timing wrapper/output name. The retry and full run completed.

Smoke command (five rows per split):

```bash
conda run -n t2sql_code_audit_20261005 \
  /root/miniconda3/envs/t2sql_code_audit_20261005/bin/python3.10 \
  experiments/bizweave_business_semantic_pilot_20261117_001/run_pilot.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird \
  --output /mnt/liansp3/sources/results/bizweave_business_semantic_pilot_20261117_001/smoke_retry_001.json \
  --limit-per-split 5
```

Full command (all frozen BIRD rows):

```bash
conda run -n t2sql_code_audit_20261005 \
  /root/miniconda3/envs/t2sql_code_audit_20261005/bin/python3.10 \
  experiments/bizweave_business_semantic_pilot_20261117_001/run_pilot.py \
  --dataset-root /mnt/liansp3/sources/datasets/bird \
  --output /mnt/liansp3/sources/results/bizweave_business_semantic_pilot_20261117_001/full_001.json
```

## Artifacts

- Idea brief: [BizWeave](../../ideas/bizweave.md)
- Frozen protocol and runner: [`experiments/bizweave_business_semantic_pilot_20261117_001`](../../../../../experiments/bizweave_business_semantic_pilot_20261117_001/)
- Anonymous aggregate: [aggregate.public.json](aggregate.public.json)
