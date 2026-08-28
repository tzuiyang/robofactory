"""The generalization: any robot = a composition of authored modules."""

import pytest

from rstream.capabilities import Capability as C
from rstream.capabilities import expand, gaps, required_part_kinds
from rstream.topology import TopologyError, synthesize


def test_talking_implies_a_processor_to_talk_with():
    assert C.ONBOARD_COMPUTE in expand({C.AUDIO_OUT})


def test_grasping_implies_manipulation():
    assert C.MANIPULATION in expand({C.GRASPING})


def test_rolling_talking_robot_composes():
    t = synthesize({C.MOBILITY, C.AUDIO_OUT, C.AUDIO_IN}, reach_m=0.3)
    ids = [i.module.id for i in t.instances]
    assert "base.diffdrive" in ids
    assert "head.sensor" in ids
    assert t.dof == 2, "differential drive is 2 DOF"
    assert {"speaker", "microphone", "compute_module"} <= t.consumes_kinds


def test_capability_gated_parts_are_not_bought_unasked():
    """A robot that only talks must not buy a camera."""
    t = synthesize({C.MOBILITY, C.AUDIO_OUT}, reach_m=0.3)
    assert "camera" not in t.consumes_kinds
    assert "camera" in synthesize({C.MOBILITY, C.VISION}, reach_m=0.3).consumes_kinds


def test_flat_material_selects_vacuum_not_gripper():
    t = synthesize({C.FLAT_MATERIAL_HANDLING, C.GRASPING}, reach_m=0.7,
                   workspace_is_planar=True)
    ids = [i.module.id for i in t.instances]
    assert "effector.vacuum" in ids and "effector.gripper" not in ids
    assert any("single layer of cloth" in n for n in t.notes)


def test_arm_has_three_revolute_joints():
    t = synthesize({C.GRASPING}, payload_kg=1.0, reach_m=0.45)
    assert t.dof == 3
    assert t.joint_slots == ["shoulder", "elbow", "wrist"]


def test_every_synthesized_chain_is_mechanically_valid():
    """Interface continuity — an unbuildable chain must not be representable."""
    for caps in (
        {C.GRASPING},
        {C.MOBILITY, C.AUDIO_OUT},
        {C.FLAT_MATERIAL_HANDLING, C.GRASPING},
        {C.MOBILITY, C.GRASPING, C.VISION},
    ):
        t = synthesize(caps, payload_kg=0.5, reach_m=0.4)
        assert t.validate() == [], f"{caps} produced an invalid chain"


def test_parentless_module_must_sit_on_the_ground():
    from rstream.topology import Topology, ModuleInstance
    from rstream.modules import LIBRARY
    t = Topology(instances=[ModuleInstance(LIBRARY["link.rigid"], {}, "floating")])
    assert any("mounts to nothing" in p for p in t.validate())


def test_mobile_manipulator_with_vision_is_valid():
    """The head branches off the base, not off the gripper. A chain model made
    this impossible to express; a tree makes it correct."""
    t = synthesize({C.MOBILITY, C.GRASPING, C.VISION}, payload_kg=0.5, reach_m=0.4)
    assert t.validate() == []
    head = next(i for i in t.instances if i.module.id == "head.sensor")
    assert head.parent == "drive_base", "head must mount to the base, not the arm tip"
    gripper = next(i for i in t.instances if i.module.kind.value == "effector")
    assert gripper.parent != head.parent or gripper.parent == "drive_base"


def test_unknown_parent_is_caught():
    from rstream.topology import Topology, ModuleInstance
    from rstream.modules import LIBRARY
    t = Topology(instances=[
        ModuleInstance(LIBRARY["base.fixed"], {}, "base"),
        ModuleInstance(LIBRARY["joint.revolute"], {}, "j1", parent="nope"),
    ])
    assert any("unknown parent" in p for p in t.validate())


def test_capability_gaps_are_reported_not_dropped():
    """Asking for audio against a catalog with no speaker must be visible."""
    g = gaps({C.AUDIO_OUT}, available_kinds={"actuator", "controller"})
    assert g
    assert "speaker" in str(g[0])
    assert "no such part in the catalog" in str(g[0])


def test_unauthored_modules_are_listed():
    """Blocks L3, not L2 — the BOM is still valid before CAD exists."""
    t = synthesize({C.GRASPING}, reach_m=0.4)
    assert t.unauthored, "no templates authored yet, must be reported"


# --- guided novice intake ------------------------------------------------

def _drive(script):
    from rstream.dialogue import GuidedIntake
    g = GuidedIntake()
    for reply in script:
        q = g.next_question()
        if q is None:
            break
        g.answer(q.key, reply)
    return g


