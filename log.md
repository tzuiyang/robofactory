# Project Log — robotics_streamline

Append-only decision and insight log. Newest entries at the bottom of each section.
This file is the project's memory: why things are the way they are, what we tried,
what broke, and what we learned. It exists so that scale decisions later are made
with the reasoning intact, not re-derived from scratch.

**Entry format** — every entry gets:

```
### [YYYY-MM-DD] <short title>
**Type:** bottleneck | breakthrough | decision | rejected | open-question | data
**Context:** what prompted this
**Finding:** the actual insight, in one or two sentences
**Consequence:** what changes in the product/architecture because of it
**Confidence:** high | medium | speculative — and what would raise it
```

Keep entries short. If something needs a page, it belongs in `docs/` and the log
links to it.

---

## 1. Product definition

### [2026-08-25] Original concept: text → full autonomous robot
**Type:** rejected
**Context:** Starting premise — AI now has Fusion MCP (CAD) and KiCad MCP (electronics),
so an agent could in principle handle mechanical + electrical + software, taking a
task description all the way to a URDF simulating in Isaac.
**Finding:** The timing thesis is correct and under-exploited — MCP genuinely made CAD
and EDA agent-addressable, and that is recent. The *product* built on top of it was
wrong: full-pipeline autonomy is not achievable to a trustworthy standard.
**Consequence:** Keep the timing thesis. Drop the "autonomous end-to-end robot generator"
framing. See the pivot entry below.
**Confidence:** high

### [2026-08-25] PIVOT — the deliverable is a sales artifact, not an engineering artifact
**Type:** breakthrough
**Context:** Reframed the app as: user describes a task (and desired look) → app produces
a **BOM + a short simulation video** of the robot working → if the user likes it, a human
robotics team builds and customizes it.
**Finding:** This moves the output from something that must be *correct* to something that
must be *credible enough to start a paid conversation*. A human team validates and
redesigns afterward. That single change dissolves most of the technical objections at once.
**Consequence:** This is the product. We are not selling AI-designed robots; we are selling
robots, and using AI to destroy the cost of pre-sales engineering. No AI liability, no need
to convince conservative hardware buyers to trust AI output, no software sales motion needed
initially — we are our own first customer.
**Confidence:** high — this is the load-bearing decision of the whole project.

### [2026-08-25] Strategic framing: lead generator, not just an internal time-saver
**Type:** decision
**Context:** Two possible uses of the same tool.
**Finding:** As an internal tool it saves engineer-hours on quotes we already produce.
As a public-facing intake ("describe your automation problem → concept + simulation +
budget range in 10 minutes") it *increases top-of-funnel*, letting us quote 50 leads
instead of 5.
**Consequence:** Design for eventual public/self-serve use even while v1 is internal-only.
Not aware of any integrator doing this — potential real differentiator.
**Confidence:** medium — depends on funnel data (see open questions).

---

## 2. Bottlenecks identified

### [2026-08-25] No cheap feedback loop in mechanical/electrical design
**Type:** bottleneck
**Context:** Why does AI work so well for code but not for hardware?
**Finding:** Coding agents work because of a loop that is free, instant, and total:
generate → compile → test → read error → fix. Milliseconds, zero marginal cost, and the
test result *is* ground truth. Hardware has no such loop.
**Consequence:** Any architecture that assumes "the agent will iterate until it's right"
is invalid for hardware. The agent must be right in very few shots, which means the design
space must be constrained rather than searched.
**Confidence:** high

### [2026-08-25] Simulation is not the compiler
**Type:** bottleneck
**Context:** Proposed using Isaac sim as the substitute verification loop.
**Finding:** A URDF that simulates beautifully verifies only a thin slice — kinematics,
reachability, gross dynamics. It does **not** verify:
tolerance stack-up · press fits · fastener access · human assemblability · wire routing ·
motor stall torque at duty cycle · thermal derating · backlash · gearbox friction ·
link compliance · manufacturability · part availability · cost · power integrity · EMC ·
sensor latency · control loop stability on real hardware.
**Consequence:** Never present a passing simulation as evidence the machine works. A
high-fidelity sim is still a demo until physical hardware moves. Label sim output honestly.
**Confidence:** high

### [2026-08-25] Compounding error across pipeline stages
**Type:** bottleneck
**Context:** Chain is intent → mechanism → CAD → URDF → electronics → firmware → control → sim.
**Finding:** At 85% correctness per stage with no inter-stage error reflection, end-to-end is
~30%. Software agents survive this only because tests reflect errors back at each step.
**Consequence:** Full-pipeline autonomy is the wrong architecture. Use stage-gated design with
hard, machine-verifiable checks between stages, and a human gate before customer delivery.
**Confidence:** high

### [2026-08-25] Physical iteration cycle time, not token cost, is the real constraint
**Type:** bottleneck
**Context:** Considered closing the loop by filming the real robot and feeding video to the AI.
Assumed the cost was tokens and time.
**Finding:** Cost model was inverted. Tokens for video are a rounding error (a few dollars)
against a ~$300 build and a week of human time. The binding constraint is **iterations per
week** — a physical loop supports single-digit samples per month.
**Consequence:** Optimize iterations/week (a mechanical + instrumentation problem), never the
token bill. A loop with a ~10-sample budget cannot rescue a low-accuracy generator; it can only
*validate* an already-good one. Therefore the physical loop is a **calibration** mechanism for
cheap virtual checks, not the primary error-correction path.
**Confidence:** high

### [2026-08-25] Vision-only feedback has no credit assignment
**Type:** bottleneck
**Context:** Proposal to film the robot and let the AI diagnose from video.
**Finding:** Video shows "the arm sags and oscillates" but cannot attribute it among: wrong
inertia tensor, gearbox backlash, undersized motor, flexing bracket, controller gains, or
encoder/comms latency. It is one blurry error signal at the end of an 8-stage pipeline.
A loop without credit assignment does not converge — it just repeats that something is wrong.
**Consequence:** Do not build the "send video to AI" loop as the primary mechanism.
**Confidence:** high

### [2026-08-25] BOM accuracy is the highest-risk artifact in the new product
**Type:** bottleneck
**Context:** Post-pivot, the video sells but the BOM is what we quote off.
**Finding:** A beautiful video with an under-specced BOM is worse than nothing — we either eat
the cost or re-quote, and re-quoting after a customer has fallen in love with a concept is how
deals die.
**Consequence:** Hard rules adopted — see `CLAUDE.md` §BOM discipline. Curated catalog only,
explicit safety factors, price as a range, never invent a part number.
**Confidence:** high

### [2026-08-25] Fusion 360 cannot be the production CAD backend
**Type:** bottleneck
**Context:** Planning the geometry layer around Fusion MCP.
**Finding:** Fusion is desktop software — GUI-driven, per-seat licensed, requires a logged-in
session on a real machine. Fusion MCP drives *our* running instance. Fine for prototyping and
for an internal tool at a few quotes/day; unworkable for a many-user app, since we cannot spin
up 50 concurrent Fusion sessions in a container.
**Consequence:** Keep the geometry layer behind a clean, swappable interface. Prototype on
Fusion, but do not build deep on it. Options: Fusion worker farm (works now, caps throughput,
licensing + ops pain) · Onshape (cloud-native REST API, built for concurrency, means
re-authoring archetypes) · headless kernel — CadQuery/build123d/OpenCascade (cheapest and
fastest, scriptable/testable/version-controlled, 100 concurrent for free, code-first authoring).
For parametric archetypes with driven dimensions, a headless kernel is a strong fit — the
archetype becomes a script. **Do not let this decision be made by accident through six months
of Fusion-specific code.** Decide once internal-vs-public is settled.
**Confidence:** high on the constraint; medium on which replacement — depends on open question #9.

### [2026-08-25] Runtime web research for parts is prohibited
**Type:** rejected
**Context:** Proposed layer 1 was "deep think + deep research", with a later layer researching
exact parts within the user's budget.
**Finding:** Live per-request part research violates the locked rule *never invent a part
number*. It produces dead links, out-of-stock parts, wrong torque figures, and non-existent
part numbers. It is also slow, non-deterministic, and unverifiable — the same query twice gives
two different BOMs, which is fatal for a quoting tool.
**Consequence:** Research is real work but happens **once, offline, into the catalog**, with a
human confirming each entry. At runtime, part selection is a **database query under a budget
constraint** — deterministic, instant, free, every result purchasable by construction.
*Exception kept:* runtime research of the **customer's task domain** (what the handled part
looks like, typical cycle times in that industry, environmental constraints) is legitimate —
it varies per request and cannot be pre-cached.
**Confidence:** high

