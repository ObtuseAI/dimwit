"""PROGRESSION_PERSISTENCE_V1 — earned-progression + versioned-profile migration gates.

Masterplan Horizon 2, bundle §B6. Progression must be EARNED from a real bot-match seat (the
designated TeamA combatant, not the passive LocalPlayer) and persisted in a versioned, corruption-
safe profile JSON. This module holds the pure-Python gate helpers that prove the schema-versioning
and v0->v1 migration invariants WITHOUT a UE run — they read ToJson() output shape and a pinned v0
fixture, so the migration is proven cheaply before the live telemetry lane.

The C++ source of truth is FWanefallPlayerProfile (SchemaVersion=1; FromJson migrates any version <
SchemaVersion by default-filling new fields, and fails closed on newer-than-known). These helpers
mirror that invariant so a Dimwit gate can recompute it from the emitted payload (recomputation
law). Floors ratchet-only.
"""
from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1
REQUIRED_V1_FIELDS = ("profile_id", "display_name", "account_level", "account_xp", "settings", "loadout", "unlocks")


def check_schema_versioned(profile_json: dict) -> tuple[bool, str]:
    v = profile_json.get("schema_version")
    if v is None:
        return False, "live profile has no schema_version (v0 legacy shape)"
    if v != CURRENT_SCHEMA_VERSION:
        return False, f"schema_version {v} != current {CURRENT_SCHEMA_VERSION}"
    return True, "schema_version present and current"


def migrate_and_validate(v0_json: dict) -> tuple[bool, str]:
    # Python mirror of the C++ v0->v1 migration invariant: no schema_version implies v0; every v1
    # field must be resolvable (present, or default-filled), and required fields must exist.
    migrated = dict(v0_json)
    migrated.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    migrated.setdefault("mode_stats", {})
    migrated.setdefault("rank_state", [])
    migrated.setdefault("recent_matches", [])
    migrated.setdefault("friends", [])
    for f in REQUIRED_V1_FIELDS:
        if f not in migrated:
            return False, f"missing required field after migration: {f}"
    if migrated["account_level"] < 1 or migrated["account_xp"] < 0:
        return False, "invalid level/xp after migration"
    return True, "v0 migrated to v1 and validates"


# ---- earn recompute mirrors (PINNED to the C++ source of truth) --------------------------------
# XP weights mirror FWanefallProgressionState::XpForEvent (WanefallProgression.cpp). Only the events
# the bot-match seat can produce are mirrored; drift in any of these fails the earned gate.
XP_KILL = 100            # EWanefallXpEvent::Kill
XP_ASSIST = 50           # EWanefallXpEvent::Assist
XP_WIN = 220             # EWanefallXpEvent::WaneTrialWin (awarded once on a win)
ANTI_FARM_CAP_PER_MATCH = 2000   # FWanefallProgressionState::AntiFarmCapPerMatch
DAILY_KILLS_TARGET = 10          # ChallengeBook.Add("daily_kills", ... Target=10) seeded in the subsystem


def level_for_xp(xp: int) -> int:
    # Mirror of FWanefallPlayerProfile::LevelForXp: level N requires cumulative 1000*N total xp.
    level, need, acc = 1, 1000, 0
    while xp >= acc + need and level < 999:
        acc += need
        level += 1
        need += 1000
    return level


def _capped_award(kills: int, assists: int, win: bool) -> int:
    """Recompute XP the earn subsystem SHOULD grant for this seat result, honouring the per-match
    anti-farm cap. Mirrors the sequential Award() calls (Kill, Assist, Win) capped cumulatively."""
    kills = max(0, int(kills))
    assists = max(0, int(assists))
    granted = 0
    for want in (kills * XP_KILL, assists * XP_ASSIST, (XP_WIN if win else 0)):
        room = max(0, ANTI_FARM_CAP_PER_MATCH - granted)
        granted += min(want, room)
    return granted


