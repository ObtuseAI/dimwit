"""UI_SETTINGS_AND_PERSISTENCE_V1 — settings save/apply + relaunch-persistence proof.

Masterplan Horizon 1, bundle 8 (§B4/B6). Settings were read-only: FWanefallSettings serialized in
the profile JSON and bundle 7's UWanefallProfileSubsystem LOADED it, but nothing saved it back and
no value reached the engine. This lane drives a flag-gated TWO-LAUNCH proof on the packaged build:
launch #1 (write) changes every setting + a resolution, persists the profile JSON + applies
UGameUserSettings; launch #2 (verify) re-loads from disk and reports what survived. The gates
recompute the round-trip from the proof JSONs — a changed setting must survive a REAL relaunch.

Laws honored: packaged proof only (exe-sha bound to manifest); pid-bound per launch; recomputation
law (every gate derived from the proof payload). Floors ratchet-only.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.packaged_build_validation import (
    MANIFEST_PATH as PACKAGED_MANIFEST_PATH,
    RESULT_PATH as PACKAGED_RESULT_PATH,
)


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "artifacts" / "ui_settings"
RESULT_PATH = RESULT_DIR / "ui_settings_result.json"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_UI_SETTINGS_REPORT.md"

FLAG = "WANEFALLSETTINGSPROOF"
PROFILE_RELATIVE = Path("ShowMeAI") / "WanefallProfiles" / "local.json"
WRITE_RELATIVE = Path("ShowMeAI") / "WanefallSettingsProof" / "settings_proof_write.json"
VERIFY_RELATIVE = Path("ShowMeAI") / "WanefallSettingsProof" / "settings_proof_verify.json"

DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60

# The 12 settings fields (keys mirror FWanefallPlayerProfile::ToJson) + their C++ defaults, so
# coverage can prove the KNOWN write block is non-default on every field.
SETTINGS_KEYS = (
    "lstick", "rstick", "remap", "vibration", "master", "voice", "music",
    "dialogue", "voice_chat", "input_device", "output_device", "graphics",
)
SETTINGS_DEFAULTS = {
    "lstick": 0.5, "rstick": 0.5, "remap": 0, "vibration": True, "master": 0.8,
    "voice": 0.8, "music": 0.6, "dialogue": 0.8, "voice_chat": True,
    "input_device": "Default Controller", "output_device": "Default Audio Device", "graphics": 3,
}
FLOAT_TOLERANCE = 1e-4
SETTING_FIELD_FLOOR = 12   # every field must round-trip (ratchet: cannot shrink)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _num(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _settings_equal(a: dict, b: dict) -> list:
    """Return a list of field mismatches between two settings blocks (empty == identical)."""
    mismatches = []
    for key in SETTINGS_KEYS:
        av, bv = a.get(key), b.get(key)
        if isinstance(SETTINGS_DEFAULTS[key], str):
            if str(av) != str(bv):
                mismatches.append(f"{key}: {av!r} != {bv!r}")
        else:
            an, bn = _num(av), _num(bv)
            if an is None or bn is None or abs(an - bn) > FLOAT_TOLERANCE:
                mismatches.append(f"{key}: {av!r} != {bv!r}")
    return mismatches


def compute_persistence_roundtrip(result: dict) -> dict:
    """write.intended settings must equal verify.loaded settings for all 12 fields — the change
    survived a real relaunch."""
    write = result.get("write") if isinstance(result.get("write"), dict) else {}
    verify = result.get("verify") if isinstance(result.get("verify"), dict) else {}
    intended = write.get("settings") if isinstance(write.get("settings"), dict) else {}
    loaded = verify.get("settings") if isinstance(verify.get("settings"), dict) else {}
    issues = []
    if not intended:
        issues.append("write proof has no settings block")
    if not loaded:
        issues.append("verify proof has no settings block")
    mismatches = _settings_equal(intended, loaded) if (intended and loaded) else []
    if mismatches:
        issues.append("settings did not survive relaunch: " + "; ".join(mismatches))
    covered = sum(1 for k in SETTINGS_KEYS if k in intended and k in loaded)
    if covered < SETTING_FIELD_FLOOR:
        issues.append(f"only {covered}/{SETTING_FIELD_FLOOR} settings fields present in both proofs")
    return {"passed": not issues, "issues": issues, "fields_roundtripped": covered,
            "mismatches": mismatches}


def _gus_block(node: dict) -> dict:
    return node.get("gus") if isinstance(node.get("gus"), dict) else {}


def compute_gameusersettings_applied(result: dict) -> dict:
    """The engine must actually take the resolution/quality (write readback == intended) AND those
    values must survive the relaunch (verify readback == intended) via GUS's own ini persistence."""
    write = result.get("write") if isinstance(result.get("write"), dict) else {}
    verify = result.get("verify") if isinstance(result.get("verify"), dict) else {}
    wg = _gus_block(write)
    vg = _gus_block(verify)
    intended = wg.get("intended") if isinstance(wg.get("intended"), dict) else {}
    w_readback = wg.get("readback") if isinstance(wg.get("readback"), dict) else {}
    v_readback = vg.get("readback") if isinstance(vg.get("readback"), dict) else {}
    issues = []
    if not intended:
        issues.append("write proof has no GUS intended block")
    # Field coverage differs by phase, on purpose:
    # - apply (write readback): resolution AND quality must both match intended — proves the engine
    #   actually TOOK every value at apply time.
    # - relaunch (verify readback): only RESOLUTION is gated. GUS owns resolution persistence
    #   (GameUserSettings.ini) and it must survive the relaunch. GetOverallScalabilityLevel() is
    #   -1-prone after a fresh headless (-nullrhi) load when the per-group scalability values don't
    #   collapse to a single level, so quality-across-relaunch is RECORDED, not gated here —
    #   graphics-quality persistence is independently proven by the profile-JSON round-trip
    #   (the `graphics` field in persistence_roundtrip + coverage).
    apply_fields = ("res_x", "res_y", "quality")
    relaunch_fields = ("res_x", "res_y")
    for label, rb, fields in (("apply", w_readback, apply_fields),
                              ("relaunch", v_readback, relaunch_fields)):
        if not rb:
            issues.append(f"{label} GUS readback missing")
            continue
        for f in fields:
            iv, rv = _num(intended.get(f)), _num(rb.get(f))
            if iv is None or rv is None or abs(iv - rv) > 0.5:
                issues.append(f"{label} GUS {f} {rb.get(f)!r} != intended {intended.get(f)!r}")
    return {"passed": not issues, "issues": issues, "intended": intended,
            "apply_readback": w_readback, "relaunch_readback": v_readback,
            "relaunch_quality_recorded": v_readback.get("quality")}


