# Amendment 001: repair packet-preparer config lookup

**Status: registered; recovery packet preparation not yet run.** Parent experiment: p0_bird_train_fk_model_proxy_review_20261107_01.

## Observed stop

The first packet-preparation attempt used output directory packet_001 and log packet_prep_001.log. Frozen input hashes passed. After loading the private constraint-audit evidence and BIRD train JSON, the preparer stopped with KeyError 'audit': the frozen configuration stores these capacity fields at inputs.identity_audit. The failure receipt SHA-256 is 56a8a04e75fb2cdd7795c4bdbb57bde2198909e40ae3f5b2e3c755213ad94558.

No review packet was written, no SQL was parsed or included in any prompt, no SQLite database was opened, no model was loaded, and no model/API call or token use occurred. The failure receipt and log remain private.

## Sole correction

Update the preparer to read the already frozen full-candidate count, exact-alignment count, and per-database candidate histogram from inputs.identity_audit. Add a required preparation run ID and record it in the private success/failure receipt. No sample logic, candidate identities, question text, complete constraint signatures, prompts, models, generation settings, agreement thresholds, or resource gates change.

The original registration and its config remain unchanged. This amendment has a new config at configs/text2sql/p0_bird_train_fk_model_proxy_review_20261107_01_amendment_001.json and uses packet-preparation run ID p0_bird_train_fk_model_proxy_review_20261107_01_packet_prep_002 with output directory packet_002. The superseded packet_001 directory is not reused.

The five stratified Smoke units and all 138 Full units remain exactly as registered. Existing model run IDs remain available because no model run was attempted; they still may run only after the original resource and Smoke gates pass. No new experiment branch or ranking run is authorized by this amendment.

## Verification and next step

The amended plan, config, and updated preparer must be committed and read back from the owned GitHub branch before packet_002 runs. The preparer will verify the source commit, amended config hash, code hash, all frozen input hashes, candidate IDs, question-key hashes, and the eight-database eligible-unit histogram. On success it writes private A/B packets and a 0600 manifest; the existing model runner then performs its packet-only preflight. Model inference remains deferred until physical GPU 1 and GPU 2 meet the frozen free-memory/utilization gates.
