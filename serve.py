"""Local web app for the guided intake. No dependencies — stdlib only.

    python3 serve.py                 # http://localhost:8000
    python3 serve.py 8000 --demo     # same, but placeholder parts are allowed

This calls ``pipeline.run()`` — the same L1→L5 path as ``demo.py``, with the L4
gate, the design record and the human review gate. It used to call ``build()``
directly and fake ``verified=True`` on every part, which meant the app users
actually touched skipped every guarantee the rest of the codebase enforces
(log.md, 2026-08-28).

``--demo`` lets unverified parts through so the flow can be shown end to end
against the placeholder catalog. It does **not** pretend they are verified: the
response carries ``demo_mode`` and an extra caveat saying the prices are not
real. Without it, a catalog of unverified parts blocks the quote — which is the
correct behaviour and, today, the behaviour on every request.

Sessions live in memory: this is a local tool for your team, not a deployment.
"""

from __future__ import annotations

import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rstream.catalog import Catalog
from rstream.config import MAX_PARTS_COST_USD
from rstream.dialogue import GuidedIntake, plain_failure
from rstream.explain import (caveat_lines, describe_machine, parts_of_machine,
                             price_sentence, speed_sentence, what_it_can_do)
from rstream.pipeline import run as run_pipeline
from rstream.record import Outcome

HERE = Path(__file__).parent
RUNS_DIR = HERE / "runs"
SESSIONS: dict[str, GuidedIntake] = {}

CATALOG = Catalog.load()
#: Set from the command line. Never defaults on: an unverified part reaching a
#: customer is the one failure mode the catalog rules exist to prevent.
DEMO_MODE = False


def question_payload(q) -> dict:
    return {"key": q.key, "text": q.text, "options": q.options, "why": q.why}


def result_payload(g: GuidedIntake) -> dict:
    req = g.to_requirements()
    result = run_pipeline(req, CATALOG, backend="null", allow_unverified=DEMO_MODE)
    cfg = result.configuration
    rec = result.record
    rec.save(RUNS_DIR)

    if cfg is None:
        reason = result.blocked_on[0] if result.blocked_on else "requirements incomplete"
        return {"done": True, "ok": False, "message": plain_failure(reason),
                "summary": g.summary(), "record_id": rec.id,
                "outcome": rec.outcome.value}

    # The cheapest tier that is inside what we build. L4 gates this too, but the
    # screen has to name a price, and it must name one from a tier we would sell.
    affordable = sorted(
        (t for t in cfg.tiers.values() if t.parts_cost_usd <= MAX_PARTS_COST_USD),
        key=lambda t: t.parts_cost_usd)
    if not affordable:
        cheapest = min(cfg.tiers.values(), key=lambda t: t.parts_cost_usd).parts_cost_usd
        return {"done": True, "ok": False,
                "message": plain_failure(
                    f"costs more in parts than we build: {cheapest:.0f} USD"),
                "summary": g.summary(), "record_id": rec.id,
                "outcome": rec.outcome.value}
    tier = affordable[0].name

    # A design that did not clear the gate does not get a price. Reporting the
    # blocker in plain language is the honest answer; a number here would be a
    # quote for a machine no check has passed.
    if rec.outcome is not Outcome.AWAITING_REVIEW:
        return {"done": True, "ok": False,
                "message": plain_failure(result.blocked_on[0] if result.blocked_on else ""),
                "summary": g.summary(), "record_id": rec.id,
                "outcome": rec.outcome.value,
                "blocked_on": result.blocked_on,
                "demo_mode": DEMO_MODE}

    caveats = caveat_lines()
    if DEMO_MODE:
        caveats = ["DEMO MODE: the parts behind this are placeholders and the prices "
                   "are not real. Nothing here has been checked against a vendor."] + caveats

    return {
        "done": True,
        "ok": True,
        "summary": g.summary(),
        "machine": describe_machine(cfg.topology),
        "parts": parts_of_machine(cfg.topology),
        "abilities": what_it_can_do(req),
        "speed": speed_sentence(cfg),
        "price": price_sentence(cfg, tier) if tier else None,
        "gaps": cfg.capability_gaps,
        "caveats": caveats,
        "demo_mode": DEMO_MODE,
        "record_id": rec.id,
        "outcome": rec.outcome.value,
        # Engineer-only. Never rendered in the customer view.
        "internal": {
            "payload_kg": req.payload_kg, "reach_m": req.reach_m,
            "dof": cfg.topology.dof if cfg.topology else None,
            "topology": cfg.topology.describe() if cfg.topology else None,
            "tree": cfg.topology.tree() if cfg.topology else None,
            "torque_nm": round(cfg.torque.required_nm, 1) if cfg.torque else None,
            "safety_factor": cfg.torque.safety_factor if cfg.torque else None,
            # Every L4 check, verbatim. A SKIP is not a PASS and the screen that
            # an engineer reviews has to show the difference.
            "checks": rec.checks,
            "repair_attempts": rec.repair_attempts,
            "panel_tier": rec.panel_tier,
            "record": f"runs/{rec.id}.json",
            # Per-joint, because the actuators now differ per joint and an
            # engineer reviewing one number cannot check three.
            "joint_loads": [
                {"label": l.label, "arm_m": round(l.moment_arm_m, 3),
                 "distal_kg": round(l.distal_mass_kg, 2), "basis": l.sizing_basis,
                 "motors": l.count,
                 "required_nm": round(l.torque.required_nm, 1) if l.torque else None}
                for l in cfg.joint_loads
            ],
            "actuators": [
                {"joints": l.joints, "part": l.part.id,
                 "role": l.part.actuator.role.value,
                 "rated_nm": l.part.actuator.rated_torque_nm}
                for l in (cfg.tiers[tier].lines if tier else []) if l.part.actuator
            ],
            "assumptions": cfg.assumptions + req.assumptions,
            "unauthored_modules": cfg.topology.unauthored if cfg.topology else [],
        },
    }


def advance(g: GuidedIntake) -> dict:
    q = g.next_question()
    return question_payload(q) if q else result_payload(g)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self._json({"error": "malformed request body"}, 400)
            return
        if not isinstance(data, dict):
            self._json({"error": "malformed request body"}, 400)
            return

        if self.path == "/api/start":
            sid = uuid.uuid4().hex[:12]
            SESSIONS[sid] = GuidedIntake()
            self._json({"session": sid, **advance(SESSIONS[sid])})
            return

        if self.path == "/api/answer":
            g = SESSIONS.get(data.get("session", ""))
            if g is None:
                self._json({"error": "session expired — please start again"}, 400)
                return
            if "key" not in data or "value" not in data:
                self._json({"error": "missing key or value"}, 400)
                return
            g.answer(data["key"], data["value"])
            self._json(advance(g))
            return

        self._json({"error": "not found"}, 404)


def main() -> int:
    global DEMO_MODE
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    DEMO_MODE = "--demo" in sys.argv
    port = int(args[0]) if args else 8000

    stats = CATALOG.stats()
    print(f"  robotics_streamline  ->  http://localhost:{port}")
    print(f"  catalog: {stats['total']} parts, {stats['verified']} verified")
    if DEMO_MODE:
        print("  DEMO MODE: unverified parts allowed. Prices shown are not real.")
    elif not stats["verified"]:
        print("  no verified parts — every request will be blocked, by design.")
        print("  run with --demo to walk the flow against placeholder parts.")
    print("  ctrl-c to stop\n", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
