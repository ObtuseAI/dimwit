"""Dimwit de-chrome: the Hi3D glTF character materials inherit MetallicFactor=1.0 (MI_Default_Opaque parent) and
are driven fully-metallic by their MetallicRoughnessTexture, so the armor mirrors the environment and blows out
to a chrome/grey blob ("overglowing"). Fix = override the metallic scalar to ~0 on each character MIC (keeps the
base-color + roughness texture detail; just stops the mirror). The right lever per fix_kit_material doctrine.

Default: Ekris only (the hold character). Pass --all to batch every SM_Char_* (alien soldiers + mechs).
Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/dechrome_char_material.py" [-- --all]
"""
import unreal, json, traceback, sys
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/dechrome_result.json")
CHARS_ROOT = "/Game/Wanefall/Dimwit/Characters"
EKRIS_MIC = f"{CHARS_ROOT}/SM_Char_02_ekris/Materials/pbr_material"
# Metallic balance: 0.0 = flat clay (no metal read in flat light), 1.0 = chrome mirror (blows out under a key).
# ~0.45 = satin metal: reflects a gentle key as silver highlights that reveal the armor, without mirroring.
# Override with:  -ExecutePythonScript=... then a trailing  metallic=0.45  token in argv (we parse it below).
METALLIC_TARGET = 0.45
for _a in sys.argv:
    if _a.startswith("metallic="):
        try:
            METALLIC_TARGET = float(_a.split("=", 1)[1])
        except ValueError:
            pass

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

def dechrome(mic_path):
    rec = {"path": mic_path}
    mic = unreal.load_asset(mic_path)
    if not isinstance(mic, unreal.MaterialInstanceConstant):
        rec["skip"] = f"not a MIC ({type(mic).__name__ if mic else 'None'})"
        return rec
    base = mic.get_base_material()
    names = [str(n) for n in mel.get_scalar_parameter_names(base)] if base else []
    rec["base"] = base.get_path_name() if base else None
    rec["scalar_param_names"] = names
    applied = {}
    for n in names:
        if n.lower() == "metallicfactor":   # exact: never touch *Texture_Rotation/_TexCoord
            mel.set_material_instance_scalar_parameter_value(mic, n, METALLIC_TARGET)
            applied[n] = METALLIC_TARGET
    rec["applied"] = applied
    try:
        mel.update_material_instance(mic)
    except Exception:
        pass
    eal.save_asset(mic_path)
    rec["ok"] = bool(applied)
    return rec

res = {"ok": False, "records": []}
try:
    do_all = "--all" in sys.argv
    if do_all:
        targets = []
        for a in eal.list_assets(CHARS_ROOT, recursive=True, include_folder=False):
            if a.rstrip("/").endswith("pbr_material") or "/Materials/" in a:
                obj = unreal.load_asset(a)
                if isinstance(obj, unreal.MaterialInstanceConstant):
                    targets.append(a.split(".")[0])
        targets = sorted(set(targets))
    else:
        targets = [EKRIS_MIC]
    res["targets"] = targets
    for t in targets:
        res["records"].append(dechrome(t))
    res["ok"] = all(r.get("ok") for r in res["records"]) if res["records"] else False
except Exception:
    res["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
unreal.log("RM_DECHROME_DONE ok=" + str(res["ok"]))
