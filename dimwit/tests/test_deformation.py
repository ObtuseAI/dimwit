"""Proof for the rig DEFORMATION metric (perception.deformation_health / rig_deformation_over_poses) — the
#32 layer that structural rig QA (weights/influences/bones) is blind to. Stdlib + numpy/Pillow.
Run:  python -m dimwit.tests.test_deformation

Locks the three deformation failure modes a real rig hits + the healthy case:
  * a clean arms-up pose (similar area, one connected silhouette) PASSES;
  * a candy-wrapper/twist COLLAPSE (silhouette pinches to nothing) FAILS;
  * a skinning EXPLOSION (area blows up) FAILS;
  * a skinning TEAR (silhouette fragments into detached shards) FAILS on connectedness;
  * the rig's score is the WORST pose (weakest-link), and any unmeasurable pose is fail-closed BLOCKED.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit import perception

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_deform_"))
_BG = (60, 62, 66)


def _img():
    return Image.new("RGB", (240, 320), _BG)


def _bind(path):
    im = _img(); d = ImageDraw.Draw(im)
    d.ellipse([100, 24, 140, 64], fill=(80, 190, 190))       # head
    d.rectangle([95, 64, 145, 200], fill=(80, 190, 190))     # torso
    d.rectangle([70, 70, 100, 170], fill=(80, 190, 190))     # left arm down
    d.rectangle([140, 70, 170, 170], fill=(80, 190, 190))    # right arm down
    d.rectangle([98, 200, 118, 300], fill=(70, 170, 170))    # left leg
    d.rectangle([122, 200, 142, 300], fill=(70, 170, 170))   # right leg
    im.save(path); return str(path)


def _good_pose(path):
    """Arms raised, still one connected mass, similar area — a healthy deformation."""
    im = _img(); d = ImageDraw.Draw(im)
    d.ellipse([100, 24, 140, 64], fill=(80, 190, 190))
    d.rectangle([95, 64, 145, 200], fill=(80, 190, 190))
    d.rectangle([70, 30, 100, 130], fill=(80, 190, 190))     # left arm up (overlaps torso top)
    d.rectangle([140, 30, 170, 130], fill=(80, 190, 190))    # right arm up
    d.rectangle([98, 200, 118, 300], fill=(70, 170, 170))
    d.rectangle([122, 200, 142, 300], fill=(70, 170, 170))
    im.save(path); return str(path)


def _collapse(path):
    """Candy-wrapper twist: the whole silhouette pinched to a thin sliver — area collapses."""
    im = _img(); d = ImageDraw.Draw(im)
    d.rectangle([116, 40, 128, 300], fill=(80, 190, 190))    # thin vertical bar
    im.save(path); return str(path)


def _explosion(path):
    """Skinning blowup: vertices flung outward, silhouette fills the frame — area explodes."""
    im = _img(); d = ImageDraw.Draw(im)
    d.rectangle([15, 15, 225, 305], fill=(80, 190, 190))     # huge filled mass
    im.save(path); return str(path)


def _tear(path):
    """Skinning tear: the mesh splits into two detached halves — fragmented silhouette."""
    im = _img(); d = ImageDraw.Draw(im)
    d.rectangle([35, 70, 95, 240], fill=(80, 190, 190))      # left half
    d.rectangle([145, 70, 205, 240], fill=(80, 190, 190))    # right half (detached, gap between)
    im.save(path); return str(path)


BIND = _bind(_TMP / "bind.png")
GOOD = _good_pose(_TMP / "good.png")
COLLAPSE = _collapse(_TMP / "collapse.png")
EXPLODE = _explosion(_TMP / "explode.png")
TEAR = _tear(_TMP / "tear.png")


def test_good_pose_passes():
    r = perception.deformation_health(GOOD, BIND)
    assert r["ok"] and r["passed"], r
    assert r["deformation_score"] >= 0.85, r


def test_collapse_fails():
    r = perception.deformation_health(COLLAPSE, BIND)
    assert r["ok"] and not r["passed"], r
    assert r["area_ratio"] < 0.55, r
    assert any("COLLAPSE" in i for i in r["issues"]), r["issues"]
    assert r["deformation_score"] < 0.85, r


def test_explosion_fails():
    r = perception.deformation_health(EXPLODE, BIND)
    assert r["ok"] and not r["passed"], r
    assert r["area_ratio"] > 1.85, r
    assert any("EXPLOSION" in i for i in r["issues"]), r["issues"]


def test_tear_fails_on_connectedness():
    r = perception.deformation_health(TEAR, BIND)
    assert r["ok"] and not r["passed"], r
    assert r["connectedness"] < 0.85 and r["components"] >= 2, r
    assert any("FRAGMENTED" in i for i in r["issues"]), r["issues"]


def test_missing_pose_blocks():
    r = perception.deformation_health(_TMP / "nope.png", BIND)
    assert r["ok"] is False and r["blocked"] is True and r["deformation_score"] is None, r


def test_over_poses_worst_sets_score_and_passes_clean_set():
    clean = perception.rig_deformation_over_poses(BIND, {"arms_up": GOOD, "bind_echo": BIND})
    assert clean["ok"] and clean["passed"], clean
    # a set containing ANY bad pose fails, and the worst pose sets the score
    bad = perception.rig_deformation_over_poses(BIND, {"arms_up": GOOD, "twist": COLLAPSE, "blowup": EXPLODE})
    assert bad["ok"] and not bad["passed"], bad
    assert bad["worst_pose"] in ("twist", "blowup"), bad
    assert bad["deformation_score"] < 0.85, bad


def test_over_poses_unmeasurable_blocks():
    r = perception.rig_deformation_over_poses(BIND, {"arms_up": GOOD, "ghost": str(_TMP / "missing.png")})
    assert r["ok"] is False and r["blocked"] is True, r


def test_frozen_rig_blocks_not_passes():
    # every 'stress pose' is identical to bind (the headless-anim-needs-PIE trap): the rig never actually
    # posed, so there was no deformation to validate. A still frame has no artifacts -> the NAIVE metric would
    # score it ~1.0; the anti-frozen gate must BLOCK it instead (this is the real Ekris failure mode).
    frozen = {"idle": BIND, "walk": BIND, "run": BIND, "jump": BIND}
    r = perception.rig_deformation_over_poses(BIND, frozen)
    assert r["ok"] is False and r["blocked"] is True, r
    assert r["deformation_score"] is None and not r.get("passed"), r
    assert "FROZEN" in r["reason"], r["reason"]


def test_moving_rig_is_not_falsely_frozen():
    # a genuinely posed set (poses differ from bind) must NOT trip the anti-frozen gate
    r = perception.rig_deformation_over_poses(BIND, {"arms_up": GOOD, "bind_echo": BIND, "twist2": GOOD})
    assert r["ok"] is True, r            # GOOD differs from BIND enough to count as 'moved'


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
