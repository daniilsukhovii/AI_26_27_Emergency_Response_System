"""A* search (SPEC §8.4, S1, tau = 0.5). Calls STUDENT kernels of erp/search.py."""
from __future__ import annotations

import math
from itertools import product

import pytest

from erp.config import Config
from erp.io_load import load_scenario
from erp.model import Route
from erp.roadnet import build_network
from erp.search import astar, euclidean_heuristic
from tests.fixtures import (
    BLOCKED, SCENARIO_DIRS, hand_network, incident, node, responder, road, two_way, write_scenario,
)
from tests.reference import dijkstra_costs, dijkstra_route

T = 1e-3


@pytest.fixture(scope="module")
def nets():
    return {k: build_network(load_scenario(d), Config(tau=0.5, after_job="on-site"))
            for k, d in zip((1, 2, 3), SCENARIO_DIRS)}


@pytest.mark.parametrize("start,goal,path,cost", [
    ("H1", "N2", ("H1", "N2"), 53.5061),
    ("N1", "N2", ("N1", "H1", "N2"), 87.4947),
    ("N3", "N1", ("N3", "N4", "H1", "N1"), 120.7102),
    ("N2", "N3", ("N2", "H1", "N4", "N3"), 124.5807),
], ids=["T-A1", "T-A2", "T-A3", "T-A4"])
def test_T_A1_A4_s1_routes(nets, start, goal, path, cost):
    r = astar(nets[1], start, goal)
    assert isinstance(r, Route)
    assert r.path == path
    assert r.cost == pytest.approx(cost, abs=T)
    assert r.cost == pytest.approx(nets[1].path_cost(r.path), abs=1e-12)


def test_T_A1_alternative_is_worse(nets):
    assert nets[1].path_cost(["H1", "N4", "N2"]) == pytest.approx(75.6406, abs=T)


@pytest.mark.parametrize("x", ["N1", "N2", "N3", "N4", "H1"])
def test_T_A5_start_equals_goal(nets, x):
    assert astar(nets[1], x, x) == Route((x,), 0.0)


@pytest.fixture
def isolated_target_net(tmp_path):
    # Z has incoming roads only from Y, and Y->Z is removed; Z->A exists (outgoing only)
    d = write_scenario(
        tmp_path / "iso",
        nodes=[node("A", 0, 0), node("B", 10, 0), node("Y", 20, 0), node("Z", 30, 0)],
        roads=two_way("A", "B", 10) + two_way("B", "Y", 10) + [road("Y", "Z", 10), road("Z", "A", 40)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "Z", "High", 100, "X")])
    s = load_scenario(d)
    cfg = Config()
    return hand_network(s, cfg, {("Y", "Z"): BLOCKED})


def test_T_A6_unreachable_target_returns_none(isolated_target_net):
    for start in ("A", "B", "Y"):
        assert astar(isolated_target_net, start, "Z") is None
    assert astar(isolated_target_net, "Z", "B") is not None


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_A7_astar_equals_dijkstra(nets, k):
    net = nets[k]
    for u, v in product(net.nodes, repeat=2):
        ref = dijkstra_route(net, u, v)
        got = astar(net, u, v)
        if ref is None:
            assert got is None, (u, v)
        else:
            assert got is not None, (u, v)
            assert got.path[0] == u and got.path[-1] == v
            assert got.cost == pytest.approx(ref.cost, abs=1e-9), (u, v)
            assert got.cost == pytest.approx(net.path_cost(got.path), abs=1e-9)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_A8_heuristic_admissible_and_consistent(nets, k):
    net = nets[k]
    for goal in net.nodes:
        h = euclidean_heuristic(net, goal)
        assert h(goal) == pytest.approx(0.0, abs=1e-12)
        dist_to_goal = {}
        for n in net.nodes:
            d = dijkstra_costs(net, n).get(goal, math.inf)
            dist_to_goal[n] = d
            assert h(n) <= d + 1e-9
        for u, v in net.usable_roads():
            assert h(u) <= net.weight(u, v) + h(v) + 1e-9


def test_T_A9_heuristic_value(nets):
    h = euclidean_heuristic(nets[1], "N2")
    assert h("H1") == pytest.approx(math.dist((512, 100), (683, 686)) / 30, abs=1e-9)
    assert h("H1") == pytest.approx(20.348, abs=T)


def test_astar_with_explicit_heuristic_zero(nets):
    """h = 0 turns A* into uniform-cost search; result must still be optimal."""
    r = astar(nets[1], "N3", "N1", h=lambda n: 0.0)
    assert r is not None and r.cost == pytest.approx(120.7102, abs=T)


def test_astar_deterministic(nets):
    assert [astar(nets[3], "N1", g) for g in nets[3].nodes] == \
           [astar(nets[3], "N1", g) for g in nets[3].nodes]
