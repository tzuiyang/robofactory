"""L2a — topology synthesis. "How many DOF and which modules" decided here.

This is the layer that makes the app general. Given a capability set and a task
scale, it composes a valid module chain and reports its DOF. It does not create
geometry — every module in the chain was authored by an engineer.

Validity is structural: adjacent modules must have matching interfaces, so an
unbuildable chain cannot be represented rather than merely being discouraged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .capabilities import Capability, expand
from .modules import LIBRARY, Interface, Module, ModuleKind


class TopologyError(RuntimeError):
    """No valid composition exists for this request."""


@dataclass
class ModuleInstance:
    module: Module
    params: dict[str, float] = field(default_factory=dict)
    label: str = ""
    #: Label of the module this one mounts to. None = mounts to ground.
    #: Topology is a TREE, not a chain: a sensor head and a manipulator arm both
    #: branch off the base. Modelling it as a chain makes a mobile manipulator
    #: with a head impossible to express.
    parent: str | None = None


@dataclass
class Topology:
    instances: list[ModuleInstance] = field(default_factory=list)
    capabilities: set[Capability] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    @property
    def dof(self) -> int:
        return sum(i.module.dof for i in self.instances)

    @property
    def joint_slots(self) -> list[str]:
        return [i.label for i in self.instances if i.module.dof > 0]

    @property
    def consumes_kinds(self) -> set[str]:
        """Part kinds this topology needs.

        Capability-gated kinds are included only when that capability was
        actually requested — otherwise a robot that only talks also buys a camera.
        """
        k: set[str] = set()
        for i in self.instances:
            k.update(i.module.consumes_kinds)
            for cap, kinds in i.module.capability_kinds.items():
                if cap in self.capabilities:
                    k.update(kinds)
        return k

    @property
    def est_mass_kg(self) -> float:
        return sum(i.module.mass_kg for i in self.instances)

    @property
    def unauthored(self) -> list[str]:
        """Modules with no parametric CAD yet. Blocks L3, not L2."""
        return sorted({i.module.id for i in self.instances if not i.module.authored})

    def validate(self) -> list[str]:
        """Interface continuity across the mounting tree.

        Each module must mate with its declared parent. Modules with no parent
        must sit on the ground. Panels are free-standing enclosures and are
        exempt from the kinematic tree.
        """
        problems = []
        by_label = {i.label: i for i in self.instances}
        for inst in self.instances:
            if inst.module.kind is ModuleKind.PANEL:
                continue
            if inst.parent is None:
                if inst.module.accepts is not Interface.GROUND:
                    problems.append(
                        f"{inst.module.id} ({inst.label}) needs "
                        f"{inst.module.accepts.value} but mounts to nothing"
                    )
                continue
            parent = by_label.get(inst.parent)
            if parent is None:
                problems.append(f"{inst.label} declares unknown parent {inst.parent!r}")
                continue
            if inst.module.accepts is not parent.module.provides:
                problems.append(
                    f"{parent.module.id} ({parent.label}) provides "
                    f"{parent.module.provides.value} but {inst.module.id} "
                    f"({inst.label}) accepts {inst.module.accepts.value} — cannot mate"
                )
        return problems

    def describe(self) -> str:
        """Render the tree, showing branches."""
        parts = []
        for i in self.instances:
            if i.module.kind is ModuleKind.PANEL:
                continue
            parts.append(i.label if i.parent else f"[{i.label}]")
        return f"{self.dof} DOF: " + " -> ".join(parts)

    def tree(self) -> str:
        lines = []
        by_parent: dict[str | None, list[ModuleInstance]] = {}
        for i in self.instances:
            by_parent.setdefault(i.parent, []).append(i)

        def walk(parent: str | None, depth: int) -> None:
            for i in by_parent.get(parent, []):
                dof = f"  [{i.module.dof} DOF]" if i.module.dof else ""
                lines.append("  " * depth + f"- {i.label} ({i.module.id}){dof}")
                walk(i.label, depth + 1)

        walk(None, 0)
        return "\n".join(lines)


def _add(topo: Topology, module_id: str, label: str = "",
         parent: str | None = None, **params) -> None:
    m = LIBRARY[module_id]
    topo.instances.append(ModuleInstance(m, params, label or m.id, parent))


def synthesize(
    caps: set[Capability],
    payload_kg: float = 0.0,
    reach_m: float = 0.0,
    workspace_is_planar: bool = False,
) -> Topology:
    """Compose a module chain that supplies the requested capabilities.

    Deliberately rule-based rather than model-driven. Topology is a discrete
    choice with a small valid space; a table of rules is auditable, repeatable
    and explains itself, where an LLM here would be none of those. The LLM's job
    is upstream — turning "a robot that folds laundry" into the capability set.
    """
    caps = expand(caps)
    topo = Topology(capabilities=caps)

    needs_manip = Capability.MANIPULATION in caps
    needs_mobile = Capability.MOBILITY in caps

    # --- base (root of the tree) ---------------------------------------
    if needs_mobile:
        _add(topo, "base.diffdrive", "drive_base",
             track_width_m=max(0.20, reach_m * 0.6), wheel_dia_m=0.10)
        base = "drive_base"
    elif needs_manip and workspace_is_planar:
        _add(topo, "base.gantry", "gantry",
             x_travel_m=max(0.2, reach_m), y_travel_m=max(0.2, reach_m * 0.7))
        base = "gantry"
    else:
        _add(topo, "base.fixed", "base")
        base = "base"

    # --- manipulator branch --------------------------------------------
    tip = base
    if needs_manip and not workspace_is_planar:
        # Three revolute joints is the minimum that both positions AND orients a
        # tool in a plane; with fewer, the approach angle is whatever the
        # geometry happens to give, which fails on any task needing a specific
        # approach (inserting, stacking, placing into a fixture).
        # Shares sum to 1.00, so the arm reaches exactly what was quoted. They used
        # to be 0.55 / 0.45 / 0.08 = 1.08, which over-reached by 8% and made every
        # moment arm 8% long — and the 0.08 share gave a 28 mm wrist link on a
        # 0.35 m arm, shorter than the motor driving it and unbuildable.
        _add(topo, "joint.revolute", "shoulder", parent=tip); tip = "shoulder"
        _add(topo, "link.rigid", "upper_link", parent=tip, length_m=reach_m * 0.50); tip = "upper_link"
        _add(topo, "joint.revolute.inline", "elbow", parent=tip); tip = "elbow"
        _add(topo, "link.rigid", "fore_link", parent=tip, length_m=reach_m * 0.36); tip = "fore_link"
        _add(topo, "joint.revolute.inline", "wrist", parent=tip); tip = "wrist"
        _add(topo, "link.rigid", "wrist_link", parent=tip, length_m=reach_m * 0.14); tip = "wrist_link"
    elif needs_manip and workspace_is_planar:
        _add(topo, "joint.revolute.inline", "z_axis", parent=tip); tip = "z_axis"
        _add(topo, "link.rigid", "z_column", parent=tip,
             length_m=min(0.4, max(0.1, reach_m * 0.4))); tip = "z_column"

    # --- end effector (tip of the manipulator branch) --------------------
    if Capability.GRASPING in caps:
        eff = ("effector.vacuum" if Capability.FLAT_MATERIAL_HANDLING in caps
               else "effector.gripper")
        _add(topo, eff, "end_effector", parent=tip)
        if eff == "effector.vacuum":
            topo.notes.append(
                "vacuum end effector selected for flat/fabric material — a parallel "
                "gripper cannot reliably pick a single layer of cloth"
            )

    # --- interaction head: a SEPARATE branch off the base ----------------
    # Not on the arm tip: a head mounted past a gripper would ride along with
    # every pick, and cannot mate to a tool interface anyway.
    head_caps = {Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.VISION}
    if caps & head_caps:
        if LIBRARY["head.sensor"].accepts is LIBRARY[
                {"drive_base": "base.diffdrive", "gantry": "base.gantry",
                 "base": "base.fixed"}[base]].provides:
            _add(topo, "head.sensor", "head", parent=base, height_m=0.15)
        else:
            topo.notes.append(
                f"sensors mounted directly to the {base} frame; the head module "
                "cannot mate to this base type")

    # --- control panel (free-standing enclosure) -------------------------
    _add(topo, "panel.control", "control_panel")

    problems = topo.validate()
    if problems:
        raise TopologyError(
            "synthesized chain is not mechanically valid: " + "; ".join(problems)
        )
    if not topo.instances:
        raise TopologyError("no modules matched the requested capabilities")
    return topo
