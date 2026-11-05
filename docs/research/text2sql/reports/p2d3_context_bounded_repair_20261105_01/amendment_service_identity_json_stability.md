# P2d.3 amendment: JSON-stable service identity recovery

**Status:** Registered before further inference. The scientific method and prepared sample remain unchanged.

## Trigger

- `smoke_002` passed its operational gate on source commit `764020a8eda7680745b6c3fd1f1c62f72a05ad76`: five cases were executable; each arm had 3/5 Set EX and 2/5 Bag EX; no repair was triggered. It made five local model requests with reported usage of 4,732 input and 233 output tokens.
- `full_002` stopped before the first Full model request with `Full run source or inference service differs from smoke`. Direct comparison of the stored receipts showed matching source commits, source file hashes, service PID, service command line hash, endpoint model ID, and model length.
- Root cause: `service_identity()` returned `models` as a Python list of tuples. JSON serialization converts tuples to arrays; after reading the Smoke receipt, each inner tuple was a list, so equality against the live tuple list failed.

## Minimal correction and recovery

- Normalize the `models` field to a list of two-element lists in `service_identity()`, and compare it to the registered `[[model_id, 32768]]` value. This affects only serialization/equality; it does not change model selection, sampling, SQL handling, or evaluation.
- Preserve the existing `smoke_001`, `full_001`, `smoke_002`, and `full_002` directories and receipts.
- Run the same frozen Smoke cases in `smoke_003`, then the same 66 frozen Full cases in `full_003`, both on the same clean published source commit and vLLM service process. Do not reuse or overwrite prior run directories.

## Remaining budget

The original registered limits were 213 model requests, 7,000,000 input tokens, 200,000 output tokens, and 14,400 seconds of stage wall time. The two completed Smoke stages consumed 10 requests, 9,464 input tokens, and 469 output tokens. `full_001` and `full_002` stopped before model calls; their measured wall times were 0.007510265335440636 and 0.0020720716565847397 seconds. After also accounting for the two Smoke stage wall times, the remaining `smoke_003 + full_003` caps are 203 requests, 6,990,536 input tokens, 199,531 output tokens, and 14,364.88782151416 seconds. The recovery adds no total budget.

No Full prediction was generated and no Full API-ledger row exists in either stopped attempt. Existing model request usage remains recorded in the shared ledger under the two Smoke run IDs. Local GPU compute is tracked separately; exact GPU-active seconds are not currently available from the runner.
