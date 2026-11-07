# BIRD train FK constraint identity audit — Amendment 001

Parent registration: [`p0_bird_train_fk_constraint_identity_20261107.md`](../p0_bird_train_fk_constraint_identity_20261107.md)  
Amendment ID: `p0_bird_train_fk_constraint_identity_20261107_01_amendment_001`  
Status: registered after a runner preflight failure; no SQLite access occurred in the failed Full run.

## Failure preserved

- Original Smoke `p0_bird_train_fk_constraint_identity_20261107_01_smoke_001` passed 5/5. Metadata and SQLite column-pair sets aligned exactly for all five units; database hashes did not change.
- Original Full `p0_bird_train_fk_constraint_identity_20261107_01_full_001` stopped with `smoke_receipt_mismatch`. It reconstructed the fixed train candidate set, then rejected the valid Smoke receipt before resolving or opening any SQLite file.
- Root cause: the runner compared the complete `input_hashes` object to a three-key dictionary. The Smoke receipt correctly also included the frozen capacity-stage aggregate and runner hashes, so the object-level comparison failed despite all expected input values matching.
- The failed Full's receipt and log remain at the private paths recorded in the experiment manifest. Its run ID will not be reused.

## Authorized change

Fix only the receipt preflight. Compare all five required hashes by key: train JSON, train schema, dev schema, prior capacity aggregate, and prior capacity runner. Extra receipt fields do not cause rejection. Also validate the run ID against the separately frozen amendment config.

The dataset, candidate reconstruction, deterministic Smoke sample, schema/PRAGMA equality rule, distinct-constraint definition, ≥60-unit/≥4-database gate, read-only authorizer, SQLite URI, and resource caps remain unchanged. This is an engineering recovery; it does not create a new scientific hypothesis or change the registered capacity claim.

## Bounded recovery

- Run one new 5-unit Smoke and, only if it passes, one Full over the remaining 379 fixed units.
- Recovery Smoke uses the same five deterministic candidate IDs as original Smoke; the new run IDs prevent overwriting or reusing old records.
- Run IDs: `p0_bird_train_fk_constraint_identity_20261107_01_amendment_001_smoke_001` and `p0_bird_train_fk_constraint_identity_20261107_01_amendment_001_full_001`.
- Private outputs use new directories `amendment_001_smoke_001/` and `amendment_001_full_001/`. Original `_smoke_001/` and `_full_001/` are retained unchanged.
- CPU only, max 8 threads, 30-minute wall, 20-minute CPU, 4 GiB RSS. No models, GPU, SQL execution, or external API calls.
- Any further runner or input failure stops this recovery. Do not retry these IDs; another attempt requires a new Amendment and run IDs.

If Full reaches at least 60 exact question×table-pair units with two or more distinct complete FK constraint signatures across at least four anonymous databases, the next action is a separate pre-registration for local-model proxy review. Model responses will not be described as human consensus or ground truth.

## Frozen recovery artifacts

- Config: `configs/text2sql/p0_bird_train_fk_constraint_identity_20261107_01_amendment_001.json`.
- Runner: `scripts/text2sql/audit_p0_bird_train_fk_constraint_identity_20261107.py`.
- Frozen config SHA-256: `8bb8f6c6d94b0f50a11fecef2d9cdf6ec7195c31bd2d561d4806bb40358e5ea1`.
- Runner SHA-256: `b37e6599bab1aa88065675fe1c676b6c47b84d1402253ad4deafb4ff160adb82`.
- Input hashes, predecessor aggregate hash, and candidate histogram are inherited without change from the parent registration.
- The config and runner must be committed to `bArtyom/gfm-rag`, read back, and matched to local blob hashes before this recovery reads train SQL or opens SQLite.
