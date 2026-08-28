"""The general case: two very different robots from plain descriptions."""

import sys
from dataclasses import replace

sys.path.insert(0, "src")

from rstream.capabilities import Capability as C
from rstream.catalog import Catalog
from rstream.config import build
from rstream.intake import Requirements

CASES = [
    ("a rolling robot that talks and listens",
     Requirements(task="a rolling robot that talks and listens", payload_kg=0.2,
                  reach_m=0.30, budget_usd=3000,
                  capabilities={C.MOBILITY, C.AUDIO_OUT, C.AUDIO_IN})),
    ("a machine that folds laundry",
     Requirements(task="a machine that folds laundry", payload_kg=0.5,
                  reach_m=0.80, budget_usd=15000, workspace_is_planar=True,
                  capabilities={C.FLAT_MATERIAL_HANDLING, C.GRASPING})),
    ("pick parts from a tray into a fixture",
     Requirements(task="pick parts from a tray into a fixture", payload_kg=0.8,
                  reach_m=0.45, budget_usd=9000, capabilities={C.GRASPING})),
]


def main() -> int:
    cat = Catalog.load()
    verified = Catalog([replace(p, verified=True) for p in cat.query(allow_unverified=True)])

    for title, req in CASES:
        print("=" * 72)
        print(title.upper())
        print("=" * 72)
        cfg = build(req, verified)
        t = cfg.topology
        print(f"  topology : {t.describe()}")
        print(f"  DOF      : {t.dof}   (AI-determined, not specified by the user)")
        print(f"  needs    : {', '.join(sorted(t.consumes_kinds))}")
        if t.notes:
            for n in t.notes:
                print(f"  note     : {n}")
        if cfg.capability_gaps:
            print("  CATALOG GAPS (must be added by a human before quoting):")
            for g in cfg.capability_gaps:
                print(f"    - {g}")
        print(f"  CAD todo : {len(t.unauthored)} unauthored modules -> {', '.join(t.unauthored)}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
