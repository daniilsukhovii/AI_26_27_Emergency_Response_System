"""Config dataclass and CLI parsing (SPEC §5.1, §5.15)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from erp.config import Config, config_from_args


def test_defaults():
    c = Config()
    assert c.tau == 0.5 and c.congested_multiplier == 1.5
    assert dict(c.traffic_multipliers) == {"Low": 1.0, "Medium": 1.2, "High": 1.5}
    assert (c.unobserved_traffic, c.after_job, c.planner, c.hmm_init_convention) == \
        ("initial", "on-site", "csp", "pi_is_t1")
    assert c.csp_node_limit == 200_000 and c.validate is True


def test_mutable_default_uses_default_factory():
    f = {x.name: x for x in dataclasses.fields(Config)}["traffic_multipliers"]
    assert f.default is dataclasses.MISSING
    assert f.default_factory is not dataclasses.MISSING
    a, b = Config(), Config()
    assert a.traffic_multipliers is not b.traffic_multipliers


def test_config_is_frozen_and_copies_multipliers():
    m = {"Low": 1.0, "Medium": 1.2, "High": 1.5}
    c = Config(traffic_multipliers=m)
    m["High"] = 9.0
    assert c.traffic_multipliers["High"] == 1.5
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.tau = 0.3  # type: ignore[misc]


def test_T_W7_multiplier_below_one_rejected():
    with pytest.raises(ValueError):
        Config(traffic_multipliers={"Low": 0.9, "Medium": 1.2, "High": 1.5})


@pytest.mark.parametrize("kw", [
    dict(tau=0.0), dict(tau=1.5), dict(congested_multiplier=0.8), dict(csp_node_limit=0),
    dict(traffic_multipliers={"Low": 1.0, "Medium": 1.2}), dict(planner="random"),
    dict(after_job="teleport"), dict(unobserved_traffic="x"), dict(hmm_init_convention="x"),
])
def test_invalid_config_values(kw):
    with pytest.raises(ValueError):
        Config(**kw)


def test_cli_defaults():
    scen, out, cfg = config_from_args(["--scenario", "Scenarios/Scenario1"])
    assert scen == Path("Scenarios/Scenario1")
    assert out == Path("outputs") / "Scenario1"
    assert cfg == Config()


def test_cli_all_flags():
    scen, out, cfg = config_from_args([
        "--scenario", "Scenarios/Scenario2", "--out", "o", "--planner", "greedy",
        "--after-job", "return", "--tau", "0.3", "--traffic-mult", "Low=1.0,Medium=1.3,High=2",
        "--unobserved-traffic", "stationary", "--hmm-init", "pi_is_t0", "--csp-node-limit", "50",
        "--no-validate"])
    assert out == Path("o")
    assert cfg == Config(tau=0.3, traffic_multipliers={"Low": 1.0, "Medium": 1.3, "High": 2.0},
                         unobserved_traffic="stationary", after_job="return", planner="greedy",
                         csp_node_limit=50, hmm_init_convention="pi_is_t0", validate=False)


@pytest.mark.parametrize("argv", [
    [], ["--scenario", "x", "--planner", "magic"], ["--scenario", "x", "--tau", "abc"],
    ["--scenario", "x", "--traffic-mult", "Low=0.5"], ["--scenario", "x", "--traffic-mult", "Huge=2"],
])
def test_cli_invalid_exits_2(argv, capsys):
    with pytest.raises(SystemExit) as e:
        config_from_args(argv)
    assert e.value.code == 2
