"""Entry point: python run.py --scenario Scenarios/Scenario1 [options]  (SPEC §5.15).

Writes plan.json and statistics.txt into the output directory.
Exit codes: 0 = OK, 1 = plan has validation errors (files are still written), 2 = input error.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from erp.config import Config, config_from_args
from erp.csp import csp_planner
from erp.greedy import greedy_planner
from erp.io_load import InputError, load_scenario
from erp.model import Issue, Scenario
from erp.output import format_statistics, write_plan, write_statistics
from erp.roadnet import RoadNetwork, build_network
from erp.routing import RouteCache
from erp.search import astar
from erp.simulate import SimulationResult, simulate
from erp.stats import Statistics, compute_statistics
from erp.validate import load_plan_json, reconstruct_timeline, validate_plan


@dataclass(frozen=True)
class RunResult:
    scenario: Scenario
    network: RoadNetwork
    simulation: SimulationResult
    statistics: Statistics
    issues: tuple[Issue, ...]
    plan_path: Path
    statistics_path: Path

    @property
    def exit_code(self) -> int:
        return 1 if any(i.severity == "error" for i in self.issues) else 0


def run_scenario(scenario_dir: Path, out_dir: Path, cfg: Config) -> RunResult:
    """Production pipeline (always the student kernels): beliefs -> network -> simulation ->
    plan.json -> validation of the written file -> statistics.txt. Raises InputError."""
    s = load_scenario(scenario_dir)
    net = build_network(s, cfg)
    router = RouteCache(net, astar)
    planner = csp_planner(cfg) if cfg.planner == "csp" else greedy_planner(cfg)
    sim = simulate(s, net, cfg, planner, router)

    out_dir = Path(out_dir)
    plan_path = out_dir / "plan.json"
    stats_path = out_dir / "statistics.txt"
    write_plan(plan_path, sim.assignments)

    if cfg.validate:
        _, timeline, issues = validate_plan(s, net, cfg, load_plan_json(plan_path))
    else:
        timeline, _ = reconstruct_timeline(s, net, cfg, list(sim.assignments))
        issues = []
    st = compute_statistics(s, timeline, sim.unhandled)
    write_statistics(stats_path, format_statistics(st, cfg, net, issues))
    return RunResult(s, net, sim, st, tuple(issues), plan_path, stats_path)


def main(argv: list[str] | None = None) -> int:
    scenario_dir, out_dir, cfg = config_from_args(argv)
    try:
        res = run_scenario(scenario_dir, out_dir, cfg)
    except InputError as exc:
        print(f"input error {exc}", file=sys.stderr)
        return 2
    for w in res.scenario.warnings:
        print(f"warning {w}", file=sys.stderr)
    for i in res.issues:
        where = "" if i.entry is None else f" [entry {i.entry}]"
        print(f"{i.severity} {i.code}{where}: {i.message}", file=sys.stderr)
    st = res.statistics
    print(f"{res.scenario.name}: {st.n_handled}/{st.n_total} incidents handled, "
          f"{len(res.simulation.assignments)} assignments -> {res.plan_path}, {res.statistics_path}")
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
