"""Validator (SPEC §8.8, checks §7).

Valid plans come from run.run_scenario with Config(validate=False), used as a black box.
Each mutation test applies ONE mutation and asserts that the expected code is reported and
that no unrelated error code appears. Mutations of a single entry are applied, where it
matters, to the *last* job of its responder, so that the change cannot legitimately affect
later jobs of the same responder (E301 / E404 of following entries).
"""
from __future__ import annotations

import copy
import dataclasses
import json
import math
import shutil

import pytest

import run
from erp.config import Config
from erp.io_load import load_scenario
from erp.roadnet import build_network
from erp.validate import (
    PlanLoadError, dijkstra_all, load_plan_json, reconstruct_timeline, validate_plan,
)
from tests.fixtures import (
    SCENARIO_DIRS, incident, node, report, responder, road, two_way, write_scenario,
)
from tests.reference import dijkstra_costs, dijkstra_route

S1 = SCENARIO_DIRS[0]


# ------------------------------------------------------------------ helpers

def make_run(d, out, **cfg):
    """Planner run without validation (black box); returns (RunResult, raw plan, config)."""
    c = Config(validate=False, **cfg)
    res = run.run_scenario(d, out, c)
    return res, json.loads(res.plan_path.read_text(encoding="utf-8")), c


def check(res, raw, code, cfg=None, entry="any", scenario=None):
    """Validate ``raw``; assert ``code`` is reported (at ``entry`` if given) and no error code
    other than ``code`` is reported. Returns the issues."""
    s = scenario or res.scenario
    _, _, issues = validate_plan(s, res.network, cfg or Config(), raw)
    hits = [i for i in issues if i.code == code]
    assert hits, f"{code} not reported; got {[(i.code, i.entry, i.message) for i in issues]}"
    if entry != "any":
        assert any(i.entry == entry for i in hits), [(i.code, i.entry) for i in hits]
    errors = {i.code for i in issues if i.severity == "error"}
    allowed = {code} if code.startswith("E") else set()
    assert errors <= allowed, f"unrelated errors {errors - allowed}: " \
                              f"{[(i.code, i.entry, i.message) for i in issues]}"
    assert all(i.severity == ("error" if i.code.startswith("E") else "warning") for i in issues)
    return issues


def last_jobs(plan):
    """Indices of each responder's last entry (by time, ties: plan order)."""
    last: dict[str, int] = {}
    for k, e in sorted(enumerate(plan), key=lambda ke: (ke[1]["time"], ke[0])):
        last[e["responder_id"]] = k
    return sorted(last.values())


def mutated(plan, k, **changes):
    p = copy.deepcopy(plan)
    p[k].update(changes)
    return p


@pytest.fixture(scope="module")
def s1(tmp_path_factory):
    return make_run(S1, tmp_path_factory.mktemp("s1"))


# ------------------------------------------------------------------ valid plans

VALID_GRID = [(d, a, extra) for d in SCENARIO_DIRS for a in ("on-site", "return")
              for extra in ({}, {"use_bayes": False}, {"use_hmm": False}, {"planner": "greedy"})]


@pytest.mark.parametrize("d,after_job,extra", VALID_GRID,
                         ids=[f"{d.name}-{a}-{'-'.join(f'{k}={v}' for k, v in x.items()) or 'default'}"
                              for d, a, x in VALID_GRID])
def test_valid_plan_has_zero_errors(tmp_path, d, after_job, extra):
    res, raw, cfg = make_run(d, tmp_path, after_job=after_job, **extra)
    accepted, timeline, issues = validate_plan(res.scenario, res.network, cfg,
                                               load_plan_json(res.plan_path))
    assert [i for i in issues if i.severity == "error"] == []
    assert len(accepted) == len(raw) == sum(len(v) for v in timeline.values())
    assert {e.assignment.incident_id for v in timeline.values() for e in v} == \
        {e["incident_id"] for e in raw}


