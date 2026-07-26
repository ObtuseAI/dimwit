from __future__ import annotations

import json
from pathlib import Path

import pytest

from dimwit.toolchains.common import output_proofs, sha256_file
from dimwit.toolchains.engines.cross_engine import compare_build_receipts


def _receipt(path: Path, engine: str, target: str, brief: Path, artifact: Path) -> Path:
    artifact.mkdir(parents=True)
    (artifact / "game.bin").write_bytes((engine + " build").encode())
    payload = {
        "state": "PASS", "ok": True, "review_ceiling": "PROMOTED_TO_REVIEW",
        "plan": {"engine": engine, "target": target, "profile": "release",
                 "metadata": {"brief_sha256": sha256_file(brief)}},
        "output_proofs": output_proofs([artifact]),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cross_engine_proof_requires_real_distinct_comparable_builds(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Build the same arena game.", encoding="utf-8")
    first = _receipt(tmp_path / "ue.json", "unreal", "windows", brief, tmp_path / "ue-build")
    second = _receipt(tmp_path / "godot.json", "godot", "windows", brief, tmp_path / "godot-build")
    output = tmp_path / "cross-engine.json"
    report = compare_build_receipts(brief, [first, second], output, allowed_output_roots=[tmp_path])
    assert report["state"] == "PASS"
    assert report["engines"] == ["godot", "unreal"]
    assert report["target"] == "windows"
    assert report["comparable"] is True
    assert output.is_file()
    with pytest.raises(ValueError, match="escapes allowed roots"):
        compare_build_receipts(brief, [first, second], tmp_path.parent / "escaped.json",
                               allowed_output_roots=[tmp_path])


def test_cross_engine_proof_blocks_hash_drift_and_brief_mismatch(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Build the same arena game.", encoding="utf-8")
    first = _receipt(tmp_path / "ue.json", "unreal", "windows", brief, tmp_path / "ue-build")
    second = _receipt(tmp_path / "godot.json", "godot", "linux", brief, tmp_path / "godot-build")
    (tmp_path / "godot-build" / "game.bin").write_bytes(b"tampered")
    brief.write_text("A different brief.", encoding="utf-8")
    report = compare_build_receipts(brief, [first, second])
    assert report["state"] == "BLOCKED"
    assert any("hash mismatch" in issue for issue in report["issues"])
    assert any("not bound" in issue for issue in report["issues"])
    assert any("same platform" in issue for issue in report["issues"])
