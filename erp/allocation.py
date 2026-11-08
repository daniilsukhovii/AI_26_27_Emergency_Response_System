"""Allocation problem, schedule simulation and lexicographic cost (SPEC §5.8, §6.7).

Shared by the CSP, the greedy planners and the tests.
"""
from __future__ import annotations

import math
from typing import Callable, Mapping, Sequence

from erp.config import Config
from erp.model import (
    EPS, AllocationProblem, CostTuple, Incident, NodeId, ResponderSnapshot, ResponderState,
    Scenario, natural_key, order_key,
)
from erp.routing import RouteCache

__all__ = ["ResponderSnapshot", "AllocationProblem", "build_problem", "compute_domains",
           "simulate_schedule", "schedule_cost"]


def compute_domains(now: float, incidents: Sequence[Incident],
                    responders: Sequence[ResponderSnapshot],
                    travel: Callable[[NodeId, NodeId], float]) -> dict[str, tuple[str, ...]]:
    """incident id -> responders that have the required capability [A §3.1] and can reach the
    incident from their ``position``; sorted by (arrival estimate, natural id), where
    arrival estimate = max(now, free_at) + travel(position, location)."""
    domains: dict[str, tuple[str, ...]] = {}
    for inc in incidents:
        cands: list[tuple[float, tuple[str, int], str]] = []
        for r in responders:
            if inc.required_capability not in r.capabilities:
                continue
            t = travel(r.position, inc.location)
            if math.isinf(t):
                continue
            cands.append((max(now, r.free_at) + t, natural_key(r.id), r.id))
        cands.sort()
        domains[inc.id] = tuple(c[2] for c in cands)
    return domains


def build_problem(now: float, pending: Sequence[Incident],
                  states: Mapping[str, ResponderState], s: Scenario,
                  router: RouteCache, cfg: Config) -> AllocationProblem:
    """Snapshot of the current decision point. Every pending incident must already be known
    (timestamp <= now) — enforced by an assertion [C]."""
    for inc in pending:
        assert inc.timestamp <= now + EPS, \
            f"future knowledge: incident {inc.id} has timestamp {inc.timestamp} > now {now}"
    incidents = tuple(sorted(pending, key=order_key))
    responders = tuple(
        ResponderSnapshot(id=rid, capabilities=s.responders[rid].capabilities,
                          start_location=s.responders[rid].start_location,
                          position=states[rid].position, free_at=states[rid].free_at)
        for rid in sorted(states, key=natural_key))
    travel = router.travel_time
    return AllocationProblem(now=now, incidents=incidents, responders=responders,
                             domains=compute_domains(now, incidents, responders, travel),
                             travel=travel, after_job=cfg.after_job)


def simulate_schedule(p: AllocationProblem, assignment: Mapping[str, str]
                      ) -> dict[str, tuple[float, float]] | None:
    """For a (partial) mapping incident->responder returns incident -> (departure, arrival) in s,
    or None if some chained leg is unreachable. Per responder the assigned incidents are served in
    order_key order (OQ-4), §6.7."""
    incidents = {i.id: i for i in p.incidents}
    responders = {r.id: r for r in p.responders}
    queues: dict[str, list[Incident]] = {}
    for iid, rid in assignment.items():
        if iid not in incidents:
            raise KeyError(f"unknown incident {iid}")
        if rid not in responders:
            raise KeyError(f"unknown responder {rid}")
        queues.setdefault(rid, []).append(incidents[iid])
    out: dict[str, tuple[float, float]] = {}
    for rid in sorted(queues, key=natural_key):
        r = responders[rid]
        t = max(p.now, r.free_at)
        pos = r.position
        for inc in sorted(queues[rid], key=order_key):
            dep = max(t, inc.timestamp)
            leg = p.travel(pos, inc.location)
            if math.isinf(leg):
                return None
            arr = dep + leg
            fin = arr + inc.time_required
            if p.after_job == "return":
                back = p.travel(inc.location, r.start_location)
                if math.isinf(back):          # OQ-7: stays at the incident location
                    t, pos = fin, inc.location
                else:
                    t, pos = fin + back, r.start_location
            else:
                t, pos = fin, inc.location
            out[inc.id] = (dep, arr)
    return out


def schedule_cost(p: AllocationProblem, assignment: Mapping[str, str]) -> CostTuple | None:
    """Lexicographic cost §6.7 over the incidents in `assignment`. Monotone: adding an incident
    to a partial assignment never decreases any component ⇒ valid lower bound for B&B."""
    sched = simulate_schedule(p, assignment)
    if sched is None:
        return None
    incidents = {i.id: i for i in p.incidents}
    crit = high = medlow = 0
    total = 0.0
    for iid in sorted(sched, key=natural_key):   # fixed summation order -> deterministic float
        inc = incidents[iid]
        arr = sched[iid][1]
        if arr > inc.deadline + EPS:
            if inc.priority == "Critical":
                crit += 1
            elif inc.priority == "High":
                high += 1
            else:
                medlow += 1
        total += arr - inc.timestamp
    return (crit, high, medlow, total)
