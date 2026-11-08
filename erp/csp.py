"""CSP allocation: backtracking + MRV + forward checking + branch-and-bound (SPEC §5.9).

Variables: pending incidents (p.incidents). Domains: p.domains (capable responders that can
reach the incident from their position; busy ones included). Objective: lexicographic cost
§6.7 (allocation.schedule_cost); deadlines are soft [D 4].

STUDENT kernels: ``select_unassigned_variable``, ``forward_check``, ``solve_allocation``.
Infra: ``csp_planner``.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from erp.allocation import schedule_cost
from erp.config import Config
from erp.greedy import greedy_assignment
from erp.model import AllocationProblem, AllocationResult, CostTuple, Planner

__all__ = ["AllocationResult", "select_unassigned_variable", "forward_check", "solve_allocation",
           "csp_planner", "CSPPlanner"]


# STUDENT:
def select_unassigned_variable(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                               assignment: Mapping[str, str]) -> str:
    """MRV: the unassigned variable (incident id) with the smallest current domain;
    ties broken by order_key (§5.9)."""
    raise NotImplementedError


# STUDENT:
def forward_check(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                  assignment: Mapping[str, str], incumbent: CostTuple | None
                  ) -> dict[str, tuple[str, ...]] | None:
    """Forward checking after an assignment (§5.9): for every unassigned variable remove the
    values that make simulate_schedule infeasible or whose schedule_cost(partial ∪ {Y: r}) is
    >= the incumbent cost (cost-based FC). Returns the reduced domains, None = wipe-out."""
    raise NotImplementedError


# STUDENT:
def solve_allocation(p: AllocationProblem, node_limit: int,
                     incumbent: Mapping[str, str] | None = None) -> AllocationResult:
    """Backtracking + MRV + FC + B&B. Returns the lexicographically optimal complete assignment
    (or best found under node_limit). Variables with empty initial domain are left out."""
    raise NotImplementedError


# infra:
def _is_complete(p: AllocationProblem, mapping: Mapping[str, str]) -> bool:
    return all(i.id in mapping for i in p.incidents if p.domains.get(i.id))


class CSPPlanner:
    """Planner (callable) wrapping solve_allocation; accumulates statistics and log messages."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.nodes_expanded = 0
        self.all_optimal = True
        self.calls = 0
        self.messages: list[str] = []

    def __call__(self, p: AllocationProblem) -> dict[str, str]:
        self.calls += 1
        greedy = greedy_assignment(p)
        feasible = _is_complete(p, greedy) and schedule_cost(p, greedy) is not None
        res = solve_allocation(p, self.cfg.csp_node_limit, greedy if feasible else None)
        self.nodes_expanded += res.nodes_expanded
        self.all_optimal = self.all_optimal and res.optimal
        self.messages.append(
            f"t={p.now:g}: CSP {len(p.incidents)} variables, nodes_expanded={res.nodes_expanded}, "
            f"optimal={'yes' if res.optimal else 'no'}, cost={res.cost}")
        if res.cost is None or not _is_complete(p, res.assignment):
            self.messages.append(f"t={p.now:g}: WARNING CSP found no feasible complete assignment; "
                                 f"falling back to the greedy mapping")
            return dict(greedy)
        return dict(res.assignment)


def csp_planner(cfg: Config) -> Planner:
    """Wraps solve_allocation; logs nodes_expanded / optimal (see CSPPlanner)."""
    return CSPPlanner(cfg)
