# robotics_streamline — Project Rules

## What this project is

An AI-driven **pre-sales concepting system** for custom robotics.

Input: a description of the task the robot must perform (plus rough desired look).
Output: a **BOM of real, purchasable parts** and a **short concept simulation video** of the
robot doing the job.
If the customer likes it, a **human robotics team** builds and customizes the real machine.

Read that again before proposing anything, because it constrains everything:

> **The deliverable is a sales artifact, not an engineering artifact.**
> It does not have to be *correct*. It has to be *credible enough to start a paid
> conversation*, because humans validate and redesign afterward.

We are not selling AI-designed robots. We sell robots, and use AI to destroy the cost of
pre-sales engineering.

---

## RULE 1 — Always log. This is not optional.

`log.md` at the repo root is the project's memory. **Every session must leave it updated.**

### When to log — log it, don't ask

Append an entry the moment any of these happens:

- **Bottleneck** — something is slow, brittle, expensive, or blocked. Log it *when found*,
  even if you fix it thirty seconds later. The fix is less valuable than the record of why
  it was needed.
- **Breakthrough** — a simplification, a reframe, or an approach that suddenly makes a hard
  thing easy.
- **Decision** — any architectural or product choice, including small ones.
- **Rejected** — an approach we considered and did **not** take, **with the reason**.
  Rejected paths are as valuable as chosen ones; without them we re-litigate the same
  arguments in three months.
- **Open question** — anything we could not resolve. Add it to the open-questions table.
- **Data** — any real number we learn (quote volume, part price, cycle time, win rate,
  measured error, token/render cost). Numbers are the scarcest thing in this log.

### How to log

Use the entry format defined at the top of `log.md`. Keep entries short — a few sentences.
If it needs a page, put the page in `docs/` and link to it from the log.

Rules:
- **Append, never rewrite history.** Correcting an earlier entry means adding a new one that
  supersedes it and says so. We need the trail of what we believed and when.
- Always date entries `[YYYY-MM-DD]`. Convert relative dates ("last week") to absolute.
- Always state **Confidence** and what would raise it. An unmarked guess becomes a fact
  after two months, and that is how projects go wrong.
- Update the **Session index** table at the bottom at the end of every working session.
- Log the **failure** even when you also log the fix.

### Why this rule exists

The long-term asset of this business is accumulated design knowledge — which archetypes work,
which parts fail, what customers actually ask for, where estimates diverge from reality. That
asset only compounds if it is written down as it happens. Reconstructing it later from code and
git history is impossible, because the valuable part is the *reasoning*, and reasoning leaves
no trace in a diff.

**If you are unsure whether something is worth logging, log it.** The cost of a redundant entry
is three lines. The cost of a lost insight is re-deriving it.

---

## Locked architectural constraints

These were decided deliberately (see `log.md` §3). Do not quietly work around them. If one
needs to change, log the change as a superseding decision with the reason — don't just do it.

### Design generation
- **Instantiate parametric archetypes. Never generate CAD geometry from scratch.**
  The AI's job is *selection and sizing*, not geometry creation. Archetypes are proper
  parametric Fusion models built by our engineers, with driven dimensions.
- Pipeline is fixed:
  `requirements extraction → archetype pick → parameter sizing → model instantiation → BOM → kinematic sim → video`
- Concept-level detail only. Do not emit CAD the build team would be implicitly bound to.

### Simulation
- **Kinematic, not physics, for v1.** The buyer asks three questions: does it reach, does it
  fit, how many parts per hour. All three are kinematic — reach envelope, collision-free path,
  cycle-time estimate. No Isaac, no physics engine, no learned policy in the proposal path.
- The video is a **scripted trajectory replay**: deterministic and repeatable.
- Physics is added later only where payload dynamics genuinely matter (high speed, heavy load,
  force control) — and only as a logged decision.

### BOM discipline — highest-risk artifact, hardest rules
- **Never invent a part number.** If it is not in the curated catalog, it does not exist.
  This is a hard constraint, not a preference.
- **Curated catalog only** — 100–300 parts the team actually uses, with real prices,
  torque/speed curves, and mounting data. This is a hand-built structured database and it is
  the core asset of the product.
- **Explicit safety factors** (2–3× on actuator torque), and the factor must be *visible* in
  the output. Conservative is free at proposal stage; optimistic is expensive.
