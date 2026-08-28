"""L3 geometry layer. Import backends through here, never by CAD-specific path."""

from .base import CADBackend, PlacedPart
from .geom import BBox, Clash, MassProperties, Measurements, Vec3, View
from .null import PANEL_TIERS, NullBackend


def get_backend(name: str) -> CADBackend:
    """Backend factory — the single place a backend is chosen.

    Swapping CAD systems later is a change to this function plus one new module.
    """
    if name == "null":
        return NullBackend()
    if name == "fusion":
        from .fusion import FusionBackend

        return FusionBackend()
    raise ValueError(f"unknown CAD backend {name!r} (have: null, fusion)")


__all__ = [
    "CADBackend", "PlacedPart", "NullBackend", "PANEL_TIERS", "get_backend",
    "BBox", "Clash", "MassProperties", "Measurements", "Vec3", "View",
]
