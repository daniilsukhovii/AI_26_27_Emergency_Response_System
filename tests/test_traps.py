"""Trap cases T1..T10 of ASSUMPTIONS.md (SPEC §8.7).

Each trap has (where possible) an "injected" test — hand-made beliefs, reference Dijkstra
router, greedy planner: infra only — and a "pipeline" test through run.run_scenario with the
STUDENT kernels and the validator.
"""
from __future__ import annotations

import json
import shutil

import pytest

import run
from erp.config import Config
from erp.greedy import greedy_planner
from erp.io_load import load_scenario
from erp.simulate import simulate
from erp.validate import validate_plan
from tests.fixtures import (
    BLOCKED, SCENARIO_DIRS, hand_network, incident, node, reference_router, report, responder,
    road, two_way, write_scenario,
)
from tests.reference import dijkstra_route

S1 = SCENARIO_DIRS[0]
P_B_RAIN = {"Open": 0.014337, "Congested": 0.458781, "Blocked": 0.526882}   # T-B2 posterior


def injected(d, cfg=None, status=None):
    cfg = cfg or Config(planner="greedy")
    s = load_scenario(d)
    net = hand_network(s, cfg, status)
    return s, net, simulate(s, net, cfg, greedy_planner(cfg), reference_router(net))


def pipeline(d, tmp_path, cfg=None):
    return run.run_scenario(d, tmp_path / "out", cfg or Config())


def codes(res, severity=None):
    return {i.code for i in res.issues if severity is None or i.severity == severity}


def plan_of(res):
    return json.loads(res.plan_path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ T1

def _s1_with_pumping(tmp_path):
    d = shutil.copytree(S1, tmp_path / "S1_T1")
    f = d / "incidents.csv"
    f.write_text(f.read_text().rstrip("\n") + "\nI8,N4,High,300,Pumping operations,0,10\n")
    return d


def test_T1_no_capable_responder_pipeline(tmp_path):
    d = _s1_with_pumping(tmp_path)
    res = pipeline(d, tmp_path)
    assert res.simulation.unhandled == {"I8": "no capable responder"}
    assert "W501" in codes(res, "warning")
    assert res.exit_code == 0
    base = pipeline(S1, tmp_path / "base")
    assert plan_of(res) == plan_of(base)                          # other incidents unaffected
    assert run.main(["--scenario", str(d), "--out", str(tmp_path / "cli")]) == 0


def test_T1_no_capable_responder_injected(tmp_path):
    d = _s1_with_pumping(tmp_path)
    s, _, res = injected(d)
    assert res.unhandled == {"I8": "no capable responder"}
    assert {a.incident_id for a in res.assignments} == {f"I{k}" for k in range(1, 8)}


# ------------------------------------------------------------------ T2

def _t2_fixture(tmp_path):
    reps = []
    for src in ("A", "Y"):                                           # every incoming road of Z
        reps += [report(src, "Z", "Rain", "Citizen", "Blocked"), report(src, "Z", "Rain", "Police", "Blocked"),
                 report(src, "Z", "Rain", "Sensor", "Congested")]
    return write_scenario(
        tmp_path / "t2", nodes=[node("A", 0, 0), node("Y", 100, 0), node("Z", 100, 100)],
        roads=two_way("A", "Y", 100) + [road("A", "Z", 150), road("Y", "Z", 100), road("Z", "A", 150)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "Z", "Critical", 100, "X"), incident("I2", "Y", "High", 100, "X")],
        reports=reps)


def test_T2_unreachable_pipeline(tmp_path):
    res = pipeline(_t2_fixture(tmp_path), tmp_path)
    assert res.network.beliefs[("Y", "Z")].status["Blocked"] == pytest.approx(0.526882, abs=1e-6)
    assert res.simulation.unhandled == {"I1": "unreachable"}
    assert "W502" in codes(res, "warning")
    assert "E501" not in codes(res)


def test_T2_unreachable_injected(tmp_path):
    _, _, res = injected(_t2_fixture(tmp_path), status={("A", "Z"): P_B_RAIN, ("Y", "Z"): P_B_RAIN})
    assert res.unhandled == {"I1": "unreachable"}
    assert [a.incident_id for a in res.assignments] == ["I2"]


