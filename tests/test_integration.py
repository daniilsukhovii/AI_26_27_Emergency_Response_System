"""End-to-end runs (SPEC §8.6 T-SIM-1, T-SIM-2, T-SIM-4, T-SIM-7) and architecture rules.

The end-to-end tests use the production pipeline (STUDENT kernels + validator)."""
from __future__ import annotations

import ast
import itertools
import json
from pathlib import Path

import pytest

import run
from erp.config import Config
from erp.io_load import load_scenario
from erp.roadnet import build_network
from tests.fixtures import (
    REPO, SCENARIO_DIRS, incident, node, observation, report, responder, two_way, write_scenario,
)

GRID = list(itertools.product(SCENARIO_DIRS, ["csp", "greedy"], ["on-site", "return"], [0.3, 0.5, 0.7]))


@pytest.mark.parametrize("scen,planner,after_job,tau", GRID,
                         ids=[f"{d.name}-{p}-{a}-{t}" for d, p, a, t in GRID])
def test_T_SIM_1_full_grid(tmp_path, scen, planner, after_job, tau):
    out = tmp_path / "out"
    code = run.main(["--scenario", str(scen), "--out", str(out), "--planner", planner,
                     "--after-job", after_job, "--tau", str(tau)])
    assert code == 0                                       # validator: 0 errors
    assert (out / "plan.json").is_file()
    stats = (out / "statistics.txt").read_text(encoding="utf-8")
    assert stats.startswith("System statistics:")
    assert " * Validation: 0 errors" in stats


def test_T_SIM_2_s1_everything_handled(tmp_path):
    res = run.run_scenario(SCENARIO_DIRS[0], tmp_path, Config(tau=0.5))
    plan = json.loads(res.plan_path.read_text())
    assert res.simulation.unhandled == {}
    assert len(plan) == 7
    ids = [e["incident_id"] for e in plan]
    assert len(set(ids)) == 7 and set(ids) == {f"I{k}" for k in range(1, 8)}


def test_T_SIM_4_s1_byte_identical(tmp_path):
    for k in (1, 2):
        assert run.main(["--scenario", str(SCENARIO_DIRS[0]), "--out", str(tmp_path / f"r{k}")]) == 0
    for f in ("plan.json", "statistics.txt"):
        assert (tmp_path / "r1" / f).read_bytes() == (tmp_path / "r2" / f).read_bytes()


def test_T_SIM_7_unobserved_traffic(tmp_path):
    plans = []
    for mode in ("initial", "neutral", "stationary"):
        out = tmp_path / mode
        assert run.main(["--scenario", str(SCENARIO_DIRS[0]), "--out", str(out),
                         "--unobserved-traffic", mode]) == 0
        plans.append((out / "plan.json").read_bytes())
    assert plans[0] == plans[1] == plans[2]                 # every S1 road is observed
    for d in SCENARIO_DIRS[1:]:
        s = load_scenario(d)
        a = build_network(s, Config(unobserved_traffic="initial")).beliefs
        b = build_network(s, Config(unobserved_traffic="neutral")).beliefs
        assert any(a[k].f_traffic != b[k].f_traffic for k in s.roads), d.name


# ------------------------------------------------------------------ infra-only checks

def test_input_error_exit_code_2(tmp_path, capsys):
    assert run.main(["--scenario", str(tmp_path / "missing"), "--out", str(tmp_path / "o")]) == 2
    assert "I001" in capsys.readouterr().err


def test_input_error_bad_file_exit_code_2(tmp_path):
    import shutil
    d = tmp_path / "S1"
    shutil.copytree(SCENARIO_DIRS[0], d)
    (d / "incidents.csv").write_text((d / "incidents.csv").read_text().replace("High", "Urgent", 1))
    assert run.main(["--scenario", str(d), "--out", str(tmp_path / "o")]) == 2
    assert not (tmp_path / "o" / "plan.json").exists()


def _two_node_scenario(directory, **extra):
    return write_scenario(directory, nodes=[node("A", 0, 0), node("B", 100, 0)],
                          roads=two_way("A", "B", 100), responders=[responder("R1", "A", ["X"])],
                          incidents=[incident("I1", "B", "High", 500, "X")], **extra)


def test_AUD4_impossible_evidence_is_an_input_error(tmp_path, capsys):
    """AUD-4: I005 accepts zero probabilities, but a report whose likelihood is 0 for every status
    makes road_status_posterior raise ValueError (Z = 0). compute_status_beliefs turns it into
    InputError I013, so run.main exits with 2 (input error), not 1 (SPEC §5.15: validation
    errors) and not a traceback."""
    d = _two_node_scenario(tmp_path / "z0", reports=[report("A", "B", "Rain", "Sensor", "Blocked")])
    f = d / "road_probabilities.json"
    probs = json.loads(f.read_text())
    probs["sensor_report"] = {"Open": {"Open": 0.9, "Congested": 0.1, "Blocked": 0.0},
                              "Congested": {"Open": 0.1, "Congested": 0.9, "Blocked": 0.0},
                              "Blocked": {"Open": 0.5, "Congested": 0.5, "Blocked": 0.0}}
    f.write_text(json.dumps(probs))
    assert run.main(["--scenario", str(d), "--out", str(tmp_path / "o")]) == 2
    assert "I013" in capsys.readouterr().err
    assert not (tmp_path / "o" / "plan.json").exists()


def test_AUD4_impossible_traffic_sequence_is_an_input_error(tmp_path, capsys):
    """AUD-4, HMM counterpart: an observation that no hidden level can emit (emission column 0)
    makes forward_filter raise ValueError; compute_traffic_factors turns it into I013 (exit 2)."""
    d = _two_node_scenario(tmp_path / "h0", observations=[observation(1, "A", "B", "High")])
    f = d / "traffic_probabilities.json"
    probs = json.loads(f.read_text())
    probs["emission"] = {"Low": {"Low": 0.8, "Medium": 0.2, "High": 0.0},
                         "Medium": {"Low": 0.2, "Medium": 0.8, "High": 0.0},
                         "High": {"Low": 0.1, "Medium": 0.9, "High": 0.0}}
    f.write_text(json.dumps(probs))
    assert run.main(["--scenario", str(d), "--out", str(tmp_path / "o")]) == 2
    assert "I013" in capsys.readouterr().err
    assert not (tmp_path / "o" / "plan.json").exists()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module)
    return names


@pytest.mark.parametrize("module", ["validate.py", "stats.py"])
def test_dependency_rule_validator_and_stats(module):
    forbidden = {"erp.simulate", "erp.csp", "erp.greedy", "erp.search"}
    assert not (_imports(REPO / "erp" / module) & forbidden)


def test_erp_never_imports_tests():
    for p in (REPO / "erp").glob("*.py"):
        assert not any(m == "tests" or m.startswith("tests.") for m in _imports(p)), p.name
