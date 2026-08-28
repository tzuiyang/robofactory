"""L0 — catalog schema.

The catalog is the core asset and the moat: 100-300 parts the team actually
uses, with real prices and real specs, curated by hand. It is not generated and
it is never researched at runtime.

Two rules are enforced here in code rather than in prose, because prose rules
get violated at 2am:

1. ``verified`` — a part a human has not confirmed cannot be quoted from.
   Seed and draft entries default to False and the store refuses to return them
   unless explicitly asked. This is the enforcement of "never invent a part
   number".
2. ``keepout`` — every component carries a clearance volume, not just its body
   size. Connectors need room. A BOM that fits on paper and not in the panel is
   the expensive kind of wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PartKind(str, Enum):
    ACTUATOR = "actuator"
    CONTROLLER = "controller"
    DRIVER = "driver"
    PSU = "psu"
    SENSOR = "sensor"
    STRUCTURE = "structure"
    END_EFFECTOR = "end_effector"
    FASTENER = "fastener"
    CABLE = "cable"
    # Kinds the module library asks for. A kind absent here is rejected at
    # catalog load, which is why a wheeled robot's BOM had holes rather than
    # wrong parts — the guardrail worked, the catalog just had not caught up.
    WHEEL = "wheel"
    BATTERY = "battery"


class ActuatorRole(str, Enum):
    """What an actuator is *for*, not just how strong it is.

    Torque alone does not make two motors interchangeable. A continuous-rotation
    drive gearmotor has no absolute position feedback and usually no brake, so it
    cannot hold a revolute joint against gravity; a high-ratio joint servo is
    strong but far too slow to drive a wheel. Selection on torque alone put a
    wheel gearmotor in an arm elbow (log.md, 2026-08-28) — the BOM looked fine
    and the machine was unbuildable.
    """

    JOINT = "joint"
    DRIVE = "drive"


@dataclass(frozen=True)
class Dimensions:
    """Millimetres. Body is the physical part; keepout adds connector/airflow
    clearance and is what panel fitting actually uses."""

    length_mm: float
    width_mm: float
    height_mm: float
    keepout_length_mm: float = 0.0
    keepout_width_mm: float = 0.0
    keepout_height_mm: float = 0.0

    def __post_init__(self) -> None:
        for f in ("length_mm", "width_mm", "height_mm"):
            if getattr(self, f) <= 0:
                raise ValueError(f"{f} must be > 0")

    @property
    def envelope_mm(self) -> tuple[float, float, float]:
        return (
            self.length_mm + self.keepout_length_mm,
            self.width_mm + self.keepout_width_mm,
            self.height_mm + self.keepout_height_mm,
        )

    @property
    def envelope_volume_m3(self) -> float:
        l, w, h = self.envelope_mm
        return (l * w * h) * 1e-9


@dataclass(frozen=True)
class ActuatorSpec:
    """Only the numbers L2 sizing actually consumes."""

    stall_torque_nm: float
    rated_torque_nm: float
    max_speed_rad_s: float
    gear_ratio: float = 1.0
    voltage_v: float = 12.0
    peak_current_a: float = 0.0
    #: Defaults to JOINT: a part the curator did not mark is assumed to be an
    #: articulation servo, which is the conservative reading — a drive motor
    #: wrongly left unmarked shows up as a too-slow wheel, not as an elbow that
    #: cannot hold position.
    role: ActuatorRole = ActuatorRole.JOINT


@dataclass(frozen=True)
class Geometry:
    """Normalized STEP reference. STL is deliberately not supported.

    A mesh has no planar face to mate or joint against, and vendor STLs carry
    inconsistent units, arbitrary origins and no mounting datum. Normalization
    (origin at mounting-face centre, explicit mounting frame, bolt pattern) is
    ~10-20 min of human work per part, done once, at catalog-entry time.
    """

    step_path: str | None = None
    origin_datum: str = "mounting_face_center"
    bolt_pattern: str | None = None
    cable_exit: str | None = None
    needs_airflow: bool = False

    def __post_init__(self) -> None:
        if self.step_path and self.step_path.lower().endswith((".stl", ".obj")):
            raise ValueError(
                f"mesh formats are not accepted in the catalog: {self.step_path!r}. "
                "Use STEP — a mesh has no face to mate against."
            )


@dataclass(frozen=True)
class Part:
    id: str
    kind: PartKind
    manufacturer: str
    part_number: str
    description: str
    price_usd: float
    dimensions: Dimensions
    mass_kg: float
    actuator: ActuatorSpec | None = None
    geometry: Geometry = field(default_factory=Geometry)
    lead_time_days: int | None = None
    source_url: str | None = None
    #: Has a human confirmed part number, price and specs against the vendor?
    #: Unverified parts cannot reach a customer-facing BOM.
    verified: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.price_usd < 0:
            raise ValueError("price_usd must be >= 0")
        if self.kind is PartKind.ACTUATOR and self.actuator is None:
            raise ValueError(f"actuator part {self.id!r} must carry an ActuatorSpec")
