"""RouteCache (SPEC §5.7) and the test-only reference Dijkstra (infra, no kernels)."""
from __future__ import annotations

import math

import pytest

from erp.config import Config
from erp.io_load import load_scenario
from erp.model import Route
from erp.routing import RouteCache
from tests.fixtures import (
    BLOCKED, hand_network, incident, node, responder, road, two_way, write_scenario,
)
from tests.reference import dijkstra_costs, dijkstra_route


@pytest.fixture
def net(tmp_path):
    # A -> B -> C (cost 1 + 1) vs A -> C direct (cost 3); D isolated
    d = write_scenario(
        tmp_path / "r",
        nodes=[node("A", 0, 0), node("B", 10, 0), node("C", 20, 0), node("D", 50, 50)],
        roads=two_way("A", "B", 10) + two_way("B", "C", 10) + [road("A", "C", 30)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "C", "High", 10, "X")])
    s = load_scenario(d)
    return hand_network(s, Config())


def test_reference_dijkstra(net):
    assert dijkstra_route(net, "A", "C") == Route(("A", "B", "C"), 2.0)
    assert dijkstra_route(net, "A", "A") == Route(("A",), 0.0)
    assert dijkstra_route(net, "A", "D") is None
    assert dijkstra_costs(net, "C") == {"C": 0.0, "B": 1.0, "A": 2.0}


def test_route_cache_memoises():
    calls = []

    def fake(net, u, v):
        calls.append((u, v))
        return None if v == "D" else Route((u, v), 7.0)

    rc = RouteCache(net=None, search=fake)  # type: ignore[arg-type]
    assert rc.route("A", "B") == Route(("A", "B"), 7.0)
    assert rc.route("A", "B") == Route(("A", "B"), 7.0)
    assert rc.travel_time("A", "B") == 7.0
    assert rc.travel_time("A", "D") == math.inf
    assert rc.route("A", "D") is None
    assert calls == [("A", "B"), ("A", "D")]
    assert rc.search_calls == 2


def test_route_cache_with_reference_search(net):
    rc = RouteCache(net, dijkstra_route)
    assert rc.travel_time("A", "C") == 2.0
    assert rc.route("C", "A").path == ("C", "B", "A")


def test_route_cache_sees_removed_roads(tmp_path):
    d = write_scenario(
        tmp_path / "r2", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["X"])], incidents=[incident("I1", "B", "High", 10, "X")])
    s = load_scenario(d)
    rc = RouteCache(hand_network(s, Config(), {("A", "B"): BLOCKED}), dijkstra_route)
    assert rc.route("A", "B") is None
    assert rc.travel_time("B", "A") == 1.0
