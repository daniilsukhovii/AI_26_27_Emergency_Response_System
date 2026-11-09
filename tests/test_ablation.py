"""Ablation switches use_bayes / use_hmm (SPEC §5.1, §5.15, §5.16, T-W8; DECISIONS.md D06).

The baseline rows call the STUDENT Bayes and HMM kernels; the ablation rows must not.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

import erp.bayes
import erp.hmm
import erp.roadnet
from erp.config import Config, config_from_args
from erp.io_load import load_scenario
from erp.output import format_statistics
from erp.roadnet import build_network
from erp.stats import compute_statistics
from tests.fixtures import SCENARIO_DIRS, hand_network, node, responder, incident, two_way, write_scenario

T = 1e-3   # s

MODES = {
    "baseline": dict(),
    "no-bayes": dict(use_bayes=False),
    "no-hmm": dict(use_hmm=False),
    "both": dict(use_bayes=False, use_hmm=False),
}


@pytest.fixture(scope="module")
def scen():
    return {k: load_scenario(d) for k, d in zip((1, 2, 3), SCENARIO_DIRS)}


def _fail(*_a, **_k):
    raise AssertionError("kernel must not be called in this ablation mode")


# ------------------------------------------------------------------ T-W8 (SPEC row)

@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W8_no_bayes(scen, k, monkeypatch):
    monkeypatch.setattr(erp.bayes, "road_status_prior", _fail)
    monkeypatch.setattr(erp.bayes, "road_status_posterior", _fail)
    monkeypatch.setattr(erp.roadnet, "compute_status_beliefs", _fail)
    s = scen[k]
    net = build_network(s, Config(use_bayes=False))
    assert net.removed_roads() == []
    assert len(net.usable_roads()) == len(s.roads)
    for key, b in net.beliefs.items():
        assert dict(b.status) == {"Open": 1.0, "Congested": 0.0, "Blocked": 0.0}
        assert b.e_mult == 1.0 and not b.removed
        assert b.has_reports == bool(s.reports.get(key))


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("unobserved", ["initial", "neutral", "stationary"])
def test_T_W8_no_hmm(scen, k, unobserved, monkeypatch):
    monkeypatch.setattr(erp.hmm, "forward_filter", _fail)
    monkeypatch.setattr(erp.hmm, "stationary_distribution", _fail)
    s = scen[k]
    net = build_network(s, Config(use_hmm=False, unobserved_traffic=unobserved))
    for b in net.beliefs.values():
        assert b.f_traffic == 1.0 and b.traffic is None


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W8_no_hmm_keeps_bayes(scen, k):
    """use_hmm = False changes only f_traffic: status, e_mult and removals are as in the baseline."""
    base = build_network(scen[k], Config())
    abl = build_network(scen[k], Config(use_hmm=False))
    assert abl.removed_roads() == base.removed_roads()
    for key, b in abl.beliefs.items():
        assert b.e_mult == base.beliefs[key].e_mult
        assert dict(b.status) == dict(base.beliefs[key].status)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W8_no_bayes_keeps_hmm(scen, k):
    base = build_network(scen[k], Config())
    abl = build_network(scen[k], Config(use_bayes=False))
    for key, b in abl.beliefs.items():
        assert b.f_traffic == base.beliefs[key].f_traffic


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W8_both(scen, k, monkeypatch):
    for mod, name in [(erp.bayes, "road_status_prior"), (erp.bayes, "road_status_posterior"),
                      (erp.roadnet, "compute_status_beliefs"), (erp.hmm, "forward_filter"),
                      (erp.hmm, "stationary_distribution")]:
        monkeypatch.setattr(mod, name, _fail)
    s = scen[k]
    net = build_network(s, Config(use_bayes=False, use_hmm=False))
    assert net.removed_roads() == []
    for (u, v), r in s.roads.items():
        assert net.weight(u, v) == pytest.approx(r.distance / r.speed, abs=1e-12)


# ------------------------------------------------------------------ S1 N2->N1 in all four modes

@pytest.mark.parametrize("mode,expected", [
    ("baseline", 78.5625),   # d/v · e_mult · f_traffic (T-W1)
    ("no-bayes", 52.4785),   # d/v · f_traffic
    ("no-hmm", 77.3471),     # d/v · e_mult
    ("both", 51.6667),       # d/v
])
def test_T_W8_s1_n2_n1(scen, mode, expected):
    net = build_network(scen[1], Config(**MODES[mode]))
    assert net.weight("N2", "N1") == pytest.approx(expected, abs=T)


@pytest.mark.parametrize("mode", list(MODES))
@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_W6_holds_in_every_mode(scen, k, mode):
    s = scen[k]
    net = build_network(s, Config(**MODES[mode]))
    usable = net.usable_roads()
    assert usable
    for u, v in usable:
        r = s.roads[(u, v)]
        w = net.weight(u, v)
        euclid = math.hypot(s.nodes[u].x - s.nodes[v].x, s.nodes[u].y - s.nodes[v].y)
        assert w >= r.distance / r.speed - 1e-12
        assert w >= euclid / net.v_max - 1e-12


# ------------------------------------------------------------------ Config / CLI

def test_defaults_are_on():
    c = Config()
    assert c.use_bayes is True and c.use_hmm is True


@pytest.mark.parametrize("flags,expected", [
    ([], dict()),
    (["--no-bayes"], dict(use_bayes=False)),
    (["--no-hmm"], dict(use_hmm=False)),
    (["--no-bayes", "--no-hmm"], dict(use_bayes=False, use_hmm=False)),
    (["--no-hmm", "--no-bayes", "--tau", "0.3"], dict(use_bayes=False, use_hmm=False, tau=0.3)),
])
def test_cli_ablation_flags(flags, expected):
    _, _, cfg = config_from_args(["--scenario", "Scenarios/Scenario1", *flags])
    assert cfg == Config(**expected)


@pytest.mark.parametrize("flag", ["--no-bayes=1", "--no-hmm=yes"])
def test_cli_ablation_flags_take_no_value(flag, capsys):
    with pytest.raises(SystemExit) as e:
        config_from_args(["--scenario", "x", flag])
    assert e.value.code == 2


@pytest.mark.parametrize("mode,suffix", [
    ("baseline", "use_bayes=yes, use_hmm=yes"),
    ("no-bayes", "use_bayes=no, use_hmm=yes"),
    ("no-hmm", "use_bayes=yes, use_hmm=no"),
    ("both", "use_bayes=no, use_hmm=no"),
])
def test_describe_shows_switches(mode, suffix):
    d = Config(**MODES[mode]).describe()
    assert d.endswith(", " + suffix)
    assert d.startswith("planner=csp, tau=0.5, ")


def test_statistics_configuration_line(tmp_path):
    d = write_scenario(tmp_path / "s", nodes=[node("A", 0, 0), node("B", 10, 0)],
                       roads=two_way("A", "B", 10), responders=[responder("R1", "A", ["X"])],
                       incidents=[incident("I1", "B", "High", 100, "X")])
    s = load_scenario(d)
    cfg = Config(use_bayes=False, use_hmm=False)
    st = compute_statistics(s, {}, {"I1": "unreachable"})
    lines = format_statistics(st, cfg, hand_network(s, cfg), []).splitlines()
    conf = [ln for ln in lines if ln.startswith(" * Configuration: ")]
    assert conf == [" * Configuration: " + cfg.describe()]
    assert conf[0].endswith("validate=yes, use_bayes=no, use_hmm=no")


# ------------------------------------------------------------------ sensitivity (§5.16)

def test_sensitivity_has_ablation_variations():
    from experiments.sensitivity import VARIATIONS
    changes = [change for _, _, change in VARIATIONS]
    assert {"use_bayes": False} in changes
    assert {"use_hmm": False} in changes
    assert {"use_bayes": False, "use_hmm": False} in changes
    for _, _, change in VARIATIONS:
        replace(Config(), **change)          # every variation is a valid Config


def _sensitivity_eval(tmp_path, d, **change):
    from experiments.sensitivity import baseline_eval, baseline_network
    import run
    cfg = replace(Config(), **change)
    r = run.run_scenario(d, tmp_path / "out", cfg)
    return r, baseline_eval(r, cfg, baseline_network(d))


@pytest.mark.parametrize("d", SCENARIO_DIRS, ids=lambda d: d.name)
def test_sensitivity_baseline_row_same_in_both_column_groups(tmp_path, d):
    from experiments.sensitivity import row
    r, b = _sensitivity_eval(tmp_path, d)
    assert b.error_counts == {} and not b.infeasible
    self_st, base_st = r.statistics, b.statistics
    assert base_st.avg_response_time == pytest.approx(self_st.avg_response_time, abs=1e-9)
    assert base_st.pct_deadlines_met == pytest.approx(self_st.pct_deadlines_met, abs=1e-9)
    assert (base_st.pct_critical_met is None) == (self_st.pct_critical_met is None)
    if self_st.pct_critical_met is not None:
        assert base_st.pct_critical_met == pytest.approx(self_st.pct_critical_met, abs=1e-9)
    cells = [c.strip() for c in row(d.name, "csp", "baseline", "-", r, b).strip("|").split("|")]
    assert cells[5:8] == cells[13:16] and cells[12] == "-"     # self == baseline columns


def test_sensitivity_s1_no_bayes_infeasible_under_baseline(tmp_path):
    from experiments.sensitivity import INFEASIBLE, row
    r, b = _sensitivity_eval(tmp_path, SCENARIO_DIRS[0], use_bayes=False)
    assert r.exit_code == 0                                      # self-evaluated: valid
    assert b.error_counts.get("E304", 0) > 0 and b.infeasible
    cells = [c.strip() for c in row("Scenario1", "csp", "use_bayes", "False", r, b).strip("|").split("|")]
    assert "E304" in cells[12] and cells[13] == INFEASIBLE


def test_sensitivity_return_plan_judged_in_return_mode(tmp_path):
    r, b = _sensitivity_eval(tmp_path, SCENARIO_DIRS[0], after_job="return")
    assert b.error_counts == {}                                  # not judged as on-site (E301)
