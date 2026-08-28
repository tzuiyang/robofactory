# System Architecture — robotics_streamline

**Status:** draft v0.1 · 2026-08-25
**Linked from:** `log.md` §3

Governing principle:

> **The LLM proposes, deterministic code disposes.**
> Every LLM output must be checkable by code. This is what prevents the compounding-error
> failure (~85% per stage × 8 stages ≈ 30% end-to-end). Errors are caught at the stage that
> produced them, never allowed to accumulate to the end.

---

## Layer stack

```
L0  CATALOG & ARCHETYPES     (offline, human-curated — the asset, not a runtime layer)
L1  INTAKE                   (LLM)
L2  CONFIGURATION            (LLM proposes, code disposes)
L3  GEOMETRY                 (CAD backend, swappable)
L4  VALIDATION               (deterministic gate → vision gate → bounded repair)
L5  PRESENTATION             (kinematic sim, BOM doc → HUMAN GATE → customer)
```

Layers communicate through a single versioned **design record** (JSON) that accumulates as it
descends the stack. It is the unit of persistence, the unit of replay, and the dataset.

---

## L0 — Catalog & Archetype Library

**Not a runtime layer.** Built once by humans, grows slowly, and is the core asset and moat of
the product — defensible precisely because it is tedious work nobody else will do.

Contains:

| Asset | Contents |
|---|---|
| **Parts catalog** | 100–300 parts the team actually uses. Real prices, torque/speed curves, mounting data, lead time, stock status. |
| **Normalized geometry** | **STEP**, not STL. One per part, normalized on entry (see below). |
| **Robot archetypes** | 2–3 parametric models with driven dimensions, authored by our engineers. |
| **Control-panel tiers** | Pre-designed panels in S/M/L with defined component slots. |

### Geometry normalization (done once, per part, by a human — ~10–20 min)

STL is rejected as a format: inconsistent units, arbitrary origins, no mounting datums, absurd
mesh densities, unclear licensing, frequently missing — and critically **a mesh has no planar
face to mate or joint against.** STEP is used instead.

Each entry is normalized to carry:
- origin at a defined datum (usually mounting-face center)
- explicit mounting frame + bolt pattern
- bounding box **and keepout volume** (connectors need clearance, not just the body)
- connector face direction, cable exit direction
- thermal flag (needs airflow y/n)

Doing this at runtime instead is slow, flaky, and wrong every time. Doing it once makes panel
layout instant and correct forever.

---

## L1 — Intake (LLM)

Conversation → **structured requirements JSON**.

Captures: payload · reach · workspace envelope · cycle time · environment (washdown /
cleanroom / dust / temperature) · **budget** · aesthetic constraints.

- Budget is a first-class input, not an afterthought: it is a hard constraint that prunes the
  design space *and* it is what the customer actually asks about.
- Ambiguities are flagged explicitly and asked back to the user rather than assumed.
- **Domain research belongs here** — the *task*, not the parts: what the handled part looks
  like, typical cycle times in that industry, environmental norms. This genuinely varies per
  request and cannot be pre-cached.
- **Part research does NOT happen here or anywhere at runtime.** See L2.

Output: validated requirements object. Fails closed if required fields are unresolved.

---

## L2 — Configuration (LLM proposes, code disposes)

1. **Archetype selection** — LLM proposes, rules validate against requirements.
2. **Sizing** — *formulas, not LLM arithmetic*. reach → link lengths;
   payload × reach × safety factor → joint torque → actuator class.
3. **Part selection** — a **constrained query over the catalog** with budget as a
   knapsack-style constraint. Deterministic, instant, free, and every result is by
   construction purchasable.
4. **Output three tiers** — good / better / best. Better sales practice (anchoring) and it
   turns a budget mismatch into a negotiation instead of a rejection.

**Runtime web research for parts is prohibited.** It produces dead links, out-of-stock parts,
wrong specs, and non-existent part numbers; it is slow and non-deterministic — the same query
twice yields two different BOMs, which is fatal for a quoting tool. Research happens offline,
into L0, with human confirmation.

