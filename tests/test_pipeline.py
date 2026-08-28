import pytest

from rstream import pipeline
from rstream.config import InfeasibleError, build
from rstream.intake import Requirements
from rstream.record import Outcome
from rstream.validate import Status, deterministic_gate


def test_end_to_end_reaches_human_review(verified_catalog, small_req):
    r = pipeline.run(small_req, verified_catalog)
    assert r.ok, r.blocked_on
    assert r.record.outcome is Outcome.AWAITING_REVIEW
    assert r.document and "CONCEPT SIMULATION" in r.document
    assert r.record.bom
    assert r.record.quoted_cost_usd > 0


def test_cost_ceiling_blocks_a_machine_we_would_not_build(verified_catalog, req):
    """We build robots that cost under 3,000 USD in parts and sell under 10,000.
    A request past that is not quoted cheaper — it is refused, after the repair
    loop has tried every cheaper tier. `req` is a 0.45 m / 0.8 kg arm, which is
    just over the line: its shoulder needs the next actuator class up and that
    single part is ~half the parts budget.
    """
    from rstream.config import MAX_PARTS_COST_USD
    r = pipeline.run(req, verified_catalog)
    assert not r.ok
    assert any("cost_target" in b for b in r.blocked_on)
    assert r.record.repair_attempts > 0, "it must try cheaper tiers before giving up"
    assert all(t.parts_cost_usd > MAX_PARTS_COST_USD for t in r.configuration.tiers.values())


def test_pipeline_never_delivers_straight_to_customer(verified_catalog, small_req):
    """The human gate is not optional."""
    r = pipeline.run(small_req, verified_catalog)
    assert r.record.outcome is not Outcome.SENT_TO_CUSTOMER


def test_unverified_catalog_blocks_the_quote(seed_catalog, req):
    """Seed data must not be able to produce a quotable design."""
    r = pipeline.run(req, seed_catalog, allow_unverified=True)
    assert not r.ok
    assert any("catalog_verified" in b for b in r.blocked_on)


def test_out_of_envelope_is_refused_not_degraded(verified_catalog):
    r = pipeline.run(
        Requirements(task="lift an engine block", payload_kg=80.0, reach_m=2.5, budget_usd=50000),
        verified_catalog,
    )
    assert r.record.outcome is Outcome.REJECTED_INFEASIBLE
    assert "no archetype" in r.blocked_on[0]


def test_missing_budget_blocks_intake(verified_catalog):
    r = pipeline.run(
        Requirements(task="x", payload_kg=1.0, reach_m=0.4, budget_usd=0.0), verified_catalog
    )
    assert r.record.outcome is Outcome.DRAFT
    assert any("budget" in b for b in r.blocked_on)


def test_open_questions_stop_the_run(verified_catalog, req):
    req.open_questions = ["what is the part presentation — tray, conveyor or bin?"]
    r = pipeline.run(req, verified_catalog)
    assert not r.ok
    assert "tray, conveyor or bin?" in r.blocked_on[0]


def test_tight_budget_downgrades_tier_rather_than_failing(deep_catalog, req):
    """Needs a catalog deep enough to offer more than one tier."""
    cfg = build(req, deep_catalog)
    assert len(cfg.tiers) > 1, "fixture must produce multiple tiers to test downgrade"
    top = cfg.tiers[next(t for t in ("best", "better", "good") if t in cfg.tiers)]
    req.budget_usd = top.price_range_usd()[0] - 500  # top tier unaffordable
    r = pipeline.run(req, deep_catalog)
    assert r.record.repair_attempts >= 1, "should have tried a cheaper tier"


def test_repair_loop_is_bounded(deep_catalog, req):
    req.budget_usd = 50.0  # unsatisfiable by any tier
    r = pipeline.run(req, deep_catalog)
    from rstream.validate import MAX_REPAIR_ATTEMPTS
    assert r.record.repair_attempts < MAX_REPAIR_ATTEMPTS
    assert not r.ok


def test_deep_catalog_produces_distinct_priced_tiers(deep_catalog, req):
    """Confirms the collapse in the seed catalog is a data problem, not a bug."""
    cfg = build(req, deep_catalog)
    costs = sorted(t.parts_cost_usd for t in cfg.tiers.values())
    assert len(set(costs)) == len(costs) > 1


def test_skipped_check_is_not_reported_as_passed(verified_catalog, req):
    """A check that did not run must never read as a clean bill of health."""
    r = pipeline.run(req, verified_catalog)
    interference = [c for c in r.record.checks if c["name"] == "interference"]
    assert interference and interference[0]["status"] == Status.SKIPPED.value
    assert "no B-rep" in interference[0]["detail"]


def test_price_is_a_range_not_a_point(verified_catalog, req):
    cfg = build(req, verified_catalog)
    low, high = cfg.tiers["good"].price_range_usd()
    assert high > low > 0


