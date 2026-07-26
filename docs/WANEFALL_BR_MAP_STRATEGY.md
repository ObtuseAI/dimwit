# WANEFALL Battle-Royale Map — Production Strategy (slice vs compose)

Status: PROPOSAL for operator decision (task #34). Grounded in the proven UE5.8 Interchange env-ingest
(Marble pipeline) + the 6-repo tooling eval (config/rig_anim_backends.json v2) + the hardened intent loop.
Decision-first; nothing is built yet.

## The question
A BR map is a large playable space. Two ways to produce one:
- **SLICE** — generate ONE cohesive whole-world (real or AI) and carve the playable region out of it.
- **COMPOSE** — assemble the map from authored/procedural PARTS (a terrain base + modular POI kits + props).

## Constraints that pre-decide a lot
- WANEFALL is a **bounded arena/BR**, NOT an open-world infinite stream. So cashgenUE's headline feature
  (infinite player-tracking tile streaming) is **unneeded** — and it has **no UE5.8 build** anyway. If used
  at all, only OFFLINE as a one-shot heightmap+erosion baker → a static Nanite landscape.
- The Blender→UE5.8 **Interchange env-ingest is already proven** (Marble pipeline: Z-up axis fix +
  scale-calibrate + weld/decimate + Nanite + UseComplexAsSimple + neutral test map). Any source terminates here.
- **Gameplay quality of a BR lives in the LAYOUT** — lanes, sightlines, cover, rotations, loot paths, pacing.
  That is authored, not found. Organic/real topology is a backdrop, not a gameplay plan.
- Tooling licenses (from the eval): **Marble** = operator-only (paid tier); **BlenderGIS** = GPL (output OK)
  but its adversarial license-verify is `PENDING_ADVERSARIAL_REVERIFY` + a separate **OSM ODbL data gate**;
  **cashgenUE** = MIT but reference-only / no UE5.8. None auto-promote (all operator-gated, fail-closed).

## Recommendation: HYBRID, compose-led — "compose the gameplay skeleton, slice the backdrop"
1. **Phase 1 — COMPOSE the playable greybox (now).** Author the BR layout as a greybox: a bounded terrain
   base (hand-sculpted, or a one-shot cashgenUE/heightmap bake → static Nanite mesh) + greybox POI blockouts
   placed FOR gameplay (lanes, cover lines, rotation routes, loot density, teal-Wane identity landmarks for
   navigation). This is the gameplay-critical part and must be authored. Gate each POI and the whole-map
   readability through the hardened loop.
2. **Phase 2 — SLICE the non-playable backdrop.** Surround the playable bounds with a cohesive horizon/skybox
   environment SLICED from Marble (AI world) or BlenderGIS (real region), ingested via the proven Interchange
   path. Slicing shines here (organic cohesion) with zero gameplay-control cost, since it's beyond the bounds.

Rationale: use each tool for its strength. Composition gives full BR pacing/legibility control where it
matters; slicing gives organic atmosphere where it doesn't. Avoids betting the playable space on un-tuned
real/AI topology, and avoids the paid/real-data license exposure on the gameplay-critical layer.

## How the hardened loop gates it (utilize the entire loop)
- **Map intent contract** (author up-front, anchored before pixels): declared layout — POI count, lane count,
  rotation routes, sightline budget, identity landmarks, silhouette-reads-at-distance, palette discipline.
- **Capture stages** (live, via the UE Claude plugin): top-down layout read, player-eye lane reads, POI hero
  shots, traversal/rotation sightlines. (Per the plugin directive — a live editor evaluates lighting/streaming
  correctly; headless can't.)
- **Fused weakest-link gate**: readability + identity + layout/lane legibility; fail-closed; → PROMOTED_TO_REVIEW.
- **Reuse env validators** (actor_count_min, lighting_present, wane_line_spine_core) + add a BR-specific
  `br_lane_readability` concept (a lane that doesn't read top-down or at player-eye caps the gate).

## Phased plan
- P0 (offline now): lock this strategy + the map intent-contract schema fields (layout/lane/POI/landmark).
- P1 (plugin): compose the greybox playable space + gate it through the loop, live-validated (own eyes + optics).
- P2 (plugin + operator): slice a backdrop (Marble or BlenderGIS — operator picks the source given license gates).
- P3: dress passes (materials/VFX/lighting) each re-gated through the loop.

## Open decision for the operator
Which backdrop source for Phase 2 — **Marble** (AI, already-built ingest, paid/operator-only) or **BlenderGIS**
(real-world, needs the license re-verify + OSM data-license check first)? Phase 1 (the compose-led greybox) does
not depend on this and can start as soon as the editor + plugin are up.
