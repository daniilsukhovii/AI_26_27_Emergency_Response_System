<task>
Implement the infrastructure of the repository described in SPEC.md, stubs for
my kernels, and the tests of SPEC.md §8. Make the changes; do not only describe
them.
</task>
<context>
SPEC.md is binding; the answers in §11 are final. Where this prompt and SPEC.md
disagree, follow SPEC.md and report the conflict. I implement every function
marked "# STUDENT:" in SPEC.md §5 myself (bayes.py, hmm.py, search.py, csp.py):
create each with the exact signature, type hints and the SPEC docstring, body
`raise NotImplementedError`, no pseudocode, no partial implementation.
The validator will be written later in a separate session that does not see the
planner code, to keep it independent: create erp/validate.py only as the §5.12
signatures raising NotImplementedError("validator: separate session").
</context>
<constraints>
Follow CLAUDE.md. Layout as SPEC.md §3.1, data structures §4, signatures §5,
CLI exactly §5.15, formulas §6. Do not edit SPEC.md or ASSUMPTIONS.md; report
needed changes instead.
Reference implementations needed by tests (Dijkstra, brute-force HMM sum over
all hidden sequences, exhaustive CSP enumeration) go to tests/reference.py,
never into erp/, and erp/ must not import them.
Write all tests of SPEC.md §8 except §8.8 (validator, later). In addition: HMM
forward_filter equals the brute-force sum on sequences of length <= 5.
Add requirements.txt (numpy, pytest) and README.md (install, run, test, flags).
</constraints>
<done_when>
1) pytest: every test that does not call a STUDENT function or the validator
   stub passes; every other test fails only with NotImplementedError (report
   both counts);
2) T-ST1..T-ST5 pass on hand-made timelines;
3) Config uses default_factory for mutable defaults;
4) one commit per logical part.
</done_when>
<output_format>
Conclusion first; files created; pytest summary (passed / NotImplementedError /
other failures); conflicts between this prompt and SPEC.md; anything in
SPEC.md you found ambiguous.
</output_format>