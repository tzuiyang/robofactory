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


@dataclass(frozen=True)
class Frame:
    """Where a module sits in the kinematic tree, and how big it is.

    Authored per module, like the geometry itself — this is the "engineer decides"
    side of the split, not something the AI picks. It is what lets a topology be
    exported as a URDF without anyone drawing anything.

    * ``joint`` / ``axis`` — the URDF joint connecting this module to its parent.
    * ``child_at`` (+ ``child_param`` along ``child_along``) — where this module's
      own child mounts, in this module's frame. A link's child sits at the far end
      of the link, so its offset is driven by ``length_m``.
    * ``size`` (+ ``size_param`` on ``size_axis``) — the primitive box used for
      visual, collision and inertia. Concept-level on purpose: a box the right
      size and mass is honest, a mesh we do not have would not be.

    Axis convention: the arm is PLANAR AND VERTICAL — every revolute joint
    pitches about +Y and links extend along +X. That is not a simplification of
    the design, it is the design `sizing.chain_loads` already assumes when it
    treats every joint as a gravity cantilever. A base yaw would be a fourth DOF
    and a topology change, not an export decision.
    """

    joint: str = "fixed"                       # fixed | revolute | continuous | prismatic
    axis: tuple[float, float, float] = (0.0, 1.0, 0.0)
    child_at: tuple[float, float, float] = (0.0, 0.0, 0.0)
    child_along: tuple[float, float, float] = (1.0, 0.0, 0.0)
    child_param: str | None = None
    size: tuple[float, float, float] = (0.06, 0.06, 0.06)
    size_param: str | None = None
    size_axis: int = 0


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
    #: Kinematic placement and primitive size. Defaults to a fixed 60 mm cube,
    #: which is wrong for anything real — every module in LIBRARY sets its own.
    frame: Frame = field(default_factory=Frame)

    @property
    def authored(self) -> bool:
        """Has an engineer built the parametric CAD for this module yet?"""
        return self.cad_template is not None


LIBRARY: dict[str, Module] = {
    m.id: m
    for m in [
        Module("base.fixed", ModuleKind.BASE, "Bolted stationary base",
               Interface.GROUND, Interface.BASE_TOP, mass_kg=2.0,
               frame=Frame(child_at=(0.0, 0.0, 0.08), size=(0.18, 0.18, 0.08))),
        Module("base.diffdrive", ModuleKind.DRIVE, "Two-wheel differential drive base",
               Interface.GROUND, Interface.BASE_TOP, dof=2,
               params={"track_width_m": (0.15, 0.60), "wheel_dia_m": (0.05, 0.25)},
               consumes_kinds=["actuator", "driver", "wheel", "battery"],
               supplies=[Capability.MOBILITY], mass_kg=4.0,
               # The 2 DOF are the two wheels, which hang off the chassis rather
               # than sitting in the chain — expanded explicitly by the exporter.
               frame=Frame(child_at=(0.0, 0.0, 0.12), size=(0.30, 0.24, 0.10))),
        Module("base.gantry", ModuleKind.BASE, "Cartesian XY gantry frame",
               Interface.GROUND, Interface.LINK_END, dof=2,
               params={"x_travel_m": (0.2, 1.5), "y_travel_m": (0.2, 1.0)},
               consumes_kinds=["actuator", "driver"], mass_kg=12.0,
               # 2 prismatic DOF, also expanded explicitly.
               frame=Frame(child_at=(0.0, 0.0, 0.90), size=(1.0, 0.8, 0.06))),
        Module("joint.revolute", ModuleKind.JOINT, "Single revolute joint",
               Interface.BASE_TOP, Interface.JOINT_OUT, dof=1,
               params={"range_rad": (1.0, 6.28)},
               consumes_kinds=["actuator", "driver", "sensor"], mass_kg=0.6,
               # Child mounts ON the axis, not past it. An offset here would add
               # to the arm's reach without adding to the moment arm the sizing
               # used, so the simulated arm would out-reach the quoted one.
               frame=Frame(joint="revolute", axis=(0.0, 1.0, 0.0),
                           child_at=(0.0, 0.0, 0.0), size=(0.08, 0.08, 0.08))),
        Module("joint.revolute.inline", ModuleKind.JOINT, "Revolute joint on a link end",
               Interface.LINK_END, Interface.JOINT_OUT, dof=1,
               params={"range_rad": (1.0, 6.28)},
               consumes_kinds=["actuator", "driver", "sensor"], mass_kg=0.6,
               # Child mounts ON the axis, not past it. An offset here would add
               # to the arm's reach without adding to the moment arm the sizing
               # used, so the simulated arm would out-reach the quoted one.
               frame=Frame(joint="revolute", axis=(0.0, 1.0, 0.0),
                           child_at=(0.0, 0.0, 0.0), size=(0.08, 0.08, 0.08))),
        Module("link.rigid", ModuleKind.LINK, "Structural link, extrusion",
               Interface.JOINT_OUT, Interface.LINK_END,
               params={"length_m": (0.05, 0.60)}, mass_kg=0.4,
               frame=Frame(child_param="length_m", child_along=(1.0, 0.0, 0.0),
                           size=(0.0, 0.04, 0.04), size_param="length_m", size_axis=0)),
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
                         Capability.ONBOARD_COMPUTE], mass_kg=0.8,
               frame=Frame(child_param="height_m", child_along=(0.0, 0.0, 1.0),
                           size=(0.10, 0.10, 0.0), size_param="height_m", size_axis=2)),
        Module("effector.gripper", ModuleKind.EFFECTOR, "Gripper mount + end effector",
               Interface.LINK_END, Interface.TOOL,
               consumes_kinds=["end_effector"],
               supplies=[Capability.GRASPING], mass_kg=0.5,
               frame=Frame(size=(0.11, 0.10, 0.05))),
        Module("effector.vacuum", ModuleKind.EFFECTOR, "Vacuum mount, for sheet/fabric",
               Interface.LINK_END, Interface.TOOL,
               consumes_kinds=["end_effector"],
               supplies=[Capability.GRASPING, Capability.FLAT_MATERIAL_HANDLING], mass_kg=0.4,
               frame=Frame(size=(0.08, 0.08, 0.06))),
        Module("panel.control", ModuleKind.PANEL, "Control panel enclosure (S/M/L tier)",
               Interface.NONE, Interface.NONE,
               consumes_kinds=["controller", "driver", "psu"], mass_kg=1.5,
               # Sits behind the base, not inside it: the panel is off the
               # kinematic tree and defaulted to the origin, which put a 240 mm
               # box through the middle of the base and self-collided on load.
               frame=Frame(child_at=(-0.22, 0.0, 0.06), size=(0.24, 0.18, 0.12))),
    ]
}


def supplying(cap: Capability) -> list[Module]:
    return [m for m in LIBRARY.values() if cap in m.supplies]
