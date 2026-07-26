"""MODE_CONTRACT_V1 -- parse + recompute the headless mode-sim proof.

Every verdict is recomputed from the raw `fields` block; the reported `pass`
is never trusted. Fail-closed: malformed/missing proof raises ModeProofError.
"""
import json
import os
import shutil
import subprocess

# Reuse the UE-lane path resolution already used by every other UE lane in this repo (validation.py,
# animation.py, environment.py, ...): module-level UE_CMD / UPROJECT constants, not a hardcoded path.
# ROOT is reused too so the harvested proof always resolves to the SAME absolute path regardless of
# CWD -- matches the ARTIFACT_DIR/RESULT_PATH pattern already used by autonomy_capability_matrix.py,
# contract_auditor.py, metahuman_utilization.py, unreal_game_builder_engine.py.
from dimwit.pipelines.validation import ROOT, UE_CMD, UPROJECT

class ModeProofError(Exception):
    pass

ARENA_MODES = [
    "arena.dm_1v1", "arena.dm_2v2", "arena.dm_ffa", "arena.a4v4_tdm",
    "arena.a4v4_ctf", "arena.a4v4_ctrl", "arena.a4v4_hard", "arena.a4v4_snd",
    "arena.a8v8_tdm", "arena.a8v8_ctf", "arena.a8v8_ctrl", "arena.a8v8_hard",
    "arena.a8v8_snd",
]
LARGE_MODES = ["br.waneroyale", "extraction.success", "extraction.kia", "extraction.timeout"]
ARCADE_MODES = ["arcade.wanerush", "arcade.waneclash", "arcade.rolltrial"]
DEMO_MODES = ["arena.a4v4_tdm", "trial.wanetrial", "practice.range"]

# ui.foundation reports no single terminal `result` worth trusting -- it's a
# stateless UI-model self-check. Recompute straight from its own raw boolean
# fields (never from the `UI_MODEL_VALID` label) per fail-closed doctrine.
_UI_FOUNDATION_BOOL_FIELDS = (
    "default_valid",
    "bad_rejected",
    "clamped",
    "categories_complete",
    "nav_ok",
    "results_model_ok",
)


