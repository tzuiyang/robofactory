"""L1 — guided intake for people with zero robotics background.

Design rules, in priority order:

1. **Never ask a robotics question.** No DOF, no payload in kg, no reach, no
   actuator class, no ROS. Ask about the person's own world — what it picks up,
   how big the area is — and derive the engineering.

2. **Only ask when the answer changes the machine.** Every derived quantity is a
   RANGE. A follow-up is asked only when that range straddles a decision
   boundary (an actuator class, an archetype envelope). "Coffee mugs" gives
   0.25-0.45 kg, entirely inside one actuator class, so we never ask again.
   "Machined parts" gives 0.1-3.0 kg, which crosses three classes, so we ask
   exactly one disambiguating question. This is what keeps the conversation to
   3-5 questions instead of a 12-field form.

3. **Confirm, don't specify.** Where possible propose a reading and let them
   correct it. Confirming is far easier than specifying.

4. **Say no early and kindly.** Many requests are outside what can be built.
   Finding that out at question 3 is a good outcome; finding out after a quote
   is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .capabilities import Capability
from .intake import Environment, Requirements
from .reference import OBJECTS, SPACES, lookup, space

#: Payload thresholds where the actuator class changes. A range that stays
#: between two adjacent boundaries needs no follow-up.
PAYLOAD_BOUNDARIES = [0.5, 2.0, 5.0]
#: Reach thresholds where the machine type changes (bench arm / gantry / large).
REACH_BOUNDARIES = [0.6, 1.5]


def _straddles(lo: float, hi: float, boundaries: list[float]) -> bool:
    return any(lo < b < hi for b in boundaries)


def _bucket_label(lo: float, hi: float) -> str:
    mid = (lo + hi) / 2
    if mid < 0.5:
        return "light"
    if mid < 2.0:
        return "medium"
    if mid < 5.0:
        return "heavy"
    return "very heavy"


@dataclass
class Question:
    key: str
    text: str
    #: Plain-language options. Empty means free text.
    options: list[str] = field(default_factory=list)
    why: str = ""       # shown on request; never robotics jargon
    optional: bool = False


@dataclass
class Estimate:
    lo: float
    hi: float
    source: str

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2

    @property
    def uncertain(self) -> bool:
        return self.hi > self.lo * 3


#: Plain words -> capabilities. In production the LLM does this step; the table
#: is the fallback and the test oracle. Keeping a table means the same sentence
#: always produces the same machine.
KEYWORDS: dict[str, list[Capability]] = {
    "pick": [Capability.GRASPING], "grab": [Capability.GRASPING],
    "move": [Capability.MANIPULATION], "sort": [Capability.GRASPING, Capability.VISION],
    "place": [Capability.GRASPING, Capability.PRECISION_PLACEMENT],
    "fold": [Capability.FLAT_MATERIAL_HANDLING, Capability.GRASPING],
    "laundry": [Capability.FLAT_MATERIAL_HANDLING, Capability.GRASPING],
    "clothes": [Capability.FLAT_MATERIAL_HANDLING, Capability.GRASPING],
    "drive": [Capability.MOBILITY], "roll": [Capability.MOBILITY],
    "move around": [Capability.MOBILITY], "follow": [Capability.MOBILITY, Capability.VISION],
    "talk": [Capability.AUDIO_OUT], "speak": [Capability.AUDIO_OUT],
    "listen": [Capability.AUDIO_IN], "voice": [Capability.AUDIO_IN, Capability.AUDIO_OUT],
    "see": [Capability.VISION], "camera": [Capability.VISION],
    "inspect": [Capability.VISION], "look": [Capability.VISION],
}


def capabilities_from_text(text: str) -> set[Capability]:
    caps: set[Capability] = set()
    t = text.lower()
    for word, cs in KEYWORDS.items():
        if word in t:
            caps.update(cs)
    return caps


class Step(str, Enum):
    TASK = "task"
    OBJECT = "object"
    WEIGHT_REFINE = "weight_refine"
    AREA = "area"
    THROUGHPUT = "throughput"
    BUDGET = "budget"
    CONFIRM = "confirm"
    DONE = "done"


@dataclass
class GuidedIntake:
    """A short conversation that ends in a valid Requirements object."""

    answers: dict[str, str] = field(default_factory=dict)
    payload: Estimate | None = None
    reach: Estimate | None = None
    caps: set[Capability] = field(default_factory=set)
    blocked: str | None = None

    # --- conversation ----------------------------------------------------
    def next_question(self) -> Question | None:
        if self.blocked:
            return None

        if Step.TASK not in self.answers:
            return Question(
                Step.TASK,
                "In your own words, what do you want this machine to do?",
                why="Everything else follows from this. Plain language is fine.",
            )

        if not self._handles_objects():
            # A machine that only drives and talks handles nothing; skip ahead.
            pass
        elif Step.OBJECT not in self.answers:
            return Question(
                Step.OBJECT,
                "What will it be picking up or handling?",
                options=["coffee mug", "small parcel", "t-shirt", "machined part",
                         "book", "something else"],
                why="This tells us how strong it needs to be.",
            )
        elif self.payload and _straddles(self.payload.lo, self.payload.hi, PAYLOAD_BOUNDARIES) \
                and Step.WEIGHT_REFINE not in self.answers:
            return Question(
                Step.WEIGHT_REFINE,
                "Roughly how heavy is one of them?",
                options=["lighter than a phone", "about a coffee mug",
                         "about a laptop", "about a brick", "heavier than that"],
                why="Your answer spans a few different motor sizes, so this one matters.",
            )

        if Step.AREA not in self.answers:
            return Question(
                Step.AREA,
                "How big is the area it needs to work in?",
                options=list(SPACES.keys()) + ["something else"],
                why="This sets how big the machine needs to be.",
            )

        if Step.BUDGET not in self.answers:
            return Question(
                Step.BUDGET,
                "What budget range are you working with?",
                # Bounded by what we actually sell. Offering a $50,000 band for
                # machines that top out near $10,000 invites someone to describe
                # a job we will then refuse — a worse experience than a smaller
                # menu, and it wastes their time before ours.
                options=["under $3,000", "$3,000 - $6,000",
                         "$6,000 - $10,000", "not sure yet"],
                why="We will show you what is achievable at your level rather than "
                    "designing something you cannot buy.",
            )

        if Step.CONFIRM not in self.answers:
            return Question(
                Step.CONFIRM,
                self.summary() + "\n\nHave I understood that correctly?",
                options=["yes, that's right", "not quite"],
            )

        return None

    def answer(self, key: str, value: str) -> None:
        self.answers[key] = value

        if key == Step.TASK:
            self.caps = capabilities_from_text(value)
            if not self.caps:
                self.caps = {Capability.GRASPING}  # the common case
            return

        if key == Step.OBJECT:
            ref = lookup(value)
            if ref is None:
                # Unmatched: fall back to asking about weight directly rather
                # than guessing. A wrong guess here mis-sizes the whole machine.
                self.payload = Estimate(0.1, 5.0, f"unrecognised: {value!r}")
                return
            self.payload = Estimate(*ref.mass_kg, source=ref.name)
            return

        if key == Step.WEIGHT_REFINE:
            self.payload = Estimate(*{
                "lighter than a phone": (0.02, 0.15),
                "about a coffee mug": (0.25, 0.45),
                "about a laptop": (1.2, 2.5),
                "about a brick": (2.0, 3.5),
                "heavier than that": (5.0, 25.0),
            }.get(value, (0.1, 3.0)), source=value)
            return

        if key == Step.AREA:
            sp = space(value)
            self.reach = Estimate(*sp, source=value) if sp else Estimate(0.3, 1.0, value)
            return

        if key == Step.BUDGET:
            return

    # --- derivation -------------------------------------------------------
    def _handles_objects(self) -> bool:
        return bool(self.caps & {Capability.GRASPING, Capability.MANIPULATION,
                                 Capability.FLAT_MATERIAL_HANDLING})

    def _budget_usd(self) -> float:
        return {
            "under $3,000": 3000.0,
            "$3,000 - $6,000": 6000.0,
            "$6,000 - $10,000": 10000.0,
            "not sure yet": 10000.0,
        }.get(self.answers.get(Step.BUDGET, ""), 10000.0)

    @staticmethod
    def _as_predicate(task: str) -> str:
        """Turn 'I want it to pick up mugs' into 'picks up mugs'.

        People answer conversationally. Echoing the raw sentence back produces
        "a machine that I want it to pick up mugs", which reads as though the app
        did not understand them — the opposite of what a confirmation is for.
        """
        t = task.strip().rstrip(".")
        for prefix in ("i want it to ", "i want a robot that ", "i want a machine that ",
                       "i need it to ", "i want to ", "it should ", "i need a robot that ",
                       "a robot that can ", "a robot that ", "a machine that ", "it needs to "):
            if t.lower().startswith(prefix):
                return t[len(prefix):]
        return t

    def summary(self) -> str:
        """Plain language, no jargon. This is what they confirm."""
        bits = [f"You want a machine to {self._as_predicate(self.answers.get(Step.TASK, ''))}."]
        if self.payload:
            src = self.payload.source
            for lead in ("about ", "roughly "):
                if src.startswith(lead):
                    src = src[len(lead):]
            if src.startswith(("lighter", "heavier")):
                bits.append(f"It handles things {src} than that.")
            else:
                article = "" if src.startswith(("a ", "an ")) else "a "
                bits.append(f"It handles things about as heavy as {article}{src}.")
        if self.reach:
            bits.append(f"It works across an area about the size of {self.reach.source}.")
        b = self.answers.get(Step.BUDGET)
        if b:
            bits.append(f"Budget: {b}.")
        return " ".join(bits)

    @property
    def complete(self) -> bool:
        return self.next_question() is None and not self.blocked

    def to_requirements(self) -> Requirements:
        if self.blocked:
            raise ValueError(self.blocked)
        payload = self.payload.mid if self.payload else 0.2
        # Reach is half the working area: the machine sits at the middle of it.
        reach = (self.reach.hi / 2) if self.reach else 0.4

        assumptions = []
        if self.payload:
            assumptions.append(
                f"payload taken as {payload:.2f} kg, estimated from "
                f"'{self.payload.source}' ({self.payload.lo:.2g}-{self.payload.hi:.2g} kg)")
        if self.reach:
            assumptions.append(
                f"reach taken as {reach:.2f} m, from a working area of "
                f"'{self.reach.source}'")
        assumptions.append(
            "the customer has no robotics background; every technical value here "
            "was derived from plain-language answers and must be confirmed at review")

        return Requirements(
            task=self.answers.get(Step.TASK, ""),
            payload_kg=round(payload, 3),
            reach_m=round(reach, 3),
            budget_usd=self._budget_usd(),
            capabilities=self.caps,
            workspace_is_planar=Capability.FLAT_MATERIAL_HANDLING in self.caps,
            environment=Environment.BENCHTOP,
            assumptions=assumptions,
        )


#: Engineer-speak -> what a non-technical person can act on. Every failure the
#: customer can see must be phrased as a choice they can make, not a diagnosis
#: they cannot parse.
#: Ordered: the first needle that matches wins, so the specific causes must sit
#: above the generic ones. "no tier could be configured" now carries the
#: underlying reason, and "not strong enough" is the wrong thing to tell someone
#: whose design is fine and whose catalog is merely unchecked.
PLAIN_FAILURES: list[tuple[str, str]] = [
    ("unverified parts cannot be quoted",
     "We're still confirming prices on some parts, so this isn't a firm quote "
     "yet. Everything else in the design stands."),
    ("no tier could be configured",
     "The parts we stock aren't strong enough for something this heavy at this "
     "distance. Two options: handle a lighter item, or work across a smaller "
     "area. Either one brings it back into range."),
    ("no catalogued actuator",
     "This needs a stronger motor than we currently stock. We can source one, "
     "but it will add to the lead time and the cost."),
    ("costs more in parts",
     "This one comes out more expensive than the machines we build. Something "
     "a bit smaller, or handling a lighter item, brings it back into range — "
     "and those are usually the two easiest things to change."),
    ("no archetype covers",
     "This is bigger than the machines we build. We'd rather tell you now than "
     "quote something we haven't proven."),
    ("not mechanically valid",
     "The combination you've described can't be assembled from our standard "
     "parts. Tell us which part of the job matters most and we'll rework it."),
]


def plain_failure(message: str) -> str:
    """Translate an internal error for a customer-facing screen.

    Falls back to a neutral sentence rather than leaking the raw message —
    'no tier could be configured from the current catalog' tells a shop owner
    nothing they can do anything about.
    """
    low = message.lower()
    for needle, friendly in PLAIN_FAILURES:
        if needle in low:
            return friendly
    return ("We can't build this one as described. Tell us more about what "
            "matters most and we'll take another pass.")
