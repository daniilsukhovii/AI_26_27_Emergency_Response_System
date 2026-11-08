"""Model parameters and CLI parsing (SPEC §5.1, §5.15)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping

from erp.model import LEVELS, Level

DEFAULT_TRAFFIC_MULTIPLIERS: Mapping[Level, float] = {"Low": 1.0, "Medium": 1.2, "High": 1.5}  # [D 7]

UNOBSERVED_TRAFFIC_MODES = ("initial", "neutral", "stationary")
AFTER_JOB_MODES = ("on-site", "return")
PLANNERS = ("csp", "greedy")
HMM_CONVENTIONS = ("pi_is_t1", "pi_is_t0")


def _default_traffic_multipliers() -> dict[Level, float]:
    return dict(DEFAULT_TRAFFIC_MULTIPLIERS)


@dataclass(frozen=True)
class Config:
    tau: float = 0.5                                   # [D 5]
    congested_multiplier: float = 1.5                  # [A §3.3]
    traffic_multipliers: Mapping[Level, float] = field(default_factory=_default_traffic_multipliers)  # [D 7]
    unobserved_traffic: Literal["initial", "neutral", "stationary"] = "initial"  # OQ-2
    after_job: Literal["on-site", "return"] = "on-site"   # [D 2]
    planner: Literal["csp", "greedy"] = "csp"
    csp_node_limit: int = 200_000                      # ENG, anytime B&B guard
    hmm_init_convention: Literal["pi_is_t1", "pi_is_t0"] = "pi_is_t1"  # OQ-1
    validate: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.tau <= 1.0:
            raise ValueError(f"tau must be in (0, 1], got {self.tau}")
        if self.congested_multiplier < 1.0:
            raise ValueError("congested_multiplier must be >= 1 (A* heuristic admissibility, §6.6)")
        mult = dict(self.traffic_multipliers)
        if set(mult) != set(LEVELS):
            raise ValueError(f"traffic_multipliers must define exactly {LEVELS}, got {sorted(mult)}")
        for level, m in mult.items():
            if not m >= 1.0:   # also rejects NaN
                raise ValueError(f"traffic multiplier for {level} must be >= 1 (§6.6), got {m}")
        # store a private copy so callers cannot mutate the frozen config afterwards
        object.__setattr__(self, "traffic_multipliers", {lv: float(mult[lv]) for lv in LEVELS})
        if self.unobserved_traffic not in UNOBSERVED_TRAFFIC_MODES:
            raise ValueError(f"unobserved_traffic must be one of {UNOBSERVED_TRAFFIC_MODES}")
        if self.after_job not in AFTER_JOB_MODES:
            raise ValueError(f"after_job must be one of {AFTER_JOB_MODES}")
        if self.planner not in PLANNERS:
            raise ValueError(f"planner must be one of {PLANNERS}")
        if self.hmm_init_convention not in HMM_CONVENTIONS:
            raise ValueError(f"hmm_init_convention must be one of {HMM_CONVENTIONS}")
        if self.csp_node_limit < 1:
            raise ValueError("csp_node_limit must be >= 1")

    def describe(self) -> str:
        """One-line, deterministic description (used in statistics.txt)."""
        mult = ",".join(f"{lv}={self.traffic_multipliers[lv]:g}" for lv in LEVELS)
        return (f"planner={self.planner}, tau={self.tau:g}, after_job={self.after_job}, "
                f"congested_multiplier={self.congested_multiplier:g}, traffic_multipliers={mult}, "
                f"unobserved_traffic={self.unobserved_traffic}, hmm_init={self.hmm_init_convention}, "
                f"csp_node_limit={self.csp_node_limit}, validate={'yes' if self.validate else 'no'}")


def parse_traffic_multipliers(text: str) -> dict[Level, float]:
    """Parse ``"Low=1.0,Medium=1.2,High=1.5"``. Levels not listed keep their default."""
    result: dict[Level, float] = dict(DEFAULT_TRAFFIC_MULTIPLIERS)
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"expected LEVEL=VALUE, got {part!r}")
        name, value = (x.strip() for x in part.split("=", 1))
        if name not in LEVELS:
            raise ValueError(f"unknown traffic level {name!r} (expected one of {LEVELS})")
        result[name] = float(value)  # type: ignore[index]
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run.py",
        description="Emergency response planner: writes plan.json and statistics.txt.")
    p.add_argument("--scenario", required=True, type=Path, help="scenario directory (7 input files)")
    p.add_argument("--out", type=Path, default=None,
                   help="output directory (default: outputs/<scenario dir name>/)")
    p.add_argument("--planner", choices=PLANNERS, default="csp")
    p.add_argument("--after-job", choices=AFTER_JOB_MODES, default="on-site")
    p.add_argument("--tau", type=float, default=0.5, help="remove road if P(Blocked) >= tau")
    p.add_argument("--traffic-mult", default=None, metavar="Low=1.0,Medium=1.2,High=1.5")
    p.add_argument("--unobserved-traffic", choices=UNOBSERVED_TRAFFIC_MODES, default="initial")
    p.add_argument("--hmm-init", choices=HMM_CONVENTIONS, default="pi_is_t1")
    p.add_argument("--csp-node-limit", type=int, default=200_000, metavar="N")
    p.add_argument("--no-validate", action="store_true")
    return p


def config_from_args(argv: list[str] | None = None) -> tuple[Path, Path, Config]:
    """Parse the CLI of SPEC §5.15. Returns (scenario dir, output dir, config).

    Invalid values exit with status 2 (argparse convention = input error).
    """
    parser = build_arg_parser()
    ns = parser.parse_args(argv)
    try:
        mult = (parse_traffic_multipliers(ns.traffic_mult) if ns.traffic_mult is not None
                else _default_traffic_multipliers())
        cfg = Config(
            tau=ns.tau,
            traffic_multipliers=mult,
            unobserved_traffic=ns.unobserved_traffic,
            after_job=ns.after_job,
            planner=ns.planner,
            csp_node_limit=ns.csp_node_limit,
            hmm_init_convention=ns.hmm_init,
            validate=not ns.no_validate,
        )
    except ValueError as exc:
        parser.error(str(exc))
    scenario: Path = ns.scenario
    out: Path = ns.out if ns.out is not None else Path("outputs") / scenario.resolve().name
    return scenario, out, cfg