### [2026-08-25] STL is the wrong format and runtime download is the wrong time
**Type:** rejected
**Context:** Proposal for the agent to grab STL files of each part online and drop them into
the control panel.
**Finding:** Vendor STLs have inconsistent units (mm vs inch), arbitrary origins, no mounting
datums, absurd mesh densities, unclear licensing, and are frequently missing. Critically,
**a mesh has no planar face to mate or joint against** — you cannot reliably constrain to
triangles.
**Consequence:** Use **STEP**, downloaded once and normalized on catalog entry: origin at a
defined datum (mounting-face center), explicit mounting frame + bolt pattern, bounding box
**and keepout volume** (connectors need clearance, not just the body), connector face and cable
exit direction, thermal flag. ~10-20 min of human work per part, once, for ~40 electronic
components — then panel layout is instant and correct forever.
**Confidence:** high

### [2026-08-25] Control-panel packing is a solver problem, not an LLM job
**Type:** bottleneck
**Context:** Proposal for the agent to place downloaded part geometry into the control panel.
**Finding:** This is 3D bin packing with clearance, connector access, cable routing, and thermal
constraints. An LLM eyeballing screenshots and nudging parts is exactly the spatial-reasoning
failure mode already identified.
**Consequence:** For v1, **do not solve it** — see the panel-tier breakthrough in §3.
**Confidence:** high

### [2026-08-25] Tier differentiation requires catalog depth
**Type:** bottleneck
**Context:** Caught by `test_offered_tiers_are_always_distinct` during first pipeline run.
**Finding:** With only three actuator sizes in the catalog, the good/better/best tiers all
resolve to the **same actuator** — producing two identically-priced tiers. Showing a customer
"better" at the same price and spec as "good" reads as padding and costs trust.
**Consequence:** `_dedupe_tiers()` collapses identical tiers and records why in the tier notes.
But the real lesson is a **data requirement, not a code fix**: meaningful tiering needs roughly
5+ actuator classes spanning the torque range. If runs keep collapsing to one tier, add catalog,
not code. Test fixture `deep_catalog` exists specifically to prove the collapse is a data
problem rather than a bug.
**Confidence:** high

### [2026-08-25] Reach check compared full span against reach
**Type:** bottleneck
**Context:** Demo output read `reach 0.900 m` for a 0.45 m requirement.
**Finding:** A revolute arm sweeps a circle, so its bounding box is ~2x its reach. The gate was
comparing bbox span against the reach requirement — which would have **passed a machine half
the required size**. Exactly the class of error the deterministic gate exists to catch, found
because the check prints its number rather than just a pass/fail.
**Consequence:** Reach is now measured from the base axis outward
(`max(|bbox.min.x|, |bbox.max.x|)`), and the detail string reports both reach and span.
Two regression tests added.
**Confidence:** high — generalisable lesson: **every check must print the number it compared,**
not just its verdict. A silent PASS hides an inverted comparison.