def test_valid_plan_timeline_matches_planner(s1):
    """Validator arrivals = time + path cost; departures = plan times; jobs never overlap."""
    res, raw, cfg = s1
    _, timeline, _ = validate_plan(res.scenario, res.network, cfg, raw)
    for rid, entries in timeline.items():
        r = res.scenario.responders[rid]
        prev_free = r.free_at_start
        for e in entries:
            a = e.assignment
            inc = res.scenario.incident(a.incident_id)
            assert e.departure == a.time >= prev_free - 1e-9
            assert e.arrival == pytest.approx(a.time + res.network.path_cost(a.path), abs=1e-9)
            assert e.finish == pytest.approx(e.arrival + inc.time_required, abs=1e-9)
            assert e.response_time == pytest.approx(e.arrival - inc.timestamp, abs=1e-9)
            assert e.deadline_met == (e.arrival <= inc.deadline + 1e-9)
            assert e.position_after == inc.location                       # on-site
            prev_free = e.free_at


# ------------------------------------------------------------------ dijkstra_all

@pytest.mark.parametrize("d", SCENARIO_DIRS, ids=lambda d: d.name)
def test_dijkstra_all_matches_reference(d):
    s = load_scenario(d)
    net = build_network(s, Config())
    for src in s.nodes:
        mine, ref = dijkstra_all(net, src), dijkstra_costs(net, src)
        assert set(mine) == set(s.nodes) and mine[src] == 0.0
        for v in s.nodes:
            if v in ref:
                assert mine[v] == pytest.approx(ref[v], abs=1e-9)
            else:
                assert mine[v] == math.inf


def test_dijkstra_all_unknown_node(s1):
    with pytest.raises(ValueError):
        dijkstra_all(s1[0].network, "N99")


# ------------------------------------------------------------------ E1xx: structure

def test_E101_top_level_object(s1, tmp_path):
    f = tmp_path / "plan.json"
    f.write_text("{}")
    issues = check(s1[0], load_plan_json(f), "E101", entry=None)
    assert [i.code for i in issues] == ["E101"]                         # nothing else (no E501)


@pytest.mark.parametrize("text", ['[{"responder_id": "R1", ', "", "not json", "[" * 100_000],
                         ids=["truncated", "empty", "garbage", "deep-nesting"])
def test_E101_malformed_file_does_not_crash(s1, tmp_path, text):
    f = tmp_path / "plan.json"
    f.write_text(text)
    raw = load_plan_json(f)
    assert isinstance(raw, PlanLoadError)
    issues = check(s1[0], raw, "E101", entry=None)
    assert [i.code for i in issues] == ["E101"]


def test_E101_missing_file(s1, tmp_path):
    raw = load_plan_json(tmp_path / "nope.json")
    assert isinstance(raw, PlanLoadError)
    check(s1[0], raw, "E101")


def test_load_plan_json_roundtrip(s1):
    res, raw, _ = s1
    assert load_plan_json(res.plan_path) == raw


def test_E102_entry_not_object(s1):
    res, raw, _ = s1
    check(res, raw + ["x"], "E102", entry=len(raw))


def test_E103_missing_key(s1):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    p = copy.deepcopy(raw)
    del p[k]["path"]
    issues = check(res, p, "E103", entry=k)
    assert "E501" not in {i.code for i in issues}        # the incident is still named in the plan


@pytest.mark.parametrize("field,value", [("time", "0"), ("time", True), ("time", None),
                                         ("responder_id", 1), ("incident_id", ["I1"]),
                                         ("path", "N1"), ("path", ["N1", 2])],
                         ids=["time-str", "time-bool", "time-null", "rid-int", "iid-list",
                              "path-str", "path-int-node"])
def test_E104_wrong_type(s1, field, value):
    res, raw, _ = s1
    if field == "incident_id":
        # in place, the incident would no longer be named in the plan (a real E501): append a copy
        check(res, raw + [dict(raw[0], incident_id=value)], "E104", entry=len(raw))
        return
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, **{field: value}), "E104", entry=k)


