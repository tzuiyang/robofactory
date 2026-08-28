"""Catalog curation — the one step in this project a person has to do.

    python3 curate.py status          # what the catalog has, what it is missing
    python3 curate.py needs           # the torque/speed rungs the sizing asks for
    python3 curate.py verify <id>     # fill in a real part and mark it verified
    python3 curate.py add             # add a part the catalog does not have yet

Why this is interactive and not automated
-----------------------------------------
Everything else here is deterministic code. This is not, on purpose. The catalog
is the one artifact where a wrong entry reaches a customer as a real-looking part
number they cannot tell from a fake one, and a novice — the person this product
is for — has no way to catch it. So `verified` is set by a human who has looked
at the vendor page, and by nobody else. That rule is enforced in
`catalog/store.py` and it is the reason the app currently refuses every request.

This tool does not look anything up. It tells you exactly what is needed and
where to type it.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "src"))

PARTS = HERE / "src" / "rstream" / "catalog" / "data" / "parts.json"

from rstream.capabilities import Capability          # noqa: E402
from rstream.catalog import Catalog                  # noqa: E402
from rstream.catalog.schema import PartKind          # noqa: E402
from rstream.config import _KIND_DEFAULTS            # noqa: E402
from rstream.sizing import chain_loads               # noqa: E402
from rstream.topology import synthesize              # noqa: E402

#: Representative jobs spanning what the product claims to cover. Used to derive
#: the torque rungs the catalog actually has to hit — not a guess at a ladder.
PROBES = [
    ("small bench arm", dict(payload_kg=0.1, reach_m=0.2),
     {Capability.MANIPULATION, Capability.GRASPING}),
    ("desk arm", dict(payload_kg=0.5, reach_m=0.35),
     {Capability.MANIPULATION, Capability.GRASPING}),
    ("bigger bench arm", dict(payload_kg=1.0, reach_m=0.5),
     {Capability.MANIPULATION, Capability.GRASPING}),
    ("table-span arm", dict(payload_kg=2.0, reach_m=0.7),
     {Capability.MANIPULATION, Capability.GRASPING}),
    ("wheeled base", dict(payload_kg=2.0, reach_m=0.3),
     {Capability.MOBILITY}),
    # Not an arm at all. Included because it is what exposes the part kinds the
    # module library asks for and the catalog has never held.
    ("talking assistant", dict(payload_kg=0.0, reach_m=0.0),
     {Capability.MOBILITY, Capability.VISION, Capability.AUDIO_IN,
      Capability.AUDIO_OUT, Capability.ONBOARD_COMPUTE}),
]


def _load() -> OrderedDict:
    return json.loads(PARTS.read_text(), object_pairs_hook=OrderedDict)


def _save(doc: OrderedDict) -> None:
    PARTS.write_text(json.dumps(doc, indent=2) + "\n")


# --- reporting ---------------------------------------------------------------

def cmd_status() -> int:
    cat = Catalog.load()
    st = cat.stats()
    print(f"\ncatalog: {st['total']} parts — {st['verified']} verified, "
          f"{st['unverified']} unverified\n")

    if not st["verified"]:
        print("  Nothing is verified, so the app blocks every request. That is the")
        print("  guardrail working. Verifying parts is what turns it on.\n")

    print("  by kind:")
    for kind, n in sorted(st["by_kind"].items()):
        print(f"    {kind:16s} {n}")

    unver = [p for p in cat.query(allow_unverified=True) if not p.verified]
    if unver:
        print(f"\n  unverified ({len(unver)}):")
        for p in sorted(unver, key=lambda p: p.id):
            role = f" [{p.actuator.role.value}]" if p.actuator else ""
            print(f"    {p.id:16s}{role:9s} {p.part_number:24s} ${p.price_usd:>8,.2f}  "
                  f"{p.description[:40]}")

    # Kinds the module library asks for that nothing in the catalog can fill.
    have = {k for k in st["by_kind"]}
    wanted: set[str] = set()
    for label, kw, caps in PROBES:
        try:
            topo = synthesize(caps, payload_kg=kw["payload_kg"],
                              reach_m=kw["reach_m"])
            wanted |= topo.consumes_kinds
        except Exception:
            continue
    missing = sorted(wanted - have)
    unmapped = sorted(k for k in wanted & have
                      if k not in _KIND_DEFAULTS and k not in
                      ("actuator", "end_effector", "structure"))
    if missing:
        print(f"\n  kinds the designs ask for and the catalog cannot fill ({len(missing)}):")
        for k in missing:
            print(f"    {k}")
        print("    -> these appear as holes in the BOM, not as wrong parts.")
    if unmapped:
        print(f"\n  kinds present but not wired into selection: {', '.join(unmapped)}")

    print(f"\n  next: python3 curate.py needs        # what specs to shop for")
    print(f"        python3 curate.py verify <id>   # fill one in\n")
    return 0


def cmd_needs() -> int:
    """What the sizing actually demands. Shop against this, not against a guess."""
    print("\nTorque the sizing asks for, per representative job.")
    print("Safety factor is already applied — buy to the number shown.\n")
    rungs: list[tuple[float, float | None, str, str]] = []
    for label, kw, caps in PROBES:
        try:
            topo = synthesize(caps, payload_kg=kw["payload_kg"], reach_m=kw["reach_m"])
            loads = chain_loads(topo, kw["payload_kg"])
        except Exception as e:
            print(f"  {label:20s} -- not synthesizable: {e}")
            continue
        print(f"  {label}  (payload {kw['payload_kg']} kg, reach {kw['reach_m']} m)")
        for l in loads:
            if l.torque is None:
                print(f"    {l.label:14s} {'unmodelled':>10s}   basis={l.sizing_basis}")
                continue
            speed = l.detail.get("wheel_speed_rad_s")
            role = "drive" if l.sizing_basis == "traction" else "joint"
            sp = f", >= {speed:.1f} rad/s" if speed else ""
            print(f"    {l.label:14s} {l.torque.required_nm:>8.1f} Nm   "
                  f"role={role}{sp}  x{l.count}")
            rungs.append((l.torque.required_nm, speed, role, f"{label}/{l.label}"))
        print()

    joint = sorted(r for r in rungs if r[2] == "joint")
    drive = sorted(r for r in rungs if r[2] == "drive")
    print("  Shopping list — one actuator at or just above each rung:\n")
    for name, group in (("joint (must hold position: encoder/brake)", joint),
                        ("drive (wheels: continuous rotation, speed matters)", drive)):
        if not group:
            continue
        print(f"    {name}")
        for nm, speed, _role, src in group:
            sp = f", >= {speed:.1f} rad/s" if speed else ""
            print(f"      >= {nm:6.1f} Nm rated{sp:22s}  ({src})")
        print()
    print("  Tiers (good/better/best) apply 1.0x / 1.4x / 2.0x on top, so gaps")
    print("  between rungs are what makes the three tiers differ at all.\n")
    return 0


# --- editing -----------------------------------------------------------------

def _ask(prompt: str, current=None, cast=str, allow_blank=True):
    shown = f" [{current}]" if current not in (None, "") else ""
    while True:
        raw = input(f"    {prompt}{shown}: ").strip()
        if not raw:
            if current not in (None, "") or allow_blank:
                return current
            print("      required.")
            continue
        try:
            return cast(raw)
        except ValueError:
            print(f"      not a valid {cast.__name__}.")


def _edit_part(entry: OrderedDict) -> bool:
    """Prompt through one part. Returns True if it should be marked verified."""
    print(f"\n  editing {entry['id']}  (blank keeps the current value)\n")
    entry["manufacturer"] = _ask("manufacturer", entry.get("manufacturer"))
    entry["part_number"] = _ask("part number", entry.get("part_number"))
    entry["description"] = _ask("description", entry.get("description"))
    entry["price_usd"] = _ask("price USD", entry.get("price_usd"), float)
    entry["mass_kg"] = _ask("mass kg", entry.get("mass_kg"), float)
    entry["source_url"] = _ask("vendor URL", entry.get("source_url"))
    lead = _ask("lead time days", entry.get("lead_time_days"), int)
    if lead is not None:
        entry["lead_time_days"] = lead

    d = entry.setdefault("dimensions", OrderedDict())
    print("\n    dimensions, mm (keepout = connector/airflow clearance on top of the body)")
    for f in ("length_mm", "width_mm", "height_mm"):
        d[f] = _ask(f, d.get(f), float)
    for f in ("keepout_length_mm", "keepout_width_mm", "keepout_height_mm"):
        d[f] = _ask(f, d.get(f, 0.0), float)

    if entry.get("actuator") is not None:
        a = entry["actuator"]
        print("\n    actuator")
        print("      role: 'joint' holds position under load (encoder/brake).")
        print("            'drive' turns a wheel continuously. Wrong role = wrong machine.")
        while True:
            role = _ask("role (joint/drive)", a.get("role", "joint"))
            if role in ("joint", "drive"):
                a["role"] = role
                break
            print("      must be 'joint' or 'drive'.")
        for f, cast in (("rated_torque_nm", float), ("stall_torque_nm", float),
                        ("max_speed_rad_s", float), ("gear_ratio", float),
                        ("voltage_v", float), ("peak_current_a", float)):
            a[f] = _ask(f, a.get(f), cast)

    print("\n  Verification. Only tick this off against the vendor's own page —")
    print("  part number, price and the specs above. An unverified part cannot be")
    print("  quoted; a wrongly-verified one reaches someone who cannot check it.")
    answer = input("    type 'checked' to mark verified (anything else leaves it off): ")
    return answer.strip().lower() == "checked"


def cmd_verify(part_id: str) -> int:
    doc = _load()
    entry = next((p for p in doc["parts"] if p["id"] == part_id), None)
    if entry is None:
        print(f"\n  no part {part_id!r} in the catalog.")
        print("  run `python3 curate.py status` for the list, or `add` to create it.\n")
        return 1
    verified = _edit_part(entry)
    entry["verified"] = verified
    _save(doc)
    try:
        Catalog.load()
    except Exception as e:
        print(f"\n  !! the catalog no longer loads: {e}")
        print("  the file was written anyway — fix the value and re-run.\n")
        return 1
    print(f"\n  saved. {part_id} is now "
          f"{'VERIFIED and quotable' if verified else 'still unverified'}.\n")
    return 0


def cmd_add() -> int:
    doc = _load()
    print("\n  kinds: " + ", ".join(k.value for k in PartKind))
    kind = input("    kind: ").strip()
    if kind not in {k.value for k in PartKind}:
        print(f"\n  {kind!r} is not a kind the schema knows. A kind absent from")
        print("  PartKind is rejected at load, so add it there first.\n")
        return 1
    pid = input("    id (e.g. act.medium): ").strip()
    if any(p["id"] == pid for p in doc["parts"]):
        print(f"\n  {pid!r} already exists — use `verify {pid}`.\n")
        return 1

    entry = OrderedDict([
        ("id", pid), ("kind", kind), ("manufacturer", ""), ("part_number", ""),
        ("description", ""), ("price_usd", 0.0),
        ("dimensions", OrderedDict()), ("mass_kg", 0.0), ("verified", False),
    ])
    if kind == PartKind.ACTUATOR.value:
        entry["actuator"] = OrderedDict([("stall_torque_nm", 0.0), ("rated_torque_nm", 0.0),
                                         ("max_speed_rad_s", 0.0), ("gear_ratio", 1.0),
                                         ("voltage_v", 24.0), ("peak_current_a", 0.0),
                                         ("role", "joint")])
    entry["verified"] = _edit_part(entry)
    doc["parts"].append(entry)
    _save(doc)
    try:
        Catalog.load()
    except Exception as e:
        print(f"\n  !! the catalog no longer loads: {e}\n")
        return 1
    print(f"\n  added {pid}.\n")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        return cmd_status()
    if cmd == "needs":
        return cmd_needs()
    if cmd == "verify":
        if len(argv) < 3:
            print("\n  usage: python3 curate.py verify <part_id>\n")
            return 1
        return cmd_verify(argv[2])
    if cmd == "add":
        return cmd_add()
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
