# TODO — robotics_streamline

Last updated: **2026-08-28**

Pick-up point for whoever opens this next (including future-me). Full reasoning behind every
decision is in `log.md`; the layer design is in `docs/architecture.md`.

---

## Where things stand

| Layer | State | Notes |
|---|---|---|
| L0 catalog | **real parts, unverified** | 22 orderable parts with vendor links, all `verified:false` — cannot produce a quote until a human checks them. 7 joint actuators 0.28–48 Nm, 3 drive gearmotors |
| L0 modules | **defined, no CAD** | 10 modules with typed interfaces; none have parametric templates yet |
| L1 intake | **done** | Guided novice conversation, 3–5 questions, zero robotics vocabulary |
| L2 config | **done** | Capability closure → topology → per-joint sizing (cantilever **+ traction**) → BOM **derived from topology** → tiers |
| L3 geometry | **interface done, backends blocked** | `NullBackend` works; `FusionBackend` written but needs templates |
| L4 validation | **done** | Deterministic gate (per-joint torque, **traction ceiling, drive speed**) → vision gate → bounded repair (max 3) |
| L5 present | **done** | Kinematic trajectory + BOM doc + plain-language render |
| Web app | **done** | stdlib server + single page, light/dark. Runs `pipeline.run()` — same L4 gate, record and human gate as `demo.py`. Blocks on the seed catalog by design; `--demo` walks it |

**105 tests passing.** No dependencies — stdlib only.

```bash
python3 serve.py              # the app -> blocks: no verified parts (correct)
python3 serve.py 8000 --demo  # walk the flow against placeholder parts
python3 demo_novice.py    # three novice conversations
python3 demo_general.py   # topology synthesis across robot types
python3 demo.py           # full pipeline -> BOM + trajectory
python3 -m pytest -q          # 105 tests
```

---

## Next steps, in order of leverage

### 1. Verify the catalog — ~1 hour, unblocks every quote

> **The parts are in.** As of 2026-08-28 the catalog holds 22 real, orderable parts
> with a `source_url` on every one and a `notes` field saying which numbers came off
> the vendor page and which are derived. Nothing is `verified` — that is your step,
> and until it happens *every* request is blocked. That is correct behaviour.
>
> ```
> python3 curate.py status          # the list, with links
> python3 curate.py verify act.j830 # open the link, check, type 'checked'
> ```
>
> **Check these first, they are engineering judgement not vendor figures:**
> - DYNAMIXEL rated torque is `stall / 5` (ROBOTIS publishes stall; the /5 comes from
>   their own XM540 page, where 10.6 Nm stall is listed as 2.12 Nm rated).
> - goBILDA rated torque is `stall / 3` and loaded speed is `free speed / 2`.
> - Every `keepout` value, and any mass or dimension marked UNCONFIRMED in `notes`.
>
> **The gap worth closing: nothing sits between 9 Nm and 48 Nm.** Every arm shoulder
> needs ~21 Nm and buys a $989.90 48 Nm actuator. One part in the 15–25 Nm band cuts
> ~$500 off every arm and is what makes good/better/best differ at all.
**File:** `src/rstream/catalog/data/parts.json` — edit it with `python3 curate.py`.

Start with `python3 curate.py needs`: it prints the torque and speed rungs the sizing
actually demands, per role, so you shop against real numbers rather than a guessed ladder.
Then `python3 curate.py verify <id>` walks one part and only sets `verified` when you
type `checked`.

Replace the PLACEHOLDER entries with parts the team actually stocks. Per part:

| Field | Notes |
|---|---|
| `manufacturer`, `part_number` | exactly as ordered |
| `price_usd` | current, not list |
| `dimensions` | L/W/H in **mm**; add `keepout_*_mm` for connector/airflow clearance |
| `mass_kg` | |
| `actuator` | actuators only: `rated_torque_nm`, `stall_torque_nm`, `max_speed_rad_s`, `gear_ratio` |
| `verified` | set `true` ONLY after checking against the vendor page |
| `actuator.role` | actuators only: `"joint"` (holds position) or `"drive"` (wheels). Omitted = `joint`. A wheel gearmotor tagged `joint` will be selected for an elbow |

> **Need 5+ actuator classes** spanning the torque range. With fewer, good/better/best tiers
> collapse into one (see log.md, "Tier differentiation requires catalog depth"). The seed
> ladder now has five (0.55 / 1.8 / 6 / 22 / 75 Nm rated) — enough to run, still too coarse:
> a 0.45 m and a 0.7 m arm select the identical set, and a 1.0 m / 2.0 kg arm needs 128 Nm
> at the shoulder and remains infeasible.

New part kinds the general topology now needs: `wheel`, `battery`, `speaker`, `microphone`,
`compute_module`, `camera`, `audio_amp`. Run `demo_general.py` — it prints exactly which kinds
are missing for each robot type.

### 2. Author the first Fusion module — biggest unlock
**Decision made 2026-08-27: wheeled base with servo articulation.** So the first module set is:

| Order | Module | `params` to drive | Why this one |
|---|---|---|---|
| 1 | `base.diffdrive` | `track_width_m`, `wheel_dia_m` | The archetype's root; wheel diameter drives both traction torque and travel speed |
| 2 | `joint.revolute` | `range_rad` | The shoulder — the governing joint on every arm |
| 3 | `link.rigid` | `length_m` | Repeats; one model covers every link |
| 4 | `panel.control` | S/M/L tiers | Unblocks `panel_envelope()` and the fit checks |

