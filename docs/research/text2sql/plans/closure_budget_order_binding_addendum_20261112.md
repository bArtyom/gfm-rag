# Posthoc measurement diagnostic; primary protocol unchanged

After the100-question pilot completed and its primary counts were inspected
(whole/late/early preparability85/76/77; gatefailed), read-only review identified
that nested unqualified columns may rebind after inner fields are removed.
Preserve every original result and the stop decision. Do not rescore the primary
metric or restart any method. Add only an evaluation diagnostic: compile the
original SQL on full empty TEXT-schema stubs with SQLite authorizer and record
physical read table/column bindings. Check whether each sealed selection retains
those bindings. Test a synthetic correlated-rebinding counterexample. Report
preparable-but-missing-binding counts, not as a new passed gate or semantic EX.
For supported full cases, construct reference-binding-only FK closure as an
explicit oracle diagnostic of budget feasibility; it uses reference labels and
is not a deployable selector. Missing original binding despite a feasible oracle
suggests a ranking/allocation bottleneck, not a causal proof of why it happens.
No model calls, training, SQL data-result execution or additional candidate run.
