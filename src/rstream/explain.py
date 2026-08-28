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


#: BOM role text -> what to call it on a shopping list. The internal roles read
#: "joint actuator — shoulder", which is exactly the vocabulary the intake spent
#: five questions avoiding. Anything unmapped falls back to the role text with the
#: known jargon words swapped out, so a new part kind degrades to clumsy English
#: rather than to "actuator".
ROLE_WORDS: dict[str, str] = {
    "motion controller": "the computer that runs it",
    "onboard computer": "a second computer, for seeing and listening",
    "motor driver": "the board that powers the motors",
    "power supply": "the mains power supply",
    "home/limit sensor": "a switch that tells it where 'home' is",
    "end effector": "the gripper on the end",
    "drive wheel": "a wheel",
    "battery": "the battery",
    "camera": "the camera",
    "microphone array": "the microphones",
    "speaker": "the speaker",
    "audio amplifier": "the amplifier that drives the speaker",
}

_JARGON_SWAPS = [("joint actuator", "motor"), ("actuator", "motor"),
                 ("end effector", "gripper"), ("effector", "gripper")]


def role_words(role: str) -> str:
    """Plain-English name for one BOM line."""
    if role in ROLE_WORDS:
        return ROLE_WORDS[role]
    text = role
    for jargon, plain in _JARGON_SWAPS:
        text = text.replace(jargon, plain)
    # "motor — shoulder, elbow" reads better as "motor for the shoulder and elbow"
    if " — " in text:
        thing, where = text.split(" — ", 1)
        parts = [w.strip().replace("_", " ") for w in where.split(",")]
        joined = parts[0] if len(parts) == 1 else (
            ", ".join(parts[:-1]) + " and " + parts[-1])
        return f"{thing.strip()} for the {joined}"
    return text


def shopping_list(config: Configuration, tier: str) -> list[dict]:
    """What to actually order, in the words of someone who has to order it.

    This is the deliverable. A person reading the result screen cannot buy "a
    rotating shoulder joint" — they need a manufacturer, a part number, a price
    and a link. Unverified parts still carry their price here, flagged, because
    withholding it would leave someone with no idea whether the machine is a
    300 dollar project or a 3,000 dollar one. What they never get is a *total*
    presented as a quote: that is the line `catalog_verified` draws.
    """
    out = []
    for line in sorted(config.tiers[tier].lines,
                       key=lambda l: -l.part.price_usd * l.qty):
        p = line.part
        # Some vendors put their own name in the part number ("Raspberry Pi 5 /
        # 8GB"), and "Raspberry Pi Raspberry Pi 5 / 8GB" reads like a bug.
        order_as = (p.part_number if p.part_number.lower().startswith(
            p.manufacturer.lower()) else f"{p.manufacturer} {p.part_number}")
        out.append({
            "qty": line.qty,
            "what": role_words(line.role),
            "manufacturer": p.manufacturer,
            "part_number": p.part_number,
            "order_as": order_as,
            "unit_usd": p.price_usd,
            "line_usd": round(p.price_usd * line.qty, 2),
            "url": p.source_url,
            "confirmed": p.verified,
        })
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
