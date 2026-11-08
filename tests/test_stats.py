"""Statistics on hand-made timelines (SPEC §8.9, formulas §6.8). Infra only."""
from __future__ import annotations

import re

import pytest

from erp.config import Config
from erp.io_load import load_scenario
from erp.model import Assignment, Issue, TimelineEntry
from erp.output import format_statistics
from erp.stats import compute_statistics
from tests.fixtures import BLOCKED, hand_network, incident, node, responder, two_way, write_scenario

# Regex of the assignment example format (Assignment1.pdf §5.2), one per line.
EXAMPLE_FORMAT = [
    r"System statistics:",
    r"",
    r" \* \d+ incidents handled",
    r" \* \d+ responders used",
    r" \* Average response time: (\d+\.\d s|n/a)",
    r" \* Deadlines met: (\d+\.\d%|n/a)",
]


def _scenario(tmp_path, incidents):
    d = write_scenario(
        tmp_path / "st", nodes=[node("A", 0, 0), node("B", 10, 0)], roads=two_way("A", "B", 10),
        responders=[responder("R1", "A", ["X"]), responder("R2", "A", ["X"]), responder("R3", "B", ["X"])],
        incidents=incidents)
    return load_scenario(d)


def entry(s, rid, iid, dep, arr):
    inc = s.incident(iid)
    return TimelineEntry(assignment=Assignment(rid, iid, ("A", "B"), dep), start_node="A",
                         departure=dep, arrival=arr, finish=arr + inc.time_required,
                         free_at=arr + inc.time_required, position_after=inc.location,
                         deadline_met=arr <= inc.deadline + 1e-9, response_time=arr - inc.timestamp)


def timeline(*entries):
    out: dict[str, list[TimelineEntry]] = {}
    for e in entries:
        out.setdefault(e.assignment.responder_id, []).append(e)
    return out


@pytest.fixture
def four(tmp_path):
    return _scenario(tmp_path, [
        incident("I1", "B", "Critical", 50, "X", 0), incident("I2", "B", "High", 50, "X", 0),
        incident("I3", "B", "Critical", 20, "X", 5), incident("I4", "B", "Medium", 99, "Pumping", 0)])


def test_T_ST1_basic(four):
    s = four
    tl = timeline(entry(s, "R1", "I1", 0, 10), entry(s, "R2", "I2", 0, 20), entry(s, "R1", "I3", 15, 35))
    st = compute_statistics(s, tl, {"I4": "no capable responder"})
    assert (st.n_total, st.n_handled, st.n_unhandled, st.n_late) == (4, 3, 1, 1)
    assert st.avg_response_time == pytest.approx(20.0)            # (10 + 20 + 30) / 3
    assert st.pct_deadlines_met == pytest.approx(50.0)            # 100 * 2 / 4
    assert st.responders_used == 2
    assert st.pct_critical_met == pytest.approx(50.0)             # I1 met, I3 late
    assert st.missed_by_class == (1, 0, 1)                        # I3 Critical late, I4 Medium unhandled
    by_id = {p.id: p for p in st.per_incident}
    assert by_id["I3"].status == "late" and by_id["I3"].response == pytest.approx(30.0)
    assert by_id["I4"].status == "unhandled" and by_id["I4"].reason == "no capable responder"


def test_T_ST2_nothing_handled(four):
    st = compute_statistics(four, {}, {i.id: "unreachable" for i in four.incidents})
    assert st.n_handled == 0 and st.responders_used == 0
    assert st.avg_response_time is None
    assert st.pct_deadlines_met == 0.0
    text = format_statistics(st, Config(), hand_network(four, Config()), [])
    assert " * Average response time: n/a" in text.splitlines()
    assert " * Deadlines met: 0.0%" in text.splitlines()


