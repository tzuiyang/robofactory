# robotics_streamline — Project Rules

## What this project is

**An app that helps ordinary people design robots.**

Someone describes, in their own words, what they want a machine to do. The app returns a real
design: a **BOM of parts that can actually be bought** and a **short concept simulation** of the
machine doing the job. No research, no CAD, no coding, and no robotics vocabulary is required
of the person using it.

**Cost ceiling: parts under $3,000. Finished machine sells under $10,000.**
Enforced in code — `MAX_PARTS_COST_USD` / `MAX_SALE_PRICE_USD` in `config.py`, gated in L4,
applied in `serve.py`, and the intake's budget menu is bounded to match.

> The job is to **streamline and assist designers** — including people who are not designers
> yet. Every layer exists to remove work a person would otherwise have to do themselves.

Read that before proposing anything, because it constrains everything:

- The output must be **honest and buildable**, not impressive.
- Someone who has never built a robot must be able to read it.
- Where the app cannot stand behind something, it says so plainly rather than hiding it.

We are not selling AI-designed robots. We use AI to remove the cost of getting from *"I want a
machine that does X"* to a design a person can actually order parts for.

---

## RULE 0 — Simplest honest model. Add depth only when a real request needs it.

This is the rule that gets broken first, and breaking it is expensive.

Depth is not free. Modelling carpet rolling resistance, skid-steer scrub, or drive-motor speed
bands costs whole sessions and answers questions **nobody has asked yet**, for machines that do
not have a customer yet. It also generates questions for the team that they should not have to
think about.

- Pick the simplest model that is **honest** — one whose assumptions can be stated out loud.
- State what it excludes. An unstated exclusion is a lie; a stated one is a scope boundary.
- Add depth when a **real request** needs it, not when it would be more rigorous.
- If something is genuinely unmodelled, report it as unmodelled. Never substitute a
  plausible-looking number from a formula that does not apply. See "a skipped check is never
  a pass" below.

Park what you do not build: log it, note it in `TODO.md`, move on.

**Do not ask the team to specify engineering parameters for a machine class that has no
customer.** Choose a defensible default, state it, and log it as an assumption.

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
- **Data** — any real number we learn (part price, cycle time, measured error, token/render
  cost, what $3,000 actually buys). Numbers are the scarcest thing in this log.

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

The long-term asset is accumulated design knowledge — which archetypes work, which parts fail,
what people actually ask for, where estimates diverge from reality. That asset only compounds
if it is written down as it happens. Reconstructing it later from code and git history is
impossible, because the valuable part is the *reasoning*, and reasoning leaves no trace in a
diff.

**If you are unsure whether something is worth logging, log it.** The cost of a redundant entry
is three lines. The cost of a lost insight is re-deriving it.

---

## Locked architectural constraints

These were decided deliberately (see `log.md` §3). Do not quietly work around them. If one
needs to change, log the change as a superseding decision with the reason — don't just do it.

### Design generation
- **Instantiate parametric archetypes. Never generate CAD geometry from scratch.**
  The AI's job is *selection and sizing*, not geometry creation. Archetypes are proper
  parametric models authored by a person, with driven dimensions.
- Pipeline is fixed:
  `requirements extraction → archetype pick → parameter sizing → model instantiation → BOM → kinematic sim → video`
- Concept-level detail only. Do not emit CAD that binds whoever builds the machine.

### Simulation
- **Kinematic, not physics, for v1.** The three questions that matter are: does it reach, does
  it fit, how fast does it work. All three are kinematic — reach envelope, collision-free path,
  cycle-time estimate. No physics engine, no learned policy.
- The video is a **scripted trajectory replay**: deterministic and repeatable.
- Physics is added later only where it genuinely matters — and only as a logged decision.

### BOM discipline — highest-risk artifact, hardest rules
- **Never invent a part number.** If it is not in the curated catalog, it does not exist.
  This is a hard constraint, not a preference. It matters *more* for a novice user, who cannot
  tell a real part number from a plausible one.
- **Curated catalog only** — a hand-built structured database with real prices and specs. This
  is the core asset of the product. Parts are added by a person, **offline, once**.
- **Only a human sets `verified=true`**, after checking the part number, price and specs
  against the vendor. Unverified parts cannot be quoted — enforced in code.
- **Explicit safety factors** (2–3× on actuator torque), and the factor must be *visible* in
  the output. Conservative is free at concept stage; optimistic is expensive.
