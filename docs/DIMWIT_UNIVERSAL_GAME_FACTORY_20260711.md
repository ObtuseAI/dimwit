# Dimwit Universal Game and Mobile Factory — 2026-07-11

## Outcome

Dimwit now has an engine-agnostic, plan-first production layer above its proven Unreal and Blender paths.
Every adapter uses the same build contract: detected project identity, target/profile, argv-only command,
confined outputs, timeout, complete logs, output hashes, explicit prerequisites, and a hard
`PROMOTED_TO_REVIEW` ceiling.

The factory does not claim that an absent engine is usable. It reports missing executables and SDKs as
blockers while preserving a stable adapter that becomes usable when the operator installs/configures the
official toolchain.

## Executable engine adapters

| Adapter | Project evidence | Targets | Local state on 2026-07-11 |
|---|---|---|---|
| Unreal | `.uproject` | Windows, Android | **Ready** — Unreal 5.8/UAT proven locally |
| Unity | `Assets` + `ProjectSettings/ProjectVersion.txt` | Windows, Linux, macOS, WebGL, Android, iOS, server, XR | **Blocked** — Unity Editor absent |
| Godot | `project.godot` + export preset | Windows, Linux, macOS, web, Android, iOS, server | **Blocked** — Godot Editor absent |
| Defold | `game.project` + `bob.jar` | Windows, Linux, macOS, HTML5, Android, iOS | **Blocked** — Bob absent |
| Bevy | `Cargo.toml` containing Bevy | Windows, Linux, macOS, web, server | **Ready** — Cargo installed |
| Web game | `package.json` containing Phaser, PlayCanvas, Babylon, Three, Pixi, or MelonJS | Web plus wrapped Android/iOS | **Ready** — Node/npm installed |
| CMake/native | `CMakeLists.txt` | Windows, Linux, macOS, Android, server, XR | **Ready** — CMake installed |
| Flutter/Flame | `pubspec.yaml` containing Flame | Desktop, web, Android, iOS | **Blocked** — Flutter absent |

Dimwit additionally detects GameMaker (`.yyp`), CryEngine (`.cryproject`), O3DE (`project.json`), and
Construct (`.c3p`) as `DETECTED_REFERENCE_ONLY`. They cannot execute until an audited command adapter is
provided through `dimwit.toolchains.engines.contracts.EngineAdapter`.

Official automation interfaces used by the adapters:

- Godot headless export: https://docs.godotengine.org/en/stable/tutorials/export/exporting_projects.html
- Unity command-line player builds: https://docs.unity3d.com/Manual/build-command-line.html
- Defold Bob builds/bundles: https://defold.com/manuals/bob/
- Unreal packaging: https://dev.epicgames.com/documentation/en-us/unreal-engine/packaging-your-project

## Mobile factory

Android is genuinely tool-ready on this machine:

- SDK root: `C:\Android\Sdk`
- Maximum installed platform API: 36
- Build-tools: 36.0.0
- NDK: 27.1.12297006
- Available: `adb`, `sdkmanager`, `aapt2`, `apksigner`, `zipalign`, and `jarsigner`
- Android package manifests must target at least API 35 under the dated 2026-07-11 policy and include ARM64.

iOS is `BLOCKED_REQUIRES_MACOS_XCODE` on this Windows host. Dimwit will not fabricate an IPA, archive,
simulator result, or signing proof. When executed on a Mac with Xcode, compatible engine adapters can export
iOS candidates; archive/export signing remains operator-only.

Primary platform references:

- Android command-line APK/AAB flow: https://developer.android.com/build/building-cmdline
- Unreal Android setup and API floor: https://dev.epicgames.com/documentation/unreal-engine/android-quick-start
- Apple command-line archive/export: https://developer.apple.com/library/archive/technotes/tn2339/_index.html

## Mobile-native validation

The factory defines 12 evidence lanes with 72 checks:

1. Touch and gestures
2. Adaptive layout, safe areas, notches, foldables, tablets, orientation
3. Cold start, backgrounding, resume, interruption, process death, save/restore
4. Frame pacing, thermal, battery, memory, startup, size, shader hitches
5. Touch/controller/keyboard/mouse/haptics/remapping
6. Offline, latency, loss, reconnect, cellular, Wi-Fi handoff
7. Accessibility
8. Localization and RTL
9. Permissions, privacy, consent, data safety, child safety
10. Store metadata and media
11. Crash/low-resource/upgrade/corrupt-save reliability
12. IAP, subscription, ads, restore-purchases, and parental gates

These are evidence requirements, not automatic PASS claims.

## Commands

```powershell
# Local adapter inventory
python dimwit.py engines
python dimwit.py engines --write

# Locate supported projects under a bounded root
python dimwit.py engines --scan "C:\path\to\games"

# Plan a build; execution is opt-in
python dimwit.py engines --project "C:\path\to\game" --target android --output "C:\Users\developer\Documents\Dimwit\artifacts\builds\game"

# Android/iOS SDK and quality audit
python dimwit.py mobile
python dimwit.py mobile --write

# Plan a manifest-gated mobile candidate
python dimwit.py mobile --project "C:\path\to\game" --target android --output "C:\Users\developer\Documents\Dimwit\artifacts\mobile\game" --manifest config\mobile_manifest.example.json
```

The example manifest is deliberately incomplete for store metadata and uses example identifiers. It must be
copied and replaced with verified project facts before a real candidate is built.

## Closed boundaries

- No engine, SDK, package, weights, or template was downloaded.
- No distribution signing secret is accepted by the autonomous lane.
- No App Store, Play Console, TestFlight, or other store upload is exposed.
- No attached Android device is touched without an explicit device identifier and execution request.
- No iOS readiness is claimed on Windows.
- No build may promote itself past `PROMOTED_TO_REVIEW`.

## Validation evidence

- Scoped Ruff: PASS.
- Full Python suite: 575 passed, 14 existing Pillow deprecation warnings, 0 failed.
- Capability registry: 26/26 targets resolved.
- Engine audit artifact: `artifacts/toolchains/universal/engine_audit.json`.
- Mobile audit artifact: `artifacts/mobile/mobile_audit.json`.
- Browser smoke: Engines and Mobile views rendered and exposed the expected 8 adapters, Android SDK API 36,
  iOS Mac/Xcode blocker, 12 quality lanes, and 72 checks.
- Mandatory full validator after self-metrics refresh: 255 PASS, 7 FAIL, 2 BLOCKED, 0 REJECTED. Remaining
  non-passes are pre-existing stale/live animation, front-door, optics, runtime, package, performance, balance,
  progression, and settings evidence.
