"""HMM forward filtering (SPEC §8.2). forward_filter is a STUDENT kernel; the
traffic-factor helpers are infra."""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from erp.config import Config
from erp.hmm import (
    compute_traffic_factors, expected_traffic_factor, forward_filter, stationary_distribution,
)
from erp.io_load import load_scenario
from erp.model import LEVELS, HMMParams
from tests.fixtures import SCENARIO_DIRS
from tests.reference import brute_force_filter

P6, P4 = 1e-6, 1e-4
MULT = Config().traffic_multipliers


@pytest.fixture(scope="module")
def scen():
    return {k: load_scenario(d) for k, d in zip((1, 2, 3), SCENARIO_DIRS)}


def _vec(d):
    return tuple(d[lv] for lv in LEVELS)


def _check(d, expected, tol):
    assert set(d) == set(LEVELS)
    assert _vec(d) == pytest.approx(expected, abs=tol)


def test_T_H1_s2_h2_n8_pi_is_t1(scen):
    s = scen[2]
    obs = s.traffic_obs[("H2", "N8")]
    assert obs == ("Low", "Medium", "High", "Medium", "High")
    alphas = forward_filter(s.hmm, obs, "pi_is_t1")
    expected = [(0.878156, 0.115258, 0.006586), (0.376579, 0.596366, 0.027054),
                (0.041359, 0.421349, 0.537292), (0.049707, 0.739731, 0.210563),
                (0.010113, 0.282220, 0.707666)]
    assert len(alphas) == 5
    for a, e in zip(alphas, expected):
        _check(a, e, P6)
    assert expected_traffic_factor(alphas[-1], MULT) == pytest.approx(1.410277, abs=P6)


def test_T_H1_default_convention_is_pi_is_t1(scen):
    s = scen[2]
    obs = s.traffic_obs[("H2", "N8")]
    _check(forward_filter(s.hmm, obs)[-1], (0.010113, 0.282220, 0.707666), P6)


def test_T_H1b_s2_h2_n8_pi_is_t0(scen):
    s = scen[2]
    alphas = forward_filter(s.hmm, s.traffic_obs[("H2", "N8")], "pi_is_t0")
    _check(alphas[-1], (0.010050, 0.281349, 0.708602), P6)
    assert expected_traffic_factor(alphas[-1], MULT) == pytest.approx(1.410571, abs=P6)


@pytest.mark.parametrize("k,road,obs,expected,f", [
    (1, ("N2", "N1"), ("High", "Low", "Medium", "High", "High", "Low", "Medium", "High", "Low", "Low"),
     (0.9290, 0.0659, 0.0051), 1.0157),
    (1, ("N4", "H1"), None, (0.0119, 0.3220, 0.6662), 1.3975),
    (3, ("N16", "N17"), None, (0.0019, 0.0748, 0.9233), 1.4766),
], ids=["T-H2", "T-H3", "T-H4"])
def test_T_H2_H4_scenario_roads(scen, k, road, obs, expected, f):
    s = scen[k]
    seq = s.traffic_obs[road]
    assert len(seq) == 10
    if obs is not None:
        assert seq == obs
    if road == ("N4", "H1"):
        assert seq[-3:] == ("Medium", "Medium", "High")
    a = forward_filter(s.hmm, seq, "pi_is_t1")
    _check(a[-1], expected, P4)
    assert expected_traffic_factor(a[-1], MULT) == pytest.approx(f, abs=P4)


def test_T_H4_s3_parameters_equal_s1(scen):
    assert scen[3].hmm == scen[1].hmm


def test_T_H5_single_observation(scen):
    a = forward_filter(scen[1].hmm, ["Low"], "pi_is_t1")
    assert len(a) == 1
    _check(a[0], (0.9410, 0.0554, 0.0037), P4)


def test_T_H6_every_alpha_is_a_distribution(scen):
    for s in scen.values():
        for conv in ("pi_is_t1", "pi_is_t0"):
            for obs in s.traffic_obs.values():
                alphas = forward_filter(s.hmm, obs, conv)
                assert len(alphas) == len(obs)
                for a in alphas:
                    assert set(a) == set(LEVELS)
                    assert all(v >= 0 for v in a.values())
                    assert sum(a.values()) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("conv", ["pi_is_t1", "pi_is_t0"])
def test_T_H7_empty_sequence_raises(scen, conv):
    with pytest.raises(ValueError):
        forward_filter(scen[1].hmm, [], conv)


def _uniform_emission(p: HMMParams) -> HMMParams:
    u = {s: {o: 1.0 / 3 for o in LEVELS} for s in LEVELS}
    return HMMParams(initial=p.initial, transition=p.transition, emission=u)