---

## L3 — Geometry (swappable CAD backend)

- Instantiate the selected archetype with computed parameters.
- Select the smallest **control-panel tier** whose volume accommodates the component list
  (bounding boxes + keepouts).
- Place normalized components into panel slots.

**Panel packing is deliberately NOT a solver in v1.** Discrete S/M/L tiers with fixed slots are
used instead of 3D bin packing with clearance/thermal/routing constraints. This is consistent
with "instantiate archetypes, don't generate," it is instantly verifiable, and it has a real
commercial benefit: three standard panel designs are faster for the team to build and can be
stocked. A packing solver is added only when the tiers stop fitting.

### CAD backend is behind an interface — see `log.md` for the open decision

Fusion 360 is desktop software (GUI-driven, per-seat licensed, requires a logged-in session).
It cannot serve a many-user app. Options:

| Option | Trade-off |
|---|---|
| Fusion worker farm | Works now, no rewrite; caps throughput, per-seat licensing, ops pain |
| Onshape | Cloud-native REST API, built for concurrency; means re-authoring archetypes |
| Headless kernel (CadQuery / build123d / OpenCascade) | Cheapest and fastest to run, fully scriptable/testable/versionable, 100 concurrent for free; code-first authoring, no CAD GUI |

**Decision: prototype on Fusion, keep the geometry layer behind a clean swappable interface,
decide the production backend once internal-vs-public is settled.** Do not let this be decided
by accident through months of Fusion-specific code.

---

## L4 — Validation (the closed loop)

Runs in strict order. Cheap and exact first, fuzzy last.

### 4a. Deterministic gate — exact, free, unambiguous
- interference / clash detection
- mass properties
- component bounding box + keepout vs. panel volume
- reach envelope vs. required workspace
- torque margin vs. actuator spec sheet
- total BOM cost vs. budget

**Never ask a vision model to judge something a query can measure.** Vision cannot measure;
letting it try produces confidently wrong dimensions.

### 4b. Vision gate — plausibility only
Multi-view screenshots → VLM review for the failures deterministic checks miss and a human
catches instantly: floating parts, inverted or backwards components, visual intersections,
absurd proportions, a machine that plainly could not do the stated task.

This loop is affordable — a CAD screenshot costs cents and takes seconds. (This is why it is
viable where the physical video loop was not: that one had single-digit samples per month at
days and hundreds of dollars per iteration.)

**Screenshot after every stage.** Per-stage capture gives stage-level attribution, which
partly solves the credit-assignment problem that killed the physical-video loop.

### 4c. Bounded repair
- repair signals must be **structured** (`part X intersects part Y at face Z`), never free
  text like "looks wrong"
- routed back to L2 or L3 depending on the failing check
- **max 3 attempts, then escalate to human.** An unbounded agent loop on a CAD model burns an
  hour and returns a worse model than it started with.

---

## L5 — Presentation

- Scripted trajectory → **kinematic** simulation (no physics engine — see `log.md` §3)
- Render with engineering overlays: dimension callouts, reach envelope, cycle-time counter,
  visible "concept simulation" label
- BOM document with part numbers, safety factors visible, **price as a range**
- Explicit list of assumptions made
- **→ HUMAN REVIEW GATE → customer**

---

## The design record — persistence and dataset

One JSON record per run, accumulating through every layer:

```
requirements → archetype choice → sizing math → BOM → geometry params
→ check results → repair attempts → ENGINEER CORRECTIONS AT THE GATE
→ customer outcome (bought / didn't) → ACTUAL BUILD COST
```

Two fields carry disproportionate value:

1. **Engineer corrections at the review gate.** Every edit is a labeled training example with
   a known input and a known-correct output — supervision that is normally impossible to get
   in engineering, and it costs nothing because the engineer was reviewing anyway.
   **Therefore the gate must capture diffs, not just approve/reject.** This single design
   choice is the difference between accumulating a dataset and accumulating nothing.
2. **Quoted vs. actual build cost.** The only loop that matters commercially.
