<task>
Write SPEC.md for an emergency-response decision-support system (Python 3.11+,
run.py -> plan.json + statistics.txt), precise enough that a coding agent can
build the infrastructure and I can implement four AI kernels myself from it.
Do not write code yet.
</task>
<context>
AI practicum; graded mainly on whether I can explain and defend the system orally.
I will personally implement: Bayesian road-status inference, HMM forward
filtering, A* search, and CSP allocation (backtracking + MRV + forward checking +
branch-and-bound). Everything else (I/O, event simulation, greedy baseline,
validator, statistics) will be generated. My design decisions are fixed in
ASSUMPTIONS.md; follow them exactly.
</context>
<sources>
Only these files in this repository: Assignment1.pdf, Scenarios/README.md,
Scenarios/Scenario1-3/*, ASSUMPTIONS.md, CLAUDE.md. If something is not stated
there, say so; do not invent rules. Where ASSUMPTIONS.md is silent or
contradicts the assignment, list it as an open question instead of deciding.
</sources>
<done_when>
1) every module has a purpose, function signatures and data structures;
2) every formula (posterior, prior via P(W), forward step, edge weight, Blocked
   rule, heuristic, lexicographic cost, statistics) is written out with units;
3) a numeric test list incl. S1 N1->N2 posterior and S2 H2->N8 filtering, plus
   my 10 trap cases from ASSUMPTIONS.md with expected behaviour;
4) a full list of validator checks with error codes;
5) open questions are listed separately.
</done_when>
<output_format>
Write SPEC.md to the repository root (English, one markdown document). Do not
commit yet. In your reply: open questions first, then a short summary of SPEC.md.
</output_format>