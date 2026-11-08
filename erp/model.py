"""Immutable data classes, type aliases and order keys (SPEC §4).

Units: times in seconds (s), distances in metres (m), speeds in m/s.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Mapping

NodeId = str
RoadKey = tuple[NodeId, NodeId]                     # (from, to), directed
Status = Literal["Open", "Congested", "Blocked"]
Level = Literal["Low", "Medium", "High"]
Priority = Literal["Critical", "High", "Medium", "Low"]
Weather = Literal["Clear", "Rain", "Storm"]
Source = Literal["Citizen", "Police", "Sensor"]
Dist = dict[str, float]                             # label -> probability
CostTuple = tuple[int, int, int, float]             # §6.7

STATUSES: tuple[Status, ...] = ("Open", "Congested", "Blocked")
LEVELS: tuple[Level, ...] = ("Low", "Medium", "High")
PRIORITIES: tuple[Priority, ...] = ("Critical", "High", "Medium", "Low")
WEATHERS: tuple[Weather, ...] = ("Clear", "Rain", "Storm")
SOURCES: tuple[Source, ...] = ("Citizen", "Police", "Sensor")

EPS = 1e-9   # s; `a <= b` is evaluated as `a <= b + EPS` (SPEC §0)

_NATURAL_RE = re.compile(r"^(.*?)(\d+)$")


def natural_key(id_: str) -> tuple[str, int]:
    """Natural id order: ``"I2" < "I10"``; key = (alpha prefix, int suffix).

    Ids without a numeric suffix get suffix -1 (sorted before numbered ids
    with the same prefix).
    """
    m = _NATURAL_RE.match(id_)
    if m is None:
        return (id_, -1)
    return (m.group(1), int(m.group(2)))


_PRIORITY_RANK: dict[str, int] = {p: k for k, p in enumerate(PRIORITIES)}


def priority_rank(p: str) -> int:
    """rank(Critical)=0, rank(High)=1, rank(Medium)=2, rank(Low)=3."""
    return _PRIORITY_RANK[p]


def order_key(inc: "Incident") -> tuple:
    """(rank(priority), deadline, timestamp, natural(id)) — SPEC §0."""
    return (priority_rank(inc.priority), inc.deadline, inc.timestamp, natural_key(inc.id))


def road_sort_key(key: RoadKey) -> tuple:
    return (natural_key(key[0]), natural_key(key[1]))


@dataclass(frozen=True)
class Node:
    id: NodeId
    name: str
    x: float          # m
    y: float          # m
    type: str         # informational only


@dataclass(frozen=True)
class Road:
    src: NodeId
    dst: NodeId
    distance: float   # m
    speed: float      # m/s
    road_type: str    # informational only

    @property
    def key(self) -> RoadKey:
        return (self.src, self.dst)


@dataclass(frozen=True)
class Responder:
    id: str
    type: str
    start_location: NodeId
    capabilities: frozenset[str]
    available: bool
    time_until_available: float   # s, raw value of the CSV column

    @property
    def free_at_start(self) -> float:
        """Free time at t = 0 [D 2]: ``time_until_available`` if Busy, else 0 s."""
        return 0.0 if self.available else self.time_until_available


@dataclass(frozen=True)
class Incident:
    id: str
    location: NodeId
    priority: Priority
    deadline: float          # s, absolute arrival deadline [A §3.2]
    required_capability: str
    timestamp: float         # s, time the incident becomes known
    time_required: float     # s, on-site handling time after arrival


@dataclass(frozen=True)
class RoadReport:
    road: RoadKey
    weather: Weather
    source: Source
    reported_status: Status


@dataclass(frozen=True)
class RoadCPTs:
    weather_prior: Mapping[Weather, float]
    status_given_weather: Mapping[Weather, Mapping[Status, float]]
    report: Mapping[Source, Mapping[Status, Mapping[Status, float]]]  # [source][true][reported]


@dataclass(frozen=True)
class HMMParams:
    initial: Mapping[Level, float]
    transition: Mapping[Level, Mapping[Level, float]]   # [prev][next]
    emission: Mapping[Level, Mapping[Level, float]]     # [state][observation]


@dataclass(frozen=True)
class Scenario:
    name: str
    nodes: Mapping[NodeId, Node]
    roads: Mapping[RoadKey, Road]
    responders: Mapping[str, Responder]                 # natural id order
    incidents: tuple[Incident, ...]                     # sorted by (timestamp, natural id)
    reports: Mapping[RoadKey, tuple[RoadReport, ...]]   # file order
    traffic_obs: Mapping[RoadKey, tuple[Level, ...]]    # ordered by observation_nr
    cpts: RoadCPTs
    hmm: HMMParams
    warnings: tuple[str, ...]

    def incident(self, incident_id: str) -> Incident:
        for inc in self.incidents:
            if inc.id == incident_id:
                return inc
        raise KeyError(incident_id)


@dataclass(frozen=True)
class RoadBelief:
    road: RoadKey
    status: Mapping[Status, float]        # posterior (reports) or prior via P(W)
    has_reports: bool
    traffic: Mapping[Level, float] | None # filtered distribution, None if no observations
    f_traffic: float                      # dimensionless, >= 1
    e_mult: float                         # E[status multiplier | not Blocked], >= 1
    removed: bool                         # status["Blocked"] >= tau
    weight: float                         # s; math.inf if removed


def _json_number(x: float) -> int | float:
    """Integral times are written as JSON integers, others as floats (SPEC §2.1)."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


@dataclass(frozen=True)
class Assignment:
    responder_id: str
    incident_id: str
    path: tuple[NodeId, ...]
    time: float                           # departure, s

    def to_json(self) -> dict:
        return {
            "responder_id": self.responder_id,
            "incident_id": self.incident_id,
            "path": list(self.path),
            "time": _json_number(float(self.time)),
        }


@dataclass
class ResponderState:                     # simulator-internal
    id: str
    position: NodeId                      # where it is / will be when free
    free_at: float                        # s


@dataclass(frozen=True)
class Route:
    path: tuple[NodeId, ...]
    cost: float                           # s


@dataclass(frozen=True)
class ResponderSnapshot:                  # SPEC §5.8
    id: str
    capabilities: frozenset[str]
    start_location: NodeId
    position: NodeId          # current node, or node where it will become free
    free_at: float            # s; <= now means free now


@dataclass(frozen=True)
class AllocationProblem:                  # SPEC §5.8
    now: float                                         # s
    incidents: tuple[Incident, ...]                    # pending, timestamp <= now, sorted by order_key
    responders: tuple[ResponderSnapshot, ...]          # natural id order
    domains: Mapping[str, tuple[str, ...]]             # incident id -> capable, reachable responder ids
    travel: Callable[[NodeId, NodeId], float]          # s
    after_job: Literal["on-site", "return"]


@dataclass(frozen=True)
class AllocationResult:                   # SPEC §5.9
    assignment: Mapping[str, str]   # incident id -> responder id
    cost: CostTuple | None
    nodes_expanded: int
    optimal: bool                   # False if csp_node_limit was hit


Planner = Callable[[AllocationProblem], Mapping[str, str]]


@dataclass(frozen=True)
class TimelineEntry:                      # validator / stats
    assignment: Assignment
    start_node: NodeId
    departure: float                      # s
    arrival: float                        # s
    finish: float                         # s
    free_at: float                        # s
    position_after: NodeId
    deadline_met: bool
    response_time: float                  # arrival - incident.timestamp, s


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Literal["error", "warning"]
    entry: int | None                     # index in plan.json, None = global
    message: str