@pytest.mark.parametrize("value", [-1, -1e-3, math.nan, math.inf, -math.inf, 10 ** 400],
                         ids=["-1", "-0.001", "nan", "inf", "-inf", "huge-int"])
def test_E105_bad_time(s1, value):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, time=value), "E105", entry=k)


def test_E105_nan_literal_in_file(s1, tmp_path):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    f = tmp_path / "plan.json"
    f.write_text(json.dumps(mutated(raw, k, time=math.nan)))          # writes the NaN literal
    assert "NaN" in f.read_text()
    check(res, load_plan_json(f), "E105", entry=k)


def test_E106_empty_path(s1):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, path=[]), "E106", entry=k)


# ------------------------------------------------------------------ E2xx: references

def test_E201_unknown_responder(s1):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, responder_id="R99"), "E201", entry=k)


def test_E202_unknown_incident(s1):
    res, raw, _ = s1
    extra = dict(raw[last_jobs(raw)[0]], incident_id="I99")
    check(res, raw + [extra], "E202", entry=len(raw))


def test_E203_unknown_node(s1):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, path=raw[k]["path"][:-1] + ["N99"]), "E203", entry=k)


def test_E204_duplicate_incident(s1):
    res, raw, _ = s1
    dup = raw + [copy.deepcopy(raw[0])]
    check(res, dup, "E204", entry=len(raw))
    acc, tl, _ = validate_plan(res.scenario, res.network, Config(), dup)
    assert len(acc) == len(raw)                                          # duplicate left out
    assert sum(len(v) for v in tl.values()) == len(raw)


# ------------------------------------------------------------------ E3xx: paths

def test_E301_path_starts_elsewhere(s1):
    res, raw, _ = s1
    net = res.network
    for k in last_jobs(raw):
        p0 = raw[k]["path"][0]
        pred = [u for u in res.scenario.nodes if net.is_usable(u, p0)]
        if pred:
            check(res, mutated(raw, k, path=[pred[0]] + raw[k]["path"]), "E301", entry=k)
            return
    pytest.fail("no usable predecessor found")


def test_E301_first_job_not_at_start(s1):
    """[T 4]: the first job must start at start_location; R4 (Busy at N3) claims to start at
    the incident node itself (cost 0, so later jobs of R4 cannot be delayed)."""
    res, raw, _ = s1
    k = min((k for k, e in enumerate(raw) if e["responder_id"] == "R4"), key=lambda k: raw[k]["time"])
    assert raw[k]["path"][0] == "N3" and raw[k]["path"][-1] != "N3"
    check(res, mutated(raw, k, path=[raw[k]["path"][-1]]), "E301", entry=k)


def test_E302_path_ends_elsewhere(s1):
    res, raw, _ = s1
    net = res.network
    for k in last_jobs(raw):
        succ = net.neighbours(raw[k]["path"][-1])
        if succ:
            check(res, mutated(raw, k, path=raw[k]["path"] + [succ[0][0]]), "E302", entry=k)
            return
    pytest.fail("no usable successor found")


def test_E303_skip_a_node(s1):
    res, raw, _ = s1
    for k in last_jobs(raw):
        p = raw[k]["path"]
        for i in range(1, len(p) - 1):
            if (p[i - 1], p[i + 1]) not in res.scenario.roads:
                check(res, mutated(raw, k, path=p[:i] + p[i + 1:]), "E303", entry=k)
                return
    pytest.fail("no path with a skippable node")


def test_E304_removed_road_N1_N2(s1):
    """R1's first job I2 (N1 -> N2) taken over the removed direct road. R1 has a later job,
    which must not get a cascading E404 / E301."""
    res, raw, _ = s1
    assert res.network.beliefs[("N1", "N2")].removed
    k = next(k for k, e in enumerate(raw) if e["path"][0] == "N1" and e["path"][-1] == "N2")
    assert sum(e["responder_id"] == raw[k]["responder_id"] for e in raw) >= 2
    check(res, mutated(raw, k, path=["N1", "N2"]), "E304", entry=k)


