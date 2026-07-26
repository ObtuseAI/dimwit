# WANEFALL Real-Game Validation Loop Design

## Goal

Build Dimwit's first authoritative real-game truth spine: a repeatable loop that launches or attaches to the actual WANEFALL game window, captures what a player sees, validates runtime-visible state, writes fail-closed evidence, and gives every autonomous pipeline a shared validation target.

Dimwit may design, build, test, validate, learn, and retry autonomously up to `PROMOTED_TO_REVIEW`. `HUMAN_ACCEPTED` and `PROMOTED_TO_ACTIVE_SLICE` remain operator-only states.

## Current Context

The live Unreal project is `C:\Users\developer\Documents\Unreal Projects\WanefallGreybox`.

The autonomous engine is `C:\Users\developer\Documents\Dimwit`.

The work hub and handoff destination is `C:\Users\developer\Desktop\Shared Folder`.

Both live folders are not git repositories in this environment, so design and implementation artifacts are written in place and mirrored to the Shared Folder. No commit is created unless explicitly requested.

Dimwit already has many validators and pipelines, but several judge proxies: headless captures, static files, constructor state, stale result JSONs, or isolated proof artifacts. The next durable step is one real-game pipeline that every other build loop can depend on.

## Design Choice

Use a dedicated `real_game_validation` production pipeline rather than embedding the loop directly inside the generic validation registry.

This keeps the real-game runtime workflow focused and reusable:

- `scripts/pipeline/run_pipeline.py real_game_validation default` can run a targeted pass.
- `scripts/pipeline/run_director.py` can schedule it as a capability.
- `scripts/pipeline/run_validation.py` can consume its result artifact through new fail-closed validators.
- Other pipelines can call it after generating or repairing an asset.

## Architecture

### Pipeline Unit

Create `dimwit/pipelines/real_game_validation.py`.

Responsibilities:

- Locate the WANEFALL project and Unreal executable.
- Optionally kill stale Unreal/game processes when explicitly enabled by task config.
- Launch standalone `WanefallGreybox` in windowed mode, or attach to an existing game window.
- Capture a still frame and a short frame burst from the actual game window.
- Analyze captures with deterministic pixel metrics.
- Run structural runtime checks from available evidence.
- Scrape recent Unreal logs for fatal/error signals.
- Emit a single JSON result at `artifacts/real_game_validation/real_game_validation_result.json`.
- Return a pipeline result that can reach `PROMOTED_TO_REVIEW` only when all V1 blocker checks pass.

The pipeline must not weaken existing validators and must not fabricate evidence. If a window cannot be found, capture is blank, logs are unavailable, or the launch fails, it returns `BLOCKED` with the reason.

### Capture Layer

Reuse `dimwit.desktop_eyes.DesktopEyes`.

Capture outputs:

- `artifacts/real_game_validation/still.png`
- `artifacts/real_game_validation/frames/frame_000.png` through frame burst
- Cropped subject images are out of V1 scope and belong to the semantic-optics follow-on slice.

V1 uses windowed standalone launch by default:

```text
C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe
C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject
/Game/Wanefall/Maps/Wanefall_Lobby?game=/Script/WanefallGreybox.WanefallLobbyGameMode
-game -windowed -ResX=1280 -ResY=720 -nosound
```

The launch command is explicit in the result JSON.

### Deterministic Validators

V1 validates what it can prove without semantic vision:

- `window_found`: a non-minimized `WanefallGreybox` or configured title window exists.
- `still_nonblank`: still frame has size, contrast, and luminance above floors.
- `frame_burst_nonblank`: at least two frames exist and are nonblank.
- `motion_or_stable_runtime`: if motion driving is enabled, frame delta must exceed the motion floor; if no input driving is requested, the result records stable-runtime mode instead of pretending motion was tested.
- `hud_region_not_blank`: center/upper HUD regions have nonzero contrast. V1 records a weak structural signal; deeper HUD element classification stays in existing HUD validators.
- `placeholder_geometry_signal`: detect visible engine-placeholder-like giant simple shapes by pixel heuristics only as a blocker when the signal is strong; deeper actor-component proof is a V2 UE runtime probe.
- `log_fatal_error_count`: recent logs do not contain new fatal/error bursts for the run window.

The output separates `checks` from `observations` so uncertain signals never masquerade as proof.

### Integration With Validation Registry

Add a new domain, `real_game_runtime`, to `dimwit/pipelines/validation_registry.py`.

V1 validators consume `artifacts/real_game_validation/real_game_validation_result.json`:

- `real_game_capture_fresh`
- `real_game_window_nonblank`
- `real_game_no_fatal_log_burst`
- `real_game_runtime_not_placeholder_dominated`

If the result is missing or stale, validators are `BLOCKED`.

### Director Integration

Register the pipeline in `dimwit/pipelines/__init__.py`.

Add a default task in `config/director_tasks.json` if the file already exists and the addition is safe:

```json
{
  "pipeline": "real_game_validation",
  "asset_id": "wanefall_default_lobby",
  "priority": 10,
  "expected_value": 3,
  "cost": 1,
  "fail_penalty": 0
}
```

If the task file format is incompatible, leave it unchanged and document the run command in the session report.

### Error Handling

All errors are explicit:

- missing Unreal executable: `BLOCKED`
- missing uproject: `BLOCKED`
- launch timeout: `BLOCKED`
- capture file missing: `BLOCKED`
- blank capture: `REJECTED` if capture exists but proves unusable
- fatal/error log burst: `REJECTED`
- validator input absent: `BLOCKED`

No fallback silently turns a failed live run into a PASS.

### Testing

Use TDD for the pure analysis code:

- A blank synthetic image must fail nonblank analysis.
- A high-contrast synthetic image must pass nonblank analysis.
- Missing result JSON must block the registry validator.
- A result JSON with `suite_pass: true` and fresh timestamp must pass the capture freshness validator.

Live Unreal launch is validated by running the pipeline. If the local machine cannot launch the game within the turn, the outcome is reported as `BLOCKED` with the exact blocker.

### Reporting

Every run writes:

- JSON result in `C:\Users\developer\Documents\Dimwit\artifacts\real_game_validation`
- Human-readable session report copied to `C:\Users\developer\Desktop\Shared Folder`

The report states:

- command run
- launch mode
- artifact paths
- validation verdict
- blockers
- no operator-only state was written

## V1 Scope Boundary

Included:

- real game launch or attach
- actual window capture
- deterministic image checks
- log scan
- validation-registry gates
- director/pipeline registration
- Shared Folder report

Deferred:

- semantic vision ensemble
- full runtime actor/component enumeration after BeginPlay
- per-asset import and capture mutation loop
- first-person weapon pose semantic judging
- full HUD OCR/classification
- automatic active-slice promotion

Those are follow-on slices that plug into this same real-game truth spine.
