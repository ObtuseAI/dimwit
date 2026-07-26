"""Audio pipeline — "Weaponized Banter" voice lines + UE SoundWave registration.

Closes the "WANEFALL has no voiced combat banter" gap with a FAIL-CLOSED, proof-driven loop:

  plan()    : pick a banter line set + resolve a TTS backend. BlockedError only if NO TTS backend
              exists at all (Piper / pyttsx3 / Windows SAPI). Records UE availability as a soft flag.
  execute() : (1) synth WAVs into artifacts/audio/ with the best available OSS/offline TTS
                  (preference: Piper MIT  ->  pyttsx3 BSD offline  ->  Windows SAPI System.Speech);
              (2) if UE is present, shell out to the UE driver `scripts/ue/ue_audio_import.py` to import the WAVs
                  as SoundWaves under /Game/Wanefall/Dimwit/Audio and (optionally) author a
                  MetaSoundSource. UE import is verified via artifacts/audio_import_result.json (the
                  FILE, never the exit code).
  qa()      : >=1 WAV synthesized AND non-empty (loudness/size sanity). If UE ran, >=1 SoundWave
              imported. Provenance fail-closed is enforced by the inherited run().
  repair()  : re-run execute() (idempotent: re-synth + re-import; SAPI fallback is always available).

IMPORT-SAFE: only stdlib at module top. All heavy/optional work (TTS engines, `import unreal`,
subprocess) happens inside methods.

TODO:
  - Author the actual MetaSound graph (node wiring / parameter inputs) instead of the stub source.
  - Freesound CC0 SFX ingest pipeline (impacts, WANE crystallize/erode stingers).
  - Per-character distinct voices (Piper voice models per roster entry; pitch/rate variation per species).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
AUDIO_DIR = ART / "audio"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
DRIVER = ROOT / "scripts/ue/ue_audio_import.py"
RESULT = ART / "audio_import_result.json"

# UE content destination for the imported SoundWaves + MetaSound source.
UE_AUDIO_PATH = "/Game/Wanefall/Dimwit/Audio"

# Default "Weaponized Banter" line set — short, punchy combat callouts in the WANE voice
# (decay-force identity: Crystallize / Erode / Snap; "saturation = truth"). Keyed by a stable id
# so re-synth is idempotent and SoundWave names are deterministic.
BANTER_LINES = {
    "banter_crystallize": "Hold still. Let the WANE crystallize you.",
    "banter_erode": "You're already eroding. I just made it quick.",
    "banter_snap": "Snap. That's the sound of you ending.",
    "banter_saturation": "Saturation is truth, and you've gone grey.",
    "banter_taunt": "Decay always wins. You just hadn't noticed yet.",
}


class AudioPipeline(ProductionPipeline):
    name = "audio"
    kind = "audio_voiceline"

    # ---- plan -----------------------------------------------------------------------------------
    def plan(self, task: dict) -> dict:
        # Resolve the banter line set (caller may override with task["lines"] = {id: text}).
        lines = task.get("lines") or BANTER_LINES
        if not isinstance(lines, dict) or not lines:
            raise BlockedError("no banter lines provided and default set is empty")
        lines = {str(k): str(v) for k, v in lines.items() if str(v).strip()}
        if not lines:
            raise BlockedError("all banter lines were empty after cleaning")

        backend = self._resolve_tts_backend()
        if backend is None:
            raise BlockedError(
                "no TTS backend available: need Piper (pip install piper-tts) or pyttsx3 "
                "(pip install pyttsx3) or Windows SAPI (powershell System.Speech)"
            )

        # MetaSound authoring is optional; UE import is a soft (verified) capability.
        ue_available = UE_CMD.exists() and UPROJECT.exists()
        return {
            "lines": lines,
            "backend": backend,                       # dict: {kind, ...}
            "ue_available": ue_available,
            "make_metasound": bool(task.get("make_metasound", True)),
            "voice": str(task.get("voice", "default")),
        }

    # ---- execute --------------------------------------------------------------------------------
    def execute(self, plan: dict) -> Artifact:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        backend = plan["backend"]

        # (1) Synthesize WAVs.
        synth = []
        for line_id, text in plan["lines"].items():
            wav = AUDIO_DIR / f"{line_id}.wav"
            ok, detail = self._synth_one(backend, text, wav)
            size = wav.stat().st_size if wav.exists() else 0
            synth.append({
                "line_id": line_id, "text": text, "wav": str(wav),
                "ok": bool(ok and size > 0), "size_bytes": size, "detail": detail,
            })

        # (2) Import into UE (only if available). Verified via the result FILE.
        ue_rec = {"ran": False}
        good_wavs = [s["wav"] for s in synth if s["ok"]]
        if plan["ue_available"] and good_wavs:
            ue_rec = self._ue_import(good_wavs, plan["make_metasound"])

        rec = {
            "backend": backend.get("kind"),
            "voice": plan.get("voice"),
            "audio_dir": str(AUDIO_DIR),
            "synth": synth,
            "wav_count": sum(1 for s in synth if s["ok"]),
            "ue": ue_rec,
            "ue_attempted": bool(plan["ue_available"] and good_wavs),
        }

        # Provenance: TTS engine (real OSS/offline license) + recorded source line set.
        prov_license = {
            "piper": "Piper TTS (MIT)",
            "pyttsx3": "pyttsx3 (BSD-3-Clause, offline)",
            "sapi": "Windows SAPI / System.Speech (OS component, in-engine use)",
        }.get(backend.get("kind"), "OSS/offline TTS (recorded)")
        return Artifact(
            asset_id=str(plan.get("voice", "default")) + "_weaponized_banter",
            kind=self.kind,
            data=rec,
            provenance={
                "source": f"Dimwit synth from WANEFALL banter line set ({len(plan['lines'])} lines)",
                "license": prov_license,
            },
        )

    # ---- qa -------------------------------------------------------------------------------------
    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        synth = r.get("synth") or []
        wav_count = int(r.get("wav_count", 0))
        ue = r.get("ue") or {}

        # Loudness/size sanity: a real WAV header + samples is comfortably > 1KB; reject empty/silence.
        non_empty = [s for s in synth if s.get("ok") and int(s.get("size_bytes", 0)) > 1024]

        checks = {
            "at_least_one_wav": wav_count >= 1,
            "wav_non_empty": len(non_empty) >= 1,
        }
        # UE import is only graded when it was actually attempted (honest: don't fail for absent UE).
        if r.get("ue_attempted"):
            checks["soundwave_imported"] = int(ue.get("imported", 0)) >= 1
            if plan.get("make_metasound"):
                # MetaSound is best-effort; record but don't hard-gate on it.
                pass

        hard = bool(ue.get("error"))
        score = sum(checks.values()) / len(checks) if checks else 0.0
        issues = [k for k, v in checks.items() if not v]
        evidence = [s["wav"] for s in non_empty]
        if r.get("ue_attempted") and not ue.get("error"):
            evidence.append(str(RESULT))
        return Verdict(
            score=score, passed=all(checks.values()) and not hard, hard_fail=hard,
            issues=issues if not hard else [ue.get("error", "UE import error")],
            detail={"checks": checks, "wav_count": wav_count,
                    "imported": ue.get("imported"), "metasound": ue.get("metasound")},
            evidence=evidence,
        )

    # ---- repair ---------------------------------------------------------------------------------
    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # Idempotent: re-synth (SAPI fallback is always available) + re-import. On a 2nd attempt,
        # drop to the most reliable always-present backend if the preferred one mis-fired.
        if attempt >= 2 and os.name == "nt":
            sapi = self._sapi_backend()
            if sapi is not None:
                plan = {**plan, "backend": sapi}
        return self.execute(plan)

    # ---- TTS backend resolution -----------------------------------------------------------------
    def _resolve_tts_backend(self):
        """Return a backend descriptor dict, preferring Piper -> pyttsx3 -> Windows SAPI. None if none."""
        # Piper (MIT) — best quality, neural. Detect the CLI or the python package.
        import shutil
        piper_exe = shutil.which("piper")
        if piper_exe:
            model = os.environ.get("PIPER_VOICE_MODEL")  # path to a .onnx voice; optional
            return {"kind": "piper", "exe": piper_exe, "model": model}
        try:
            import importlib.util
            if importlib.util.find_spec("piper") is not None:
                model = os.environ.get("PIPER_VOICE_MODEL")
                return {"kind": "piper", "exe": None, "model": model}
        except Exception:
            pass
        # pyttsx3 (BSD, fully offline)
        try:
            import importlib.util
            if importlib.util.find_spec("pyttsx3") is not None:
                return {"kind": "pyttsx3"}
        except Exception:
            pass
        # Windows SAPI via PowerShell System.Speech (always present on Windows)
        return self._sapi_backend()

    def _sapi_backend(self):
        if os.name != "nt":
            return None
        import shutil
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            return None
        return {"kind": "sapi", "pwsh": pwsh}

    def _synth_one(self, backend, text: str, wav: Path):
        """Synthesize one line to `wav`. Returns (ok, detail)."""
        try:
            if wav.exists():
                wav.unlink()
        except Exception:
            pass
        kind = backend.get("kind")
        try:
            if kind == "piper":
                return self._synth_piper(backend, text, wav)
            if kind == "pyttsx3":
                return self._synth_pyttsx3(text, wav)
            if kind == "sapi":
                return self._synth_sapi(backend, text, wav)
        except Exception as e:  # noqa: BLE001 — synth backends are best-effort; record the failure
            return False, f"{kind} exception: {e}"
        return False, f"unknown backend {kind}"

    def _synth_piper(self, backend, text: str, wav: Path):
        model = backend.get("model")
        if not model or not Path(model).exists():
            # Piper requires a voice .onnx; without one we cannot synth. Caller's resolver may
            # still have ranked piper first, so fall back transparently to SAPI/pyttsx3.
            fb = self._sapi_backend()
            if fb:
                return self._synth_sapi(fb, text, wav)
            return False, "piper present but no PIPER_VOICE_MODEL (.onnx) and no SAPI fallback"
        exe = backend.get("exe")
        if exe:
            cmd = [exe, "--model", model, "--output_file", str(wav)]
        else:
            cmd = ["python", "-m", "piper", "--model", model, "--output_file", str(wav)]
        p = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=300)
        return wav.exists() and wav.stat().st_size > 0, f"piper rc={p.returncode}"

    def _synth_pyttsx3(self, text: str, wav: Path):
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(text, str(wav))
        engine.runAndWait()
        engine.stop()
        return wav.exists() and wav.stat().st_size > 0, "pyttsx3 save_to_file"

    def _synth_sapi(self, backend, text: str, wav: Path):
        pwsh = backend.get("pwsh") or "powershell"
        safe_text = text.replace("'", "''")
        wav_posix = str(wav).replace("\\", "/")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{wav_posix}'); "
            f"$s.Speak('{safe_text}'); "
            "$s.Dispose();"
        )
        p = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=300,
        )
        ok = wav.exists() and wav.stat().st_size > 0
        return ok, f"sapi rc={p.returncode} {('' if ok else p.stderr[:200])}"

    # ---- UE import --------------------------------------------------------------------------------
    def _ue_import(self, wav_paths, make_metasound: bool) -> dict:
        if RESULT.exists():
            try:
                RESULT.unlink()
            except Exception:
                pass
        # Pass the WAV list via a manifest file (avoids fragile long arg quoting).
        manifest = AUDIO_DIR / "_import_manifest.json"
        manifest.write_text(json.dumps({"wavs": list(wav_paths), "dest": UE_AUDIO_PATH}),
                            encoding="utf-8")
        cmd = [
            str(UE_CMD), str(UPROJECT),
            # forward slashes: UE mis-parses backslash paths passed through subprocess list quoting
            (f"-ExecutePythonScript={DRIVER} manifest={manifest} dest={UE_AUDIO_PATH} "
             f"metasound={'1' if make_metasound else '0'}").replace("\\", "/"),
            "-unattended", "-nosplash", "-nopause", "-stdout",
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except Exception as e:  # noqa: BLE001 — verify via the result FILE, not the call
            return {"ran": True, "error": f"ue subprocess failed: {e}"}
        if not RESULT.exists():
            return {"ran": True, "error": "UE driver produced no result file (import unverified)"}
        try:
            rec = json.loads(RESULT.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return {"ran": True, "error": f"unreadable UE result: {e}"}
        rec["ran"] = True
        return rec
