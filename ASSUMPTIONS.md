# Assumptions and design decisions

All times are in seconds, distances in metres, speeds in m/s.

## 1. Design decisions

| # | Question | Decision | Consequence / what to say in the defence |
|---|---|---|---|
| 1 | What is `time` in the plan? | **Departure time**; `time >= max(incident timestamp, time the responder becomes free)` | Matches the assignment's wording: "the simulation time at which the responder starts the assignment" |
| 2 | Where is the responder after finishing a job? | **Default: stays at the incident location.** CLI flag `--after-job on-site\|return`; `return` = drive back to its `start_location` by the A* route, the responder stays occupied until it arrives there; the return trip is not written to `plan.json` | A responder that is `Busy` at t = 0 becomes free at its `start_location` (in both modes). In `return` mode the validator must derive the responder's position and free time from the same rule |
| 3 | Online policy | **Rolling horizon**: decisions only at events (an incident appears / a responder becomes free); only departures that start now are committed, everything else may be re-planned at the next event | Only incidents with `timestamp <= t` are known at time `t` |
| 4 | Deadline that cannot be met | **Assign late** if a capable responder exists; the incident counts as handled with a missed deadline. If no capable responder can reach it at all → "unhandled" | Justify in the report |
| 5 | Blocked rule | **Threshold τ = 0.5**: a road with `P(Blocked) >= τ` is removed from the graph | Sensitivity analysis τ ∈ {0.3, 0.5, 0.7} |
| 6 | Roads without reports | **Prior via P(W)**: `P(S) = Σ_w P(w)·P(S\|w)` = (Open 0.685, Congested 0.18, Blocked 0.135) | Every road without reports has a 13.5% chance of being blocked; since 0.135 < τ it stays usable |
| 7 | Traffic → travel time | **Multiplier** Low 1.0 / Medium 1.2 / High 1.5 (assumption, configurable) | Risk of double counting with Congested ×1.5; acknowledge in the report |
| 8 | HMM over time | **Filtering, static**: the distribution of the state after the last observation of each road | Forecasting ahead is a possible improvement (the stationary distribution 0.354/0.386/0.26 is "worse" than the initial 0.6/0.3/0.1) |
| 9 | Response time | **arrival time − incident timestamp** | Average over handled incidents only (incidents assigned late are handled and included) |
| 10 | % of deadlines met | **Of all incidents** (unhandled = missed), plus a separate figure for Critical | |
| 11 | Optimisation objective | **Lexicographic**: number of missed Critical deadlines → missed High → missed Medium/Low → Σ response time | Easy to explain and consistent with "satisfy constraints, minimise response time" |

**Additionally:** one responder per incident; road states are static during the simulation (reports refer to t = 0); weather is local to the reported road; reports depend on the direction of the road (`from → to`); fractional seconds are allowed and must not be truncated.

## 2. Formulas (for SPEC)

- Road status: `P(S | w, r_1..r_k) ∝ P(S|w) · Π_k P(r_k | S)`; without reports: `P(S) = Σ_w P(w)·P(S|w)`. CPT orientation: the outer key is the true status, the inner key is the reported status.
- Edge weight: `t = d / v · E[mult | not Blocked] · f_traffic`, where `E[mult] = (P(O)·1 + P(C)·1.5) / (P(O) + P(C))` and `f_traffic = Σ_level P(level)·mult(level)`.
- A*: `h(n) = euclidean(n, goal) / 30 m/s`. Admissible and consistent, because for every road the Euclidean distance between its endpoints is ≤ its `distance`, every speed is ≤ 30 m/s, and all multipliers are ≥ 1.

## 3. Trap cases (expected behaviour, written before any code)

1. An incident whose required capability no responder has → "unhandled"; the program does not crash.
2. An incident location that no capable responder can reach (every route contains a removed road) → "unhandled" and reported; no infinite loop.
3. Two Critical incidents with the same deadline and only one capable responder → both handled sequentially by that responder, no overlapping jobs, deterministic order (tie-break by incident id); the second counts as missed if it arrives after its deadline.
4. Busy responder (S1 R4: free after 10 s at N3) → if assigned, `time >= 10` and its path starts at N3.
5. Deadline that cannot be met even if all roads are Open → assigned late, counted as handled with a missed deadline (decision 4).
6. A road with different reports in each direction (S1 N1→N2: P(Blocked) = 0.527 → removed; N2→N1: P(Congested) = 0.993 → kept, ×1.5 expected).
7. Empty lines in CSV files → ignored.
8. Fractional seconds → kept as floats, not truncated to int.
9. An incident appears while a responder is driving → its current job is not interrupted; the new incident goes to another responder or waits until this one is free.
10. All outgoing roads of a node are removed → a responder at that node cannot be dispatched; incidents it could serve go to other responders or become "unhandled"; no crash.
