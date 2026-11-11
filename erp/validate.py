"""Plan validator (SPEC §5.12, checks §7).

Independent check of the planner: every responder timeline is rebuilt only from
``plan + scenario + network`` (§7, rules of §6.7). The module shares the edge model of
``erp.roadnet`` with the planner (limitation L2) but never imports simulate, csp, greedy,
search, routing or allocation (dependency rule, SPEC §3.2); shortest paths come from the
module's own ``dijkstra_all``.

Malformed plan.json (choice for SPEC §5.12 / E101): ``load_plan_json`` never raises on a
bad file. If the file cannot be read or is not valid JSON it returns a ``PlanLoadError``
value instead of the parsed JSON; ``validate_plan`` turns that value into E101 with the
reason in the message. A file that parses but whose top level is not a list also gives E101.

Units: all times in seconds (s).
"""
from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from erp.config import Config
from erp.model import (
    EPS, Assignment, Incident, Issue, NodeId, Responder, Scenario, TimelineEntry, natural_key,
)
from erp.roadnet import RoadNetwork

PLAN_KEYS: tuple[str, ...] = ("responder_id", "incident_id", "path", "time")
W302_TOL = 1e-6   # s, tolerance of the route-optimality cross-check (§7.2 W302)


@dataclass(frozen=True)
class PlanLoadError:
    """Returned by ``load_plan_json`` instead of raising; reported as E101 by validate_plan."""
    path: str
    reason: str


# ------------------------------------------------------------------ shortest paths

def dijkstra_all(net: RoadNetwork, source: NodeId) -> dict[NodeId, float]:
    """Shortest expected travel time (s) from ``source`` to every node of the network, over
    usable roads only (``net.neighbours``). Unreachable nodes map to ``math.inf``.

    Own implementation, independent of erp/search.py. Raises ValueError for an unknown node.
    """
    if source not in net.nodes:
        raise ValueError(f"unknown node {source!r}")
    dist: dict[NodeId, float] = {n: math.inf for n in net.nodes}
    dist[source] = 0.0
    settled: set[NodeId] = set()
    heap: list[tuple[float, tuple[str, int], NodeId]] = [(0.0, natural_key(source), source)]
    while heap:
        d, _, u = heapq.heappop(heap)
        if u in settled:
            continue
        settled.add(u)
        for v, w in net.neighbours(u):
            if v in settled:
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, natural_key(v), v))
    return dist


class _Distances:
    """Memoised dijkstra_all per source node (one validation run)."""

    def __init__(self, net: RoadNetwork) -> None:
        self._net = net
        self._cache: dict[NodeId, dict[NodeId, float]] = {}

    def __call__(self, u: NodeId, v: NodeId) -> float:
        if u not in self._cache:
            self._cache[u] = dijkstra_all(self._net, u)
        return self._cache[u].get(v, math.inf)


# ------------------------------------------------------------------ timeline reconstruction

def _issue(code: str, entry: int | None, message: str) -> Issue:
    severity = "error" if code.startswith("E") else "warning"
    return Issue(code=code, severity=severity, entry=entry, message=message)


def _initial_state(r: Responder) -> tuple[NodeId, float]:
    """(position, free time in s) at t = 0 [D 2]: start_location, time_until_available if Busy."""
    return r.start_location, r.free_at_start


