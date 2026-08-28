"""L1 — intake. Conversation -> structured requirements.

This is the one layer where an LLM does the primary work, because turning messy
human description into structured fields is exactly what LLMs are good at. It is
also the one layer where research at runtime is legitimate — but only about the
*task domain* (what the handled part is, industry cycle norms, environment),
never about parts. Part research at runtime is prohibited; see catalog/store.py.

The extractor is behind a Protocol so the pipeline can be tested and run with no
model attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .capabilities import Capability


class Environment(str, Enum):
    BENCHTOP = "benchtop"
    INDUSTRIAL = "industrial"
    WASHDOWN = "washdown"
    CLEANROOM = "cleanroom"


@dataclass
class Requirements:
    """Everything L2 needs. Missing fields fail closed rather than defaulting."""

    task: str
    payload_kg: float
    reach_m: float
    budget_usd: float
    cycle_time_target_s: float | None = None
    workspace_m: tuple[float, float, float] | None = None
    environment: Environment = Environment.BENCHTOP
    duty_hours_per_day: float = 8.0
    aesthetic_notes: str = ""
    #: What the machine must be able to DO. The LLM's primary job at L1: turn
    #: "a rolling robot that talks" into {MOBILITY, AUDIO_OUT, AUDIO_IN}.
    #: Empty means manipulation is assumed (the classic pick-and-place case).
    capabilities: set[Capability] = field(default_factory=set)
    workspace_is_planar: bool = False
    #: Anything the extractor had to guess. Surfaced to the customer verbatim —
    #: an unstated assumption is how a quote becomes an argument.
    assumptions: list[str] = field(default_factory=list)
    #: Anything genuinely unresolved. Non-empty means ASK, do not proceed.
    open_questions: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        problems = []
        if self.payload_kg <= 0:
            problems.append("payload_kg must be > 0")
        if self.reach_m <= 0:
            problems.append("reach_m must be > 0")
        if self.budget_usd <= 0:
            problems.append("budget_usd must be > 0 — budget is a required input, not optional")
        if self.cycle_time_target_s is not None and self.cycle_time_target_s <= 0:
            problems.append("cycle_time_target_s must be > 0 when given")
        return problems

    @property
    def ready(self) -> bool:
        return not self.validate() and not self.open_questions


class RequirementsExtractor(Protocol):
    """LLM boundary. Implement with a real model; the pipeline never imports one
    directly."""

    def extract(self, conversation: str) -> Requirements: ...


class ManualExtractor:
    """Requirements supplied directly, no model. Used for tests, replay of a
    stored design record, and any run where a human has already scoped the job."""

    def __init__(self, requirements: Requirements) -> None:
        self._r = requirements

    def extract(self, conversation: str) -> Requirements:
        return self._r
