"""Everyday-object reference table: the novice's units.

A person with no robotics background cannot answer "payload in kg" or "reach in
metres". They can answer "it picks up coffee mugs" and "about the size of a
desk". This table converts the second into the first.

A table rather than an LLM estimate on purpose: it is auditable, identical
across runs, and correctable by a human when it is wrong. An LLM guessing the
mass of a "small box" differently on each run would make the same request
produce different machines.

Values are typical ranges, not precision data. The range IS the point — it is
what drives whether we need to ask a follow-up question (see dialogue.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    name: str
    mass_kg: tuple[float, float]      # (low, high)
    longest_dim_m: tuple[float, float]
    note: str = ""


OBJECTS: dict[str, Ref] = {r.name: r for r in [
    Ref("envelope",        (0.005, 0.05), (0.10, 0.35)),
    Ref("sheet of paper",  (0.004, 0.01), (0.21, 0.30)),
    Ref("phone",           (0.15, 0.25),  (0.14, 0.17)),
    Ref("coffee mug",      (0.25, 0.45),  (0.08, 0.13)),
    Ref("soda can",        (0.33, 0.40),  (0.12, 0.13)),
    Ref("book",            (0.30, 1.20),  (0.18, 0.30)),
    Ref("shoe",            (0.30, 0.90),  (0.25, 0.33)),
    Ref("t-shirt",         (0.12, 0.25),  (0.50, 0.75), "folded size varies hugely"),
    Ref("towel",           (0.35, 0.80),  (0.60, 1.40)),
    Ref("bed sheet",       (0.50, 1.50),  (1.40, 2.60)),
    Ref("plate",           (0.40, 0.90),  (0.20, 0.30)),
    Ref("water bottle",    (0.50, 1.10),  (0.20, 0.32)),
    Ref("laptop",          (1.20, 2.50),  (0.30, 0.40)),
    Ref("brick",           (2.00, 3.50),  (0.20, 0.24)),
    Ref("toolbox",         (3.00, 12.0),  (0.35, 0.60)),
    Ref("bag of groceries",(2.00, 8.00),  (0.30, 0.45), "highly variable"),
    Ref("car wheel",       (15.0, 25.0),  (0.55, 0.70)),
    Ref("small parcel",    (0.20, 2.00),  (0.15, 0.40), "very wide range — expect a follow-up"),
    Ref("machined part",   (0.10, 3.00),  (0.03, 0.20), "very wide range — expect a follow-up"),
]}

#: Everyday spaces -> the working area the machine must cover.
SPACES: dict[str, tuple[float, float]] = {
    "a shoebox":            (0.20, 0.35),
    "a dinner plate":       (0.25, 0.30),
    "a laptop":             (0.30, 0.40),
    "a desk":               (0.60, 1.40),
    "a dining table":       (0.90, 1.80),
    "a kitchen counter":    (0.60, 2.40),
    "a doorway":            (0.80, 2.00),
    "a small room":         (2.50, 4.00),
    "a garage":             (3.00, 6.00),
}


def lookup(name: str) -> Ref | None:
    """Tolerant match: 'a coffee mug', 'MUGS', 'mug' all resolve.

    Deliberately forgiving — a novice types what they say out loud, and making
    them guess our vocabulary is exactly the friction this module exists to
    remove. An unmatched term is not an error; the caller asks a follow-up.
    """
    q = name.lower().strip().strip(".!?")
    for prefix in ("a ", "an ", "the ", "some ", "my "):
        if q.startswith(prefix):
            q = q[len(prefix):]

    forms = [q]
    if q.endswith("es"):
        forms.append(q[:-2])
    if q.endswith("s"):
        forms.append(q[:-1])

    for f in forms:
        if f in OBJECTS:
            return OBJECTS[f]
    # substring either direction: "mug" matches "coffee mug", "coffee mugs" too
    for f in forms:
        for name_, ref in OBJECTS.items():
            if f and (f in name_ or name_ in f):
                return ref
    return None


def space(name: str) -> tuple[float, float] | None:
    q = name.lower().strip()
    for prefix in ("about ", "roughly ", "around "):
        if q.startswith(prefix):
            q = q[len(prefix):]
    if not q.startswith("a ") and f"a {q}" in SPACES:
        q = f"a {q}"
    return SPACES.get(q)
