"""Fusion 360 backend — the first CADBackend implementation.

This module is the ONLY place ``adsk`` concepts appear. Everything above L3 sees
the neutral types in ``geom``. Fusion works in centimetres internally; conversion
happens here and nowhere else.

SAFETY — the golden rule
    Imported vendor assemblies are read-only. Every generated script begins with
    a guard that refuses to run if the active document is not the scratch design
    this backend created. A ThroughAll cut with unpinned participants is how a
    vendor part gets destroyed, and it has happened before. The guard is not
    optional and must not be removed to "make a script work".

TRANSPORT
    Script execution is injected rather than imported, so this class can be
    built, unit-tested and reviewed with no Fusion running. Wire ``transport`` to
    the Fusion MCP execute tool to make it live.
"""

from __future__ import annotations

import json
from typing import Callable

from .base import CADBackend, PlacedPart
from .geom import BBox, Clash, MassProperties, Measurements, Vec3, View

CM_PER_M = 100.0

#: Prepended to every script. Refuses to touch anything but our scratch design.
GUARD = '''
import adsk.core, adsk.fusion, json

def _guard(expected_name):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if doc.name != expected_name:
        raise RuntimeError(
            "GOLDEN RULE: active document is %r, expected scratch design %r. "
            "Refusing to modify a document this backend did not create."
            % (doc.name, expected_name))
    des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if des is None:
        raise RuntimeError("active document has no design product")
    return app, doc, des
'''


class FusionNotConnected(RuntimeError):
    pass


def _no_transport(script: str) -> str:
    raise FusionNotConnected(
        "FusionBackend has no transport. Pass transport=<callable> that executes a "
        "Fusion Python script and returns its stdout, e.g. a wrapper around the "
        "fusion_mcp_execute tool. Use NullBackend to run the pipeline without Fusion."
    )


