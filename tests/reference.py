"""Reference implementations used ONLY by tests (never imported by erp/).

* Dijkstra (independent of erp/search.py) — cross-check of A* and an injectable router.
* Brute-force HMM filtering: sum over all hidden state sequences.
* Exhaustive CSP enumeration over all assignments (itertools.product).
* Floyd-Warshall closure for random metric travel matrices.
"""
from __future__ import annotations

import heapq
import itertools
import math
from typing import Callable, Mapping, Sequence

from erp.model import LEVELS, AllocationProblem, CostTuple, HMMParams, NodeId, Route, natural_key


# ------------------------------------------------------------------ Dijkstra

def dijkstra(net, source: NodeId) -> tuple[dict[NodeId, float], dict[NodeId, NodeId]]:
    """Shortest costs from ``source`` over ``net.neighbours`` and the predecessor map."""
    dist: dict[NodeId, float] = {source: 0.0}
    prev: dict[NodeId, NodeId] = {}
    done: set[NodeId] = set()
    pq = [(0.0, natural_key(source), source)]
    while pq:
        d, _, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        for v, w in net.neighbours(u):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, natural_key(v), v))
    return dist, prev


def dijkstra_costs(net, source: NodeId) -> dict[NodeId, float]:
    return dijkstra(net, source)[0]


def dijkstra_route(net, start: NodeId, goal: NodeId) -> Route | None:
    """Route with the same contract as erp.search.astar (injectable into RouteCache)."""
    if start == goal:
        return Route((start,), 0.0)
    dist, prev = dijkstra(net, start)
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return Route(tuple(path), net.path_cost(path))


# ------------------------------------------------------------------ HMM

def brute_force_filter(params: HMMParams, observations: Sequence[str],
                       convention: str = "pi_is_t1") -> list[dict[str, float]]:
    """P(X_t | o_1..o_t) for t = 1..T by summing the joint over all hidden sequences.

    pi_is_t1: P(x_1..x_t, o_1..o_t) = π(x_1)B(x_1,o_1) Π_{k>=2} A(x_{k-1},x_k)B(x_k,o_k)
    pi_is_t0: an extra hidden X_0 ~ π, then Π_{k>=1} A(x_{k-1},x_k)B(x_k,o_k)
    """
    out: list[dict[str, float]] = []
    pi, a, b = params.initial, params.transition, params.emission
    for t in range(1, len(observations) + 1):
        obs = observations[:t]
        acc = {lv: 0.0 for lv in LEVELS}
        extra = 1 if convention == "pi_is_t0" else 0
        for seq in itertools.product(LEVELS, repeat=t + extra):
            if convention == "pi_is_t0":
                p = pi[seq[0]]
                hidden = seq[1:]
                prev = seq[0]
                for x, o in zip(hidden, obs):
                    p *= a[prev][x] * b[x][o]
                    prev = x
            else:
                p = pi[seq[0]] * b[seq[0]][obs[0]]
                for k in range(1, t):
                    p *= a[seq[k - 1]][seq[k]] * b[seq[k]][obs[k]]
            acc[seq[-1]] += p
        z = sum(acc.values())
        out.append({lv: acc[lv] / z for lv in LEVELS})
    return out


# ------------------------------------------------------------------ CSP

def exhaustive_allocation(p: AllocationProblem,
                          cost_fn: Callable[[AllocationProblem, Mapping[str, str]], CostTuple | None]
                          ) -> tuple[CostTuple | None, list[dict[str, str]]]:
    """Minimum cost over every complete assignment of the variables with non-empty domain."""
    variables = [i.id for i in p.incidents if p.domains.get(i.id)]
    best: CostTuple | None = None
    best_assignments: list[dict[str, str]] = []
    for values in itertools.product(*(p.domains[v] for v in variables)):
        a = dict(zip(variables, values))
        c = cost_fn(p, a)
        if c is None:
            continue
        if best is None or c < best:
            best, best_assignments = c, [a]
        elif c == best:
            best_assignments.append(a)
    return best, best_assignments


def floyd_warshall(nodes: Sequence[str], edges: Mapping[tuple[str, str], float]
                   ) -> dict[tuple[str, str], float]:
    """All-pairs shortest travel times; inf where unreachable; d(u,u) = 0 (metric closure)."""
    d = {(u, v): (0.0 if u == v else edges.get((u, v), math.inf)) for u in nodes for v in nodes}
    for k in nodes:
        for i in nodes:
            dik = d[(i, k)]
            if dik == math.inf:
                continue
            for j in nodes:
                if dik + d[(k, j)] < d[(i, j)]:
                    d[(i, j)] = dik + d[(k, j)]
    return d