# ------------------------------------------------------------------ T3

def _t3_fixture(tmp_path):
    # A->B 10 s, B->C 15 s, A->C 30 s; time_required 10; common deadline 30
    return write_scenario(
        tmp_path / "t3", nodes=[node("A", 0, 0), node("B", 100, 0), node("C", 200, 0)],
        roads=two_way("A", "B", 100) + two_way("B", "C", 150) + two_way("A", "C", 300),
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I2", "C", "Critical", 30, "X", 0, 10),
                   incident("I1", "B", "Critical", 30, "X", 0, 10)])


def test_T3_sequential_same_deadline_injected(tmp_path):
    _, net, res = injected(_t3_fixture(tmp_path))
    first, second = res.assignments
    assert (first.responder_id, first.incident_id, first.time, first.path) == ("R1", "I1", 0.0, ("A", "B"))
    assert second.incident_id == "I2" and second.responder_id == "R1"
    assert second.time == pytest.approx(net.path_cost(first.path) + 10)    # finish of I1
    assert second.path[0] == "B"


def test_T3_sequential_same_deadline_pipeline(tmp_path):
    res = pipeline(_t3_fixture(tmp_path), tmp_path)
    plan = plan_of(res)
    assert [(e["responder_id"], e["incident_id"]) for e in plan] == [("R1", "I1"), ("R1", "I2")]
    assert plan[0]["time"] == 0
    assert "E404" not in codes(res)
    i2 = next(p for p in res.statistics.per_incident if p.id == "I2")
    assert (i2.status == "late") == (i2.arrive > 30 + 1e-9)
    entry_i1 = next(p for p in res.statistics.per_incident if p.id == "I1")
    assert plan[1]["time"] == pytest.approx(entry_i1.arrive + 10)


# ------------------------------------------------------------------ T4

def test_T4_busy_responder_s1(tmp_path):
    res = pipeline(S1, tmp_path)
    plan = plan_of(res)
    r4 = [e for e in plan if e["responder_id"] == "R4"]
    if r4:
        first = min(r4, key=lambda e: e["time"])
        assert first["time"] >= 10 and first["path"][0] == "N3"
        mutated = [dict(e) for e in plan]
        mutated[plan.index(first)]["time"] = 5
    else:
        # R4 unused: give it one of the incidents it is capable of, departing at 5 from N3
        s = res.scenario
        caps = s.responders["R4"].capabilities
        k = next(k for k, e in enumerate(plan) if s.incident(e["incident_id"]).required_capability in caps)
        route = dijkstra_route(res.network, "N3", s.incident(plan[k]["incident_id"]).location)
        mutated = [dict(e) for e in plan]
        mutated[k] = {"responder_id": "R4", "incident_id": plan[k]["incident_id"],
                      "path": list(route.path), "time": 5}
    _, _, issues = validate_plan(res.scenario, res.network, Config(), mutated)
    assert "E403" in {i.code for i in issues if i.severity == "error"}


# ------------------------------------------------------------------ T5

def _t5_fixture(tmp_path):
    # all-Open travel A->B = 100 s > deadline 50
    return write_scenario(
        tmp_path / "t5", nodes=[node("A", 0, 0), node("B", 1000, 0)], roads=two_way("A", "B", 1000),
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "B", "Critical", 50, "X", 0, 5), incident("I2", "A", "Low", 500, "X", 0, 5)])


def test_T5_impossible_deadline_injected(tmp_path):
    _, net, res = injected(_t5_fixture(tmp_path))
    assert net.path_cost(["A", "B"]) > 50
    assert res.unhandled == {}
    assert [a.incident_id for a in res.assignments][0] == "I1"


