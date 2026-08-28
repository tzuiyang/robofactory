"""The design record — one JSON object per run, accumulating through every layer.

It is the unit of persistence, of replay, and of dataset. Two fields carry
disproportionate long-term value:

* ``engineer_corrections`` — every edit made at the human review gate is a
  labelled training example with a known input and a known-correct output.
  That supervision is normally impossible to obtain in engineering and here it
  costs nothing, because the engineer was reviewing anyway. **This is why the
  gate captures diffs and not just approve/reject.**
* ``actual_build_cost_usd`` — closes the only loop that matters commercially:
  quoted versus actual.

Both are cheap to record now and expensive to retrofit. They are in the schema
from day one even though nothing writes them yet.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class Stage(str, Enum):
    INTAKE = "L1_intake"
    CONFIG = "L2_config"
    GEOMETRY = "L3_geometry"
    VALIDATE = "L4_validate"
    PRESENT = "L5_present"


class Outcome(str, Enum):
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_human_review"
    REJECTED_INFEASIBLE = "rejected_infeasible"
    SENT_TO_CUSTOMER = "sent_to_customer"
    WON = "won"
    LOST = "lost"


@dataclass
class StageLog:
    stage: Stage
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass
class DesignRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    schema_version: int = SCHEMA_VERSION
    created_at: str | None = None  # stamped by the caller; keeps this module pure

    requirements: dict[str, Any] = field(default_factory=dict)
    archetype_id: str | None = None
    sizing: dict[str, Any] = field(default_factory=dict)
    bom: list[dict[str, Any]] = field(default_factory=list)
    tiers: dict[str, Any] = field(default_factory=dict)
    panel_tier: str | None = None
    geometry_params: dict[str, float] = field(default_factory=dict)

    checks: list[dict[str, Any]] = field(default_factory=list)
    repair_attempts: int = 0
    screenshots: list[str] = field(default_factory=list)

    stages: list[StageLog] = field(default_factory=list)
    outcome: Outcome = Outcome.DRAFT

    # --- the flywheel fields ---------------------------------------------
    engineer_corrections: list[dict[str, Any]] = field(default_factory=list)
    customer_outcome: str | None = None
    quoted_cost_usd: float | None = None
    actual_build_cost_usd: float | None = None

    def log(self, stage: Stage, ok: bool, detail: dict | None = None, *messages: str) -> None:
        self.stages.append(StageLog(stage=stage, ok=ok, detail=detail or {}, messages=list(messages)))

    def record_correction(self, field_path: str, before: Any, after: Any, reason: str = "") -> None:
        """Capture one engineer edit at the review gate. The training signal."""
        self.engineer_corrections.append(
            {"field": field_path, "before": before, "after": after, "reason": reason}
        )

    def to_json(self, indent: int = 2) -> str:
        def enc(o):
            if isinstance(o, Enum):
                return o.value
            raise TypeError(type(o))

        return json.dumps(asdict(self), indent=indent, default=enc)

    def save(self, directory: Path | str) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{self.id}.json"
        p.write_text(self.to_json())
        return p
