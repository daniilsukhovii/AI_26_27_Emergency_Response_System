"""Road beliefs, edge weights and the usable directed graph (SPEC §5.5, §6.3, §6.5)."""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from erp.bayes import compute_status_beliefs
from erp.config import Config
from erp.hmm import compute_traffic_factors
from erp.model import (
    Level, Node, NodeId, Road, RoadBelief, RoadKey, Scenario, Status, natural_key, road_sort_key,
)


def expected_status_multiplier(status: Mapping[Status, float], congested_mult: float) -> float:
    """E[mult | not Blocked] = (P(O)·1 + P(C)·m_C) / (P(O) + P(C))  (§6.3), dimensionless.

    Returns math.inf if P(Open) + P(Congested) = 0 (such a road is always removed)."""
    p_o, p_c = status["Open"], status["Congested"]
    denom = p_o + p_c
    if denom <= 0.0:
        return math.inf
    return (p_o * 1.0 + p_c * congested_mult) / denom


def edge_weight(road: Road, e_mult: float, f_traffic: float) -> float:
    """w(e) = distance / speed · E[mult | not Blocked] · f_traffic  (§6.5), seconds."""
    return road.distance / road.speed * e_mult * f_traffic


def make_belief(road: Road, status: Mapping[Status, float], has_reports: bool,
                traffic: Mapping[Level, float] | None, f_traffic: float, cfg: Config) -> RoadBelief:
    """Assemble a RoadBelief from a status distribution and a traffic factor (ENG helper).

    Also used by tests to inject hand-made beliefs (SPEC §3.2 injection rule)."""
    removed = status["Blocked"] >= cfg.tau
    e_mult = expected_status_multiplier(status, cfg.congested_multiplier)
    weight = math.inf if removed else edge_weight(road, e_mult, f_traffic)
    return RoadBelief(road=road.key, status=dict(status), has_reports=has_reports,
                      traffic=None if traffic is None else dict(traffic), f_traffic=f_traffic,
                      e_mult=e_mult, removed=removed, weight=weight)


def compute_road_beliefs(s: Scenario, cfg: Config) -> dict[RoadKey, RoadBelief]:
    """Bayes posterior/prior (§6.1-6.2) + HMM traffic factor (§6.4-6.5) for every graph road."""
    status = compute_status_beliefs(s)
    traffic = compute_traffic_factors(s, cfg)
    out: dict[RoadKey, RoadBelief] = {}
    for key, road in s.roads.items():
        dist, has_reports = status[key]
        tdist, f = traffic[key]
        out[key] = make_belief(road, dist, has_reports, tdist, f, cfg)
    return out


class RoadNetwork:
    """Directed graph of usable roads with expected travel-time weights (s)."""

    def __init__(self, s: Scenario, beliefs: Mapping[RoadKey, RoadBelief], cfg: Config) -> None:
        missing = [k for k in s.roads if k not in beliefs]
        if missing:
            raise ValueError(f"no belief for road(s) {missing}")
        self.cfg = cfg
        self.nodes: Mapping[NodeId, Node] = s.nodes
        self.roads: Mapping[RoadKey, Road] = s.roads
        self.beliefs: Mapping[RoadKey, RoadBelief] = {k: beliefs[k] for k in s.roads}
        # OQ-3: v_max = maximum road speed of the loaded graph (m/s)
        self.v_max: float = max((r.speed for r in s.roads.values()), default=math.inf)
        adj: dict[NodeId, list[tuple[NodeId, float]]] = {n: [] for n in s.nodes}
        for key, b in self.beliefs.items():
            if not b.removed and math.isfinite(b.weight):
                adj[key[0]].append((key[1], b.weight))
        for u in adj:
            adj[u].sort(key=lambda vw: natural_key(vw[0]))
        self._adj = adj
        self._w: dict[RoadKey, float] = {(u, v): w for u, lst in adj.items() for v, w in lst}

    def neighbours(self, u: NodeId) -> list[tuple[NodeId, float]]:
        """(v, w(u,v)) for usable roads u->v, natural order of v."""
        return list(self._adj.get(u, ()))

    def is_usable(self, u: NodeId, v: NodeId) -> bool:
        return (u, v) in self._w

    def weight(self, u: NodeId, v: NodeId) -> float:
        """Edge weight in s; inf if the road is missing or removed."""
        return self._w.get((u, v), math.inf)

    def path_cost(self, path: Sequence[NodeId]) -> float:
        """Σ weights (s); 0 for a 1-node path; inf if any edge is unusable."""
        if len(path) == 0:
            raise ValueError("empty path")
        return float(sum(self.weight(u, v) for u, v in zip(path, path[1:])))

    def removed_roads(self) -> list[tuple[RoadKey, float]]:
        """Removed roads with their P(Blocked), natural order of (from, to)."""
        return [(k, b.status["Blocked"]) for k, b in sorted(self.beliefs.items(),
                                                            key=lambda kv: road_sort_key(kv[0]))
                if b.removed]

    def usable_roads(self) -> list[RoadKey]:
        return sorted(self._w, key=road_sort_key)


def build_network(s: Scenario, cfg: Config,
                  beliefs: Mapping[RoadKey, RoadBelief] | None = None) -> RoadNetwork:
    """Build the network; ``beliefs`` may be injected (tests), else they are computed."""
    if beliefs is None:
        beliefs = compute_road_beliefs(s, cfg)
    return RoadNetwork(s, beliefs, cfg)
