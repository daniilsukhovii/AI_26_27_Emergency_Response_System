"""Greedy planners (SPEC §5.10, OQ-8)."""
from __future__ import annotations

from erp.allocation import simulate_schedule
from erp.config import Config
from erp.model import EPS, AllocationProblem, Planner, natural_key


def greedy_assignment(p: AllocationProblem) -> dict[str, str]:
    """Incidents in order_key order; each takes the capable responder (free now or busy) with the
    earliest arrival given the responders' already-built queues (simulate_schedule); ties by
    natural responder id. Used as CSP incumbent.

    An incident is omitted if its domain is empty or every candidate makes the chained
    schedule infeasible (the result is then not a complete assignment)."""
    mapping: dict[str, str] = {}
    for inc in p.incidents:                      # already sorted by order_key
        best: tuple[float, tuple[str, int], str] | None = None
        for rid in p.domains.get(inc.id, ()):
            cand = dict(mapping)
            cand[inc.id] = rid
            sched = simulate_schedule(p, cand)
            if sched is None:
                continue
            key = (sched[inc.id][1], natural_key(rid), rid)
            if best is None or key < best:
                best = key
        if best is not None:
            mapping[inc.id] = best[2]
    return mapping


def greedy_planner(cfg: Config) -> Planner:
    """Baseline for comparison: incidents in order_key order; each takes the capable responder
    that is free NOW with the earliest arrival; a responder takes at most one incident per event;
    no reservations of busy responders."""

    def plan(p: AllocationProblem) -> dict[str, str]:
        free = {r.id: r for r in p.responders if r.free_at <= p.now + EPS}
        used: set[str] = set()
        mapping: dict[str, str] = {}
        for inc in p.incidents:
            best: tuple[float, tuple[str, int], str] | None = None
            for rid in p.domains.get(inc.id, ()):
                if rid not in free or rid in used:
                    continue
                arr = p.now + p.travel(free[rid].position, inc.location)
                key = (arr, natural_key(rid), rid)
                if best is None or key < best:
                    best = key
            if best is not None:
                mapping[inc.id] = best[2]
                used.add(best[2])
        return mapping

    return plan