- **Price as a range, never a point estimate.** e.g. "Estimated $8.5k–12k, subject to
  engineering review."
- Every dimension is a number with a stated unit. "Looks about right" is not a value.

### Output presentation
- The video must look **engineering-honest, not beautiful** — CAD-shaded, dimension callouts,
  reach-envelope overlay, cycle-time counter, and a visible "concept simulation" label.
  More credible to an industrial buyer, and it protects us from expectation gaps.
- Never present a simulation as evidence the machine works. Simulation verifies a thin slice
  (kinematics, reachability) and verifies *nothing* about tolerance stack-up, assembly,
  thermal, wiring, backlash, manufacturability, or control stability on real hardware.
- Styling is constrained to what is manufacturable: extrusion, sheet metal, printed covers.

### Data & runtime research
- **No runtime web research for parts. Ever.** Part selection is a *database query* over the
  curated catalog under a budget constraint — deterministic, instant, every result purchasable
  by construction. Live research produces dead links, out-of-stock parts, wrong specs, and
  invented part numbers, and returns a different BOM on every run.
- Runtime research IS allowed for the **customer's task domain** (handled part, industry cycle
  times, environment) — that varies per request and cannot be pre-cached.
- Component geometry is **STEP, not STL**, downloaded once and normalized into the catalog with
  a defined origin/datum, mounting frame + bolt pattern, bounding box **and keepout volume**,
  connector + cable-exit direction, thermal flag. A mesh has no planar face to mate against.

### Control panel
- The control panel is an **archetype too**: discrete S/M/L tiers with fixed slots. Pick the
  smallest tier that fits (volume + keepouts). No 3D packing solver in v1, and no LLM placing
  parts by eye.

### Validation order — cheap and exact first, fuzzy last
1. **Deterministic gate:** clash detection · mass properties · bbox+keepout vs panel volume ·
   reach envelope · torque margin vs spec sheet · BOM cost vs budget.
2. **Vision gate (plausibility only):** floating/inverted/backwards parts, visual
   intersections, absurd proportions, a machine that plainly can't do the task.
   **Never ask a vision model to judge what a query can measure.** Vision cannot measure.
3. **Bounded repair:** structured signals only (`part X intersects part Y at face Z`), never
   "looks wrong". **Max 3 attempts, then escalate to a human.**
- Screenshot after **every stage**, not just at the end — per-stage capture gives credit
  assignment.

### CAD backend
- The geometry layer sits behind a **clean, swappable interface**. Fusion is a prototyping
  backend, not a production one (desktop, per-seat, needs a logged-in session — cannot serve
  concurrent users). Do not write Fusion-specific code outside the adapter.

### The design record
- One versioned JSON record per run, accumulating through every layer. It is the unit of
  persistence, replay, and dataset.
- **The human review gate captures diffs, not just approve/reject.** Every engineer correction
  is a labeled training example and it is free — this is the whole data flywheel.
- The record must carry **customer outcome** and **quoted vs. actual build cost**.

### Process
- **A human review gate before anything reaches a customer.** Always, at least for the first
  year. An engineer spending 15 minutes checking instead of 8 hours building the quote is
  still a ~30× win with none of the risk.
- Full layer spec: **`docs/architecture.md`**. Governing principle: **the LLM proposes,
  deterministic code disposes** — every LLM output must be checkable by code.
- Stage-gated pipeline with machine-verifiable checks between stages. Never build a fully
  autonomous end-to-end path — at ~85% correctness per stage, eight stages compounds to ~30%.

---

## Fusion CAD work

The global Fusion rules in `~/.claude/CLAUDE.md` apply in full, in particular the
**GOLDEN RULE: imported/vendor assemblies are READ-ONLY.** Pin `participantBodies` on every
cut/join to our own bodies. Verify after every modelling session and report the result.

Archetype templates are *our* models and may be edited freely — but changing an archetype's
parameter scheme is an architectural decision and must be logged.

---

## Working style

- Optimize **iterations per week**, never the token bill. Tokens are a rounding error against
  hardware cost and human time.
- Prefer boring, hand-curated data over clever generation. The catalog is the moat precisely
  because it is tedious work nobody else will do.
- When a real number is available, get the real number. Estimates go in the log marked
  `Confidence: speculative`.
