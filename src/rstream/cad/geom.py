"""Backend-neutral geometry types.

These are the ONLY types allowed to cross the CADBackend boundary. No Fusion
(``adsk.*``), Onshape, or OpenCascade type may appear in a signature outside its
own adapter module. That rule is what keeps the backend swappable.

Units are SI throughout: metres, kilograms, seconds, radians. Fusion's internal
unit is centimetres, so the Fusion adapter converts at its boundary and nowhere
else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __iter__(self):
        yield from (self.x, self.y, self.z)


@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box, metres."""

    min: Vec3
    max: Vec3

    @property
    def size(self) -> Vec3:
        return Vec3(self.max.x - self.min.x, self.max.y - self.min.y, self.max.z - self.min.z)

    @property
    def volume_m3(self) -> float:
        s = self.size
        return s.x * s.y * s.z

    def fits_inside(self, other: "BBox", clearance_m: float = 0.0) -> bool:
        """Can this box fit inside ``other``, allowing ``clearance_m`` on every side?

        Axis-aligned only — no rotation search. Deliberate: panel slots have a
        fixed orientation, so a rotating fit would be answering a question we do
        not ask.
        """
        a, b = self.size, other.size
        pad = 2 * clearance_m
        return a.x + pad <= b.x and a.y + pad <= b.y and a.z + pad <= b.z


@dataclass(frozen=True)
class MassProperties:
    mass_kg: float
    center_of_mass: Vec3
    volume_m3: float


@dataclass(frozen=True)
class Clash:
    """One interference pair from the deterministic gate (L4a)."""

    body_a: str
    body_b: str
    volume_m3: float

    def __str__(self) -> str:
        return f"{self.body_a} intersects {self.body_b} ({self.volume_m3 * 1e6:.1f} cm^3)"


class View(str, Enum):
    """Standard capture directions for the vision gate (L4b)."""

    FRONT = "front"
    TOP = "top"
    RIGHT = "right"
    ISO = "iso-top-right"


@dataclass(frozen=True)
class Measurements:
    """Everything the deterministic gate needs, read back from the model."""

    bbox: BBox
    mass: MassProperties
    body_count: int
