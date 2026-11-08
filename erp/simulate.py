"""Event-driven rolling-horizon simulation (SPEC §5.11, [D 3]).

Decisions are taken only at events (an incident becomes known / a responder becomes free).
Only departures that start now are committed; everything else is re-planned at the next event.
A component never sees an incident whose timestamp is later than the current time [C].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from erp.allocation import build_problem
from erp.config import Config
from erp.model import (
    EPS, Assignment, Incident, Planner, ResponderState, Scenario, natural_key, order_key,
)
from erp.roadnet import RoadNetwork
from erp.routing import RouteCache


@dataclass(frozen=True)
class SimulationResult:
    assignments: tuple[Assignment, ...]
    unhandled: Mapping[str, str]          # incident id -> reason ("no capable responder" | "unreachable")
    event_log: tuple[str, ...]
    planner_calls: int
    csp_nodes_expanded: int
    csp_all_optimal: bool


def _check_mapping(mapping: Mapping[str, str], pending: Mapping[str, Incident],
                   s: Scenario) -> None:
    for iid, rid in mapping.items():
        if iid not in pending:
            raise ValueError(f"planner assigned unknown or non-pending incident {iid}")
        if rid not in s.responders:
            raise ValueError(f"planner assigned unknown responder {rid}")
        if pending[iid].required_capability not in s.responders[rid].capabilities:
            raise ValueError(f"planner assigned {rid} to {iid} without the required capability")


def simulate(s: Scenario, net: RoadNetwork, cfg: Config,
             planner: Planner, router: RouteCache) -> SimulationResult:
    state: dict[str, ResponderState] = {
        r.id: ResponderState(r.id, r.start_location, r.free_at_start)
        for r in sorted(s.responders.values(), key=lambda r: natural_key(r.id))}
    assigned: dict[str, str] = {}
    assignments: list[Assignment] = []
    log: list[str] = []
    planner_calls = 0
    t = 0.0

    while True:
        known = [i for i in s.incidents if i.timestamp <= t + EPS]          # never later ones [C]
        pending = {i.id: i for i in known if i.id not in assigned}
        free = [rid for rid in state if state[rid].free_at <= t + EPS]
        repeat = False
        if pending and free:
            p = build_problem(t, list(pending.values()), state, s, router, cfg)
            planner_calls += 1
            mapping = dict(planner(p))
            for msg in getattr(planner, "messages", ()):
                log.append(msg)
            if hasattr(planner, "messages"):
                planner.messages.clear()                                    # type: ignore[attr-defined]
            _check_mapping(mapping, pending, s)
            for rid in free:                                                # natural order
                queue = sorted((pending[i] for i, r in mapping.items() if r == rid), key=order_key)
                if not queue:
                    continue
                job = queue[0]
                st = state[rid]
                route = router.route(st.position, job.location)
                if route is None:
                    log.append(f"t={t:g}: WARNING planner chose {rid} for {job.id}, but "
                               f"{job.location} is unreachable from {st.position}; not dispatched")
                    continue
                arrival = t + route.cost
                finish = arrival + job.time_required
                if cfg.after_job == "return":
                    home = s.responders[rid].start_location
                    back = router.route(job.location, home)
                    if back is None:                                        # OQ-7
                        log.append(f"t={t:g}: WARNING {rid} has no route back from {job.location} "
                                   f"to {home}; stays at {job.location}")
                        state[rid] = ResponderState(rid, job.location, finish)
                    else:
                        state[rid] = ResponderState(rid, home, finish + back.cost)
                else:
                    state[rid] = ResponderState(rid, job.location, finish)
                assignments.append(Assignment(rid, job.id, route.path, t))
                assigned[job.id] = rid
                del pending[job.id]
                log.append(f"t={t:g}: dispatch {rid} -> {job.id} via {'-'.join(route.path)}, "
                           f"arrival {arrival:g}, free at {state[rid].free_at:g} "
                           f"at {state[rid].position}")
                if state[rid].free_at <= t + EPS:
                    repeat = True                                           # zero-length job
        if repeat and pending:
            continue                                                        # same t again
        future = [i.timestamp for i in s.incidents if i.timestamp > t + EPS]
        future += [st.free_at for st in state.values() if st.free_at > t + EPS]
        if not future:
            break
        t = min(future)

    unhandled: dict[str, str] = {}
    for inc in sorted((i for i in s.incidents if i.id not in assigned), key=lambda i: natural_key(i.id)):
        capable = any(inc.required_capability in r.capabilities for r in s.responders.values())
        unhandled[inc.id] = "unreachable" if capable else "no capable responder"   # OQ-6, [T 1], [T 2]
        log.append(f"end: {inc.id} unhandled ({unhandled[inc.id]})")

    return SimulationResult(
        assignments=tuple(assignments), unhandled=unhandled, event_log=tuple(log),
        planner_calls=planner_calls,
        csp_nodes_expanded=int(getattr(planner, "nodes_expanded", 0)),
        csp_all_optimal=bool(getattr(planner, "all_optimal", True)))