def _check_path(s: Scenario, net: RoadNetwork, k: int, a: Assignment,
                inc: Incident, pos: NodeId, dist: _Distances) -> tuple[float, list[Issue]]:
    """Path checks E301-E304, W301, W302. Returns (path cost in s, issues)."""
    issues: list[Issue] = []
    path = a.path
    if path[0] != pos:
        issues.append(_issue("E301", k, f"{a.responder_id}: path starts at {path[0]}, but the "
                                        f"responder is at {pos} at departure"))
    if path[-1] != inc.location:
        issues.append(_issue("E302", k, f"path ends at {path[-1]}, but {inc.id} is at {inc.location}"))
    for u, v in zip(path, path[1:]):
        if (u, v) not in s.roads:
            issues.append(_issue("E303", k, f"{u}->{v} is not a road of the graph"))
        elif not net.is_usable(u, v):
            b = net.beliefs[(u, v)].status["Blocked"] if (u, v) in net.beliefs else math.nan
            issues.append(_issue("E304", k, f"{u}->{v} is a removed road (P(Blocked) = {b:.6f} "
                                            f">= tau)"))
    if len(set(path)) < len(path):
        issues.append(_issue("W301", k, "path visits a node more than once"))
    cost = net.path_cost(path)
    if math.isfinite(cost):
        best = dist(path[0], path[-1])
        if cost > best + W302_TOL:
            issues.append(_issue("W302", k, f"path cost {cost:.4f} s > shortest {path[0]}->"
                                            f"{path[-1]} {best:.4f} s"))
    return cost, issues


def reconstruct_timeline(s: Scenario, net: RoadNetwork, cfg: Config,
                         plan: Sequence[Assignment]) -> tuple[dict[str, list[TimelineEntry]], list[Issue]]:
    """Rebuild every responder's timeline from plan + scenario + network only (SPEC §7).

    Per responder r: pos = start_location, free = time_until_available if Busy else 0 [D 2].
    Its entries are processed in order of ``time`` (ties: plan order). For each entry:
    departure = time, arrival = time + net.path_cost(path), finish = arrival + time_required;
    on-site: pos = incident location, free = finish; return: pos = start_location,
    free = finish + dijkstra(incident location -> start_location), or (no route back, OQ-7)
    pos = incident location, free = finish.

    Usable on its own (run.py --no-validate). Entries with an unknown responder / incident /
    node, an empty path or an already-seen incident are reported (E201/E202/E203/E106/E204)
    and left out of the timeline; ``Issue.entry`` is the index in ``plan``.
    Checks E301-E304, E401-E404, W301, W302, W401, W402 are reported here.

    If an entry's path cost is infinite (E303/E304), its arrival is ∞ in the timeline, but the
    responder's free time for the *next* entry is taken as the lower bound
    ``departure + time_required``, so a broken path does not cascade into E404 on later jobs.

    Returns ({responder id: entries in time order} for responders with ≥ 1 entry, issues).
    """
    issues: list[Issue] = []
    incidents = {i.id: i for i in s.incidents}
    dist = _Distances(net)

    seen: set[str] = set()
    per_resp: dict[str, list[tuple[int, Assignment]]] = {}
    for k, a in enumerate(plan):
        bad = False
        if a.responder_id not in s.responders:
            issues.append(_issue("E201", k, f"unknown responder {a.responder_id!r}"))
            bad = True
        if a.incident_id not in incidents:
            issues.append(_issue("E202", k, f"unknown incident {a.incident_id!r}"))
            bad = True
        if len(a.path) == 0:
            issues.append(_issue("E106", k, "path is empty"))
            bad = True
        else:
            unknown = [n for n in a.path if n not in s.nodes]
            if unknown:
                issues.append(_issue("E203", k, f"path node(s) not in the graph: {unknown}"))
                bad = True
        if a.incident_id in seen:
            issues.append(_issue("E204", k, f"{a.incident_id} appears in more than one entry"))
            bad = True
        if a.incident_id in incidents:
            seen.add(a.incident_id)
        if not bad:
            per_resp.setdefault(a.responder_id, []).append((k, a))

    timeline: dict[str, list[TimelineEntry]] = {}
    for rid in sorted(per_resp, key=natural_key):
        r = s.responders[rid]
        entries = sorted(per_resp[rid], key=lambda ka: (ka[1].time, ka[0]))   # stable: plan order
        pos, free = _initial_state(r)
        first = True
        out: list[TimelineEntry] = []
        for k, a in entries:
            inc = incidents[a.incident_id]
            t = float(a.time)
            if inc.required_capability not in r.capabilities:
                issues.append(_issue("E401", k, f"{rid} lacks capability {inc.required_capability!r} "
                                                f"required by {inc.id}"))
            if t < inc.timestamp:                                        # exact, no EPS [C]
                issues.append(_issue("E402", k, f"departure {t:g} s before {inc.id} is known "
                                                f"(timestamp {inc.timestamp:g} s)"))
            if first:
                if not r.available and t < r.time_until_available - EPS:
                    issues.append(_issue("E403", k, f"{rid} is Busy until {r.time_until_available:g} s "
                                                    f"but departs at {t:g} s"))
            elif t < free - EPS:
                issues.append(_issue("E404", k, f"{rid} departs at {t:g} s but is busy with its "
                                                f"previous job until {free:.4f} s"))
            earliest = max(inc.timestamp, free)
            if t > earliest + EPS:
                issues.append(_issue("W402", k, f"{rid} departs at {t:g} s, could depart at "
                                                f"{earliest:.4f} s"))

            cost, path_issues = _check_path(s, net, k, a, inc, pos, dist)
            issues.extend(path_issues)
            arrival = t + cost
            finish = arrival + inc.time_required
            if math.isfinite(arrival) and arrival > inc.deadline + EPS:
                issues.append(_issue("W401", k, f"{inc.id} ({inc.priority}) arrives at {arrival:.4f} s, "
                                                f"deadline {inc.deadline:g} s"))
            next_free = finish if math.isfinite(finish) else t + inc.time_required   # lower bound
            new_pos: NodeId = inc.location
            if cfg.after_job == "return":
                back = dist(inc.location, r.start_location)
                if math.isfinite(back):
                    new_pos, next_free = r.start_location, next_free + back
                # else OQ-7: stays at the incident location, free at finish
            out.append(TimelineEntry(
                assignment=a, start_node=a.path[0], departure=t, arrival=arrival, finish=finish,
                free_at=next_free if math.isfinite(finish) else math.inf,
                position_after=new_pos,
                deadline_met=arrival <= inc.deadline + EPS,
                response_time=arrival - inc.timestamp))
            pos, free, first = new_pos, next_free, False
        timeline[rid] = out
    return timeline, issues


