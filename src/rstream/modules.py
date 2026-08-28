"""L0 — module library. The generalization of fixed archetypes.

A module is a parametric building block an engineer authored once: a drive base,
a revolute joint, a link, a head, a control panel, an end-effector mount. Robots
are *compositions* of modules, so a laundry folder and a rolling talking robot
are different topologies over one library rather than two separate products.

The split that makes this work:

    AI decides   -> which modules, how many, in what chain, and their parameters
                    (discrete reasoning + arithmetic — tractable)
    Engineer authors -> each module's geometry and mounting interfaces
                    (continuous spatial design — not tractable for an LLM)

Modules connect only through declared interfaces. Two modules whose interfaces
do not match cannot be composed, which makes an unbuildable chain impossible to
express rather than merely discouraged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .capabilities import Capability


class Interface(str, Enum):
    """Mechanical mating standards. A chain is valid only if adjacent interfaces
    match — this is the buildability constraint, expressed in the type system."""

    GROUND = "ground"          # sits on the floor/bench
    BASE_TOP = "base_top"      # top face of a base
    JOINT_OUT = "joint_out"    # rotating output of a joint
    LINK_END = "link_end"      # far end of a structural link
    TOOL = "tool"              # end-effector mount
    NONE = "none"              # terminal


class ModuleKind(str, Enum):
    BASE = "base"
    DRIVE = "drive"
    JOINT = "joint"
    LINK = "link"
    HEAD = "head"
    PANEL = "panel"
    EFFECTOR = "effector"


@dataclass(frozen=True)
class Module:
    id: str
    kind: ModuleKind
    description: str
    accepts: Interface
    provides: Interface
    #: Degrees of freedom this module contributes.
    dof: int = 0
    #: Driven parameters, SI. Become CADBackend.instantiate args.
    params: dict[str, tuple[float, float]] = field(default_factory=dict)
    #: Catalog part kinds this module ALWAYS requires.
    consumes_kinds: list[str] = field(default_factory=list)
    #: Part kinds required only when a given capability was actually requested.
    #: Without this a sensor head buys a camera for a robot that only talks.
    capability_kinds: dict[Capability, list[str]] = field(default_factory=dict)
    #: Capabilities this module supplies.
    supplies: list[Capability] = field(default_factory=list)
    mass_kg: float = 0.0
    cad_template: str | None = None

    @property
    def authored(self) -> bool:
        """Has an engineer built the parametric CAD for this module yet?"""
        return self.cad_template is not None


LIBRARY: dict[str, Module] = {
    m.id: m
    for m in [
        Module("base.fixed", ModuleKind.BASE, "Bolted stationary base",
               Interface.GROUND, Interface.BASE_TOP, mass_kg=2.0),
        Module("base.diffdrive", ModuleKind.DRIVE, "Two-wheel differential drive base",
               Interface.GROUND, Interface.BASE_TOP, dof=2,
               params={"track_width_m": (0.15, 0.60), "wheel_dia_m": (0.05, 0.25)},
               consumes_kinds=["actuator", "driver", "wheel", "battery"],
               supplies=[Capability.MOBILITY], mass_kg=4.0),
        Module("base.gantry", ModuleKind.BASE, "Cartesian XY gantry frame",
               Interface.GROUND, Interface.LINK_END, dof=2,
               params={"x_travel_m": (0.2, 1.5), "y_travel_m": (0.2, 1.0)},
               consumes_kinds=["actuator", "driver"], mass_kg=12.0),
        Module("joint.revolute", ModuleKind.JOINT, "Single revolute joint",
               Interface.BASE_TOP, Interface.JOINT_OUT, dof=1,
               params={"range_rad": (1.0, 6.28)},
               consumes_kinds=["actuator", "driver", "sensor"], mass_kg=0.6),
        Module("joint.revolute.inline", ModuleKind.JOINT, "Revolute joint on a link end",
               Interface.LINK_END, Interface.JOINT_OUT, dof=1,
               params={"range_rad": (1.0, 6.28)},
               consumes_kinds=["actuator", "driver", "sensor"], mass_kg=0.6),
        Module("link.rigid", ModuleKind.LINK, "Structural link, extrusion",
               Interface.JOINT_OUT, Interface.LINK_END,
               params={"length_m": (0.05, 0.60)}, mass_kg=0.4),
        Module("head.sensor", ModuleKind.HEAD, "Sensor/interaction head",
               Interface.BASE_TOP, Interface.NONE, dof=0,
               params={"height_m": (0.05, 0.50)},
               consumes_kinds=["compute_module"],
               capability_kinds={
                   Capability.AUDIO_OUT: ["speaker", "audio_amp"],
                   Capability.AUDIO_IN: ["microphone"],
                   Capability.VISION: ["camera"],
               },
               supplies=[Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.VISION,
                         Capability.ONBOARD_COMPUTE], mass_kg=0.8),
        Module("effector.gripper", ModuleKind.EFFECTOR, "Gripper mount + end effector",
               Interface.LINK_END, Interface.TOOL,
               consumes_kinds=["end_effector"],
               supplies=[Capability.GRASPING], mass_kg=0.5),
        Module("effector.vacuum", ModuleKind.EFFECTOR, "Vacuum mount, for sheet/fabric",
               Interface.LINK_END, Interface.TOOL,
               consumes_kinds=["end_effector"],
               supplies=[Capability.GRASPING, Capability.FLAT_MATERIAL_HANDLING], mass_kg=0.4),
        Module("panel.control", ModuleKind.PANEL, "Control panel enclosure (S/M/L tier)",
               Interface.NONE, Interface.NONE,
               consumes_kinds=["controller", "driver", "psu"], mass_kg=1.5),
    ]
}


def supplying(cap: Capability) -> list[Module]:
    return [m for m in LIBRARY.values() if cap in m.supplies]
