"""Scenario loading and input checks (SPEC §1, §5.2).

Errors raise ``InputError(code, msg)``; warnings are collected in
``Scenario.warnings`` as strings ``"<code>: <message>"``.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from erp.model import (
    LEVELS, PRIORITIES, SOURCES, STATUSES, WEATHERS,
    HMMParams, Incident, Node, NodeId, Responder, Road, RoadCPTs, RoadKey,
    RoadReport, Scenario, natural_key, road_sort_key,
)

FILES = (
    "city_graph.json", "responders.csv", "incidents.csv", "road_reports.csv",
    "road_probabilities.json", "observed_traffic.csv", "traffic_probabilities.json",
)

SOURCE_TO_CPT = {"Citizen": "citizen_report", "Police": "police_report", "Sensor": "sensor_report"}

PROB_TOL = 1e-6


class InputError(Exception):
    """Invalid scenario input; ``code`` is one of the I0xx codes of SPEC §1.3."""

    def __init__(self, code: str, msg: str) -> None:
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.msg = msg


# ---------------------------------------------------------------- primitives

def read_csv_rows(path: Path, required: Sequence[str]) -> list[dict[str, str]]:
    """Read a CSV with header; strip whitespace; skip blank lines [T 7].

    Raises InputError I001 if a required column is missing or a row is short.
    """
    if not path.is_file():
        raise InputError("I001", f"missing file {path.name}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    # drop blank / whitespace-only lines
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise InputError("I001", f"{path.name}: empty file (no header)")
    header = [h.strip() for h in rows[0]]
    missing = [c for c in required if c not in header]
    if missing:
        raise InputError("I001", f"{path.name}: missing column(s) {missing}")
    out: list[dict[str, str]] = []
    for lineno, r in enumerate(rows[1:], start=2):
        cells = [c.strip() for c in r]
        if len(cells) < len(header):
            raise InputError("I001", f"{path.name}: row {lineno} has {len(cells)} fields, "
                                     f"expected {len(header)}")
        out.append(dict(zip(header, cells)))
    return out


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise InputError("I001", f"missing file {path.name}")
    with path.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise InputError("I001", f"{path.name}: invalid JSON ({exc})") from exc


def _float(value: Any, what: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise InputError("I006", f"{what}: not a number ({value!r})") from None
    if not math.isfinite(x):
        raise InputError("I006", f"{what}: not finite ({value!r})")
    return x


def _label(value: str, allowed: Sequence[str], what: str) -> str:
    if value not in allowed:
        raise InputError("I004", f"{what}: unknown label {value!r} (expected one of {list(allowed)})")
    return value


def _get(d: Any, key: str, what: str) -> Any:
    if not isinstance(d, dict) or key not in d:
        raise InputError("I001", f"{what}: missing key {key!r}")
    return d[key]


def _dist(d: Any, labels: Sequence[str], what: str) -> dict[str, float]:
    """Validate a probability row over ``labels`` (I004 unknown label, I005 bad row)."""
    if not isinstance(d, dict):
        raise InputError("I001", f"{what}: expected an object")
    for k in d:
        _label(k, labels, what)
    missing = [lb for lb in labels if lb not in d]
    if missing:
        raise InputError("I005", f"{what}: missing probabilities for {missing}")
    row = {lb: _float(d[lb], f"{what}[{lb}]") for lb in labels}
    if any(p < 0 for p in row.values()):
        raise InputError("I005", f"{what}: negative probability {row}")
    total = sum(row.values())
    if abs(total - 1.0) > PROB_TOL:
        raise InputError("I005", f"{what}: probabilities sum to {total}, not 1")
    return row


def _table(d: Any, outer: Sequence[str], inner: Sequence[str], what: str) -> dict[str, dict[str, float]]:
    if not isinstance(d, dict):
        raise InputError("I001", f"{what}: expected an object")
    for k in d:
        _label(k, outer, what)
    return {o: _dist(_get(d, o, what), inner, f"{what}[{o}]") for o in outer}


# ---------------------------------------------------------------- per file

def _load_graph(path: Path) -> tuple[dict[NodeId, Node], dict[RoadKey, Road]]:
    data = _load_json(path)
    nodes_raw = _get(data, "nodes", path.name)
    roads_raw = _get(data, "roads", path.name)
    nodes: dict[NodeId, Node] = {}
    for k, n in enumerate(nodes_raw):
        what = f"{path.name} nodes[{k}]"
        nid = str(_get(n, "id", what))
        if nid in nodes:
            raise InputError("I002", f"duplicate node id {nid}")
        nodes[nid] = Node(id=nid, name=str(n.get("name", nid)),
                          x=_float(_get(n, "x", what), f"{what}.x"),
                          y=_float(_get(n, "y", what), f"{what}.y"),
                          type=str(n.get("type", "")))
    roads: dict[RoadKey, Road] = {}
    for k, r in enumerate(roads_raw):
        what = f"{path.name} roads[{k}]"
        src, dst = str(_get(r, "from", what)), str(_get(r, "to", what))
        for v in (src, dst):
            if v not in nodes:
                raise InputError("I003", f"{what}: unknown node {v}")
        if (src, dst) in roads:
            raise InputError("I002", f"duplicate directed road {src}->{dst}")
        dist = _float(_get(r, "distance", what), f"{what}.distance")
        speed = _float(_get(r, "speed", what), f"{what}.speed")
        if dist <= 0 or speed <= 0:
            raise InputError("I006", f"{what}: distance and speed must be > 0 ({dist}, {speed})")
        roads[(src, dst)] = Road(src=src, dst=dst, distance=dist, speed=speed,
                                 road_type=str(r.get("road_type", "")))
    nodes = {k: nodes[k] for k in sorted(nodes, key=natural_key)}
    roads = {k: roads[k] for k in sorted(roads, key=road_sort_key)}
    return nodes, roads


def _load_responders(path: Path, nodes: Mapping[NodeId, Node]) -> dict[str, Responder]:
    rows = read_csv_rows(path, ["responder_id", "type", "start_location", "capabilities",
                                "availability", "time_until_available"])
    out: dict[str, Responder] = {}
    for row in rows:
        rid = row["responder_id"]
        if rid in out:
            raise InputError("I002", f"duplicate responder id {rid}")
        if row["start_location"] not in nodes:
            raise InputError("I003", f"responder {rid}: unknown start_location {row['start_location']}")
        avail = _label(row["availability"], ("Available", "Busy"), f"responder {rid} availability")
        tua = _float(row["time_until_available"], f"responder {rid} time_until_available")
        if tua < 0:
            raise InputError("I006", f"responder {rid}: negative time_until_available {tua}")
        caps = frozenset(c.strip() for c in row["capabilities"].split(";") if c.strip())
        out[rid] = Responder(id=rid, type=row["type"], start_location=row["start_location"],
                             capabilities=caps, available=(avail == "Available"),
                             time_until_available=tua)
    return {k: out[k] for k in sorted(out, key=natural_key)}


def _load_incidents(path: Path, nodes: Mapping[NodeId, Node]) -> tuple[Incident, ...]:
    rows = read_csv_rows(path, ["incident_id", "location", "priority", "deadline",
                                "required_capability", "timestamp", "time_required"])
    seen: set[str] = set()
    out: list[Incident] = []
    for row in rows:
        iid = row["incident_id"]
        if iid in seen:
            raise InputError("I002", f"duplicate incident id {iid}")
        seen.add(iid)
        if row["location"] not in nodes:
            raise InputError("I003", f"incident {iid}: unknown location {row['location']}")
        prio = _label(row["priority"], PRIORITIES, f"incident {iid} priority")
        inc = Incident(id=iid, location=row["location"], priority=prio,  # type: ignore[arg-type]
                       deadline=_float(row["deadline"], f"incident {iid} deadline"),
                       required_capability=row["required_capability"],
                       timestamp=_float(row["timestamp"], f"incident {iid} timestamp"),
                       time_required=_float(row["time_required"], f"incident {iid} time_required"))
        if inc.timestamp < 0 or inc.time_required < 0:
            raise InputError("I006", f"incident {iid}: negative timestamp or time_required")
        out.append(inc)
    out.sort(key=lambda i: (i.timestamp, natural_key(i.id)))
    return tuple(out)


def _load_reports(path: Path, nodes: Mapping[NodeId, Node], roads: Mapping[RoadKey, Road],
                  warnings: list[str]) -> dict[RoadKey, tuple[RoadReport, ...]]:
    rows = read_csv_rows(path, ["from", "to", "weather", "source", "reported_status"])
    grouped: dict[RoadKey, list[RoadReport]] = {}
    for k, row in enumerate(rows, start=1):
        what = f"{path.name} report {k}"
        for v in (row["from"], row["to"]):
            if v not in nodes:
                raise InputError("I003", f"{what}: unknown node {v}")
        key = (row["from"], row["to"])
        rep = RoadReport(road=key,
                         weather=_label(row["weather"], WEATHERS, f"{what} weather"),  # type: ignore[arg-type]
                         source=_label(row["source"], SOURCES, f"{what} source"),  # type: ignore[arg-type]
                         reported_status=_label(row["reported_status"], STATUSES, f"{what} status"))  # type: ignore[arg-type]
        if key not in roads:
            warnings.append(f"I012: {what} refers to road {key[0]}->{key[1]} not in the graph (ignored)")
            continue
        grouped.setdefault(key, []).append(rep)
    for key, reps in grouped.items():
        weathers = {r.weather for r in reps}
        if len(weathers) > 1:
            raise InputError("I007", f"reports for road {key[0]}->{key[1]} carry different weather "
                                     f"values {sorted(weathers)}")
    return {k: tuple(grouped[k]) for k in sorted(grouped, key=road_sort_key)}


def _load_observations(path: Path, nodes: Mapping[NodeId, Node], roads: Mapping[RoadKey, Road],
                       warnings: list[str]) -> dict[RoadKey, tuple[str, ...]]:
    rows = read_csv_rows(path, ["observation_nr", "from", "to", "traffic_observation"])
    grouped: dict[RoadKey, list[tuple[int, int, str]]] = {}
    ignored: set[RoadKey] = set()
    for k, row in enumerate(rows, start=1):
        what = f"{path.name} observation {k}"
        for v in (row["from"], row["to"]):
            if v not in nodes:
                raise InputError("I003", f"{what}: unknown node {v}")
        try:
            nr = int(row["observation_nr"])
        except ValueError:
            raise InputError("I006", f"{what}: observation_nr is not an integer "
                                     f"({row['observation_nr']!r})") from None
        level = _label(row["traffic_observation"], LEVELS, f"{what} level")
        key = (row["from"], row["to"])
        if key not in roads:
            if key not in ignored:
                warnings.append(f"I012: observations refer to road {key[0]}->{key[1]} "
                                f"not in the graph (ignored)")
                ignored.add(key)
            continue
        grouped.setdefault(key, []).append((nr, k, level))
    out: dict[RoadKey, tuple[str, ...]] = {}
    for key in sorted(grouped, key=road_sort_key):
        seq = sorted(grouped[key])            # by observation_nr, then file order
        nrs = [nr for nr, _, _ in seq]
        if nrs != list(range(1, len(nrs) + 1)):
            warnings.append(f"I008: observation_nr of road {key[0]}->{key[1]} is not 1..{len(nrs)} "
                            f"without gaps ({nrs}); ordered by observation_nr")
        out[key] = tuple(level for _, _, level in seq)
    return out


def _load_cpts(path: Path) -> RoadCPTs:
    data = _load_json(path)
    prior = _dist(_get(data, "weather_prior", path.name), WEATHERS, "weather_prior")
    sgw = _table(_get(data, "road_status_given_weather", path.name), WEATHERS, STATUSES,
                 "road_status_given_weather")
    report = {src: _table(_get(data, key, path.name), STATUSES, STATUSES, key)
              for src, key in SOURCE_TO_CPT.items()}
    return RoadCPTs(weather_prior=prior, status_given_weather=sgw, report=report)  # type: ignore[arg-type]


def _load_hmm(path: Path) -> HMMParams:
    data = _load_json(path)
    return HMMParams(
        initial=_dist(_get(data, "initial", path.name), LEVELS, "initial"),  # type: ignore[arg-type]
        transition=_table(_get(data, "transition", path.name), LEVELS, LEVELS, "transition"),  # type: ignore[arg-type]
        emission=_table(_get(data, "emission", path.name), LEVELS, LEVELS, "emission"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- public API

def check_scenario(s: Scenario) -> list[str]:
    """Structural warnings of SPEC §1.3 that can be derived from a loaded Scenario
    (I009, I010, I011). I008 and I012 need raw file data and are produced while parsing."""
    warnings: list[str] = []
    for inc in sorted(s.incidents, key=lambda i: natural_key(i.id)):
        if inc.deadline < inc.timestamp:
            warnings.append(f"I009: incident {inc.id} deadline {inc.deadline:g} < timestamp "
                            f"{inc.timestamp:g} (can never be met; still planned)")
    for key, road in s.roads.items():
        a, b = s.nodes[road.src], s.nodes[road.dst]
        euclid = math.hypot(a.x - b.x, a.y - b.y)
        if euclid > road.distance + 1e-9:
            warnings.append(f"I010: road {key[0]}->{key[1]} Euclidean distance {euclid:.3f} m > "
                            f"distance {road.distance:g} m (A* heuristic may be inadmissible)")
    for r in s.responders.values():
        if r.available and r.time_until_available > 0:
            warnings.append(f"I011: responder {r.id} is Available but time_until_available = "
                            f"{r.time_until_available:g} (treated as free at 0)")
        if not r.available and r.time_until_available == 0:
            warnings.append(f"I011: responder {r.id} is Busy but time_until_available = 0")
    return warnings


def load_scenario(directory: Path) -> Scenario:
    """Load and check one scenario directory (7 files, SPEC §1)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise InputError("I001", f"scenario directory {directory} does not exist")
    for f in FILES:
        if not (directory / f).is_file():
            raise InputError("I001", f"missing file {f} in {directory}")
    warnings: list[str] = []
    nodes, roads = _load_graph(directory / "city_graph.json")
    responders = _load_responders(directory / "responders.csv", nodes)
    incidents = _load_incidents(directory / "incidents.csv", nodes)
    reports = _load_reports(directory / "road_reports.csv", nodes, roads, warnings)
    cpts = _load_cpts(directory / "road_probabilities.json")
    obs = _load_observations(directory / "observed_traffic.csv", nodes, roads, warnings)
    hmm = _load_hmm(directory / "traffic_probabilities.json")
    s = Scenario(name=directory.resolve().name, nodes=nodes, roads=roads, responders=responders,
                 incidents=incidents, reports=reports, traffic_obs=obs,  # type: ignore[arg-type]
                 cpts=cpts, hmm=hmm, warnings=())
    all_warnings = tuple(warnings + check_scenario(s))
    return Scenario(name=s.name, nodes=nodes, roads=roads, responders=responders,
                    incidents=incidents, reports=reports, traffic_obs=obs,  # type: ignore[arg-type]
                    cpts=cpts, hmm=hmm, warnings=all_warnings)
