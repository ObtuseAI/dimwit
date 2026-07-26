---
version: alpha
name: WANEFALL
description: >-
  Competitive alien-warrior arena + extraction FPS in a dark, Wane-corrupted
  galaxy. One identity read across two camera contexts: a cool sealed-visor first
  person and a warm, readable third person. Cyan/teal is the in-world tactical
  signal and the ally voice; violet is Wane corruption and the menu/brand voice;
  everything sits on cool near-black. Readable-at-a-glance, information-first,
  grown-and-weaponized — never soft, never chrome, never a full-body glow.
colors:
  # — Semantic roles (DESIGN.md convention; literal aliases of the Wane palette) —
  primary: "#C469FD"            # brand / menu voice = Wane violet
  secondary: "#59EDF6"          # tactical / ally voice = Wane cyan
  tertiary: "#FF9F2E"           # objective / waypoint = amber
  neutral: "#0B0F16"            # structural surface near-black
  # — Surfaces: cool near-black, never pure #000 (declared canon) —
  void: "#05070B"
  surface: "#0B0F16"
  surface-raised: "#141A24"
  surface-line: "#243044"
  # — Carapace neutrals: the species material language (declared canon) —
  obsidian-chitin: "#0C0E12"
  charcoal: "#1A1D21"
  gunmetal: "#2B2F36"
  bone-metal: "#C7C9CE"
  old-silver: "#8A8D94"
  # — Text: cool white, never pure white for body —
  on-surface: "#E6ECF5"
  on-surface-dim: "#8A94A6"
  on-surface-faint: "#5A6478"
  white: "#FFFFFF"
  # — Wane accents: code-grounded, converted from in-game FLinearColor → sRGB —
  wane-cyan: "#59EDF6"          # in-world tactical signal / HUD primary  (0.10,0.85,0.92)
  wane-cyan-pale: "#B3F9FF"     # bright relic/tracer highlight           (0.45,0.95,1.00)
  wane-teal: "#61C4CE"          # seam glow, portals, calm in-world        (0.12,0.55,0.62)
  wane-violet: "#C469FD"        # Wane corruption / menu + brand primary   (0.55,0.14,0.98)
  wane-violet-deep: "#9561C4"   # corrupted target glow                    (0.30,0.12,0.55)
  wane-green: "#59C495"         # trial / safe-economy state               (0.10,0.55,0.30)
  # — Signal: HUD semantics (declared from the HUD reference) —
  signal-threat: "#FF4D4D"      # enemy, contraband, danger
  signal-objective: "#FF9F2E"   # objective markers, waypoints
  signal-ally: "#59EDF6"        # team = cyan (alias of wane-cyan by intent)
typography:
  wordmark:
    fontFamily: Rajdhani
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1.0
    letterSpacing: 0.18em
  display-lg:
    fontFamily: Rajdhani
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: 0.04em
  heading-md:
    fontFamily: Rajdhani
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.02em
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0.12em
  telemetry:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.02em
rounded:
  none: 0px
  sm: 2px
  md: 4px
  lg: 8px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 24px
components:
  hud-panel:
    backgroundColor: "rgba(8, 12, 20, 0.72)"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
  hud-readout:
    textColor: "{colors.wane-cyan}"
    typography: "{typography.telemetry}"
  hud-threat:
    textColor: "{colors.signal-threat}"
    typography: "{typography.label-caps}"
  hud-objective:
    textColor: "{colors.tertiary}"
    typography: "{typography.label-caps}"
  brand-wordmark:
    textColor: "{colors.white}"
    typography: "{typography.wordmark}"
  menu-surface:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.on-surface}"
    padding: "{spacing.lg}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.void}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.md}"
    height: 44px
    padding: 0 24px
  button-primary-hover:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.void}"
  tab-active:
    textColor: "{colors.primary}"
  tab-inactive:
    textColor: "{colors.on-surface-dim}"
  wane-hazard:
    textColor: "{colors.wane-violet-deep}"
    typography: "{typography.label-caps}"
  relic-highlight:
    textColor: "{colors.wane-cyan-pale}"
    typography: "{typography.telemetry}"
  status-safe:
    textColor: "{colors.wane-green}"
    typography: "{typography.label-caps}"
  scan-trim:
    textColor: "{colors.wane-teal}"
    typography: "{typography.telemetry}"
  caption-faint:
    textColor: "{colors.on-surface-faint}"
    typography: "{typography.label-caps}"
