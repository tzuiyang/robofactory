"""L2 — configuration. LLM proposes, code disposes.

Archetype choice may be model-assisted; everything numeric here is not. Part
selection is a constrained query over the curated catalog, never a search.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .archetypes import Archetype, candidates
from .capabilities import Capability, gaps
from .modules import ModuleKind
from .topology import Topology, TopologyError, synthesize
from .catalog import ActuatorRole, Catalog, Part, PartKind
from .intake import Requirements
from .sizing import (
    CycleEstimate, JointLoad, TorqueEstimate, chain_loads, cycle_time,
    estimate_link_mass, joint_torque, worst_case,
)


#: What we build, set by the team 2026-08-28. These are ceilings on the *product*,
#: not on the customer's wallet — a request that cannot be met under them is
#: outside what we make, and saying so beats designing something we cannot sell.
MAX_PARTS_COST_USD = 3000.0
MAX_SALE_PRICE_USD = 10000.0


_MOBILE_ONLY = Archetype(
    id="mobile.base_only",
    name="Mobile base (no manipulator)",
    description="A machine that moves itself and carries sensors, but does not reach for things.",
    dof=2, params={}, max_payload_kg=50.0, max_reach_m=0.0, joint_slots=["left", "right"],
    notes="Synthesized, not a preset — reach limits do not apply.",
)


class InfeasibleError(RuntimeError):
    """No archetype or no catalog part can meet the requirement.

    Raised rather than degraded. Telling a customer "we cannot do this" is worth
    more than a plausible design that fails on the shop floor.
    """


@dataclass
class BOMLine:
    part: Part
    qty: int
    role: str
    #: Joint labels this line covers, when the line is a per-joint actuator.
    #: Empty for everything else. Carried so the review gate can show an
    #: engineer *which* joint an over- or under-sized part belongs to.
    joints: list[str] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return self.part.price_usd * self.qty


@dataclass
class Tier:
    """One of good / better / best. Three tiers turn a budget mismatch into a
    negotiation instead of a rejection."""

    name: str
    lines: list[BOMLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def parts_cost_usd(self) -> float:
        return sum(l.total_usd for l in self.lines)

    def price_range_usd(self, labor_multiplier: float = 1.8, spread: float = 0.18) -> tuple[float, float]:
        """Quoted range, never a point estimate.

        ``labor_multiplier`` covers integration, wiring, fabrication and test.
        ``spread`` is the quoting band. Both are visible, not buried.
        """
        mid = self.parts_cost_usd * labor_multiplier
        return (round(mid * (1 - spread), -1), round(mid * (1 + spread), -1))


@dataclass
class Configuration:
    archetype: Archetype
    topology: Topology | None = None
    torque: TorqueEstimate = None
    cycle: CycleEstimate = None
    tiers: dict[str, Tier] = field(default_factory=dict)
    #: Per-joint load path. Empty when no topology was synthesized.
    joint_loads: list[JointLoad] = field(default_factory=list)
    geometry_params: dict[str, float] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    #: Capabilities requested that the catalog cannot currently supply.
    #: Reported, never silently dropped — a robot delivered without the speaker
    #: it was quoted with is a lost deal at delivery instead of at quote.
    capability_gaps: list[str] = field(default_factory=list)


def select_archetype(req: Requirements, preferred: str | None = None) -> Archetype:
    fits = candidates(req.payload_kg, req.reach_m)
    if not fits:
        raise InfeasibleError(
            f"no archetype covers payload {req.payload_kg} kg at reach {req.reach_m} m. "
            "This is outside what we build — say so rather than designing something untested."
        )
    if preferred:
        for a in fits:
            if a.id == preferred:
                return a
        raise InfeasibleError(
            f"preferred archetype {preferred!r} does not fit; candidates: {[a.id for a in fits]}"
        )
    return fits[0]


def _pick_actuator(catalog: Catalog, required_nm: float, budget: float, allow_unverified: bool,
                   min_speed_rad_s: float | None = None,
                   role: ActuatorRole = ActuatorRole.JOINT) -> Part:
    options = catalog.query(
        kind=PartKind.ACTUATOR, min_torque_nm=required_nm, min_speed_rad_s=min_speed_rad_s,
        actuator_role=role, allow_unverified=allow_unverified,
    )
    if not options:
        speed = f" at {min_speed_rad_s:.1f} rad/s or faster" if min_speed_rad_s else ""
        # Distinguish "we don't stock one" from "we stock one nobody has checked".
        # Both blocked the quote and both used to surface as "not strong enough",
        # which sends the customer off to shrink a design that already fits.
        if not allow_unverified and catalog.query(
                kind=PartKind.ACTUATOR, min_torque_nm=required_nm,
                min_speed_rad_s=min_speed_rad_s, actuator_role=role,
                allow_unverified=True):
            raise InfeasibleError(
                f"unverified parts cannot be quoted: the only {role.value} actuators "
                f"delivering {required_nm:.1f} Nm rated{speed} are not human-verified. "
                "Check part number, price and specs against the vendor, then set "
                "verified=true in the catalog."
            )
        raise InfeasibleError(
            f"no catalogued {role.value} actuator delivers {required_nm:.1f} Nm rated{speed}. "
            "Either the design needs a gearbox stage or the part must be added to the catalog "
            "(by a human, offline)."
        )
    affordable = [p for p in options if p.price_usd <= budget]
    return (affordable or options)[0]


def _actuator_lines(
    catalog: Catalog,
    loads: list[JointLoad],
    fallback_nm: float,
    sf_scale: float,
    per_joint_budget: float,
    allow_unverified: bool,
) -> list[BOMLine]:
    """One actuator per joint, each sized at *that joint's* own load.

    Sizing every joint at the shoulder's worst case is safe but materially
    over-specs the BOM — and the inflated number is the one a customer compares
    against a competitor. Identical picks are grouped back into one BOM line so
    the document still reads like a parts list, not a joint list.

    Joints whose axis is not a gravity cantilever (gantry, drive) fall back to
    ``fallback_nm``, the governing cantilever joint. That is conservative rather
    than correct, and it is stated in the tier notes — not hidden.
    """
    grouped: dict[str, tuple[Part, list[str], int]] = {}
    for load in loads:
        need_nm = (load.torque.required_nm if load.torque else fallback_nm) * sf_scale
        # Torque scales with the tier; the travel speed the customer asked for
        # does not, so it is a floor on every tier alike.
        # A wheel axis needs a drive gearmotor; everything else needs a servo that
        # can hold position. Selecting on torque alone put the drive motor in an
        # arm elbow (log.md, 2026-08-28).
        role = (ActuatorRole.DRIVE if load.sizing_basis == "traction"
                else ActuatorRole.JOINT)
        part = _pick_actuator(catalog, need_nm, per_joint_budget * sf_scale, allow_unverified,
                              min_speed_rad_s=load.detail.get("wheel_speed_rad_s"), role=role)
        # ``count``, not 1: a differential drive base is one label and two motors.
        p, labels, qty = grouped.get(part.id, (part, [], 0))
        grouped[part.id] = (p, labels + [load.label], qty + load.count)

    return [
        BOMLine(part, qty, "joint actuator — " + ", ".join(labels), list(labels))
        for part, labels, qty in grouped.values()
    ]


#: Which catalog part currently fills each part kind the modules ask for.
#: A stand-in for real selection logic: once the catalog holds several parts per
#: kind this becomes a constrained query like ``_pick_actuator``. It is a dict so
#: that a kind with no entry shows up as a hole in the BOM instead of vanishing.
_KIND_DEFAULTS: dict[str, tuple[str, str]] = {
    "controller": ("ctrl.pi5", "motion controller"),
    "driver": ("drv.mdd10a", "motor driver"),
    "psu": ("psu.150w", "power supply"),
    "sensor": ("sens.limit", "home/limit sensor"),
    "wheel": ("wheel.96mm", "drive wheel"),
    "battery": ("batt.24v", "battery"),
    "camera": ("cam.picam3", "camera"),
    "microphone": ("mic.respeaker2", "microphone array"),
    "speaker": ("spk.mono3w", "speaker"),
    "audio_amp": ("amp.max98357", "audio amplifier"),
    "compute_module": ("comp.pi5", "onboard computer"),
}

#: End effector is chosen by which effector module the topology actually placed,
#: not by a default — a vacuum robot must not be quoted a parallel gripper.
_EFFECTOR_PARTS = {"effector.gripper": "ee.gripper2f", "effector.vacuum": "ee.vacuum"}


def _support_lines(
    catalog: Catalog, topo: Topology | None, n_actuators: int, n_joints: int,
) -> tuple[list[BOMLine], set[str]]:
    """Everything that is not a joint actuator, derived from what the modules ask for.

    Previously a fixed list, which meant a patrol robot that cannot grasp was
    still quoted a gripper and limit switches, while the wheels and battery its
    drive base genuinely needs were dropped on the floor. Parts must follow from
    the topology or the BOM describes a different machine than the one designed.

    Returns the lines and the kinds nothing in the catalog can fill.
    """
    if topo is None:  # legacy archetype-only path, unchanged
        lines = []
        for pid, qty, role in (
            ("ctrl.main", 1, "motion controller"),
            ("drv.dual", max(1, (n_joints + 1) // 2), "motor driver"),
            ("psu.150w", 1, "power supply"),
            ("ee.gripper2f", 1, "end effector"),
            ("sens.limit", n_joints, "home/limit sensor"),
        ):
            try:
                lines.append(BOMLine(catalog.get(pid), qty, role))
            except KeyError:
                pass
        return lines, set()

    wheels = sum(i.module.dof for i in topo.instances if i.module.kind is ModuleKind.DRIVE)
    quantities = {
        "driver": max(1, (n_actuators + 1) // 2),  # dual-channel drivers
        "sensor": n_joints,
        "wheel": max(2, wheels),
    }

    lines: list[BOMLine] = []
    missing: set[str] = set()
    for kind in sorted(topo.consumes_kinds):
        if kind == "actuator":
            continue  # already sized per joint
        if kind == "end_effector":
            eff = next((i for i in topo.instances if i.module.id in _EFFECTOR_PARTS), None)
            entry = (_EFFECTOR_PARTS[eff.module.id], "end effector") if eff else None
        else:
            entry = _KIND_DEFAULTS.get(kind)
        if entry is None:
            missing.add(kind)
            continue
        try:
            lines.append(BOMLine(catalog.get(entry[0]), quantities.get(kind, 1), entry[1]))
        except KeyError:
            missing.add(kind)
    return lines, missing


def build(
    req: Requirements,
    catalog: Catalog,
    preferred_archetype: str | None = None,
    allow_unverified: bool = False,
) -> Configuration:
    problems = req.validate()
    if problems:
        raise InfeasibleError("requirements invalid: " + "; ".join(problems))

    # A rover that only drives and talks has no manipulator, so a manipulator
    # reach envelope must not gate it. Previously a companion robot was rejected
    # as "no archetype covers 0.2 kg at 2.0 m" — a meaningless test for a machine
    # that never reaches for anything.
    needs_manipulator = (
        not req.capabilities
        or bool(req.capabilities & {Capability.MANIPULATION, Capability.GRASPING,
                                    Capability.FLAT_MATERIAL_HANDLING})
    )
    archetype = select_archetype(req, preferred_archetype) if needs_manipulator else _MOBILE_ONLY

    topo = None
    cap_gaps: list[str] = []
    if req.capabilities:
        try:
            topo = synthesize(req.capabilities, req.payload_kg, req.reach_m,
                              req.workspace_is_planar)
        except TopologyError as e:
            raise InfeasibleError(str(e)) from None
        available = {p.kind.value for p in catalog.query(allow_unverified=True)}
        cap_gaps = [str(g) for g in gaps(req.capabilities, available)]

    joint_loads: list[JointLoad] = []
    if topo is not None:
        joint_loads = chain_loads(topo, req.payload_kg)

    if needs_manipulator:
        link_mass = estimate_link_mass(req.reach_m)
        # Prefer the real load path when we have one. Falling back to the
        # single-shoulder formula only when no topology was synthesized keeps
        # the archetype-only path working unchanged.
        torque = worst_case(joint_loads) or joint_torque(req.payload_kg, req.reach_m, link_mass)
    else:
        # Drive torque is a traction problem, not a cantilever problem. Sizing it
        # with the arm formula would be confidently wrong, so we do not pretend.
        link_mass = 0.0
        torque = joint_torque(req.payload_kg, 0.15, 0.0)
        torque = replace(torque, assumptions=[
            "mobile base: drive torque sized as a placeholder only",
            "traction, gradient and rolling resistance are NOT yet modelled — "
            "an engineer must size the drivetrain",
        ])

    # Actuator budget: joints are the dominant cost, so allot the bulk of parts
    # spend across them before anything else is chosen.
    n_joints = max(1, len(topo.joint_slots) if topo else len(archetype.joint_slots))
    per_joint_budget = (req.budget_usd * 0.45) / n_joints

    tiers: dict[str, Tier] = {}
    #: Why each tier fell out. Without it every cause collapses into "no tier
    #: could be configured", which the customer screen renders as "not strong
    #: enough" — sending someone off to shrink a design whose only problem was
    #: that nobody has verified the parts yet.
    tier_failures: list[str] = []
    for tier_name, sf_scale, note in (
        ("good", 1.0, "meets the stated requirement at the stated safety factor"),
        ("better", 1.4, "40% torque headroom — tolerates payload growth and duty increase"),
        ("best", 2.0, "2x headroom, faster cycle, spare I/O for future automation"),
    ):
        target_nm = torque.required_nm * sf_scale
        try:
            if joint_loads:
                lines = _actuator_lines(catalog, joint_loads, torque.required_nm,
                                        sf_scale, per_joint_budget, allow_unverified)
            else:
                lines = [BOMLine(
                    _pick_actuator(catalog, target_nm, per_joint_budget * sf_scale,
                                   allow_unverified),
                    n_joints, "joint actuator")]
        except InfeasibleError as e:
            tier_failures.append(str(e))
            continue  # this tier is not reachable; the others may still be
        n_act = sum(l.qty for l in lines)
        support, missing_kinds = _support_lines(catalog, topo, n_act, n_joints)
        lines.extend(support)

        tier_notes = [note]
        if missing_kinds:
            tier_notes.append(
                "no catalogued part for: " + ", ".join(sorted(missing_kinds))
                + " — the BOM is incomplete until a human adds them")
        if joint_loads:
            tier_notes.append(
                "each joint sized at its own load; governing joint "
                f"{max((l for l in joint_loads if l.torque), key=lambda l: l.torque.required_nm).label} "
                f"at {target_nm:.1f} Nm (SF {torque.safety_factor}x)"
                if any(l.torque for l in joint_loads)
                else f"sized for {target_nm:.1f} Nm at joint (SF {torque.safety_factor}x)")
            unmodelled = [l.label for l in joint_loads if l.torque is None]
            if unmodelled:
                tier_notes.append(
                    f"axes {', '.join(unmodelled)} are NOT cantilever joints — sized "
                    "conservatively at the governing joint's torque as a placeholder; "
                    "an engineer must size these properly")
        else:
            tier_notes.append(f"sized for {target_nm:.1f} Nm at joint (SF {torque.safety_factor}x)")

        tiers[tier_name] = Tier(name=tier_name, lines=lines, notes=tier_notes)

    tiers = _dedupe_tiers(tiers)
    if not tiers:
        # Report the reason the *cheapest* tier failed: it is the one closest to
        # being reachable, so it is the actionable one.
        reason = tier_failures[0] if tier_failures else ""
        raise InfeasibleError(
            f"no tier could be configured from the current catalog: {reason}"
            if reason else "no tier could be configured from the current catalog")

    cycle = cycle_time(pick_travel_m=req.reach_m * 0.8, place_travel_m=req.reach_m * 0.8)

    geometry_params = {"reach_m": req.reach_m, "est_mass_kg": link_mass + req.payload_kg}
    for name in archetype.params:
        geometry_params.setdefault(name, _default_param(name, req))

    return Configuration(
        archetype=archetype,
        topology=topo,
        joint_loads=joint_loads,
        capability_gaps=cap_gaps,
        torque=torque,
        cycle=cycle,
        tiers=tiers,
        geometry_params=geometry_params,
        assumptions=[*torque.assumptions, *cycle.assumptions, _mass_assumption(joint_loads, link_mass)],
    )


def _mass_assumption(joint_loads: list[JointLoad], link_mass: float) -> str:
    """State the mass model that actually drove the torque.

    When a load path exists, quoting the old linear-density figure would
    describe a calculation that was not performed — the exact way an assumption
    becomes a fact nobody re-checks.
    """
    cantilever = [l for l in joint_loads if l.torque is not None]
    if not cantilever:
        return f"structural mass estimated at {link_mass:.2f} kg (linear density model)"
    governing = max(cantilever, key=lambda l: l.torque.required_nm)
    return (f"distal mass at the governing joint ({governing.label}) estimated at "
            f"{governing.distal_mass_kg:.2f} kg — authored module masses plus extrusion at "
            "1.2 kg/m; actuator mass is nominal and is not re-checked against the part chosen")


def _dedupe_tiers(tiers: dict[str, Tier]) -> dict[str, Tier]:
    """Collapse tiers that resolve to the same parts.

    A sparse catalog makes two tiers pick the same actuator, and offering a
    customer "better" at the same price and spec as "good" reads as padding and
    costs trust. Keeps the cheapest-named survivor and records why.

    Consequence worth knowing: **meaningful tiering requires catalog depth.**
    Three actuator sizes cannot support three genuine tiers. If runs keep
    collapsing to one tier, the fix is more catalog, not more code.
    """
    seen: dict[tuple, str] = {}
    out: dict[str, Tier] = {}
    for name in ("good", "better", "best"):
        t = tiers.get(name)
        if t is None:
            continue
        key = tuple(sorted((l.part.id, l.qty) for l in t.lines))
        if key in seen:
            out[seen[key]].notes.append(
                f"tier '{name}' collapsed into this one — the catalog holds no distinct "
                "part set at that level"
            )
            continue
        seen[key] = name
        out[name] = t
    return out


def _default_param(name: str, req: Requirements) -> float:
    """First-pass values for archetype parameters not directly given."""
    if name.startswith("link1"):
        return req.reach_m * 0.55
    if name.startswith("link2"):
        return req.reach_m * 0.45
    if "z_travel" in name:
        return min(0.25, req.reach_m * 0.4)
    if "x_travel" in name:
        return req.reach_m
    if "y_travel" in name:
        return req.reach_m * 0.7
    if "height" in name:
        return req.reach_m * 0.5
    return req.reach_m
