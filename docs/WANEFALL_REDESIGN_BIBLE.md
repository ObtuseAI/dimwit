# THE WANEFALL REDESIGN BIBLE

_One game. One force (THE WANE). Every surface — HUD, front-end, maps — made of it._

Source: adversarial anti-slop multi-agent workflow (22 agents: diverse directions per surface -> novelty/badass/authentic/readability gate -> per-surface synthesis -> unified bible).

---

# SURFACE: HUD — In-combat HUD

I have everything I need to fuse these. Here's the decisive spec.

---

# WANEFALL IN-COMBAT HUD — FINAL DIRECTION: **"THE FADE"**

## CORE CONCEPT
There is no HUD. You are an alien perceiving combat through a **Wane-sense organ**, and your own survival is read as **how lit you still are**. We fuse three things into one spine:

- **Vitals live ON YOUR BODY** (from WANELIGHT) — the load-bearing read.
- **Damage and decay express as ENTROPY** (from THE WANE DECAY) — the edge-dissolve and re-knit.
- **Enemies are AGE-DECAYING WANE-GHOSTS** (from WANESIGHT) — the one genuinely un-copyable mechanic, where staleness *is* the intel.

One sentence: **Your suit is your health bar, your gun is your ammo counter, and the enemy's own decay is your radar — and all three are the same energy, THE WANE, draining out of the world.**

We pick **WANELIGHT's body-channel vitals as the spine** (it's the most readable and most franchise-locked), graft **THE WANE DECAY's edge-dissolve damage + re-knit healing**, and graft **WANESIGHT's age-decaying ghosts** as the single threat system. We kill every redundant off-screen-threat gimmick, every full-screen blinding effect, and every reinvented waypoint.

---

## THE NAMED ELEMENTS

**1. WANE CHANNELS (vitals).** The glowing seams in your forearms, chest-core, and pauldron, lit in your species' accent (Vorlax electric-blue → Nexor rose). Both forearms + the chest core sit in lower-center frame, right behind your gun, where the eye already rests. Damage extinguishes channel segments **from the extremities inward; the chest core dies last**. You never read a bar — you watch yourself going dark. **A hard integer HP value is etched beside the chest core, on by default in ranked.** (We do NOT bury the number — comp players track trade math.)

**2. THE RE-LIGHT (healing).** Healing re-floods Wane *outward from the core*, color returns to the suit and the world re-saturates around you. This is the signature positive beat — you literally come back to life. It's THE WANE DECAY's re-knit run through the body instead of the screen frame.

**3. EDGE-BITE (directional damage).** Getting shot tears an ashen, dissolving **bite** out of the screen edge nearest the threat — particles peel inward toward you, deeper bite = bigger hit. It encodes **direction AND magnitude in one pre-attentive cue** and auto-knits closed in ~1.2s if you break contact. This replaces the red chevron entirely. It is the ONLY screen-edge threat cue — there is no second one.

**4. WANE-GHOSTS (the radar, and our crown jewel).** Enemies sensed through geometry render as volumetric silhouettes in *their* species color — so you read **WHO before you see them**. The ghost **decays by sensory age**: sensed <0.3s ago = crisp edge-lit outline; by ~1.5s it's smeared into drifting ash in the last-known travel direction. **The decay rate IS the intel** — sharp ghost = live threat now, smeared ghost = stale. This makes peek-timing a skill and structurally prevents perfect wallhacks. Footstep/gunfire info from unseen enemies **refreshes the nearest ghost's sharpness** rather than spawning a separate sonar system — one channel, not three.

**5. CHARGE-RAIL (ammo).** A physical Wane-lit rail along the weapon's receiver that depletes toward the muzzle as you fire. Etched tick-notches let pros count exact rounds like a thermometer; last ~20% glows red-hot and guttering. Reload ejects the spent cell dark and re-floods the rail. **Ability cooldowns also ride a node on this same gun-spine** — we do NOT trust a forearm gauntlet that's off-screen half the time. Ready node = single bloom + faint haptic.

**6. THE FADE (low-health state) — with INVERTED CONTRAST.** Below ~25%, the world desaturates and softens. **But this is capped well short of monochrome, and contrast is inverted to PROTECT you:** enemies and incoming tracers stay fully saturated and gain a faint rim-light, so a dying player sees *threats more clearly* against a greyed world. The Fade punishes your spatial comfort, never your ability to fight back. Hard clarity floor on the center 60% of screen. No tinnitus tone, no visor cracks, no ash in the center — those are trailer-bait that blind you mid-clutch.

**7. SENSORIUM CLARITY (the readability governor) — load-bearing, not optional.** Caps simultaneous ghost density (LOD-fades least-relevant ghosts in chaos), enforces species-color contrast against each map's palette, and protects the center 60%. The accessibility profile swaps decay-static for solid silhouettes and surfaces numeric ammo/HP — without ever reverting to a floating box.

---

