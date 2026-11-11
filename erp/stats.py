"""Statistics (SPEC §5.13, formulas §6.8, [D 9], [D 10]).

Computed from the validator timeline (never from simulator internals), except the reasons of
unhandled incidents, which come from ``SimulationResult.unhandled`` (plan.json does not record
why an incident was not dispatched):
response time = arrival - incident timestamp (s); % deadlines met is over ALL incidents
(unhandled = missed). Dependency rule (§3.2): no import of simulate / csp / greedy / search.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from erp.model import EPS, Scenario, TimelineEntry, natural_key


@dataclass(frozen=True)
class IncidentStat:
    id: str
    priority: str
    responder: str | None
    depart: float | None          # s
    arrive: float | None          # s
    deadline: float               # s
    response: float | None        # s, arrive - timestamp
    status: str                   # "met" | "late" | "unhandled"
    reason: str | None            # unhandled reason


@dataclass(frozen=True)
class Statistics:
    n_total: int
    n_handled: int
    n_unhandled: int
    n_late: int
    responders_used: int
    avg_response_time: float | None          # s
    pct_deadlines_met: float | None          # %
    pct_critical_met: float | None           # %
    missed_by_class: tuple[int, int, int]    # Critical, High, Medium/Low
    per_incident: tuple[IncidentStat, ...]   # natural incident id order
    n_met: int = 0
    n_critical: int = 0
    n_critical_met: int = 0


def compute_statistics(s: Scenario, timeline: Mapping[str, list[TimelineEntry]],
                       unhandled: Mapping[str, str]) -> Statistics:
    entries: dict[str, TimelineEntry] = {}
    for lst in timeline.values():
        for e in lst:
            iid = e.assignment.incident_id
            if iid in entries:
                raise ValueError(f"incident {iid} appears twice in the timeline")
            entries[iid] = e
    responders_used = len({e.assignment.responder_id for e in entries.values()})

    per: list[IncidentStat] = []
    met = late = crit_total = crit_met = 0
    missed = {"Critical": 0, "High": 0, "Medium/Low": 0}
    responses: list[float] = []
    for inc in sorted(s.incidents, key=lambda i: natural_key(i.id)):
        e = entries.get(inc.id)
        if e is None:
            ok = False
            per.append(IncidentStat(inc.id, inc.priority, None, None, None, inc.deadline, None,
                                    "unhandled", unhandled.get(inc.id)))
        else:
            ok = e.arrival <= inc.deadline + EPS
            response = e.arrival - inc.timestamp                 # [D 9]
            responses.append(response)
            per.append(IncidentStat(inc.id, inc.priority, e.assignment.responder_id, e.departure,
                                    e.arrival, inc.deadline, response, "met" if ok else "late", None))
            if not ok:
                late += 1
        if inc.priority == "Critical":
            crit_total += 1
            crit_met += int(ok)
        if ok:
            met += 1
        else:
            cls = inc.priority if inc.priority in ("Critical", "High") else "Medium/Low"
            missed[cls] += 1

    n = len(s.incidents)
    h = len(entries)
    return Statistics(
        n_total=n, n_handled=h, n_unhandled=n - h, n_late=late,
        responders_used=responders_used,
        avg_response_time=(sum(responses) / h) if h else None,
        pct_deadlines_met=(100.0 * met / n) if n else None,          # [D 10]
        pct_critical_met=(100.0 * crit_met / crit_total) if crit_total else None,
        missed_by_class=(missed["Critical"], missed["High"], missed["Medium/Low"]),
        per_incident=tuple(per), n_met=met, n_critical=crit_total, n_critical_met=crit_met)