def test_novice_is_never_asked_a_robotics_question():
    """No DOF, payload, reach, actuator, ROS, torque, kinematics."""
    from rstream.dialogue import GuidedIntake
    jargon = ["dof", "payload", "reach", "actuator", "servo", "ros", "torque",
              "kinematic", "end effector", "urdf", "gantry", "scara", "kg", "newton"]
    g = GuidedIntake()
    asked = []
    for reply in ["pick up mugs", "coffee mug", "a desk", "under $5,000", "yes"]:
        q = g.next_question()
        if q is None:
            break
        asked.append((q.text + " " + " ".join(q.options) + " " + q.why).lower())
        g.answer(q.key, reply)
    import re
    for text in asked:
        for word in jargon:
            # Word boundaries matter: "ros" is a substring of "across".
            assert not re.search(rf"\b{re.escape(word)}\b", text), \
                f"jargon {word!r} leaked into: {text[:80]}"


def test_certain_object_needs_no_weight_followup():
    """'coffee mug' is 0.25-0.45 kg — inside one motor class, so don't ask again."""
    g = _drive(["pick up mugs", "coffee mug", "a desk", "under $5,000", "yes"])
    assert "weight_refine" not in g.answers


def test_uncertain_object_triggers_exactly_one_followup():
    """'machined part' spans 0.1-3.0 kg, crossing motor classes — must ask."""
    from rstream.dialogue import GuidedIntake
    g = GuidedIntake()
    g.answer("task", "sort machined parts")
    g.answer("object", "machined part")
    q = g.next_question()
    assert q is not None and q.key == "weight_refine"
    g.answer("weight_refine", "about a laptop")
    assert g.next_question().key == "area", "must not ask about weight twice"


def test_non_handling_robot_is_not_asked_what_it_picks_up():
    g = _drive(["roll around and talk to my kids", "a small room", "under $5,000", "yes"])
    assert "object" not in g.answers
    assert len([k for k in g.answers if k != "confirm"]) <= 3


def test_confirmation_reads_as_english():
    g = _drive(["I want it to pick up mugs from a shelf", "coffee mug", "a desk",
                "under $5,000"])
    s = g.summary()
    assert "machine to pick up mugs" in s
    assert "I want it to" not in s
    # No units in the confirmation — someone who said "coffee mug" cannot judge
    # "0.25-0.45 kg", and showing it invites an argument they cannot win.
    assert "kg" not in s and " m " not in s
    assert "as heavy as coffee mug" in s or "as heavy as a coffee mug" in s


def test_requirements_record_how_each_number_was_guessed():
    g = _drive(["pick up mugs", "coffee mug", "a desk", "under $5,000", "yes"])
    req = g.to_requirements()
    assert req.payload_kg == pytest.approx(0.35, abs=0.01)
    assert any("coffee mug" in a for a in req.assumptions)
    assert any("no robotics background" in a for a in req.assumptions)


def test_mobile_only_robot_is_not_judged_on_manipulator_reach():
    """A rover never reaches for anything; a reach envelope must not reject it."""
    from rstream.catalog import Catalog
    from rstream.config import build
    from dataclasses import replace as dc_replace
    cat = Catalog.load()
    verified = Catalog([dc_replace(p, verified=True) for p in cat.query(allow_unverified=True)])
    g = _drive(["roll around and talk to my kids", "a small room", "under $5,000", "yes"])
    cfg = build(g.to_requirements(), verified)
    assert cfg.topology.dof == 2
    assert any("NOT yet modelled" in a for a in cfg.assumptions)


def test_internal_errors_are_translated_for_customers():
    from rstream.dialogue import plain_failure
    out = plain_failure("no tier could be configured from the current catalog")
    assert "catalog" not in out.lower() and "tier" not in out.lower()
    assert "lighter" in out or "smaller" in out


def test_throughput_claim_is_derated_not_theoretical():
    """The raw kinematic rate assumes zero dwell and 100% uptime. Quoting it is
    an over-promise discovered at delivery."""
    from rstream.catalog import Catalog
    from rstream.config import build
    from rstream.explain import UTILISATION, speed_sentence
    from dataclasses import replace as dc_replace
    cat = Catalog.load()
    v = Catalog([dc_replace(p, verified=True) for p in cat.query(allow_unverified=True)])
    g = _drive(["pick up mugs", "coffee mug", "a desk", "under $5,000", "yes"])
    cfg = build(g.to_requirements(), v)
    sentence = speed_sentence(cfg)
    theoretical = int(cfg.cycle.parts_per_hour)
    assert str(theoretical) not in sentence.replace(",", ""), "raw rate must not be quoted"
    assert UTILISATION < 1.0
    assert "downtime" in sentence
