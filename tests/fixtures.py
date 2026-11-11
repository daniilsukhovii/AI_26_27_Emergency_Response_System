"""Small hand-made scenarios for tests (SPEC §8: built from in-memory dicts written to tmp_path).

Fixture probability tables are copied from Scenario1 at test time (no values duplicated here).
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parent.parent
SCENARIOS = REPO / "Scenarios"
SCENARIO_DIRS = [SCENARIOS / f"Scenario{k}" for k in (1, 2, 3)]


def node(id_: str, x: float, y: float, type_: str = "normal") -> dict:
    return {"id": id_, "name": id_, "x": x, "y": y, "type": type_}


def road(src: str, dst: str, distance: float, speed: float = 10.0, road_type: str = "main") -> dict:
    return {"from": src, "to": dst, "distance": distance, "road_type": road_type, "speed": speed}


def two_way(a: str, b: str, distance: float, speed: float = 10.0) -> list[dict]:
    return [road(a, b, distance, speed), road(b, a, distance, speed)]


def responder(id_: str, start: str, caps: Iterable[str], busy_for: float | None = None,
              type_: str = "Unit") -> dict:
    return {"responder_id": id_, "type": type_, "start_location": start,
            "capabilities": ";".join(caps),
            "availability": "Busy" if busy_for is not None else "Available",
            "time_until_available": busy_for if busy_for is not None else 0}


def incident(id_: str, location: str, priority: str, deadline: float, cap: str,
             timestamp: float = 0, time_required: float = 0) -> dict:
    return {"incident_id": id_, "location": location, "priority": priority, "deadline": deadline,
            "required_capability": cap, "timestamp": timestamp, "time_required": time_required}


def report(src: str, dst: str, weather: str, source: str, status: str) -> dict:
    return {"from": src, "to": dst, "weather": weather, "source": source, "reported_status": status}


def observation(nr: int, src: str, dst: str, level: str) -> dict:
    return {"observation_nr": nr, "from": src, "to": dst, "traffic_observation": level}


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(header), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_scenario(directory: Path, nodes: list[dict], roads: list[dict], responders: list[dict],
                   incidents: list[dict], reports: list[dict] = (), observations: list[dict] = (),
                   probs_from: Path = SCENARIO_DIRS[0]) -> Path:
    """Write the 7 scenario files to ``directory`` and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "city_graph.json").write_text(json.dumps({"nodes": nodes, "roads": roads}, indent=2))
    _write_csv(directory / "responders.csv",
               ["responder_id", "type", "start_location", "capabilities", "availability",
                "time_until_available"], responders)
    _write_csv(directory / "incidents.csv",
               ["incident_id", "location", "priority", "deadline", "required_capability",
                "timestamp", "time_required"], incidents)
    _write_csv(directory / "road_reports.csv",
               ["from", "to", "weather", "source", "reported_status"], reports)
    _write_csv(directory / "observed_traffic.csv",
               ["observation_nr", "from", "to", "traffic_observation"], observations)
    for f in ("road_probabilities.json", "traffic_probabilities.json"):
        shutil.copy(probs_from / f, directory / f)
    return directory


# ------------------------------------------------------------------ mutation checks (AUD-5, AUD-6)

MUTANT_RUN_ENV = "ERP_MUTANT_RUN"   # set inside a nested mutant run, so mutation checks skip themselves


def suite_kills_mutant(tmp_path: Path, plugin_source: str) -> int:
    """Run the whole test suite in a subprocess with a mutant patched in by a pytest plugin
    (``plugin_source``, imported before collection). Returns pytest's exit code:
    1 = some test failed (mutant killed), 0 = mutant survived. Tests that call this skip
    themselves inside the nested run (``MUTANT_RUN_ENV``), so the run does not recurse."""
    (tmp_path / "audit_mutant_plugin.py").write_text(textwrap.dedent(plugin_source))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(REPO)]), **{MUTANT_RUN_ENV: "1"})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "audit_mutant_plugin", "-p", "no:cacheprovider",
         "tests"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
    return proc.returncode