### [2026-08-25] All joints sized at shoulder torque — known over-spec
**Type:** open-question
**Context:** SCARA run selected 4x the largest actuator (4 x $640) for a 0.8 kg payload.
**Finding:** `config.build()` sizes every joint slot at the worst-case shoulder torque. On a
SCARA the Z and theta joints carry far less, so the BOM is materially over-specified and the
quote is inflated.
**Consequence:** Conservative is safe but expensive, and an inflated quote loses deals as surely
as an under-specced one. Needs per-joint torque derivation from the archetype's kinematic chain.
Deferred: it requires the archetype templates to declare per-slot load paths, which is blocked
on the templates existing (open question #6).
**Confidence:** high that it is wrong; medium on how much it inflates the quote.

### [2026-08-25] Topology is a tree, not a chain
**Type:** bottleneck
**Context:** `test_every_synthesized_chain_is_mechanically_valid` failed on
{MOBILITY, GRASPING, VISION}.
**Finding:** The composer modelled the robot as a linear chain, so a mobile manipulator with a
sensor head tried to mount the head **past the gripper** — which cannot mate to a TOOL interface,
and would physically ride along with every pick. A whole class of real robots (mobile
manipulators, anything with both an arm and a head) was inexpressible.
**Consequence:** `ModuleInstance` gained a `parent` label; validation walks the mounting tree
rather than a sequence. Arm and head are now separate branches off the base. Verified: mobile
manipulator with vision + audio composes to 5 DOF and validates clean.
**Confidence:** high — found only because a test enumerated capability combinations rather than
checking one happy path.

### [2026-08-25] Modules bought parts for capabilities nobody requested
**Type:** bottleneck
**Context:** The talking-rover run pulled a **camera** into the BOM.
**Finding:** `head.sensor` declared all its part kinds unconditionally, so a robot that only
talks also bought vision hardware — silently inflating the quote.
**Consequence:** Added `Module.capability_kinds`: capability-gated part kinds included only when
that capability was actually requested. Same failure family as the per-joint over-sizing entry
above: **conservative defaults inflate quotes, and an inflated quote loses deals as surely as an
under-specced one.**
**Confidence:** high

### [2026-08-25] Mobile-only robots were rejected by a manipulator reach envelope
**Type:** bottleneck
**Context:** "A robot that rolls around the house and talks to my kids" was rejected as
"no archetype covers payload 0.2 kg at reach 2.0 m".
**Finding:** Archetype selection and torque sizing ran unconditionally, but a rover never
reaches for anything — a manipulator reach envelope is a **meaningless test** for it, and the
cantilever torque formula is the wrong physics entirely (drive torque is a traction problem).
**Consequence:** `build()` now gates the manipulator path on manipulation capabilities. Mobile
bases use a synthesized `_MOBILE_ONLY` archetype and carry an explicit assumption that traction,
gradient and rolling resistance are NOT modelled and need an engineer. Generalisable: **as the
app covers more machine types, every "always run" step must be re-examined for whether it even
applies.** Silently applying the wrong physics is worse than not applying any.
**Confidence:** high

### [2026-08-25] Confirmation echoed the raw sentence back
**Type:** bottleneck
**Finding:** "You want a machine that I want it to pick up mugs" — people answer
conversationally, and echoing verbatim reads as though the app did not understand them, which is
the opposite of what a confirmation is for.
**Consequence:** `_as_predicate()` strips conversational lead-ins; the frame changed to the
infinitive ("a machine **to** pick up mugs"), which is grammatical for every phrasing without
needing verb conjugation.
**Confidence:** high

### [2026-08-25] Jargon test false positive: "ros" inside "across"
**Type:** data
**Finding:** The no-jargon test used substring matching and flagged "ac**ros**s".
**Consequence:** Word-boundary regex. Noted because the same naive-substring trap will recur in
any future content filter — and because the test **did** catch two genuine leaks before this
(the word "reach" in a help string, and a kg range in the confirmation), which is why it stays.
**Confidence:** high

### [2026-08-25] Throughput claim was theoretical, not achievable
**Type:** bottleneck
**Context:** The result screen quoted "roughly 989 items an hour" for a mug-picking arm.
**Finding:** The kinematic cycle time assumes zero dwell, perfect part presentation and 100%
uptime. The arithmetic is right and the claim is not — quoting it is an over-promise that gets
discovered **at delivery**, which is the expensive time to discover it.
**Consequence:** Added `UTILISATION = 0.65` and rounded the result so it reads as an estimate
rather than a measurement: "expect roughly 600 items an hour once loading, dwell and downtime
are accounted for." Test asserts the raw rate never appears in customer-facing text.
Same family as the per-joint over-sizing and uncommanded-parts entries: **every number shown to
a customer needs checking for whether it is achievable, not merely correct.**
**Confidence:** high — the 0.65 figure itself is a placeholder and should be replaced with the
team's real observed utilisation (new open question #14).

---

### [2026-08-28] End-to-end user test: the web app is not the pipeline
**Type:** bottleneck
**Context:** First full ETE run pretending to be a brand-new user — server started, intake
walked in a browser and over the API, plus edge cases.
**Finding:** `serve.py` calls `config.build()` + `explain` directly. It never touches
`pipeline.py`, `validate.py`, `present.py` or `record.py`. So the user-facing app runs with
no L4 gate (torque, reach, interference, catalog_verified), writes no design record, and has
no human review gate — the three things the README says protect the customer. It also
force-sets `verified=True` on all 31 PLACEHOLDER parts (`serve.py:31`), so it quotes
"$2,540 to $3,650" from invented part numbers. `demo.py` runs the real pipeline and behaves
correctly (blocks, reports SKIP, outcome `draft`).
**Consequence:** The demo path and the product path have diverged. The web app must call
`pipeline.run()` and render its outcome, or every guarantee in `CLAUDE.md` is enforced only
in a demo script nobody ships.
**Confidence:** high — observed directly, both paths executed.

### [2026-08-28] Drive gearmotor selected for an arm elbow
**Type:** bottleneck
**Context:** Same ETE run, first successful design (0.2 m reach, 0.085 kg payload).
**Finding:** `_pick_actuator` filters on `PartKind.ACTUATOR` and torque only. Every actuator
in the catalog shares one kind, so `act.drive` (PLACEHOLDER-ACT-DRIVE, the wheel gearmotor,
3.5 Nm) was selected for the **elbow** of a bench-mounted arm, sitting between `act.large` at
the shoulder and `act.small` at the wrist. A continuous-rotation drive motor has no position
feedback and cannot serve as a revolute joint.
**Consequence:** Actuators need a sub-kind (joint servo vs drive gearmotor) and
`_pick_actuator` needs to filter on it. This will silently produce unbuildable BOMs the moment
the catalog holds real parts.
**Confidence:** high — reproduced in the returned BOM.

### [2026-08-28] The user journey has no BOM and no simulation
**Type:** bottleneck
**Context:** ETE run, result screen inspected in the browser.
**Finding:** The result screen shows a prose parts list ("a rotating shoulder joint"), a cycle
time, a price range, caveats, an Engineering-detail disclosure, and "Design another". Neither
of the two headline deliverables is present: no purchasable BOM with part numbers, no concept
simulation. A caveat reads "The simulation shows the machine reaching and moving" while no
simulation is rendered. The journey then dead-ends — no way to submit for review.
**Consequence:** L5 produces a trajectory and a BOM document; the web app just does not render
them. Wiring the existing L5 output into the result screen is the cheapest large win available.
**Confidence:** high.

### [2026-08-28] Data: the reachable design envelope is one workspace size wide
**Type:** data
**Context:** ETE swept workspace size at the lightest payload, cheapest budget.
**Finding:** shoebox / dinner plate / laptop all succeed and return the *identical* price
($2,540–$3,650); desk and larger are rejected as over the $3,000 parts ceiling. So under the
placeholder catalog the app can offer exactly one machine, and the three smallest answers to
"how big an area?" have no effect on the output.
**Consequence:** Confirms the tier-collapse entry from 2026-08-25 from the user side, and
raises open question #12 in priority: the catalog is what sets the envelope, not the code.
**Confidence:** high with placeholder prices; real prices would move the boundary.

### [2026-08-28] Customer-facing grammar bug in the confirmation sentence
**Type:** bottleneck
**Context:** ETE run; the sentence is displayed at h1 size on the confirm step.
**Finding:** `GuidedIntake.summary()` renders "You want a machine to pick up small parts...
It handles things **lighter than a phone than that**." — the weight-refine option text is
concatenated onto a stem that already ends in a comparative. The free-text task answer is also
spliced in raw, so "I want a machine that picks up parts" becomes "a machine to picks up parts".
An empty task answer yields "You want a machine to ."
**Consequence:** The product's whole claim is careful plain language; this is the first full
sentence a user reads. Needs a phrasing table per option rather than string concatenation, and
a non-empty check on the task field.
**Confidence:** high — seen in the browser.

### [2026-08-28] Malformed request body crashes the handler thread
**Type:** bottleneck
**Context:** ETE edge cases. `POST /api/start` with a non-JSON body.
**Finding:** `serve.py:124` calls `json.loads` unguarded; the exception escapes `do_POST`, the
connection is dropped with no response (curl reports http=000) and a traceback is printed.
Session-expiry, missing fields, unknown routes and path traversal all behave correctly.
**Consequence:** One try/except returning 400. Low severity locally, but it is the only
unhandled path found.
**Confidence:** high — reproduced with traceback.

### [2026-08-28] Web app rewired onto the pipeline; actuator role added
**Type:** breakthrough
**Context:** Acting on the two blocking findings from the same day's end-to-end user test.
**Finding:** Two fixes, both small, both closing a class of error rather than an instance.
(1) `serve.py` now calls `pipeline.run()` and saves the design record, so the user path gets
the L4 gate, the SKIP-is-not-PASS reporting and the human gate. The `verified=True` override
is gone; a `--demo` flag passes `allow_unverified` into the pipeline instead and labels the
result, so nothing is ever claimed to be checked that is not. (2) `ActuatorRole` (`joint` |
`drive`) is now a field on `ActuatorSpec` and a hard filter in `Catalog.query`, so the wheel
gearmotor can no longer land in an arm elbow. Also: `_pick_actuator` now distinguishes "we
stock nothing strong enough" from "the only candidates are unverified" — those had collapsed
into one message telling the customer to shrink a design that was already fine.
**Consequence:** With the seed catalog the app now blocks every request, which is correct and
newly visible. 97 tests (was 87); `tests/test_web_app.py` pins the app to the pipeline and
`tests/test_actuator_role.py` pins role selection in both directions.
**Data:** fixing the elbow moved the example design from $2,540-3,650 to $2,780-4,000 — the
earlier number was cheap because it was quoting a wheel motor as an elbow servo.
**Confidence:** high — both paths run, tests green.

### [2026-08-28] Design records in `runs/` deleted during cleanup
**Type:** bottleneck
**Context:** An overbroad `rm -f runs/*.json` while clearing test output.
**Finding:** ~10 design records from earlier sessions were destroyed. The repo is not under
version control, so they are not recoverable.
**Consequence:** Nothing downstream depended on them — they were demo runs, not curated data.
But the records are supposed to be the dataset, and the dataset is currently sitting in an
untracked directory that a stray glob can empty. `git init` before the records start carrying
engineer corrections.
**Confidence:** high.

## 3. Breakthroughs / core architectural decisions

### [2026-08-25] Instantiate parametric archetypes — do not generate CAD
**Type:** breakthrough
**Context:** LLMs are bad at spatial reasoning and feature-tree editing is brittle.
**Finding:** The AI does not need to create geometry. Build 2–3 parametric CAD templates for
archetypes the team already builds well (tabletop SCARA, small gantry, fixed-base arm), each a
proper Fusion parametric model with driven dimensions. The AI's job becomes **selection and
sizing**, which LLMs are genuinely good at.

```
task description
  → extract requirements (payload, reach, cycle time, workspace, environment)
  → pick archetype
  → size parameters (reach → link lengths; payload × reach → joint torque → actuator)
  → instantiate the parametric model
  → pull BOM from curated catalog
  → kinematic sim → video
```
**Consequence:** This is the central architectural decision. It guarantees output is buildable
because our own engineers designed the archetype, and it eliminates the generative-CAD failure
mode entirely. Tradeoff: too few archetypes feels canned, too many is expensive to build.
Start with what we already have real CAD for.
**Confidence:** high

### [2026-08-25] Kinematic simulation beats physics simulation for a proposal
**Type:** breakthrough
**Context:** Original plan was Isaac Gym / physics sim.
**Finding:** A buyer asks three questions: **Does it reach? Does it fit in my space? How many
parts per hour?** All three are kinematic — reach envelope, collision-free path, cycle-time
estimate. None require physics.
**Consequence:** Skip physics sim entirely for v1. It is slower, stochastic, needs per-scene
tuning, and answers a question the customer is not yet asking. The video becomes a scripted
trajectory replay: reliable, repeatable, no RL policy that might fail on render day. Add
physics later only where payload dynamics genuinely matter (high speed, heavy load, force control).
**Confidence:** high

### [2026-08-25] Constrain the design space to a real, purchasable catalog
**Type:** decision
**Context:** How to make an LLM's output reliably buildable.
**Finding:** Composing from a fixed kit (goBILDA / MISUMI / OpenBuilds extrusion, Dynamixel or
ODrive actuators, standard bearings and fasteners) gives three things generation cannot: every
part is purchasable, every interface is known-good, and the search space shrinks to something an
agent handles reliably. Also yields a real BOM with part numbers and prices as a free byproduct.
**Consequence:** The curated catalog (100–300 parts, hand-built, with prices, torque/speed
curves, mounting data) is the **core asset** of the product — and the most defensible, because
it is boring work nobody else will do.
**Confidence:** high

### [2026-08-25] If a physical loop is ever built, use telemetry + system identification
**Type:** decision (deferred — not v1)
**Context:** The right way to close sim-to-real, if/when we do it.
**Finding:** The robot's own telemetry is strictly better than video: joint encoders (1 kHz,
directly comparable to sim `q`), motor current (1 kHz, ∝ joint torque), IMU (~$5, 200 Hz+).
Video is a lossy, uncalibrated, unregistered, low-rate proxy for what we can log natively for
free. Per-joint time-resolved residuals *do* give credit assignment: lag on direction reversal →
backlash; steady-state droop under load → gravity comp or link compliance; current above spec →
undersized actuator.
The correct loop is system identification:
```
scripted excitation trajectory
  → sim → predicted q(t), τ(t)
  → hardware → measured q(t), i(t)
  → residual → fit physical params (friction, backlash, compliance, Kt, inertia scale)
  → write back into URDF/sim config → residual shrinks
```
Pay the hardware cost once to calibrate, then iterate for free in sim.
**Consequence:** Deferred beyond v1. When we do it: vision keeps a narrow complementary role as
a detector for *uninstrumented* failure modes (bracket flexing, wire snagging, screw backing
out, collisions, wobble, thermal via IR) — not as the primary loop.
**Confidence:** high

