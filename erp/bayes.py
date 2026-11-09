"""Road-status inference (SPEC §5.3, formulas §6.1, §6.2).

STUDENT kernels: ``road_status_prior``, ``road_status_posterior``.
Infra wrapper: ``compute_status_beliefs``.
"""
from __future__ import annotations

from typing import Sequence, get_args

from erp.model import RoadCPTs, RoadKey, RoadReport, Scenario, Status, Weather


# STUDENT:
def road_status_prior(cpts: RoadCPTs) -> dict[Status, float]:
    """P(S) = Σ_w P(w)·P(S|w)  (§6.2). Used for roads without reports [D 6]."""
    prior : dict[Status, float] = {}
    for s in get_args(Status):
        prior[s] = 0.0
        for (weather, prior_weather) in cpts.weather_prior.items():
            prior[s] += prior_weather * cpts.status_given_weather[weather][s]
    return prior


# STUDENT:
def road_status_posterior(cpts: RoadCPTs, weather: Weather,
                          reports: Sequence[RoadReport]) -> dict[Status, float]:
    """P(S | w, r_1..r_k) ∝ P(S|w)·Π_k P(r_k|S, source_k)  (§6.1).
    Normalised by Z = Σ_S' P(S'|w)·Π_k P(r_k|S', source_k); order-invariant.
    With an empty report list it returns P(S|w)."""

    posterior : dict[Status, float] = {}
    for s in get_args(Status):
        p = cpts.status_given_weather[weather][s]
        for report in reports:
            p *= cpts.report[report.source][s][report.reported_status]
        posterior[s] = p

    total = sum(posterior.values())
    if total > 0:
        for s in posterior:
            posterior[s] /= total
    return posterior


# infra:
def compute_status_beliefs(s: Scenario) -> dict[RoadKey, tuple[dict[Status, float], bool]]:
    """For every graph road: posterior if it has reports (weather taken from its reports),
    else the prior. Returns (distribution, has_reports)."""
    out: dict[RoadKey, tuple[dict[Status, float], bool]] = {}
    prior: dict[Status, float] | None = None
    for key in s.roads:
        reports = s.reports.get(key, ())
        if reports:
            weather = reports[0].weather          # uniform per road, checked by I007
            out[key] = (dict(road_status_posterior(s.cpts, weather, reports)), True)
        else:
            if prior is None:
                prior = dict(road_status_prior(s.cpts))
            out[key] = (dict(prior), False)
    return out
