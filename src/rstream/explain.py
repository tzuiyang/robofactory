"""Customer-facing language for everything the pipeline produces.

The intake is careful never to ask a robotics question. The output has to hold
the same line — "3 DOF: [base] -> shoulder -> upper_link -> elbow" is exactly
the vocabulary we spent the whole conversation avoiding.

Everything here is descriptive plain English. Numbers appear only where a
non-technical person can act on them: how fast, how much, how big.
"""

from __future__ import annotations

from .config import Configuration
from .intake import Requirements
from .topology import Topology

#: module id -> how a person would describe it
MODULE_WORDS: dict[str, str] = {
    "base.fixed": "a fixed base that bolts down to a bench or table",
    "base.diffdrive": "a wheeled base that drives itself around",
    "base.gantry": "an overhead frame that slides in two directions",
    "joint.revolute": "a rotating shoulder joint",
    "joint.revolute.inline": "a rotating joint",
    "link.rigid": "an arm segment",
    "head.sensor": "a head that holds its camera, microphone and speaker",
    "effector.gripper": "a two-finger gripper that opens and closes",
    "effector.vacuum": "a suction pickup, for picking up flat things one layer at a time",
    "panel.control": "a control box holding the electronics",
}

CAPABILITY_WORDS: dict[str, str] = {
    "manipulation": "move things around",
    "grasping": "pick things up and put them down",
    "mobility": "drive itself from place to place",
    "audio_out": "speak out loud",
    "audio_in": "hear you and respond",
    "vision": "see what it is working with",
    "onboard_compute": "think for itself without a laptop attached",
    "precision_placement": "place things accurately, not just roughly",
    "flat_material_handling": "handle flat, floppy material like cloth or paper",
}


def describe_machine(topo: Topology) -> str:
    """One sentence a person can picture."""
    joints = sum(1 for i in topo.instances if i.module.dof > 0
                 and i.module.kind.value == "joint")
    ids = [i.module.id for i in topo.instances]

    if "base.diffdrive" in ids:
        head = " with a head for its camera and speaker" if "head.sensor" in ids else ""
        arm = f", plus an arm with {joints} joints" if joints else ""
        return f"A robot on wheels that drives itself around{head}{arm}."
    if "base.gantry" in ids:
        return ("An overhead frame that slides across the work area, with a pickup "
                "head that moves up and down.")
    if joints:
        grip = ("a two-finger gripper" if "effector.gripper" in ids
                else "a suction pickup" if "effector.vacuum" in ids else "a tool mount")
        return (f"A robot arm with {joints} joints, bolted to a bench, "
                f"with {grip} on the end.")
    return "A fixed unit with sensors and electronics."


def parts_of_machine(topo: Topology) -> list[str]:
    """Bulleted plain-language build-up, in mounting order."""
    out = []
    for i in topo.instances:
        words = MODULE_WORDS.get(i.module.id)
        if words and words not in out:
            out.append(words)
    return out


def what_it_can_do(req: Requirements) -> list[str]:
    return [CAPABILITY_WORDS[c.value] for c in sorted(req.capabilities, key=lambda x: x.value)
            if c.value in CAPABILITY_WORDS]


#: Real-world utilisation. The kinematic cycle time assumes zero dwell, perfect
#: part presentation and 100% uptime. Quoting that raw number ("989 items an
#: hour" for a mug-picking arm) is an over-promise that gets discovered at
#: delivery, which is the expensive time to discover it.
UTILISATION = 0.65


def speed_sentence(config: Configuration) -> str | None:
    if not config.cycle:
        return None
    s = config.cycle.seconds_per_cycle
    realistic = int(config.cycle.parts_per_hour * UTILISATION)
    # Round to something that reads as an estimate, not a measurement.
    step = 10 if realistic < 200 else 50
    realistic = max(step, (realistic // step) * step)
    return (f"About {s:.1f} seconds per item. In practice, expect roughly "
            f"{realistic:,} items an hour once loading, dwell and downtime "
            f"are accounted for.")


def price_sentence(config: Configuration, tier: str) -> str | None:
    t = config.tiers.get(tier)
    if not t:
        return None
    low, high = t.price_range_usd()
    return (f"Estimated ${low:,.0f} to ${high:,.0f}, including building, wiring "
            f"and testing it.")


def caveat_lines() -> list[str]:
    """Said plainly, because it is the honest part and burying it costs trust."""
    return [
        "This is a concept, not a finished quotation.",
        "The simulation shows the machine reaching and moving — it is not a video "
        "of a machine that has been built.",
        "An engineer reviews every design before we give you a firm price.",
    ]
