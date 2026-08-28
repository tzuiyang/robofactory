"""End-to-end orchestration: L1 -> L5, with bounded repair.

Stage-gated by design. At ~85% correctness per stage, eight ungated stages
compound to ~30% end-to-end; gates catch an error at the stage that produced it
instead of letting it accumulate to the output.

The pipeline never delivers to a customer. It stops at AWAITING_REVIEW. The
human gate is both the safety mechanism and the data-collection mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config as L2
from .cad import CADBackend, PlacedPart, View, get_backend
from .cad.null import PANEL_TIERS
from .catalog import Catalog
from .intake import Requirements
from .present import bom_document, build_trajectory
from .record import DesignRecord, Outcome, Stage
from .validate import MAX_REPAIR_ATTEMPTS, Status, deterministic_gate, vision_gate

TIER_ORDER = ["best", "better", "good"]
PANEL_ORDER = ["S", "M", "L"]


@dataclass
class RunResult:
    record: DesignRecord
    configuration: L2.Configuration | None = None
    document: str | None = None
    trajectory: object | None = None
    blocked_on: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.record.outcome is Outcome.AWAITING_REVIEW


def _choose_panel_tier(config: L2.Configuration, tier: str) -> str:
    """Smallest tier whose usable volume holds the panel components."""
    from .validate import _components_envelope

    needed, _ = _components_envelope(config, tier)
    for name in PANEL_ORDER:
        l, w, h = PANEL_TIERS[name]
        if l * w * h * 0.55 >= needed:
            return name
    return PANEL_ORDER[-1]


def run(
    req: Requirements,
    catalog: Catalog,
    backend: CADBackend | str = "null",
    reviewer=None,
    preferred_archetype: str | None = None,
    allow_unverified: bool = False,
) -> RunResult:
    cad = get_backend(backend) if isinstance(backend, str) else backend
    rec = DesignRecord()
    rec.requirements = {
        "task": req.task, "payload_kg": req.payload_kg, "reach_m": req.reach_m,
        "budget_usd": req.budget_usd, "environment": req.environment.value,
    }
    result = RunResult(record=rec)

    # --- L1 ------------------------------------------------------------
    problems = req.validate()
    if problems or req.open_questions:
        rec.log(Stage.INTAKE, False, {"problems": problems, "open": req.open_questions})
        rec.outcome = Outcome.DRAFT
        result.blocked_on = problems + req.open_questions
        return result
    rec.log(Stage.INTAKE, True, {"assumptions": req.assumptions})

    # --- L2 ------------------------------------------------------------
    try:
        cfg = L2.build(req, catalog, preferred_archetype, allow_unverified)
    except L2.InfeasibleError as e:
        rec.log(Stage.CONFIG, False, {}, str(e))
        rec.outcome = Outcome.REJECTED_INFEASIBLE
        result.blocked_on = [str(e)]
        return result

    result.configuration = cfg
    rec.archetype_id = cfg.archetype.id
    rec.sizing = {
        "required_nm": cfg.torque.required_nm, "safety_factor": cfg.torque.safety_factor,
        "cycle_s": cfg.cycle.seconds_per_cycle, "parts_per_hour": cfg.cycle.parts_per_hour,
        # Per-joint load path. Persisted because the review gate captures diffs:
        # an engineer who corrects one joint's actuator is producing a labelled
        # training example, and it is worthless without the load it was sized to.
        "joints": [
            {"label": l.label, "module": l.module_id, "moment_arm_m": l.moment_arm_m,
             "distal_mass_kg": l.distal_mass_kg, "basis": l.sizing_basis,
             "required_nm": l.torque.required_nm if l.torque else None}
            for l in cfg.joint_loads
        ],
    }
    rec.tiers = {
        name: {"parts_usd": t.parts_cost_usd, "range_usd": list(t.price_range_usd())}
        for name, t in cfg.tiers.items()
    }
    rec.log(Stage.CONFIG, True, {"archetype": cfg.archetype.id, "tiers": list(cfg.tiers)})

    # --- L3 + L4 with bounded repair -----------------------------------
    tier = next((t for t in TIER_ORDER if t in cfg.tiers), None)
    gate = None
    for attempt in range(MAX_REPAIR_ATTEMPTS):
        rec.repair_attempts = attempt
        panel = _choose_panel_tier(cfg, tier)

        cad.open_design(f"concept_{rec.id}")
        cad.instantiate_archetype(cfg.archetype.id, cfg.geometry_params)
        cad.place_panel(panel)
        cad.place_parts([
            PlacedPart(l.part.id, f"slot_{i}", l.part.geometry.step_path or "")
            for i, l in enumerate(cfg.tiers[tier].lines)
        ])
        rec.panel_tier = panel
        rec.geometry_params = dict(cfg.geometry_params)
        rec.log(Stage.GEOMETRY, True, {"panel_tier": panel, "tier": tier, "attempt": attempt})

        gate = deterministic_gate(cad, cfg, tier, req.budget_usd)
        rec.checks = [
            {"name": c.name, "status": c.status.value, "detail": c.detail, "repair": c.repair}
            for c in gate.checks
        ]
        if gate.passed:
            break

        # 4c — route on structured repair signals only, never on prose.
        actions = {c.repair["action"] for c in gate.failures if c.repair}
        if "downgrade_tier" in actions:
            remaining = [t for t in TIER_ORDER[TIER_ORDER.index(tier) + 1:] if t in cfg.tiers]
            if remaining:
                tier = remaining[0]
                continue
        if "human_verify_parts" in actions:
            break  # only a human can clear this; retrying cannot help
        break

    rec.log(Stage.VALIDATE, bool(gate and gate.passed),
            {"summary": gate.summary() if gate else "", "attempts": rec.repair_attempts})

    # --- L4b ------------------------------------------------------------
    vgate = vision_gate(cad, reviewer, f"{req.task} / {cfg.archetype.name}")
    rec.checks.extend(
        {"name": c.name, "status": c.status.value, "detail": c.detail, "repair": c.repair}
        for c in vgate.checks
    )
    rec.screenshots = [v.value for v in (View.ISO, View.FRONT, View.TOP)]

    # --- L5 -------------------------------------------------------------
    result.trajectory = build_trajectory(cfg, req)
    result.document = bom_document(cfg, req, tier)
    rec.bom = [
        {"part_id": l.part.id, "part_number": l.part.part_number, "qty": l.qty,
         "role": l.role, "unit_usd": l.part.price_usd, "verified": l.part.verified}
        for l in cfg.tiers[tier].lines
    ]
    low, high = cfg.tiers[tier].price_range_usd()
    rec.quoted_cost_usd = (low + high) / 2
    rec.log(Stage.PRESENT, True, {"tier": tier, "range_usd": [low, high]})

    blocking = [c for c in (gate.failures if gate else [])]
    if blocking:
        result.blocked_on = [f"{c.name}: {c.detail}" for c in blocking]
        rec.outcome = Outcome.DRAFT
    else:
        rec.outcome = Outcome.AWAITING_REVIEW

    cad.close()
    return result
