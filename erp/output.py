"""Writers for plan.json and statistics.txt (SPEC §2, §5.14)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Sequence

from erp.config import Config
from erp.model import Assignment, Issue, natural_key
from erp.roadnet import RoadNetwork
from erp.stats import Statistics


def plan_to_json(plan: Sequence[Assignment]) -> str:
    """Entries ordered by (time, natural responder id); indent 4; trailing newline."""
    ordered = sorted(plan, key=lambda a: (a.time, natural_key(a.responder_id)))
    return json.dumps([a.to_json() for a in ordered], indent=4, ensure_ascii=False) + "\n"


def write_plan(path: Path, plan: Sequence[Assignment]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan_to_json(plan), encoding="utf-8")


def _num(x: float | None, suffix: str = "") -> str:
    return "n/a" if x is None else f"{x:.1f}{suffix}"


def _ratio(pct: float | None, num: int, den: int) -> str:
    return "n/a" if pct is None else f"{pct:.1f}% ({num}/{den})"


def _issues_line(issues: Sequence[Issue], cfg: Config) -> str:
    if not cfg.validate:
        return "skipped (--no-validate)"
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    def summary(items: Sequence[Issue]) -> str:
        c = Counter(i.code for i in items)
        return "" if not c else " (" + ", ".join(f"{k} x{c[k]}" for k in sorted(c)) + ")"

    return (f"{len(errors)} error{'s' if len(errors) != 1 else ''}{summary(errors)}, "
            f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}{summary(warnings)}")


def format_statistics(st: Statistics, cfg: Config, net: RoadNetwork, issues: Sequence[Issue]) -> str:
    lines = [
        "System statistics:",
        "",
        f" * {st.n_handled} incidents handled",
        f" * {st.responders_used} responders used",
        f" * Average response time: {_num(st.avg_response_time, ' s')}",
        f" * Deadlines met: {_num(st.pct_deadlines_met, '%')}",
        "",
        "Details:",
        ' * The "Deadlines met" line above is the same value as "Deadlines met (all incidents)" '
        "below (§6.8, [D 10])",
        " * Time unit: seconds (s) of simulation time; response time = arrival time - incident timestamp",
    ]
    unhandled = [p for p in st.per_incident if p.status == "unhandled"]
    unh = ""
    if unhandled:
        unh = ": " + ", ".join(f"{p.id} ({p.reason or 'unknown'})" for p in unhandled)
    lines += [
        f" * Incidents: {st.n_total} total, {st.n_handled} handled ({st.n_late} late), "
        f"{st.n_unhandled} unhandled{unh}",
        f" * Deadlines met (all incidents, unhandled = missed): "
        f"{_ratio(st.pct_deadlines_met, st.n_met, st.n_total)}",
        f" * Deadlines met (Critical): {_ratio(st.pct_critical_met, st.n_critical_met, st.n_critical)}",
        f" * Missed deadlines: Critical {st.missed_by_class[0]}, High {st.missed_by_class[1]}, "
        f"Medium/Low {st.missed_by_class[2]}",
        f" * Configuration: {cfg.describe()}",
    ]
    removed = net.removed_roads()
    removed_txt = ", ".join(f"{u}->{v} ({p:.3f})" for (u, v), p in removed) if removed else "none"
    lines += [
        f" * Roads removed (P(Blocked) >= tau): {removed_txt}",
        f" * Validation: {_issues_line(issues, cfg)}",
        "",
        "Per incident:",
        f" {'id':<5}{'priority':<10}{'responder':<11}{'depart':>8} {'arrive':>8} {'deadline':>9} "
        f"{'response':>9}  status",
    ]
    for p in st.per_incident:
        status = p.status if p.reason is None else f"{p.status} ({p.reason})"
        lines.append(f" {p.id:<5}{p.priority:<10}{p.responder or '-':<11}{_num(p.depart):>8} "
                     f"{_num(p.arrive):>8} {p.deadline:>9.1f} {_num(p.response):>9}  {status}")
    return "\n".join(lines) + "\n"


def write_statistics(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
