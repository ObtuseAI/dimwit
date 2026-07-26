"""CONTENT_UNDER_LFS_V1 (Horizon 2) — doctrine lock for the WANEFALL content-versioning decision.

The ~2.5G of authored `Content/Wanefall/**` is irreplaceable and is versioned via Git LFS (the 19G of
redownloadable Epic marketplace packs stay gitignored). Nothing but discipline keeps that true: a stray
`.gitattributes` edit, a blanket `Content/` ignore, or a re-tracked raw binary silently un-versions the
authored content and the next machine loses it. This gate makes that regression fail-closed.

Three layers, cheapest first (all static / filesystem, no UE runtime, no re-cook):
  1. LFS filter contract — `.gitattributes` routes every required Content/Wanefall extension through
     `filter=lfs diff=lfs merge=lfs` (uasset/umap/png/tga/fbx/wav). Dropping a rule -> fail.
  2. ignore carve-out — `.gitignore` does not leave Content/Wanefall ignored (a broad `Content/*`
     must be re-included by `!Content/Wanefall/`). Losing the negation -> fail.
  3. real-asset proof — a sample of on-disk `*.uasset` is resolved through `git check-attr filter`
     and must report `lfs`. Contract present but not in force (raw-committed asset) -> fail. git
     unavailable -> BLOCKED (never a silent pass).

Fail-closed on missing/unreadable `.gitattributes` / `.gitignore` (BlockedError at the validator).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
CONTENT_ROOT = PROJECT / "Content" / "Wanefall"
GITATTRIBUTES = PROJECT / ".gitattributes"
GITIGNORE = PROJECT / ".gitignore"

# Binary asset extensions that MUST be LFS-routed under Content/Wanefall.
REQUIRED_LFS_EXTS = ("uasset", "umap", "png", "tga", "fbx", "wav")
# All three tokens must be present for a rule to count as a full LFS filter (not a half-applied one).
LFS_TOKENS = ("filter=lfs", "diff=lfs", "merge=lfs")
# LFS rules must be scoped to the authored tree, never the whole Content/ dir.
CONTENT_PREFIX = "Content/Wanefall/"
# Path the ignore-precedence walk resolves.
_IGNORE_TARGET = "Content/Wanefall"

# Max on-disk assets resolved through git check-attr (bounded — the proof is a sample, not a census).
SAMPLE_N = 8


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def live_gitattributes() -> str | None:
    return _read(GITATTRIBUTES)


def live_gitignore() -> str | None:
    return _read(GITIGNORE)


# ---------------------------------------------------------------- 1. LFS filter contract
def parse_lfs_exts(gitattributes_text: str) -> set[str]:
    """Extensions under Content/Wanefall that carry a FULL LFS filter (all three tokens)."""
    exts: set[str] = set()
    for raw in gitattributes_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        pattern = fields[0]
        if not pattern.startswith(CONTENT_PREFIX):
            continue
        if not all(tok in line for tok in LFS_TOKENS):
            continue
        if "." in pattern:
            exts.add(pattern.rsplit(".", 1)[1].lower())
    return exts


def check_lfs_attrs(gitattributes_text: str) -> dict:
    if not gitattributes_text or not gitattributes_text.strip():
        return {"passed": False, "issues": [".gitattributes empty/unreadable"], "missing": list(REQUIRED_LFS_EXTS)}
    have = parse_lfs_exts(gitattributes_text)
    missing = [e for e in REQUIRED_LFS_EXTS if e not in have]
    if missing:
        return {"passed": False,
                "issues": [f"Content/Wanefall LFS filter missing for: {missing}"],
                "missing": missing}
    return {"passed": True, "issues": [], "missing": []}


# ---------------------------------------------------------------- 2. ignore carve-out
def _covers_target(pattern: str) -> bool:
    """Does a .gitignore pattern (already stripped of a leading '!') apply to Content/Wanefall?"""
    base = pattern.strip().rstrip("/")
    for suffix in ("/**", "/*"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    base = base.rstrip("/")
    if not base:
        return False
    return _IGNORE_TARGET == base or _IGNORE_TARGET.startswith(base + "/")


def wanefall_is_ignored(gitignore_text: str) -> bool:
    """Simulate gitignore last-match-wins precedence for the Content/Wanefall path."""
    ignored = False
    for raw in gitignore_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        neg = line.startswith("!")
        pattern = line[1:] if neg else line
        if _covers_target(pattern):
            ignored = not neg
    return ignored


def check_gitignore_carveout(gitignore_text: str) -> dict:
    if gitignore_text is None:
        return {"passed": False, "issues": [".gitignore unreadable"]}
    if wanefall_is_ignored(gitignore_text):
        return {"passed": False,
                "issues": ["Content/Wanefall is gitignored (carve-out lost) — authored content untracked"]}
    return {"passed": True, "issues": []}


# ---------------------------------------------------------------- 3. real-asset proof
def sample_assets(content_root: Path, n: int = SAMPLE_N) -> list[Path]:
    try:
        found = sorted(content_root.rglob("*.uasset"))
    except Exception:
        return []
    return found[:n]


def evaluate_check_attr_output(stdout: str, expected_posix: list[str]) -> dict:
    """Parse `git check-attr filter` output; every expected path must resolve to filter=lfs."""
    resolved: dict[str, str] = {}
    for line in stdout.splitlines():
        if ": filter: " not in line:
            continue
        path, val = line.rsplit(": filter: ", 1)
        resolved[path.strip()] = val.strip()
    untracked = [p for p in expected_posix if resolved.get(p) != "lfs"]
    if untracked:
        return {"passed": False,
                "issues": [f"on-disk assets not LFS-tracked (filter != lfs): {untracked[:5]}"],
                "untracked": untracked}
    return {"passed": True, "issues": [], "untracked": []}


def _default_git_runner(project_root: Path, rel_posix: list[str]):
    cmd = ["git", "-C", str(project_root), "check-attr", "filter", "--", *rel_posix]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _default_index_reader(project_root: Path, rel_posix: str) -> dict:
    tracked = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "--error-unmatch", "--", rel_posix],
        capture_output=True, text=True, timeout=60,
    )
    if tracked.returncode != 0:
        return {"tracked": False, "content": b"", "error": tracked.stderr}
    blob = subprocess.run(
        ["git", "-C", str(project_root), "show", f":{rel_posix}"],
        capture_output=True, timeout=60,
    )
    return {"tracked": blob.returncode == 0, "content": blob.stdout,
            "error": blob.stderr.decode("utf-8", errors="replace")}


def evaluate_index_lfs(rows: dict[str, dict]) -> dict:
    pointer_prefix = b"version https://git-lfs.github.com/spec/v1\n"
    invalid = []
    for path, row in rows.items():
        if not row.get("tracked") or not bytes(row.get("content") or b"").startswith(pointer_prefix):
            invalid.append(path)
    return {"passed": not invalid,
            "issues": [] if not invalid else [f"assets absent from the Git index or stored as raw blobs: {invalid[:5]}"],
            "invalid_index_assets": invalid}


def check_assets_lfs_tracked(project_root: Path, content_root: Path, runner=None,
                             index_reader=None, n: int = SAMPLE_N) -> dict:
    """Resolve a sample of real assets through git's attribute stack. runner is injectable for tests."""
    runner = runner or _default_git_runner
    assets = sample_assets(content_root, n)
    if not assets:
        return {"passed": False, "blocked": False,
                "issues": [f"no Content/Wanefall *.uasset found on disk under {content_root}"],
                "checked": 0}
    rel_posix = [a.relative_to(project_root).as_posix() for a in assets]
    try:
        res = runner(project_root, rel_posix)
    except FileNotFoundError:
        return {"passed": False, "blocked": True,
                "issues": ["git unavailable — cannot verify Content/Wanefall LFS tracking"], "checked": 0}
    if getattr(res, "returncode", 0) != 0:
        return {"passed": False, "blocked": True,
                "issues": [f"git check-attr failed: {getattr(res, 'stderr', '')[:200]}"], "checked": 0}
    out = evaluate_check_attr_output(res.stdout, rel_posix)
    if out["passed"]:
        index_reader = index_reader or _default_index_reader
        try:
            index_rows = {path: index_reader(project_root, path) for path in rel_posix}
        except FileNotFoundError:
            return {"passed": False, "blocked": True,
                    "issues": ["git unavailable — cannot inspect indexed LFS pointers"], "checked": 0}
        index_result = evaluate_index_lfs(index_rows)
        out.update(index_result)
    out["checked"] = len(rel_posix)
    out["blocked"] = False
    return out
