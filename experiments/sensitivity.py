"""One-factor-at-a-time sensitivity analysis (SPEC §5.16).

    python experiments/sensitivity.py [--scenarios-dir Scenarios] [--out outputs]

Baseline: tau = 0.5, after_job = on-site, unobserved_traffic = initial, default multipliers.
For every scenario and planner in {csp, greedy}: the baseline, then tau in {0.3, 0.7},
unobserved_traffic in {neutral, stationary}, after_job = return, and the ablations
use_bayes = False, use_hmm = False and both False (D06). Writes outputs/sensitivity.md.

Every plan is judged twice: "self" = the network it was planned on (validation inside
run_scenario), "baseline" = validate_plan on the baseline network (default tau, multipliers,
use_bayes, use_hmm) with the run's after_job, so ablation plans are judged by the full model.
A plan with any error-severity issue under the baseline model (e.g. E304 removed road, E404
overlapping jobs) is infeasible there: its error codes are listed with counts and its baseline
avg response, % met and % Critical met are shown as "n/a (infeasible)".
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from erp.config import Config  # noqa: E402
from erp.io_load import load_scenario  # noqa: E402
from erp.roadnet import RoadNetwork, build_network  # noqa: E402
from erp.stats import Statistics, compute_statistics  # noqa: E402
from erp.validate import load_plan_json, validate_plan  # noqa: E402
from run import RunResult, run_scenario  # noqa: E402

VARIATIONS: list[tuple[str, str, dict]] = [
    ("baseline", "-", {}),
    ("tau", "0.3", {"tau": 0.3}),
    ("tau", "0.7", {"tau": 0.7}),
    ("unobserved_traffic", "neutral", {"unobserved_traffic": "neutral"}),
    ("unobserved_traffic", "stationary", {"unobserved_traffic": "stationary"}),
    ("after_job", "return", {"after_job": "return"}),
    ("use_bayes", "False", {"use_bayes": False}),               # ablation, D06
    ("use_hmm", "False", {"use_hmm": False}),                   # ablation, D06
    ("use_bayes+use_hmm", "False", {"use_bayes": False, "use_hmm": False}),
]

HEADER = ("| scenario | planner | varied factor | value | handled | avg response (s) [self] | % met [self] | "
          "% Critical met [self] | removed roads | observed traffic / usable roads | CSP nodes | CSP optimal | "
          "errors [baseline] | avg response (s) [baseline] | % met [baseline] | % Critical met [baseline] |")

INFEASIBLE = "n/a (infeasible)"


@dataclass(frozen=True)
class BaselineEval:
    """A run's plan judged by the baseline network (SPEC §5.16)."""
    error_counts: dict[str, int]      # error code -> count
    statistics: Statistics
    infeasible: bool                  # any error-severity issue under the baseline model

    def errors_text(self) -> str:
        return ", ".join(f"{c} x{n}" for c, n in sorted(self.error_counts.items())) or "-"


def baseline_network(scenario_dir: Path) -> RoadNetwork:
    """Network of the baseline model: default tau, multipliers, use_bayes, use_hmm."""
    return build_network(load_scenario(scenario_dir), Config())


def baseline_eval(r: RunResult, cfg: Config, base_net: RoadNetwork) -> BaselineEval:
    """validate_plan(scenario, baseline network, cfg_eval, plan); cfg_eval keeps the run's
    after_job (a return-mode plan is not judged as on-site)."""
    cfg_eval = Config(after_job=cfg.after_job)
    _, timeline, issues = validate_plan(r.scenario, base_net, cfg_eval, load_plan_json(r.plan_path))
    counts = Counter(i.code for i in issues if i.severity == "error")
    st = compute_statistics(r.scenario, timeline, r.simulation.unhandled)
    return BaselineEval(dict(counts), st, bool(counts))


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def _baseline_cell(b: BaselineEval, x: float | None) -> str:
    """A baseline-evaluated metric; not computed from the timeline of an infeasible plan."""
    return INFEASIBLE if b.infeasible else _fmt(x)


def row(scenario: str, planner: str, factor: str, value: str, r: RunResult, b: BaselineEval) -> str:
    st, net, sim = r.statistics, r.network, r.simulation
    bst = b.statistics
    usable = net.usable_roads()
    # counted from the input, so the column does not drop to 0 under use_hmm = False
    observed = sum(1 for k in usable if r.scenario.traffic_obs.get(k))
    csp_nodes = str(sim.csp_nodes_expanded) if planner == "csp" else "-"
    csp_opt = ("yes" if sim.csp_all_optimal else "no") if planner == "csp" else "-"
    return (f"| {scenario} | {planner} | {factor} | {value} | {st.n_handled}/{st.n_total} | "
            f"{_fmt(st.avg_response_time)} | {_fmt(st.pct_deadlines_met)} | "
            f"{_fmt(st.pct_critical_met)} | {len(net.removed_roads())} | {observed} / {len(usable)} | "
            f"{csp_nodes} | {csp_opt} | {b.errors_text()} | "
            f"{_baseline_cell(b, bst.avg_response_time)} | {_baseline_cell(b, bst.pct_deadlines_met)} | "
            f"{_baseline_cell(b, bst.pct_critical_met)} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios-dir", type=Path, default=REPO / "Scenarios")
    ap.add_argument("--out", type=Path, default=REPO / "outputs")
    ns = ap.parse_args(argv)
    scenarios = sorted(d for d in ns.scenarios_dir.iterdir() if d.is_dir())
    separator = "|" + "---|" * (HEADER.count("|") - 1)
    lines = ["# Sensitivity analysis", "", "Baseline: " + Config().describe(), "", HEADER, separator]
    for sdir in scenarios:
        base_net = baseline_network(sdir)
        for planner in ("csp", "greedy"):
            for factor, value, change in VARIATIONS:
                cfg = replace(Config(planner=planner), **change)
                out = ns.out / "sensitivity" / sdir.name / f"{planner}_{factor}_{value}"
                r = run_scenario(sdir, out, cfg)
                lines.append(row(sdir.name, planner, factor, value, r, baseline_eval(r, cfg, base_net)))
                print(lines[-1])
    target = ns.out / "sensitivity.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
