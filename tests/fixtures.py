"""Small hand-made scenarios for tests (SPEC §8: built from in-memory dicts written to tmp_path).

Fixture probability tables are copied from Scenario1 at test time (no values duplicated here).
"""
from __future__ import annotations

import csv
import json
import shutil
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


def copy_scenario(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst
