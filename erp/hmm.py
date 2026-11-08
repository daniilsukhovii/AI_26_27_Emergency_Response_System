"""HMM forward filtering of traffic levels (SPEC §5.4, formulas §6.4, §6.5).

STUDENT kernel: ``forward_filter``.
Infra: ``expected_traffic_factor``, ``stationary_distribution``, ``compute_traffic_factors``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

import numpy as np

from erp.model import LEVELS, HMMParams, Level, RoadKey, Scenario

if TYPE_CHECKING:
    from erp.config import Config


# STUDENT:
def forward_filter(params: HMMParams, observations: Sequence[Level],
                   convention: str = "pi_is_t1") -> list[dict[Level, float]]:
    """Normalised forward messages α_1..α_T (§6.4). Returns one distribution per observation;
    the last one is the filtered state [D 8]. Raises ValueError on an empty sequence."""
    raise NotImplementedError


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
    f_traffic according to cfg.unobserved_traffic (OQ-2)."""
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