# ------------------------------------------------------------------ raw plan parsing

def _is_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _as_float(x: int | float) -> float:
    """JSON integers may exceed the float range: such a time is treated as +inf (E105)."""
    try:
        return float(x)
    except OverflowError:
        return math.inf if x > 0 else -math.inf


def _parse_entry(k: int, e: object, issues: list[Issue]) -> Assignment | None:
    """Structural checks E102-E106, W101 for one plan entry. None if the entry is rejected."""
    if not isinstance(e, dict):
        issues.append(_issue("E102", k, f"entry is not a JSON object ({type(e).__name__})"))
        return None
    missing = [key for key in PLAN_KEYS if key not in e]
    extra = sorted(str(key) for key in e if key not in PLAN_KEYS)
    if extra:
        issues.append(_issue("W101", k, f"extra key(s) {extra}"))
    if missing:
        issues.append(_issue("E103", k, f"missing key(s) {missing}"))
        return None
    wrong: list[str] = []
    if not isinstance(e["responder_id"], str):
        wrong.append("responder_id is not a string")
    if not isinstance(e["incident_id"], str):
        wrong.append("incident_id is not a string")
    path = e["path"]
    if not isinstance(path, list) or not all(isinstance(n, str) for n in path):
        wrong.append("path is not a list of strings")
    if not _is_number(e["time"]):
        wrong.append(f"time is not a number ({type(e['time']).__name__})")
    if wrong:
        issues.append(_issue("E104", k, "; ".join(wrong)))
        return None
    t = _as_float(e["time"])
    if not math.isfinite(t) or t < 0:
        issues.append(_issue("E105", k, f"time {e['time']!r} is NaN, infinite or negative"))
        return None
    return Assignment(responder_id=e["responder_id"], incident_id=e["incident_id"],
                      path=tuple(path), time=t)


