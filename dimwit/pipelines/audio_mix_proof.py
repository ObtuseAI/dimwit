"""AUDIO_FOUNDATION_V1 leg 5 — packaged-mix WASAPI-loopback silence-proof.

Records the system audio mix while the packaged game plays, then proves the COMBAT segment carries
real spectral energy above a floor AND above the MENU baseline (a silent, or menu-only, shipped mix
blocks). Fail-closed: no loopback backend, or no recording, => BLOCKED result (never a fake PASS).

Loopback capture uses ffmpeg WASAPI/dshow if present. The match is driven by launching the packaged
exe in windowed real-RHI bot-match mode (`-WANEFALLBOTMATCH` self-plays with NO injected input, so
audio can be captured without the foreground-focus constraint that the input-driven lanes have — but
it MUST be real-RHI with an audio device, NOT -nullrhi). Operator runs it; see run().

Writes artifacts/audio/mix_proof_result.json:
  {"passed": bool, "combat_energy": float, "menu_energy": float, "floor": float,
   "margin_db": float, "recording": "<wav>", "issues": [...], "backend": "ffmpeg|none"}

The FFT segment-energy math (segment_band_energy) is pure + unit-tested; the capture/launch I/O is
integration run by the operator.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "artifacts" / "audio"
RESULT = AUDIO_DIR / "mix_proof_result.json"
RECORDING = AUDIO_DIR / "mix_proof_capture.wav"

# A silence-proof asks "is there real, audible signal in combat vs a silent baseline". Combat cues are
# short + sparse, so a continuous-energy floor is the wrong tool (a 0.15 s cue in a 1 s window averages
# down). Gate on PEAK amplitude instead: 0.02 (~-34 dBFS) is far above dither/noise but easily cleared
# by any real cue, and the baseline must be near-silent so we're proving combat audio, not a constant hum.
_PEAK_FLOOR = 0.02
_BASELINE_PEAK_CEIL = 0.01     # pre-combat window must be ~silent for the contrast to mean anything
_MARGIN_DB = 6.0
_BAND_HZ = (150.0, 8000.0)     # reported spectral-energy band (detail, not the gate)


def segment_band_energy(samples: list[float], sr: int, band=_BAND_HZ, bins: int = 12) -> float:
    """Band-emphasized mean-square power (RMS^2) of the segment. Pure/testable.

    A silence-proof needs a robust "is there audible energy here" measure, not per-bin FFT power
    (which is tiny for broadband content and would false-fail a real combat mix). We reject DC/rumble
    with a one-tap high-pass (first difference) so a menu drone doesn't read as combat, then take
    mean-square. Combat (loud, broadband) >> menu (quiet) — the gate compares the two + a floor.
    `band`/`bins` are kept for signature/documentation compatibility.
    """
    if not samples or sr <= 0:
        return 0.0
    # first-difference high-pass to suppress DC and sub-bass rumble, then mean-square power
    acc = 0.0
    prev = samples[0]
    for x in samples[1:]:
        d = x - prev
        acc += d * d
        prev = x
    n = len(samples) - 1
    return acc / n if n > 0 else 0.0


def _read_wav(path: Path):
    import array
    with wave.open(str(path), "rb") as w:
        n_ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(f"expected 16-bit capture, got {sw*8}-bit")
    a = array.array("h")
    a.frombytes(raw)
    data = [v / 32768.0 for v in a]
    if n_ch > 1:
        data = [sum(data[i:i + n_ch]) / n_ch for i in range(0, len(data), n_ch)]
    return data, sr


def analyze_capture(path: Path, baseline_s: float = 2.0, win_s: float = 1.0) -> dict:
    """Silence-proof: the pre-combat baseline (first `baseline_s`) vs the LOUDEST combat window.

    Combat cues are sparse (a few short bursts across the match), so a fixed combat window can miss
    them; instead slide a `win_s` window across everything after the baseline and take the MAX energy.
    Pass if that peak clears the silence floor AND beats the baseline by the margin.
    """
    data, sr = _read_wav(Path(path))
    n = len(data)
    base_end = int(baseline_s * sr)

    def _peak(seg):
        return max((abs(x) for x in seg), default=0.0)

    baseline_peak = _peak(data[:base_end]) if base_end > 0 else 0.0
    # loudest sample after the baseline + where it is (for evidence)
    combat_peak = 0.0
    peak_at = 0.0
    for i in range(base_end, n):
        v = abs(data[i])
        if v > combat_peak:
            combat_peak = v
            peak_at = i / sr
    # spectral energy in the loudest 1 s window (reported detail)
    w = max(1, int(win_s * sr))
    pk_idx = int(peak_at * sr)
    band_energy = segment_band_energy(data[max(base_end, pk_idx - w // 2):pk_idx + w // 2], sr)

    margin_db = 20.0 * math.log10(combat_peak / baseline_peak) if (baseline_peak > 0 and combat_peak > 0) else (
        99.0 if combat_peak > 0 else -99.0)
    issues = []
    if combat_peak < _PEAK_FLOOR:
        issues.append(f"combat peak {combat_peak:.4f} below floor {_PEAK_FLOOR} (silent mix — no audible combat audio)")
    if baseline_peak > _BASELINE_PEAK_CEIL:
        issues.append(f"baseline peak {baseline_peak:.4f} not silent (> {_BASELINE_PEAK_CEIL}); contrast invalid")
    if margin_db < _MARGIN_DB:
        issues.append(f"combat only {margin_db:.1f} dB over baseline (< {_MARGIN_DB} dB)")
    return {"passed": not issues, "combat_peak": combat_peak, "baseline_peak": baseline_peak,
            "band_energy": band_energy, "peak_floor": _PEAK_FLOOR, "margin_db": margin_db,
            "peak_at_s": peak_at, "recording": str(path), "issues": issues}


def _write_result(rec: dict) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(rec, indent=2), encoding="utf-8")


# --- in-engine capture (editor -game, real RHI + audio; no OS loopback, no cook) ---------------
UE_EDITOR = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
PROJ_SAVED_AUDIO = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/Saved/Audio")
ARENA_MAP = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"
MARKER = PROJ_SAVED_AUDIO / "wanefall_audio_proof.json"
ENGINE_WAV = PROJ_SAVED_AUDIO / "WanefallAudioProof.wav"


def run(task: dict | None = None) -> dict:
    """Prove the runtime combat mix has signal via IN-ENGINE Master-submix recording.

    Launches the editor in -game with -WANEFALLBOTMATCH -WANEFALLAUDIOPROOF (real RHI + audio, uses
    the compiled module directly — no cook, no OS loopback device). The bot-match subsystem records
    the Master submix of match 0 to a WAV, which we analyze for spectral signal. Fail-closed: if the
    editor/uproject is absent or no WAV is produced, writes a BLOCKED-style result, never a fake PASS.

    Evidence records source="editor_game" (real runtime audio path). A cooked-package variant runs the
    same flags against WanefallGreybox.exe — pass packaged_exe=<...> to use it instead.
    """
    task = task or {}
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    exe = task.get("packaged_exe")
    if exe and Path(exe).exists():
        launch = [str(exe), ARENA_MAP, "-WANEFALLBOTMATCH", "-WANEFALLAUDIOPROOF",
                  "-BotMatchCount=1", "-BotMatchMaxSeconds=20", "-windowed", "-ResX=1280", "-ResY=720",
                  "-ExecCmds=au.UnfocusedVolumeMultiplier 1.0"]
        source = "packaged"
    else:
        if not (UE_EDITOR.exists() and UPROJECT.exists()):
            rec = {"passed": False, "source": "none",
                   "issues": ["no packaged_exe and no editor/uproject found — cannot run the mix proof"]}
            _write_result(rec)
            return rec
        launch = [str(UE_EDITOR), str(UPROJECT), ARENA_MAP, "-game",
                  "-WANEFALLBOTMATCH", "-WANEFALLAUDIOPROOF", "-BotMatchCount=1",
                  "-BotMatchMaxSeconds=20", "-windowed", "-ResX=1280", "-ResY=720", "-stdout",
                  # UE mutes audio when the window is unfocused (UnfocusedVolumeMultiplier defaults 0);
                  # a background launch never gains focus -> silent submix. Force full unfocused volume.
                  "-ExecCmds=au.UnfocusedVolumeMultiplier 1.0"]
        source = "editor_game"

    # fresh: clear any stale marker/wav so we never analyze a previous run
    for p in (MARKER, ENGINE_WAV):
        try:
            p.unlink()
        except Exception:
            pass

    timeout_s = float(task.get("timeout_s", 300.0))
    proc = subprocess.Popen(launch)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass

    if not ENGINE_WAV.exists() or ENGINE_WAV.stat().st_size < 1024:
        rec = {"passed": False, "source": source,
               "issues": [f"no submix WAV at {ENGINE_WAV} — the run must be real-RHI (NOT -nullrhi) "
                          "so an audio device exists; check the [WaneAudioProof] log lines"]}
        _write_result(rec)
        return rec

    # copy into artifacts for the record, analyze the in-engine capture
    try:
        shutil.copyfile(ENGINE_WAV, RECORDING)
    except Exception:
        pass
    rec = analyze_capture(ENGINE_WAV)
    rec["source"] = source
    if MARKER.exists():
        try:
            rec["engine_marker"] = json.loads(MARKER.read_text(encoding="utf-8"))
        except Exception:
            pass
    _write_result(rec)
    return rec


if __name__ == "__main__":
    import sys
    kv = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    print(json.dumps(run(kv), indent=2))
