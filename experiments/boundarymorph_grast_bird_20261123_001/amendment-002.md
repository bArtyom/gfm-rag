# Amendment 002: BoundaryMORPH observation tuple

- Date: 2026-11-23.
- Second smoke attempt: `smoke_5q_20261123_02` aligned all frozen inputs, loaded the local Jina proxy, and completed 155 query-column scoring pairs across the fixed and random policies plus the first BoundaryMORPH round. The BoundaryMORPH acquisition then stopped because its observed-index set expected two-field records while the runtime stores a third field for tokenizer input length.
- The run directory is preserved, including completed fixed/random smoke outputs and `progress.json`. Confirmed local Jina usage for this partial attempt: 8,855 input tokens, 0 output tokens, 155 pairs, and 1.536 GPU-seconds. No full run began.
- Correction: read the candidate index from each observation record without unpacking the optional token-count field. Add no method, budget, or configuration changes. Retry in a new smoke directory; do not overwrite this partial run.
