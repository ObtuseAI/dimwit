"""Check or explicitly apply Dimwit's reviewed patches to clean upstream neural3d submodules."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES = (
    (ROOT / "neural3d" / "InstantMesh", ROOT / "third_party" / "patches" / "instantmesh-dimwit.patch"),
    (ROOT / "neural3d" / "TripoSR", ROOT / "third_party" / "patches" / "triposr-dimwit.patch"),
)


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, shell=False)


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    failures = []
    for checkout, patch in PATCHES:
        if not checkout.is_dir() or not patch.is_file():
            failures.append(f"missing checkout or patch: {checkout} / {patch}")
            continue
        reverse = run(["git", "apply", "--reverse", "--check", str(patch)], checkout)
        if reverse.returncode == 0:
            print(f"already applied: {patch.name}")
            continue
        check = run(["git", "apply", "--check", str(patch)], checkout)
        if check.returncode != 0:
            failures.append(f"patch does not apply cleanly: {patch.name}: {check.stderr.strip()}")
            continue
        if apply:
            result = run(["git", "apply", str(patch)], checkout)
            if result.returncode != 0:
                failures.append(f"apply failed: {patch.name}: {result.stderr.strip()}")
            else:
                print(f"applied: {patch.name}")
        else:
            print(f"ready: {patch.name} (use --apply to mutate the submodule)")
    for failure in failures:
        print(f"BLOCKED: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
