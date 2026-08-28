"""End-to-end demo: task description -> BOM + trajectory, with no CAD attached.

    python3 demo.py

Runs on the NullBackend, so the entire L1-L5 flow executes without Fusion. That
is the point of the seam: the pipeline is testable and reviewable before any CAD
work exists.
"""

import sys
from dataclasses import replace

sys.path.insert(0, "src")

from rstream import pipeline
from rstream.capabilities import Capability
from rstream.catalog import Catalog
from rstream.intake import Requirements


def main() -> int:
    catalog = Catalog.load()
    print(f"catalog: {catalog.stats()}\n")

    req = Requirements(
        task="pick 0.8 kg machined parts from a tray and place them into a test fixture",
        payload_kg=0.8,
        reach_m=0.45,
        budget_usd=9000.0,
        cycle_time_target_s=4.0,
        # The guided intake always produces capabilities, so the demo must too —
        # otherwise it exercises the legacy archetype-only path and never shows
        # the synthesized topology or the per-joint load path the app really uses.
        capabilities={Capability.MANIPULATION, Capability.GRASPING},
        assumptions=["parts presented in a fixed tray, not bin-picked"],
    )

    print("=" * 70)
    print("RUN 1 — real seed catalog (all parts unverified)")
    print("=" * 70)
    r = pipeline.run(req, catalog, allow_unverified=True)
    print(f"outcome : {r.record.outcome.value}")
    for b in r.blocked_on:
        print(f"blocked : {b}")

    print("\n" + "=" * 70)
    print("RUN 2 — same request, parts marked verified (simulating human sign-off)")
    print("=" * 70)
    verified = Catalog([replace(p, verified=True) for p in catalog.query(allow_unverified=True)])
    r = pipeline.run(req, verified)

    print(f"outcome  : {r.record.outcome.value}")
    print(f"archetype: {r.configuration.archetype.name}")
    print(f"panel    : tier {r.record.panel_tier}")
    print(f"attempts : {r.record.repair_attempts}")
    print(f"tiers    : {list(r.configuration.tiers)}")
    print("\nchecks:")
    for c in r.record.checks:
        mark = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP", "warn": "WARN"}[c["status"]]
        print(f"  [{mark}] {c['name']:<20} {c['detail']}")

    print("\ntrajectory:")
    for w in r.trajectory.waypoints:
        print(f"  t={w.t_s:>5.2f}s  {w.label}")
    print("\noverlays:")
    for o in r.trajectory.overlays:
        print(f"  {o}")

    print("\n" + "-" * 70)
    print(r.document)

    out = r.record.save("runs")
    print(f"\ndesign record -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