def compute_coverage(result: dict) -> dict:
    """The KNOWN write block must differ from FWanefallSettings::MakeDefault on EVERY field — so a
    passing round-trip proves each field is exercised, not just one value that equals its default."""
    write = result.get("write") if isinstance(result.get("write"), dict) else {}
    intended = write.get("settings") if isinstance(write.get("settings"), dict) else {}
    issues = []
    if not intended:
        return {"passed": False, "issues": ["write proof has no settings block"], "non_default": 0}
    non_default = 0
    for key in SETTINGS_KEYS:
        default = SETTINGS_DEFAULTS[key]
        val = intended.get(key)
        if isinstance(default, str):
            differs = str(val) != str(default)
        else:
            n = _num(val)
            differs = n is None or abs(n - float(default)) > FLOAT_TOLERANCE
        if differs:
            non_default += 1
        else:
            issues.append(f"{key} equals its default ({default!r}) — field not exercised")
    if non_default < SETTING_FIELD_FLOOR:
        issues.append(f"only {non_default}/{SETTING_FIELD_FLOOR} fields changed from default")
    return {"passed": not issues, "issues": issues, "non_default": non_default}


def _recompute_binding(result: dict) -> dict:
    """Both proofs must be flag-marked, pid-bound to their launch, and exe-sha bound to the package
    manifest; the two launches must have DISTINCT pids (a real relaunch, not one process)."""
    issues = []
    binding = result.get("package_binding") if isinstance(result.get("package_binding"), dict) else {}
    if binding.get("matches") is not True:
        issues.append("package binding not verified (matches != True)")
    manifest_sha = str(binding.get("manifest_sha256") or "")
    run_sha = str(binding.get("exe_sha256_at_run") or "")
    if len(manifest_sha) != 64 or manifest_sha != run_sha:
        issues.append("executable sha256 at run does not match package manifest sha256")
    pids = []
    for phase in ("write", "verify"):
        node = result.get(phase) if isinstance(result.get(phase), dict) else {}
        if str(node.get("flag") or "") != FLAG:
            issues.append(f"{phase} proof flag {node.get('flag')!r} != {FLAG!r}")
        launched = result.get(f"{phase}_launched_pid")
        proof_pid = node.get("pid")
        if not isinstance(launched, int) or not isinstance(proof_pid, int) or launched != proof_pid:
            issues.append(f"{phase} proof pid {proof_pid!r} != launched pid {launched!r}")
        if isinstance(proof_pid, int):
            pids.append(proof_pid)
    if len(pids) == 2 and pids[0] == pids[1]:
        issues.append("write and verify share a pid — not a real relaunch")
    return {"passed": not issues, "issues": issues, "pids": pids}


