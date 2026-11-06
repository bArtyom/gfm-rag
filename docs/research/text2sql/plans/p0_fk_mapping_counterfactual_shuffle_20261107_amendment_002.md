# Amendment 002: pin the local source artifacts

**Experiment:** `p0_fk_mapping_counterfactual_shuffle_20261107_01`
**Timing:** before parsing question/SQL records or opening any SQLite connection
**Status:** preregistered source-integrity receipt

The byte-hash capture completed after Amendment 001 and before any SQL parsing or SQLite connection. The BIRD `dev.json`, `dev_tables.json`, and frozen source manifest matched the hashes already published in the preceding experiment report. The previous Full_002 private metrics file and all four SQLite snapshots are now pinned by SHA-256 and byte length in the accompanying config. The exact DB paths, question text, SQL, row values, and candidate IDs remain private.

This amendment adds no sample, does not inspect the private metric contents, and does not change the 55 fixed candidate comparisons, eligibility rules, seeds, metrics, thresholds, resource budget, or stop rule. The runner must verify these hashes before reading the pinned metrics or connecting to SQLite, then verify the SQLite files again after Full.

## Pinned anonymous SQLite snapshots

| Anonymous database | Bytes | SHA-256 |
|---|---:|---|
| DB-A | 481,419,264 | `92101be6d2a9f6adceea59d38f6d1c556087f9eea1432432a21268cb1348036d` |
| DB-B | 597,754,880 | `e4d361dbeec6591a4b315877c0c481da05c8ff5a3d389b34d6e17b6f15bee4e0` |
| DB-C | 237,568 | `75e94a2c3236ee3bb2c01fb97a1c4b4c1c269bcefd4eab1d04be323d2d0825b1` |
| DB-D | 2,678,784 | `f5fa7f21af1ad878ff8fef1b0582b8cb2d7ed63dbac65ff16d2ba05667650c5b` |
