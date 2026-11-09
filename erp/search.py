"""A* route search over the usable road network (SPEC §5.6, heuristic §6.6).

STUDENT kernels: ``euclidean_heuristic``, ``astar``.
"""
from __future__ import annotations

import math
from queue import PriorityQueue
from typing import Callable

from erp.model import NodeId, Route
from erp.roadnet import RoadNetwork


# STUDENT:
def euclidean_heuristic(net: RoadNetwork, goal: NodeId) -> Callable[[NodeId], float]:
    """h(n) = euclid(n, goal) / v_max  (§6.6), seconds."""

    v_max = net.v_max
    if v_max <= 0:
        raise ValueError("v_max must be positive")

    if not net.nodes.__contains__(goal):
        raise ValueError(f"goal {goal} not in network")

    goal_node = net.nodes[goal]
    gx, gy = goal_node.x, goal_node.y

    def h(n: NodeId) -> float:
        node = net.nodes[n]
        x, y = node.x, node.y
        return math.sqrt((x - gx)**2 + (y - gy)**2) / v_max   # відстань до цілі / v_max

    return h



# STUDENT:
def astar(net: RoadNetwork, start: NodeId, goal: NodeId,
          h: Callable[[NodeId], float] | None = None) -> Route | None:
    """A* over usable roads. Returns Route(path, cost) with path[0]=start, path[-1]=goal,
    cost = net.path_cost(path); Route((start,), 0.0) if start == goal; None if unreachable.
    Must terminate on every finite graph. Deterministic tie-break on equal f: smaller h, then
    natural node id (ENG; the student may change the rule but must keep it deterministic)."""


    if start == goal:
        return Route((start,), 0.0)

    heuristic = h if h is not None else lambda _: 0.0

    pq: PriorityQueue[tuple[float, float, NodeId, Route]] = PriorityQueue()
    g_score = {start: 0.0}

    start_route = Route((start,), 0.0)
    start_h = heuristic(start)

    pq.put((start_h, start_h, start, start_route))

    while not pq.empty():
        f_score, h_score, node_id, cr_route = pq.get()

        # already saw a cheaper way
        if cr_route.cost > g_score[node_id]:
            continue

        if node_id == goal:
            return cr_route

        for neighbour_node_id, edge_cost in net.neighbours(node_id):
            #
            if not net.is_usable(node_id, neighbour_node_id):
                continue

            tentative_g = cr_route.cost + edge_cost

            if tentative_g >= g_score.get(neighbour_node_id, float("inf")):
                continue

            g_score[neighbour_node_id] = tentative_g

            path = cr_route.path + (neighbour_node_id,)
            new_route = Route(path, tentative_g)

            neighbour_h = heuristic(neighbour_node_id)
            priority = tentative_g + neighbour_h

            pq.put((
                priority,
                neighbour_h,
                neighbour_node_id,
                new_route
            ))

    return None