# ------------------------------------------------------------------ E4xx: feasibility

def _reassign(res, raw, k, new_rid, cfg=None):
    """Move entry k to responder ``new_rid``, appended after its last job (path from its final
    position, departure when it is free) — only the capability differs from a valid plan."""
    _, tl, _ = validate_plan(res.scenario, res.network, cfg or Config(), raw)
    r = res.scenario.responders[new_rid]
    entries = tl.get(new_rid, [])
    pos = entries[-1].position_after if entries else r.start_location
    free = entries[-1].free_at if entries else r.free_at_start
    inc = res.scenario.incident(raw[k]["incident_id"])
    route = dijkstra_route(res.network, pos, inc.location)
    assert route is not None
    return mutated(raw, k, responder_id=new_rid, path=list(route.path),
                   time=max(free, inc.timestamp, raw[k]["time"]))


def test_E401_responder_without_capability(s1):
    res, raw, _ = s1
    s = res.scenario
    for k in last_jobs(raw):
        cap = s.incident(raw[k]["incident_id"]).required_capability
        for rid, r in s.responders.items():
            if cap not in r.capabilities:
                try:
                    p = _reassign(res, raw, k, rid)
                except AssertionError:
                    continue
                check(res, p, "E401", entry=k)
                return
    pytest.fail("no reassignment candidate")


def test_E402_departure_before_timestamp(tmp_path):
    d = write_scenario(tmp_path / "e402", nodes=[node("A", 0, 0), node("B", 100, 0)],
                       roads=two_way("A", "B", 100), responders=[responder("R1", "A", ["X"])],
                       incidents=[incident("I1", "B", "High", 500, "X", 50, 5)])
    res, raw, _ = make_run(d, tmp_path / "out")
    assert raw[0]["time"] == 50
    _, _, ok = validate_plan(res.scenario, res.network, Config(), raw)
    assert [i for i in ok if i.severity == "error"] == []
    check(res, mutated(raw, 0, time=10), "E402", entry=0)


def test_E402_is_exact_no_eps_window(tmp_path):
    """AUD-3: E402 compares exactly (SPEC §0): a departure 5e-10 s before the timestamp is
    flagged, although it lies inside the EPS window used for deadlines and free_at."""
    ts = 10.0000000005
    d = write_scenario(tmp_path / "e402x", nodes=[node("A", 0, 0), node("B", 100, 0)],
                       roads=two_way("A", "B", 100), responders=[responder("R1", "A", ["X"])],
                       incidents=[incident("I1", "B", "High", 500, "X", ts, 5)])
    res, raw, _ = make_run(d, tmp_path / "out")
    assert raw[0]["time"] == ts
    check(res, mutated(raw, 0, time=10.0), "E402", entry=0)


def test_E403_busy_responder_R4_at_5(s1):
    res, raw, _ = s1
    k = min((k for k, e in enumerate(raw) if e["responder_id"] == "R4"), key=lambda k: raw[k]["time"])
    assert raw[k]["time"] >= 10 and raw[k]["path"][0] == "N3"          # [T 4]
    issues = check(res, mutated(raw, k, time=5), "E403", entry=k)
    assert [i.code for i in issues if i.severity == "error"] == ["E403"]


def test_E404_overlapping_jobs(s1):
    res, raw, cfg = s1
    _, tl, _ = validate_plan(res.scenario, res.network, cfg, raw)
    for rid, entries in tl.items():
        for prev, nxt in zip(entries, entries[1:]):
            inc = res.scenario.incident(nxt.assignment.incident_id)
            t = max(inc.timestamp, prev.departure + 1e-3)
            if t < prev.free_at - 1e-3:
                k = next(k for k, e in enumerate(raw) if e["incident_id"] == inc.id)
                check(res, mutated(raw, k, time=t), "E404", entry=k)
                return
    pytest.fail("no responder with two jobs that can be made to overlap")


