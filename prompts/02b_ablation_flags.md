<task>
Implement the ablation switches for the Bayesian and HMM components that
SPEC.md already specifies (§5.1 use_bayes / use_hmm, §5.15 --no-bayes /
--no-hmm, §5.16 variations, §8.3 T-W8), and test them. Make the changes; do not
only describe them.
</task>
<context>
AI practicum. The report needs an ablation table (with/without Bayes,
with/without HMM) to show that both components really influence the decisions.
The decision is recorded in DECISIONS.md D06; SPEC.md was updated by me and is
binding. The validator is still a stub; it will be written later in a separate
session, so do not touch erp/validate.py.
</context>
<sources>
SPEC.md (binding), DECISIONS.md D06, CLAUDE.md, the existing code in erp/,
run.py, experiments/sensitivity.py and tests/.
</sources>
<constraints>
Follow CLAUDE.md: never write or change the body of a "# STUDENT:" function.
Do not edit SPEC.md; if it is unclear or contradicts this task, report it.
Implement the switches in the infrastructure layer only (Config and CLI
parsing, the infra wrappers that build road beliefs and traffic factors,
output, experiments/sensitivity.py):
  - use_bayes=False: every road has status Open with P = 1, e_mult = 1, no road
    is removed, and the Bayesian kernels are not called;
  - use_hmm=False: f_traffic = 1 for every road, observed or not;
    forward_filter is not called and unobserved_traffic has no effect;
  - both can be combined.
The "Configuration:" line of statistics.txt (Config.describe()) must show
use_bayes and use_hmm. With default values every existing output must stay
byte-identical.
Do not modify existing tests; only add new ones. T-W8 must check, besides the
SPEC row, these values for S1 road N2→N1 (abs 1e-3 s): baseline 78.5625 s;
--no-bayes 52.4785 s (d/v · f_traffic); --no-hmm 77.3471 s (d/v · e_mult);
both 51.6667 s (d/v); and that T-W6 (w >= distance/speed and w >= euclid/v_max)
holds for every usable road of S1-S3 in all four modes. Also add tests for CLI
parsing of both flags and for the Configuration line.
</constraints>
<done_when>
1) pytest: every test that passed before still passes, the new tests pass, and
   the only failures are tests that need the validator, failing with
   NotImplementedError("validator: separate session") (report all counts);
2) README lists --no-bayes and --no-hmm;
3) one commit for the implementation and its tests.
</done_when>
<output_format>
Conclusion first; files changed; pytest summary (passed / NotImplementedError /
other failures); the four N2→N1 weights as computed by the code; anything in
SPEC.md that conflicts with this task.
</output_format>