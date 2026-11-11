"""Audit checks (prompts/04_audit.md). Every test here is EXPECTED TO FAIL on the audited code:
each one reproduces one finding of the audit report. Nothing in erp/ was changed.

Ids AUD-n match the findings table of the audit report.
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Mapping

import pytest

import run
from erp.config import Config
from erp.csp import solve_allocation
from tests.fixtures import (
    REPO, SCENARIO_DIRS, inc, incident, matrix_problem, node, report, responder, snap,
    t_c1_problem, two_way, write_scenario,
)


# ------------------------------------------------------------------ AUD-5, AUD-6 (medium): surviving mutants

def _suite_kills(tmp_path, plugin_source: str) -> int:
    """Run the existing suite (without this file) with a mutant patched in by a pytest plugin.
    Returns pytest's exit code: 1 = some test failed (mutant killed), 0 = mutant survived."""
    (tmp_path / "audit_mutant_plugin.py").write_text(textwrap.dedent(plugin_source))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(REPO)]))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "audit_mutant_plugin", "-p", "no:cacheprovider",
         "tests", "--ignore=tests/test_audit.py"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
    return proc.returncode


def test_AUD5_suite_detects_astar_without_heuristic(tmp_path):
    """D07 regression guard: the exact D07 bug (h=None treated as h=0 in the production path)
    still passes every existing test, because T-A7 (tests/test_search.py:237-249) compares costs
    only and no test checks that RouteCache/run.py search with the Euclidean heuristic."""
    code = _suite_kills(tmp_path, """
        import erp.search
        _orig = erp.search.astar
        def astar(net, start, goal, h=None):
            return _orig(net, start, goal, h if h is not None else (lambda n: 0.0))
        erp.search.astar = astar
    """)
    assert code == 1, "the D07 mutant (A* = uniform-cost search in production) survives the suite"


def test_AUD6_suite_detects_priority_first_mrv(tmp_path):
    """D08 (1) regression guard: the original 'priority first, then domain size' variable order
    still passes every existing test (T-C3 fixtures, tests/test_csp.py:64-76, never combine a
    higher priority with a larger domain)."""
    code = _suite_kills(tmp_path, """
        import erp.csp
        from erp.model import order_key, priority_rank
        def select_unassigned_variable(p, domains, assignment):
            incs = {i.id: i for i in p.incidents}
            cand = [v for v in domains if v not in assignment and v in incs]
            return min(cand, key=lambda v: (priority_rank(incs[v].priority), len(domains[v]),
                                            order_key(incs[v])))
        erp.csp.select_unassigned_variable = select_unassigned_variable
    """)
    assert code == 1, "the D08(1) mutant (priority before MRV) survives the suite"


# ------------------------------------------------------------------ AUD-7 (low)

def test_AUD7_solve_allocation_returns_a_mapping():
    """SPEC §5.9: AllocationResult.assignment is a Mapping. With node_limit = 1 and no incumbent,
    solve_allocation returns assignment=None (csp.py:109, 189)."""
    res = solve_allocation(t_c1_problem(), node_limit=1)
    assert isinstance(res.assignment, Mapping), f"assignment is {res.assignment!r}"


# ------------------------------------------------------------------ AUD-8 (low)

def test_AUD8_future_knowledge_guard_survives_python_O():
    """SPEC L5 says future knowledge is 'enforced in the simulator by an assertion'
    (allocation.py:48). Under `python -O` the guard disappears: build_problem accepts an
    incident with timestamp 4 at now = 0 without complaint."""
    code = textwrap.dedent("""
        from erp.allocation import build_problem
        from erp.config import Config
        from erp.model import Incident, ResponderState
        from erp.routing import RouteCache
        class S:  # minimal scenario stand-in: build_problem only reads s.responders
            responders = {}
        inc = Incident("I1", "A", "High", 10.0, "X", 4.0, 0.0)
        try:
            build_problem(0.0, [inc], {}, S(), RouteCache(None), Config())
        except Exception:
            raise SystemExit(0)
        raise SystemExit(3)
    """)
    proc = subprocess.run([sys.executable, "-O", "-c", code], cwd=REPO, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONPATH=str(REPO)), timeout=60)
    assert proc.returncode == 0, "future incident accepted under python -O (guard is an assert)"