- **Price as a range, never a point estimate.** e.g. "Estimated $4,500–6,600."
- Every dimension is a number with a stated unit. "Looks about right" is not a value.

### Output presentation
- **No robotics vocabulary in customer-facing text.** Enforced by a test. Careful plain-language
  intake is wasted if the result screen says "3 DOF: [base] -> shoulder -> upper_link". Detail
  belongs behind an "Engineering detail" disclosure.
- The video should look **engineering-honest, not beautiful** — CAD-shaded, dimension callouts,
  reach-envelope overlay, cycle-time counter, and a visible "concept simulation" label. It
  protects against expectation gaps, which matter most for someone new to robotics.
- Never present a simulation as evidence the machine works. Simulation verifies a thin slice
  (kinematics, reachability) and verifies *nothing* about tolerance stack-up, assembly,
  thermal, wiring, backlash, manufacturability, or control stability on real hardware.
- Styling is constrained to what is manufacturable: extrusion, sheet metal, printed covers.

### Data & runtime research
- **No runtime web research for parts. Ever.** Part selection is a *database query* over the
  curated catalog under a budget constraint — deterministic, instant, every result purchasable
  by construction. Live research produces dead links, out-of-stock parts, wrong specs, invented
  part numbers, and a different BOM on every run.
  *This is about the **quote path**, not about ownership.* The catalog does not have to mirror a
  physical inventory — it can be built from anything commonly purchasable. Curation still
  happens offline, once, by a person.
- Runtime research IS allowed for the **user's task domain** (the thing being handled, the
  environment) — that varies per request and cannot be pre-cached.
- Component geometry is **STEP, not STL**, downloaded once and normalized into the catalog with
  a defined origin/datum, mounting frame + bolt pattern, bounding box **and keepout volume**,
  connector + cable-exit direction, thermal flag. A mesh has no planar face to mate against.

### Control panel
- The control panel is an **archetype too**: discrete S/M/L tiers with fixed slots. Pick the
  smallest tier that fits (volume + keepouts). No 3D packing solver, and no LLM placing parts
  by eye.

### Validation order — cheap and exact first, fuzzy last
1. **Deterministic gate:** clash detection · mass properties · bbox+keepout vs panel volume ·
   reach envelope · torque margin vs spec sheet · **cost vs the $3k/$10k ceiling**.
2. **Vision gate (plausibility only):** floating/inverted/backwards parts, visual
   intersections, absurd proportions, a machine that plainly can't do the task.
   **Never ask a vision model to judge what a query can measure.** Vision cannot measure.
3. **Bounded repair:** structured signals only (`part X intersects part Y at face Z`), never
   "looks wrong". **Max 3 attempts, then escalate to a human.**
- **A skipped check is never a pass.** Backends without B-rep report `SKIPPED`, not `PASS`.
- **The repair vocabulary must be as fine-grained as the physics.** Two failure modes with
  different fixes must not share one signal — the loop acts on it. A slipping wheel is fixed
  with grip, not torque.
- Screenshot after **every stage**, not just at the end — per-stage capture gives credit
  assignment.

### CAD backend
- The geometry layer sits behind a **clean, swappable interface**. Fusion is a prototyping
  backend, not a production one (desktop, per-seat, needs a logged-in session — cannot serve
  concurrent users). Do not write Fusion-specific code outside the adapter.

### The design record
- One versioned JSON record per run, accumulating through every layer. It is the unit of
  persistence, replay, and dataset.
- **The human review gate captures diffs, not just approve/reject.** Every correction a person
  makes is a labeled training example and it is free — this is the whole data flywheel.

### Process
- **A human check before anything is presented as a firm quote.** The app stops at
  `awaiting_human_review`; it never hands someone a promise nobody has looked at.
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
- **Finish what is asked, then stop.** Do not extend scope into adjacent engineering because it
  would be more complete. See RULE 0.

---

## History

This project was previously framed as a **pre-sales concepting tool for an industrial robotics
team**, where the deliverable was a sales artifact and a human team built the machine
afterwards. That framing was corrected on **2026-08-28** (see `log.md`). The original file is
kept at `docs/CLAUDE-v1-presales-framing.md`.

Most constraints survived the reframe unchanged — catalog discipline, kinematic-only
simulation, the human gate, and the validation order are right under either reading. What
changed is **who the output is for**: an ordinary person designing a robot, not a procurement
department.
