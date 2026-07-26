# ROSTER_FIDELITY_V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring all 14 active WANEFALL roster characters (6 humanoids + 8 mechs) to deformation-free, in-match animated fidelity and gate that fidelity in the validation suite.

**Architecture:** Extend the two proven pipelines (`rigging.py`, `animation.py`) to cover all 14 active characters through one shared SK_Mannequin retarget. Add a rigid per-plate weight mode to the Blender auto-rig for hard-surface mechs. Accumulate a per-character fidelity cert (rig + anim + deformation) and add a new `character_roster_fidelity` suite domain that gates every active roster character plus a coverage gate.

**Tech Stack:** Python 3.14, Blender 5.1 headless (`bpy`), Unreal Editor 5.8 (`UnrealEditor-Cmd.exe` + `-ExecutePythonScript`), pytest.

## Global Constraints

- Doctrine: fail-closed. Missing input → `BlockedError` → BLOCKED, never PASS.
- Doctrine ceiling stays `PROMOTED_TO_REVIEW`. Never write `HUMAN_ACCEPTED` / `PROMOTED_TO_ACTIVE_SLICE`.
- Validators may only be added or hardened, never weakened. `DEFORM_FLOOR = 0.85` held for all 14 — do NOT lower it for mechs.
- Scope = 14 active characters only. `vorlax` (01) and `ekris` (02) stay QUARANTINED, untouched, not un-quarantined.
- Rig target skeleton for every character: `/Game/Mannequins/Meshes/SK_Mannequin.SK_Mannequin`.
- Mech decimation input: `artifacts/ue_staging_new/<Asset>.glb`. Skinning mesh output: `artifacts/ue_staging_sym/<Asset>.glb` (~45k tris).
- Rigged asset UE path: `/Game/Wanefall/Dimwit/CharactersRigged/<Asset>_Rig`.
- Cert store: `artifacts/roster_fidelity/<Asset>.json`.
- Commit message trailer (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01QCnxq5Ed7S2csjrMjqf8R2
  ```

## File Structure

- Create `dimwit/pipelines/roster_fidelity.py` — 14-target roster list, cert read/write, cert validation, coverage. Pure Python, no `bpy`/`unreal` at module top.
- Create `tests/test_roster_fidelity.py` — units for the above.
- Create `blender_scripts/decimate_for_skinning.py` — headless decimate a full glb to ~45k, export skinning glb.
- Modify `blender_scripts/rig_to_mannequin.py` — add `rigid=true` mode (single-bone weights).
- Modify `dimwit/pipelines/rigging.py` — `ASSET_FOR` +8 mechs, per-char `rigid` flag, mech skinning-mesh prereq.
- Modify `dimwit/pipelines/animation.py` — `ASSET_FOR` +8 mechs.
- Modify `dimwit/pipelines/validation_registry.py` — new `character_roster_fidelity` domain: per-char (14) cert validators + coverage gate.
- Create `scripts/pipeline/run_roster_fidelity.py` — batch driver: for each target, decimate (mech) → rig → anim → deform capture → write cert.

---

### Task 1: Roster fidelity target list + cert store

**Files:**
- Create: `dimwit/pipelines/roster_fidelity.py`
- Test: `tests/test_roster_fidelity.py`

**Interfaces:**
- Produces:
  - `ACTIVE_ROSTER_TARGETS: list[dict]` — 14 dicts `{"key": str, "asset": str, "kind": "humanoid"|"mech", "rigid": bool}`.
  - `active_roster_targets(root=ROOT) -> list[dict]` — `ACTIVE_ROSTER_TARGETS` filtered to exclude any quarantined character (fail-safe; mechs are never quarantined, humanoid quarantine already excludes vorlax/ekris).
  - `cert_path(asset: str, root=ROOT) -> Path`
  - `write_cert(asset, kind, rig_result: dict, anim_result: dict, deform_result: dict, root=ROOT) -> dict`
  - `load_cert(asset, root=ROOT) -> dict` — raises `BlockedError` if the cert file is missing/unreadable.
  - `validate_cert(cert: dict) -> dict` — `{"passed": bool, "issues": list[str]}`.
  - `roster_fidelity_coverage(root=ROOT) -> dict` — `{"passed": bool, "issues": list[str], "covered": list[str], "missing": list[str]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roster_fidelity.py
import json
from pathlib import Path
import pytest
from dimwit.pipelines import roster_fidelity as rf
from dimwit.pipelines.base import BlockedError


def test_active_targets_cover_14_active_roster():
    targets = rf.active_roster_targets()
    assert len(targets) == 14
    humanoids = [t for t in targets if t["kind"] == "humanoid"]
    mechs = [t for t in targets if t["kind"] == "mech"]
    assert len(humanoids) == 6 and len(mechs) == 8
    keys = {t["key"] for t in targets}
    # quarantined humanoids excluded
    assert "vorlax" not in keys and "ekris" not in keys
    # mechs are rigid, humanoids are smooth
    assert all(t["rigid"] for t in mechs)
    assert all(not t["rigid"] for t in humanoids)


def test_validate_cert_requires_all_three_legs():
    good = {"rig": {"passed": True}, "anim": {"passed": True},
            "deformation": {"passed": True, "score": 0.9}}
    assert rf.validate_cert(good)["passed"] is True
    for leg in ("rig", "anim", "deformation"):
        bad = json.loads(json.dumps(good))
        bad[leg]["passed"] = False
        assert rf.validate_cert(bad)["passed"] is False


def test_load_cert_fail_closed(tmp_path):
    with pytest.raises(BlockedError):
        rf.load_cert("SM_Char_Does_Not_Exist", root=tmp_path)


def test_coverage_missing_when_no_certs(tmp_path):
    cov = rf.roster_fidelity_coverage(root=tmp_path)
    assert cov["passed"] is False
    assert len(cov["missing"]) == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/developer/Documents/Dimwit && python -m pytest tests/test_roster_fidelity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dimwit.pipelines.roster_fidelity'`.

- [ ] **Step 3: Write minimal implementation**

```python
# dimwit/pipelines/roster_fidelity.py
"""ROSTER_FIDELITY_V1 — per-character rig+anim+deformation cert store + active-roster coverage.

Fail-closed: a missing/unreadable cert is BLOCKED, never a silent pass. Pure Python (no bpy/unreal at
module top) so it imports under pytest and the suite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import BlockedError
from .character_roster import active_mech_characters, is_quarantined_character

ROOT = Path(__file__).resolve().parents[2]
CERT_DIR = ROOT / "artifacts" / "roster_fidelity"

# 6 active humanoids (vorlax/ekris are quarantined and excluded here).
_HUMANOIDS = [
    ("zythan", "SM_Char_03_zythan"), ("qorin", "SM_Char_04_qorin"),
    ("therak", "SM_Char_05_therak"), ("ullio", "SM_Char_06_ullio"),
    ("kelous", "SM_Char_07_kelous"), ("nexor", "SM_Char_08_nexor"),
]


def _mech_targets() -> list[dict[str, Any]]:
    out = []
    for mech in active_mech_characters(ROOT):
        out.append({"key": str(mech["key"]), "asset": str(mech["asset_name"]),
                    "kind": "mech", "rigid": True})
    return out


ACTIVE_ROSTER_TARGETS: list[dict[str, Any]] = [
    {"key": k, "asset": a, "kind": "humanoid", "rigid": False} for k, a in _HUMANOIDS
] + _mech_targets()


def active_roster_targets(root: Path = ROOT) -> list[dict[str, Any]]:
    return [t for t in ACTIVE_ROSTER_TARGETS
            if not is_quarantined_character(t["key"], root)
            and not is_quarantined_character(t["asset"], root)]


def cert_path(asset: str, root: Path = ROOT) -> Path:
    return Path(root) / "artifacts" / "roster_fidelity" / f"{asset}.json"


def write_cert(asset: str, kind: str, rig_result: dict, anim_result: dict,
               deform_result: dict, root: Path = ROOT) -> dict[str, Any]:
    cert = {
        "schema_version": 1,
        "asset": asset,
        "kind": kind,
        "rig": rig_result,
        "anim": anim_result,
        "deformation": deform_result,
    }
    path = cert_path(asset, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
    return cert


def load_cert(asset: str, root: Path = ROOT) -> dict[str, Any]:
    path = cert_path(asset, root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"roster-fidelity cert missing/unreadable for {asset}: {e}")
    if not isinstance(data, dict):
        raise BlockedError(f"roster-fidelity cert malformed for {asset}")
    return data


def validate_cert(cert: dict) -> dict[str, Any]:
    issues: list[str] = []
    for leg in ("rig", "anim", "deformation"):
        sub = cert.get(leg) or {}
        if not sub.get("passed"):
            issues.append(f"{cert.get('asset', '?')}: {leg} not passed")
    deform = cert.get("deformation") or {}
    score = deform.get("score")
    if deform.get("passed") and (score is None or float(score) < 0.85):
        issues.append(f"{cert.get('asset', '?')}: deformation score {score} < 0.85")
    return {"passed": not issues, "issues": issues}


def roster_fidelity_coverage(root: Path = ROOT) -> dict[str, Any]:
    covered, missing, issues = [], [], []
    for t in active_roster_targets(root):
        asset = t["asset"]
        try:
            cert = load_cert(asset, root)
        except BlockedError:
            missing.append(asset)
            continue
        result = validate_cert(cert)
        if result["passed"]:
            covered.append(asset)
        else:
            missing.append(asset)
            issues.extend(result["issues"])
    return {"passed": not missing, "issues": issues, "covered": covered, "missing": missing}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_roster_fidelity.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add dimwit/pipelines/roster_fidelity.py tests/test_roster_fidelity.py
git commit -m "feat(roster-fidelity): 14-target cert store + coverage gate"
```

---

### Task 2: Extend rigging.py to mechs (ASSET_FOR + rigid flag + skinning prereq)

**Files:**
- Modify: `dimwit/pipelines/rigging.py:35-39` (`ASSET_FOR`), `:96-109` (`plan`), `:111-137` (`execute`)
- Test: `tests/test_rigging_roster.py`

**Interfaces:**
- Consumes: `roster_fidelity.active_roster_targets` (asset names + rigid flags).
- Produces: `RiggingPipeline.plan(task)` returns a plan dict that additionally carries `"rigid": bool`; `ASSET_FOR` resolves all 14 active keys.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rigging_roster.py
from dimwit.pipelines.rigging import ASSET_FOR
from dimwit.pipelines.roster_fidelity import active_roster_targets


def test_asset_for_covers_all_14_active():
    keys = {t["key"] for t in active_roster_targets()}
    missing = [k for k in keys if k not in ASSET_FOR]
    assert missing == [], f"rigging.ASSET_FOR missing active roster keys: {missing}"


def test_mech_keys_map_to_mech_assets():
    assert ASSET_FOR["mech_01_glaciera"] == "SM_Char_Mech_01_Glaciera"
    assert ASSET_FOR["mech_08_nightwire"] == "SM_Char_Mech_08_Nightwire"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rigging_roster.py -v`
Expected: FAIL — `KeyError`/assertion: mech keys missing from `ASSET_FOR`.

- [ ] **Step 3: Write minimal implementation**

In `dimwit/pipelines/rigging.py`, replace the `ASSET_FOR` dict (lines 35-39) with humanoids + the 8 mechs:

```python
ASSET_FOR = {
    "vorlax": "SM_Char_01_Vorlax", "ekris": "SM_Char_02_ekris", "zythan": "SM_Char_03_zythan",
    "qorin": "SM_Char_04_qorin", "therak": "SM_Char_05_therak", "ullio": "SM_Char_06_ullio",
    "kelous": "SM_Char_07_kelous", "nexor": "SM_Char_08_nexor",
    "mech_01_glaciera": "SM_Char_Mech_01_Glaciera", "mech_02_voidrunner": "SM_Char_Mech_02_Voidrunner",
    "mech_03_aurelion": "SM_Char_Mech_03_Aurelion", "mech_04_luxorion": "SM_Char_Mech_04_Luxorion",
    "mech_05_pyroclast": "SM_Char_Mech_05_Pyroclast", "mech_06_jadewind": "SM_Char_Mech_06_Jadewind",
    "mech_07_ironline": "SM_Char_Mech_07_Ironline", "mech_08_nightwire": "SM_Char_Mech_08_Nightwire",
}

# Hard-surface mechs skin with rigid single-bone weights (armor plates must not stretch like cloth).
RIGID_KEYS = {k for k in ASSET_FOR if k.startswith("mech_")}
```

Then in `plan` (after the `mesh_glb` existence check, before the return), add the rigid flag and forward it:

```python
        rigid = plan_key in RIGID_KEYS if (plan_key := key) else False
        return {"key": key, "asset": ASSET_FOR[key], "mesh_glb": str(mesh_glb),
                "rigid": rigid,
                "out_fbx": str(ART / "rig" / f"{ASSET_FOR[key]}_rigged.fbx")}
```

Then in `execute`, pass `rigid` to the Blender call (the `subprocess.run([... RIG_SCRIPT ...])` invocation around line 119):

```python
            subprocess.run([str(BLENDER), "--background", "--python", str(RIG_SCRIPT), "--",
                            f"mannequin={MANN_FBX}", f"mesh={plan['mesh_glb']}", f"out={plan['out_fbx']}",
                            f"rigid={'true' if plan.get('rigid') else 'false'}"],
                           capture_output=True, text=True, timeout=1200)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rigging_roster.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add dimwit/pipelines/rigging.py tests/test_rigging_roster.py
git commit -m "feat(rigging): cover 8 mechs + forward rigid weight flag to Blender"
```

---

### Task 3: Extend animation.py to mechs (ASSET_FOR)

**Files:**
- Modify: `dimwit/pipelines/animation.py:43-47` (`ASSET_FOR`)
- Test: `tests/test_animation_roster.py`

**Interfaces:**
- Produces: `animation.ASSET_FOR` resolves all 14 active keys. No logic change (ABP_Manny reuse is skeleton-driven).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_animation_roster.py
from dimwit.pipelines.animation import ASSET_FOR
from dimwit.pipelines.roster_fidelity import active_roster_targets


def test_anim_asset_for_covers_all_14_active():
    keys = {t["key"] for t in active_roster_targets()}
    missing = [k for k in keys if k not in ASSET_FOR]
    assert missing == [], f"animation.ASSET_FOR missing active roster keys: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_animation_roster.py -v`
Expected: FAIL — mech keys missing.

- [ ] **Step 3: Write minimal implementation**

In `dimwit/pipelines/animation.py`, replace `ASSET_FOR` (lines 43-47) with the identical 16-entry map from Task 2 (humanoids + 8 mechs). Copy the exact dict literal shown in Task 2, Step 3.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_animation_roster.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add dimwit/pipelines/animation.py tests/test_animation_roster.py
git commit -m "feat(animation): cover 8 mechs (ABP_Manny reuse, no logic change)"
```

---

### Task 4: Rigid weight mode in the Blender auto-rig

**Files:**
- Modify: `blender_scripts/rig_to_mannequin.py` (arg parse near `:14-19`; skinning near `:240-253`; add `rigid_bone_weights`)
- Test: verified by result JSON in Task 6 pilot (`bpy` cannot be unit-tested headless without Blender).

**Interfaces:**
- Consumes: CLI arg `rigid=true|false` (from Task 2's Blender invocation).
- Produces: `<out>.rig.json` with `max_influences == 1` and `weight_coverage > 0.99` when `rigid=true`; smooth path unchanged when `rigid=false`.

- [ ] **Step 1: Parse the rigid arg**

After line 18 (`TARGET_H = float(A.get("height", 180.0))`), add:

```python
RIGID = str(A.get("rigid", "false")).lower() in ("1", "true", "yes")
res["rigid"] = RIGID
```

- [ ] **Step 2: Add the rigid weighting function**

Add next to `nearest_bone_weights` (after line 185):

```python
def rigid_bone_weights(mesh, arm):
    """RIGID hard-surface skinning: each vertex assigned 100% to its single nearest DEFORM bone (segment
    distance), no blend. Armor plates stay rigid instead of stretching. Produces max_influences == 1."""
    import mathutils
    mesh.vertex_groups.clear()
    deform = [b for b in arm.data.bones if b.use_deform] or list(arm.data.bones)
    amw = arm.matrix_world
    heads = [amw @ b.head_local for b in deform]
    tails = [amw @ b.tail_local for b in deform]
    names = [b.name for b in deform]
    mids = [(heads[i] + tails[i]) * 0.5 for i in range(len(names))]
    kd = mathutils.kdtree.KDTree(len(mids))
    for i, p in enumerate(mids):
        kd.insert(p, i)
    kd.balance()
    groups = {nme: mesh.vertex_groups.new(name=nme) for nme in set(names)}

    def seg_dist(p, a, b):
        ab = b - a
        d2 = ab.length_squared
        t = 0.0 if d2 < 1e-9 else max(0.0, min(1.0, (p - a).dot(ab) / d2))
        return (p - (a + ab * t)).length

    PREFILTER = min(len(mids), 14)
    mw = mesh.matrix_world
    for v in mesh.data.vertices:
        co = mw @ v.co
        cand = kd.find_n(co, PREFILTER)
        best = min(((seg_dist(co, heads[i], tails[i]), i) for (_, i, _) in cand), key=lambda x: x[0])[1]
        groups[names[best]].add([v.index], 1.0, "REPLACE")
    if not any(m.type == "ARMATURE" for m in mesh.modifiers):
        md = mesh.modifiers.new("Armature", "ARMATURE")
        md.object = arm
```

- [ ] **Step 3: Branch the skinning path on RIGID**

Replace the auto-weight block (lines 240-253, the `# 4) parent with automatic ... nearest_bone_weights(mesh, arm)` section) with:

```python
    # 4) skinning: rigid single-bone for hard-surface mechs, else bone-heat auto + smooth fallback
    if RIGID:
        res["skinning_mode"] = "rigid_single_bone"
        rigid_bone_weights(mesh, arm)
    else:
        res["skinning_mode"] = "smooth_auto"
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True); arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        except Exception as e:
            res["auto_weight_warn"] = str(e)
        res["auto_coverage"] = round(coverage(mesh), 4)
        if coverage(mesh) < 0.99:
            res["used_fallback"] = "nearest_bone"
            nearest_bone_weights(mesh, arm)
```

Note: the `vertex_group_limit_total(limit=4)` step (line 259) is harmless for rigid (already 1 influence) — leave it.

- [ ] **Step 4: Verification deferred to Task 6**

No standalone run here. Task 6 runs this on Glaciera and asserts `rig.json.max_influences == 1` and `skinning_mode == "rigid_single_bone"`.

- [ ] **Step 5: Commit**

```bash
git add blender_scripts/rig_to_mannequin.py
git commit -m "feat(rig): add rigid single-bone weight mode for hard-surface mechs"
```

---

### Task 5: Decimation script for mech skinning meshes

**Files:**
- Create: `blender_scripts/decimate_for_skinning.py`
- Test: run on Glaciera in this task (integration; asserts output glb + tri count).

**Interfaces:**
- Consumes: CLI args `in=<full.glb> out=<skin.glb> [target_tris=45000]`.
- Produces: `<out>` glb with triangle count within [30k, 60k]; `<out>.decim.json` with `{"ok": bool, "tris_before": int, "tris_after": int}`.

- [ ] **Step 1: Write the decimation script**

```python
# blender_scripts/decimate_for_skinning.py
"""Headless decimate a full character glb to a skinning-grade mesh (~45k tris) for rig_to_mannequin.py.
The full Nanite mesh stays the static display; only this decimated copy gets skinned.
Run: blender --background --python decimate_for_skinning.py -- in=<full.glb> out=<skin.glb> [target_tris=45000]
"""
import bpy, sys, json
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
IN, OUT = A.get("in"), A.get("out")
TARGET = int(A.get("target_tris", 45000))
res = {"ok": False, "in": IN, "out": OUT, "target_tris": TARGET}

try:
    assert IN and OUT, "need in= and out="
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.import_scene.gltf(filepath=IN)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert meshes, "no mesh imported"
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    tris_before = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    res["tris_before"] = tris_before
    if tris_before > TARGET:
        mod = mesh.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = max(0.01, min(1.0, TARGET / max(1, tris_before)))
        bpy.ops.object.modifier_apply(modifier=mod.name)
    res["tris_after"] = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format="GLB")
    res["ok"] = Path(OUT).exists()
except Exception:
    import traceback
    res["error"] = traceback.format_exc()

Path((OUT or "decim") + ".decim.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("DIMWIT_DECIM_DONE " + json.dumps({k: res.get(k) for k in ("ok", "tris_before", "tris_after")}))
```

- [ ] **Step 2: Run it on Glaciera**

Run:
```bash
cd C:/Users/developer/Documents/Dimwit && \
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python blender_scripts/decimate_for_skinning.py -- \
  in=artifacts/ue_staging_new/SM_Char_Mech_01_Glaciera.glb \
  out=artifacts/ue_staging_sym/SM_Char_Mech_01_Glaciera.glb target_tris=45000
```
Expected stdout tail: `DIMWIT_DECIM_DONE {"ok": true, "tris_before": <N>, "tris_after": <~45000>}`.

- [ ] **Step 3: Assert the output**

Run:
```bash
python -c "import json; d=json.load(open('artifacts/ue_staging_sym/SM_Char_Mech_01_Glaciera.glb.decim.json')); assert d['ok'] and 30000 <= d['tris_after'] <= 60000, d; print('OK', d['tris_after'])"
```
Expected: `OK <tris>`.

- [ ] **Step 4: Commit**

```bash
git add blender_scripts/decimate_for_skinning.py
git commit -m "feat(rig): headless decimate-for-skinning script (~45k tris)"
```

---

### Task 6: PILOT — full fidelity chain on Glaciera (mech_01), RED-first

**Files:**
- Create: `scripts/pipeline/run_roster_fidelity.py` (batch driver; runs one asset here)
- Uses: `rigging.RiggingPipeline`, `animation.AnimationPipeline`, `scripts/ue/ue_capture_poses.py`, `roster_fidelity.write_cert`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: `scripts/pipeline/run_roster_fidelity.py` with `run_one(key: str) -> dict` and `run_all() -> dict`; writes `artifacts/roster_fidelity/<Asset>.json` per target.

- [ ] **Step 1: RED — confirm the coverage gate fails for the uncertified mech**

Run:
```bash
python -c "from dimwit.pipelines.roster_fidelity import roster_fidelity_coverage as c; r=c(); assert 'SM_Char_Mech_01_Glaciera' in r['missing']; print('RED confirmed: Glaciera uncertified')"
```
Expected: `RED confirmed: Glaciera uncertified`.

- [ ] **Step 2: Write the batch driver**

```python
# scripts/pipeline/run_roster_fidelity.py
"""Batch driver: for each active roster target, run rig -> anim -> deformation capture -> write cert.
Mechs get decimated to a skinning mesh first. Fail-closed: a failed leg writes passed:false, never skips.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dimwit.pipelines import roster_fidelity as rf
from dimwit.pipelines.rigging import RiggingPipeline, ASSET_FOR, STAGING_SYM, ROOT, BLENDER
from dimwit.pipelines.animation import AnimationPipeline

DECIM = ROOT / "blender_scripts" / "decimate_for_skinning.py"
STAGING_NEW = ROOT / "artifacts" / "ue_staging_new"


def _decimate_if_mech(target: dict) -> None:
    if target["kind"] != "mech":
        return
    out = STAGING_SYM / f"{target['asset']}.glb"
    if out.exists():
        return
    src = STAGING_NEW / f"{target['asset']}.glb"
    subprocess.run([str(BLENDER), "--background", "--python", str(DECIM), "--",
                    f"in={src}", f"out={out}", "target_tris=45000"],
                   capture_output=True, text=True, timeout=1200)


def run_one(key: str) -> dict:
    target = next(t for t in rf.active_roster_targets() if t["key"] == key)
    _decimate_if_mech(target)
    rig = RiggingPipeline()
    rig_art = rig.run({"asset_id": key})                 # ProductionPipeline.run -> PipelineResult
    anim = AnimationPipeline()
    anim_art = anim.run({"asset_id": key})

    # A BLOCKED run (missing mesh/tool) has verdict=None — record it fail-closed, never crash.
    class _Blocked:
        passed = False
        issues = ["pipeline BLOCKED (no verdict) — see ledger"]
    rig_v = rig_art.verdict or _Blocked()
    anim_v = anim_art.verdict or _Blocked()
    rig_data = (rig_art.artifact.data if rig_art.artifact else {}) or {}
    deform_verdict = RiggingPipeline.deformation_verdict(rig_data)
    cert = rf.write_cert(
        asset=target["asset"], kind=target["kind"],
        rig_result={"passed": bool(rig_v.passed), "issues": rig_v.issues},
        anim_result={"passed": bool(anim_v.passed), "issues": anim_v.issues},
        deform_result={"passed": bool(deform_verdict["passed"]),
                       "score": deform_verdict.get("deformation_score"),
                       "worst_pose": deform_verdict.get("worst_pose")},
    )
    return rf.validate_cert(cert)


def run_all() -> dict:
    return {t["key"]: run_one(t["key"]) for t in rf.active_roster_targets()}


if __name__ == "__main__":
    keys = sys.argv[1:] or [t["key"] for t in rf.active_roster_targets()]
    out = {k: run_one(k) for k in keys}
    print(json.dumps(out, indent=2))
```

Note: confirm `ProductionPipeline.run(...)` returns an object exposing `.artifact` and `.verdict`. If the base API differs, adapt `run_one` to call `plan`/`execute`/`qa` directly — check `dimwit/pipelines/base.py` before running. Do NOT invent an API; match `base.py`.

- [ ] **Step 3: Run the pilot on Glaciera (foreground — UE deformation capture renders)**

Run:
```bash
cd C:/Users/developer/Documents/Dimwit && python scripts/pipeline/run_roster_fidelity.py mech_01_glaciera
```
Expected: JSON `{"mech_01_glaciera": {"passed": true, "issues": []}}`.
If deformation fails, inspect `artifacts/roster_fidelity/SM_Char_Mech_01_Glaciera.json` and the worst-pose PNG under `artifacts/pose_capture/` before scaling.

- [ ] **Step 4: Eyeball the rigid rig + confirm rig.json**

Run:
```bash
python -c "import json; d=json.load(open('artifacts/rig/SM_Char_Mech_01_Glaciera_rigged.fbx.rig.json')); assert d['skinning_mode']=='rigid_single_bone' and d['max_influences']==1 and d['weight_coverage']>0.99, d; print('rigid OK', d['weight_coverage'])"
```
Expected: `rigid OK <coverage>`.
Then open the newest capture under `artifacts/pose_capture/` and confirm no cloth-stretch or exploded plates. If joint gaps are unacceptable, STOP and escalate (hybrid rigid+sleeve, per spec risk section) before Task 7.

- [ ] **Step 5: GREEN + commit**

Run:
```bash
python -c "from dimwit.pipelines.roster_fidelity import roster_fidelity_coverage as c; print('Glaciera covered:', 'SM_Char_Mech_01_Glaciera' in c()['covered'])"
```
Expected: `Glaciera covered: True`.

```bash
git add scripts/pipeline/run_roster_fidelity.py artifacts/roster_fidelity/SM_Char_Mech_01_Glaciera.json
git commit -m "feat(roster-fidelity): pilot Glaciera rig+anim+deformation cert (mech track proven)"
```

---

### Task 7: Batch the remaining 7 mechs

**Files:** none new (uses `scripts/pipeline/run_roster_fidelity.py`).

- [ ] **Step 1: Run the 7 mechs**

Run:
```bash
cd C:/Users/developer/Documents/Dimwit && python scripts/pipeline/run_roster_fidelity.py \
  mech_02_voidrunner mech_03_aurelion mech_04_luxorion mech_05_pyroclast \
  mech_06_jadewind mech_07_ironline mech_08_nightwire
```
Expected: JSON with `"passed": true` for all 7.

- [ ] **Step 2: Verify all 8 mechs covered**

Run:
```bash
python -c "from dimwit.pipelines.roster_fidelity import roster_fidelity_coverage as c; r=c(); mechs=[a for a in r['covered'] if 'Mech' in a]; assert len(mechs)==8, r['missing']; print('8 mechs covered')"
```
Expected: `8 mechs covered`.

- [ ] **Step 3: Commit**

```bash
git add artifacts/roster_fidelity/SM_Char_Mech_0*.json
git commit -m "feat(roster-fidelity): certify remaining 7 mechs"
```

---

### Task 8: Certify the 6 active humanoids

**Files:** none new.

- [ ] **Step 1: Run the 6 humanoids**

Run:
```bash
cd C:/Users/developer/Documents/Dimwit && python scripts/pipeline/run_roster_fidelity.py \
  zythan qorin therak ullio kelous nexor
```
Expected: JSON with `"passed": true` for all 6. (Machinery already proven on ekris; humanoids reuse the smooth-weight path.)

- [ ] **Step 2: Verify full 14 coverage**

Run:
```bash
python -c "from dimwit.pipelines.roster_fidelity import roster_fidelity_coverage as c; r=c(); assert r['passed'], r['missing']; print('14/14 roster certified')"
```
Expected: `14/14 roster certified`.

- [ ] **Step 3: Commit**

```bash
git add artifacts/roster_fidelity/SM_Char_0*.json
git commit -m "feat(roster-fidelity): certify 6 active humanoids — full 14/14 roster"
```

---

### Task 9: Suite validators — character_roster_fidelity domain

**Files:**
- Modify: `dimwit/pipelines/validation_registry.py` (add validator fns near the other char validators; register in `build_registry` after the `A = "animation_wiring"` block near `:3866`)
- Test: `tests/test_roster_fidelity_registry.py`

**Interfaces:**
- Consumes: `roster_fidelity.active_roster_targets`, `load_cert`, `validate_cert`, `roster_fidelity_coverage`.
- Produces: one `Validator` per active target (14) named `roster_fidelity_<asset>` + one `roster_fidelity_coverage` validator, all domain `character_roster_fidelity`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roster_fidelity_registry.py
from dimwit.pipelines.validation_registry import build_registry


def test_registry_has_roster_fidelity_domain():
    reg = build_registry()
    rf = [v for v in reg if getattr(v, "domain", None) == "character_roster_fidelity"]
    ids = {v.id for v in rf}   # Validator's identifier field is `id`, not `name`
    assert "roster_fidelity_coverage" in ids
    # 14 per-char + 1 coverage
    assert len(rf) == 15, sorted(ids)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_roster_fidelity_registry.py -v`
Expected: FAIL — no `character_roster_fidelity` domain validators.

- [ ] **Step 3: Add validator fns + register**

Near the other character validators in `validation_registry.py` (after the rig/anim fns, before `build_registry`), add:

```python
# ============================================================ roster fidelity (14-char rig+anim+deform cert)
from dimwit.pipelines import roster_fidelity as _rfid


def _v_roster_fidelity_char(asset: str):
    def _fn(ctx):
        try:
            cert = _rfid.load_cert(asset)
        except BlockedError as e:
            return fail(issues=[str(e)], hard=True)
        result = _rfid.validate_cert(cert)
        if not result["passed"]:
            return fail(issues=result["issues"],
                        score=(cert.get("deformation") or {}).get("score") or 0.0)
        return ok(score=(cert.get("deformation") or {}).get("score") or 1.0,
                  kind=cert.get("kind"))
    _fn.__name__ = f"v_roster_fidelity_{asset}"
    return _fn


def v_roster_fidelity_coverage(ctx):
    cov = _rfid.roster_fidelity_coverage()
    if not cov["passed"]:
        return fail(issues=[f"active roster not fully certified; missing: {cov['missing']}"] + cov["issues"],
                    hard=True)
    return ok(covered=len(cov["covered"]))
```

In `build_registry`, after the `A = "animation_wiring"` block (ends near line 3866), add:

```python
    RF = "character_roster_fidelity"
    for t in _rfid.active_roster_targets():
        reg.append(Validator(f"roster_fidelity_{t['asset']}", RF, P.STATIC, S.BLOCKER,
                             f"artifacts/roster_fidelity/{t['asset']}.json",
                             "roster character shipped without a rig+anim+deformation cert",
                             _v_roster_fidelity_char(t["asset"])))
    reg.append(Validator("roster_fidelity_coverage", RF, P.STATIC, S.BLOCKER,
                         "artifacts/roster_fidelity/*.json vs active roster",
                         "an active roster character silently uncertified for rig+anim+deformation",
                         v_roster_fidelity_coverage))
```

Add the `_rfid` import at the top of the file with the other `dimwit.pipelines` imports if the inline import above is not preferred; either is fine as long as it imports once.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_roster_fidelity_registry.py -v`
Expected: 1 passed (15 validators).

- [ ] **Step 5: Commit**

```bash
git add dimwit/pipelines/validation_registry.py tests/test_roster_fidelity_registry.py
git commit -m "feat(suite): character_roster_fidelity domain — 14 per-char certs + coverage gate"
```

---

### Task 10: Full-suite green landing + push

**Files:** none new. Follow the recorded green-landing runbook.

- [ ] **Step 1: Run the full validation suite**

Run: `cd C:/Users/developer/Documents/Dimwit && python scripts/pipeline/run_validation.py`
Expected: the new `character_roster_fidelity` domain is GREEN (15 validators PASS). Note any freshness-decayed lanes to refresh (background-safe first; combat/perf lane LAST to preserve `[WaneFX]` markers — see memory `wanefall-p0-bundles-20260701`).

- [ ] **Step 2: self_metrics tail to exit-0**

Run the recorded tail: `scripts/pipeline/run_validation.py` → `self_metrics_director` → `scripts/pipeline/run_validation.py`, confirming `recomputed == stored` and exit-0 with zero non-pass. (Same sequence as the audio green landing.)

- [ ] **Step 3: Run the full pytest suite**

Run: `python -m pytest -q`
Expected: all green, count increased by the new tests (roster_fidelity, rigging_roster, animation_roster, roster_fidelity_registry).

- [ ] **Step 4: Push both repos**

```bash
git -C C:/Users/developer/Documents/Dimwit push origin HEAD
git -C "C:/Users/developer/Documents/Unreal Projects/WanefallGreybox" push origin HEAD
```
(WanefallGreybox push carries the new rigged mech `_Rig` uassets + skinning glbs as incremental LFS objects — small, passes the classifier.)

- [ ] **Step 5: Record the landing in memory**

Update `C:/Users/developer/.claude/projects/C--/memory/wanefall-p0-bundles-20260701.md` with the ROSTER_FIDELITY_V1 landing: 14/14 certified, suite total, both pushes, and any mech-specific finding (rigid-weight joint behavior). Add MEMORY.md pointer if a new file is warranted.
