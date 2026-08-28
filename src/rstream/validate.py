"""L4 — validation. Cheap and exact first, fuzzy last.

Order matters and is not negotiable:

    4a deterministic gate  — exact, free, unambiguous
    4b vision gate         — plausibility only
    4c bounded repair      — structured signals, max 3 attempts, then a human

Never ask a vision model to judge something a query can measure. Vision cannot
measure; letting it try produces confidently wrong dimensions. And a check that
did not run is reported SKIPPED, never PASSED — an unrun check must not read as
a clean bill of health.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .cad import CADBackend, View
from .cad.geom import BBox, Vec3
from .config import MAX_PARTS_COST_USD, MAX_SALE_PRICE_USD, Configuration

MAX_REPAIR_ATTEMPTS = 3


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    WARN = "warn"


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""
    #: Structured repair signal. Never free text like "looks wrong" — the repair
    #: loop routes on these fields, and prose cannot be routed on.
    repair: dict | None = None

    @property
    def blocking(self) -> bool:
        return self.status is Status.FAIL


@dataclass
class GateResult:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(c.blocking for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.blocking]

    @property
    def skipped(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.SKIPPED]

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for c in self.checks:
            counts[c.status.value] = counts.get(c.status.value, 0) + 1
        return " ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def _components_envelope(config: Configuration, tier: str) -> tuple[float, tuple[float, float, float]]:
    """Total keepout volume and the largest single component envelope."""
    total = 0.0
    largest = (0.0, 0.0, 0.0)
    panel_kinds = {"controller", "driver", "psu", "sensor"}
    for line in config.tiers[tier].lines:
        if line.part.kind.value not in panel_kinds:
            continue
        total += line.part.dimensions.envelope_volume_m3 * line.qty
        env = line.part.dimensions.envelope_mm
        if env[0] * env[1] * env[2] > largest[0] * largest[1] * largest[2]:
            largest = env
    return total, largest


def _torque_margin_checks(config: Configuration, tier: str) -> list[Check]:
    """One check per actuated joint, plus a WARN for any joint whose axis we do
    not model. An unmodelled axis is not a passing axis."""
    lines = [l for l in config.tiers[tier].lines if l.part.actuator]
    if not lines:
        return [Check("torque_margin", Status.SKIPPED, "no actuator in tier")]

    required: dict[str, float] = {}
    unmodelled: set[str] = set()
    for load in config.joint_loads:
        if load.torque is None:
            unmodelled.add(load.label)
        else:
            required[load.label] = load.torque.required_nm

    # No per-joint load path (archetype-only run): fall back to the single
    # governing figure against the tier's largest actuator, as before.
    if not config.joint_loads:
        act = lines[0].part
        margin = act.actuator.rated_torque_nm / config.torque.required_nm
        if margin < 1.0:
            return [Check(
                "torque_margin", Status.FAIL,
                f"{act.id} rated {act.actuator.rated_torque_nm} Nm < required "
                f"{config.torque.required_nm:.1f} Nm",
                repair={"action": "upsize_actuator", "need_nm": config.torque.required_nm})]
        return [Check("torque_margin", Status.PASS,
                      f"{margin:.2f}x rated over required "
                      f"(SF {config.torque.safety_factor}x already applied)")]

    checks: list[Check] = []
    for line in lines:
        for joint in (line.joints or [None]):
            rated = line.part.actuator.rated_torque_nm
            if joint in unmodelled:
                checks.append(Check(
                    f"torque_margin[{joint}]", Status.WARN,
                    f"{line.part.id} chosen for {joint} but this axis is not a gravity "
                    "cantilever — its real requirement is unmodelled and must be sized "
                    "by an engineer"))
                continue
            need = required.get(joint, config.torque.required_nm)
            margin = rated / need
            name = f"torque_margin[{joint}]" if joint else "torque_margin"
            if margin < 1.0:
                checks.append(Check(
                    name, Status.FAIL,
                    f"{line.part.id} rated {rated} Nm < {need:.1f} Nm required at {joint}",
                    repair={"action": "upsize_actuator", "joint": joint, "need_nm": need}))
            else:
                checks.append(Check(
                    name, Status.PASS,
                    f"{margin:.2f}x rated over {need:.1f} Nm required at {joint} "
                    f"(SF {config.torque.safety_factor}x already applied)"))
    return checks


def _drive_checks(config: Configuration, tier: str) -> list[Check]:
    """Two things a torque margin cannot tell you about a wheeled base.

    **Traction.** Force at the contact patch is capped by friction, not by the
    motor. Past that cap the wheels spin and a bigger actuator changes nothing —
    so the repair is a grippier or larger wheel, or more weight over the driven
    axle, and the signal must say so. Routing this to ``upsize_actuator`` would
    send the repair loop to burn its three attempts on the wrong knob.

    **Speed.** A base sized only for torque can be geared so low it crawls. A
    120 kg/hr claim from a machine doing 0.04 m/s is the kind of number that
    gets caught in the room.
    """
    checks: list[Check] = []
    by_label = {l.label: l for l in config.joint_loads if l.sizing_basis == "traction"}
    if not by_label:
        return checks

    actuator_for: dict[str, object] = {}
    for line in config.tiers[tier].lines:
        if line.part.actuator:
            for j in line.joints:
                actuator_for[j] = line.part

    for label, load in by_label.items():
        margin = load.detail.get("slip_margin", 0.0)
        if margin < 1.0:
            checks.append(Check(
                f"traction[{label}]", Status.FAIL,
                f"needs {load.detail['tractive_force_n']:.0f} N at the contact patch but "
                f"friction caps it at {load.detail['traction_limit_n']:.0f} N — the wheels "
                "will slip; a larger motor does not help",
                repair={"action": "increase_traction", "joint": label,
                        "short_by_n": load.detail["tractive_force_n"] - load.detail["traction_limit_n"]}))
        elif margin < 1.5:
            checks.append(Check(
                f"traction[{label}]", Status.WARN,
                f"{margin:.2f}x traction margin — thin for a dusty or wet floor"))
        else:
            checks.append(Check(f"traction[{label}]", Status.PASS,
                                f"{margin:.2f}x traction margin"))

        act = actuator_for.get(label)
        need_rad_s = load.detail.get("wheel_speed_rad_s", 0.0)
        if act is None or act.actuator is None:
            checks.append(Check(f"drive_speed[{label}]", Status.SKIPPED,
                                "no actuator selected for this axis"))
        elif act.actuator.max_speed_rad_s < need_rad_s:
            achieved = act.actuator.max_speed_rad_s * load.moment_arm_m
            checks.append(Check(
                f"drive_speed[{label}]", Status.FAIL,
                f"{act.id} tops out at {act.actuator.max_speed_rad_s} rad/s, needs "
                f"{need_rad_s:.1f} rad/s — the machine would travel {achieved:.2f} m/s, "
                "and every throughput figure derived from travel speed is wrong",
                repair={"action": "regear_drive", "joint": label,
                        "need_rad_s": need_rad_s, "have_rad_s": act.actuator.max_speed_rad_s}))
        else:
            checks.append(Check(
                f"drive_speed[{label}]", Status.PASS,
                f"{act.actuator.max_speed_rad_s} rad/s available, {need_rad_s:.1f} needed"))
    return checks


def deterministic_gate(
    backend: CADBackend, config: Configuration, tier: str, budget_usd: float,
    packing_efficiency: float = 0.55,
) -> GateResult:
    """4a — every check here is exact arithmetic or a CAD query. No model involved."""
    result = GateResult()
    t = config.tiers[tier]

    # --- budget -------------------------------------------------------
    low, high = t.price_range_usd()
    if low > budget_usd:
        result.checks.append(Check(
            "budget", Status.FAIL,
            f"tier '{tier}' quotes {low:,.0f}-{high:,.0f} USD against a {budget_usd:,.0f} budget",
            repair={"action": "downgrade_tier", "over_by_usd": low - budget_usd},
        ))
    elif high > budget_usd:
        result.checks.append(Check(
            "budget", Status.WARN,
            f"top of range ({high:,.0f}) exceeds budget ({budget_usd:,.0f})"))
    else:
        result.checks.append(Check("budget", Status.PASS, f"{low:,.0f}-{high:,.0f} USD"))

    # --- cost target --------------------------------------------------
    # The product has a ceiling of its own, independent of what this customer
    # said they could spend. Over it, the right move is a cheaper tier, and
    # failing that, telling them it is outside what we build.
    if t.parts_cost_usd > MAX_PARTS_COST_USD:
        result.checks.append(Check(
            "cost_target", Status.FAIL,
            f"parts cost {t.parts_cost_usd:,.0f} USD exceeds the {MAX_PARTS_COST_USD:,.0f} "
            "USD ceiling for a machine we build",
            repair={"action": "downgrade_tier",
                    "over_by_usd": t.parts_cost_usd - MAX_PARTS_COST_USD},
        ))
    elif high > MAX_SALE_PRICE_USD:
        result.checks.append(Check(
            "cost_target", Status.FAIL,
            f"top of the quoted range ({high:,.0f} USD) exceeds the "
            f"{MAX_SALE_PRICE_USD:,.0f} USD ceiling",
            repair={"action": "downgrade_tier", "over_by_usd": high - MAX_SALE_PRICE_USD},
        ))
    else:
        result.checks.append(Check(
            "cost_target", Status.PASS,
            f"parts {t.parts_cost_usd:,.0f} / {MAX_PARTS_COST_USD:,.0f} USD, "
            f"sells at {low:,.0f}-{high:,.0f} / {MAX_SALE_PRICE_USD:,.0f} USD"))

    # --- torque margin ------------------------------------------------
    # Checked per joint, not once for the tier. Since actuators are sized against
    # each joint's own load, a single check on the largest actuator would leave
    # every distal joint unverified — and the distal ones are precisely the ones
    # that were just made smaller.
    result.checks.extend(_torque_margin_checks(config, tier))
    result.checks.extend(_drive_checks(config, tier))

    # --- panel volume -------------------------------------------------
    needed_m3, largest_mm = _components_envelope(config, tier)
    try:
        envelope = backend.panel_envelope()
    except RuntimeError as e:
        result.checks.append(Check("panel_volume", Status.SKIPPED, str(e)))
    else:
        usable = envelope.volume_m3 * packing_efficiency
        if needed_m3 > usable:
            result.checks.append(Check(
                "panel_volume", Status.FAIL,
                f"components need {needed_m3 * 1e6:.0f} cm^3 (keepout incl.), tier provides "
                f"{usable * 1e6:.0f} cm^3 usable at {packing_efficiency:.0%} packing",
                repair={"action": "upsize_panel_tier", "need_m3": needed_m3},
            ))
        else:
            result.checks.append(Check(
                "panel_volume", Status.PASS,
                f"{needed_m3 * 1e6:.0f} / {usable * 1e6:.0f} cm^3 used"))

        largest_box = BBox(Vec3(0, 0, 0), Vec3(*[d / 1000 for d in largest_mm]))
        if not largest_box.fits_inside(envelope):
            result.checks.append(Check(
                "panel_largest_part", Status.FAIL,
                f"largest component envelope {largest_mm} mm does not fit the tier",
                repair={"action": "upsize_panel_tier"},
            ))
        else:
            result.checks.append(Check("panel_largest_part", Status.PASS))

    # --- reach --------------------------------------------------------
    # Reach is measured from the base axis outward, NOT the model's full span.
    # A revolute arm sweeps a circle, so its bounding box is ~2x its reach;
    # comparing span against reach would pass a machine half the size needed.
    m = backend.measure()
    reach = config.geometry_params.get("reach_m", 0.0)
    achieved = max(abs(m.bbox.min.x), abs(m.bbox.max.x))
    if achieved < reach:
        result.checks.append(Check(
            "reach", Status.FAIL,
            f"model reaches {achieved:.3f} m from base, requirement {reach:.3f} m",
            repair={"action": "regenerate_geometry", "need_m": reach},
        ))
    else:
        result.checks.append(Check(
            "reach", Status.PASS, f"{achieved:.3f} m from base (span {m.bbox.size.x:.3f} m)"))

    # --- interference -------------------------------------------------
    if not getattr(backend, "supports_interference", True):
        result.checks.append(Check(
            "interference", Status.SKIPPED,
            f"backend '{backend.name}' has no B-rep; run on a real CAD backend before quoting"))
    else:
        clashes = backend.check_interference()
        if clashes:
            result.checks.append(Check(
                "interference", Status.FAIL,
                "; ".join(str(c) for c in clashes[:5]),
                repair={"action": "reposition_parts",
                        "pairs": [(c.body_a, c.body_b) for c in clashes]},
            ))
        else:
            result.checks.append(Check("interference", Status.PASS, "no clashes"))

    # --- catalog verification ----------------------------------------
    unverified = [l.part.id for l in t.lines if not l.part.verified]
    if unverified:
        result.checks.append(Check(
            "catalog_verified", Status.FAIL,
            "unverified parts cannot be quoted: " + ", ".join(sorted(unverified)),
            repair={"action": "human_verify_parts", "parts": sorted(unverified)},
        ))
    else:
        result.checks.append(Check("catalog_verified", Status.PASS))

    return result


class VisionReviewer(Protocol):
    """4b boundary. A VLM implements this; the pipeline never imports one."""

    def review(self, images: dict[str, bytes], context: str) -> list[Check]: ...


def vision_gate(
    backend: CADBackend, reviewer: VisionReviewer | None, context: str,
    views: tuple[View, ...] = (View.ISO, View.FRONT, View.TOP),
) -> GateResult:
    """4b — plausibility only: floating parts, inverted or backwards components,
    visual intersections, absurd proportions, a machine that plainly could not do
    the stated task."""
    result = GateResult()
    if reviewer is None:
        result.checks.append(Check("vision", Status.SKIPPED, "no reviewer configured"))
        return result

    images = {v.value: backend.screenshot(v) for v in views}
    if not any(images.values()):
        result.checks.append(Check(
            "vision", Status.SKIPPED, f"backend '{backend.name}' renders nothing"))
        return result

    result.checks.extend(reviewer.review(images, context))
    return result
