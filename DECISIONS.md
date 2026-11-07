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