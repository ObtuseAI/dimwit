# Dimwit → Marble (World Labs) Environment Ingest

Bring a **Marble** (World Labs, `marble.worldlabs.ai`) AI-generated 3D world into **WANEFALL** as a playable
Unreal Engine 5.8 environment — cleaned, correctly oriented, correctly scaled, Nanite, solid collision, in a
saveable test map. Claude orchestrates; Dimwit executes the Blender + UE stages; both validate live.

---

## TL;DR

```
# After you (the human) have generated + exported a world from Marble to a local file:
cd C:\Users\developer\Documents\Dimwit
python scripts/pipeline/run_pipeline.py marble_ingest src="C:\path\to\marble_export.glb" ^
    ref_dim_meters=2.4 ref_axis=z ^
    license="World Labs <plan> — commercial rights asserted by operator"
```

`ref_dim_meters` = the real-world size of some feature you can measure in the world (a door ~2.1 m, a car ~4.5 m
long, a storey ~3 m). Marble has **no real-world scale**, so a playable env *requires* this or it refuses to run
(pass `allow_unscaled=1` only for a non-walkable backdrop).

---

## The human-only boundary (Dimwit/Claude CANNOT do these for you)

These steps require **your** account, **your** payment, and a file **you** download. They are deliberately outside
the automation — the assistant will not create accounts, subscribe, or download files on your behalf:

1. **Account** — create / sign in at `marble.worldlabs.ai`.
2. **Plan / commercial rights** — to *ship* WANEFALL you need the tier that grants **commercial rights** AND
   **mesh/splat export** (Pro / commercial tier; the free & standard tiers grant no commercial rights, and export
   itself is a **paid** feature). PLY/GLB export and the High-Quality mesh are paid; the HQ mesh is generated
   offline (can take ~1 hr).
3. **Generate** the world (text/image prompt) in Marble.
4. **Export & download** one of:
   - **Collider Mesh GLB** (~100–200k tris) — physics/collision geometry, low visual detail.
   - **High-Quality Mesh GLB** (~600k–1M tris) — production visual; **best single-file playable path for UE 5.8**.
   - **Splat** (`.ply` / `.spz`) — visual-only Gaussian splat, **no collision**.
5. Save the file somewhere on disk and note its path.

Once the file exists on disk, **everything below is automated.**

---

## What kind of export should I pick?

| Export | Ext | What it is | UE 5.8 playable? |
|---|---|---|---|
| **High-Quality Mesh** | `.glb` | Full visual mesh (~0.6–1M tris) | ✅ **Best** — Nanite static mesh + complex collision. Recommended. |
| **Collider Mesh** | `.glb` | Low-detail physics shell | ✅ Playable but visually plain (use as collision under splat visuals). |
| **Splat** | `.ply` / `.spz` | Gaussian-splat visuals, no geometry | ⚠️ **BLOCKED on 5.8** — no confirmed Gaussian-splat plugin build for 5.8 (Volinga 5.3–5.6, NanoGS 5.6+, Postshot 5.2). Splat-only has **no collision**. |

**Recommendation: export the High-Quality Mesh GLB.** It is the only fully-supported, single-file, walkable path on
UE 5.8. Splats are tracked but intentionally fail-closed (recorded as BLOCKED, never a fake pass) until a
5.8-compatible splat plugin is confirmed.

---

## The pipeline (what Dimwit does, fail-closed at every step)

```
Stage 0  INTAKE GATE   file exists / non-empty / extension-whitelisted / magic-byte sniff.
                       No file → BLOCKED ("generate + export in Marble first"). Never fabricates geometry.
Stage 1  ROUTE         auto-detect kind from the bytes: collider|hq GLB  vs  splat PLY/SPZ (overridable: kind=).
                       splat with no paired collider → flagged not-playable (no collision).
Stage 2  BLENDER       blender_scripts/marble_blender_ingest.py (headless):
                         OpenCV → Z-up axis fix (+ bake), weld/cleanup/normals, scale calibration against
                         ref_dim_meters, decimate to a UE-sane tri budget, triangulate, UV/vertex-color resolve,
                         export a clean GLB to artifacts/marble_staging/.
Stage 3  UE 5.8        scripts/ue/ue_marble_import.py (headless, Interchange):
                         import as StaticMesh → enable Nanite (judged vs SOURCE tris) → Collision Complexity =
                         UseComplexAsSimple → build a neutral test map (mesh@origin + PlayerStart + Directional +
                         Sky + manual-exposure PostProcessVolume + GameModeBase) → save the map.
```

