"""A* route search over the usable road network (SPEC §5.6, heuristic §6.6).

STUDENT kernels: ``euclidean_heuristic``, ``astar``.
"""
from __future__ import annotations

from typing import Callable

from erp.model import NodeId, Route
from erp.roadnet import RoadNetwork


# STUDENT:
def euclidean_heuristic(net: RoadNetwork, goal: NodeId) -> Callable[[NodeId], float]:
    """h(n) = euclid(n, goal) / v_max  (§6.6), seconds."""
    raise NotImplementedError


# STUDENT:
def astar(net: RoadNetwork, start: NodeId, goal: NodeId,
          h: Callable[[NodeId], float] | None = None) -> Route | None:
    """A* over usable roads. Returns Route(path, cost) with path[0]=start, path[-1]=goal,
    cost = net.path_cost(path); Route((start,), 0.0) if start == goal; None if unreachable.
    Must terminate on every finite graph. Deterministic tie-break on equal f: smaller h, then
    natural node id (ENG; the student may change the rule but must keep it deterministic)."""
    raise NotImplementedError
