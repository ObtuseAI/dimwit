"""Dimwit: create ekris_mat at CharactersRigged/ — the missing per-character material instance.

Duplicates MI_Default_Opaque (the glTF neutral base, same as all 7 other roster chars), then wires
the already-imported Ekris textures (albedo/normal/AO) and scalar params (Metallic=0, Roughness=0.5).
Assigns the material to all SkeletalMesh slots on SM_Char_02_ekris_Rig so in-game the character
displays its silver+orange-accent look instead of falling back to generic pbr_material.

Writes artifacts/create_ekris_mat_result.json.

Run:
  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_create_ekris_mat.py" -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

RES     = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/create_ekris_mat_result.json")
DEST    = "/Game/Wanefall/Dimwit/CharactersRigged"
MAT     = f"{DEST}/ekris_mat"
TEX     = f"{DEST}/Textures"
GLTF    = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
RIG     = f"{DEST}/SM_Char_02_ekris_Rig"

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal   = unreal.EditorAssetLibrary
mel   = unreal.MaterialEditingLibrary
out   = {"ok": False, "mat": MAT}

try:
    # 1) Create ekris_mat by duplicating the glTF neutral base (same parent as vorlax_mat, zythan_mat, etc.)
    if eal.does_asset_exist(MAT):
        unreal.log(f"[ekris_mat] already exists at {MAT}, re-wiring textures")
    else:
        if not eal.does_asset_exist(GLTF):
            out["error"] = f"Base material not found: {GLTF}"
            raise RuntimeError(out["error"])
        eal.duplicate_asset(GLTF, MAT)
        unreal.log(f"[ekris_mat] duplicated {GLTF} -> {MAT}")
    out["mat_created"] = eal.does_asset_exist(MAT)

    mic = unreal.load_asset(MAT)
    if not isinstance(mic, unreal.MaterialInstanceConstant):
        out["error"] = f"MAT is not a MaterialInstanceConstant: {type(mic)}"
        raise RuntimeError(out["error"])
    out["mat_type"] = type(mic).__name__

    # 2) Load the already-imported Ekris textures
    alb_path = f"{TEX}/SM_Char_02_ekris_Rig_albedo"
    nrm_path = f"{TEX}/SM_Char_02_ekris_Rig_normal"
    ao_path  = f"{TEX}/SM_Char_02_ekris_Rig_ao"

    alb = unreal.load_asset(alb_path) if eal.does_asset_exist(alb_path) else None
    nrm = unreal.load_asset(nrm_path) if eal.does_asset_exist(nrm_path) else None
    ao  = unreal.load_asset(ao_path)  if eal.does_asset_exist(ao_path)  else None

    out["alb_found"] = isinstance(alb, unreal.Texture2D)
    out["nrm_found"] = isinstance(nrm, unreal.Texture2D)
    out["ao_found"]  = isinstance(ao,  unreal.Texture2D)
    unreal.log(f"[ekris_mat] textures: alb={out['alb_found']} nrm={out['nrm_found']} ao={out['ao_found']}")

    # 3) Wire texture parameters (matching the exact param names used by scripts/ue/ue_import_handcrafted_rig.py)
    if isinstance(alb, unreal.Texture2D):
        mel.set_material_instance_texture_parameter_value(mic, "BaseColorTexture", alb)
        out["alb_wired"] = True
    if isinstance(nrm, unreal.Texture2D):
        for pname in ("NormalTexture", "Normal"):
            try:
                mel.set_material_instance_texture_parameter_value(mic, pname, nrm)
                out["nrm_wired"] = pname
                break
            except Exception:
                continue
    if isinstance(ao, unreal.Texture2D):
        for pname in ("OcclusionTexture", "AOTexture", "AmbientOcclusionTexture", "ORMTexture"):
            try:
                mel.set_material_instance_texture_parameter_value(mic, pname, ao)
                out["ao_wired"] = pname
                break
            except Exception:
                continue

    # 4) Scalar params: metallic=0 (de-chrome), roughness=0.5 (satin)
    for nm, val in (("Metallic", 0.0), ("Roughness", 0.5), ("Specular", 0.5)):
        try:
            mel.set_material_instance_scalar_parameter_value(mic, nm, val)
        except Exception:
            pass

    try:
        mel.update_material_instance(mic)
    except Exception:
        pass
    eal.save_asset(MAT)
    out["mat_saved"] = True

    # 5) Assign to all SkeletalMesh slots on SM_Char_02_ekris_Rig
    rmesh = unreal.load_asset(RIG) if eal.does_asset_exist(RIG) else None
    if isinstance(rmesh, unreal.SkeletalMesh):
        mats = rmesh.materials
        for i in range(len(mats)):
            mats[i] = unreal.SkeletalMaterial(material_interface=mic)
        rmesh.set_editor_property("materials", mats)
        eal.save_asset(RIG)
        out["rig_mat_assigned"] = True
        out["rig_slots"] = len(mats)
    else:
        out["rig_mat_assigned"] = False
        out["rig_note"] = f"rig not a SkeletalMesh: {type(rmesh)}"

    out["ok"] = out.get("mat_created") and isinstance(mic, unreal.MaterialInstanceConstant) and out.get("alb_wired")

except Exception:
    out["error"] = traceback.format_exc()

RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log(f"DIMWIT_CREATE_EKRIS_MAT_DONE ok={out.get('ok')}")
