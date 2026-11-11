<task>
Audit this repository against SPEC.md and Assignment1.pdf and find defects.
Do not fix anything.
</task>
<context>
AI practicum, graded mainly on whether I can explain and defend the system, so I
need every place where code, tests, experiments or documentation do not do what
they claim. The functions marked "# STUDENT:" (bayes, hmm, search, csp) were
written by me; everything else was generated. A green test suite is not
evidence: earlier, A* was called without its heuristic in production while all
tests passed (DECISIONS.md D07), and the ablation experiment judged plans with
their own simplified model (D09). DECISIONS.md lists the defects found so far:
check that their fixes are complete, and report them again only if they are not.
</context>
<sources>
The whole repository. SPEC.md and ASSUMPTIONS.md are the requirements;
Assignment1.pdf has priority. Report conflicts between them; do not resolve
them.
</sources>
<focus>
1) deviations of code from SPEC.md: signatures, formulas, tie-breaks, CLI
   (§5.15), statistics (§6.8), validator codes (§7), experiments (§5.16);
2) any way an incident with timestamp > t can influence a decision taken at t;
3) units, float/int rounding, EPS comparisons, formatting of plan.json and
   statistics.txt against Assignment1.pdf §5;
4) every STUDENT function: does the production path (run.py) call it with the
   intended parameters, and does it do what its docstring and SPEC.md say;
5) tests that cannot fail or do not test what their name claims;
6) validator independence: imports and logic shared with the planner (SPEC.md
   §3.2, L2);
7) experiments/sensitivity.py: is every reported number computed the way its
   column header says, including the baseline-evaluated columns;
8) docstrings and comments that contradict the code;
9) reproducibility from a clean clone (README, requirements.txt, outputs/ is
   git-ignored).
</focus>
<done_when>
Every finding has file:line, a one-line defect, a severity (high = wrong plan or
statistic, or a requirement violation; medium = wrong for some input, or
misleading in the defence; low = cosmetic) and a reproducible check: a pytest
function in tests/test_audit.py that fails on the current code, or, for
documentation defects, the exact contradicting lines. Run tests/test_audit.py
and show that it fails. Do not commit.
</done_when>
<output_format>
Findings table, most severe first; then, per focus item, what was checked and
found correct; then open questions.
</output_format>