### [2026-08-25] Modular kit choice controls iteration speed
**Type:** decision
**Context:** Sample budget for any physical validation.
**Finding:** With modular hardware (goBILDA-style) we can change link lengths, swap actuators,
add payload, and shift load points in minutes instead of reprinting — turning cycle time from
weeks to hours and sample budget from ~10/month to ~100/month.
**Consequence:** Choose the kit that maximizes **reconfigurations per dollar**. This single
choice is worth more than any AI cleverness in the loop.
**Confidence:** high

### [2026-08-25] Sim-to-real residuals are a potential data moat
**Type:** open-question / data
**Context:** What compounding asset could this business accumulate?
**Finding:** Logging `(design parameters, sim prediction, real measurement)` triples across many
builds produces a sim-to-real residual dataset nobody has — the data needed to train a
correction model that makes generated designs *predictive* rather than merely plausible.
**Consequence:** Worth instrumenting for from the start even though the payoff is far out.
Caveat: it accrues at hardware speed, so it only compounds if reconfiguration cost is low.
**Confidence:** speculative — the moat is real in principle; the accrual rate is the risk.

### [2026-08-25] Control panel becomes an archetype too — discrete S/M/L tiers
**Type:** breakthrough
**Context:** Avoiding a 3D packing solver in v1.
**Finding:** Pre-design the control panel in three discrete size tiers with fixed component
slots. Given the component list, compute total volume + keepouts, pick the smallest tier that
fits, drop parts into slots. Deterministic and instantly verifiable.
**Consequence:** Consistent with the locked "instantiate archetypes, don't generate" decision,
and it carries a real commercial benefit: three standard panel designs are faster for the team
to build and can be **stocked**. The constraint that makes the software reliable is the same
constraint that makes the business efficient. Add a real packing solver only when tiers stop
fitting.
**Confidence:** high

### [2026-08-25] Budget is a first-class input, and output should be three tiers
**Type:** decision
**Context:** User proposed researching parts within the user's budget range.
**Finding:** Budget is a hard constraint that prunes the design space **and** it is what the
customer actually asks about. But a single design against a single budget turns a mismatch into
a rejection.
**Consequence:** Budget enters at L1 as a required field and acts as a knapsack-style constraint
on the L2 catalog query. Output **three tiers — good / better / best** — which is better sales
practice (anchoring) and converts a budget mismatch into a negotiation.
**Confidence:** medium-high

### [2026-08-25] The CAD screenshot loop IS viable — unlike the physical video loop
**Type:** breakthrough
**Context:** Proposal to use screenshots and recordings for constant agent self-checking.
Superficially resembles the rejected vision loop, but the economics are completely different.
**Finding:** The physical-video loop failed on cost: single-digit samples/month, days per
iteration, hundreds of dollars per turn. **A CAD screenshot costs cents and takes seconds.**
That loop is affordable, therefore viable. Further, screenshotting **after every stage** gives
stage-level attribution — partly solving the credit-assignment problem that killed the video loop.
**Consequence:** Adopted, with three constraints:
1. It runs **after** the deterministic gate, never instead of it. Clash detection, mass
   properties, bbox vs. volume, reach envelope, torque margin and BOM-vs-budget are exact,
   free and unambiguous. **Never ask a vision model to judge what a query can measure** —
   vision cannot measure, and letting it try yields confidently wrong dimensions.
2. Vision's job is the **plausibility gate** only: floating parts, inverted/backwards
   components, visual intersections, absurd proportions, a machine that plainly could not do
   the stated task.
3. **Bounded repair: structured signals** (`part X intersects part Y at face Z`), never free
   text like "looks wrong"; **max 3 attempts, then escalate to human.** An unbounded agent loop
   on a CAD model burns an hour and returns a worse model than it started with.
**Confidence:** high

### [2026-08-25] Governing principle: LLM proposes, deterministic code disposes
**Type:** breakthrough
**Context:** Designing the layer stack against the compounding-error bottleneck (§2).
**Finding:** Every LLM output must be checkable by code. Sizing is done with **formulas, not
LLM arithmetic**; archetype choice is LLM-proposed but rules-validated; part selection is a
constrained DB query, not a judgement.
**Consequence:** This is what stops ~85%-per-stage from compounding to ~30% end-to-end — errors
are caught at the stage that produced them instead of accumulating. Applies to every layer.
**Confidence:** high

### [2026-08-25] Layered architecture defined (L0-L5)
**Type:** decision
**Context:** First full system plan.
**Finding:** Six layers, communicating through one versioned **design record** (JSON) that
accumulates as it descends the stack — the unit of persistence, of replay, and of dataset.
```
L0 CATALOG & ARCHETYPES  (offline, human-curated — the asset, not a runtime layer)
L1 INTAKE                (LLM: requirements JSON, budget, domain research)
L2 CONFIGURATION         (LLM proposes / code disposes: archetype, sizing, BOM, 3 tiers)
L3 GEOMETRY              (swappable CAD backend: instantiate, panel tier, place parts)
L4 VALIDATION            (deterministic gate -> vision gate -> bounded repair, max 3)
L5 PRESENTATION          (kinematic sim, BOM doc -> HUMAN GATE -> customer)
```
**Consequence:** Full spec written to **`docs/architecture.md`**. Note L0 is not a runtime
layer — it is the substrate, built once and grown slowly.
**Confidence:** high

