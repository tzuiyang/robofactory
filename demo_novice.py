"""Two novice conversations, start to finished design.

Neither person is asked about DOF, payload, reach, motors, sensors or ROS.
"""

import sys
from dataclasses import replace

sys.path.insert(0, "src")

from rstream.catalog import Catalog
from rstream.config import build
from rstream.dialogue import GuidedIntake, plain_failure

SCRIPTS = [
    ("Person A — knows nothing about robots, wants a helper for their shop", [
        "I want it to pick up mugs from a shelf and put them on a table",
        "coffee mug",
        "a desk",
        "$5,000 - $15,000",
        "yes, that's right",
    ]),
    ("Person B — vague about the object, so the app must probe", [
        "sort machined parts into bins and inspect them",
        "machined part",
        "about a laptop",          # only asked because the range straddled classes
        "a kitchen counter",
        "$15,000 - $50,000",
        "yes, that's right",
    ]),
    ("Person C — wants a companion robot, handles nothing", [
        "a robot that can roll around the house and talk to my kids",
        "a small room",
        "under $5,000",
        "yes, that's right",
    ]),
]


def main() -> int:
    cat = Catalog.load()
    verified = Catalog([replace(p, verified=True) for p in cat.query(allow_unverified=True)])

    for title, script in SCRIPTS:
        print("=" * 74)
        print(title)
        print("=" * 74)
        g = GuidedIntake()
        for reply in script:
            q = g.next_question()
            if q is None:
                break
            print(f"\n  Q: {q.text}")
            if q.options:
                print(f"     [{'] ['.join(q.options[:6])}]")
            if q.why:
                print(f"     ({q.why})")
            print(f"  A: {reply}")
            g.answer(q.key, reply)

        print(f"\n  --> asked {len([k for k in g.answers if k != 'confirm'])} questions\n")
        req = g.to_requirements()
        print("  DERIVED (never shown to the customer):")
        print(f"    payload      {req.payload_kg} kg")
        print(f"    reach        {req.reach_m} m")
        print(f"    capabilities {sorted(c.value for c in req.capabilities)}")
        try:
            cfg = build(req, verified)
            print(f"    topology     {cfg.topology.describe()}")
            if cfg.capability_gaps:
                print(f"    gaps         {len(cfg.capability_gaps)} catalog parts missing")
        except Exception as e:
            print(f"    internal : {e}")
            print(f"    SHOWN TO CUSTOMER:\n      \"{plain_failure(str(e))}\"")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
