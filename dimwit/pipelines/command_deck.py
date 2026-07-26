"""COMMAND_DECK_TRUTH_V1 (masterplan Horizon 1, bundle 7; B4) — command-deck honesty checks.

The packaged front door (`Wanefall_ModeShell_Prototype_01` + WanefallLobbyGameMode ->
AWanefallLobbyHUD) must not draw fiction the game cannot back: no hardcoded rank/leaderboard
numbers, no fake stats, no internal dev jargon or debug strings leaked to players. Panels are
either bound to the REAL local profile (`UWanefallProfileSubsystem` / FWanefallPlayerProfile) or
show an HONEST empty/coming-soon state.

These are STATIC source scans (pure functions over file text) — the fiction lives in the HUD
source; the packaged still + own-eyes review prove it renders truthfully after the repackage.
Fail-closed: a missing/unreadable source fails every check.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
UI_SOURCE = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallLobbyHUD.cpp"
SUBSYSTEM_HEADER = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallProfileSubsystem.h"
SUBSYSTEM_SOURCE = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallProfileSubsystem.cpp"

# Fiction / dev-jargon / debug tokens that must never reach the packaged command deck. Matched
# case-insensitively as substrings. RATCHET-ONLY: tokens may be ADDED, never removed
# (test_fiction_blocklist_is_ratchet). The fake leaderboard handles are the literal pre-fix rows.
FICTION_TOKENS = (
    # internal dev jargon leaked to players (masterplan-named blocker class)
    "melee-safe",
    "sandbox",
    # fabricated liveness / sync claims
    "synchronized",
    "playlists staged",
    "refresh armed",
    "channels synchronized",
    # the hardcoded fake leaderboard handles + stat literal
    "zythan_prime",
    "apexkelous",
    "therak_77",
    "nexorbyte",
    "1.42 k/d",
    # debug / placeholder leakage
    "todo",
    "fixme",
    "debug",
    "placeholder",
    "lorem",
)

# Real-data-binding proof: the HUD must reference the profile subsystem + real accessors, so the
# panels are data-bound rather than literal. At least MIN_PROFILE_HITS distinct tokens required.
PROFILE_BINDING_TOKENS = (
    "ProfileSubsystem",
    "GetProfile",
    "RankState",
    "ModeStats",
    "KD(",
    "TierName",
    "Leaderboard",
    "AccountLevel",
)
MIN_PROFILE_HITS = 3

# Honest empty-state proof: at least these fallback strings must be present so no-data renders
# honestly instead of faking values.
HONEST_FALLBACK_TOKENS = (
    "UNRANKED",
    "NO LOCAL RECORDS",
    "COMING SOON",
)

# PROGRESSION_PERSISTENCE_V1 §B6 (Task 7): the deck must surface EARNED challenges from the real
# progression subsystem challenge book — not a hardcoded objective list. These tokens prove the
# CHALLENGES panel is bound to UWanefallProgressionSubsystem and renders live Progress/Target.
PROGRESSION_BINDING_TOKENS = (
    "ProgressionSubsystem",
    "Challenges()",
    "FWanefallChallenge",
)
PROGRESSION_MIN_HITS = 3
PROGRESSION_HEADER_TOKEN = "CHALLENGES"
PROGRESSION_EMPTY_STATE = "NO ACTIVE CHALLENGES"
# live per-challenge progress must be rendered (C.Progress / C.Target), else the bar could be faked
PROGRESSION_LIVE_TOKENS = ("Progress", "Target")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _without_cpp_comments(text: str) -> str:
    """Remove C/C++ comments while preserving string and character literals."""
    out = []
    i = 0
    quote = None
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            out.append("\n")
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and text[i:i + 2] != "*/":
                out.append("\n" if text[i] in "\r\n" else " ")
                i += 1
            i = min(len(text), i + 2)
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def scan_ui_fiction(text: str, tokens=FICTION_TOKENS) -> dict:
    """Any blocklisted fiction/jargon/debug token present -> fail. Pure over the source text."""
    if not isinstance(text, str) or not text:
        return {"passed": False, "issues": ["command-deck source empty/unreadable"], "hits": []}
    low = text.lower()
    hits = [t for t in tokens if t.lower() in low]
    return {"passed": not hits, "issues": [f"command-deck fiction/jargon token present: {t!r}"
                                           for t in hits], "hits": hits}


def check_reads_real_profile(text: str) -> dict:
    if not isinstance(text, str) or not text:
        return {"passed": False, "issues": ["command-deck source empty/unreadable"], "found": []}
    code = _without_cpp_comments(text)
    found = [t for t in PROFILE_BINDING_TOKENS if t in code]
    if len(found) < MIN_PROFILE_HITS:
        return {"passed": False,
                "issues": [f"command deck references only {len(found)} real-profile accessor(s) "
                           f"({found}) < {MIN_PROFILE_HITS} — panels are not data-bound"],
                "found": found}
    return {"passed": True, "issues": [], "found": found}


def check_honest_empty_states(text: str) -> dict:
    if not isinstance(text, str) or not text:
        return {"passed": False, "issues": ["command-deck source empty/unreadable"],
                "missing": list(HONEST_FALLBACK_TOKENS)}
    code = _without_cpp_comments(text)
    missing = [t for t in HONEST_FALLBACK_TOKENS if t not in code]
    if missing:
        return {"passed": False,
                "issues": [f"honest empty-state string missing: {t!r}" for t in missing],
                "missing": missing}
    return {"passed": True, "issues": [], "missing": []}


def check_reads_earned_progression(text: str) -> dict:
    """The command deck must surface EARNED challenges: a CHALLENGES panel bound to the real
    progression subsystem challenge book, rendering live Progress/Target, with an honest empty
    state. Fail-closed on missing/unreadable source. Pure over the source text."""
    if not isinstance(text, str) or not text:
        return {"passed": False, "issues": ["command-deck source empty/unreadable"], "found": []}
    issues = []
    code = _without_cpp_comments(text)
    found = [t for t in PROGRESSION_BINDING_TOKENS if t in code]
    if len(found) < PROGRESSION_MIN_HITS:
        issues.append(f"CHALLENGES panel binds only {len(found)} progression token(s) ({found}) "
                      f"< {PROGRESSION_MIN_HITS} — challenges are not read from the real subsystem")
    if PROGRESSION_HEADER_TOKEN not in code:
        issues.append(f"no CHALLENGES panel header ({PROGRESSION_HEADER_TOKEN!r}) on the deck")
    missing_live = [t for t in PROGRESSION_LIVE_TOKENS if t not in code]
    if missing_live:
        issues.append(f"challenge rows never render live progress (missing {missing_live}) — "
                      f"a static/faked bar")
    if PROGRESSION_EMPTY_STATE not in code:
        issues.append(f"no honest empty state ({PROGRESSION_EMPTY_STATE!r}) — a challenge-less "
                      f"profile would render blank or faked")
    return {"passed": not issues, "issues": issues, "found": found}


def check_profile_subsystem(header_text: str, source_text: str) -> dict:
    """The real data source must be real code: a UGameInstanceSubsystem that loads-or-defaults the
    local profile. Fail-closed if either file is missing."""
    issues = []
    if not isinstance(header_text, str) or not header_text:
        issues.append("WanefallProfileSubsystem.h missing/unreadable")
    else:
        if "UGameInstanceSubsystem" not in header_text:
            issues.append("profile subsystem is not a UGameInstanceSubsystem")
        if "UWanefallProfileSubsystem" not in header_text:
            issues.append("UWanefallProfileSubsystem class not declared")
        if "GetProfile" not in header_text:
            issues.append("profile subsystem exposes no GetProfile accessor")
    if not isinstance(source_text, str) or not source_text:
        issues.append("WanefallProfileSubsystem.cpp missing/unreadable")
    else:
        if "MakeDefault" not in source_text:
            issues.append("profile subsystem has no default-profile fallback (MakeDefault)")
        if "FromJson" not in source_text:
            issues.append("profile subsystem never loads a persisted profile (no FromJson)")
    return {"passed": not issues, "issues": issues}


# ---- live-file readers (used by the registry validators) ----

def live_ui_text() -> str | None:
    return _read(UI_SOURCE)


def live_subsystem_texts() -> tuple[str | None, str | None]:
    return _read(SUBSYSTEM_HEADER), _read(SUBSYSTEM_SOURCE)
