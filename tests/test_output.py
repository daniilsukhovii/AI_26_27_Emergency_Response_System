"""plan.json writer (SPEC §2.1). Infra only."""
from __future__ import annotations

import json

from erp.model import Assignment
from erp.output import plan_to_json, write_plan


def test_plan_json_format(tmp_path):
    plan = [Assignment("R10", "I3", ("A", "B"), 5.0), Assignment("R2", "I1", ("N1", "H1", "N2"), 0.0),
            Assignment("R2", "I2", ("N2",), 12.5), Assignment("R1", "I4", ("C", "D"), 5.0)]
    path = tmp_path / "sub" / "plan.json"
    write_plan(path, plan)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("]\n")
    data = json.loads(text)
    # order by (time, natural responder id)
    assert [(e["responder_id"], e["incident_id"]) for e in data] == \
        [("R2", "I1"), ("R1", "I4"), ("R10", "I3"), ("R2", "I2")]
    assert data[0] == {"responder_id": "R2", "incident_id": "I1", "path": ["N1", "H1", "N2"], "time": 0}
    assert isinstance(data[0]["time"], int)            # integral -> JSON integer
    assert data[3]["time"] == 12.5 and isinstance(data[3]["time"], float)   # [T 8] not truncated
    assert '\n    {\n        "responder_id": "R2",' in text                  # indent 4


def test_empty_plan():
    assert plan_to_json([]) == "[]\n"