# — Custom token groups: the 3D / in-engine law (the format accepts any key) —
cameras:
  first-person:
    reference: Halo 3 sealed-visor — cool, desaturated, locked exposure
    whiteTemp: 5600
    autoExposureBias: 0.10
    autoExposureMin: 0.45
    autoExposureMax: 1.5
    colorSaturation: "0.88, 0.89, 0.93"
    colorGain: "0.97, 0.99, 1.04"
    blendWeight: 1.0
  third-person:
    reference: Fortnite readability — warm, punchy, saturated
    whiteTemp: 7000
    autoExposureBias: 0.55
    autoExposureMin: 0.50
    autoExposureMax: 2.2
    colorSaturation: "1.22, 1.20, 1.16"
    colorGain: "1.06, 1.04, 0.98"
    blendWeight: 1.0
materials:
  carapace-metallic: 0
  carapace-base: "glTF MI_Default_Opaque (opaque, metallic 0) — never legacy Phong"
  weakpoint-emissive: 1.0
  wane-seam: "#61C4CE"
  wane-crack: "#59EDF6"
  wane-corruption: "#C469FD"
motion:
  hud-feedback: 120ms
  menu-transition: 220ms
  easing: "cubic-bezier(0.2, 0, 0, 1)"
---

# WANEFALL — Visual Identity

## Overview

WANEFALL is a competitive alien-warrior FPS — arena and extraction — set in a
dark galaxy eaten by the **Wane**, a corruption that cracks through ancient
relic-tech and living carapace alike. The look is not "sci-fi clean." It is a
sealed-helmet soldier's view of a beautiful, hostile, half-ruined world: matte
near-black surfaces, hard angular chrome-free armor, and two colors of light that
*mean* things — **cyan/teal** for the world and your allies, **violet** for the
Wane and for the menus that frame the war.

The identity has to survive two completely different reading contexts and stay
recognizably one game:

- **First person** is a **sealed Halo-3 visor**: cool, slightly desaturated,
  exposure locked to a narrow band so the world feels stable behind glass.
- **Third person** is **Fortnite-readable**: warmer, more saturated, a wider
  exposure swing so silhouettes and team color pop.

When a rule or token doesn't cover a decision, fall back to this: *would a
disciplined alien frontline soldier find it instantly readable, and does it feel
grown-and-weaponized rather than manufactured-and-glossy?*

## Colors

The world is built on **cool near-black** with two load-bearing accents. Neutrals
carry everything structural; accents are scarce and each one carries a single
fixed meaning.

