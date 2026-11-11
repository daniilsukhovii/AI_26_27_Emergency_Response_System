"""Allocation problem, schedule simulation, lexicographic cost and greedy planners
(SPEC §5.8, §5.10, §6.7). Infra only — no STUDENT kernels."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import textwrap

import pytest

from erp.allocation import build_problem, compute_domains, schedule_cost, simulate_schedule
from erp.config import Config
from erp.greedy import greedy_assignment, greedy_planner
from erp.io_load import load_scenario
from erp.model import ResponderState
from tests.fixtures import (
    REPO, hand_network, inc, incident, matrix_problem, matrix_travel, node, reference_router, responder,
    snap, t_c1_problem, two_way, write_scenario,
)


# ------------------------------------------------------------------ domains / build_problem

def test_compute_domains_filters_and_orders():
    travel = matrix_travel({("A", "P"): 10, ("B", "P"): 4, ("C", "P"): 4, ("D", "P"): 1})
    responders = [snap("R1", "A"), snap("R10", "B"), snap("R2", "C"),
                  snap("R3", "D", caps=("other",)),        # not capable
                  snap("R4", "E"),                         # cannot reach
                  snap("R5", "A", free_at=3)]              # busy until 3
    d = compute_domains(0.0, [inc("I1", "P")], responders, travel)
    # arrivals: R1 10, R10 4, R2 4, R5 13 ; tie R2 < R10 by natural id
    assert d == {"I1": ("R2", "R10", "R1", "R5")}


@pytest.fixture
def line(tmp_path):
    d = write_scenario(
        tmp_path / "line",
        nodes=[node("A", 0, 0), node("B", 10, 0), node("C", 20, 0)],
        roads=two_way("A", "B", 10) + two_way("B", "C", 10),
        responders=[responder("R2", "A", ["X"]), responder("R1", "C", ["X", "Y"], busy_for=4)],
        incidents=[incident("I1", "B", "High", 50, "X", 0), incident("I2", "B", "Critical", 60, "Y", 0),
                   incident("I3", "C", "Low", 10, "X", 5)])
    s = load_scenario(d)
    net = hand_network(s, Config())
    return s, net, reference_router(net)


def _states(s):
    return {r.id: ResponderState(r.id, r.start_location, r.free_at_start) for r in s.responders.values()}


def test_build_problem(line):
    s, net, router = line
    p = build_problem(0.0, [s.incident("I1"), s.incident("I2")], _states(s), s, router, Config())
    assert [i.id for i in p.incidents] == ["I2", "I1"]                # order_key: Critical first
    assert [r.id for r in p.responders] == ["R1", "R2"]               # natural order
    assert p.responders[0].free_at == 4 and p.responders[0].position == "C"
    assert p.domains == {"I2": ("R1",), "I1": ("R2", "R1")}           # R2 arr 1, R1 arr 4 + 1
    assert p.travel("A", "C") == pytest.approx(2.0)
    assert p.after_job == "on-site" and p.now == 0.0


def test_build_problem_rejects_future_incidents(line):
    s, net, router = line
    with pytest.raises(ValueError, match="future knowledge"):
        build_problem(4.0, [s.incident("I3")], _states(s), s, router, Config())


def test_AUD8_future_knowledge_guard_survives_python_O():
    """AUD-8: the 'no future knowledge' guard of build_problem is an explicit check, not an
    assert, so under `python -O` an incident with timestamp 4 is still rejected at now = 0."""
    code = textwrap.dedent("""
        from erp.allocation import build_problem
        from erp.config import Config
        from erp.model import Incident, ResponderState
        from erp.routing import RouteCache
        class S:  # minimal scenario stand-in: build_problem only reads s.responders
            responders = {}
        inc = Incident("I1", "A", "High", 10.0, "X", 4.0, 0.0)
        try:
            build_problem(0.0, [inc], {}, S(), RouteCache(None), Config())
        except ValueError:
            raise SystemExit(0)
        raise SystemExit(3)
    """)
    proc = subprocess.run([sys.executable, "-O", "-c", code], cwd=REPO, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONPATH=str(REPO)), timeout=60)
    assert proc.returncode == 0, "future incident accepted under python -O (guard is an assert)"


# ------------------------------------------------------------------ simulate_schedule

def test_simulate_schedule_chain_on_site():
    p = matrix_problem([inc("I1", "P", "Critical", time_required=3), inc("I2", "Q", "High", time_required=2)],
                       [snap("R1", "X", free_at=5)], {("X", "P"): 10, ("P", "Q"): 4}, now=1.0)
    assert simulate_schedule(p, {"I1": "R1", "I2": "R1"}) == {"I1": (5.0, 15.0), "I2": (18.0, 22.0)}
    assert simulate_schedule(p, {}) == {}


def test_simulate_schedule_chain_return_mode():
    p = matrix_problem([inc("I1", "P", "Critical", time_required=3), inc("I2", "Q", "High")],
                       [snap("R1", "X")], {("X", "P"): 10, ("P", "X"): 6, ("X", "Q"): 2, ("P", "Q"): 1},
                       after_job="return")
    # I1: dep 0 arr 10 fin 13 back 6 -> free 19 at X ; I2: dep 19 arr 21
    assert simulate_schedule(p, {"I1": "R1", "I2": "R1"}) == {"I1": (0.0, 10.0), "I2": (19.0, 21.0)}


def test_simulate_schedule_return_without_route_back_stays_on_site():
    p = matrix_problem([inc("I1", "P", "Critical", time_required=3), inc("I2", "Q", "High")],
                       [snap("R1", "X")], {("X", "P"): 10, ("X", "Q"): 2, ("P", "Q"): 1},
                       after_job="return")
    assert simulate_schedule(p, {"I1": "R1", "I2": "R1"}) == {"I1": (0.0, 10.0), "I2": (13.0, 14.0)}


def test_simulate_schedule_unreachable_chain_is_none():
    p = matrix_problem([inc("I1", "P", "Critical"), inc("I2", "Q", "High")],
                       [snap("R1", "X")], {("X", "P"): 1, ("X", "Q"): 1})
    assert simulate_schedule(p, {"I2": "R1"}) == {"I2": (0.0, 1.0)}
    assert simulate_schedule(p, {"I1": "R1", "I2": "R1"}) is None
    assert schedule_cost(p, {"I1": "R1", "I2": "R1"}) is None


def test_simulate_schedule_unknown_ids():
    p = t_c1_problem()
    with pytest.raises(KeyError):
        simulate_schedule(p, {"I9": "R1"})
    with pytest.raises(KeyError):
        simulate_schedule(p, {"I1": "R9"})


# ------------------------------------------------------------------ schedule_cost (T-C1 numbers)

def test_T_C1_costs_of_all_alternatives():
    p = t_c1_problem()
    assert schedule_cost(p, {"I1": "R1", "I2": "R2"}) == (0, 1, 0, 35.0)
    assert schedule_cost(p, {"I1": "R2", "I2": "R1"}) == (1, 0, 0, 21.0)
    assert schedule_cost(p, {"I1": "R1", "I2": "R1"}) == (0, 1, 0, 70.0)
    assert (0, 1, 0, 35.0) < (1, 0, 0, 21.0)          # lexicographic: Critical misses dominate


def test_cost_deadline_inclusive_and_classes():
    p = matrix_problem([inc("I1", "P", "Critical", deadline=10), inc("I2", "P", "Medium", deadline=5),
                        inc("I3", "P", "Low", deadline=5, timestamp=0)],
                       [snap("R1", "X"), snap("R2", "X"), snap("R3", "X")], {("X", "P"): 10})
    # I1 arrives exactly at its deadline -> met; I2, I3 missed (Medium + Low share a component)
    assert schedule_cost(p, {"I1": "R1", "I2": "R2", "I3": "R3"}) == (0, 0, 2, 30.0)


def test_cost_counts_response_from_timestamp():
    p = matrix_problem([inc("I1", "P", timestamp=4)], [snap("R1", "X")], {("X", "P"): 3}, now=10)
    assert schedule_cost(p, {"I1": "R1"}) == (0, 0, 0, 9.0)        # arrival 13 - timestamp 4


# ------------------------------------------------------------------ greedy

def test_greedy_assignment_t_c1():
    assert greedy_assignment(t_c1_problem()) == {"I1": "R1", "I2": "R2"}


def test_greedy_assignment_uses_busy_responders_and_queues():
    # R1 free now but far; R2 busy until 5 but close. I1 then I2 at the same place.
    p = matrix_problem([inc("I1", "P", "Critical", time_required=10), inc("I2", "P", "High", time_required=10)],
                       [snap("R1", "X"), snap("R2", "Y", free_at=5)], {("X", "P"): 20, ("Y", "P"): 1})
    # I1: R1 arr 20, R2 arr 6 -> R2 ; I2: R1 arr 20, R2 queue arr 16 -> R2
    assert greedy_assignment(p) == {"I1": "R2", "I2": "R2"}


def test_greedy_assignment_ties_by_natural_id():
    p = matrix_problem([inc("I1", "P")], [snap("R10", "X"), snap("R2", "Y")], {("X", "P"): 5, ("Y", "P"): 5})
    assert greedy_assignment(p) == {"I1": "R2"}


def test_greedy_assignment_omits_empty_domain():
    p = matrix_problem([inc("I1", "P", cap="none"), inc("I2", "P")], [snap("R1", "X")], {("X", "P"): 1})
    assert greedy_assignment(p) == {"I2": "R1"}


def test_greedy_planner_only_free_now_one_per_responder():
    p = matrix_problem([inc("I1", "P", "Critical"), inc("I2", "P", "High"), inc("I3", "P", "Low")],
                       [snap("R1", "X"), snap("R2", "Y", free_at=5), snap("R3", "Z")],
                       {("X", "P"): 3, ("Y", "P"): 1, ("Z", "P"): 9})
    assert greedy_planner(Config())(p) == {"I1": "R1", "I2": "R3"}


def test_greedy_planner_is_deterministic():
    p = matrix_problem([inc(f"I{k}", "P") for k in range(1, 5)],
                       [snap(f"R{k}", "X") for k in (3, 1, 2)], {("X", "P"): 1})
    a = greedy_planner(Config())(p)
    assert a == greedy_planner(Config())(p) == {"I1": "R1", "I2": "R2", "I3": "R3"}
    assert math.isfinite(p.travel("X", "P"))