def test_T5_impossible_deadline_pipeline(tmp_path):
    res = pipeline(_t5_fixture(tmp_path), tmp_path)
    st = res.statistics
    i1 = next(p for p in st.per_incident if p.id == "I1")
    assert i1.status == "late" and st.n_handled == 2 and st.n_late >= 1
    assert "W401" in codes(res, "warning")
    responses = [p.response for p in st.per_incident if p.response is not None]
    assert st.avg_response_time == pytest.approx(sum(responses) / 2)       # late one included
    assert st.pct_deadlines_met == pytest.approx(100.0 * st.n_met / 2)
    assert st.n_met <= 1                                                    # I1 counted missed


# ------------------------------------------------------------------ T6

def test_T6_direction_dependent_reports(tmp_path):
    res = pipeline(S1, tmp_path)
    b12, b21 = res.network.beliefs[("N1", "N2")], res.network.beliefs[("N2", "N1")]
    assert b12.removed and b12.status["Blocked"] == pytest.approx(0.526882, abs=1e-6)
    assert not b21.removed and b21.status["Congested"] == pytest.approx(0.993169, abs=1e-6)
    assert b21.e_mult == pytest.approx(1.497042, abs=1e-6)
    for e in plan_of(res):
        assert ("N1", "N2") not in list(zip(e["path"], e["path"][1:]))


# ------------------------------------------------------------------ T7

@pytest.mark.parametrize("d,reports,observations", [(SCENARIO_DIRS[0], 18, 140), (SCENARIO_DIRS[1], 42, 15)],
                         ids=["S1", "S2"])
def test_T7_blank_lines_in_given_files(d, reports, observations):
    raw = (d / "road_reports.csv").read_text() + (d / "observed_traffic.csv").read_text()
    assert "\n\n" in raw                                                    # the files contain blank lines
    s = load_scenario(d)
    assert sum(len(v) for v in s.reports.values()) == reports
    assert sum(len(v) for v in s.traffic_obs.values()) == observations


def test_T7_trailing_and_whitespace_lines(tmp_path):
    d = write_scenario(tmp_path / "t7", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
                       responders=[responder("R1", "A", ["X"])], incidents=[incident("I1", "B", "High", 9, "X")])
    for f in ("incidents.csv", "responders.csv"):
        (d / f).write_text((d / f).read_text() + "   \n\n \t \n\n")
    (d / "road_reports.csv").write_text("from,to,weather,source,reported_status\n\n  \nA,B,Rain,Police,Open\n\n\n")
    (d / "observed_traffic.csv").write_text("observation_nr,from,to,traffic_observation\n1,A,B,Low\n   \n"
                                            "2,A,B,High\n\n")
    s = load_scenario(d)
    assert len(s.incidents) == 1 and len(s.responders) == 1
    assert len(s.reports[("A", "B")]) == 1 and s.traffic_obs[("A", "B")] == ("Low", "High")
    assert s.warnings == ()


# ------------------------------------------------------------------ T8

def _t8_fixture(tmp_path):
    return write_scenario(
        tmp_path / "t8", nodes=[node("A", 0, 0), node("B", 100, 0)], roads=two_way("A", "B", 100),
        responders=[responder("R1", "A", ["X"], busy_for=3.5)],
        incidents=[incident("I1", "B", "High", 70.25, "X", 12.5, 7.75)])


def test_T8_fractional_seconds_injected(tmp_path):
    from erp.output import plan_to_json
    _, _, res = injected(_t8_fixture(tmp_path))
    (a,) = res.assignments
    assert a.time == 12.5
    data = json.loads(plan_to_json(res.assignments))
    assert data[0]["time"] == 12.5 and isinstance(data[0]["time"], float)


def test_T8_fractional_seconds_pipeline(tmp_path):
    res = pipeline(_t8_fixture(tmp_path), tmp_path)
    plan = plan_of(res)
    assert plan[0]["time"] == 12.5 and isinstance(plan[0]["time"], float)
    p = res.statistics.per_incident[0]
    assert p.deadline == 70.25 and p.depart == 12.5
    assert p.response == pytest.approx(p.arrive - 12.5, abs=1e-12)
    assert (p.status == "met") == (p.arrive <= 70.25 + 1e-9)


# ------------------------------------------------------------------ T9

