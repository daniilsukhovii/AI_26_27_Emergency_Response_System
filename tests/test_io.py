"""Scenario loading and input checks (SPEC §1.2, §1.3)."""
from __future__ import annotations

import json

import pytest

from erp.io_load import InputError, load_scenario, read_csv_rows
from tests.fixtures import (
    SCENARIO_DIRS, copy_scenario, incident, node, observation, report, responder, two_way,
    write_scenario,
)


def _base(tmp_path, **over):
    kw = dict(
        nodes=[node("A", 0, 0), node("B", 10, 0)],
        roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["Cap"])],
        incidents=[incident("I1", "B", "High", 100, "Cap")],
    )
    kw.update(over)
    return write_scenario(tmp_path / "sc", **kw)


@pytest.mark.parametrize("d", SCENARIO_DIRS, ids=lambda d: d.name)
def test_given_scenarios_load_without_warnings(d):
    s = load_scenario(d)
    assert s.warnings == ()
    assert s.name == d.name


def test_s1_structure():
    s = load_scenario(SCENARIO_DIRS[0])
    assert list(s.responders) == ["R1", "R2", "R3", "R4"]
    r4 = s.responders["R4"]
    assert not r4.available and r4.time_until_available == 10.0 and r4.free_at_start == 10.0
    assert s.responders["R1"].free_at_start == 0.0
    assert s.responders["R1"].capabilities == frozenset({"Fire suppression", "Rescue"})
    # incidents sorted by (timestamp, natural id)
    assert [i.id for i in s.incidents] == ["I1", "I2", "I3", "I4", "I5", "I6", "I7"]
    assert [r.source for r in s.reports[("N1", "N2")]] == ["Citizen", "Police", "Sensor"]
    assert s.traffic_obs[("N2", "N1")][:3] == ("High", "Low", "Medium")
    assert s.cpts.report["Sensor"]["Congested"]["Blocked"] == pytest.approx(0.10)
    assert s.hmm.transition["High"]["Medium"] == pytest.approx(0.20)


def test_incidents_sorted_naturally(tmp_path):
    d = _base(tmp_path, incidents=[incident("I10", "B", "High", 100, "Cap", 0),
                                   incident("I2", "B", "High", 100, "Cap", 0),
                                   incident("I1", "B", "High", 100, "Cap", 5)])
    assert [i.id for i in load_scenario(d).incidents] == ["I2", "I10", "I1"]


def test_floats_not_truncated(tmp_path):
    d = _base(tmp_path, incidents=[incident("I1", "B", "High", 70.25, "Cap", 12.5, 7.75)],
              responders=[responder("R1", "A", ["Cap"], busy_for=3.5)])
    s = load_scenario(d)
    i = s.incidents[0]
    assert (i.timestamp, i.deadline, i.time_required) == (12.5, 70.25, 7.75)
    assert s.responders["R1"].free_at_start == 3.5