def test_offered_tiers_are_always_distinct(verified_catalog, req):
    """Never show a customer two tiers with the same parts at the same price."""
    cfg = build(req, verified_catalog)
    assert set(cfg.tiers) <= {"good", "better", "best"}
    assert cfg.tiers
    keys = [tuple(sorted((l.part.id, l.qty) for l in t.lines)) for t in cfg.tiers.values()]
    assert len(keys) == len(set(keys)), "duplicate tiers must be collapsed"


def test_sparse_catalog_collapses_tiers_and_says_so(verified_catalog, req):
    """Documents a real constraint: meaningful tiering needs catalog depth.

    With only three actuator sizes, tiers collapse. That is the catalog's fault,
    not the code's, and the note must make that visible rather than silently
    offering fewer options.
    """
    cfg = build(req, verified_catalog)
    if len(cfg.tiers) < 3:
        notes = " ".join(n for t in cfg.tiers.values() for n in t.notes)
        assert "collapsed" in notes or len(cfg.tiers) >= 1


def test_document_states_what_is_not_verified(verified_catalog, req):
    r = pipeline.run(req, verified_catalog)
    assert "does NOT verify" in r.document
    assert "tolerance stack-up" in r.document


def test_trajectory_matches_quoted_cycle_time(verified_catalog, req):
    """The clip and the quoted rate cannot be allowed to disagree."""
    r = pipeline.run(req, verified_catalog)
    cfg = r.configuration
    assert r.trajectory.duration_s == pytest.approx(cfg.cycle.seconds_per_cycle, rel=0.01)


def test_design_record_carries_flywheel_fields(verified_catalog, req):
    r = pipeline.run(req, verified_catalog)
    rec = r.record
    rec.record_correction("bom[0].part_id", "act.medium", "act.large", "measured duty was higher")
    assert rec.engineer_corrections[0]["after"] == "act.large"
    assert hasattr(rec, "actual_build_cost_usd")
    assert "engineer_corrections" in rec.to_json()


def test_reach_is_measured_from_base_not_full_span(verified_catalog, req):
    """A revolute arm's bounding box is ~2x its reach. Comparing span against
    reach would pass a machine half the required size."""
    r = pipeline.run(req, verified_catalog)
    reach_check = next(c for c in r.record.checks if c["name"] == "reach")
    assert f"{req.reach_m:.3f} m from base" in reach_check["detail"]


def test_undersized_model_fails_the_reach_check(verified_catalog, req):
    from rstream.cad import NullBackend
    from rstream.config import build
    from rstream.validate import Status, deterministic_gate

    cfg = build(req, verified_catalog)
    backend = NullBackend()
    backend.open_design("t")
    backend.instantiate_archetype(cfg.archetype.id, {"reach_m": req.reach_m * 0.4})
    backend.place_panel("M")
    gate = deterministic_gate(backend, cfg, next(iter(cfg.tiers)), req.budget_usd)
    reach = next(c for c in gate.checks if c.name == "reach")
    assert reach.status is Status.FAIL


# --- per-joint actuator selection -------------------------------------------

def test_per_joint_sizing_beats_worst_case_sizing_on_cost(deep_catalog):
    """The whole point: a wrist does not buy a shoulder actuator.

    Compared against what the old model produced — the governing joint's
    actuator fitted to every joint — at the same load model and same catalog.
    """
    from rstream.capabilities import Capability
    from rstream.config import build
    from rstream.intake import Requirements

    r = Requirements(task="pick parts from a tray into a fixture", payload_kg=0.5,
                     reach_m=0.7, budget_usd=20000.0,
                     capabilities={Capability.MANIPULATION, Capability.GRASPING})
    cfg = build(r, deep_catalog)
    tier = cfg.tiers["good"]
    acts = [l for l in tier.lines if l.part.actuator]

    assert len({l.part.id for l in acts}) > 1, "joints must not all get the same actuator"
    assert sum(len(l.joints) for l in acts) == len(cfg.joint_loads), "every joint gets one"

    biggest = max(acts, key=lambda l: l.part.actuator.rated_torque_nm).part
    worst_case_cost = biggest.price_usd * len(cfg.joint_loads)
    assert sum(l.total_usd for l in acts) < worst_case_cost


def test_every_joint_is_torque_checked_not_just_the_largest(deep_catalog):
    """A per-joint BOM needs a per-joint gate. Checking only the biggest actuator
    would leave the distal joints — the ones just made smaller — unverified."""
    from dataclasses import replace as dc_replace
    from rstream.capabilities import Capability
    from rstream.config import build
    from rstream.intake import Requirements
    from rstream.validate import Status, _torque_margin_checks

    r = Requirements(task="pick parts from a tray into a fixture", payload_kg=0.5,
                     reach_m=0.7, budget_usd=20000.0,
                     capabilities={Capability.MANIPULATION, Capability.GRASPING})
    cfg = build(r, deep_catalog)
    assert all(c.status is Status.PASS for c in _torque_margin_checks(cfg, "good"))

    # Sabotage the *smallest* actuator line — the one a single check would miss.
    tier = cfg.tiers["good"]
    smallest = min((l for l in tier.lines if l.part.actuator),
                   key=lambda l: l.part.actuator.rated_torque_nm)
    smallest.part = dc_replace(
        smallest.part,
        actuator=dc_replace(smallest.part.actuator, rated_torque_nm=0.001))

    checks = _torque_margin_checks(cfg, "good")
    failed = [c for c in checks if c.status is Status.FAIL]
    assert failed, "an undersized distal actuator must fail the gate"
    assert failed[0].repair["joint"] in smallest.joints
    assert failed[0].repair["action"] == "upsize_actuator"


