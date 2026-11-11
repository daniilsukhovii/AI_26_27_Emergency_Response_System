"""CSP allocation: backtracking + MRV + forward checking + branch-and-bound (SPEC §5.9).

Variables: pending incidents (p.incidents). Domains: p.domains (capable responders that can
reach the incident from their position; busy ones included). Objective: lexicographic cost
§6.7 (allocation.schedule_cost); deadlines are soft [D 4].

STUDENT kernels: ``select_unassigned_variable``, ``forward_check``, ``solve_allocation``.
Infra: ``csp_planner``.
"""
from __future__ import annotations

from typing import Mapping, Sequence, Any

from erp.allocation import schedule_cost, simulate_schedule
from erp.config import Config
from erp.greedy import greedy_assignment
from erp.model import AllocationProblem, AllocationResult, CostTuple, Planner, order_key, natural_key

__all__ = ["AllocationResult", "select_unassigned_variable", "forward_check", "solve_allocation",
           "csp_planner", "CSPPlanner"]


# STUDENT:
def select_unassigned_variable(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                               assignment: Mapping[str, str]) -> str:
    """MRV: the unassigned variable (incident id) with the smallest current domain;
    ties broken by order_key (§5.9)."""

    key: tuple[float, tuple[Any, ...], str] = (float('inf'), (), "")

    for v_incident_id, sequence in domains.items():
        if v_incident_id in assignment:
            continue

        incident = next(
            (i for i in p.incidents if i.id == v_incident_id),
            None
        )

        if incident is None:
            continue

        v_size = len(sequence)
        order_key_i = order_key(incident)

        if v_size < key[0] or (
            v_size == key[0] and key[1] > order_key_i
        ):
            key = (v_size, order_key_i, v_incident_id)

    return key[2]


# STUDENT:
def forward_check(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                  assignment: Mapping[str, str], incumbent: CostTuple | None
                  ) -> dict[str, tuple[str, ...]] | None:
    """Forward checking after an assignment (§5.9): for every unassigned variable remove the
    values that make simulate_schedule infeasible or whose schedule_cost(partial ∪ {Y: r}) is
    >= the incumbent cost (cost-based FC). Returns the reduced domains, None = wipe-out."""

    new_domains: dict[str, tuple[str, ...]] = {}

    for x, r in assignment.items():
        new_domains[x] = (r,)

    for inc in p.incidents:
        inc_id = inc.id
        if inc_id in assignment or inc_id not in domains:
            continue

        kept = []
        for r in domains[inc_id]:
            partial = dict(assignment) | {inc_id: r}

            # 1) Validity check
            sched = simulate_schedule(p, partial)
            if sched is None:
                continue

            # 2) Cost-based FC: cut-off by incumbent
            if incumbent is not None:
                c: CostTuple = schedule_cost(p, partial)
                if c is None:
                    continue
                if c >= incumbent:
                    continue

            kept.append(r)

        if len(kept) == 0:
            return None

        new_domains[inc_id] = tuple(kept)

    return new_domains


# STUDENT:
def solve_allocation(p: AllocationProblem, node_limit: int,
                     incumbent: Mapping[str, str] | None = None) -> AllocationResult:
    """Backtracking + MRV + FC + B&B. Returns the lexicographically optimal complete assignment
    (or best found under node_limit). Variables with empty initial domain are left out."""

    variables = [inc.id for inc in p.incidents if len(p.domains[inc.id]) != 0]
    domains0 = {Y: p.domains[Y] for Y in variables}

    best_assignment: Mapping[str, str] = {}
    best_cost: CostTuple = None
    nodes = 0
    truncated = False # True = node_limit triggered

    if incumbent is not None:
        if (
                set(incumbent.keys()) == set(variables)
                and all(r in domains0[Y] for Y, r in incumbent.items())
                and simulate_schedule(p, incumbent) is not None
        ):
            best_assignment = incumbent.copy()
            best_cost = schedule_cost(p, incumbent)

    root : dict[str, tuple[str, ...]] | None = forward_check(p, domains0, {}, best_cost)
    if root is None:
        # there is nothing better than the incumbent (or there is no complete solution at all)
        return AllocationResult(
            assignment      = best_assignment,
            cost            = best_cost,
            nodes_expanded  = nodes,
            optimal         =True
        )

    def search(assignment :  dict[str, str], domains: dict[str, tuple[str, ...]]):
        nonlocal nodes
        nonlocal truncated
        nonlocal variables
        nonlocal best_cost
        nonlocal best_assignment
        if nodes >= node_limit:
            truncated = True
            return
        nodes += 1

        # Base case: all variables are assigned
        if len(assignment) == len(variables):
            c = schedule_cost(p, assignment)
            if best_cost is None or c < best_cost:
                best_cost = c
                best_assignment = assignment.copy()
            return

        # MRV: unassigned variable with the smallest domain; ties ==> order_key
        y = select_unassigned_variable(p, domains, assignment)

        # Ordering of values: by increasing cost of the partial schedule,
        # ties ==> by the ID of the person responsible (natural id order)
        scored: list[tuple[CostTuple, str]] = []
        for responder in domains[y]:
            temp = dict(assignment) | {y: responder}
            cost: CostTuple | None  = schedule_cost(p, temp)
            if cost is None:
                continue
            scored.append((cost, responder))

        scored.sort(key=lambda item: (item[0], natural_key(item[1])))



        for c, r in scored:

            # Branch & Bound: `best_cost` could have improved during the loop
            if best_cost is not None and c >= best_cost:
                break

            new_assignment = dict(assignment) | {y: r}

            # Forward checking with a current bound
            new_domains = forward_check(p, domains, new_assignment, best_cost)
            if new_domains is None:
                continue

            search(new_assignment, new_domains)
            if truncated:
                return

    search({}, root)

    return AllocationResult(
        assignment      = best_assignment,        # None / empty, if no solution is found
        cost            = best_cost,
        nodes_expanded  = nodes,
        optimal         = not truncated           # Optimality is proven only if the search has concluded.
    )


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