## HOW IT READS IN A 200ms GLANCE
Your eye rests on your gun. In one saccade you have: **forearm/core channels = health**, **rail = ammo**, **gun-spine node = ability ready**. Threats arrive in your periphery as **colored ghosts** (who + where + how recently) and **edge-bites** (who's shooting you, from where, how hard). Nothing requires a downward look to a corner box. Color does the instant work; etched numbers do the precise work.

## THE SIGNATURE MOMENT
You're at 8 HP in **The Fade** — world greyed to ash, your channels nearly all dark, one dying core-pulse, the enemy a fully-saturated electric-blue ghost smearing around a pillar. You hit your heal: Wane **re-floods from your core outward**, color crashes back into the suit and then the world, your channels re-ignite extremity-by-extremity — and you wheel out lit and alive. **Decay, then defiance.** That is the entire faction ("ADAPT OR VANISH") in two seconds, and no other game can show it because no other game's UI is made of its own lore-force.

## THE 3 THINGS THAT MAKE IT UN-COPYABLE
1. **Age-decaying Wane-ghosts where staleness is the data.** This can only exist in a game whose core force is entropy. Bolt it onto any other shooter and it's nonsense. It also solves the wallhack-balance problem natively.
2. **One energy, three jobs, eight authored decay signatures.** THE WANE is simultaneously your health, your enemy IFF, and your ammo — and each species *decays differently* (Therak cinders, Vorlax datamosh, Kelous burnt-gilt, Nexor rose-wilt). One readability grammar, eight ownable skins. The marketing screenshots and the mastery curve live here.
3. **The Re-Light.** Inverting heal from "bar fills" to "the man and the world come back to life from the core outward." Every shooter shows you dying; only WANEFALL makes recovery a visceral re-saturation event.

## WHAT WE DROPPED AS SLOP
Edge-fray-as-radar (ambiguous, conflates damage-dir with proximity); ambient see-through-wall heat-haze (wallhack-by-vibes); full-screen monochrome (blinds you when you need sight most); ash/cracked-visor center clutter; tinnitus hum; the removed/replaced minimap (kept faint + an *additive* Wane-pulse scan, never a blind-between-pulses replacement); reticle shard-burst hitmarkers (generic); glowing waypoint columns (Fortnite-grade); chromatic aberration (the exact post-FX cliché this brief is reacting against); forearm-only ability gauntlet (off-screen, unreadable — moved to gun-spine); and "no numbers by default" purity (comp ships with the integer on).

**Build priority:** Wane-channel vitals + charge-rail + edge-bite + age-decaying ghosts are the must-ships. World-fade in The Fade is the first thing to scale down on weak hardware — the channels and ghosts must never drop.


---

# SURFACE: UI — Front-end / menus

# WANEFALL FRONT-END — UNIFIED DIRECTION SPEC

## THE HOLD, RUN BY GLYPH

**One-line:** The front-end is the cargo hold of your own dropship being eaten alive by the Wane — and you don't click through it, you **spell** your way across it. The room is the fiction; the keyboard is the speed.

---

## SPINE (what everything hangs off)

Take **THE HOLD's** continuous diegetic room as the world, and bolt **WANEROT's glyph-chord navigation** onto it as the nervous system. The Hold gives us a place that could only be WANEFALL; the chord layer fixes the one thing that would have killed The Hold — that dollying your eyeline across a room feels like wading. You don't walk the room. You *invoke* it. Press a key and the camera **whip-pans** to that station, already resident, in under 120ms.

**The single non-negotiable idea — THE WANE IS THE CHROME, NOT A WIDGET.** There is no XP bar, no season ring, no separate progress UI anywhere. A crust of crystalline Wane-rot is eating the hold, and that one crust is *simultaneously*:
- your **season meter** (how far it has spread = how deep into the season),
- your **matchmaking countdown** (on Deploy it visibly accelerates and devours the hull in real time as the queue fills),
- your **locked-content gate** (locked iron is encased in Wane-crystal you can't lift).

The game's literal name does triple duty as functional UI. No engine template ships this; it only exists because the game is about entropy.

---

## THE THREE STATIONS (one room, three anchored zones)

You never "open a menu." The camera lives in the hold and snaps between three props:

- **THE RACK** (key: `R`) — loadout. Guns on a magnetic wall rack, energy hammers/swords in floor sheaths, grenades foam-cut in a crate.
- **THE SQUAD** (key: `Q`) — character/skin. 8 species + 8 mechs standing on the deck, each lit only by their own Wane accent.
- **THE TABLE** (key: `E`) — mode/map/deploy. A battered holo-slab.

`Esc` collapses to a top-down schematic of the whole hold (the "snap layer"). `Enter` deploys from anywhere. **Boot-to-Deploy in under 4 seconds without ever touching the mouse** — and equally, fully mouse-clickable for controller/pointer players. The chord layer is a fast *path*, never the only path, never a thing you "graduate out of."

---

## STATION DETAIL

### THE RACK — loadout
- **Locked = encased in crystal; owned = bare iron.** A 200ms silhouette read. Spending currency = you physically **scrape/burn the Wane-crystal off** the weapon to reveal the iron underneath. The unlock verb is *"push back the Fall."* This is the best unlock interaction in the doc — keep it exact.
- **Equip is a fast magnetic CLACK, not a cinematic.** The full gauntlets-lift-rotate-slap handling animation is reserved for the **hero/first-equip moment only** (and the weapon-inspect screen). Routine loadout edits — the thing you do on the 40th iteration — snap instantly. We do NOT pay the per-weapon animation tax across 25 guns × 11 melee × attachments.
- **Stats: etched on the receiver for flavor, real numbers in the snap-schematic.** The grease-pencil/hand-scrawled look stays as texture, but `Esc`-schematic exposes precise values — you *can* compare 1304 vs 1290 DPS. We never ship marks-not-numbers as the only data layer.

### THE SQUAD — character select
- The species you **own** are physically present, standing in formation under a flickering work-lamp, each lit **only by their own Wane accent** (Vorlax electric-blue, Therak molten-orange, Kelous black+gold...). You read your pick **by glow color alone** across the dark hold — the same accent the soldier emits in-match, so menu-time trains the 200ms combat color-read.
- The one you look at **steps into the lamp**, idles with weight, accent brightens.
- **Unowned species are empty armor stands** — vacant Wane-shrouded husks. Owned-vs-locked is a one-glance read (a body vs a husk) *and* a thematic gut-punch: **ADAPT OR VANISH**, staged literally.

### THE TABLE — deploy
- Maps are scuffed metal terrain-tiles; slotting one spins up a **low, dirty, glitching hologram** of that arena — Wane-static eating the edges, never a clean minimap.
- **Mode is a single decisive physical throw** — slam the 2v2 / 4v4 / 8v8 / warzone plate into the slot. We **CUT the dog-tag counting** (hanging 8 tags to pick 8v8 is fiddly inventory-management on the most frequent decision in the flow).
- Pull the physical **DEPLOY lever** → the signature moment fires.

---

## MOTION IS A VOCABULARY, NOT DECORATION (3 verbs, menu + HUD share them)

Three motions, fixed meanings, used identically in the front-end and the in-match HUD so menu-time teaches combat-reads:

1. **CRYSTALLIZE** — something arriving / confirmed / owned (assembles from glyph-dust inward).
2. **ERODE** — something lost / locked / unavailable (frays outward into Wane-dust).
3. **SNAP** — a hard one-frame electric flash on commit (equip, purchase, ready).

A frayed edge *always* means locked. A crystallizing element *always* means arriving. Players read state without reading text. **Decay only fires on state-change** — not perpetual ambient rot. The focus node and all interactive text stay 100% crisp and stable always; only secondary/unavailable elements decay. (A menu that visibly rots while idle reads as *broken*, not *thematic* — we hold a hard floor against that.)

---

## THE SIGNATURE MOMENT — "THE HOLD FALLS"

You pull the DEPLOY lever. The matchmaking-rot you've been watching crawl now **accelerates and eats your own ship in real time** as the lobby fills. In an 8-player lobby, each player readying fires a **species-colored SNAP** — a shockwave of their accent across the hull (8v8 = a cascade of 8 colored cracks of light). On the final ready, the whole frayed hold **CRYSTALLIZES to full crispness for one breath** — the crew holding back the Fall together for a single beat — then the Wane reaches the airlock, the doors blow, accent-glows snap out one by one, and the hull tears into white.

**The load screen is your own ship being devoured by the theme.** That's the shot that goes on the box.

---

## ACCESSIBILITY / SPEED RAILS (non-negotiable)

- **Layout is deterministic and identical** with or without VFX. The room's hotspots are fixed; muscle memory is sacred.
- **Reduced-Motion mode** swaps every CRYSTALLIZE/ERODE for a 120ms ash-wipe and holds the exact same layout. Nothing about navigation depends on the effect.
- **Mouse + controller are first-class**, not a fallback. The glyph wheel is fully clickable.
- All text is **plain legible Latin**. The Wane-glyph is exactly **one etched sigil per station** (a chord mnemonic) — we **CUT the alien-script-that-resolves-to-Latin** idea outright: it tanks scannability, it's an 8-language localization nightmare, and it's the exact Destiny/Halo "mysterious alien font" slop we're here to kill.
- No transition exceeds 120ms; particle theater rides a separate layer that **never blocks input** — you can chord through an animation mid-play. Frame-data UI, not a web app.

---

## THE THREE THINGS THAT MAKE IT UN-COPYABLE

1. **The Wane crust is the entire progression/matchmaking/lock economy as one physical object.** Rip it out and the game's name stops meaning anything. A generic engine can't ship this because it only works if your whole game is about entropy — ours is.

2. **You spell the room.** A diegetic 3D space navigated at fighting-game speed by keyboard chords (`R`/`Q`/`E`/`Enter`), with the room as fiction and the keyboard as the nervous system. Lobby-as-room games are slow and mouse-led; chord-driven menus are flat and abstract. Nobody fuses the two — the fusion is the moat.

3. **Owned is a body, locked is a husk; spending is scraping the Fall off your iron.** Absence and cost are staged *physically and thematically* — empty armor stands for species you don't have, crystal-encased weapons you literally burn free. The economy screens (store, battle-pass) — the most generic surfaces in any F2P shooter — become the *most* on-theme surfaces in ours.

---

## WHAT WE EXPLICITLY CUT (the anti-slop ledger)

- **Dog-tag mode-counting** — fiddly inventory-management on the highest-frequency decision. Replaced with a decisive plate-throw.
- **Full per-weapon lift-rotate-slap equip** — unbuildable across the arsenal; reserved for hero/inspect only.
- **Grease-pencil marks as the only stat read** — kept as texture; real numbers live in the schematic.
- **Continuous-dolly-as-only-nav** — the wading problem; chords + snap-schematic are co-equal from minute one, surfaced to new players, not hidden for veterans.
- **Alien-script typography** — localization/scannability poison; one etched sigil per station instead.
- **Perpetual ambient decay** — reads as "broken/unfinished"; decay fires on state-change only, focus node always crisp.
- **Tertiary diegetic-everything** (corkboard mail, helmets-on-hooks friends list, welded-plate routed through tapping props) — kept exactly ONE hero diegetic social object (the **welded kill-wall** for rank, sparks-and-all), everything else is a fast overlay summoned in-space.

---

**The pitch in one breath:** You boot in. You're standing in the cargo hold of your own ship, and the Wane is eating it from the corner. You tap `R` — whip-pan to the rack, you burn the crystal off a new rifle, it CLACKS to your hip. `Q` — the hold goes dark but for eight colored silhouettes; you look at the blue one, Vorlax steps into the lamp. `E` — you slam the 8v8 plate into the war table, a filthy hologram of the arena coughs up out of the slab. You haul the DEPLOY lever. The rot screams across the hull, eight colored snaps crack around you, the room freezes crisp for one breath — then the airlock blows and you fall into the match. You never touched the mouse. You never saw a single flat panel. **Four seconds, boot to Fall.**


---

# SURFACE: MAPS — Map design system

I'll fuse these into one decisive spec. Let me think through the adversarial vetting first, then write it.

# WANEFALL MAP SYSTEM — "THE WANE LINE"
## One place, dying on a clock you can read off the walls

---

## THE SPINE (and why)

Take **THE FALLING MAP** as the chassis — its WANE LINE (a literal advancing collapse front on a deterministic timeline) is the single highest-leverage idea in the batch, because it turns the IP's one proprietary concept (entropy) into a moment-to-moment *verb*. A map that is collapsing cannot be reskinned into Apex or Halo without dragging THE WANE along with it. That's the un-copyable core.

Then **graft three organs** from the others:

1. From **COLLAPSE CLOCK** → the **INVERSION** and the **saturation-as-truth perceptual law** and the **"Fading" debuff on your own body.** The Inversion is the one idea that solves "memorized in one match" *structurally* — endgame geometry is a different arena than the opening.
2. From **FALLING LANDMARK** → **silhouette-first authoring + map-select-by-silhouette** and **Wane-vein wayfinding.** This is the actual, concrete fix for "22 mandalas": you build 8 unforgettable named places, not 22 clones.
3. Everything flagged slop gets **dropped** (list at the bottom — non-negotiable).

The result is not three systems bolted together. It's **one place** (silhouette-first), **dying on one front** (the Wane Line), **that inverts once** (the structural beat), **read entirely off the world's saturation** (the perceptual law). Four ideas, one spine.

---

## CORE CONCEPT

Every WANEFALL map is **a single named real place caught at the exact second THE WANE begins eating it.** Not an arena — a *moment*. The Wane physically advances across the map during the match as a visible **collapse front**, converting living ground into dead ground on a fixed, learnable timeline. Mirror-symmetry is **banned by mandate.** Fairness comes from the collapse timeline being identical and deterministic for both teams — *determinism is the integrity guarantee, not geometry.*

The whole map is authored as **two material states of the same structure** — PRISTINE and FALLEN — and the Wane Line is literally the wipe between them. You build one place twice (intact / collapsed) and reveal the collapsed layer as the line passes. This is a timeline-triggered material/LOD swap, not 22 bespoke maps. The production answer is baked into the concept.

---

## THE NAMED ELEMENTS

### 1. THE WANE LINE — the master mechanic
A shimmering, geometry-fraying corruption front, ~3–8m thick, that sweeps the map on a fixed schedule (advances ~1 lane per 60–90s in 4v4). It defines three live zones:

- **HOLDING ground** (ahead of the line): intact, lit, full-saturation, normal physics, normal light. Safe.
- **THE LINE itself:** the kill-creation zone — sightlines tearing open, structure fraying. Where the map *changes.*
- **FALLEN ground** (behind the line): **darker, quieter, emptier.** The Wane *ate the light.* Surfaces lose texture-detail and desaturate toward ash/bone-white. This is the hard rule that protects the anti-slop claim — **fallen ground is NOT a glowing particle rave. It is a dead, dim, drained husk.** (See the perceptual law.)

Standing in Fallen ground applies **FADING** — a non-lethal, stacking pressure debuff that **desaturates your own player outline.** You literally start to vanish. "ADAPT OR VANISH" is a thing you feel on your own body, not a wall poster. It's a *gradient*, not a gas cloud — it shapes movement, it doesn't insta-punish.

### 2. THE INVERSION — the one structural beat (at ~2/3)
Until the 2/3 mark, the line eats *inward toward the core*, pushing the fight to the rich outer ground. At the 2/3 trigger, **a single Wane-Pulse detonates from center: the core RE-SOLIDIFIES into a dense final-stand arena, and the entire outer ring begins falling inward.** The match that started spread-out violently compresses into a different map. This happens **once.** (We do NOT do Collapse Clock's "multiple simultaneous inversions in 8v8" — see cuts.) This is the load-bearing answer to "every map memorized in one game."

### 3. ENTROPY EVENTS — 1–2 scripted, deterministic geometry rewrites per map
At fixed timestamps a piece of the place permanently un-builds. Examples per map: a spire's anchor-veins rot through and it **topples along a telegraphed shadow-arc**, carving a new debris-bridge and sealing an old lane. These are deterministic so pros learn them — that's what makes them a *system,* not a gimmick. **Hard rule: max one major geometry rewrite per ~2.5 min**, so a player's mental map is never invalidated faster than it can be re-learned.

**The mandatory TELL (this is the one unproven combat-readability risk — we solve it, we don't assume it):** every Entropy Event and the Wane Line's leading edge get a **15-second pre-collapse telegraph** — accelerating Wane-bleed (accent veins flaring), drifting ash, a low structural groan, and a hard-edged **white-hot wane hazard flash** on the doomed geometry. No collapse ever kills without a 15s learnable warning. If we can't telegraph it, we cut it.

### 4. LOAD-BEARING WANE-VEINS — readable destruction + wayfinding (double-duty)
The structure's species accent-energy runs through it as glowing veins. They do **two jobs**:
- **Destruction:** only geometry with bright veins can collapse. Vein **brightness/flicker = "this is about to go."** Concentrated damage OR the rot-advance severs a vein and the attached geometry drops *predictably.* This kills AAA "rubble-soup" — destruction is readable, not chaotic.
- **Wayfinding:** veins always flow **downhill toward the contested core.** Lost player reads: brightening veins → the fight; dimming veins → safety. No minimap dependence.

### 5. SILHOUETTE-FIRST PLACES — the fix for "22 mandalas"
Ship **8 hero maps, one per species accent**, not 22 clones. Each is authored as **one unmistakable black silhouette** against its species wane-color, named in one sentence:

- **HOLLOW SUN** — a dead Therak reactor cracked open like an egg, molten-orange Wane in the pit. *"Fight the rim of a broken sun as the core inverts under you."*
- **TIDEWRECK** — an Ekris capital ship beached on its side, silver hull = the floor, the Wane rusting it out from under you, data-architecture un-writing itself.
- **GLACIERA DRY-DOCK** — freezing AND fraying, ice + teal-Ullio decay.
- **SPIRECRACK** — a 400m Vorlax spire fractured 60% up, electric-blue, the upper third dangling on energy tethers (its Entropy Event = the topple).

Map select = a wall of silhouettes against species color, picked the way a fighting-game player picks a stage. Identity is instant. **Asymmetry-by-elevation:** the two teams spawn at *different structural features of the same landmark* (bridge vs. torn stern), never mirrored points.

### 6. THE DIEGETIC FRONT-READER (replaces the radar)
The "minimap" is a **single sweeping accent-light arc on a near-blank field** showing only the Wane Line's current position and travel direction. Intact ground = faint solid; Fallen ground = static/noise; the line = one bright moving stroke. One 200ms glance answers exactly one question: *where's the front and which way is it coming.* (Note: we deliberately do NOT use Collapse Clock's "central draining Wane-Spire fuse" — that's a recycled Apex-ring beacon sitting in the least stable real estate. Phase is read off **world saturation**, which we already have for free.)

---

## THE PERCEPTUAL LAW (the thing that makes it READABLE in 200ms)

**Saturation = truth.** One rule governs danger, structural integrity, and match phase simultaneously:

- **Bright + saturated species-accent = ALIVE / SAFE / LOAD-BEARING.**
- **Grey / desaturated / drained = ROTTING / LETHAL / ABOUT TO COLLAPSE.**
- **White-hot wane = the 15s hazard telegraph** (and ONLY that).

The world *gets emptier and darker as it dies* — the opposite of the glowing-everywhere AAA look. Enemy soldiers (lit by their own species accent) and the contested bright veins always pop against the desaturating world. **Mandatory per-map hazard-contrast rule:** on blue/teal maps (Vorlax, Ullio) the accent veins sit near the white-hot telegraph on the spectrum — those maps get an enforced contrast offset (warmer telegraph or cooler vein) so the "about to collapse" flash never muddies under HDR/flashbangs. This is specified, not assumed.

---

## HOW IT READS IN REAL PLAY

You spawn in bright, intact HOLDING ground. Glance left: a dim, drained husk where the map already died — you don't go there, your own outline would start fading. Glance at the front-reader: one bright arc, sweeping toward your strong position. You fight forward of it. At 4:00 the veins on the central spire flare white-hot and groan — 15 seconds, everyone reads it, everyone rotates. The spire topples on its telegraphed arc, a new debris-bridge opens, your old flank is sealed. At the 2/3 Inversion the whole outer ring you've been fighting in starts to die and the re-solidified core pulls everyone into a compressed last stand. The match *ends in a different place than it began*, and the wreckage tells the story — every match produces a unique ruin (great for clips and spectator identity).

---

## THE SIGNATURE MOMENT

**The Inversion.** You and the enemy have spent four minutes pushing each other across the bright outer ring. The center has been dead, rotting ground the whole match. Then the Wane-Pulse fires from the core: the dead center **violently re-solidifies into the final arena** while the bright ground under your feet goes grey and starts to fade — the safe world and the dead world **trade places in one beat.** Everyone is yanked inward into one compressed, last-stand fight on ground that was lethal sixty seconds ago. "FALL IS INEVITABLE" stops being a tagline and becomes the geometry pulling you in.

---

## THE 3 THINGS THAT MAKE IT UN-COPYABLE

1. **The map is a verb.** Every other shooter ships a static stage and decorates it with "a door opens, a train passes." WANEFALL ships a *place actively dying on a deterministic clock,* where the collapse IS the balance system and IS the objective pressure. Rip out the collapse and you don't have a map — you have nothing. You cannot lift this into Apex without lifting THE WANE with it.

2. **Determinism replaces symmetry as the fairness guarantee.** No competitive shooter balances via "the same place dies on the same timeline for both teams" instead of "two mirrored halves." It's a genuinely defensible integrity argument *and* it's the thing that kills the 22-mandala slop tell. Pros learn the collapse the way they learn a fighting-game stage.

3. **You watch yourself vanish.** Saturation-as-truth means the same perceptual rule that tells you "this wall is about to fall" also tells you "*you* are about to fall" — the Fading debuff desaturates your own body in the Wane. The faction's entire thesis (entropy, holding on as the world fades) is rendered on the player's own silhouette. No reskin survives that, because the theme is welded to the perception layer, not painted on top.

---

## DROPPED AS SLOP (non-negotiable)

- **Corruption-pool = stand-in-the-bad-circle-for-a-buff.** Pure Apex/Destiny rift-and-gas vocabulary. Cut. (If a Wane-charge mechanic is ever wanted, it must cost *durability/lifespan* — decay-flavored — not just eat a DOT.)
- **Decay runnels = fast-but-loud movement lane.** Stock Titanfall/Apex tradeoff. Cut as a "novel" feature.
- **"Drain" / "Bloom" elemental events** (conductive-fluid-electrifies-a-lane, structure-cracks-into-a-glowing-objective). The exact "a door opens" set-dressing the pitches themselves mock. Keep only events that **permanently rewrite positioning** (the topple). Cut the rest.
- **Rot-and-regrow cover** re-crystallizing into an unpredictable new shape. RNG geometry = feel-bad deaths = competitive death. Cut. (Only deterministic, ghost-telegraphed regrows survive, and only if QA-proven.)
- **The central draining "Wane-Spire" clock.** Recycled battle-royale beacon, and it sits in the core where Inversion chaos lives. Cut — phase is read off world saturation.
- **8v8 multiple simultaneous inversions / merging rot-fronts.** Authoring + netcode + readability landmine. One front, one inversion. (8v8 gets a larger single front, not parallel ones.)
- **"Gravity-stuttering" fallen physics.** Non-deterministic grav in the fight zone = pro hate-test bait. Cut unless made as deterministic as the timeline.
- **"Validated with playtest heatmaps" / "monochrome makes enemies pop"** as *features.* Table stakes, not design. Don't pad the doc with them.

---

**Build order:** one collapse-system tech stack, reused across all 8 maps. Per map = one hero silhouette mesh (pristine + fallen states) + 3 elevation bands + the Wane Line wipe + 1 Inversion + 1–2 telegraphed Entropy Events + vein-lighting pass + species accent color. Eight unforgettable dying places beats twenty-two clones.


---

# UNIFIED DESIGN BIBLE + BUILD ROADMAP

This is a creative direction synthesis task. The four surface specs are already written and decisive. My job is to write the Design Bible that unifies them, plus a practical UE5 build roadmap. I have everything I need in the brief. Let me write it directly.

# THE WANEFALL DESIGN BIBLE
### One game. One force. Every surface made of it.

---

## PART 1 — THE WANEFALL DESIGN LANGUAGE
*The 5 laws that make HUD, front-end, and maps read as one object*

Every shooter has a HUD, a menu, and maps. Ours are not three problems — they are three views of **one substance draining out of the world**. These five laws are inviolable. If a feature breaks one, it is slop, and it is cut.

### LAW 1 — THE WANE IS THE CHROME, NEVER A WIDGET
Nothing in WANEFALL is a panel painted on top of the game. The interface is *made of the same energy the game is about.* Your health is Wane in your body. Your ammo is Wane in your gun. The enemy is Wane decaying in the air. Your season progress is Wane-rot eating your ship. A map's clock is Wane eating the ground. **There is no abstract layer** — no bars, no corner boxes, no XP rings, no floating chevrons. If you can point at a thing on screen and say "that's UI, not world," it's wrong. The literal force the faction is named for does every functional job an interface normally does.

### LAW 2 — SATURATION IS TRUTH (the one perceptual grammar, everywhere)
A single color law governs all three surfaces so a player learns it once and reads it for life:

- **Bright + saturated species-accent = ALIVE / SAFE / READY / OWNED / LOAD-BEARING.**
- **Grey / desaturated / drained = DYING / LOST / LOCKED / STALE / ABOUT-TO-COLLAPSE.**
- **White-hot Wane = the hazard telegraph, and ONLY ever that** (15s collapse warning in maps; the SNAP commit-flash in menus; the red-hot last-rounds on the charge-rail).

This is why the world gets *emptier and darker as it dies* — the deliberate inverse of the glowing-everywhere AAA look. The same rule that tells you "this wall is about to fall" tells you "you are about to fall" tells you "this weapon is locked." One grammar, three surfaces, zero relearning.

### LAW 3 — DECAY FIRES ON STATE-CHANGE; THE FOCUS IS ALWAYS CRISP
Entropy is the theme, but **a thing that visibly rots while you're idle reads as broken, not thematic.** Hard floor across every surface: decay animates only on a *change of state* — you take a hit (edge-bite), you lose a life (Fading), you lock/unlock an item (erode/crystallize), the collapse front passes (the wipe). The element you are *acting on right now* — the focus node, the center 60% of combat screen, the interactive text — stays 100% stable and crisp **always.** Decay is an event, never wallpaper.

### LAW 4 — THREE MOTION VERBS, FIXED MEANINGS, SHARED MENU↔COMBAT
The same three motions carry the same meaning in the front-end and the HUD, so **menu-time literally trains combat-reads:**

1. **CRYSTALLIZE** — arriving / confirmed / owned / re-lit (assembles inward from Wane-dust). *Menu: an unlock. Combat: the Re-Light heal flooding back.*
2. **ERODE** — lost / locked / stale / dying (frays outward into ash). *Menu: a locked husk. Combat: an enemy ghost smearing, your channels going dark, your Fading outline.*
3. **SNAP** — a hard one-frame electric flash on commit (equip / purchase / ready / kill / ready-up). Species-colored.

A frayed edge *always* means decay/loss. A crystallizing element *always* means arrival/life. The player reads state without reading text, in menus and mid-firefight identically.

### LAW 5 — EIGHT AUTHORED DECAY SIGNATURES; READABILITY IS A GOVERNOR, NOT A HOPE
THE WANE is one grammar with **eight ownable skins** — each species decays *differently* (Therak cinders, Vorlax datamosh, Kelous burnt-gilt, Nexor rose-wilt, Ekris silver-rust...). This is the mastery curve and the marketing surface: you read **WHO** before you see them in combat, you pick your soldier **by glow alone** across a dark hold, you pick a **map by its silhouette** against its species color. And because chaos can blind, **readability is an explicit, load-bearing system, not an afterthought** — the *Sensorium Clarity* governor (HUD) caps ghost density and protects the center; the *map hazard-contrast rule* offsets white-hot telegraph against blue/teal accents; the *menu reduced-motion mode* swaps every effect for a 120ms ash-wipe on an identical layout. Accessibility never reverts to a floating box; it surfaces numbers and solid silhouettes *inside the same grammar.*

> **The whole bible in one sentence:** *THE WANE — the energy of decay the faction is named for — is simultaneously your health, your ammo, your radar, your menu, your economy, and your map clock; it obeys one color law and three motion verbs across every screen; and it drains the world darker as it dies, so the player feels entropy on their own body instead of reading it off a poster.*

---

## PART 2 — PER-SURFACE SUMMARY
*Three views of the one substance*

### THE HUD — "THE FADE"
**There is no HUD; you are an alien reading combat through a Wane-sense, and your survival is how lit you still are.** Vitals live on your body — glowing **Wane Channels** in forearms/chest-core (your species accent) that extinguish extremity-inward, core dies last, hard integer HP etched beside the core for comp. Ammo is the **Charge-Rail** along the gun receiver, tick-notched, last 20% red-hot; ability cooldowns ride the *same gun-spine* (never an off-screen gauntlet). Damage is the **Edge-Bite** — an ashen dissolving bite torn from the screen edge nearest the threat, direction+magnitude in one cue, auto-knits in 1.2s (the only edge threat cue). The radar is **Wane-Ghosts** — enemies rendered in their species color, *decaying by sensory age* (crisp <0.3s → smeared ash by 1.5s), where **staleness IS the intel** and wallhacks are structurally impossible. Below 25% you enter **The Fade** — world desaturates but **contrast inverts to protect you** (threats stay saturated + rim-lit), capped short of monochrome, center 60% always clear. Healing is **The Re-Light** — Wane re-floods from the core outward, you and the world re-saturate: *decay, then defiance.*
*Must-ships: channels + rail + edge-bite + ghosts. First to scale on weak HW: world-fade. Channels and ghosts never drop.*

### THE FRONT-END — "THE HOLD, RUN BY GLYPH"
**You don't click a menu; you stand in the cargo hold of your own ship as the Wane eats it, and you spell your way across it.** Three diegetic stations, chord-navigated, whip-pan <120ms, **boot-to-Deploy in under 4s without the mouse** (and fully mouse/controller-clickable): **THE RACK** (`R`, loadout — locked weapons encased in crystal, you *scrape the Fall off* to own them, equip is a fast magnetic CLACK), **THE SQUAD** (`Q`, character — owned species stand lit by their own accent, unowned are empty husks: *ADAPT OR VANISH staged literally*), **THE TABLE** (`E`, deploy — slam a mode-plate, a dirty glitching hologram coughs up, pull the lever). The single un-copyable idea: **the Wane-rot crust IS the entire progression economy as one physical object** — season meter, matchmaking countdown, and lock-gate are the same crawling crust. Signature moment **"THE HOLD FALLS"**: the lever drops, rot eats the hull in real time, each ready fires a species-colored SNAP, the room crystallizes crisp for one breath, then the airlock blows and you fall into the match. *No flat panels. No alien-font slop. One etched sigil per station.*

### THE MAPS — "THE WANE LINE"
**Every map is one named real place caught at the second THE WANE begins eating it — a moment, not an arena.** A visible **collapse front** sweeps the map on a deterministic, learnable timeline (mirror-symmetry is *banned*; **determinism, not geometry, is the fairness guarantee**). Three zones: **Holding** (intact, saturated, safe), **The Line** (the kill-creation tear), **Fallen** (dark, drained, husk — standing in it applies **Fading**, desaturating *your own outline*). Built as **two material states of one structure** (pristine/fallen) with the line as the wipe — one place built twice, not 22 clones. The structural beat is **The Inversion** at 2/3: the dead core re-solidifies into a final-stand arena while the safe outer ring starts to fall inward — the match *ends in a different place than it began.* **Load-bearing Wane-veins** do double duty (only bright-veined geometry collapses, predictably; veins flow downhill to the contested core for wayfinding). Ship **8 silhouette-first hero maps**, one per species accent (Hollow Sun, Tidewreck, Glaciera Dry-Dock, Spirecrack...), picked like fighting-game stages. Every collapse gets a **mandatory 15s telegraph** — if we can't telegraph it, we cut it.

---

## PART 3 — THE BUILD ROADMAP
*UE 5.8, existing greybox third-person project (WanefallGreybox). Phased, with the vertical slice that proves the whole direction.*

### THE CORE TECH BET (build this first, everything else depends on it)
Before any surface: build **`UWaneSubsystem`** (a `UGameInstanceSubsystem`) + a **shared material function library** `MF_Wane`. This is the spine that guarantees Laws 1–2 are *enforced in code, not in art discipline*:

- **`FWaneSignature`** data asset per species (8): accent color (HDR, in-range ~1.0 so it survives bloom), decay-style enum (cinder/datamosh/burnt-gilt/rose-wilt...), erode/crystallize particle params, white-hot-telegraph offset value (Law 5 contrast rule).
- **`MF_Wane`** material function: inputs = `Saturation` (0–1 truth axis), `DecayPhase`, `AccentColor`, `Telegraph`. Outputs the desaturate-to-ash + edge-fray + white-hot behaviors. **Every surface material — channel, rail, ghost, menu prop, map vein, fallen ground — calls this one function.** This is how "saturation = truth" becomes physically impossible to violate.
- **Three Blueprint-callable motion macros** — `Crystallize(target)`, `Erode(target)`, `Snap(target, accentColor)` — driving UMG *and* world materials with identical timing curves. Law 4 made into reusable code.

Ship this with an 8-swatch test scene proving all 8 species decay correctly through the *same* function before building a single screen.

---

### PHASE 0 — Foundation (the spine above) + the HUD must-ships
*Goal: the in-combat read works and feels like nothing else. HUD before menus — it's the surface players spend 95% of their time in and the hardest to fake.*

1. **Wane Channels (vitals)** — skeletal-mesh emissive masks on the first-person/third-person arms + chest socket, driven by HP→segment-extinguish (extremity-inward, core last). UMG only for the etched integer HP anchored to the core socket via `WidgetComponent`. *Must-ship.*
2. **Charge-Rail (ammo)** — emissive UV-scroll mask on weapon receiver, tick-notched material, red-hot last 20%; ability cooldown node on the same spine. *Must-ship.*
3. **Edge-Bite (directional damage)** — post-process material on a screen-edge mask; damage-direction → which edge, magnitude → bite depth, `Erode` in / auto-`Crystallize` closed over 1.2s. Single cue, no chevrons. *Must-ship.*
4. **Wane-Ghosts (radar)** — the crown jewel. Custom-depth/stencil pass on occluded enemies → `MF_Wane` volumetric silhouette in species accent; **`SensoryAge` float per ghost drives Saturation↓ + smear** (crisp→ash 0–1.5s); footstep/gunfire events refresh nearest ghost's age. **`USensoriumClarity`** governor caps simultaneous ghosts + protects center 60%. *Must-ship.*

### PHASE 1 — The Fade + Re-Light (the emotional spine)
5. **The Fade** low-health post-process: desaturate world, **invert contrast** (enemies/tracers stay saturated + rim-lit), hard clarity floor center 60%, capped short of mono. *First thing to scale down on weak HW.*
6. **The Re-Light** heal: `Crystallize` flooding core→outward across the suit + world re-saturation. **This is the signature combat moment — prototype it early as the "does this feel special?" gut check.**

### PHASE 2 — The Hold (front-end) on the shared spine
7. Build the **3D hold scene** once (cargo-hold greybox, fixed station hotspots). Chord nav (`R`/`Q`/`E`/`Enter`) → camera whip-pan <120ms; `Esc` snap-schematic; full mouse/controller parity. **Deterministic layout independent of VFX** (Law 5 muscle-memory floor).
8. **The Wane-rot crust** as one mesh+`MF_Wane` instance, driven by a single `WaneProgress` float = season meter = matchmaking countdown = lock-gate. **Locked items encased in crystal; unlock = `Erode` the crust off → bare iron.** Real stat numbers in the snap-schematic; etched flavor on props.
9. **THE HOLD FALLS** deploy sequence (reuse `Snap` per-player ready, `Crystallize` the crisp breath, `Erode` to the airlock blow) → doubles as the load screen.

### PHASE 3 — The Wane Line (map system)
10. **`UWaneLineSubsystem`** — the deterministic collapse-front timeline (one front, advances ~1 lane/60–90s), zone queries (Holding/Line/Fallen), Fading debuff applying `Saturation`↓ to the *player's own* material.
11. **Pristine/Fallen dual-material map authoring workflow** + the line as a timeline-driven world-position wipe through `MF_Wane`. **Load-bearing Wane-veins** (only bright-veined geo registered as collapsible; veins flow to core for wayfinding).
12. **The Inversion** (2/3 trigger: core re-solidify + outer-ring fall-in) + **1–2 Entropy Events** per map with the **mandatory 15s telegraph** (accelerating vein-flare + ash + groan + white-hot flash). **Diegetic front-reader** replaces the minimap.

---

### THE VERTICAL SLICE — "THE EIGHT-SECOND PROOF"
*Build this first as the green-light artifact. It proves the entire bible in one unbroken take and exercises every core system.*

**One species (Vorlax, electric-blue), one map (Spirecrack), one full loop:**

> Boot → you're in **The Hold**. Tap `R`, scrape the crystal off a rifle (CLACK). `Q`, the blue Vorlax steps into the lamp. `E`, slam the plate, pull the lever → **THE HOLD FALLS** → load into **Spirecrack**. You fight forward in bright Holding ground; a **Wane-Ghost** of the enemy smears around a pillar (you read blue = Vorlax before you see them); an **Edge-Bite** tears the left screen-edge — you turn, trade, your **Channels** go dark extremity-inward, your **Charge-Rail** burns red-hot on the last rounds. At 8 HP you drop into **The Fade** — world greys, the enemy stays saturated. You hit heal: **The Re-Light** floods from your core, you wheel out lit. The spire's veins flare **white-hot** — 15s telegraph — it topples on its arc, sealing your lane. The **Inversion** fires; the dead core re-solidifies and pulls you into the last stand.

This single slice exercises: the `UWaneSubsystem` spine, `MF_Wane`, all three motion verbs, all four HUD must-ships, The Fade + Re-Light, the Hold's chord-nav + crust economy + deploy moment, and the Wane Line + veins + Inversion + telegraph. **If this slice feels authentic and reads in 200ms, the direction is proven and scales to 8 species × 8 maps by content, not new systems.**

---

## PART 4 — THE NOVELTY GUARANTEE
*Why this is not slop, and structurally cannot be copied*

The test for un-copyable is simple: **bolt the feature onto a generic shooter and watch it become nonsense.** Every signature here fails that test on purpose — it only works because the whole game is about entropy.

1. **Age-decaying Wane-Ghosts where staleness IS the data.** A radar that rots — sharp = live, smeared = stale — can only exist in a game whose core force is decay. It *also natively solves the wallhack-balance problem* (no perfect wallhacks because intel ages), which no bolted-on feature does. Lift it into Apex and it's incoherent.

2. **One energy, six jobs, eight decay signatures.** THE WANE is health AND ammo AND IFF AND menu AND economy AND map-clock — under one color law and three motion verbs — and each species decays *differently*. One readability grammar, eight ownable skins: the mastery curve, the marketing screenshots, and the localization-safe identity all live here. A template engine cannot ship a UI that is literally the game's lore-force.

3. **The Re-Light.** Every shooter shows you dying. Only WANEFALL makes *recovery* a visceral re-saturation of the man and the world from the core outward. Heal-as-rebirth instead of heal-as-bar-fill is "ADAPT OR VANISH" rendered in two seconds.

4. **The Wane-rot crust as the entire economy as one physical object.** Season meter, matchmaking timer, and lock-gate are the *same* crawling crust eating your ship; unlocking is *scraping the Fall off your iron;* owned is a body and locked is a husk. The most generic surfaces in F2P (store, battle-pass, character-select) become the *most* on-theme. Rip the crust out and the game's name stops meaning anything.

5. **You spell the room.** A diegetic 3D lobby navigated at fighting-game speed by keyboard chords — room as fiction, keyboard as nervous system. Lobby-as-room games are slow; chord menus are flat-abstract. Nobody fuses them; the fusion is the moat.

6. **The map is a verb, and you watch yourself vanish.** The stage is a place actively dying on a deterministic clock where the collapse IS the balance system; **determinism replaces symmetry** as the fairness guarantee (a genuinely defensible competitive-integrity argument, and the death of the 22-mandala tell); and the same saturation law that says "this wall is about to fall" says "*you* are about to fall" by draining your own silhouette. The theme is welded to the *perception layer*, not painted on top — so no reskin survives it.

**The anti-slop ledger (what we refused to ship):** corner-box universal HUD, red damage chevrons, see-through-wall heat-haze, full-screen monochrome, cracked-visor/tinnitus trailer-bait, chromatic aberration, generic premium-F2P purple card-grids, mysterious-alien-font typography, lobby-dolly wading, dog-tag mode-counting, per-weapon cinematic equip across 25 guns, glowing waypoint columns, 22 mirror-symmetric mandalas, stand-in-the-circle buff pools, RNG regrow cover, recycled battle-royale ring-beacons, and "no numbers for purity." Each was named, judged derivative or unreadable or unbuildable, and cut on the record.

> **One game. One force. THE WANE drains out of your body, your gun, the air, your ship, and the ground — under one law you learn once and read forever. That is the thing only WANEFALL could have built.**

---

Key build artifacts to create first, in the existing UE5 project at `C:/Users/developer/Documents/Unreal Projects/WanefallGreybox`:
- `Source/.../Wane/UWaneSubsystem.h/.cpp` (+ `FWaneSignature` DataAsset, 8 species instances)
- `Content/.../Materials/MF_Wane` (the single shared material function — Law 2 enforced in code)
- `Content/.../Wane/BPL_WaneMotion` (Crystallize / Erode / Snap macros — Law 4)
- HUD must-ship widgets/materials: `WBP_CoreHP`, `M_WaneChannel`, `M_ChargeRail`, `PP_EdgeBite`, `M_WaneGhost` + `USensoriumClarity`
- Then the vertical slice (Vorlax × Spirecrack) as the green-light artifact.