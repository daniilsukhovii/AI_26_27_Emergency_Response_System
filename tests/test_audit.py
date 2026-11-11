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
