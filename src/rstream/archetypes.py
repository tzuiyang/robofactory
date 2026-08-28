"""L0 — archetype library.

The AI does not generate geometry. It selects an archetype our engineers
authored and computes its driven parameters. That single decision is what makes
the output buildable: the archetype was designed by someone who has built one.

Each archetype declares the parameters it accepts and the envelope it is valid
within. Asking for a design outside every archetype's envelope is a legitimate
"we cannot do this" answer, and saying so is worth more than a plausible design
that fails on the shop floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParamRange:
    min: float
    max: float
    unit: str

    def contains(self, v: float) -> bool:
        return self.min <= v <= self.max


@dataclass(frozen=True)
class Archetype:
    id: str
    name: str
    description: str
    dof: int
    #: Driven parameters, SI. These become CADBackend.instantiate_archetype args.
    params: dict[str, ParamRange]
    #: Hard envelope the archetype is valid within.
    max_payload_kg: float
    max_reach_m: float
    #: Named slots on the arm/frame that catalog parts mount into.
    joint_slots: list[str] = field(default_factory=list)
    cad_template: str | None = None
    notes: str = ""

    def validate(self, payload_kg: float, reach_m: float) -> list[str]:
        """Return reasons this archetype does not fit. Empty list == fits."""
        problems = []
        if payload_kg > self.max_payload_kg:
            problems.append(
                f"payload {payload_kg} kg exceeds {self.id} limit of {self.max_payload_kg} kg"
            )
        if reach_m > self.max_reach_m:
            problems.append(
                f"reach {reach_m} m exceeds {self.id} limit of {self.max_reach_m} m"
            )
        return problems


ARCHETYPES: dict[str, Archetype] = {
    "arm.3dof": Archetype(
        id="arm.3dof",
        name="Fixed-base 3-DOF arm",
        description="Shoulder/elbow/wrist revolute arm on a fixed base. Bench-top pick and place.",
        dof=3,
        params={
            "reach_m": ParamRange(0.20, 0.80, "m"),
            "base_height_m": ParamRange(0.05, 0.30, "m"),
            "link1_m": ParamRange(0.10, 0.45, "m"),
            "link2_m": ParamRange(0.10, 0.40, "m"),
        },
        max_payload_kg=3.0,
        max_reach_m=0.80,
        joint_slots=["shoulder", "elbow", "wrist"],
        notes="TEMPLATE NOT YET AUTHORED — see open question #6 in log.md.",
    ),
    "gantry.xy": Archetype(
        id="gantry.xy",
        name="Cartesian XY gantry",
        description="Two-axis overhead gantry with vertical Z. Rectangular work area, high repeatability.",
        dof=3,
        params={
            "x_travel_m": ParamRange(0.20, 1.50, "m"),
            "y_travel_m": ParamRange(0.20, 1.00, "m"),
            "z_travel_m": ParamRange(0.05, 0.40, "m"),
            "frame_height_m": ParamRange(0.30, 1.20, "m"),
        },
        max_payload_kg=5.0,
        max_reach_m=1.50,
        joint_slots=["x_axis", "y_axis", "z_axis"],
        notes="TEMPLATE NOT YET AUTHORED — see open question #6 in log.md.",
    ),
    "scara.tabletop": Archetype(
        id="scara.tabletop",
        name="Tabletop SCARA",
        description="Two revolute joints in a horizontal plane plus vertical Z. Fast planar pick and place.",
        dof=4,
        params={
            "reach_m": ParamRange(0.15, 0.60, "m"),
            "z_travel_m": ParamRange(0.05, 0.25, "m"),
            "link1_m": ParamRange(0.08, 0.35, "m"),
            "link2_m": ParamRange(0.07, 0.30, "m"),
        },
        max_payload_kg=2.0,
        max_reach_m=0.60,
        joint_slots=["j1", "j2", "z", "theta"],
        notes="TEMPLATE NOT YET AUTHORED — see open question #6 in log.md.",
    ),
}


def candidates(payload_kg: float, reach_m: float) -> list[Archetype]:
    """Archetypes whose envelope admits this problem, cheapest-envelope first."""
    fitting = [a for a in ARCHETYPES.values() if not a.validate(payload_kg, reach_m)]
    return sorted(fitting, key=lambda a: (a.max_payload_kg, a.max_reach_m))
