"""Edge weights and the usable network (SPEC §8.3).

T-W1..T-W6 build the real belief set (STUDENT Bayes + HMM kernels). The remaining tests
use injected beliefs and test infra only.
"""
from __future__ import annotations

import math

import pytest

from erp.config import Config
from erp.io_load import load_scenario
from erp.model import Road
from erp.roadnet import (
    RoadNetwork, build_network, edge_weight, expected_status_multiplier, make_belief,
)
from tests.fixtures import (
    BLOCKED, SCENARIO_DIRS, hand_beliefs, incident, node, responder, road, two_way, write_scenario,
)

T = 1e-3   # s


@pytest.fixture(scope="module")
def scen():
    return {k: load_scenario(d) for k, d in zip((1, 2, 3), SCENARIO_DIRS)}


@pytest.fixture(scope="module")
def s1net(scen):
    return build_network(scen[1], Config(tau=0.5))


@pytest.mark.parametrize("road_key,base,weight", [
    (("N2", "N1"), 775 / 15, 78.5625),
    (("H1", "N4"), 340 / 30, 12.6232),
    (("N4", "N2"), 41.0, 63.0174),
    (("N3", "N4"), 51.6, 68.5916),
], ids=["T-W1", "T-W2", "T-W3", "T-W4"])
def test_T_W1_W4_weights(scen, s1net, road_key, base, weight):
    r = scen[1].roads[road_key]
    assert r.distance / r.speed == pytest.approx(base, abs=T)
    assert s1net.weight(*road_key) == pytest.approx(weight, abs=T)
    b = s1net.beliefs[road_key]
    assert b.weight == pytest.approx(edge_weight(r, b.e_mult, b.f_traffic), abs=1e-12)


def test_T_W2_prior_road_factors(s1net):
    b = s1net.beliefs[("H1", "N4")]
    assert not b.has_reports
    assert b.e_mult == pytest.approx(1.104046, abs=1e-6)
    assert b.f_traffic == pytest.approx(1.0088, abs=1e-4)


def test_T_W5_removed_road(s1net):
    assert s1net.weight("N1", "N2") == math.inf
    assert not s1net.is_usable("N1", "N2")
    assert "N2" not in [v for v, _ in s1net.neighbours("N1")]
    assert s1net.beliefs[("N1", "N2")].removed


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W6_weights_bounded_below(scen, k):
    s = scen[k]
    net = build_network(s, Config())
    assert net.v_max == max(r.speed for r in s.roads.values())
    usable = net.usable_roads()
    assert usable
    for u, v in usable:
        r = s.roads[(u, v)]
        w = net.weight(u, v)
        euclid = math.hypot(s.nodes[u].x - s.nodes[v].x, s.nodes[u].y - s.nodes[v].y)
        assert w >= r.distance / r.speed - 1e-12
        assert w >= euclid / net.v_max - 1e-12


def test_T_W7_multiplier_below_one():
    with pytest.raises(ValueError):
        Config(traffic_multipliers={"Low": 1.0, "Medium": 0.99, "High": 1.5})


# ------------------------------------------------------------------ infra only

def test_expected_status_multiplier_values():
    prior = {"Open": 0.685, "Congested": 0.18, "Blocked": 0.135}
    assert expected_status_multiplier(prior, 1.5) == pytest.approx(0.955 / 0.865, abs=1e-12)
    assert expected_status_multiplier(prior, 1.5) == pytest.approx(1.104046, abs=1e-6)
    assert expected_status_multiplier({"Open": 1, "Congested": 0, "Blocked": 0}, 1.5) == 1.0
    assert expected_status_multiplier({"Open": 0, "Congested": 0.4, "Blocked": 0.6}, 1.5) == \
        pytest.approx(1.5, abs=1e-12)
    assert expected_status_multiplier(BLOCKED, 1.5) == math.inf


def test_edge_weight_formula():
    r = Road("A", "B", distance=775, speed=15, road_type="secondary")
    assert edge_weight(r, 1.5, 1.2) == pytest.approx(775 / 15 * 1.8, abs=1e-12)
    assert edge_weight(r, 1.0, 1.0) == pytest.approx(775 / 15, abs=1e-12)


def test_make_belief_threshold_is_inclusive():
    r = Road("A", "B", 100, 10, "main")
    st = {"Open": 0.3, "Congested": 0.2, "Blocked": 0.5}
    b = make_belief(r, st, True, None, 1.1, Config(tau=0.5))
    assert b.removed and b.weight == math.inf
    b = make_belief(r, st, True, None, 1.1, Config(tau=0.51))
    assert not b.removed
    assert b.e_mult == pytest.approx((0.3 + 0.2 * 1.5) / 0.5)
    assert b.weight == pytest.approx(10 * b.e_mult * 1.1)


@pytest.fixture
def small(tmp_path):
    d = write_scenario(
        tmp_path / "small",
        nodes=[node("A", 0, 0), node("B", 10, 0), node("C", 10, 10), node("N10", 0, 10),
               node("N2", 5, 5)],
        roads=two_way("A", "B", 10) + two_way("B", "C", 10, speed=20) + [road("A", "N10", 10),
                                                                         road("A", "N2", 8)]
              + [road("A", "C", 20)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "C", "High", 100, "X")])
    return load_scenario(d)


def test_network_with_injected_beliefs(small):
    cfg = Config()
    net = RoadNetwork(small, hand_beliefs(small, cfg, {("A", "C"): BLOCKED}), cfg)
    assert net.v_max == 20
    # natural order of neighbour ids: B < N2 < N10 ; removed A->C absent
    assert [v for v, _ in net.neighbours("A")] == ["B", "N2", "N10"]
    assert net.weight("A", "B") == pytest.approx(1.0)
    assert net.weight("B", "C") == pytest.approx(0.5)
    assert net.weight("A", "C") == math.inf and not net.is_usable("A", "C")
    assert net.weight("C", "A") == math.inf                   # no such road
    assert net.path_cost(["A"]) == 0.0
    assert net.path_cost(["A", "B", "C"]) == pytest.approx(1.5)
    assert net.path_cost(["A", "C"]) == math.inf
    assert net.removed_roads() == [(("A", "C"), 1.0)]
    assert net.neighbours("N10") == []


def test_network_requires_belief_for_every_road(small):
    cfg = Config()
    b = hand_beliefs(small, cfg)
    b.pop(("A", "B"))
    with pytest.raises(ValueError):
        RoadNetwork(small, b, cfg)


def test_build_network_uses_injected_beliefs(small):
    cfg = Config()
    b = hand_beliefs(small, cfg, f_traffic=2.0)
    net = build_network(small, cfg, beliefs=b)
    assert net.weight("A", "B") == pytest.approx(2.0)