def copy_scenario(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


# ------------------------------------------------------------------ injected beliefs (no kernels)

OPEN = {"Open": 1.0, "Congested": 0.0, "Blocked": 0.0}
BLOCKED = {"Open": 0.0, "Congested": 0.0, "Blocked": 1.0}


def hand_beliefs(s, cfg, status: dict | None = None, f_traffic: float = 1.0):
    """Beliefs without the Bayes/HMM kernels: every road Open with f_traffic, except roads
    listed in ``status`` ({road key: status distribution})."""
    from erp.roadnet import make_belief
    status = status or {}
    return {k: make_belief(r, status.get(k, OPEN), k in status, None, f_traffic, cfg)
            for k, r in s.roads.items()}


def hand_network(s, cfg, status: dict | None = None, f_traffic: float = 1.0):
    from erp.roadnet import build_network
    return build_network(s, cfg, beliefs=hand_beliefs(s, cfg, status, f_traffic))


def reference_router(net):
    """RouteCache backed by the test-only Dijkstra instead of the student's A*."""
    from erp.routing import RouteCache
    from tests.reference import dijkstra_route
    return RouteCache(net, dijkstra_route)


# ------------------------------------------------------------------ allocation problems (no graph)

def inc(id_: str, location: str, priority: str = "High", deadline: float = 100.0,
        cap: str = "X", timestamp: float = 0.0, time_required: float = 0.0):
    from erp.model import Incident
    return Incident(id=id_, location=location, priority=priority, deadline=deadline,
                    required_capability=cap, timestamp=timestamp, time_required=time_required)


def snap(id_: str, position: str, caps=("X",), free_at: float = 0.0, start: str | None = None):
    from erp.model import ResponderSnapshot
    return ResponderSnapshot(id=id_, capabilities=frozenset(caps),
                             start_location=start if start is not None else position,
                             position=position, free_at=free_at)


def matrix_travel(matrix: dict):
    """travel(u, v) from an explicit matrix; 0 on the diagonal, inf where missing."""
    import math

    def travel(u, v):
        if u == v:
            return 0.0
        return matrix.get((u, v), math.inf)
    return travel


def matrix_problem(incidents, responders, matrix: dict, now: float = 0.0, after_job="on-site"):
    """AllocationProblem with an explicit travel matrix; domains computed as in build_problem."""
    from erp.allocation import compute_domains
    from erp.model import AllocationProblem, natural_key, order_key
    incs = tuple(sorted(incidents, key=order_key))
    resps = tuple(sorted(responders, key=lambda r: natural_key(r.id)))
    travel = matrix_travel(matrix)
    return AllocationProblem(now=now, incidents=incs, responders=resps,
                             domains=compute_domains(now, incs, resps, travel),
                             travel=travel, after_job=after_job)


def t_c1_problem():
    """SPEC T-C1: lexicographic objective instance."""
    return matrix_problem(
        [inc("I1", "P", "Critical", 10, time_required=10), inc("I2", "Q", "High", 25, time_required=10)],
        [snap("R1", "X"), snap("R2", "Y")],
        {("X", "P"): 5, ("X", "Q"): 1, ("Y", "P"): 20, ("Y", "Q"): 30, ("P", "Q"): 50, ("Q", "P"): 50})


def random_problem(seed: int, n_incidents: int | None = None, n_responders: int | None = None):
    """Seeded random instance: <= 6 incidents, <= 4 responders. Travel times are the shortest-path
    closure of a random directed graph (metric, inf where unreachable), as RouteCache would give."""
    import random
    from tests.reference import floyd_warshall
    rng = random.Random(seed)
    nodes = [f"L{k}" for k in range(1, 7)]
    edges = {(u, v): float(rng.randint(1, 30)) for u in nodes for v in nodes
             if u != v and rng.random() < 0.45}
    matrix = floyd_warshall(nodes, edges)
    caps = ["a", "b", "c"]
    n_i = n_incidents if n_incidents is not None else rng.randint(1, 6)
    n_r = n_responders if n_responders is not None else rng.randint(1, 4)
    now = float(rng.randint(0, 20))
    responders = []
    for k in range(1, n_r + 1):
        rc = [c for c in caps if rng.random() < 0.6] or [rng.choice(caps)]
        free_at = now if rng.random() < 0.6 else now + rng.randint(1, 30)
        responders.append(snap(f"R{k}", rng.choice(nodes), rc, free_at, start=rng.choice(nodes)))
    incidents = []
    for k in range(1, n_i + 1):
        ts = float(rng.randint(0, int(now)))
        incidents.append(inc(f"I{k}", rng.choice(nodes), rng.choice(["Critical", "High", "Medium", "Low"]),
                             ts + rng.randint(5, 70), rng.choice(caps), ts, float(rng.randint(0, 20))))
    return matrix_problem(incidents, responders, matrix, now=now,
                          after_job=rng.choice(["on-site", "return"]))