def check_earned_from_telemetry(proof: dict) -> tuple[bool, str]:
    """A single apply-proof must be internally honest: granted XP == recompute(events) under the
    anti-farm cap, and the stored level == level_for_xp(stored xp). Catches fabricated xp/level."""
    kills = int(proof.get("kills") or 0)
    assists = int(proof.get("assists") or 0)
    win = bool(proof.get("win"))
    expected = _capped_award(kills, assists, win)
    granted = int(proof.get("xp_granted") or 0)
    if granted != expected:
        return False, f"xp_granted {granted} != recomputed {expected} (kills={kills} assists={assists} win={win})"
    xp_after = int(proof.get("account_xp_after") or 0)
    lvl_after = int(proof.get("account_level_after") or 0)
    if lvl_after != level_for_xp(xp_after):
        return False, f"account_level_after {lvl_after} != level_for_xp({xp_after})={level_for_xp(xp_after)}"
    if xp_after < granted:
        return False, f"account_xp_after {xp_after} < xp_granted {granted}"
    return True, "earn proof internally consistent (xp + level recompute)"


def check_anti_farm(proof: dict) -> tuple[bool, str]:
    """The per-match anti-farm cap must hold: recomputed grant never exceeds the cap, and once the
    uncapped want exceeds the cap the grant is EXACTLY the cap (no farm past it)."""
    kills = int(proof.get("kills") or 0)
    assists = int(proof.get("assists") or 0)
    win = bool(proof.get("win"))
    uncapped = max(0, kills) * XP_KILL + max(0, assists) * XP_ASSIST + (XP_WIN if win else 0)
    granted = _capped_award(kills, assists, win)
    if granted > ANTI_FARM_CAP_PER_MATCH:
        return False, f"granted {granted} exceeds cap {ANTI_FARM_CAP_PER_MATCH}"
    if uncapped > ANTI_FARM_CAP_PER_MATCH and granted != ANTI_FARM_CAP_PER_MATCH:
        return False, f"uncapped {uncapped} > cap but granted {granted} != cap {ANTI_FARM_CAP_PER_MATCH}"
    return True, f"anti-farm cap honoured (uncapped={uncapped} granted={granted})"


def check_challenges(proof: dict) -> tuple[bool, str]:
    """Per-proof sanity: daily_kills progress is bounded to [0, target]. The challenge accumulates
    ACROSS a run's matches and completes once, so a single proof cannot pin it to this match's kills
    — the cumulative correctness (progress == min(cumulative_kills, target)) is checked over the
    ordered run in compute_cumulative_challenges. A single kill this match can never exceed target."""
    progress = int(proof.get("challenge_daily_kills_progress") or 0)
    if progress < 0 or progress > DAILY_KILLS_TARGET:
        return False, f"challenge_daily_kills_progress {progress} out of [0, {DAILY_KILLS_TARGET}]"
    return True, "challenge progress within bounds"


def compute_cumulative_challenges(proofs: list) -> tuple[bool, str]:
    """Over one run's ordered apply-proofs, daily_kills progress must equal min(cumulative_kills,
    target) at every match — advanced from real event counts, clamped, monotonic non-decreasing."""
    ordered = sorted(proofs, key=lambda p: int(str(p.get("match_id", "botmatch_0")).split("_")[-1] or 0))
    cum_kills = 0
    prev_progress = 0
    for p in ordered:
        cum_kills += max(0, int(p.get("kills") or 0))
        expected = min(cum_kills, DAILY_KILLS_TARGET)
        progress = int(p.get("challenge_daily_kills_progress") or 0)
        if progress != expected:
            return False, (f"{p.get('match_id')}: challenge progress {progress} != "
                           f"min(cumulative_kills={cum_kills}, {DAILY_KILLS_TARGET})={expected}")
        if progress < prev_progress:
            return False, f"{p.get('match_id')}: challenge progress decreased ({prev_progress} -> {progress})"
        prev_progress = progress
    return True, "cumulative challenge progress matches real event counts"


# ================================================================================================
# Live proof lane: two sequential packaged bot-match launches prove earnings are REAL (recomputed
# from the emitted apply-proofs) and PERSIST across a real process relaunch (run #2 loads run #1's
# saved profile from disk, never resets). Reuses the existing bot-match harness — no new commandlet.
# ================================================================================================
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
RESULT_DIR = ROOT / "artifacts" / "progression"
RESULT_PATH = RESULT_DIR / "progression_result.json"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_PROGRESSION_REPORT.md"