def test_E404_return_mode_counts_return_trip(tmp_path):
    """T-SIM-5 shape: in return mode the second job may only depart after the drive back.
    Departing at the on-site finish time is an overlap (E404) in return mode."""
    d = write_scenario(tmp_path / "ret", nodes=[node("A", 0, 0), node("B", 100, 0)],
                       roads=two_way("A", "B", 100), responders=[responder("R1", "A", ["X"])],
                       incidents=[incident("I1", "B", "Critical", 500, "X", 0, 5),
                                  incident("I2", "A", "High", 500, "X", 0, 5)])
    res, raw, cfg = make_run(d, tmp_path / "out", after_job="return")
    assert [(e["incident_id"], e["path"]) for e in raw] == [("I1", ["A", "B"]), ("I2", ["A"])]
    leg = res.network.path_cost(["A", "B"])
    back = res.network.path_cost(["B", "A"])
    assert raw[1]["time"] == pytest.approx(leg + 5 + back)
    _, tl, ok = validate_plan(res.scenario, res.network, cfg, raw)
    assert [i for i in ok if i.severity == "error"] == []
    assert tl["R1"][0].position_after == "A" and tl["R1"][0].free_at == pytest.approx(leg + 5 + back)
    check(res, mutated(raw, 1, time=leg + 5), "E404", cfg=cfg, entry=1)
    # the same plan judged in on-site mode: the responder would still be at B -> E301
    _, _, onsite = validate_plan(res.scenario, res.network, Config(), raw)
    assert "E301" in {i.code for i in onsite}


def test_return_mode_without_route_back_OQ7(tmp_path):
    """OQ-7: no usable road back -> the responder stays at the incident location."""
    d = write_scenario(tmp_path / "oq7", nodes=[node("A", 0, 0), node("B", 100, 0)],
                       roads=[road("A", "B", 100)], responders=[responder("R1", "A", ["X"])],
                       incidents=[incident("I1", "B", "Critical", 500, "X", 0, 5),
                                  incident("I2", "B", "High", 500, "X", 0, 5)])
    res, raw, cfg = make_run(d, tmp_path / "out", after_job="return")
    _, tl, issues = validate_plan(res.scenario, res.network, cfg, raw)
    assert [i for i in issues if i.severity == "error"] == []
    first = tl["R1"][0]
    assert first.position_after == "B" and first.free_at == pytest.approx(first.finish)


# ------------------------------------------------------------------ E501

def test_E501_reachable_incident_missing(s1):
    res, raw, _ = s1
    k = max(last_jobs(raw), key=lambda k: raw[k]["time"])
    iid = raw[k]["incident_id"]
    issues = check(res, raw[:k] + raw[k + 1:], "E501", entry=None)
    assert any(iid in i.message for i in issues if i.code == "E501")


# ------------------------------------------------------------------ warnings

def test_W101_extra_key(s1):
    res, raw, _ = s1
    check(res, mutated(raw, 0, note="hello"), "W101", entry=0)


def test_W301_path_not_simple(s1):
    res, raw, _ = s1
    net = res.network
    for k in last_jobs(raw):
        p = raw[k]["path"]
        for v, _ in net.neighbours(p[0]):
            if net.is_usable(v, p[0]):
                check(res, mutated(raw, k, path=[p[0], v] + p), "W301", entry=k)
                return
    pytest.fail("no back-and-forth detour available")


def test_W302_longer_valid_path(s1):
    res, raw, _ = s1
    net = res.network
    for k in last_jobs(raw):
        p = raw[k]["path"]
        best = dijkstra_all(net, p[0])[p[-1]]
        for n, _ in net.neighbours(p[0]):
            alt = dijkstra_route(net, n, p[-1])
            if alt is None or p[0] in alt.path:
                continue
            cand = [p[0]] + list(alt.path)
            if net.path_cost(cand) > best + 1e-6:
                issues = check(res, mutated(raw, k, path=cand), "W302", entry=k)
                assert "W301" not in {i.code for i in issues if i.entry == k}   # simple path
                return
    pytest.fail("no longer simple path found")