class FusionBackend(CADBackend):
    name = "fusion"
    supports_interference = True

    def __init__(self, transport: Callable[[str], str] | None = None) -> None:
        self._exec = transport or _no_transport
        self._design_name: str | None = None

    # --- helpers ---------------------------------------------------------
    def _run(self, body: str) -> dict:
        if self._design_name is None:
            raise RuntimeError("open_design() must be called first")
        script = (
            f"{GUARD}\n"
            f"def run(_context: str):\n"
            f"    app, doc, des = _guard({self._design_name!r})\n"
            f"{body}\n"
        )
        out = self._exec(script)
        try:
            return json.loads(out) if out and out.strip().startswith("{") else {}
        except json.JSONDecodeError:
            return {}

    # --- lifecycle -------------------------------------------------------
    def open_design(self, name: str) -> None:
        """Create a NEW design. Never adopts whatever the user has open."""
        script = (
            "import adsk.core, adsk.fusion, json\n"
            "def run(_context: str):\n"
            "    app = adsk.core.Application.get()\n"
            "    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)\n"
            f"    doc.name = {name!r}\n"
            "    print(json.dumps({'created': doc.name}))\n"
        )
        self._exec(script)
        self._design_name = name

    def close(self, save: bool = False) -> None:
        self._design_name = None

    # --- L3 build --------------------------------------------------------
    def instantiate_archetype(self, archetype_id: str, params: dict[str, float]) -> None:
        """Drive a pre-authored parametric template.

        NOT IMPLEMENTED — blocked on the templates existing (open question #6 in
        log.md). Raising is deliberate: silently producing an empty design would
        let a bad concept reach a customer, which is the failure mode this whole
        architecture exists to prevent.
        """
        raise NotImplementedError(
            f"archetype template {archetype_id!r} has not been authored yet. "
            "Templates are parametric Fusion models built by an engineer; the AI "
            "instantiates them, it does not generate geometry. See log.md open question #6."
        )

    def place_panel(self, tier: str) -> None:
        raise NotImplementedError("control-panel tier models not yet authored")

    def place_parts(self, parts: list[PlacedPart]) -> None:
        missing = [p.part_id for p in parts if not p.geometry_ref]
        if missing:
            raise NotImplementedError(
                "no normalized STEP geometry for: " + ", ".join(sorted(missing))
                + ". Normalize at catalog-entry time (origin at mounting-face centre, "
                "bolt pattern, keepout) — never download at runtime."
            )
        raise NotImplementedError("component placement pending panel tier models")

    # --- L4a -------------------------------------------------------------
    def measure(self) -> Measurements:
        d = self._run(
            "    root = des.rootComponent\n"
            "    bodies = [b for b in root.bRepBodies if b.isSolid]\n"
            "    if not bodies:\n"
            "        print(json.dumps({'empty': True})); return\n"
            "    bb = bodies[0].boundingBox\n"
            "    for b in bodies[1:]:\n"
            "        bb.combine(b.boundingBox)\n"
            "    mass = sum(b.physicalProperties.mass for b in bodies)\n"
            "    vol = sum(b.physicalProperties.volume for b in bodies)\n"
            "    cx = sum(b.physicalProperties.centerOfMass.x * b.physicalProperties.mass "
            "for b in bodies) / mass if mass else 0\n"
            "    cy = sum(b.physicalProperties.centerOfMass.y * b.physicalProperties.mass "
            "for b in bodies) / mass if mass else 0\n"
            "    cz = sum(b.physicalProperties.centerOfMass.z * b.physicalProperties.mass "
            "for b in bodies) / mass if mass else 0\n"
            "    print(json.dumps({'min': [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z],\n"
            "                      'max': [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z],\n"
            "                      'mass_kg': mass, 'volume_cm3': vol, 'com': [cx, cy, cz],\n"
            "                      'count': len(bodies)}))"
        )
        if not d or d.get("empty"):
            zero = Vec3(0, 0, 0)
            return Measurements(BBox(zero, zero), MassProperties(0, zero, 0), 0)

        mn = [v / CM_PER_M for v in d["min"]]
        mx = [v / CM_PER_M for v in d["max"]]
        com = [v / CM_PER_M for v in d["com"]]
        return Measurements(
            bbox=BBox(Vec3(*mn), Vec3(*mx)),
            mass=MassProperties(d["mass_kg"], Vec3(*com), d["volume_cm3"] * 1e-6),
            body_count=d["count"],
        )

    def check_interference(self) -> list[Clash]:
        d = self._run(
            "    root = des.rootComponent\n"
            "    bodies = adsk.core.ObjectCollection.create()\n"
            "    for b in root.bRepBodies:\n"
            "        if b.isSolid: bodies.add(b)\n"
            "    for occ in root.occurrences:\n"
            "        for b in occ.bRepBodies:\n"
            "            if b.isSolid: bodies.add(b)\n"
            "    if bodies.count < 2:\n"
            "        print(json.dumps({'clashes': []})); return\n"
            "    ipt = des.createInterferenceInput(bodies)\n"
            "    ipt.areCoincidentFacesIncluded = False\n"
            "    res = des.analyzeInterference(ipt)\n"
            "    out = [{'a': r.entityOne.name, 'b': r.entityTwo.name,\n"
            "            'vol_cm3': r.interferenceBody.physicalProperties.volume}\n"
            "           for r in res]\n"
            "    print(json.dumps({'clashes': out}))"
        )
        return [
            Clash(c["a"], c["b"], c["vol_cm3"] * 1e-6) for c in d.get("clashes", [])
        ]

    def panel_envelope(self) -> BBox:
        raise NotImplementedError("panel tier models not yet authored")

    # --- L4b -------------------------------------------------------------
    def screenshot(self, view: View, width: int = 1280, height: int = 960) -> bytes:
        """Captured per stage, not only at the end — per-stage capture is what
        gives the vision gate stage-level attribution."""
        raise NotImplementedError(
            "screenshot goes through the MCP read tool (queryType='screenshot', "
            f"direction={view.value!r}), not the script transport. Wire it when the "
            "backend goes live."
        )

    def export(self, fmt: str, path: str) -> str:
        raise NotImplementedError("export not yet wired")