ARENA_MAP_URL = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"
FLAG = "WANEFALLBOTMATCH"
PROFILE_RELATIVE = Path("ShowMeAI") / "WanefallProfiles" / "local.json"
PROOF_DIR_RELATIVE = Path("ShowMeAI") / "WanefallProgressionProof"
FIXED_FPS = 60
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _freshness(result: dict, max_age_seconds: int) -> dict:
    ts = _num_or_none(result.get("run_ts"))
    if ts is None:
        return {"passed": False, "issues": ["result has no run_ts"], "age_seconds": None}
    age = time.time() - ts
    if age > max_age_seconds:
        return {"passed": False, "issues": [f"progression proof stale ({int(age)}s > {max_age_seconds}s)"],
                "age_seconds": age}
    return {"passed": True, "issues": [], "age_seconds": age}


def _num_or_none(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        return float(v)
    return None


def compute_earned_checks(result: dict) -> dict:
    """Every apply-proof from the fresh run must pass the per-proof earn/anti-farm/challenge gates,
    AND the run must chain: proof[i].account_xp_after == proof[i-1].account_xp_after + xp_granted[i]
    (with proof[0] anchored to the pre-run profile xp). Catches fabricated or out-of-nowhere xp."""
    proofs = result.get("apply_proofs") if isinstance(result.get("apply_proofs"), list) else []
    issues = []
    if not proofs:
        issues.append("no apply-proofs emitted by the run (earn path never fired)")
    for p in proofs:
        for label, fn in (("earned", check_earned_from_telemetry), ("anti_farm", check_anti_farm),
                          ("challenges", check_challenges)):
            ok, detail = fn(p)
            if not ok:
                issues.append(f"{p.get('match_id')}: {label}: {detail}")
    # chain accumulation within the run. The apply-proofs on disk are RUN #2's (run #1's were
    # overwritten), so anchor the chain to the profile xp AFTER run #1 (run #2's starting point).
    prev = _num_or_none((result.get("profile_after_run1") or {}).get("account_xp"))
    ordered = sorted(proofs, key=lambda p: int(p.get("match_id", "botmatch_0").split("_")[-1] or 0))
    for p in ordered:
        after = _num_or_none(p.get("account_xp_after"))
        granted = _num_or_none(p.get("xp_granted"))
        if after is None or granted is None:
            issues.append(f"{p.get('match_id')}: missing xp fields")
            continue
        if prev is not None and after != prev + granted:
            issues.append(f"{p.get('match_id')}: chain break: {after} != {prev} + {granted}")
        prev = after
    return {"passed": not issues, "issues": issues, "proofs": len(proofs)}


def compute_persistence(result: dict) -> dict:
    """Run #2 must LOAD run #1's saved profile (relaunch-persistence), not reset it: a distinct pid,
    and account_xp after run #2 == account_xp after run #1 + run #2's total granted xp, and the
    recent-match ledger grew across the process boundary."""
    a = result.get("profile_after_run1") if isinstance(result.get("profile_after_run1"), dict) else {}
    b = result.get("profile_after_run2") if isinstance(result.get("profile_after_run2"), dict) else {}
    pid1 = result.get("run1_pid")
    pid2 = result.get("run2_pid")
    proofs = result.get("apply_proofs") if isinstance(result.get("apply_proofs"), list) else []
    issues = []
    if not a or not b:
        issues.append("missing run-1/run-2 profile snapshots")
        return {"passed": False, "issues": issues}
    if pid1 is None or pid2 is None or pid1 == pid2:
        issues.append(f"relaunch pids not distinct (pid1={pid1} pid2={pid2})")
    xp_a = _num_or_none(a.get("account_xp"))
    xp_b = _num_or_none(b.get("account_xp"))
    run2_granted = sum(_num_or_none(p.get("xp_granted")) or 0.0 for p in proofs)
    if xp_a is None or xp_b is None:
        issues.append("profile snapshots missing account_xp")
    else:
        if xp_a <= 0:
            issues.append("run #1 earned no xp — nothing to prove persisted")
        if xp_b != xp_a + run2_granted:
            issues.append(f"account_xp after relaunch {xp_b} != run1 {xp_a} + run2 granted {run2_granted} "
                          "(profile was reset, not loaded)")
    ra = len(a.get("recent_matches") or [])
    rb = len(b.get("recent_matches") or [])
    if rb <= ra:
        issues.append(f"recent-match ledger did not grow across relaunch ({ra} -> {rb})")
    return {"passed": not issues, "issues": issues, "xp_run1": xp_a, "xp_run2": xp_b,
            "run2_granted": run2_granted, "recent_run1": ra, "recent_run2": rb}


def compute_schema_versioned(result: dict) -> dict:
    """The persisted profile must carry the current schema_version (proves the real save is v1)."""
    b = result.get("profile_after_run2") if isinstance(result.get("profile_after_run2"), dict) else {}
    ok_v, detail_v = check_schema_versioned(b)
    return {"passed": ok_v, "issues": [] if ok_v else [detail_v]}


def compute_migration_roundtrips(result: dict) -> dict:
    """A v0 shape of the REAL saved profile (schema_version stripped) must still migrate + validate."""
    b = result.get("profile_after_run2") if isinstance(result.get("profile_after_run2"), dict) else {}
    v0 = {k: v for k, v in b.items() if k != "schema_version"}
    ok_m, detail_m = migrate_and_validate(v0)
    return {"passed": ok_m, "issues": [] if ok_m else [detail_m]}


def validate_progression_result(path: Path | str = RESULT_PATH,
                                max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"progression result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"progression result unreadable: {exc}") from exc
    if not isinstance(result, dict):
        raise BlockedError(f"progression result root is not an object: {result_path}")

    result = dict(result)
    binding = result.get("package_binding") if isinstance(result.get("package_binding"), dict) else {}
    proofs = result.get("apply_proofs") if isinstance(result.get("apply_proofs"), list) else []

    def _per_proof(fn):
        if not proofs:
            return {"passed": False, "issues": ["no apply-proofs"]}
        issues = [f"{p.get('match_id')}: {fn(p)[1]}" for p in proofs if not fn(p)[0]]
        return {"passed": not issues, "issues": issues}

    cum_ok, cum_detail = compute_cumulative_challenges(proofs)
    checks = {
        "freshness": _freshness(result, max_age_seconds=max_age_seconds),
        "evidence_bound": {"passed": bool(binding.get("matches")),
                           "issues": [] if binding.get("matches") else ["exe sha256 != package manifest sha256"]},
        "earned_from_real_telemetry": compute_earned_checks(result),
        "anti_farm": _per_proof(check_anti_farm),
        "challenges": {"passed": cum_ok and bool(proofs),
                       "issues": ([] if cum_ok else [cum_detail]) if proofs else ["no apply-proofs"]},
        "persists_across_relaunch": compute_persistence(result),
        "schema_versioned": compute_schema_versioned(result),
        "migration_roundtrips": compute_migration_roundtrips(result),
    }
    result["checks"] = checks
    result["suite_pass"] = bool(checks) and all(bool(c.get("passed")) for c in checks.values())
    result["state"] = "PASS" if result["suite_pass"] else "BLOCKED"
    return result


class ProgressionPipeline(ProductionPipeline):
    name = "progression"
    kind = "progression"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        output_dir = Path(task.get("output_dir") or RESULT_DIR)
        return {
            "asset_id": str(task.get("asset_id") or "wanefall_win64_development_progression"),
            "output_dir": output_dir,
            "result_path": output_dir / RESULT_PATH.name,
            "local_report": output_dir / LOCAL_REPORT.name,
            "packaged_result_path": Path(task.get("packaged_result_path") or PACKAGED_RESULT_PATH),
            "packaged_manifest_path": Path(task.get("packaged_manifest_path") or PACKAGED_MANIFEST_PATH),
            "matches_per_run": int(task.get("matches_per_run") or 6),
            "launch_timeout_seconds": int(task.get("launch_timeout_seconds") or 300),
            "poll_seconds": float(task.get("poll_seconds") or 2.0),
        }

    def execute(self, plan: dict) -> Artifact:
        result = self._run_proof(plan)
        _write_json(Path(plan["result_path"]), result)
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={"result_path": str(plan["result_path"]), "suite_pass": bool(result.get("suite_pass"))},
            provenance={"source": "local_wanefall_packaged_progression_earn", "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_progression_result(Path(plan["result_path"]))
        issues = []
        for nm, ch in (result.get("checks") or {}).items():
            if not ch.get("passed"):
                issues.extend([f"{nm}: {i}" for i in ch.get("issues", [])] or [f"{nm}: failed"])
        score = round(sum(1 for c in (result.get("checks") or {}).values() if c.get("passed"))
                      / max(1, len(result.get("checks") or {})), 4)
        return Verdict(score=1.0 if result.get("suite_pass") else score,
                       passed=bool(result.get("suite_pass")), hard_fail=False, issues=issues,
                       detail={"state": result.get("state"), "checks": result.get("checks")},
                       evidence=[str(plan["result_path"])])

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact

    # ---- internals ----

    def _resolve_package(self, plan: dict):
        pr = Path(plan["packaged_result_path"])
        if not pr.exists():
            raise BlockedError(f"packaged build result missing: {pr}")
        packaged = _read_json(pr)
        archive_dir = Path((packaged.get("package") or {}).get("archive_dir") or "")
        manifest = _read_json(Path(plan["packaged_manifest_path"]))
        executable = Path(((manifest.get("executable") or {}).get("path")) or "")
        manifest_sha = str((manifest.get("executable") or {}).get("sha256") or "")
        if not archive_dir.exists() or not executable.exists() or len(manifest_sha) != 64:
            raise BlockedError("packaged archive/executable/manifest sha missing")
        return archive_dir, executable, manifest_sha

    def _saved_dir(self, archive_dir: Path) -> Path:
        return archive_dir / "Windows" / "WanefallGreybox" / "Saved"

    def _launch_botmatch(self, executable: Path, matches: int, seed: int, log_path: Path,
                         timeout: int, poll: float) -> int:
        # NOTE: never delete the profile here — run #2 must inherit run #1's saved profile from disk
        # (that inheritance IS the relaunch-persistence proof). Only _run_proof clears it, once,
        # before run #1.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(executable), ARENA_MAP_URL, "-nullrhi", "-nosound", "-unattended",
               "-deterministic", f"-fps={FIXED_FPS}", f"-abslog={log_path}", f"-{FLAG}",
               f"-BotMatchCount={matches}", f"-BotMatchSeed={seed}", "-BotMatchMaxSeconds=180",
               "-BotMatchWaneEvery=3"]
        proc = subprocess.Popen(cmd, cwd=str(executable.parent))
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(poll)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
        return proc.pid

    def _snapshot_profile(self, profile_path: Path) -> dict:
        # full local.json so schema/migration gates see every field; persistence reads account_xp +
        # recent_matches straight off it.
        return _read_json(profile_path)

    def _collect_apply_proofs(self, proof_dir: Path) -> list:
        out = []
        if proof_dir.exists():
            for f in sorted(proof_dir.glob("apply_*.json")):
                d = _read_json(f)
                if d:
                    out.append(d)
        return out

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
        profile_path = saved / PROFILE_RELATIVE
        proof_dir = saved / PROOF_DIR_RELATIVE

        # fresh-run truth: clear profile + prior apply-proofs so run #1 starts from an empty profile
        for target in (profile_path,):
            try:
                if target.exists():
                    target.unlink()
            except Exception:
                pass
        if proof_dir.exists():
            for f in proof_dir.glob("apply_*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass

        matches = int(plan["matches_per_run"])
        timeout = int(plan["launch_timeout_seconds"])
        poll = float(plan["poll_seconds"])

        run1_pid = self._launch_botmatch(executable, matches, 20260703,
                                         output_dir / "logs" / "progression_run1.log", timeout, poll)
        profile_after_run1 = self._snapshot_profile(profile_path)

        run2_pid = self._launch_botmatch(executable, matches, 20260704,
                                         output_dir / "logs" / "progression_run2.log", timeout, poll)
        profile_after_run2 = self._snapshot_profile(profile_path)
        apply_proofs = self._collect_apply_proofs(proof_dir)   # run #2's fresh proofs (run #1 overwritten)

        result = {
            "schema_version": 1,
            "run_ts": time.time(),
            "run_started_at": started,
            "asset_id": plan["asset_id"],
            "package_binding": binding,
            "run1_pid": run1_pid,
            "run2_pid": run2_pid,
            "profile_before": {"account_xp": 0, "account_level": 1},   # cleared before run #1
            "profile_after_run1": profile_after_run1,
            "profile_after_run2": profile_after_run2,
            "apply_proofs": apply_proofs,
        }
        _write_json(Path(plan["result_path"]), result)
        return validate_progression_result(Path(plan["result_path"]))
