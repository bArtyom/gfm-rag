# P2d.3 amendment: same-source Smoke recovery

**Status:** Registered before further inference. This amendment preserves the original method, sample, success criteria, and total resource limits.

## Why this amendment is needed

- The frozen Smoke sample completed as `smoke_001` on source commit `e62ed2180d7d72c723a42366a4d40216e14ff02f`. Its operational gate passed: all five reference/predicted SQL pairs were executable. Each arm had 3/5 Set EX and 2/5 Bag EX; no repair was triggered. The run made five local model requests with reported usage of 4,732 input and 236 output tokens.
- The subsequent `full_001` launch used source commit `f9f15613c0e1e55b1d8accaf4db77de23609301a`. The runner stopped at its frozen Smoke/Full source-identity gate before the first model request. Its start receipt and failure receipt remain in the private result directory; no SQL prediction or Full request was produced.
- The commits differed because the post-Smoke runner revision allowed the registered `smoke_pass_full_pending` state. The SQL-generation procedure and prepared cases did not change, but the runner intentionally requires exact source identity between Smoke and Full.

## Recovery protocol

- Keep the original prepared cases unchanged: Full 66 and Smoke 5, with all 33 prior P2d prepared questions excluded. Reuse the same five registered Smoke cases as a source-consistency check; do not treat this operational rerun as an independent accuracy sample.
- Use new, non-overwriting run IDs and directories: `p2d3_context_bounded_repair_smoke5_20261105_02` / `smoke_002`, then `p2d3_context_bounded_repair_full66_20261105_02` / `full_002`.
- Run both stages on the same clean, published commit and the same local vLLM process identity. Full still requires Smoke's `smoke_gate=PASS` and matching source/service receipts.
- Keep all arms, prompts, one-repair limit, read-only safeguards, sample, metrics, success criteria, and stop rules unchanged.

## Remaining budget

The original caps were 213 model requests, 7,000,000 input tokens, 200,000 output tokens, and 14,400 seconds of stage wall time. Subtract the confirmed `smoke_001` usage and wall time. The amended caps for `smoke_002 + full_002` are therefore 208 requests, 6,995,268 input tokens, 199,764 output tokens, and 14,382.912179963663 seconds. This keeps the combined experiment within the originally registered maximum; it does not add budget.

The two startup/identity preflight failures and `full_001` source-gate stop produced no inference requests and consumed none of these model-call budgets. Local GPU startup/compute time is tracked separately; the first Smoke runner did not measure exact GPU-active seconds.

## Files and privacy

The private `smoke_001` and `full_001` receipts/logs remain in their original directories. The new attempts use the fixed paths above. No question IDs, prompts, SQL, database names/paths, or result rows are added to this amendment.
