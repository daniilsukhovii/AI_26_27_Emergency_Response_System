"""Plan validator (SPEC §5.12, checks §7).

Placeholder: the validator is written in a separate session that does not see the planner
code, to keep it independent. Only the §5.12 signatures exist here.
Dependency rule (SPEC §3.2): this module must never import simulate, csp, greedy or search.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from erp.config import Config
from erp.model import Assignment, Issue, NodeId, Scenario, TimelineEntry
from erp.roadnet import RoadNetwork


def dijkstra_all(net: RoadNetwork, source: NodeId) -> dict[NodeId, float]:
    raise NotImplementedError("validator: separate session")


def reconstruct_timeline(s: Scenario, net: RoadNetwork, cfg: Config,
                         plan: Sequence[Assignment]) -> tuple[dict[str, list[TimelineEntry]], list[Issue]]:
    raise NotImplementedError("validator: separate session")


def validate_plan(s: Scenario, net: RoadNetwork, cfg: Config,
                  raw_plan: object) -> tuple[list[Assignment], dict[str, list[TimelineEntry]], list[Issue]]:
    raise NotImplementedError("validator: separate session")


def load_plan_json(path: Path) -> object:
    raise NotImplementedError("validator: separate session")
