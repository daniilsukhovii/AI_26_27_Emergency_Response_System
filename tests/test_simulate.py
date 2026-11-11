"""Event-driven simulation (SPEC §8.6 T-SIM-3, T-SIM-5, T-SIM-6 + simulator properties).

Fixture tests inject hand-made beliefs, the reference Dijkstra router and the greedy planner,
so they exercise infra only. Variants marked "kernels" use the production pipeline.
"""
from __future__ import annotations

import json

import pytest

import run

from erp.config import Config
from erp.csp import csp_planner
from erp.greedy import greedy_planner
from erp.io_load import load_scenario
from erp.roadnet import build_network
from erp.routing import RouteCache
from erp.simulate import simulate
from tests.fixtures import (
    SCENARIO_DIRS, hand_network, incident, node, reference_router, responder, road, two_way,
    write_scenario,
)


class Spy:
    def __init__(self, inner):
        self.inner = inner
        self.problems = []

    def __call__(self, p):
        self.problems.append(p)
        return self.inner(p)


def _assert_no_future_knowledge(spy):
    assert spy.problems
    for p in spy.problems:
        for i in p.incidents:
            assert i.timestamp <= p.now + 1e-9, (i.id, i.timestamp, p.now)


def test_T_SIM_3_spy_planner_s3_kernels():
    s = load_scenario(SCENARIO_DIRS[2])
    cfg = Config()
    net = build_network(s, cfg)
    spy = Spy(csp_planner(cfg))
    simulate(s, net, cfg, spy, RouteCache(net))
    _assert_no_future_knowledge(spy)


@pytest.mark.parametrize("after_job", ["on-site", "return"])
def test_T_SIM_3_spy_planner_s3_injected(after_job):
    s = load_scenario(SCENARIO_DIRS[2])
    cfg = Config(after_job=after_job, planner="greedy")
    net = hand_network(s, cfg)
    spy = Spy(greedy_planner(cfg))
    res = simulate(s, net, cfg, spy, reference_router(net))
    _assert_no_future_knowledge(spy)
    for a in res.assignments:                           # departure never before the incident is known
        assert a.time >= s.incident(a.incident_id).timestamp


def _run(d, cfg, status=None, planner=None):
    s = load_scenario(d)
    net = hand_network(s, cfg, status)
    res = simulate(s, net, cfg, planner or greedy_planner(cfg), reference_router(net))
    return s, net, res


def test_T_SIM_5_return_mode(tmp_path):
    # A-B: 10 s each way (distance 100, speed 10); B-A back trip 10 s.
    d = write_scenario(
        tmp_path / "ret", nodes=[node("A", 0, 0), node("B", 100, 0)], roads=two_way("A", "B", 100),
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "B", "Critical", 100, "X", 0, 5),
                   incident("I2", "A", "High", 100, "X", 0, 0)])
    s, net, res = _run(d, Config(after_job="return", planner="greedy"))
    first, second = res.assignments
    assert (first.incident_id, first.time, first.path) == ("I1", 0.0, ("A", "B"))
    assert second.incident_id == "I2"
    assert second.time == pytest.approx(10 + 5 + net.path_cost(["B", "A"]))
    assert second.path[0] == "A"
    assert res.unhandled == {}


def test_T_SIM_5_on_site_mode_for_contrast(tmp_path):
    d = write_scenario(
        tmp_path / "ons", nodes=[node("A", 0, 0), node("B", 100, 0)], roads=two_way("A", "B", 100),
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "B", "Critical", 100, "X", 0, 5),
                   incident("I2", "A", "High", 100, "X", 0, 0)])
    _, _, res = _run(d, Config(after_job="on-site", planner="greedy"))
    second = res.assignments[1]
    assert second.time == pytest.approx(15.0) and second.path == ("B", "A")


def test_T_SIM_6_zero_travel_zero_duration(tmp_path):
    d = write_scenario(
        tmp_path / "zero", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "A", "High", 10, "X", 3, 0), incident("I2", "A", "High", 10, "X", 3, 0)])
    _, _, res = _run(d, Config(planner="greedy"))
    assert [(a.incident_id, a.time, a.path) for a in res.assignments] == \
        [("I1", 3.0, ("A",)), ("I2", 3.0, ("A",))]
    assert res.unhandled == {}


def test_busy_responder_never_dispatched_early(tmp_path):
    d = write_scenario(
        tmp_path / "busy", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["X"], busy_for=7.5)],
        incidents=[incident("I1", "B", "Critical", 5, "X", 0, 1)])
    _, _, res = _run(d, Config(planner="greedy"))
    (a,) = res.assignments
    assert a.time == 7.5 and a.path == ("A", "B")


def test_unhandled_reasons(tmp_path):
    d = write_scenario(
        tmp_path / "unh", nodes=[node("A", 0, 0), node("B", 10, 0), node("C", 20, 0)],
        roads=two_way("A", "B", 10) + [road("C", "A", 20)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "B", "High", 50, "X"), incident("I2", "C", "High", 50, "X"),
                   incident("I3", "B", "High", 50, "Pumping")])
    _, _, res = _run(d, Config(planner="greedy"))
    assert [a.incident_id for a in res.assignments] == ["I1"]
    assert res.unhandled == {"I2": "unreachable", "I3": "no capable responder"}


def test_planner_assigning_incapable_responder_is_rejected(tmp_path):
    d = write_scenario(
        tmp_path / "bad", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["X"]), responder("R2", "A", ["Y"])],
        incidents=[incident("I1", "B", "High", 50, "X")])
    with pytest.raises(ValueError):
        _run(d, Config(), planner=lambda p: {"I1": "R2"})


def test_simulation_is_deterministic():
    s = load_scenario(SCENARIO_DIRS[2])
    cfg = Config(planner="greedy")
    runs = []
    for _ in range(2):
        net = hand_network(s, cfg)
        runs.append(simulate(s, net, cfg, greedy_planner(cfg), reference_router(net)))
    assert runs[0] == runs[1]


def test_AUD3_incident_later_than_now_is_not_used(tmp_path):
    """AUD-3, CLAUDE.md: never use incidents whose timestamp is later than the current simulation
    time. An incident is known at t iff timestamp <= t, exactly (SPEC §0): at t = 10 (R1 becomes
    free) an incident with timestamp 10 + 5e-10 is not yet known; it is planned and dispatched at
    its own timestamp, and the plan has no E402."""
    ts = 10.0000000005
    d = write_scenario(tmp_path / "eps", nodes=[node("A", 0, 0), node("B", 100, 0)],
                       roads=two_way("A", "B", 100), responders=[responder("R1", "A", ["X"], busy_for=10)],
                       incidents=[incident("I1", "B", "High", 500, "X", ts, 5)])
    res = run.run_scenario(d, tmp_path / "out", Config())
    (entry,) = json.loads(res.plan_path.read_text())
    assert entry["time"] >= ts, f"dispatched at {entry['time']} before the incident exists ({ts})"
    assert res.simulation.unhandled == {}
    assert "E402" not in {i.code for i in res.issues}
