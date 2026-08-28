"""A backend that models geometry arithmetically instead of in CAD.

This is not a mock for tests only. It lets the entire L1-L5 pipeline run, be
tested, and be reasoned about with no CAD application attached — which matters
because CAD is the slowest, least available, and least scriptable dependency in
the stack. Anything that needs real B-rep (true interference volumes, fastener
access, exact mass) falls through to a real backend; everything else is checked
here, instantly and for free.

It also proves the seam is honest: if the pipeline runs on this, no Fusion type
has leaked upward.
"""

from __future__ import annotations

from .base import CADBackend, PlacedPart
from .geom import BBox, Clash, MassProperties, Measurements, Vec3, View

# Internal usable volume per panel tier, metres (L x W x H).
PANEL_TIERS: dict[str, tuple[float, float, float]] = {
    "S": (0.15, 0.10, 0.06),
    "M": (0.25, 0.18, 0.09),
    "L": (0.40, 0.30, 0.12),
}


class NullBackend(CADBackend):
    name = "null"
    supports_interference = False

    def __init__(self) -> None:
        self._design: str | None = None
        self._params: dict[str, float] = {}
        self._tier: str | None = None
        self._parts: list[PlacedPart] = []
        self.screenshots_taken: list[View] = []

    def open_design(self, name: str) -> None:
        self._design = name

    def close(self, save: bool = False) -> None:
        self._design = None

    def instantiate_archetype(self, archetype_id: str, params: dict[str, float]) -> None:
        self._archetype = archetype_id
        self._params = dict(params)

    def place_panel(self, tier: str) -> None:
        if tier not in PANEL_TIERS:
            raise ValueError(f"unknown panel tier {tier!r}; expected one of {sorted(PANEL_TIERS)}")
        self._tier = tier

    def place_parts(self, parts: list[PlacedPart]) -> None:
        slots = [p.slot for p in parts]
        dupes = {s for s in slots if slots.count(s) > 1}
        if dupes:
            # Two parts in one slot is a clash the arithmetic model CAN catch.
            raise ValueError(f"slot collision: {sorted(dupes)}")
        self._parts = list(parts)

    def measure(self) -> Measurements:
        reach = self._params.get("reach_m", 0.0)
        return Measurements(
            bbox=BBox(Vec3(-reach, -reach, 0.0), Vec3(reach, reach, reach)),
            mass=MassProperties(
                mass_kg=self._params.get("est_mass_kg", 0.0),
                center_of_mass=Vec3(0.0, 0.0, reach / 3 if reach else 0.0),
                volume_m3=0.0,
            ),
            body_count=len(self._parts) + 1,
        )

    def check_interference(self) -> list[Clash]:
        """No B-rep here, so no true interference test is possible.

        Returns empty, but ``supports_interference`` is False so L4 reports the
        check as SKIPPED rather than PASSED. An unrun check must never read as a
        clean bill of health.
        """
        return []

    def panel_envelope(self) -> BBox:
        if self._tier is None:
            raise RuntimeError("place_panel() must be called before panel_envelope()")
        l, w, h = PANEL_TIERS[self._tier]
        return BBox(Vec3(0, 0, 0), Vec3(l, w, h))

    def screenshot(self, view: View, width: int = 1280, height: int = 960) -> bytes:
        self.screenshots_taken.append(view)
        return b""  # nothing to render; L4b skips when empty

    def export(self, fmt: str, path: str) -> str:
        return path