Each needs a parametric Fusion model with driven dimensions matching `params` in
`src/rstream/modules.py`, and `cad_template` set on the module.

Wire `FusionBackend.instantiate_archetype()` / `place_panel()` / `place_parts()` in
`src/rstream/cad/fusion.py` — they currently raise `NotImplementedError` on purpose, so a bad
concept cannot silently reach a customer.

**Golden rule still applies:** `wattson_v2` and every imported assembly are READ-ONLY. The
generated-script guard in `fusion.py` refuses to run against any document the backend did not
create. Do not remove it to make a script work.

### 3. Then, in rough order
- [ ] Component STEP normalization (origin at mounting-face centre, bolt pattern, keepout) —
      ~10–20 min per part, once, ~40 parts. Never at runtime.
- [ ] Control-panel tier models (S/M/L) so `panel_envelope()` works on Fusion
- [ ] Screenshot capture wired to the MCP read tool → activates the L4b vision gate
- [x] ~~Per-joint torque sizing~~ — **done 2026-08-27.** `sizing.chain_loads()` walks the
      topology tree; actuators are selected per joint and the L4 torque gate checks each
      one. ~50% off actuator cost on a 3-joint arm (log.md).
- [ ] Close the sizing circularity: distal mass uses the module's *nominal* actuator mass,
      not the part actually chosen. One re-solve pass would close it. Currently stated as
      an assumption in the output rather than fixed.
- [x] ~~Size diff-drive traction~~ — **done 2026-08-28.** `sizing.drive_torque()`; wheeled
      bases select on torque *and* speed and are gated on the friction ceiling.
- [ ] Gantry lead-screw axes are still `sizing_basis="unmodelled"` and fall back to the
      governing joint's torque. Only matters when a gantry job comes up — not the chosen
      archetype, so parked deliberately.
- [ ] Skid-steer turning scrub is not modelled. A diff-drive rotating on the spot can need
      well over the straight-line figure; currently absorbed by the 2.5x safety factor.
- [ ] `_KIND_DEFAULTS` in `config.py` maps each part kind to exactly one catalog id. Once
      the catalog holds several parts per kind this must become a constrained query like
      `_pick_actuator`, or the extra parts are unreachable.
- [ ] Link lengths sum to 1.08x the stated reach (0.55 + 0.45 + 0.08 in `topology.py`),
      so the moment arm is ~8% longer than the quoted reach. Decide which is authoritative.
- [x] ~~Orderable parts list on the result screen~~ — **done 2026-08-28.** `explain.shopping_list()`
      -> "What to order": qty, plain-English role, manufacturer, part number, price, vendor link.
      Unverified prices carry a `?`; the subtotal is withheld until the parts are verified.
- [ ] Real cycle-time video render for L5
- [ ] Firmware/control code generation — the one layer that can be fully automated (compiler +
      tests + millisecond loop). Not started.
- [ ] Review gate UI that **captures engineer diffs**, not just approve/reject — this is the
      entire data flywheel and it is cheap now, expensive to retrofit

---

## Scope note (2026-08-28)

This is an app that helps **ordinary people design robots** without doing the research, coding
or CAD themselves. It is not an internal quoting tool for an industrial robotics team. Default
to the **simplest model that is honest**; add depth only when a real request needs it. Two
items below are parked on purpose for that reason, not forgotten.

**Product ceiling: parts under $3,000, sells under $10,000.** Enforced in `config.py`
(`MAX_PARTS_COST_USD` / `MAX_SALE_PRICE_USD`), gated in L4, applied in `serve.py`, and the
intake's budget menu is bounded to match. With placeholder prices that buys roughly a
**0.35 m reach at 0.5 kg**; past that the shoulder actuator alone is half the parts budget.

`CLAUDE.md` was rewritten on 2026-08-28 to match this; the original framing is preserved at
`docs/CLAUDE-v1-presales-framing.md`.

---

## Decisions only the team can make

| # | Question | Blocks |
|---|---|---|
| 1 | How many quotes/month today, how long each, what win rate? | Whether this is a tool or a business |
| 12 | Real prices for the actuator ladder — the shoulder actuator is ~half the parts budget, so it alone sets what fits under $3,000 | The size of machine we can offer |
| 9 | Internal tool only, or public self-serve? | CAD backend choice (Fusion farm / Onshape / headless kernel) |
| 11 | Do three control-panel tiers cover our historical builds? | Whether a packing solver is needed |
| 14 | Real observed utilisation vs theoretical cycle time? | `UTILISATION = 0.65` in `explain.py` sets every throughput claim we make |

---

## Rules that must not be quietly broken

Full list in `CLAUDE.md`. The ones that bite:

- **Never invent a part number.** Not in the catalog = does not exist.
- **Never generate CAD geometry.** Instantiate authored modules; the AI sizes and selects.
- **A skipped check is never a pass.** Backends without B-rep report `SKIPPED`.
- **Price as a range, safety factor visible, never a point estimate.**
- **Nothing reaches a customer without a human review gate.**
- **No robotics vocabulary in customer-facing text** — enforced by a test.
- **Log every bottleneck, breakthrough, decision and rejected approach** in `log.md`, dated,
  with a confidence level.