@pytest.mark.parametrize("k", [1, 2])
@pytest.mark.parametrize("conv,extra", [("pi_is_t1", 0), ("pi_is_t0", 1)])
def test_T_H8_uniform_emission_reduces_to_prediction(scen, k, conv, extra):
    p = _uniform_emission(scen[k].hmm)
    pi = np.array([p.initial[lv] for lv in LEVELS])
    a = np.array([[p.transition[i][j] for j in LEVELS] for i in LEVELS])
    for t in (1, 2, 5, 10):
        obs = ["High", "Low", "Medium"] * 4
        got = forward_filter(p, obs[:t], conv)[-1]
        expected = pi @ np.linalg.matrix_power(a, t - 1 + extra)   # π·A^(T-1) for pi_is_t1
        assert _vec(got) == pytest.approx(tuple(expected), abs=1e-9)


@pytest.mark.parametrize("k", [1, 2])
@pytest.mark.parametrize("conv", ["pi_is_t1", "pi_is_t0"])
def test_forward_filter_equals_brute_force_up_to_length_5(scen, k, conv):
    """Extra test: every α_t equals the brute-force sum over all hidden sequences, for every
    observation sequence of length 1..5."""
    params = scen[k].hmm
    for T in range(1, 6):
        for obs in itertools.product(LEVELS, repeat=T):
            got = forward_filter(params, list(obs), conv)
            ref = brute_force_filter(params, obs, conv)
            assert len(got) == T
            for g, r in zip(got, ref):
                assert _vec(g) == pytest.approx(_vec(r), abs=1e-12)


def test_brute_force_reference_matches_spec_T_H1(scen):
    """Sanity check of the reference itself (no kernel involved)."""
    s = scen[2]
    ref = brute_force_filter(s.hmm, s.traffic_obs[("H2", "N8")], "pi_is_t1")
    _check(ref[-1], (0.010113, 0.282220, 0.707666), P6)
    ref0 = brute_force_filter(s.hmm, s.traffic_obs[("H2", "N8")], "pi_is_t0")
    _check(ref0[-1], (0.010050, 0.281349, 0.708602), P6)


# --------------------------------------------------------------- T-H9 (infra parts)

@pytest.mark.parametrize("k,f", [(1, 1.110), (2, 1.145), (3, 1.110)])
def test_T_H9_initial_factor(scen, k, f):
    assert expected_traffic_factor(scen[k].hmm.initial, MULT) == pytest.approx(f, abs=P4)


def test_T_H9_stationary(scen):
    st = stationary_distribution(scen[1].hmm)
    _check(st, (0.3543, 0.3858, 0.2598), P4)
    assert expected_traffic_factor(st, MULT) == pytest.approx(1.2071, abs=P4)
    assert expected_traffic_factor(stationary_distribution(scen[2].hmm), MULT) == \
        pytest.approx(1.2288, abs=P4)
    # π∞ is a fixed point of the transition matrix
    a = np.array([[scen[2].hmm.transition[i][j] for j in LEVELS] for i in LEVELS])
    v = np.array(_vec(stationary_distribution(scen[2].hmm)))
    assert v @ a == pytest.approx(v, abs=1e-12)


@pytest.mark.parametrize("mode,f", [("initial", 1.145), ("neutral", 1.0), ("stationary", 1.2288)])
def test_T_H9_compute_traffic_factors_unobserved_roads(scen, mode, f):
    s = scen[2]
    factors = compute_traffic_factors(s, Config(unobserved_traffic=mode))
    assert set(factors) == set(s.roads)
    unobserved = [k for k in s.roads if k not in s.traffic_obs]
    assert unobserved
    for key in unobserved:
        dist, ft = factors[key]
        assert dist is None and ft == pytest.approx(f, abs=P4)
    dist, ft = factors[("H2", "N8")]
    _check(dist, (0.010113, 0.282220, 0.707666), P6)
    assert ft == pytest.approx(1.410277, abs=P6)


@pytest.mark.parametrize("mode,conv,f", [
    ("initial", "pi_is_t1", 1.145),          # π = (0.5, 0.35, 0.15)
    # π·A = (0.5·0.75 + 0.35·0.15 + 0.15·0.03, 0.5·0.22 + 0.35·0.7 + 0.15·0.22,
    #        0.5·0.03 + 0.35·0.15 + 0.15·0.75) = (0.432, 0.388, 0.18);
    # f = 0.432·1.0 + 0.388·1.2 + 0.18·1.5 = 1.1676
    ("initial", "pi_is_t0", 1.1676),
    ("neutral", "pi_is_t0", 1.0),
    ("stationary", "pi_is_t0", 1.2288),      # π∞ does not depend on the convention
])
def test_unobserved_roads_follow_hmm_init_convention(scen, mode, conv, f):
    """Open question 1 of the audit: with pi_is_t0, π is P(X_0), so a road without observations
    uses the distribution of X_1 = π·A (S2), consistent with forward_filter's first step."""
    s = scen[2]
    factors = compute_traffic_factors(s, Config(unobserved_traffic=mode, hmm_init_convention=conv))
    unobserved = [k for k in s.roads if k not in s.traffic_obs]
    assert unobserved
    for key in unobserved:
        dist, ft = factors[key]
        assert dist is None and ft == pytest.approx(f, abs=1e-12 if mode != "stationary" else P4)
