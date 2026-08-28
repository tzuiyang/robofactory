# Fusion module build plan

**Status: not started — blocked on a Claude Code restart.** The Fusion MCP server
is up and answering on `http://127.0.0.1:27182/mcp`; the session that needs it
connected before Fusion did and cached the failure. Restart, then work this file
top to bottom.

## Objective

Replace the primitive boxes and cylinders in the exported URDF with authored
parametric geometry, so a generated design looks like a machine somebody would
build rather than a diagram. Nine modules, each a Fusion design with driven
dimensions matching the `params` already declared in `src/rstream/modules.py`.

## The seam it drops into — already built

`export/urdf.py` looks for `assets/meshes/<module_id with dots as underscores>.obj`
(or `.stl` / `.dae`). If it finds one, that link's **visual** becomes a `<mesh>`;
if not, it falls back to the primitive. So modules can be authored one at a time
and every design keeps exporting the whole way through. **Collision stays a
primitive on purpose** — mesh-vs-mesh is slow and buys nothing at concept level.

Nothing else needs changing to consume the geometry. Only the export step is missing.

## Rules that bind this work

From `~/.claude/CLAUDE.md` and `CLAUDE.md`:

- **Vendor assemblies are READ-ONLY.** `wattson_v2` and every imported goBILDA part
  must not be cut, joined, moved or re-jointed. Pin `participantBodies` to our own
  bodies on every cut and combine.
- **Archetype templates are ours** and may be edited freely — that is what this is.
- **Changing a module's parameter scheme is an architectural decision** and must be
  logged in `log.md`. Adding geometry that respects the existing scheme is not.
- Verify after every session: `rootComponent.features.count == 0`, every imported
  component has 0 sketches and only `BaseFeature`/`MoveFeature`, every body
  `isSolid == True`. Report the result.

## Order of work

Authored in the order that most improves what a customer sees. Each is a separate
Fusion design, saved as `rf_<module>`, exported to `assets/meshes/`.

| # | Module | Driven params | Why this one first |
|---|---|---|---|
| 1 | `link.rigid` | `length_m` | Appears 3x on every arm. One model fixes the most surface area. |
| 2 | `joint.revolute` | `range_rad` | The shoulder. Housing must match the actuator envelope the exporter already draws — see `_housing()`. |
| 3 | `joint.revolute.inline` | `range_rad` | Elbow and wrist. Likely a variant of #2 with a different mounting face. |
| 4 | `effector.gripper` | — | The end of the arm and the thing people look at. |
| 5 | `base.fixed` | — | Bolted base plate + column. |
| 6 | `base.diffdrive` | `track_width_m`, `wheel_dia_m` | Chassis only; wheels stay primitives (they are catalog parts, not our design). |
| 7 | `panel.control` | S/M/L tiers | Also unblocks `panel_envelope()` on the Fusion backend. |
| 8 | `head.sensor` | `height_m` | Camera/mic/speaker shell. |
| 9 | `effector.vacuum` | — | Only needed for the laundry/sheet archetype. |

## Per-module requirements

Every module must satisfy all of these before its mesh is exported:

1. **Origin at the mounting face centre**, +X along the direction its child mounts,
   +Z up. This matches `Frame.child_at` / `child_along` in `modules.py` exactly — if
   the CAD origin disagrees with the frame, the URDF will assemble wrong and no test
   will catch it.
2. **Driven dimensions named after the `params` keys**, so a user parameter of the
   same name drives the model (`length_m` in metres, or a `length_mm` = `length_m` × 1000
   expression — state which in the design's notes).
3. **Fastener pattern modelled**, not implied. Edge distance and head clearance are
   what make it look built rather than drawn.
4. **Wall thickness and material stated** in the design's description field.
5. Exported as `.obj` (preferred — carries material, small, universally read) at
   **metres**, triangle count under ~20k. Fusion exports STL in mm by default; set
   the unit or the robot arrives 1000x too big.

## Export step to write

`cad/fusion.py` currently raises `NotImplementedError` for
`instantiate_archetype`, `place_panel`, `place_parts` and export. Only one new
method is needed for this work:

```python
def export_module_mesh(self, module_id: str, params: dict, out_dir: Path) -> Path:
    """Open the authored design for `module_id`, drive its parameters, export a
    mesh. Refuses any document the backend did not create — the generated-script
    guard already in this file must not be removed to make an export work."""
```

Note it exports **per module**, not per design: `link.rigid` at 0.175 m and at
0.25 m are two meshes. Cache by `(module_id, rounded params)` so a repeated size
is exported once.

## Open question for the team

The catalog rule says **STEP, not STL** for component geometry — because a mesh has
no planar face to mate against. That rule is about *catalog parts used for mating*.
URDF visual meshes are a render artifact and cannot be STEP; no simulator reads it.
These are different uses of the word "geometry" and the rule is not being broken,
but the distinction should be written down before someone reads the two files and
concludes otherwise. **Proposed:** STEP stays authoritative for mating and panel
fit; `.obj` is a derived render artifact, regenerated from it, never hand-edited.

## What "done" looks like

`python3 tools/render.py docs/img` produces an image where the arm reads as a
machine — visible fasteners, real proportions, a gripper with fingers — and
`check_urdf` still passes on all four topology shapes.
