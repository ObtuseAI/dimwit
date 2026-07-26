"""AUDIO_FOUNDATION_V1 leg 4 — procedural WANE SFX synthesizer + provenance ledger.

Always-available, offline, $0, license-clean (self-authored) stinger generator. Produces one 48 kHz
16-bit mono WAV per cue declared in the cue-coverage manifest, loudness-normalized toward its bus
target (so the leg-3 loudness gates pass on REAL assets, not placeholders), and records a provenance
entry per asset (license=self-authored, generator, sha256). Optional operator-provided CC0 files can
be dropped into artifacts/audio/ with a sidecar (see check_sfx_provenance) — network fetch (Freesound)
is operator-gated and NOT performed here.

stdlib only (math, wave, struct, hashlib, json). Timbre per cue is deterministic (no RNG) so re-runs
are byte-idempotent and the sha256 ledger is stable.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import wave
from pathlib import Path

from dimwit.audio_loudness import analyze_wav

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "artifacts" / "audio"
PROVENANCE = AUDIO_DIR / "sfx_provenance.json"
SR = 48000
_TP_CEIL_DBTP = -1.0
_SYNTH_TP_TARGET = -1.5  # leave headroom under the ceiling

# Per-cue voice: (base_hz, kind, dur_s, sweep_ratio). kind in {sine, fm, noise, chord, sweep}.
# Deterministic — same params -> same bytes.
CUE_VOICES = {
    "cue_hit_confirm":    (880.0,  "fm",    0.10, 1.0),
    "cue_downed":         (440.0,  "sweep", 0.28, 0.5),
    "cue_finished":       (330.0,  "chord", 0.32, 1.0),
    "cue_eliminated":     (523.0,  "chord", 0.40, 1.5),
    "cue_score":          (1200.0, "sine",  0.08, 1.0),
    "cue_death_watch":    (110.0,  "sine",  0.45, 1.0),
    "cue_respawn":        (392.0,  "sweep", 0.35, 2.0),
    "cue_round_start":    (523.0,  "sweep", 0.30, 1.5),
    "cue_round_complete": (392.0,  "chord", 0.50, 1.0),
    "cue_bot_fire":       (1600.0, "noise", 0.06, 0.4),
    "cue_taunt":          (196.0,  "fm",    0.40, 1.2),
    "cue_taunt_reject":   (147.0,  "sweep", 0.30, 0.6),
    "cue_ui_confirm":     (1046.0, "sine",  0.06, 1.0),
    "cue_ui_back":        (784.0,  "sine",  0.06, 0.8),
}


def _env(i: int, n: int) -> float:
    """Percussive attack + exponential decay envelope."""
    t = i / n
    attack = min(1.0, t / 0.02) if t < 0.02 else 1.0
    decay = math.exp(-3.5 * t)
    return attack * decay


def _render(base: float, kind: str, dur: float, sweep: float) -> list[float]:
    n = int(dur * SR)
    out = [0.0] * n
    # deterministic pseudo-noise (LCG) for the noise voice
    seed = 0x2545F491
    for i in range(n):
        t = i / SR
        f = base * (1.0 + (sweep - 1.0) * (i / n)) if kind == "sweep" else base
        if kind == "sine":
            s = math.sin(2 * math.pi * base * t)
        elif kind == "fm":
            s = math.sin(2 * math.pi * base * t + 3.0 * math.sin(2 * math.pi * base * 0.5 * t))
        elif kind == "sweep":
            s = math.sin(2 * math.pi * f * t)
        elif kind == "chord":
            s = (math.sin(2 * math.pi * base * t)
                 + 0.6 * math.sin(2 * math.pi * base * 1.5 * t)
                 + 0.4 * math.sin(2 * math.pi * base * 2.0 * t)) / 2.0
        elif kind == "noise":
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            s = ((seed / 0x3FFFFFFF) - 1.0) * math.sin(2 * math.pi * base * t)
        else:
            s = math.sin(2 * math.pi * base * t)
        out[i] = s * _env(i, n)
    return out


def _write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767.0)
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def synth_cue(cue_id: str, target_lufs: float, out_dir: Path = AUDIO_DIR) -> dict:
    """Synthesize one cue WAV normalized toward target_lufs with true-peak headroom. Returns a record."""
    base, kind, dur, sweep = CUE_VOICES.get(cue_id, (440.0, "sine", 0.15, 1.0))
    samples = _render(base, kind, dur, sweep)
    peak = max((abs(s) for s in samples), default=0.0) or 1.0
    # normalize to a safe true-peak first
    samples = [s / peak * (10 ** (_SYNTH_TP_TARGET / 20.0)) for s in samples]
    wav = out_dir / f"{cue_id}.wav"
    _write_wav(wav, samples)
    # one loudness-correction pass toward the bus target (tolerance is generous; 1 pass suffices)
    meas = analyze_wav(wav)
    if meas["lufs"] > -math.inf and isinstance(target_lufs, (int, float)):
        gain_db = target_lufs - meas["lufs"]
        # never let the correction push true-peak over the ceiling
        headroom = _TP_CEIL_DBTP - meas["true_peak_dbtp"]
        gain_db = min(gain_db, headroom)
        g = 10 ** (gain_db / 20.0)
        samples = [s * g for s in samples]
        _write_wav(wav, samples)
        meas = analyze_wav(wav)
    return {"cue": cue_id, "wav": str(wav), "lufs": meas["lufs"],
            "true_peak_dbtp": meas["true_peak_dbtp"], "sha256": _sha256(wav)}


def _bus_target_for(cue_id: str, cue_manifest: dict, bus_manifest: dict) -> float:
    """Resolve a cue's bus target LUFS from the manifests (default -18)."""
    bus = None
    for group in ("combat_cues", "ui_cues"):
        for _k, decl in (cue_manifest.get(group) or {}).items():
            if isinstance(decl, dict) and decl.get("cue") == cue_id:
                bus = decl.get("bus")
    buses = (bus_manifest or {}).get("buses") or {}
    b = buses.get(bus) if bus else None
    return b.get("target_lufs", -18.0) if isinstance(b, dict) else -18.0


