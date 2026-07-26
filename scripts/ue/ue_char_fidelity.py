"""Dimwit CHARACTER-FIDELITY UE driver (canonical). For one character or all 8:
  1) import the FULL-detail Hi3D GLB as a NANITE static mesh (no decimation) replacing the asset in place,
  2) ensure the glTF base material has the Nanite usage flag (else Nanite renders the smooth fallback blob),
  3) de-chrome (MetallicFactor satin) — these Hi3D albedos are non-metallic + dark-for-studio,
  4) report STRUCTURAL metrics (honest proof the fix landed, no screenshot needed).

Run headless:
  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_char_fidelity.py [asset=SM_Char_02_ekris src=hi3d_02_ekris]"
  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_char_fidelity.py --all"
Result -> artifacts/char_fidelity_result.json
"""
import unreal, json, shutil, sys, traceback
from pathlib import Path

ART = Path(r"C:/Users/developer/Documents/Dimwit/artifacts")
STAGE = ART / "nanite_staging"
RESULT = ART / "char_fidelity_result.json"
CHARS = "/Game/Wanefall/Dimwit/Characters"
METALLIC_TARGET = 0.35

ROSTER = [
    ("hi3d_01_vorlax", "SM_Char_01_Vorlax"), ("hi3d_02_ekris", "SM_Char_02_ekris"),
    ("hi3d_03_zythan", "SM_Char_03_zythan"), ("hi3d_04_qorin", "SM_Char_04_qorin"),
    ("hi3d_05_therak", "SM_Char_05_therak"), ("hi3d_06_ullio", "SM_Char_06_ullio"),
    ("hi3d_07_kelous", "SM_Char_07_kelous"), ("hi3d_08_nexor", "SM_Char_08_nexor"),
]

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def set_nanite_flag(mat):
    for prop in ("used_with_nanite", "b_used_with_nanite"):
        try:
            mat.set_editor_property(prop, True)
            return prop
        except Exception:
            continue
    return None


def enable_nanite(mesh):
    try:
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if hasattr(sub, "set_nanite_enabled"):
            sub.set_nanite_enabled(mesh, True)
            return "subsystem"
    except Exception:
        pass
    try:
        ns = mesh.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        mesh.set_editor_property("nanite_settings", ns)
        return "property"
    except Exception:
        return None


def process(src_stem, asset, metallic=METALLIC_TARGET):
    rec = {"asset": asset, "src": src_stem, "ok": False}
    src_glb = ART / f"{src_stem}.glb"
    if not src_glb.exists():
        rec["error"] = f"source GLB missing: {src_glb}"
        return rec
    # clean any double-nested folder from a bad prior dest
    doubled = f"{CHARS}/{asset}/{asset}"
    if eal.does_directory_exist(doubled):
        eal.delete_directory(doubled)
        rec["cleaned_doubled"] = True
    # stage with the correct name so the imported asset name matches the C++/material path
    STAGE.mkdir(parents=True, exist_ok=True)
    staged = STAGE / f"{asset}.glb"
    shutil.copyfile(src_glb, staged)
    rec["src_size_mb"] = round(src_glb.stat().st_size / 1e6, 1)
    # import (dest = group folder; Interchange nests <dest>/<Asset>/StaticMeshes/<Asset>)
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", str(staged))
    t.set_editor_property("destination_path", CHARS)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    tools.import_asset_tasks([t])
    mesh_path = f"{CHARS}/{asset}/StaticMeshes/{asset}"
    mic_path = f"{CHARS}/{asset}/Materials/pbr_material"
    mesh = unreal.load_asset(mesh_path)
    if not isinstance(mesh, unreal.StaticMesh):
        rec["error"] = f"mesh not found after import: {mesh_path}"
        return rec
    rec["nanite_mode"] = enable_nanite(mesh)
    try:
        rec["nanite_enabled"] = mesh.get_editor_property("nanite_settings").get_editor_property("enabled")
        rec["fallback_tris"] = mesh.get_num_triangles(0)
    except Exception:
        pass
    eal.save_asset(mesh_path)
    # material: Nanite flag (on base) + de-chrome
    mic = unreal.load_asset(mic_path)
    if isinstance(mic, unreal.MaterialInstanceConstant):
        base = mic.get_base_material()
        if base:
            rec["nanite_flag_prop"] = set_nanite_flag(base)
            try:
                eal.save_asset(base.get_path_name())
                rec["nanite_flag_after"] = base.get_editor_property("used_with_nanite")
            except Exception as e:
                rec["flag_save_err"] = str(e)
            for n in mel.get_scalar_parameter_names(base):
                if str(n).lower() == "metallicfactor":
                    mel.set_material_instance_scalar_parameter_value(mic, str(n), metallic)
                    rec["metallic_set"] = metallic
        try:
            mel.update_material_instance(mic)
        except Exception:
            pass
        eal.save_asset(mic_path)
    # honest structural metrics
    try:
        from os.path import getsize
        uasset = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/Content/Wanefall/Dimwit/Characters") / asset / "StaticMeshes" / f"{asset}.uasset"
        rec["uasset_mb"] = round(uasset.stat().st_size / 1e6, 1) if uasset.exists() else None
    except Exception:
        pass
    rec["ok"] = bool(rec.get("nanite_enabled")) and bool(rec.get("nanite_flag_after"))
    return rec


def main():
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv if "=" in a}
    do_all = "--all" in sys.argv
    metallic = float(args.get("metallic", METALLIC_TARGET))
    out = {"records": []}
    try:
        if do_all:
            targets = ROSTER
        else:
            targets = [(args.get("src", "hi3d_02_ekris"), args.get("asset", "SM_Char_02_ekris"))]
        for src_stem, asset in targets:
            try:
                out["records"].append(process(src_stem, asset, metallic))
            except Exception:
                out["records"].append({"asset": asset, "src": src_stem, "ok": False,
                                       "error": traceback.format_exc()})
        out["ok_count"] = sum(1 for r in out["records"] if r.get("ok"))
        out["total"] = len(out["records"])
    except Exception:
        out["error"] = traceback.format_exc()
    RESULT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    unreal.log(f"DIMWIT_CHAR_FIDELITY_DONE ok={out.get('ok_count')}/{out.get('total')}")


main()
