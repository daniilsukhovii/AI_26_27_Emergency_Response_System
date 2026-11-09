"""One-factor-at-a-time sensitivity analysis (SPEC §5.16).

    python experiments/sensitivity.py [--scenarios-dir Scenarios] [--out outputs]

Baseline: tau = 0.5, after_job = on-site, unobserved_traffic = initial, default multipliers.
For every scenario and planner in {csp, greedy}: the baseline, then tau in {0.3, 0.7},
unobserved_traffic in {neutral, stationary}, after_job = return, and the ablations
use_bayes = False, use_hmm = False and both False (D06). Writes outputs/sensitivity.md.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from erp.config import Config  # noqa: E402
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

HEADER = ("| scenario | planner | varied factor | value | handled | avg response (s) | % met | "
          "% Critical met | removed roads | observed traffic / usable roads | CSP nodes | CSP optimal |")


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def row(scenario: str, planner: str, factor: str, value: str, r: RunResult) -> str:
    st, net, sim = r.statistics, r.network, r.simulation
    usable = net.usable_roads()
    # counted from the input, so the column does not drop to 0 under use_hmm = False
    observed = sum(1 for k in usable if r.scenario.traffic_obs.get(k))
    csp_nodes = str(sim.csp_nodes_expanded) if planner == "csp" else "-"
    csp_opt = ("yes" if sim.csp_all_optimal else "no") if planner == "csp" else "-"
    return (f"| {scenario} | {planner} | {factor} | {value} | {st.n_handled}/{st.n_total} | "
            f"{_fmt(st.avg_response_time)} | {_fmt(st.pct_deadlines_met)} | "
            f"{_fmt(st.pct_critical_met)} | {len(net.removed_roads())} | {observed} / {len(usable)} | "
            f"{csp_nodes} | {csp_opt} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios-dir", type=Path, default=REPO / "Scenarios")
    ap.add_argument("--out", type=Path, default=REPO / "outputs")
    ns = ap.parse_args(argv)
    scenarios = sorted(d for d in ns.scenarios_dir.iterdir() if d.is_dir())
    separator = "|" + "---|" * (HEADER.count("|") - 1)
    lines = ["# Sensitivity analysis", "", "Baseline: " + Config().describe(), "", HEADER, separator]
    for sdir in scenarios:
        for planner in ("csp", "greedy"):
            for factor, value, change in VARIATIONS:
                cfg = replace(Config(planner=planner), **change)
                out = ns.out / "sensitivity" / sdir.name / f"{planner}_{factor}_{value}"
                r = run_scenario(sdir, out, cfg)
                lines.append(row(sdir.name, planner, factor, value, r))
                print(lines[-1])
    target = ns.out / "sensitivity.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
