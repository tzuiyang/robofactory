"""L2 — sizing formulas.

Deliberately pure functions with no LLM in the path. The governing principle is
"the LLM proposes, deterministic code disposes": an LLM may choose the archetype
and interpret the customer's intent, but it never does the arithmetic that
decides whether an actuator is big enough.

Units are SI everywhere. Every returned quantity carries the assumption that
produced it, because an unstated safety factor is how a quote becomes a loss.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.80665  # m/s^2

#: Default torque safety factor. Conservative is free at proposal stage;
#: optimistic is expensive. Always surfaced in the output, never hidden.
DEFAULT_SAFETY_FACTOR = 2.5


@dataclass(frozen=True)
class TorqueEstimate:
    static_nm: float
    dynamic_nm: float
    required_nm: float
    safety_factor: float
    assumptions: list[str] = field(default_factory=list)


def joint_torque(
    payload_kg: float,
    reach_m: float,
    link_mass_kg: float,
    accel_rad_s2: float = 2.0,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
) -> TorqueEstimate:
    """Worst-case torque at the shoulder of a revolute arm, fully extended.

    Static term  : gravity on payload at full reach + link mass at its centroid.
                   tau = g * (m_pay * L + m_link * L/2)
    Dynamic term : tau = I * alpha, with the link modelled as a uniform rod
                   about its end (I = 1/3 m L^2) plus the payload as a point
                   mass (I = m L^2).

    Horizontal full extension is the worst case for a revolute shoulder, which is
    why it is the sizing case. This does NOT model friction, gearbox efficiency,
    or duty-cycle thermal derating — those are covered by the safety factor and
    must be checked by an engineer before the design is built.
    """
    if payload_kg < 0 or reach_m <= 0 or link_mass_kg < 0:
        raise ValueError("payload_kg >= 0, link_mass_kg >= 0, reach_m > 0 required")

    static = G * (payload_kg * reach_m + link_mass_kg * reach_m / 2.0)
    inertia = payload_kg * reach_m**2 + (link_mass_kg * reach_m**2) / 3.0
    dynamic = inertia * accel_rad_s2

    return TorqueEstimate(
        static_nm=static,
        dynamic_nm=dynamic,
        required_nm=(static + dynamic) * safety_factor,
        safety_factor=safety_factor,
        assumptions=[
            "worst case: arm horizontal, fully extended",
            f"angular acceleration {accel_rad_s2} rad/s^2",
            "link modelled as uniform rod about its end",
            "excludes friction, gearbox efficiency and thermal derating "
            f"(covered by the {safety_factor}x safety factor)",
        ],
    )


@dataclass(frozen=True)
class MoveTime:
    seconds: float
    profile: str  # "triangular" | "trapezoidal"


def move_time(distance_m: float, max_speed_m_s: float, accel_m_s2: float) -> MoveTime:
    """Point-to-point time under a trapezoidal velocity profile.

    Falls back to a triangular profile when the move is too short to reach
    max speed — which is most short pick-and-place moves, and getting this
    wrong is the usual reason a quoted cycle time is optimistic.
    """
    if distance_m < 0 or max_speed_m_s <= 0 or accel_m_s2 <= 0:
        raise ValueError("distance_m >= 0, max_speed_m_s > 0, accel_m_s2 > 0 required")
    if distance_m == 0:
        return MoveTime(0.0, "triangular")

    d_to_peak = max_speed_m_s**2 / accel_m_s2  # accel + decel distance
    if distance_m <= d_to_peak:
        return MoveTime(2.0 * math.sqrt(distance_m / accel_m_s2), "triangular")

    t_ramp = 2.0 * max_speed_m_s / accel_m_s2
    t_cruise = (distance_m - d_to_peak) / max_speed_m_s
    return MoveTime(t_ramp + t_cruise, "trapezoidal")


@dataclass(frozen=True)
class CycleEstimate:
    seconds_per_cycle: float
    parts_per_hour: float
    breakdown: dict[str, float]
    assumptions: list[str] = field(default_factory=list)


def cycle_time(
    pick_travel_m: float,
    place_travel_m: float,
    max_speed_m_s: float = 0.5,
    accel_m_s2: float = 2.0,
    grip_time_s: float = 0.35,
    release_time_s: float = 0.25,
    settle_time_s: float = 0.15,
) -> CycleEstimate:
    """Estimated pick-and-place cycle. This answers the question the customer
    actually asks — "how many parts per hour" — and it is kinematic, which is
    why L5 needs no physics engine."""
    t_pick = move_time(pick_travel_m, max_speed_m_s, accel_m_s2)
    t_place = move_time(place_travel_m, max_speed_m_s, accel_m_s2)

    breakdown = {
        "move_to_pick_s": t_pick.seconds,
        "grip_s": grip_time_s,
        "move_to_place_s": t_place.seconds,
        "release_s": release_time_s,
        "settle_s": settle_time_s * 2,
    }
    total = sum(breakdown.values())
    return CycleEstimate(
        seconds_per_cycle=total,
        parts_per_hour=3600.0 / total if total > 0 else 0.0,
        breakdown=breakdown,
        assumptions=[
            f"{t_pick.profile} profile to pick, {t_place.profile} to place",
            f"max speed {max_speed_m_s} m/s, accel {accel_m_s2} m/s^2",
            "excludes vision/inspection dwell and operator interaction",
            "no allowance for conveyor sync or part presentation variability",
        ],
    )


def estimate_link_mass(reach_m: float, kg_per_m: float = 1.2) -> float:
    """First-pass structural mass for the sizing loop.

    Circular dependency ducked deliberately: torque depends on link mass, link
    mass depends on the actuator chosen for that torque. One pass with a linear
    density estimate is accurate enough for a proposal and is re-checked against
    real geometry in L4.
    """
    return reach_m * kg_per_m


# --- per-joint sizing -------------------------------------------------------
#
# Sizing every joint at the shoulder's worst case is safe but materially
# over-specs the BOM: a wrist carrying a 0.5 kg gripper on an 80 mm arm does not
# need the actuator that holds the whole arm out horizontally. At proposal stage
# that inflates the quoted price of the cheapest tier, which is exactly the
# number a customer compares against a competitor.
#
# The load path is already in the topology tree, so this is arithmetic, not a
# model: each joint carries everything distal to it, at the summed length of the
# links distal to it.

#: Shortest moment arm we will size against. A joint whose only descendant is an
#: effector still has a real tool offset; zero would divide the design by luck.
MIN_MOMENT_ARM_M = 0.05


@dataclass(frozen=True)
class JointLoad:
    """What one joint actually has to hold.

    ``torque`` is ``None`` when we have no model for this DOF (a gantry lead
    screw). We do not substitute the arm formula there — it would be confidently
    wrong. Callers must handle ``None`` rather than treat it as zero; a skipped
    calculation is never a pass. Wheeled bases ARE modelled, by traction.
    """

    label: str
    module_id: str
    moment_arm_m: float
    distal_mass_kg: float
    carries_payload: bool
    sizing_basis: str  # "cantilever" | "traction" | "unmodelled"
    torque: TorqueEstimate | None = None
    #: Actuators needed at this joint. A revolute joint is 1; a differential
    #: drive base is 2. Without this the BOM buys one motor for two wheels.
    count: int = 1
    #: Structured facts L4 routes on — traction ceiling, required wheel speed.
    #: Never prose: the gate must be able to tell "needs a bigger motor" from
    #: "needs a grippier wheel", and those have opposite repairs.
    detail: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def chain_loads(
    topo,
    payload_kg: float,
    accel_rad_s2: float = 2.0,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
    kg_per_m: float = 1.2,
    travel_speed_m_s: float = 0.5,
) -> list[JointLoad]:
    """Torque required at every actuated joint in a topology tree.

    Distal mass = authored module masses below the joint + link extrusion at
    ``kg_per_m``. Actuator mass is the module's nominal figure and is NOT
    re-checked against the part finally chosen — that circular dependency is
    ducked here exactly as it is in :func:`estimate_link_mass`, and closed in L4
    against real geometry.
    """
    from .modules import ModuleKind  # local import keeps this module dependency-light

    children: dict[str | None, list] = {}
    for inst in topo.instances:
        children.setdefault(inst.parent, []).append(inst)

    def descendants(label: str) -> list:
        out = []
        for c in children.get(label, []):
            out.append(c)
            out.extend(descendants(c.label))
        return out

    loads: list[JointLoad] = []
    for inst in topo.instances:
        if inst.module.dof <= 0:
            continue

        if inst.module.kind is ModuleKind.DRIVE:
            # The wheels carry the whole machine, not just what is above them —
            # including the control panel, which hangs off the tree root.
            total = topo.est_mass_kg + payload_kg
            est = drive_torque(
                total_mass_kg=total,
                wheel_dia_m=float(inst.params.get("wheel_dia_m", 0.10)),
                n_driven=max(1, inst.module.dof),
                max_speed_m_s=travel_speed_m_s,
                safety_factor=safety_factor,
            )
            loads.append(JointLoad(
                label=inst.label, module_id=inst.module.id,
                moment_arm_m=float(inst.params.get("wheel_dia_m", 0.10)) / 2.0,
                distal_mass_kg=total, carries_payload=True,
                sizing_basis="traction", torque=est.torque, count=max(1, inst.module.dof),
                detail={
                    "tractive_force_n": est.tractive_force_n,
                    "traction_limit_n": est.traction_limit_n,
                    "slip_margin": est.slip_margin,
                    "wheel_speed_rad_s": est.wheel_speed_rad_s,
                },
            ))
            continue

        if inst.module.kind is not ModuleKind.JOINT:
            loads.append(JointLoad(
                label=inst.label, module_id=inst.module.id,
                moment_arm_m=0.0, distal_mass_kg=0.0, carries_payload=False,
                sizing_basis="unmodelled", torque=None, count=max(1, inst.module.dof),
                notes=[f"{inst.module.id} is not a gravity cantilever and not a wheeled "
                       "drive — lead-screw pitch and efficiency decide this axis and "
                       "neither is modelled yet"],
            ))
            continue

        desc = descendants(inst.label)
        links = [d for d in desc if d.module.kind is ModuleKind.LINK]
        arm = sum(float(d.params.get("length_m", 0.0)) for d in links)
        struct_mass = (sum(d.module.mass_kg for d in desc)
                       + sum(float(d.params.get("length_m", 0.0)) * kg_per_m for d in links))
        carries_payload = any(d.module.kind is ModuleKind.EFFECTOR for d in desc)

        notes = []
        if arm < MIN_MOMENT_ARM_M:
            notes.append(f"no distal link; sized at the {MIN_MOMENT_ARM_M} m minimum tool offset")
            arm = MIN_MOMENT_ARM_M

        loads.append(JointLoad(
            label=inst.label, module_id=inst.module.id,
            moment_arm_m=arm, distal_mass_kg=struct_mass,
            carries_payload=carries_payload, sizing_basis="cantilever",
            torque=joint_torque(
                payload_kg if carries_payload else 0.0, arm, struct_mass,
                accel_rad_s2=accel_rad_s2, safety_factor=safety_factor),
            notes=notes,
        ))
    return loads


def worst_case(loads: list[JointLoad]) -> TorqueEstimate | None:
    """The governing joint. Kept because headline output and the reach-envelope
    overlay quote one number, and it must be the largest one."""
    sized = [l.torque for l in loads if l.torque is not None]
    return max(sized, key=lambda t: t.required_nm) if sized else None


# --- traction sizing --------------------------------------------------------
#
# A driven wheel is not a cantilever. Its torque comes from rolling resistance,
# gradient and acceleration acting at the wheel radius — and it is capped by
# friction, not by the motor. That cap is the part worth computing: a
# traction-limited machine does not get better with a bigger actuator, it just
# spins its wheels, so "upsize the motor" is the wrong repair and must not be
# the one the gate suggests.

#: Rolling resistance coefficient — rubber wheels on a hard, sealed indoor floor.
#: Carpet is 3-5x worse and would need to be stated per site.
DEFAULT_ROLLING_RESISTANCE = 0.02
#: Grade the machine must start on and climb from rest. 5 deg is a little steeper
#: than an ADA ramp (1:12 ~ 4.76 deg), so a door threshold or a loading ramp.
DEFAULT_GRADE_DEG = 5.0
#: Tyre/floor friction, rubber on smooth sealed concrete. Taken at the low end —
#: dust, swarf and coolant all reduce it and none of them are modelled.
DEFAULT_FRICTION_COEFF = 0.6
#: Share of the machine's weight sitting over the driven wheels; the rest is on
#: casters and contributes nothing to traction.
DEFAULT_DRIVEN_WEIGHT_FRACTION = 0.7


@dataclass(frozen=True)
class DriveEstimate:
    torque: TorqueEstimate
    tractive_force_n: float
    traction_limit_n: float
    wheel_speed_rad_s: float
    per_wheel_nm: float

    @property
    def slip_margin(self) -> float:
        """<1.0 means the floor gives way before the motor does."""
        return self.traction_limit_n / self.tractive_force_n if self.tractive_force_n else float("inf")


def drive_torque(
    total_mass_kg: float,
    wheel_dia_m: float,
    n_driven: int = 2,
    max_speed_m_s: float = 0.5,
    accel_m_s2: float = 0.5,
    grade_deg: float = DEFAULT_GRADE_DEG,
    rolling_resistance: float = DEFAULT_ROLLING_RESISTANCE,
    friction_coeff: float = DEFAULT_FRICTION_COEFF,
    driven_weight_fraction: float = DEFAULT_DRIVEN_WEIGHT_FRACTION,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
) -> DriveEstimate:
    """Torque per driven wheel for a wheeled base, plus the traction ceiling.

    Static term  : rolling resistance + gravity on the worst grade it must start
                   on, since starting on a ramp is harder than running on one.
    Dynamic term : F = m*a at the same wheel radius.

    Does NOT model turning resistance (a skid-steer scrubbing its wheels around
    a point can need well over the straight-line figure), drivetrain efficiency,
    or wheel scrub on carpet. Covered by the safety factor and flagged for review.
    """
    if total_mass_kg <= 0 or wheel_dia_m <= 0 or n_driven < 1:
        raise ValueError("total_mass_kg > 0, wheel_dia_m > 0, n_driven >= 1 required")

    radius = wheel_dia_m / 2.0
    weight_n = total_mass_kg * G

    f_roll = rolling_resistance * weight_n
    f_grade = weight_n * math.sin(math.radians(grade_deg))
    f_acc = total_mass_kg * accel_m_s2
    f_total = f_roll + f_grade + f_acc

    static_nm = (f_roll + f_grade) * radius / n_driven
    dynamic_nm = f_acc * radius / n_driven

    return DriveEstimate(
        torque=TorqueEstimate(
            static_nm=static_nm,
            dynamic_nm=dynamic_nm,
            required_nm=(static_nm + dynamic_nm) * safety_factor,
            safety_factor=safety_factor,
            assumptions=[
                f"drive: {total_mass_kg:.1f} kg total on {n_driven} driven wheels "
                f"of {wheel_dia_m * 1000:.0f} mm diameter",
                f"worst case: starting from rest on a {grade_deg} deg grade",
                f"rolling resistance {rolling_resistance} (hard sealed floor; carpet is 3-5x worse)",
                f"acceleration {accel_m_s2} m/s^2 to {max_speed_m_s} m/s",
                "excludes turning/skid-steer scrub, drivetrain efficiency and wheel slip losses "
                f"(covered by the {safety_factor}x safety factor)",
            ],
        ),
        tractive_force_n=f_total,
        traction_limit_n=friction_coeff * weight_n * driven_weight_fraction,
        wheel_speed_rad_s=max_speed_m_s / radius,
        per_wheel_nm=f_total * radius / n_driven,
    )