- **Void (#05070B)** and **Surface (#0B0F16)** are the canvas — cool near-black,
  never pure `#000`. The world, the HUD glass, and the menus all sit on this.
- **Carapace neutrals** — Obsidian Chitin (#0C0E12), Charcoal (#1A1D21),
  Gunmetal (#2B2F36) — are the species material language: hard, grown, matte.
  Bone-Metal (#C7C9CE) and Old-Silver (#8A8D94) are the ceremonial/relic neutrals.
- **Wane Cyan (#59EDF6)** is the in-world tactical signal and the ally voice —
  scanners, team, your own relic light. It is the HUD's primary readout color.
- **Wane Teal (#61C4CE)** is the calmer in-world variant: seam glow, portals,
  trim. **Wane Violet (#C469FD)** is the **Wane corruption itself** *and* the
  menu/brand voice — hazards, corrupted cores, and every front-end surface.
- **Signal colors** are HUD-only semantics: **Threat (#FF4D4D)** for enemies and
  contraband, **Objective (#FF9F2E)** for waypoints. They never appear as
  decoration.

The cyan accents are converted directly from the colors the game already renders
(`FLinearColor` → sRGB), so the spec matches the build rather than guessing.

## Typography

Two voices. A **wide techno display** (Rajdhani-class: condensed, uppercase, wide
tracking) carries the **WANEFALL** wordmark, screen titles, and section headers —
it should read like stenciled hardware. A **clean humanist sans** (Inter) carries
body and menu copy. HUD numerals and telemetry use a **monospace** (JetBrains
Mono) so values don't jitter as they tick. Micro-labels on the HUD use
**Space Grotesk** in caps with wide tracking.

- Headings are wide and uppercase; never set body in the display face.
- Telemetry (ammo, timers, scores) is always monospace — fixed-width, calm.
- Trust modest size jumps. The HUD hierarchy is built from weight, tracking, and
  color, not from giant type.

## Layout

Two layout systems share one grid (`spacing` scale, 24px gutter).

- **HUD** is corner-anchored and information-first: compass + scanner top, team /
  objective panels in the corners, ammo and ability bar bottom, a clean center.
  Panels are collapsible and the middle of the screen stays mostly empty —
  negative space is a feature, not waste.
- **Menus** are dense and premium: a left nav rail, a top tab bar, a hero panel,
  and gridded cards (loadout, operator, map, inventory). Density is high but
  every block is aligned to the same gutter.

Respect generous safe-zone margins; nothing critical hugs a screen edge.

## Elevation & Depth

Depth comes from **translucency and glow**, not skeuomorphic shadow. HUD panels
are semi-transparent dark glass over the live world (`rgba(8,12,20,0.72)`) with a
single hairline border (`surface-line`). Active/Wane elements get a soft colored
bloom in their accent; inert elements get none. Avoid heavy drop shadows, beveled
chrome, or glassy gradients — the world behind the glass is the depth.

## Shapes

Angular and hard. Thin **1px hairline borders**, chamfered/clipped corners, and a
recurring **hex / diamond** motif (rank diamonds, ability hexes). Rounding is
minimal — `rounded.sm`–`md` at most; the only fully-round shapes are status dots
and timers. No soft pills, no rounded-rect "app" cards.

## Components

- **hud-panel** — dark translucent glass, hairline border, cool-white text.
- **hud-readout** — Wane-cyan monospace telemetry (ammo, timers, scores).
- **hud-threat / hud-objective** — caps micro-labels in threat-red / objective-amber.
- **menu-surface** — opaque void background; the front-end's deep stage.
- **button-primary** — Wane-violet fill with void-dark label; **hover shifts to
  Wane-cyan**. Violet = "this is a menu action," cyan = "confirmed / in-world."
- **tab-active** — violet text + underline; inactive tabs drop to dimmed neutral.

## Cameras & Grading

The single most important rule: **first person and third person must not look the
same.** These are the live, shipping post-process values (per-camera
`PostProcessSettings`, `BlendWeight 1.0`):

- **First person — sealed visor (cool):** WhiteTemp **5600**, slightly
  *desaturated* (ColorSaturation `0.88, 0.89, 0.93`), a cool gain lift
  (`0.97, 0.99, 1.04`), and a **narrow** auto-exposure band (bias 0.10, min 0.45,
  max 1.5) so brightness barely breathes — the locked-visor feel.
- **Third person — readable (warm):** WhiteTemp **7000**, *punchy*
  (ColorSaturation `1.22, 1.20, 1.16`), a warm gain (`1.06, 1.04, 0.98`), and a
  **wide** exposure band (bias 0.55, min 0.50, max 2.2) so the world reads bright
  and silhouettes pop.

These overrides also exist to *defeat the dark theme PPV crushing the player to
black* — exposure is authored, not left to auto.

## Materials & Wane Language

- **Characters are de-chromed: metallic = 0.** Carapace uses a glTF
  `MI_Default_Opaque`-style opaque base, never a legacy Phong/FBX material (that
  renders silver-dark). Chrome is the #1 way a character reads wrong.
- **Wane light is structural, not cosmetic.** Cyan/teal **seam glow** lives in the
  cracks *under* shell plates; violet is **corruption**. Wane never becomes a
  full-body glow.
- **Emissive weak-points stay in HDR range (~1.0)** — bright enough to read, never
  blown out to a white blob.

## Characters & Species

Eight visually distinct alien species share one **competitive fairness envelope**:
identical capsule, camera height, hitbox, movement, and aim. Difference is
*visual only* — head/helmet wedge, shoulder/collar profile, carapace pattern, Wane
pattern, accent color.

Primary silhouettes are **masculine, lean-athletic, combat-built**: broad
shoulders, tight hips, armored posture, aggressive alien-warrior presence. No
human read — human rigs are scaffolding only; the final must be non-human alien
humanoid. **Kharvex** (carapace war-born shock species — charcoal/obsidian chitin,
gunmetal, dark-teal seam glow, cold-cyan Wane cracks, triangular predator helm) is
the flagship/starter and the reference for the lane.

## Motion

Quick and mechanical — a light switch, not a door closing. HUD feedback
**120ms**, menu transitions **220ms**, shared easing `cubic-bezier(0.2,0,0,1)`.
Nothing bounces, overshoots, or lingers; nothing animates past ~300ms. Respect
reduced-motion: collapse durations to 0.

## Do's and Don'ts

- **Don't** let first person and third person grade the same. FP is cool/sealed
  (5600K, desaturated, narrow exposure); TP is warm/readable (7000K, saturated,
  wide exposure).
- **Don't** chrome the characters. Carapace metallic stays **0**; a legacy
  Phong/FBX material renders silver-dark and reads wrong.
- **Don't** reveal hidden weapon kitbash sub-parts. Showing a mesh with
  propagate-to-children re-reveals raw placeholder boxes — show the parent
  without propagation, then hide children individually.
- **Don't** make a species "a black mannequin with teal glow," and don't make Wane
  a full-body glow — it's pressure cracks beneath the shell.
- **Don't** use curvy, soft, or feminine-coded silhouettes for the primary roster,
  and don't bulk armor up enough to imply a bigger hitbox.
- **Don't** cross the accent meanings: **cyan = world / ally / confirmed**,
  **violet = Wane / menu / brand**. Threat-red and objective-amber are HUD-only.
- **Don't** blow out emissive weak-points; keep them ~1.0 HDR, in range.
- **Don't** use pure `#000` or pure `#FFF` for surfaces or body text — cool
  near-black and cool white.
- **Do** keep the HUD information-first and clutter-free: readable at a glance,
  empty center, collapsible modules.
- **Do** treat a specific reference as law — "Halo 3 sealed visor," "Fortnite
  readability," "grown and weaponized carapace" — over a list of adjectives.
- **Do** keep one fixed meaning per accent color. Scarcity is what makes the
  signal legible.

## Linting & Validation

This file is validated by `design.md lint`. It is the canonical, machine-checked
WANEFALL visual law — read by Claude (validator rubric) and Dimwit (fail-closed
`design_md` gate). The gate fails closed on **errors** and on **`diff` regressions**
against the committed baseline; **warnings are advisory** and do not block.

A clean run reports **0 errors**. The standing warnings are intentional and must
not be "fixed" by inventing fake components:

- **Unreferenced material/world colors** (`obsidian-chitin`, `charcoal`,
  `gunmetal`, `bone-metal`, `old-silver`, `surface-raised`, `surface-line`,
  `wane-violet`, `signal-objective`, `signal-ally`). The linter only counts a color
  as "used" when a 2D component references it. These are 3D carapace/Wane/world and
  elevation primitives, plus signal roots whose semantic aliases (`primary`,
  `secondary`, `tertiary`) *are* wired to components. They are law for materials and
  the live game, not for a HUD widget.
- **Custom token groups** (`cameras`, `materials`, `motion`) are not part of the
  web-UI schema and are reported as unrecognized keys. They carry the 3D art law
  (per-camera grading, carapace/emissive material rules, feedback timing) that the
  format intentionally allows as extension sections. Export commands ignore them;
  Claude and Dimwit read them as prose-backed normative values.

Never weaken the validator to silence these. If a warning ever appears outside
this list, treat it as a real finding.
