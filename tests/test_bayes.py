"""Bayesian road-status inference (SPEC §8.1). Calls STUDENT kernels of erp/bayes.py."""
from __future__ import annotations

import itertools
import random

import pytest

from erp.bayes import compute_status_beliefs, road_status_posterior, road_status_prior
from erp.config import Config
from erp.io_load import load_scenario
from erp.model import SOURCES, STATUSES, WEATHERS, RoadReport
from erp.roadnet import build_network, expected_status_multiplier, make_belief
from tests.fixtures import SCENARIO_DIRS

P6 = 1e-6     # SPEC §8: six given digits -> abs 1e-6
P4 = 1e-4


@pytest.fixture(scope="module")
def scen():
    return {k: load_scenario(d) for k, d in zip((1, 2, 3), SCENARIO_DIRS)}


def _check(dist, expected, tol):
    assert set(dist) == set(STATUSES)
    for s, v in zip(STATUSES, expected):
        assert dist[s] == pytest.approx(v, abs=tol), s


def _road_reports(s, road, weather, pairs):
    """Reports of ``road`` from the file; assert they are what the SPEC row describes."""
    reps = s.reports[road]
    assert {r.weather for r in reps} == {weather}
    assert sorted((r.source, r.reported_status) for r in reps) == sorted(pairs)
    return reps


@pytest.mark.parametrize("k", [1, 2, 3])
def test_T_B1_prior(scen, k):
    _check(road_status_prior(scen[k].cpts), (0.685, 0.18, 0.135), 1e-12)


def test_T_B2_s1_n1_n2(scen):
    s = scen[1]
    reps = _road_reports(s, ("N1", "N2"), "Rain",
                         [("Citizen", "Blocked"), ("Police", "Blocked"), ("Sensor", "Congested")])
    post = road_status_posterior(s.cpts, "Rain", reps)
    _check(post, (0.014337, 0.458781, 0.526882), P6)
    road = s.roads[("N1", "N2")]
    for tau, removed in ((0.3, True), (0.5, True), (0.7, False)):
        assert make_belief(road, post, True, None, 1.0, Config(tau=tau)).removed is removed


def test_T_B3_s1_n2_n1(scen):
    s = scen[1]
    reps = _road_reports(s, ("N2", "N1"), "Rain",
                         [("Citizen", "Congested"), ("Police", "Congested"), ("Sensor", "Congested")])
    post = road_status_posterior(s.cpts, "Rain", reps)
    _check(post, (0.005912, 0.993169, 0.000920), P6)
    assert not make_belief(s.roads[("N2", "N1")], post, True, None, 1.0, Config()).removed
    assert expected_status_multiplier(post, 1.5) == pytest.approx(1.497042, abs=P6)


@pytest.mark.parametrize("road", [("H1", "N3"), ("N3", "H1")])
def test_T_B4_s1_storm_three_blocked(scen, road):
    s = scen[1]
    reps = _road_reports(s, road, "Storm",
                         [("Citizen", "Blocked"), ("Police", "Blocked"), ("Sensor", "Blocked")])
    post = road_status_posterior(s.cpts, "Storm", reps)
    assert post["Blocked"] == pytest.approx(0.998008, abs=P6)
    assert post["Open"] == pytest.approx(0.000006 / 0.284066, abs=P6)
    assert post["Congested"] == pytest.approx(0.00056 / 0.284066, abs=P6)
    for tau in (0.3, 0.5, 0.7):
        assert make_belief(s.roads[road], post, True, None, 1.0, Config(tau=tau)).removed


def test_T_B5_s2_n1_n2(scen):
    s = scen[2]
    reps = _road_reports(s, ("N1", "N2"), "Storm",
                         [("Citizen", "Blocked"), ("Police", "Blocked"), ("Sensor", "Congested")])
    post = road_status_posterior(s.cpts, "Storm", reps)
    _check(post, (0.001130, 0.168675, 0.830196), P6)
    for tau in (0.3, 0.5, 0.7):
        assert make_belief(s.roads[("N1", "N2")], post, True, None, 1.0, Config(tau=tau)).removed


def test_T_B6_s2_h2_n8_near_tie(scen):
    s = scen[2]
    reps = _road_reports(s, ("H2", "N8"), "Rain",
                         [("Citizen", "Congested"), ("Sensor", "Congested"), ("Police", "Open")])
    post = road_status_posterior(s.cpts, "Rain", reps)
    _check(post, (0.488755, 0.510005, 0.001240), P6)
    assert expected_status_multiplier(post, 1.5) == pytest.approx(1.2553, abs=P4)


def test_T_B7_s2_n7_h2(scen):
    s = scen[2]
    reps = _road_reports(s, ("N7", "H2"), "Rain",
                         [("Citizen", "Open"), ("Police", "Congested"), ("Sensor", "Open")])
    _check(road_status_posterior(s.cpts, "Rain", reps), (0.814097, 0.185022, 0.000881), P6)


def _random_reports(rng, n):
    return [RoadReport(("A", "B"), "Rain", rng.choice(SOURCES), rng.choice(STATUSES)) for _ in range(n)]


def test_T_B8_order_invariance(scen):
    cpts = scen[1].cpts
    rng = random.Random(8)
    lists = [list(scen[2].reports[("H2", "N8")])] + [_random_reports(rng, n) for n in (2, 3, 4)]
    for reps in lists:
        w = rng.choice(WEATHERS)
        ref = road_status_posterior(cpts, w, reps)
        for perm in itertools.permutations(reps):
            p = road_status_posterior(cpts, w, list(perm))
            for s in STATUSES:
                assert p[s] == pytest.approx(ref[s], abs=1e-12)


def test_T_B9_empty_reports_storm(scen):
    _check(road_status_posterior(scen[1].cpts, "Storm", []), (0.15, 0.35, 0.50), 1e-12)


def test_T_B10_posteriors_are_distributions(scen):
    rng = random.Random(10)
    cases = [(s.cpts, reps[0].weather, reps) for s in scen.values() for reps in s.reports.values()]
    cases += [(scen[1].cpts, rng.choice(WEATHERS), _random_reports(rng, rng.randint(0, 6)))
              for _ in range(200)]
    for cpts, w, reps in cases:
        p = road_status_posterior(cpts, w, reps)
        assert set(p) == set(STATUSES)
        assert all(v >= 0 for v in p.values())
        assert sum(p.values()) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("k,expected", [
    (1, {("N1", "N2"), ("N2", "N4"), ("H1", "N3"), ("N3", "H1")}),
    (2, {("N1", "N2"), ("N2", "N1")}),
    (3, {("N5", "N16"), ("N16", "N5")}),
])
def test_T_B11_removed_roads(scen, k, expected):
    net = build_network(scen[k], Config(tau=0.5))
    assert {key for key, _ in net.removed_roads()} == expected


def test_compute_status_beliefs_uses_posterior_or_prior(scen):
    s = scen[1]
    beliefs = compute_status_beliefs(s)
    assert set(beliefs) == set(s.roads)
    dist, has = beliefs[("N1", "N2")]
    assert has and dist["Blocked"] == pytest.approx(0.526882, abs=P6)
    dist, has = beliefs[("H1", "N4")]
    assert not has and dist["Blocked"] == pytest.approx(0.135, abs=1e-12)
