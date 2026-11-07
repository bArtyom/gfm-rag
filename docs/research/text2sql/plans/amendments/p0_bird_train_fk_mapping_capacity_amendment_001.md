# BIRD train FK mapping capacity Amendment 001

Experiment: `p0_bird_train_fk_mapping_capacity_20261107_01`
Status: preregistered before any BIRD train question/SQL read.

## Reason

The original plan could be read as requiring the schema JSON to identify whole FK constraints. BIRD's schema representation exposes `foreign_keys` as column-index pairs but does not necessarily provide a constraint ID. The capacity stage must not treat two members of one composite FK as two independently reviewable mappings.

## Frozen clarification

1. Database disjointness is checked first using only `db_id` values in `train_tables.json` and `dev_tables.json`. A nonzero overlap stops the run before opening `train.json`.
2. If disjoint, the capacity scan counts distinct declared FK column-pair rows per resolved physical table pair. This is explicitly an upper-bound capacity proxy, not a count of independently verified constraints or semantic alternatives.
3. A passed capacity gate only permits a new registration for FK constraint-identity verification. No model review or G-reasoner/Dense ranking may use the metadata-only candidate pool until that separate verification is complete.

No dataset, question, parser rule, sample size gate, database-coverage gate, resource budget, or stopping condition changes. No sample SQL/label or database content has been read, and no run has started.
