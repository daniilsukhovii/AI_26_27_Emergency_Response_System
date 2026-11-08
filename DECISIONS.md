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