def _final_positions(s: Scenario, timeline: Mapping[str, list[TimelineEntry]]) -> dict[str, NodeId]:
    """Responder position at the end of its timeline (start_location if it has no entry)."""
    out: dict[str, NodeId] = {}
    for rid, r in s.responders.items():
        entries = timeline.get(rid)
        out[rid] = entries[-1].position_after if entries else r.start_location
    return out


def validate_plan(s: Scenario, net: RoadNetwork, cfg: Config,
                  raw_plan: object) -> tuple[list[Assignment], dict[str, list[TimelineEntry]], list[Issue]]:
    """Validate a parsed plan.json (or a PlanLoadError from load_plan_json) against SPEC §7.

    ``net`` must be built with the run's tau / multipliers; ``cfg.after_job`` selects the
    reconstruction mode. Returns (accepted assignments, timeline, issues). Accepted =
    entries that pass the structural and reference checks (E101-E106, E201-E204); only those
    enter the timeline. Issues are sorted by entry index (global issues last).
    """
    if isinstance(raw_plan, PlanLoadError):
        return [], {}, [_issue("E101", None, f"{raw_plan.path}: {raw_plan.reason}")]
    if not isinstance(raw_plan, list):
        return [], {}, [_issue("E101", None, f"top level of plan.json is {type(raw_plan).__name__}, "
                                             f"not a list")]
    issues: list[Issue] = []
    parsed: list[tuple[int, Assignment]] = []
    mentioned: set[str] = set()      # incident ids named by any object entry (even rejected ones)
    for k, e in enumerate(raw_plan):
        if isinstance(e, dict) and isinstance(e.get("incident_id"), str):
            mentioned.add(e["incident_id"])
        a = _parse_entry(k, e, issues)
        if a is not None:
            parsed.append((k, a))

    # E201-E204 and the timeline checks; map the timeline's indices back to plan indices.
    index = [k for k, _ in parsed]
    timeline, tl_issues = reconstruct_timeline(s, net, cfg, [a for _, a in parsed])
    issues.extend(Issue(i.code, i.severity, None if i.entry is None else index[i.entry], i.message)
                  for i in tl_issues)
    accepted_ids = {id(e.assignment) for lst in timeline.values() for e in lst}
    accepted = [a for _, a in parsed if id(a) in accepted_ids]

    # Coverage: E501 / W501 / W502 against the final positions (OQ-6).
    final = _final_positions(s, timeline)
    dist = _Distances(net)
    for inc in s.incidents:
        if inc.id in mentioned:
            continue
        capable = [rid for rid, r in s.responders.items() if inc.required_capability in r.capabilities]
        if not capable:
            issues.append(_issue("W501", None, f"{inc.id} unhandled: no responder has "
                                               f"{inc.required_capability!r}"))
            continue
        reach = [rid for rid in capable if math.isfinite(dist(final[rid], inc.location))]
        if reach:
            issues.append(_issue("E501", None, f"{inc.id} is not in the plan, but capable responder(s) "
                                               f"{reach} can reach {inc.location}"))
        else:
            issues.append(_issue("W502", None, f"{inc.id} unhandled: capable responder(s) {capable} "
                                               f"cannot reach {inc.location}"))

    issues.sort(key=lambda i: (i.entry is None, i.entry if i.entry is not None else 0))  # stable
    return accepted, timeline, issues


def load_plan_json(path: Path) -> object:
    """Parse plan.json. Never raises on a bad file: an unreadable file or invalid JSON
    (including nesting too deep for the parser) returns a ``PlanLoadError``, which
    validate_plan reports as E101. ``NaN`` / ``Infinity`` literals are accepted by the parser
    and reported as E105 by validate_plan."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return PlanLoadError(str(path), f"cannot read file ({exc})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return PlanLoadError(str(path), f"not valid JSON ({exc})")
    except RecursionError:
        return PlanLoadError(str(path), "not valid JSON (nesting too deep)")
