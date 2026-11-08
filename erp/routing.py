"""Memoised route queries (SPEC §5.7). Road states are static [D add.], so every
(u, v) query is answered once."""
from __future__ import annotations

import math
from typing import Callable

from erp.model import NodeId, Route
from erp.roadnet import RoadNetwork
from erp.search import astar


class RouteCache:
    def __init__(self, net: RoadNetwork,
                 search: Callable[..., Route | None] = astar) -> None:
        self.net = net
        self._search = search
        self._cache: dict[tuple[NodeId, NodeId], Route | None] = {}
        self.search_calls = 0

    def route(self, u: NodeId, v: NodeId) -> Route | None:
        """Best route u -> v (memoised); None if unreachable."""
        key = (u, v)
        if key not in self._cache:
            self.search_calls += 1
            self._cache[key] = self._search(self.net, u, v)
        return self._cache[key]

    def travel_time(self, u: NodeId, v: NodeId) -> float:
        """Route cost in s; inf if unreachable."""
        r = self.route(u, v)
        return math.inf if r is None else r.cost
