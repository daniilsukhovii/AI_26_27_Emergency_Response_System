<task>
Fix the accepted findings of the audit in 04_audit_answer.md (repository root)
exactly as decided below, then regenerate the results. Make the changes; do not
only describe them.
</task>
<context>
AI practicum; graded mainly on whether I can explain and defend the system. This
is a fresh session: read 04_audit_answer.md, CLAUDE.md, SPEC.md and
DECISIONS.md first. Functions marked "# STUDENT:" are mine; I have already fixed
AUD-7 and DOC-a myself and corrected D08. tests/test_audit.py contains one
check per code finding. Before changing anything, run python -m pytest: the
expected state is exactly 7 failures, all in tests/test_audit.py (AUD-7
passes). If the state differs, stop and report it.
</context>
<decisions>
AUD-1  accepted. In experiments/sensitivity.py a plan with any error-severity
       issue under the baseline model (not only E304) is infeasible: print its
       error codes with counts and show avg response, % met and % Critical met
       as "n/a (infeasible)". Update SPEC.md §5.16 accordingly (this also fixes
       DOC-e).
AUD-2  rejected for the code: the CSP keeps ordering values by partial schedule
       cost (it enables the B&B break). Update the "value order" sentence in
       SPEC.md §5.9 to describe this, ties by natural responder id. Delete
       test_AUD2. Do not touch csp.py.
AUD-3  accepted: an incident is known at time t iff timestamp <= t (exact, no
       EPS) in simulate.py and allocation.py; E402 in validate.py uses the exact
       comparison too. EPS stays for free_at and deadline comparisons. Update
       SPEC.md §0 and §5.11.
AUD-4  accepted: the kernels already raise ValueError on zero-probability
       evidence. In the infrastructure wrappers that call them, convert that
       ValueError into InputError with new code I013 (add it to SPEC.md §1.3),
       so run.py exits with status 2. Do not change the kernels.
AUD-5  accepted: regression test that the production path (run.py ->
       RouteCache -> astar) uses the Euclidean heuristic.
AUD-6  accepted: T-C3 fixture where a higher priority has a larger domain.
AUD-7  fixed by me; keep the test.
AUD-8  accepted: replace the bare assert with an explicit exception.
DOC-b, DOC-c, DOC-d  accepted: correct the texts named in 04_audit_answer.md.
TST-a  accepted: add erp.routing and erp.allocation to the forbidden imports
       of validate.py and stats.py.
TST-b  accepted: the validator derives a responder's initial free time from
       the raw fields (availability, time_until_available), not from
       Responder.free_at_start.
TST-c  accepted: assert equal lengths instead of relying on zip().
TST-d  accepted: replace the tautological assertions with hand-computed
       expected values.
Open question 1 accepted: with --hmm-init pi_is_t0, roads without traffic
       observations use pi·A (the distribution of X_1), not pi. Infrastructure
       code only.
</decisions>
<constraints>
Follow CLAUDE.md: never write or change the body of a "# STUDENT:" function. If
a decision above would require that, stop and report it. Do not weaken or
delete any test except test_AUD2. Move every remaining check from
tests/test_audit.py into the matching test file, then delete
tests/test_audit.py. Do not edit 04_audit_answer.md. Change nothing that is not
listed above; report anything else you notice instead of fixing it.
</constraints>
<done_when>
1) python -m pytest passes (report counts);
2) outputs regenerated: run.py for Scenario1-3 (default settings) and
   experiments/sensitivity.py;
3) results/ (tracked by git) contains sensitivity.md and the three default
   statistics.txt files, and README says how to regenerate them;
4) one commit per finding or per file group, plus one commit for results/.
</done_when>
<output_format>
Conclusion first; per finding: what changed, file:line, test; pytest summary;
every change in the S1-S3 statistics or in the sensitivity table compared with
before; anything you noticed but did not change.
</output_format>