def _freshness(result: dict, max_age_seconds: int) -> dict:
    captured = _num(result.get("captured_at"))
    if captured is None:
        return {"passed": False, "issues": ["captured_at missing/non-numeric"], "age_seconds": None}
    age = time.time() - captured
    if age > max_age_seconds:
        return {"passed": False,
                "issues": [f"settings proof is {age / 3600.0:.1f}h old > ceiling "
                           f"{max_age_seconds / 3600.0:.1f}h — rerun the ui-settings lane"],
                "age_seconds": round(age, 1)}
    return {"passed": True, "issues": [], "age_seconds": round(age, 1)}


def validate_ui_settings_result(path: Path | str = RESULT_PATH,
                                max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"ui-settings result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"ui-settings result unreadable: {exc}") from exc
    if not isinstance(result, dict):
        raise BlockedError(f"ui-settings result root is not an object: {result_path}")

    result = dict(result)
    checks = dict(result.get("checks") or {})
    checks["freshness"] = _freshness(result, max_age_seconds=max_age_seconds)
    checks["evidence_bound"] = _recompute_binding(result)
    checks["persistence_roundtrip"] = compute_persistence_roundtrip(result)
    checks["gameusersettings_applied"] = compute_gameusersettings_applied(result)
    checks["coverage"] = compute_coverage(result)
    result["checks"] = checks
    result["suite_pass"] = bool(checks) and all(bool(c.get("passed")) for c in checks.values())
    result["state"] = "PASS" if result["suite_pass"] else "BLOCKED"
    return result


def _make_report(result: dict, report_path: Path) -> str:
    checks = result.get("checks") or {}
    lines = [
        "# WANEFALL UI Settings Persistence Report (UI_SETTINGS_AND_PERSISTENCE_V1)",
        "",
        f"State: {result.get('state')}",
        f"Suite pass: {result.get('suite_pass')}",
        f"Write pid: {result.get('write_launched_pid')}  Verify pid: {result.get('verify_launched_pid')}",
        "",
        "## Checks",
    ]
    for name, check in checks.items():
        lines.append(f"- {name}: passed={check.get('passed')} issues={check.get('issues', [])}")
    lines.extend([
        "",
        "## Scope",
        "- Proves the persistence MECHANISM: 12-field settings + one non-default resolution "
        "round-trip across a REAL relaunch.",
        "- Multi-resolution matrix sweep is PARTIAL (follow-up; each resolution = another launch).",
        "",
        "## Boundaries",
        "- Floors are ratchet-only; no HUMAN_ACCEPTED/PROMOTED_TO_ACTIVE_SLICE state written.",
        "- Missing/unbound proof stays BLOCKED, never fake green.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class UiSettingsPersistencePipeline(ProductionPipeline):
    name = "ui_settings_persistence"
    kind = "ui_settings_persistence"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "wanefall_win64_development_settings")
        output_dir = Path(task.get("output_dir") or RESULT_DIR)
        return {
            "asset_id": asset_id,
            "output_dir": output_dir,
            "result_path": output_dir / RESULT_PATH.name,
            "local_report": output_dir / LOCAL_REPORT.name,
            "packaged_result_path": Path(task.get("packaged_result_path") or PACKAGED_RESULT_PATH),
            "packaged_manifest_path": Path(task.get("packaged_manifest_path") or PACKAGED_MANIFEST_PATH),
            "archive_dir": task.get("archive_dir"),
            "launch_timeout_seconds": int(task.get("launch_timeout_seconds") or 180),
            "poll_seconds": float(task.get("poll_seconds") or 2.0),
        }

    def execute(self, plan: dict) -> Artifact:
        result = self._run_proof(plan)
        _write_json(Path(plan["result_path"]), result)
        _make_report(result, Path(plan["local_report"]))
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={"result_path": str(plan["result_path"]), "suite_pass": bool(result.get("suite_pass"))},
            provenance={"source": "local_wanefall_packaged_settings_persistence",
                        "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_ui_settings_result(Path(plan["result_path"]))
        issues = []
        for name, check in (result.get("checks") or {}).items():
            if not check.get("passed"):
                issues.extend([f"{name}: {i}" for i in check.get("issues", [])] or [f"{name}: failed"])
        return Verdict(score=1.0 if result.get("suite_pass") else self._score(result.get("checks") or {}),
                       passed=bool(result.get("suite_pass")), hard_fail=False, issues=issues,
                       detail={"state": result.get("state"), "checks": result.get("checks")},
                       evidence=[str(plan["result_path"])])

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact

    # ---- internals ----

    def _resolve_package(self, plan: dict) -> tuple[Path, Path, str]:
        packaged_result_path = Path(plan["packaged_result_path"])
        if not packaged_result_path.exists():
            raise BlockedError(f"packaged build result missing: {packaged_result_path}")
        packaged = json.loads(packaged_result_path.read_text(encoding="utf-8"))
        archive_dir = Path(plan.get("archive_dir") or (packaged.get("package") or {}).get("archive_dir") or "")
        if not archive_dir or not archive_dir.exists():
            raise BlockedError(f"packaged archive dir missing: {archive_dir}")
        manifest_path = Path(plan["packaged_manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        executable = Path(((manifest.get("executable") or {}).get("path")) or "")
        manifest_sha = str((manifest.get("executable") or {}).get("sha256") or "")
        if not executable.exists() or len(manifest_sha) != 64:
            raise BlockedError("packaged executable/manifest sha missing")
        return archive_dir, executable, manifest_sha

    def _saved_dir(self, archive_dir: Path) -> Path:
        return archive_dir / "Windows" / "WanefallGreybox" / "Saved"

    def _launch_phase(self, executable: Path, phase: str, proof_path: Path, timeout: int,
                      poll: float) -> tuple[int | None, dict]:
        if proof_path.exists():
            proof_path.unlink()
        cmd = [str(executable), "-nullrhi", "-nosound", "-unattended",
               f"-{FLAG}", f"-SettingsProofPhase={phase}"]
        proc = subprocess.Popen(cmd, cwd=str(executable.parent))
        deadline = time.time() + timeout
        payload: dict = {}
        try:
            while time.time() < deadline:
                if proof_path.exists():
                    try:
                        payload = json.loads(proof_path.read_text(encoding="utf-8"))
                        if isinstance(payload, dict) and payload:
                            break
                    except Exception:
                        pass
                if proc.poll() is not None:
                    time.sleep(1.0)
                    if proof_path.exists():
                        try:
                            payload = json.loads(proof_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    break
                time.sleep(poll)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        return proc.pid, (payload if isinstance(payload, dict) else {})

    def _run_proof(self, plan: dict) -> dict:
        started = time.time()
        output_dir = Path(plan["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        archive_dir, executable, manifest_sha = self._resolve_package(plan)
        exe_sha = _sha256_file(executable)
        binding = {"archive_dir": str(archive_dir), "manifest_sha256": manifest_sha,
                   "exe_sha256_at_run": exe_sha, "matches": exe_sha == manifest_sha}
        if not binding["matches"]:
            raise BlockedError("packaged executable does not match manifest sha256 — wrong subject")

        saved = self._saved_dir(archive_dir)
        gus_path = archive_dir / "Windows" / "WanefallGreybox" / "Config" / "WindowsNoEditor" / "GameUserSettings.ini"
        # fresh-run truth: clear the profile + GUS + prior proofs so the write launch starts clean
        for p in (saved / PROFILE_RELATIVE, saved / WRITE_RELATIVE, saved / VERIFY_RELATIVE, gus_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

        write_pid, write_payload = self._launch_phase(
            executable, "write", saved / WRITE_RELATIVE, int(plan["launch_timeout_seconds"]),
            float(plan["poll_seconds"]))
        verify_pid, verify_payload = self._launch_phase(
            executable, "verify", saved / VERIFY_RELATIVE, int(plan["launch_timeout_seconds"]),
            float(plan["poll_seconds"]))

        for name, payload in (("settings_proof_write.json", write_payload),
                              ("settings_proof_verify.json", verify_payload)):
            if payload:
                _write_json(output_dir / name, payload)

        result = {
            "schema_version": 1,
            "captured_at": time.time(),
            "run_started_at": started,
            "asset_id": plan["asset_id"],
            "package_binding": binding,
            "write_launched_pid": write_pid,
            "verify_launched_pid": verify_pid,
            "write": write_payload,
            "verify": verify_payload,
            "checks": {},
            "operator_only_states_written": [],
        }
        _write_json(Path(plan["result_path"]), result)
        return validate_ui_settings_result(Path(plan["result_path"]))

    def _score(self, checks: dict) -> float:
        if not checks:
            return 0.0
        return round(sum(1 for c in checks.values() if c.get("passed")) / len(checks), 4)
