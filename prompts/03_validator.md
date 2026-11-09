<task>
Implement erp/validate.py (SPEC.md §5.12, checks §7) and tests/test_validate.py
(SPEC.md §8.8). The validator is the independent check of the planner. Make the
changes; do not only describe them.
</task>
<context>
AI practicum. This is a fresh session on purpose: the validator must not share
reasoning or code with the planner. All other modules are implemented; the
four kernels (bayes, hmm, search, csp) were written by me. validate.py is
currently a stub with the §5.12 signatures; every test that fails now fails
with NotImplementedError("validator: separate session"). These tests
(integration, trap and output tests) are the acceptance tests of this task and
must pass without being modified.
</context>
<sources>
SPEC.md is binding (§0, §2, §3.2, §6.5-6.8, §7, §8.6-8.8), plus ASSUMPTIONS.md,
CLAUDE.md, Assignment1.pdf, Scenarios/ and tests/.
You may read and import erp/model.py, erp/config.py, erp/io_load.py and
erp/roadnet.py (shared edge model, limitation L2). Use erp/stats.py,
erp/output.py and run.py only as black boxes.
Do not open or import erp/simulate.py, erp/allocation.py, erp/greedy.py,
erp/csp.py, erp/search.py or erp/routing.py.
</sources>
<constraints>
Follow CLAUDE.md. dijkstra_all is your own implementation inside validate.py.
reconstruct_timeline must work on its own, because run.py --no-validate calls
it without validate_plan. Rebuild each responder's timeline only from plan +
scenario + network, as in SPEC.md §7, for both after-job modes.
load_plan_json must not crash on a malformed file: choose how malformed JSON
reaches E101 through validate_plan, and report the choice.
Implement every code of §7.1-7.2. Write one mutation test per code as listed
in §8.8, each asserting the expected code and no unrelated error codes. To get
a valid plan, tests call run.run_scenario with Config(validate=False) as a black
box.
Do not modify existing tests or non-validator modules. If an existing test, or
a plan produced by the planner, looks wrong, do not change the planner or the
test: report the test or plan entry, the check, and why.
</constraints>
<done_when>
1) the full pytest suite passes (report counts);
2) python run.py --scenario Scenarios/ScenarioN --out outputs/ScenarioN writes
   plan.json and statistics.txt for N = 1, 2, 3 with exit code 0, also with
   --no-bayes, with --no-hmm and with --after-job return; any run with exit code
   1 is reported with its exact errors instead of being fixed in the planner;
3) every mutation of §8.8 is reported with its code;
4) a list of what the validator does NOT check (SPEC.md §7.3 plus anything you
   found);
5) one commit for the validator, one for its tests.
</done_when>
<output_format>
Conclusion first; files; pytest summary; statistics.txt of Scenario1-3
(default settings) verbatim; errors and warnings per scenario and mode;
validator limitations; conflicts with SPEC.md or with existing tests.
</output_format>