## D01 — Under-specified "return to base" mode (decision #2)
Phase: pre-SPEC review of ASSUMPTIONS.md

Context: my own extension of the plan: CLI flag to choose whether a responder
stays on site or returns after a job.

LLM review found: the mode was not defined — return destination, whether the
responder is occupied while driving back, and how the validator reconstructs the
responder's position (the return trip is not an assignment in plan.json).

LLM proposed: --after-job on-site|return; return = A* route to start_location;
occupied until arrival; return trip not written to plan.json; validator derives
position and free time with the same rule.

Decision: accepted  — allows you to answer the relevant question during the project defense by running the CLI; the definition is precise enough for testing.

Cost/risk: extra logic in simulate.py and validate.py; first candidate to move
to "future work" if time runs short.

## D02 — Machine translation silently changed the meaning of ASSUMPTIONS.md
Phase: pre-SPEC review of ASSUMPTIONS.md

Tool: DeepL Translator (deepl.com), Ukrainian -> English; text was pasted in
separate chunks, so the translator had no context of the whole document.

LLM review found (semantic errors, would change system behaviour):
  - decision #6: "road without reports" -> "unpaved road";
  - trap 1: "no capable responder" -> "no available responder" (a temporarily
    busy responder would make an incident "unhandled" instead of waiting);
  - trap 5: "missed deadline" -> "skipped" (contradicts decision #4: assign late);
  - decision #1: "responder becomes free" -> "transponder release";
  - decision #11: "missed Critical deadlines" -> "omitted Critical". 
  - Wording errors (meaning unclear, not wrong): garbled consequence of #1,
  "processed data" (#9), "dispatches are recorded now" (#3), "for all paths"
  instead of "for every road", "route" instead of "road" (trap 6), "=<". 
  - Also found: traps 3 and 10 were not testable as written (my original
  phrasing, not a translation error).

How found: review of the file against the Ukrainian plan before writing SPEC.md;
  the errors were not visible when reading the English text on its own.

Change: replaced ASSUMPTIONS.md with the corrected version; I checked every line
  against the original Ukrainian decisions.

Decision: accepted

Lesson: ASSUMPTIONS.md is executed "exactly" by the coding agent, so a
  plausible-sounding mistranslation becomes a wrong requirement. From now on:
  documents that drive generation are written directly in English or
  translated as a whole and checked against a glossary of key terms (capable vs
  available, missed vs unhandled, road vs route, departure vs arrival).

## D03 — Interface code in SPEC.md is a contract, not verified code
Phase: review of SPEC.md (Prompt 1 output), before Prompt 2

Observation: SPEC.md contains Python-like blocks (dataclasses, function
  signatures, docstrings, pseudocode of the simulation loop). I first suspected
  the agent had ignored "Do not write code yet".

Analysis: done_when 1 of Prompt 1 explicitly asked for function signatures and
  data structures, so the blocks are the requested interface contract. No
  "# STUDENT:" function has a body in SPEC.md; pseudocode exists only for
  infrastructure (simulate loop, §5.11).

LLM review found: the blocks were never executed and are not valid as written.
  Example: Config (§5.1) declares a dict default in a frozen dataclass, which
  raises "ValueError: mutable default <class 'dict'> ... use default_factory"
  when run.

Change: none in SPEC.md; the snippets are treated as a contract for names,
  types and units.

Decision: accepted — the Python-like contract is acceptable.

Lesson: generated specification code looks authoritative but is unverified;
  only code that has been run counts as checked.

## D04 — Inconsistent statistics.txt example in SPEC.md §2.2
Phase: review of SPEC.md (Prompt 1 output), before Prompt 2

LLM generated: the header block of the example was copied verbatim from the
  assignment (5 handled, 2 responders, 65.7 s, Deadlines met 100.0%), while the
  "Details" block describes a different, invented run (7 incidents, 4 met ->
  57.1%, Critical 50.0%).

Problem: by [D 10] the header line "Deadlines met" and "Deadlines met (all
  incidents)" are the same value, so the example contradicted my own decision.
  The agent could implement the header as a separate metric, or fit test T-ST5
  to the copied numbers. A second inconsistency was found during the follow-up
  check: "1 late" but "W401 x2" (W401 = missed deadline of a handled incident;
  the two unhandled incidents produce W501 and W502, not W401).

How found: my own review of SPEC.md (header 100.0% vs details 57.1%); the
  W401 count was found by the LLM when checking my finding.

Change: replaced the example in §2.2 with one consistent run (header 57.1%,
  no value copied from the assignment example), added an explicit line that the
  header value equals "Deadlines met (all incidents)", and corrected the
  validation line to "3 warnings (W401 x1, W501 x1, W502 x1)".

Decision: modified — saved with corrections.

Lesson: illustrative examples in a spec act as requirements for the coding
  agent; every number in an example must follow the spec's own formulas.

## D05 — Traffic factor for roads without observations (SPEC OQ-2)
Phase: review of SPEC.md (Prompt 1 output), before Prompt 2

LLM generated: SPEC flagged that ASSUMPTIONS.md [D 8] covers only roads with
  traffic observations, offered three options (initial / neutral /
  stationary) and proposed `initial` as default.

Why it matters: observations exist on 3 of 28 usable roads in S2 and 10 of 58
  in S3, so this choice sets the traffic factor of most edges there (S1 is
  unaffected: every road is observed).

Options: initial = Σ π(L)·mult(L) (S1/S3 1.110, S2 1.145), consistent with
  [D 6] (no evidence -> prior); neutral = 1.0 (ignore traffic where unknown);
  stationary = long-run distribution (S1/S3 1.2071, S2 1.2288; more pessimistic).

LLM review suggested: evaluate `neutral` in the sensitivity analysis.

Change: accepted `initial` as default; SPEC §5.16 changed from a full grid to
  one-factor-at-a-time variations from a baseline, with unobserved_traffic ∈
  {neutral, stationary} added; new test T-SIM-7 (S1 must be unchanged).

Decision: accepted — saved with improvements, due to an optimal choice and the addition of a new test coating.

Report: limitation + sensitivity row; if results in S2/S3 change noticeably,
  the conclusions depend on an unobserved quantity, and the report must say so.

## D06 — Prompt 2 rewritten to match SPEC.md; ablation flags deferred
Phase: before Prompt 2

Problem: Prompt 2 was drafted in the plan before SPEC.md existed. It named
  kernel functions that SPEC defines differently (e.g. hmm.forward vs
  forward_filter, csp.solve vs three functions), cited wrong SPEC sections
  (§3 for signatures, §6 for tests), listed CLI flags that conflict with SPEC
  §5.15 (--allocator vs --planner, --seed), and said "do not write the
  validator" although SPEC derives statistics from the validator timeline and
  uses the validator's Dijkstra in tests.

How found: LLM review of Prompt 2 against SPEC.md.

LLM proposed: (1) rewrite Prompt 2 to reference SPEC.md instead of repeating
  its lists; (2) add use_bayes/use_hmm (--no-bayes, --no-hmm) and test T-W8 to
  SPEC.md, because the ablation in the experiments needs them and the existing
  flags cannot express "no Bayes".

Change: (1) applied: Prompt 2 now refers to SPEC.md, SPEC wins on conflicts,
  reference implementations for tests go to tests/reference.py, validate.py is
  created as a stub for a later independent session.
  (2) deferred: SPEC.md was not changed before Prompt 2, so the scaffold has no
  --no-bayes/--no-hmm (confirmed in the repository after Prompt 2). The SPEC
  change and its implementation are scheduled right before Prompt 3 (implemented in commit c9b6d0ac). 

Decision: (1) accepted; (2) accepted, deferred — the deviation from the original scenario in Prompt 2 was already a significant change, so it was decided to break it down into several steps.

Lesson: a prompt drafted before the spec must be re-checked against it; a prompt
  should reference the spec rather than restate it.

## D07 — A* ran without its heuristic in production
Phase: review after the student kernels (before Prompt 3)

Problem: astar treats h=None as h=0; RouteCache (production path) calls
  astar(net, u, v) without h, so every route was computed by uniform-cost
  search. euclidean_heuristic was only called by tests. All tests passed,
  because A* with h=0 is still optimal (T-A7 compares costs only).

How found: LLM code review: euclidean_heuristic has no caller in erp/.
  Measured on S3 all pairs: 8450 node expansions with h=0 vs 7795 with h.

Change: astar defaults to euclidean_heuristic(net, goal) when h is None

Decision: accepted — a “lambda _: 0.0” from the IDE's autocomplete passed the tests, which is, of course, an unintentional mistake by the student.

## D08 — CSP kernel deviations from SPEC §5.9
Phase: review after the student kernels (before Prompt 3)

Found: (1) select_unassigned_variable orders by priority first, domain size
  second, i.e. not MRV as specified (T-C3 passed only because its fixture has
  equal priorities); (2) values are ordered by partial schedule cost instead of
  domain order; (3) the incumbent was accepted if any (not all) of its values
  were in the domains; (4) docstrings/comments contradicted the code (two
  docstrings in select_unassigned_variable, "natural order" vs string order;
  "=" instead of "∝" in bayes.py).

How found: LLM code review against SPEC §5.9 and the docstrings.

Change: (1) MRV restored: (domain size, order_key);
  (2) kept: values ordered by partial schedule cost.
Cheaper values first find a good incumbent earlier, so B&B prunes more.
The sorted order also allows a break instead of continue, which by itself changes nothing.
  (3) fixed; (4) texts corrected.

Decision: accepted

## D09 — Ablation runs evaluated themselves with their own simplified model
Phase: review after Prompt 3 (validator)

Problem: experiments judged every plan with the network it was planned on.
  Plans made without Bayes looked best (S1 --no-bayes: 100% deadlines met) —
  because that network assumes every road is Open.

How found: LLM review: re-validated the ablation plans with the baseline network
  (Bayes + HMM): S1/S3 --no-bayes 4 x E304 (routes over roads with
  P(Blocked) >= tau) plus E404; S2/S3 --no-hmm 2-5 x E404 (travel times
  underestimated, jobs overlap). Baseline plans: 0 errors in both views. The
  agent's own limitation list pointed at the cause: the validator cannot tell
  which network a plan was made with.

Change: sensitivity.py reports self-evaluated and baseline-evaluated columns
  (commit dc223aef); SPEC §5.16 updated.

Decision: accepted.

Report: ablation shows that both components change the decisions; the
  baseline-evaluated view is still an expectation, not ground truth (L1); Monte
  Carlo evaluation (plan D1) is the next step.

## D10 — Independent audit session (Prompt 4) and fixes (Prompt 5)

Phase: after experiments, before the report

Found: 8 code/test defects (each with a failing test) + 9 doc/test-quality
  defects (04_audit_answer.md). Most important: AUD-1 — the D09 fix was
  incomplete: plans with E404 under the baseline model still got baseline
  averages, so ablated plans could look better because their jobs overlapped;
  AUD-2 — D08 claimed a change that git showed was never made; AUD-5/6 — the
  D07 and D08 bugs would still pass the whole suite (no regression tests).

How found: fresh Claude Code session without history (Prompt 4); claims checked
  against git history and by running mutants.

Change: AUD-7 and DOC-a fixed by me, D08 corrected (95f7a1e). Accepted and fixed
  by Prompt 5: AUD-1 (acbe882), AUD-3 (33202b9), AUD-4 (4b32904), AUD-5/6
  (18592ec), AUD-7 test kept (6caced1), AUD-8 (88e19d6), DOC-b..d (c312ae2),
  TST-a (4c3750c), TST-b/c (772465f), TST-d (fda1885), OQ-1 pi·A for
  pi_is_t0 (b66c69f); results/ snapshot (82d7e34). AUD-2 rejected for the code
  (cost-ordered values keep the B&B break); SPEC §5.9 corrected instead
  (b47bd4b). Default S1-S3 statistics unchanged; in the sensitivity table every
  plan that is invalid under the baseline model now shows "n/a (infeasible)".

Decision: accepted, AUD-2 modified — When the cheapest values are tried first, the first complete solution found is more likely to be close to the optimal one.
In this case, `best_cost` becomes small early on, and more branches are pruned from the tree—both in the loop and in `forward_check`, which also uses `best_cost`.
With `domain order`, good solutions may be found later, the bound remains weak for longer, and the search explores more nodes.

Lesson: a fix is only finished when a test would catch the original bug; an
  entry in the decision log is not evidence that the code changed.