def test_read_csv_rows_skips_blank_and_whitespace_lines(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a, b\n1, 2\n\n   \n3,4\n\n\n")
    assert read_csv_rows(p, ["a", "b"]) == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def _code(exc_info) -> str:
    return exc_info.value.code


def test_I001_missing_file(tmp_path):
    d = _base(tmp_path)
    (d / "road_reports.csv").unlink()
    with pytest.raises(InputError) as e:
        load_scenario(d)
    assert _code(e) == "I001"


def test_I001_missing_column(tmp_path):
    d = _base(tmp_path)
    (d / "incidents.csv").write_text("incident_id,location\nI1,B\n")
    with pytest.raises(InputError) as e:
        load_scenario(d)
    assert _code(e) == "I001"


@pytest.mark.parametrize("what", ["node", "responder", "incident", "road"])
def test_I002_duplicates(tmp_path, what):
    over = {
        "node": dict(nodes=[node("A", 0, 0), node("B", 10, 0), node("A", 1, 1)]),
        "responder": dict(responders=[responder("R1", "A", ["Cap"]), responder("R1", "B", ["Cap"])]),
        "incident": dict(incidents=[incident("I1", "B", "High", 1, "Cap"),
                                    incident("I1", "A", "High", 1, "Cap")]),
        "road": dict(roads=two_way("A", "B", 10) + two_way("A", "B", 12)[:1]),
    }[what]
    with pytest.raises(InputError) as e:
        load_scenario(_base(tmp_path, **over))
    assert _code(e) == "I002"


@pytest.mark.parametrize("over", [
    dict(roads=two_way("A", "Z", 10)),
    dict(responders=[responder("R1", "Z", ["Cap"])]),
    dict(incidents=[incident("I1", "Z", "High", 1, "Cap")]),
    dict(reports=[report("A", "Z", "Rain", "Citizen", "Open")]),
    dict(observations=[observation(1, "Z", "A", "Low")]),
], ids=["road", "responder", "incident", "report", "observation"])
def test_I003_unknown_node(tmp_path, over):
    with pytest.raises(InputError) as e:
        load_scenario(_base(tmp_path, **over))
    assert _code(e) == "I003"


@pytest.mark.parametrize("over", [
    dict(incidents=[incident("I1", "B", "Urgent", 1, "Cap")]),
    dict(responders=[{**responder("R1", "A", ["Cap"]), "availability": "Maybe"}]),
    dict(reports=[report("A", "B", "Snow", "Citizen", "Open")]),
    dict(reports=[report("A", "B", "Rain", "Drone", "Open")]),
    dict(reports=[report("A", "B", "Rain", "Citizen", "Flooded")]),
    dict(observations=[observation(1, "A", "B", "Extreme")]),
], ids=["priority", "availability", "weather", "source", "status", "level"])
def test_I004_unknown_label(tmp_path, over):
    with pytest.raises(InputError) as e:
        load_scenario(_base(tmp_path, **over))
    assert _code(e) == "I004"


@pytest.mark.parametrize("file,mutate", [
    ("road_probabilities.json", lambda d: d["weather_prior"].update(Clear=0.6)),
    ("road_probabilities.json", lambda d: d["police_report"]["Open"].update(Open=-0.1, Congested=1.08)),
    ("traffic_probabilities.json", lambda d: d["transition"]["Low"].update(Low=0.5)),
    ("traffic_probabilities.json", lambda d: d["emission"]["High"].pop("Low")),
])
def test_I005_bad_probability_row(tmp_path, file, mutate):
    d = _base(tmp_path)
    data = json.loads((d / file).read_text())
    mutate(data)
    (d / file).write_text(json.dumps(data))
    with pytest.raises(InputError) as e:
        load_scenario(d)
    assert _code(e) == "I005"


@pytest.mark.parametrize("over", [
    dict(roads=two_way("A", "B", 0)),
    dict(roads=two_way("A", "B", 10, speed=-1)),
    dict(incidents=[incident("I1", "B", "High", 1, "Cap", time_required=-1)]),
    dict(incidents=[incident("I1", "B", "High", 1, "Cap", timestamp=-1)]),
    dict(responders=[responder("R1", "A", ["Cap"], busy_for=-5)]),
], ids=["distance", "speed", "time_required", "timestamp", "time_until_available"])
def test_I006_non_positive_values(tmp_path, over):
    with pytest.raises(InputError) as e:
        load_scenario(_base(tmp_path, **over))
    assert _code(e) == "I006"


def test_I007_mixed_weather(tmp_path):
    d = _base(tmp_path, reports=[report("A", "B", "Rain", "Citizen", "Open"),
                                 report("A", "B", "Storm", "Police", "Open")])
    with pytest.raises(InputError) as e:
        load_scenario(d)
    assert _code(e) == "I007"


def test_I008_observation_gap_warning_and_order(tmp_path):
    d = _base(tmp_path, observations=[observation(3, "A", "B", "High"),
                                      observation(1, "A", "B", "Low")])
    s = load_scenario(d)
    assert s.traffic_obs[("A", "B")] == ("Low", "High")
    assert any(w.startswith("I008") for w in s.warnings)


def test_I009_deadline_before_timestamp(tmp_path):
    s = load_scenario(_base(tmp_path, incidents=[incident("I1", "B", "High", 5, "Cap", 10)]))
    assert any(w.startswith("I009") for w in s.warnings)
    assert len(s.incidents) == 1           # still planned [D 4]


def test_I010_euclid_longer_than_road(tmp_path):
    s = load_scenario(_base(tmp_path, roads=two_way("A", "B", 5)))   # nodes are 10 m apart
    assert sum(w.startswith("I010") for w in s.warnings) == 2


@pytest.mark.parametrize("resp", [
    {**responder("R1", "A", ["Cap"]), "time_until_available": 4},
    responder("R1", "A", ["Cap"], busy_for=0),
], ids=["available-with-time", "busy-zero"])
def test_I011_availability_inconsistent(tmp_path, resp):
    s = load_scenario(_base(tmp_path, responders=[resp]))
    assert any(w.startswith("I011") for w in s.warnings)
    if resp["availability"] == "Available":
        assert s.responders["R1"].free_at_start == 0.0


def test_I012_unknown_road_ignored(tmp_path):
    d = _base(tmp_path, nodes=[node("A", 0, 0), node("B", 10, 0), node("C", 20, 0)],
              reports=[report("A", "C", "Rain", "Citizen", "Open")],
              observations=[observation(1, "C", "A", "Low")])
    s = load_scenario(d)
    assert ("A", "C") not in s.reports and ("C", "A") not in s.traffic_obs
    assert sum(w.startswith("I012") for w in s.warnings) == 2


def test_given_scenarios_copied_load_identically(tmp_path):
    d = copy_scenario(SCENARIO_DIRS[1], tmp_path / "S2")
    a, b = load_scenario(SCENARIO_DIRS[1]), load_scenario(d)
    assert a.roads == b.roads and a.incidents == b.incidents and a.reports == b.reports