### Validators (V1–V11, hash-chained, fail-closed — a check may FAIL but never silently PASS)

| | Check |
|---|---|
| V1 | intake (stage 0) |
| V2 | axis fixed to Z-up |
| V3 | mesh non-empty / welded (≥ 5k tris) |
| V4 | scale calibrated (required for a playable mesh env) |
| V5 | normals / cleanup ok |
| V6 | tri budget within UE-sane range (5k – 1.5M) |
| V7 | textures / vertex-color resolved |
| V8 | **Nanite enabled — judged against the SOURCE tri count, never the low-poly fallback** |
| V9 | collision present (RED if splat-only with no collider) |
| V10 | test map saved + ≥1 PlayerStart |
| V11 | **optics readability** — live PIE capture (reject white/black/rotated/disfigured/uniform-albedo). *Deferred to a live capture; recorded as pending, not a silent pass.* |

**Provenance is fail-closed:** you must assert a commercial-tier license via `license="..."` or the artifact is
**REJECTED** (no silent promotion of legally-unusable assets). Autonomous ceiling = `PROMOTED_TO_REVIEW`; promoting
into the active slice is always operator-gated.

---

## Arguments

| Arg | Required | Meaning |
|---|---|---|
| `src=` | ✅ | Path to the Marble export file (`.glb` / `.gltf` / `.ply` / `.spz`). |
| `license=` | ✅ (to promote) | Operator assertion of commercial rights, e.g. `"World Labs Pro — commercial"`. Empty → REJECTED. |
| `ref_dim_meters=` | ✅ for playable mesh | Real-world size of a measurable feature (door ≈ 2.1, storey ≈ 3, car ≈ 4.5). |
| `ref_axis=` | optional | Which axis `ref_dim_meters` measures: `x`\|`y`\|`z` (default `z`). |
| `kind=` | optional | Override route: `hq`\|`collider` (GLB sub-kind the bytes can't distinguish; default `hq`). |
| `allow_unscaled=1` | optional | Accept arbitrary scale (non-walkable backdrop only; **not** recommended for a playable env). |
| `playable=0` | optional | Mark as a non-walkable backdrop (relaxes the scale gate). |
| `target_tris=` | optional | Decimation budget (default 1.5M). Repair tightens this automatically on a V6/V8 fail. |
| `asset_name=` | optional | StaticMesh name (default `SM_Marble_<filestem>`). |
| `dest=` | optional | Content folder (default `/Game/Wanefall/Imported/Marble`). |
| `level=` | optional | Test map path (default `/Game/Wanefall/Maps/Wanefall_Marble_<filestem>`). |

---

## Outputs

- Cleaned mesh: `artifacts/marble_staging/<asset_name>.glb`
- Imported asset: `<dest>/<asset_name>` (Nanite, UseComplexAsSimple collision)
- Test map: `<level>` (open in the editor or `-game` to walk it)
- Proof JSONs: `artifacts/marble_blender_result.json`, `artifacts/marble_ue_result.json`
- Ledger: the hash-chained pipeline ledger entry (plan → execute → QA → gate)

---

## After a run — live validation (the operating model)

Nothing is "done" until **both** Claude and the operator have seen the imported world live on the running game.
After the pipeline reaches `PROMOTED_TO_REVIEW`:

1. Open `<level>` in the UE editor (or set it as the `-game` startup map) and walk it.
2. Confirm: correct **orientation** (ground is down, not a wall), believable **scale** (you fit through doors), the
   mesh **renders** (not white/black/rotated/disfigured), and you **collide** with the floor/walls.
3. That live look is **V11 (optics)** — close it by capturing a PIE frame and eyeballing it (the per-camera
   Halo3/Fortnite grade applies here too).
4. Only the operator promotes the env into the active slice.

---

## Notes / gotchas

- **Marble axes = OpenCV** (+X left, +Y down, +Z forward) and **no real scale** → the Blender stage's axis fix +
  scale calibration are load-bearing; skipping the reference dimension gives a wrongly-sized world.
- Marble meshes are typically **unwelded** (every triangle loose) → the weld pass is required before decimation.
- **Nanite source-tris gotcha:** `get_num_triangles` on a Nanite mesh returns the *fallback*, so V8 reads the
  source count **before** Nanite is enabled.
- glTF carries an **unbaked Y-up→Z-up rotation** → the Blender stage `transform_apply`s before reading vertex Z.
- SPLAT visuals stay **BLOCKED** on 5.8 by design; the MESH track (Collider/HQ GLB) is the supported path.