def test_W401_deadline_missed(s1):
    """Tighten the deadline of an incident the plan meets (scenario mutation, plan unchanged)."""
    res, raw, cfg = s1
    _, tl, base = validate_plan(res.scenario, res.network, cfg, raw)
    met = next(e for v in tl.values() for e in v if e.deadline_met)
    iid = met.assignment.incident_id
    assert not any(i.code == "W401" and iid in i.message for i in base)
    s = res.scenario
    incs = tuple(dataclasses.replace(i, deadline=met.arrival - 1.0) if i.id == iid else i
                 for i in s.incidents)
    k = next(k for k, e in enumerate(raw) if e["incident_id"] == iid)
    check(res, raw, "W401", entry=k, scenario=dataclasses.replace(s, incidents=incs))


def test_W402_departs_later_than_possible(s1):
    res, raw, _ = s1
    k = last_jobs(raw)[0]
    check(res, mutated(raw, k, time=raw[k]["time"] + 100), "W402", entry=k)


def test_W501_no_capable_responder(tmp_path):
    d = shutil.copytree(S1, tmp_path / "S1_T1")
    f = d / "incidents.csv"
    f.write_text(f.read_text().rstrip("\n") + "\nI8,N4,High,300,Pumping operations,0,10\n")
    res, raw, _ = make_run(d, tmp_path / "out")
    issues = check(res, raw, "W501", entry=None)
    assert [i.message.split()[0] for i in issues if i.code == "W501"] == ["I8"]


def test_W502_unreachable(tmp_path):
    reps = []
    for src in ("A", "Y"):                                     # every incoming road of Z
        reps += [report(src, "Z", "Rain", "Citizen", "Blocked"), report(src, "Z", "Rain", "Police", "Blocked"),
                 report(src, "Z", "Rain", "Sensor", "Congested")]
    d = write_scenario(
        tmp_path / "w502", nodes=[node("A", 0, 0), node("Y", 100, 0), node("Z", 100, 100)],
        roads=two_way("A", "Y", 100) + [road("A", "Z", 150), road("Y", "Z", 100), road("Z", "A", 150)],
        responders=[responder("R1", "A", ["X"])],
        incidents=[incident("I1", "Z", "Critical", 100, "X"), incident("I2", "Y", "High", 100, "X")],
        reports=reps)
    res, raw, _ = make_run(d, tmp_path / "out")
    issues = check(res, raw, "W502", entry=None)
    assert "E501" not in {i.code for i in issues}


# ------------------------------------------------------------------ standalone reconstruction

@pytest.mark.parametrize("after_job", ["on-site", "return"])
def test_reconstruct_timeline_standalone_equals_validate(tmp_path, after_job):
    """run.py --no-validate uses reconstruct_timeline alone; it must give the same timeline."""
    res, raw, cfg = make_run(S1, tmp_path, after_job=after_job)
    tl_alone, _ = reconstruct_timeline(res.scenario, res.network, cfg, list(res.simulation.assignments))
    _, tl_val, _ = validate_plan(res.scenario, res.network, cfg, raw)
    strip = lambda tl: {r: [(e.assignment.incident_id, e.departure, e.arrival, e.finish, e.free_at,
                             e.position_after) for e in v] for r, v in tl.items()}
    assert strip(tl_alone).keys() == strip(tl_val).keys()
    for r in tl_alone:
        for a, b in zip(strip(tl_alone)[r], strip(tl_val)[r]):
            assert a[0] == b[0] and a[5] == b[5] and a[1:5] == pytest.approx(b[1:5], abs=1e-9)


def test_no_validate_cli_same_per_incident_block(tmp_path):
    for flag, out in (([], "v"), (["--no-validate"], "nv")):
        assert run.main(["--scenario", str(S1), "--out", str(tmp_path / out)] + flag) == 0
    block = lambda p: (p / "statistics.txt").read_text().split("Per incident:")[1]
    assert block(tmp_path / "v") == block(tmp_path / "nv")