def test_T_ST3_no_critical(tmp_path):
    s = _scenario(tmp_path, [incident("I1", "B", "High", 50, "X"), incident("I2", "B", "Low", 50, "X")])
    st = compute_statistics(s, timeline(entry(s, "R1", "I1", 0, 1)), {"I2": "unreachable"})
    assert st.pct_critical_met is None
    text = format_statistics(st, Config(), hand_network(s, Config()), [])
    assert " * Deadlines met (Critical): n/a" in text.splitlines()


def test_T_ST4_arrival_equal_to_deadline_is_met(tmp_path):
    s = _scenario(tmp_path, [incident("I1", "B", "Critical", 70.25, "X", 12.5)])
    st = compute_statistics(s, timeline(entry(s, "R1", "I1", 12.5, 70.25)), {})
    assert st.n_late == 0 and st.pct_deadlines_met == 100.0 and st.pct_critical_met == 100.0
    assert st.per_incident[0].status == "met"
    assert st.avg_response_time == pytest.approx(57.75)          # unrounded values


def test_T_ST4_just_after_deadline_is_late(tmp_path):
    s = _scenario(tmp_path, [incident("I1", "B", "Critical", 70.25, "X", 12.5)])
    st = compute_statistics(s, timeline(entry(s, "R1", "I1", 12.5, 70.26)), {})
    assert st.n_late == 1 and st.pct_deadlines_met == 0.0


@pytest.mark.parametrize("case", ["handled", "nothing-handled", "empty-scenario"])
def test_T_ST5_example_format(tmp_path, four, case):
    s = four
    if case == "handled":
        st = compute_statistics(s, timeline(entry(s, "R1", "I1", 0, 10), entry(s, "R2", "I2", 0, 20)),
                                {"I3": "unreachable", "I4": "no capable responder"})
    elif case == "nothing-handled":
        st = compute_statistics(s, {}, {})
    else:
        s = _scenario(tmp_path, [])
        st = compute_statistics(s, {}, {})
    text = format_statistics(st, Config(), hand_network(s, Config()), [])
    lines = text.splitlines()
    assert len(lines) >= 6
    for line, pattern in zip(lines[:6], EXAMPLE_FORMAT):
        assert re.fullmatch(pattern, line), (line, pattern)
    assert text.endswith("\n")


def test_statistics_text_details(four):
    s = four
    cfg = Config()
    net = hand_network(s, cfg, {("A", "B"): BLOCKED})
    st = compute_statistics(s, timeline(entry(s, "R1", "I1", 0, 10), entry(s, "R2", "I2", 0, 20),
                                        entry(s, "R1", "I3", 15, 35)), {"I4": "no capable responder"})
    issues = [Issue("W401", "warning", 2, "late"), Issue("W501", "warning", None, "x")]
    text = format_statistics(st, cfg, net, issues)
    lines = text.splitlines()
    assert lines[2:6] == [" * 3 incidents handled", " * 2 responders used",
                          " * Average response time: 20.0 s", " * Deadlines met: 50.0%"]
    assert " * Incidents: 4 total, 3 handled (1 late), 1 unhandled: I4 (no capable responder)" in lines
    assert " * Deadlines met (all incidents, unhandled = missed): 50.0% (2/4)" in lines
    assert " * Deadlines met (Critical): 50.0% (1/2)" in lines
    assert " * Missed deadlines: Critical 1, High 0, Medium/Low 1" in lines
    assert " * Roads removed (P(Blocked) >= tau): A->B (1.000)" in lines
    assert " * Validation: 0 errors, 2 warnings (W401 x1, W501 x1)" in lines
    assert any(line.startswith(" * Configuration: planner=csp, tau=0.5") for line in lines)
    assert "Per incident:" in lines


def test_validation_skipped_line(four):
    st = compute_statistics(four, {}, {})
    text = format_statistics(st, Config(validate=False), hand_network(four, Config()), [])
    assert " * Validation: skipped (--no-validate)" in text.splitlines()


def test_duplicate_incident_in_timeline_rejected(four):
    s = four
    with pytest.raises(ValueError):
        compute_statistics(s, timeline(entry(s, "R1", "I1", 0, 10), entry(s, "R2", "I1", 0, 12)), {})