def load_proof(path):
    if not os.path.isfile(path):
        raise ModeProofError(f"mode-sim proof missing: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ModeProofError(f"mode-sim proof unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ModeProofError(f"mode-sim proof root is not an object: {type(data).__name__}")
    if not data.get("complete"):
        raise ModeProofError("mode-sim proof not marked complete")
    modes = data.get("modes")
    if not isinstance(modes, list) or not modes:
        raise ModeProofError("mode-sim proof has no modes")
    if data.get("mode_count") != len(modes):
        raise ModeProofError(f"mode_count {data.get('mode_count')} != {len(modes)} modes")
    return data


def _by_name(proof):
    return {m.get("name"): m for m in proof.get("modes", [])}


def _f(mode, key):
    return mode.get("fields", {}).get(key, "")


def _b(mode, key):
    return _f(mode, key) == "true"


def _i(mode, key, default=0):
    try:
        return int(_f(mode, key))
    except (ValueError, TypeError):
        return default


def _resolved(mode):
    """Field-driven terminal-resolution check for the generic arena/large/arcade branch.

    Keys off the mode's own numeric/bool FIELDS, never the human-readable `result`
    string (that string is emitted as f"SIDE_{WinnerSide()}_WIN" even when
    WinnerSide() == -1, so a naive "WIN" in result substring check is vacuously
    true for non-resolving modes -- this is the bug being fixed here).
    Fail-closed: an unrecognized mode with none of these fields is NOT resolved.
    """
    f = mode.get("fields", {})
    if "winner" in f:              # arena side/team modes + brawl
        return _i(mode, "winner", -1) >= 0
    if "alive" in f:               # battle royale: last combatant standing
        return _i(mode, "alive", -1) == 1
    if "finished" in f:            # race / rolling
        return _b(mode, "finished")
    if any(k in f for k in ("success", "dead", "timed_out")):  # extraction family: any terminal outcome
        return _b(mode, "success") or _b(mode, "dead") or _b(mode, "timed_out")
    return False                   # fail-closed: no recognized resolution field


def recompute_mode(mode):
    """Recompute pass/fail from raw fields per the mode's contract."""
    name = mode.get("name", "")
    reset_ok = bool(mode.get("reset_ok"))
    live = _b(mode, "went_live")
    if name == "practice.range":
        return live and (not _b(mode, "is_over")) and _i(mode, "winner", -1) == -1 and reset_ok
    if name == "trial.wanetrial":
        return (live and _b(mode, "second_chance_before_finish")
                and _i(mode, "winner", -1) == 0 and _i(mode, "downs") == 1
                and _i(mode, "finishes") == 1 and _i(mode, "kills") == 1 and reset_ok)
    if name == "ui.foundation":
        # never trust the self-reported UI_MODEL_VALID label -- recompute from
        # this mode's own raw boolean fields.
        fields = mode.get("fields", {})
        if "went_live" in fields and not live:
            return False
        present = [k for k in _UI_FOUNDATION_BOOL_FIELDS if k in fields]
        return bool(present) and all(_b(mode, k) for k in present) and reset_ok
    # generic arena/large/arcade: went live (where applicable) + resolved + clean reset
    fields = mode.get("fields", {})
    if "went_live" in fields and not live:
        return False
    return _resolved(mode) and reset_ok


def _suite(proof, names):
    idx = _by_name(proof)
    missing = [n for n in names if n not in idx]
    if missing:
        return False, f"missing modes: {missing}"
    bad = [n for n in names if not recompute_mode(idx[n])]
    if bad:
        return False, f"failed contract: {bad}"
    return True, f"{len(names)} modes pass recomputed contract"


def check_arena_suite(proof):
    return _suite(proof, ARENA_MODES)

def check_large_suite(proof):
    return _suite(proof, LARGE_MODES)

def check_arcade_suite(proof):
    return _suite(proof, ARCADE_MODES)

def check_ui_foundation(proof):
    return _suite(proof, ["ui.foundation"])

def check_wanetrial(proof):
    idx = _by_name(proof)
    if "trial.wanetrial" not in idx:
        return False, "trial.wanetrial absent"
    ok = recompute_mode(idx["trial.wanetrial"])
    return ok, "wanetrial second-chance contract" + ("" if ok else " VIOLATED")

def check_practice(proof):
    idx = _by_name(proof)
    if "practice.range" not in idx:
        return False, "practice.range absent"
    ok = recompute_mode(idx["practice.range"])
    return ok, "practice endless/no-winner contract" + ("" if ok else " VIOLATED")

def check_demo_covered(proof):
    idx = _by_name(proof)
    missing = [n for n in DEMO_MODES if n not in idx or not recompute_mode(idx[n])]
    if missing:
        return False, f"demo modes not green: {missing}"
    return True, "TDM + WaneTrial + PracticeRange green"

def check_recompute_all(proof):
    mism = [m.get("name") for m in proof.get("modes", [])
            if bool(m.get("pass")) != recompute_mode(m)]
    if mism:
        return False, f"reported pass != recomputed for: {mism}"
    return True, f"all {len(proof.get('modes', []))} modes recompute-consistent"


# ---------------------------------------------------------------- commandlet run + harvest

# Absolute (anchored to ROOT), NOT a bare relative path: run_commandlet_and_harvest() writes here and
# load_proof()/harvested_proof_path() read from here, so both sides agree regardless of process CWD.
ARTIFACT_DIR = ROOT / "artifacts" / "mode_contract"
ARTIFACT_PROOF = ARTIFACT_DIR / "mode_sim_proof.json"

# The commandlet is pure (no World/RHI/wall-clock/randomness) and runs in seconds, so a tight
# freshness ceiling is cheap: every `--domain mode_contract` run re-harvests the proof anyway.
PROOF_MAX_AGE_SECONDS = 24 * 60 * 60


class ModeContractBlocked(Exception):
    """Raised when the proof cannot be produced/harvested -- maps to BLOCKED, never PASS."""


def run_commandlet_and_harvest():
    """Launch the mode-sim commandlet, copy its proof into artifacts/. Returns proof path."""
    editor = UE_CMD
    uproject = UPROJECT
    if not os.path.isfile(str(editor)):
        raise ModeContractBlocked(f"UnrealEditor-Cmd.exe not found: {editor}")
    if not os.path.isfile(str(uproject)):
        raise ModeContractBlocked(f"WanefallGreybox.uproject not found: {uproject}")
    saved = os.path.join(os.path.dirname(str(uproject)), "Saved", "ShowMeAI")
    src = os.path.join(saved, "mode_sim_proof.json")
    done = os.path.join(saved, "mode_sim_proof_done.json")
    # Delete stale proof BEFORE launch so a leftover file can't masquerade as a fresh success.
    for p in (src, done):
        if os.path.isfile(p):
            os.remove(p)
    proc = subprocess.run(
        [str(editor), str(uproject), "-run=WanefallModeSimProof", "-stdout", "-unattended", "-nosplash"],
        capture_output=True, text=True, timeout=600,
    )
    # NOTE: the editor process may exit nonzero from UNRELATED plugin noise (e.g. an MCP/
    # HttpListener bind failure on 127.0.0.1:8000) even when the commandlet itself succeeded.
    # The atomic success signal is the .done marker (written LAST, only after the proof write).
    # So gate on the marker + a freshly-written proof, not on returncode. returncode/stderr are
    # captured only to explain a BLOCK when the marker is genuinely absent.
    if not os.path.isfile(done):
        tail = (proc.stderr or proc.stdout or "")[-400:]
        raise ModeContractBlocked(
            f"mode_sim_proof_done marker absent (commandlet did not complete; exit={proc.returncode}); tail: {tail}")
    if not os.path.isfile(src):
        raise ModeContractBlocked("mode_sim_proof.json not produced despite done marker")
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    shutil.copyfile(src, ARTIFACT_PROOF)
    return ARTIFACT_PROOF


# Process-wide harvest cache: the commandlet must run ONCE per suite invocation, not once per
# validator -- nine validators share this cached path/error so a single commandlet failure
# BLOCKs all nine gates instead of relaunching UE nine times.
_HARVEST_CACHE: dict = {}


def harvested_proof_path():
    """Harvest the commandlet proof once per process; every validator shares the result/error."""
    if not _HARVEST_CACHE:
        try:
            _HARVEST_CACHE["path"] = run_commandlet_and_harvest()
        except ModeContractBlocked as exc:
            _HARVEST_CACHE["error"] = str(exc)
    if "error" in _HARVEST_CACHE:
        raise ModeContractBlocked(_HARVEST_CACHE["error"])
    return _HARVEST_CACHE["path"]
