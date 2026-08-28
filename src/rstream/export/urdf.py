"""L5 — URDF export. The design record, in the syntax a simulator reads.

This is a *renderer*, not a modelling step. The topology is already a link tree
with parents, joint types, driven lengths and per-module masses; a URDF is
exactly that plus XML. What this file adds is three things the tree does not
carry: primitive shapes, inertia tensors, and the actuator limits pulled from
the parts actually selected for each joint.

That last one is the point. Most hand-written URDFs carry invented `effort` and
`velocity` limits because nobody has picked a motor yet. Here the motor is
chosen, from a catalog, against a sized load — so the limits are the real
numbers off the part you would buy.

Deliberately NOT here:

* **Meshes.** Every link is a box. A box of the right size and mass is honest;
  a mesh we do not have would not be. When the CAD backend can export per-module
  geometry, only the ``<geometry>`` element changes.
* **Physics tuning.** No friction, damping, PID gains or contact parameters.
  This is kinematically faithful and dynamically approximate, and the header
  comment in every generated file says so.

A URDF that looks right in a simulator is not evidence the machine works. It
verifies reach, envelope and collision-free motion. It verifies nothing about
tolerance stack-up, wiring, thermal behaviour, backlash or control stability —
the same limits the concept animation carries.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.dom import minidom

from ..config import Configuration
from ..modules import ModuleKind

#: Minimum box edge, metres. A zero-length link would give a zero inertia tensor,
#: which most simulators accept and then behave strangely around.
MIN_EDGE_M = 0.01
#: Minimum link mass, kg. Gazebo refuses to simulate a zero-mass link.
MIN_MASS_KG = 0.01


class URDFError(RuntimeError):
    """The topology cannot be expressed as a valid URDF."""


@dataclass
class _Link:
    name: str
    size: tuple[float, float, float]
    mass_kg: float
    #: Offset of the box centre from the link origin. Links grow along one axis
    #: from their mount face, so the centre is half the extent along that axis.
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class _Joint:
    name: str
    kind: str
    parent: str
    child: str
    origin: tuple[float, float, float]
    axis: tuple[float, float, float] = (0.0, 1.0, 0.0)
    lower: float | None = None
    upper: float | None = None
    effort_nm: float = 0.0
    velocity: float = 0.0


def _box_inertia(mass: float, size: tuple[float, float, float]) -> tuple[float, float, float]:
    """Principal inertias of a uniform box. Concept-level and stated as such."""
    x, y, z = (max(v, MIN_EDGE_M) for v in size)
    c = mass / 12.0
    return (c * (y * y + z * z), c * (x * x + z * z), c * (x * x + y * y))


#: Wheel width, metres. Sets how far outboard of the chassis a wheel sits.
WHEEL_WIDTH_M = 0.03


def _resolved_size(inst) -> tuple[float, float, float]:
    f = inst.module.frame
    size = list(f.size)
    if f.size_param:
        size[f.size_axis] = float(inst.params.get(f.size_param, 0.0))
    if inst.module.id == "base.diffdrive":
        # Chassis spans the track minus a wheel either side, so the wheels are
        # outboard where they can touch the ground. The static 0.24 m width was
        # wider than a 0.20 m track, which put both wheels inside the body.
        track = float(inst.params.get("track_width_m", 0.30))
        size[1] = track - 2 * WHEEL_WIDTH_M
    return tuple(max(v, MIN_EDGE_M) for v in size)


def _child_offset(inst) -> tuple[float, float, float]:
    """Where this module's child mounts, in this module's frame."""
    f = inst.module.frame
    if inst.module.id == "base.diffdrive":
        # Whatever mounts on a rolling base mounts on top of the chassis, which
        # is itself a wheel radius off the ground.
        return (0.0, 0.0, _wheel_radius(inst) + _resolved_size(inst)[2])
    out = list(f.child_at)
    if f.child_param:
        d = float(inst.params.get(f.child_param, 0.0))
        for i, a in enumerate(f.child_along):
            out[i] += d * a
    return tuple(out)


def _wheel_radius(inst) -> float:
    return float(inst.params.get("wheel_dia_m", 0.10)) / 2.0


def _centre_of(inst) -> tuple[float, float, float]:
    """Box centre relative to the link origin.

    A link's origin is its mounting face, not its middle. Putting the centre of
    mass at the origin would move it half a link length toward the joint and
    quietly make every arm lighter to hold up than it is.
    """
    f = inst.module.frame
    size = _resolved_size(inst)
    if inst.module.id == "base.diffdrive":
        # The chassis rides ON the wheels. Deriving its centre from child_at the
        # generic way put the box across the axle line, so the wheels rendered
        # buried inside the body and the robot floated. Depends on wheel_dia, so
        # it cannot be a static constant on Frame.
        return (0.0, 0.0, _wheel_radius(inst) + size[2] / 2.0)
    if f.child_param:  # extends along child_along
        return tuple(size[i] / 2.0 * a for i, a in enumerate(f.child_along))
    if f.joint == "fixed" and f.child_at != (0.0, 0.0, 0.0):
        return tuple(v / 2.0 for v in f.child_at)
    return (0.0, 0.0, 0.0)


def _actuator_by_joint(config: Configuration, tier: str) -> dict:
    """joint label -> the catalog part selected for it."""
    out = {}
    for line in config.tiers[tier].lines:
        if line.part.actuator:
            for label in line.joints:
                out[label] = line.part
    return out


def _limits(inst, part) -> tuple[float, float, float, float]:
    """(lower, upper, effort, velocity) for one joint.

    Range comes from the module's driven parameter; effort and velocity come off
    the actuator that was actually chosen for this joint. Where no part was
    selected the limits are zero and the caller says so rather than inventing one.
    """
    span = float(inst.params.get("range_rad", 0.0)) or 3.14159
    lower, upper = -span / 2.0, span / 2.0
    if part is None or part.actuator is None:
        return lower, upper, 0.0, 0.0
    return lower, upper, part.actuator.rated_torque_nm, part.actuator.max_speed_rad_s


def _build(config: Configuration, tier: str) -> tuple[list[_Link], list[_Joint], list[str]]:
    topo = config.topology
    if topo is None or not topo.instances:
        raise URDFError("no topology to export")

    by_label = {i.label: i for i in topo.instances}
    actuators = _actuator_by_joint(config, tier)
    links: list[_Link] = []
    joints: list[_Joint] = []
    notes: list[str] = []

    roots = [i for i in topo.instances if i.parent is None]
    if not roots:
        raise URDFError("topology has no root: every module names a parent")
    root = roots[0]

    for inst in topo.instances:
        f = inst.module.frame
        size = _resolved_size(inst)
        mass = inst.module.mass_kg
        part = actuators.get(inst.label)
        if part is not None:
            # The motor is bolted to the joint it drives; its mass belongs there,
            # not spread over the arm.
            mass += part.mass_kg
        links.append(_Link(inst.label, size, max(mass, MIN_MASS_KG), _centre_of(inst)))

        if inst is root:
            continue
        if inst.parent is None:
            # A module off the kinematic tree (the control panel). It is still
            # part of the machine and still has mass, so it is bolted to the root
            # rather than dropped.
            joints.append(_Joint(f"{root.label}_to_{inst.label}", "fixed",
                                 root.label, inst.label, f.child_at))
            continue
        if inst.parent not in by_label:
            raise URDFError(f"{inst.label!r} mounts to {inst.parent!r}, which does not exist")

        origin = _child_offset(by_label[inst.parent])
        if f.joint == "fixed":
            joints.append(_Joint(f"{inst.parent}_to_{inst.label}", "fixed",
                                 inst.parent, inst.label, origin))
        else:
            lower, upper, effort, vel = _limits(inst, part)
            if part is None:
                notes.append(f"{inst.label}: no actuator selected — effort and velocity "
                             f"limits are 0, not a real rating")
            joints.append(_Joint(f"{inst.parent}_to_{inst.label}", f.joint,
                                 inst.parent, inst.label, origin, f.axis,
                                 lower, upper, effort, vel))

    # Modules whose DOF are not a link in the chain (wheels, gantry carriages).
    for inst in topo.instances:
        if inst.module.id == "base.diffdrive":
            links, joints, extra = _expand_diffdrive(inst, actuators, links, joints)
            notes.extend(extra)

    return links, joints, notes


def _expand_diffdrive(inst, actuators, links, joints):
    """Two wheels on continuous joints, one either side of the chassis.

    They are not in the chain — nothing mounts to a wheel — so the generic walk
    above cannot place them, and without them the base rolls on nothing.
    """
    track = float(inst.params.get("track_width_m", 0.30))
    dia = float(inst.params.get("wheel_dia_m", 0.10))
    part = actuators.get(inst.label)
    mass = (part.mass_kg if part else 0.2)
    effort = part.actuator.rated_torque_nm if part and part.actuator else 0.0
    vel = part.actuator.max_speed_rad_s if part and part.actuator else 0.0
    notes = []
    if part is None:
        notes.append(f"{inst.label}: no drive motor selected — wheel limits are 0")
    # Axles sit one wheel radius above the ground, which is where the root frame
    # is. Placing them at z=0 put the axle on the floor and sank the robot.
    for side, sign in (("left", 1.0), ("right", -1.0)):
        name = f"{inst.label}_wheel_{side}"
        links.append(_Link(name, (dia, WHEEL_WIDTH_M, dia), max(mass, MIN_MASS_KG)))
        joints.append(_Joint(f"{inst.label}_to_{name}", "continuous",
                             inst.label, name,
                             (0.0, sign * (track / 2.0), dia / 2.0),
                             (0.0, 1.0, 0.0), None, None, effort, vel))
    return links, joints, notes


def _reach_note(config: Configuration, joints: list[_Joint]) -> str | None:
    """Compare the model's actual X extent to the reach we quoted.

    `topology` splits reach into links that sum to slightly more than the figure
    the customer was given, so the simulated arm out-reaches the quoted one. That
    is a known open item; what is not acceptable is it being invisible. Anyone
    measuring the URDF should be told before they measure.
    """
    topo = config.topology
    quoted = topo and config.geometry_params.get("reach_m")
    if not quoted:
        return None
    # Only meaningful for something with an arm. A mobile base carries a reach
    # figure it never uses, and comparing against it reports a false 0.00x.
    if not any(i.module.kind is ModuleKind.LINK for i in topo.instances):
        return None
    # Furthest point along +X reachable through the tree. Summing every joint
    # origin instead would fold in the control panel hanging off the back.
    children: dict[str, list[_Joint]] = {}
    for j in joints:
        children.setdefault(j.parent, []).append(j)
    roots = {j.parent for j in joints} - {j.child for j in joints}

    def furthest(link: str, x: float) -> float:
        return max([x] + [furthest(j.child, x + j.origin[0])
                          for j in children.get(link, [])])

    extent = max((furthest(r, 0.0) for r in roots), default=0.0)
    if abs(extent - quoted) < 0.005:
        return None
    return (f"the model reaches {extent:.3f} m along +X, against a quoted reach of "
            f"{quoted:.3f} m ({extent / quoted:.2f}x) — link lengths sum to more than "
            f"the stated reach (see TODO.md)")


def _validate(links: list[_Link], joints: list[_Joint]) -> None:
    """Structural checks a simulator would otherwise fail on at load time.

    Cheap and exact, run before the file is written — the same order the rest of
    the validation layer uses.
    """
    names = [l.name for l in links]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise URDFError(f"duplicate link names: {sorted(dupes)}")

    known = set(names)
    for j in joints:
        for end in (j.parent, j.child):
            if end not in known:
                raise URDFError(f"joint {j.name!r} references unknown link {end!r}")

    children = [j.child for j in joints]
    redundant = {c for c in children if children.count(c) > 1}
    if redundant:
        raise URDFError(f"links with more than one parent: {sorted(redundant)}")

    orphans = known - set(children)
    if len(orphans) != 1:
        raise URDFError(f"a URDF needs exactly one root link, found {sorted(orphans)}")

    for l in links:
        if l.mass_kg <= 0:
            raise URDFError(f"link {l.name!r} has no mass; Gazebo will refuse it")


def _xml(links, joints, name, header) -> str:
    robot = ET.Element("robot", {"name": name})

    for l in links:
        link = ET.SubElement(robot, "link", {"name": l.name})
        origin = {"xyz": " ".join(f"{v:.6f}" for v in l.centre), "rpy": "0 0 0"}
        size = " ".join(f"{v:.6f}" for v in l.size)

        for tag in ("visual", "collision"):
            node = ET.SubElement(link, tag)
            ET.SubElement(node, "origin", origin)
            geom = ET.SubElement(node, "geometry")
            ET.SubElement(geom, "box", {"size": size})

        inertial = ET.SubElement(link, "inertial")
        ET.SubElement(inertial, "origin", origin)
        ET.SubElement(inertial, "mass", {"value": f"{l.mass_kg:.6f}"})
        ixx, iyy, izz = _box_inertia(l.mass_kg, l.size)
        ET.SubElement(inertial, "inertia", {
            "ixx": f"{ixx:.8f}", "ixy": "0", "ixz": "0",
            "iyy": f"{iyy:.8f}", "iyz": "0", "izz": f"{izz:.8f}"})

    for j in joints:
        node = ET.SubElement(robot, "joint", {"name": j.name, "type": j.kind})
        ET.SubElement(node, "parent", {"link": j.parent})
        ET.SubElement(node, "child", {"link": j.child})
        ET.SubElement(node, "origin", {
            "xyz": " ".join(f"{v:.6f}" for v in j.origin), "rpy": "0 0 0"})
        if j.kind != "fixed":
            ET.SubElement(node, "axis", {"xyz": " ".join(f"{v:.1f}" for v in j.axis)})
            limit = {"effort": f"{j.effort_nm:.4f}", "velocity": f"{j.velocity:.4f}"}
            if j.kind != "continuous":
                limit["lower"] = f"{j.lower:.6f}"
                limit["upper"] = f"{j.upper:.6f}"
            ET.SubElement(node, "limit", limit)

    pretty = minidom.parseString(ET.tostring(robot, "unicode")).toprettyxml(indent="  ")
    body = pretty.split("\n", 1)[1]          # drop minidom's own xml declaration
    return '<?xml version="1.0"?>\n' + header + body


def urdf_document(config: Configuration, tier: str, name: str = "concept") -> str:
    """Render a finished configuration as URDF. Raises rather than emitting a
    file a simulator will reject."""
    links, joints, notes = _build(config, tier)
    _validate(links, joints)
    reach = _reach_note(config, joints)
    if reach:
        notes.append(reach)

    dof = sum(1 for j in joints if j.kind != "fixed")
    lines = [
        "CONCEPT MODEL — generated, not engineered.",
        "",
        f"{len(links)} links, {dof} moving joints.",
        "Kinematically faithful: link lengths, joint ranges and the tree come from",
        "the sized design. Joint effort and velocity limits are the rated figures of",
        "the actuators actually selected from the catalog.",
        "",
        "Dynamically approximate: every link is a uniform box, so inertia tensors are",
        "shape estimates, not measurements. No friction, damping or contact tuning.",
        "",
        "Loading this in a simulator verifies reach, envelope and collision-free",
        "motion. It verifies nothing about tolerance stack-up, assembly, wiring,",
        "thermal behaviour, backlash or control stability on real hardware.",
    ]
    lines += [""] + [f"NOTE: {n}" for n in notes] if notes else []
    header = "<!--\n  " + "\n  ".join(lines) + "\n-->\n"
    return _xml(links, joints, name, header)
