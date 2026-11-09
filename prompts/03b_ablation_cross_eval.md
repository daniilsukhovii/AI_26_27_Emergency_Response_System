<task>
Extend experiments/sensitivity.py so that every plan is also judged by the
baseline model, and regenerate outputs/sensitivity.md. Make the changes; do not
only describe them.
</task>
<context>
Each run currently judges its plan with the network it was planned on. For the
ablation rows this is misleading: S1 --no-bayes reports 100% deadlines met, but
judged by the baseline network (Bayes + HMM) the same plan has 4 x E304 (removed
roads) and 1 x E404. The report needs both views.
</context>
<constraints>
Do not change the planner, the validator or any "# STUDENT:" function. For each
run, keep the existing columns as "self-evaluated" and add "baseline-evaluated"
columns from validate_plan(scenario, baseline_network, cfg_eval, plan), where
baseline_network uses the default tau, multipliers, use_bayes and use_hmm, and
cfg_eval keeps the run's after_job (a return-mode plan must not be judged as
on-site). Columns: error codes with counts, % met, % Critical met, avg response
(print "n/a (infeasible)" if a path uses a removed road).
Add one sentence describing this to SPEC.md §5.16.
Add tests: the baseline row is identical in both column groups; S1 --no-bayes
has E304 > 0 when baseline-evaluated.
</constraints>
<done_when>
1) pytest passes (report counts);
2) outputs/sensitivity.md regenerated for S1-S3;
3) one commit.
</done_when>
<output_format>
Conclusion first; files changed; pytest summary; the regenerated table verbatim.
</output_format>