def synthesize_all(cue_manifest: dict, bus_manifest: dict, out_dir: Path = AUDIO_DIR) -> dict:
    """Synthesize every cue in the manifest + write the provenance ledger. Returns the ledger dict."""
    cues = set()
    for group in ("combat_cues", "ui_cues"):
        for _k, decl in (cue_manifest.get(group) or {}).items():
            if isinstance(decl, dict) and decl.get("cue"):
                cues.add(decl["cue"])
    ledger = {}
    for cue_id in sorted(cues):
        rec = synth_cue(cue_id, _bus_target_for(cue_id, cue_manifest, bus_manifest), out_dir)
        ledger[cue_id] = {
            "license": "self-authored",
            "source": "dimwit.pipelines.audio_sfx procedural synth (CC0-equivalent)",
            "generator": "audio_sfx.synth_cue",
            "sha256": rec["sha256"],
            "lufs": rec["lufs"],
            "true_peak_dbtp": rec["true_peak_dbtp"],
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger


# ---- provenance gate (leg 4) ---------------------------------------------------------------------
_VALID_LICENSES = {"self-authored", "CC0", "operator-provided"}


def check_sfx_provenance(cue_manifest: dict, provenance: dict, audio_dir: Path) -> dict:
    """Every cue backed by a real WAV must carry a provenance record with a valid license + a sha256
    matching the file on disk. Placeholder-only cues (no WAV yet) are not required to be provenanced.
    Fail-closed: an un-provenanced or sha-mismatched real asset blocks.
    """
    issues: list[str] = []
    provenance = provenance or {}
    cues = {}
    for group in ("combat_cues", "ui_cues"):
        for _k, decl in (cue_manifest.get(group) or {}).items():
            if isinstance(decl, dict) and decl.get("cue"):
                cues[decl["cue"]] = decl
    checked = 0
    for cue_id in sorted(cues):
        wav = audio_dir / f"{cue_id}.wav"
        if not (wav.exists() and wav.stat().st_size > 44):
            continue  # placeholder — leg-2 resolvable gate handles it
        checked += 1
        rec = provenance.get(cue_id)
        if not isinstance(rec, dict):
            issues.append(f"{cue_id}: real WAV with no provenance record")
            continue
        if rec.get("license") not in _VALID_LICENSES:
            issues.append(f"{cue_id}: license {rec.get('license')!r} not in {sorted(_VALID_LICENSES)}")
        want = hashlib.sha256(wav.read_bytes()).hexdigest()
        if rec.get("sha256") != want:
            issues.append(f"{cue_id}: provenance sha256 mismatch (asset changed without re-ledgering)")
    return {"passed": not issues, "issues": issues, "checked": checked}