### [2026-08-25] The data flywheel lives in the human review gate
**Type:** breakthrough
**Context:** Goal of collecting massive data as the system scales.
**Finding:** The obvious data is the design records. The valuable data is elsewhere: **every
edit the engineer makes at the review gate is a labeled training example** — known input,
known-correct output. "AI chose actuator A, engineer swapped to actuator B" is precisely the
supervision that is normally impossible to obtain in engineering, and it costs nothing because
the engineer was reviewing anyway.
**Consequence:** **The review gate must capture diffs, not just approve/reject.** This single
design choice is the difference between accumulating a dataset and accumulating nothing.
The design record must also carry the two commercially decisive fields: customer outcome
(bought / didn't) and **quoted vs. actual build cost**.
**Confidence:** high — cheap to build in, expensive to retrofit. Build it from day one.

### [2026-08-25] NullBackend is architecture, not a test mock
**Type:** breakthrough
**Context:** Needed to build and test the pipeline with no CAD attached.
**Finding:** A backend that models geometry arithmetically lets the **entire L1-L5 pipeline
run, be tested and be reasoned about with zero CAD** — which matters because CAD is the slowest,
least available and least scriptable dependency in the stack. Anything needing real B-rep
(true interference, fastener access, exact mass) falls through to a real backend; everything
else is checked instantly and for free.
**Consequence:** Also serves as the proof that the seam is honest — if the pipeline runs on
NullBackend, no Fusion type has leaked upward. Enforced by `test_no_cad_specific_types_cross_the_seam`.
**Confidence:** high

### [2026-08-25] A check that did not run must never read as PASSED
**Type:** decision
**Context:** NullBackend cannot do interference tests.
**Finding:** The tempting implementation returns an empty clash list, which is indistinguishable
from "no clashes found" — a backend limitation silently becomes a clean bill of health.
**Consequence:** Backends carry a `supports_interference` capability flag; L4 reports SKIPPED
with the reason ("backend 'null' has no B-rep; run on a real CAD backend before quoting").
Status enum is PASS/FAIL/WARN/**SKIPPED**. Generalise this to every future check.
**Confidence:** high

### [2026-08-25] Catalog rules enforced in code, not prose
**Type:** decision
**Context:** CLAUDE.md says "never invent a part number" — prose rules get violated at 2am.
**Finding:** Three rules are now structurally impossible to break:
1. `Part.verified` defaults False; `Catalog.query()` excludes unverified by default; the L4
   gate hard-FAILs on any unverified part in a tier. **Seed data cannot produce a quote.**
2. `Geometry.__post_init__` rejects `.stl`/`.obj` outright — a mesh has no face to mate against.
3. `Catalog.get()` on an unknown id raises with "Parts are added by a human, offline — never
   invented at runtime."
**Consequence:** Verified by demo RUN 1: the real seed catalog blocks with
`catalog_verified: unverified parts cannot be quoted: act.large, ctrl.main, ...`
**Confidence:** high

### [2026-08-25] Pipeline scaffolded end to end, runs without Fusion
**Type:** decision
**Context:** "Set up the whole streamline first", Fusion not to be run.
**Finding:** All six layers exist as code. L1/L2/L4/L5 are complete and deterministic;
L3 is complete as an interface with two backends (Null working, Fusion written but blocked on
archetype templates existing).
**Consequence:** 45 tests pass; `demo.py` runs task description -> BOM + trajectory + design
record with no CAD attached. The blocking work is now **content, not code**: real catalog parts
(open q #5) and authored archetype templates (open q #6).
**Confidence:** high

### [2026-08-25] PIVOT 2 — generalize the topology, constrain the modules
**Type:** breakthrough
**Context:** User pushed back on fixed archetypes: the app must handle "a folding laundry
machine" or "a rolling robot that talks" and decide DOF and subsystems itself. Crucially they
were describing **their own manual workflow** (LLM plan -> LLM part research -> Fusion MCP body
-> Claude Code firmware -> simulate -> build), which they have actually executed. That makes it
an automation problem, not a research problem.
**Finding:** The design space is not binary — "3 fixed archetypes" vs "generate anything" was a
false dichotomy. A laundry folder and a talking rover are different **compositions of the same
module library**. The correct split:
| AI decides (discrete reasoning — tractable) | Engineer authors (spatial design — not tractable) |
|---|---|
| how many DOF and where | each module's parametric CAD |
| which modules, in what tree | mounting interfaces |
| capability -> subsystem ("talks" -> mic+speaker+SBC) | module internals |
| every parameter value | |
**Consequence:** `archetypes.py` becomes a preset layer over a general composer.
Added `capabilities.py` (task -> capability -> subsystem), `modules.py` (authored parametric
building blocks with typed mating interfaces), `topology.py` (synthesis + structural validation).
**Nothing previously built was discarded** — catalog, sizing, gates, record and the CAD seam are
unchanged. Module library grows with the first five real jobs, not upfront.
**Confidence:** high

### [2026-08-25] Buildability enforced by typed mating interfaces
**Type:** decision
**Context:** How to stop the composer emitting chains that cannot physically be assembled.
**Finding:** Each module declares `accepts` and `provides` interfaces (GROUND, BASE_TOP,
JOINT_OUT, LINK_END, TOOL). A composition is valid only if every module mates with its parent.
**Consequence:** An unbuildable robot is **not representable**, rather than merely discouraged —
the same enforcement-in-code pattern as the catalog `verified` flag. Verified by
`test_every_synthesized_chain_is_mechanically_valid` across four capability sets.
**Confidence:** high

### [2026-08-25] Capability closure: "it talks" implies a processor to talk with
**Type:** decision
**Finding:** Capability sets are closed under implication (AUDIO_OUT -> ONBOARD_COMPUTE,
GRASPING -> MANIPULATION, FLAT_MATERIAL_HANDLING -> MANIPULATION + VISION). Capability -> part
kind is a **fixed table**, not an LLM judgement: "talks" always means an audio output chain and
must not be re-derived or hallucinated per run.
**Consequence:** Omitting the SBC behind a speaker is exactly the kind of gap that makes a BOM
unbuildable. Now structurally impossible. The LLM's job is only the upstream language step:
"a rolling robot that talks" -> {MOBILITY, AUDIO_OUT, AUDIO_IN}.
**Confidence:** high

### [2026-08-25] Capability gaps are reported, never silently dropped
**Type:** decision
**Finding:** Asking for audio against a catalog with no speaker now returns an explicit gap
("audio_out needs speaker, audio_amp — no such part in the catalog").
**Consequence:** A robot quoted without the speaker it was asked for is a lost deal **at
delivery** instead of at quote. Demo confirms the talking-rover case reports 4 gaps rather than
producing a confident, wrong BOM.
**Confidence:** high

### [2026-08-25] The software layer is the one that fully automates today
**Type:** decision
**Context:** User's workflow includes Claude Code writing the firmware/control code.
**Finding:** Firmware and control have a compiler, tests and a millisecond feedback loop — the
exact conditions that make coding agents work. It is the mechanical side that needs the human
gate, not the software side.
**Consequence:** Do not apply mechanical-grade caution to the code layer. It can be end-to-end
automated once the topology and BOM are fixed. Not yet built.
**Confidence:** high

### [2026-08-25] Novice intake: never ask a robotics question, derive it
**Type:** breakthrough
**Context:** App must serve people with no robotics background — no DOF, no ROS, no motors,
no sensors, no units.
**Finding:** Every technical field can be derived from a question about the person's own world.
`payload_kg` <- "what does it pick up?" -> everyday-object table. `reach_m` <- "how big is the
area?" -> everyday-space table. Capabilities <- their own sentence. DOF, archetype, modules and
actuator class are **never asked and never shown**.
**Consequence:** `reference.py` (everyday objects/spaces -> mass and size ranges) and
`dialogue.py` (guided intake). A table rather than LLM estimation on purpose: auditable,
identical across runs, human-correctable. An LLM guessing "small box" differently each run would
make the same request produce different machines.
**Confidence:** high

### [2026-08-25] Ask only when the uncertainty crosses a decision boundary
**Type:** breakthrough
**Context:** How to keep a novice conversation to 3-5 questions instead of a 12-field form.
**Finding:** Every derived quantity is a **range**, and a follow-up is warranted only when that
range straddles a boundary where the machine actually changes (an actuator class, an archetype
envelope). "Coffee mug" = 0.25-0.45 kg, entirely inside one motor class -> never ask again.
"Machined part" = 0.1-3.0 kg, crossing three classes -> ask exactly one disambiguating question.
**Consequence:** Measured in `demo_novice.py`: 4 questions for a shop owner, 5 when the object
was ambiguous, **3** for a companion robot that handles nothing. Generalises to every future
field — the question to ask is never "what else could we collect" but "what would change the
answer".
**Confidence:** high

### [2026-08-25] Confirm in the customer's units, not ours
**Type:** decision
**Finding:** The confirmation originally read "0.25-0.45 kg". Someone who answered "coffee mug"
has no way to judge that number, and showing it invites an argument they cannot win.
**Consequence:** Confirmation is now "about as heavy as a coffee mug" — no units anywhere in the
customer-facing summary. Derived numbers live in `Requirements.assumptions` for the engineer.
Enforced by a test asserting no units appear in `summary()`.
**Confidence:** high

### [2026-08-25] Every customer-visible failure is translated to a choice
**Type:** decision
**Finding:** "no tier could be configured from the current catalog" tells a shop owner nothing
they can act on.
**Consequence:** `plain_failure()` maps internal errors to a decision the person can make:
"The parts we stock aren't strong enough for something this heavy at this distance. Two options:
handle a lighter item, or work across a smaller area." Falls back to a neutral sentence rather
than leaking the raw message. Tested to assert no internal vocabulary survives translation.
**Confidence:** high

### [2026-08-25] Web app: the output must hold the same no-jargon line as the intake
**Type:** decision
**Context:** Built the customer-facing UI (`serve.py` + `web/index.html`, stdlib only, no deps).
**Finding:** Careful novice intake is wasted if the *result* screen says
"3 DOF: [base] -> shoulder -> upper_link -> elbow" — that is exactly the vocabulary the whole
conversation avoided.
**Consequence:** `explain.py` renders every output in plain English: "A robot arm with 3 joints,
bolted to a bench, with a two-finger gripper on the end." Engineering detail (payload, reach,
DOF, torque, topology tree, assumptions, unauthored modules) lives behind a collapsed
"Engineering detail" disclosure — present for the team, invisible to the customer.
**Confidence:** high

### [2026-08-25] Zero-dependency stack for the local tool
**Type:** decision
**Finding:** stdlib `http.server` + one HTML file, no npm, no framework, no install.
**Consequence:** Runs with `python3 serve.py` on any machine with Python. Correct for a local
internal tool; revisit only if/when it goes public (open question #9).
**Confidence:** high


### [2026-08-27] Per-joint torque sizing — the wrist stops buying a shoulder actuator
**Type:** breakthrough
**Context:** Logged since the first pipeline session: every joint was sized at the
worst-case shoulder torque, because there was no load path to size against. The
topology tree has been there since PIVOT 2, so the load path was already in the data
— nothing was reading it.
**Finding:** `chain_loads()` walks the mounting tree and computes, per joint, the mass
and moment arm of everything distal to it. Actuator selection is then per joint and
regrouped into BOM lines. On a 3-joint arm the required torque falls **46.4 → 14.6 →
1.2 Nm** (0.7 m reach, 0.35 kg payload) — a 39× spread the old model flattened to one
number.
**Consequence:** Actuator spend on a 3-joint arm drops **~50%** against the same load
model and the same catalog (measured: $2,205 vs $4,440, seed ladder). That is the
number a customer compares against a competitor, so it was the most expensive
approximation in the product.
**Confidence:** high — arithmetic, covered by 8 new tests.

### [2026-08-27] The old sizing model under-modelled arm mass by ~4x
**Type:** data
**Context:** Found while implementing the load path — the shoulder figure went *up*, not
down, which was not the expected direction.
**Finding:** The old `estimate_link_mass()` counted extrusion only: 0.84 kg of structure
for a 0.7 m arm. The real distal mass — authored joint, link and effector module masses
plus extrusion — is **3.81 kg**. Structure now dominates payload in the static term by
about 5:1 on a light-payload arm. Shoulder requirement rose 14.8 → 46.4 Nm.
**Consequence:** Two effects ran in opposite directions in one change: distal joints got
much smaller (the intended win), the shoulder got substantially bigger (a correction of
a real error). The net is still ~50% off actuator cost, but the honest headline is
*correct differentiation*, not *cheaper*. Actuator mass is still nominal and is not
re-checked against the part finally chosen — that circularity remains open and is stated
in the output assumptions rather than hidden.
**Confidence:** high for the arithmetic; **medium** for the absolute figure, because
module `mass_kg` values in `modules.py` are authored placeholders. Real numbers arrive
with real modules.

### [2026-08-27] Seed catalog could not build a 0.7 m arm; ladder extended to 5 classes
**Type:** data
**Context:** With honest distal mass, the 22 Nm top of the seed ladder was exceeded by
the shoulder of a *mug-picking* robot, and `build()` began raising InfeasibleError on the
demo path.
**Finding:** Added `act.micro` (0.55 Nm) and `act.xlarge` (75 Nm) so the placeholder ladder
spans **0.55–75 Nm across 5 classes**, as TODO already required for tier differentiation.
Still `verified:false`, still PLACEHOLDER part numbers — nothing became quotable.
**Data:** a 1.0 m / 2.0 kg arm needs **128.3 Nm** at the shoulder and is still infeasible
on the seed ladder. A real catalog needs a rung above 75 Nm, or a gearbox stage, to quote
a metre-class arm.
**Consequence:** Confirms open question #12 empirically rather than by argument: torque
range, not part count, is what the catalog has to span. The 5-rung ladder is coarse enough
that a 0.45 m and a 0.7 m arm select the identical actuator set — so it sizes tiers, it
does not yet differentiate designs.
**Confidence:** high for the torque figures; the prices are invented and must not be quoted.

### [2026-08-27] A per-joint BOM requires a per-joint gate
**Type:** bottleneck
**Context:** Found immediately after per-joint selection landed — the L4 torque check read
`actuators[0]` and compared it to the single governing figure.
**Finding:** With one actuator per joint that check verifies the *largest* actuator and
silently skips every distal one — precisely the joints that had just been made smaller.
A downsizing change had made its own verification blind.
**Consequence:** `_torque_margin_checks()` now emits one check per joint, carries the joint
label in the repair signal (`{"action": "upsize_actuator", "joint": ..., "need_nm": ...}`),
and returns **WARN, not PASS**, for axes whose sizing basis is unmodelled. Test
`test_every_joint_is_torque_checked_not_just_the_largest` sabotages the *smallest*
actuator specifically, because that is the failure a single check cannot see.
**General lesson worth keeping:** when an artifact becomes finer-grained, its gate must
become finer-grained in the same commit, or the change ships with weaker verification than
what it replaced.
**Confidence:** high

### [2026-08-27] Non-cantilever axes return `None`, not a number
**Type:** decision
**Context:** Gantry axes and drive wheels are actuated DOF but are not gravity cantilevers.
**Finding:** Applying the arm formula to a drive wheel would produce a confident, wrong
number that reads exactly like a real one. `JointLoad.torque` is therefore `None` with
`sizing_basis="unmodelled"`; callers must handle it.
**Consequence:** Those axes fall back to the governing cantilever torque for part selection
— conservative, not correct — and that substitution is stated in the tier notes, the BOM
document and the L4 gate. Consistent with the standing rule that a skipped check is never
a pass. Traction, gradient, rolling resistance and lead-screw efficiency remain unmodelled.
**Confidence:** high

### [2026-08-27] `demo.py` was exercising the legacy path
**Type:** bottleneck
**Finding:** `demo.py` built `Requirements` without capabilities, so `topo` was `None` and
the demo ran the archetype-only branch — not the branch the guided intake and the web app
actually use. The flagship demo was validating code the product does not run.
**Consequence:** Demo now passes capabilities. Both branches still exist and both are
tested; the archetype-only branch is legacy and should be deleted once nothing constructs
`Requirements` without capabilities.
**Confidence:** high


### [2026-08-28] First archetype chosen: wheeled base with servo-driven articulation
**Type:** decision
**Context:** Answer to open questions #4/#13, from the team: *"wheel robotics, but has much
servos."*
**Finding:** The first archetype is a **wheeled mobile base carrying servo-driven joints** —
`base.diffdrive` + a revolute chain, which `synthesize()` already composes. The module set to
author first is therefore `base.diffdrive`, `joint.revolute`, `link.rigid`, `panel.control`,
not the `base.fixed` arm set previously assumed in TODO.
**Consequence:** Closes #4/#13 and re-prioritises L3. It also promoted "non-cantilever axes are
unmodelled" from a nice-to-have to the critical path, because the chosen archetype's *primary*
axes were the unmodelled ones.
**Confidence:** high

### [2026-08-28] Sizing a wheel with the arm formula put a $1,480 actuator on a rover
**Type:** bottleneck
**Context:** Found immediately on running the newly-chosen archetype through `build()`.
**Finding:** `drive_base` came back `sizing_basis="unmodelled"` and fell back to the governing
cantilever torque — so the **most expensive line in a wheeled robot's BOM was chosen by a
calculation that did not apply to it**: `act.xlarge`, 75 Nm, $1,480. Real requirement by
traction: **0.97 Nm**, met by a $95 gearmotor. A ~77x over-spec on that line.
**Consequence:** `drive_torque()` models rolling resistance + grade + acceleration at the wheel
radius, and returns the friction ceiling alongside. Wheeled bases are now sized, not guessed.
**Confidence:** high — but the fallback was *conservative*, so it produced expensive quotes,
never unsafe ones. Worth noting the failure mode direction: unmodelled + conservative fallback
loses deals quietly rather than breaking machines loudly.

### [2026-08-28] Wheeled bases are speed-limited; arms are torque-limited
**Type:** data
**Context:** The drive axis passed its torque check at **6.19x** margin and still could not hit
the 0.5 m/s travel speed — a 100 mm wheel at 0.5 m/s needs 10.0 rad/s, and the entire joint-servo
ladder tops out at 9.4 rad/s.
**Finding:** High-ratio joint servos are torque-rich and speed-poor; a drive axis is the exact
opposite problem. **A servo ladder built for joints is not a drive-motor ladder** — they are
different part classes, and no amount of catalog depth in joint servos fixes it.
**Consequence:** `Catalog.query()` gained `min_speed_rad_s`, and drive axes now select on torque
*and* speed. Added `act.drive` (3.5 Nm / 16.7 rad/s / 30:1) as a placeholder gearmotor class.
Direct implication for the real catalog: **the team needs two distinct actuator families**, and
"how many actuator classes" (open q #12) is really two questions.
**Confidence:** high for the physics; the specific ladder is placeholder.

### [2026-08-28] Traction failure and torque failure have opposite repairs
**Type:** breakthrough
**Finding:** Past the friction ceiling the wheels slip and a bigger motor changes nothing — the
fix is grip, wheel size, or weight over the driven axle. A gate that reported this as a torque
shortfall would send the bounded-repair loop to spend all three attempts on the wrong knob and
then escalate with a wrong diagnosis attached.
**Consequence:** `_drive_checks()` emits `{"action": "increase_traction"}` and
`{"action": "regear_drive"}` as distinct signals from `upsize_actuator`. Test
`test_traction_failure_does_not_ask_for_a_bigger_motor` pins it.
**General lesson:** the repair vocabulary has to be as fine-grained as the physics. Collapsing
two failure modes into one signal is worse than having no signal, because the loop acts on it.
**Confidence:** high

### [2026-08-28] The BOM was a fixed list, so it described a different machine than the design
**Type:** bottleneck
**Context:** Found while checking the wheeled archetype's parts list.
**Finding:** `build()` appended a hardcoded five parts to every configuration. A patrol robot
that cannot grasp was quoted **a gripper and four limit switches it has no use for**, while the
**wheels and battery its drive base genuinely declares** were dropped silently — `catalog.get()`
raised `KeyError` and the code passed. The topology said one thing and the BOM said another.
**Consequence:** `_support_lines()` derives every non-actuator part from `topo.consumes_kinds`,
picks the end effector from the effector module actually placed (so a vacuum robot is never
quoted a parallel gripper), and reports unfillable kinds as a visible tier note instead of a
silent omission. Added placeholder `wheel.100mm` and `batt.24v`; `PartKind` gained `WHEEL` and
`BATTERY`.
**Worth keeping:** the schema guardrail worked exactly as designed — `PartKind` *rejected* the
new kinds at load rather than accepting junk. The hole was in the catalog, not the type system.
**Confidence:** high

### [2026-08-28] "Whatever is in stock online" is compatible with the no-runtime-research rule
**Type:** decision
**Context:** Team's answer to open question #5, *"doesn't matter, whatever is online in stock,
we can buy and get delivered."*
**Finding:** This removes the constraint that the catalog mirror a physical inventory — it does
**not** authorise part lookup inside the quote path. Curation stays offline, once, by a human;
`verified=true` still requires a person checking the vendor page. The locked constraint was
always about *runtime* research (dead links, out-of-stock, invented part numbers, a different
BOM every run), not about ownership of stock.
**Consequence:** The catalog can be built from commonly-available parts rather than a private
stock list, which makes it easier, not different. Open q #5 is answered; **#12 is not** — the
torque and speed *ranges* still have to be chosen, and the wheeled archetype needs two actuator
families.
**Confidence:** high


### [2026-08-28] Cost target set: under $3,000 in parts, sells under $10,000
**Type:** decision
**Context:** From the team, answering what the machines are for: *"targeting a full robot to
cost less than 3000 and be sold within 10k."*
**Finding:** These are ceilings on the **product**, not on the customer's wallet, so they belong
in code rather than in a person's head. `MAX_PARTS_COST_USD = 3000` and
`MAX_SALE_PRICE_USD = 10000` in `config.py`, gated in L4 as `cost_target` with a
`downgrade_tier` repair so the loop walks to a cheaper tier before giving up. `serve.py`
applies the same ceiling — it calls `build()` directly and so was not covered by the pipeline's
gate, and would have quoted a machine we had decided not to make.
**Consequence:** The intake's budget menu was offering "$15,000 - $50,000" and "over $50,000"
for machines that top out near $10,000. Now bounded to under $3k / $3-6k / $6-10k. Inviting a
request we will then refuse wastes the customer's time before ours.
**Confidence:** high

### [2026-08-28] What $3,000 in parts actually buys
**Type:** data
**Context:** Measured immediately against the new ceiling, on placeholder prices.
**Finding:** The ceiling lands the buildable envelope at roughly **0.35 m reach and 0.5 kg
payload** for an arm. At 0.45 m / 0.8 kg the shoulder jumps an actuator class to `act.xlarge`
and that **single part is $1,480 — about half the entire parts budget** — putting the machine
at $3,104 and over the line. A wheeled patrol robot with no arm comes in at $766.
**Consequence:** The shoulder actuator is the cost driver for every machine with an arm, and it
is the one part where catalog choice moves the price envelope most. Worth knowing before anyone
spends time optimising anything else.
**Confidence:** medium — the ratio is structural and will hold, the absolute numbers are
placeholder prices and will move.

### [2026-08-28] Course correction: this is a design-assist app for ordinary people
**Type:** decision — supersedes part of the framing in `CLAUDE.md`
**Context:** Direct feedback from the team after I pushed on drive-motor speed bands, floor
friction and skid-steer scrub: *"this is too deep, ur focusing on the wrong parts... this app is
just to help normal people design robots, without all the complex research and ai and coding and
cadding... ur getting into too much details and asking things might not even happen yet."*
**Finding:** The product is an app that **streamlines and assists designers** — it lets ordinary
people get into robotics without doing the research, coding or CAD themselves. It is not an
internal quoting tool for an industrial robotics team with a stocked shop floor, which is the
frame `CLAUDE.md` is written in and which I was reasoning from.
**Consequence:** Depth is not free — modelling carpet rolling resistance and turning scrub costs
sessions and answers questions nobody has asked yet. **Default to the simplest model that is
honest, and add depth only when a real request needs it.** The gantry lead-screw axis and
skid-steer scrub are logged and parked rather than built.
**Rejected as a result:** asking the team to specify drive-motor speed bands, floor surface and
grade. Those are engineering parameters for a machine class that does not have a customer yet.
**Open — needs a human call:** `CLAUDE.md` still describes a pre-sales concepting system for a
human robotics team and an industrial buyer. It governs every session, and it now conflicts with
this entry. Someone should reconcile them; I have not edited it unilaterally.
**Confidence:** high on the correction; medium on how far the reframe reaches, because the
"human review gate before anything reaches a customer" and "curated catalog only" constraints
still look right under either framing.


### [2026-08-28] `CLAUDE.md` reframed to match the product
**Type:** decision — supersedes the framing in the previous `CLAUDE.md`
**Context:** The governing doc described a pre-sales concepting tool for an industrial robotics
team and an industrial buyer. That is what I kept reasoning from, and it is why I went deep on
drive-motor speed bands and floor friction.
**Finding:** Rewritten around what the app actually is: **an app that helps ordinary people
design robots.** Added **RULE 0 — simplest honest model, add depth only when a real request
needs it**, including "do not ask the team to specify engineering parameters for a machine class
that has no customer". Added the $3,000 / $10,000 ceiling as a stated product constraint.
**Kept unchanged** (right under either framing): catalog discipline and never inventing a part
number, human-only `verified=true`, kinematic-only simulation, validation order, a skipped check
is never a pass, the swappable CAD backend, the design record, and the human gate before
anything is presented as firm.
**Judgement calls made, worth a human glance:** (1) the human gate is now phrased as "before
anything is presented as a firm quote" rather than "before anything reaches a customer";
(2) "no robotics vocabulary in customer-facing text" was promoted from a note into the locked
constraints, since it matters more for a novice audience than it did for an industrial one.
**Consequence:** Original preserved at `docs/CLAUDE-v1-presales-framing.md` — this project is
not under git, so an overwrite would have been unrecoverable.
**Confidence:** high on the reframe; medium on the two judgement calls above.

---

## 4. Traps and things to deliberately avoid

### [2026-08-25] The "look / appearance" input is a trap
**Type:** decision
**Finding:** Letting users describe appearance creates aesthetic promises the team must hit at
the quoted price, and a glossy render implies a finish that extrusion-and-brackets reality will
not match.
**Consequence:** Make the video deliberately **engineering-honest** rather than beautiful —
CAD-shaded, dimension callouts, reach-envelope overlay, cycle-time counter, visible
"concept simulation" label. More credible to an industrial buyer, protects against expectation
gaps, and is consistent with the founding instinct of *not shipping fake AI videos*. Constrain
styling to what is manufacturable: extrusion, sheet metal, printed covers.
**Confidence:** high

### [2026-08-25] Do not emit CAD detail the build team must honor
**Type:** decision
**Finding:** Concept-level CAD only. If the app emits detailed geometry, the team is implicitly
bound to it and loses design freedom.
**Consequence:** State the concept-level scope inside the delivered artifact itself.
**Confidence:** medium

### [2026-08-25] Platform dependency risk
**Type:** open-question
**Finding:** Building on Fusion/KiCad MCP means being an app on someone else's API; Autodesk
will ship its own AI features. Defensibility cannot be "we call the CAD API."
**Consequence:** The moat must be the curated catalog + archetype library + robotics-specific
validation, not the CAD integration.
**Confidence:** medium

---

## 5. Market reality checks

### [2026-08-25] The original market was small and skeptical
**Type:** bottleneck
**Finding:** ~30M software developers vs. maybe low hundreds of thousands of robot hardware
designers worldwide. Hardware buyers are conservative — mistakes cost money and can injure
people. And for most robotics companies mechanical design is *not* the bottleneck; policies,
reliability, and data are.
**Consequence:** Reinforced the pivot. Post-pivot we sell robots (large ticket, existing
demand) rather than design software (small market, high skepticism).
**Confidence:** high

### [2026-08-25] Competitive landscape
**Type:** data
**Finding:** Policy-side players (Physical Intelligence, Skild) are not competitors — different
layer. CAD-side: Zoo/KittyCAD text-to-CAD, PhysicsX, nTop, and Autodesk's own roadmap.
**Consequence:** Position as robotics-specific pre-sales concepting, not as a CAD tool.
**Confidence:** medium — needs a proper landscape scan.

---

## 6. Open questions (must answer)

| # | Question | Why it matters | Status |
|---|---|---|---|
| 1 | How many quotes/month does the team produce today? | 5 quotes × 8h = nice-to-have. 50 = a business. This is the riskiest assumption in the whole plan. | **open** |
| 2 | How long does one quote take end-to-end today? | Baseline for the ROI claim | open |
| 3 | What is the current win rate? | Determines value of quoting more vs. quoting better | open |
| 4 | Which task family do we already build best? | Determines the first archetype | **answered 2026-08-27: wheeled base + servo articulation** |
| 5 | Which components does the team already stock/trust? | Seeds the curated catalog | **answered 2026-08-27: no fixed stock — anything purchasable online. Offline curation unchanged** |
| 6 | Do we have existing parametric CAD we can reuse? | Likely ~60% of archetype work is already done | open |
| 7 | How do we gate inbound so free quoting doesn't flood us with tire-kickers? | Quality of funnel | open |
| 8 | Acceptable competitive leakage from showing our design approach publicly? | Judged mild, worth it | open |
| 9 | Internal tool only, or public self-serve funnel? | Determines the CAD backend decision (Fusion farm vs Onshape vs headless kernel) and therefore months of code | **open — blocking L3** |
| 10 | How many distinct electronic components does the team actually reuse? | Sizes the STEP normalization effort (~10-20 min each, once) | open |
| 11 | Do three control-panel tiers actually cover our historical builds? | If not, tier approach fails and a packing solver is needed sooner | open |
| 12 | How many actuator classes span our real torque range — **and separately, what drive-motor speed range?** Two families, not one (2026-08-28) | Fewer than ~5 and good/better/best tiers collapse into one. **Measured 2026-08-27:** the range that matters is 1.2-128 Nm across the arms we tested; a 5-rung placeholder ladder (0.55-75 Nm) still cannot quote a 1.0 m / 2.0 kg arm | **open — blocks tiering** |
| 14 | What is the team's real observed utilisation vs theoretical cycle time? | `UTILISATION = 0.65` in explain.py is a guess and it sets every throughput claim we make | open |
| 13 | Which archetype template gets authored first? | Blocks all of L3; everything else is built and waiting | **answered 2026-08-27: `base.diffdrive`, `joint.revolute`, `link.rigid`, `panel.control`** |

---

## 7. v1 scope (agreed)

1. **One** task family the team already builds well. Not general robots.
2. Curated component catalog — hand-built, real prices/specs. **Do this first.**
3. 2–3 parametric archetype models in Fusion.
4. LLM layer: requirements extraction → archetype pick → sizing → BOM.
5. Kinematic sim + rendered clip with engineering overlays.
6. **Human review gate before anything reaches a customer.** At least for the first year.
   Engineer spends 15 min checking instead of 8h building the quote — still ~30× win,
   with none of the risk.

---

## 8. Session index

| Date | Topic | Outcome |
|---|---|---|
| 2026-08-25 | Idea evaluation: text→robot autonomous pipeline | Rejected as product; timing thesis kept |
| 2026-08-25 | Vision-based closed-loop feedback | Rejected as primary loop; telemetry + sysid deferred to later |
| 2026-08-25 | Pivot to BOM + concept simulation for pre-sales | **Adopted.** v1 scope defined |
| 2026-08-25 | Repo bootstrap: `log.md`, `CLAUDE.md` | Done |
| 2026-08-25 | Progress checkpoint: `TODO.md` written with status, next steps and blocking decisions | Safe to pause here |
| 2026-08-25 | Web app: stdlib server + single-page UI, plain-language result screen, engineering detail behind a disclosure. 66 tests. Fixed: theoretical throughput claim | Demoable to a non-technical person today |
| 2026-08-25 | Novice guided intake: everyday-object units, boundary-driven questioning, plain-language failures. 65 tests. Fixed: mobile-only gating, raw-sentence echo | 3-5 questions, zero robotics vocabulary |
| 2026-08-25 | PIVOT 2: general topology synthesis (capabilities -> modules -> tree). 57 tests. Found+fixed: chain-vs-tree, uncommanded parts | Handles arbitrary robot descriptions; module library is now the asset |
| 2026-08-25 | Pipeline scaffolded L0-L5, 45 tests green, runs on NullBackend without Fusion. Found+fixed: tier collapse, reach-vs-span. Logged: per-joint over-sizing | Code complete; blocked on catalog + templates (content, not code) |
| 2026-08-28 | `CLAUDE.md` rewritten around the real product; RULE 0 (simplest honest model) added; original kept at `docs/CLAUDE-v1-presales-framing.md` | Governing doc no longer pulls toward industrial quoting |
| 2026-08-28 | Cost target wired in ($3k parts / $10k sale) as an L4 gate and in the web app; budget menu bounded to what we sell. 87 tests. **Course correction from the team: stop going deep — this is a design-assist app for ordinary people, not an industrial quoting tool.** Data: $3k buys ~0.35 m reach at 0.5 kg; the shoulder actuator is ~half the parts budget | Scope reset; `CLAUDE.md` framing now needs reconciling |
| 2026-08-28 | Wheeled archetype made real: traction sizing, speed as a selection constraint, BOM derived from topology. 85 tests. Found+fixed: $1,480 actuator on a rover (77x over-spec), 2 wheels/1 motor, gripper on a robot that can't grasp, wheels+battery silently dropped. Data: drive axes are speed-limited not torque-limited | Wheeled + servo-arm robots now reach `awaiting_human_review` with no blocking failures |
| 2026-08-27 | Per-joint torque sizing: load path from the topology tree, per-joint actuator selection, per-joint L4 gate. 74 tests. Found+fixed: old mass model under-counted structure ~4x; per-joint BOM had a single-joint gate; demo.py ran the legacy path. Data: ~50% actuator cost, 46/15/1.2 Nm spread | Actuators now differ per joint; catalog ladder extended to 5 classes |
| 2026-08-25 | Layered system plan L0-L5 | **Adopted.** Spec in `docs/architecture.md`. Rejected: runtime part research, STL download, LLM panel packing. Adopted: panel tiers, screenshot gate, review-gate data capture. Flagged: Fusion cannot be production backend (open q #9) |
| 2026-08-28 | First end-to-end user test (browser + API + edge cases). Found: web app bypasses the pipeline/L4/record/human gate and fakes `verified`; drive gearmotor picked for an arm elbow; result screen has no BOM and no simulation; confirm-sentence grammar; unguarded `json.loads`. Data: only one machine is reachable under the placeholder catalog | Pipeline is honest; the app that users touch is not yet wired to it |
| 2026-08-28 | Acted on the ETE findings: web app rewired onto `pipeline.run()` with the fake `verified` override removed and a labelled `--demo` flag; `ActuatorRole` added as a hard selection filter; unverified-vs-unavailable now reported distinctly. 97 tests. Lost: `runs/` cleared by an overbroad rm | The app users touch is now the pipeline; catalog verification is the only thing standing between it and a quote |
