"""L3 — the swappable CAD seam.

Fusion is the first backend, not the only one. Fusion 360 is desktop software:
GUI-driven, per-seat licensed, needs a logged-in session. That is fine for a local
internal tool and impossible for a published multi-user service. So the geometry
layer talks to this interface and never to a CAD API directly.

Adding a backend later (Onshape REST, CadQuery/build123d headless) means writing
one new subclass. It does not mean touching L1, L2, L4, or L5.

THE RULE: no backend-specific type may appear in any signature below. Only the
neutral types from ``geom`` cross this line.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .geom import BBox, Clash, Measurements, View


@dataclass(frozen=True)
class PlacedPart:
    """A catalog part positioned in the model."""

    part_id: str
    slot: str
    geometry_ref: str  # path to the normalized STEP in the catalog


class CADBackend(ABC):
    """Every geometry operation the pipeline is allowed to perform."""

    name: str = "abstract"

    #: Whether this backend can perform a real B-rep interference test. Backends
    #: that cannot must report False so L4 marks the check SKIPPED, never PASSED.
    #: A check that did not run must never read as a clean bill of health.
    supports_interference: bool = True

    # --- lifecycle -------------------------------------------------------
    @abstractmethod
    def open_design(self, name: str) -> None:
        """Create/open a scratch design. Must never target an existing user document."""

    @abstractmethod
    def close(self, save: bool = False) -> None: ...

    # --- L3 build --------------------------------------------------------
    @abstractmethod
    def instantiate_archetype(self, archetype_id: str, params: dict[str, float]) -> None:
        """Drive a parametric archetype to the given parameters (SI units).

        Implementations instantiate a pre-authored template. They do NOT generate
        geometry from scratch — see docs/architecture.md.
        """

    @abstractmethod
    def place_panel(self, tier: str) -> None:
        """Insert the control-panel tier (S/M/L) shell."""

    @abstractmethod
    def place_parts(self, parts: list[PlacedPart]) -> None:
        """Drop normalized component geometry into named panel slots."""

    # --- L4a deterministic gate -----------------------------------------
    @abstractmethod
    def measure(self) -> Measurements: ...

    @abstractmethod
    def check_interference(self) -> list[Clash]: ...

    @abstractmethod
    def panel_envelope(self) -> BBox:
        """Internal usable volume of the placed panel."""

    # --- L4b vision gate -------------------------------------------------
    @abstractmethod
    def screenshot(self, view: View, width: int = 1280, height: int = 960) -> bytes:
        """PNG bytes. Captured per stage, not only at the end, so a failure
        localizes to the stage that caused it."""

    # --- L5 --------------------------------------------------------------
    @abstractmethod
    def export(self, fmt: str, path: str) -> str: ...
