"""L1.5 — task -> capabilities -> subsystems.

The step that makes the app general. "A rolling robot that talks" and "a machine
that folds laundry" are not different products; they are different *capability
sets* over one module and part library.

An LLM does the task->capability mapping (language understanding, which it is
good at). Capability->subsystem is a fixed table, because "talks" always means
an audio output chain and that should not be re-derived, or hallucinated, per run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Capability(str, Enum):
    MANIPULATION = "manipulation"      # move a payload through space
    MOBILITY = "mobility"              # move the machine itself
    GRASPING = "grasping"
    AUDIO_OUT = "audio_out"            # "talks"
    AUDIO_IN = "audio_in"              # "listens", voice commands
    VISION = "vision"
    ONBOARD_COMPUTE = "onboard_compute"  # local inference / LLM on device
    PRECISION_PLACEMENT = "precision_placement"
    FLAT_MATERIAL_HANDLING = "flat_material_handling"  # fabric, sheet, paper


#: Capability -> catalog part kinds that must appear in the BOM.
#: A fixed table on purpose: this is knowledge, not a judgement call.
SUBSYSTEMS: dict[Capability, list[str]] = {
    Capability.MANIPULATION: ["actuator", "driver"],
    Capability.MOBILITY: ["actuator", "driver", "wheel", "battery"],
    Capability.GRASPING: ["end_effector"],
    Capability.AUDIO_OUT: ["speaker", "audio_amp"],
    Capability.AUDIO_IN: ["microphone"],
    Capability.VISION: ["camera"],
    Capability.ONBOARD_COMPUTE: ["compute_module"],
    Capability.PRECISION_PLACEMENT: ["sensor"],
    Capability.FLAT_MATERIAL_HANDLING: ["end_effector", "sensor"],
}

#: Capabilities that imply others. Applied transitively.
IMPLIES: dict[Capability, list[Capability]] = {
    Capability.AUDIO_IN: [Capability.ONBOARD_COMPUTE],
    Capability.AUDIO_OUT: [Capability.ONBOARD_COMPUTE],
    Capability.VISION: [Capability.ONBOARD_COMPUTE],
    Capability.GRASPING: [Capability.MANIPULATION],
    Capability.FLAT_MATERIAL_HANDLING: [Capability.MANIPULATION, Capability.VISION],
}


def expand(caps: set[Capability]) -> set[Capability]:
    """Close a capability set under implication.

    "It talks" implies a processor to talk *with*. Missing that is exactly the
    kind of omission that makes a BOM unbuildable, so it is a rule, not a hope.
    """
    out = set(caps)
    changed = True
    while changed:
        changed = False
        for c in list(out):
            for implied in IMPLIES.get(c, []):
                if implied not in out:
                    out.add(implied)
                    changed = True
    return out


def required_part_kinds(caps: set[Capability]) -> set[str]:
    kinds: set[str] = set()
    for c in expand(caps):
        kinds.update(SUBSYSTEMS.get(c, []))
    return kinds


@dataclass
class CapabilityGap:
    """A capability we understand but cannot yet supply from the catalog."""

    capability: Capability
    missing_kinds: list[str]

    def __str__(self) -> str:
        return (
            f"{self.capability.value} needs {', '.join(self.missing_kinds)} — "
            "no such part in the catalog. Add it (offline, by a human) or drop the capability."
        )


def gaps(caps: set[Capability], available_kinds: set[str]) -> list[CapabilityGap]:
    """What the customer asked for that we cannot currently build.

    Reported rather than silently dropped: a robot quoted without the speaker it
    was asked for is a lost deal at delivery, not at quote.
    """
    out = []
    for c in sorted(expand(caps), key=lambda x: x.value):
        missing = [k for k in SUBSYSTEMS.get(c, []) if k not in available_kinds]
        if missing:
            out.append(CapabilityGap(c, missing))
    return out
