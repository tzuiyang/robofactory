# robotics_streamline

Task description in → **BOM + concept simulation** out. A human robotics team builds it.

The deliverable is a **sales artifact, not an engineering artifact**: it must be credible enough
to start a paid conversation, because engineers validate and redesign afterward. See
`docs/architecture.md` for the layer design and `log.md` for why every decision was made.

## Run it

```bash
python3 serve.py             # the app -> http://localhost:8000
python3 serve.py 8000 --demo # same, but placeholder parts are allowed through
python3 demo_novice.py       # three novice conversations, in the terminal
python3 demo_general.py      # topology synthesis for very different robots
python3 demo.py              # full pipeline -> BOM + trajectory
python3 -m pytest -q         # 101 tests
```

The app runs the same `pipeline.run()` path as `demo.py`, so it is subject to the
same L4 gate and writes the same design record. **With the seed catalog it blocks
every request**, because no part is human-verified — that is the guardrail
working, not a bug. `--demo` lets unverified parts through so the flow can be
walked end to end; it labels the result as a demo and never claims the prices are
real.

No dependencies. stdlib only.

## Layers

```
L0 catalog/ archetypes.py   parts + templates (offline, human-curated — the asset)
L1 intake.py                conversation -> requirements JSON        [LLM boundary]
L2 config.py + sizing.py    archetype pick, per-joint sizing, BOM, 3 tiers
L3 cad/                     geometry, behind a SWAPPABLE backend
L4 validate.py              deterministic gate -> vision gate -> bounded repair
L5 present.py               kinematic trajectory + BOM doc -> HUMAN GATE
   pipeline.py              orchestrates L1->L5
   record.py                the design record / dataset
```

Governing principle: **the LLM proposes, deterministic code disposes.** Every LLM output is
checkable by code, so errors are caught at the stage that produced them.

## The swappable seam

`cad/base.py` defines `CADBackend`. Only neutral types from `cad/geom.py` cross it — enforced by
`tests/test_cad_seam.py`. Backends:

| Backend | Status | Use |
|---|---|---|
| `null` | working | Runs the whole pipeline with no CAD. Arithmetic geometry. |
| `fusion` | written, blocked | Local prototyping. Needs archetype templates authored. |

Fusion is desktop software and cannot serve concurrent users, so publishing later means writing
one new subclass (Onshape REST, or a headless kernel like CadQuery/build123d) — not a rewrite.

## Rules enforced in code, not prose

- **Unverified parts cannot be quoted.** Seed catalog is 100% unverified, so it *cannot* produce
  a customer BOM. A human sets `verified=true` after checking part number, price and specs.
- **No mesh geometry.** `.stl`/`.obj` are rejected at catalog entry — a mesh has no planar face
  to mate against. STEP only, normalized once.
- **No runtime part research.** Part selection is a catalog query. Unknown id raises.
- **A skipped check is never a pass.** Backends without B-rep report `SKIPPED`, not `PASS`.
- **Price is a range, never a point.** Safety factor is always visible.
- **The pipeline never reaches a customer** — it stops at `awaiting_human_review`.

## Curating the catalog

The one step a person has to do. `verified` is set by a human who has looked at the
vendor page and by nobody else — enforced in `catalog/store.py`, and the reason the
app currently refuses every request.

```bash
python3 curate.py status        # what the catalog has, what it cannot fill
python3 curate.py needs         # the torque/speed rungs the sizing actually asks for
python3 curate.py verify act.small
python3 curate.py add
```

`needs` derives the shopping list from the sizing code, not from a guess: it prints
every joint torque across representative jobs, split by actuator role.

## What's blocking

Both are *content*, not code:

1. **Real catalog parts** (log.md open q #5, #12) — replace PLACEHOLDER entries with real
   purchasable parts. Needs ~5+ actuator classes or the good/better/best tiers collapse into
   one. Use `curate.py`.
2. **Archetype templates** (open q #6, #13) — parametric CAD authored by an engineer. The AI
   instantiates them; it does not generate geometry.