def _t9_fixture(tmp_path, with_r2):
    resp = [responder("R1", "A", ["X"])] + ([responder("R2", "A", ["X"])] if with_r2 else [])
    return write_scenario(
        tmp_path / f"t9{with_r2}", nodes=[node("A", 0, 0), node("B", 10, 0), node("F", 900, 0)],
        roads=two_way("A", "F", 900) + two_way("A", "B", 10),
        responders=resp,
        incidents=[incident("I1", "F", "Critical", 500, "X", 0, 10),   # R1 busy until 90 + 10 = 100
                   incident("I2", "B", "High", 500, "X", 5, 5)])


def _check_t9(assignments, with_r2, r1_free):
    by_inc = {a["incident_id"]: a for a in assignments}
    assert by_inc["I1"]["responder_id"] == "R1" and by_inc["I1"]["time"] == 0
    if with_r2:
        assert by_inc["I2"]["responder_id"] == "R2" and by_inc["I2"]["time"] == 5
    else:
        assert by_inc["I2"]["responder_id"] == "R1" and by_inc["I2"]["time"] >= r1_free - 1e-9
    assert not [a for a in assignments if a["responder_id"] == "R1" and 0 < a["time"] < r1_free]


@pytest.mark.parametrize("with_r2", [True, False], ids=["a-R2-free", "b-no-R2"])
def test_T9_no_interruption_injected(tmp_path, with_r2):
    _, net, res = injected(_t9_fixture(tmp_path, with_r2))
    _check_t9([a.to_json() for a in res.assignments], with_r2, net.path_cost(["A", "F"]) + 10)


@pytest.mark.parametrize("with_r2", [True, False], ids=["a-R2-free", "b-no-R2"])
def test_T9_no_interruption_pipeline(tmp_path, with_r2):
    res = pipeline(_t9_fixture(tmp_path, with_r2), tmp_path)
    plan = plan_of(res)
    i1 = next(p for p in res.statistics.per_incident if p.id == "I1")
    _check_t9(plan, with_r2, i1.arrive + 10)


# ------------------------------------------------------------------ T10

def _t10_fixture(tmp_path, with_r2):
    reps = [report("X", dst, "Storm", src, "Blocked") for dst in ("Y", "W") for src in ("Citizen", "Police", "Sensor")]
    resp = [responder("R1", "X", ["Cap"])] + ([responder("R2", "W", ["Cap"])] if with_r2 else [])
    return write_scenario(
        tmp_path / f"t10{with_r2}", nodes=[node("X", 0, 0), node("Y", 100, 0), node("W", 0, 100)],
        roads=two_way("X", "Y", 100) + two_way("X", "W", 100) + two_way("Y", "W", 150),
        responders=resp,
        incidents=[incident("I1", "Y", "Critical", 500, "Cap"), incident("I2", "X", "High", 500, "Cap")],
        reports=reps)


def _check_t10(assignments, unhandled, with_r2):
    for a in assignments:
        if a["responder_id"] == "R1":
            assert a["path"] == ["X"]                       # never dispatched to another node
    by_inc = {a["incident_id"]: a for a in assignments}
    assert by_inc["I2"]["path"][-1] == "X"                 # OQ-5: incident at X itself is served
    if with_r2:
        assert by_inc["I1"]["responder_id"] == "R2" and unhandled == {}
    else:
        assert "I1" not in by_inc and unhandled == {"I1": "unreachable"}


@pytest.mark.parametrize("with_r2", [True, False], ids=["with-R2", "without-R2"])
def test_T10_isolated_start_injected(tmp_path, with_r2):
    _, _, res = injected(_t10_fixture(tmp_path, with_r2),
                         status={("X", "Y"): BLOCKED, ("X", "W"): BLOCKED})
    _check_t10([a.to_json() for a in res.assignments], dict(res.unhandled), with_r2)


@pytest.mark.parametrize("with_r2", [True, False], ids=["with-R2", "without-R2"])
def test_T10_isolated_start_pipeline(tmp_path, with_r2):
    res = pipeline(_t10_fixture(tmp_path, with_r2), tmp_path)
    assert res.network.neighbours("X") == []
    _check_t10(plan_of(res), dict(res.simulation.unhandled), with_r2)
    assert res.exit_code == 0
