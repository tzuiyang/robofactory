"""L5 — presentation. BOM document + kinematic trajectory.

Kinematic, not physics: the buyer asks does it reach, does it fit, how many
parts per hour. All three are kinematic. The clip is a scripted trajectory
replay — deterministic and repeatable, with no learned policy that might fail on
render day.

Output is deliberately engineering-honest rather than beautiful: dimension
callouts, reach envelope, cycle counter, and a visible concept label. More
credible to an industrial buyer, and it protects against expectation gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Configuration
from .intake import Requirements

CONCEPT_LABEL = "CONCEPT SIMULATION — not a recording of a built machine"


@dataclass
class Waypoint:
    t_s: float
    label: str
    position_m: tuple[float, float, float]


@dataclass
class Trajectory:
    waypoints: list[Waypoint] = field(default_factory=list)
    overlays: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.waypoints[-1].t_s if self.waypoints else 0.0


def build_trajectory(config: Configuration, req: Requirements) -> Trajectory:
    """Scripted pick-and-place path derived from the cycle-time breakdown, so the
    clip and the quoted rate cannot disagree."""
    r = req.reach_m
    b = config.cycle.breakdown
    t = 0.0
    wp = [Waypoint(0.0, "home", (0.0, 0.0, r * 0.5))]
    for label, dt, pos in (
        ("approach pick", b["move_to_pick_s"], (r * 0.8, 0.0, r * 0.15)),
        ("grip", b["grip_s"], (r * 0.8, 0.0, r * 0.10)),
        ("lift", b["settle_s"] / 2, (r * 0.8, 0.0, r * 0.45)),
        ("approach place", b["move_to_place_s"], (0.0, r * 0.8, r * 0.45)),
        ("release", b["release_s"], (0.0, r * 0.8, r * 0.15)),
        ("retract", b["settle_s"] / 2, (0.0, 0.0, r * 0.5)),
    ):
        t += dt
        wp.append(Waypoint(round(t, 3), label, pos))

    return Trajectory(
        waypoints=wp,
        overlays=[
            CONCEPT_LABEL,
            f"reach {r:.2f} m | payload {req.payload_kg:.1f} kg",
            f"cycle {config.cycle.seconds_per_cycle:.2f} s -> {config.cycle.parts_per_hour:.0f} parts/hr",
            f"torque {config.torque.required_nm:.1f} Nm required (SF {config.torque.safety_factor}x)",
        ],
    )


def _joint_load_table(config: Configuration) -> list[str]:
    """Per-joint load path, shown because the actuators differ per joint.

    Without it the BOM reads as three unexplained different motors. With it, an
    engineer can check the sizing in thirty seconds — which is the entire point
    of the review gate.
    """
    if not config.joint_loads:
        return []
    rows = [
        "### Load path (each joint sized at its own load)",
        "",
        "| Joint | Module | Sized by | Arm / radius (m) | Mass carried (kg) | Motors | Required (Nm) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for l in config.joint_loads:
        need = f"{l.torque.required_nm:.1f}" if l.torque else "**not modelled**"
        rows.append(f"| {l.label} | `{l.module_id}` | {l.sizing_basis} | {l.moment_arm_m:.3f} | "
                    f"{l.distal_mass_kg:.2f} | {l.count} | {need} |")

    traction = [l for l in config.joint_loads if l.sizing_basis == "traction"]
    for l in traction:
        rows += ["", f"`{l.label}` is sized by traction, not by a cantilever: "
                     f"{l.detail['tractive_force_n']:.0f} N needed at the contact patch against "
                     f"a friction ceiling of {l.detail['traction_limit_n']:.0f} N "
                     f"({l.detail['slip_margin']:.2f}x margin), and "
                     f"{l.detail['wheel_speed_rad_s']:.1f} rad/s at the wheel to hold travel speed. "
                     "Turning scrub, drivetrain efficiency and carpet are not modelled."]
    if any(l.torque is None for l in config.joint_loads):
        rows += ["", "Axes marked *not modelled* are neither gravity cantilevers nor wheeled "
                     "drives — a gantry lead screw's pitch and efficiency decide them, and an "
                     "engineer must size them. The placeholder in the BOM is conservative, "
                     "not correct."]
    return rows + [""]


def bom_document(config: Configuration, req: Requirements, tier: str) -> str:
    """Customer-facing BOM. Prices as a range, safety factor visible,
    assumptions stated."""
    t = config.tiers[tier]
    low, high = t.price_range_usd()
    rows = [
        "| Qty | Part | Manufacturer | P/N | Role | Unit USD | Line USD | Verified |",
        "|---:|---|---|---|---|---:|---:|:--:|",
    ]
    for l in sorted(t.lines, key=lambda x: -x.total_usd):
        rows.append(
            f"| {l.qty} | {l.part.description} | {l.part.manufacturer} | {l.part.part_number} | "
            f"{l.role} | {l.part.price_usd:,.2f} | {l.total_usd:,.2f} | "
            f"{'yes' if l.part.verified else '**NO**'} |"
        )

    out = [
        f"# Concept: {req.task}",
        "",
        f"**{CONCEPT_LABEL}**",
        "",
        f"- Archetype: **{config.archetype.name}** (`{config.archetype.id}`), {config.archetype.dof} DOF",
        f"- Payload: {req.payload_kg:.2f} kg at {req.reach_m:.2f} m reach",
        f"- Estimated cycle: {config.cycle.seconds_per_cycle:.2f} s "
        f"({config.cycle.parts_per_hour:.0f} parts/hr)",
        f"- Governing joint torque: {config.torque.required_nm:.1f} Nm "
        f"(static {config.torque.static_nm:.1f} + dynamic {config.torque.dynamic_nm:.1f}, "
        f"safety factor **{config.torque.safety_factor}x**)",
        "",
        *_joint_load_table(config),
        f"## Bill of materials — tier `{tier}`",
        "",
        *rows,
        "",
        f"**Parts subtotal:** {t.parts_cost_usd:,.2f} USD",
        "",
        f"### Estimated price: {low:,.0f} – {high:,.0f} USD",
        "",
        "Range includes integration, wiring, fabrication and test. "
        "Subject to engineering review — this is a concept, not a quotation.",
        "",
        "## Assumptions",
        "",
        *[f"- {a}" for a in config.assumptions],
        *[f"- {a}" for a in req.assumptions],
        "",
        "## What this concept does NOT verify",
        "",
        "Kinematic feasibility only. Not verified: tolerance stack-up, assembly access, "
        "wire routing, thermal behaviour, duty-cycle derating, backlash and compliance, "
        "EMC, or control-loop stability on real hardware. These are covered by engineering "
        "review before build.",
    ]
    return "\n".join(out)
