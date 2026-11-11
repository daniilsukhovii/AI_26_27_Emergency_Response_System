"""HMM forward filtering of traffic levels (SPEC §5.4, formulas §6.4, §6.5).

STUDENT kernel: ``forward_filter``.
Infra: ``expected_traffic_factor``, ``stationary_distribution``, ``compute_traffic_factors``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence, get_args, Any

import numpy as np

from erp.model import LEVELS, HMMParams, Level, RoadKey, Scenario

if TYPE_CHECKING:
    from erp.config import Config


def normalise_alphas(alpha: dict[Level, float]) -> dict[Level, float]:
    total = sum(alpha.values())
    if total <= 0:
        raise ValueError("observation sequence has zero probability under the model")
    return {s: p / total for s, p in alpha.items()}

# STUDENT:
def forward_filter(params: HMMParams, observations: Sequence[Level],
                   convention: str = "pi_is_t1") -> list[dict[Level, float]]:
    """Normalised forward messages α_1..α_T (§6.4). Returns one distribution per observation;
    the last one is the filtered state [D 8]. Raises ValueError on an empty sequence."""

    if convention not in ("pi_is_t1", "pi_is_t0"):
        raise ValueError(
            f"Unknown convention: {convention!r}. "
            "Expected 'pi_is_t1' or 'pi_is_t0'."
        )

    if len(observations) == 0:
        raise ValueError("observations must be non-empty")

    levels = get_args(Level)

    # Initial state distribution before the first observation
    prior = {}
    if convention == "pi_is_t1":
        # pi is the distribution of X_1
        for s in levels:
            prior[s] = params.initial[s]

    else:
        # pi is the distribution of X_0, so we pass it through the transition once
        for s in levels:
            temp_sum = 0
            for p in levels:
                temp_sum += params.initial[p] * params.transition[p][s]
            prior[s] = temp_sum

    o1 = observations[0]


    temp: dict[Level, float] = {}
    for s in levels:
        temp[s] = prior[s] * params.emission[s][o1]

    alphas: list[dict[Level, float]] = [normalise_alphas(temp)]

    for obs in observations[1:]:
        prev = alphas[-1]

        alpha : dict[Any, float] = {}
        for s in levels:
            sum_prev = 0
            for p in levels:
                sum_prev += prev[p] * params.transition[p][s]
            alpha[s] = params.emission[s][obs] * sum_prev

        alphas.append(normalise_alphas(alpha))

    return alphas


# infra:
def expected_traffic_factor(dist: Mapping[Level, float], mult: Mapping[Level, float]) -> float:
    """f_traffic = Σ_L P(L)·mult(L)  (§6.5), dimensionless."""
    return float(sum(dist[lv] * mult[lv] for lv in LEVELS))


def stationary_distribution(params: HMMParams) -> dict[Level, float]:
    """π∞ with π∞·A = π∞ (left eigenvector of A for eigenvalue 1), normalised.
    Only used for OQ-2 mode "stationary"."""
    a = np.array([[params.transition[i][j] for j in LEVELS] for i in LEVELS], dtype=float)
    vals, vecs = np.linalg.eig(a.T)
    k = int(np.argmin(np.abs(vals - 1.0)))
    v = np.real(vecs[:, k])
    v = v / v.sum()
    return {lv: float(v[n]) for n, lv in enumerate(LEVELS)}


def unobserved_traffic_factor(params: HMMParams, cfg: "Config") -> float:
    """f_traffic for a road without observations according to cfg.unobserved_traffic (OQ-2)."""
    mode = cfg.unobserved_traffic
    if mode == "initial":
        return expected_traffic_factor(params.initial, cfg.traffic_multipliers)
    if mode == "neutral":
        return 1.0
    if mode == "stationary":
        return expected_traffic_factor(stationary_distribution(params), cfg.traffic_multipliers)
    raise ValueError(f"unknown unobserved_traffic mode {mode!r}")


def compute_traffic_factors(s: Scenario, cfg: "Config"
                            ) -> dict[RoadKey, tuple[dict[Level, float] | None, float]]:
    """Per graph road: (filtered distribution or None, f_traffic). Roads without observations get
    f_traffic according to cfg.unobserved_traffic (OQ-2).

    Ablation ``cfg.use_hmm = False`` (SPEC §5.1, D06): (None, 1.0) for every road, observed or
    not; forward_filter is not called and cfg.unobserved_traffic has no effect."""
    if not cfg.use_hmm:
        return {key: (None, 1.0) for key in s.roads}
    out: dict[RoadKey, tuple[dict[Level, float] | None, float]] = {}
    unobserved: float | None = None
    for key in s.roads:
        obs = s.traffic_obs.get(key, ())
        if obs:
            alphas = forward_filter(s.hmm, obs, cfg.hmm_init_convention)
            dist = dict(alphas[-1])
            out[key] = (dist, expected_traffic_factor(dist, cfg.traffic_multipliers))
        else:
            if unobserved is None:
                unobserved = unobserved_traffic_factor(s.hmm, cfg)
            out[key] = (None, unobserved)
    return out