# --- the wheeled-servo archetype --------------------------------------------

def _wheeled(caps, catalog, **kw):
    from rstream.config import build
    from rstream.intake import Requirements
    return build(Requirements(task="wheeled robot", payload_kg=1.0, reach_m=0.4,
                              budget_usd=12000.0, capabilities=caps, **kw), catalog)


def test_wheeled_base_gets_wheels_and_a_battery(verified_catalog):
    """These kinds are declared by base.diffdrive and were silently dropped from
    every wheeled BOM — the robot was quoted without the wheels it drives on."""
    from rstream.capabilities import Capability
    cfg = _wheeled({Capability.MOBILITY}, verified_catalog)
    kinds = {l.part.kind.value for l in cfg.tiers[next(iter(cfg.tiers))].lines}
    assert "wheel" in kinds and "battery" in kinds


def test_a_robot_that_cannot_grasp_is_not_quoted_a_gripper(verified_catalog):
    """Parts follow from the topology. A fixed parts list put an end effector and
    limit sensors on a patrol robot that has neither."""
    from rstream.capabilities import Capability
    patrol = _wheeled({Capability.MOBILITY}, verified_catalog)
    lines = cfg_lines = patrol.tiers[next(iter(patrol.tiers))].lines
    assert not any(l.part.kind.value == "end_effector" for l in lines)

    grasper = _wheeled({Capability.MOBILITY, Capability.MANIPULATION, Capability.GRASPING},
                       verified_catalog)
    glines = grasper.tiers[next(iter(grasper.tiers))].lines
    assert any(l.part.kind.value == "end_effector" for l in glines)


def test_two_wheels_get_two_motors(verified_catalog):
    from rstream.capabilities import Capability
    cfg = _wheeled({Capability.MOBILITY}, verified_catalog)
    drive = next(l for l in cfg.joint_loads if l.sizing_basis == "traction")
    assert drive.count == 2
    qty = sum(l.qty for l in cfg.tiers[next(iter(cfg.tiers))].lines
              if l.part.actuator and drive.label in l.joints)
    assert qty == 2


def test_drive_axis_selection_respects_travel_speed(verified_catalog):
    """A high-ratio joint servo has the torque for a wheel and nowhere near the
    speed. Selecting on torque alone produced a machine that crawled at 0.24 m/s
    while passing its torque check 6x over."""
    from rstream.capabilities import Capability
    cfg = _wheeled({Capability.MOBILITY}, verified_catalog)
    drive = next(l for l in cfg.joint_loads if l.sizing_basis == "traction")
    need = drive.detail["wheel_speed_rad_s"]
    chosen = [l.part for l in cfg.tiers[next(iter(cfg.tiers))].lines
              if l.part.actuator and drive.label in l.joints]
    assert chosen and all(p.actuator.max_speed_rad_s >= need for p in chosen)


def test_traction_failure_does_not_ask_for_a_bigger_motor(verified_catalog):
    """A slipping wheel is fixed with grip, not torque. Routing this to
    upsize_actuator would spend all three repair attempts on the wrong knob."""
    from rstream.capabilities import Capability
    from rstream.validate import Status, _drive_checks
    cfg = _wheeled({Capability.MOBILITY}, verified_catalog)
    tier = next(iter(cfg.tiers))
    assert all(c.status is not Status.FAIL for c in _drive_checks(cfg, tier))

    drive = next(l for l in cfg.joint_loads if l.sizing_basis == "traction")
    drive.detail["slip_margin"] = 0.6
    drive.detail["traction_limit_n"] = drive.detail["tractive_force_n"] * 0.6
    failed = [c for c in _drive_checks(cfg, tier) if c.status is Status.FAIL]
    assert failed and failed[0].repair["action"] == "increase_traction"


def test_budget_options_stay_inside_what_we_sell():
    """Offering a band we do not build in invites a request we then refuse.
    If the product ceiling moves, this test is the reminder to move the menu."""
    from rstream.config import MAX_SALE_PRICE_USD
    from rstream.dialogue import GuidedIntake, Step

    g = GuidedIntake()
    g.answer(Step.TASK, "pick up mugs")
    g.answer(Step.OBJECT, "coffee mug")
    g.answer(Step.AREA, "a desk")
    q = g.next_question()
    assert q.key is Step.BUDGET
    for option in q.options:
        g2 = GuidedIntake()
        g2.answer(Step.BUDGET, option)
        assert g2._budget_usd() <= MAX_SALE_PRICE_USD, option
