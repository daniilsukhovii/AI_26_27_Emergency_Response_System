"""CSP allocation (SPEC §8.5). Fixtures use AllocationProblem with an explicit travel matrix.

Calls STUDENT kernels of erp/csp.py except T-C8 (schedule_cost, infra).
"""
from __future__ import annotations

import random

import pytest

from erp.allocation import schedule_cost
from erp.config import Config
from erp.csp import csp_planner, forward_check, select_unassigned_variable, solve_allocation
from erp.greedy import greedy_assignment
from erp.model import AllocationResult
from tests.fixtures import inc, matrix_problem, random_problem, snap, t_c1_problem
from tests.reference import exhaustive_allocation

LIMIT = Config().csp_node_limit
N_RANDOM = 200


def _same_cost(a, b):
    if a is None or b is None:
        return a is b
    return a[:3] == b[:3] and a[3] == pytest.approx(b[3], abs=1e-9)


def test_T_C1_lexicographic():
    p = t_c1_problem()
    res = solve_allocation(p, LIMIT)
    assert isinstance(res, AllocationResult)
    assert dict(res.assignment) == {"I1": "R1", "I2": "R2"}
    assert res.cost == (0, 1, 0, 35.0)
    assert res.optimal


@pytest.mark.parametrize("with_incumbent", [False, True], ids=["no-incumbent", "greedy-incumbent"])
def test_T_C2_optimal_vs_brute_force(with_incumbent):
    for seed in range(N_RANDOM):
        p = random_problem(seed)
        best, _ = exhaustive_allocation(p, schedule_cost)
        incumbent = None
        if with_incumbent:
            g = greedy_assignment(p)
            complete = all(i.id in g for i in p.incidents if p.domains[i.id])
            incumbent = g if complete and schedule_cost(p, g) is not None else None
        res = solve_allocation(p, LIMIT, incumbent)
        assert _same_cost(res.cost, best), (seed, res.cost, best)
        assert res.optimal, seed
        if best is not None:
            vars_ = {i.id for i in p.incidents if p.domains[i.id]}
            assert set(res.assignment) == vars_, seed
            assert all(res.assignment[v] in p.domains[v] for v in vars_)
            assert _same_cost(schedule_cost(p, res.assignment), res.cost), seed


def _three_incident_problem(priorities=("High", "High", "High")):
    return matrix_problem(
        [inc("I1", "P", priorities[0]), inc("I2", "P", priorities[1]), inc("I3", "P", priorities[2])],
        [snap("R1", "X"), snap("R2", "X"), snap("R3", "X")], {("X", "P"): 1})


def test_T_C3_mrv_smallest_domain():
    p = _three_incident_problem()
    domains = {"I1": ("R1", "R2", "R3"), "I2": ("R1",), "I3": ("R1", "R2")}
    assert select_unassigned_variable(p, domains, {}) == "I2"


def test_T_C3_mrv_ties_by_order_key():
    p = _three_incident_problem(("High", "Critical", "Low"))
    domains = {"I1": ("R1", "R2"), "I2": ("R1", "R2"), "I3": ("R1", "R2")}
    assert select_unassigned_variable(p, domains, {}) == "I2"            # Critical first
    assert select_unassigned_variable(p, domains, {"I2": "R1"}) == "I1"  # assigned ones skipped
    p2 = _three_incident_problem()
    assert select_unassigned_variable(p2, domains, {}) == "I1"           # natural id last tie-break


def test_T_C4_forward_check_wipe_out():
    # I2 reachable from R1's position X, but not from I1's location P.
    p = matrix_problem([inc("I1", "P", "Critical"), inc("I2", "Q", "High")],
                       [snap("R1", "X")], {("X", "P"): 5, ("X", "Q"): 5})
    assert p.domains == {"I1": ("R1",), "I2": ("R1",)}
    assert forward_check(p, p.domains, {"I1": "R1"}, None) is None


def test_T_C5_branch_and_bound_pruning():
    """Size-6 instances of the T-C2 generator: the greedy incumbent prunes the search
    (fewer nodes in total) and never changes the optimal cost."""
    with_inc = without = 0
    for seed in range(40):
        p = random_problem(seed, n_incidents=6, n_responders=4)
        g = greedy_assignment(p)
        if not (all(i.id in g for i in p.incidents if p.domains[i.id]) and schedule_cost(p, g)):
            continue
        a = solve_allocation(p, LIMIT, None)
        b = solve_allocation(p, LIMIT, g)
        assert _same_cost(a.cost, b.cost), seed
        without += a.nodes_expanded
        with_inc += b.nodes_expanded
    assert without > 0
    assert with_inc < without


def test_T_C6_empty_domain_is_omitted():
    p = matrix_problem([inc("I1", "P"), inc("I2", "P", cap="Pumping"), inc("I3", "Z")],
                       [snap("R1", "X")], {("X", "P"): 1})
    assert p.domains["I2"] == () and p.domains["I3"] == ()
    res = solve_allocation(p, LIMIT)
    assert dict(res.assignment) == {"I1": "R1"}
    assert res.cost == (0, 0, 0, 1.0)


def test_T_C7_node_limit_returns_incumbent():
    # first seeded instance with >= 3 variables and a complete, feasible greedy incumbent
    for seed in range(N_RANDOM):
        p = random_problem(seed, n_incidents=4, n_responders=3)
        g = greedy_assignment(p)
        vars_ = [i.id for i in p.incidents if p.domains[i.id]]
        if len(vars_) >= 3 and all(v in g for v in vars_) and schedule_cost(p, g) is not None:
            break
    else:
        pytest.fail("no suitable instance")
    res = solve_allocation(p, 1, g)
    assert res.optimal is False
    assert dict(res.assignment) == g
    assert res.cost is not None and _same_cost(res.cost, schedule_cost(p, g))


def test_T_C8_cost_monotone_under_extension():
    """Infra: adding one variable to a feasible partial assignment never decreases
    schedule_cost lexicographically (valid lower bound for B&B). Feasibility itself is not
    monotone (an inserted job can make a later leg reachable), so only feasible pairs count."""
    rng = random.Random(88)
    checked = 0
    for seed in range(N_RANDOM):
        p = random_problem(seed)
        vars_ = [i.id for i in p.incidents if p.domains[i.id]]
        for _ in range(10):
            k = rng.randint(0, max(0, len(vars_) - 1))
            chosen = rng.sample(vars_, k)
            partial = {v: rng.choice(p.domains[v]) for v in chosen}
            rest = [v for v in vars_ if v not in partial]
            if not rest:
                continue
            y = rng.choice(rest)
            ext = dict(partial, **{y: rng.choice(p.domains[y])})
            c0, c1 = schedule_cost(p, partial), schedule_cost(p, ext)
            if c0 is None or c1 is None:
                continue
            checked += 1
            assert all(a >= b for a, b in zip(c1[:3], c0[:3])), (seed, partial, y)
            assert c1[3] >= c0[3] - 1e-9, (seed, partial, y)
    assert checked > 500


def test_T_C9_determinism():
    for seed in (3, 11, 42):
        p = random_problem(seed, n_incidents=6, n_responders=4)
        assert solve_allocation(p, LIMIT) == solve_allocation(p, LIMIT)


def test_csp_planner_returns_optimum_and_counts_nodes():
    planner = csp_planner(Config())
    assert planner(t_c1_problem()) == {"I1": "R1", "I2": "R2"}
    assert planner.nodes_expanded > 0 and planner.all_optimal
